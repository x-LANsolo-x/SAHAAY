import pytest
import httpx
from httpx import ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

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
    
    # Seed vaccine schedules
    schedules = [
        ("BCG", 1, 0),
        ("OPV", 1, 0),
        ("DPT", 1, 42),
        ("DPT", 2, 70),
    ]
    for vax, dose, days in schedules:
        db.add(models.VaccineScheduleRule(vaccine_name=vax, dose_number=dose, due_age_days=days))
    
    # Seed milestones
    db.add(models.Milestone(age_months=2, description="Smiles"))
    db.add(models.Milestone(age_months=6, description="Sits"))
    db.commit()
    
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
async def test_next_due_vaccine_computed_correctly():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "baby1")
        
        # Set age to 0 (newborn)
        me = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})).json()
        await client.patch("/profiles/me", json={"age": 0}, headers={"Authorization": f"Bearer {token}"})
        
        # Next due should be BCG or OPV at birth (due_age_days=0)
        r = await client.get(f"/vax/next_due?user_id={me['user_id']}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["vaccine_name"] in ["BCG", "OPV"]
        assert body["dose_number"] == 1


@pytest.mark.anyio
async def test_missing_dob_returns_400():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "no_age")
        me = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})).json()
        
        # age is None by default
        r = await client.get(f"/vax/next_due?user_id={me['user_id']}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400
        assert "DOB required" in r.json()["detail"]


@pytest.mark.anyio
async def test_late_vaccine_returns_overdue():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "late_baby")
        me = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})).json()
        
        # Set age to 1 year (365 days old)
        await client.patch("/profiles/me", json={"age": 1}, headers={"Authorization": f"Bearer {token}"})
        
        # Next due should be BCG (due at day 0), which is overdue
        r = await client.get(f"/vax/next_due?user_id={me['user_id']}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["overdue"] is True


@pytest.mark.anyio
async def test_vaccination_record_and_milestones():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "child")
        
        # Create vaccination record
        r = await client.post(
            "/vax/records",
            json={"vaccine_name": "BCG", "dose_number": 1, "administered_at": "2026-01-28T10:00:00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        # Create growth record
        r = await client.post(
            "/growth/records",
            json={"height_cm": 50.0, "weight_kg": 3.5, "recorded_at": "2026-01-28T10:00:00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        # Get milestones for age 6 months
        r = await client.get("/milestones?age_months=6", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        milestones = r.json()
        assert len(milestones) == 2  # 2 and 6 month milestones
