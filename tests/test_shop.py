from datetime import datetime, timedelta

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import CartItem, Product, Users

# ─── helpers ──────────────────────────────────────────


async def _signup_user(client, username="shopuser", email="shop@example.com"):
    await client.post(
        "/signup",
        data={
            "username": username,
            "email": email,
            "password": "password123",
        },
        follow_redirects=False,
    )


async def _seed_product(
    engine,
    name="Test Panel",
    price=50000.0,
    category="solar_panel",
    image_url=None,
    description="A test product",
):
    async with AsyncSession(engine) as session:
        product = Product(
            name=name,
            price=price,
            category=category,
            image_url=image_url,
            description=description,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)
        return product


# ─── auth guards ──────────────────────────────────────


@pytest.mark.asyncio
async def test_cart_redirects_when_not_authenticated(client):
    r = await client.get("/cart", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/catalog"


@pytest.mark.asyncio
async def test_cart_add_redirects_when_not_authenticated(client):
    r = await client.post(
        "/cart/add",
        data={"product_id": 1, "quantity": 1},
        follow_redirects=False,
    )
    assert r.status_code == 307
    assert r.headers["location"] == "/catalog"


@pytest.mark.asyncio
async def test_cart_remove_redirects_when_not_authenticated(client):
    r = await client.post(
        "/cart/remove",
        data={"cart_item_id": 1},
        follow_redirects=False,
    )
    assert r.status_code == 307
    assert r.headers["location"] == "/catalog"


@pytest.mark.asyncio
async def test_cart_update_redirects_when_not_authenticated(client):
    r = await client.post(
        "/cart/update",
        data={"cart_item_id": 1, "delta": 1},
        follow_redirects=False,
    )
    assert r.status_code == 307
    assert r.headers["location"] == "/catalog"


@pytest.mark.asyncio
async def test_account_redirects_when_not_authenticated(client):
    r = await client.get("/account", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/catalog"


# ─── cart read ────────────────────────────────────────


@pytest.mark.asyncio
async def test_cart_empty_for_authenticated_user(client):
    await _signup_user(client)
    r = await client.get("/cart")
    assert r.status_code == 200
    assert "Your cart is empty" in r.text


@pytest.mark.asyncio
async def test_cart_shows_item_and_computes_totals(client, engine):
    await _signup_user(client)
    product = await _seed_product(engine, price=25000.0)

    await client.post(
        "/cart/add",
        data={"product_id": product.id, "quantity": 3},
        follow_redirects=False,
    )

    r = await client.get("/cart")
    assert r.status_code == 200
    assert product.name in r.text
    # 3 × 25,000 = 75,000
    assert "75,000.00" in r.text


@pytest.mark.asyncio
async def test_cart_lifo_ordering(client, engine):
    await _signup_user(client)
    p1 = await _seed_product(engine, name="Panel A", price=100.0)
    p2 = await _seed_product(engine, name="Panel B", price=200.0)

    await client.post(
        "/cart/add", data={"product_id": p1.id, "quantity": 1}, follow_redirects=False
    )
    await client.post(
        "/cart/add", data={"product_id": p2.id, "quantity": 1}, follow_redirects=False
    )

    r = await client.get("/cart")
    text = r.text
    # LIFO: most recently added (p2) should appear first
    assert text.index("Panel B") < text.index("Panel A")


# ─── cart add ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_cart_add_creates_item_and_sets_added_param(client, engine):
    await _signup_user(client)
    product = await _seed_product(engine)

    r = await client.post(
        "/cart/add",
        data={"product_id": product.id, "quantity": 2},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"] == f"/cart?added={product.id}"

    async with AsyncSession(engine) as session:
        result = await session.exec(select(CartItem))
        items = result.all()
        assert len(items) == 1
        assert items[0].quantity == 2
        assert items[0].product_id == product.id


# ─── cart remove ──────────────────────────────────────


@pytest.mark.asyncio
async def test_cart_remove_deletes_item(client, engine):
    await _signup_user(client)
    product = await _seed_product(engine)

    await client.post(
        "/cart/add",
        data={"product_id": product.id, "quantity": 1},
        follow_redirects=False,
    )

    async with AsyncSession(engine) as session:
        result = await session.exec(select(CartItem))
        cart_item = result.first()

    r = await client.post(
        "/cart/remove",
        data={"cart_item_id": cart_item.id},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"] == "/cart"

    async with AsyncSession(engine) as session:
        result = await session.exec(select(CartItem))
        assert len(result.all()) == 0


@pytest.mark.asyncio
async def test_cart_remove_ignores_other_users_item(client, engine):
    # User A creates item
    await _signup_user(client, username="usera", email="a@example.com")
    product = await _seed_product(engine)
    await client.post(
        "/cart/add",
        data={"product_id": product.id, "quantity": 1},
        follow_redirects=False,
    )

    async with AsyncSession(engine) as session:
        result = await session.exec(select(CartItem))
        item_a = result.first()

    # User B tries to delete it
    client.cookies.clear()
    await _signup_user(client, username="userb", email="b@example.com")

    r = await client.post(
        "/cart/remove",
        data={"cart_item_id": item_a.id},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"] == "/cart"

    # Item A still exists
    async with AsyncSession(engine) as session:
        result = await session.exec(select(CartItem))
        assert len(result.all()) == 1


# ─── cart update (delta) ──────────────────────────────


@pytest.mark.asyncio
async def test_cart_update_increases_quantity(client, engine):
    await _signup_user(client)
    product = await _seed_product(engine)

    await client.post(
        "/cart/add",
        data={"product_id": product.id, "quantity": 1},
        follow_redirects=False,
    )

    async with AsyncSession(engine) as session:
        result = await session.exec(select(CartItem))
        cart_item = result.first()

    r = await client.post(
        "/cart/update",
        data={"cart_item_id": cart_item.id, "delta": 1},
        follow_redirects=False,
    )
    assert r.status_code == 302

    async with AsyncSession(engine) as session:
        result = await session.exec(select(CartItem).where(CartItem.id == cart_item.id))
        refreshed = result.first()
        assert refreshed.quantity == 2


@pytest.mark.asyncio
async def test_cart_update_decreases_quantity(client, engine):
    await _signup_user(client)
    product = await _seed_product(engine)

    await client.post(
        "/cart/add",
        data={"product_id": product.id, "quantity": 3},
        follow_redirects=False,
    )

    async with AsyncSession(engine) as session:
        result = await session.exec(select(CartItem))
        cart_item = result.first()

    r = await client.post(
        "/cart/update",
        data={"cart_item_id": cart_item.id, "delta": -1},
        follow_redirects=False,
    )
    assert r.status_code == 302

    async with AsyncSession(engine) as session:
        result = await session.exec(select(CartItem).where(CartItem.id == cart_item.id))
        refreshed = result.first()
        assert refreshed.quantity == 2


@pytest.mark.asyncio
async def test_cart_update_deletes_when_quantity_zero(client, engine):
    await _signup_user(client)
    product = await _seed_product(engine)

    await client.post(
        "/cart/add",
        data={"product_id": product.id, "quantity": 1},
        follow_redirects=False,
    )

    async with AsyncSession(engine) as session:
        result = await session.exec(select(CartItem))
        cart_item = result.first()

    r = await client.post(
        "/cart/update",
        data={"cart_item_id": cart_item.id, "delta": -1},
        follow_redirects=False,
    )
    assert r.status_code == 302

    async with AsyncSession(engine) as session:
        result = await session.exec(select(CartItem))
        assert len(result.all()) == 0


@pytest.mark.asyncio
async def test_cart_update_ignores_other_users_item(client, engine):
    await _signup_user(client, username="usera", email="a@example.com")
    product = await _seed_product(engine)
    await client.post(
        "/cart/add",
        data={"product_id": product.id, "quantity": 5},
        follow_redirects=False,
    )

    async with AsyncSession(engine) as session:
        result = await session.exec(select(CartItem))
        item_a = result.first()

    client.cookies.clear()
    await _signup_user(client, username="userb", email="b@example.com")

    r = await client.post(
        "/cart/update",
        data={"cart_item_id": item_a.id, "delta": -1},
        follow_redirects=False,
    )
    assert r.status_code == 302

    async with AsyncSession(engine) as session:
        result = await session.exec(select(CartItem).where(CartItem.id == item_a.id))
        refreshed = result.first()
        assert refreshed.quantity == 5


# ─── account ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_account_page_loads_for_authenticated_user(client):
    await _signup_user(client)
    r = await client.get("/account")
    assert r.status_code == 200
    assert "shopuser" in r.text


@pytest.mark.asyncio
async def test_profile_update_persists_changes(client, engine):
    await _signup_user(client)

    # Bypass the 3-hour rate limit by setting updated_at to 4 hours ago
    async with AsyncSession(engine) as session:
        result = await session.exec(
            select(Users).where(Users.email == "shop@example.com")
        )
        user = result.first()
        user.updated_at = datetime.utcnow() - timedelta(hours=4)
        await session.commit()

    r = await client.post(
        "/account/profile",
        data={
            "username": "newname",
            "email": "new@example.com",
            "phone": "08012345678",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/account?updated=1"

    async with AsyncSession(engine) as session:
        result = await session.exec(
            select(Users).where(Users.email == "new@example.com")
        )
        user = result.first()
        assert user is not None
        assert user.username == "newname"
