from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

# Use "db: DbSession" in a route to get a database session.
DbSession = Annotated[AsyncSession, Depends(get_db)]
