from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy.orm import Session

from services.api import models
from services.api.auth import create_access_token, hash_password, verify_password, get_current_user
from services.api.audit import verify_audit_chain, write_audit
from services.api.consent import has_active_consent, upsert_consent
from services.api.sync import process_event
from services.api.telesahay import enqueue_message, render_sms_summary, validate_status_transition
from services.api.triage import generate_triage
from services.api.db import engine, get_db
from services.api.schemas import (
    AnalyticsEventResponse,
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
)

# Create tables (dev-only). In production use Alembic migrations.
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="SAHAAY API")


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
    return ExportResponse(
        profile=ProfileResponse(
            id=profile.id,
            user_id=profile.user_id,
            full_name=profile.full_name,
            age=profile.age,
            sex=profile.sex,
            pincode=profile.pincode,
        )
    )


@app.post("/analytics/ping", response_model=AnalyticsEventResponse, tags=["Analytics"])
def analytics_ping(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    # Example analytics generation endpoint: only allowed if analytics+gov_aggregated consent granted.
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
    
    return DailySummaryResponse(date=date, water_total_ml=water_sum, food_total_calories=food_sum, sleep_total_minutes=sleep_sum, mood_avg=mood_avg, vitals_count=vitals_count)

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
