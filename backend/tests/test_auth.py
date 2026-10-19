from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update

from app.core.config import settings
from app.core.security import hash_refresh_token
from app.models import RefreshToken, User

EMAIL = "user@example.com"
PASSWORD = "correct-horse-battery"


async def register(client, email=EMAIL, password=PASSWORD):
    return await client.post("/api/v1/auth/register", json={"email": email, "password": password})


async def login(client, email=EMAIL, password=PASSWORD):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def register_and_login(client) -> str:
    """Returns the access token. The refresh cookie is kept in the client."""
    await register(client)
    response = await login(client)
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def refresh_with(client, raw_token: str):
    # An explicit Cookie header wins over the client's cookie jar, so we choose the token.
    return await client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={raw_token}"}
    )


# ---------- register ----------


async def test_register_returns_user_without_password(client):
    response = await register(client)
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "created_at"}
    assert body["email"] == EMAIL


async def test_register_normalizes_email_and_rejects_duplicates(client):
    first = await register(client, email="Mixed@Example.com")
    assert first.status_code == 201
    assert first.json()["email"] == "mixed@example.com"

    second = await register(client, email="MIXED@example.com")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "email_taken"


async def test_register_rejects_short_password_without_echoing_it(client):
    response = await register(client, password="abc1234")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "abc1234" not in response.text


async def test_register_rejects_invalid_email(client):
    response = await register(client, email="not-an-email")
    assert response.status_code == 422


# ---------- login ----------


async def test_login_returns_token_and_secure_cookie(client):
    await register(client)
    response = await login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.access_token_minutes * 60

    cookie = response.headers["set-cookie"].lower()
    assert "refresh_token=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/api/v1/auth" in cookie


async def test_login_failures_look_identical(client):
    await register(client)
    wrong_password = await login(client, password="wrong-password-123")
    unknown_email = await login(client, email="nobody@example.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["error"]["code"] == "invalid_credentials"


# ---------- me ----------


async def test_me_requires_a_token(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


async def test_me_rejects_a_garbage_token(client):
    response = await client.get("/api/v1/auth/me", headers=auth_header("garbage"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


async def test_me_returns_the_current_user(client):
    token = await register_and_login(client)
    response = await client.get("/api/v1/auth/me", headers=auth_header(token))
    assert response.status_code == 200
    assert response.json()["email"] == EMAIL


async def test_me_rejects_a_token_of_a_deleted_user(client, db_session):
    token = await register_and_login(client)
    await db_session.execute(delete(User))
    await db_session.commit()

    response = await client.get("/api/v1/auth/me", headers=auth_header(token))
    assert response.status_code == 401


# ---------- refresh ----------


async def test_refresh_rotates_the_token(client, db_session):
    await register_and_login(client)
    old_raw = client.cookies.get("refresh_token")

    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    new_raw = client.cookies.get("refresh_token")
    assert new_raw and new_raw != old_raw

    # The new access token works.
    me = await client.get("/api/v1/auth/me", headers=auth_header(response.json()["access_token"]))
    assert me.status_code == 200

    # The old refresh token is now revoked in the database.
    old_row = await db_session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(old_raw))
    )
    assert old_row.revoked_at is not None


async def test_refresh_without_cookie_fails(client):
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"


async def test_reused_refresh_token_revokes_every_session(client):
    await register_and_login(client)
    old_raw = client.cookies.get("refresh_token")

    assert (await client.post("/api/v1/auth/refresh")).status_code == 200
    new_raw = client.cookies.get("refresh_token")

    # Presenting the already-used token looks like theft...
    assert (await refresh_with(client, old_raw)).status_code == 401
    # ...so even the newest token is dead now.
    assert (await refresh_with(client, new_raw)).status_code == 401


async def test_expired_refresh_token_is_rejected(client, db_session):
    await register_and_login(client)
    await db_session.execute(
        update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.commit()

    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


# ---------- logout ----------


async def test_logout_revokes_the_refresh_token(client):
    await register_and_login(client)
    raw = client.cookies.get("refresh_token")

    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()

    assert (await refresh_with(client, raw)).status_code == 401


async def test_logout_without_a_cookie_is_fine(client):
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 204


# ---------- storage ----------


async def test_refresh_tokens_are_stored_hashed(client, db_session):
    await register_and_login(client)
    raw = client.cookies.get("refresh_token")

    rows = (await db_session.scalars(select(RefreshToken))).all()
    assert len(rows) == 1
    assert rows[0].token_hash != raw
    assert rows[0].token_hash == hash_refresh_token(raw)
