"""Seed default SLA rules for complaint escalation.

Default SLA timings:
- District level (level 1): 48-168 hours depending on category
- State level (level 2): 72-240 hours
- National level (level 3): 120-336 hours
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.api import models
from services.api.db import SessionLocal


def seed_sla_rules():
    """Create default SLA rules for all complaint categories."""
    db = SessionLocal()
    
    # Default SLA rules (in hours)
    # Format: (category, level, hours)
    default_rules = [
        # Critical: medication_error, discrimination - faster escalation
        ("medication_error", 1, 24),   # 24 hours at district
        ("medication_error", 2, 48),   # 48 hours at state
        ("medication_error", 3, 72),   # 72 hours at national
        
        ("discrimination", 1, 48),     # 48 hours at district
        ("discrimination", 2, 96),     # 96 hours at state
        ("discrimination", 3, 168),    # 168 hours (7 days) at national
        
        # High priority: service_quality, staff_behavior, facility_issues
        ("service_quality", 1, 72),    # 72 hours (3 days) at district
        ("service_quality", 2, 168),   # 168 hours (7 days) at state
        ("service_quality", 3, 336),   # 336 hours (14 days) at national
        
        ("staff_behavior", 1, 72),
        ("staff_behavior", 2, 168),
        ("staff_behavior", 3, 336),
        
        ("facility_issues", 1, 96),    # 96 hours (4 days) at district
        ("facility_issues", 2, 192),   # 192 hours (8 days) at state
        ("facility_issues", 3, 336),   # 336 hours (14 days) at national
        
        # Medium priority: billing_dispute
        ("billing_dispute", 1, 120),   # 120 hours (5 days) at district
        ("billing_dispute", 2, 240),   # 240 hours (10 days) at state
        ("billing_dispute", 3, 336),   # 336 hours (14 days) at national
        
        # Lower priority: other
        ("other", 1, 168),             # 168 hours (7 days) at district
        ("other", 2, 240),             # 240 hours (10 days) at state
        ("other", 3, 336),             # 336 hours (14 days) at national
    ]
    
    created_count = 0
    updated_count = 0
    
    for category_str, level, hours in default_rules:
        category = models.ComplaintCategory(category_str)
        
        # Check if rule exists
        existing = db.query(models.SLARule).filter(
            models.SLARule.category == category,
            models.SLARule.escalation_level == level
        ).first()
        
        if existing:
            # Update if different
            if existing.time_limit_hours != hours:
                existing.time_limit_hours = hours
                updated_count += 1
                print(f"Updated: {category_str} level {level}: {hours}h")
        else:
            # Create new rule
            rule = models.SLARule(
                category=category,
                escalation_level=level,
                time_limit_hours=hours,
            )
            db.add(rule)
            created_count += 1
            print(f"Created: {category_str} level {level}: {hours}h")
    
    db.commit()
    db.close()
    
    print(f"\nSLA Rules seeded: {created_count} created, {updated_count} updated")
    return created_count + updated_count


if __name__ == "__main__":
    seed_sla_rules()
