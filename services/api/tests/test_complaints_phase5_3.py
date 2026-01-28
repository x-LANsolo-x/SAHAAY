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
    role = db.get(models.Role, role_name)
    if not role:
        db.add(models.Role(name=role_name))
        db.flush()
    db.add(models.UserRole(user_id=user_id, role_name=role_name))
    db.commit()


@pytest.mark.anyio
async def test_close_complaint_with_feedback(test_db_session):
    """Test successful closure with valid feedback."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        citizen_token = await _register(client, "citizen")
        officer_token = await _register(client, "officer")
        
        # Assign officer role
        officer_profile = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {officer_token}"})).json()
        _assign_role(test_db_session, officer_profile["user_id"], models.RoleName.district_officer)
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "service_quality", "description": "Long wait times", "is_anonymous": False},
            headers={"Authorization": f"Bearer {citizen_token}"}
        )
        complaint_id = r.json()["id"]
        
        # Close with feedback
        payload = {
            "feedback": {
                "rating": 4,
                "comments": "Issue was resolved quickly. Staff was helpful."
            },
            "resolution_notes": "Complaint addressed and resolved"
        }
        
        r = await client.patch(
            f"/complaints/{complaint_id}/close",
            json=payload,
            headers={"Authorization": f"Bearer {officer_token}"}
        )
        assert r.status_code == 200
        
        result = r.json()
        assert result["status"] == "closed"
        
        # Verify feedback was stored
        complaint = test_db_session.get(models.Complaint, complaint_id)
        assert complaint.feedback_rating == 4
        assert complaint.feedback_comments == "Issue was resolved quickly. Staff was helpful."
        assert complaint.feedback_submitted_at is not None
        assert complaint.closed_at is not None


@pytest.mark.anyio
async def test_closure_blocked_without_feedback(test_db_session):
    """Test that closure is blocked if feedback is missing."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        citizen_token = await _register(client, "citizen2")
        officer_token = await _register(client, "officer2")
        
        # Assign officer role
        officer_profile = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {officer_token}"})).json()
        _assign_role(test_db_session, officer_profile["user_id"], models.RoleName.district_officer)
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "staff_behavior", "description": "Rude behavior", "is_anonymous": False},
            headers={"Authorization": f"Bearer {citizen_token}"}
        )
        complaint_id = r.json()["id"]
        
        # Try to close without feedback (empty comments)
        payload = {
            "feedback": {
                "rating": 3,
                "comments": ""
            }
        }
        
        r = await client.patch(
            f"/complaints/{complaint_id}/close",
            json=payload,
            headers={"Authorization": f"Bearer {officer_token}"}
        )
        assert r.status_code == 400
        assert "required" in r.json()["detail"].lower()
        
        # Verify complaint is NOT closed
        complaint = test_db_session.get(models.Complaint, complaint_id)
        assert complaint.status != models.ComplaintStatus.closed
        assert complaint.feedback_rating is None


@pytest.mark.anyio
async def test_closure_blocked_with_invalid_rating(test_db_session):
    """Test that closure is blocked with invalid rating."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        citizen_token = await _register(client, "citizen3")
        officer_token = await _register(client, "officer3")
        
        # Assign officer role
        officer_profile = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {officer_token}"})).json()
        _assign_role(test_db_session, officer_profile["user_id"], models.RoleName.district_officer)
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "facility_issues", "description": "Broken equipment", "is_anonymous": False},
            headers={"Authorization": f"Bearer {citizen_token}"}
        )
        complaint_id = r.json()["id"]
        
        # Try with rating out of range (0)
        payload = {
            "feedback": {
                "rating": 0,
                "comments": "Very poor service"
            }
        }
        
        r = await client.patch(
            f"/complaints/{complaint_id}/close",
            json=payload,
            headers={"Authorization": f"Bearer {officer_token}"}
        )
        assert r.status_code == 400
        assert "1 and 5" in r.json()["detail"]
        
        # Try with rating > 5
        payload["feedback"]["rating"] = 6
        r = await client.patch(
            f"/complaints/{complaint_id}/close",
            json=payload,
            headers={"Authorization": f"Bearer {officer_token}"}
        )
        assert r.status_code == 400
        assert "1 and 5" in r.json()["detail"]


@pytest.mark.anyio
async def test_closure_requires_officer_role(test_db_session):
    """Test that only officers can close complaints."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        citizen_token = await _register(client, "citizen4")
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "billing_dispute", "description": "Overcharged", "is_anonymous": False},
            headers={"Authorization": f"Bearer {citizen_token}"}
        )
        complaint_id = r.json()["id"]
        
        # Try to close as citizen (not officer)
        payload = {
            "feedback": {
                "rating": 5,
                "comments": "All good now"
            }
        }
        
        r = await client.patch(
            f"/complaints/{complaint_id}/close",
            json=payload,
            headers={"Authorization": f"Bearer {citizen_token}"}
        )
        assert r.status_code == 403
        assert "officer" in r.json()["detail"].lower()


