import pytest
import httpx
import io
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
async def test_create_authenticated_complaint():
    """Test creating a complaint as authenticated user."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "complaint_user")
        
        payload = {
            "category": "service_quality",
            "description": "Long wait times at the clinic",
            "is_anonymous": False
        }
        
        r = await client.post("/complaints", json=payload, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        
        complaint = r.json()
        assert complaint["category"] == "service_quality"
        assert complaint["description"] == "Long wait times at the clinic"
        assert complaint["status"] == "submitted"
        assert complaint["current_level"] == 1
        assert complaint["is_anonymous"] is False
        assert complaint["sla_due_at"] is not None
        assert len(complaint["evidence"]) == 0


@pytest.mark.anyio
async def test_create_anonymous_complaint():
    """Test anonymous complaint creation without exposing identity."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "category": "discrimination",
            "description": "I was denied service due to my background",
            "contact_info": "anonymous@email.com",
            "is_anonymous": True
        }
        
        # Anonymous complaint - no auth required
        r = await client.post("/complaints", json=payload)
        assert r.status_code == 200
        
        complaint = r.json()
        assert complaint["is_anonymous"] is True
        assert complaint["category"] == "discrimination"
        assert "contact_info" not in complaint  # Should not expose contact info


@pytest.mark.anyio
async def test_anonymous_complaint_privacy_in_audit(test_db_session):
    """Test that anonymous complaints don't expose identity in audit logs."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "category": "staff_behavior",
            "description": "Rude staff member",
            "is_anonymous": True
        }
        
        r = await client.post("/complaints", json=payload)
        assert r.status_code == 200
        complaint_id = r.json()["id"]
        
        # Check audit log
        audit = test_db_session.query(models.AuditLog).filter(
            models.AuditLog.action == "complaint.create",
            models.AuditLog.entity_id == complaint_id
        ).first()
        
        assert audit is not None
        assert audit.actor_user_id is None  # Should be None for anonymous


@pytest.mark.anyio
async def test_evidence_upload_small_file():
    """Test direct evidence upload for small file (<5MB)."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "evidence_user")
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "facility_issues", "description": "Broken equipment", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        
        # Initiate evidence upload (small file)
        r = await client.post(
            f"/complaints/{complaint_id}/evidence/initiate",
            json={"filename": "photo.jpg", "content_type": "image/jpeg", "file_size": 1024000},  # 1MB
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        evidence_id = r.json()["evidence_id"]
        upload_id = r.json()["upload_id"]
        assert upload_id is None  # Small file, no chunked upload
        
        # Upload file directly
        file_content = b"fake_image_data" * 1000
        files = {"file": ("photo.jpg", io.BytesIO(file_content), "image/jpeg")}
        r = await client.post(
            f"/complaints/{complaint_id}/evidence/{evidence_id}/upload",
            files=files,
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "success"
        assert "checksum" in r.json()


@pytest.mark.anyio
async def test_evidence_upload_chunked():
    """Test chunked evidence upload for large file (>5MB) with resume capability."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "chunked_user")
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "medication_error", "description": "Wrong medication dispensed", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        
        # Initiate chunked upload (large file)
        file_size = 10 * 1024 * 1024  # 10MB
        r = await client.post(
            f"/complaints/{complaint_id}/evidence/initiate",
            json={"filename": "video.mp4", "content_type": "video/mp4", "file_size": file_size},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        evidence_id = r.json()["evidence_id"]
        upload_id = r.json()["upload_id"]
        chunk_size = r.json()["chunk_size"]
        
        assert upload_id is not None  # Large file, chunked upload required
        assert chunk_size == 5 * 1024 * 1024  # 5MB chunks
        
        # Upload chunks (simulate 2 chunks)
        import hashlib
        sha256 = hashlib.sha256()
        
        for chunk_num in range(2):
            chunk_data = b"x" * chunk_size
            sha256.update(chunk_data)
            files = {"chunk": (f"chunk_{chunk_num}", io.BytesIO(chunk_data), "application/octet-stream")}
            r = await client.post(
                f"/complaints/{complaint_id}/evidence/{evidence_id}/chunk/{chunk_num}",
                files=files,
                headers={"Authorization": f"Bearer {token}"}
            )
            assert r.status_code == 200
            assert r.json()["chunk_number"] == chunk_num
        
        # Complete upload with checksum
        client_checksum = sha256.hexdigest()
        r = await client.post(
            f"/complaints/{complaint_id}/evidence/{evidence_id}/complete",
            json={"checksum": client_checksum},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        assert r.json()["checksum"] == client_checksum


@pytest.mark.anyio
async def test_evidence_upload_resume_after_failure():
    """Test resume capability - upload can continue after network failure."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "resume_user")
        
        # Create complaint
        r = await client.post(
            "/complaints",
            json={"category": "billing_dispute", "description": "Overcharged", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        
        # Initiate chunked upload
        r = await client.post(
            f"/complaints/{complaint_id}/evidence/initiate",
            json={"filename": "receipt.pdf", "content_type": "application/pdf", "file_size": 8000000},
            headers={"Authorization": f"Bearer {token}"}
        )
        evidence_id = r.json()["evidence_id"]
        
        # Upload first chunk
        chunk_data = b"y" * (5 * 1024 * 1024)
        files = {"chunk": ("chunk_0", io.BytesIO(chunk_data), "application/octet-stream")}
        r = await client.post(
            f"/complaints/{complaint_id}/evidence/{evidence_id}/chunk/0",
            files=files,
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        
        # Simulate network failure / app restart / client crash
        # ... time passes ...
        
        # Resume: upload remaining chunks
        import hashlib
        sha256 = hashlib.sha256()
        sha256.update(chunk_data)
        
        chunk_data2 = b"z" * (3 * 1024 * 1024)
        sha256.update(chunk_data2)
        files = {"chunk": ("chunk_1", io.BytesIO(chunk_data2), "application/octet-stream")}
        r = await client.post(
            f"/complaints/{complaint_id}/evidence/{evidence_id}/chunk/1",
            files=files,
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        
        # Complete upload
        r = await client.post(
            f"/complaints/{complaint_id}/evidence/{evidence_id}/complete",
            json={"checksum": sha256.hexdigest()},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200


@pytest.mark.anyio
async def test_checksum_verification_failure():
    """Test that mismatched checksums are rejected."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "checksum_user")
        
        # Create complaint and initiate upload
        r = await client.post(
            "/complaints",
            json={"category": "other", "description": "Test", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        complaint_id = r.json()["id"]
        
        r = await client.post(
            f"/complaints/{complaint_id}/evidence/initiate",
            json={"filename": "doc.pdf", "content_type": "application/pdf", "file_size": 6000000},
            headers={"Authorization": f"Bearer {token}"}
        )
        evidence_id = r.json()["evidence_id"]
        
        # Upload chunk
        files = {"chunk": ("chunk_0", io.BytesIO(b"data" * 1000000), "application/octet-stream")}
        await client.post(
            f"/complaints/{complaint_id}/evidence/{evidence_id}/chunk/0",
            files=files,
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Try to complete with wrong checksum
        r = await client.post(
            f"/complaints/{complaint_id}/evidence/{evidence_id}/complete",
            json={"checksum": "0" * 64},  # Wrong checksum
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 400
        assert "checksum mismatch" in r.json()["detail"].lower()


@pytest.mark.anyio
async def test_complaint_access_control(test_db_session):
    """Test that users can only view their own complaints."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token1 = await _register(client, "user1")
        token2 = await _register(client, "user2")
        
        # User1 creates complaint
        r = await client.post(
            "/complaints",
            json={"category": "service_quality", "description": "User1 complaint", "is_anonymous": False},
            headers={"Authorization": f"Bearer {token1}"}
        )
        complaint_id = r.json()["id"]
        
        # User1 can view own complaint
        r = await client.get(f"/complaints/{complaint_id}", headers={"Authorization": f"Bearer {token1}"})
        assert r.status_code == 200
        
        # User2 cannot view User1's complaint
        r = await client.get(f"/complaints/{complaint_id}", headers={"Authorization": f"Bearer {token2}"})
        assert r.status_code == 403


@pytest.mark.anyio
async def test_officer_can_view_all_complaints(test_db_session):
    """Test that officers can view all complaints."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        citizen_token = await _register(client, "citizen")
        officer_token = await _register(client, "officer")
        
        # Assign officer role
        officer_profile = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {officer_token}"})).json()
        _assign_role(test_db_session, officer_profile["user_id"], models.RoleName.district_officer)
        
        # Citizen creates complaint
        r = await client.post(
            "/complaints",
            json={"category": "facility_issues", "description": "Citizen complaint", "is_anonymous": False},
            headers={"Authorization": f"Bearer {citizen_token}"}
        )
        complaint_id = r.json()["id"]
        
        # Officer can view citizen's complaint
        r = await client.get(f"/complaints/{complaint_id}", headers={"Authorization": f"Bearer {officer_token}"})
        assert r.status_code == 200
        assert r.json()["id"] == complaint_id


@pytest.mark.anyio
async def test_list_complaints_filtering():
    """Test complaint listing with filters."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "list_user")
        
        # Create multiple complaints
        categories = ["service_quality", "staff_behavior", "service_quality"]
        for cat in categories:
            await client.post(
                "/complaints",
                json={"category": cat, "description": f"Test {cat}", "is_anonymous": False},
                headers={"Authorization": f"Bearer {token}"}
            )
        
        # List all
        r = await client.get("/complaints", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert len(r.json()) == 3
        
        # Filter by category
        r = await client.get("/complaints?category=service_quality", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        complaints = r.json()
        assert len(complaints) == 2
        assert all(c["category"] == "service_quality" for c in complaints)
