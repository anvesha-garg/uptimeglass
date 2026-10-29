"""Runs the retention job about once an hour."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.retention import run_retention_locked

logger = logging.getLogger(__name__)

FIRST_RUN_DELAY_SECONDS = 60.0
INTERVAL_SECONDS = 3600.0


async def run_retention_loop(
    session_factory: async_sessionmaker[AsyncSession],
    stop_event: asyncio.Event,
    *,
    first_delay: float = FIRST_RUN_DELAY_SECONDS,
    interval: float = INTERVAL_SECONDS,
) -> None:
    delay = first_delay
    while True:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
            return  # asked to stop
        except TimeoutError:
            pass
        try:
            async with session_factory() as db:
                report = await run_retention_locked(db)
            if report is None:
                logger.info("Retention skipped: another worker is running it.")
            else:
                logger.info("Retention done: %s", report)
        except Exception:
            logger.exception("Retention failed")  # tried again next hour
        delay = interval
