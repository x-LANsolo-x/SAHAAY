from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy.orm import Session

from fastapi.middleware.gzip import GZipMiddleware

from services.api import models
from services.api.auth import create_access_token, hash_password, verify_password, get_current_user
from services.api.audit import verify_audit_chain, write_audit
from services.api.consent import has_active_consent, upsert_consent
from services.api.sync import process_event
from services.api.telesahay import enqueue_message, render_sms_summary, validate_status_transition
from services.api.triage import generate_triage
from services.api.db import engine, get_db
from services.api.analytics import (
    emit_analytics_event,
    emit_triage_analytics,
    emit_complaint_analytics,
    emit_vaccination_analytics,
    emit_neuroscreen_analytics,
    get_analytics_summary,
)
from services.api.dashboard_queries import (
    get_time_series_data,
    get_geo_heatmap_data,
    get_category_breakdown,
    get_demographics_breakdown,
    get_top_geo_cells,
    get_dashboard_summary,
)
from services.api.materialized_views import (
    create_all_materialized_views,
    refresh_all_materialized_views,
    get_view_stats,
    query_daily_triage_counts,
    query_complaint_categories,
    query_symptom_heatmap,
    query_sla_breach_counts,
)
from services.api.outbreak_sense import (
    run_outbreak_detection,
    persist_alerts,
    get_active_alerts,
    acknowledge_alert,
    resolve_alert,
    get_outbreak_summary,
)
from services.api.schemas import (
    AnalyticsEventResponse,
    AnalyticsEventGenerate,
    AnalyticsEventDetailResponse,
    AnalyticsSummaryResponse,
    DeidentifiedEventResponse,
    TimeSeriesResponse,
    TimeSeriesDataPoint,
    GeoHeatmapResponse,
    GeoHeatmapPoint,
    CategoryBreakdownResponse,
    DemographicsBreakdownResponse,
    TopGeoCellsResponse,
    DashboardSummaryResponse,
    OutbreakAlertResponse,
    OutbreakAlertsListResponse,
    OutbreakSummaryResponse,
    AcknowledgeAlertRequest,
    ResolveAlertRequest,
    AuditLogResponse,
    AuditVerifyResponse,
    ConsentResponse,
    ConsentUpsertRequest,
    ExportResponse,
    FamilyInviteCreateRequest,
    FamilyInviteResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    RegisterRequest,
    SyncBatchRequest,
    SyncBatchResponse,
    SyncEventResult,
    TokenResponse,
    TriageSessionCreate,
    TriageSessionResponse,
    TeleRequestCreate,
    TeleRequestResponse,
    TeleRequestUpdateStatus,
    PrescriptionCreate,
    PrescriptionResponse,
    VitalsCreate,
    FoodLogCreate,
    SleepLogCreate,
    WaterLogCreate,
    MoodLogCreate,
    MedicationPlanCreate,
    AdherenceEventCreate,
    DailySummaryResponse,
    VaccinationRecordCreate,
    GrowthRecordCreate,
    NextDueVaccineResponse,
    MilestoneResponse,
    NeuroscreenResultCreate,
    NeuroscreenResultResponse,
    TherapyPackCreate,
    TherapyPackResponse,
    TherapyModuleCreate,
    TherapyModuleResponse,
    TherapyStepResponse,
    AACSymbolCreate,
    AACSymbolResponse,
    AACSymbolSetCreate,
    AACSymbolSetResponse,
    AACSymbolSetDetailResponse,
    AACPhraseboardCreate,
    AACPhraseboardResponse,
    ComplaintCreate,
    ComplaintResponse,
    ComplaintEvidenceResponse,
    ComplaintUpdateStatus,
    EvidenceUploadInitiate,
    EvidenceUploadInitiateResponse,
    EvidenceUploadComplete,
    SLARuleCreate,
    SLARuleResponse,
    ComplaintStatusHistoryResponse,
    ComplaintFeedback,
    ComplaintCloseRequest,
    BlockchainAnchorResponse,
)

# Create tables (dev-only). In production use Alembic migrations.
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="SAHAAY API")

# Report versioning constant
# Versioning contract:
# - 1.0 -> 1.1: Minor changes (add fields, backward compatible)
# - 1.0 -> 2.0: Major changes (remove/rename fields, breaking changes)
# All report builders MUST include report_version in their response.
REPORT_VERSION = "1.0"

# Add gzip compression middleware for large payloads
app.add_middleware(GZipMiddleware, minimum_size=1000)


def _require_consent(db: Session, user_id: str, *, category: models.ConsentCategory, scope: models.ConsentScope):
    if not has_active_consent(db=db, user_id=user_id, category=category, scope=scope):
        raise HTTPException(status_code=403, detail="Consent not granted")


@app.get("/health", tags=["Monitoring"])
def get_health():
    return {"status": "ok"}


@app.get("/version", tags=["Monitoring"])
def get_version():
    return {"service": "sahaay-api", "version": "0.0.1", "time": datetime.utcnow().isoformat()}


@app.post("/auth/register", response_model=TokenResponse, tags=["Auth"])
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    user = models.User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()

    # Default role
    role = db.get(models.Role, models.RoleName.citizen)
    if not role:
        db.add(models.Role(name=models.RoleName.citizen))
        db.flush()

    db.add(models.UserRole(user_id=user.id, role_name=models.RoleName.citizen))

    # Create empty profile
    profile = models.Profile(user_id=user.id)
    db.add(profile)

    token = create_access_token(user_id=user.id, db=db)

    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="auth.register",
        entity_type="user",
        entity_id=user.id,
    )

    db.commit()

    return TokenResponse(access_token=token)


@app.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
def login(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user_id=user.id, db=db)

    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
    )

    db.commit()
    return TokenResponse(access_token=token)


@app.get("/profiles/me", response_model=ProfileResponse, tags=["Profiles"])
def get_my_profile(user: models.User = Depends(get_current_user)):
    p = user.profile
    return ProfileResponse(
        id=p.id,
        user_id=p.user_id,
        full_name=p.full_name,
        age=p.age,
        sex=p.sex,
        pincode=p.pincode,
    )


@app.patch("/profiles/me", response_model=ProfileResponse, tags=["Profiles"])
def update_my_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    profile = db.query(models.Profile).filter(models.Profile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(profile, k, v)

    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="profiles.update",
        entity_type="profile",
        entity_id=profile.id,
    )

    db.commit()
    db.refresh(profile)
    return ProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        full_name=profile.full_name,
        age=profile.age,
        sex=profile.sex,
        pincode=profile.pincode,
    )


