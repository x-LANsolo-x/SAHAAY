# PRD — SAHAY (Sampoorna Aarogya & Humari Assistance Yojana)

## 1. Document control
- **Product name:** SAHAY — “One Nation, One Health Platform – For Every Mind, Every Body, Every Village”
- **Version:** 1.0 (derived from `team-ZerOne_BuildforBharat.pptx`)
- **Date:** 2026-01-28
- **Authors (from deck):** Team ZerOne (Chandigarh University) — Sahil Dhillon, Armaan Alam, Millee Kesarwani, Kumar Utkarsh
- **Domains:** AI/ML, Healthcare, IoT, Blockchain, Accessibility

## 2. Executive summary
SAHAY is an **AI-powered, offline-first, voice-first, inclusive public health intelligence network** intended to provide a unified platform for:
1) **Universal healthcare access** (including feature phones via IVR),
2) **Daily wellness tracking** for prevention and early detection,
3) **Neurodiversity-native support** (screening → therapy → education → employment pathways),
4) **Blockchain accountability** for healthcare grievances (ShikayatChain), and
5) **Real-time government intelligence** (GovSahay) for data-driven decisions and predictive outbreak analytics.

The core design principle is to eliminate the “**triple exclusion**” highlighted in the deck:
- **Geographic exclusion:** rural distance, weak networks
- **Economic exclusion:** smartphone and data affordability
- **Cognitive exclusion:** literacy barriers and neurodiverse usability

## 3. Problem statement & opportunity
### 3.1 Context scenario (from deck)
A mother in a remote village has a child with fever for 3 days. The nearest doctor is 40 km away. She has **no smartphone, no internet, and limited money**. Existing digital health solutions fail her.

### 3.2 Key crisis metrics (from deck)
- **40 crore** without healthcare access (≈ 1 in 3 can’t see a doctor when sick)
- Rural doctor–patient ratio **1:25,000** vs WHO **1:1,000**
- **3 crore** children with undiagnosed developmental delays
- Autism diagnosis delay: **~7 years** (vs most brain development by age 5)
- **90%** districts lack mental health professionals
- **₹4.5 lakh crore** annual economic loss due to ill health
- **24 lakh** preventable deaths/year
- **65%** can’t use telemedicine (no smartphone/stable internet)

### 3.3 What’s missing today (core gaps)
- No single platform covering **physical + mental + developmental + daily wellness**
- No **offline-capable** system for zero-connectivity regions
- No **voice-first** access for ~30 crore illiterate citizens
- No **neurodiverse-friendly** health technology
- No daily wellness tracking linked to clinical care
- No real-time health data for government decisions; reliance on old/incomplete surveys
- No predictive systems for outbreaks/developmental trends
- Poor integration across Anganwadi, ASHA, PHCs, and hospitals
- No employment pathway layer for persons with disabilities
- No tamper-proof grievance system; complaints get lost

### 3.4 Product thesis
If SAHAY provides **voice-first + offline-first** access plus **frontline-worker enablement** and **real-time government dashboards**, then:
- people can receive **triage and care guidance** without smartphones,
- preventable conditions can be detected earlier via daily tracking,
- neurodiverse children can be screened early and supported continuously,
- grievances can be acted on with **enforced SLAs**,
- governments can allocate resources based on **live, village-level signals**.

## 4. Goals, non-goals, and guiding principles
### 4.1 Goals
1. **Access:** Provide health triage and care pathways to users with **feature phones / low literacy / low connectivity**.
2. **Prevention:** Enable daily wellness tracking and smart alerts for early detection and chronic management.
3. **Neurodiversity:** Reduce screening-to-support delays (targeting months vs years) and provide therapy and life outcomes.
4. **Accountability:** Ensure grievances are immutable, trackable, and escalated if not resolved within SLA.
5. **Intelligence:** Deliver live health data and predictive analytics for district/state/national decisions.

### 4.2 Non-goals (v1/MVP)
- Not a replacement for licensed medical diagnosis. SAHAY provides **triage, guidance, routing**, and supports clinician workflows.
- Not a full EHR replacement; SAHAY will integrate/align with ABDM rather than duplicate everything.
- Not a hardware manufacturer; IoT support is optional/partner-driven.

