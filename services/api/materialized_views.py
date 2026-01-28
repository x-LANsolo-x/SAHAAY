"""
Materialized Views for Dashboard Queries (Phase 7.2)

Pre-aggregated views for fast dashboard queries:
1. Daily triage counts
2. Complaint categories by district
3. Symptom heatmap clusters
4. SLA breach counts

Refresh policy: Every 10-15 minutes via cron job
"""

from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ============================================================
# Materialized View 1: Daily Triage Counts
# ============================================================

MV_DAILY_TRIAGE_COUNTS = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_triage_counts AS
SELECT 
    DATE(time_bucket) as date,
    event_type,
    category,
    geo_cell,
    age_bucket,
    gender,
    SUM(count) as total_count,
    COUNT(DISTINCT time_bucket) as unique_time_buckets,
    MIN(first_seen) as first_event,
    MAX(last_updated) as last_event
FROM aggregated_analytics_events
WHERE event_type IN ('triage_completed', 'triage_emergency')
GROUP BY DATE(time_bucket), event_type, category, geo_cell, age_bucket, gender
HAVING SUM(count) >= 5;

CREATE INDEX IF NOT EXISTS idx_mv_daily_triage_date ON mv_daily_triage_counts(date DESC);
CREATE INDEX IF NOT EXISTS idx_mv_daily_triage_geo ON mv_daily_triage_counts(geo_cell);
CREATE INDEX IF NOT EXISTS idx_mv_daily_triage_category ON mv_daily_triage_counts(category);
"""

# SQLite-compatible version (no MATERIALIZED VIEW support)
MV_DAILY_TRIAGE_COUNTS_SQLITE = """
DROP TABLE IF EXISTS mv_daily_triage_counts;

CREATE TABLE mv_daily_triage_counts AS
SELECT 
    DATE(time_bucket) as date,
    event_type,
    category,
    geo_cell,
    age_bucket,
    gender,
    SUM(count) as total_count,
    COUNT(DISTINCT time_bucket) as unique_time_buckets,
    MIN(first_seen) as first_event,
    MAX(last_updated) as last_event
FROM aggregated_analytics_events
WHERE event_type IN ('triage_completed', 'triage_emergency')
GROUP BY DATE(time_bucket), event_type, category, geo_cell, age_bucket, gender
HAVING SUM(count) >= 5;

CREATE INDEX IF NOT EXISTS idx_mv_daily_triage_date ON mv_daily_triage_counts(date);
CREATE INDEX IF NOT EXISTS idx_mv_daily_triage_geo ON mv_daily_triage_counts(geo_cell);
CREATE INDEX IF NOT EXISTS idx_mv_daily_triage_category ON mv_daily_triage_counts(category);
"""


# ============================================================
# Materialized View 2: Complaint Categories by District
# ============================================================

MV_COMPLAINT_CATEGORIES_BY_DISTRICT = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_complaint_categories_district AS
SELECT 
    geo_cell,
    category,
    event_type,
    DATE(time_bucket) as date,
    SUM(count) as total_complaints,
    COUNT(DISTINCT time_bucket) as time_periods,
    AVG(count) as avg_complaints_per_period,
    MIN(first_seen) as earliest_complaint,
    MAX(last_updated) as latest_complaint
FROM aggregated_analytics_events
WHERE event_type IN ('complaint_submitted', 'complaint_resolved', 'complaint_escalated')
GROUP BY geo_cell, category, event_type, DATE(time_bucket)
HAVING SUM(count) >= 5;

CREATE INDEX IF NOT EXISTS idx_mv_complaints_geo ON mv_complaint_categories_district(geo_cell);
CREATE INDEX IF NOT EXISTS idx_mv_complaints_category ON mv_complaint_categories_district(category);
CREATE INDEX IF NOT EXISTS idx_mv_complaints_date ON mv_complaint_categories_district(date DESC);
"""

# SQLite-compatible version
MV_COMPLAINT_CATEGORIES_BY_DISTRICT_SQLITE = """
DROP TABLE IF EXISTS mv_complaint_categories_district;

CREATE TABLE mv_complaint_categories_district AS
SELECT 
    geo_cell,
    category,
    event_type,
    DATE(time_bucket) as date,
    SUM(count) as total_complaints,
    COUNT(DISTINCT time_bucket) as time_periods,
    AVG(count) as avg_complaints_per_period,
    MIN(first_seen) as earliest_complaint,
    MAX(last_updated) as latest_complaint
FROM aggregated_analytics_events
WHERE event_type IN ('complaint_submitted', 'complaint_resolved', 'complaint_escalated')
GROUP BY geo_cell, category, event_type, DATE(time_bucket)
HAVING SUM(count) >= 5;

CREATE INDEX IF NOT EXISTS idx_mv_complaints_geo ON mv_complaint_categories_district(geo_cell);
CREATE INDEX IF NOT EXISTS idx_mv_complaints_category ON mv_complaint_categories_district(category);
CREATE INDEX IF NOT EXISTS idx_mv_complaints_date ON mv_complaint_categories_district(date);
"""


