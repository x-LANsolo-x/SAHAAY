import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RoleName(str, enum.Enum):
    citizen = "citizen"
    caregiver = "caregiver"
    asha = "asha"
    clinician = "clinician"
    district_officer = "district_officer"
    state_officer = "state_officer"
    national_admin = "national_admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    profile: Mapped["Profile"] = relationship(back_populates="user", uselist=False)
    roles: Mapped[list["UserRole"]] = relationship(back_populates="user")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True)

    # Minimal profile fields (expand later)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    age: Mapped[int | None] = mapped_column(nullable=True)
    sex: Mapped[str | None] = mapped_column(String, nullable=True)
    pincode: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="profile")


class Role(Base):
    __tablename__ = "roles"

    name: Mapped[RoleName] = mapped_column(Enum(RoleName), primary_key=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    role_name: Mapped[RoleName] = mapped_column(Enum(RoleName), ForeignKey("roles.name"))

    __table_args__ = (UniqueConstraint("user_id", "role_name", name="uq_user_role"),)

    user: Mapped[User] = relationship(back_populates="roles")


class FamilyGroup(Base):
    __tablename__ = "family_groups"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_by_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    members: Mapped[list["FamilyMember"]] = relationship(back_populates="family_group")


class FamilyMember(Base):
    __tablename__ = "family_members"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    family_group_id: Mapped[str] = mapped_column(String, ForeignKey("family_groups.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("family_group_id", "user_id", name="uq_family_member"),)

    family_group: Mapped[FamilyGroup] = relationship(back_populates="members")


class InviteStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ConsentCategory(str, enum.Enum):
    tracking = "tracking"
    neuro = "neuro"
    complaints = "complaints"
    analytics = "analytics"


class ConsentScope(str, enum.Enum):
    local_storage = "local_storage"
    cloud_sync = "cloud_sync"
    share_with_clinician = "share_with_clinician"
    share_with_asha = "share_with_asha"
    gov_aggregated = "gov_aggregated"


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    category: Mapped[ConsentCategory] = mapped_column(Enum(ConsentCategory), index=True)
    scope: Mapped[ConsentScope] = mapped_column(Enum(ConsentScope), index=True)

    # Versioning: each (user,category,scope) can have multiple records over time.
    version: Mapped[int] = mapped_column(default=1)

    granted: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "category", "scope", "version", name="uq_consent_version"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)

    action: Mapped[str] = mapped_column(String, index=True)
    entity_type: Mapped[str] = mapped_column(String, index=True)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    device_id: Mapped[str | None] = mapped_column(String, nullable=True)

    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Tamper detection: hash chain
    prev_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    entry_hash: Mapped[str] = mapped_column(String, index=True)


class SyncEvent(Base):
    __tablename__ = "sync_events"

    # Client-generated unique id for idempotency.
    event_id: Mapped[str] = mapped_column(String, primary_key=True)

    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    device_id: Mapped[str] = mapped_column(String, index=True)

    entity_type: Mapped[str] = mapped_column(String, index=True)
    operation: Mapped[str] = mapped_column(String, index=True)

    client_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    payload_json: Mapped[str] = mapped_column(String)


class TriageCategory(str, enum.Enum):
    self_care = "self_care"
    phc = "phc"
    emergency = "emergency"


class TriageSession(Base):
    __tablename__ = "triage_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    symptom_text: Mapped[str] = mapped_column(String)
    followup_answers_json: Mapped[str] = mapped_column(String)

    triage_category: Mapped[TriageCategory] = mapped_column(Enum(TriageCategory), index=True)
    red_flags_json: Mapped[str] = mapped_column(String)
    guidance_text: Mapped[str] = mapped_column(String)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TeleRequestStatus(str, enum.Enum):
    requested = "requested"
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"


class TeleRequest(Base):
    __tablename__ = "tele_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    symptom_summary: Mapped[str] = mapped_column(String)
    preferred_time: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[TeleRequestStatus] = mapped_column(Enum(TeleRequestStatus), default=TeleRequestStatus.requested, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Prescription(Base):
    __tablename__ = "prescriptions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    clinician_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    items_json: Mapped[str] = mapped_column(String)
    summary_text: Mapped[str] = mapped_column(String)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class MessageQueueStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class MessageQueue(Base):
    __tablename__ = "message_queue"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    channel: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[str] = mapped_column(String)
    status: Mapped[MessageQueueStatus] = mapped_column(Enum(MessageQueueStatus), default=MessageQueueStatus.pending, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class VitalsMeasurement(Base):
    __tablename__ = "vitals_measurements"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    type: Mapped[str] = mapped_column(String, index=True)  # bp, sugar, heart_rate, spo2, weight
    value: Mapped[str] = mapped_column(String)
    unit: Mapped[str] = mapped_column(String)
    measured_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class FoodLog(Base):
    __tablename__ = "food_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    description: Mapped[str] = mapped_column(String)
    calories: Mapped[int | None] = mapped_column(nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class SleepLog(Base):
    __tablename__ = "sleep_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    duration_minutes: Mapped[int] = mapped_column()
    quality: Mapped[str | None] = mapped_column(String, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class WaterLog(Base):
    __tablename__ = "water_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    amount_ml: Mapped[int] = mapped_column()
    logged_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class MoodLog(Base):
    __tablename__ = "mood_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    mood_scale: Mapped[int] = mapped_column()
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class MedicationPlan(Base):
    __tablename__ = "medication_plans"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    name: Mapped[str] = mapped_column(String)
    schedule_json: Mapped[str] = mapped_column(String)
    start_date: Mapped[datetime] = mapped_column(DateTime)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AdherenceEvent(Base):
    __tablename__ = "adherence_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    medication_plan_id: Mapped[str] = mapped_column(String, ForeignKey("medication_plans.id"), index=True)

    taken_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String)


class VaccineScheduleRule(Base):
    __tablename__ = "vaccine_schedule_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    vaccine_name: Mapped[str] = mapped_column(String, index=True)
    dose_number: Mapped[int] = mapped_column()
    due_age_days: Mapped[int] = mapped_column()


class VaccinationRecord(Base):
    __tablename__ = "vaccination_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    vaccine_name: Mapped[str] = mapped_column(String)
    dose_number: Mapped[int] = mapped_column()
    administered_at: Mapped[datetime] = mapped_column(DateTime)


class GrowthRecord(Base):
    __tablename__ = "growth_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    height_cm: Mapped[float | None] = mapped_column(nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime)


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    age_months: Mapped[int] = mapped_column(index=True)
    description: Mapped[str] = mapped_column(String)


class NeuroscreenVersion(Base):
    __tablename__ = "neuroscreen_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String)
    scoring_rules_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class NeuroscreenBand(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class NeuroscreenResult(Base):
    __tablename__ = "neuroscreen_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    version_id: Mapped[str] = mapped_column(String, ForeignKey("neuroscreen_versions.id"), index=True)

    responses_json: Mapped[str] = mapped_column(String)
    raw_score: Mapped[int] = mapped_column()
    band: Mapped[NeuroscreenBand] = mapped_column(Enum(NeuroscreenBand))
    guidance_text: Mapped[str] = mapped_column(String)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TherapyModule(Base):
    """Therapy module metadata (type, age range, description)."""
    __tablename__ = "therapy_modules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[str] = mapped_column(String)
    module_type: Mapped[str] = mapped_column(String, index=True)  # e.g., "speech", "motor", "social"
    age_range_min: Mapped[int | None] = mapped_column(nullable=True)  # age in months
    age_range_max: Mapped[int | None] = mapped_column(nullable=True)  # age in months
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    steps: Mapped[list["TherapyStep"]] = relationship(back_populates="module", cascade="all, delete-orphan")


class TherapyStep(Base):
    """Structured step data for a therapy module."""
    __tablename__ = "therapy_steps"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    module_id: Mapped[str] = mapped_column(String, ForeignKey("therapy_modules.id"), index=True)
    step_number: Mapped[int] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    media_references: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON array of media file keys
    duration_minutes: Mapped[int | None] = mapped_column(nullable=True)

    __table_args__ = (UniqueConstraint("module_id", "step_number", name="uq_module_step"),)

    module: Mapped[TherapyModule] = relationship(back_populates="steps")


class TherapyPack(Base):
    """ZIP bundle metadata with checksum and storage location."""
    __tablename__ = "therapy_packs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String)
    checksum: Mapped[str] = mapped_column(String)
    minio_key: Mapped[str] = mapped_column(String)
    module_id: Mapped[str | None] = mapped_column(String, ForeignKey("therapy_modules.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TherapyPackModule(Base):
    """Legacy: module metadata embedded in packs (deprecated in favor of TherapyModule)."""
    __tablename__ = "therapy_pack_modules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    pack_id: Mapped[str] = mapped_column(String, ForeignKey("therapy_packs.id"), index=True)
    title: Mapped[str] = mapped_column(String)
    step_count: Mapped[int] = mapped_column()
    metadata_json: Mapped[str] = mapped_column(String)


class AACSymbolSet(Base):
    """AAC symbol set metadata with language and version info."""
    __tablename__ = "aac_symbol_sets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, index=True)
    language: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[str] = mapped_column(String)
    metadata_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    symbols: Mapped[list["AACSymbol"]] = relationship(back_populates="symbol_set", cascade="all, delete-orphan")


class AACSymbol(Base):
    """Individual AAC symbol with name, image reference, and category."""
    __tablename__ = "aac_symbols"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol_set_id: Mapped[str] = mapped_column(String, ForeignKey("aac_symbol_sets.id"), index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    image_reference: Mapped[str] = mapped_column(String)  # URL or storage key to image
    category: Mapped[str] = mapped_column(String, index=True)  # e.g., "food", "emotions", "actions"
    metadata_json: Mapped[str | None] = mapped_column(String, nullable=True)  # Additional metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    symbol_set: Mapped[AACSymbolSet] = relationship(back_populates="symbols")


class AACPhraseboard(Base):
    """AAC phraseboard with board layout and associated symbols."""
    __tablename__ = "aac_phraseboards"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol_set_id: Mapped[str] = mapped_column(String, ForeignKey("aac_symbol_sets.id"), index=True)
    title: Mapped[str] = mapped_column(String, index=True)
    phrases_json: Mapped[str] = mapped_column(String)  # Board layout with symbol references
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AnalyticsEvent(Base):
    """
    De-identified analytics events for GovSahay dashboards.
    
    CRITICAL PRIVACY NOTES:
    - user_id is stored ONLY for audit/consent tracking, NOT for analytics queries
    - All analytics queries MUST use payload_json (which is de-identified)
    - payload_json contains NO direct identifiers (see analytics.py for schema)
    
    DEPRECATED: This model stores individual events. Use AggregatedAnalyticsEvent instead.
    """
    __tablename__ = "analytics_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # user_id for audit/consent only - MUST NOT be used in analytics aggregations
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    
    event_type: Mapped[str] = mapped_column(String, index=True)
    
    # De-identified payload (see analytics.py for allowed fields)
    payload_json: Mapped[str] = mapped_column(String)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AggregatedAnalyticsEvent(Base):
    """
    Aggregated analytics events - multiple user events merged into single rows.
    
    This is the PRIMARY table for analytics queries. Individual events are accumulated
    in memory and flushed as aggregated rows periodically.
    
    Example: 20 individual triage events → 1 aggregated row with count=20
    
    Aggregation key: (event_type, category, time_bucket, geo_cell, age_bucket, gender)
    """
    __tablename__ = "aggregated_analytics_events"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Aggregation dimensions (used as composite key)
    event_type: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String, index=True)
    time_bucket: Mapped[datetime] = mapped_column(DateTime, index=True)  # Rounded to 15-min
    geo_cell: Mapped[str] = mapped_column(String, index=True)  # District-level
    age_bucket: Mapped[str] = mapped_column(String, index=True)  # 0-5, 6-12, etc.
    gender: Mapped[str] = mapped_column(String, index=True)  # M/F/Other/Unknown
    
    # Aggregated metrics
    count: Mapped[int] = mapped_column(default=1)  # Number of events merged
    
    # Metadata (JSON for flexibility)
    metadata_json: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Tracking
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Schema version
    schema_version: Mapped[str] = mapped_column(String, default="1.0")
    
    # Composite unique constraint on aggregation dimensions
    __table_args__ = (
        UniqueConstraint(
            "event_type", "category", "time_bucket", "geo_cell", "age_bucket", "gender",
            name="uq_aggregated_event_key"
        ),
    )


class OutbreakAlert(Base):
    """
    Outbreak alerts detected by OutbreakSense (Phase 7.3).
    
    Anomaly detection flags regions with unusual triage volumes that may indicate
    disease outbreaks or public health emergencies.
    
    Algorithm: Rolling baseline (7-day mean/std) + 3-sigma threshold
    """
    __tablename__ = "outbreak_alerts"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Location and time
    geo_cell: Mapped[str] = mapped_column(String, index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    
    # Event details
    event_type: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Baseline statistics (from rolling 7-day window)
    baseline_mean: Mapped[float] = mapped_column()
    baseline_std: Mapped[float] = mapped_column()
    
    # Observed values
    observed_count: Mapped[int] = mapped_column()
    
    # Anomaly metrics
    z_score: Mapped[float] = mapped_column()  # (observed - mean) / std
    threshold_sigma: Mapped[float] = mapped_column(default=3.0)  # Detection threshold
    
    # Alert classification
    alert_level: Mapped[str] = mapped_column(String, index=True)  # 'low', 'medium', 'high', 'critical'
    confidence: Mapped[float] = mapped_column()  # 0.0 to 1.0
    
    # Status tracking
    status: Mapped[str] = mapped_column(String, default="active", index=True)  # 'active', 'resolved', 'false_positive'
    acknowledged_by: Mapped[str | None] = mapped_column(String, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FamilyInvite(Base):
    __tablename__ = "family_invites"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    family_group_id: Mapped[str] = mapped_column(String, ForeignKey("family_groups.id"), index=True)
    inviter_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    invitee_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    status: Mapped[InviteStatus] = mapped_column(Enum(InviteStatus), default=InviteStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("family_group_id", "invitee_user_id", name="uq_family_invitee"),)


class ComplaintStatus(str, enum.Enum):
    """Complaint lifecycle status."""
    submitted = "submitted"
    under_review = "under_review"
    investigating = "investigating"
    resolved = "resolved"
    closed = "closed"
    escalated = "escalated"


class ComplaintCategory(str, enum.Enum):
    """Complaint categories for routing."""
    service_quality = "service_quality"
    staff_behavior = "staff_behavior"
    facility_issues = "facility_issues"
    medication_error = "medication_error"
    billing_dispute = "billing_dispute"
    discrimination = "discrimination"
    other = "other"


class Complaint(Base):
    """Complaint with support for anonymous submissions."""
    __tablename__ = "complaints"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)  # NULL for anonymous
    
    category: Mapped[ComplaintCategory] = mapped_column(Enum(ComplaintCategory), index=True)
    description: Mapped[str] = mapped_column(String)
    status: Mapped[ComplaintStatus] = mapped_column(Enum(ComplaintStatus), default=ComplaintStatus.submitted, index=True)
    
    # Escalation tracking
    current_level: Mapped[int] = mapped_column(default=1, index=True)  # 1=district, 2=state, 3=national
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # SLA tracking
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # Closure feedback (required for closed status)
    feedback_rating: Mapped[int | None] = mapped_column(nullable=True)  # 1-5 stars
    feedback_comments: Mapped[str | None] = mapped_column(String, nullable=True)
    feedback_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # Anonymous contact (optional)
    contact_info_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)  # Encrypted phone/email for anonymous
    
    # Relationships
    evidence: Mapped[list["ComplaintEvidence"]] = relationship(back_populates="complaint", cascade="all, delete-orphan")


class ComplaintEvidence(Base):
    """Evidence attachments for complaints with encrypted storage."""
    __tablename__ = "complaint_evidence"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_id: Mapped[str] = mapped_column(String, ForeignKey("complaints.id"), index=True)
    
    # Encrypted object key (MinIO path)
    object_key: Mapped[str] = mapped_column(String)
    
    # File metadata
    filename: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    file_size: Mapped[int] = mapped_column()  # bytes
    checksum: Mapped[str] = mapped_column(String)  # SHA256 for integrity
    
    # Upload tracking (for resumable uploads)
    upload_id: Mapped[str | None] = mapped_column(String, nullable=True)  # For multipart uploads
    is_complete: Mapped[bool] = mapped_column(Boolean, default=True)
    
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationship
    complaint: Mapped[Complaint] = relationship(back_populates="evidence")


class SLARule(Base):
    """SLA policy rules for complaint categories and escalation levels."""
    __tablename__ = "sla_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    category: Mapped[ComplaintCategory] = mapped_column(Enum(ComplaintCategory), index=True)
    escalation_level: Mapped[int] = mapped_column(index=True)  # 1=district, 2=state, 3=national
    time_limit_hours: Mapped[int] = mapped_column()  # Hours before escalation
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (UniqueConstraint("category", "escalation_level", name="uq_sla_category_level"),)


class ComplaintStatusHistory(Base):
    """History of complaint status changes for audit and tracking."""
    __tablename__ = "complaint_status_history"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_id: Mapped[str] = mapped_column(String, ForeignKey("complaints.id"), index=True)
    
    old_status: Mapped[ComplaintStatus | None] = mapped_column(Enum(ComplaintStatus), nullable=True)
    new_status: Mapped[ComplaintStatus] = mapped_column(Enum(ComplaintStatus), index=True)
    
    old_level: Mapped[int | None] = mapped_column(nullable=True)
    new_level: Mapped[int] = mapped_column()
    
    changed_by_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    change_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    is_auto_escalation: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class BlockchainAnchor(Base):
    """Blockchain anchoring records for immutability (hashes only, no PII)."""
    __tablename__ = "blockchain_anchors"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Entity being anchored
    entity_type: Mapped[str] = mapped_column(String, index=True)  # "complaint", "status_change", etc.
    entity_id: Mapped[str] = mapped_column(String, index=True)
    
    # Hash payload (NO PII - only hashes)
    complaint_hash: Mapped[str] = mapped_column(String)  # SHA256 of complaint metadata
    status_hash: Mapped[str | None] = mapped_column(String, nullable=True)  # SHA256 of status
    sla_params_hash: Mapped[str | None] = mapped_column(String, nullable=True)  # SHA256 of SLA params
    
    # Timestamps (safe to store on-chain)
    created_at_timestamp: Mapped[int] = mapped_column()  # Unix timestamp
    updated_at_timestamp: Mapped[int | None] = mapped_column(nullable=True)
    
    # Blockchain metadata
    event_id: Mapped[str] = mapped_column(String, unique=True, index=True)  # Nonce/event ID
    blockchain_tx_hash: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    blockchain_block_number: Mapped[int | None] = mapped_column(nullable=True, index=True)
    blockchain_status: Mapped[str] = mapped_column(String, default="pending", index=True)  # pending/confirmed/failed
    
    # Anchoring metadata
    anchor_version: Mapped[str] = mapped_column(String, default="1.0")
    anchored_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "event_id", name="uq_anchor_entity_event"),)
