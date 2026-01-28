# Apache Superset Dashboard Configuration Guide

## Overview

This guide shows how to connect Apache Superset to the SAHAAY analytics backend and create the required dashboards for GovSahay.

---

## Part 1: Setup and Connection

### 1.1 Install Apache Superset

```bash
# Using Docker (recommended)
docker pull apache/superset:latest

docker run -d -p 8088:8088 \
  --name superset \
  -e "SUPERSET_SECRET_KEY=your-secret-key-here" \
  apache/superset:latest

# Initialize database
docker exec -it superset superset db upgrade
docker exec -it superset superset fab create-admin \
  --username admin \
  --firstname Admin \
  --lastname User \
  --email admin@sahaay.gov.in \
  --password admin

docker exec -it superset superset init
```

### 1.2 Add SAHAAY Database Connection

1. Navigate to **Data → Databases**
2. Click **+ Database**
3. Configure connection:

**PostgreSQL (Production):**
```
SQLAlchemy URI: postgresql://user:password@localhost:5432/sahaay
```

**SQLite (Development):**
```
SQLAlchemy URI: sqlite:////path/to/sahaay.db
```

4. Test connection
5. Save

### 1.3 Add Datasets

Navigate to **Data → Datasets** and add:

1. **aggregated_analytics_events** (main table)
2. **mv_daily_triage_counts** (materialized view)
3. **mv_complaint_categories_district** (materialized view)
4. **mv_symptom_heatmap** (materialized view)
5. **mv_sla_breach_counts** (materialized view)

---

## Part 2: Dashboard 1 - Triage Volume Over Time

### Purpose
Track triage session volume trends over time to identify patterns and surges.

### Data Source
- **Dataset:** `mv_daily_triage_counts`
- **Columns:**
  - `date` (temporal)
  - `event_type` (dimension)
  - `category` (dimension)
  - `total_count` (metric)
  - `geo_cell` (dimension)

### Chart Configuration

#### Chart 1: Daily Triage Volume (Line Chart)
```yaml
Chart Type: Line Chart
Metrics:
  - SUM(total_count) AS "Total Triages"
Dimensions:
  - date
Filters:
  - event_type IN ('triage_completed', 'triage_emergency')
Time Range: Last 30 days
Group By: date
Order By: date ASC
```

#### Chart 2: Triage by Category (Stacked Bar)
```yaml
Chart Type: Bar Chart (Stacked)
Metrics:
  - SUM(total_count)
Dimensions:
  - date (X-axis)
  - category (Group)
Filters:
  - event_type = 'triage_completed'
Time Range: Last 30 days
```

#### Chart 3: Emergency vs Regular (Area Chart)
```yaml
Chart Type: Area Chart
Metrics:
  - SUM(total_count)
Dimensions:
  - date (X-axis)
  - event_type (Group)
Filters:
  - event_type IN ('triage_completed', 'triage_emergency')
Time Range: Last 30 days
```

#### Chart 4: Top Districts (Table)
```yaml
Chart Type: Table
Metrics:
  - SUM(total_count) AS "Triages"
  - COUNT(DISTINCT date) AS "Active Days"
Dimensions:
  - geo_cell
Filters:
  - None
Order By: Triages DESC
Limit: 10
```

### Dashboard Layout
```
┌─────────────────────────────────────────────────┐
│  Triage Volume Over Time Dashboard              │
├──────────────┬──────────────────────────────────┤
│              │                                  │
│  Big Number  │  Daily Triage Volume (Line)     │
│  KPI         │                                  │
│              │                                  │
├──────────────┴──────────────────────────────────┤
│  Triage by Category (Stacked Bar)               │
│                                                  │
├──────────────┬──────────────────────────────────┤
│  Emergency   │  Top Districts (Table)          │
│  vs Regular  │                                  │
│  (Area)      │                                  │
└──────────────┴──────────────────────────────────┘
```

---

## Part 3: Dashboard 2 - Complaint Category Distribution

### Purpose
Visualize complaint categories and their distribution across districts.

