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
    report_version: str
    profile: ProfileResponse


class AnalyticsEventResponse(BaseModel):
    id: str
    event_type: str


class AnalyticsEventGenerate(BaseModel):
    """Request to generate a de-identified analytics event."""
    event_type: str
    category: str | None = None
    metadata: dict | None = None


class DeidentifiedEventResponse(BaseModel):
    """De-identified analytics event payload (safe for export)."""
    event_type: str
    event_time: str
    age_bucket: str
    gender: str
    geo_cell: str
    category: str
    count: int
    metadata: dict
    schema_version: str


class AnalyticsEventDetailResponse(BaseModel):
    """Full analytics event including de-identified payload."""
    id: str
    event_type: str
    payload: DeidentifiedEventResponse
    created_at: str


class AnalyticsSummaryResponse(BaseModel):
    """Aggregated analytics summary with k-anonymity guarantees."""
    summary: list[dict]
    total_events: int
    privacy_threshold: int
    note: str


# ============================================================
# Dashboard Schemas (Phase 7.2)
# ============================================================

class TimeSeriesDataPoint(BaseModel):
    """Single data point in time series."""
    time: str
    event_type: str
    category: str
    count: int
    unique_geos: int


class TimeSeriesResponse(BaseModel):
    """Time-series data for trend charts."""
    data: list[TimeSeriesDataPoint]
    time_period: dict
    interval: str


class GeoHeatmapPoint(BaseModel):
    """Single point in geo heatmap."""
    geo_cell: str
    event_type: str
    category: str
    count: int
    density: float


class GeoHeatmapResponse(BaseModel):
    """Geo-spatial heatmap data for MapLibre."""
    data: list[GeoHeatmapPoint]
    min_count_threshold: int
    days: int


class CategoryBreakdownItem(BaseModel):
    """Category breakdown item."""
    category: str
    count: int
    percentage: float


class CategoryBreakdownResponse(BaseModel):
    """Category breakdown for pie/bar charts."""
    data: list[CategoryBreakdownItem]
    total: int


class DemographicsBreakdownResponse(BaseModel):
    """Demographics breakdown (age, gender)."""
    age_buckets: list[dict]
    gender: list[dict]


class TopGeoCell(BaseModel):
    """Top geographic region."""
    rank: int
    geo_cell: str
    count: int


class TopGeoCellsResponse(BaseModel):
    """Top geographic regions by event count."""
    data: list[TopGeoCell]
    limit: int
    days: int


class DashboardSummaryResponse(BaseModel):
    """High-level dashboard summary."""
    total_events: int
    unique_geos: int
    event_types: dict
    time_period: dict


# ============================================================
# Outbreak Detection Schemas (Phase 7.3)
# ============================================================

class OutbreakAlertResponse(BaseModel):
    """Single outbreak alert."""
    id: str
    geo_cell: str
    event_time: str
    event_type: str
    category: str | None
    baseline_mean: float
    baseline_std: float
    observed_count: int
    z_score: float
    threshold_sigma: float
    alert_level: str
    confidence: float
    status: str
    acknowledged_by: str | None
    acknowledged_at: str | None
    resolution_notes: str | None
    created_at: str


class OutbreakAlertsListResponse(BaseModel):
    """List of outbreak alerts."""
    alerts: list[OutbreakAlertResponse]
    count: int
    filters: dict


class OutbreakSummaryResponse(BaseModel):
    """Outbreak detection system summary."""
    total_alerts: int
    active_alerts: int
    by_level: dict
    by_status: dict
    top_geo_cells: list[dict]
    false_positive_rate: float
    time_period: dict


class AcknowledgeAlertRequest(BaseModel):
    """Request to acknowledge an alert."""
    alert_id: str
    notes: str | None = None


class ResolveAlertRequest(BaseModel):
    """Request to resolve an alert."""
    alert_id: str
    resolution: str  # 'resolved' or 'false_positive'
    notes: str | None = None


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
    report_version: str
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


# ------------------------------
# NeuroScreen (Phase 4.1)
# ------------------------------


class NeuroscreenResultCreate(BaseModel):
    version_id: str
    responses: dict


class NeuroscreenResultResponse(BaseModel):
    id: str
    user_id: str
    version_id: str
    responses: dict
    raw_score: int
    band: str
    guidance_text: str
    created_at: str


# ------------------------------
# TherapyHome (Phase 4.2)
# ------------------------------


class TherapyStepCreate(BaseModel):
    step_number: int
    title: str
    description: str
    media_references: list[str] | None = None
    duration_minutes: int | None = None


