"""Seed NeuroScreen scoring versions."""
import json
from services.api import models
from services.api.db import SessionLocal


def seed_neuroscreen_versions():
    db = SessionLocal()
    try:
        # Check if already seeded
        if db.query(models.NeuroscreenVersion).first():
            print("NeuroScreen versions already seeded")
            return

        # Version 1: Simple scoring (sum of weighted responses)
        rules_v1 = {
            "question_weights": {
                "q1": 1,
                "q2": 2,
                "q3": 1,
                "q4": 3,
                "q5": 2,
            },
            "band_thresholds": {
                "low": [0, 3],
                "medium": [4, 7],
                "high": [8, 100],
            },
        }

        v1 = models.NeuroscreenVersion(
            name="Autism Screening v1",
            scoring_rules_json=json.dumps(rules_v1),
            is_active=True,
        )
        db.add(v1)
        db.commit()
        print(f"Seeded NeuroScreen version: {v1.id}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_neuroscreen_versions()
