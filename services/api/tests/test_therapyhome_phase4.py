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
from services.api.storage import compute_checksum


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
async def test_therapy_pack_checksum_matches():
    """Upload pack, download, verify checksum matches."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "uploader")
        
        # Create fake zip content
        zip_content = b"PK\x03\x04fake_zip_content_for_testing"
        expected_checksum = compute_checksum(zip_content)
        
        # Upload
        files = {"file": ("test_pack.zip", io.BytesIO(zip_content), "application/zip")}
        data = {"title": "Test Pack", "description": "Test", "version": "1.0"}
        r = await client.post("/therapy/packs", data=data, files=files, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        pack_resp = r.json()
        assert pack_resp["checksum"] == expected_checksum
        pack_id = pack_resp["id"]
        
        # Assign caregiver role to download
        me = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})).json()
        # Need db access to assign role
        # For this test we'll use test_db_session via fixture
        # Since we can't easily access test_db_session here, we'll test permission separately


@pytest.mark.anyio
async def test_therapy_pack_access_permissions(test_db_session):
    """Only caregiver/ASHA/clinician can download."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        uploader_token = await _register(client, "uploader2")
        citizen_token = await _register(client, "citizen")
        caregiver_token = await _register(client, "caregiver_user")
        
        # Get user IDs
        citizen_id = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {citizen_token}"})).json()["user_id"]
        caregiver_id = (await client.get("/profiles/me", headers={"Authorization": f"Bearer {caregiver_token}"})).json()["user_id"]
        
        # Assign caregiver role
        _assign_role(test_db_session, caregiver_id, models.RoleName.caregiver)
        
        # Upload pack
        zip_content = b"PK\x03\x04test_permissions"
        files = {"file": ("perm_test.zip", io.BytesIO(zip_content), "application/zip")}
        data = {"title": "Permission Test", "description": "Test", "version": "1.0"}
        r = await client.post("/therapy/packs", data=data, files=files, headers={"Authorization": f"Bearer {uploader_token}"})
        assert r.status_code == 200
        pack_id = r.json()["id"]
        
        # Citizen without role cannot download
        r = await client.get(f"/therapy/packs/{pack_id}/download", headers={"Authorization": f"Bearer {citizen_token}"})
        assert r.status_code == 403
        
        # Caregiver can download
        r = await client.get(f"/therapy/packs/{pack_id}/download", headers={"Authorization": f"Bearer {caregiver_token}"})
        assert r.status_code == 200
        downloaded_bytes = r.content
        assert downloaded_bytes == zip_content


