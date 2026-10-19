from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import auth, health
from app.core.errors import register_exception_handlers
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # The embedded worker will start here in Phase 3.
    yield
    await engine.dispose()


app = FastAPI(title="UptimeGlass API", version="0.1.0", lifespan=lifespan)
register_exception_handlers(app)

# Every route lives under /api/v1.
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
