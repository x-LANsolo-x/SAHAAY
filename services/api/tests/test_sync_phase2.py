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
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.mark.anyio
async def test_reject_unknown_entity_type_and_validate_schema():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user001")
        # invalid entity_type
        r = await client.post(
            "/sync/events:batch",
            json={
                "events": [
                    {
                        "event_id": "e1",
                        "device_id": "d1",
                        "user_id": "wrong",  # mismatch also tested
                        "entity_type": "unknown",
                        "operation": "CREATE",
                        "client_time": "2026-01-28T00:00:00Z",
                        "payload": {},
                    }
                ]
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        res = r.json()["results"][0]
        assert res["status"] == "rejected"


@pytest.mark.anyio
async def test_idempotency_and_partial_failures():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user002")
        me = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})).json()["user_id"]

        payload = {
            "events": [
                {
                    "event_id": "e-ok",
                    "device_id": "d1",
                    "user_id": me,
                    "entity_type": "profile",
                    "operation": "UPDATE",
                    "client_time": "2026-01-28T00:00:00Z",
                    "payload": {"full_name": "Name1"},
                },
                {
                    "event_id": "e-bad",
                    "device_id": "d1",
                    "user_id": me,
                    "entity_type": "nope",
                    "operation": "UPDATE",
                    "client_time": "2026-01-28T00:00:00Z",
                    "payload": {},
                },
            ]
        }

        r = await client.post("/sync/events:batch", json=payload, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        results = {x["event_id"]: x for x in r.json()["results"]}
        assert results["e-ok"]["status"] == "accepted"
        assert results["e-bad"]["status"] == "rejected"

        # sending again -> duplicate
        r = await client.post("/sync/events:batch", json=payload, headers={"Authorization": f"Bearer {token}"})
        results = {x["event_id"]: x for x in r.json()["results"]}
        assert results["e-ok"]["status"] == "duplicate"


@pytest.mark.anyio
async def test_profile_last_write_wins_deterministic():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user003")
        me = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})).json()["user_id"]

        # device A sets name old, device B sets name new
        r = await client.post(
            "/sync/events:batch",
            json={
                "events": [
                    {
                        "event_id": "e1",
                        "device_id": "A",
                        "user_id": me,
                        "entity_type": "profile",
                        "operation": "UPDATE",
                        "client_time": "2026-01-28T00:00:00Z",
                        "payload": {"full_name": "Old"},
                    },
                    {
                        "event_id": "e2",
                        "device_id": "B",
                        "user_id": me,
                        "entity_type": "profile",
                        "operation": "UPDATE",
                        "client_time": "2026-01-28T00:00:10Z",
                        "payload": {"full_name": "New"},
                    },
                ]
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

        # profile reflects last update
        prof = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})).json()
        assert prof["full_name"] == "New"


@pytest.mark.anyio
async def test_append_only_entities_do_not_overwrite():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user004")
        me = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})).json()["user_id"]

        # send two vitals events with same payload key; should both be accepted (raw events stored)
        r = await client.post(
            "/sync/events:batch",
            json={
                "events": [
                    {
                        "event_id": "v1",
                        "device_id": "A",
                        "user_id": me,
                        "entity_type": "vitals",
                        "operation": "CREATE",
                        "client_time": "2026-01-28T00:00:00Z",
                        "payload": {"bp": "120/80"},
                    },
                    {
                        "event_id": "v2",
                        "device_id": "A",
                        "user_id": me,
                        "entity_type": "vitals",
                        "operation": "UPDATE",
                        "client_time": "2026-01-28T00:00:05Z",
                        "payload": {"bp": "120/80"},
                    },
                ]
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        res = r.json()["results"]
        assert [x["status"] for x in res] == ["accepted", "accepted"]

        # verify both exist in sync_events
        # (direct DB check via API isn't exposed yet; but we can check audit logs count)
        audit = (await client.get("/audit/logs", headers={"Authorization": f"Bearer {token}"})).json()
        assert len([a for a in audit if a["action"] == "sync.event.accepted"]) >= 2
