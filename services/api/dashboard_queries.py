"""
Dashboard Queries (Phase 7.2)

Optimized queries for GovSahay dashboards using materialized views.
Provides time-series, geo-spatial, and categorical aggregations.

Architecture:
- Raw table: AggregatedAnalyticsEvent (already has indexed aggregations)
- Materialized views: Pre-computed aggregations for fast dashboard queries
- Query layer: API endpoints for Superset/MapLibre visualization
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict
from sqlalchemy import text, func, and_
from sqlalchemy.orm import Session

from services.api import models


# ============================================================
# Materialized View Creation (SQL)
# ============================================================

# These SQL statements create materialized views for fast dashboard queries
# Execute once during deployment or via migration

MATERIALIZED_VIEW_DAILY_EVENTS = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_events AS
SELECT 
    DATE_TRUNC('day', time_bucket) as date,
    event_type,
    category,
    geo_cell,
    SUM(count) as total_count,
    COUNT(DISTINCT time_bucket) as unique_time_buckets,
    MIN(first_seen) as first_event,
    MAX(last_updated) as last_event
FROM aggregated_analytics_events
GROUP BY DATE_TRUNC('day', time_bucket), event_type, category, geo_cell;

CREATE INDEX IF NOT EXISTS idx_mv_daily_events_date ON mv_daily_events(date);
CREATE INDEX IF NOT EXISTS idx_mv_daily_events_geo ON mv_daily_events(geo_cell);
CREATE INDEX IF NOT EXISTS idx_mv_daily_events_type ON mv_daily_events(event_type);
"""

MATERIALIZED_VIEW_GEO_HEATMAP = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_geo_heatmap AS
SELECT 
    geo_cell,
    event_type,
    category,
    age_bucket,
    gender,
    SUM(count) as total_count,
    COUNT(*) as num_time_buckets,
    MIN(time_bucket) as earliest_event,
    MAX(time_bucket) as latest_event
FROM aggregated_analytics_events
WHERE time_bucket >= NOW() - INTERVAL '30 days'
GROUP BY geo_cell, event_type, category, age_bucket, gender;

CREATE INDEX IF NOT EXISTS idx_mv_geo_heatmap_geo ON mv_geo_heatmap(geo_cell);
CREATE INDEX IF NOT EXISTS idx_mv_geo_heatmap_type ON mv_geo_heatmap(event_type);
"""

MATERIALIZED_VIEW_TIME_SERIES = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_time_series AS
SELECT 
    time_bucket,
    event_type,
    category,
    SUM(count) as total_count,
    COUNT(DISTINCT geo_cell) as unique_geos,
    COUNT(DISTINCT age_bucket) as unique_age_groups
FROM aggregated_analytics_events
WHERE time_bucket >= NOW() - INTERVAL '7 days'
GROUP BY time_bucket, event_type, category;

CREATE INDEX IF NOT EXISTS idx_mv_time_series_time ON mv_time_series(time_bucket);
CREATE INDEX IF NOT EXISTS idx_mv_time_series_type ON mv_time_series(event_type);
"""

# Refresh commands (run periodically via cron or background worker)
REFRESH_MATERIALIZED_VIEWS = """
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_events;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geo_heatmap;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_time_series;
"""


def create_materialized_views(db: Session):
    """
    Create all materialized views for dashboard queries.
    
    Call this once during deployment or as part of database migrations.
    """
    db.execute(text(MATERIALIZED_VIEW_DAILY_EVENTS))
    db.execute(text(MATERIALIZED_VIEW_GEO_HEATMAP))
    db.execute(text(MATERIALIZED_VIEW_TIME_SERIES))
    db.commit()


def refresh_materialized_views(db: Session):
    """
    Refresh all materialized views with latest data.
    
    Should be called periodically (e.g., every 5-15 minutes) via background worker.
    """
    db.execute(text(REFRESH_MATERIALIZED_VIEWS))
    db.commit()


