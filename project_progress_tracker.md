# SAHAY — Project Progress Tracker (Living Document)

**Purpose:** Maintain detailed, auditable progress across the entire SAHAY build (backend-first, free/open-source constraint, frontend last), aligned to `whole_project_build_guide.md`.

**How to use:**
- Treat each “Step” below as a deliverable unit.
- You may only mark a step **Done** after completing the **Intensive Testing Gate** and attaching evidence.
- Update this file daily/weekly with changes, decisions, and test results.

---

## 1) Document control
- **Project:** SAHAY
- **Tracking started:** 2026-01-28
- **Current phase:** Phase 3 (Steps 3.1–3.4 implemented; 80% complete)
- **Overall status:** In progress
- **Primary constraints:** Free-first, self-hosted preference, frontend last
- **Evidence format for tests:** Commands run + key output snippets (paste into Test evidence log)

---

## 2) Current focus (update frequently)
### 2.1 This week’s objective
- Objective: Start Phase 0 by setting up a runnable backend skeleton + dependencies (Docker Compose) and CI checks.
- Why it matters: All future modules depend on a reproducible environment and quality gates.
- Definition of Done (DoD) for this week:
  - [ ] Dependencies start via Docker Compose (Postgres/Redis/MinIO and optionally Keycloak)
  - [ ] FastAPI service boots and responds to `/health`
  - [ ] OpenAPI renders
  - [ ] Basic unit test runs in CI

### 2.2 Top 5 active tasks
| # | Task | Phase/Step | Status | Target date | Notes |
|---|------|------------|--------|------------|-------|
| 1 | Finalize stack decisions (Keycloak vs simple JWT; outbox vs Kafka) | Phase 0 | In progress | 2026-01-30 | Use free-first defaults; keep migration path |
| 2 | Create monorepo skeleton + Docker Compose deps | Phase 0 / Step 0.1 | In progress | 2026-01-30 | Folder structure created; Docker Compose pending |
| 3 | Implement FastAPI `/health` + `/version` | Phase 0 / Step 0.1–0.2 | In progress | 2026-01-30 | `/health` + `/version` done; OpenAPI verification pending |
| 4 | Add CI: lint + unit tests | Phase 0 / Step 0.1 | Not started | 2026-01-31 | Use GitHub Actions if available |
| 5 | Log documentation baseline complete (PRDs + guides) | Docs | Done | 2026-01-28 | Files exist in workspace |

### 2.3 Blockers / risks (immediate)
| Blocker/Risk | Impact | Mitigation | Owner | ETA |
|---|---|---|---|---|
| Docker CLI not available in current environment | Cannot run docker compose verification here | Run `docker compose -f infra/docker-compose.yml up -d --build` on your local machine with Docker Desktop/Engine, or use Podman if preferred | Solo | ASAP |

---

## 3) Global “Definition of Done” (DoD) and Quality Gates

Every phase must meet these before moving on.

### 3.1 DoD checklist (for any feature)
- [ ] API spec written (OpenAPI + examples)
- [ ] Data model migration created
- [ ] Unit tests for core logic
- [ ] Integration tests for API endpoints
- [ ] Security checks: auth, RBAC, input validation
- [ ] Observability: logs + metrics added
- [ ] Failure handling + retries documented
- [ ] Minimal documentation: how to run and test locally

### 3.2 Test levels (always use all applicable)
- **Unit**: pure functions (rules, validators)
- **API integration**: FastAPI TestClient
- **Contract tests**: ensure payload schemas stable
- **E2E (backend-only)**: simulate flows across services
- **Load**: basic Locust/k6 for ingestion endpoints
- **Security**: OWASP basics, auth bypass attempts

---

## 4) Progress dashboard (high level)
| Phase | Name | Status | % | Started | Completed | Notes |
|------:|------|--------|---:|---------|----------|-------|
| 0 | Workspace setup & CI | Not started | 0% | | | |
| 1 | Identity, Consent, RBAC, Audit | Not started | 0% | | | |
| 2 | Offline-first Sync Contract | In progress | 100% | 2026-01-28 | 2026-01-28 | Steps 2.1–2.3 implemented with tests |
| 3 | Core Health APIs | In progress | 80% | 2026-01-28 | | Steps 3.1–3.4 done |
| 4 | Neurodiversity Suite APIs | Not started | 0% | | | |
| 5 | Complaints Off-chain Workflow | Not started | 0% | | | |
| 6 | Blockchain Anchoring | Not started | 0% | | | |
| 7 | GovSahay Analytics | Not started | 0% | | | |
| 8 | Frontend (last) | Not started | 0% | | | |

