# SAHAY (Hackathon, Solo, 3 Days) — Phased Execution Guide with Intensive Testing

**Constraints assumed:**
- No credit/debit card → **no Twilio/Exotel** provisioning during hackathon.
- You can use **Groq API**.
- Solo developer, 3 days.

**Target demo:**
"VoiceSahay Call Simulator" → FastAPI backend → red-flag safety rules + Groq summarization → **SMS preview** → GovSahay live dashboard updates.

---

## 0) Ground rules (do these first)
### 0.1 Define the single demo story (don’t skip)
- Pick one hero scenario (from your PPT): e.g., mother in rural village.
- Decide exactly what the judge will see in <3 minutes.

**Deliverable:** a 6–10 line demo script.

### 0.2 Choose the fastest stack
- Backend: **FastAPI**
- DB: **SQLite** (hackathon speed)
- UI: **Next.js** (or plain HTML if you’re racing)
- Charts: simple table + counts (optional Chart.js)
- AI: **Groq** LLM with constrained JSON output

### 0.3 Repo structure (recommended)
```
/ (workspace)
  backend/
    app.py
    db.py
    models.py
    services/
      triage_rules.py
      groq_client.py
  web/
    pages/
      index.tsx        # call simulator
      gov.tsx          # dashboard
```

### Intensive tests (Phase 0)
- [ ] You can run backend locally (`uvicorn ...`) without errors.
- [ ] You can open web pages without build errors.
- [ ] You have Groq API key available as env var (never hardcode keys).

---

## Phase 1 (Day 1) — Backend “rails” + minimal end-to-end
**Goal:** A triage session can be created via API, stored, and returned as an SMS preview.

### Step 1.1 — Create DB schema (SQLite)
Create a table for triage sessions.

**Minimum fields:**
- `id` (uuid)
- `created_at` (timestamp)
- `language` (string)
- `age` (int) and/or `age_band`
- `sex` (string)
- `pincode` (string, optional)
- `symptoms_text` (string)
- `risk_level` (enum: `SELF_CARE|PHC|EMERGENCY`)
- `rule_flags` (json/text)
- `llm_json` (json/text)
- `sms_preview` (text)

**Deliverable:** DB migration/init code and a simple insert/select.

#### Intensive tests (after Step 1.1)
- [ ] Create DB from scratch successfully.
- [ ] Insert a record manually (script or REPL) and fetch it.
- [ ] Restart server and confirm record persists.

---

### Step 1.2 — Implement conservative red-flag rule engine
Create `triage_rules.py` with:
- a list of red-flag symptoms (examples):
  - severe breathing difficulty, unconsciousness, chest pain, stroke signs, severe bleeding, seizure, pregnancy bleeding, very high fever with stiff neck, etc.
- rule outputs:
  - `risk_level_suggested`
  - `flags_triggered[]`
  - `safe_next_steps[]` templates

**Deliverable:** `evaluate_rules(symptoms_text, age, sex, pregnancy_flag)`.

#### Intensive tests (after Step 1.2)
Create a small test matrix and run it (manual or automated):
- [ ] Input contains “chest pain + sweating” → EMERGENCY.
- [ ] Input contains “mild cold, runny nose” → not EMERGENCY.
- [ ] Input contains “unconscious” → EMERGENCY.
- [ ] Empty/garbage input → returns safe fallback (ask to seek local help/PHC).
- [ ] Ensure rule engine never returns dangerous advice.

---

### Step 1.3 — Add Groq LLM client (JSON-only output)
Implement `groq_client.py`:
- send a prompt that forces strict JSON schema.
- include: language, symptoms, rule flags, and a directive:
  - "If rule flags include any emergency indicator, output risk_level=EMERGENCY."
- parse JSON with strict validation.
- on failure: fallback to deterministic templates.

**Deliverable:** `groq_triage(symptoms_text, context) -> dict`.

#### Intensive tests (after Step 1.3)
- [ ] Valid JSON returned and parsed.
- [ ] When Groq times out / errors, fallback works.
- [ ] “Prompt injection” attempt ("ignore instructions...") does not break JSON or override emergency rules.
- [ ] Language output matches requested language (at least English + Hindi for demo).

---

### Step 1.4 — Implement `POST /triage`
API request (suggested):
```json
{
  "language": "en",
  "age": 28,
  "sex": "female",
  "pincode": "160036",
  "symptoms_text": "fever for 3 days and cough",
  "pregnancy": false
}
```

API response (suggested):
```json
{
  "triage_id": "...",
  "risk_level": "PHC",
  "next_steps": ["..."],
  "summary_for_doctor": "...",
  "sms_preview": "..."
}
```

**Deliverable:** endpoint returns output and persists session.

#### Intensive tests (after Step 1.4)
- [ ] 10 repeated requests do not duplicate IDs (idempotency optional but nice).
- [ ] Stored record exactly matches response.
- [ ] “EMERGENCY” requests always include emergency next steps.
- [ ] API rejects missing required fields with clear errors.

---

## Phase 2 (Day 1–2) — Call Simulator UI (IVR-like) + proof of value
**Goal:** UI can simulate an IVR call and show SMS preview + receipt.