### 4.3 Guiding principles
- **Offline-first by default:** core flows must work without network.
- **Voice-first access:** all critical functions accessible via IVR/voice.
- **Inclusive & neurodiverse-native:** calm mode, AAC, adaptive UI; minimal cognitive load.
- **Trust by design:** secure identity, clear consent, auditability.
- **Government-ready:** designed for ABDM/ICDS/NHM/UDID/PM-JAY integration.

## 5. Users & personas
### 5.1 Primary personas
1. **Rural citizen on feature phone**
   - Constraints: no smartphone, low literacy, weak signal.
   - Needs: symptom guidance, referral, SMS prescriptions, vaccine reminders.

2. **Low-income smartphone user (intermittent data)**
   - Needs: offline tracking, sync later, affordable consult.

3. **Pregnant woman / mother**
   - Needs: antenatal support, vaccination schedules, child milestone monitoring.

4. **Elderly person + caregiver**
   - Needs: medicine reminders, fall/SOS, family monitoring.

5. **Neurodiverse child’s parent/caregiver**
   - Needs: early screening, therapy routines, school guidance, support network.

6. **Neurodiverse adult**
   - Needs: communication tools (AAC), sensory support, employment matching.

7. **ASHA / Anganwadi worker (frontline)**
   - Needs: offline screening tools, decision support, simple data capture, training.

8. **PHC doctor / telemedicine clinician**
   - Needs: structured triage summary, prior measurements, prescriptions via SMS, referral routing.

9. **District/State/National health official**
   - Needs: heatmaps, vaccination gaps, complaint hotspots, predictive analytics, resource demand.

### 5.2 Key accessibility needs
- Voice in **22 Indian languages**
- Screen readers, dyslexia-friendly fonts (e.g., OpenDyslexic)
- Calm mode / sensory-safe UI
- AAC (symbols, TTS) and visual schedules

## 6. Product scope & modules (from deck)
SAHAY is presented as a **three-layer ecosystem**. For requirements, we treat it as five product “suites”:

1) **Access Suite:** VoiceSahay (IVR), TeleSahay, ASHASahay, VaxTrack, SOS, Locator
2) **Daily Wellness Suite (DailySahay):** VitalTrack, AaharSahay, FitSahay, NeendSahay, JalSahay, MannSahay, NaariSahay, VriddhSahay, BalVikas, DawaiSahay, ParivarSahay, ChronicCare
3) **Neurodiversity Suite:** NeuroScreen, AdaptLearn, TherapyHome, CommBridge, SensoryShield, RoutineBuilder, MeltdownPredict, RozgarSahay, NeuroNetwork, EmpathyTrainer
4) **Trust & Records Suite:** HealthChain (portable tamper-proof records)
5) **Accountability Suite:** ShikayatChain (blockchain complaint system)
6) **Government Suite:** GovSahay dashboard + predictive analytics

> Note: Some suites overlap (e.g., HealthChain supports all modules). This PRD separates them for clarity.

## 7. Key user journeys (end-to-end)
### 7.1 Journey A — Feature phone triage → PHC routing → SMS prescription
**Actor:** Rural citizen (feature phone)
1. User calls **toll-free VoiceSahay**.
2. System greets in regional language; asks consent + basic profile (age/sex/pregnancy/known conditions).
3. Voice symptom capture (free speech) + follow-up questions.
4. Triage outcome: **self-care** vs **PHC visit** vs **emergency**.
5. If PHC/doctor needed:
   - connects to TeleSahay clinician (call) or schedules callback.
6. After consult, system sends **SMS prescription** and care instructions.
7. If connectivity later available, the session syncs to HealthChain/ABDM-linked record.

### 7.2 Journey B — Daily wellness tracking → early risk alert → doctor-ready report
**Actor:** Smartphone user (offline-first)
1. User logs vitals (manual or device), food (voice/photo), sleep, water, mood.
2. On-device model detects trend risk (e.g., high BP pattern).
3. App generates alert + recommended actions.
4. User can generate a “doctor-ready report” and share via QR/PDF/SMS summary.

