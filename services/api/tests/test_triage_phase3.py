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
async def test_red_flag_forces_emergency():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_triage1")

        # Red-flag symptom
        r = await client.post(
            "/triage/sessions",
            json={"symptom_text": "I have chest pain and shortness of breath", "followup_answers": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["triage_category"] == "emergency"
        assert len(body["red_flags"]) > 0


@pytest.mark.anyio
async def test_triage_guidance_is_non_diagnostic():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_triage2")

        # Non-emergency symptom
        r = await client.post(
            "/triage/sessions",
            json={"symptom_text": "mild fever", "followup_answers": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()

        guidance_lower = body["guidance_text"].lower()
        # Ensure no diagnosis terms
        forbidden = ["diagnosis", "cancer", "stroke confirmed", "you have", "diagnosed with"]
        for term in forbidden:
            assert term not in guidance_lower, f"Guidance contains forbidden term: {term}"


@pytest.mark.anyio
async def test_only_owner_can_read_session():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token1 = await _register(client, "owner")
        token2 = await _register(client, "other")

        # owner creates session
        r = await client.post(
            "/triage/sessions",
            json={"symptom_text": "headache", "followup_answers": {}},
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert r.status_code == 200
        session_id = r.json()["id"]

        # owner can read
        r = await client.get(f"/triage/sessions/{session_id}", headers={"Authorization": f"Bearer {token1}"})
        assert r.status_code == 200

        # other user cannot read
        r = await client.get(f"/triage/sessions/{session_id}", headers={"Authorization": f"Bearer {token2}"})
        assert r.status_code == 403
