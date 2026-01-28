import pytest
import httpx
import time
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


@pytest.mark.anyio
async def test_large_phraseboard_response_time():
    """Test large payload (5-10 MB) performance with gzip compression."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "aac_user")
        
        # Create symbol set
        r = await client.post(
            "/aac/symbol-sets",
            json={"name": "Large Set", "language": "en", "version": "1.0", "metadata": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        symbol_set_id = r.json()["id"]
        
        # Create large phraseboard (~5 MB JSON)
        # Each phrase ~100 bytes; 50,000 phrases ≈ 5 MB
        large_phrases = [
            {"id": i, "symbol": f"sym{i}", "text": f"phrase {i}", "category": "test"}
            for i in range(50000)
        ]
        
        start = time.time()
        r = await client.post(
            "/aac/phraseboards",
            json={"symbol_set_id": symbol_set_id, "title": "Large Phraseboard", "phrases": large_phrases},
            headers={"Authorization": f"Bearer {token}"},
        )
        create_time = time.time() - start
        assert r.status_code == 200
        pb_id = r.json()["id"]
        
        # Retrieve large phraseboard
        start = time.time()
        r = await client.get(f"/aac/phraseboards/{pb_id}", headers={"Authorization": f"Bearer {token}"})
        retrieve_time = time.time() - start
        assert r.status_code == 200
        
        # Validate response
        body = r.json()
        assert len(body["phrases"]) == 50000
        
        # Performance thresholds (relaxed for test env; production would be stricter)
        print(f"Large payload: create {create_time:.2f}s, retrieve {retrieve_time:.2f}s")
        assert create_time < 30  # 30s budget for 5 MB upload
        assert retrieve_time < 10  # 10s budget for 5 MB download (with gzip)


@pytest.mark.anyio
async def test_phraseboard_pagination():
    """Test pagination for listing phraseboards."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "pagination_user")
        
        # Create symbol set
        r = await client.post(
            "/aac/symbol-sets",
            json={"name": "Test Set", "language": "en", "version": "1.0", "metadata": {}, "symbols": []},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        symbol_set_id = r.json()["id"]
        
        # Create 25 phraseboards
        for i in range(25):
            r = await client.post(
                "/aac/phraseboards",
                json={"symbol_set_id": symbol_set_id, "title": f"Board {i}", "phrases": [{"id": i}]},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200
        
        # Paginate: first page (limit 10)
        r = await client.get(f"/aac/phraseboards?symbol_set_id={symbol_set_id}&limit=10&offset=0", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        page1 = r.json()
        assert len(page1) == 10
        
        # Second page
        r = await client.get(f"/aac/phraseboards?symbol_set_id={symbol_set_id}&limit=10&offset=10", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        page2 = r.json()
        assert len(page2) == 10
        
        # Third page
        r = await client.get(f"/aac/phraseboards?symbol_set_id={symbol_set_id}&limit=10&offset=20", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        page3 = r.json()
        assert len(page3) == 5
        
        # Verify no overlap
        ids_page1 = {p["id"] for p in page1}
        ids_page2 = {p["id"] for p in page2}
        assert len(ids_page1.intersection(ids_page2)) == 0


@pytest.mark.anyio
async def test_10k_symbols_performance():
    """Test 10k symbols can be created and retrieved within performance budget."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=120.0) as client:
        token = await _register(client, "symbol_perf_user")
        
        # Create symbol set with 10k symbols
        symbols = [
            {
                "name": f"symbol_{i}",
                "image_reference": f"https://cdn.example.com/symbols/{i}.png",
                "category": f"category_{i % 10}",
                "metadata": {"index": i}
            }
            for i in range(10000)
        ]
        
        start = time.time()
        r = await client.post(
            "/aac/symbol-sets",
            json={"name": "Large Symbol Set", "language": "en", "version": "1.0", "metadata": {}, "symbols": symbols},
            headers={"Authorization": f"Bearer {token}"},
        )
        create_time = time.time() - start
        assert r.status_code == 200
        symbol_set_id = r.json()["id"]
        assert len(r.json()["symbols"]) == 10000
        
        # Test paginated retrieval
        start = time.time()
        r = await client.get(
            f"/aac/symbol-sets/{symbol_set_id}?include_symbols=true&symbols_limit=1000&symbols_offset=0",
            headers={"Authorization": f"Bearer {token}"}
        )
        retrieve_time = time.time() - start
        assert r.status_code == 200
        assert len(r.json()["symbols"]) == 1000
        
        # Test metadata-only retrieval (should be fast)
        start = time.time()
        r = await client.get(
            f"/aac/symbol-sets/{symbol_set_id}?include_symbols=false",
            headers={"Authorization": f"Bearer {token}"}
        )
        metadata_time = time.time() - start
        assert r.status_code == 200
        assert len(r.json()["symbols"]) == 0
        
        # Performance thresholds
        print(f"10k symbols: create {create_time:.2f}s, retrieve 1k {retrieve_time:.2f}s, metadata {metadata_time:.2f}s")
        assert create_time < 60  # 60s budget for creating 10k symbols
        assert retrieve_time < 5  # 5s budget for retrieving 1k symbols
        assert metadata_time < 1  # 1s budget for metadata only


@pytest.mark.anyio
async def test_symbol_set_pagination():
    """Test pagination for listing symbol sets."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "symbolset_pagination_user")
        
        # Create 15 symbol sets
        for i in range(15):
            r = await client.post(
                "/aac/symbol-sets",
                json={"name": f"Set {i}", "language": "en", "version": "1.0", "metadata": {}, "symbols": []},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200
        
        # List with pagination
        r = await client.get("/aac/symbol-sets?limit=10&offset=0", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        page1 = r.json()
        assert len(page1) == 10
        
        r = await client.get("/aac/symbol-sets?limit=10&offset=10", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        page2 = r.json()
        assert len(page2) == 5
        
        # Verify symbol_count is present
        assert all("symbol_count" in s for s in page1)


@pytest.mark.anyio
async def test_get_single_phraseboard():
    """Test GET /aac/phraseboards/{id} endpoint."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "single_pb_user")
        
        # Create symbol set
        r = await client.post(
            "/aac/symbol-sets",
            json={"name": "Test Set", "language": "en", "version": "1.0", "metadata": {}, "symbols": []},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        symbol_set_id = r.json()["id"]
        
        # Create phraseboard
        phrases = [{"symbol": "hello", "text": "Hello"}, {"symbol": "goodbye", "text": "Goodbye"}]
        r = await client.post(
            "/aac/phraseboards",
            json={"symbol_set_id": symbol_set_id, "title": "Greetings", "phrases": phrases},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        pb_id = r.json()["id"]
        
        # Get single phraseboard
        r = await client.get(f"/aac/phraseboards/{pb_id}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        pb = r.json()
        assert pb["id"] == pb_id
        assert pb["title"] == "Greetings"
        assert len(pb["phrases"]) == 2
        
        # Try non-existent phraseboard
        r = await client.get("/aac/phraseboards/nonexistent", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404
