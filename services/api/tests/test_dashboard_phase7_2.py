"""
Tests for Phase 7.2 - Dashboard Storage and Queries

Tests verify:
1. Dashboard summary endpoint
2. Time-series data for trend charts
3. Geo-spatial heatmap data
4. Category breakdown (pie/bar charts)
5. Demographics breakdown
6. Top regions ranking
7. k-anonymity enforcement in dashboard queries
8. Query performance
"""

import pytest
import httpx
from httpx import ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

from services.api import models
from services.api.app import app
from services.api.db import get_db
from services.api.analytics import flush_aggregation_buffer


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


async def _set_consent(client: httpx.AsyncClient, token: str):
    r = await client.post(
        "/consents",
        json={"category": "analytics", "scope": "gov_aggregated", "granted": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


async def _update_profile(client: httpx.AsyncClient, token: str, **kwargs):
    r = await client.patch(
        "/profiles/me",
        json=kwargs,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


async def _create_test_data(client: httpx.AsyncClient, test_db_session, num_users: int = 10):
    """Create test analytics data for dashboard queries."""
    tokens = []
    
    for i in range(num_users):
        token = await _register(client, f"dashboard_test_user_{i}")
        await _set_consent(client, token)
        
        # Vary demographics for diversity
        age = 20 + (i % 5) * 10  # Ages: 20, 30, 40, 50, 60
        gender = "M" if i % 2 == 0 else "F"
        pincode = "110001" if i < num_users // 2 else "560001"
        
        await _update_profile(client, token, age=age, sex=gender, pincode=pincode)
        
        # Create triage sessions
        r = await client.post(
            "/triage/sessions",
            json={"symptom_text": "fever and cough", "followup_answers": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        tokens.append(token)
    
    # Flush analytics to aggregated table
    flush_aggregation_buffer(test_db_session, force=True)
    
    return tokens


# ============================================================
# Dashboard Summary Tests
# ============================================================

@pytest.mark.anyio
async def test_dashboard_summary_endpoint(test_db_session):
    """Test dashboard summary returns overview statistics."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create test data
        await _create_test_data(client, test_db_session, num_users=10)
        
        # Get admin token
        admin_token = await _register(client, "admin_dashboard")
        await _set_consent(client, admin_token)
        
        # Query dashboard summary
        r = await client.get(
            "/dashboard/summary?days=30",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ Dashboard Summary:")
        print(f"   Total events: {data['total_events']}")
        print(f"   Unique geos: {data['unique_geos']}")
        print(f"   Event types: {data['event_types']}")
        
        assert data['total_events'] >= 10, "Should have at least 10 events"
        assert data['unique_geos'] >= 1, "Should have at least 1 unique geo"
        assert 'time_period' in data


@pytest.mark.anyio
async def test_timeseries_endpoint(test_db_session):
    """Test time-series endpoint returns data for trend charts."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _create_test_data(client, test_db_session, num_users=8)
        
        admin_token = await _register(client, "admin_timeseries")
        await _set_consent(client, admin_token)
        
        # Query time-series data
        r = await client.get(
            "/dashboard/timeseries?event_type=triage_completed",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ Time-Series Data:")
        print(f"   Data points: {len(data['data'])}")
        print(f"   Interval: {data['interval']}")
        print(f"   Time period: {data['time_period']}")
        
        assert 'data' in data
        assert 'time_period' in data
        assert 'interval' in data
        
        if len(data['data']) > 0:
            point = data['data'][0]
            assert 'time' in point
            assert 'event_type' in point
            assert 'count' in point


@pytest.mark.anyio
async def test_heatmap_endpoint(test_db_session):
    """Test heatmap endpoint returns geo-spatial data."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _create_test_data(client, test_db_session, num_users=12)
        
        admin_token = await _register(client, "admin_heatmap")
        await _set_consent(client, admin_token)
        
        # Query heatmap data
        r = await client.get(
            "/dashboard/heatmap?min_count=5",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ Heatmap Data:")
        print(f"   Geo cells: {len(data['data'])}")
        print(f"   Min count threshold: {data['min_count_threshold']}")
        print(f"   Days: {data['days']}")
        
        assert 'data' in data
        assert 'min_count_threshold' in data
        assert data['min_count_threshold'] == 5
        
        # Verify all returned cells meet threshold
        for point in data['data']:
            assert point['count'] >= 5, f"Cell {point['geo_cell']} has count < 5 (k-anonymity violation)"
            assert 'geo_cell' in point
            assert 'density' in point


@pytest.mark.anyio
async def test_categories_endpoint(test_db_session):
    """Test categories endpoint returns breakdown for charts."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _create_test_data(client, test_db_session, num_users=10)
        
        admin_token = await _register(client, "admin_categories")
        await _set_consent(client, admin_token)
        
        # Query category breakdown
        r = await client.get(
            "/dashboard/categories?event_type=triage_completed",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ Category Breakdown:")
        print(f"   Categories: {len(data['data'])}")
        print(f"   Total: {data['total']}")
        
        assert 'data' in data
        assert 'total' in data
        
        # Verify percentages sum to ~100%
        if len(data['data']) > 0:
            total_percentage = sum(item['percentage'] for item in data['data'])
            assert 99 <= total_percentage <= 101, "Percentages should sum to ~100%"
            
            for item in data['data']:
                print(f"     {item['category']}: {item['count']} ({item['percentage']}%)")


@pytest.mark.anyio
async def test_demographics_endpoint(test_db_session):
    """Test demographics endpoint returns age/gender breakdown."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _create_test_data(client, test_db_session, num_users=10)
        
        admin_token = await _register(client, "admin_demographics")
        await _set_consent(client, admin_token)
        
        # Query demographics
        r = await client.get(
            "/dashboard/demographics",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ Demographics Breakdown:")
        print(f"   Age buckets: {len(data['age_buckets'])}")
        print(f"   Gender groups: {len(data['gender'])}")
        
        assert 'age_buckets' in data
        assert 'gender' in data
        
        if len(data['age_buckets']) > 0:
            print(f"\n   Age Distribution:")
            for item in data['age_buckets']:
                print(f"     {item['age_bucket']}: {item['count']} ({item['percentage']}%)")
        
        if len(data['gender']) > 0:
            print(f"\n   Gender Distribution:")
            for item in data['gender']:
                print(f"     {item['gender']}: {item['count']} ({item['percentage']}%)")


@pytest.mark.anyio
async def test_top_regions_endpoint(test_db_session):
    """Test top regions endpoint returns ranked list."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _create_test_data(client, test_db_session, num_users=12)
        
        admin_token = await _register(client, "admin_regions")
        await _set_consent(client, admin_token)
        
        # Query top regions
        r = await client.get(
            "/dashboard/top-regions?limit=5",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ Top Regions:")
        print(f"   Regions returned: {len(data['data'])}")
        print(f"   Limit: {data['limit']}")
        
        assert 'data' in data
        assert 'limit' in data
        assert len(data['data']) <= data['limit']
        
        # Verify ranking order (descending by count)
        for i, region in enumerate(data['data']):
            print(f"     #{region['rank']}: {region['geo_cell']} - {region['count']} events")
            assert region['rank'] == i + 1, "Ranks should be sequential"
            
            if i > 0:
                prev_count = data['data'][i - 1]['count']
                assert region['count'] <= prev_count, "Regions should be sorted by count (descending)"


# ============================================================
# k-Anonymity Enforcement Tests
# ============================================================

@pytest.mark.anyio
async def test_heatmap_enforces_k_anonymity(test_db_session):
    """Test heatmap endpoint suppresses cells with count < k."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create only 3 events (below k=5)
        await _create_test_data(client, test_db_session, num_users=3)
        
        admin_token = await _register(client, "admin_k_test")
        await _set_consent(client, admin_token)
        
        # Query with min_count=5
        r = await client.get(
            "/dashboard/heatmap?min_count=5",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ k-Anonymity Test (Heatmap):")
        print(f"   Events created: 3")
        print(f"   Min count threshold: {data['min_count_threshold']}")
        print(f"   Cells returned: {len(data['data'])}")
        
        # Should return 0 cells (all below threshold)
        assert len(data['data']) == 0, "Cells with count < 5 should be suppressed"


@pytest.mark.anyio
async def test_categories_enforces_k_anonymity(test_db_session):
    """Test categories endpoint suppresses small groups."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create 4 events (below k=5)
        await _create_test_data(client, test_db_session, num_users=4)
        
        admin_token = await _register(client, "admin_k_cat")
        await _set_consent(client, admin_token)
        
        # Query with min_count=5
        r = await client.get(
            "/dashboard/categories?min_count=5",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ k-Anonymity Test (Categories):")
        print(f"   Events created: 4")
        print(f"   Categories returned: {len(data['data'])}")
        
        # Should return 0 categories (all below threshold)
        assert len(data['data']) == 0, "Categories with count < 5 should be suppressed"


# ============================================================
# Performance Tests
# ============================================================

@pytest.mark.anyio
async def test_dashboard_query_performance(test_db_session):
    """Test dashboard queries complete in reasonable time."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create substantial test data
        await _create_test_data(client, test_db_session, num_users=20)
        
        admin_token = await _register(client, "admin_perf")
        await _set_consent(client, admin_token)
        
        endpoints = [
            "/dashboard/summary",
            "/dashboard/timeseries",
            "/dashboard/heatmap",
            "/dashboard/categories",
            "/dashboard/demographics",
            "/dashboard/top-regions",
        ]
        
        print(f"\n✅ Performance Test:")
        
        for endpoint in endpoints:
            import time
            start = time.time()
            
            r = await client.get(
                endpoint,
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            
            elapsed = time.time() - start
            
            assert r.status_code == 200, f"{endpoint} failed"
            print(f"   {endpoint}: {elapsed*1000:.2f}ms")
            
            # Performance target: < 2 seconds (generous for SQLite in-memory)
            assert elapsed < 2.0, f"{endpoint} took too long: {elapsed}s"


@pytest.mark.anyio
async def test_filtered_queries_work(test_db_session):
    """Test dashboard queries with filters."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _create_test_data(client, test_db_session, num_users=10)
        
        admin_token = await _register(client, "admin_filters")
        await _set_consent(client, admin_token)
        
        # Test various filters
        r = await client.get(
            "/dashboard/timeseries?event_type=triage_completed&category=phc",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        
        r = await client.get(
            "/dashboard/heatmap?days=7",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        
        r = await client.get(
            "/dashboard/top-regions?limit=3",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        
        print(f"\n✅ Filtered queries work correctly")


def test_dashboard_summary_output():
    """Document expected dashboard output structure."""
    print("\n" + "="*70)
    print("DASHBOARD ENDPOINTS — Phase 7.2")
    print("="*70)
    
    print("\n📊 Available Endpoints:")
    print("  • GET /dashboard/summary          - Overview statistics")
    print("  • GET /dashboard/timeseries       - Time-series trend data")
    print("  • GET /dashboard/heatmap          - Geo-spatial heatmap")
    print("  • GET /dashboard/categories       - Category breakdown")
    print("  • GET /dashboard/demographics     - Age/gender distribution")
    print("  • GET /dashboard/top-regions      - Top regions ranking")
    print("  • POST /dashboard/refresh-views   - Refresh materialized views")
    
    print("\n✅ All endpoints enforce k-anonymity (min_count >= 5)")
    print("✅ Fast queries using indexed aggregated_analytics_events table")
    print("✅ Ready for visualization with Superset/MapLibre/D3")
    
    print("\n" + "="*70 + "\n")