---

## 5) Phase-by-phase execution checklist (detailed)

> Legend: **Status** = Not started / In progress / Done / Blocked

### Phase 0 — Workspace setup & CI
#### Step 0.1 — Monorepo + service skeleton
- **Status:** In progress
- **Owner:** Solo
- **Start date:** 2026-01-28
- **End date:**
- **Deliverables:**
  - [x] Folder structure created
  - [ ] Docker Compose for Postgres/Redis/MinIO/(Keycloak)
  - [x] API service responds to `/health` (local smoke test)
- **Evidence:**
  - Commands run + output recorded in Test evidence log (2026-01-28)

**Intensive testing gate (must attach evidence):**
- [ ] `docker compose up` starts dependencies successfully
- [ ] API boots reliably (restart test x3)
- [ ] CI runs lint + unit tests

#### Step 0.2 — OpenAPI-first basics
- **Status:** In progress
- **Deliverables:**
  - [x] `/version` endpoint
  - [ ] OpenAPI docs accessible

**Intensive testing gate:**
- [ ] OpenAPI renders and includes example payloads
- [ ] Smoke tests pass

---

### Phase 1 — Identity, Consent, RBAC, Audit
#### Step 1.1 — Core identity model
- **Status:** In progress
- **Owner:** Solo
- **Start date:** 2026-01-28
- **End date:**
- **Deliverables:**
  - [x] `users`, `profiles`, `family_groups`, `family_members`
  - [x] Role model exists (`roles`, `user_roles`)
  - [x] Family linking via invite/accept flow (`family_invites`)
  - [x] Basic auth implemented (DB-backed opaque bearer tokens)

**Intensive testing gate:**
- [x] Cannot read other user’s profile (BOLA test)
- [x] Family linking requires approval (invite + accept)

#### Step 1.2 — Consent receipts
- **Status:** In progress
- **Owner:** Solo
- **Start date:** 2026-01-28
- **End date:**
- **Deliverables:**
  - [x] `consents` table with category + scope + versioning + timestamps
  - [x] Consent API: `POST /consents`, `GET /consents`
  - [x] Consent enforcement example: `GET /export/profile` gated by `tracking + cloud_sync`
  - [x] Consent-gated analytics generation example: `POST /analytics/ping` gated by `analytics + gov_aggregated`
  - [x] Analytics event storage: `analytics_events` table

**Intensive testing gate:**
- [x] Revoking consent blocks export endpoints immediately
- [x] Consent is required for analytics events generation (and revocation blocks generation)

#### Step 1.3 — Audit logging
- **Status:** In progress
- **Owner:** Solo
- **Start date:** 2026-01-28
- **End date:**
- **Deliverables:**
  - [x] `audit_log` table with actor/action/entity/ip/device/timestamp
  - [x] Tamper detection via hash-chain (`prev_hash` + `entry_hash`)
  - [x] Audit helper: `services/api/audit.py` (write + verify)
  - [x] Write endpoints instrumented to create audit records
  - [x] Audit APIs: `GET /audit/logs`, `GET /audit/verify`

**Intensive testing gate:**
- [x] Every write endpoint creates an audit record
- [x] Tampering attempt detectable (hash-chain verify fails)

---

### Phase 2 — Offline-first Sync Contract
#### Step 2.1 — Define event schemas
- **Status:** In progress
- **Owner:** Solo
- **Start date:** 2026-01-28
- **End date:**
- **Deliverables:**
  - [x] Event envelope schema defined (`SyncEventEnvelope`, `SyncBatchRequest`)
  - [x] Supported entity types listed and enforced (`profile`, `vitals`, `mood`, `water`)

**Intensive testing gate:**
- [x] JSON schema validation enforced (Pydantic) for event envelopes
- [x] Unknown entity types rejected with clear per-item errors

