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
)

# Matched only when one of these is the ENTIRE message, so "the red dress" or
# "i'm done with my report" do not trip the stop. "i'm done" is ambiguous in prose
# (task completion vs. a real stop), so it only counts as a safeword when said alone.
SAFEWORD_STANDALONE: tuple[str, ...] = ("red", "i'm done")

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
