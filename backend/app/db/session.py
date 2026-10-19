from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# pool_pre_ping checks a connection is alive before using it (survives DB restarts).
engine = create_async_engine(settings.database_url, pool_pre_ping=True)

# expire_on_commit=False: objects stay readable after commit (async can't lazy-load them).
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request. Code commits explicitly; closing without commit discards changes."""
    async with SessionLocal() as session:
        yield session
