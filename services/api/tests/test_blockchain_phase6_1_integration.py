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


async def _register(client: httpx.AsyncClient, username: str) -> str:
    r = await client.post("/auth/register", json={"username": username, "password": "password123"})
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.mark.anyio
async def test_anchor_complaint_to_blockchain():
    """Test anchoring a complaint to blockchain (hashes only, no PII)."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "anchor_user")
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "service_quality", "description": "Test complaint", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        
        # Anchor to blockchain
        r = await client.post(
            f"/blockchain/anchor/complaint/{complaint_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        
        anchor = r.json()
        assert anchor["entity_type"] == "complaint"
        assert anchor["entity_id"] == complaint_id
        assert len(anchor["complaint_hash"]) == 64  # SHA256
        assert len(anchor["status_hash"]) == 64
        assert len(anchor["sla_params_hash"]) == 64
        assert anchor["blockchain_status"] == "pending"
        assert "event_id" in anchor
        
        # Verify NO PII in response
        assert "user_id" not in anchor
        assert "description" not in anchor
        assert "contact_info" not in anchor


@pytest.mark.anyio
async def test_get_complaint_anchors():
    """Test retrieving all anchors for a complaint."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "get_anchors_user")
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "staff_behavior", "description": "Test", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        
        # Create multiple anchors
        for _ in range(3):
            await client.post(
                f"/blockchain/anchor/complaint/{complaint_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
        
        # Get all anchors
        r = await client.get(
            f"/blockchain/anchors/complaint/{complaint_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        anchors = r.json()
        assert len(anchors) == 3
        
        # Verify each anchor has unique event_id
        event_ids = [a["event_id"] for a in anchors]
        assert len(event_ids) == len(set(event_ids))  # All unique


@pytest.mark.anyio
async def test_verify_blockchain_anchor():
    """Test verification of blockchain anchor."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "verify_user")
        
        # Create and anchor complaint
        r = await client.post(
            "/complaints",
            json={"category": "facility_issues", "description": "Broken AC", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        
        r = await client.post(
            f"/blockchain/anchor/complaint/{complaint_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        anchor_id = r.json()["id"]
        
        # Verify anchor
        r = await client.get(
            f"/blockchain/verify/{anchor_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        
        verification = r.json()
        assert verification["anchor_id"] == anchor_id
        assert verification["is_valid"] is True
        assert verification["verification"]["complaint_hash_match"] is True
        assert verification["verification"]["status_hash_match"] is True
        assert verification["verification"]["sla_params_hash_match"] is True


@pytest.mark.anyio
async def test_verify_detects_tampering(test_db_session):
    """Test that verification detects if complaint data is tampered with."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "tamper_user")
        
        # Create and anchor complaint
        r = await client.post(
            "/complaints",
            json={"category": "other", "description": "Test", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        
        r = await client.post(
            f"/blockchain/anchor/complaint/{complaint_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        anchor_id = r.json()["id"]
        
        # Tamper with complaint (change status)
        complaint = test_db_session.get(models.Complaint, complaint_id)
        complaint.status = models.ComplaintStatus.resolved  # Changed!
        test_db_session.commit()
        
        # Verify should detect tampering
        r = await client.get(
            f"/blockchain/verify/{anchor_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        
        verification = r.json()
        assert verification["is_valid"] is False  # Tampered!
        assert verification["verification"]["status_hash_match"] is False


@pytest.mark.anyio
async def test_blockchain_anchor_no_pii_in_database(test_db_session):
    """Test that no PII is stored in blockchain_anchors table."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "nopii_user")
        
        # Create complaint with PII
        r = await client.post(
            "/complaints",
            json={
                "category": "discrimination",
                "description": "I was discriminated against",  # PII
                "is_anonymous": False
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        
        # Anchor
        r = await client.post(
            f"/blockchain/anchor/complaint/{complaint_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        anchor_id = r.json()["id"]
        
        # Check database directly
        anchor = test_db_session.get(models.BlockchainAnchor, anchor_id)
        
        # Verify NO PII in anchor record
        assert anchor.complaint_hash is not None  # Hash present
        assert len(anchor.complaint_hash) == 64  # SHA256
        
        # Convert all anchor attributes to string and check for PII
        anchor_str = str(vars(anchor))
        assert "discriminated" not in anchor_str.lower()
        assert "description" not in anchor_str.lower()
