"""
Tests for Phase 7.1 - Analytics Event Generation with Privacy Guarantees

Tests verify:
1. Consent is required for analytics generation
2. Event schema validation (allowed types/categories only)
3. De-identification (no PII in payload)
4. Time bucketing and age bucketing
5. Geo-hashing for location privacy
6. k-anonymity thresholds in aggregations
7. Integration with triage, complaints, vaccination, neuroscreen
"""

import json
import pytest
import httpx
from datetime import datetime
from httpx import ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from services.api import models
from services.api.app import app
from services.api.db import get_db
from services.api.analytics import (
    round_to_time_bucket,
    get_age_bucket,
    pincode_to_h3,
    AnalyticsEventSchema,
)


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


async def _update_profile(client: httpx.AsyncClient, token: str, **kwargs):
    r = await client.patch(
        "/profiles/me",
        json=kwargs,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


# ============================================================
# Core Privacy Helper Tests
# ============================================================

def test_time_bucketing_rounds_to_15_minutes():
    """Verify time is rounded to 15-minute buckets for privacy."""
    dt1 = datetime(2024, 1, 1, 10, 7, 30)
    dt2 = datetime(2024, 1, 1, 10, 14, 59)
    dt3 = datetime(2024, 1, 1, 10, 15, 0)
    
    assert round_to_time_bucket(dt1) == datetime(2024, 1, 1, 10, 0, 0)
    assert round_to_time_bucket(dt2) == datetime(2024, 1, 1, 10, 0, 0)
    assert round_to_time_bucket(dt3) == datetime(2024, 1, 1, 10, 15, 0)


def test_age_bucketing_preserves_privacy():
    """Verify age is converted to buckets, not exact values."""
    assert get_age_bucket(3) == "0-5"
    assert get_age_bucket(10) == "6-12"
    assert get_age_bucket(16) == "13-18"
    assert get_age_bucket(25) == "19-35"
    assert get_age_bucket(50) == "36-60"
    assert get_age_bucket(70) == "60+"
    assert get_age_bucket(None) == "unknown"


def test_pincode_to_h3_aggregates_location():
    """Verify pincode is aggregated to district-level, not exact location."""
    assert pincode_to_h3("110001") == "pincode_110xxx"
    assert pincode_to_h3("110025") == "pincode_110xxx"
    assert pincode_to_h3("560001") == "pincode_560xxx"
    assert pincode_to_h3("12") == "unknown"  # Too short
    assert pincode_to_h3("") == "unknown"


def test_event_schema_validation():
    """Verify only allowed event types and categories are accepted."""
    assert AnalyticsEventSchema.validate_event_type("triage_completed") is True
    assert AnalyticsEventSchema.validate_event_type("complaint_submitted") is True
    assert AnalyticsEventSchema.validate_event_type("invalid_event") is False
    
    assert AnalyticsEventSchema.validate_category("self_care") is True
    assert AnalyticsEventSchema.validate_category("service_quality") is True
    assert AnalyticsEventSchema.validate_category("invalid_category") is False
    assert AnalyticsEventSchema.validate_category(None) is True  # Optional


# ============================================================
# Consent & Authorization Tests
# ============================================================

@pytest.mark.anyio
async def test_analytics_requires_consent():
    """Verify analytics event generation requires explicit consent."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user1")
        
        # Without consent -> forbidden
        r = await client.post(
            "/analytics/events",
            json={"event_type": "triage_completed", "category": "self_care"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        assert "consent" in r.text.lower()


@pytest.mark.anyio
async def test_analytics_with_consent_succeeds():
    """Verify analytics works with proper consent."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user2")
        
        # Grant consent
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        # Set profile for demographics
        await _update_profile(client, token, age=25, sex="F", pincode="110001")
        
        # Generate event -> success
        r = await client.post(
            "/analytics/events",
            json={"event_type": "triage_completed", "category": "self_care"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        assert data["event_type"] == "triage_completed"
        assert "payload" in data
        
        # Verify de-identified payload
        payload = data["payload"]
        assert payload["event_type"] == "triage_completed"
        assert payload["category"] == "self_care"
        assert payload["age_bucket"] == "19-35"
        assert payload["gender"] == "F"
        assert payload["geo_cell"] == "pincode_110xxx"
        assert payload["schema_version"] == "1.0"


@pytest.mark.anyio
async def test_revoking_consent_blocks_analytics():
    """Verify revoking consent immediately blocks analytics generation."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user3")
        
        # Grant consent
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        # Generate event -> success
        r = await client.post(
            "/analytics/events",
            json={"event_type": "triage_completed", "category": "phc"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        # Revoke consent
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=False)
        
        # Generate event -> forbidden
        r = await client.post(
            "/analytics/events",
            json={"event_type": "triage_completed", "category": "phc"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403


# ============================================================
# Privacy & De-identification Tests
# ============================================================

@pytest.mark.anyio
async def test_analytics_payload_has_no_pii():
    """Verify analytics payload contains no PII (user_id, phone, email, etc.)."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user4")
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        await _update_profile(client, token, full_name="John Doe", age=30, pincode="560001")
        
        r = await client.post(
            "/analytics/events",
            json={"event_type": "complaint_submitted", "category": "service_quality"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        payload = r.json()["payload"]
        
        # Verify NO PII fields
        assert "user_id" not in payload
        assert "username" not in payload
        assert "full_name" not in payload
        assert "phone" not in payload
        assert "email" not in payload
        assert "complaint_id" not in payload
        assert "exact_location" not in payload
        
        # Verify ONLY aggregated/bucketed fields
        assert "age_bucket" in payload
        assert "geo_cell" in payload
        assert payload["geo_cell"] == "pincode_560xxx"


@pytest.mark.anyio
async def test_analytics_rejects_pii_in_metadata():
    """Verify analytics rejects metadata containing PII fields."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user5")
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        # Try to pass PII in metadata -> rejected
        r = await client.post(
            "/analytics/events",
            json={
                "event_type": "triage_completed",
                "category": "emergency",
                "metadata": {"user_id": "malicious", "phone": "1234567890"}
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        assert "disallowed" in r.text.lower() or "pii" in r.text.lower()


@pytest.mark.anyio
async def test_analytics_rejects_invalid_event_types():
    """Verify only allowed event types are accepted."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user6")
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        # Invalid event type -> rejected
        r = await client.post(
            "/analytics/events",
            json={"event_type": "invalid_event_type", "category": "self_care"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        assert "invalid" in r.text.lower()


@pytest.mark.anyio
async def test_analytics_rejects_invalid_categories():
    """Verify only allowed categories are accepted."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user7")
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        # Invalid category -> rejected
        r = await client.post(
            "/analytics/events",
            json={"event_type": "triage_completed", "category": "invalid_category"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        assert "invalid" in r.text.lower()


# ============================================================
# Aggregation & k-Anonymity Tests
# ============================================================

@pytest.mark.anyio
async def test_analytics_summary_enforces_k_anonymity():
    """Verify analytics summary only shows aggregates with >= 5 events."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create 6 users and generate events
        for i in range(6):
            token = await _register(client, f"user_agg_{i}")
            await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
            await _update_profile(client, token, age=25 + i, pincode="110001")
            
            # Generate 1 event per user (total 6 for triage_completed)
            await client.post(
                "/analytics/events",
                json={"event_type": "triage_completed", "category": "self_care"},
                headers={"Authorization": f"Bearer {token}"},
            )
        
        # Get summary
        token = await _register(client, "admin")
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        r = await client.get(
            "/analytics/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        assert "summary" in data
        assert "privacy_threshold" in data
        assert data["privacy_threshold"] == 5
        
        # Should show triage_completed (6 events >= 5)
        summary_items = data["summary"]
        triage_items = [s for s in summary_items if s["event_type"] == "triage_completed"]
        assert len(triage_items) > 0
        assert triage_items[0]["count"] >= 5


@pytest.mark.anyio
async def test_analytics_summary_hides_low_count_aggregates():
    """Verify analytics summary hides aggregates with < 5 events."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create 3 users with emergency events (below threshold)
        for i in range(3):
            token = await _register(client, f"user_emergency_{i}")
            await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
            await _update_profile(client, token, age=30, pincode="560001")
            
            await client.post(
                "/analytics/events",
                json={"event_type": "triage_emergency", "category": "emergency"},
                headers={"Authorization": f"Bearer {token}"},
            )
        
        # Get summary
        token = await _register(client, "admin2")
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        r = await client.get(
            "/analytics/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        summary_items = data["summary"]
        
        # Should NOT show triage_emergency (only 3 events < 5)
        emergency_items = [s for s in summary_items if s["event_type"] == "triage_emergency"]
        assert len(emergency_items) == 0  # Hidden due to k-anonymity


# ============================================================
# Edge Cases & Robustness Tests
# ============================================================

@pytest.mark.anyio
async def test_analytics_handles_missing_profile_gracefully():
    """Verify analytics works even with missing profile data."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_no_profile")
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        # Don't set profile -> should use "unknown" values
        r = await client.post(
            "/analytics/events",
            json={"event_type": "triage_completed", "category": "phc"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        payload = r.json()["payload"]
        assert payload["age_bucket"] == "unknown"
        assert payload["gender"] == "unknown"
        assert payload["geo_cell"] == "unknown"


@pytest.mark.anyio
async def test_analytics_allows_valid_metadata():
    """Verify analytics accepts PII-free metadata."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_metadata")
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        # Valid metadata (no PII)
        r = await client.post(
            "/analytics/events",
            json={
                "event_type": "vaccination_recorded",
                "metadata": {"vaccine_type": "DPT", "dose_sequence": 2}
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        payload = r.json()["payload"]
        assert payload["metadata"]["vaccine_type"] == "DPT"
        assert payload["metadata"]["dose_sequence"] == 2


@pytest.mark.anyio
async def test_legacy_ping_endpoint_still_works():
    """Verify backward compatibility with /analytics/ping."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_legacy")
        await _set_consent(client, token, category="analytics", scope="gov_aggregated", granted=True)
        
        r = await client.post(
            "/analytics/ping",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["event_type"] == "ping"
