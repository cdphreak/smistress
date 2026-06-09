from __future__ import annotations

from app.db.models.character import CharacterModel
from app.db.models.economy import EconomyState
from app.db.models.profile import SubProfile
from app.llm.types import ChatMessage

_JSON_SCHEMA = (
    'Return ONE JSON object and nothing else, of the form:\n'
    '{\n'
    '  "tasks": [\n'
    '    {"description": str, "proof": "photo"|"video"|"timer"|"honor"|"none",\n'
    '     "merit_reward": int, "merit_fail_penalty": int, "merit_miss_penalty": int,\n'
    '     "difficulty": "gentle"|"standard"|"demanding"}\n'
    '  ],\n'
    '  "lines": [\n'
    '    {"unit": "assignment"|"reminder", "event": "task_drop"|"no_task"|"batch_window",\n'
    '     "merit_band": "low"|"mid"|"high"|"any",\n'
    '     "time_of_day": "morning"|"day"|"evening"|"night"|"any", "text": str}\n'
    '  ],\n'
    '  "punishments": [\n'
    '    {"type": "penance_task"|"chastity_extension"|"token_confiscation",\n'
    '     "severity": 1|2|3, "reason": str}\n'
    '  ]\n'
    '}\n'
    'For "task_drop" lines, include the literal placeholder {task}. Lines and '
    'punishment reasons are cold, mechanical, in-persona (never warm). A punishment '
    '"reason" is the penance/consequence text (e.g. "Write 50 lines: ...").'
)


def _profile_brief(profile: SubProfile, character: CharacterModel | None) -> str:
    goals = ", ".join(g.title for g in profile.goals if g.title) or "none recorded"
    favs = ", ".join(
        k.kink for k in profile.kinks if k.rating and k.rating.value in ("favorite", "like")
    ) or "none recorded"
    voice = "the Mistress"
    if character is not None:
        voice = (
            f"{character.honorific or 'the Mistress'} "
            f"(strict={character.strictness}, warmth={character.warmth})"
        )
    return (
        f"Sub's goals: {goals}.\n"
        f"Favoured kinks: {favs}.\n"
        f"Intensity ceiling: {profile.intensity_ceiling}/100.\n"
        f"Voice: {voice}."
    )


def build_generation_prompt(
    profile: SubProfile,
    character: CharacterModel | None,
    econ: EconomyState | None,
    *,
    task_count: int,
    line_count: int,
    punishment_count: int,
) -> list[ChatMessage]:
    merit = econ.merit if econ is not None else 0
    system = (
        "You are pre-generating offline material for a consensual adult D/s habit-training "
        "app. The Mistress is away; her deterministic 'drones' will serve this material with "
        "no model present. Produce varied, in-character content that respects the sub's "
        "limits and intensity ceiling. Keep tasks concrete and safe."
    )
    user = (
        f"{_profile_brief(profile, character)}\n"
        f"Current merit: {merit} (band drives tone).\n\n"
        f"Generate {task_count} task-pool items, {line_count} drone lines, and "
        f"{punishment_count} punishments.\n\n"
        f"{_JSON_SCHEMA}"
    )
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]