# ============================================================
# Dashboard Query Functions
# ============================================================

def get_time_series_data(
    *,
    db: Session,
    event_type: Optional[str] = None,
    category: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    interval: str = "1 hour",
) -> List[Dict]:
    """
    Get time-series data for trend charts.
    
    Args:
        db: Database session
        event_type: Filter by event type
        category: Filter by category
        start_date: Start date (default: 7 days ago)
        end_date: End date (default: now)
        interval: Time grouping (1 hour, 1 day, etc.)
    
    Returns:
        List of {time, event_type, category, count, unique_geos}
    """
    if start_date is None:
        start_date = datetime.utcnow() - timedelta(days=7)
    if end_date is None:
        end_date = datetime.utcnow()
    
    query = db.query(
        models.AggregatedAnalyticsEvent.time_bucket,
        models.AggregatedAnalyticsEvent.event_type,
        models.AggregatedAnalyticsEvent.category,
        func.sum(models.AggregatedAnalyticsEvent.count).label("total_count"),
        func.count(func.distinct(models.AggregatedAnalyticsEvent.geo_cell)).label("unique_geos"),
    )
    
    query = query.filter(
        and_(
            models.AggregatedAnalyticsEvent.time_bucket >= start_date,
            models.AggregatedAnalyticsEvent.time_bucket <= end_date,
        )
    )
    
    if event_type:
        query = query.filter(models.AggregatedAnalyticsEvent.event_type == event_type)
    if category:
        query = query.filter(models.AggregatedAnalyticsEvent.category == category)
    
    query = query.group_by(
        models.AggregatedAnalyticsEvent.time_bucket,
        models.AggregatedAnalyticsEvent.event_type,
        models.AggregatedAnalyticsEvent.category,
    ).order_by(models.AggregatedAnalyticsEvent.time_bucket)
    
    results = []
    for row in query.all():
        results.append({
            "time": row.time_bucket.isoformat(),
            "event_type": row.event_type,
            "category": row.category,
            "count": int(row.total_count),
            "unique_geos": int(row.unique_geos),
        })
    
    return results


