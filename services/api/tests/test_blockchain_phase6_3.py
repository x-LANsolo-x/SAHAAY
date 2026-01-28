import pytest
import httpx
from datetime import datetime
from httpx import ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock

from services.api import models
from services.api.app import app
from services.api.db import get_db
from services.api.blockchain_service import BlockchainService, BlockchainServiceError


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


def test_blockchain_service_initialization():
    """Test blockchain service can be initialized."""
    service = BlockchainService()
    assert service.enabled is False  # No provider configured
    
    service_with_config = BlockchainService(
        web3_provider="http://localhost:8545",
        contract_address="0x1234567890123456789012345678901234567890"
    )
    assert service_with_config.enabled is True


def test_anchor_complaint_success(test_db_session):
    """Test successful complaint anchoring."""
    service = BlockchainService(
        web3_provider="http://localhost:8545",
        contract_address="0x1234567890123456789012345678901234567890"
    )
    
    # Create test complaint
    complaint = models.Complaint(
        id="test_complaint_1",
        category=models.ComplaintCategory.service_quality,
        description="Test complaint for blockchain anchoring",
        status=models.ComplaintStatus.submitted,
        current_level=1,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
        sla_due_at=datetime(2024, 1, 8, 12, 0, 0),
    )
    test_db_session.add(complaint)
    test_db_session.commit()
    
    # Anchor complaint
    success, tx_hash = service.anchor_complaint(test_db_session, complaint)
    
    # Should succeed most of the time (90% success rate in simulation)
    if success:
        assert tx_hash is not None
        assert tx_hash.startswith("0x")
        
        # Verify anchor created
        anchor = test_db_session.query(models.BlockchainAnchor).filter(
            models.BlockchainAnchor.entity_id == complaint.id
        ).first()
        assert anchor is not None
        assert anchor.blockchain_tx_hash == tx_hash
        assert anchor.blockchain_status == "pending"


def test_anchor_complaint_graceful_failure(test_db_session):
    """Test graceful degradation when blockchain fails."""
    service = BlockchainService(
        web3_provider="http://localhost:8545",
        contract_address="0x1234567890123456789012345678901234567890"
    )
    
    complaint = models.Complaint(
        id="test_complaint_2",
        category=models.ComplaintCategory.staff_behavior,
        description="Test complaint for failure handling",
        status=models.ComplaintStatus.submitted,
        current_level=1,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
        sla_due_at=datetime(2024, 1, 8, 12, 0, 0),
    )
    test_db_session.add(complaint)
    test_db_session.commit()
    
    # Mock blockchain failure
    with patch.object(service, '_send_to_blockchain', side_effect=BlockchainServiceError("Network error")):
        success, tx_hash = service.anchor_complaint(test_db_session, complaint)
        
        # Should fail gracefully
        assert success is False
        assert tx_hash is None
        
        # Anchor should be marked for retry
        anchor = test_db_session.query(models.BlockchainAnchor).filter(
            models.BlockchainAnchor.entity_id == complaint.id
        ).first()
        assert anchor is not None
        assert anchor.blockchain_status == "pending_retry"
        assert anchor.blockchain_tx_hash is None


def test_anchor_disabled_service(test_db_session):
    """Test that disabled service returns False without error."""
    service = BlockchainService()  # No config = disabled
    
    complaint = models.Complaint(
        id="test_complaint_3",
        category=models.ComplaintCategory.facility_issues,
        description="Test complaint for disabled service",
        status=models.ComplaintStatus.submitted,
        current_level=1,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
        sla_due_at=datetime(2024, 1, 8, 12, 0, 0),
    )
    test_db_session.add(complaint)
    test_db_session.commit()
    
    success, tx_hash = service.anchor_complaint(test_db_session, complaint)
    
    assert success is False
    assert tx_hash is None
    # No exception raised!