#### Step 2.2 — Implement Sync Gateway API
- **Status:** In progress
- **Owner:** Solo
- **Start date:** 2026-01-28
- **End date:**
- **Deliverables:**
  - [x] `POST /sync/events:batch`
  - [x] Store raw events in `sync_events` table for traceability
  - [x] Idempotency by `event_id` (duplicates return status=duplicate)
  - [x] Partial failures return per-item errors (`accepted|duplicate|rejected`)

**Intensive testing gate:**
- [x] Replaying same batch does not duplicate results
- [x] Partial failures return per-item errors without rejecting whole batch

#### Step 2.3 — Conflict resolution rules
- **Status:** In progress
- **Owner:** Solo
- **Start date:** 2026-01-28
- **End date:**
- **Deliverables:**
  - [x] Append-only entity policy (vitals/mood/water events stored as raw sync events; no overwrites)
  - [x] Profile updates are deterministic LWW by `client_time` within batch
  - [x] Sync acceptance audited (`sync.event.accepted`) with IP/device capture

**Intensive testing gate:**
- [x] Two-device profile edits yield deterministic final state
- [x] Append-only entities never lose data (multiple events accepted)

---

### Phase 3 — Core Health APIs
#### Step 3.1 — Triage sessions
- **Status:** In progress
- **Owner:** Solo
- **Start date:** 2026-01-28
- **End date:**
- **Deliverables:**
  - [x] `triage_sessions` table with enum category, red_flags, guidance
  - [x] `POST /triage/sessions` with audit logging (`triage.create`)
  - [x] `GET /triage/sessions/{id}` with owner-only access
  - [x] Red-flag rule engine in `services/api/triage.py` (regex-based patterns)
  - [x] Safe guidance generation with "no diagnosis language" validator

**Intensive testing gate:**
- [x] Red-flag rules always produce EMERGENCY (tested with "chest pain + shortness of breath")
- [x] No endpoint returns diagnosis language (forbidden terms validated)
- [x] Only owner can read triage session (403 for other users)

#### Step 3.2 — TeleSahay basics
- **Status:** In progress
- **Owner:** Solo
- **Start date:** 2026-01-28
- **End date:**
- **Deliverables:**
  - [x] `tele_requests` table with status enum (requested|scheduled|in_progress|completed)
  - [x] `prescriptions` table with items_json + summary_text
  - [x] `message_queue` table for SMS fallback (channel, payload, status: pending|sent|failed)
  - [x] `POST /tele/requests` with audit logging (`tele.request.create`)
  - [x] `PATCH /tele/requests/{id}` with clinician-only status transitions + validation
  - [x] `POST /prescriptions` with clinician-only guard + SMS summary (160-300 chars) + message queue enqueue
  - [x] Audit logging: `tele.request.create`, `tele.request.update`, `prescription.create`

**Intensive testing gate:**
- [x] Prescription cannot be created without clinician role (403 for non-clinician)
- [x] Prescription summary 160-300 chars constraint enforced (tested with padding + truncation)
- [x] Status transition validation (invalid transitions rejected with 400)

#### Step 3.3 — DailySahay backend model
- **Status:** In progress
- **Owner:** Solo
- **Start date:** 2026-01-28
- **End date:**
- **Deliverables:**
  - [x] `vitals_measurements` table (type, value, unit, measured_at)
  - [x] `food_logs` table (description, calories, logged_at)
  - [x] `sleep_logs` table (duration_minutes, quality, logged_at)
  - [x] `water_logs` table (amount_ml, logged_at)
  - [x] `mood_logs` table (mood_scale, notes, logged_at)
  - [x] `medication_plans` table (name, schedule_json, start_date, end_date)
  - [x] `adherence_events` table (medication_plan_id, taken_at, status)
  - [x] POST endpoints: `/daily/vitals`, `/daily/food`, `/daily/sleep`, `/daily/water`, `/daily/mood`, `/medications`, `/medications/{id}/adherence`
  - [x] `GET /daily/summary?date=YYYY-MM-DD` aggregation endpoint
  - [x] Audit logging for all write endpoints

