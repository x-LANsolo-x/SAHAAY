# Technical PRD — Voice/IVR (VoiceSahay + Telephony)

## 1. Scope
Feature-phone accessible SAHAY flows:
- **VoiceSahay:** toll-free helpline with AI triage
- **TeleSahay:** call-based clinician connection
- **Voice complaint filing:** ShikayatChain intake via voice

Deck stack: Twilio/Exotel, Whisper STT, Google TTS (regional voices).

## 2. Call flows
### 2.1 Entry
- Language selection (22 languages) with DTMF fallback.
- Consent prompt.

### 2.2 Triage conversation
- Capture symptoms (free speech) + structured follow-ups.
- Red-flag detection and emergency guidance.

### 2.3 Handoff
- Connect to clinician queue OR schedule callback.
- Generate SMS summary.

### 2.4 Complaint filing
- Category selection, voice description, optional evidence via WhatsApp.
- SMS receipt.

## 3. STT/TTS requirements
- STT must handle code-mixed speech.
- TTS supports regional voices.
- DTMF fallback for low-quality audio.

## 4. Reliability and safety
- Graceful degradation to menu-based triage if AI fails.
- Record consent and minimize retention.
- Rate limits and abuse detection.

## 5. Metrics
- Call completion rate.
- Average handle time.
- STT WER by language.
- Emergency escalation correctness.

## 6. MVP deliverables
- IVR menu + basic symptom capture.
- AI triage output + SMS summary.
- Clinician callback scheduling.
