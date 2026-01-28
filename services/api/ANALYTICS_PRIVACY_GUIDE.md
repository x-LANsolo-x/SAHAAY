# Analytics Event Generation - Privacy & Security Guide (Phase 7.1)

## Overview

This document describes the privacy-preserving analytics system for GovSahay dashboards. The system implements **strict de-identification** with multiple privacy guarantees to enable public health analytics while protecting individual privacy.

## Privacy Guarantees

### 1. **Explicit Consent Required**
- All analytics generation requires explicit user consent
- Consent category: `analytics`
- Consent scope: `gov_aggregated`
- Users can revoke consent at any time (immediate effect)

### 2. **Strict De-identification**
All analytics events undergo mandatory de-identification before storage:

#### **DISALLOWED Fields** (Never stored in analytics)
- `user_id`, `username` (stored separately for audit only)
- `phone`, `email`
- `complaint_id` (use cohort_id instead)
- Exact GPS coordinates (lat/lng)
- Free-text comments
- Evidence filenames or URLs
- Any other direct identifiers

#### **ALLOWED Fields** (Aggregated/Bucketed)
- `event_type` - Pre-defined event types only
- `event_time` - Rounded to 15-minute buckets
- `age_bucket` - Age ranges (0-5, 6-12, 13-18, 19-35, 36-60, 60+)
- `gender` - Male/Female/Other/Unknown
- `geo_cell` - Coarse geographic regions (H3 cells or district-level)
- `category` - Pre-defined categories only
- `count` - Always aggregate
- `metadata` - PII-free structured data only

### 3. **Time Bucketing**
All event times are rounded to **15-minute intervals** to prevent temporal re-identification:
- Event at 10:07:30 → Stored as 10:00:00
- Event at 10:14:59 → Stored as 10:00:00
- Event at 10:15:00 → Stored as 10:15:00

### 4. **Age Bucketing**
Exact ages are converted to broad ranges:
- 0-5 years
- 6-12 years
- 13-18 years
- 19-35 years
- 36-60 years
- 60+ years
- Unknown (if not provided)

### 5. **Geographic Aggregation**
Locations are aggregated to prevent address-level identification:

**Current Implementation (MVP):**
- Pincode → District-level (first 3 digits): `110001` → `pincode_110xxx`

**Production (Future):**
- Use H3 hexagonal grid at resolution 7 (~5km hexagons)
- Prevents exact location inference

### 6. **k-Anonymity Threshold**
All aggregated reports enforce a minimum count threshold:
- **Threshold**: 5 events minimum
- Aggregates with < 5 events are **hidden** from reports
- Prevents individual-level inference from small groups

### 7. **Schema Validation**
Only pre-approved event types and categories are accepted:

**Allowed Event Types:**
- `triage_completed`
- `triage_emergency`
- `complaint_submitted`
- `complaint_resolved`
- `complaint_escalated`
- `vaccination_recorded`
- `neuroscreen_completed`
- `daily_wellness_logged`
- `tele_request_created`
- `tele_consultation_completed`

**Allowed Categories:**
- Triage: `self_care`, `phc`, `emergency`
- Complaints: `service_quality`, `staff_behavior`, `facility_issues`, `medication_error`, `billing_dispute`, `discrimination`, `other`
- NeuroScreen: `low`, `medium`, `high`

### 8. **Metadata Filtering**
Custom metadata is automatically rejected if it contains disallowed PII fields:
- Rejected keys: `user_id`, `username`, `phone`, `email`, `complaint_id`, `full_name`, `name`, `address`, `gps`, `latitude`, `longitude`, `evidence`, `filename`, `url`, `comment`, `text`, `description`

---

## API Reference

### Generate Analytics Event

**Endpoint:** `POST /analytics/events`

**Authentication:** Required (Bearer token)

**Consent Required:** `analytics` + `gov_aggregated`

**Request Body:**
```json
{
  "event_type": "triage_completed",
  "category": "self_care",
  "metadata": {
    "has_red_flags": false
  }
}
```

**Response:** (200 OK)
```json
{
  "id": "evt_123",
  "event_type": "triage_completed",
  "payload": {
    "event_type": "triage_completed",
    "event_time": "2024-01-15T10:00:00",
    "age_bucket": "19-35",
    "gender": "F",
    "geo_cell": "pincode_110xxx",
    "category": "self_care",
    "count": 1,
    "metadata": {
      "has_red_flags": false
    },
    "schema_version": "1.0"
  },
  "created_at": "2024-01-15T10:07:30"
}
```

**Note:** `user_id` is stored internally for audit purposes but is **never** included in the payload or analytics queries.

### Get Analytics Summary

**Endpoint:** `GET /analytics/summary`

**Authentication:** Required (Bearer token)

**Query Parameters:**
- `start_date` (optional): ISO 8601 date string
- `end_date` (optional): ISO 8601 date string
- `event_type` (optional): Filter by event type

**Response:** (200 OK)
```json
{
  "summary": [
    {
      "event_type": "triage_completed",
      "category": "self_care",
      "count": 127,
      "unique_geo_cells": 8,
      "unique_age_buckets": 5
    },
    {
      "event_type": "complaint_submitted",
      "category": "service_quality",
      "count": 34,
      "unique_geo_cells": 12,
      "unique_age_buckets": 4
    }
  ],
  "total_events": 161,
  "privacy_threshold": 5,
  "note": "Only showing aggregates with >= 5 events (k-anonymity)"
}
```

**Note:** Only aggregates with ≥ 5 events are returned. Smaller groups are hidden to prevent re-identification.

