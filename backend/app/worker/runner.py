"""Entrypoint for running the scheduler as its own process.

Run from the backend folder:  python -m app.worker.runner
"""

import asyncio
import logging
import signal

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.worker.retention_loop import run_retention_loop
from app.worker.scheduler import run_forever
from app.worker.telegram_poller import run_telegram_polling

logger = logging.getLogger("uptimeglass.worker")


async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows cannot do this. Ctrl+C is handled below instead.
            pass

    jobs = [run_forever(SessionLocal, stop_event), run_retention_loop(SessionLocal, stop_event)]
    # Telegram allows only one program to poll a bot. When the API runs the embedded
    # worker, it already polls, so this process stays out of the way.
    if not settings.run_embedded_worker:
        jobs.append(run_telegram_polling(SessionLocal, stop_event))

    logger.info("Worker started. Press Ctrl+C to stop.")
    try:
        await asyncio.gather(*jobs)
    finally:
        await engine.dispose()
        logger.info("Worker stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
