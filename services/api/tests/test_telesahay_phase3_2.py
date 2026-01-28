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


def _assign_role(db, user_id: str, role_name: models.RoleName):
    # Ensure role exists
    role = db.get(models.Role, role_name)
    if not role:
        db.add(models.Role(name=role_name))
        db.flush()
    # Assign role
    db.add(models.UserRole(user_id=user_id, role_name=role_name))
    db.commit()


@pytest.mark.anyio
async def test_prescription_requires_clinician_role(test_db_session):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        patient_token = await _register(client, "patient")
        clinician_token = await _register(client, "clinician")

        # Get user IDs
        patient_id = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {patient_token}"})).json()["user_id"]
        clinician_id = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {clinician_token}"})).json()["user_id"]

        # Patient cannot create prescription
        r = await client.post(
            "/prescriptions",
            json={"user_id": patient_id, "items": [{"drug": "med1", "dose": "10mg"}], "advice": "rest"},
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert r.status_code == 403

        # Assign clinician role
        _assign_role(test_db_session, clinician_id, models.RoleName.clinician)

        # Now clinician can create prescription
        r = await client.post(
            "/prescriptions",
            json={"user_id": patient_id, "items": [{"drug": "med1", "dose": "10mg"}], "advice": "rest"},
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["clinician_user_id"] == clinician_id


def test_prescription_summary_length_constraint():
    from services.api.telesahay import render_sms_summary

    # Test short items
    summary = render_sms_summary([{"drug": "med1", "dose": "10mg"}], "rest")
    assert 160 <= len(summary) <= 300

    # Test long items
    items = [{"drug": f"medicine{i}", "dose": "10mg"} for i in range(10)]
    summary = render_sms_summary(items, "very long advice text" * 20)
    assert len(summary) <= 300


@pytest.mark.anyio
async def test_tele_request_status_transition_validation(test_db_session):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        patient_token = await _register(client, "patient_tele")
        clinician_token = await _register(client, "clinician_tele")

        clinician_id = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {clinician_token}"})).json()["user_id"]
        _assign_role(test_db_session, clinician_id, models.RoleName.clinician)

        # Patient creates request
        r = await client.post(
            "/tele/requests",
            json={"symptom_summary": "need consult"},
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert r.status_code == 200
        req_id = r.json()["id"]
        assert r.json()["status"] == "requested"

        # Patient cannot transition to scheduled (needs clinician)
        r = await client.patch(
            f"/tele/requests/{req_id}",
            json={"status": "scheduled"},
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert r.status_code == 403

        # Clinician can transition to scheduled
        r = await client.patch(
            f"/tele/requests/{req_id}",
            json={"status": "scheduled"},
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "scheduled"

        # Invalid transition: scheduled -> completed (must go through in_progress)
        r = await client.patch(
            f"/tele/requests/{req_id}",
            json={"status": "completed"},
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        assert r.status_code == 400