### 7.3 Journey C — NeuroScreen via ASHA/Anganwadi → therapy at home → school support
**Actor:** ASHA + parent
1. ASHA opens offline NeuroScreen for child.
2. 5-minute screening; results: “low/medium/high likelihood”; guidance generated.
3. Referral pathway: tele-specialist booking for diagnosis.
4. TherapyHome delivers speech/OT/behavior modules with caregiver guidance.
5. RoutineBuilder and SensoryShield support daily function.
6. EmpathyTrainer packages for teachers/school.

### 7.4 Journey D — Complaint filing → blockchain receipt → SLA enforcement → closure feedback
**Actor:** Citizen or ASHA
1. User files complaint via app/IVR/WhatsApp/ASHA.
2. System anchors complaint to blockchain and returns **SMS receipt**.
3. Smart contract routes to authority and starts SLA timer.
4. User sees real-time status updates.
5. If not resolved: auto-escalate District → State → National.
6. Closure requires **mandatory user feedback**.
7. Facility/officer performance score updated.

### 7.5 Journey E — Government sees heatmap + predictive outbreak → allocates resources
**Actor:** District official
1. Opens GovSahay district view.
2. Sees disease and vaccination heatmap + complaint hotspots.
3. Receives OutbreakSense early warning (2–3 weeks).
4. Allocates mobile clinic/medicine stocks; monitors SLA compliance.

## 8. Functional requirements (detailed)
### 8.1 Account, identity, and consent
**FR-1 User profile creation (multi-channel)**
- Create profile via: smartphone app, ASHA-assisted app, IVR.
- Minimal fields for IVR: name/alias, age band, sex, village/pincode, pregnancy status (if applicable), known conditions.
- Support family linking (ParivarSahay).

**FR-2 Consent & privacy controls**
- Explicit consent prompts for:
  - storing health data locally
  - syncing to cloud/government systems when connectivity exists
  - sharing with clinicians/ASHAs
  - using aggregated data for GovSahay (de-identified)

**FR-3 Portable record linkage**
- Support linking to ABDM health ID / verifiable ID when available.

**Acceptance criteria (examples):**
- IVR caller can create a minimal profile in <3 minutes.
- User can revoke data-sharing consent; new exports stop immediately.

### 8.2 VoiceSahay (IVR + voice assistant)
**FR-4 Toll-free IVR access**
- Works on feature phones; no smartphone needed.
- Language selection (22 languages) at entry and remembered.

**FR-5 Voice symptom intake & conversational triage**
- Capture free-form description and ask structured follow-ups.
- Output one of: self-care guidance, PHC referral, emergency escalation.

**FR-6 SMS follow-ups**
- Send SMS with summary, care steps, referral instructions, and ticket IDs.

**FR-7 Safety & escalation**
- For red-flag symptoms, guide to emergency and offer SOS.

**Acceptance criteria:**
- 95% of calls receive a triage category without agent intervention.
- Red-flag flows always provide emergency guidance and nearest facility info (when location known).

### 8.3 TeleSahay (consults + prescriptions)
**FR-8 Doctor connect (call/video where possible)**
- Call-based consult primary; video optional for smartphones.
- Appointment scheduling and callback.

**FR-9 Prescription delivery**
- SMS prescriptions for feature phones.
- For smartphone users, digital prescription stored in profile.

**FR-10 Clinician view**
- Show triage summary, past vitals, medications, allergies (when known).

### 8.4 DailySahay (daily wellness tracking)
**FR-11 VitalTrack**
- Track BP, sugar, heart rate, SpO₂, weight.
- Trends + risk alerts.

**FR-12 AaharSahay**
- Voice/photo food logging.
- Indian diet plans + nutrition insights.

**FR-13 FitSahay / NeendSahay / JalSahay**
- Steps/workouts/yoga reminders and challenges.
- Sleep tracking with smart alarm + habit insights.
- Water goals with weather/activity-aware reminders.

**FR-14 MannSahay (mental wellbeing)**
- Mood tracking, stress check-ins, meditation guidance, anxiety checks.
- SOS for crisis.

