import json
import re

from services.api import models


# Red-flag keywords/patterns that always force category=emergency
RED_FLAG_PATTERNS = [
    r"\bchest pain\b",
    r"\bshortness of breath\b",
    r"\bunconscious\b",
    r"\bseizure\b",
    r"\bsevere bleeding\b",
    r"\bstroke\b",
    r"\bsuicide\b",
    r"\bhigh fever.*stiff neck\b",
    r"\bpregnancy.*bleeding\b",
]

# Forbidden diagnosis terms (must not appear in guidance)
DIAGNOSIS_TERMS = [
    "diagnosis",
    "cancer",
    "stroke confirmed",
    "you have",
    "diagnosed with",
]


def detect_red_flags(symptom_text: str, followup_answers: dict) -> list[str]:
    """Returns list of red-flag indicators matched."""
    flags = []
    combined = symptom_text.lower() + " " + json.dumps(followup_answers).lower()

    for pattern in RED_FLAG_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            flags.append(pattern)

    return flags


def generate_triage(
    *, symptom_text: str, followup_answers: dict
) -> tuple[models.TriageCategory, list[str], str]:
    """Run red-flag detection and generate guidance.

    Returns:
        (category, red_flags, guidance_text)
    """
    red_flags = detect_red_flags(symptom_text, followup_answers)

    if red_flags:
        category = models.TriageCategory.emergency
        guidance = (
            "Based on your symptoms, we recommend seeking immediate emergency care. "
            "Please go to the nearest emergency room or call emergency services."
        )
    else:
        # Simple heuristic for MVP
        if "fever" in symptom_text.lower() or "pain" in symptom_text.lower():
            category = models.TriageCategory.phc
            guidance = (
                "We recommend scheduling a visit with your primary health center (PHC) "
                "to assess your symptoms. This is informational guidance only."
            )
        else:
            category = models.TriageCategory.self_care
            guidance = (
                "Your symptoms may be manageable with self-care. "
                "Monitor your condition and consult a healthcare provider if symptoms worsen. "
                "This is informational guidance only."
            )

    # Validate guidance text does not contain diagnosis language
    _validate_no_diagnosis_language(guidance)

    return category, red_flags, guidance


def _validate_no_diagnosis_language(text: str):
    """Raises ValueError if text contains forbidden diagnosis terms."""
    lower = text.lower()
    for term in DIAGNOSIS_TERMS:
        if term.lower() in lower:
            raise ValueError(f"Guidance contains forbidden diagnosis term: {term}")
