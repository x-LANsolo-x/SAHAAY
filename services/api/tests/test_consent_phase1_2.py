import pytest
import httpx
from httpx import ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from services.api import models
from services.api.app import app
from services.api.db import get_db


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def test_db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = Session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def override_db(test_db_session):
    def _get_db_override():
        yield test_db_session

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.clear()


async def _register(client: httpx.AsyncClient, username: str, password: str = "password123") -> str:
    r = await client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _set_consent(client: httpx.AsyncClient, token: str, *, category: str, scope: str, granted: bool):
    r = await client.post(
        "/consents",
        json={"category": category, "scope": scope, "granted": granted},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.anyio
async def test_revoking_consent_blocks_export_immediately():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user")

        # No consent -> export forbidden
        r = await client.get("/export/profile", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

        # Grant consent -> export allowed
        await _set_consent(client, token, category="tracking", scope="cloud_sync", granted=True)
        r = await client.get("/export/profile", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

        # Revoke consent -> export forbidden again immediately
        await _set_consent(client, token, category="tracking", scope="cloud_sync", granted=False)
        r = await client.get("/export/profile", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403


@pytest.mark.anyio
async def test_consent_required_for_analytics_event_generation():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user2")

        # Without consent -> cannot generate
        r = await client.post("/analytics/ping", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

        # Grant analytics consent -> generation allowed
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        r = await client.post("/analytics/ping", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        evt = r.json()
        assert evt["event_type"] == "ping"

        # Listing shows at least one event
        r = await client.get("/analytics/events", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert len(r.json()) >= 1

        # Revoke consent -> generation blocked again
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=False)
        r = await client.post("/analytics/ping", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403