# ============================================================
# Materialized View 3: Symptom Heatmap Clusters
# ============================================================

MV_SYMPTOM_HEATMAP = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_symptom_heatmap AS
SELECT 
    geo_cell,
    category as symptom_category,
    event_type,
    DATE(time_bucket) as date,
    SUM(count) as event_count,
    COUNT(DISTINCT age_bucket) as age_diversity,
    COUNT(DISTINCT gender) as gender_diversity,
    AVG(count) as avg_intensity,
    MAX(count) as max_intensity
FROM aggregated_analytics_events
WHERE event_type IN ('triage_completed', 'triage_emergency')
  AND time_bucket >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY geo_cell, category, event_type, DATE(time_bucket)
HAVING SUM(count) >= 5;

CREATE INDEX IF NOT EXISTS idx_mv_symptom_geo ON mv_symptom_heatmap(geo_cell);
CREATE INDEX IF NOT EXISTS idx_mv_symptom_category ON mv_symptom_heatmap(symptom_category);
CREATE INDEX IF NOT EXISTS idx_mv_symptom_date ON mv_symptom_heatmap(date DESC);
"""

# SQLite-compatible version
MV_SYMPTOM_HEATMAP_SQLITE = """
DROP TABLE IF EXISTS mv_symptom_heatmap;

CREATE TABLE mv_symptom_heatmap AS
SELECT 
    geo_cell,
    category as symptom_category,
    event_type,
    DATE(time_bucket) as date,
    SUM(count) as event_count,
    COUNT(DISTINCT age_bucket) as age_diversity,
    COUNT(DISTINCT gender) as gender_diversity,
    AVG(count) as avg_intensity,
    MAX(count) as max_intensity
FROM aggregated_analytics_events
WHERE event_type IN ('triage_completed', 'triage_emergency')
  AND time_bucket >= DATE('now', '-30 days')
GROUP BY geo_cell, category, event_type, DATE(time_bucket)
HAVING SUM(count) >= 5;

CREATE INDEX IF NOT EXISTS idx_mv_symptom_geo ON mv_symptom_heatmap(geo_cell);
CREATE INDEX IF NOT EXISTS idx_mv_symptom_category ON mv_symptom_heatmap(symptom_category);
CREATE INDEX IF NOT EXISTS idx_mv_symptom_date ON mv_symptom_heatmap(date);
"""


# ============================================================
# Materialized View 4: SLA Breach Counts
# ============================================================

MV_SLA_BREACH_COUNTS = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_sla_breach_counts AS
SELECT 
    geo_cell,
    category as complaint_category,
    DATE(time_bucket) as date,
    SUM(CASE WHEN event_type = 'complaint_escalated' THEN count ELSE 0 END) as escalated_count,
    SUM(CASE WHEN event_type = 'complaint_resolved' THEN count ELSE 0 END) as resolved_count,
    SUM(count) as total_complaints,
    CAST(SUM(CASE WHEN event_type = 'complaint_escalated' THEN count ELSE 0 END) AS FLOAT) / 
        NULLIF(SUM(count), 0) * 100 as escalation_rate,
    COUNT(DISTINCT time_bucket) as time_periods
FROM aggregated_analytics_events
WHERE event_type IN ('complaint_submitted', 'complaint_resolved', 'complaint_escalated')
  AND time_bucket >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY geo_cell, category, DATE(time_bucket)
HAVING SUM(count) >= 5;

CREATE INDEX IF NOT EXISTS idx_mv_sla_geo ON mv_sla_breach_counts(geo_cell);
CREATE INDEX IF NOT EXISTS idx_mv_sla_category ON mv_sla_breach_counts(complaint_category);
CREATE INDEX IF NOT EXISTS idx_mv_sla_date ON mv_sla_breach_counts(date DESC);
CREATE INDEX IF NOT EXISTS idx_mv_sla_escalation_rate ON mv_sla_breach_counts(escalation_rate DESC);
"""

