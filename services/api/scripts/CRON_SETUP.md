# Cron Setup for Materialized Views Refresh

## Overview

Materialized views need to be refreshed every 10-15 minutes to ensure dashboards show recent data.

## Setup Instructions

### 1. Make Script Executable

```bash
chmod +x services/api/scripts/refresh_materialized_views_cron.py
```

### 2. Create Log Directory

```bash
sudo mkdir -p /var/log/sahaay
sudo chown $USER:$USER /var/log/sahaay
```

### 3. Add to Crontab

```bash
crontab -e
```

Add one of the following entries:

#### Option A: Refresh Every 10 Minutes (Recommended)
```cron
*/10 * * * * cd /path/to/SAHAAY && /usr/bin/python3 services/api/scripts/refresh_materialized_views_cron.py >> /var/log/sahaay/cron.log 2>&1
```

#### Option B: Refresh Every 15 Minutes
```cron
*/15 * * * * cd /path/to/SAHAAY && /usr/bin/python3 services/api/scripts/refresh_materialized_views_cron.py >> /var/log/sahaay/cron.log 2>&1
```

#### Option C: Refresh Every 5 Minutes (High-Frequency)
```cron
*/5 * * * * cd /path/to/SAHAAY && /usr/bin/python3 services/api/scripts/refresh_materialized_views_cron.py >> /var/log/sahaay/cron.log 2>&1
```

### 4. Verify Cron Job

```bash
# List current cron jobs
crontab -l

# Monitor log file
tail -f /var/log/sahaay/materialized_views_refresh.log
```

## Alternative: Systemd Timer

For production environments, consider using systemd timers instead of cron:

### Create Service File: `/etc/systemd/system/sahaay-refresh-views.service`

```ini
[Unit]
Description=Refresh SAHAAY Materialized Views
After=network.target postgresql.service

[Service]
Type=oneshot
User=sahaay
WorkingDirectory=/opt/sahaay
ExecStart=/usr/bin/python3 services/api/scripts/refresh_materialized_views_cron.py
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Create Timer File: `/etc/systemd/system/sahaay-refresh-views.timer`

```ini
[Unit]
Description=Refresh SAHAAY Materialized Views Every 10 Minutes
Requires=sahaay-refresh-views.service

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
Unit=sahaay-refresh-views.service

[Install]
WantedBy=timers.target
```

### Enable and Start Timer

```bash
sudo systemctl daemon-reload
sudo systemctl enable sahaay-refresh-views.timer
sudo systemctl start sahaay-refresh-views.timer

# Check status
sudo systemctl status sahaay-refresh-views.timer
sudo systemctl list-timers | grep sahaay
```

## Monitoring

### Check Last Run

```bash
# View cron logs
cat /var/log/sahaay/cron.log

# View detailed refresh logs
cat /var/log/sahaay/materialized_views_refresh.log
```

### Check View Stats via API

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/dashboard/materialized-views/stats
```

### Manual Refresh

```bash
# Via script
python services/api/scripts/refresh_materialized_views_cron.py

# Via API
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/dashboard/materialized-views/refresh
```

## Troubleshooting

### Cron Job Not Running

1. Check cron service is running:
   ```bash
   sudo systemctl status cron
   ```

2. Check cron logs:
   ```bash
   sudo tail -f /var/log/syslog | grep CRON
   ```

3. Verify script permissions:
   ```bash
   ls -la services/api/scripts/refresh_materialized_views_cron.py
   ```

### Database Connection Errors

1. Check database is accessible
2. Verify environment variables are set
3. Check database credentials in `.env` file

### Performance Issues

1. Consider increasing refresh interval (15 min instead of 10 min)
2. Add indexes to aggregated_analytics_events table
3. Monitor database query performance
4. Consider migrating to ClickHouse for large datasets

## Production Best Practices

1. **Use systemd timers** instead of cron (better logging, monitoring)
2. **Set up alerts** if refresh fails multiple times
3. **Monitor refresh duration** - should complete in < 30 seconds
4. **Log rotation** - configure logrotate for refresh logs
5. **Health checks** - integrate with monitoring systems (Prometheus, Grafana)

## Example Monitoring with Prometheus

Add to your monitoring script:

```python
from prometheus_client import Gauge

refresh_duration = Gauge('sahaay_mv_refresh_duration_seconds', 
                         'Duration of materialized view refresh')
refresh_success = Gauge('sahaay_mv_refresh_success', 
                        'Success status of last refresh')

# In refresh script:
with refresh_duration.time():
    results = refresh_all_materialized_views(db)

success = all(v == "success" for v in results.values())
refresh_success.set(1 if success else 0)
```

## Emergency Manual Rebuild

If views become corrupted or outdated:

```bash
# Drop and recreate all views
curl -X POST -H "Authorization: Bearer ADMIN_TOKEN" \
  http://localhost:8000/dashboard/materialized-views/create
```