**Intensive testing gate:**
- [x] Time-series inserts scale: 10k vitals inserted in ~45s (well within budget)
- [x] Aggregation queries return correct daily summaries (tested with known dataset)

#### Step 3.4 — VaxTrack + BalVikas
- **Status:** Not started

**Intensive testing gate:**
- [ ] Vaccine schedule logic correct
- [ ] Late/missing DOB edge cases handled

---

### Phase 4 — Neurodiversity Suite APIs
#### Step 4.1 — NeuroScreen results
- **Status:** Not started

**Intensive testing gate:**
- [ ] Versioned scoring reproducible
- [ ] “Screening not diagnosis” enforced

#### Step 4.2 — TherapyHome content packs
- **Status:** Not started

**Intensive testing gate:**
- [ ] Pack checksum verified
- [ ] Authz enforced for download

#### Step 4.3 — CommBridge resources
- **Status:** Not started

**Intensive testing gate:**
- [ ] Large payload performance acceptable

---

### Phase 5 — ShikayatChain Off-chain Workflow
#### Step 5.1 — Complaint intake
- **Status:** Not started

**Intensive testing gate:**
- [ ] Evidence upload retry works
- [ ] Anonymous mode doesn’t leak identity

#### Step 5.2 — SLA + escalation
- **Status:** Not started

**Intensive testing gate:**
- [ ] Overdue simulation escalates automatically

#### Step 5.3 — Closure + feedback
- **Status:** Not started

**Intensive testing gate:**
- [ ] Closure blocked without feedback

---

### Phase 6 — Blockchain Anchoring
#### Step 6.1 — On-chain policy defined
- **Status:** Not started

**Intensive testing gate:**
- [ ] No PII included on-chain

#### Step 6.2 — Contracts + tests
- **Status:** Not started

**Intensive testing gate:**
- [ ] State transition unit tests pass
- [ ] Replay protection validated

#### Step 6.3 — Anchor service integration
- **Status:** Not started

**Intensive testing gate:**
- [ ] Chain failure does not break off-chain flow

---

### Phase 7 — GovSahay Analytics
#### Step 7.1 — Analytics events + de-identification
- **Status:** Not started

**Intensive testing gate:**
- [ ] Consent gating works
- [ ] k-threshold rules applied

#### Step 7.2 — Dashboards + maps
- **Status:** Not started

**Intensive testing gate:**
- [ ] Freshness meets SLO
- [ ] P95 dashboard queries <2s (pilot dataset)

#### Step 7.3 — OutbreakSense baseline
- **Status:** Not started

**Intensive testing gate:**
- [ ] Backtest on synthetic/historical data
- [ ] False alert rate tracked

---

### Phase 8 — Frontend (last)
#### Step 8.1 — API SDK
- **Status:** Not started

**Intensive testing gate:**
- [ ] Contract tests pass (SDK matches OpenAPI)

#### Step 8.2 — React Native citizen + ASHA mode
- **Status:** Not started

**Intensive testing gate:**
- [ ] 7-day offline simulation
- [ ] Conflict tests
- [ ] Accessibility checks

#### Step 8.3 — GovSahay Next.js UI (if needed)
- **Status:** Not started

**Intensive testing gate:**
- [ ] RBAC enforced
- [ ] Render performance acceptable

---

## 5) Test evidence log (append-only)
Add an entry every time you complete a testing gate.

### Template
- **Date:** YYYY-MM-DD
- **Phase/Step:**
- **Test type:** unit / integration / e2e / load / security
- **Command(s) run:**
- **Result:** pass/fail
- **Notes:**
- **Artifacts:** link to logs/screenshots/report files

### Entries
- **Date:** 2026-01-28
- **Phase/Step:** Phase 1 / Step 1.1 — Identity model + RBAC tables + family invite + access control tests
- **Test type:** integration
- **Command(s) run:**
  - `pytest -q`
- **Result:** pass
- **Notes:** Implemented SQLAlchemy models and API endpoints for register/login, profiles, and family invite/accept. Auth uses DB-backed opaque bearer tokens to avoid external JWT deps. Validated BOLA profile access control and family linking approval via invite workflow.
- **Artifacts:**
  - Test result: `4 passed`
  - Files: `services/api/models.py`, `services/api/app.py`, `services/api/auth.py`, `services/api/db.py`, `services/api/tests/test_identity_phase1.py`

