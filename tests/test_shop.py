import pytest
from sqlmodel import select

from app.models import CartItem, Product, User

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
    db_session, name="Test Panel", price=50000.0, category="solar_panel", image_url=None
):
    product = Product(name=name, price=price, category=category, image_url=image_url)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
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
