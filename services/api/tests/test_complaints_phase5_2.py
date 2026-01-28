import pytest
import httpx
from datetime import datetime, timedelta
from httpx import ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from services.api import models
from services.api.app import app
from services.api.db import get_db
from services.api.escalation_worker import run_escalation_check


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
    role = db.get(models.Role, role_name)
    if not role:
        db.add(models.Role(name=role_name))
        db.flush()
    db.add(models.UserRole(user_id=user_id, role_name=role_name))
    db.commit()


def _seed_sla_rules(db):
    """Seed basic SLA rules for testing."""
    rules = [
        ("service_quality", 1, 72),   # 72 hours at district
        ("service_quality", 2, 168),  # 7 days at state
        ("service_quality", 3, 336),  # 14 days at national
        
        ("medication_error", 1, 24),  # 24 hours (critical)
        ("medication_error", 2, 48),
        ("medication_error", 3, 72),
    ]
    
    for category_str, level, hours in rules:
        rule = models.SLARule(
            category=models.ComplaintCategory(category_str),
            escalation_level=level,
            time_limit_hours=hours,
        )
        db.add(rule)
    
    db.commit()


@pytest.mark.anyio
async def test_create_sla_rule():
    """Test creating SLA rules."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "sla_admin")
        
        payload = {
            "category": "staff_behavior",
            "escalation_level": 1,
            "time_limit_hours": 48
        }
        
        r = await client.post("/sla-rules", json=payload, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        
        rule = r.json()
        assert rule["category"] == "staff_behavior"
        assert rule["escalation_level"] == 1
        assert rule["time_limit_hours"] == 48


@pytest.mark.anyio
async def test_list_sla_rules():
    """Test listing SLA rules with filtering."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=30.0) as client:
        token = await _register(client, "sla_lister")
        
        # Create multiple rules
        categories = ["service_quality", "staff_behavior", "service_quality"]
        for i, cat in enumerate(categories):
            payload = {"category": cat, "escalation_level": 1, "time_limit_hours": 48 + i * 24}
            await client.post("/sla-rules", json=payload, headers={"Authorization": f"Bearer {token}"})
        
        # List all
        r = await client.get("/sla-rules", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        rules = r.json()
        assert len(rules) == 2  # Only 2 unique category+level combinations
        
        # Filter by category
        r = await client.get("/sla-rules?category=service_quality", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        filtered = r.json()
        assert len(filtered) == 1
        assert filtered[0]["category"] == "service_quality"


@pytest.mark.anyio
async def test_complaint_auto_escalation(test_db_session):
    """Test automatic escalation when SLA is breached."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "escalation_user")
        
        # Seed SLA rules
        _seed_sla_rules(test_db_session)
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "service_quality", "description": "Test complaint", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        
        # Simulate time passing by manually setting created_at to past
        complaint = test_db_session.get(models.Complaint, complaint_id)
        complaint.created_at = datetime.utcnow() - timedelta(hours=80)  # 80 hours ago (exceeds 72h SLA)
        complaint.sla_due_at = datetime.utcnow() - timedelta(hours=8)  # SLA already breached
        test_db_session.commit()
        
        # Run escalation check
        result = run_escalation_check(test_db_session)
        assert result["checked"] == 1
        assert result["escalated"] == 1
        
        # Verify escalation
        test_db_session.refresh(complaint)
        assert complaint.current_level == 2  # Escalated from 1 to 2
        assert complaint.status == models.ComplaintStatus.escalated
        
        # Verify history was recorded
        history = test_db_session.query(models.ComplaintStatusHistory).filter(
            models.ComplaintStatusHistory.complaint_id == complaint_id,
            models.ComplaintStatusHistory.is_auto_escalation == True
        ).first()
        
        assert history is not None
        assert history.old_level == 1
        assert history.new_level == 2
        assert history.changed_by_user_id is None  # Automatic


@pytest.mark.anyio
async def test_escalation_without_manual_action(test_db_session):
    """Test that escalation happens automatically without any manual intervention."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "auto_escalate_user")
        
        # Seed SLA rules
        _seed_sla_rules(test_db_session)
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "medication_error", "description": "Critical issue", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        initial_level = r.json()["current_level"]
        assert initial_level == 1
        
        # Simulate time passing - 25 hours (exceeds 24h SLA for medication_error)
        complaint = test_db_session.get(models.Complaint, complaint_id)
        complaint.created_at = datetime.utcnow() - timedelta(hours=25)
        complaint.sla_due_at = datetime.utcnow() - timedelta(hours=1)
        test_db_session.commit()
        
        # NO MANUAL ACTION - just run background worker
        result = run_escalation_check(test_db_session)
        
        # Verify automatic escalation
        assert result["escalated"] == 1
        
        test_db_session.refresh(complaint)
        assert complaint.current_level == 2
        assert complaint.status == models.ComplaintStatus.escalated
        
        # Verify it was automatic
        history = test_db_session.query(models.ComplaintStatusHistory).filter(
            models.ComplaintStatusHistory.complaint_id == complaint_id
        ).all()
        
        assert len(history) == 1
        assert history[0].is_auto_escalation is True
        assert history[0].changed_by_user_id is None


@pytest.mark.anyio
async def test_multiple_escalations(test_db_session):
    """Test that a complaint can escalate through all levels."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "multi_escalate_user")
        
        _seed_sla_rules(test_db_session)
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "medication_error", "description": "Critical", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        complaint = test_db_session.get(models.Complaint, complaint_id)
        
        # First escalation: level 1 → 2
        complaint.created_at = datetime.utcnow() - timedelta(hours=25)
        complaint.sla_due_at = datetime.utcnow() - timedelta(hours=1)
        test_db_session.commit()
        
        run_escalation_check(test_db_session)
        test_db_session.refresh(complaint)
        assert complaint.current_level == 2
        
        # Second escalation: level 2 → 3
        complaint.created_at = datetime.utcnow() - timedelta(hours=50)  # Total 50 hours (exceeds 48h for level 2)
        complaint.sla_due_at = datetime.utcnow() - timedelta(hours=1)
        test_db_session.commit()
        
        run_escalation_check(test_db_session)
        test_db_session.refresh(complaint)
        assert complaint.current_level == 3
        
        # Third escalation attempt: should NOT escalate beyond level 3
        complaint.created_at = datetime.utcnow() - timedelta(hours=80)
        complaint.sla_due_at = datetime.utcnow() - timedelta(hours=1)
        test_db_session.commit()
        
        run_escalation_check(test_db_session)
        test_db_session.refresh(complaint)
        assert complaint.current_level == 3  # Still 3, doesn't go beyond


@pytest.mark.anyio
async def test_resolved_complaint_not_escalated(test_db_session):
    """Test that resolved complaints are not escalated even if SLA breached."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "resolved_user")
        officer_token = await _register(client, "officer")
        
        # Assign officer role
        officer_profile = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {officer_token}"})).json()
        _assign_role(test_db_session, officer_profile["user_id"], models.RoleName.district_officer)
        
        _seed_sla_rules(test_db_session)
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "service_quality", "description": "Test", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        
        # Resolve complaint
        await client.put(
            f"/complaints/{complaint_id}/status",
            json={"status": "resolved", "resolution_notes": "Fixed"},
            headers={"Authorization": f"Bearer {officer_token}"}
        )
        
        # Simulate time passing
        complaint = test_db_session.get(models.Complaint, complaint_id)
        complaint.created_at = datetime.utcnow() - timedelta(hours=100)
        complaint.sla_due_at = datetime.utcnow() - timedelta(hours=1)
        test_db_session.commit()
        
        # Run escalation
        result = run_escalation_check(test_db_session)
        
        # Should not escalate resolved complaint
        test_db_session.refresh(complaint)
        assert complaint.current_level == 1  # Still at level 1
        assert complaint.status == models.ComplaintStatus.resolved


@pytest.mark.anyio
async def test_status_update_with_history(test_db_session):
    """Test manual status updates create history entries."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        citizen_token = await _register(client, "citizen")
        officer_token = await _register(client, "officer")
        
        # Assign officer role
        officer_profile = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {officer_token}"})).json()
        _assign_role(test_db_session, officer_profile["user_id"], models.RoleName.district_officer)
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "facility_issues", "description": "Broken AC", "is_anonymous": False},
            headers={"Authorization": f"Bearer {citizen_token}"}
        )
        complaint_id = r.json()["id"]
        
        # Update status
        r = await client.put(
            f"/complaints/{complaint_id}/status",
            json={"status": "under_review", "resolution_notes": "Investigating"},
            headers={"Authorization": f"Bearer {officer_token}"}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "under_review"
        
        # Get history
        r = await client.get(f"/complaints/{complaint_id}/history", headers={"Authorization": f"Bearer {officer_token}"})
        assert r.status_code == 200
        history = r.json()
        
        assert len(history) == 1
        assert history[0]["old_status"] == "submitted"
        assert history[0]["new_status"] == "under_review"
        assert history[0]["is_auto_escalation"] is False
        assert history[0]["change_reason"] == "Investigating"


@pytest.mark.anyio
async def test_manual_escalation_trigger(test_db_session):
    """Test manually triggering escalation check via API."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "admin_user")
        
        # Seed SLA rules so escalation check can run
        _seed_sla_rules(test_db_session)
        
        r = await client.post("/complaints/escalation/run", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        
        result = r.json()
        assert "checked" in result
        assert "escalated" in result
        assert "timestamp" in result