def get_geo_heatmap_data(
    *,
    db: Session,
    event_type: Optional[str] = None,
    category: Optional[str] = None,
    min_count: int = 5,  # k-anonymity threshold
    days: int = 30,
) -> List[Dict]:
    """
    Get geo-spatial heatmap data for MapLibre visualization.
    
    Args:
        db: Database session
        event_type: Filter by event type
        category: Filter by category
        min_count: Minimum count threshold (k-anonymity)
        days: Number of days to look back
    
    Returns:
        List of {geo_cell, event_type, category, count, density}
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    query = db.query(
        models.AggregatedAnalyticsEvent.geo_cell,
        models.AggregatedAnalyticsEvent.event_type,
        models.AggregatedAnalyticsEvent.category,
        func.sum(models.AggregatedAnalyticsEvent.count).label("total_count"),
        func.count(func.distinct(models.AggregatedAnalyticsEvent.time_bucket)).label("time_buckets"),
    )
    
    query = query.filter(
        models.AggregatedAnalyticsEvent.time_bucket >= start_date
    )
    
    if event_type:
        query = query.filter(models.AggregatedAnalyticsEvent.event_type == event_type)
    if category:
        query = query.filter(models.AggregatedAnalyticsEvent.category == category)
    
    query = query.group_by(
        models.AggregatedAnalyticsEvent.geo_cell,
        models.AggregatedAnalyticsEvent.event_type,
        models.AggregatedAnalyticsEvent.category,
    ).having(func.sum(models.AggregatedAnalyticsEvent.count) >= min_count)
    
    results = []
    for row in query.all():
        results.append({
            "geo_cell": row.geo_cell,
            "event_type": row.event_type,
            "category": row.category,
            "count": int(row.total_count),
            "density": float(row.total_count) / float(row.time_buckets) if row.time_buckets > 0 else 0,
        })
    
    return results


def get_category_breakdown(
    *,
    db: Session,
    event_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    min_count: int = 5,
) -> List[Dict]:
    """
    Get category breakdown for pie/bar charts.
    
    Args:
        db: Database session
        event_type: Filter by event type
        start_date: Start date (default: 30 days ago)
        end_date: End date (default: now)
        min_count: Minimum count threshold
    
    Returns:
        List of {category, count, percentage}
    """
    if start_date is None:
        start_date = datetime.utcnow() - timedelta(days=30)
    if end_date is None:
        end_date = datetime.utcnow()
    
    query = db.query(
        models.AggregatedAnalyticsEvent.category,
        func.sum(models.AggregatedAnalyticsEvent.count).label("total_count"),
    )
    
    query = query.filter(
        and_(
            models.AggregatedAnalyticsEvent.time_bucket >= start_date,
            models.AggregatedAnalyticsEvent.time_bucket <= end_date,
        )
    )
    
    if event_type:
        query = query.filter(models.AggregatedAnalyticsEvent.event_type == event_type)
    
    query = query.group_by(
        models.AggregatedAnalyticsEvent.category
    ).having(func.sum(models.AggregatedAnalyticsEvent.count) >= min_count)
    
    results = query.all()
    total = sum(row.total_count for row in results)
    
    output = []
    for row in results:
        output.append({
            "category": row.category,
            "count": int(row.total_count),
            "percentage": round((row.total_count / total * 100), 2) if total > 0 else 0,
        })
    
    return sorted(output, key=lambda x: x["count"], reverse=True)


def get_demographics_breakdown(
    *,
    db: Session,
    event_type: Optional[str] = None,
    category: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    min_count: int = 5,
) -> Dict[str, List[Dict]]:
    """
    Get demographics breakdown (age, gender) for charts.
    
    Args:
        db: Database session
        event_type: Filter by event type
        category: Filter by category
        start_date: Start date (default: 30 days ago)
        end_date: End date (default: now)
        min_count: Minimum count threshold
    
    Returns:
        {
            "age_buckets": [{age_bucket, count, percentage}],
            "gender": [{gender, count, percentage}]
        }
    """
    if start_date is None:
        start_date = datetime.utcnow() - timedelta(days=30)
    if end_date is None:
        end_date = datetime.utcnow()
    
    base_filter = and_(
        models.AggregatedAnalyticsEvent.time_bucket >= start_date,
        models.AggregatedAnalyticsEvent.time_bucket <= end_date,
    )
    
    # Age breakdown
    age_query = db.query(
        models.AggregatedAnalyticsEvent.age_bucket,
        func.sum(models.AggregatedAnalyticsEvent.count).label("total_count"),
    ).filter(base_filter)
    
    if event_type:
        age_query = age_query.filter(models.AggregatedAnalyticsEvent.event_type == event_type)
    if category:
        age_query = age_query.filter(models.AggregatedAnalyticsEvent.category == category)
    
    age_query = age_query.group_by(
        models.AggregatedAnalyticsEvent.age_bucket
    ).having(func.sum(models.AggregatedAnalyticsEvent.count) >= min_count)
    
    age_results = age_query.all()
    age_total = sum(row.total_count for row in age_results)
    
    age_breakdown = []
    for row in age_results:
        age_breakdown.append({
            "age_bucket": row.age_bucket,
            "count": int(row.total_count),
            "percentage": round((row.total_count / age_total * 100), 2) if age_total > 0 else 0,
        })
    
    # Gender breakdown
    gender_query = db.query(
        models.AggregatedAnalyticsEvent.gender,
        func.sum(models.AggregatedAnalyticsEvent.count).label("total_count"),
    ).filter(base_filter)
    
    if event_type:
        gender_query = gender_query.filter(models.AggregatedAnalyticsEvent.event_type == event_type)
    if category:
        gender_query = gender_query.filter(models.AggregatedAnalyticsEvent.category == category)
    
    gender_query = gender_query.group_by(
        models.AggregatedAnalyticsEvent.gender
    ).having(func.sum(models.AggregatedAnalyticsEvent.count) >= min_count)
    
    gender_results = gender_query.all()
    gender_total = sum(row.total_count for row in gender_results)
    
    gender_breakdown = []
    for row in gender_results:
        gender_breakdown.append({
            "gender": row.gender,
            "count": int(row.total_count),
            "percentage": round((row.total_count / gender_total * 100), 2) if gender_total > 0 else 0,
        })
    
    return {
        "age_buckets": sorted(age_breakdown, key=lambda x: x["count"], reverse=True),
        "gender": sorted(gender_breakdown, key=lambda x: x["count"], reverse=True),
    }


def get_top_geo_cells(
    *,
    db: Session,
    event_type: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
    days: int = 30,
    min_count: int = 5,
) -> List[Dict]:
    """
    Get top geographic regions by event count (for ranking/tables).
    
    Args:
        db: Database session
        event_type: Filter by event type
        category: Filter by category
        limit: Number of top regions to return
        days: Number of days to look back
        min_count: Minimum count threshold
    
    Returns:
        List of {geo_cell, count, rank}
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    query = db.query(
        models.AggregatedAnalyticsEvent.geo_cell,
        func.sum(models.AggregatedAnalyticsEvent.count).label("total_count"),
    )
    
    query = query.filter(
        models.AggregatedAnalyticsEvent.time_bucket >= start_date
    )
    
    if event_type:
        query = query.filter(models.AggregatedAnalyticsEvent.event_type == event_type)
    if category:
        query = query.filter(models.AggregatedAnalyticsEvent.category == category)
    
    query = query.group_by(
        models.AggregatedAnalyticsEvent.geo_cell
    ).having(
        func.sum(models.AggregatedAnalyticsEvent.count) >= min_count
    ).order_by(
        func.sum(models.AggregatedAnalyticsEvent.count).desc()
    ).limit(limit)
    
    results = []
    for rank, row in enumerate(query.all(), start=1):
        results.append({
            "rank": rank,
            "geo_cell": row.geo_cell,
            "count": int(row.total_count),
        })
    
    return results