---

## Integration Patterns

### Automatic Analytics from Business Logic

The system provides helper functions for automatic analytics generation from key events:

#### Triage Analytics
```python
from services.api.analytics import emit_triage_analytics

# After triage completion
emit_triage_analytics(
    db=db,
    user_id=user.id,
    triage_category="emergency",
    has_red_flags=True,
)
```

#### Complaint Analytics
```python
from services.api.analytics import emit_complaint_analytics

# After complaint submission
emit_complaint_analytics(
    db=db,
    user_id=user.id,  # None for anonymous
    event_type="complaint_submitted",
    complaint_category="service_quality",
    escalation_level=1,
)
```

#### Vaccination Analytics
```python
from services.api.analytics import emit_vaccination_analytics

# After vaccination record
emit_vaccination_analytics(
    db=db,
    user_id=user.id,
    vaccine_name="DPT",
    dose_number=2,
)
```

#### NeuroScreen Analytics
```python
from services.api.analytics import emit_neuroscreen_analytics

# After NeuroScreen completion
emit_neuroscreen_analytics(
    db=db,
    user_id=user.id,
    band="medium",
)
```

**Note:** All helper functions silently skip analytics if consent is not granted, preventing disruption to main business logic.

---

## Database Schema

### AnalyticsEvent Model

```python
class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: str  # UUID
    user_id: str  # For audit/consent only - NOT for analytics queries
    event_type: str  # Indexed
    payload_json: str  # De-identified payload (see schema)
    created_at: datetime  # Indexed
```

**CRITICAL:** The `user_id` field is for audit and consent tracking ONLY. All analytics queries MUST use `payload_json` which contains de-identified data.

---

## Security Best Practices

### For Developers

1. **Never query analytics by user_id**
   - Use aggregate queries on `payload_json` only
   - Filter by `event_type`, `created_at`, etc.

2. **Always validate metadata**
   - Use `emit_analytics_event()` which validates PII automatically
   - Don't manually construct `AnalyticsEvent` objects

3. **Don't log de-identified payloads with user context**
   - Logging "User X generated event Y" defeats de-identification
   - Log audit events separately

4. **Test privacy guarantees**
   - Run `test_analytics_phase7_1.py` to verify privacy
   - Add tests for new event types

### For Analysts

1. **Never attempt to re-identify individuals**
   - Even if you suspect you know someone's pattern
   - Re-identification is a privacy violation

2. **Respect k-anonymity thresholds**
   - Don't drill down into small aggregates
   - Use broader time/geo ranges if needed

3. **Export only aggregates**
   - Never export individual events
   - Always aggregate before sharing

---

## Compliance & Auditing

### GDPR/Data Protection Compliance

✅ **Consent-based processing**
- Explicit, informed consent required
- Easy revocation (immediate effect)
- Granular consent scopes

✅ **Data minimization**
- Only aggregate data collected
- No direct identifiers stored in analytics

✅ **Purpose limitation**
- Analytics used only for public health dashboards
- Not for individual profiling

✅ **Right to erasure**
- User data deletion removes audit link (user_id)
- Analytics remain (de-identified)

### Audit Trail

All analytics generation is logged in the audit system:
- Action: `analytics.event.generate`
- Entity: `analytics_event`
- Actor: User who generated event (for consent verification)

---

## Future Enhancements (Production)

### Phase 7.2+

1. **True H3 geo-hashing**
   - Add `h3-py` dependency
   - Implement hexagonal grid at multiple resolutions
   - Allow dynamic resolution based on density

2. **Differential Privacy**
   - Add noise to aggregate counts
   - Implement ε-differential privacy guarantees
   - Protect against membership inference

3. **Kafka Integration**
   - Stream events to `analytics.events` topic
   - Real-time aggregation pipeline
   - Separate analytics DB (ClickHouse)

4. **Advanced k-anonymity**
   - l-diversity (multiple sensitive attributes)
   - t-closeness (distribution matching)
   - Dynamic threshold based on sensitivity

5. **Federated Analytics**
   - State-level aggregation
   - National-level rollups
   - Privacy-preserving cross-state queries

---

## Testing

Run the complete test suite:

```bash
cd services/api
python -m pytest tests/test_analytics_phase7_1.py -v
```

**Test Coverage:**
- ✅ Consent requirements
- ✅ Schema validation
- ✅ De-identification enforcement
- ✅ Time bucketing accuracy
- ✅ Age bucketing accuracy
- ✅ Geographic aggregation
- ✅ PII rejection
- ✅ k-anonymity thresholds
- ✅ Edge cases (missing profile, etc.)

---

## Troubleshooting

### "Consent not granted" error
**Solution:** User must grant `analytics` + `gov_aggregated` consent via `/consents` endpoint.

### "Invalid event_type" error
**Solution:** Check `AnalyticsEventSchema.ALLOWED_EVENT_TYPES` for valid types. Add new types only after privacy review.

### "Disallowed PII field" error
**Solution:** Remove PII fields from metadata. Use aggregate/bucketed values only.

### Analytics not appearing in summary
**Solution:** Summary requires ≥ 5 events for each aggregate. Generate more events or lower threshold (not recommended for production).

---

## Contact & Support

For privacy concerns or questions about analytics:
- Review: `services/api/analytics.py`
- Tests: `services/api/tests/test_analytics_phase7_1.py`
- Schema: `services/api/models.py` (AnalyticsEvent)

**Remember:** Privacy is not just a feature—it's a fundamental requirement for public health systems.
