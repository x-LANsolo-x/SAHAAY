"""Background worker for automatic complaint escalation based on SLA rules.

This worker:
1. Runs periodically to check for SLA breaches
2. Automatically escalates complaints that exceed time limits
3. Records status history for audit trails
4. Updates complaint levels (district → state → national)
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from services.api import models
from services.api.db import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_sla_deadline(complaint: models.Complaint, sla_rules: dict) -> datetime | None:
    """Calculate SLA deadline for a complaint based on category and level.
    
    Args:
        complaint: Complaint instance
        sla_rules: Dict mapping (category, level) -> time_limit_hours
        
    Returns:
        Deadline datetime or None if no rule found
    """
    key = (complaint.category, complaint.current_level)
    if key not in sla_rules:
        return None
    
    time_limit_hours = sla_rules[key]
    return complaint.created_at + timedelta(hours=time_limit_hours)


def should_escalate(complaint: models.Complaint, sla_rules: dict) -> bool:
    """Check if a complaint should be escalated.
    
    Escalation criteria:
    - Status is not resolved or closed
    - Current time exceeds SLA deadline
    - Not already at maximum escalation level (3)
    """
    # Don't escalate resolved/closed complaints
    if complaint.status in [models.ComplaintStatus.resolved, models.ComplaintStatus.closed]:
        return False
    
    # Don't escalate if already at national level
    if complaint.current_level >= 3:
        return False
    
    # Check if deadline passed
    deadline = get_sla_deadline(complaint, sla_rules)
    if deadline is None:
        return False
    
    return datetime.utcnow() > deadline


def escalate_complaint(db: Session, complaint: models.Complaint, reason: str = "SLA breach") -> None:
    """Escalate a complaint to the next level.
    
    Updates:
    - current_level (1→2→3)
    - status (to escalated if not already)
    - sla_due_at (reset based on new level)
    - Adds status history entry
    """
    old_level = complaint.current_level
    old_status = complaint.status
    
    # Escalate level
    new_level = min(old_level + 1, 3)
    complaint.current_level = new_level
    
    # Update status to escalated
    if complaint.status != models.ComplaintStatus.escalated:
        complaint.status = models.ComplaintStatus.escalated
    
    # Reset SLA deadline for new level
    # Fetch SLA rule for new level
    sla_rule = db.query(models.SLARule).filter(
        models.SLARule.category == complaint.category,
        models.SLARule.escalation_level == new_level
    ).first()
    
    if sla_rule:
        complaint.sla_due_at = datetime.utcnow() + timedelta(hours=sla_rule.time_limit_hours)
    
    complaint.updated_at = datetime.utcnow()
    
    # Record status history
    history = models.ComplaintStatusHistory(
        complaint_id=complaint.id,
        old_status=old_status,
        new_status=complaint.status,
        old_level=old_level,
        new_level=new_level,
        changed_by_user_id=None,  # Automatic escalation
        change_reason=reason,
        is_auto_escalation=True,
    )
    db.add(history)
    
    logger.info(f"Escalated complaint {complaint.id} from level {old_level} to {new_level}")


def run_escalation_check(db: Session | None = None) -> dict:
    """Run escalation check for all active complaints.
    
    Returns:
        Statistics about escalations performed
    """
    if db is None:
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    
    try:
        # Load SLA rules into memory for fast lookup
        sla_rules = {}
        for rule in db.query(models.SLARule).all():
            sla_rules[(rule.category, rule.escalation_level)] = rule.time_limit_hours
        
        if not sla_rules:
            logger.warning("No SLA rules configured. Skipping escalation check.")
            return {"checked": 0, "escalated": 0, "message": "No SLA rules configured"}
        
        # Find active complaints (not resolved/closed)
        active_statuses = [
            models.ComplaintStatus.submitted,
            models.ComplaintStatus.under_review,
            models.ComplaintStatus.investigating,
            models.ComplaintStatus.escalated,
        ]
        
        complaints = db.query(models.Complaint).filter(
            models.Complaint.status.in_(active_statuses)
        ).all()
        
        escalated_count = 0
        for complaint in complaints:
            if should_escalate(complaint, sla_rules):
                escalate_complaint(db, complaint)
                escalated_count += 1
        
        db.commit()
        
        logger.info(f"Escalation check complete: {len(complaints)} checked, {escalated_count} escalated")
        
        return {
            "checked": len(complaints),
            "escalated": escalated_count,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error during escalation check: {e}")
        db.rollback()
        raise
    finally:
        if should_close:
            db.close()


def run_periodic_escalation(interval_seconds: int = 3600):
    """Run escalation check periodically.
    
    Args:
        interval_seconds: Time between checks (default: 1 hour)
    """
    import time
    
    logger.info(f"Starting periodic escalation worker (interval: {interval_seconds}s)")
    
    while True:
        try:
            result = run_escalation_check()
            logger.info(f"Escalation result: {result}")
        except Exception as e:
            logger.error(f"Escalation check failed: {e}")
        
        time.sleep(interval_seconds)


if __name__ == "__main__":
    # Run worker with 1-hour interval
    run_periodic_escalation(interval_seconds=3600)
