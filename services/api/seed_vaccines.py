"""Seed vaccine schedule rules (India's UIP schedule - simplified for MVP)."""
from services.api import models
from services.api.db import SessionLocal


def seed_vaccine_schedules():
    db = SessionLocal()
    try:
        # Check if already seeded
        if db.query(models.VaccineScheduleRule).first():
            print("Vaccine schedules already seeded")
            return

        # Simplified UIP schedule (age in days from birth)
        schedules = [
            ("BCG", 1, 0),  # at birth
            ("OPV", 1, 0),  # at birth
            ("Hepatitis B", 1, 0),  # at birth
            ("DPT", 1, 42),  # 6 weeks
            ("OPV", 2, 42),
            ("Hepatitis B", 2, 42),
            ("DPT", 2, 70),  # 10 weeks
            ("OPV", 3, 70),
            ("DPT", 3, 98),  # 14 weeks
            ("OPV", 4, 98),
            ("Hepatitis B", 3, 98),
            ("MMR", 1, 270),  # 9 months
            ("DPT", 4, 540),  # 18 months (booster)
            ("OPV", 5, 540),
            ("MMR", 2, 540),
        ]

        for vax, dose, days in schedules:
            db.add(models.VaccineScheduleRule(vaccine_name=vax, dose_number=dose, due_age_days=days))

        # Seed milestones
        milestones_data = [
            (2, "Smiles, follows objects with eyes"),
            (4, "Holds head steady, reaches for toys"),
            (6, "Rolls over, begins to sit with support"),
            (9, "Crawls, stands with support"),
            (12, "First words, walks with assistance"),
            (18, "Walks independently, simple words"),
            (24, "Runs, two-word phrases"),
        ]

        for age, desc in milestones_data:
            db.add(models.Milestone(age_months=age, description=desc))

        db.commit()
        print("Seeded vaccine schedules and milestones")
    finally:
        db.close()


if __name__ == "__main__":
    seed_vaccine_schedules()