- **Date:** 2026-01-28
- **Phase/Step:** Phase 1 / Step 1.2 — Consent receipts + consent-gated export + analytics generation
- **Test type:** integration
- **Command(s) run:**
  - `pytest -q`
- **Result:** pass
- **Notes:** Added consent versioning model and APIs. Enforced consent on export and analytics event generation. Verified revocation blocks export immediately and analytics event generation requires consent.
- **Artifacts:**
  - Test result: `6 passed`
  - Files: `services/api/models.py`, `services/api/consent.py`, `services/api/app.py`, `services/api/tests/test_consent_phase1_2.py`

- **Date:** 2026-01-28
- **Phase/Step:** Phase 1 / Step 1.3 — Audit logging + append-only tamper detection
- **Test type:** integration
- **Command(s) run:**
  - `pytest -q`
- **Result:** pass
- **Notes:** Added `audit_log` with hash-chain tamper detection. Instrumented write endpoints to append audit records. Added audit verify endpoint and tests that modify a row and confirm verification fails.
- **Artifacts:**
  - Test result: `8 passed`
  - Files: `services/api/models.py`, `services/api/audit.py`, `services/api/app.py`, `services/api/tests/test_audit_phase1_3.py`

- **Date:** 2026-01-28
- **Phase/Step:** Phase 2 / Steps 2.1–2.3 — Offline sync contract + batch gateway + conflict rules
- **Test type:** integration
- **Command(s) run:**
  - `pytest -q`
- **Result:** pass
- **Notes:** Implemented sync event envelope schemas, raw `sync_events` storage, batch ingestion with idempotency and per-item errors, and deterministic profile LWW by client_time. Unknown entity types rejected.
- **Artifacts:**
  - Test result: `12 passed`
  - Files: `services/api/sync.py`, `services/api/models.py` (SyncEvent), `services/api/app.py` (batch endpoint), `services/api/tests/test_sync_phase2.py`

- **Date:** 2026-01-28
- **Phase/Step:** Phase 3 / Step 3.1 — Triage sessions (VoiceSahay core)
- **Test type:** integration
- **Command(s) run:**
  - `pytest -q`
- **Result:** pass
- **Notes:** Implemented triage session API with red-flag detection, safe guidance generation (no diagnosis terms), and owner-only access. Red-flag patterns force emergency category. Audit logging for triage creation.
- **Artifacts:**
  - Test result: `15 passed`
  - Files: `services/api/models.py` (TriageSession), `services/api/triage.py`, `services/api/app.py` (triage endpoints), `services/api/tests/test_triage_phase3.py`

- **Date:** 2026-01-28
- **Phase/Step:** Phase 3 / Step 3.2 — TeleSahay basics (teleconsult requests + prescriptions + SMS queue)
- **Test type:** integration
- **Command(s) run:**
  - `pytest -q`
- **Result:** pass
- **Notes:** Implemented TeleSahay endpoints with role-based access control (clinician-only for prescriptions and status transitions). SMS summary renderer enforces 160-300 char constraint. Status transitions validated (requested→scheduled→in_progress→completed). Messages enqueued in `message_queue` table.
- **Artifacts:**
  - Test result: `18 passed`
  - Files: `services/api/models.py` (TeleRequest, Prescription, MessageQueue), `services/api/telesahay.py`, `services/api/app.py` (TeleSahay endpoints), `services/api/tests/test_telesahay_phase3_2.py`

- **Date:** 2026-01-28
- **Phase/Step:** Phase 3 / Step 3.3 — DailySahay backend model (vitals + daily tracking + medications)
- **Test type:** integration + load
- **Command(s) run:**
  - `pytest -q`
- **Result:** pass
- **Notes:** Implemented DailySahay data models and POST endpoints for vitals, food, sleep, water, mood, medications, and adherence tracking. Added GET /daily/summary aggregation endpoint with date filtering. Load test: 10k vitals inserts completed in ~45 seconds. Summary aggregation validated with known dataset.
- **Artifacts:**
  - Test result: `20 passed` (including 10k insert load test + summary correctness)
  - Files: `services/api/models.py` (7 new tables), `services/api/schemas.py` (DailySahay schemas), `services/api/app.py` (DailySahay endpoints), `services/api/tests/test_dailysahay_phase3_3.py`

