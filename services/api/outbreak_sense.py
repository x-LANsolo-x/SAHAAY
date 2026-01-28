"""
OutbreakSense — Anomaly Detection for Disease Outbreaks (Phase 7.3)

Baseline anomaly detection over triage counts to identify potential outbreaks.

Algorithm:
1. Calculate rolling 7-day baseline (mean + std deviation) per geo_cell
2. Detect anomalies: count_today > mean + (3 * std_dev)
3. Generate alerts with severity levels

Detection thresholds:
- Low: 2-3 sigma above baseline
- Medium: 3-4 sigma above baseline
- High: 4-5 sigma above baseline
- Critical: > 5 sigma above baseline
"""

import statistics
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from services.api import models


# Configuration
BASELINE_WINDOW_DAYS = 7  # Rolling window for baseline calculation
DETECTION_THRESHOLD_SIGMA = 3.0  # Standard threshold (3-sigma)
MIN_BASELINE_SAMPLES = 5  # Minimum days needed for reliable baseline


def calculate_baseline(
    db: Session,
    geo_cell: str,
    event_type: str,
    end_date: datetime,
    window_days: int = BASELINE_WINDOW_DAYS,
) -> Tuple[float, float, int]:
    """
    Calculate rolling baseline statistics for a geo_cell.
    
    Args:
        db: Database session
        geo_cell: Geographic cell identifier
        event_type: Type of event (e.g., 'triage_completed')
        end_date: End of baseline window
        window_days: Number of days for rolling window
    
    Returns:
        (mean, std_dev, sample_count) tuple
    """
    start_date = end_date - timedelta(days=window_days)
    
    # Query daily aggregated counts from materialized view
    query = db.query(
        func.date(models.AggregatedAnalyticsEvent.time_bucket).label('date'),
        func.sum(models.AggregatedAnalyticsEvent.count).label('daily_count')
    ).filter(
        and_(
            models.AggregatedAnalyticsEvent.geo_cell == geo_cell,
            models.AggregatedAnalyticsEvent.event_type == event_type,
            models.AggregatedAnalyticsEvent.time_bucket >= start_date,
            models.AggregatedAnalyticsEvent.time_bucket < end_date,
        )
    ).group_by(
        func.date(models.AggregatedAnalyticsEvent.time_bucket)
    ).all()
    
    if not query or len(query) < MIN_BASELINE_SAMPLES:
        # Insufficient data for reliable baseline
        return (0.0, 0.0, len(query) if query else 0)
    
    # Extract daily counts
    daily_counts = [float(row.daily_count) for row in query]
    
    # Calculate statistics
    mean = statistics.mean(daily_counts)
    std_dev = statistics.stdev(daily_counts) if len(daily_counts) > 1 else 0.0
    
    return (mean, std_dev, len(daily_counts))


def detect_anomaly(
    observed: int,
    baseline_mean: float,
    baseline_std: float,
    threshold_sigma: float = DETECTION_THRESHOLD_SIGMA,
) -> Tuple[bool, float, str, float]:
    """
    Detect if observed count is anomalous compared to baseline.
    
    Args:
        observed: Observed count today
        baseline_mean: Baseline mean from rolling window
        baseline_std: Baseline standard deviation
        threshold_sigma: Detection threshold (default: 3.0)
    
    Returns:
        (is_anomaly, z_score, alert_level, confidence) tuple
    """
    # Handle edge case: no variation in baseline
    if baseline_std == 0:
        if observed > baseline_mean:
            # Any increase above constant baseline is suspicious
            z_score = float(observed - baseline_mean)
            is_anomaly = z_score > 0
            alert_level = "medium" if z_score > 10 else "low"
            confidence = min(0.9, 0.5 + (z_score / 20))
            return (is_anomaly, z_score, alert_level, confidence)
        else:
            return (False, 0.0, "none", 0.0)
    
    # Calculate z-score
    z_score = (observed - baseline_mean) / baseline_std
    
    # Determine if anomalous
    is_anomaly = z_score > threshold_sigma
    
    # Classify alert level and confidence
    if z_score < threshold_sigma:
        alert_level = "none"
        confidence = 0.0
    elif z_score < 4.0:
        alert_level = "low"
        confidence = 0.6 + (z_score - threshold_sigma) * 0.1
    elif z_score < 5.0:
        alert_level = "medium"
        confidence = 0.7 + (z_score - 4.0) * 0.1
    elif z_score < 6.0:
        alert_level = "high"
        confidence = 0.8 + (z_score - 5.0) * 0.1
    else:
        alert_level = "critical"
        confidence = min(0.99, 0.9 + (z_score - 6.0) * 0.01)
    
    return (is_anomaly, z_score, alert_level, confidence)


