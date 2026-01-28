# Technical PRD — Data, Analytics & GovSahay

## 1. Scope
- De-identified analytics pipeline powering **GovSahay**:
  - health heatmaps (disease, vaccination, maternal/child, mental health)
  - disability mapping
  - complaint hotspots
  - predictive analytics outputs (OutbreakSense)

Deck stack: ClickHouse, Superset, Grafana, Mapbox, D3.

## 2. Data sources
- Triage sessions (aggregated)
- Daily wellness logs (aggregated)
- Vaccination events
- NeuroScreen aggregated results
- Complaints metadata + SLA states
- Facility load signals (where available)

## 3. Privacy model
- Strict separation between PII stores and analytics.
- Aggregation thresholds and k-anonymity style safeguards.
- Geo granularity controls (village/block/district) based on sensitivity.

## 4. Pipeline architecture
- Ingestion via Kafka `analytics.events`.
- Stream processing for near-real-time aggregates.
- Storage:
  - ClickHouse for fast OLAP
  - Postgres for metadata

## 5. GovSahay product requirements
### 5.1 Three-level views
- District: block-level actions, ASHA & PHC performance
- State: district comparisons, policy tracking
- National: trends, SDG progress, budget usage

### 5.2 Heatmaps
- Mapbox-based tiles/layers.
- Filters: time window, program, demographic.

### 5.3 Predictive analytics
- Outbreak warnings 2–3 weeks.
- Demand prediction for beds/medicines/staff.

### 5.4 Accountability
- SLA compliance views.
- Complaint hotspots.
- Facility/officer performance scorecards.

## 6. NFRs
- Data freshness targets:
  - pilot: <15 minutes for key aggregates
  - scale: <5 minutes
- Query latency: P95 < 2s for typical dashboard queries.

## 7. MVP deliverables
- District dashboard with:
  - basic disease/triage heatmap
  - vaccination gap view (if data available)
  - complaint hotspot map
  - SLA compliance table
