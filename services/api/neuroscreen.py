import json
from services.api import models


def score_neuroscreen(version: models.NeuroscreenVersion, responses: dict) -> tuple[int, models.NeuroscreenBand, str]:
    """Deterministic scoring using version rules.

    Returns:
        (raw_score, band, guidance_text)
    """
    rules = json.loads(version.scoring_rules_json)
    weights = rules.get("question_weights", {})
    thresholds = rules.get("band_thresholds", {})

    # Compute raw score
    raw_score = 0
    for q_id, weight in weights.items():
        response_value = responses.get(q_id, 0)
        raw_score += response_value * weight

    # Determine band
    band = None
    for band_name, (min_score, max_score) in thresholds.items():
        if min_score <= raw_score <= max_score:
            band = models.NeuroscreenBand(band_name)
            break

    if band is None:
        band = models.NeuroscreenBand.low

    # Generate guidance with mandatory screening disclaimer
    if band == models.NeuroscreenBand.high:
        guidance = (
            "Results indicate higher likelihood. We recommend a professional evaluation for comprehensive assessment. "
            "This is a screening, not a diagnosis."
        )
    elif band == models.NeuroscreenBand.medium:
        guidance = (
            "Results indicate moderate likelihood. Consider consulting a specialist for further evaluation. "
            "This is a screening, not a diagnosis."
        )
    else:
        guidance = (
            "Results indicate lower likelihood based on this screening. Continue monitoring developmental progress. "
            "This is a screening, not a diagnosis."
        )

    return raw_score, band, guidance
