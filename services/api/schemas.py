from datetime import date

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileResponse(BaseModel):
    id: str
    user_id: str
    full_name: str | None = None
    age: int | None = None
    sex: str | None = None
    pincode: str | None = None


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = None
    age: int | None = None
    sex: str | None = None
    pincode: str | None = None


class FamilyGroupResponse(BaseModel):
    id: str


class FamilyInviteCreateRequest(BaseModel):
    invitee_username: str


class FamilyInviteResponse(BaseModel):
    id: str
    family_group_id: str
    inviter_user_id: str
    invitee_user_id: str
    status: str


class ConsentUpsertRequest(BaseModel):
    category: str
    scope: str
    granted: bool


class ConsentResponse(BaseModel):
    id: str
    user_id: str
    category: str
    scope: str
    version: int
    granted: bool


class ExportResponse(BaseModel):
    profile: ProfileResponse


class AnalyticsEventResponse(BaseModel):
    id: str
    event_type: str


class AuditLogResponse(BaseModel):
    id: str
    actor_user_id: str | None
    action: str
    entity_type: str
    entity_id: str | None
    ip: str | None
    device_id: str | None
    ts: str
    prev_hash: str | None
    entry_hash: str


class AuditVerifyResponse(BaseModel):
    ok: bool


# ------------------------------
# Sync contract (Phase 2)
# ------------------------------


class SyncEventEnvelope(BaseModel):
    event_id: str
    device_id: str
    user_id: str
    entity_type: str
    operation: str
    client_time: str
    payload: dict


class SyncBatchRequest(BaseModel):
    events: list[SyncEventEnvelope]


class SyncEventResult(BaseModel):
    event_id: str
    status: str  # accepted|duplicate|rejected
    error: str | None = None


class SyncBatchResponse(BaseModel):
    results: list[SyncEventResult]


# ------------------------------
# Triage (Phase 3.1)
# ------------------------------


class TriageSessionCreate(BaseModel):
    symptom_text: str
    followup_answers: dict = {}


class TriageSessionResponse(BaseModel):
    id: str
    user_id: str
    symptom_text: str
    followup_answers: dict
    triage_category: str
    red_flags: list[str]
    guidance_text: str
    created_at: str


# ------------------------------
# TeleSahay (Phase 3.2)
# ------------------------------


class TeleRequestCreate(BaseModel):
    symptom_summary: str
    preferred_time: str | None = None


class TeleRequestUpdateStatus(BaseModel):
    status: str


class TeleRequestResponse(BaseModel):
    id: str
    user_id: str
    symptom_summary: str
    preferred_time: str | None
    status: str
    created_at: str


class PrescriptionCreate(BaseModel):
    user_id: str
    items: list[dict]  # e.g., [{"drug": "...", "dose": "..."}]
    advice: str | None = None


class PrescriptionResponse(BaseModel):
    id: str
    user_id: str
    clinician_user_id: str
    items: list[dict]
    summary_text: str
    created_at: str


# ------------------------------
# DailySahay (Phase 3.3)
# ------------------------------


class VitalsCreate(BaseModel):
    type: str
    value: str
    unit: str
    measured_at: str


class FoodLogCreate(BaseModel):
    description: str
    calories: int | None = None
    logged_at: str


class SleepLogCreate(BaseModel):
    duration_minutes: int
    quality: str | None = None
    logged_at: str


class WaterLogCreate(BaseModel):
    amount_ml: int
    logged_at: str


class MoodLogCreate(BaseModel):
    mood_scale: int
    notes: str | None = None
    logged_at: str


class MedicationPlanCreate(BaseModel):
    name: str
    schedule: dict
    start_date: str
    end_date: str | None = None


class AdherenceEventCreate(BaseModel):
    medication_plan_id: str
    taken_at: str
    status: str


class DailySummaryResponse(BaseModel):
    date: str
    water_total_ml: int
    food_total_calories: int
    sleep_total_minutes: int
    mood_avg: float | None
    vitals_count: int


# ------------------------------
# VaxTrack + BalVikas (Phase 3.4)
# ------------------------------


class VaccinationRecordCreate(BaseModel):
    vaccine_name: str
    dose_number: int
    administered_at: str


class GrowthRecordCreate(BaseModel):
    height_cm: float | None = None
    weight_kg: float | None = None
    recorded_at: str


class NextDueVaccineResponse(BaseModel):
    vaccine_name: str
    dose_number: int
    due_date: str
    overdue: bool


class MilestoneResponse(BaseModel):
    age_months: int
    description: str
