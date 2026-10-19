from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User

# Use "db: DbSession" in a route to get a database session.
DbSession = Annotated[AsyncSession, Depends(get_db)]

# auto_error=False: we raise our own error, so the format stays {"error": {...}}.
# This also gives Swagger an "Authorize" button where you paste an access token.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise AppError(401, "not_authenticated", "Missing access token.")
    user_id = decode_access_token(credentials.credentials)
    user = await db.get(User, user_id)
    if user is None:
        # The token is valid but the account was deleted.
        raise AppError(401, "invalid_token", "Invalid or expired access token.")
    return user


# Use "user: CurrentUser" in a route to require login and get the logged-in user.
CurrentUser = Annotated[User, Depends(get_current_user)]
