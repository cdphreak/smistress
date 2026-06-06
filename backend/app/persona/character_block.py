from __future__ import annotations

from app.db.models.character import CharacterModel

# Pretty labels for archetype blend keys.
_ARCHETYPE_LABELS = {
    "aristocrat": "Aristocrat",
    "governess": "Governess",
    "owner": "Owner",
    "drill_instructor": "Drill Instructor",
}

# Per-dial phrasing for the low / moderate / high buckets.
_DIAL_PHRASES: dict[str, tuple[str, str, str]] = {
    "warmth": ("reserved and cool", "measured warmth", "openly affectionate"),
    "strictness": ("lenient on standards", "firm", "exacting and demanding"),
    "sadism": (
        "takes no pleasure in discomfort",
        "mildly enjoys discomfort",
        "relishes discomfort",
    ),
    "formality": ("casual", "proper", "rigidly formal"),
    "verbosity": ("terse", "balanced", "expansive and explanatory"),
    "crudeness": ("refined language", "plain language", "vulgar language"),
    "wit": ("humorless", "dryly amused", "sharp, cutting wit"),
}

_DIAL_ORDER = (
    "warmth",
    "strictness",
    "sadism",
    "formality",
    "verbosity",
    "crudeness",
    "wit",
)


def _bucket(value: int) -> str:
    if value <= 33:
        return "low"
    if value >= 67:
        return "high"
    return "moderate"


def _describe_dial(name: str, value: int) -> str:
    low, mid, high = _DIAL_PHRASES[name]
    phrase = {"low": low, "moderate": mid, "high": high}[_bucket(value)]
    return f"- {name.capitalize()} ({value}/100, {_bucket(value)}): {phrase}."


def _describe_blend(blend: dict[str, int]) -> str:
    parts = sorted(blend.items(), key=lambda kv: kv[1], reverse=True)
    rendered = ", ".join(
        f"{_ARCHETYPE_LABELS.get(k, k.replace('_', ' ').title())} ({w})" for k, w in parts
    )
    return rendered or "unspecified"


def render_character_block(char: CharacterModel) -> str:
    """Render the configurable character model (spec 5A) into a stable persona block.

    This is her core identity; the disposition (rendered separately) only shifts her
    register around this center, never who she fundamentally is.
    """
    name_line = f"You are {char.name}, " if char.name else "You are "
    lines = [
        "## WHO YOU ARE",
        f"{name_line}known as {char.honorific}. You address the user as \"{char.address_term}\". "
        f"Your pronouns are {char.pronouns}.",
        f"Your character is a blend of: {_describe_blend(char.archetype_blend)}.",
        "",
        "## YOUR VOICE (dials set your center; your mood swings you around it)",
    ]
    lines.extend(_describe_dial(name, getattr(char, name)) for name in _DIAL_ORDER)
    if char.signature_flavor:
        lines.append("")
        lines.append(f"## SIGNATURE\n{char.signature_flavor}")
    return "\n".join(lines)