@pytest.mark.anyio
async def test_cannot_close_already_closed_complaint(test_db_session):
    """Test that already closed complaints cannot be closed again."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        citizen_token = await _register(client, "citizen5")
        officer_token = await _register(client, "officer5")
        
        # Assign officer role
        officer_profile = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {officer_token}"})).json()
        _assign_role(test_db_session, officer_profile["user_id"], models.RoleName.district_officer)
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "other", "description": "Test complaint", "is_anonymous": False},
            headers={"Authorization": f"Bearer {citizen_token}"}
        )
        complaint_id = r.json()["id"]
        
        # Close once
        payload = {
            "feedback": {
                "rating": 4,
                "comments": "Good service"
            }
        }
        
        r = await client.patch(
            f"/complaints/{complaint_id}/close",
            json=payload,
            headers={"Authorization": f"Bearer {officer_token}"}
        )
        assert r.status_code == 200
        
        # Try to close again
        r = await client.patch(
            f"/complaints/{complaint_id}/close",
            json=payload,
            headers={"Authorization": f"Bearer {officer_token}"}
        )
        assert r.status_code == 400
        assert "already closed" in r.json()["detail"].lower()


@pytest.mark.anyio
async def test_feedback_stored_in_history(test_db_session):
    """Test that closure creates proper history entry."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        citizen_token = await _register(client, "citizen6")
        officer_token = await _register(client, "officer6")
        
        # Assign officer role
        officer_profile = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {officer_token}"})).json()
        officer_id = officer_profile["user_id"]
        _assign_role(test_db_session, officer_id, models.RoleName.district_officer)
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "discrimination", "description": "Discrimination case", "is_anonymous": False},
            headers={"Authorization": f"Bearer {citizen_token}"}
        )
        complaint_id = r.json()["id"]
        
        # Close with feedback
        payload = {
            "feedback": {
                "rating": 5,
                "comments": "Matter resolved satisfactorily"
            },
            "resolution_notes": "Complaint investigated and resolved"
        }
        
        r = await client.patch(
            f"/complaints/{complaint_id}/close",
            json=payload,
            headers={"Authorization": f"Bearer {officer_token}"}
        )
        assert r.status_code == 200
        
        # Get history
        r = await client.get(f"/complaints/{complaint_id}/history", headers={"Authorization": f"Bearer {officer_token}"})
        assert r.status_code == 200
        history = r.json()
        
        # Find closure entry
        closure_entry = [h for h in history if h["new_status"] == "closed"]
        assert len(closure_entry) == 1
        assert closure_entry[0]["changed_by_user_id"] == officer_id
        assert closure_entry[0]["change_reason"] == "Complaint investigated and resolved"
        assert closure_entry[0]["is_auto_escalation"] is False


@pytest.mark.anyio
async def test_whitespace_only_comments_rejected(test_db_session):
    """Test that whitespace-only comments are rejected."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        citizen_token = await _register(client, "citizen7")
        officer_token = await _register(client, "officer7")
        
        # Assign officer role
        officer_profile = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {officer_token}"})).json()
        _assign_role(test_db_session, officer_profile["user_id"], models.RoleName.district_officer)
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "medication_error", "description": "Wrong prescription", "is_anonymous": False},
            headers={"Authorization": f"Bearer {citizen_token}"}
        )
        complaint_id = r.json()["id"]
        
        # Try to close with only whitespace
        payload = {
            "feedback": {
                "rating": 3,
                "comments": "   \n\t  "
            }
        }
        
        r = await client.patch(
            f"/complaints/{complaint_id}/close",
            json=payload,
            headers={"Authorization": f"Bearer {officer_token}"}
        )
        assert r.status_code == 400
        assert "required" in r.json()["detail"].lower()
