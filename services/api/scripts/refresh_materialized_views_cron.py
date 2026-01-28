#!/usr/bin/env python3
"""
Cron Script: Refresh Materialized Views

Schedule: Every 10-15 minutes
Crontab entry: */10 * * * * /path/to/python /path/to/refresh_materialized_views_cron.py

Purpose:
- Refresh all materialized views with latest analytics data
- Ensures dashboards show recent data
- Runs in background without blocking user requests

Usage:
    python services/api/scripts/refresh_materialized_views_cron.py
"""

import sys
import os
from datetime import datetime
import logging

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from services.api.db import SessionLocal
from services.api.materialized_views import refresh_all_materialized_views

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/sahaay/materialized_views_refresh.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Main function to refresh materialized views."""
    start_time = datetime.utcnow()
    logger.info("="*70)
    logger.info(f"Starting materialized views refresh at {start_time.isoformat()}")
    
    db = SessionLocal()
    
    try:
        # Refresh all views
        results = refresh_all_materialized_views(db)
        
        # Log results
        success_count = sum(1 for v in results.values() if v == "success")
        error_count = len(results) - success_count
        
        logger.info(f"Refresh completed: {success_count} succeeded, {error_count} failed")
        
        for view_name, status in results.items():
            if status == "success":
                logger.info(f"  ✓ {view_name}: {status}")
            else:
                logger.error(f"  ✗ {view_name}: {status}")
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"Refresh duration: {duration:.2f} seconds")
        logger.info("="*70)
        
        # Exit code
        sys.exit(0 if error_count == 0 else 1)
        
    except Exception as e:
        logger.error(f"Fatal error during refresh: {str(e)}", exc_info=True)
        sys.exit(1)
        
    finally:
        db.close()


if __name__ == "__main__":
    main()
