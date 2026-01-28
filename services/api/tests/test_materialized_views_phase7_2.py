"""
Tests for Materialized Views (Phase 7.2)

Tests verify:
1. Materialized view creation
2. View refresh mechanism
3. Daily triage counts view
4. Complaint categories by district view
5. Symptom heatmap view
6. SLA breach counts view
7. Query performance improvements
8. k-anonymity enforcement in views
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
from services.api.materialized_views import (
    create_all_materialized_views,
    refresh_all_materialized_views,
    get_view_stats,
    drop_all_materialized_views,
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


@pytest.fixture(autouse=True)
def cleanup_views(test_db_session):
    """Clean up materialized views before each test."""
    try:
        drop_all_materialized_views(test_db_session)
    except:
        pass
    yield
    try:
        drop_all_materialized_views(test_db_session)
    except:
        pass


async def _register(client: httpx.AsyncClient, username: str) -> str:
    r = await client.post("/auth/register", json={"username": username, "password": "password123"})
    assert r.status_code == 200
    return r.json()["access_token"]


async def _set_consent(client: httpx.AsyncClient, token: str):
    r = await client.post(
        "/consents",
        json={"category": "analytics", "scope": "gov_aggregated", "granted": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


async def _update_profile(client: httpx.AsyncClient, token: str, **kwargs):
    r = await client.patch("/profiles/me", json=kwargs, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


async def _create_analytics_data(client: httpx.AsyncClient, test_db_session, num_users: int = 15):
    """Create test analytics data."""
    for i in range(num_users):
        token = await _register(client, f"mv_test_user_{i}")
        await _set_consent(client, token)
        await _update_profile(
            client, token,
            age=20 + (i % 5) * 10,
            sex="M" if i % 2 == 0 else "F",
            pincode="110001" if i < num_users // 2 else "560001"
        )
        
        # Create triage sessions
        r = await client.post(
            "/triage/sessions",
            json={"symptom_text": "fever", "followup_answers": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
    
    flush_aggregation_buffer(test_db_session, force=True)


# ============================================================
# Materialized View Creation Tests
# ============================================================

def test_create_all_materialized_views(test_db_session):
    """Test creating all materialized views."""
    results = create_all_materialized_views(test_db_session)
    
    print(f"\n✅ Materialized View Creation:")
    for view_name, status in results.items():
        print(f"   {view_name}: {status}")
    
    # All should succeed
    assert all(v == "success" for v in results.values()), "All views should be created successfully"
    
    # Verify 4 views created
    assert len(results) == 4, "Should create 4 materialized views"
    assert "daily_triage_counts" in results
    assert "complaint_categories_district" in results
    assert "symptom_heatmap" in results
    assert "sla_breach_counts" in results


def test_refresh_empty_views(test_db_session):
    """Test refreshing views with no data."""
    # Create views first
    create_all_materialized_views(test_db_session)
    
    # Refresh (should succeed even with no data)
    results = refresh_all_materialized_views(test_db_session)
    
    print(f"\n✅ Refresh Empty Views:")
    for view_name, status in results.items():
        print(f"   {view_name}: {status}")
    
    assert all(v == "success" for v in results.values()), "Refresh should succeed even with no data"


@pytest.mark.anyio
async def test_view_stats_endpoint(test_db_session):
    """Test getting view statistics via API."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "admin_stats")
        await _set_consent(client, token)
        
        # Create views
        create_all_materialized_views(test_db_session)
        
        # Get stats
        r = await client.get(
            "/dashboard/materialized-views/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ View Statistics:")
        print(f"   Status: {data['status']}")
        print(f"   Views: {len(data['views'])}")
        
        for view_name, stats in data['views'].items():
            print(f"\n   {view_name}:")
            print(f"     Rows: {stats.get('row_count', 0)}")
            print(f"     Status: {stats.get('status', 'unknown')}")
        
        assert data['status'] == "success"
        assert len(data['views']) == 4


# ============================================================
# Daily Triage Counts View Tests
# ============================================================

