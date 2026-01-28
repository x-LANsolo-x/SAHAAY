import pytest
import httpx
from httpx import ASGITransport

from services.api.main import app


@pytest.mark.anyio
async def test_health_ok():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_version_ok():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "sahaay-api"
    assert isinstance(body["version"], str)
