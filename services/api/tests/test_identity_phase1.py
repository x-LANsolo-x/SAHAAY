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
        try:
            yield test_db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.clear()


async def _register(client: httpx.AsyncClient, username: str, password: str = "password123") -> str:
    r = await client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.anyio
async def test_cannot_read_other_users_profile():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        t1 = await _register(client, "user1")
        t2 = await _register(client, "user2")

        r = await client.get("/profiles/me", headers={"Authorization": f"Bearer {t1}"})
        p1 = r.json()
        r = await client.get("/profiles/me", headers={"Authorization": f"Bearer {t2}"})
        p2 = r.json()

        # user1 can read own profile by id
        r = await client.get(f"/profiles/{p1['id']}", headers={"Authorization": f"Bearer {t1}"})
        assert r.status_code == 200

        # user1 cannot read user2 profile
        r = await client.get(f"/profiles/{p2['id']}", headers={"Authorization": f"Bearer {t1}"})
        assert r.status_code == 403


@pytest.mark.anyio
async def test_family_linking_only_via_invite_accept():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        t1 = await _register(client, "inviter")
        t2 = await _register(client, "invitee")

        # Create invite
        r = await client.post(
            "/family/invites",
            json={"invitee_username": "invitee"},
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert r.status_code == 200, r.text
        inv = r.json()

        # Invitee is not a member until accepted: try inviting again should still be conflict only after membership.
        # Accept invite
        r = await client.post(
            f"/family/invites/{inv['id']}/accept",
            headers={"Authorization": f"Bearer {t2}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "accepted"

        # Now inviter cannot re-invite since invitee is member
        r = await client.post(
            "/family/invites",
            json={"invitee_username": "invitee"},
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert r.status_code == 409

        # Another user cannot accept someone else's invite
        t3 = await _register(client, "other")
        r = await client.post(
            f"/family/invites/{inv['id']}/accept",
            headers={"Authorization": f"Bearer {t3}"},
        )
        assert r.status_code == 403
