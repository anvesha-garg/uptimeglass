import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import AppError, register_exception_handlers


@pytest.fixture
async def mini_client():
    # A tiny separate app, so we test only the error handlers.
    mini = FastAPI()
    register_exception_handlers(mini)

    @mini.get("/app-error")
    async def app_error():
        raise AppError(409, "email_taken", "That email is already registered.")

    @mini.get("/number")
    async def number(n: int):
        return {"n": n}

    @mini.get("/boom")
    async def boom():
        raise RuntimeError("secret internal detail")

    # raise_app_exceptions=False lets us see the 500 response instead of the raw exception.
    transport = ASGITransport(app=mini, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_app_error_uses_the_standard_format(mini_client):
    response = await mini_client.get("/app-error")
    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "email_taken", "message": "That email is already registered."}
    }


async def test_validation_error_uses_the_standard_format(mini_client):
    response = await mini_client.get("/number", params={"n": "abc"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"].startswith("n:")


async def test_unknown_route_returns_json_404(mini_client):
    response = await mini_client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_unexpected_error_hides_internal_details(mini_client):
    response = await mini_client.get("/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret internal detail" not in response.text
