import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import alerts, analytics, auth, health, incidents, monitors
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.db.session import SessionLocal, engine
from app.worker.scheduler import run_forever
from app.worker.telegram_poller import run_telegram_polling

logger = logging.getLogger(__name__)

# How long shutdown waits for the embedded worker to finish its current cycle.
WORKER_STOP_TIMEOUT_SECONDS = 30


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    stop_event = asyncio.Event()
    workers: list[asyncio.Task] = []
    # Embedded mode: the API process also runs the scheduler (single-service hosting).
    # Never in tests, so a test cannot start a background loop by accident.
    if settings.run_embedded_worker and settings.env != "test":
        workers.append(asyncio.create_task(run_forever(SessionLocal, stop_event)))
        workers.append(asyncio.create_task(run_telegram_polling(SessionLocal, stop_event)))
        logger.info("Embedded worker started.")

    yield

    if workers:
        stop_event.set()
        try:
            await asyncio.wait_for(asyncio.gather(*workers), timeout=WORKER_STOP_TIMEOUT_SECONDS)
        except TimeoutError:
            logger.warning("Embedded worker did not stop in time.")
    await engine.dispose()


app = FastAPI(title="UptimeGlass API", version="0.1.0", lifespan=lifespan)
register_exception_handlers(app)

# Every route lives under /api/v1.
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(monitors.router, prefix="/api/v1")
app.include_router(incidents.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
