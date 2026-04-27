"""Input/output guardrails for the PawPal+ agent.

Two responsibilities:
1. Sanity-check tool inputs (durations, frequencies, categories) so the agent
   can't put nonsensical data into the system.
2. Detect when the user is asking for something the agent shouldn't answer
   (vet diagnosis, dosage advice) so we can deflect to a human professional.
"""

from dataclasses import dataclass
import re
from typing import Optional

VALID_CATEGORIES = {"walk", "feeding", "meds", "grooming", "enrichment"}
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_FREQUENCIES = {"daily", "weekly", "as-needed"}

MIN_DURATION = 1
MAX_DURATION = 240  # 4 hours — anything longer is likely a mistake


# Patterns that indicate a request the agent should refuse and redirect.
# Kept narrow so that benign questions ("when should I walk my dog?") aren't
# blocked. The agent is allowed to discuss general care; it must not diagnose,
# prescribe, or give dosage advice.
DIAGNOSIS_PATTERNS = [
    r"\bdiagnos(e|is|ing)\b",
    r"\b(what'?s?|what\s+is)\s+wrong\s+with\s+(my|the)\b",
    r"\bdoes\s+(my|the)\s+\w+\s+have\s+(cancer|diabetes|kidney|liver|heart\s+disease)",
    r"\bwhat\s+disease\b",
]

DOSAGE_PATTERNS = [
    r"\bhow\s+much\s+(\w+\s+)?(medication|medicine|drug|insulin|tylenol|ibuprofen|benadryl)",
    r"\bwhat\s+dose\s+of\b",
    r"\bdosage\s+for\b",
    r"\bcan\s+i\s+give\s+(my|the)\s+\w+\s+(human|my)\s+\w+",
]


@dataclass
class GuardrailResult:
    allowed: bool
    reason: Optional[str] = None
    safe_response: Optional[str] = None  # what the agent should say instead


def check_user_input(text: str) -> GuardrailResult:
    """Inspect a user message for requests we shouldn't answer."""
    lower = text.lower()

    for pattern in DIAGNOSIS_PATTERNS:
        if re.search(pattern, lower):
            return GuardrailResult(
                allowed=False,
                reason="diagnosis_request",
                safe_response=(
                    "I can't diagnose health conditions — that's a job for your vet. "
                    "I can help you track symptoms, schedule a vet appointment as a task, "
                    "or share general care information from my knowledge base. "
                    "If your pet seems unwell, please call your vet."
                ),
            )

    for pattern in DOSAGE_PATTERNS:
        if re.search(pattern, lower):
            return GuardrailResult(
                allowed=False,
                reason="dosage_request",
                safe_response=(
                    "I won't give specific medication dosages — only your vet should set those. "
                    "I can remind you about the cadence your vet has already prescribed "
                    "(e.g., 'monthly heartworm pill') and help you build that into a schedule."
                ),
            )

    return GuardrailResult(allowed=True)


def validate_task_input(
    name: str,
    category: str,
    duration: int,
    priority: str,
    frequency: str,
) -> GuardrailResult:
    """Validate fields before creating a Task."""
    if not name or not name.strip():
        return GuardrailResult(allowed=False, reason="Task name cannot be empty.")
    if len(name) > 80:
        return GuardrailResult(allowed=False, reason="Task name is too long (max 80 chars).")

    if category not in VALID_CATEGORIES:
        return GuardrailResult(
            allowed=False,
            reason=f"Category must be one of {sorted(VALID_CATEGORIES)}, got {category!r}.",
        )

    if not isinstance(duration, int) or duration < MIN_DURATION or duration > MAX_DURATION:
        return GuardrailResult(
            allowed=False,
            reason=f"Duration must be an integer between {MIN_DURATION} and {MAX_DURATION} minutes.",
        )

    if priority not in VALID_PRIORITIES:
        return GuardrailResult(
            allowed=False,
            reason=f"Priority must be one of {sorted(VALID_PRIORITIES)}.",
        )

    if frequency not in VALID_FREQUENCIES:
        return GuardrailResult(
            allowed=False,
            reason=f"Frequency must be one of {sorted(VALID_FREQUENCIES)}.",
        )

    return GuardrailResult(allowed=True)


def append_safety_footer(response_text: str) -> str:
    """Add a disclaimer when the response touches health-adjacent topics."""
    health_keywords = [
        "vet", "medication", "meds", "symptom", "ill", "sick", "vomit",
        "diarrhea", "limp", "lethargic", "bleeding", "seizure",
    ]
    if any(kw in response_text.lower() for kw in health_keywords):
        return response_text + (
            "\n\n_Note: PawPal+ is a planning assistant, not a substitute for "
            "veterinary care. When in doubt, contact your vet._"
        )
    return response_text