### Step 2.1 — Build Call Simulator page
UI elements:
- Language selector (English/Hindi)
- Age, sex, pincode
- Symptom text box (optional microphone input later)
- Submit button
- Output cards:
  - risk level
  - next steps
  - SMS preview
  - triage ID

**Deliverable:** `web/pages/index.*` working end-to-end.

#### Intensive tests (after Step 2.1)
- [ ] Submit works even on slow network (loading state).
- [ ] Error states visible (LLM down, API down).
- [ ] Works on mobile viewport.
- [ ] No key leaked to frontend (Groq key stays backend-only).

---

### Step 2.2 — Add a DTMF-style mode (optional but strong)
Mimic IVR prompts with buttons:
- “Press 1: Fever” “Press 2: Cough” etc.
- generate `symptoms_text` from selections.

**Deliverable:** a toggle: Free-text vs IVR-buttons.

#### Intensive tests (after Step 2.2)
- [ ] Each button path generates a consistent symptoms_text.
- [ ] No duplicate/unparseable strings.

---

## Phase 3 (Day 2) — GovSahay mini dashboard (live updates)
**Goal:** A dashboard updates after each triage submission.

### Step 3.1 — Backend aggregation endpoint: `GET /gov/summary`
Return:
- total triages today
- counts by risk
- last 10 triages (timestamp, pincode, risk)
- optional: counts per pincode

**Deliverable:** endpoint + SQL queries.

#### Intensive tests (after Step 3.1)
- [ ] Correct counts after 1, 5, 20 records.
- [ ] Handles empty DB gracefully.
- [ ] Time-window logic correct (today vs last 24h).

---

### Step 3.2 — Dashboard UI page
Display:
- KPI cards (total, emergency, PHC, self-care)
- Recent table
- Optional chart for pincode distribution

**Deliverable:** `web/pages/gov.*`.

#### Intensive tests (after Step 3.2)
- [ ] Refresh shows new record.
- [ ] Auto-refresh every 5–10 seconds (optional) without spamming backend.
- [ ] UI does not break with long text.

---

## Phase 4 (Day 2–3) — Reliability, guardrails, and demo polish
**Goal:** Make it stable enough that nothing breaks on stage.

### Step 4.1 — Strong fallbacks
Backend must never fail the user journey:
- If Groq fails → respond with rule-based triage + generic next steps.
- If DB write fails → return error with retry suggestion.

#### Intensive tests (after Step 4.1)
- [ ] Temporarily disable Groq (wrong key) → system still works.
- [ ] Force DB locked error → graceful response.

---

### Step 4.2 — Observability for hackathon
Add minimal logging:
- request id
- triage id
- time to respond
- groq success/failure

#### Intensive tests (after Step 4.2)
- [ ] Logs show one line per request with timings.
- [ ] No PII printed in logs (avoid full symptoms text).

---

### Step 4.3 — Demo mode
Add 3 preset scenarios as one-click buttons:
- Fever in child (PHC)
- Chest pain (EMERGENCY)
- Mild cold (SELF_CARE)

#### Intensive tests (after Step 4.3)
- [ ] Presets always produce consistent results.
- [ ] Presets cover all risk categories.

---

## Optional Phase 5 (only if time remains) — Complaint receipt + SLA timer (off-chain)
**Goal:** Show accountability without blockchain integration.

### Step 5.1 — `POST /complaint` + receipt ID
Store:
- category
- description
- created_at
- sla_deadline
- status

Return:
- complaint_id
- receipt text

#### Intensive tests
- [ ] SLA deadline computed correctly.
- [ ] Status transitions valid.

### Step 5.2 — Show complaint table on Gov dashboard
- # complaints
- # overdue
- list by status

---

## Stage-ready final checklist (do these before submission)
### Functional
- [ ] Call Simulator: submit → get triage + SMS preview
- [ ] Gov dashboard updates after each submission
- [ ] Demo presets work

### Safety
- [ ] Emergency triggers are conservative
- [ ] App never claims "diagnosis"; always says "guidance/triage"

### Reliability
- [ ] Works when Groq fails
- [ ] Works after server restart

### Pitch alignment
- [ ] One slide: “This simulator is the IVR adapter; production uses Twilio/Exotel”
- [ ] One slide: architecture diagram
- [ ] One slide: roadmap (DailySahay, NeuroScreen, ShikayatChain on-chain)

---

## Suggested prompts (copy/paste template)
### Groq triage prompt (strict JSON)
System:
- You are a clinical triage assistant. You must output ONLY valid JSON matching the schema.
- Never provide a diagnosis.
- If any emergency flag is present, output risk_level="EMERGENCY".

User payload:
- language: {{language}}
- age: {{age}}
- sex: {{sex}}
- pregnancy: {{pregnancy}}
- symptoms_text: {{symptoms_text}}
- rule_flags: {{flags}}

Required JSON schema:
```json
{
  "risk_level": "SELF_CARE|PHC|EMERGENCY",
  "summary_for_doctor": "string",
  "next_steps": ["string"],
  "sms_text": "string"
}
```

---

## What to do next
1) Tell me your preferred stack choice for the UI: **Next.js** or **single HTML page**.
2) If Next.js: tell me if you want **one app** (simulator + dashboard) or two separate pages.