def get_dashboard_summary(
    *,
    db: Session,
    days: int = 30,
) -> Dict:
    """
    Get high-level summary stats for dashboard overview.
    
    Args:
        db: Database session
        days: Number of days to look back
    
    Returns:
        {
            "total_events": int,
            "unique_geos": int,
            "event_types": {event_type: count},
            "time_period": {start, end}
        }
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Total events
    total_events = db.query(
        func.sum(models.AggregatedAnalyticsEvent.count)
    ).filter(
        models.AggregatedAnalyticsEvent.time_bucket >= start_date
    ).scalar() or 0
    
    # Unique geo cells
    unique_geos = db.query(
        func.count(func.distinct(models.AggregatedAnalyticsEvent.geo_cell))
    ).filter(
        models.AggregatedAnalyticsEvent.time_bucket >= start_date
    ).scalar() or 0
    
    # Event type breakdown
    event_types_query = db.query(
        models.AggregatedAnalyticsEvent.event_type,
        func.sum(models.AggregatedAnalyticsEvent.count).label("total_count"),
    ).filter(
        models.AggregatedAnalyticsEvent.time_bucket >= start_date
    ).group_by(
        models.AggregatedAnalyticsEvent.event_type
    ).all()
    
    event_types = {row.event_type: int(row.total_count) for row in event_types_query}
    
    return {
        "total_events": int(total_events),
        "unique_geos": int(unique_geos),
        "event_types": event_types,
        "time_period": {
            "start": start_date.isoformat(),
            "end": datetime.utcnow().isoformat(),
            "days": days,
        },
    }
