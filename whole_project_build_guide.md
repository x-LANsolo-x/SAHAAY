# SAHAY — Complete Build Guide (Free/Open-Source Constraint, Frontend Last)

This guide is designed to help you build the **entire SAHAY vision** (VoiceSahay, DailySahay, Neurodiversity suite, HealthChain, ShikayatChain, GovSahay) under **free / open-source constraints**, while intentionally **deferring frontend implementation until the end**.

> Key idea: build a **backend-first, API-first, event-driven platform** with a local-first sync contract and robust testing. Then any frontend (React Native / Next.js) becomes an integration layer—not the foundation.

---

## 0) Constraints, assumptions, and guiding decisions

### 0.1 “Free constraint” definition used here
This guide assumes:
- Prefer **open-source** software for infra and libraries.
- Prefer **self-hosted** components over paid managed services.
- Avoid paid telephony providers (Twilio/Exotel) until later.
- Avoid paid LLM APIs; use **local/self-hosted** models or deterministic logic until you can fund hosted AI.

This does **not** mean you cannot ever integrate paid services—only that the baseline plan works without them.

### 0.2 Recommended baseline stack (free-first, production-lean)
You can run the entire stack on a laptop for dev and on a small server later.

**Backend services**
- API: **FastAPI** (Python)
- Worker jobs: **Celery** (with Redis) or pure async tasks
- Auth: **Keycloak** (open-source) or FastAPI JWT (simpler early)

**Datastores**
- Relational core: **PostgreSQL**
- Time-series vitals: **TimescaleDB** extension on Postgres (free)
- Analytics: start with Postgres materialized views; later add **ClickHouse**
- Object storage (self-host): **MinIO** (S3-compatible)

**Eventing**
- Start: Postgres outbox pattern (simple)
- Scale: **Kafka** or **Redpanda** later

**Voice/IVR**
- Free-first: **Asterisk** (self-host PBX) + simple IVR scripts
- Alternative: GSM gateway (hardware) if you have it; otherwise keep voice as a later integration

**AI/ML**
- Triage rules engine (deterministic) + later add:
- Local LLM inference: **Ollama** (Llama family) or **vLLM** (GPU if available)
- STT: **Whisper.cpp** local
- TTS: **Piper TTS** local (quality varies by language)

**Blockchain**
- Dev/local: **Hardhat** local chain
- Free public testnet: Polygon testnet or any EVM testnet (no fiat cost)
- Storage: IPFS via local node (or public gateways—rate-limited)

**Dashboards**
- **Apache Superset** (free) + Map rendering via MapLibre/OpenStreetMap

### 0.3 Build order (frontend last)
1. Platform rails (data model, auth/consent, audit)
2. Sync contract + event pipeline
3. Core health modules APIs (triage, teleconsult, wellness tracking)
4. Neurodiversity APIs + content packs
5. Complaints workflow (off-chain)
6. Blockchain anchoring (hash-only) + SLA contracts
7. Analytics pipeline + GovSahay APIs
8. Frontend apps (mobile + web) integrating stable APIs

---

## 1) Global “Definition of Done” (DoD) and Quality Gates

Every phase must meet these before moving on.

### 1.1 DoD checklist (for any feature)
- [ ] API spec written (OpenAPI + examples)
- [ ] Data model migration created
- [ ] Unit tests for core logic
- [ ] Integration tests for API endpoints
- [ ] Security checks: auth, RBAC, input validation
- [ ] Observability: logs + metrics added
- [ ] Failure handling + retries documented
- [ ] Minimal documentation: how to run and test locally

### 1.2 Test levels (always use all applicable)
- **Unit**: pure functions (rules, validators)
- **API integration**: FastAPI TestClient
- **Contract tests**: ensure payload schemas stable
- **E2E (backend-only)**: simulate flows across services
- **Load**: basic Locust/k6 for ingestion endpoints
- **Security**: OWASP basics, auth bypass attempts

---

## 2) Phase-by-phase build plan (with intensive testing after every step)

### Phase 0 — Workspace setup & CI (Week 0)
**Goal:** reproducible environment and a safe path to change.

#### Step 0.1 — Monorepo + service skeleton
- Create folders: `services/api`, `services/worker`, `infra/`, `docs/` (optional), `tests/`
- Add Docker Compose for: Postgres, Redis, MinIO, Keycloak (optional)

**Intensive testing gate**
- [ ] `docker compose up` starts all dependencies
- [ ] API service boots and responds to `/health`
- [ ] CI runs unit tests + lints

#### Step 0.2 — OpenAPI-first approach
- Enable OpenAPI docs in FastAPI
- Add `/version` endpoint

**Intensive testing gate**
- [ ] OpenAPI renders
- [ ] Example requests validate

---

### Phase 1 — Identity, Consent, RBAC, Audit (Weeks 1–2)
**Goal:** everything is secured and consent-aware before any health data grows.