### Data Source
- **Dataset:** `mv_complaint_categories_district`
- **Columns:**
  - `geo_cell` (dimension)
  - `category` (dimension)
  - `event_type` (dimension)
  - `total_complaints` (metric)
  - `avg_complaints_per_period` (metric)

### Chart Configuration

#### Chart 1: Category Pie Chart
```yaml
Chart Type: Pie Chart
Metrics:
  - SUM(total_complaints)
Dimensions:
  - category
Filters:
  - event_type = 'complaint_submitted'
Show Labels: Yes
Show Percentages: Yes
```

#### Chart 2: Complaints by District (Bar)
```yaml
Chart Type: Bar Chart
Metrics:
  - SUM(total_complaints) AS "Complaints"
Dimensions:
  - geo_cell
Filters:
  - event_type = 'complaint_submitted'
Order By: Complaints DESC
Limit: 15
Color Scheme: Sequential
```

#### Chart 3: Category Heatmap
```yaml
Chart Type: Heatmap
Metrics:
  - SUM(total_complaints)
Dimensions:
  - geo_cell (Y-axis)
  - category (X-axis)
Filters:
  - event_type = 'complaint_submitted'
Color Scheme: Red-Yellow-Green (Inverted)
```

#### Chart 4: Trend Over Time
```yaml
Chart Type: Line Chart (Multi-line)
Metrics:
  - SUM(total_complaints)
Dimensions:
  - date (X-axis)
  - category (Group)
Time Range: Last 90 days
```

---

## Part 4: Dashboard 3 - SLA Breach Heatmap

### Purpose
Identify districts with high SLA breach rates for accountability.

### Data Source
- **Dataset:** `mv_sla_breach_counts`
- **Columns:**
  - `geo_cell` (dimension)
  - `complaint_category` (dimension)
  - `escalated_count` (metric)
  - `resolved_count` (metric)
  - `escalation_rate` (metric)

### Chart Configuration

#### Chart 1: SLA Breach Rate by District (Map/Heatmap)
```yaml
Chart Type: Heatmap or Big Number with Trendline
Metrics:
  - AVG(escalation_rate) AS "Escalation %"
  - SUM(escalated_count) AS "Escalated"
Dimensions:
  - geo_cell
Filters:
  - escalated_count > 0
Color Scheme: Red (high) to Green (low)
Thresholds:
  - Green: < 10%
  - Yellow: 10-30%
  - Red: > 30%
```

#### Chart 2: Worst Offenders (Table)
```yaml
Chart Type: Table
Metrics:
  - geo_cell
  - SUM(total_complaints) AS "Total"
  - SUM(escalated_count) AS "Escalated"
  - AVG(escalation_rate) AS "Rate %"
Filters:
  - escalation_rate > 20
Order By: escalation_rate DESC
Limit: 20
Conditional Formatting: Red for rate > 30%
```

#### Chart 3: SLA Performance Trend
```yaml
Chart Type: Line Chart
Metrics:
  - AVG(escalation_rate)
Dimensions:
  - date
Time Range: Last 90 days
Target Line: 15% (SLA threshold)
```

---

## Part 5: Dashboard 4 - AAC (Analytics Adoption Coverage)

### Purpose
Track analytics consent adoption by district.

### Data Source
- **Custom SQL Query:**
```sql
SELECT 
  p.pincode_prefix AS geo_cell,
  COUNT(DISTINCT c.user_id) AS users_consented,
  COUNT(DISTINCT u.id) AS total_users,
  CAST(COUNT(DISTINCT c.user_id) AS FLOAT) / 
    NULLIF(COUNT(DISTINCT u.id), 0) * 100 AS adoption_rate
FROM users u
LEFT JOIN profiles p ON u.id = p.user_id
LEFT JOIN consents c ON u.id = c.user_id 
  AND c.category = 'analytics' 
  AND c.granted = TRUE
GROUP BY p.pincode_prefix
HAVING COUNT(DISTINCT u.id) >= 5;
```

### Chart Configuration

