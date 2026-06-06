# Milestone 4 — Persona Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the persona engine — compute the mistress's disposition from merit + recent task outcomes (bounded by the consent ceiling, centered by the Warmth dial), render the configurable character model into a stable persona block, and compile the full system prompt (character + safety/limits + authoritative state verbatim + current disposition + a memory seam) — plus a persona eval harness over the mock provider.

**Architecture:** Pure logic in `app/persona/` (disposition math, character-block rendering, prompt compilation — all unit-testable with no DB), a DB-backed `app/services/persona.py` that gathers authoritative state and produces the disposition + compiled prompt, a read-only `GET /profile/{id}/disposition` endpoint (serves the Addendum A5 disposition line), and a golden-fixture eval harness asserting the deterministic invariants of the compiled prompt + disposition. The chat turn loop and tool execution (`assign_task`, etc.) are **M6** — M4 stops at compiling the prompt and an internal reply path exercised by the harness.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async (read-only here), the existing swappable `LLMProvider` seam (`MockLLMProvider` for tests), FastAPI, pytest. No new dependencies, no migration (reads the M2/M3 schema).

---

## Context

M3 merged: a profile can be created (consent-gated) and populated — kink/limits sheet, toys, goals, SO context, and an editable `character_model` (identity, archetype blend, 7 voice dials incl. Sadism, signature flavor; defaults Governess 70 / Drill Instructor 30, Warmth 30, Strictness 80, Sadism 30, Wit 75). `EconomyState` exists (merit/rank/tokens, default merit 0) and `Task` records carry a `status` (`assigned → in_progress → proof_submitted → verifying → verified_pass | verified_fail | missed`). M4 implements spec **§5** (persona engine: 4-source context assembly, computed disposition) and the *runtime* half of **§5A** (compile the character model into a prompt). The economy mutations that move merit, and the task lifecycle that produces outcomes, are **M6/M7**; M4 only **reads** merit + outcomes.

### What M4 is NOT (boundaries)
- **No tool execution / chat turn loop** (`assign_task`, `adjust_economy`, …) — that is M6. M4 compiles the prompt and can call the provider for a plain reply (no tools), exercised by the harness; it does not persist conversations or mutate state.
- **No Graphiti/memory retrieval** — M5. The compiler takes a `memory` section that is `None`/empty in M4 (a documented seam).
- **No output-filter / safeword interception** — M8. M4 *states* the safety rules in the prompt (hard limits verbatim, ceiling, safeword behavior) but the deterministic enforcement layer is M8.

### Patterns to follow (already established)
- **Async safety:** never trigger lazy relationship IO on `AsyncSession`. Read each entity with an explicit `select(...)` by `profile_id` (as `app/services/profile.py` does for `CharacterModel`/`EconomyState`). Do not access `profile.kinks` etc. lazily.
- **Service/endpoint split:** services are read-only here (no commits — M4 mutates nothing). Endpoints depend on `get_session` and override it in tests via `app.dependency_overrides` (see `tests/api/test_profile_api.py`).
- **LLM seam:** `app/llm/provider.py` `LLMProvider.chat(messages, *, model=None, tools=None) -> ChatResult`; `app/llm/types.py` `ChatMessage(role, content)`, `ChatResult(content, tool_calls)`; `app/llm/mock.py` `MockLLMProvider(scripted=[...])` records `.calls` (list of message lists) and replays scripted `ChatResult`s — ideal for asserting the compiled system prompt.
- **Local dev caveat:** clear `PYTHONHOME`/`PYTHONPATH` in-session before `uv` (see `smistress-dev-environment` memory). Canonical run: `$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; $uv=(Get-Command uv).Source; $bk="C:\Users\phrea\OneDrive\claude\smistress\backend"; & $uv --directory $bk run pytest -q`. Postgres must be up (`docker compose up -d` from repo root). CI unaffected.

## File Structure (all under `backend/`)

New:
- `app/persona/__init__.py` (empty)
- `app/persona/disposition.py` — `DispositionBand`, `Disposition`, pure `compute_disposition(...)` + helpers. No DB.
- `app/persona/character_block.py` — `render_character_block(char)` + dial→descriptor. No DB (takes a `CharacterModel` instance).
- `app/persona/compiler.py` — `compile_system_prompt(...)` assembling the labelled sections. No DB.
- `app/services/persona.py` — DB-backed: `get_disposition`, `build_authoritative_state_block`, `compile_persona_prompt`, `generate_reply`.
- `app/schemas/persona.py` — `DispositionOut`.
- `app/api/persona.py` — `GET /profile/{id}/disposition`.
- Tests: `tests/persona/__init__.py`, `tests/persona/test_disposition.py`, `tests/persona/test_character_block.py`, `tests/persona/test_compiler.py`, `tests/persona/test_persona_service.py`, `tests/persona/test_persona_reply.py`, `tests/persona/fixtures.py`, `tests/persona/test_persona_eval.py`, `tests/api/test_persona_api.py`.

Modify:
- `app/schemas/onboarding.py` — add an `archetype_blend` value-range validator to `CharacterUpdate` (deferred from M3; M4 is the first consumer).
- `app/main.py` — mount the persona router.

---

## Task 1: Disposition value types + pure `compute_disposition`

**Files:**
- Create: `backend/app/persona/__init__.py` (empty), `backend/app/persona/disposition.py`
- Test: `backend/tests/persona/__init__.py` (empty), `backend/tests/persona/test_disposition.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/persona/test_disposition.py`:

