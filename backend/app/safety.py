"""
Safety filters and content moderation for medical chatbot.
Two-tier emergency detection + mental health pathway.
"""

import logging
import re
import asyncio
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Emergency keywords requiring immediate medical attention
EMERGENCY_KEYWORDS = [
    # Suicide/self-harm
    "suicide", "kill myself", "end my life", "want to die", "self harm",
    "hurt myself", "suicidal",

    # Cardiac emergencies
    "chest pain", "heart attack", "cardiac arrest", "crushing chest",

    # Stroke
    "stroke", "can't move", "face drooping", "slurred speech",

    # Breathing
    "can't breathe", "difficulty breathing", "choking", "suffocating",

    # Bleeding/trauma
    "severe bleeding", "heavy bleeding", "bleeding won't stop",
    "major injury", "severe trauma",

    # Consciousness
    "unconscious", "passed out", "unresponsive", "losing consciousness",

    # Poisoning/overdose
    "overdose", "poisoning", "swallowed", "toxic",

    # Allergic reactions
    "severe allergic", "anaphylaxis", "throat swelling", "lips swelling",

    # Additional emergency keywords
    "seizure", "convulsion", "can't stop shaking",
    "blood in stool", "vomiting blood", "coughing up blood",
    "sudden vision loss", "can't see", "sudden blindness",
    "severe burn", "chemical burn",
    "head injury", "hit my head", "concussion",
    "can't move my", "paralysis", "numb on one side",
    "high fever baby", "infant not breathing",
    "diabetic emergency", "blood sugar very low",
    "severe dehydration", "haven't urinated",
]

# Mental health indicators (non-emergency)
MENTAL_HEALTH_INDICATORS = [
    "anxiety", "anxious", "depressed", "depression", "stressed",
    "panic attack", "insomnia", "can't sleep", "lonely", "hopeless",
    "overwhelmed", "burnout", "grief", "trauma", "ptsd",
    "eating disorder", "ocd", "bipolar", "mood swings",
    "feeling down", "no motivation", "worthless", "empty inside",
    "nervous", "worried all the time", "social anxiety",
]

# Inappropriate content keywords
INAPPROPRIATE_KEYWORDS = [
    "hack", "exploit", "illegal drug", "how to make", "bomb",
    "self-harm instructions", "suicide method", "weapons"
]

EMERGENCY_RESPONSE = """🚨 **EMERGENCY ALERT** 🚨

Your message suggests a potentially life-threatening situation.

**IMMEDIATE ACTION REQUIRED:**

📞 **Call Emergency Services NOW:**
• Ambulance: 108
• Medical Helpline: 102
• Police: 100
• General Emergency: 112

🏥 **Go to the nearest Emergency Room immediately**

💬 **Crisis Helplines:**
• iCall: 9152987821
• Vandrevala Foundation: 1860-2662-345
• AASRA: 91-22-27546669

⚠ **This chatbot is NOT a substitute for emergency medical care.**

Please seek immediate professional help. Your life matters."""

MENTAL_HEALTH_PREAMBLE = """💙 **I hear you, and your feelings are valid.**

While I'm primarily a medical information assistant, I want you to know that mental health is just as important as physical health. Here are some resources that can help:

**Professional Support:**
• **iCall:** 9152987821
• **Vandrevala Foundation:** 1860-2662-345
• **NIMHANS Helpline:** 080-46110007
• **AASRA:** 91-22-27546669

**Self-care suggestions:**
• Talk to someone you trust about how you're feeling
• Practice deep breathing or grounding exercises
• Maintain regular sleep, nutrition, and gentle movement
• Consider reaching out to a mental health professional

---

"""


def check_emergency_keywords(message: str) -> bool:
    """
    Tier 1: Fast keyword pre-screen for potential emergencies.
    Returns True if emergency keywords are found.
    """
    message_lower = message.lower()
    for keyword in EMERGENCY_KEYWORDS:
        if keyword in message_lower:
            return True
    return False