#### Step 1.1 — Core identity model
- Tables:
  - `users` (internal)
  - `profiles` (citizen profile)
  - `family_groups` + `family_members`
  - `roles` / `user_roles`

**Intensive testing gate**
- [ ] Cannot read other user’s profile
- [ ] Family linking only via invitation/approval

#### Step 1.2 — Consent receipts
- Table `consents` with:
  - data categories (tracking, neuro, complaints, analytics)
  - scope (share with clinician/ASHA/gov aggregated)
  - versioning and timestamps

**Intensive testing gate**
- [ ] Revoking consent blocks export endpoints immediately
- [ ] Consent is required for analytics events generation

#### Step 1.3 — Audit logging
- Table `audit_log` capturing:
  - actor, action, entity type/id, timestamp, IP/device

**Intensive testing gate**
- [ ] Every write endpoint creates an audit record
- [ ] Tampering attempt detectable (append-only rules)

---

### Phase 2 — Offline-first Sync Contract (Weeks 2–4)
**Goal:** define how any client (future frontend) will work offline.

#### Step 2.1 — Define event schemas (the “sync contract”)
- Standard envelope:
  - `event_id`, `device_id`, `user_id`, `entity_type`, `operation`, `client_time`, `payload`
- Operations: CREATE/UPDATE/DELETE

**Intensive testing gate**
- [ ] JSON schema validation for events
- [ ] Reject unknown entity types

#### Step 2.2 — Implement Sync Gateway API
- `POST /sync/events:batch`
- Idempotency: ignore duplicates by `event_id`
- Store events (raw) in `sync_events` for traceability

**Intensive testing gate**
- [ ] Sending the same batch twice does not duplicate results
- [ ] Partial failures return per-item errors

#### Step 2.3 — Conflict resolution rules
- Append-only logs (vitals/mood/water) never overwrite
- Profile fields: last-write-wins with audit

**Intensive testing gate**
- [ ] Two “devices” editing profile yields deterministic final state + audit trail
- [ ] Append-only entities never lose data

---

### Phase 3 — Core Health APIs (Weeks 4–8)
**Goal:** backend implements real SAHAY capabilities, even before UI.

#### Step 3.1 — Triage sessions (VoiceSahay core)
- Endpoints:
  - `POST /triage/sessions`
  - `GET /triage/sessions/{id}`
- Store: symptom text, follow-up answers, triage output

**Intensive testing gate**
- [ ] Red-flag rules always produce EMERGENCY
- [ ] No endpoint returns medical diagnosis language

#### Step 3.2 — TeleSahay basics
- Endpoints:
  - `POST /tele/requests`
  - `PATCH /tele/requests/{id}` status
  - `POST /prescriptions`
- SMS: free-first fallback is "message queue" (store messages in DB)

**Intensive testing gate**
- [ ] Prescription cannot be created without clinician role
- [ ] Prescription summary renders under 160–300 chars (SMS-friendly)

#### Step 3.3 — DailySahay data model (backend)
- Entities:
  - `vitals_measurements` (Timescale)
  - `food_logs`, `sleep_logs`, `water_logs`, `mood_logs`
  - `medication_plans`, `adherence_events`

**Intensive testing gate**
- [ ] Time-series inserts scale (load test 10k inserts)
- [ ] Aggregation queries return correct daily summaries

#### Step 3.4 — VaxTrack + BalVikas basics
- Vaccine schedule rules stored per age
- Growth/milestones table

**Intensive testing gate**
- [ ] Next due vaccine computed correctly
- [ ] Edge cases: missing DOB, late vaccines

---

### Phase 4 — Neurodiversity Suite APIs (Weeks 8–14)
**Goal:** backend supports screening, therapy plans, and AAC content delivery.

#### Step 4.1 — NeuroScreen results
- Store questionnaire + scoring version
- Output: likelihood band + referral guidance

**Intensive testing gate**
- [ ] Versioned scoring: old results remain reproducible
- [ ] Results labeled as screening, not diagnosis

#### Step 4.2 — TherapyHome content packs
- Store content metadata (modules, steps)
- Serve zipped “offline packs” via MinIO

**Intensive testing gate**
- [ ] Content pack checksum verification
- [ ] Permission checks: only authorized caregivers/ASHAs

#### Step 4.3 — CommBridge (AAC) resources
- Symbol set metadata + phraseboards

**Intensive testing gate**
- [ ] Large payload performance test

---

### Phase 5 — ShikayatChain (Complaints) Off-chain Workflow (Weeks 14–18)
**Goal:** full complaint lifecycle and SLA enforcement without blockchain.

#### Step 5.1 — Complaint intake
- Endpoint `POST /complaints`
- Evidence uploads to MinIO (encrypted object keys)

**Intensive testing gate**
- [ ] Evidence upload works with resume/retry
- [ ] Anonymous complaints do not expose identity in responses/logs

