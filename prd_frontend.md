# Technical PRD — Frontend (SAHAY)

## 1. Scope & outcomes
### 1.1 In-scope surfaces
- **Mobile app (React Native):** citizen smartphone app + ASHA/Anganwadi worker mode (role-based)
- **Web app / PWA (Next.js):** lightweight citizen access, admin tools (where appropriate), GovSahay dashboard shell (if web)
- **Accessibility-first UI system:** WCAG 2.1 AAA target from deck; neurodiverse-native design

### 1.2 Primary outcomes
- **Offline-first UX:** full usability in zero connectivity; seamless sync when online.
- **Voice-first augmentation:** in-app voice input/output complements IVR for smartphone users.
- **Low cognitive load:** adaptive UI profiles (literacy, neurodiversity, elderly).

### 1.3 Out of scope (frontend)
- Telephony IVR infrastructure (covered in `prd_voice_ivr.md`)
- Backend services, ML model training (covered elsewhere)

## 2. Personas & UX modes (frontend requirements)
### 2.1 UX modes
- **Standard mode:** typical smartphone users.
- **Lite mode:** low-end devices, minimal animations, low bandwidth.
- **Calm mode (sensory-safe):** reduced motion, muted palette, fewer simultaneous stimuli.
- **Caregiver mode:** manage family members (ParivarSahay) + alerts.
- **ASHA mode:** offline field workflow, visit queue, quick forms, bulk sync.
- **AAC mode (CommBridge):** symbols, large targets, TTS, offline packs.

### 2.2 Language support
- 22 Indian languages; user-selectable and persisted.
- UI text localization + audio prompts (where relevant).

## 3. Feature requirements by module

### 3.1 Onboarding & profile
**FE-FR-1 Profile creation**
- Create individual profile + optionally join/create family group.
- Minimal onboarding path available for Lite mode.

**FE-FR-2 Consent UX**
- Clear consent screens with toggles for:
  - local storage
  - cloud sync
  - share with ASHA/clinicians
  - de-identified analytics
- Show when last synced + what data categories sync.

**FE-FR-3 Role-based UI**
- Roles: citizen, caregiver, ASHA/Anganwadi, clinician (optional), admin.
- Role selection gated by backend-issued claims.

### 3.2 DailySahay (daily wellness tracking)
**FE-FR-4 Tracking home**
- “Today” dashboard: quick add for vitals, water, mood, meds.
- Doctor-ready report generation and sharing.

**FE-FR-5 VitalTrack**
- Manual entry + optional device import.
- Trend charts that work offline.

**FE-FR-6 AaharSahay**
- Photo capture with offline queue.
- Voice logging with local buffering.

**FE-FR-7 MannSahay**
- Mood tracker, guided breathing/meditation audio.
- SOS entrypoint.

**FE-FR-8 BalVikas / VaxTrack**
- Growth & milestones timeline.
- Vaccination schedule reminders; certificate viewer (when integrated).

**FE-FR-9 DawaiSahay**
- Medication schedule UI with large, accessible reminders.
- Interaction warnings displayed cautiously (non-alarming language).

### 3.3 Access suite
**FE-FR-10 TeleSahay booking UI**
- Create consult request, preferred time, attach symptom summary.
- View prescriptions and visit notes.

**FE-FR-11 Locator**
- Map + list view; offline cached directory.
- Filters: open now, PHC/hospital/pharmacy/lab.

**FE-FR-12 SOS**
- One-tap entry with confirmation step.
- Display what will be shared (location, profile summary).

### 3.4 Neurodiversity suite
**FE-FR-13 NeuroScreen**
- 5-min guided screening flow (ASHA/caregiver).
- Accessible controls, progress indicator, offline completion.

**FE-FR-14 TherapyHome**
- Module library with offline content packs.
- Daily routine view + completion tracking.

**FE-FR-15 CommBridge (AAC)**
- Symbol boards, customizable phrases.
- TTS output offline; optional multilingual.

**FE-FR-16 SensoryShield + RoutineBuilder**
- Calm toolkit: timers, breathing, safe visuals.
- Visual schedule with transitions.

**FE-FR-17 MeltdownPredict (alerts)**
- Caregiver notifications with configurable sensitivity.

### 3.5 ShikayatChain (complaints)
**FE-FR-18 Complaint filing**
- Category selection + voice/text description.
- Evidence attachments (photo/audio) stored locally until sync.
- Show immutable receipt ID + status timeline.

**FE-FR-19 Closure feedback**
- Mandatory feedback UI with accessibility support.

### 3.6 GovSahay (frontend shell)
- Web-first dashboard with RBAC.
- Filters: time, geography, program, demographic.
- Heatmaps + trend panels.

## 4. Offline-first architecture (frontend)
### 4.1 Storage
- Local DB: **SQLite** (RN) + IndexedDB (web) for offline cache.
- Data categories: profiles, logs, drafts, attachments metadata, sync queue.

### 4.2 Sync engine (client)
- Event-sourcing style queue: `CREATE/UPDATE` events with timestamps, device ID.
- Conflict resolution:
  - “append-only” for logs
  - “last-write-wins” for profile fields with audit
  - server authoritative for prescriptions/complaints state

### 4.3 Attachment handling
- Store locally with encryption at rest.
- Upload when online; show per-item upload state.

## 5. Accessibility & inclusive design requirements
- WCAG 2.1 AAA target where feasible.
- Screen reader semantics everywhere.
- Minimum touch target sizes.
- Dyslexia-friendly font option.
- Reduce motion option.
- Color contrast safe palettes.
- Plain-language content; voice reading of key screens.

## 6. Security requirements (frontend)
- Secure storage for tokens (Keychain/Keystore).
- Local encryption for sensitive caches.
- Session timeout and device binding (configurable).
- Jailbreak/root detection (optional, policy-driven).

## 7. Observability
- Client events: screen views, sync success/failure, crash logs.
- Offline metrics: queue length, average time-to-sync.

## 8. Acceptance criteria (system-level)
- App usable for **7+ days offline** (create logs, screen results, complaint drafts).
- Sync completes automatically when online; user can force “Sync now”.
- All critical flows usable with screen readers.

## 9. Delivery plan
- **MVP (0–3 months):** onboarding, VitalTrack, DawaiSahay, BalVikas/VaxTrack basics, TeleSahay request, ShikayatChain filing, offline sync core.
- **Pilot (3–9 months):** AAC, calm mode, expanded neuro modules, improved reporting, localization scale.
- **Scale (9–24 months):** advanced dashboards, richer device integrations, performance hardening.
