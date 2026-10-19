import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def make_token(key: str | None = settings.jwt_secret, algorithm: str = "HS256", **overrides):
    """Builds a token by hand, so tests can create broken ones."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    payload.update(overrides)
    return jwt.encode(payload, key, algorithm=algorithm)


def test_password_hash_verifies():
    password_hash = hash_password("correct-horse-battery")
    assert password_hash != "correct-horse-battery"
    assert verify_password("correct-horse-battery", password_hash) is True


def test_wrong_password_fails():
    password_hash = hash_password("correct-horse-battery")
    assert verify_password("wrong-password", password_hash) is False


def test_same_password_gives_different_hashes():
    # Each hash has its own random salt.
    assert hash_password("same-password") != hash_password("same-password")


def test_unreadable_hash_returns_false_instead_of_crashing():
    assert verify_password("anything", "not-a-real-hash") is False


def test_access_token_round_trip():
    user_id = uuid4()
    assert decode_access_token(create_access_token(user_id)) == user_id


def test_expired_access_token_is_rejected():
    token = make_token(exp=datetime.now(UTC) - timedelta(minutes=1))
    with pytest.raises(AppError) as error:
        decode_access_token(token)
    assert error.value.status_code == 401


def test_token_signed_with_another_secret_is_rejected():
    token = make_token(key="a-different-secret-that-is-at-least-32-chars")
    with pytest.raises(AppError):
        decode_access_token(token)


def test_unsigned_token_is_rejected():
    # The classic "alg: none" attack must not work.
    token = make_token(key=None, algorithm="none")
    with pytest.raises(AppError):
        decode_access_token(token)


def test_token_of_the_wrong_type_is_rejected():
    with pytest.raises(AppError):
        decode_access_token(make_token(type="refresh"))


def test_refresh_token_helpers():
    first, second = generate_refresh_token(), generate_refresh_token()
    assert first != second
    stored = hash_refresh_token(first)
    assert len(stored) == 64
    assert stored == hashlib.sha256(first.encode()).hexdigest()
