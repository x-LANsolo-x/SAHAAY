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


async def _login(client: httpx.AsyncClient, username: str, password: str = "password123") -> str:
    r = await client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.anyio
async def test_every_write_endpoint_creates_audit_record():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # register logs audit
        t1 = await _register(client, "alice")

        # login logs audit
        _ = await _login(client, "alice")

        # update profile logs audit
        r = await client.patch(
            "/profiles/me",
            json={"full_name": "Alice"},
            headers={"Authorization": f"Bearer {t1}", "X-Device-Id": "dev1"},
        )
        assert r.status_code == 200

        # set consent logs audit
        r = await client.post(
            "/consents",
            json={"category": "tracking", "scope": "cloud_sync", "granted": True},
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert r.status_code == 200

        # family invite create + accept logs audit
        t2 = await _register(client, "bob")
        r = await client.post(
            "/family/invites",
            json={"invitee_username": "bob"},
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert r.status_code == 200
        invite_id = r.json()["id"]

        r = await client.post(
            f"/family/invites/{invite_id}/accept",
            headers={"Authorization": f"Bearer {t2}"},
        )
        assert r.status_code == 200

        # Verify audit entries exist
        r = await client.get("/audit/logs", headers={"Authorization": f"Bearer {t1}"})
        assert r.status_code == 200
        logs = r.json()
        actions = {x["action"] for x in logs}
        assert "auth.register" in actions
        assert "auth.login" in actions
        assert "profiles.update" in actions
        assert "consent.set" in actions
        assert "family.invite.create" in actions

        # Bob should have accept log
        r = await client.get("/audit/logs", headers={"Authorization": f"Bearer {t2}"})
        assert r.status_code == 200
        actions2 = {x["action"] for x in r.json()}
        assert "family.invite.accept" in actions2


@pytest.mark.anyio
async def test_tampering_is_detectable_via_hash_chain_verification(test_db_session):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        t1 = await _register(client, "eve")

        # Create some audit activity
        r = await client.patch(
            "/profiles/me",
            json={"full_name": "Eve"},
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert r.status_code == 200

        # Verify ok
        r = await client.get("/audit/verify", headers={"Authorization": f"Bearer {t1}"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # Tamper: mutate an existing audit row
        row = test_db_session.query(models.AuditLog).order_by(models.AuditLog.ts.asc()).first()
        assert row is not None
        row.action = "tampered.action"
        test_db_session.commit()

        # Verify fails
        r = await client.get("/audit/verify", headers={"Authorization": f"Bearer {t1}"})
        assert r.status_code == 200
        assert r.json()["ok"] is False