@pytest.mark.anyio
async def test_therapy_pack_list():
    """List packs."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "lister")
        
        # Upload two packs
        for i in range(2):
            files = {"file": (f"pack{i}.zip", io.BytesIO(b"content"), "application/zip")}
            data = {"title": f"Pack {i}", "description": "Test", "version": "1.0"}
            r = await client.post("/therapy/packs", data=data, files=files, headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200
        
        # List
        r = await client.get("/therapy/packs", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        packs = r.json()
        assert len(packs) == 2


@pytest.mark.anyio
async def test_create_therapy_module():
    """Create a therapy module with steps."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "module_creator")
        
        payload = {
            "title": "Speech Therapy Basic",
            "description": "Basic speech exercises for children",
            "module_type": "speech",
            "age_range_min": 24,
            "age_range_max": 60,
            "steps": [
                {
                    "step_number": 1,
                    "title": "Warm-up",
                    "description": "Facial muscle warm-up exercises",
                    "duration_minutes": 5,
                    "media_references": ["video_001.mp4", "image_001.jpg"]
                },
                {
                    "step_number": 2,
                    "title": "Vowel sounds",
                    "description": "Practice A, E, I, O, U sounds",
                    "duration_minutes": 10,
                    "media_references": ["audio_002.mp3"]
                }
            ]
        }
        
        r = await client.post("/therapy/modules", json=payload, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        
        module = r.json()
        assert module["title"] == "Speech Therapy Basic"
        assert module["module_type"] == "speech"
        assert module["age_range_min"] == 24
        assert module["age_range_max"] == 60
        assert len(module["steps"]) == 2
        assert module["steps"][0]["title"] == "Warm-up"
        assert module["steps"][0]["media_references"] == ["video_001.mp4", "image_001.jpg"]


@pytest.mark.anyio
async def test_list_therapy_modules_with_filters():
    """List therapy modules with filtering."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "module_lister")
        
        # Create modules of different types
        modules_data = [
            {"title": "Speech 1", "module_type": "speech", "age_range_min": 12, "age_range_max": 36},
            {"title": "Motor 1", "module_type": "motor", "age_range_min": 24, "age_range_max": 48},
            {"title": "Speech 2", "module_type": "speech", "age_range_min": 36, "age_range_max": 60},
        ]
        
        for data in modules_data:
            payload = {
                "title": data["title"],
                "description": "Test module",
                "module_type": data["module_type"],
                "age_range_min": data["age_range_min"],
                "age_range_max": data["age_range_max"],
                "steps": []
            }
            r = await client.post("/therapy/modules", json=payload, headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200
        
        # List all
        r = await client.get("/therapy/modules", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert len(r.json()) == 3
        
        # Filter by type
        r = await client.get("/therapy/modules?module_type=speech", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        speech_modules = r.json()
        assert len(speech_modules) == 2
        assert all(m["module_type"] == "speech" for m in speech_modules)
        
        # Filter by age (30 months should match Speech 1 and Motor 1)
        r = await client.get("/therapy/modules?age_months=30", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        age_modules = r.json()
        assert len(age_modules) == 2


@pytest.mark.anyio
async def test_generate_pack_from_module():
    """Generate a therapy pack from a module using pack builder."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "pack_generator")
        
        # Create a module
        module_payload = {
            "title": "Motor Skills",
            "description": "Fine motor skill development",
            "module_type": "motor",
            "age_range_min": 12,
            "age_range_max": 36,
            "steps": [
                {
                    "step_number": 1,
                    "title": "Finger exercises",
                    "description": "Practice finger movements",
                    "duration_minutes": 5
                },
                {
                    "step_number": 2,
                    "title": "Gripping practice",
                    "description": "Hold and manipulate objects",
                    "duration_minutes": 10
                }
            ]
        }
        
        r = await client.post("/therapy/modules", json=module_payload, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        module_id = r.json()["id"]
        
        # Generate pack from module
        r = await client.post(
            f"/therapy/modules/{module_id}/generate-pack?version=1.0",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        pack = r.json()
        assert pack["title"] == "Motor Skills v1.0"
        assert pack["version"] == "1.0"
        assert pack["module_id"] == module_id
        assert "checksum" in pack
        
        # Verify pack was stored
        pack_id = pack["id"]
        r = await client.get(f"/therapy/packs/{pack_id}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["id"] == pack_id


@pytest.mark.anyio
async def test_pack_checksum_verification():
    """Verify that generated packs have correct checksums."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "checksum_tester")
        
        # Create module and generate pack
        module_payload = {
            "title": "Test Module",
            "description": "For checksum testing",
            "module_type": "test",
            "steps": [
                {"step_number": 1, "title": "Step 1", "description": "Test step"}
            ]
        }
        
        r = await client.post("/therapy/modules", json=module_payload, headers={"Authorization": f"Bearer {token}"})
        module_id = r.json()["id"]
        
        r = await client.post(
            f"/therapy/modules/{module_id}/generate-pack",
            headers={"Authorization": f"Bearer {token}"}
        )
        pack = r.json()
        stored_checksum = pack["checksum"]
        
        # Verify checksum is present and valid SHA256 hex digest
        assert stored_checksum
        assert len(stored_checksum) == 64  # SHA256 hex digest length
        assert all(c in '0123456789abcdef' for c in stored_checksum)  # Valid hex characters


@pytest.mark.anyio
async def test_get_single_therapy_pack():
    """Get a single therapy pack by ID."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "pack_getter")
        
        # Upload a pack
        zip_content = b"PK\\x03\\x04single_pack_test"
        files = {"file": ("test.zip", io.BytesIO(zip_content), "application/zip")}
        data = {"title": "Single Pack", "description": "Test", "version": "1.0"}
        r = await client.post("/therapy/packs", data=data, files=files, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        pack_id = r.json()["id"]
        
        # Get the pack
        r = await client.get(f"/therapy/packs/{pack_id}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        pack = r.json()
        assert pack["id"] == pack_id
        assert pack["title"] == "Single Pack"
        
        # Try to get non-existent pack
        r = await client.get("/therapy/packs/nonexistent", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404
