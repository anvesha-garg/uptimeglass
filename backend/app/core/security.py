"""Password hashing, access tokens (JWT) and refresh tokens."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings
from app.core.errors import AppError

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"

# Tests create many users, so they use the cheapest argon2 settings. Real runs use the
# library's recommended defaults. The settings are stored inside each hash, so verifying
# works whichever settings created it.
_hasher = (
    PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    if settings.env == "test"
    else PasswordHasher()
)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        # Wrong password, or a hash we cannot read: either way it is "no".
        return False


# Login verifies against this when the email is unknown, so a missing user takes the same
# time as a wrong password and the response time does not reveal which emails exist.
DUMMY_HASH = hash_password("not-a-real-password")


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> UUID:
    """Return the user id inside a valid access token, or raise a 401 AppError."""
    try:
        # algorithms=[...] is required: it blocks "alg: none" and algorithm-swap attacks.
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        if payload.get("type") != ACCESS_TOKEN_TYPE:
            raise jwt.InvalidTokenError("wrong token type")
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError):
        raise AppError(401, "invalid_token", "Invalid or expired access token.") from None


def generate_refresh_token() -> str:
    # 48 random bytes: impossible to guess, so a fast hash is enough to store it safely.
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
