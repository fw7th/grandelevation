import pytest


@pytest.mark.asyncio
async def test_signup_page_loads(client):
    r = await client.get("/signup")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_signup_creates_user_and_redirects(client):
    r = await client.post(
        "/signup",
        data={
            "username": "testuser",
            "email": "test@example.com",
            "password": "password123",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/catalog"


@pytest.mark.asyncio
async def test_signin_with_bad_password_shows_error(client):
    # create user first
    await client.post(
        "/signup",
        data={
            "username": "testuser2",
            "email": "test2@example.com",
            "password": "password123",
        },
    )
    r = await client.post(
        "/signin",
        data={
            "email": "test2@example.com",
            "password": "wrongpassword",
        },
    )
    assert r.status_code == 200
    assert "Invalid email or password" in r.text


@pytest.mark.asyncio
async def test_catalog_is_public(client):
    r = await client.get("/catalog")
    assert r.status_code == 200
