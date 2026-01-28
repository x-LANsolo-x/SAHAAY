import pytest
import httpx
import time
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
async def test_10k_vitals_inserts_scale():
    """Load test: insert 10k vitals and assert completes within reasonable time."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "loadtest")

        start = time.time()
        for i in range(10000):
            r = await client.post(
                "/daily/vitals",
                json={"type": "bp", "value": "120/80", "unit": "mmHg", "measured_at": f"2026-01-28T{i % 24:02d}:00:00"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200

        elapsed = time.time() - start
        print(f"10k inserts took {elapsed:.2f}s")
        # Budget: should complete (relaxed for test env; production would be faster)
        assert elapsed < 300  # 5 min budget for 10k in test


@pytest.mark.anyio
async def test_daily_summary_aggregation_correctness():
    """Create known dataset and assert summary is correct."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "summary_user")

        # Create known data for 2026-01-28
        await client.post("/daily/water", json={"amount_ml": 250, "logged_at": "2026-01-28T08:00:00"}, headers={"Authorization": f"Bearer {token}"})
        await client.post("/daily/water", json={"amount_ml": 300, "logged_at": "2026-01-28T12:00:00"}, headers={"Authorization": f"Bearer {token}"})
        
        await client.post("/daily/food", json={"description": "breakfast", "calories": 400, "logged_at": "2026-01-28T08:30:00"}, headers={"Authorization": f"Bearer {token}"})
        await client.post("/daily/food", json={"description": "lunch", "calories": 600, "logged_at": "2026-01-28T13:00:00"}, headers={"Authorization": f"Bearer {token}"})
        
        await client.post("/daily/sleep", json={"duration_minutes": 480, "logged_at": "2026-01-28T06:00:00"}, headers={"Authorization": f"Bearer {token}"})
        
        await client.post("/daily/mood", json={"mood_scale": 7, "logged_at": "2026-01-28T09:00:00"}, headers={"Authorization": f"Bearer {token}"})
        await client.post("/daily/mood", json={"mood_scale": 8, "logged_at": "2026-01-28T14:00:00"}, headers={"Authorization": f"Bearer {token}"})
        await client.post("/daily/mood", json={"mood_scale": 6, "logged_at": "2026-01-28T20:00:00"}, headers={"Authorization": f"Bearer {token}"})
        
        await client.post("/daily/vitals", json={"type": "bp", "value": "120/80", "unit": "mmHg", "measured_at": "2026-01-28T08:00:00"}, headers={"Authorization": f"Bearer {token}"})
        await client.post("/daily/vitals", json={"type": "sugar", "value": "100", "unit": "mg/dL", "measured_at": "2026-01-28T12:00:00"}, headers={"Authorization": f"Bearer {token}"})

        # Get summary
        r = await client.get("/daily/summary?date=2026-01-28", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        summary = r.json()

        # Assert correctness
        assert summary["water_total_ml"] == 550
        assert summary["food_total_calories"] == 1000
        assert summary["sleep_total_minutes"] == 480
        assert summary["mood_avg"] == 7.0  # (7+8+6)/3
        assert summary["vitals_count"] == 2

        # Summary for different date should be empty
        r = await client.get("/daily/summary?date=2026-01-29", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        summary_empty = r.json()
        assert summary_empty["water_total_ml"] == 0
        assert summary_empty["vitals_count"] == 0