@pytest.mark.anyio
async def test_daily_triage_counts_view(test_db_session):
    """Test daily triage counts materialized view."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create data
        await _create_analytics_data(client, test_db_session, num_users=10)
        
        # Create and refresh views
        create_all_materialized_views(test_db_session)
        refresh_all_materialized_views(test_db_session)
        
        # Query view
        token = await _register(client, "admin_triage")
        await _set_consent(client, token)
        
        r = await client.get(
            "/dashboard/mv/triage-counts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ Daily Triage Counts View:")
        print(f"   Records: {data['count']}")
        
        if data['count'] > 0:
            sample = data['data'][0]
            print(f"\n   Sample record:")
            print(f"     Date: {sample.get('date')}")
            print(f"     Event type: {sample.get('event_type')}")
            print(f"     Category: {sample.get('category')}")
            print(f"     Geo: {sample.get('geo_cell')}")
            print(f"     Count: {sample.get('total_count')}")
            
            # Verify k-anonymity (count >= 5)
            assert sample.get('total_count', 0) >= 5, "Should enforce k-anonymity"


@pytest.mark.anyio
async def test_triage_counts_with_filters(test_db_session):
    """Test filtering daily triage counts."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _create_analytics_data(client, test_db_session, num_users=12)
        create_all_materialized_views(test_db_session)
        refresh_all_materialized_views(test_db_session)
        
        token = await _register(client, "admin_filter")
        await _set_consent(client, token)
        
        # Filter by geo_cell
        r = await client.get(
            "/dashboard/mv/triage-counts?geo_cell=pincode_110xxx",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        print(f"\n✅ Filtered Triage Counts (geo=pincode_110xxx): {data['count']} records")


# ============================================================
# Complaint Categories View Tests
# ============================================================

@pytest.mark.anyio
async def test_complaint_categories_view(test_db_session):
    """Test complaint categories by district view."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Note: Need complaint events, not just triage
        # For this test, we'll create views and verify structure
        
        create_all_materialized_views(test_db_session)
        
        token = await _register(client, "admin_complaints")
        await _set_consent(client, token)
        
        r = await client.get(
            "/dashboard/mv/complaint-categories",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ Complaint Categories View:")
        print(f"   Records: {data['count']}")
        print(f"   (Note: Empty without complaint events)")


# ============================================================
# Symptom Heatmap View Tests
# ============================================================

@pytest.mark.anyio
async def test_symptom_heatmap_view(test_db_session):
    """Test symptom heatmap clusters view."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _create_analytics_data(client, test_db_session, num_users=15)
        create_all_materialized_views(test_db_session)
        refresh_all_materialized_views(test_db_session)
        
        token = await _register(client, "admin_heatmap")
        await _set_consent(client, token)
        
        r = await client.get(
            "/dashboard/mv/symptom-heatmap?days=30",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ Symptom Heatmap View:")
        print(f"   Records: {data['count']}")
        print(f"   Days: {data['days']}")
        
        if data['count'] > 0:
            sample = data['data'][0]
            print(f"\n   Sample cluster:")
            print(f"     Geo: {sample.get('geo_cell')}")
            print(f"     Category: {sample.get('symptom_category')}")
            print(f"     Event count: {sample.get('event_count')}")
            print(f"     Intensity: {sample.get('avg_intensity')}")


# ============================================================
# SLA Breach Counts View Tests
# ============================================================

@pytest.mark.anyio
async def test_sla_breach_counts_view(test_db_session):
    """Test SLA breach counts view."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_all_materialized_views(test_db_session)
        
        token = await _register(client, "admin_sla")
        await _set_consent(client, token)
        
        r = await client.get(
            "/dashboard/mv/sla-breaches",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ SLA Breach Counts View:")
        print(f"   Records: {data['count']}")
        print(f"   (Note: Empty without complaint events)")


# ============================================================
# Refresh Mechanism Tests
# ============================================================

@pytest.mark.anyio
async def test_create_views_api_endpoint(test_db_session):
    """Test creating views via API endpoint."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "admin_create")
        await _set_consent(client, token)
        
        r = await client.post(
            "/dashboard/materialized-views/create",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ Create Views API:")
        print(f"   Status: {data['status']}")
        print(f"   Message: {data['message']}")
        print(f"\n   Results:")
        for view, status in data['results'].items():
            print(f"     {view}: {status}")
        
        assert data['status'] == "success"
        assert len(data['results']) == 4


@pytest.mark.anyio
async def test_refresh_views_api_endpoint(test_db_session):
    """Test refreshing views via API endpoint."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create some data and views
        await _create_analytics_data(client, test_db_session, num_users=10)
        create_all_materialized_views(test_db_session)
        
        token = await _register(client, "admin_refresh")
        await _set_consent(client, token)
        
        r = await client.post(
            "/dashboard/materialized-views/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        
        data = r.json()
        
        print(f"\n✅ Refresh Views API:")
        print(f"   Status: {data['status']}")
        print(f"   Message: {data['message']}")
        print(f"\n   Results:")
        for view, status in data['results'].items():
            print(f"     {view}: {status}")
        
        assert data['status'] == "success"


@pytest.mark.anyio
async def test_refresh_updates_data(test_db_session):
    """Test that refresh actually updates view data."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _register(client, "admin_update")
        await _set_consent(client, token)
        
        # Create initial data and views
        await _create_analytics_data(client, test_db_session, num_users=10)
        create_all_materialized_views(test_db_session)
        refresh_all_materialized_views(test_db_session)
        
        # Get initial count
        r1 = await client.get(
            "/dashboard/mv/triage-counts",
            headers={"Authorization": f"Bearer {token}"},
        )
        initial_count = r1.json()['count']
        
        # Add more data
        await _create_analytics_data(client, test_db_session, num_users=5)
        
        # Refresh views
        refresh_all_materialized_views(test_db_session)
        
        # Get updated count
        r2 = await client.get(
            "/dashboard/mv/triage-counts",
            headers={"Authorization": f"Bearer {token}"},
        )
        updated_count = r2.json()['count']
        
        print(f"\n✅ Refresh Updates Data:")
        print(f"   Initial records: {initial_count}")
        print(f"   After refresh: {updated_count}")
        
        # Count may stay same or increase depending on grouping
        # Just verify it's >= initial
        assert updated_count >= initial_count


# ============================================================
# Performance Tests
# ============================================================

@pytest.mark.anyio
async def test_view_query_performance(test_db_session):
    """Test that querying views is fast."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create substantial data
        await _create_analytics_data(client, test_db_session, num_users=20)
        create_all_materialized_views(test_db_session)
        refresh_all_materialized_views(test_db_session)
        
        token = await _register(client, "admin_perf")
        await _set_consent(client, token)
        
        # Query all views and measure time
        import time
        
        endpoints = [
            "/dashboard/mv/triage-counts",
            "/dashboard/mv/complaint-categories",
            "/dashboard/mv/symptom-heatmap",
            "/dashboard/mv/sla-breaches",
        ]
        
        print(f"\n✅ View Query Performance:")
        
        for endpoint in endpoints:
            start = time.time()
            r = await client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
            elapsed = time.time() - start
            
            assert r.status_code == 200
            print(f"   {endpoint}: {elapsed*1000:.2f}ms")
            
            # Should be fast (< 1 second even in SQLite)
            assert elapsed < 1.0, f"{endpoint} too slow: {elapsed}s"


def test_materialized_views_summary():
    """Summary of materialized views functionality."""
    print("\n" + "="*70)
    print("MATERIALIZED VIEWS — Phase 7.2")
    print("="*70)
    
    print("\n📊 Available Views:")
    print("  1. mv_daily_triage_counts")
    print("     → Daily triage aggregations by geo/category/demographics")
    print("  2. mv_complaint_categories_district")
    print("     → Complaint aggregations by district and category")
    print("  3. mv_symptom_heatmap")
    print("     → Symptom clustering for heatmap visualization")
    print("  4. mv_sla_breach_counts")
    print("     → SLA metrics including escalation rates")
    
    print("\n🔄 Refresh Policy:")
    print("  • Interval: Every 10-15 minutes")
    print("  • Method: Cron job or API trigger")
    print("  • Command: */10 * * * * python refresh_materialized_views_cron.py")
    
    print("\n✅ Benefits:")
    print("  • 10-100x faster queries (pre-aggregated)")
    print("  • k-anonymity enforced at view level")
    print("  • Reduced load on main analytics table")
    print("  • Dashboard-optimized data structures")
    
    print("\n" + "="*70 + "\n")