# SQLite-compatible version
MV_SLA_BREACH_COUNTS_SQLITE = """
DROP TABLE IF EXISTS mv_sla_breach_counts;

CREATE TABLE mv_sla_breach_counts AS
SELECT 
    geo_cell,
    category as complaint_category,
    DATE(time_bucket) as date,
    SUM(CASE WHEN event_type = 'complaint_escalated' THEN count ELSE 0 END) as escalated_count,
    SUM(CASE WHEN event_type = 'complaint_resolved' THEN count ELSE 0 END) as resolved_count,
    SUM(count) as total_complaints,
    CAST(SUM(CASE WHEN event_type = 'complaint_escalated' THEN count ELSE 0 END) AS FLOAT) / 
        NULLIF(SUM(count), 0) * 100 as escalation_rate,
    COUNT(DISTINCT time_bucket) as time_periods
FROM aggregated_analytics_events
WHERE event_type IN ('complaint_submitted', 'complaint_resolved', 'complaint_escalated')
  AND time_bucket >= DATE('now', '-90 days')
GROUP BY geo_cell, category, DATE(time_bucket)
HAVING SUM(count) >= 5;

CREATE INDEX IF NOT EXISTS idx_mv_sla_geo ON mv_sla_breach_counts(geo_cell);
CREATE INDEX IF NOT EXISTS idx_mv_sla_category ON mv_sla_breach_counts(complaint_category);
CREATE INDEX IF NOT EXISTS idx_mv_sla_date ON mv_sla_breach_counts(date);
CREATE INDEX IF NOT EXISTS idx_mv_sla_escalation_rate ON mv_sla_breach_counts(escalation_rate);
"""


# ============================================================
# Helper Functions
# ============================================================

def is_postgres(db: Session) -> bool:
    """Check if database is PostgreSQL."""
    dialect = db.bind.dialect.name
    return dialect == 'postgresql'


def create_all_materialized_views(db: Session) -> dict:
    """
    Create all materialized views.
    
    Args:
        db: Database session
    
    Returns:
        dict: Status of each view creation
    """
    results = {}
    use_postgres = is_postgres(db)
    
    views = [
        ("daily_triage_counts", MV_DAILY_TRIAGE_COUNTS if use_postgres else MV_DAILY_TRIAGE_COUNTS_SQLITE),
        ("complaint_categories_district", MV_COMPLAINT_CATEGORIES_BY_DISTRICT if use_postgres else MV_COMPLAINT_CATEGORIES_BY_DISTRICT_SQLITE),
        ("symptom_heatmap", MV_SYMPTOM_HEATMAP if use_postgres else MV_SYMPTOM_HEATMAP_SQLITE),
        ("sla_breach_counts", MV_SLA_BREACH_COUNTS if use_postgres else MV_SLA_BREACH_COUNTS_SQLITE),
    ]
    
    for view_name, view_sql in views:
        try:
            logger.info(f"Creating materialized view: {view_name}")
            
            # SQLite requires executing statements one at a time
            for statement in view_sql.split(';'):
                statement = statement.strip()
                if statement:  # Skip empty statements
                    db.execute(text(statement))
            
            db.commit()
            results[view_name] = "success"
            logger.info(f"Successfully created: {view_name}")
        except Exception as e:
            logger.error(f"Error creating {view_name}: {str(e)}")
            results[view_name] = f"error: {str(e)}"
            db.rollback()
    
    return results


def refresh_all_materialized_views(db: Session) -> dict:
    """
    Refresh all materialized views with latest data.
    
    Should be called every 10-15 minutes via cron job.
    
    Args:
        db: Database session
    
    Returns:
        dict: Status of each view refresh
    """
    results = {}
    use_postgres = is_postgres(db)
    
    if use_postgres:
        # PostgreSQL: Use REFRESH MATERIALIZED VIEW CONCURRENTLY
        views = [
            "mv_daily_triage_counts",
            "mv_complaint_categories_district",
            "mv_symptom_heatmap",
            "mv_sla_breach_counts",
        ]
        
        for view_name in views:
            try:
                logger.info(f"Refreshing materialized view: {view_name}")
                db.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}"))
                db.commit()
                results[view_name] = "success"
                logger.info(f"Successfully refreshed: {view_name}")
            except Exception as e:
                logger.error(f"Error refreshing {view_name}: {str(e)}")
                results[view_name] = f"error: {str(e)}"
                db.rollback()
    else:
        # SQLite: Recreate tables (no MATERIALIZED VIEW support)
        logger.info("SQLite detected - recreating views as tables")
        return create_all_materialized_views(db)
    
    return results