#### Chart 1: Adoption Rate by District
```yaml
Chart Type: Bar Chart
Metrics:
  - adoption_rate AS "Adoption %"
Dimensions:
  - geo_cell
Order By: adoption_rate DESC
Color: Green gradient
Target Line: 50%
```

#### Chart 2: Consent Funnel
```yaml
Chart Type: Funnel
Metrics:
  - total_users → "Total Users"
  - users_consented → "Consented"
  - (from analytics events) → "Active Users"
```

---

## Part 6: Advanced Configuration

### 6.1 Refresh Schedule

Configure automatic refresh for all dashboards:

```yaml
Dashboard Settings → Cache Timeout: 600 seconds (10 minutes)
Dataset Settings → Cache Timeout: 300 seconds (5 minutes)
```

### 6.2 Filters and Parameters

Add dashboard-level filters:

```yaml
Filters:
  - Time Range (date picker)
  - District (multi-select dropdown from geo_cell)
  - Event Type (multi-select)
```

### 6.3 Role-Based Access

```yaml
Roles:
  - district_officer: View own district only
  - state_officer: View all districts in state
  - national_admin: View all data
```

SQL Rule for Row-Level Security:
```sql
-- District Officer
WHERE geo_cell = '{{ current_user_district() }}'

-- State Officer  
WHERE geo_cell LIKE '{{ current_user_state_prefix() }}%'
```

### 6.4 Alerts

Set up alerts for critical metrics:

```yaml
Alert 1: SLA Breach Rate
  Condition: AVG(escalation_rate) > 30%
  Frequency: Daily
  Recipients: district_officers@sahaay.gov.in

Alert 2: Triage Surge
  Condition: COUNT(triages) > 2x daily average
  Frequency: Hourly
  Recipients: health_officers@sahaay.gov.in
```

---

## Part 7: Direct API Integration (Alternative)

If Superset is not available, consume APIs directly:

### Using JavaScript/React

```javascript
// Fetch dashboard data
const fetchDashboardData = async (token) => {
  // Triage volume
  const triageResponse = await fetch(
    'http://api.sahaay.gov.in/dashboard/mv/triage-counts',
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const triageData = await triageResponse.json();

  // Complaints
  const complaintsResponse = await fetch(
    'http://api.sahaay.gov.in/dashboard/mv/complaint-categories',
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const complaintsData = await complaintsResponse.json();

  // SLA breaches
  const slaResponse = await fetch(
    'http://api.sahaay.gov.in/dashboard/mv/sla-breaches',
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const slaData = await slaResponse.json();

  return { triageData, complaintsData, slaData };
};
```

### Using Python/Pandas

```python
import requests
import pandas as pd

API_BASE = "http://api.sahaay.gov.in"
TOKEN = "your-token-here"

headers = {"Authorization": f"Bearer {TOKEN}"}

# Fetch triage data
triage_df = pd.DataFrame(
    requests.get(f"{API_BASE}/dashboard/mv/triage-counts", headers=headers).json()['data']
)

# Create visualizations
import plotly.express as px

fig = px.line(triage_df, x='date', y='total_count', color='category')
fig.show()
```

---

## Troubleshooting

### Issue: "No data returned"
- Check materialized views are created: `GET /dashboard/materialized-views/stats`
- Refresh views: `POST /dashboard/materialized-views/refresh`
- Verify data exists: Query `aggregated_analytics_events` table directly

### Issue: "Slow queries"
- Ensure materialized views are refreshed regularly (cron job running)
- Check indexes exist on view tables
- Consider upgrading to ClickHouse for large datasets

### Issue: "Permission denied"
- Verify user has correct role in Superset
- Check row-level security rules
- Verify API token is valid and not expired

---

## Next Steps

1. ✅ Connect Superset to SAHAAY database
2. ✅ Import datasets (tables and materialized views)
3. ✅ Create 4 dashboards as specified
4. ✅ Configure refresh schedules
5. ✅ Set up role-based access
6. ✅ Configure alerts
7. 🎯 Train district/state officers on dashboard usage

For MapLibre heatmap integration, see `MAPLIBRE_HEATMAP_GUIDE.md`.
