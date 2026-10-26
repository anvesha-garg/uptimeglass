import asyncio

import pytest

from app import main as main_module
from app.core.config import settings
from app.main import app


@pytest.fixture
def events(monkeypatch) -> list[str]:
    """Replaces the scheduler loop and the Telegram poller with fakes."""
    recorded: list[str] = []

    async def fake_run_forever(session_factory, stop_event, **kwargs):
        recorded.append("started")
        await stop_event.wait()
        recorded.append("stopped")

    async def fake_polling(session_factory, stop_event, **kwargs):
        await stop_event.wait()

    monkeypatch.setattr(main_module, "run_forever", fake_run_forever)
    monkeypatch.setattr(main_module, "run_telegram_polling", fake_polling)
    return recorded


async def test_embedded_worker_starts_and_stops_with_the_app(monkeypatch, events):
    monkeypatch.setattr(settings, "env", "development")
    monkeypatch.setattr(settings, "run_embedded_worker", True)

    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.05)
        assert events == ["started"]
    assert events == ["started", "stopped"]  # shutdown waited for a clean stop


@pytest.mark.parametrize(
    ("env", "embedded"),
    [
        ("test", True),  # never in tests, even when the flag is on
        ("development", False),  # the flag is off
    ],
)
async def test_embedded_worker_stays_off(monkeypatch, events, env, embedded):
    monkeypatch.setattr(settings, "env", env)
    monkeypatch.setattr(settings, "run_embedded_worker", embedded)

    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.05)
    assert events == []
