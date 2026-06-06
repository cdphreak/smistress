from __future__ import annotations

# 0-4 agreement scale: 0 = strongly disagree, 4 = strongly agree.
MAX_ANSWER = 4

ARCHETYPES: tuple[str, ...] = (
    "submissive",
    "slave",
    "brat",
    "pet",
    "masochist",
    "degradee",
    "rope_bunny",
)

# Each statement measures exactly one archetype. Two statements per archetype.
QUESTIONNAIRE: tuple[dict[str, str], ...] = (
    {"id": "q1", "archetype": "submissive", "text": "I feel most at ease when someone else is in charge."},  # noqa: E501
    {"id": "q2", "archetype": "submissive", "text": "Following clear instructions brings me satisfaction."},  # noqa: E501
    {"id": "q3", "archetype": "slave", "text": "I want to devote myself entirely to another's service."},  # noqa: E501
    {"id": "q4", "archetype": "slave", "text": "Being owned and used for someone's benefit appeals to me."},  # noqa: E501
    {"id": "q5", "archetype": "brat", "text": "I enjoy provoking a reaction by misbehaving."},
    {"id": "q6", "archetype": "brat", "text": "Being made to comply after I resist is exciting."},
    {"id": "q7", "archetype": "pet", "text": "I like being cared for and treated as a cherished pet."},  # noqa: E501
    {"id": "q8", "archetype": "pet", "text": "Affection and praise motivate me more than strictness."},  # noqa: E501
    {"id": "q9", "archetype": "masochist", "text": "Physical discomfort can be pleasurable to me."},  # noqa: E501
    {"id": "q10", "archetype": "masochist", "text": "I crave intense sensation, including pain."},
    {"id": "q11", "archetype": "degradee", "text": "Humiliation and verbal degradation arouse me."},  # noqa: E501
    {"id": "q12", "archetype": "degradee", "text": "Being talked down to during a scene excites me."},  # noqa: E501
    {"id": "q13", "archetype": "rope_bunny", "text": "Being bound and restrained appeals to me."},
    {"id": "q14", "archetype": "rope_bunny", "text": "I enjoy the helplessness of being tied up."},
)

_VALID_IDS = frozenset(q["id"] for q in QUESTIONNAIRE)


def unknown_answer_ids(raw_answers: dict[str, int]) -> set[str]:
    """Return any answer keys that are not real questionnaire statement ids."""
    return set(raw_answers) - _VALID_IDS


def score_archetypes(raw_answers: dict[str, int]) -> dict[str, int]:
    """Compute 0-100 percentages per archetype from raw 0-4 answers.

    Unanswered (or absent) statements count as 0. Each archetype's score is the
    mean of its statements' answers, scaled to 0-100 and rounded.
    """
    buckets: dict[str, list[int]] = {a: [] for a in ARCHETYPES}
    for q in QUESTIONNAIRE:
        buckets[q["archetype"]].append(int(raw_answers.get(q["id"], 0)))
    return {
        arch: round(sum(vals) / (len(vals) * MAX_ANSWER) * 100) if vals else 0
        for arch, vals in buckets.items()
    }