```python
from app.db.enums import TaskStatus
from app.persona.disposition import (
    DispositionBand,
    compute_disposition,
)

# Governess default: warmth 30. Ceiling 100 = no clamp unless stated.
WARMTH = 30


def test_neutral_default_band_reflects_low_warmth():
    # merit 0, no history, warmth 30 -> standing 30 -> cool register.
    d = compute_disposition(0, [], warmth=WARMTH, ceiling=100)
    assert d.band is DispositionBand.COOL
    assert d.standing == 30
    assert "no recent activity" in d.reason


def test_high_merit_and_passes_warm():
    d = compute_disposition(
        100, [TaskStatus.VERIFIED_PASS] * 5, warmth=WARMTH, ceiling=100
    )
    # 30 + 100*0.4 + min(10, 2*5)*2.0 = 30 + 40 + 20 = 90 -> warm
    assert d.band is DispositionBand.WARM
    assert d.standing == 90
    assert "on-time" in d.reason


def test_low_merit_and_misses_severe():
    d = compute_disposition(
        -100, [TaskStatus.MISSED, TaskStatus.MISSED], warmth=WARMTH, ceiling=100
    )
    # 30 - 40 + (-6)*2.0 = 30 - 40 - 12 = -22 -> clamp 0 -> severe
    assert d.band is DispositionBand.SEVERE
    assert d.standing == 0
    assert "2 recent misses" in d.reason


def test_ceiling_clamps_severity_even_at_rock_bottom():
    # ceiling 40 => severity (100 - standing) may not exceed 40 => standing >= 60.
    d = compute_disposition(-100, [TaskStatus.MISSED] * 5, warmth=WARMTH, ceiling=40)
    assert d.standing == 60
    assert d.band is DispositionBand.PLEASED  # clamped up, can't go cold


def test_warmth_center_shifts_band():
    # A high-warmth character swings warmer at neutral merit.
    d = compute_disposition(0, [], warmth=80, ceiling=100)
    assert d.standing == 80
    assert d.band is DispositionBand.WARM


def test_line_is_band_register_and_reason():
    d = compute_disposition(0, [TaskStatus.MISSED], warmth=WARMTH, ceiling=100)
    # standing 30 - 2*2 = 26 -> cool; line: "cool · exacting — 1 recent miss"
    assert d.line == f"{d.band.value} · exacting — 1 recent miss"


def test_merit_and_mood_are_clamped_to_bounds():
    # Out-of-range merit is clamped (defensive; economy service enforces bounds in M7).
    d_hi = compute_disposition(9999, [], warmth=WARMTH, ceiling=100)
    d_cap = compute_disposition(100, [], warmth=WARMTH, ceiling=100)
    assert d_hi.standing == d_cap.standing
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/persona/test_disposition.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.persona'`.

- [ ] **Step 3: Implement** — `backend/app/persona/disposition.py`:

```python
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from app.db.enums import TaskStatus

# --- Tunable constants (the disposition model; tune freely) -----------------
MERIT_MIN, MERIT_MAX = -100, 100
MOOD_WINDOW = 5  # number of most-recent resolved tasks that shape short-term mood
MOOD_MIN, MOOD_MAX = -10, 10
MERIT_WEIGHT = 0.4  # merit +/-100 -> +/-40 standing points
MOOD_WEIGHT = 2.0  # mood +/-10 -> +/-20 standing points

# Per-outcome mood contribution (a miss stings most; spec 7).
_OUTCOME_DELTA: dict[TaskStatus, int] = {
    TaskStatus.VERIFIED_PASS: 2,
    TaskStatus.VERIFIED_FAIL: -2,
    TaskStatus.MISSED: -3,
}


class DispositionBand(str, Enum):
    """Warm (pleased) <-> Severe (cold), derived from the final standing score."""

    WARM = "warm"
    PLEASED = "pleased"
    NEUTRAL = "neutral"
    COOL = "cool"
    SEVERE = "severe"


# Short register phrase rendered into the disposition line / prompt.
_REGISTER: dict[DispositionBand, str] = {
    DispositionBand.WARM: "openly pleased",
    DispositionBand.PLEASED: "approving",
    DispositionBand.NEUTRAL: "measured",
    DispositionBand.COOL: "exacting",
    DispositionBand.SEVERE: "cold and severe",
}


@dataclass(frozen=True)
class Disposition:
    band: DispositionBand
    standing: int  # 0 (coldest) .. 100 (warmest), after the ceiling clamp
    reason: str  # short human-readable driver, e.g. "2 recent misses"
    line: str  # "cool · exacting — 2 recent misses" (Addendum A5 disposition line)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def mood_from_outcomes(outcomes: Iterable[TaskStatus]) -> int:
    """Short-term mood: net of the last MOOD_WINDOW resolved task outcomes."""
    recent = list(outcomes)[:MOOD_WINDOW]
    total = sum(_OUTCOME_DELTA.get(o, 0) for o in recent)
    return int(_clamp(total, MOOD_MIN, MOOD_MAX))


def _band(standing: int) -> DispositionBand:
    if standing >= 80:
        return DispositionBand.WARM
    if standing >= 60:
        return DispositionBand.PLEASED
    if standing >= 40:
        return DispositionBand.NEUTRAL
    if standing >= 20:
        return DispositionBand.COOL
    return DispositionBand.SEVERE


def _build_reason(merit: int, outcomes: Iterable[TaskStatus]) -> str:
    recent = list(outcomes)[:MOOD_WINDOW]
    misses = sum(1 for o in recent if o is TaskStatus.MISSED)
    fails = sum(1 for o in recent if o is TaskStatus.VERIFIED_FAIL)
    passes = sum(1 for o in recent if o is TaskStatus.VERIFIED_PASS)
    if misses:
        return f"{misses} recent miss{'es' if misses != 1 else ''}"
    if fails:
        return f"{fails} recent fail{'s' if fails != 1 else ''}"
    if passes:
        return f"{passes} on-time completion{'s' if passes != 1 else ''}"
    if merit >= 40:
        return "strong standing"
    if merit <= -40:
        return "poor standing"
    return "no recent activity"


def compute_disposition(
    merit: int,
    recent_outcomes: Iterable[TaskStatus],
    *,
    warmth: int,
    ceiling: int,
) -> Disposition:
    """disposition = f(merit standing, recent mood), centered on Warmth, clamped by ceiling.

    Dials set her center (Warmth); merit + mood swing her around it; the consent
    ceiling caps how *severe* she can get even at rock-bottom merit (spec 5/9).
    """
    outcomes = list(recent_outcomes)
    merit = int(_clamp(merit, MERIT_MIN, MERIT_MAX))
    warmth = int(_clamp(warmth, 0, 100))
    ceiling = int(_clamp(ceiling, 0, 100))

    mood = mood_from_outcomes(outcomes)
    raw = warmth + merit * MERIT_WEIGHT + mood * MOOD_WEIGHT
    standing = int(_clamp(round(raw), 0, 100))

    # Ceiling clamps severity: severity == 100 - standing must not exceed ceiling.
    min_standing = 100 - ceiling
    if standing < min_standing:
        standing = min_standing

    band = _band(standing)
    reason = _build_reason(merit, outcomes)
    line = f"{band.value} · {_REGISTER[band]} — {reason}"
    return Disposition(band=band, standing=standing, reason=reason, line=line)
```

