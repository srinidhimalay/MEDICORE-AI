"""
Triage assessment system for medical chatbot.
Classifies queries into urgency levels.
"""

import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)


class TriageLevel:
    EMERGENCY = "emergency"       # Call 911/108 immediately
    URGENT = "urgent"             # See doctor within 24 hours
    SEMI_URGENT = "semi_urgent"   # See doctor within 1-3 days
    ROUTINE = "routine"           # Self-care, see doctor if persists
    INFORMATIONAL = "info"        # General health question, no symptoms


# Color and display mapping for frontend
TRIAGE_DISPLAY = {
    "emergency": {"color": "#ff0000", "label": "Emergency", "icon": "🔴"},
    "urgent": {"color": "#ff6600", "label": "Urgent", "icon": "🟠"},
    "semi_urgent": {"color": "#ffcc00", "label": "Semi-Urgent", "icon": "🟡"},
    "routine": {"color": "#00cc00", "label": "Routine", "icon": "🟢"},
    "info": {"color": "#0088ff", "label": "Informational", "icon": "🔵"},
}


async def assess_triage_level(message: str, llm_service) -> dict:
    """
    Assess clinical urgency level based on the user's message.

    Args:
        message: User's medical query
        llm_service: LLM service instance for classification

    Returns:
        Dict with 'level', 'reason', 'color', 'label', 'icon'
    """
    try:
        prompt = f"""Based on this patient message, assess the clinical urgency level.

Patient message: "{message}"

Classify as exactly ONE of these levels:
- EMERGENCY: Life-threatening symptoms happening now (chest pain with shortness of breath, stroke symptoms, severe allergic reaction, active suicidal ideation, severe bleeding, loss of consciousness)
- URGENT: Needs medical attention within 24 hours (high fever over 103F/39.4C, severe pain, signs of infection with fever, persistent vomiting, head injury with symptoms)
- SEMI_URGENT: Should see doctor within 1-3 days (persistent symptoms over a week, moderate pain not improving, new concerning symptoms, medication side effects)
- ROUTINE: Self-care appropriate, see doctor if persists beyond 1-2 weeks (mild cold symptoms, minor aches, general wellness questions about symptoms)
- INFO: General health question with no active symptoms described (asking about a condition, medication information, health tips, prevention)

Respond in this exact format (two lines only):
LEVEL
One sentence reason

Example:
URGENT
High fever with body aches suggests possible infection requiring medical evaluation within 24 hours."""

        completion = await llm_service._chat_completion(
            model=llm_service.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a medical triage classifier. Classify patient urgency accurately. Respond with exactly the level and one sentence reason."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=100,
        )

        result = completion.choices[0].message.content.strip()
        lines = result.split("\n", 1)

        # Parse level
        level_text = lines[0].strip().upper().replace(" ", "_")
        reason = lines[1].strip() if len(lines) > 1 else "Assessment based on described symptoms."

        # Map to valid level
        level_map = {
            "EMERGENCY": TriageLevel.EMERGENCY,
            "URGENT": TriageLevel.URGENT,
            "SEMI_URGENT": TriageLevel.SEMI_URGENT,
            "ROUTINE": TriageLevel.ROUTINE,
            "INFO": TriageLevel.INFORMATIONAL,
            "INFORMATIONAL": TriageLevel.INFORMATIONAL,
        }

        level = level_map.get(level_text, TriageLevel.ROUTINE)
        display = TRIAGE_DISPLAY.get(level, TRIAGE_DISPLAY["routine"])

        logger.info(f"Triage assessment: {level} - {reason[:80]}")

        return {
            "level": level,
            "reason": reason,
            "color": display["color"],
            "label": display["label"],
            "icon": display["icon"],
        }

    except Exception as e:
        logger.error(f"Triage assessment error: {e}", exc_info=True)
        return {
            "level": TriageLevel.ROUTINE,
            "reason": "Unable to assess urgency. Please consult a healthcare provider if concerned.",
            "color": TRIAGE_DISPLAY["routine"]["color"],
            "label": TRIAGE_DISPLAY["routine"]["label"],
            "icon": TRIAGE_DISPLAY["routine"]["icon"],
        }