**FR-15 NaariSahay / VriddhSahay / BalVikas**
- Women’s health: period/pregnancy/menopause.
- Elderly: medicines, fall detection (where device permits), SOS, family monitoring.
- Child: growth, milestones, vaccines, development alerts.

**FR-16 DawaiSahay**
- Medication reminders.
- Interaction checks (where data available) and generics suggestions.

**FR-17 ParivarSahay**
- Multiple profiles; shared care alerts for caregivers.

**FR-18 ChronicCare**
- Structured programs for diabetes, hypertension, asthma, thyroid, heart.

**Acceptance criteria:**
- All modules function offline; sync occurs automatically when connectivity returns.
- App can generate a shareable health summary report in <30 seconds.

### 8.5 ASHASahay (frontline worker tools)
**FR-19 Offline-first workflow**
- Operates without network for field visits.
- Sync queue with conflict resolution.

**FR-20 Screening + referrals**
- Quick checklists for common conditions; integrate NeuroScreen.
- Referral recommendations and facility locator.

**FR-21 Training**
- 2-hour in-app training (as per deck) with certification.

### 8.6 VaxTrack
**FR-22 Vaccine schedule management**
- Reminders, catch-up plans.
- Store/view certificates where available (e.g., CoWIN integration referenced in deck under scheme integration).

### 8.7 Locator
**FR-23 Nearby facilities**
- PHCs, hospitals, pharmacies, labs.
- Offline cached directory where possible.

### 8.8 SOS
**FR-24 Emergency mode**
- One-tap emergency (smartphone) or IVR quick path.
- Share location and medical history when available.

### 8.9 Neurodiversity Suite
**FR-25 NeuroScreen**
- 5-minute AI screening for autism, ADHD, dyslexia.
- Designed for ASHA/Anganwadi and caregivers.

**FR-26 TherapyHome**
- Guided modules (speech/OT/behavior) with routines.
- Voice/video guidance; offline content packs.

**FR-27 CommBridge (AAC)**
- Symbols + TTS; offline capable.

**FR-28 SensoryShield + RoutineBuilder**
- Calm UI and coping tools.
- Visual schedules and transition support.

**FR-29 MeltdownPredict**
- Early warning signals and caregiver alerts.

**FR-30 RozgarSahay**
- Skills assessment, job matching, coaching; inclusive employers.

**FR-31 NeuroNetwork + EmpathyTrainer**
- Parent groups/mentors/resources.
- Training for schools, employers, families.

**Acceptance criteria:**
- NeuroScreen can be completed offline and produces a stored result and referral guidance.
- AAC functions fully offline with at least one local TTS voice per supported language set.

### 8.10 HealthChain (records)
**FR-32 Portable health record**
- Local record store (offline) with sync.
- Tamper-proof audit trail; align with ABDM where possible.

**FR-33 Data export/share**
- Share with clinician via QR/short code/SMS summary.

### 8.11 ShikayatChain (blockchain complaints)
**FR-34 Multi-channel complaint intake**
- App, IVR, WhatsApp, ASHA-assisted.
- Voice supported in any language.

**FR-35 Blockchain anchoring + receipt**
- Complaint recorded immutably; SMS receipt.
- Evidence stored tamper-proof (IPFS) and referenced.

**FR-36 Routing + SLA timers**
- Auto-route to authority.
- SLA countdown visible; smart contract enforces escalation.

**FR-37 Tracking & closure**
- Real-time status.
- Mandatory user feedback before closure.
- Public facility/officer performance scores.

**Acceptance criteria:**
- Every submitted complaint returns a receipt ID and immutable transaction reference.
- If SLA expires, escalation occurs automatically without manual intervention.

### 8.12 GovSahay (government dashboard)
**FR-38 Three-level views**
- District: block-level data, ASHA/PHC performance.
- State: district comparisons, policy tracking.
- National: pan-India trends, SDG progress, budget usage.

**FR-39 Heatmaps and gap views**
- Disease, vaccination gaps, maternal/child health, mental health.
- Disability mapping: autism, ADHD, physical disabilities.
- Complaint hotspots.

**FR-40 Predictive analytics**
- Outbreak warnings (2–3 weeks).
- Seasonal forecasts.
- Demand prediction for beds/medicines/staff.

