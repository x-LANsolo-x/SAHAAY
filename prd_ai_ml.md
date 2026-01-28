# Technical PRD — AI/ML (SAHAY)

## 1. Scope
AI/ML powering:
- **Symptom triage** (VoiceSahay + app)
- **NeuroScreen** (autism/ADHD/dyslexia screening support)
- **OutbreakSense** (2–3 week early warnings)
- **Personalized insights** for DailySahay (risk alerts, habits)

Deck hints: GPT-4/LLaMA chat, custom triage, screening AI, outbreak prediction; edge via TensorFlow Lite.

## 2. Guiding principles
- **Safety first:** conservative recommendations; escalation for red flags.
- **Explainability:** human-readable reasoning and citations to protocol rules.
- **Privacy:** on-device inference where possible; minimize raw audio/text retention.
- **Inclusivity:** multilingual (22 languages), low literacy; robust to code-mixed speech.

## 3. Model portfolio
### 3.1 Triage
- Hybrid approach:
  1) **Rule-based red-flag engine** (deterministic, medically reviewed)
  2) **LLM dialogue manager** (question asking, summarization)
  3) **Classifier** for acuity category: self-care / PHC / emergency

Outputs:
- Triage category
- Next-step instructions
- Summary for clinician
- Confidence and uncertainty flags

### 3.2 NeuroScreen
- Short-screening assistant producing:
  - likelihood bands (low/medium/high)
  - recommended referral pathway
  - suggested TherapyHome starting pack

Must be validated clinically; present as screening, not diagnosis.

### 3.3 OutbreakSense
- Time-series + geo anomaly detection.
- Inputs: symptom triage counts, vitals trends (aggregated), facility load, seasonality.
- Outputs: risk scores by district/block, lead time 2–3 weeks.

### 3.4 Personalization
- On-device heuristics + lightweight models for:
  - BP/glucose risk trends
  - adherence nudges
  - sleep/water habit suggestions

## 4. Data & labeling
- Collect de-identified interaction logs with consent.
- Label sources:
  - clinician-reviewed triage transcripts
  - gold-standard screening questionnaires
  - historical public health datasets for outbreaks

## 5. Evaluation & safety
### 5.1 Metrics
- Triage: sensitivity for emergencies, calibration, referral appropriateness.
- NeuroScreen: AUC, sensitivity for high-likelihood band.
- Outbreak: precision/recall for alerts, lead time.
- ASR (if used): WER per language.

### 5.2 Safety controls
- Red-flag override always wins.
- Hallucination guardrails: retrieval of approved protocols; constrained generation.
- Continuous monitoring and rollback.

## 6. On-device (offline) ML
- TFLite models for:
  - basic symptom keyword/intent detection
  - vitals trend risk
  - simple AAC suggestions

Sync for heavier inference when online.

## 7. MLOps
- Model registry, versioning.
- Shadow testing in pilot districts.
- Bias audits across language/region/gender.

## 8. MVP deliverables
- Red-flag engine + basic triage classifier.
- LLM summarization for clinician handoff.
- NeuroScreen scoring prototype.
- OutbreakSense heuristic baseline.