def run_outbreak_detection(
    db: Session,
    target_date: Optional[datetime] = None,
    geo_cells: Optional[List[str]] = None,
    event_types: Optional[List[str]] = None,
) -> List[models.OutbreakAlert]:
    """
    Run outbreak detection for specified date and geo_cells.
    
    Args:
        db: Database session
        target_date: Date to check (default: today)
        geo_cells: List of geo_cells to check (default: all)
        event_types: List of event types to check (default: triage only)
    
    Returns:
        List of OutbreakAlert objects (only anomalies)
    """
    if target_date is None:
        target_date = datetime.utcnow().date()
    
    if event_types is None:
        event_types = ['triage_completed', 'triage_emergency']
    
    # Get unique geo_cells if not specified
    if geo_cells is None:
        geo_cells_query = db.query(
            models.AggregatedAnalyticsEvent.geo_cell
        ).filter(
            models.AggregatedAnalyticsEvent.event_type.in_(event_types)
        ).distinct().all()
        
        geo_cells = [row.geo_cell for row in geo_cells_query]
    
    alerts = []
    
    # Check each geo_cell
    for geo_cell in geo_cells:
        for event_type in event_types:
            # Calculate baseline
            baseline_mean, baseline_std, sample_count = calculate_baseline(
                db=db,
                geo_cell=geo_cell,
                event_type=event_type,
                end_date=datetime.combine(target_date, datetime.min.time()),
                window_days=BASELINE_WINDOW_DAYS,
            )
            
            # Skip if insufficient baseline data
            if sample_count < MIN_BASELINE_SAMPLES:
                continue
            
            # Get observed count for target date
            start_of_day = datetime.combine(target_date, datetime.min.time())
            end_of_day = start_of_day + timedelta(days=1)
            
            observed_query = db.query(
                func.sum(models.AggregatedAnalyticsEvent.count)
            ).filter(
                and_(
                    models.AggregatedAnalyticsEvent.geo_cell == geo_cell,
                    models.AggregatedAnalyticsEvent.event_type == event_type,
                    models.AggregatedAnalyticsEvent.time_bucket >= start_of_day,
                    models.AggregatedAnalyticsEvent.time_bucket < end_of_day,
                )
            ).scalar()
            
            observed_count = int(observed_query) if observed_query else 0
            
            # Skip if no activity today
            if observed_count == 0:
                continue
            
            # Detect anomaly
            is_anomaly, z_score, alert_level, confidence = detect_anomaly(
                observed=observed_count,
                baseline_mean=baseline_mean,
                baseline_std=baseline_std,
                threshold_sigma=DETECTION_THRESHOLD_SIGMA,
            )
            
            # Create alert if anomalous
            if is_anomaly:
                alert = models.OutbreakAlert(
                    geo_cell=geo_cell,
                    event_time=start_of_day,
                    event_type=event_type,
                    baseline_mean=baseline_mean,
                    baseline_std=baseline_std,
                    observed_count=observed_count,
                    z_score=z_score,
                    threshold_sigma=DETECTION_THRESHOLD_SIGMA,
                    alert_level=alert_level,
                    confidence=confidence,
                    status="active",
                )
                alerts.append(alert)
    
    return alerts


def persist_alerts(db: Session, alerts: List[models.OutbreakAlert]) -> int:
    """
    Persist outbreak alerts to database.
    
    Args:
        db: Database session
        alerts: List of OutbreakAlert objects
    
    Returns:
        Number of alerts persisted
    """
    if not alerts:
        return 0
    
    for alert in alerts:
        db.add(alert)
    
    db.commit()
    
    return len(alerts)


def get_active_alerts(
    db: Session,
    geo_cell: Optional[str] = None,
    min_alert_level: Optional[str] = None,
    days: int = 7,
) -> List[models.OutbreakAlert]:
    """
    Get active outbreak alerts.
    
    Args:
        db: Database session
        geo_cell: Filter by geo_cell (optional)
        min_alert_level: Minimum alert level (low, medium, high, critical)
        days: Number of days to look back
    
    Returns:
        List of active OutbreakAlert objects
    """
    query = db.query(models.OutbreakAlert).filter(
        models.OutbreakAlert.status == "active"
    )
    
    # Time filter
    start_date = datetime.utcnow() - timedelta(days=days)
    query = query.filter(models.OutbreakAlert.event_time >= start_date)
    
    # Geo filter
    if geo_cell:
        query = query.filter(models.OutbreakAlert.geo_cell == geo_cell)
    
    # Alert level filter
    if min_alert_level:
        level_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        min_level_value = level_order.get(min_alert_level, 1)
        
        query = query.filter(
            models.OutbreakAlert.alert_level.in_([
                level for level, value in level_order.items()
                if value >= min_level_value
            ])
        )
    
    # Order by severity and time
    query = query.order_by(
        models.OutbreakAlert.alert_level.desc(),
        models.OutbreakAlert.z_score.desc(),
        models.OutbreakAlert.event_time.desc()
    )
    
    return query.all()