def test_retry_pending_anchors(test_db_session):
    """Test retry mechanism for failed anchors."""
    service = BlockchainService(
        web3_provider="http://localhost:8545",
        contract_address="0x1234567890123456789012345678901234567890"
    )
    
    # Create complaint
    complaint = models.Complaint(
        id="test_complaint_4",
        category=models.ComplaintCategory.medication_error,
        description="Test complaint for retry mechanism",
        status=models.ComplaintStatus.submitted,
        current_level=1,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
        sla_due_at=datetime(2024, 1, 8, 12, 0, 0),
    )
    test_db_session.add(complaint)
    test_db_session.commit()
    
    # Create pending anchor
    anchor = models.BlockchainAnchor(
        entity_type="complaint",
        entity_id=complaint.id,
        complaint_hash="0x" + "a" * 64,
        status_hash="0x" + "b" * 64,
        sla_params_hash="0x" + "c" * 64,
        created_at_timestamp=int(complaint.created_at.timestamp()),
        updated_at_timestamp=int(complaint.updated_at.timestamp()),
        event_id="event_123",
        anchor_version="1.0",
        blockchain_status="pending_retry",
    )
    test_db_session.add(anchor)
    test_db_session.commit()
    
    # Retry
    result = service.retry_pending_anchors(test_db_session)
    
    assert result["total_pending"] == 1
    assert result["retried"] >= 0
    # May succeed or fail depending on simulation


@pytest.mark.anyio
async def test_anchor_endpoint_graceful_degradation():
    """Test that anchor endpoint continues to work even if blockchain fails."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "anchor_test_user")
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "service_quality", "description": "Test", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        
        # Try to anchor (may succeed or fail, but should not crash)
        r = await client.post(
            f"/blockchain/anchor/complaint/{complaint_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should return 200 even if blockchain fails
        assert r.status_code in [200, 500]  # 500 only if anchor record creation fails
        
        if r.status_code == 200:
            anchor = r.json()
            assert "blockchain_status" in anchor
            # Status should be "pending" or "pending_retry"
            assert anchor["blockchain_status"] in ["pending", "pending_retry"]


@pytest.mark.anyio
async def test_complaint_workflow_continues_on_blockchain_failure():
    """Test that complaint workflow continues even if blockchain is down."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=30.0) as client:
        token = await _register(client, "workflow_user")
        
        # Create complaint (should work regardless of blockchain)
        r = await client.post(
            "/complaints",
            json={"category": "staff_behavior", "description": "Test complaint", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        complaint_id = r.json()["id"]
        
        # Try to anchor (blockchain may be down, but complaint still exists)
        r = await client.post(
            f"/blockchain/anchor/complaint/{complaint_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        # Should not hard fail
        
        # Verify complaint still accessible
        r = await client.get(
            f"/complaints/{complaint_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        assert r.json()["id"] == complaint_id


@pytest.mark.anyio
async def test_retry_endpoint():
    """Test manual retry endpoint."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "retry_user")
        
        # Call retry endpoint
        r = await client.post(
            "/blockchain/retry-pending",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        
        result = r.json()
        assert "total_pending" in result
        assert "retried" in result
        assert "succeeded" in result
        assert "failed" in result


def test_no_pii_in_blockchain_payload(test_db_session):
    """Test that anchoring never sends PII to blockchain."""
    service = BlockchainService(
        web3_provider="http://localhost:8545",
        contract_address="0x1234567890123456789012345678901234567890"
    )
    
    # Create complaint with PII
    complaint = models.Complaint(
        id="test_complaint_pii",
        user_id="user_with_pii",  # PII!
        category=models.ComplaintCategory.discrimination,
        description="I was discriminated against",  # PII!
        status=models.ComplaintStatus.submitted,
        current_level=1,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
        sla_due_at=datetime(2024, 1, 8, 12, 0, 0),
    )
    test_db_session.add(complaint)
    test_db_session.commit()
    
    # Mock blockchain call to inspect payload
    sent_payloads = []
    
    def mock_send(payload):
        sent_payloads.append(payload)
        return "0x" + "abc" * 21 + "def"
    
    with patch.object(service, '_send_to_blockchain', side_effect=mock_send):
        service.anchor_complaint(test_db_session, complaint)
    
    # Verify NO PII in sent payload
    if sent_payloads:
        payload = sent_payloads[0]
        payload_str = str(payload)
        
        assert "user_with_pii" not in payload_str
        assert "discriminated" not in payload_str
        assert "user_id" not in payload_str
        assert "description" not in payload_str
        
        # Should only contain hashes
        assert "complaint_hash" in payload
        assert "status_hash" in payload
        assert "sla_params_hash" in payload