class TherapyStepResponse(BaseModel):
    id: str
    step_number: int
    title: str
    description: str
    media_references: list[str] | None = None
    duration_minutes: int | None = None


class TherapyModuleCreate(BaseModel):
    title: str
    description: str
    module_type: str
    age_range_min: int | None = None
    age_range_max: int | None = None
    steps: list[TherapyStepCreate] = []


class TherapyModuleResponse(BaseModel):
    id: str
    title: str
    description: str
    module_type: str
    age_range_min: int | None = None
    age_range_max: int | None = None
    created_at: str
    steps: list[TherapyStepResponse] = []


class TherapyPackCreate(BaseModel):
    title: str
    description: str
    version: str
    # file_data will be in multipart form


class TherapyPackResponse(BaseModel):
    id: str
    title: str
    description: str
    version: str
    checksum: str
    created_at: str
    module_id: str | None = None


# ------------------------------
# CommBridge AAC (Phase 4.3)
# ------------------------------


class AACSymbolCreate(BaseModel):
    name: str
    image_reference: str
    category: str
    metadata: dict | None = None


class AACSymbolResponse(BaseModel):
    id: str
    name: str
    image_reference: str
    category: str
    metadata: dict | None = None


class AACSymbolSetCreate(BaseModel):
    name: str
    language: str
    version: str
    metadata: dict
    symbols: list[AACSymbolCreate] = []


class AACSymbolSetResponse(BaseModel):
    id: str
    name: str
    language: str
    version: str
    created_at: str
    symbol_count: int = 0


class AACSymbolSetDetailResponse(BaseModel):
    id: str
    name: str
    language: str
    version: str
    created_at: str
    symbols: list[AACSymbolResponse] = []


class AACPhraseboardCreate(BaseModel):
    symbol_set_id: str
    title: str
    phrases: list[dict]


class AACPhraseboardResponse(BaseModel):
    id: str
    symbol_set_id: str
    title: str
    phrases: list[dict]
    created_at: str


# ------------------------------
# ShikayatChain Complaints (Phase 5.1)
# ------------------------------


class ComplaintCreate(BaseModel):
    category: str
    description: str
    contact_info: str | None = None  # For anonymous complaints (will be encrypted)
    is_anonymous: bool = False


class ComplaintEvidenceResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    file_size: int
    checksum: str
    uploaded_at: str
    is_complete: bool


class ComplaintResponse(BaseModel):
    id: str
    category: str
    description: str
    status: str
    current_level: int
    created_at: str
    updated_at: str
    sla_due_at: str | None = None
    resolved_at: str | None = None
    is_anonymous: bool
    evidence: list[ComplaintEvidenceResponse] = []


class ComplaintUpdateStatus(BaseModel):
    status: str
    resolution_notes: str | None = None


class EvidenceUploadInitiate(BaseModel):
    filename: str
    content_type: str
    file_size: int


class EvidenceUploadInitiateResponse(BaseModel):
    evidence_id: str
    upload_url: str | None = None  # Signed URL for direct upload
    upload_id: str | None = None  # For multipart uploads
    chunk_size: int | None = None  # Recommended chunk size for resumable uploads


class EvidenceUploadComplete(BaseModel):
    checksum: str  # Client-computed SHA256


class SLARuleCreate(BaseModel):
    category: str
    escalation_level: int
    time_limit_hours: int


class SLARuleResponse(BaseModel):
    id: str
    category: str
    escalation_level: int
    time_limit_hours: int
    created_at: str


class ComplaintStatusHistoryResponse(BaseModel):
    id: str
    complaint_id: str
    old_status: str | None
    new_status: str
    old_level: int | None
    new_level: int
    changed_by_user_id: str | None
    change_reason: str | None
    is_auto_escalation: bool
    timestamp: str


class ComplaintFeedback(BaseModel):
    rating: int  # 1-5 stars
    comments: str


class ComplaintCloseRequest(BaseModel):
    feedback: ComplaintFeedback
    resolution_notes: str | None = None


# ------------------------------
# Blockchain Anchoring (Phase 6.1)
# ------------------------------


class BlockchainAnchorResponse(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    complaint_hash: str
    status_hash: str | None
    sla_params_hash: str | None
    created_at_timestamp: int
    updated_at_timestamp: int | None
    event_id: str
    blockchain_tx_hash: str | None
    blockchain_block_number: int | None
    blockchain_status: str
    anchor_version: str
    anchored_at: str
    confirmed_at: str | None
