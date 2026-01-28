# SAHAY — Domain-wise Technical PRDs (Index)

This index links the domain-specific technical PRDs that break down implementation requirements for SAHAY.

## Core product PRD
- `prd.md` — Overall Product Requirements Document (problem, personas, journeys, functional + NFRs, MVP, rollout)

## Domain technical PRDs
1. `prd_frontend.md` — React Native + Next.js PWA, accessibility (WCAG 2.1 AAA target), offline UX, neurodiverse UI modes
2. `prd_backend_platform.md` — Backend service architecture, offline sync gateway, APIs, storage, integrations, SLOs
3. `prd_voice_ivr.md` — VoiceSahay IVR/telephony flows, STT/TTS requirements, reliability, safety metrics
4. `prd_ai_ml.md` — Triage + NeuroScreen + OutbreakSense + personalization models, evaluation, safety, on-device ML
5. `prd_blockchain.md` — ShikayatChain SLA enforcement + HealthChain anchoring, IPFS evidence, privacy/security
6. `prd_data_analytics_govsahay.md` — Data pipelines, de-identification, GovSahay heatmaps/dashboards, freshness/latency targets

## Suggested reading order (for engineering)
1) `prd.md` → 2) `prd_backend_platform.md` + `prd_frontend.md` → 3) `prd_voice_ivr.md` → 4) `prd_ai_ml.md` → 5) `prd_blockchain.md` → 6) `prd_data_analytics_govsahay.md`
