# Technical PRD — Backend & Platform (SAHAY)

## 1. Scope
Backend platform that powers:
- Citizen apps (mobile/PWA), ASHA tools
- TeleSahay consults + prescriptions
- HealthChain record sync and sharing
- ShikayatChain complaint orchestration
- GovSahay analytics ingestion and APIs

Tech stack targets from deck: **FastAPI**, **Node.js (real-time)**, **Kafka**, **Redis**, **Celery**, **Kubernetes**; DBs: **PostgreSQL**, **MongoDB**, **TimescaleDB**, **ClickHouse**, vector DB (Pinecone).

## 2. Architecture overview
### 2.1 Service boundaries (proposed)
1. **Identity & Consent Service** (profiles, roles, consent receipts)
2. **Sync Gateway** (offline-first event ingestion, conflict handling)
3. **Care/Triage Service** (stores triage sessions; calls AI service)
4. **TeleSahay Service** (appointments, clinician routing, prescriptions)
5. **DailySahay Service** (wellness logs; time-series storage)
6. **Neuro Service** (screening results, therapy plans)
7. **Complaints Orchestrator** (ShikayatChain: routing, SLA timers, escalation)
8. **Facilities Directory Service** (PHCs/hospitals/pharmacies)
9. **GovSahay API** (aggregations, geo queries)
10. **Integration Service** (ABDM, ICDS, NHM, UDID, PM-JAY, DigiLocker/CoWIN as applicable)

### 2.2 Messaging & async
- Kafka topics:
  - `sync.events`
  - `triage.events`
  - `complaints.events`
  - `analytics.events`
  - `integration.jobs`
- Redis for caching and short-lived state (rate limits, session tokens).
- Celery workers for batch processing (exports, notifications, PDF generation).

## 3. Core platform requirements

### 3.1 Identity, auth, roles
**BE-FR-1 Authentication**
- OAuth/JWT per deck; support device-bound sessions.

**BE-FR-2 RBAC**
- Roles: citizen, caregiver, ASHA/Anganwadi, clinician, district_officer, state_officer, national_admin.

**BE-FR-3 Consent receipts**
- Store granular consent with versioning.
- Enforce consent at API gateway (deny exports if revoked).

### 3.2 Offline-first sync
**BE-FR-4 Event ingestion**
- Accept client “events” with idempotency keys.
- Validate schema and quarantine bad payloads.

**BE-FR-5 Conflict resolution**
- Append-only logs: accept all, order by (client_time, server_time).
- Profile edits: last-write-wins with audit.

**BE-FR-6 Sync acknowledgements**
- Provide per-event ack with server-assigned IDs.
- Partial success supported.

### 3.3 Health data storage
- PostgreSQL: identities, consent, prescriptions, complaints metadata.
- TimescaleDB: vitals and time series.
- MongoDB: semi-structured therapy content, drafts.
- ClickHouse: analytics-ready aggregates.

### 3.4 TeleSahay
**BE-FR-7 Appointment lifecycle**
- Request → schedule → in-progress → completed.

**BE-FR-8 Prescription generation**
- Store structured prescription; render as SMS-friendly summary.

### 3.5 Notifications
- SMS and push.
- Templates localized (22 languages).

### 3.6 Directory & geo
- Facility directory with periodic updates.
- Geo queries for nearest resources.

## 4. API surface (high-level)
- `POST /v1/sync/events:batch`
- `GET /v1/profile/me`
- `POST /v1/triage/sessions`
- `POST /v1/tele/requests`
- `POST /v1/prescriptions/{id}/send_sms`
- `POST /v1/complaints`
- `GET /v1/complaints/{id}`
- `GET /v1/gov/heatmaps?metric=...&geo=...`

## 5. Security & compliance
- TLS 1.3; AES-256 at rest.
- DPDP audit logs.
- Data minimization for analytics; separate PII vault.
- Rate limiting for IVR and public endpoints.

## 6. SLOs & NFRs
- 99.9% uptime (pilot), scale to 99.95% (national).
- P95 read latency < 500ms, P99 < 800ms for key endpoints.
- Event ingestion durable with at-least-once processing.

## 7. Deployment & operations
- Kubernetes deployments per service.
- Observability: Prometheus/Grafana, structured logs, distributed tracing.
- Blue/green or canary releases.

## 8. MVP milestones
- Sync gateway + profiles + consent
- Daily vitals logs ingestion
- Basic triage session storage
- Complaint orchestration hooks
- GovSahay basic aggregate APIs