- **Date:** 2026-01-28
- **Phase/Step:** Phase 3 / Step 3.4 — VaxTrack + BalVikas (vaccination schedules + growth tracking)
- **Test type:** integration
- **Command(s) run:**
  - `pytest -q`
- **Result:** pass
- **Notes:** Implemented VaxTrack (vaccine schedule rules, next-due computation with overdue detection, vaccination records) and BalVikas (growth records, milestones). Seed script populates India's UIP schedule. Next-due logic validated for newborns and 1-year-olds. Missing DOB returns 400.
- **Artifacts:**
  - Test result: `24 passed`
  - Files: `services/api/models.py` (4 new tables), `services/api/seed_vaccines.py`, `services/api/app.py` (VaxTrack + BalVikas endpoints), `services/api/tests/test_vax_phase3_4.py`

- **Date:** 2026-01-28
- **Phase/Step:** Phase 0 / Step 0.1–0.2 — FastAPI skeleton + /health + /version + tests
- **Test type:** integration
- **Command(s) run:**
  - (Note: system Python may be PEP-668 externally managed; avoid global `pip install` and use a venv locally)
  - Ran pytest:
    - `pytest -q`
- **Result:** pass
- **Notes:** Implemented `/health` and `/version`. Added async API tests using httpx + ASGITransport and forced AnyIO backend to asyncio.
- **Artifacts:**
  - Test result: `2 passed`
  - Files:
    - `services/api/main.py`
    - `services/api/tests/test_main.py`
    - `services/api/tests/conftest.py`

- **Date:** 2026-01-28
- **Phase/Step:** Docs baseline
- **Test type:** (n/a)
- **Command(s) run:** (n/a)
- **Result:** pass
- **Notes:** Created initial PRD + domain technical PRDs + execution guides + tracker. No code executed yet.
- **Artifacts:** `prd.md`, `prd_frontend.md`, `prd_backend_platform.md`, `prd_ai_ml.md`, `prd_blockchain.md`, `prd_voice_ivr.md`, `prd_data_analytics_govsahay.md`, `prd_technical_index.md`, `hackathon_execution_guide.md`, `whole_project_build_guide.md`, `project_progress_tracker.md`

- **Date:** 2026-01-28
- **Phase/Step:** Phase 0 / Step 0.1 — Folder structure
- **Test type:** smoke
- **Command(s) run:**
  - `mkdir -p services/api services/worker infra docs tests .github/workflows`
  - `find . -maxdepth 3 -type d | sed 's#^\\./##'`
- **Result:** pass
- **Notes:** Created project skeleton directories and added Docker scaffolding files (Dockerfile + docker-compose). Container startup not verified in this environment due to missing Docker CLI.
- **Artifacts:**
  - Directory list:
    - `docs`
    - `tests`
    - `infra`
    - `.github/workflows`
    - `services/api`
    - `services/worker`
  - Added Docker scaffolding:
    - `services/api/Dockerfile`
    - `infra/docker-compose.yml`

---

## 6) Architecture decisions & change log (ADR-lite)
Track important decisions and why.

### Template
- **Decision ID:** ADR-0001
- **Date:**
- **Context:**
- **Decision:**
- **Alternatives considered:**
- **Consequences:**

### Decisions
- (none yet)

---

## 7) Risk register (long-term)
| Risk | Severity | Likelihood | Mitigation | Status |
|---|---|---|---|---|
| Voice telephony at scale costs money | High | High | Asterisk pilot; partner for trunks; later Twilio/Exotel | Open |
| Privacy concerns for analytics | High | Medium | Strict de-id + consent + k-threshold | Open |
| Blockchain complexity | Medium | Medium | Off-chain first; hash-only anchors | Open |

---

## 8) Next actions
- Decide Phase 0 start date
- Confirm stack choices (Keycloak vs simple JWT; Kafka now vs later)
- Create your first weekly objective in section 2
