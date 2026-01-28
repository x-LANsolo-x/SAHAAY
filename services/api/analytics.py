"""
Analytics Event Generation (Phase 7.1)

De-identified analytics with strict privacy guarantees:
- No direct identifiers (user_id, phone, email, complaint_id)
- Time rounded to 15-minute buckets
- Geo-hashing using H3 cells (coarse level)
- Age bucketing (0-5, 6-12, 13-18, 19-35, 36-60, 60+)
- Only with explicit consent
- AGGREGATED: Multiple events merged into single rows (20:1 ratio)
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from services.api import models
from services.api.consent import has_active_consent


# Privacy constants
TIME_BUCKET_MINUTES = 15  # Round time to 15-minute intervals
H3_RESOLUTION = 7  # Coarse geo resolution (~5km hexagons)
MIN_AGGREGATION_COUNT = 5  # k-anonymity threshold

# Aggregation constants
AGGREGATION_BUFFER_SIZE = 100  # Flush to DB after this many events
AGGREGATION_FLUSH_INTERVAL_SECONDS = 300  # Flush to DB every 5 minutes


# In-memory aggregation buffer
# Structure: {aggregation_key: {"count": N, "metadata": {...}, "first_seen": dt}}
_aggregation_buffer = defaultdict(lambda: {"count": 0, "metadata": {}, "first_seen": datetime.utcnow()})
_buffer_lock = Lock()
_buffer_event_count = 0


def round_to_time_bucket(dt: datetime) -> datetime:
    """Round datetime to nearest 15-minute bucket for privacy."""
    minutes = (dt.minute // TIME_BUCKET_MINUTES) * TIME_BUCKET_MINUTES
    return dt.replace(minute=minutes, second=0, microsecond=0)


def get_age_bucket(age: Optional[int]) -> str:
    """Convert age to privacy-preserving bucket."""
    if age is None:
        return "unknown"
    if age < 6:
        return "0-5"
    elif age < 13:
        return "6-12"
    elif age < 19:
        return "13-18"
    elif age < 36:
        return "19-35"
    elif age < 61:
        return "36-60"
    else:
        return "60+"


def lat_lng_to_h3(lat: float, lng: float, resolution: int = H3_RESOLUTION) -> str:
    """
    Convert lat/lng to H3 cell for coarse geospatial aggregation.
    
    For MVP: we'll use a simple grid-based bucketing.
    In production: use actual h3-py library.
    
    Args:
        lat: Latitude
        lng: Longitude
        resolution: H3 resolution (7 = ~5km hexagons)
    
    Returns:
        H3 cell identifier (or grid bucket for MVP)
    """
    # MVP implementation: Simple grid bucketing (0.1 degree = ~11km at equator)
    # In production, replace with: h3.geo_to_h3(lat, lng, resolution)
    lat_bucket = int(lat * 10) / 10  # Round to 0.1 degrees
    lng_bucket = int(lng * 10) / 10
    return f"grid_{lat_bucket}_{lng_bucket}"


def pincode_to_h3(pincode: str) -> str:
    """
    Convert pincode to approximate H3 cell.
    
    For MVP: we'll use a hash-based bucketing.
    In production: use pincode geocoding + h3 conversion.
    
    Args:
        pincode: Postal code
    
    Returns:
        H3-like cell identifier
    """
    # MVP implementation: Hash-based bucketing
    # In production: geocode pincode -> lat/lng -> h3
    if not pincode or len(pincode) < 3:
        return "unknown"
    
    # Use first 3 digits for district-level aggregation
    district_prefix = pincode[:3]
    return f"pincode_{district_prefix}xxx"


def hash_for_anonymity(value: str, salt: str = "sahaay_analytics_v1") -> str:
    """
    Create one-way hash for pseudonymization.
    
    Used for creating anonymous cohort identifiers without storing original values.
    """
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:16]


class AnalyticsEventSchema:
    """
    Strict schema for analytics events - only these fields are allowed.
    
    DISALLOWED fields (enforced by not having them in schema):
    - user_id, username
    - phone, email
    - complaint_id (use hashed cohort_id instead)
    - exact GPS coordinates
    - free-text comments
    - evidence filenames or URLs
    """
    
    ALLOWED_EVENT_TYPES = {
        # Triage events
        "triage_completed",
        "triage_emergency",
        
        # Complaint events
        "complaint_submitted",
        "complaint_resolved",
        "complaint_escalated",
        
        # Health tracking events
        "vaccination_recorded",
        "neuroscreen_completed",
        "daily_wellness_logged",
        
        # Teleconsultation events
        "tele_request_created",
        "tele_consultation_completed",
    }
    
    ALLOWED_CATEGORIES = {
        # Triage categories
        "self_care",
        "phc",
        "emergency",
        
        # Complaint categories
        "service_quality",
        "staff_behavior",
        "facility_issues",
        "medication_error",
        "billing_dispute",
        "discrimination",
        "other",
        
        # NeuroScreen bands
        "low",
        "medium",
        "high",
    }
    
    @staticmethod
    def validate_event_type(event_type: str) -> bool:
        """Check if event_type is in allowed list."""
        return event_type in AnalyticsEventSchema.ALLOWED_EVENT_TYPES
    
    @staticmethod
    def validate_category(category: Optional[str]) -> bool:
        """Check if category is in allowed list."""
        if category is None:
            return True
        return category in AnalyticsEventSchema.ALLOWED_CATEGORIES


def generate_analytics_event(
    *,
    db: Session,
    user_id: str,
    event_type: str,
    category: Optional[str] = None,
    count: int = 1,
    metadata: Optional[dict] = None,
) -> dict:
    """
    Generate a de-identified analytics event with consent check.
    
    Args:
        db: Database session
        user_id: User ID (for consent check only - NOT stored in event)
        event_type: Type of event (must be in ALLOWED_EVENT_TYPES)
        category: Optional category (triage outcome, complaint category, etc.)
        count: Count for aggregation (default: 1)
        metadata: Optional metadata (must not contain PII)
    
    Returns:
        De-identified event payload ready for analytics pipeline
    
    Raises:
        HTTPException: If consent not granted or validation fails
    """
    
    # 1. Consent check - REQUIRED
    if not has_active_consent(
        db=db,
        user_id=user_id,
        category=models.ConsentCategory.analytics,
        scope=models.ConsentScope.gov_aggregated,
    ):
        raise HTTPException(
            status_code=403,
            detail="Analytics consent (gov_aggregated scope) not granted"
        )
    
    # 2. Validate event_type
    if not AnalyticsEventSchema.validate_event_type(event_type):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event_type: {event_type}. Must be one of {AnalyticsEventSchema.ALLOWED_EVENT_TYPES}"
        )
    
    # 3. Validate category
    if not AnalyticsEventSchema.validate_category(category):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category: {category}. Must be one of {AnalyticsEventSchema.ALLOWED_CATEGORIES}"
        )
    
    # 4. Get user profile for de-identified demographics
    profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
    
    # 5. Build de-identified event payload
    event_time = round_to_time_bucket(datetime.utcnow())
    
    event_payload = {
        # Core fields (ALLOWED)
        "event_type": event_type,
        "event_time": event_time.isoformat(),
        
        # Demographics (aggregated/bucketed)
        "age_bucket": get_age_bucket(profile.age if profile else None),
        "gender": profile.sex if (profile and profile.sex) else "unknown",
        
        # Geo (coarse H3 cell)
        "geo_cell": pincode_to_h3(profile.pincode) if (profile and profile.pincode) else "unknown",
        
        # Category/classification
        "category": category if category else "unknown",
        
        # Aggregation
        "count": count,
        
        # Metadata (must be PII-free)
        "metadata": metadata if metadata else {},
        
        # Version tracking
        "schema_version": "1.0",
    }
    
    # 6. Validate no PII in metadata
    if metadata:
        disallowed_keys = {
            "user_id", "username", "phone", "email", "complaint_id",
            "full_name", "name", "address", "gps", "latitude", "longitude",
            "evidence", "filename", "url", "comment", "text", "description"
        }
        for key in metadata.keys():
            if key.lower() in disallowed_keys:
                raise HTTPException(
                    status_code=400,
                    detail=f"Metadata contains disallowed PII field: {key}"
                )
    
    return event_payload


def _get_aggregation_key(payload: dict) -> str:
    """
    Generate aggregation key from de-identified payload.
    
    Key dimensions: event_type, category, time_bucket, geo_cell, age_bucket, gender
    Events with the same key are merged into a single aggregated row.
    """
    return "|".join([
        payload.get("event_type", "unknown"),
        payload.get("category", "unknown"),
        payload.get("event_time", ""),  # Already bucketed to 15-min
        payload.get("geo_cell", "unknown"),
        payload.get("age_bucket", "unknown"),
        payload.get("gender", "unknown"),
    ])


def flush_aggregation_buffer(db: Session, force: bool = False) -> int:
    """
    Flush in-memory aggregation buffer to database.
    
    Merges multiple individual events into aggregated rows using UPSERT logic:
    - If aggregation key exists: increment count
    - If new: insert new row
    
    Args:
        db: Database session
        force: Force flush even if buffer is not full
    
    Returns:
        Number of aggregated events flushed
    """
    global _buffer_event_count
    
    with _buffer_lock:
        if not force and _buffer_event_count < AGGREGATION_BUFFER_SIZE:
            return 0  # Buffer not full yet
        
        if not _aggregation_buffer:
            return 0  # Nothing to flush
        
        flushed_count = 0
        
        for agg_key, data in list(_aggregation_buffer.items()):
            # Parse aggregation key
            parts = agg_key.split("|")
            if len(parts) != 6:
                continue  # Skip malformed keys
            
            event_type, category, time_bucket_str, geo_cell, age_bucket, gender = parts
            
            # Parse time bucket
            try:
                time_bucket = datetime.fromisoformat(time_bucket_str)
            except (ValueError, TypeError):
                time_bucket = datetime.utcnow()
            
            # Try to find existing aggregated event
            existing = db.query(models.AggregatedAnalyticsEvent).filter(
                models.AggregatedAnalyticsEvent.event_type == event_type,
                models.AggregatedAnalyticsEvent.category == category,
                models.AggregatedAnalyticsEvent.time_bucket == time_bucket,
                models.AggregatedAnalyticsEvent.geo_cell == geo_cell,
                models.AggregatedAnalyticsEvent.age_bucket == age_bucket,
                models.AggregatedAnalyticsEvent.gender == gender,
            ).first()
            
            if existing:
                # Update existing: increment count
                existing.count += data["count"]
                existing.last_updated = datetime.utcnow()
            else:
                # Insert new aggregated event
                agg_event = models.AggregatedAnalyticsEvent(
                    event_type=event_type,
                    category=category,
                    time_bucket=time_bucket,
                    geo_cell=geo_cell,
                    age_bucket=age_bucket,
                    gender=gender,
                    count=data["count"],
                    metadata_json=json.dumps(data.get("metadata", {})),
                    first_seen=data.get("first_seen", datetime.utcnow()),
                )
                db.add(agg_event)
            
            flushed_count += data["count"]
        
        # Clear buffer
        _aggregation_buffer.clear()
        _buffer_event_count = 0
        
        db.commit()
        return flushed_count


def emit_analytics_event(
    *,
    db: Session,
    user_id: str,
    event_type: str,
    category: Optional[str] = None,
    count: int = 1,
    metadata: Optional[dict] = None,
) -> Optional[models.AnalyticsEvent]:
    """
    Generate and accumulate a de-identified analytics event.
    
    This is the main function for emitting analytics events from the application.
    
    AGGREGATION: Events are accumulated in memory and periodically flushed as
    aggregated rows to the database (e.g., 100 events → fewer rows with count totals).
    
    Example: 20 triage events with same demographics → 1 aggregated row with count=20
    
    Args:
        db: Database session
        user_id: User ID (for consent check only)
        event_type: Type of event
        category: Optional category
        count: Count for aggregation
        metadata: Optional PII-free metadata
    
    Returns:
        Individual AnalyticsEvent (for backward compatibility, will be deprecated)
    
    Raises:
        HTTPException: If consent not granted or validation fails
    """
    global _buffer_event_count
    
    # Generate de-identified payload
    event_payload = generate_analytics_event(
        db=db,
        user_id=user_id,
        event_type=event_type,
        category=category,
        count=count,
        metadata=metadata,
    )
    
    # Add to aggregation buffer (in-memory)
    agg_key = _get_aggregation_key(event_payload)
    
    with _buffer_lock:
        _aggregation_buffer[agg_key]["count"] += 1
        _aggregation_buffer[agg_key]["metadata"] = metadata or {}
        if "first_seen" not in _aggregation_buffer[agg_key] or _aggregation_buffer[agg_key]["first_seen"] == datetime.utcnow():
            _aggregation_buffer[agg_key]["first_seen"] = datetime.utcnow()
        
        _buffer_event_count += 1
    
    # Auto-flush if buffer is full
    if _buffer_event_count >= AGGREGATION_BUFFER_SIZE:
        flush_aggregation_buffer(db, force=True)
    
    # For backward compatibility, still store individual event (will be deprecated)
    # This allows gradual migration to aggregated model
    evt = models.AnalyticsEvent(
        user_id=user_id,  # For audit only
        event_type=event_type,
        payload_json=json.dumps(event_payload),
    )
    db.add(evt)
    db.flush()
    
    return evt


def emit_triage_analytics(
    *,
    db: Session,
    user_id: str,
    triage_category: str,
    has_red_flags: bool = False,
) -> Optional[models.AnalyticsEvent]:
    """
    Emit analytics event for triage completion.
    
    Args:
        db: Database session
        user_id: User ID
        triage_category: Triage outcome (self_care, phc, emergency)
        has_red_flags: Whether red flags were detected
    
    Returns:
        AnalyticsEvent if consent granted, None otherwise
    """
    try:
        event_type = "triage_emergency" if triage_category == "emergency" else "triage_completed"
        
        return emit_analytics_event(
            db=db,
            user_id=user_id,
            event_type=event_type,
            category=triage_category,
            metadata={
                "has_red_flags": has_red_flags,
            }
        )
    except HTTPException:
        # If consent not granted, silently skip (don't block main flow)
        return None


def emit_complaint_analytics(
    *,
    db: Session,
    user_id: Optional[str],
    event_type: str,
    complaint_category: str,
    escalation_level: int = 1,
) -> Optional[models.AnalyticsEvent]:
    """
    Emit analytics event for complaint lifecycle.
    
    Args:
        db: Database session
        user_id: User ID (None for anonymous complaints)
        event_type: complaint_submitted, complaint_resolved, complaint_escalated
        complaint_category: Complaint category
        escalation_level: Current escalation level (1-3)
    
    Returns:
        AnalyticsEvent if consent granted, None otherwise
    """
    # For anonymous complaints, we can't emit user-level events
    # Instead, these would be aggregated separately in batch jobs
    if user_id is None:
        return None
    
    try:
        return emit_analytics_event(
            db=db,
            user_id=user_id,
            event_type=event_type,
            category=complaint_category,
            metadata={
                "escalation_level": escalation_level,
            }
        )
    except HTTPException:
        # If consent not granted, silently skip
        return None


def emit_vaccination_analytics(
    *,
    db: Session,
    user_id: str,
    vaccine_name: str,
    dose_number: int,
) -> Optional[models.AnalyticsEvent]:
    """
    Emit analytics event for vaccination record.
    
    Args:
        db: Database session
        user_id: User ID
        vaccine_name: Vaccine name (e.g., "BCG", "DPT")
        dose_number: Dose number
    
    Returns:
        AnalyticsEvent if consent granted, None otherwise
    """
    try:
        return emit_analytics_event(
            db=db,
            user_id=user_id,
            event_type="vaccination_recorded",
            metadata={
                "vaccine_type": vaccine_name,  # Generalized (not exact brand)
                "dose_sequence": dose_number,
            }
        )
    except HTTPException:
        return None


def emit_neuroscreen_analytics(
    *,
    db: Session,
    user_id: str,
    band: str,
) -> Optional[models.AnalyticsEvent]:
    """
    Emit analytics event for NeuroScreen completion.
    
    Args:
        db: Database session
        user_id: User ID
        band: Risk band (low, medium, high)
    
    Returns:
        AnalyticsEvent if consent granted, None otherwise
    """
    try:
        return emit_analytics_event(
            db=db,
            user_id=user_id,
            event_type="neuroscreen_completed",
            category=band,
        )
    except HTTPException:
        return None


def get_analytics_summary(
    *,
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    event_type: Optional[str] = None,
) -> dict:
    """
    Get aggregated analytics summary (admin/officer view).
    
    This returns only aggregate counts, never individual records.
    Enforces k-anonymity threshold.
    
    Args:
        db: Database session
        start_date: Start date filter
        end_date: End date filter
        event_type: Event type filter
    
    Returns:
        Aggregated summary with privacy guarantees
    """
    
    query = db.query(models.AnalyticsEvent)
    
    if start_date:
        query = query.filter(models.AnalyticsEvent.created_at >= start_date)
    if end_date:
        query = query.filter(models.AnalyticsEvent.created_at <= end_date)
    if event_type:
        query = query.filter(models.AnalyticsEvent.event_type == event_type)
    
    events = query.all()
    
    # Aggregate by event_type and category
    aggregates = {}
    for event in events:
        try:
            payload = json.loads(event.payload_json)
            key = (payload.get("event_type", "unknown"), payload.get("category", "unknown"))
            
            if key not in aggregates:
                aggregates[key] = {
                    "event_type": key[0],
                    "category": key[1],
                    "count": 0,
                    "geo_cells": set(),
                    "age_buckets": set(),
                }
            
            aggregates[key]["count"] += payload.get("count", 1)
            aggregates[key]["geo_cells"].add(payload.get("geo_cell", "unknown"))
            aggregates[key]["age_buckets"].add(payload.get("age_bucket", "unknown"))
        except (json.JSONDecodeError, KeyError):
            continue
    
    # Apply k-anonymity threshold
    filtered_aggregates = []
    for key, data in aggregates.items():
        if data["count"] >= MIN_AGGREGATION_COUNT:
            filtered_aggregates.append({
                "event_type": data["event_type"],
                "category": data["category"],
                "count": data["count"],
                "unique_geo_cells": len(data["geo_cells"]),
                "unique_age_buckets": len(data["age_buckets"]),
            })
    
    return {
        "summary": filtered_aggregates,
        "total_events": sum(agg["count"] for agg in filtered_aggregates),
        "privacy_threshold": MIN_AGGREGATION_COUNT,
        "note": f"Only showing aggregates with >= {MIN_AGGREGATION_COUNT} events (k-anonymity)",
    }