#### Step 5.2 — SLA timers + escalation
- Background job checks overdue complaints
- Escalation rules district→state→national

**Intensive testing gate**
- [ ] Simulate time passing; overdue complaints escalate automatically
- [ ] No manual action needed to escalate

#### Step 5.3 — Closure & feedback
- Cannot close without feedback field set

**Intensive testing gate**
- [ ] Closure blocked without feedback

---

### Phase 6 — Blockchain Anchoring (Weeks 18–24)
**Goal:** immutability: store **hashes only** on-chain; keep PII off-chain.

#### Step 6.1 — Choose on-chain data policy
- On-chain: complaint hash, timestamps, SLA params, status hash
- Off-chain: full content (encrypted)

**Intensive testing gate**
- [ ] Static check: no PII fields included in contract calls

#### Step 6.2 — Smart contracts (Hardhat)
- `createComplaintAnchor()`
- `updateStatusAnchor()`

**Intensive testing gate**
- [ ] Unit tests for contract state transitions
- [ ] Replay attacks prevented (nonce/event id)

#### Step 6.3 — Anchor service integration
- Backend signs and submits tx (later move to multisig)

**Intensive testing gate**
- [ ] If chain fails, off-chain workflow still works (graceful degradation)

---

### Phase 7 — GovSahay Analytics (Weeks 24–32)
**Goal:** de-identified dashboards and heatmaps.

#### Step 7.1 — Analytics event generation
- Emit events only with consent
- Remove direct identifiers; aggregate by geo/time

**Intensive testing gate**
- [ ] Consent revoked → no analytics events
- [ ] Re-identification risk checks (k-threshold)

#### Step 7.2 — Storage and dashboards
- Start with Postgres materialized views
- Later: ClickHouse for faster OLAP
- Superset dashboards; MapLibre maps

**Intensive testing gate**
- [ ] Freshness SLO test (e.g., <15 min pilot)
- [ ] Dashboard queries P95 <2s on pilot dataset

#### Step 7.3 — OutbreakSense (baseline)
- Start with anomaly detection over triage counts
- Later add ML models

**Intensive testing gate**
- [ ] Backtest on historical-like synthetic data
- [ ] False alert rate monitored

---

### Phase 8 — Frontend (Weeks 32+; implement last as requested)
**Goal:** build mobile/web clients against stable APIs.

#### Step 8.1 — API client SDK first
- Generate typed SDK from OpenAPI

**Intensive testing gate**
- [ ] Contract tests: SDK matches backend OpenAPI

#### Step 8.2 — React Native citizen + ASHA mode
- Offline local DB + sync queue
- Accessibility features (calm mode, dyslexia font)

**Intensive testing gate**
- [ ] 7-day offline simulation
- [ ] Sync conflict tests
- [ ] Accessibility checks

#### Step 8.3 — Next.js GovSahay UI (if not already)

**Intensive testing gate**
- [ ] RBAC enforcement
- [ ] P95 dashboard render time acceptable

---

## 3) Free-first VoiceSahay strategy (realistic)
Voice is hard to do “free” at scale. Here’s the practical plan:

1) Build **triage APIs** and session handling first (Phase 3).
2) For voice in development:
   - Use recorded audio uploads + Whisper.cpp locally
3) For real calls later:
   - Self-host **Asterisk** and integrate SIP trunks (may cost money)
   - Or integrate Twilio/Exotel when budget exists

Testing emphasis: make voice just an **adapter** into the same triage session API.

---

## 4) Security & privacy checklist (must not be postponed)
- Data classification: PII vs health data vs analytics
- Encryption at rest for attachments (MinIO SSE + app-level encryption)
- TLS in transit
- RBAC everywhere
- Audit logs for write actions
- No PII on-chain

**Intensive testing (security regression)**
- [ ] Auth bypass tests
- [ ] Role escalation tests
- [ ] Broken object-level authorization tests
- [ ] Sensitive logs scan

---

## 5) Practical milestone plan (so it doesn’t take forever)
If you are solo, the above phases are large. Use vertical slices to keep momentum:

### Milestone A (first shippable backend)
- Phase 1 + Phase 2 + Step 3.1
- Result: secure platform + offline sync contract + triage sessions

### Milestone B (wellness tracking backend)
- Step 3.3 + basic summaries

### Milestone C (complaints lifecycle off-chain)
- Phase 5 complete

### Milestone D (gov analytics v1)
- Phase 7.1 + 7.2 minimal

Then add neuro + blockchain + final frontend.

---

## 6) What you should do next (immediate next steps)
1) Confirm the exact meaning of “free” for you:
   - Are you okay with **free tiers** of hosted services, or strictly self-hosted only?
2) Decide if you want **Keycloak** (more setup but real RBAC) or **simple JWT** initially.
3) Decide if you want **Kafka now** or start with Postgres outbox.

If you answer these, I can rewrite this guide into a **dated week-by-week plan** with exact deliverables and a test plan per week.
