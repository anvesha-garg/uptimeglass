import pytest

PASSWORD = "correct-horse-battery"


@pytest.fixture
async def headers(client):
    email = "owner@example.com"
    await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def payload(**overrides) -> dict:
    data = {"name": "Site", "url": "https://example.com"}
    data.update(overrides)
    return data


async def test_head_with_keyword_is_rejected_on_create(client, headers):
    response = await client.post(
        "/api/v1/monitors", json=payload(method="HEAD", keyword="hello"), headers=headers
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_head_without_keyword_is_fine(client, headers):
    response = await client.post("/api/v1/monitors", json=payload(method="HEAD"), headers=headers)
    assert response.status_code == 201


async def test_switching_a_keyword_monitor_to_head_is_rejected(client, headers):
    created = await client.post("/api/v1/monitors", json=payload(keyword="hello"), headers=headers)
    url = f"/api/v1/monitors/{created.json()['id']}"
    response = await client.patch(url, json={"method": "HEAD"}, headers=headers)
    assert response.status_code == 422


async def test_adding_a_keyword_to_a_head_monitor_is_rejected(client, headers):
    created = await client.post("/api/v1/monitors", json=payload(method="HEAD"), headers=headers)
    url = f"/api/v1/monitors/{created.json()['id']}"
    response = await client.patch(url, json={"keyword": "hello"}, headers=headers)
    assert response.status_code == 422


async def test_switching_to_head_and_removing_the_keyword_together_is_fine(client, headers):
    created = await client.post("/api/v1/monitors", json=payload(keyword="hello"), headers=headers)
    url = f"/api/v1/monitors/{created.json()['id']}"
    response = await client.patch(url, json={"method": "HEAD", "keyword": None}, headers=headers)
    assert response.status_code == 200
    assert response.json()["method"] == "HEAD"
    assert response.json()["keyword"] is None