**FR-41 Action & accountability**
- Resource allocation recommendations.
- SLA and performance tracking.

**Acceptance criteria:**
- Dashboard supports near-real-time updates (see NFRs for exact SLOs).
- Users can filter by time, geography, demographic segments, and program.

## 9. Non-functional requirements (NFRs)
### 9.1 Offline-first & sync
- Core actions must work offline: triage capture, daily tracking logs, NeuroScreen, complaint capture (queued).
- Sync strategy: **local-first with eventual consistency**, conflict resolution rules.

**Targets:**
- App usable with 0 connectivity for >7 days.
- Sync completes within 5 minutes of regained connectivity for typical payloads.

### 9.2 Performance & scalability
- Backend designed for national scale (Kafka + Kubernetes in tech stack).
- Support high IVR concurrency.

**Targets (initial):**
- 99th percentile API latency < 800ms for key reads.
- Queue processing within 60 seconds for “dashboard ingestion” events (pilot scale).

### 9.3 Accessibility & inclusivity
- **WCAG 2.1 AAA** UI target (deck).
- Multi-language (22).
- Neurodiverse features: calm mode, simplified navigation, low sensory overload.

### 9.4 Security, privacy, and compliance
- Encryption: AES-256 at rest, TLS 1.3 in transit (deck).
- Auth: JWT/OAuth, RBAC.
- DPDP-compliant audits.
- Strong separation between identifiable data and de-identified analytics datasets.

### 9.5 Safety & clinical governance
- Clearly present that triage is guidance; encourage clinician consultation.
- Red-flag symptom protocols maintained with medical advisors.
- Audit logs for AI outputs used in care pathways.

### 9.6 Reliability
- IVR must degrade gracefully to human agent or minimal menu.
- Offline queue durability and no data loss.

## 10. Integrations
### 10.1 Government & national platforms (from deck)
- ABDM
- ICDS
- NHM
- UDID
- PM-JAY
- DigiLocker
- CoWIN (implied by vaccine certificates and scheme integration mention)

### 10.2 Communications
- Twilio/Exotel for IVR and telephony.

### 10.3 Maps/geo
- Mapbox for heatmaps and location views.

## 11. Data model (conceptual)
### 11.1 Core entities
- **UserProfile** (individual) + **FamilyGroup**
- **Encounter** (IVR triage session / teleconsult)
- **VitalsMeasurement**
- **FoodLog**, **SleepLog**, **WaterLog**, **ActivityLog**, **MoodLog**
- **MedicationPlan** + **AdherenceEvent**
- **VaccinationSchedule** + **VaccinationEvent**
- **NeuroScreenResult** + **TherapyPlan** + **RoutineSchedule**
- **Complaint** + **EvidenceArtifact** + **SLAState** + **EscalationHistory**
- **Facility** + **Officer** (for accountability scoring)
- **AnalyticsEvent** (de-identified)

### 11.2 Data separation
- PII store (protected)
- Health records store
- De-identified analytics store (GovSahay)
- Blockchain anchors: store only hashes/refs, not raw PII

## 12. Analytics & success metrics
### 12.1 Product KPIs
- Access:
  - # of VoiceSahay calls/day, completion rate, language coverage
  - % triage resolved locally (deck suggests **~40%** cases resolved locally)
  - Referral follow-through rate
- Daily wellness:
  - 7-day and 30-day active users
  - % users with consistent logs (vitals/food/sleep)
  - # of early risk alerts and confirmations
- Neurodiversity:
  - # screenings, time to specialist consult, therapy adherence
  - diagnosis delay reduction (deck target: 7 years → 7 months)
- Accountability:
  - # complaints filed, SLA compliance, escalation rate, closure satisfaction
- Government:
  - dashboard adoption, time-to-detect outbreaks, resource allocation actions

### 12.2 Outcome metrics (from deck, to be validated)
- 70% less travel for consultations
- 24 lakh lives/year saved via early detection
- ₹5,000/year saved per family
- ₹35,000 Cr/year government budget savings
- 2–3 weeks outbreak warnings