@app.get("/profiles/{profile_id}", response_model=ProfileResponse, tags=["Profiles"])
def get_profile(profile_id: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Step 1.1 gate: users cannot read other user's profile (unless you later implement caregiver sharing/consent)
    my_profile = db.query(models.Profile).filter(models.Profile.user_id == user.id).first()
    if not my_profile or my_profile.id != profile_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return ProfileResponse(
        id=my_profile.id,
        user_id=my_profile.user_id,
        full_name=my_profile.full_name,
        age=my_profile.age,
        sex=my_profile.sex,
        pincode=my_profile.pincode,
    )


def _get_or_create_family_group(db: Session, creator_user_id: str) -> models.FamilyGroup:
    fg = db.query(models.FamilyGroup).filter(models.FamilyGroup.created_by_user_id == creator_user_id).first()
    if fg:
        return fg
    fg = models.FamilyGroup(created_by_user_id=creator_user_id)
    db.add(fg)
    db.flush()
    # Add creator as member
    db.add(models.FamilyMember(family_group_id=fg.id, user_id=creator_user_id))
    return fg


@app.post("/family/invites", response_model=FamilyInviteResponse, tags=["Family"])
def create_family_invite(
    payload: FamilyInviteCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    invitee = db.query(models.User).filter(models.User.username == payload.invitee_username).first()
    if not invitee:
        raise HTTPException(status_code=404, detail="Invitee not found")
    if invitee.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot invite yourself")

    family_group = _get_or_create_family_group(db, user.id)

    # Ensure invitee is not already a member
    existing_member = (
        db.query(models.FamilyMember)
        .filter(models.FamilyMember.family_group_id == family_group.id, models.FamilyMember.user_id == invitee.id)
        .first()
    )
    if existing_member:
        raise HTTPException(status_code=409, detail="Already a member")

    inv = models.FamilyInvite(
        family_group_id=family_group.id,
        inviter_user_id=user.id,
        invitee_user_id=invitee.id,
    )
    db.add(inv)

    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="family.invite.create",
        entity_type="family_invite",
        entity_id=inv.id,
    )

    db.commit()
    db.refresh(inv)

    return FamilyInviteResponse(
        id=inv.id,
        family_group_id=inv.family_group_id,
        inviter_user_id=inv.inviter_user_id,
        invitee_user_id=inv.invitee_user_id,
        status=inv.status.value,
    )


@app.post("/consents", response_model=ConsentResponse, tags=["Consent"])
def set_consent(
    payload: ConsentUpsertRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    c = upsert_consent(db=db, user_id=user.id, category=payload.category, scope=payload.scope, granted=payload.granted)

    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="consent.set",
        entity_type="consent",
        entity_id=c.id,
    )

    db.commit()
    db.refresh(c)
    return ConsentResponse(
        id=c.id,
        user_id=c.user_id,
        category=c.category.value,
        scope=c.scope.value,
        version=c.version,
        granted=c.granted,
    )


@app.get("/consents", response_model=list[ConsentResponse], tags=["Consent"])
def list_consents(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    # Return latest consent per (category, scope)
    rows = (
        db.query(models.Consent)
        .filter(models.Consent.user_id == user.id)
        .order_by(models.Consent.category.asc(), models.Consent.scope.asc(), models.Consent.version.desc())
        .all()
    )
    latest = {}
    for r in rows:
        key = (r.category, r.scope)
        if key not in latest:
            latest[key] = r
    return [
        ConsentResponse(
            id=r.id,
            user_id=r.user_id,
            category=r.category.value,
            scope=r.scope.value,
            version=r.version,
            granted=r.granted,
        )
        for r in latest.values()
    ]


@app.get("/export/profile", response_model=ExportResponse, tags=["Export"])
def export_profile(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    # Gate export behind explicit consent.
    _require_consent(
        db,
        user.id,
        category=models.ConsentCategory.tracking,
        scope=models.ConsentScope.cloud_sync,
    )

    profile = db.query(models.Profile).filter(models.Profile.user_id == user.id).first()

    # Export is read-only but still audited for traceability.
    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="export.profile",
        entity_type="profile",
        entity_id=profile.id if profile else None,
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    # NOTE: Bump REPORT_VERSION on schema changes (1.1, 2.0, etc.)
    # This ensures clients can handle different report formats gracefully.
    return ExportResponse(
        report_version=REPORT_VERSION,
        profile=ProfileResponse(
            id=profile.id,
            user_id=profile.user_id,
            full_name=profile.full_name,
            age=profile.age,
            sex=profile.sex,
            pincode=profile.pincode,
        )
    )


@app.post("/analytics/events", response_model=AnalyticsEventDetailResponse, tags=["Analytics"])
def generate_analytics_event_api(
    payload: AnalyticsEventGenerate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Generate a de-identified analytics event (Phase 7.1).
    
    Requires explicit consent (analytics + gov_aggregated).
    Only allowed event types and categories accepted.
    All PII is stripped/aggregated before storage.
    """
    
    evt = emit_analytics_event(
        db=db,
        user_id=user.id,
        event_type=payload.event_type,
        category=payload.category,
        metadata=payload.metadata,
    )
    
    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="analytics.event.generate",
        entity_type="analytics_event",
        entity_id=evt.id,
    )
    
    db.commit()
    db.refresh(evt)
    
    # Parse and return de-identified payload
    import json
    payload_dict = json.loads(evt.payload_json)
    
    return AnalyticsEventDetailResponse(
        id=evt.id,
        event_type=evt.event_type,
        payload=DeidentifiedEventResponse(**payload_dict),
        created_at=evt.created_at.isoformat(),
    )


@app.get("/analytics/summary", response_model=AnalyticsSummaryResponse, tags=["Analytics"])
def get_analytics_summary_api(
    start_date: str | None = None,
    end_date: str | None = None,
    event_type: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get aggregated analytics summary with k-anonymity guarantees (Phase 7.1).
    
    Only returns aggregates with >= 5 events (k-anonymity threshold).
    No individual-level data exposed.
    
    For MVP: accessible to all authenticated users.
    In production: restrict to district_officer, state_officer, national_admin roles.
    """
    from datetime import datetime
    
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    
    summary = get_analytics_summary(
        db=db,
        start_date=start_dt,
        end_date=end_dt,
        event_type=event_type,
    )
    
    return AnalyticsSummaryResponse(**summary)


@app.post("/analytics/ping", response_model=AnalyticsEventResponse, tags=["Analytics"])
def analytics_ping(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Legacy ping endpoint for backward compatibility."""
    _require_consent(
        db,
        user.id,
        category=models.ConsentCategory.analytics,
        scope=models.ConsentScope.gov_aggregated,
    )

    evt = models.AnalyticsEvent(user_id=user.id, event_type="ping", payload_json="{}")
    db.add(evt)

    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="analytics.generate",
        entity_type="analytics_event",
        entity_id=evt.id,
    )

    db.commit()
    db.refresh(evt)
    return AnalyticsEventResponse(id=evt.id, event_type=evt.event_type)


# ============================================================
# Dashboard Endpoints (Phase 7.2)
# ============================================================

@app.get("/dashboard/summary", response_model=DashboardSummaryResponse, tags=["Dashboard"])
def get_dashboard_summary_api(
    days: int = 30,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get high-level dashboard summary (Phase 7.2).
    
    Returns overview statistics for the specified time period.
    
    For MVP: accessible to all authenticated users.
    In production: restrict to district_officer, state_officer, national_admin roles.
    """
    summary = get_dashboard_summary(db=db, days=days)
    return DashboardSummaryResponse(**summary)


@app.get("/dashboard/timeseries", response_model=TimeSeriesResponse, tags=["Dashboard"])
def get_timeseries_api(
    event_type: str | None = None,
    category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    interval: str = "1 hour",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get time-series data for trend charts (Phase 7.2).
    
    Useful for:
    - Line charts showing events over time
    - Trend analysis
    - Forecasting visualization
    
    Interval options: "15 minutes", "1 hour", "1 day"
    """
    from datetime import datetime, timedelta
    
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    
    data = get_time_series_data(
        db=db,
        event_type=event_type,
        category=category,
        start_date=start_dt,
        end_date=end_dt,
        interval=interval,
    )
    
    return TimeSeriesResponse(
        data=[TimeSeriesDataPoint(**point) for point in data],
        time_period={
            "start": start_dt.isoformat() if start_dt else (datetime.utcnow() - timedelta(days=7)).isoformat(),
            "end": end_dt.isoformat() if end_dt else datetime.utcnow().isoformat(),
        },
        interval=interval,
    )


@app.get("/dashboard/heatmap", response_model=GeoHeatmapResponse, tags=["Dashboard"])
def get_heatmap_api(
    event_type: str | None = None,
    category: str | None = None,
    days: int = 30,
    min_count: int = 5,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get geo-spatial heatmap data for MapLibre visualization (Phase 7.2).
    
    Returns aggregated event counts by geographic cell.
    Only returns cells with count >= min_count (k-anonymity).
    
    Use with MapLibre GL JS for interactive maps.
    """
    data = get_geo_heatmap_data(
        db=db,
        event_type=event_type,
        category=category,
        min_count=min_count,
        days=days,
    )
    
    return GeoHeatmapResponse(
        data=[GeoHeatmapPoint(**point) for point in data],
        min_count_threshold=min_count,
        days=days,
    )


@app.get("/dashboard/categories", response_model=CategoryBreakdownResponse, tags=["Dashboard"])
def get_categories_api(
    event_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_count: int = 5,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get category breakdown for pie/bar charts (Phase 7.2).
    
    Returns percentage distribution of events by category.
    Useful for:
    - Pie charts
    - Stacked bar charts
    - Category comparison
    """
    from datetime import datetime
    
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    
    data = get_category_breakdown(
        db=db,
        event_type=event_type,
        start_date=start_dt,
        end_date=end_dt,
        min_count=min_count,
    )
    
    total = sum(item["count"] for item in data)
    
    return CategoryBreakdownResponse(
        data=data,
        total=total,
    )


@app.get("/dashboard/demographics", response_model=DemographicsBreakdownResponse, tags=["Dashboard"])
def get_demographics_api(
    event_type: str | None = None,
    category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_count: int = 5,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get demographics breakdown (age, gender) for charts (Phase 7.2).
    
    Returns percentage distributions for:
    - Age buckets (0-5, 6-12, 13-18, 19-35, 36-60, 60+)
    - Gender (M, F, Other, Unknown)
    
    Useful for understanding user demographics.
    """
    from datetime import datetime
    
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    
    data = get_demographics_breakdown(
        db=db,
        event_type=event_type,
        category=category,
        start_date=start_dt,
        end_date=end_dt,
        min_count=min_count,
    )
    
    return DemographicsBreakdownResponse(**data)


@app.get("/dashboard/top-regions", response_model=TopGeoCellsResponse, tags=["Dashboard"])
def get_top_regions_api(
    event_type: str | None = None,
    category: str | None = None,
    limit: int = 10,
    days: int = 30,
    min_count: int = 5,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get top geographic regions by event count (Phase 7.2).
    
    Returns ranked list of regions with highest event counts.
    Useful for:
    - Ranking tables
    - Priority allocation
    - Resource distribution
    """
    data = get_top_geo_cells(
        db=db,
        event_type=event_type,
        category=category,
        limit=limit,
        days=days,
        min_count=min_count,
    )
    
    return TopGeoCellsResponse(
        data=data,
        limit=limit,
        days=days,
    )


@app.post("/dashboard/materialized-views/create", tags=["Dashboard"])
def create_materialized_views_api(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Create all materialized views (Phase 7.2).
    
    Creates:
    - mv_daily_triage_counts
    - mv_complaint_categories_district
    - mv_symptom_heatmap
    - mv_sla_breach_counts
    
    Call once during deployment or when schema changes.
    In production: restrict to admin roles only.
    """
    from datetime import datetime
    
    results = create_all_materialized_views(db=db)
    
    return {
        "status": "success",
        "message": "Materialized views created",
        "results": results,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/dashboard/materialized-views/refresh", tags=["Dashboard"])
def refresh_materialized_views_api(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Refresh all materialized views with latest data (Phase 7.2).
    
    Should be called every 10-15 minutes via cron job.
    
    Refresh policy:
    - Development/MVP: Manual trigger via API
    - Production: Automated cron job (*/10 * * * *)
    
    In production: restrict to admin/system roles only.
    """
    from datetime import datetime
    
    results = refresh_all_materialized_views(db=db)
    
    return {
        "status": "success",
        "message": "Materialized views refreshed",
        "results": results,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/dashboard/materialized-views/stats", tags=["Dashboard"])
def get_materialized_view_stats(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get statistics about materialized views (Phase 7.2).
    
    Returns row counts and freshness info for each view.
    Useful for monitoring and debugging.
    """
    stats = get_view_stats(db=db)
    
    return {
        "status": "success",
        "views": stats,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/dashboard/mv/triage-counts", tags=["Dashboard"])
def get_daily_triage_from_mv(
    start_date: str | None = None,
    end_date: str | None = None,
    geo_cell: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get daily triage counts from materialized view (Phase 7.2).
    
    Much faster than querying raw aggregated events.
    Pre-computed daily aggregations with k-anonymity enforcement.
    """
    data = query_daily_triage_counts(
        db=db,
        start_date=start_date,
        end_date=end_date,
        geo_cell=geo_cell,
    )
    
    return {
        "data": data,
        "count": len(data),
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "geo_cell": geo_cell,
        },
    }


@app.get("/dashboard/mv/complaint-categories", tags=["Dashboard"])
def get_complaint_categories_from_mv(
    geo_cell: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get complaint categories by district from materialized view (Phase 7.2).
    
    Pre-computed complaint aggregations by geography and category.
    """
    data = query_complaint_categories(
        db=db,
        geo_cell=geo_cell,
        category=category,
    )
    
    return {
        "data": data,
        "count": len(data),
        "filters": {
            "geo_cell": geo_cell,
            "category": category,
        },
    }


@app.get("/dashboard/mv/symptom-heatmap", tags=["Dashboard"])
def get_symptom_heatmap_from_mv(
    days: int = 30,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get symptom heatmap clusters from materialized view (Phase 7.2).
    
    Pre-computed symptom clustering by geography.
    Ready for MapLibre visualization.
    """
    data = query_symptom_heatmap(
        db=db,
        days=days,
    )
    
    return {
        "data": data,
        "count": len(data),
        "days": days,
    }


@app.get("/dashboard/mv/sla-breaches", tags=["Dashboard"])
def get_sla_breaches_from_mv(
    geo_cell: str | None = None,
    min_escalation_rate: float | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get SLA breach counts from materialized view (Phase 7.2).
    
    Pre-computed SLA metrics including escalation rates.
    Useful for accountability dashboards.
    """
    data = query_sla_breach_counts(
        db=db,
        geo_cell=geo_cell,
        min_escalation_rate=min_escalation_rate,
    )
    
    return {
        "data": data,
        "count": len(data),
        "filters": {
            "geo_cell": geo_cell,
            "min_escalation_rate": min_escalation_rate,
        },
    }


@app.get("/audit/logs", response_model=list[AuditLogResponse], tags=["Audit"])
def list_audit_logs(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    # For now, return only the requesting user's audit entries.
    rows = db.query(models.AuditLog).filter(models.AuditLog.actor_user_id == user.id).order_by(models.AuditLog.ts.asc()).all()
    return [
        AuditLogResponse(
            id=r.id,
            actor_user_id=r.actor_user_id,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            ip=r.ip,
            device_id=r.device_id,
            ts=r.ts.isoformat(),
            prev_hash=r.prev_hash,
            entry_hash=r.entry_hash,
        )
        for r in rows
    ]


@app.get("/audit/verify", response_model=AuditVerifyResponse, tags=["Audit"])
def verify_audit(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    # For MVP we verify the whole chain.
    return AuditVerifyResponse(ok=verify_audit_chain(db))


@app.post("/sync/events:batch", response_model=SyncBatchResponse, tags=["Sync"])
def sync_events_batch(payload: SyncBatchRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    results: list[SyncEventResult] = []

    # Apply deterministic ordering for profile events (LWW by client_time):
    # process non-profile in arrival order; process profile events in client_time order.
    profile_events = [e for e in payload.events if e.entity_type == "profile"]
    other_events = [e for e in payload.events if e.entity_type != "profile"]
    profile_events.sort(key=lambda e: e.client_time)
    ordered_events = other_events + profile_events

    for ev in ordered_events:
        # Enforce that user can only sync for themselves
        if ev.user_id != user.id:
            results.append(SyncEventResult(event_id=ev.event_id, status="rejected", error="user_id mismatch"))
            continue

        # Idempotency: if event exists, mark duplicate
        existing = db.get(models.SyncEvent, ev.event_id)
        if existing:
            results.append(SyncEventResult(event_id=ev.event_id, status="duplicate"))
            continue

        try:
            process_event(db, ev)
            # audit each accepted sync event
            write_audit(
                db=db,
                request=request,
                actor_user_id=user.id,
                action="sync.event.accepted",
                entity_type=ev.entity_type,
                entity_id=ev.event_id,
            )
            results.append(SyncEventResult(event_id=ev.event_id, status="accepted"))
            db.commit()
        except HTTPException as e:
            db.rollback()
            results.append(SyncEventResult(event_id=ev.event_id, status="rejected", error=str(e.detail)))
        except Exception as e:
            db.rollback()
            results.append(SyncEventResult(event_id=ev.event_id, status="rejected", error="internal error"))

    return SyncBatchResponse(results=results)


@app.post("/triage/sessions", response_model=TriageSessionResponse, tags=["Triage"])
def create_triage_session(
    payload: TriageSessionCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    category, red_flags, guidance = generate_triage(
        symptom_text=payload.symptom_text,
        followup_answers=payload.followup_answers,
    )

    import json
    session = models.TriageSession(
        user_id=user.id,
        symptom_text=payload.symptom_text,
        followup_answers_json=json.dumps(payload.followup_answers),
        triage_category=category,
        red_flags_json=json.dumps(red_flags),
        guidance_text=guidance,
    )
    db.add(session)

    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="triage.create",
        entity_type="triage_session",
        entity_id=session.id,
    )

    # Emit analytics event with consent gate (Phase 7.1)
    # Only emits if user has granted analytics consent
    emit_triage_analytics(
        db=db,
        user_id=user.id,
        triage_category=session.triage_category.value,
        has_red_flags=len(red_flags) > 0,
    )

    db.commit()
    db.refresh(session)

    return TriageSessionResponse(
        id=session.id,
        user_id=session.user_id,
        symptom_text=session.symptom_text,
        followup_answers=payload.followup_answers,
        triage_category=session.triage_category.value,
        red_flags=red_flags,
        guidance_text=session.guidance_text,
        created_at=session.created_at.isoformat(),
    )


@app.get("/triage/sessions/{session_id}", response_model=TriageSessionResponse, tags=["Triage"])
def get_triage_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    session = db.get(models.TriageSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Triage session not found")

    # Auth: only owner can read
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    import json
    return TriageSessionResponse(
        id=session.id,
        user_id=session.user_id,
        symptom_text=session.symptom_text,
        followup_answers=json.loads(session.followup_answers_json),
        triage_category=session.triage_category.value,
        red_flags=json.loads(session.red_flags_json),
        guidance_text=session.guidance_text,
        created_at=session.created_at.isoformat(),
    )


@app.post("/tele/requests", response_model=TeleRequestResponse, tags=["TeleSahay"])
def create_tele_request(
    payload: TeleRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    req = models.TeleRequest(
        user_id=user.id,
        symptom_summary=payload.symptom_summary,
        preferred_time=payload.preferred_time,
    )
    db.add(req)

    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="tele.request.create",
        entity_type="tele_request",
        entity_id=req.id,
    )

    db.commit()
    db.refresh(req)

    return TeleRequestResponse(
        id=req.id,
        user_id=req.user_id,
        symptom_summary=req.symptom_summary,
        preferred_time=req.preferred_time,
        status=req.status.value,
        created_at=req.created_at.isoformat(),
    )


@app.patch("/tele/requests/{request_id}", response_model=TeleRequestResponse, tags=["TeleSahay"])
def update_tele_request_status(
    request_id: str,
    payload: TeleRequestUpdateStatus,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from services.api.auth import require_role

    # Only clinician can transition beyond requested
    req_obj = db.get(models.TeleRequest, request_id)
    if not req_obj:
        raise HTTPException(status_code=404, detail="Tele request not found")

    try:
        new_status = models.TeleRequestStatus(payload.status)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid status")

    # If transitioning beyond requested, require clinician role
    if new_status != models.TeleRequestStatus.requested:
        # Check clinician role
        is_clinician = (
            db.query(models.UserRole)
            .filter(models.UserRole.user_id == user.id, models.UserRole.role_name == models.RoleName.clinician)
            .first()
        )
        if not is_clinician:
            raise HTTPException(status_code=403, detail="Clinician role required")

    # Validate transition
    if not validate_status_transition(req_obj.status, new_status):
        raise HTTPException(status_code=400, detail="Invalid status transition")

    req_obj.status = new_status

    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="tele.request.update",
        entity_type="tele_request",
        entity_id=req_obj.id,
    )

    db.commit()
    db.refresh(req_obj)

    return TeleRequestResponse(
        id=req_obj.id,
        user_id=req_obj.user_id,
        symptom_summary=req_obj.symptom_summary,
        preferred_time=req_obj.preferred_time,
        status=req_obj.status.value,
        created_at=req_obj.created_at.isoformat(),
    )


@app.post("/prescriptions", response_model=PrescriptionResponse, tags=["TeleSahay"])
def create_prescription(
    payload: PrescriptionCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    # Require clinician role
    from services.api.auth import require_role

    is_clinician = (
        db.query(models.UserRole)
        .filter(models.UserRole.user_id == user.id, models.UserRole.role_name == models.RoleName.clinician)
        .first()
    )
    if not is_clinician:
        raise HTTPException(status_code=403, detail="Clinician role required")

    summary = render_sms_summary(payload.items, payload.advice)

    import json
    rx = models.Prescription(
        user_id=payload.user_id,
        clinician_user_id=user.id,
        items_json=json.dumps(payload.items),
        summary_text=summary,
    )
    db.add(rx)

    # Enqueue SMS message
    enqueue_message(db=db, user_id=payload.user_id, channel="sms", payload=summary)

    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="prescription.create",
        entity_type="prescription",
        entity_id=rx.id,
    )

    db.commit()
    db.refresh(rx)

    return PrescriptionResponse(
        id=rx.id,
        user_id=rx.user_id,
        clinician_user_id=rx.clinician_user_id,
        items=payload.items,
        summary_text=rx.summary_text,
        created_at=rx.created_at.isoformat(),
    )


@app.get("/analytics/events", response_model=list[AnalyticsEventResponse], tags=["Analytics"])
def list_my_analytics_events(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = db.query(models.AnalyticsEvent).filter(models.AnalyticsEvent.user_id == user.id).all()
    return [AnalyticsEventResponse(id=r.id, event_type=r.event_type) for r in rows]


@app.post("/family/invites/{invite_id}/accept", response_model=FamilyInviteResponse, tags=["Family"])
def accept_family_invite(
    invite_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    inv = db.get(models.FamilyInvite, invite_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invite not found")
    if inv.invitee_user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if inv.status != models.InviteStatus.pending:
        raise HTTPException(status_code=409, detail="Invite already handled")

    inv.status = models.InviteStatus.accepted
    inv.responded_at = datetime.utcnow()

    # Add membership
    db.add(models.FamilyMember(family_group_id=inv.family_group_id, user_id=user.id))

    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="family.invite.accept",
        entity_type="family_invite",
        entity_id=inv.id,
    )

    db.commit()
    db.refresh(inv)

    return FamilyInviteResponse(
        id=inv.id,
        family_group_id=inv.family_group_id,
        inviter_user_id=inv.inviter_user_id,
        invitee_user_id=inv.invitee_user_id,
        status=inv.status.value,
    )

# DailySahay endpoints (Phase 3.3)

@app.post("/daily/vitals", tags=["DailySahay"])
def create_vitals(payload: VitalsCreate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    from datetime import datetime
    v = models.VitalsMeasurement(user_id=user.id, type=payload.type, value=payload.value, unit=payload.unit, measured_at=datetime.fromisoformat(payload.measured_at))
    db.add(v)
    write_audit(db=db, request=request, actor_user_id=user.id, action="daily.vitals.create", entity_type="vitals", entity_id=v.id)
    db.commit()
    return {"id": v.id}

@app.post("/daily/food", tags=["DailySahay"])
def create_food(payload: FoodLogCreate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    from datetime import datetime
    f = models.FoodLog(user_id=user.id, description=payload.description, calories=payload.calories, logged_at=datetime.fromisoformat(payload.logged_at))
    db.add(f)
    write_audit(db=db, request=request, actor_user_id=user.id, action="daily.food.create", entity_type="food", entity_id=f.id)
    db.commit()
    return {"id": f.id}

@app.post("/daily/sleep", tags=["DailySahay"])
def create_sleep(payload: SleepLogCreate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    from datetime import datetime
    s = models.SleepLog(user_id=user.id, duration_minutes=payload.duration_minutes, quality=payload.quality, logged_at=datetime.fromisoformat(payload.logged_at))
    db.add(s)
    write_audit(db=db, request=request, actor_user_id=user.id, action="daily.sleep.create", entity_type="sleep", entity_id=s.id)
    db.commit()
    return {"id": s.id}

@app.post("/daily/water", tags=["DailySahay"])
def create_water(payload: WaterLogCreate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    from datetime import datetime
    w = models.WaterLog(user_id=user.id, amount_ml=payload.amount_ml, logged_at=datetime.fromisoformat(payload.logged_at))
    db.add(w)
    write_audit(db=db, request=request, actor_user_id=user.id, action="daily.water.create", entity_type="water", entity_id=w.id)
    db.commit()
    return {"id": w.id}

@app.post("/daily/mood", tags=["DailySahay"])
def create_mood(payload: MoodLogCreate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    from datetime import datetime
    m = models.MoodLog(user_id=user.id, mood_scale=payload.mood_scale, notes=payload.notes, logged_at=datetime.fromisoformat(payload.logged_at))
    db.add(m)
    write_audit(db=db, request=request, actor_user_id=user.id, action="daily.mood.create", entity_type="mood", entity_id=m.id)
    db.commit()
    return {"id": m.id}

@app.post("/medications", tags=["DailySahay"])
def create_medication_plan(payload: MedicationPlanCreate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    from datetime import datetime
    import json
    mp = models.MedicationPlan(user_id=user.id, name=payload.name, schedule_json=json.dumps(payload.schedule), start_date=datetime.fromisoformat(payload.start_date), end_date=datetime.fromisoformat(payload.end_date) if payload.end_date else None)
    db.add(mp)
    write_audit(db=db, request=request, actor_user_id=user.id, action="medication.create", entity_type="medication", entity_id=mp.id)
    db.commit()
    return {"id": mp.id}

@app.post("/medications/{plan_id}/adherence", tags=["DailySahay"])
def create_adherence_event(plan_id: str, payload: AdherenceEventCreate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    from datetime import datetime
    ae = models.AdherenceEvent(user_id=user.id, medication_plan_id=payload.medication_plan_id, taken_at=datetime.fromisoformat(payload.taken_at), status=payload.status)
    db.add(ae)
    write_audit(db=db, request=request, actor_user_id=user.id, action="adherence.create", entity_type="adherence", entity_id=ae.id)
    db.commit()
    return {"id": ae.id}

@app.get("/daily/summary", response_model=DailySummaryResponse, tags=["DailySahay"])
def get_daily_summary(date: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    from datetime import datetime, timedelta
    target_date = datetime.fromisoformat(date).date()
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)
    
    water_total = db.query(models.WaterLog).filter(models.WaterLog.user_id == user.id, models.WaterLog.logged_at >= start, models.WaterLog.logged_at < end).all()
    water_sum = sum([w.amount_ml for w in water_total])
    
    food_total = db.query(models.FoodLog).filter(models.FoodLog.user_id == user.id, models.FoodLog.logged_at >= start, models.FoodLog.logged_at < end).all()
    food_sum = sum([f.calories for f in food_total if f.calories])
    
    sleep_total = db.query(models.SleepLog).filter(models.SleepLog.user_id == user.id, models.SleepLog.logged_at >= start, models.SleepLog.logged_at < end).all()
    sleep_sum = sum([s.duration_minutes for s in sleep_total])
    
    mood_total = db.query(models.MoodLog).filter(models.MoodLog.user_id == user.id, models.MoodLog.logged_at >= start, models.MoodLog.logged_at < end).all()
    mood_avg = sum([m.mood_scale for m in mood_total]) / len(mood_total) if mood_total else None
    
    vitals_count = db.query(models.VitalsMeasurement).filter(models.VitalsMeasurement.user_id == user.id, models.VitalsMeasurement.measured_at >= start, models.VitalsMeasurement.measured_at < end).count()
    
    # NOTE: Bump REPORT_VERSION on schema changes (1.1, 2.0, etc.)
    # This ensures clients can handle different report formats gracefully.
    return DailySummaryResponse(report_version=REPORT_VERSION, date=date, water_total_ml=water_sum, food_total_calories=food_sum, sleep_total_minutes=sleep_sum, mood_avg=mood_avg, vitals_count=vitals_count)

# VaxTrack + BalVikas endpoints (Phase 3.4)

@app.get("/vax/next_due", response_model=NextDueVaccineResponse, tags=["VaxTrack"])
def get_next_due_vaccine(user_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    from datetime import datetime, timedelta
    # Get user's profile to find age
    profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
    if not profile or profile.age is None:
        raise HTTPException(status_code=400, detail="DOB required")
    
    # For MVP: use age (years) as proxy; assume DOB = today - age*365
    dob_approx = datetime.utcnow() - timedelta(days=profile.age * 365)
    age_days = (datetime.utcnow() - dob_approx).days
    
    # Get all schedule rules
    rules = db.query(models.VaccineScheduleRule).order_by(models.VaccineScheduleRule.due_age_days).all()
    
    # Get user's vaccination records
    records = db.query(models.VaccinationRecord).filter(models.VaccinationRecord.user_id == user_id).all()
    administered = {(r.vaccine_name, r.dose_number) for r in records}
    
    # Find next due
    for rule in rules:
        if (rule.vaccine_name, rule.dose_number) not in administered:
            due_date_abs = dob_approx + timedelta(days=rule.due_age_days)
            overdue = due_date_abs < datetime.utcnow()
            return NextDueVaccineResponse(vaccine_name=rule.vaccine_name, dose_number=rule.dose_number, due_date=due_date_abs.date().isoformat(), overdue=overdue)
    
    raise HTTPException(status_code=404, detail="No pending vaccines")

@app.post("/vax/records", tags=["VaxTrack"])
def create_vaccination_record(payload: VaccinationRecordCreate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    from datetime import datetime
    rec = models.VaccinationRecord(user_id=user.id, vaccine_name=payload.vaccine_name, dose_number=payload.dose_number, administered_at=datetime.fromisoformat(payload.administered_at))
    db.add(rec)
    write_audit(db=db, request=request, actor_user_id=user.id, action="vax.record.create", entity_type="vax", entity_id=rec.id)
    
    # Emit analytics event with consent gate (Phase 7.1)
    # Only emits if user has granted analytics consent
    emit_vaccination_analytics(
        db=db,
        user_id=user.id,
        vaccine_name=payload.vaccine_name,
        dose_number=payload.dose_number,
    )
    
    db.commit()
    return {"id": rec.id}

@app.post("/growth/records", tags=["BalVikas"])
def create_growth_record(payload: GrowthRecordCreate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    from datetime import datetime
    rec = models.GrowthRecord(user_id=user.id, height_cm=payload.height_cm, weight_kg=payload.weight_kg, recorded_at=datetime.fromisoformat(payload.recorded_at))
    db.add(rec)
    write_audit(db=db, request=request, actor_user_id=user.id, action="growth.record.create", entity_type="growth", entity_id=rec.id)
    db.commit()
    return {"id": rec.id}

@app.get("/milestones", response_model=list[MilestoneResponse], tags=["BalVikas"])
def get_milestones(age_months: int | None = None, db: Session = Depends(get_db)):
    if age_months is not None:
        rows = db.query(models.Milestone).filter(models.Milestone.age_months <= age_months).all()
    else:
        rows = db.query(models.Milestone).all()
    return [MilestoneResponse(age_months=r.age_months, description=r.description) for r in rows]

# NeuroScreen endpoints (Phase 4.1)

@app.post("/neuroscreen/results", response_model=NeuroscreenResultResponse, tags=["NeuroScreen"])
def create_neuroscreen_result(payload: NeuroscreenResultCreate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    from services.api.neuroscreen import score_neuroscreen
    import json
    
    version = db.get(models.NeuroscreenVersion, payload.version_id)
    if not version:
        raise HTTPException(status_code=404, detail="NeuroScreen version not found")
    
    raw_score, band, guidance = score_neuroscreen(version, payload.responses)
    
    result = models.NeuroscreenResult(
        user_id=user.id,
        version_id=payload.version_id,
        responses_json=json.dumps(payload.responses),
        raw_score=raw_score,
        band=band,
        guidance_text=guidance,
    )
    db.add(result)
    
    write_audit(db=db, request=request, actor_user_id=user.id, action="neuroscreen.result.create", entity_type="neuroscreen", entity_id=result.id)
    
    # Emit analytics event with consent gate (Phase 7.1)
    # Only emits if user has granted analytics consent
    emit_neuroscreen_analytics(
        db=db,
        user_id=user.id,
        band=result.band.value,
    )
    
    db.commit()
    db.refresh(result)
    
    return NeuroscreenResultResponse(
        id=result.id,
        user_id=result.user_id,
        version_id=result.version_id,
        responses=payload.responses,
        raw_score=result.raw_score,
        band=result.band.value,
        guidance_text=result.guidance_text,
        created_at=result.created_at.isoformat(),
    )


@app.get("/neuroscreen/results/{result_id}", response_model=NeuroscreenResultResponse, tags=["NeuroScreen"])
def get_neuroscreen_result(result_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    import json
    
    result = db.get(models.NeuroscreenResult, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="NeuroScreen result not found")
    
    # Auth: only owner can read (TODO: add caregiver/clinician access later)
    if result.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    return NeuroscreenResultResponse(
        id=result.id,
        user_id=result.user_id,
        version_id=result.version_id,
        responses=json.loads(result.responses_json),
        raw_score=result.raw_score,
        band=result.band.value,
        guidance_text=result.guidance_text,
        created_at=result.created_at.isoformat(),
    )

# TherapyHome content packs endpoints (Phase 4.2)

from fastapi import UploadFile, File, Form
from services.api import storage as storage_module
from services.api.therapy_pack_builder import build_therapy_pack

@app.post("/therapy/modules", response_model=TherapyModuleResponse, tags=["TherapyHome"])
def create_therapy_module(
    payload: TherapyModuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Create a therapy module with metadata and steps.
    
    Admin/clinician only (for MVP: allow authenticated users).
    """
    import json
    
    # Create module
    module = models.TherapyModule(
        title=payload.title,
        description=payload.description,
        module_type=payload.module_type,
        age_range_min=payload.age_range_min,
        age_range_max=payload.age_range_max,
    )
    db.add(module)
    db.flush()
    
    # Create steps
    for step_data in payload.steps:
        media_refs_json = json.dumps(step_data.media_references) if step_data.media_references else None
        step = models.TherapyStep(
            module_id=module.id,
            step_number=step_data.step_number,
            title=step_data.title,
            description=step_data.description,
            media_references=media_refs_json,
            duration_minutes=step_data.duration_minutes,
        )
        db.add(step)
    
    write_audit(db=db, request=request, actor_user_id=user.id, action="therapy.module.create", entity_type="therapy_module", entity_id=module.id)
    
    db.commit()
    db.refresh(module)
    
    # Build response with steps
    steps_response = []
    for step in sorted(module.steps, key=lambda s: s.step_number):
        media_refs = json.loads(step.media_references) if step.media_references else None
        steps_response.append(TherapyStepResponse(
            id=step.id,
            step_number=step.step_number,
            title=step.title,
            description=step.description,
            media_references=media_refs,
            duration_minutes=step.duration_minutes,
        ))
    
    return TherapyModuleResponse(
        id=module.id,
        title=module.title,
        description=module.description,
        module_type=module.module_type,
        age_range_min=module.age_range_min,
        age_range_max=module.age_range_max,
        created_at=module.created_at.isoformat(),
        steps=steps_response,
    )


@app.get("/therapy/modules", response_model=list[TherapyModuleResponse], tags=["TherapyHome"])
def list_therapy_modules(
    module_type: str | None = None,
    age_months: int | None = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """List therapy modules with optional filtering.
    
    Args:
        module_type: Filter by module type (e.g., "speech", "motor")
        age_months: Filter by age (returns modules where age is in range)
        limit: Max number of results
        offset: Pagination offset
    """
    import json
    
    query = db.query(models.TherapyModule)
    
    if module_type:
        query = query.filter(models.TherapyModule.module_type == module_type)
    
    if age_months is not None:
        # Filter where age_months falls within the module's age range
        query = query.filter(
            (models.TherapyModule.age_range_min == None) | (models.TherapyModule.age_range_min <= age_months)
        ).filter(
            (models.TherapyModule.age_range_max == None) | (models.TherapyModule.age_range_max >= age_months)
        )
    
    query = query.order_by(models.TherapyModule.created_at.desc()).offset(offset).limit(limit)
    modules = query.all()
    
    result = []
    for module in modules:
        steps_response = []
        for step in sorted(module.steps, key=lambda s: s.step_number):
            media_refs = json.loads(step.media_references) if step.media_references else None
            steps_response.append(TherapyStepResponse(
                id=step.id,
                step_number=step.step_number,
                title=step.title,
                description=step.description,
                media_references=media_refs,
                duration_minutes=step.duration_minutes,
            ))
        
        result.append(TherapyModuleResponse(
            id=module.id,
            title=module.title,
            description=module.description,
            module_type=module.module_type,
            age_range_min=module.age_range_min,
            age_range_max=module.age_range_max,
            created_at=module.created_at.isoformat(),
            steps=steps_response,
        ))
    
    return result


@app.post("/therapy/modules/{module_id}/generate-pack", response_model=TherapyPackResponse, tags=["TherapyHome"])
def generate_pack_from_module(
    module_id: str,
    version: str = "1.0",
    request: Request = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Auto-generate a therapy pack ZIP from a module.
    
    This is the pack builder endpoint that creates offline content bundles.
    """
    module = db.get(models.TherapyModule, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    
    # Generate ZIP bundle
    zip_bytes = build_therapy_pack(module)
    
    # Store the pack
    minio_key = f"therapy-packs/{module.title.replace(' ', '_')}_{version}.zip"
    checksum = storage_module.store_file(minio_key, zip_bytes)
    
    pack = models.TherapyPack(
        title=f"{module.title} v{version}",
        description=module.description,
        version=version,
        checksum=checksum,
        minio_key=minio_key,
        module_id=module_id,
    )
    db.add(pack)
    
    write_audit(db=db, request=request, actor_user_id=user.id, action="therapy.pack.generate", entity_type="therapy_pack", entity_id=pack.id)
    
    db.commit()
    db.refresh(pack)
    
    return TherapyPackResponse(
        id=pack.id,
        title=pack.title,
        description=pack.description,
        version=pack.version,
        checksum=pack.checksum,
        created_at=pack.created_at.isoformat(),
        module_id=pack.module_id,
    )


@app.post("/therapy/packs", response_model=TherapyPackResponse, tags=["TherapyHome"])
async def create_therapy_pack(
    title: str = Form(...),
    description: str = Form(...),
    version: str = Form(...),
    file: UploadFile = File(...),
    module_id: str = Form(None),
    request: Request = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Upload a therapy pack ZIP file.
    
    Admin-only (for MVP: allow any authenticated user to upload; add admin check later).
    """
    
    file_bytes = await file.read()
    minio_key = f"therapy-packs/{title.replace(' ', '_')}_{version}.zip"
    checksum = storage_module.store_file(minio_key, file_bytes)
    
    pack = models.TherapyPack(
        title=title,
        description=description,
        version=version,
        checksum=checksum,
        minio_key=minio_key,
        module_id=module_id,
    )
    db.add(pack)
    
    write_audit(db=db, request=request, actor_user_id=user.id, action="therapy.pack.upload", entity_type="therapy_pack", entity_id=pack.id)
    
    db.commit()
    db.refresh(pack)
    
    return TherapyPackResponse(
        id=pack.id,
        title=pack.title,
        description=pack.description,
        version=pack.version,
        checksum=pack.checksum,
        created_at=pack.created_at.isoformat(),
        module_id=pack.module_id,
    )


@app.get("/therapy/packs/{pack_id}", response_model=TherapyPackResponse, tags=["TherapyHome"])
def get_therapy_pack(
    pack_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Get therapy pack metadata by ID."""
    pack = db.get(models.TherapyPack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Therapy pack not found")
    
    return TherapyPackResponse(
        id=pack.id,
        title=pack.title,
        description=pack.description,
        version=pack.version,
        checksum=pack.checksum,
        created_at=pack.created_at.isoformat(),
        module_id=pack.module_id,
    )


@app.get("/therapy/packs", response_model=list[TherapyPackResponse], tags=["TherapyHome"])
def list_therapy_packs(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """List all therapy packs.
    
    Authorized roles: caregiver, ASHA, clinician (for MVP: allow all authenticated).
    """
    packs = db.query(models.TherapyPack).order_by(models.TherapyPack.created_at.desc()).all()
    return [
        TherapyPackResponse(
            id=p.id,
            title=p.title,
            description=p.description,
            version=p.version,
            checksum=p.checksum,
            created_at=p.created_at.isoformat(),
            module_id=p.module_id,
        )
        for p in packs
    ]


from fastapi.responses import StreamingResponse

@app.get("/therapy/packs/{pack_id}/download", tags=["TherapyHome"])
def download_therapy_pack(
    pack_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    # Permission check: caregiver/ASHA/clinician only
    allowed_roles = [models.RoleName.caregiver, models.RoleName.asha, models.RoleName.clinician]
    user_roles = db.query(models.UserRole).filter(models.UserRole.user_id == user.id).all()
    has_permission = any(r.role_name in allowed_roles for r in user_roles)
    
    if not has_permission:
        raise HTTPException(status_code=403, detail="Caregiver, ASHA, or clinician role required")
    
    pack = db.get(models.TherapyPack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Therapy pack not found")
    
    file_bytes = storage_module.retrieve_file(pack.minio_key)
    
    write_audit(db=db, request=request, actor_user_id=user.id, action="therapy.pack.download", entity_type="therapy_pack", entity_id=pack.id)
    db.commit()
    
    return StreamingResponse(
        iter([file_bytes]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={pack.title}_{pack.version}.zip"},
    )

# CommBridge AAC endpoints (Phase 4.3)

@app.post("/aac/symbol-sets", response_model=AACSymbolSetDetailResponse, tags=["AAC"])
def create_aac_symbol_set(
    payload: AACSymbolSetCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Create AAC symbol set with symbols.
    
    Supports bulk symbol creation for performance with large libraries.
    """
    import json
    
    ss = models.AACSymbolSet(
        name=payload.name,
        language=payload.language,
        version=payload.version,
        metadata_json=json.dumps(payload.metadata),
    )
    db.add(ss)
    db.flush()
    
    # Create symbols
    for symbol_data in payload.symbols:
        metadata_json = json.dumps(symbol_data.metadata) if symbol_data.metadata else None
        symbol = models.AACSymbol(
            symbol_set_id=ss.id,
            name=symbol_data.name,
            image_reference=symbol_data.image_reference,
            category=symbol_data.category,
            metadata_json=metadata_json,
        )
        db.add(symbol)
    
    write_audit(db=db, request=request, actor_user_id=user.id, action="aac.symbolset.create", entity_type="aac_symbolset", entity_id=ss.id)
    
    db.commit()
    db.refresh(ss)
    
    # Build response with symbols
    symbols_response = []
    for symbol in ss.symbols:
        metadata = json.loads(symbol.metadata_json) if symbol.metadata_json else None
        symbols_response.append(AACSymbolResponse(
            id=symbol.id,
            name=symbol.name,
            image_reference=symbol.image_reference,
            category=symbol.category,
            metadata=metadata,
        ))
    
    return AACSymbolSetDetailResponse(
        id=ss.id,
        name=ss.name,
        language=ss.language,
        version=ss.version,
        created_at=ss.created_at.isoformat(),
        symbols=symbols_response,
    )


@app.get("/aac/symbol-sets", response_model=list[AACSymbolSetResponse], tags=["AAC"])
def list_aac_symbol_sets(
    language: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """List AAC symbol sets with pagination.
    
    Performance guard: Uses pagination to handle large symbol libraries efficiently.
    """
    from sqlalchemy import func
    
    query = db.query(models.AACSymbolSet)
    
    if language:
        query = query.filter(models.AACSymbolSet.language == language)
    
    query = query.order_by(models.AACSymbolSet.created_at.desc()).offset(offset).limit(limit)
    symbol_sets = query.all()
    
    result = []
    for ss in symbol_sets:
        # Count symbols for each set
        symbol_count = db.query(func.count(models.AACSymbol.id)).filter(
            models.AACSymbol.symbol_set_id == ss.id
        ).scalar()
        
        result.append(AACSymbolSetResponse(
            id=ss.id,
            name=ss.name,
            language=ss.language,
            version=ss.version,
            created_at=ss.created_at.isoformat(),
            symbol_count=symbol_count,
        ))
    
    return result


@app.get("/aac/symbol-sets/{symbol_set_id}", response_model=AACSymbolSetDetailResponse, tags=["AAC"])
def get_aac_symbol_set(
    symbol_set_id: str,
    include_symbols: bool = True,
    symbols_limit: int = 1000,
    symbols_offset: int = 0,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Get AAC symbol set with optional symbol pagination.
    
    Performance guard: Symbol loading is paginated for large libraries (10k+ symbols).
    Set include_symbols=false to get only metadata.
    """
    import json
    
    ss = db.get(models.AACSymbolSet, symbol_set_id)
    if not ss:
        raise HTTPException(status_code=404, detail="Symbol set not found")
    
    symbols_response = []
    if include_symbols:
        # Paginated symbol loading for performance
        symbols = db.query(models.AACSymbol).filter(
            models.AACSymbol.symbol_set_id == symbol_set_id
        ).offset(symbols_offset).limit(symbols_limit).all()
        
        for symbol in symbols:
            metadata = json.loads(symbol.metadata_json) if symbol.metadata_json else None
            symbols_response.append(AACSymbolResponse(
                id=symbol.id,
                name=symbol.name,
                image_reference=symbol.image_reference,
                category=symbol.category,
                metadata=metadata,
            ))
    
    return AACSymbolSetDetailResponse(
        id=ss.id,
        name=ss.name,
        language=ss.language,
        version=ss.version,
        created_at=ss.created_at.isoformat(),
        symbols=symbols_response,
    )


@app.post("/aac/phraseboards", response_model=AACPhraseboardResponse, tags=["AAC"])
def create_aac_phraseboard(
    payload: AACPhraseboardCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    import json
    pb = models.AACPhraseboard(
        symbol_set_id=payload.symbol_set_id,
        title=payload.title,
        phrases_json=json.dumps(payload.phrases),
    )
    db.add(pb)
    
    write_audit(db=db, request=request, actor_user_id=user.id, action="aac.phraseboard.create", entity_type="aac_phraseboard", entity_id=pb.id)
    
    db.commit()
    db.refresh(pb)
    
    return AACPhraseboardResponse(
        id=pb.id,
        symbol_set_id=pb.symbol_set_id,
        title=pb.title,
        phrases=payload.phrases,
        created_at=pb.created_at.isoformat(),
    )


@app.get("/aac/phraseboards", response_model=list[AACPhraseboardResponse], tags=["AAC"])
def list_aac_phraseboards(
    symbol_set_id: str | None = None,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    import json
    query = db.query(models.AACPhraseboard)
    if symbol_set_id:
        query = query.filter(models.AACPhraseboard.symbol_set_id == symbol_set_id)
    
    query = query.offset(offset).limit(limit)
    pbs = query.all()
    
    return [
        AACPhraseboardResponse(
            id=pb.id,
            symbol_set_id=pb.symbol_set_id,
            title=pb.title,
            phrases=json.loads(pb.phrases_json),
            created_at=pb.created_at.isoformat(),
        )
        for pb in pbs
    ]


@app.get("/aac/phraseboards/{phraseboard_id}", response_model=AACPhraseboardResponse, tags=["AAC"])
def get_aac_phraseboard(
    phraseboard_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    import json
    pb = db.get(models.AACPhraseboard, phraseboard_id)
    if not pb:
        raise HTTPException(status_code=404, detail="Phraseboard not found")
    
    return AACPhraseboardResponse(
        id=pb.id,
        symbol_set_id=pb.symbol_set_id,
        title=pb.title,
        phrases=json.loads(pb.phrases_json),
        created_at=pb.created_at.isoformat(),
    )


# ShikayatChain Complaints endpoints (Phase 5.1)

from typing import Optional
from fastapi import Header

@app.post("/complaints", response_model=ComplaintResponse, tags=["Complaints"])
async def create_complaint(
    payload: ComplaintCreate,
    request: Request,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """Create a complaint with optional anonymous mode.
    
    Anonymous complaints:
    - Set is_anonymous=True or omit Authorization header
    - user_id will be NULL
    - Optional contact_info will be encrypted
    - Audit logs show "anonymous" actor
    
    Authenticated complaints:
    - Provide Authorization header
    - Set is_anonymous=False
    - user_id links to authenticated user
    """
    from datetime import timedelta
    
    # Get user if authenticated
    user = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        user = db.query(models.User).join(models.AuthToken).filter(
            models.AuthToken.token == token,
            models.AuthToken.revoked_at == None
        ).first()
    
    # Determine user_id (None for anonymous)
    user_id = None if payload.is_anonymous else (user.id if user else None)
    
    # Encrypt contact info if provided for anonymous complaints
    contact_encrypted = None
    if payload.is_anonymous and payload.contact_info:
        # Simple encryption for MVP (use proper encryption in production)
        import base64
        contact_encrypted = base64.b64encode(payload.contact_info.encode()).decode()
    
    # Calculate SLA due date (default: 7 days for district level)
    sla_due_at = datetime.utcnow() + timedelta(days=7)
    
    complaint = models.Complaint(
        user_id=user_id,
        category=models.ComplaintCategory(payload.category),
        description=payload.description,
        status=models.ComplaintStatus.submitted,
        current_level=1,
        sla_due_at=sla_due_at,
        contact_info_encrypted=contact_encrypted,
    )
    db.add(complaint)
    db.flush()
    
    # Audit with anonymous actor handling
    write_audit(
        db=db,
        request=request,
        actor_user_id=None if payload.is_anonymous else user_id,
        action="complaint.create",
        entity_type="complaint",
        entity_id=complaint.id,
    )
    
    db.commit()
    db.refresh(complaint)
    
    return ComplaintResponse(
        id=complaint.id,
        category=complaint.category.value,
        description=complaint.description,
        status=complaint.status.value,
        current_level=complaint.current_level,
        created_at=complaint.created_at.isoformat(),
        updated_at=complaint.updated_at.isoformat(),
        sla_due_at=complaint.sla_due_at.isoformat() if complaint.sla_due_at else None,
        resolved_at=complaint.resolved_at.isoformat() if complaint.resolved_at else None,
        is_anonymous=user_id is None,
        evidence=[],
    )


@app.get("/complaints/{complaint_id}", response_model=ComplaintResponse, tags=["Complaints"])
def get_complaint(
    complaint_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Get complaint details.
    
    Privacy: Users can only view their own complaints unless they have officer role.
    """
    complaint = db.get(models.Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    # Access control: user can view own complaints or officers can view all
    is_officer = db.query(models.UserRole).filter(
        models.UserRole.user_id == user.id,
        models.UserRole.role_name.in_([
            models.RoleName.district_officer,
            models.RoleName.state_officer,
            models.RoleName.national_admin
        ])
    ).first()
    
    if not is_officer and complaint.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # Build evidence response
    evidence_list = []
    for ev in complaint.evidence:
        evidence_list.append(ComplaintEvidenceResponse(
            id=ev.id,
            filename=ev.filename,
            content_type=ev.content_type,
            file_size=ev.file_size,
            checksum=ev.checksum,
            uploaded_at=ev.uploaded_at.isoformat(),
            is_complete=ev.is_complete,
        ))
    
    return ComplaintResponse(
        id=complaint.id,
        category=complaint.category.value,
        description=complaint.description,
        status=complaint.status.value,
        current_level=complaint.current_level,
        created_at=complaint.created_at.isoformat(),
        updated_at=complaint.updated_at.isoformat(),
        sla_due_at=complaint.sla_due_at.isoformat() if complaint.sla_due_at else None,
        resolved_at=complaint.resolved_at.isoformat() if complaint.resolved_at else None,
        is_anonymous=complaint.user_id is None,
        evidence=evidence_list,
    )


@app.get("/complaints", response_model=list[ComplaintResponse], tags=["Complaints"])
def list_complaints(
    status: str | None = None,
    category: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """List complaints with filtering.
    
    Regular users see only their own complaints.
    Officers see all complaints at their level or below.
    """
    # Check if user is an officer
    user_roles = db.query(models.UserRole).filter(models.UserRole.user_id == user.id).all()
    officer_roles = [models.RoleName.district_officer, models.RoleName.state_officer, models.RoleName.national_admin]
    is_officer = any(r.role_name in officer_roles for r in user_roles)
    
    query = db.query(models.Complaint)
    
    # Access control
    if not is_officer:
        query = query.filter(models.Complaint.user_id == user.id)
    
    # Filters
    if status:
        query = query.filter(models.Complaint.status == models.ComplaintStatus(status))
    if category:
        query = query.filter(models.Complaint.category == models.ComplaintCategory(category))
    
    query = query.order_by(models.Complaint.created_at.desc()).offset(offset).limit(limit)
    complaints = query.all()
    
    result = []
    for complaint in complaints:
        evidence_list = [
            ComplaintEvidenceResponse(
                id=ev.id,
                filename=ev.filename,
                content_type=ev.content_type,
                file_size=ev.file_size,
                checksum=ev.checksum,
                uploaded_at=ev.uploaded_at.isoformat(),
                is_complete=ev.is_complete,
            )
            for ev in complaint.evidence
        ]
        
        result.append(ComplaintResponse(
            id=complaint.id,
            category=complaint.category.value,
            description=complaint.description,
            status=complaint.status.value,
            current_level=complaint.current_level,
            created_at=complaint.created_at.isoformat(),
            updated_at=complaint.updated_at.isoformat(),
            sla_due_at=complaint.sla_due_at.isoformat() if complaint.sla_due_at else None,
            resolved_at=complaint.resolved_at.isoformat() if complaint.resolved_at else None,
            is_anonymous=complaint.user_id is None,
            evidence=evidence_list,
        ))
    
    return result


@app.post("/complaints/{complaint_id}/evidence/initiate", response_model=EvidenceUploadInitiateResponse, tags=["Complaints"])
async def initiate_evidence_upload(
    complaint_id: str,
    payload: EvidenceUploadInitiate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Initiate evidence upload with resumable/chunked upload support.
    
    For large files (>5MB), returns upload_id for chunked upload.
    For smaller files, returns upload_url for direct upload.
    """
    from services.api.storage import generate_encrypted_key, initiate_chunked_upload, CHUNK_SIZE
    
    complaint = db.get(models.Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    # Access control: only complaint owner can upload evidence
    if complaint.user_id != user.id and complaint.user_id is not None:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # Generate encrypted object key
    object_key = generate_encrypted_key(payload.filename, prefix="complaint-evidence")
    
    # Create evidence record
    evidence = models.ComplaintEvidence(
        complaint_id=complaint_id,
        object_key=object_key,
        filename=payload.filename,
        content_type=payload.content_type,
        file_size=payload.file_size,
        checksum="",  # Will be set on completion
        is_complete=False,
    )
    
    # For large files, initiate chunked upload
    upload_id = None
    chunk_size = None
    if payload.file_size > CHUNK_SIZE:
        upload_id = initiate_chunked_upload(object_key)
        evidence.upload_id = upload_id
        chunk_size = CHUNK_SIZE
    
    db.add(evidence)
    
    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="complaint.evidence.initiate",
        entity_type="complaint_evidence",
        entity_id=evidence.id,
    )
    
    db.commit()
    db.refresh(evidence)
    
    return EvidenceUploadInitiateResponse(
        evidence_id=evidence.id,
        upload_url=None,  # For MVP, client uploads via chunk endpoint
        upload_id=upload_id,
        chunk_size=chunk_size,
    )


@app.post("/complaints/{complaint_id}/evidence/{evidence_id}/upload", tags=["Complaints"])
async def upload_evidence_direct(
    complaint_id: str,
    evidence_id: str,
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Direct upload for small evidence files (<5MB).
    
    For larger files, use chunked upload instead.
    """
    from services.api.storage import store_file_stream
    
    evidence = db.get(models.ComplaintEvidence, evidence_id)
    if not evidence or evidence.complaint_id != complaint_id:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    # Store file
    checksum = store_file_stream(evidence.object_key, file.file)
    
    # Update evidence record
    evidence.checksum = checksum
    evidence.is_complete = True
    
    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="complaint.evidence.upload",
        entity_type="complaint_evidence",
        entity_id=evidence.id,
    )
    
    db.commit()
    
    return {"status": "success", "evidence_id": evidence.id, "checksum": checksum}


@app.post("/complaints/{complaint_id}/evidence/{evidence_id}/chunk/{chunk_number}", tags=["Complaints"])
async def upload_evidence_chunk(
    complaint_id: str,
    evidence_id: str,
    chunk_number: int,
    chunk: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Upload a single chunk for resumable upload."""
    from services.api.storage import upload_chunk
    
    evidence = db.get(models.ComplaintEvidence, evidence_id)
    if not evidence or evidence.complaint_id != complaint_id:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    if not evidence.upload_id:
        raise HTTPException(status_code=400, detail="Not a chunked upload")
    
    # Upload chunk
    chunk_data = await chunk.read()
    upload_chunk(evidence.upload_id, chunk_number, chunk_data)
    
    return {"status": "success", "chunk_number": chunk_number}


@app.post("/complaints/{complaint_id}/evidence/{evidence_id}/complete", tags=["Complaints"])
def complete_evidence_upload(
    complaint_id: str,
    evidence_id: str,
    payload: EvidenceUploadComplete,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Complete a chunked upload and verify checksum."""
    from services.api.storage import complete_chunked_upload
    
    evidence = db.get(models.ComplaintEvidence, evidence_id)
    if not evidence or evidence.complaint_id != complaint_id:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    if not evidence.upload_id:
        raise HTTPException(status_code=400, detail="Not a chunked upload")
    
    # Complete upload
    object_key, server_checksum = complete_chunked_upload(evidence.upload_id)
    
    # Verify checksum
    if server_checksum != payload.checksum:
        raise HTTPException(status_code=400, detail="Checksum mismatch")
    
    # Update evidence
    evidence.checksum = server_checksum
    evidence.is_complete = True
    evidence.upload_id = None
    
    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="complaint.evidence.complete",
        entity_type="complaint_evidence",
        entity_id=evidence.id,
    )
    
    db.commit()
    
    return {"status": "success", "evidence_id": evidence.id, "checksum": server_checksum}


# SLA Management endpoints (Phase 5.2)

@app.post("/sla-rules", response_model=SLARuleResponse, tags=["SLA"])
def create_sla_rule(
    payload: SLARuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Create or update SLA rule for a category and escalation level.
    
    Admin only (for MVP: allow authenticated users).
    """
    # Check if rule already exists
    existing = db.query(models.SLARule).filter(
        models.SLARule.category == models.ComplaintCategory(payload.category),
        models.SLARule.escalation_level == payload.escalation_level
    ).first()
    
    if existing:
        # Update existing rule
        existing.time_limit_hours = payload.time_limit_hours
        db.commit()
        db.refresh(existing)
        
        return SLARuleResponse(
            id=existing.id,
            category=existing.category.value,
            escalation_level=existing.escalation_level,
            time_limit_hours=existing.time_limit_hours,
            created_at=existing.created_at.isoformat(),
        )
    
    # Create new rule
    rule = models.SLARule(
        category=models.ComplaintCategory(payload.category),
        escalation_level=payload.escalation_level,
        time_limit_hours=payload.time_limit_hours,
    )
    db.add(rule)
    
    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="sla.rule.create",
        entity_type="sla_rule",
        entity_id=rule.id,
    )
    
    db.commit()
    db.refresh(rule)
    
    return SLARuleResponse(
        id=rule.id,
        category=rule.category.value,
        escalation_level=rule.escalation_level,
        time_limit_hours=rule.time_limit_hours,
        created_at=rule.created_at.isoformat(),
    )


@app.get("/sla-rules", response_model=list[SLARuleResponse], tags=["SLA"])
def list_sla_rules(
    category: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """List SLA rules with optional category filter."""
    query = db.query(models.SLARule)
    
    if category:
        query = query.filter(models.SLARule.category == models.ComplaintCategory(category))
    
    query = query.order_by(models.SLARule.category, models.SLARule.escalation_level)
    rules = query.all()
    
    return [
        SLARuleResponse(
            id=r.id,
            category=r.category.value,
            escalation_level=r.escalation_level,
            time_limit_hours=r.time_limit_hours,
            created_at=r.created_at.isoformat(),
        )
        for r in rules
    ]


@app.put("/complaints/{complaint_id}/status", response_model=ComplaintResponse, tags=["Complaints"])
def update_complaint_status(
    complaint_id: str,
    payload: ComplaintUpdateStatus,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Update complaint status with SLA enforcement.
    
    Status transitions:
    - submitted → under_review → investigating → resolved/closed
    - Any status → escalated (if SLA breached)
    
    Officers can update any complaint status.
    Regular users cannot update status.
    """
    complaint = db.get(models.Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    # Access control: only officers can update status
    user_roles = db.query(models.UserRole).filter(models.UserRole.user_id == user.id).all()
    officer_roles = [models.RoleName.district_officer, models.RoleName.state_officer, models.RoleName.national_admin]
    is_officer = any(r.role_name in officer_roles for r in user_roles)
    
    if not is_officer:
        raise HTTPException(status_code=403, detail="Only officers can update complaint status")
    
    # Record history
    old_status = complaint.status
    old_level = complaint.current_level
    new_status = models.ComplaintStatus(payload.status)
    
    # Update complaint
    complaint.status = new_status
    complaint.updated_at = datetime.utcnow()
    
    # If resolved, record resolution time
    if new_status == models.ComplaintStatus.resolved:
        complaint.resolved_at = datetime.utcnow()
    
    # Add status history
    history = models.ComplaintStatusHistory(
        complaint_id=complaint_id,
        old_status=old_status,
        new_status=new_status,
        old_level=old_level,
        new_level=complaint.current_level,
        changed_by_user_id=user.id,
        change_reason=payload.resolution_notes,
        is_auto_escalation=False,
    )
    db.add(history)
    
    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="complaint.status.update",
        entity_type="complaint",
        entity_id=complaint.id,
    )
    
    db.commit()
    db.refresh(complaint)
    
    # Build response
    evidence_list = [
        ComplaintEvidenceResponse(
            id=ev.id,
            filename=ev.filename,
            content_type=ev.content_type,
            file_size=ev.file_size,
            checksum=ev.checksum,
            uploaded_at=ev.uploaded_at.isoformat(),
            is_complete=ev.is_complete,
        )
        for ev in complaint.evidence
    ]
    
    return ComplaintResponse(
        id=complaint.id,
        category=complaint.category.value,
        description=complaint.description,
        status=complaint.status.value,
        current_level=complaint.current_level,
        created_at=complaint.created_at.isoformat(),
        updated_at=complaint.updated_at.isoformat(),
        sla_due_at=complaint.sla_due_at.isoformat() if complaint.sla_due_at else None,
        resolved_at=complaint.resolved_at.isoformat() if complaint.resolved_at else None,
        is_anonymous=complaint.user_id is None,
        evidence=evidence_list,
    )


@app.get("/complaints/{complaint_id}/history", response_model=list[ComplaintStatusHistoryResponse], tags=["Complaints"])
def get_complaint_history(
    complaint_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Get status change history for a complaint.
    
    Officers can view all history.
    Regular users can view history for their own complaints.
    """
    complaint = db.get(models.Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    # Access control
    user_roles = db.query(models.UserRole).filter(models.UserRole.user_id == user.id).all()
    officer_roles = [models.RoleName.district_officer, models.RoleName.state_officer, models.RoleName.national_admin]
    is_officer = any(r.role_name in officer_roles for r in user_roles)
    
    if not is_officer and complaint.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # Get history
    history = db.query(models.ComplaintStatusHistory).filter(
        models.ComplaintStatusHistory.complaint_id == complaint_id
    ).order_by(models.ComplaintStatusHistory.timestamp).all()
    
    return [
        ComplaintStatusHistoryResponse(
            id=h.id,
            complaint_id=h.complaint_id,
            old_status=h.old_status.value if h.old_status else None,
            new_status=h.new_status.value,
            old_level=h.old_level,
            new_level=h.new_level,
            changed_by_user_id=h.changed_by_user_id,
            change_reason=h.change_reason,
            is_auto_escalation=h.is_auto_escalation,
            timestamp=h.timestamp.isoformat(),
        )
        for h in history
    ]


@app.post("/complaints/escalation/run", tags=["SLA"])
def run_escalation(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Manually trigger escalation check.
    
    Admin only. Normally runs via background worker.
    """
    from services.api.escalation_worker import run_escalation_check
    
    result = run_escalation_check(db)
    
    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="escalation.manual_run",
        entity_type="system",
        entity_id="escalation_worker",
    )
    
    return result


# Complaint Closure with Feedback (Phase 5.3)

@app.patch("/complaints/{complaint_id}/close", response_model=ComplaintResponse, tags=["Complaints"])
def close_complaint(
    complaint_id: str,
    payload: ComplaintCloseRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Close a complaint with required feedback.
    
    Closure requirements:
    - Feedback must be provided (rating + comments)
    - Rating must be 1-5 stars
    - Only officers can close complaints
    - Complaint must not already be closed
    
    This enforces that citizens provide feedback before complaint is closed.
    """
    complaint = db.get(models.Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    # Access control: only officers can close
    user_roles = db.query(models.UserRole).filter(models.UserRole.user_id == user.id).all()
    officer_roles = [models.RoleName.district_officer, models.RoleName.state_officer, models.RoleName.national_admin]
    is_officer = any(r.role_name in officer_roles for r in user_roles)
    
    if not is_officer:
        raise HTTPException(status_code=403, detail="Only officers can close complaints")
    
    # Validate feedback
    if payload.feedback.rating < 1 or payload.feedback.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    
    if not payload.feedback.comments or len(payload.feedback.comments.strip()) == 0:
        raise HTTPException(status_code=400, detail="Feedback comments are required")
    
    # Validate complaint can be closed
    if complaint.status == models.ComplaintStatus.closed:
        raise HTTPException(status_code=400, detail="Complaint is already closed")
    
    # Record history
    old_status = complaint.status
    
    # Update complaint with feedback and close
    complaint.feedback_rating = payload.feedback.rating
    complaint.feedback_comments = payload.feedback.comments
    complaint.feedback_submitted_at = datetime.utcnow()
    complaint.status = models.ComplaintStatus.closed
    complaint.closed_at = datetime.utcnow()
    complaint.updated_at = datetime.utcnow()
    
    # Add status history
    history = models.ComplaintStatusHistory(
        complaint_id=complaint_id,
        old_status=old_status,
        new_status=models.ComplaintStatus.closed,
        old_level=complaint.current_level,
        new_level=complaint.current_level,
        changed_by_user_id=user.id,
        change_reason=payload.resolution_notes,
        is_auto_escalation=False,
    )
    db.add(history)
    
    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="complaint.close",
        entity_type="complaint",
        entity_id=complaint.id,
    )
    
    db.commit()
    db.refresh(complaint)
    
    # Build response
    evidence_list = [
        ComplaintEvidenceResponse(
            id=ev.id,
            filename=ev.filename,
            content_type=ev.content_type,
            file_size=ev.file_size,
            checksum=ev.checksum,
            uploaded_at=ev.uploaded_at.isoformat(),
            is_complete=ev.is_complete,
        )
        for ev in complaint.evidence
    ]
    
    return ComplaintResponse(
        id=complaint.id,
        category=complaint.category.value,
        description=complaint.description,
        status=complaint.status.value,
        current_level=complaint.current_level,
        created_at=complaint.created_at.isoformat(),
        updated_at=complaint.updated_at.isoformat(),
        sla_due_at=complaint.sla_due_at.isoformat() if complaint.sla_due_at else None,
        resolved_at=complaint.resolved_at.isoformat() if complaint.resolved_at else None,
        is_anonymous=complaint.user_id is None,
        evidence=evidence_list,
    )


# Blockchain Anchoring endpoints (Phase 6.1)

@app.post("/blockchain/anchor/complaint/{complaint_id}", response_model=BlockchainAnchorResponse, tags=["Blockchain"])
def anchor_complaint_to_blockchain(
    complaint_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Anchor a complaint to blockchain with graceful degradation.
    
    This creates an immutable record with:
    - Hashes of complaint metadata (NO PII)
    - Timestamps
    - Event ID (nonce)
    
    Graceful degradation: If blockchain fails, anchor is marked for retry.
    The actual complaint data stays off-chain in encrypted database.
    """
    from services.api.blockchain_service import blockchain_service
    
    complaint = db.get(models.Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    # Anchor to blockchain (graceful degradation - never throws)
    success, tx_hash = blockchain_service.anchor_complaint(db, complaint)
    
    # Get the anchor record (created by service)
    anchor = db.query(models.BlockchainAnchor).filter(
        models.BlockchainAnchor.entity_type == "complaint",
        models.BlockchainAnchor.entity_id == complaint_id
    ).order_by(models.BlockchainAnchor.anchored_at.desc()).first()
    
    if not anchor:
        raise HTTPException(status_code=500, detail="Failed to create anchor record")
    
    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="blockchain.anchor.create",
        entity_type="blockchain_anchor",
        entity_id=anchor.id,
    )
    
    return BlockchainAnchorResponse(
        id=anchor.id,
        entity_type=anchor.entity_type,
        entity_id=anchor.entity_id,
        complaint_hash=anchor.complaint_hash,
        status_hash=anchor.status_hash,
        sla_params_hash=anchor.sla_params_hash,
        created_at_timestamp=anchor.created_at_timestamp,
        updated_at_timestamp=anchor.updated_at_timestamp,
        event_id=anchor.event_id,
        blockchain_tx_hash=anchor.blockchain_tx_hash,
        blockchain_block_number=anchor.blockchain_block_number,
        blockchain_status=anchor.blockchain_status,
        anchor_version=anchor.anchor_version,
        anchored_at=anchor.anchored_at.isoformat(),
        confirmed_at=anchor.confirmed_at.isoformat() if anchor.confirmed_at else None,
    )


@app.get("/blockchain/anchors/complaint/{complaint_id}", response_model=list[BlockchainAnchorResponse], tags=["Blockchain"])
def get_complaint_anchors(
    complaint_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Get all blockchain anchors for a complaint."""
    complaint = db.get(models.Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    # Access control
    user_roles = db.query(models.UserRole).filter(models.UserRole.user_id == user.id).all()
    officer_roles = [models.RoleName.district_officer, models.RoleName.state_officer, models.RoleName.national_admin]
    is_officer = any(r.role_name in officer_roles for r in user_roles)
    
    if not is_officer and complaint.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    anchors = db.query(models.BlockchainAnchor).filter(
        models.BlockchainAnchor.entity_type == "complaint",
        models.BlockchainAnchor.entity_id == complaint_id
    ).order_by(models.BlockchainAnchor.anchored_at).all()
    
    return [
        BlockchainAnchorResponse(
            id=a.id,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            complaint_hash=a.complaint_hash,
            status_hash=a.status_hash,
            sla_params_hash=a.sla_params_hash,
            created_at_timestamp=a.created_at_timestamp,
            updated_at_timestamp=a.updated_at_timestamp,
            event_id=a.event_id,
            blockchain_tx_hash=a.blockchain_tx_hash,
            blockchain_block_number=a.blockchain_block_number,
            blockchain_status=a.blockchain_status,
            anchor_version=a.anchor_version,
            anchored_at=a.anchored_at.isoformat(),
            confirmed_at=a.confirmed_at.isoformat() if a.confirmed_at else None,
        )
        for a in anchors
    ]


@app.get("/blockchain/verify/{anchor_id}", tags=["Blockchain"])
def verify_blockchain_anchor(
    anchor_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Verify a blockchain anchor by recomputing hashes."""
    from services.api.blockchain_hash import generate_complaint_hash, generate_status_hash, generate_sla_params_hash
    
    anchor = db.get(models.BlockchainAnchor, anchor_id)
    if not anchor:
        raise HTTPException(status_code=404, detail="Anchor not found")
    
    complaint = db.get(models.Complaint, anchor.entity_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Original complaint not found")
    
    # Recompute hashes
    current_complaint_hash = generate_complaint_hash(complaint)
    current_status_hash = generate_status_hash(complaint)
    current_sla_hash = generate_sla_params_hash(complaint)
    
    # Compare with anchored hashes
    return {
        "anchor_id": anchor.id,
        "entity_id": anchor.entity_id,
        "blockchain_status": anchor.blockchain_status,
        "verification": {
            "complaint_hash_match": current_complaint_hash == anchor.complaint_hash,
            "status_hash_match": current_status_hash == anchor.status_hash,
            "sla_params_hash_match": current_sla_hash == anchor.sla_params_hash,
        },
        "is_valid": (
            current_complaint_hash == anchor.complaint_hash and
            current_status_hash == anchor.status_hash and
            current_sla_hash == anchor.sla_params_hash
        ),
    }


@app.post("/blockchain/retry-pending", tags=["Blockchain"])
def retry_pending_anchors(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Manually trigger retry of pending blockchain anchors.
    
    Admin only. Normally runs via background worker.
    """
    from services.api.blockchain_service import blockchain_service
    
    result = blockchain_service.retry_pending_anchors(db)
    
    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="blockchain.retry.manual",
        entity_type="system",
        entity_id="retry_worker",
    )
    
    return result


# ============================================================
# OutbreakSense Endpoints (Phase 7.3)
# ============================================================

@app.post("/outbreak/detect", tags=["OutbreakSense"])
def run_outbreak_detection_api(
    target_date: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Run outbreak detection for specified date (Phase 7.3).
    
    Analyzes triage volumes and detects anomalies that may indicate outbreaks.
    Uses 7-day rolling baseline with 3-sigma threshold.
    
    In production: restrict to admin/health_officer roles.
    Should be run daily via cron job.
    """
    from datetime import datetime
    
    target_dt = datetime.fromisoformat(target_date).date() if target_date else None
    
    # Run detection
    alerts = run_outbreak_detection(db=db, target_date=target_dt)
    
    # Persist alerts
    count = persist_alerts(db=db, alerts=alerts)
    
    return {
        "status": "success",
        "alerts_detected": count,
        "target_date": target_dt.isoformat() if target_dt else datetime.utcnow().date().isoformat(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/outbreak/alerts", response_model=OutbreakAlertsListResponse, tags=["OutbreakSense"])
def get_outbreak_alerts_api(
    geo_cell: str | None = None,
    min_alert_level: str | None = None,
    days: int = 7,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get active outbreak alerts (Phase 7.3).
    
    Returns list of active alerts, optionally filtered by:
    - geo_cell: Specific geographic region
    - min_alert_level: Minimum severity (low, medium, high, critical)
    - days: Number of days to look back
    
    For district officers: automatically filtered to their district.
    """
    alerts = get_active_alerts(
        db=db,
        geo_cell=geo_cell,
        min_alert_level=min_alert_level,
        days=days,
    )
    
    # Convert to response format
    alert_responses = []
    for alert in alerts:
        alert_responses.append(OutbreakAlertResponse(
            id=alert.id,
            geo_cell=alert.geo_cell,
            event_time=alert.event_time.isoformat(),
            event_type=alert.event_type,
            category=alert.category,
            baseline_mean=alert.baseline_mean,
            baseline_std=alert.baseline_std,
            observed_count=alert.observed_count,
            z_score=alert.z_score,
            threshold_sigma=alert.threshold_sigma,
            alert_level=alert.alert_level,
            confidence=alert.confidence,
            status=alert.status,
            acknowledged_by=alert.acknowledged_by,
            acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
            resolution_notes=alert.resolution_notes,
            created_at=alert.created_at.isoformat(),
        ))
    
    return OutbreakAlertsListResponse(
        alerts=alert_responses,
        count=len(alert_responses),
        filters={
            "geo_cell": geo_cell,
            "min_alert_level": min_alert_level,
            "days": days,
        },
    )


@app.post("/outbreak/alerts/{alert_id}/acknowledge", tags=["OutbreakSense"])
def acknowledge_outbreak_alert_api(
    alert_id: str,
    payload: AcknowledgeAlertRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Acknowledge an outbreak alert (Phase 7.3).
    
    Marks alert as seen by a health officer.
    Does not resolve the alert.
    """
    alert = acknowledge_alert(
        db=db,
        alert_id=alert_id,
        acknowledged_by=user.username,
        notes=payload.notes,
    )
    
    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action="outbreak_alert.acknowledge",
        entity_type="outbreak_alert",
        entity_id=alert_id,
    )
    
    return {
        "status": "success",
        "alert_id": alert_id,
        "acknowledged_by": user.username,
        "acknowledged_at": alert.acknowledged_at.isoformat(),
    }


@app.post("/outbreak/alerts/{alert_id}/resolve", tags=["OutbreakSense"])
def resolve_outbreak_alert_api(
    alert_id: str,
    payload: ResolveAlertRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Resolve an outbreak alert (Phase 7.3).
    
    Marks alert as resolved or false positive.
    Resolution options:
    - 'resolved': Outbreak confirmed and addressed
    - 'false_positive': False alarm, no outbreak
    """
    if payload.resolution not in ['resolved', 'false_positive']:
        raise HTTPException(status_code=400, detail="Resolution must be 'resolved' or 'false_positive'")
    
    alert = resolve_alert(
        db=db,
        alert_id=alert_id,
        resolution=payload.resolution,
        notes=payload.notes,
    )
    
    write_audit(
        db=db,
        request=request,
        actor_user_id=user.id,
        action=f"outbreak_alert.resolve.{payload.resolution}",
        entity_type="outbreak_alert",
        entity_id=alert_id,
    )
    
    return {
        "status": "success",
        "alert_id": alert_id,
        "resolution": payload.resolution,
        "resolved_by": user.username,
    }


@app.get("/outbreak/summary", response_model=OutbreakSummaryResponse, tags=["OutbreakSense"])
def get_outbreak_summary_api(
    days: int = 30,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Get outbreak detection system summary (Phase 7.3).
    
    Returns:
    - Total alerts generated
    - Active alerts count
    - Breakdown by severity level
    - Breakdown by status
    - Top geo_cells with most alerts
    - False positive rate
    
    Useful for monitoring system performance and outbreak trends.
    """
    summary = get_outbreak_summary(db=db, days=days)
    
    return OutbreakSummaryResponse(**summary)
