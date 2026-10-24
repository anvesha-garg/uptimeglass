"""Entrypoint for running the scheduler as its own process.

Run from the backend folder:  python -m app.worker.runner
"""

import asyncio
import logging
import signal

from app.db.session import SessionLocal, engine
from app.worker.scheduler import run_forever

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

    logger.info("Worker started. Press Ctrl+C to stop.")
    try:
        await run_forever(SessionLocal, stop_event)
    finally:
        await engine.dispose()
        logger.info("Worker stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
