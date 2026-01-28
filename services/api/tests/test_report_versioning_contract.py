"""
Test versioning contract enforcement for report builders (Step 6.3).
Ensures that all report responses include the report_version field.
"""
import pytest
import httpx
from httpx import ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from services.api import models
from services.api.app import app, REPORT_VERSION
from services.api.db import get_db
from services.api.schemas import ExportResponse, DailySummaryResponse


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


def test_export_response_schema_has_report_version_field():
    """Unit test: Ensure ExportResponse schema has report_version field."""
    # This test will fail if report_version is removed from the schema
    schema_fields = ExportResponse.model_fields
    assert "report_version" in schema_fields, "ExportResponse schema must include 'report_version' field"
    
    # Verify it's a required field (not optional)
    field_info = schema_fields["report_version"]
    assert field_info.is_required(), "report_version must be a required field in ExportResponse"


def test_daily_summary_response_schema_has_report_version_field():
    """Unit test: Ensure DailySummaryResponse schema has report_version field."""
    # This test will fail if report_version is removed from the schema
    schema_fields = DailySummaryResponse.model_fields
    assert "report_version" in schema_fields, "DailySummaryResponse schema must include 'report_version' field"
    
    # Verify it's a required field (not optional)
    field_info = schema_fields["report_version"]
    assert field_info.is_required(), "report_version must be a required field in DailySummaryResponse"


def test_report_version_constant_exists():
    """Unit test: Ensure REPORT_VERSION constant is defined."""
    assert REPORT_VERSION is not None, "REPORT_VERSION constant must be defined"
    assert isinstance(REPORT_VERSION, str), "REPORT_VERSION must be a string"
    assert len(REPORT_VERSION) > 0, "REPORT_VERSION must not be empty"
    
    # Verify it follows semantic versioning pattern (X.Y or X.Y.Z)
    parts = REPORT_VERSION.split(".")
    assert len(parts) >= 2, "REPORT_VERSION should follow semantic versioning (e.g., '1.0' or '1.0.0')"
    assert all(part.isdigit() for part in parts), "REPORT_VERSION parts should be numeric"


@pytest.mark.anyio
async def test_export_profile_api_returns_report_version():
    """API test: Verify export_profile endpoint returns report_version in response."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_export_contract")
        await _set_consent(client, token, category="tracking", scope="cloud_sync", granted=True)
        
        r = await client.get("/export/profile", headers={"Authorization": f"Bearer {token}"})
        
        assert r.status_code == 200
        data = r.json()
        
        # Strict enforcement: report_version MUST be present
        assert "report_version" in data, "API contract violation: report_version missing from /export/profile response"
        assert data["report_version"] == REPORT_VERSION, f"report_version mismatch: expected {REPORT_VERSION}, got {data['report_version']}"
        
        # Verify it's a string
        assert isinstance(data["report_version"], str), "report_version must be a string"


@pytest.mark.anyio
async def test_daily_summary_api_returns_report_version():
    """API test: Verify daily/summary endpoint returns report_version in response."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_summary_contract")
        
        r = await client.get("/daily/summary?date=2026-01-28", headers={"Authorization": f"Bearer {token}"})
        
        assert r.status_code == 200
        data = r.json()
        
        # Strict enforcement: report_version MUST be present
        assert "report_version" in data, "API contract violation: report_version missing from /daily/summary response"
        assert data["report_version"] == REPORT_VERSION, f"report_version mismatch: expected {REPORT_VERSION}, got {data['report_version']}"
        
        # Verify it's a string
        assert isinstance(data["report_version"], str), "report_version must be a string"


@pytest.mark.anyio
async def test_all_report_endpoints_have_consistent_version():
    """API test: Verify all report endpoints return the same report_version."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_consistency_check")
        await _set_consent(client, token, category="tracking", scope="cloud_sync", granted=True)
        
        # Get version from export_profile
        r1 = await client.get("/export/profile", headers={"Authorization": f"Bearer {token}"})
        version1 = r1.json()["report_version"]
        
        # Get version from daily/summary
        r2 = await client.get("/daily/summary?date=2026-01-28", headers={"Authorization": f"Bearer {token}"})
        version2 = r2.json()["report_version"]
        
        # Both should return the same version
        assert version1 == version2, f"Version inconsistency: export_profile={version1}, daily/summary={version2}"
        assert version1 == REPORT_VERSION, "All reports must use the global REPORT_VERSION constant"


@pytest.mark.anyio
async def test_report_version_appears_first_in_json():
    """API test: Verify report_version appears early in JSON response for client convenience."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "user_field_order")
        await _set_consent(client, token, category="tracking", scope="cloud_sync", granted=True)
        
        r = await client.get("/export/profile", headers={"Authorization": f"Bearer {token}"})
        data = r.json()
        
        # Get the first key in the response
        keys = list(data.keys())
        assert len(keys) > 0, "Response should have at least one key"
        
        # report_version should be the first field (best practice for versioned APIs)
        assert keys[0] == "report_version", f"report_version should be first field, but found: {keys[0]}"


def test_report_version_format_validation():
    """Unit test: Validate REPORT_VERSION follows expected format."""
    # Current version should be "1.0"
    assert REPORT_VERSION == "1.0", "Initial REPORT_VERSION should be '1.0'"
    
    # Should not have leading/trailing whitespace
    assert REPORT_VERSION == REPORT_VERSION.strip(), "REPORT_VERSION should not have whitespace"
    
    # Should not be empty
    assert len(REPORT_VERSION) > 0, "REPORT_VERSION must not be empty"


@pytest.mark.anyio
async def test_version_backward_compatibility_note():
    """
    Documentation test: Ensure versioning contract is clear.
    
    When bumping REPORT_VERSION:
    - 1.0 -> 1.1: Minor changes (add fields, backward compatible)
    - 1.0 -> 2.0: Major changes (remove/rename fields, breaking changes)
    
    This test serves as documentation and will always pass,
    but reminds developers of the versioning contract.
    """
    assert True, "Versioning contract documented"
    
    # Future versions should maintain this contract:
    # - Minor version bump: Add new fields only
    # - Major version bump: Breaking changes to existing fields
    # - All reports should use the same REPORT_VERSION
    # - Clients should check report_version and handle accordingly
