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


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