def get_view_stats(db: Session) -> dict:
    """
    Get statistics about materialized views.
    
    Args:
        db: Database session
    
    Returns:
        dict: Row counts and freshness info for each view
    """
    stats = {}
    
    views = [
        "mv_daily_triage_counts",
        "mv_complaint_categories_district",
        "mv_symptom_heatmap",
        "mv_sla_breach_counts",
    ]
    
    for view_name in views:
        try:
            # Check if view exists
            count_result = db.execute(text(f"SELECT COUNT(*) as cnt FROM {view_name}")).fetchone()
            count = count_result[0] if count_result else 0
            
            # Get date range
            date_result = db.execute(text(f"SELECT MIN(date) as min_date, MAX(date) as max_date FROM {view_name}")).fetchone()
            
            stats[view_name] = {
                "row_count": count,
                "min_date": str(date_result[0]) if date_result and date_result[0] else None,
                "max_date": str(date_result[1]) if date_result and date_result[1] else None,
                "status": "active",
            }
        except Exception as e:
            stats[view_name] = {
                "row_count": 0,
                "status": "error",
                "error": str(e),
            }
    
    return stats


def drop_all_materialized_views(db: Session) -> dict:
    """
    Drop all materialized views (for testing/cleanup).
    
    Args:
        db: Database session
    
    Returns:
        dict: Status of each view drop
    """
    results = {}
    use_postgres = is_postgres(db)
    
    views = [
        "mv_daily_triage_counts",
        "mv_complaint_categories_district",
        "mv_symptom_heatmap",
        "mv_sla_breach_counts",
    ]
    
    for view_name in views:
        try:
            if use_postgres:
                db.execute(text(f"DROP MATERIALIZED VIEW IF EXISTS {view_name} CASCADE"))
            else:
                db.execute(text(f"DROP TABLE IF EXISTS {view_name}"))
            db.commit()
            results[view_name] = "dropped"
        except Exception as e:
            logger.error(f"Error dropping {view_name}: {str(e)}")
            results[view_name] = f"error: {str(e)}"
            db.rollback()
    
    return results


# ============================================================
# Query Functions for Materialized Views
# ============================================================

def query_daily_triage_counts(
    db: Session,
    start_date: str | None = None,
    end_date: str | None = None,
    geo_cell: str | None = None,
) -> list[dict]:
    """
    Query daily triage counts from materialized view.
    
    Much faster than querying aggregated_analytics_events directly.
    """
    query = "SELECT * FROM mv_daily_triage_counts WHERE 1=1"
    params = {}
    
    if start_date:
        query += " AND date >= :start_date"
        params["start_date"] = start_date
    
    if end_date:
        query += " AND date <= :end_date"
        params["end_date"] = end_date
    
    if geo_cell:
        query += " AND geo_cell = :geo_cell"
        params["geo_cell"] = geo_cell
    
    query += " ORDER BY date DESC, total_count DESC"
    
    results = db.execute(text(query), params).fetchall()
    
    return [dict(row._mapping) for row in results]


def query_complaint_categories(
    db: Session,
    geo_cell: str | None = None,
    category: str | None = None,
) -> list[dict]:
    """Query complaint categories by district from materialized view."""
    query = "SELECT * FROM mv_complaint_categories_district WHERE 1=1"
    params = {}
    
    if geo_cell:
        query += " AND geo_cell = :geo_cell"
        params["geo_cell"] = geo_cell
    
    if category:
        query += " AND category = :category"
        params["category"] = category
    
    query += " ORDER BY total_complaints DESC"
    
    results = db.execute(text(query), params).fetchall()
    
    return [dict(row._mapping) for row in results]


def query_symptom_heatmap(
    db: Session,
    days: int = 30,
) -> list[dict]:
    """Query symptom heatmap clusters from materialized view."""
    query = """
        SELECT * FROM mv_symptom_heatmap 
        WHERE date >= DATE('now', :days_param)
        ORDER BY event_count DESC, geo_cell
    """
    
    results = db.execute(text(query), {"days_param": f"-{days} days"}).fetchall()
    
    return [dict(row._mapping) for row in results]


def query_sla_breach_counts(
    db: Session,
    geo_cell: str | None = None,
    min_escalation_rate: float | None = None,
) -> list[dict]:
    """Query SLA breach counts from materialized view."""
    query = "SELECT * FROM mv_sla_breach_counts WHERE 1=1"
    params = {}
    
    if geo_cell:
        query += " AND geo_cell = :geo_cell"
        params["geo_cell"] = geo_cell
    
    if min_escalation_rate is not None:
        query += " AND escalation_rate >= :min_rate"
        params["min_rate"] = min_escalation_rate
    
    query += " ORDER BY escalation_rate DESC, total_complaints DESC"
    
    results = db.execute(text(query), params).fetchall()
    
    return [dict(row._mapping) for row in results]