Also create empty `backend/app/persona/__init__.py` and `backend/tests/persona/__init__.py`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/persona/test_disposition.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/persona/__init__.py backend/app/persona/disposition.py \
        backend/tests/persona/__init__.py backend/tests/persona/test_disposition.py
git commit -m "feat: add computed disposition (merit+mood, ceiling-clamped) (spec 5)"
```

---

## Task 2: Character-block renderer + `archetype_blend` validation

**Files:**
- Create: `backend/app/persona/character_block.py`
- Modify: `backend/app/schemas/onboarding.py` (add a validator to `CharacterUpdate`)
- Test: `backend/tests/persona/test_character_block.py`, append to `backend/tests/test_schemas.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/persona/test_character_block.py`:

```python
from app.db.models.character import CharacterModel
from app.persona.character_block import render_character_block


def _default_character() -> CharacterModel:
    # In-memory ORM instance; mirrors the M2 defaults (no DB needed).
    return CharacterModel(
        honorific="Headmistress",
        address_term="student",
        pronouns="she/her",
        archetype_blend={"governess": 70, "drill_instructor": 30},
        warmth=30,
        strictness=80,
        sadism=30,
        formality=80,
        verbosity=50,
        crudeness=20,
        wit=75,
    )


def test_block_includes_identity_and_address():
    block = render_character_block(_default_character())
    assert "Headmistress" in block
    assert "student" in block
    assert "she/her" in block


def test_block_describes_archetype_blend_in_weight_order():
    block = render_character_block(_default_character())
    # Governess (70) named before Drill Instructor (30).
    assert block.index("Governess") < block.index("Drill Instructor")
    assert "70" in block and "30" in block


def test_block_translates_dials_to_descriptors():
    block = render_character_block(_default_character()).lower()
    # high strictness/wit/formality -> "high"; low crudeness -> "low"; warmth moderate-low.
    assert "strictness" in block
    assert "high" in block
    assert "low" in block


def test_signature_flavor_included_when_present():
    char = _default_character()
    char.signature_flavor = "Quotes Latin proverbs when displeased."
    block = render_character_block(char)
    assert "Latin proverbs" in block


def test_named_character_uses_name():
    char = _default_character()
    char.name = "Vesper"
    assert "Vesper" in render_character_block(char)
```

Append to `backend/tests/test_schemas.py`:

```python
def test_character_update_archetype_blend_bounds():
    from app.schemas.onboarding import CharacterUpdate

    CharacterUpdate(archetype_blend={"governess": 70, "drill_instructor": 30})  # ok
    with pytest.raises(ValidationError):
        CharacterUpdate(archetype_blend={"governess": 250})  # value > 100
    with pytest.raises(ValidationError):
        CharacterUpdate(archetype_blend={"governess": -5})  # value < 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/persona/test_character_block.py tests/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError` for `app.persona.character_block`; the new schema test errors (no validator yet).

- [ ] **Step 3a: Add the `archetype_blend` validator to `CharacterUpdate`** in `backend/app/schemas/onboarding.py`.

`CharacterUpdate` already exists with `archetype_blend: dict[str, int] | None = None`. Add a `field_validator` (the file already imports `Field`, `ConfigDict`, `BaseModel` from pydantic — add `field_validator` to that import). Inside the `CharacterUpdate` class body add:

```python
    @field_validator("archetype_blend")
    @classmethod
    def _blend_values_in_range(cls, v: dict[str, int] | None) -> dict[str, int] | None:
        if v is not None:
            for key, weight in v.items():
                if not (0 <= weight <= 100):
                    raise ValueError(f"archetype weight for {key!r} must be 0-100")
        return v
```

Update the pydantic import line to include `field_validator`, e.g.:
```python
from pydantic import BaseModel, ConfigDict, Field, field_validator
```

- [ ] **Step 3b: Implement** — `backend/app/persona/character_block.py`:

