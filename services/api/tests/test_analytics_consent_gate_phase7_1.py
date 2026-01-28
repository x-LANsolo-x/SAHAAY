"""
Tests for Phase 7.1 - Automatic Analytics Emission with Consent Gates

Verifies that analytics are automatically emitted from business logic endpoints
ONLY when user has granted analytics consent.
"""

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


# ============================================================
# Triage Analytics - Consent Gate Tests
# ============================================================

@pytest.mark.anyio
async def test_triage_emits_analytics_with_consent():
    """Verify triage automatically emits analytics when consent is granted."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_triage_1")
        
        # Grant analytics consent
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        # Create triage session
        r = await client.post(
            "/triage/sessions",
            json={"symptom_text": "fever and cough", "followup_answers": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        # Check analytics event was created
        r = await client.get(
            "/analytics/events",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        events = r.json()
        
        # Should have at least one analytics event
        assert len(events) > 0
        # Should have triage event
        triage_events = [e for e in events if e["event_type"] in ["triage_completed", "triage_emergency"]]
        assert len(triage_events) > 0


@pytest.mark.anyio
async def test_triage_does_not_emit_analytics_without_consent():
    """Verify triage does NOT emit analytics when consent is not granted."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_triage_2")
        
        # Do NOT grant analytics consent
        
        # Create triage session
        r = await client.post(
            "/triage/sessions",
            json={"symptom_text": "headache", "followup_answers": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        # Check NO analytics events were created
        r = await client.get(
            "/analytics/events",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        events = r.json()
        
        # Should have NO analytics events
        assert len(events) == 0


# ============================================================
# Vaccination Analytics - Consent Gate Tests
# ============================================================

@pytest.mark.anyio
async def test_vaccination_emits_analytics_with_consent():
    """Verify vaccination automatically emits analytics when consent is granted."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_vax_1")
        
        # Grant analytics consent
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        # Create vaccination record
        r = await client.post(
            "/vax/records",
            json={
                "vaccine_name": "BCG",
                "dose_number": 1,
                "administered_at": "2024-01-15T10:00:00"
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        # Check analytics event was created
        r = await client.get(
            "/analytics/events",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        events = r.json()
        
        # Should have vaccination analytics event
        assert len(events) > 0
        vax_events = [e for e in events if e["event_type"] == "vaccination_recorded"]
        assert len(vax_events) > 0


@pytest.mark.anyio
async def test_vaccination_does_not_emit_analytics_without_consent():
    """Verify vaccination does NOT emit analytics when consent is not granted."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_vax_2")
        
        # Do NOT grant analytics consent
        
        # Create vaccination record
        r = await client.post(
            "/vax/records",
            json={
                "vaccine_name": "DPT",
                "dose_number": 1,
                "administered_at": "2024-01-15T10:00:00"
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        # Check NO analytics events were created
        r = await client.get(
            "/analytics/events",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        events = r.json()
        
        # Should have NO analytics events
        assert len(events) == 0


# ============================================================
# NeuroScreen Analytics - Consent Gate Tests
# ============================================================

@pytest.mark.anyio
async def test_neuroscreen_emits_analytics_with_consent(test_db_session):
    """Verify neuroscreen automatically emits analytics when consent is granted."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a neuroscreen version first
        import json
        version = models.NeuroscreenVersion(
            name="Test Version",
            scoring_rules_json=json.dumps({"bands": {"low": [0, 10], "medium": [11, 20], "high": [21, 100]}}),
            is_active=True,
        )
        test_db_session.add(version)
        test_db_session.commit()
        
        token = await _register(client, "user_neuro_1")
        
        # Grant analytics consent
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        # Create neuroscreen result
        r = await client.post(
            "/neuroscreen/results",
            json={
                "version_id": version.id,
                "responses": {"q1": 5, "q2": 3}
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        # Check analytics event was created
        r = await client.get(
            "/analytics/events",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        events = r.json()
        
        # Should have neuroscreen analytics event
        assert len(events) > 0
        neuro_events = [e for e in events if e["event_type"] == "neuroscreen_completed"]
        assert len(neuro_events) > 0


@pytest.mark.anyio
async def test_neuroscreen_does_not_emit_analytics_without_consent(test_db_session):
    """Verify neuroscreen does NOT emit analytics when consent is not granted."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a neuroscreen version first
        import json
        version = models.NeuroscreenVersion(
            name="Test Version 2",
            scoring_rules_json=json.dumps({"bands": {"low": [0, 10], "medium": [11, 20], "high": [21, 100]}}),
            is_active=True,
        )
        test_db_session.add(version)
        test_db_session.commit()
        
        token = await _register(client, "user_neuro_2")
        
        # Do NOT grant analytics consent
        
        # Create neuroscreen result
        r = await client.post(
            "/neuroscreen/results",
            json={
                "version_id": version.id,
                "responses": {"q1": 8, "q2": 6}
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        # Check NO analytics events were created
        r = await client.get(
            "/analytics/events",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        events = r.json()
        
        # Should have NO analytics events
        assert len(events) == 0


# ============================================================
# Consent Revocation Tests
# ============================================================

@pytest.mark.anyio
async def test_revoking_consent_stops_future_analytics():
    """Verify that revoking consent stops future analytics emissions."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_revoke")
        
        # Grant analytics consent
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        # Create triage session -> should emit analytics
        r = await client.post(
            "/triage/sessions",
            json={"symptom_text": "fever", "followup_answers": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        # Check analytics event was created
        r = await client.get(
            "/analytics/events",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        events_before = r.json()
        assert len(events_before) > 0
        
        # Revoke consent
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=False)
        
        # Create another triage session -> should NOT emit analytics
        r = await client.post(
            "/triage/sessions",
            json={"symptom_text": "cough", "followup_answers": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        # Check NO NEW analytics events were created
        r = await client.get(
            "/analytics/events",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        events_after = r.json()
        
        # Should have same number of events (no new ones added)
        assert len(events_after) == len(events_before)