def acknowledge_alert(
    db: Session,
    alert_id: str,
    acknowledged_by: str,
    notes: Optional[str] = None,
) -> models.OutbreakAlert:
    """
    Acknowledge an outbreak alert.
    
    Args:
        db: Database session
        alert_id: Alert ID
        acknowledged_by: User who acknowledged (username/ID)
        notes: Optional notes
    
    Returns:
        Updated OutbreakAlert object
    """
    alert = db.query(models.OutbreakAlert).filter(
        models.OutbreakAlert.id == alert_id
    ).first()
    
    if not alert:
        raise ValueError(f"Alert {alert_id} not found")
    
    alert.acknowledged_by = acknowledged_by
    alert.acknowledged_at = datetime.utcnow()
    
    if notes:
        alert.resolution_notes = notes
    
    db.commit()
    db.refresh(alert)
    
    return alert


def resolve_alert(
    db: Session,
    alert_id: str,
    resolution: str = "resolved",
    notes: Optional[str] = None,
) -> models.OutbreakAlert:
    """
    Resolve an outbreak alert.
    
    Args:
        db: Database session
        alert_id: Alert ID
        resolution: Resolution status ('resolved' or 'false_positive')
        notes: Resolution notes
    
    Returns:
        Updated OutbreakAlert object
    """
    alert = db.query(models.OutbreakAlert).filter(
        models.OutbreakAlert.id == alert_id
    ).first()
    
    if not alert:
        raise ValueError(f"Alert {alert_id} not found")
    
    alert.status = resolution
    
    if notes:
        alert.resolution_notes = notes
    
    db.commit()
    db.refresh(alert)
    
    return alert


def get_outbreak_summary(
    db: Session,
    days: int = 30,
) -> Dict:
    """
    Get summary statistics for outbreak detection system.
    
    Args:
        db: Database session
        days: Number of days to analyze
    
    Returns:
        Summary dict with counts and metrics
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Total alerts
    total_alerts = db.query(models.OutbreakAlert).filter(
        models.OutbreakAlert.created_at >= start_date
    ).count()
    
    # Active alerts
    active_alerts = db.query(models.OutbreakAlert).filter(
        and_(
            models.OutbreakAlert.status == "active",
            models.OutbreakAlert.created_at >= start_date,
        )
    ).count()
    
    # By alert level
    by_level = {}
    for level in ['low', 'medium', 'high', 'critical']:
        count = db.query(models.OutbreakAlert).filter(
            and_(
                models.OutbreakAlert.alert_level == level,
                models.OutbreakAlert.created_at >= start_date,
            )
        ).count()
        by_level[level] = count
    
    # By status
    by_status = {}
    for status in ['active', 'resolved', 'false_positive']:
        count = db.query(models.OutbreakAlert).filter(
            and_(
                models.OutbreakAlert.status == status,
                models.OutbreakAlert.created_at >= start_date,
            )
        ).count()
        by_status[status] = count
    
    # Top geo_cells with alerts
    top_geos = db.query(
        models.OutbreakAlert.geo_cell,
        func.count(models.OutbreakAlert.id).label('alert_count')
    ).filter(
        models.OutbreakAlert.created_at >= start_date
    ).group_by(
        models.OutbreakAlert.geo_cell
    ).order_by(
        func.count(models.OutbreakAlert.id).desc()
    ).limit(10).all()
    
    # False positive rate (if we have resolved alerts)
    total_resolved = by_status.get('resolved', 0) + by_status.get('false_positive', 0)
    false_positive_rate = (by_status.get('false_positive', 0) / total_resolved * 100) if total_resolved > 0 else 0.0
    
    return {
        "total_alerts": total_alerts,
        "active_alerts": active_alerts,
        "by_level": by_level,
        "by_status": by_status,
        "top_geo_cells": [{"geo_cell": row.geo_cell, "count": row.alert_count} for row in top_geos],
        "false_positive_rate": round(false_positive_rate, 2),
        "time_period": {
            "start": start_date.isoformat(),
            "end": datetime.utcnow().isoformat(),
            "days": days,
        },
    }