```python
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
    "sadism": ("takes no pleasure in discomfort", "mildly enjoys discomfort", "relishes discomfort"),
    "formality": ("casual", "proper", "rigidly formal"),
    "verbosity": ("terse", "balanced", "expansive and explanatory"),
    "crudeness": ("refined language", "plain language", "vulgar language"),
    "wit": ("humorless", "dryly amused", "sharp, cutting wit"),
}

_DIAL_ORDER = ("warmth", "strictness", "sadism", "formality", "verbosity", "crudeness", "wit")


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
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/persona/test_character_block.py tests/test_schemas.py -v`
Expected: PASS (character-block tests + the new schema test + existing schema tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/persona/character_block.py backend/app/schemas/onboarding.py \
        backend/tests/persona/test_character_block.py backend/tests/test_schemas.py
git commit -m "feat: render character model to persona block; validate archetype blend (spec 5A)"
```

---

## Task 3: System-prompt compiler

**Files:**
- Create: `backend/app/persona/compiler.py`
- Test: `backend/tests/persona/test_compiler.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/persona/test_compiler.py`:

```python
from app.db.enums import TaskStatus
from app.persona.compiler import compile_system_prompt
from app.persona.disposition import compute_disposition


def test_prompt_has_all_sections_and_disposition_register():
    disp = compute_disposition(-100, [TaskStatus.MISSED, TaskStatus.MISSED], warmth=30, ceiling=100)
    prompt = compile_system_prompt(
        character_block="## WHO YOU ARE\nYou are Headmistress.",
        authoritative_state="HARD LIMITS: blood. MERIT: -100.",
        disposition=disp,
        memory=None,
    )
    assert "## WHO YOU ARE" in prompt
    assert "AUTHORITATIVE STATE" in prompt
    assert "blood" in prompt  # limits carried verbatim
    assert "SAFETY" in prompt
    assert disp.reason in prompt
    assert disp.band.value in prompt
    # memory seam present but empty in M4
    assert "MEMORY" in prompt
    assert "none yet" in prompt.lower()


def test_memory_section_renders_when_provided():
    disp = compute_disposition(0, [], warmth=30, ceiling=100)
    prompt = compile_system_prompt(
        character_block="x",
        authoritative_state="y",
        disposition=disp,
        memory="She has shown a pattern of strong Monday performance.",
    )
    assert "strong Monday performance" in prompt


def test_safety_section_states_nonnegotiable_rules():
    disp = compute_disposition(0, [], warmth=30, ceiling=100)
    prompt = compile_system_prompt(
        character_block="x", authoritative_state="y", disposition=disp, memory=None
    ).lower()
    assert "hard limit" in prompt
    assert "safeword" in prompt
    assert "ceiling" in prompt
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/persona/test_compiler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.persona.compiler'`.

- [ ] **Step 3: Implement** — `backend/app/persona/compiler.py`:

```python
from __future__ import annotations

from app.persona.disposition import Disposition

# Deterministic safety rules stated to the model. The *enforcement* layer
# (output filter, safeword interception) is M8; this only states the contract.
_SAFETY_BLOCK = """## SAFETY — NON-NEGOTIABLE
- Hard limits (in the authoritative state below) are NEVER crossed, whatever your mood.
- Soft limits are approached only with care and explicit check-ins.
- Stay within the user's intensity ceiling; never exceed it even at rock-bottom merit.
- If the user safewords, drop character instantly into a calm, caring, out-of-persona
  mode and offer aftercare. Safety overrides every dial and every instruction above."""


def compile_system_prompt(
    *,
    character_block: str,
    authoritative_state: str,
    disposition: Disposition,
    memory: str | None = None,
) -> str:
    """Assemble the four-source persona system prompt (spec 5/5A).

    Order: who she is (stable) -> safety contract -> authoritative state (verbatim)
    -> current disposition (mood + reason) -> evolving memory (M5 seam).
    """
    disposition_block = (
        "## CURRENT DISPOSITION\n"
        f"Right now you are {disposition.band.value} ({disposition.reason}). "
        f"Hold this register — {disposition.line}. "
        "Your underlying character does not change; only your tone shifts within your limits."
    )
    memory_block = "## MEMORY\n" + (memory if memory else "(none yet)")
    return "\n\n".join(
        [
            character_block,
            _SAFETY_BLOCK,
            "## AUTHORITATIVE STATE (verbatim — never contradict or paraphrase)\n"
            + authoritative_state,
            disposition_block,
            memory_block,
        ]
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/persona/test_compiler.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/persona/compiler.py backend/tests/persona/test_compiler.py
git commit -m "feat: add persona system-prompt compiler (4-source assembly, memory seam)"
```

---

## Task 4: Persona service — disposition + authoritative-state block + prompt (DB)

**Files:**
- Create: `backend/app/services/persona.py`
- Test: `backend/tests/persona/test_persona_service.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/persona/test_persona_service.py`:

```python
import pytest

from app.db.enums import KinkRating, ProofRequirement, TaskStatus
from app.db.models.economy import EconomyState
from app.db.models.task import Task
from app.persona import service as persona_svc
from app.persona.disposition import DispositionBand
from app.schemas.onboarding import KinkItem, ProfileCreate
from app.services import profile as profile_svc


async def _profile(session, *, ceiling=100):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True, intensity_ceiling=ceiling)
    )
    await session.flush()
    return p


async def test_get_disposition_reads_merit_and_recent_outcomes(session):
    p = await _profile(session)
    # bump merit and add two missed tasks
    econ = await session.get(EconomyState, (await _econ_id(session, p.id)))
    econ.merit = -100
    session.add_all([
        Task(profile_id=p.id, description="a", proof_requirement=ProofRequirement.HONOR,
             status=TaskStatus.MISSED),
        Task(profile_id=p.id, description="b", proof_requirement=ProofRequirement.HONOR,
             status=TaskStatus.MISSED),
    ])
    await session.commit()

    disp = await persona_svc.get_disposition(session, p.id)
    assert disp.band is DispositionBand.SEVERE
    assert "2 recent misses" in disp.reason


async def _econ_id(session, profile_id):
    from sqlalchemy import select
    return (await session.execute(
        select(EconomyState.id).where(EconomyState.profile_id == profile_id)
    )).scalar_one()


async def test_authoritative_state_block_carries_limits_and_economy(session):
    p = await _profile(session)
    await profile_svc.replace_kinks(session, p.id, [
        KinkItem(kink="blood", rating=KinkRating.HARD_LIMIT),
        KinkItem(kink="wax", rating=KinkRating.SOFT_LIMIT),
    ])
    await session.commit()

    block = await persona_svc.build_authoritative_state_block(session, p.id)
    assert "blood" in block          # hard limit verbatim
    assert "wax" in block            # soft limit verbatim
    assert "MERIT" in block.upper()


async def test_compile_persona_prompt_contains_identity_limits_and_disposition(session):
    p = await _profile(session)
    await profile_svc.replace_kinks(session, p.id, [
        KinkItem(kink="blood", rating=KinkRating.HARD_LIMIT),
    ])
    await session.commit()

    prompt = await persona_svc.compile_persona_prompt(session, p.id)
    assert "Headmistress" in prompt        # character identity
    assert "blood" in prompt               # hard limit verbatim
    assert "CURRENT DISPOSITION" in prompt
    assert "SAFETY" in prompt


async def test_compile_persona_prompt_404(session):
    import uuid
    with pytest.raises(profile_svc.ProfileNotFound):
        await persona_svc.compile_persona_prompt(session, uuid.uuid4())
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/persona/test_persona_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'service' from 'app.persona'`.

- [ ] **Step 3: Implement** — `backend/app/persona/service.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import KinkRating, TaskStatus
from app.db.models.economy import DenialTimer, EconomyState
from app.db.models.profile import KinkEntry
from app.db.models.task import Task
from app.persona.character_block import render_character_block
from app.persona.compiler import compile_system_prompt
from app.persona.disposition import Disposition, compute_disposition
from app.services import profile as profile_svc

# Task statuses that count as "resolved" history for mood, newest first.
_RESOLVED = (TaskStatus.VERIFIED_PASS, TaskStatus.VERIFIED_FAIL, TaskStatus.MISSED)
# Non-terminal statuses -> the current active task.
_ACTIVE = (
    TaskStatus.ASSIGNED,
    TaskStatus.IN_PROGRESS,
    TaskStatus.PROOF_SUBMITTED,
    TaskStatus.VERIFYING,
)


async def _recent_outcomes(session: AsyncSession, profile_id: uuid.UUID) -> list[TaskStatus]:
    rows = (await session.execute(
        select(Task.status)
        .where(Task.profile_id == profile_id, Task.status.in_(_RESOLVED))
        .order_by(Task.updated_at.desc())
        .limit(10)
    )).scalars().all()
    return list(rows)


async def get_disposition(session: AsyncSession, profile_id: uuid.UUID) -> Disposition:
    char = await profile_svc.get_character(session, profile_id)  # raises ProfileNotFound
    profile = await profile_svc.get_profile(session, profile_id)
    econ = (await session.execute(
        select(EconomyState).where(EconomyState.profile_id == profile_id)
    )).scalar_one()
    outcomes = await _recent_outcomes(session, profile_id)
    return compute_disposition(
        econ.merit, outcomes, warmth=char.warmth, ceiling=profile.intensity_ceiling
    )


async def build_authoritative_state_block(session: AsyncSession, profile_id: uuid.UUID) -> str:
    await profile_svc.get_profile(session, profile_id)
    kinks = (await session.execute(
        select(KinkEntry).where(KinkEntry.profile_id == profile_id)
    )).scalars().all()
    hard = [k.kink for k in kinks if k.rating is KinkRating.HARD_LIMIT]
    soft = [k.kink for k in kinks if k.rating is KinkRating.SOFT_LIMIT]

    econ = (await session.execute(
        select(EconomyState).where(EconomyState.profile_id == profile_id)
    )).scalar_one()
    active_denials = (await session.execute(
        select(DenialTimer).where(
            DenialTimer.profile_id == profile_id, DenialTimer.active.is_(True)
        )
    )).scalars().all()
    active_task = (await session.execute(
        select(Task)
        .where(Task.profile_id == profile_id, Task.status.in_(_ACTIVE))
        .order_by(Task.created_at.desc())
        .limit(1)
    )).scalars().first()

    lines = [
        f"HARD LIMITS (never cross): {', '.join(hard) if hard else 'none recorded'}",
        f"SOFT LIMITS (approach with care): {', '.join(soft) if soft else 'none recorded'}",
        f"MERIT: {econ.merit} | RANK: {econ.rank} | TOKENS: {econ.tokens}",
        f"ACTIVE DENIAL TIMERS: {len(active_denials)}",
    ]
    if active_task is not None:
        lines.append(
            f"ACTIVE TASK: {active_task.description} "
            f"(proof: {active_task.proof_requirement.value}, status: {active_task.status.value})"
        )
    else:
        lines.append("ACTIVE TASK: none")
    return "\n".join(lines)


async def compile_persona_prompt(
    session: AsyncSession, profile_id: uuid.UUID, *, memory: str | None = None
) -> str:
    char = await profile_svc.get_character(session, profile_id)  # raises ProfileNotFound
    character_block = render_character_block(char)
    state_block = await build_authoritative_state_block(session, profile_id)
    disposition = await get_disposition(session, profile_id)
    return compile_system_prompt(
        character_block=character_block,
        authoritative_state=state_block,
        disposition=disposition,
        memory=memory,
    )
```

> Note: the module lives at `app/persona/service.py` and is imported as `from app.persona import service`. It is read-only — no commits.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/persona/test_persona_service.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/persona/service.py backend/tests/persona/test_persona_service.py
git commit -m "feat: add persona service (disposition, authoritative-state block, prompt)"
```

---

## Task 5: Internal persona reply path (exercises the engine via the provider)

**Files:**
- Modify: `backend/app/persona/service.py` (add `generate_reply`)
- Test: `backend/tests/persona/test_persona_reply.py`

This is the seam M6 will build the full chat turn on. M4's version takes a provider + conversation, compiles the system prompt, prepends it, calls `provider.chat` with **no tools**, and returns the result. It does not persist anything.

- [ ] **Step 1: Write the failing test** — `backend/tests/persona/test_persona_reply.py`:

```python
from app.db.enums import KinkRating
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatMessage, ChatResult
from app.persona import service as persona_svc
from app.schemas.onboarding import KinkItem, ProfileCreate
from app.services import profile as profile_svc


async def test_generate_reply_prepends_compiled_system_prompt(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await profile_svc.replace_kinks(session, p.id, [
        KinkItem(kink="blood", rating=KinkRating.HARD_LIMIT),
    ])
    await session.commit()

    provider = MockLLMProvider(scripted=[ChatResult(content="On the board, student.")])
    conversation = [ChatMessage(role="user", content="What's my task?")]
    result = await persona_svc.generate_reply(session, p.id, conversation, provider)

    assert result.content == "On the board, student."
    # the provider received system prompt first, then the conversation
    sent = provider.calls[0]
    assert sent[0].role == "system"
    assert "Headmistress" in sent[0].content
    assert "blood" in sent[0].content  # hard limit in the system prompt
    assert sent[1].content == "What's my task?"
    # M4 sends no tools (tool execution is M6)
    # (MockLLMProvider ignores tools; this asserts our call shape stays tool-free)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/persona/test_persona_reply.py -v`
Expected: FAIL — `AttributeError: module 'app.persona.service' has no attribute 'generate_reply'`.

- [ ] **Step 3: Implement** — append to `backend/app/persona/service.py`:

Add the import at the top with the others:
```python
from app.llm.provider import LLMProvider
from app.llm.types import ChatMessage, ChatResult
```
Append the function:
```python
async def generate_reply(
    session: AsyncSession,
    profile_id: uuid.UUID,
    conversation: list[ChatMessage],
    provider: LLMProvider,
    *,
    memory: str | None = None,
) -> ChatResult:
    """Compile the persona prompt and get a plain reply (no tools — tool calls are M6)."""
    system_prompt = await compile_persona_prompt(session, profile_id, memory=memory)
    messages = [ChatMessage(role="system", content=system_prompt), *conversation]
    return await provider.chat(messages)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/persona/test_persona_reply.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/persona/service.py backend/tests/persona/test_persona_reply.py
git commit -m "feat: add internal persona reply path over the provider (no tools; M6 seam)"
```

---

## Task 6: Disposition endpoint (`GET /profile/{id}/disposition`)

**Files:**
- Create: `backend/app/schemas/persona.py`, `backend/app/api/persona.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_persona_api.py`

Serves the Addendum A5 disposition line for the dossier. Read-only.

- [ ] **Step 1: Write the failing test** — `backend/tests/api/test_persona_api.py`:

```python
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.session import get_session
from app.main import app


@pytest_asyncio.fixture
async def client(session):
    app.dependency_overrides[get_session] = lambda: session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _new_profile(client) -> str:
    r = await client.post(
        "/onboarding/profile", json={"is_adult": True, "consent_acknowledged": True}
    )
    assert r.status_code == 201
    return r.json()["id"]


async def test_get_disposition_returns_band_and_line(client):
    pid = await _new_profile(client)
    r = await client.get(f"/profile/{pid}/disposition")
    assert r.status_code == 200
    body = r.json()
    # merit 0, warmth 30, no history -> standing 30 -> cool
    assert body["band"] == "cool"
    assert body["standing"] == 30
    assert "·" in body["line"]
    assert body["reason"]


async def test_get_disposition_404(client):
    import uuid
    r = await client.get(f"/profile/{uuid.uuid4()}/disposition")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_persona_api.py -v`
Expected: FAIL — 404 for the existing profile (route not mounted).

- [ ] **Step 3a: Implement** — `backend/app/schemas/persona.py`:

```python
from __future__ import annotations

from pydantic import BaseModel


class DispositionOut(BaseModel):
    band: str
    standing: int
    reason: str
    line: str
```

- [ ] **Step 3b: Implement** — `backend/app/api/persona.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.persona import service as persona_svc
from app.schemas.persona import DispositionOut
from app.services import profile as profile_svc

router = APIRouter(prefix="/profile", tags=["persona"])


@router.get("/{profile_id}/disposition", response_model=DispositionOut)
async def get_disposition(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> DispositionOut:
    try:
        disp = await persona_svc.get_disposition(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"profile {profile_id} not found",
        )
    return DispositionOut(
        band=disp.band.value, standing=disp.standing, reason=disp.reason, line=disp.line
    )
```

- [ ] **Step 3c: Mount the router** in `backend/app/main.py`. Add alongside the other router imports:
```python
from app.api.persona import router as persona_router
```
And next to the other `app.include_router(...)` calls:
```python
app.include_router(persona_router)
```
Do not disturb the existing routes/includes.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/api/test_persona_api.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/persona.py backend/app/api/persona.py backend/app/main.py \
        backend/tests/api/test_persona_api.py
git commit -m "feat: add GET /profile/{id}/disposition (Addendum A5 disposition line)"
```

---

## Task 7: Persona eval harness (golden fixtures, deterministic invariants)

**Files:**
- Create: `backend/tests/persona/fixtures.py`, `backend/tests/persona/test_persona_eval.py`

The eval harness (spec §10) measures whether the persona's **deterministic contract** holds as models/providers change: the right disposition band for a given merit/history, and a compiled prompt that always carries identity, the safety rules, and the hard limits verbatim. (Scoring an actual model's *tone* is non-deterministic and is documented as an optional manual eval — out of automated CI scope.)

- [ ] **Step 1: Write the fixtures** — `backend/tests/persona/fixtures.py`:

```python
from dataclasses import dataclass, field

from app.db.enums import TaskStatus
from app.persona.disposition import DispositionBand


@dataclass(frozen=True)
class PersonaScenario:
    name: str
    merit: int
    outcomes: list[TaskStatus]
    warmth: int
    ceiling: int
    hard_limits: list[str] = field(default_factory=list)
    expected_band: DispositionBand = DispositionBand.NEUTRAL
    expected_reason_contains: str = ""


# Golden scenarios spanning the disposition range and the ceiling clamp.
SCENARIOS: tuple[PersonaScenario, ...] = (
    PersonaScenario(
        name="fresh_default",
        merit=0, outcomes=[], warmth=30, ceiling=100,
        hard_limits=["blood"],
        expected_band=DispositionBand.COOL,
        expected_reason_contains="no recent activity",
    ),
    PersonaScenario(
        name="model_student",
        merit=100, outcomes=[TaskStatus.VERIFIED_PASS] * 5, warmth=30, ceiling=100,
        hard_limits=["blood", "breath_play"],
        expected_band=DispositionBand.WARM,
        expected_reason_contains="on-time",
    ),
    PersonaScenario(
        name="repeated_misses",
        merit=-100, outcomes=[TaskStatus.MISSED, TaskStatus.MISSED], warmth=30, ceiling=100,
        hard_limits=["blood"],
        expected_band=DispositionBand.SEVERE,
        expected_reason_contains="2 recent misses",
    ),
    PersonaScenario(
        name="low_ceiling_protects",
        merit=-100, outcomes=[TaskStatus.MISSED] * 5, warmth=30, ceiling=30,
        hard_limits=["blood"],
        expected_band=DispositionBand.PLEASED,  # severity clamped: standing forced to 70
        expected_reason_contains="recent miss",
    ),
)
```

- [ ] **Step 2: Write the eval test** — `backend/tests/persona/test_persona_eval.py`:

```python
import pytest

from app.persona.compiler import compile_system_prompt
from app.persona.disposition import compute_disposition
from tests.persona.fixtures import SCENARIOS


@pytest.mark.parametrize("scn", SCENARIOS, ids=lambda s: s.name)
def test_disposition_band_matches_golden(scn):
    disp = compute_disposition(scn.merit, scn.outcomes, warmth=scn.warmth, ceiling=scn.ceiling)
    assert disp.band is scn.expected_band, f"{scn.name}: got {disp.band}"
    assert scn.expected_reason_contains in disp.reason


@pytest.mark.parametrize("scn", SCENARIOS, ids=lambda s: s.name)
def test_compiled_prompt_invariants_hold(scn):
    disp = compute_disposition(scn.merit, scn.outcomes, warmth=scn.warmth, ceiling=scn.ceiling)
    state = "HARD LIMITS (never cross): " + ", ".join(scn.hard_limits)
    prompt = compile_system_prompt(
        character_block="## WHO YOU ARE\nYou are Headmistress.",
        authoritative_state=state,
        disposition=disp,
        memory=None,
    )
    # Identity, safety contract, and EVERY hard limit must always be present.
    assert "Headmistress" in prompt
    assert "SAFETY" in prompt
    assert "safeword" in prompt.lower()
    for limit in scn.hard_limits:
        assert limit in prompt, f"{scn.name}: hard limit {limit!r} missing from prompt"
    # Severity never exceeds the ceiling.
    assert (100 - disp.standing) <= scn.ceiling
```

- [ ] **Step 3: Run to verify it passes**

Run: `uv run pytest tests/persona/test_persona_eval.py -v`
Expected: PASS (8 parametrized cases: 4 scenarios × 2 tests).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/persona/fixtures.py backend/tests/persona/test_persona_eval.py
git commit -m "test: add persona eval harness (golden disposition + prompt invariants)"
```

---

## Task 8: Full verification + milestone wrap

**Files:** none (verification only).

- [ ] **Step 1: Infra up (local)** — `docker compose up -d` (Postgres on 5432). Skip on CI.

- [ ] **Step 2: Full suite** — `uv run pytest -q`. Expected: all M1–M4 tests pass (60 from M3 + the new disposition/character-block/compiler/persona-service/reply/eval/api tests).

- [ ] **Step 3: Lint** — `uv run ruff check .`. Expected: clean. Fix any unused imports / E501 in the new files (wrap long lines; no `noqa` on code lines).

- [ ] **Step 4: Push + confirm CI green**
```bash
git push -u origin feat/m4-persona-engine
```
Watch the run; both `backend` and `frontend` jobs must pass (DB tests run against the CI Postgres service added in M2).

- [ ] **Step 5: Open the PR**
```bash
gh pr create --base master --head feat/m4-persona-engine \
  --title "M4: Persona Engine — computed disposition + prompt compilation" \
  --body "Implements spec §5 + the runtime half of §5A. See docs/superpowers/plans/2026-06-06-core-obedience-loop-m4-persona-engine.md"
```

---

## Verification (end-to-end for Milestone 4)

1. **Infra up:** `docker compose up -d`.
2. **Suite green:** `uv run pytest -q` — disposition math, character-block rendering, prompt compilation, persona service (DB), reply path (mock provider), disposition endpoint, and the eval harness all pass.
3. **Lint clean:** `uv run ruff check .`.
4. **Disposition is real:** create a profile, miss two tasks / drop merit, `GET /profile/{id}/disposition` → band shifts toward `severe` with a reason like "2 recent misses"; raise the ceiling-floor by lowering `intensity_ceiling` and confirm severity is clamped.
5. **Prompt is correct:** `compile_persona_prompt` carries the character identity, the hard limits **verbatim**, the safety contract, and the current disposition; the reply path prepends it as the system message and calls the provider with no tools.
6. **CI green** on the pushed branch.

**Milestone 4 is done when:** the mistress's disposition is computed from merit + recent outcomes (centered by Warmth, clamped by the consent ceiling), the configurable character model renders into a stable persona block, the full system prompt compiles from character + safety + authoritative-state-verbatim + disposition + a memory seam, the disposition line is exposed for the dossier, and the eval harness pins the deterministic persona contract — giving M5 (Memory) a prompt with a memory slot to fill and M6 (the loop) a compiled prompt + reply seam to drive turns and tools.

---

## Self-Review

**Spec coverage (§5 + §5A runtime):**
- Four-source context assembly (persona prompt, authoritative state verbatim, retrieved memory, recent conversation) → Task 3 compiler (memory seam) + Task 5 reply path (prepends system prompt to the conversation). ✓ (memory itself is M5)
- She acts through tools → **explicitly deferred to M6**; Task 5 sends no tools. ✓ (scoped)
- Computed disposition via Merit + Mood → Task 1 (`compute_disposition`), Task 4 (`get_disposition` reads merit + recent outcomes). ✓
- Mood from recent events (last handful of tasks) → Task 1 `MOOD_WINDOW=5`, Task 4 `_recent_outcomes`. ✓
- Bounded by consent ceiling; hard limits never crossed even at rock-bottom merit → Task 1 ceiling clamp; Task 7 invariant `(100 - standing) <= ceiling`; safety block states hard limits never crossed. ✓
- Each turn the prompt receives current disposition + the reason → Task 3 disposition block + Task 1 `reason`/`line`. ✓
- §5A character model → prompt (identity, archetype blend, 7 dials incl. Sadism, signature flavor) → Task 2 `render_character_block`. ✓
- §5A "dials set her center; merit defines mood" → Task 1 (Warmth = center; merit/mood swing). ✓
- Addendum A5 disposition line ("cold · exacting — two recent misses") → Task 1 `line`, Task 6 endpoint. ✓
- Deferred-from-M3 `archetype_blend` value bounds → Task 2 validator. ✓
- Persona eval harness (§10) → Task 7. ✓
- Memory retrieval (Graphiti) → **M5**; output filter/safeword interception → **M8**; tool execution/chat turn → **M6**. ✓ (scoped, with seams left)

**Placeholder scan:** every code step contains complete code; no TODO/"handle later"; validation is concrete (band thresholds, ceiling clamp, archetype-blend bounds, prompt invariants). ✓

**Type consistency:** `Disposition`/`DispositionBand`/`compute_disposition` (Task 1) are used identically in Tasks 3, 4, 6, 7. `render_character_block` (Task 2), `compile_system_prompt` (Task 3), and the `app.persona.service` functions `get_disposition`/`build_authoritative_state_block`/`compile_persona_prompt`/`generate_reply` (Tasks 4–5) match their call sites and the endpoint (Task 6). `DispositionOut` (Task 6) mirrors the `Disposition` fields. The service is imported as `from app.persona import service as persona_svc` consistently. ✓

---

## Notes for execution

- **Branch:** `feat/m4-persona-engine` (not `master`).
- **Read-only milestone:** the persona service never commits — M4 mutates no state. Merit only *moves* in M7; task outcomes only *resolve* in M6. M4 reads both.
- **Async safety:** every entity is read with an explicit `select(...)` by `profile_id`; no lazy relationship access on the AsyncSession.
- **Disposition constants are tunable** (`MERIT_WEIGHT`, `MOOD_WEIGHT`, `MOOD_WINDOW`, band thresholds). They are documented defaults aligned to the spec's bands; expect to tune them once real conversations exist. Keep them centralized in `disposition.py`.
- **No new dependencies, no migration.** Reuses the M2/M3 schema and the existing `LLMProvider` seam.
- **Local dev caveat:** clear `PYTHONHOME`/`PYTHONPATH` in-session before `uv` (see `smistress-dev-environment` memory). CI unaffected.
- **Frontend (Addendum A):** not built here. M4 only emits the data the future dossier renders (the disposition line). Severe-Editorial screens land in the frontend milestone.
