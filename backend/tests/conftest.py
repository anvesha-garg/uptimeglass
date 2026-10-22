"""Shared test setup. Tests run against a separate database that is wiped for every test."""

import os

# These must be set BEFORE the app is imported, because settings are read at import time.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://uptimeglass:uptimeglass@127.0.0.1:5433/uptimeglass_test",
)
# Safety lock: tests drop tables, so they must never point at the dev database.
assert TEST_DATABASE_URL.rsplit("/", 1)[-1].endswith("_test"), "Test DB name must end with _test"

os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET"] = "test-only-secret-that-is-at-least-32-characters-long"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import ssrf  # noqa: E402

# Names the monitor tests use. They resolve to a fixed address, so no real DNS is needed.
FAKE_DNS = {
    "example.com": ["93.184.216.34"],
    "other.example.com": ["93.184.216.35"],
    "internal.example.com": ["10.0.0.5"],
}


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    real_resolver = ssrf.system_resolver

    async def resolver(host: str, port: int) -> list[str]:
        if host in FAKE_DNS:
            return FAKE_DNS[host]
        return await real_resolver(host, port)

    monkeypatch.setattr(ssrf, "system_resolver", resolver)


@pytest.fixture
async def engine():
    # NullPool: no connection is reused between tests (each test has its own event loop).
    test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def db_session(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest.fixture
async def client(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
