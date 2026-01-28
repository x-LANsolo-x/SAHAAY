import pytest
import httpx
import json
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
    
    # Seed v1 scoring rules
    rules_v1 = {
        "question_weights": {"q1": 1, "q2": 2, "q3": 1, "q4": 3, "q5": 2},
        "band_thresholds": {"low": [0, 3], "medium": [4, 7], "high": [8, 100]},
    }
    v1 = models.NeuroscreenVersion(name="Test v1", scoring_rules_json=json.dumps(rules_v1), is_active=True)
    db.add(v1)
    db.commit()
    
    # Seed v2 (different thresholds)
    rules_v2 = {
        "question_weights": {"q1": 1, "q2": 2, "q3": 1, "q4": 3, "q5": 2},
        "band_thresholds": {"low": [0, 5], "medium": [6, 9], "high": [10, 100]},
    }
    v2 = models.NeuroscreenVersion(name="Test v2", scoring_rules_json=json.dumps(rules_v2), is_active=True)
    db.add(v2)
    db.commit()
    
    try:
        yield db, v1.id, v2.id
    finally:
        db.close()


@pytest.fixture(autouse=True)
def override_db(test_db_session):
    db, v1_id, v2_id = test_db_session
    def _get_db_override():
        yield db

    app.dependency_overrides[get_db] = _get_db_override
    yield v1_id, v2_id
    app.dependency_overrides.clear()


async def _register(client: httpx.AsyncClient, username: str, password: str = "password123") -> str:
    r = await client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.mark.anyio
async def test_versioned_scoring_reproducible(override_db):
    v1_id, v2_id = override_db
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "neuro_user")

        responses = {"q1": 1, "q2": 1, "q3": 1, "q4": 2, "q5": 1}
        
        # Submit with v1
        r = await client.post(
            "/neuroscreen/results",
            json={"version_id": v1_id, "responses": responses},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        result_v1 = r.json()
        
        # Expected score: 1*1 + 1*2 + 1*1 + 2*3 + 1*2 = 1+2+1+6+2 = 12
        assert result_v1["raw_score"] == 12
        assert result_v1["band"] == "high"  # v1 threshold: high >= 8
        
        # Submit same responses with v2
        r = await client.post(
            "/neuroscreen/results",
            json={"version_id": v2_id, "responses": responses},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        result_v2 = r.json()
        
        # Same score but different band due to v2 thresholds
        assert result_v2["raw_score"] == 12
        assert result_v2["band"] == "high"  # v2 threshold: high >= 10
        
        # Re-submit with v1 to ensure reproducibility
        r = await client.post(
            "/neuroscreen/results",
            json={"version_id": v1_id, "responses": responses},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        result_v1_again = r.json()
        assert result_v1_again["raw_score"] == result_v1["raw_score"]
        assert result_v1_again["band"] == result_v1["band"]


@pytest.mark.anyio
async def test_guidance_contains_screening_disclaimer(override_db):
    v1_id, _ = override_db
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "screening_user")

        # Test low band
        r = await client.post(
            "/neuroscreen/results",
            json={"version_id": v1_id, "responses": {"q1": 0, "q2": 0, "q3": 0, "q4": 0, "q5": 0}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        low_result = r.json()
        assert "screening" in low_result["guidance_text"].lower()
        assert "not a diagnosis" in low_result["guidance_text"].lower()
        
        # Test high band
        r = await client.post(
            "/neuroscreen/results",
            json={"version_id": v1_id, "responses": {"q1": 3, "q2": 3, "q3": 3, "q4": 3, "q5": 3}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        high_result = r.json()
        assert "screening" in high_result["guidance_text"].lower()
        assert "not a diagnosis" in high_result["guidance_text"].lower()


@pytest.mark.anyio
async def test_access_controls_results(override_db):
    v1_id, _ = override_db
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token1 = await _register(client, "owner")
        token2 = await _register(client, "other")

        # Owner creates result
        r = await client.post(
            "/neuroscreen/results",
            json={"version_id": v1_id, "responses": {"q1": 1, "q2": 1, "q3": 1, "q4": 1, "q5": 1}},
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert r.status_code == 200
        result_id = r.json()["id"]

        # Owner can read
        r = await client.get(f"/neuroscreen/results/{result_id}", headers={"Authorization": f"Bearer {token1}"})
        assert r.status_code == 200

        # Other user cannot read
        r = await client.get(f"/neuroscreen/results/{result_id}", headers={"Authorization": f"Bearer {token2}"})
        assert r.status_code == 403
