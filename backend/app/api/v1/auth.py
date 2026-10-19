"""Register, login, refresh, logout and "who am I" endpoints."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.errors import AppError
from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
# The browser sends this cookie only to the auth endpoints, never to other API routes.
REFRESH_COOKIE_PATH = "/api/v1/auth"


def invalid_refresh_token() -> AppError:
    return AppError(401, "invalid_refresh_token", "Invalid or expired refresh token.")


def set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw_token,
        max_age=settings.refresh_token_days * 24 * 3600,
        httponly=True,  # JavaScript cannot read it
        secure=settings.env == "production",  # plain http locally cannot send secure cookies
        samesite="lax",  # other sites cannot trigger a refresh
        path=REFRESH_COOKIE_PATH,
    )


def token_response(user_id: UUID) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user_id),
        expires_in=settings.access_token_minutes * 60,
    )


async def issue_refresh_token(db: AsyncSession, user_id: UUID) -> str:
    """Store a new refresh token (hashed) and return the raw value. The caller commits."""
    raw_token = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    return raw_token


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterRequest, db: DbSession):
    # Hashing is CPU work, so it runs in a thread and does not block other requests.
    password_hash = await asyncio.to_thread(hash_password, body.password)
    user = User(email=body.email, password_hash=password_hash)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # The unique constraint is the real guard, so two simultaneous sign-ups cannot both win.
        await db.rollback()
        raise AppError(409, "email_taken", "That email is already registered.") from None
    await db.refresh(user)  # loads created_at, which the database filled in
    return user


@router.post("/login", response_model=TokenOut)
async def login(body: LoginRequest, response: Response, db: DbSession):
    user = await db.scalar(select(User).where(User.email == body.email))
    hash_to_check = user.password_hash if user else DUMMY_HASH
    password_ok = await asyncio.to_thread(verify_password, body.password, hash_to_check)
    if user is None or not password_ok:
        # Same message for "no such email" and "wrong password".
        raise AppError(401, "invalid_credentials", "Incorrect email or password.")

    raw_token = await issue_refresh_token(db, user.id)
    await db.commit()
    set_refresh_cookie(response, raw_token)
    return token_response(user.id)


@router.post("/refresh", response_model=TokenOut)
async def refresh(request: Request, response: Response, db: DbSession):
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if not raw_token:
        raise invalid_refresh_token()

    # FOR UPDATE locks the row, so two requests with the same token cannot both succeed.
    stored = await db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
        .with_for_update()
    )
    if stored is None:
        raise invalid_refresh_token()

    now = datetime.now(UTC)
    if stored.revoked_at is not None:
        # A used token came back: it was probably stolen. End every session of this user.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == stored.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()
        raise invalid_refresh_token()
    if stored.expires_at <= now:
        raise invalid_refresh_token()

    # Rotation: the old token dies, a new one is issued.
    stored.revoked_at = now
    new_raw_token = await issue_refresh_token(db, stored.user_id)
    await db.commit()
    set_refresh_cookie(response, new_raw_token)
    return token_response(stored.user_id)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: DbSession) -> None:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token:
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == hash_refresh_token(raw_token),
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await db.commit()
    # Logging out twice, or without a cookie, is not an error.
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