## 13. MVP definition
### 13.1 MVP objective (3 months per deck)
Deliver a deployable MVP that proves:
- **Voice-first triage** works on feature phones.
- **Offline-first ASHA tools** and at least one screening workflow.
- **Basic daily tracking** with offline sync.
- **Complaint intake + immutable receipt + SLA escalation prototype**.
- **Gov dashboard** with live ingestion and basic heatmap.

### 13.2 MVP in-scope features
- VoiceSahay: IVR language selection, symptom intake, triage output, SMS summary.
- TeleSahay: call-based consult workflow + SMS prescription.
- ASHASahay: offline patient capture + NeuroScreen (basic).
- DailySahay: VitalTrack, DawaiSahay, BalVikas (minimum set) with offline storage.
- ShikayatChain: complaint create, receipt, SLA escalation (pilot authority routing).
- GovSahay: district view + complaint hotspots + basic disease/vax heatmap.

### 13.3 MVP out-of-scope
- Full RozgarSahay job marketplace.
- Full national-scale predictive models (use heuristic/early ML).
- Advanced IoT integrations beyond manual entry.

## 14. Rollout plan (from deck timeline)
1. **MVP (0–3 months):** functional pilot-ready system.
2. **State pilot (3–9 months):** expand languages, integrations, model accuracy, dashboard maturity.
3. **National scale (9–24 months):** multi-state rollout, full scheme integration, hardened infra.

## 15. Risks & mitigations
### 15.1 Connectivity & device constraints
- **Risk:** zero network; feature phones only.
- **Mitigation:** IVR-first, offline-first storage and sync.

### 15.2 Clinical safety / liability
- **Risk:** incorrect triage guidance.
- **Mitigation:** red-flag protocols, human escalation, audit trails, medical advisory board.

### 15.3 Privacy & trust
- **Risk:** misuse of health data; fear of retaliation in complaints.
- **Mitigation:** consent management, anonymized complaints, immutable logs, RBAC.

### 15.4 Adoption by frontline workers
- **Risk:** training burden / resistance.
- **Mitigation:** 2-hour training, offline workflow, reduce paperwork, incentives.

### 15.5 Blockchain cost/complexity
- **Risk:** operational overhead.
- **Mitigation:** store only hashes on-chain; use low-cost chains (Polygon) and batch anchoring.

## 16. Open questions
1. Which languages are in the initial 22-language set for MVP/pilot?
2. What is the intended governance model for clinician network (gov-employed vs partners)?
3. What complaint SLAs should smart contracts enforce for each complaint category?
4. What minimum dataset is shared to GovSahay (fields, granularity, de-identification rules)?
5. What medical device integrations are expected in pilot districts (BP cuff, glucometer brands)?

## 17. Technical approach (as per deck; non-binding)
- **Frontend:** React Native; **Web:** Next.js PWA
- **Voice:** Twilio/Exotel; STT Whisper; TTS Google regional voices
- **AI/ML:** GPT-family/LLaMA chat; custom triage/screening/outbreak models; on-device TFLite
- **Backend:** FastAPI + Node.js real-time; Kafka, Redis, Celery; Kubernetes
- **DB:** PostgreSQL, MongoDB, TimescaleDB, Pinecone, ClickHouse
- **Blockchain:** Polygon + Solidity; IPFS; verifiable IDs
- **Analytics:** Superset, Grafana, Mapbox, D3
- **Security:** AES-256, TLS 1.3, JWT/OAuth, RBAC, DPDP audits

---

Appendix A — Module list (from deck)
- DailySahay: VitalTrack, AaharSahay, FitSahay, NeendSahay, JalSahay, MannSahay, NaariSahay, VriddhSahay, BalVikas, DawaiSahay, ParivarSahay, ChronicCare
- Access: VoiceSahay, TeleSahay, ASHASahay, VaxTrack, HealthChain, SOS, Locator, OutbreakSense
- Neurodiversity: NeuroScreen, AdaptLearn, TherapyHome, CommBridge, SensoryShield, RoutineBuilder, MeltdownPredict, RozgarSahay, NeuroNetwork, EmpathyTrainer
- Accountability: ShikayatChain
- Government: GovSahay