async def assess_emergency_context(message: str, llm_service) -> str:
    """
    Tier 2: LLM-based contextual assessment to reduce false positives.
    Determines if the emergency is ACTIVE vs. past/hypothetical/about someone else.

    Returns: "ACTIVE_EMERGENCY", "NOT_EMERGENCY", or "UNCLEAR"
    """
    try:
        prompt = f"""Assess if this message describes an ACTIVE medical emergency happening RIGHT NOW to the person writing it.

Message: "{message}"

Consider:
- Is this happening RIGHT NOW or describing a past event?
- Is this about the writer themselves or about someone else (friend, family)?
- Is the severity described as life-threatening?
- Is this a question about a condition vs. an active crisis?

Examples:
- "I'm having chest pain right now" -> ACTIVE_EMERGENCY
- "I had chest pain last week" -> NOT_EMERGENCY
- "What causes chest pain?" -> NOT_EMERGENCY
- "My friend had a heart attack" -> NOT_EMERGENCY
- "I want to kill myself" -> ACTIVE_EMERGENCY
- "What is a stroke?" -> NOT_EMERGENCY
- "I think I'm having a stroke, my face feels numb" -> ACTIVE_EMERGENCY

Respond with ONLY one of:
ACTIVE_EMERGENCY
NOT_EMERGENCY
UNCLEAR"""

        completion = await llm_service._chat_completion(
            model=llm_service.model,
            messages=[
                {
                    "role": "system",
                    "content": "You assess medical emergency severity. Respond with exactly one classification. When in doubt, classify as ACTIVE_EMERGENCY for safety."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=10,
        )

        result = completion.choices[0].message.content.strip().upper()

        if "ACTIVE" in result:
            return "ACTIVE_EMERGENCY"
        elif "NOT" in result:
            return "NOT_EMERGENCY"
        else:
            return "UNCLEAR"

    except Exception as e:
        logger.error(f"Emergency context assessment error: {e}")
        return "UNCLEAR"  # Default to unclear (will show emergency alert for safety)


def check_mental_health(message: str) -> bool:
    """Check if message contains mental health indicators."""
    message_lower = message.lower()
    for indicator in MENTAL_HEALTH_INDICATORS:
        if indicator in message_lower:
            return True
    return False


def check_emergency(message: str) -> Tuple[bool, str]:
    """
    Tier 1 only emergency check (synchronous, for backwards compatibility).
    Use check_emergency_tiered() for the full two-tier system.
    """
    if check_emergency_keywords(message):
        logger.warning("⚠ Emergency keyword detected (Tier 1)")
        return True, EMERGENCY_RESPONSE
    return False, ""


async def check_emergency_tiered(message: str, llm_service) -> Tuple[bool, str]:
    """
    Two-tier emergency detection:
    - Tier 1: Fast keyword scan
    - Tier 2: LLM contextual assessment (only if Tier 1 triggers)

    Returns:
        (is_emergency, emergency_response)
    """
    # Tier 1: Keyword pre-screen
    if not check_emergency_keywords(message):
        return False, ""

    logger.warning("⚠ Emergency keyword detected (Tier 1), running contextual assessment...")

    # Tier 2: LLM contextual assessment
    assessment = await assess_emergency_context(message, llm_service)

    if assessment == "NOT_EMERGENCY":
        logger.info("✓ Tier 2 assessment: NOT an active emergency (past/hypothetical/informational)")
        return False, ""
    else:
        # ACTIVE_EMERGENCY or UNCLEAR - show emergency alert for safety
        logger.warning(f"🚨 Tier 2 assessment: {assessment} - showing emergency alert")
        return True, EMERGENCY_RESPONSE


def check_inappropriate_content(message: str) -> Tuple[bool, str]:
    """Check if message contains inappropriate content."""
    message_lower = message.lower()

    for keyword in INAPPROPRIATE_KEYWORDS:
        if keyword in message_lower:
            logger.warning(f"⚠ Inappropriate content detected: '{keyword}'")

            rejection = """I'm designed to provide educational medical information only.

I cannot assist with:
❌ Illegal activities
❌ Self-harm instructions
❌ Harmful content
❌ Dangerous substances

If you have legitimate medical questions, I'm here to help.

For mental health support, please contact:
• iCall: 9152987821
• Vandrevala Foundation: 1860-2662-345
• AASRA: 91-22-27546669"""

            return True, rejection

    return False, ""


def validate_message_length(message: str) -> Tuple[bool, str]:
    """Validate message length."""
    message_stripped = message.strip()

    if not message_stripped:
        return False, "Please provide a valid message."

    if len(message_stripped) < 3:
        return False, "Your message is too short. Please provide more details."

    if len(message_stripped) > 2000:
        return False, "Your message is too long (max 2000 characters). Please shorten it."

    return True, ""


def validate_message(message: str) -> Tuple[bool, str]:
    """
    Synchronous message validation (backwards compatible).
    Uses Tier 1 only for emergency detection.
    """
    # Check message length
    is_valid_length, length_error = validate_message_length(message)
    if not is_valid_length:
        return False, length_error

    # Check for emergency keywords (Tier 1 only)
    is_emergency, emergency_msg = check_emergency(message)
    if is_emergency:
        return False, emergency_msg

    # Check for inappropriate content
    is_inappropriate, inappropriate_msg = check_inappropriate_content(message)
    if is_inappropriate:
        return False, inappropriate_msg

    # All checks passed
    return True, ""


async def validate_message_async(message: str, llm_service) -> Tuple[bool, str, Optional[str]]:
    """
    Async message validation with two-tier emergency detection and mental health pathway.

    Returns:
        (is_valid, response_message, mental_health_preamble)
        - is_valid: True if message can proceed to normal processing
        - response_message: If invalid, the rejection/emergency message
        - mental_health_preamble: If mental health detected, preamble to prepend to response
    """
    # Check message length
    is_valid_length, length_error = validate_message_length(message)
    if not is_valid_length:
        return False, length_error, None

    # Check for inappropriate content (before emergency to catch "suicide method" etc.)
    is_inappropriate, inappropriate_msg = check_inappropriate_content(message)
    if is_inappropriate:
        return False, inappropriate_msg, None

    # Two-tier emergency detection
    is_emergency, emergency_msg = await check_emergency_tiered(message, llm_service)
    if is_emergency:
        return False, emergency_msg, None

    # Check for mental health indicators (non-emergency)
    mental_health_preamble = None
    if check_mental_health(message):
        logger.info("💙 Mental health indicators detected, will add supportive preamble")
        mental_health_preamble = MENTAL_HEALTH_PREAMBLE

    # All checks passed
    return True, "", mental_health_preamble


def sanitize_input(text: str) -> str:
    """Sanitize user input by removing potentially harmful content."""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)

    # Remove control characters
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)

    # Trim
    text = text.strip()

    return text
