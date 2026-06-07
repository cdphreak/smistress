from __future__ import annotations

# Recognized safeword phrases, matched as a substring of the (lowercased) message.
# Conservative set to avoid false positives; the always-available panic *button*
# (REST endpoint) is the unambiguous primary path.
SAFEWORD_PHRASES: tuple[str, ...] = (
    "safeword",
    "stop the scene",
    "end the scene",
    "i want to stop",
    "i need to stop",
    "i'm done",
)

# The classic traffic-light safeword: matched only when it is the entire message,
# so "the red dress" does not trip it.
SAFEWORD_STANDALONE: tuple[str, ...] = ("red",)

# Signs of genuine distress / self-harm. Substring match (lowercased).
CRISIS_PHRASES: tuple[str, ...] = (
    "kill myself",
    "want to die",
    "end my life",
    "suicidal",
    "self-harm",
    "self harm",
    "hurt myself",
    "hurting myself",
    "no reason to live",
)


def detect_safeword(text: str) -> bool:
    t = text.strip().lower()
    if t in SAFEWORD_STANDALONE:
        return True
    return any(phrase in t for phrase in SAFEWORD_PHRASES)


def detect_crisis(text: str) -> bool:
    t = text.lower()
    return any(phrase in t for phrase in CRISIS_PHRASES)
