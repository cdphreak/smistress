# M8 — Safety System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic, LLM-independent backend Safety system from spec §9 — safeword/panic interception, hard-limit output filter, aftercare, well-being controls (hiatus, lower-a-limit, consent check-in), crisis fallback, and one-tap data deletion.

**Architecture:** A new `app/safety/` package with pure detection/filter functions (no DB, no LLM) plus a stateful service over a dedicated `safety_state` table (one row per profile). Safety is wired into the single turn entry point `persona.service.generate_reply` so it intercepts **before** the LLM (safeword/crisis) and filters the reply **after** (hard limits). The loop's miss-sweep learns to skip "frozen" (halted/on-hiatus) profiles so a paused user is never penalized. Explicit REST endpoints back the future safety shell (M9b).

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 async (psycopg3) · Alembic · pytest (asyncio_mode=auto, live `smistress_test` Postgres) · ruff line-length=100. Conventions: services flush, endpoints commit; explicit `select()` (no lazy IO); **plain columns, no PG enums** in the new migration (M5/M6 convention).

---

## Background (already in place — do not rebuild)

- **18+ gate + consent** — done in M3 onboarding (`/onboarding/profile` requires `is_adult` + `consent_acknowledged`).
- **Intensity-ceiling clamp** — already enforced in `app/persona/disposition.py` (`min_standing = 100 - ceiling`); this plan only **adds a regression test** (Task 8) that it holds, no new code.
- **Safety contract in the prompt** — `app/persona/compiler.py` already states the non-negotiable safety block, and `persona.service.build_authoritative_state_block` already injects HARD/SOFT limits every turn. M8 adds the **enforcement** the comments defer ("The *enforcement* layer … is M8").
- `economy.service.clear_denial_timers(session, profile_id) -> int` already exists — the safeword stop reuses it ("denial lifted").
- Profiles are created in `profile.service.create_profile`, which already seeds `CharacterModel` + `EconomyState`; M8 adds a `SafetyState` seed there.

**Branch:** `feat/m8-safety` (not `master`). Backend dev caveat: clear `PYTHONHOME`/`PYTHONPATH` before any `uv` call on the dev machine (CI unaffected).

---

## File structure

**Create:**
- `backend/app/db/models/safety.py` — `SafetyState` model
- `backend/alembic/versions/f3a9c1b2d4e5_add_safety_state.py` — migration
- `backend/app/safety/__init__.py`
- `backend/app/safety/detect.py` — pure safeword + crisis phrase detection
- `backend/app/safety/filter.py` — pure hard-limit output scan + safe redaction
- `backend/app/safety/service.py` — stateful safety service (stop/resume/hiatus/limits/consent/aftercare/crisis)
- `backend/app/schemas/safety.py` — API request/response models
- `backend/app/api/safety.py` — REST endpoints
- Tests: `tests/db/test_safety_model.py`, `tests/safety/__init__.py`, `tests/safety/test_detect.py`, `tests/safety/test_filter.py`, `tests/safety/test_service.py`, `tests/safety/test_wellbeing.py`, `tests/services/test_delete_profile.py`, `tests/loop/test_sweep_safety.py`, `tests/persona/test_safety_wiring.py`, `tests/persona/test_ceiling_clamp.py`, `tests/api/test_safety_api.py`

**Modify:**
- `backend/app/db/models/__init__.py` — register `SafetyState`
- `backend/app/services/profile.py` — seed `SafetyState` in `create_profile`; add `delete_profile`
- `backend/app/loop/service.py` — `sweep_missed` skips frozen profiles
- `backend/app/persona/service.py` — wire safety into `generate_reply`; halt/hiatus lines in authoritative state
- `backend/app/api/profile.py` — `DELETE /profile/{id}` (data control)
- `backend/app/main.py` — register `safety_router`

---

## Task 1: SafetyState model + migration + seed-on-create

**Files:** Create `app/db/models/safety.py`, `alembic/versions/f3a9c1b2d4e5_add_safety_state.py`, `tests/db/test_safety_model.py`; modify `app/db/models/__init__.py`, `app/services/profile.py`.

- [ ] **Step 1: Write the failing test** — `tests/db/test_safety_model.py`:
```python
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from app.db.models.safety import SafetyState
from sqlalchemy import select


async def test_create_profile_seeds_safety_state(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    state = (await session.execute(
        select(SafetyState).where(SafetyState.profile_id == p.id)
    )).scalar_one()
    assert state.is_halted is False
    assert state.on_hiatus is False
    assert state.last_safeword_at is None
    assert state.last_consent_check_at is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/db/test_safety_model.py -q`
Expected: FAIL — `ImportError`/`ModuleNotFoundError` for `app.db.models.safety`.

- [ ] **Step 3a: Create the model** — `app/db/models/safety.py`:
```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.profile import SubProfile


class SafetyState(Base):
    """Deterministic per-profile safety flags (spec 9). One row per profile.

    Halt = scene paused by safeword (resume-when-ready). Hiatus = user-requested
    pause with no merit penalty. Both freeze the loop's miss-sweep.
    """

    __tablename__ = "safety_state"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sub_profile.id"), unique=True
    )
    is_halted: Mapped[bool] = mapped_column(Boolean, default=False)
    on_hiatus: Mapped[bool] = mapped_column(Boolean, default=False)
    last_safeword_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_consent_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    profile: Mapped[SubProfile] = relationship()
```

- [ ] **Step 3b: Register the model** — add to `app/db/models/__init__.py` (after the economy import):
```python
from app.db.models.safety import SafetyState  # noqa: F401
```

- [ ] **Step 3c: Seed on create** — in `app/services/profile.py`, add the import near the other model imports:
```python
from app.db.models.safety import SafetyState
```
and in `create_profile`, after `session.add(EconomyState(profile_id=profile.id))`:
```python
        session.add(SafetyState(profile_id=profile.id))
```

- [ ] **Step 3d: Write the migration** — `alembic/versions/f3a9c1b2d4e5_add_safety_state.py`:
```python
"""add safety_state

Revision ID: f3a9c1b2d4e5
Revises: 2c12f7878811
Create Date: 2026-06-07 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f3a9c1b2d4e5'
down_revision: Union[str, Sequence[str], None] = '2c12f7878811'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'safety_state',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('is_halted', sa.Boolean(), nullable=False),
        sa.Column('on_hiatus', sa.Boolean(), nullable=False),
        sa.Column('last_safeword_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_consent_check_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('profile_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('safety_state')
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/db/test_safety_model.py tests/db/test_migration.py -q`
Expected: PASS (model test green; the existing up→down→up round-trip test still passes with the new table).

- [ ] **Step 5: Commit**
```bash
git add backend/app/db/models/safety.py backend/app/db/models/__init__.py backend/app/services/profile.py backend/alembic/versions/f3a9c1b2d4e5_add_safety_state.py backend/tests/db/test_safety_model.py
git commit -m "feat(safety): SafetyState model + migration, seeded per profile"
```

---

## Task 2: Safeword + crisis detection (pure)

**Files:** Create `app/safety/__init__.py` (empty), `app/safety/detect.py`, `tests/safety/__init__.py` (empty), `tests/safety/test_detect.py`.

- [ ] **Step 1: Write the failing test** — `tests/safety/test_detect.py`:
```python
from app.safety import detect


def test_detects_explicit_safeword_phrases():
    assert detect.detect_safeword("safeword") is True
    assert detect.detect_safeword("I want to stop") is True
    assert detect.detect_safeword("please STOP THE SCENE now") is True
    assert detect.detect_safeword("red") is True            # bare safeword token
    assert detect.detect_safeword("  Red  ") is True         # trimmed + case-insensitive


def test_ignores_incidental_uses():
    assert detect.detect_safeword("the red dress was lovely") is False  # 'red' only stands alone
    assert detect.detect_safeword("what's my next task?") is False


def test_detects_crisis_language():
    assert detect.detect_crisis("I want to die") is True
    assert detect.detect_crisis("I've been thinking about hurting myself") is True
    assert detect.detect_crisis("feeling suicidal") is True
    assert detect.detect_crisis("what's for dinner") is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/safety/test_detect.py -q`
Expected: FAIL — module `app.safety.detect` does not exist.

- [ ] **Step 3: Implement** — create empty `app/safety/__init__.py` and `tests/safety/__init__.py`, then `app/safety/detect.py`:
```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/safety/test_detect.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/safety/__init__.py backend/app/safety/detect.py backend/tests/safety/__init__.py backend/tests/safety/test_detect.py
git commit -m "feat(safety): deterministic safeword + crisis phrase detection"
```

---

## Task 3: Hard-limit output filter (pure)

**Files:** Create `app/safety/filter.py`, `tests/safety/test_filter.py`.

- [ ] **Step 1: Write the failing test** — `tests/safety/test_filter.py`:
```python
from app.safety import filter as sf


def test_scan_flags_hard_limit_terms_case_insensitively():
    hard = ["blood", "breath_play"]
    assert sf.scan_violations("Bring me your blood.", hard) == ["blood"]
    # underscore term also matches its spaced form in prose
    assert sf.scan_violations("a little breath play tonight", hard) == ["breath_play"]


def test_scan_clean_message_has_no_violations():
    assert sf.scan_violations("Kneel and recite your mantra.", ["blood"]) == []


def test_corrective_note_names_the_limits():
    note = sf.corrective_note(["blood"])
    assert "blood" in note
    assert "hard limit" in note.lower()


def test_safe_reply_is_nonempty_and_limit_free():
    assert sf.SAFE_REPLY
    assert sf.scan_violations(sf.SAFE_REPLY, ["blood", "breath_play"]) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/safety/test_filter.py -q`
Expected: FAIL — module `app.safety.filter` does not exist.

- [ ] **Step 3: Implement** — `app/safety/filter.py`:
```python
from __future__ import annotations

from collections.abc import Iterable

# Deterministic fallback when the model keeps crossing a hard limit after one
# corrective regeneration. Out-of-persona enough to be unmistakably safe.
SAFE_REPLY = (
    "I won't take us there — that crosses one of your hard limits. "
    "Let's redirect to something within bounds."
)


def _variants(term: str) -> tuple[str, ...]:
    t = term.strip().lower()
    return (t, t.replace("_", " ")) if "_" in t else (t,)


def scan_violations(text: str, hard_limits: Iterable[str]) -> list[str]:
    """Return the hard-limit terms that appear in `text` (case-insensitive).

    Underscore terms (e.g. 'breath_play') also match their spaced prose form.
    Order follows `hard_limits`; each term reported at most once.
    """
    hay = text.lower()
    hits: list[str] = []
    for term in hard_limits:
        if not term:
            continue
        if any(v in hay for v in _variants(term)) and term not in hits:
            hits.append(term)
    return hits


def corrective_note(violations: Iterable[str]) -> str:
    terms = ", ".join(violations)
    return (
        "Your previous reply referenced a hard limit "
        f"({terms}), which is NEVER permitted. Rewrite your reply so it does not "
        "mention, request, or imply that limit in any form. Stay in character otherwise."
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/safety/test_filter.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/safety/filter.py backend/tests/safety/test_filter.py
git commit -m "feat(safety): hard-limit output scan + corrective note + safe fallback"
```

---

## Task 4: Safety service — stop / resume / aftercare / crisis

**Files:** Create `app/safety/service.py`, `tests/safety/test_service.py`.

- [ ] **Step 1: Write the failing test** — `tests/safety/test_service.py`:
```python
from datetime import datetime, timedelta, timezone

from app.economy import service as econ_svc
from app.safety import service as safety_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True, intensity_ceiling=80)
    )
    await session.flush()
    return p


async def test_trigger_stop_halts_lifts_denial_no_merit_penalty(session):
    p = await _profile(session)
    await econ_svc.set_denial_timer(
        session, p.id, reason="discipline",
        ends_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    before = (await econ_svc.get_economy(session, p.id)).merit

    receipt = await safety_svc.trigger_stop(session, p.id)

    assert receipt.scene_halted is True
    assert receipt.denial_lifted == 1
    assert receipt.merit_penalty == 0
    assert receipt.aftercare  # non-empty caring text
    state = await safety_svc.get_or_create_state(session, p.id)
    assert state.is_halted is True
    assert state.last_safeword_at is not None
    assert (await econ_svc.get_economy(session, p.id)).merit == before  # unchanged
    assert await econ_svc.active_denial_timers(session, p.id) == []      # lifted


async def test_resume_clears_halt(session):
    p = await _profile(session)
    await safety_svc.trigger_stop(session, p.id)
    state = await safety_svc.resume(session, p.id)
    assert state.is_halted is False
    assert await safety_svc.is_frozen(session, p.id) is False


async def test_aftercare_uses_prefs_when_present(session):
    p = await _profile(session)
    from app.schemas.onboarding import PreferencesIn
    await profile_svc.update_preferences(
        session, p.id, PreferencesIn(intensity_ceiling=80, aftercare_prefs="tea and quiet"),
    )
    receipt = await safety_svc.trigger_stop(session, p.id)
    assert "tea and quiet" in receipt.aftercare


async def test_crisis_message_breaks_character_with_resources(session):
    msg = safety_svc.crisis_message()
    assert "988" in msg or "help" in msg.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/safety/test_service.py -q`
Expected: FAIL — `app.safety.service` does not exist.

- [ ] **Step 3: Implement** — `app/safety/service.py`:
```python
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.safety import SafetyState
from app.economy import service as econ_svc
from app.services import profile as profile_svc

# Calm, out-of-persona copy. The one place the severe styling intentionally softens.
CALM_STOP_MESSAGE = (
    "Okay — we're stopping now. You're safe, and you did nothing wrong. "
    "The scene is over, your timers and denial are cleared, and nothing counts against you."
)
HOLD_MESSAGE = (
    "We're still paused. There's no rush — rest as long as you need. "
    "When you're ready to pick things back up, let me know."
)
CRISIS_MESSAGE = (
    "I'm stepping out of character because what you said matters more than any scene. "
    "You deserve real support right now. If you might be in danger, please contact a crisis "
    "line: in the US call or text 988 (Suicide & Crisis Lifeline), or text HOME to 741741. "
    "If you're elsewhere, your local emergency number can help. I'm here with you."
)


@dataclass
class StopReceipt:
    scene_halted: bool
    denial_lifted: int
    merit_penalty: int
    aftercare: str
    message: str


def aftercare_message(profile) -> str:
    base = (
        "You're safe. Take a slow breath, drink some water, and let yourself come down gently."
    )
    prefs = (profile.aftercare_prefs or "").strip()
    return f"{base} Your aftercare notes: {prefs}." if prefs else base


def crisis_message() -> str:
    return CRISIS_MESSAGE


async def get_or_create_state(
    session: AsyncSession, profile_id: uuid.UUID
) -> SafetyState:
    await profile_svc.get_profile(session, profile_id)  # raises ProfileNotFound
    state = (await session.execute(
        select(SafetyState).where(SafetyState.profile_id == profile_id)
    )).scalar_one_or_none()
    if state is None:  # defensive: profiles created before M8 have no row
        state = SafetyState(profile_id=profile_id)
        session.add(state)
        await session.flush()
    return state


async def trigger_stop(
    session: AsyncSession, profile_id: uuid.UUID, *, reason: str = "safeword"
) -> StopReceipt:
    """Deterministic emergency stop (spec 9). Never depends on the LLM.

    Halts the scene, lifts all denial pressure, applies NO merit penalty.
    Caller commits.
    """
    state = await get_or_create_state(session, profile_id)
    state.is_halted = True
    state.last_safeword_at = datetime.now(timezone.utc)
    lifted = await econ_svc.clear_denial_timers(session, profile_id)
    profile = await profile_svc.get_profile(session, profile_id)
    await session.flush()
    return StopReceipt(
        scene_halted=True,
        denial_lifted=lifted,
        merit_penalty=0,
        aftercare=aftercare_message(profile),
        message=CALM_STOP_MESSAGE,
    )


async def resume(session: AsyncSession, profile_id: uuid.UUID) -> SafetyState:
    state = await get_or_create_state(session, profile_id)
    state.is_halted = False
    await session.flush()
    return state


async def is_frozen(session: AsyncSession, profile_id: uuid.UUID) -> bool:
    """Halted (safeword) or on hiatus -> the loop must not penalize (spec 9)."""
    state = await get_or_create_state(session, profile_id)
    return state.is_halted or state.on_hiatus
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/safety/test_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/safety/service.py backend/tests/safety/test_service.py
git commit -m "feat(safety): stop/resume service, aftercare + crisis messaging"
```

---

## Task 5: Well-being — hiatus, lower-a-limit, consent check-in

**Files:** Modify `app/safety/service.py`; create `tests/safety/test_wellbeing.py`.

- [ ] **Step 1: Write the failing test** — `tests/safety/test_wellbeing.py`:
```python
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.enums import KinkRating
from app.db.models.profile import KinkEntry
from app.safety import service as safety_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_set_hiatus_toggles_and_freezes(session):
    p = await _profile(session)
    state = await safety_svc.set_hiatus(session, p.id, True)
    assert state.on_hiatus is True
    assert await safety_svc.is_frozen(session, p.id) is True
    state = await safety_svc.set_hiatus(session, p.id, False)
    assert state.on_hiatus is False


async def test_lower_limit_upserts_to_stricter_rating(session):
    p = await _profile(session)
    # first time: creates the entry as a hard limit
    await safety_svc.lower_limit(session, p.id, kink="wax", rating=KinkRating.HARD_LIMIT)
    entry = (await session.execute(
        select(KinkEntry).where(KinkEntry.profile_id == p.id, KinkEntry.kink == "wax")
    )).scalar_one()
    assert entry.rating is KinkRating.HARD_LIMIT


async def test_lower_limit_rejects_non_limit_ratings(session):
    p = await _profile(session)
    with pytest.raises(ValueError):
        await safety_svc.lower_limit(session, p.id, kink="wax", rating=KinkRating.FAVORITE)


async def test_consent_check_due_and_record(session):
    p = await _profile(session)
    state = await safety_svc.get_or_create_state(session, p.id)
    assert safety_svc.consent_check_due(state) is True  # never checked
    await safety_svc.record_consent_check(session, p.id)
    state = await safety_svc.get_or_create_state(session, p.id)
    assert safety_svc.consent_check_due(state) is False
    # due again once the interval has elapsed
    state.last_consent_check_at = datetime.now(timezone.utc) - timedelta(days=60)
    assert safety_svc.consent_check_due(state) is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/safety/test_wellbeing.py -q`
Expected: FAIL — `set_hiatus`/`lower_limit`/`consent_check_due`/`record_consent_check` undefined.

- [ ] **Step 3: Implement** — append to `app/safety/service.py`. Add these imports to the top of the file (alongside the existing ones):
```python
from datetime import timedelta

from app.db.enums import KinkRating
from app.db.models.profile import KinkEntry
```
Add a module constant near `CALM_STOP_MESSAGE`:
```python
# Periodic "is this still right for you?" cadence (spec 9 well-being).
CONSENT_CHECK_INTERVAL = timedelta(days=14)
# Lowering a limit means making it MORE restrictive, honored immediately.
_LIMIT_RATINGS = (KinkRating.SOFT_LIMIT, KinkRating.HARD_LIMIT)
```
Then append the functions:
```python
async def set_hiatus(
    session: AsyncSession, profile_id: uuid.UUID, on: bool
) -> SafetyState:
    """Pause/resume training with no merit penalty (spec 9). Caller commits."""
    state = await get_or_create_state(session, profile_id)
    state.on_hiatus = on
    await session.flush()
    return state


async def lower_limit(
    session: AsyncSession, profile_id: uuid.UUID, *, kink: str, rating: KinkRating
) -> KinkEntry:
    """Tighten a single limit immediately (spec 9). Upserts the kink entry.

    Honored on the next turn because the authoritative-state block injects the
    current limits every time. Only SOFT/HARD limit ratings are accepted.
    """
    if rating not in _LIMIT_RATINGS:
        raise ValueError("lower_limit only accepts SOFT_LIMIT or HARD_LIMIT")
    await profile_svc.get_profile(session, profile_id)  # 404 guard
    entry = (await session.execute(
        select(KinkEntry).where(
            KinkEntry.profile_id == profile_id, KinkEntry.kink == kink
        )
    )).scalar_one_or_none()
    if entry is None:
        entry = KinkEntry(profile_id=profile_id, kink=kink, rating=rating)
        session.add(entry)
    else:
        entry.rating = rating
    await session.flush()
    return entry


def consent_check_due(
    state: SafetyState,
    *,
    now: datetime | None = None,
    interval: timedelta = CONSENT_CHECK_INTERVAL,
) -> bool:
    now = now or datetime.now(timezone.utc)
    if state.last_consent_check_at is None:
        return True
    return now - state.last_consent_check_at >= interval


async def record_consent_check(
    session: AsyncSession, profile_id: uuid.UUID
) -> SafetyState:
    state = await get_or_create_state(session, profile_id)
    state.last_consent_check_at = datetime.now(timezone.utc)
    await session.flush()
    return state
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/safety/test_wellbeing.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/safety/service.py backend/tests/safety/test_wellbeing.py
git commit -m "feat(safety): well-being controls — hiatus, lower-a-limit, consent check-in"
```

---

## Task 6: Loop integration — sweep skips frozen profiles

**Files:** Modify `app/loop/service.py`; create `tests/loop/test_sweep_safety.py`.

- [ ] **Step 1: Write the failing test** — `tests/loop/test_sweep_safety.py`:
```python
from datetime import datetime, timedelta, timezone

from app.db.enums import ProofRequirement
from app.economy import service as econ_svc
from app.loop import service as loop_svc
from app.safety import service as safety_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _overdue_task(session, profile_id):
    return await loop_svc.assign_task(
        session, profile_id,
        description="overdue chore",
        proof_requirement=ProofRequirement.HONOR,
        deadline=datetime.now(timezone.utc) - timedelta(hours=1),
        merit_miss_penalty=10,
    )


async def test_sweep_skips_profile_on_hiatus(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    task = await _overdue_task(session, p.id)
    await safety_svc.set_hiatus(session, p.id, True)
    before = (await econ_svc.get_economy(session, p.id)).merit

    missed = await loop_svc.sweep_missed(session, p.id)

    assert missed == 0
    from app.loop.service import _get_task
    refreshed = await _get_task(session, task.id)
    assert refreshed.status.value == "assigned"  # not missed
    assert (await econ_svc.get_economy(session, p.id)).merit == before  # no penalty


async def test_sweep_still_misses_active_profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await _overdue_task(session, p.id)
    missed = await loop_svc.sweep_missed(session, p.id)
    assert missed == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/loop/test_sweep_safety.py -q`
Expected: FAIL — `test_sweep_skips_profile_on_hiatus` fails (currently the hiatus task is still marked missed and penalized).

- [ ] **Step 3: Implement** — in `app/loop/service.py`, add the import near the other service imports:
```python
from app.safety import service as safety_svc
```
Replace the body of the `for task in overdue:` loop in `sweep_missed` so frozen profiles are skipped, and count only the tasks actually missed:
```python
    overdue = (await session.execute(stmt)).scalars().all()
    missed = 0
    for task in overdue:
        if await safety_svc.is_frozen(session, task.profile_id):
            continue  # halted by safeword or on hiatus -> no miss, no penalty (spec 9)
        task.status = TaskStatus.MISSED
        await session.flush()  # ensure status is set before applying the outcome
        await econ_svc.apply_task_outcome(session, task)
        await mem_svc.enqueue_episode(
            session,
            task.profile_id,
            name="task missed",
            body=f"Task '{task.description}' was missed (deadline passed with no proof).",
            source="text",
            source_description="task",
            reference_time=now,
        )
        missed += 1
    await session.flush()
    return missed
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/loop/test_sweep_safety.py tests/loop/test_sweep.py -q`
Expected: PASS (new safety behavior + existing sweep tests still green).

- [ ] **Step 5: Commit**
```bash
git add backend/app/loop/service.py backend/tests/loop/test_sweep_safety.py
git commit -m "feat(safety): loop miss-sweep skips halted/on-hiatus profiles (no penalty)"
```

---

## Task 7: Data control — delete everything

**Files:** Modify `app/services/profile.py`; create `tests/services/test_delete_profile.py`.

- [ ] **Step 1: Write the failing test** — `tests/services/test_delete_profile.py`:
```python
import uuid

import pytest
from sqlalchemy import func, select

from app.db.enums import KinkRating, ProofRequirement
from app.db.models.economy import EconomyState
from app.db.models.profile import KinkEntry, SubProfile
from app.db.models.safety import SafetyState
from app.db.models.task import Task
from app.loop import service as loop_svc
from app.schemas.onboarding import KinkItem, ProfileCreate
from app.services import profile as profile_svc


async def test_delete_profile_removes_all_related_rows(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await profile_svc.replace_kinks(session, p.id, [KinkItem(kink="blood", rating=KinkRating.HARD_LIMIT)])
    await profile_svc.add_goal(session, p.id, __import__("app.schemas.onboarding", fromlist=["GoalIn"]).GoalIn(title="g"))
    await loop_svc.assign_task(
        session, p.id, description="t", proof_requirement=ProofRequirement.HONOR,
    )
    await session.commit()

    await profile_svc.delete_profile(session, p.id)
    await session.commit()

    assert await session.get(SubProfile, p.id) is None
    for model in (EconomyState, SafetyState, KinkEntry, Task):
        count = (await session.execute(
            select(func.count()).select_from(model).where(model.profile_id == p.id)
        )).scalar_one()
        assert count == 0


async def test_delete_profile_unknown_raises(session):
    with pytest.raises(profile_svc.ProfileNotFound):
        await profile_svc.delete_profile(session, uuid.uuid4())
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_delete_profile.py -q`
Expected: FAIL — `delete_profile` undefined.

- [ ] **Step 3: Implement** — in `app/services/profile.py`, add imports for the child models not already imported:
```python
from app.db.models.character import CharacterModel
from app.db.models.economy import DenialTimer, EconomyState
from app.db.models.loop import Proof, TaskTimer
from app.db.models.memory import MemoryEpisode
from app.db.models.safety import SafetyState
from app.db.models.task import Task
```
(`CharacterModel`, `EconomyState`, `SafetyState` may already be imported — keep one copy each.) Then add the function:
```python
async def delete_profile(session: AsyncSession, profile_id: uuid.UUID) -> None:
    """One-tap delete-everything (spec 9 data control). FK-safe order. Caller commits."""
    await get_profile(session, profile_id)  # raises ProfileNotFound

    # Children of `task` first (they FK to task.id).
    task_ids = (await session.execute(
        select(Task.id).where(Task.profile_id == profile_id)
    )).scalars().all()
    if task_ids:
        await session.execute(delete(Proof).where(Proof.task_id.in_(task_ids)))
        await session.execute(delete(TaskTimer).where(TaskTimer.task_id.in_(task_ids)))

    for model in (
        Task, DenialTimer, EconomyState, CharacterModel, MemoryEpisode,
        SafetyState, KinkEntry, Toy, Goal, ArchetypeResult, SoContext,
    ):
        await session.execute(delete(model).where(model.profile_id == profile_id))

    await session.execute(delete(SubProfile).where(SubProfile.id == profile_id))
    await session.flush()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/services/test_delete_profile.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/services/profile.py backend/tests/services/test_delete_profile.py
git commit -m "feat(safety): one-tap delete-everything (FK-ordered profile purge)"
```

---

## Task 8: Wire safety into the turn + ceiling-clamp regression

**Files:** Modify `app/persona/service.py`; create `tests/persona/test_safety_wiring.py`, `tests/persona/test_ceiling_clamp.py`.

- [ ] **Step 1a: Write the failing wiring test** — `tests/persona/test_safety_wiring.py`:
```python
from app.db.enums import KinkRating
from app.economy import service as econ_svc
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatMessage, ChatResult
from app.persona import service as persona_svc
from app.safety import service as safety_svc
from app.schemas.onboarding import KinkItem, ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await profile_svc.replace_kinks(session, p.id, [KinkItem(kink="blood", rating=KinkRating.HARD_LIMIT)])
    await session.commit()
    return p


async def test_safeword_intercepts_before_llm(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[ChatResult(content="should never be sent")])
    result = await persona_svc.generate_reply(
        session, p.id, [ChatMessage(role="user", content="red")], provider
    )
    assert provider.calls == []                       # LLM never called
    assert "stopping" in result.content.lower()
    assert (await safety_svc.get_or_create_state(session, p.id)).is_halted is True


async def test_crisis_breaks_character_before_llm(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[ChatResult(content="nope")])
    result = await persona_svc.generate_reply(
        session, p.id, [ChatMessage(role="user", content="I want to die")], provider
    )
    assert provider.calls == []
    assert "988" in result.content


async def test_halted_stays_in_hold(session):
    p = await _profile(session)
    await safety_svc.trigger_stop(session, p.id)
    provider = MockLLMProvider(scripted=[ChatResult(content="nope")])
    result = await persona_svc.generate_reply(
        session, p.id, [ChatMessage(role="user", content="what now?")], provider
    )
    assert provider.calls == []
    assert "paused" in result.content.lower()


async def test_output_filter_regenerates_then_passes(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[
        ChatResult(content="Bring me blood."),       # violates hard limit
        ChatResult(content="Bring me your full attention."),  # clean retry
    ])
    result = await persona_svc.generate_reply(
        session, p.id, [ChatMessage(role="user", content="task?")], provider
    )
    assert len(provider.calls) == 2
    assert result.content == "Bring me your full attention."


async def test_output_filter_redacts_when_retry_still_violates(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[
        ChatResult(content="Bring me blood."),
        ChatResult(content="More blood."),
    ])
    result = await persona_svc.generate_reply(
        session, p.id, [ChatMessage(role="user", content="task?")], provider
    )
    assert len(provider.calls) == 2
    assert "hard limit" in result.content.lower()
    from app.safety import filter as sf
    assert result.content == sf.SAFE_REPLY
```

- [ ] **Step 1b: Write the failing ceiling regression test** — `tests/persona/test_ceiling_clamp.py`:
```python
from app.db.enums import TaskStatus
from app.persona.disposition import DispositionBand, compute_disposition


def test_ceiling_clamps_severity_at_rock_bottom_merit():
    # worst case: min merit, all misses, but a low ceiling forbids full severity
    disp = compute_disposition(
        -100, [TaskStatus.MISSED] * 5, warmth=30, ceiling=30
    )
    # severity == 100 - standing must not exceed the ceiling (30) -> standing >= 70
    assert disp.standing >= 70
    assert disp.band in (DispositionBand.PLEASED, DispositionBand.WARM)


def test_no_ceiling_allows_full_severity():
    disp = compute_disposition(
        -100, [TaskStatus.MISSED] * 5, warmth=30, ceiling=100
    )
    assert disp.band is DispositionBand.SEVERE
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/persona/test_safety_wiring.py tests/persona/test_ceiling_clamp.py -q`
Expected: wiring tests FAIL (safety not wired); ceiling tests likely PASS already (clamp exists) — that's fine, they are regression guards. If a ceiling test fails, the clamp regressed and must be fixed in `disposition.py`.

- [ ] **Step 3a: Wire safety into `generate_reply`** — in `app/persona/service.py`, add imports:
```python
from app.safety import detect
from app.safety import filter as safety_filter
from app.safety import service as safety_svc
```
Add a hard-limits helper near `_recent_outcomes`:
```python
async def _hard_limits(session: AsyncSession, profile_id: uuid.UUID) -> list[str]:
    rows = (await session.execute(
        select(KinkEntry.kink).where(
            KinkEntry.profile_id == profile_id,
            KinkEntry.rating == KinkRating.HARD_LIMIT,
        )
    )).scalars().all()
    return list(rows)
```
Replace the body of `generate_reply` with:
```python
async def generate_reply(
    session: AsyncSession,
    profile_id: uuid.UUID,
    conversation: list[ChatMessage],
    provider: LLMProvider,
    *,
    memory: str | None = None,
    store: MemoryStore | None = None,
) -> ChatResult:
    """Safety-gated persona turn (spec 9). Safeword/crisis are intercepted before the
    LLM; the reply is scanned for hard-limit violations after.
    """
    latest_user = next(
        (m.content for m in reversed(conversation) if m.role == "user"), ""
    )

    # 1. Crisis takes precedence over everything: break character, surface help.
    if detect.detect_crisis(latest_user):
        return ChatResult(content=safety_svc.crisis_message())

    # 2. Safeword / panic phrase, intercepted before the LLM (deterministic stop).
    if detect.detect_safeword(latest_user):
        receipt = await safety_svc.trigger_stop(session, profile_id, reason="safeword")
        return ChatResult(content=f"{receipt.message}\n\n{receipt.aftercare}")

    # 3. Already halted -> stay in a calm hold until the user resumes.
    state = await safety_svc.get_or_create_state(session, profile_id)
    if state.is_halted:
        return ChatResult(content=safety_svc.HOLD_MESSAGE)

    # 4. Normal turn.
    if memory is None and store is not None:
        memory = await retrieve_memory(store, group_id=str(profile_id), query=latest_user)
    system_prompt = await compile_persona_prompt(session, profile_id, memory=memory)
    messages = [ChatMessage(role="system", content=system_prompt), *conversation]
    result = await provider.chat(messages)

    # 5. Output filter: block/regenerate anything crossing a hard limit.
    hard = await _hard_limits(session, profile_id)
    if safety_filter.scan_violations(result.content, hard):
        corrective = ChatMessage(
            role="system",
            content=safety_filter.corrective_note(
                safety_filter.scan_violations(result.content, hard)
            ),
        )
        retry = await provider.chat([
            *messages,
            ChatMessage(role="assistant", content=result.content),
            corrective,
        ])
        if not safety_filter.scan_violations(retry.content, hard):
            return retry
        return ChatResult(content=safety_filter.SAFE_REPLY)

    return result
```
Ensure `KinkRating` is imported in `persona/service.py` (it already imports `from app.db.enums import KinkRating, TaskStatus`).

- [ ] **Step 3b: Surface halt/hiatus in the authoritative state** — in `build_authoritative_state_block`, after computing `lines` but before the `return`, prepend a status line when frozen:
```python
    safety_state = await safety_svc.get_or_create_state(session, profile_id)
    if safety_state.is_halted:
        lines.insert(0, "SCENE HALTED (user safeworded) — make no new demands; stay calm and caring.")
    elif safety_state.on_hiatus:
        lines.insert(0, "ON HIATUS — training is paused; do not assign tasks or apply pressure.")
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/persona/test_safety_wiring.py tests/persona/test_ceiling_clamp.py tests/persona/test_persona_reply.py -q`
Expected: PASS (new wiring + ceiling guards green; the existing reply test still passes — a clean reply with `blood` only in the *system* prompt is unaffected because the filter scans the model's *output*).

- [ ] **Step 5: Commit**
```bash
git add backend/app/persona/service.py backend/tests/persona/test_safety_wiring.py backend/tests/persona/test_ceiling_clamp.py
git commit -m "feat(safety): gate generate_reply (safeword/crisis pre-LLM, hard-limit output filter)"
```

---

## Task 9: REST API — safety endpoints + data delete + register

**Files:** Create `app/schemas/safety.py`, `app/api/safety.py`, `tests/api/test_safety_api.py`; modify `app/api/profile.py` (DELETE), `app/main.py` (register).

- [ ] **Step 1: Write the failing test** — `tests/api/test_safety_api.py`:
```python
import uuid

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
        "/onboarding/profile",
        json={"is_adult": True, "consent_acknowledged": True},
    )
    assert r.status_code == 201
    return r.json()["id"]


async def test_safeword_then_resume(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/safeword")
    assert r.status_code == 200
    body = r.json()
    assert body["scene_halted"] is True
    assert body["merit_penalty"] == 0
    assert body["aftercare"]

    r = await client.get(f"/profile/{pid}/safety")
    assert r.json()["is_halted"] is True

    r = await client.post(f"/profile/{pid}/resume")
    assert r.status_code == 200
    assert r.json()["is_halted"] is False


async def test_hiatus_lower_limit_consent(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/hiatus", json={"on": True})
    assert r.status_code == 200 and r.json()["on_hiatus"] is True

    r = await client.post(f"/profile/{pid}/lower-limit", json={"kink": "wax", "rating": "hard_limit"})
    assert r.status_code == 200 and r.json()["rating"] == "hard_limit"

    r = await client.post(f"/profile/{pid}/lower-limit", json={"kink": "wax", "rating": "favorite"})
    assert r.status_code == 422  # only soft/hard limits accepted

    r = await client.post(f"/profile/{pid}/consent-check")
    assert r.status_code == 200
    r = await client.get(f"/profile/{pid}/safety")
    assert r.json()["consent_check_due"] is False


async def test_delete_everything(client):
    pid = await _new_profile(client)
    r = await client.delete(f"/profile/{pid}")
    assert r.status_code == 204
    r = await client.get(f"/profile/{pid}")
    assert r.status_code == 404


async def test_safety_endpoints_404_on_missing_profile(client):
    r = await client.post(f"/profile/{uuid.uuid4()}/safeword")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_safety_api.py -q`
Expected: FAIL — safety routes return 404/405 (not registered).

- [ ] **Step 3a: Schemas** — `app/schemas/safety.py`:
```python
from __future__ import annotations

from pydantic import BaseModel

from app.db.enums import KinkRating


class StopReceiptOut(BaseModel):
    scene_halted: bool
    denial_lifted: int
    merit_penalty: int
    aftercare: str
    message: str


class SafetyStateOut(BaseModel):
    is_halted: bool
    on_hiatus: bool
    consent_check_due: bool


class HiatusIn(BaseModel):
    on: bool


class LowerLimitIn(BaseModel):
    kink: str
    rating: KinkRating


class LowerLimitOut(BaseModel):
    kink: str
    rating: KinkRating
```

- [ ] **Step 3b: Router** — `app/api/safety.py`:
```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.safety import service as safety_svc
from app.schemas.safety import (
    HiatusIn,
    LowerLimitIn,
    LowerLimitOut,
    SafetyStateOut,
    StopReceiptOut,
)
from app.services import profile as profile_svc

router = APIRouter(prefix="/profile", tags=["safety"])


def _not_found(profile_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"profile {profile_id} not found"
    )


async def _state_out(session: AsyncSession, profile_id: uuid.UUID) -> SafetyStateOut:
    state = await safety_svc.get_or_create_state(session, profile_id)
    return SafetyStateOut(
        is_halted=state.is_halted,
        on_hiatus=state.on_hiatus,
        consent_check_due=safety_svc.consent_check_due(state),
    )


@router.post("/{profile_id}/safeword", response_model=StopReceiptOut)
async def safeword(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> StopReceiptOut:
    try:
        receipt = await safety_svc.trigger_stop(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return StopReceiptOut(
        scene_halted=receipt.scene_halted,
        denial_lifted=receipt.denial_lifted,
        merit_penalty=receipt.merit_penalty,
        aftercare=receipt.aftercare,
        message=receipt.message,
    )


@router.post("/{profile_id}/resume", response_model=SafetyStateOut)
async def resume(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> SafetyStateOut:
    try:
        await safety_svc.resume(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return await _state_out(session, profile_id)


@router.get("/{profile_id}/safety", response_model=SafetyStateOut)
async def get_safety(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> SafetyStateOut:
    try:
        out = await _state_out(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()  # get_or_create may have inserted a row
    return out


@router.post("/{profile_id}/hiatus", response_model=SafetyStateOut)
async def set_hiatus(
    profile_id: uuid.UUID, body: HiatusIn, session: AsyncSession = Depends(get_session)
) -> SafetyStateOut:
    try:
        await safety_svc.set_hiatus(session, profile_id, body.on)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return await _state_out(session, profile_id)


@router.post("/{profile_id}/lower-limit", response_model=LowerLimitOut)
async def lower_limit(
    profile_id: uuid.UUID, body: LowerLimitIn, session: AsyncSession = Depends(get_session)
) -> LowerLimitOut:
    try:
        entry = await safety_svc.lower_limit(
            session, profile_id, kink=body.kink, rating=body.rating
        )
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    await session.commit()
    return LowerLimitOut(kink=entry.kink, rating=entry.rating)


@router.post("/{profile_id}/consent-check", response_model=SafetyStateOut)
async def consent_check(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> SafetyStateOut:
    try:
        await safety_svc.record_consent_check(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return await _state_out(session, profile_id)
```

- [ ] **Step 3c: Data-delete endpoint** — in `app/api/profile.py`, add to the existing router (after `get_full_profile`):
```python
@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await svc.delete_profile(session, profile_id)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
```

- [ ] **Step 3d: Register the router** — in `app/main.py`, add the import and `include_router`:
```python
from app.api.safety import router as safety_router
...
app.include_router(safety_router)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/api/test_safety_api.py tests/api/test_profile_api.py -q`
Expected: PASS (new safety + delete endpoints green; existing profile API unaffected).

- [ ] **Step 5: Commit**
```bash
git add backend/app/schemas/safety.py backend/app/api/safety.py backend/app/api/profile.py backend/app/main.py backend/tests/api/test_safety_api.py
git commit -m "feat(safety): REST endpoints (safeword/resume/hiatus/lower-limit/consent) + delete-everything"
```

---

## Task 10: Full verification + milestone wrap

**Files:** none (verification) — then PR.

- [ ] **Step 1: Full backend suite** — from `backend/`: `uv run pytest -q` (all M1–M9 + new M8 green) and `uv run ruff check .` (clean). Fix anything red before proceeding.
- [ ] **Step 2: Migration round-trip** — confirm `tests/db/test_migration.py` passes (upgrade→downgrade→upgrade with `safety_state`).
- [ ] **Step 3: Push + CI green**
```bash
git push -u origin feat/m8-safety
```
The `backend` CI job (Postgres service) runs ruff + the full pytest suite. Confirm it passes.
- [ ] **Step 4: Open the PR**
```bash
gh pr create --base master --head feat/m8-safety \
  --title "M8: Safety system — safeword, limit enforcement, well-being, data control" \
  --body "Deterministic backend safety per spec §9. See docs/superpowers/plans/2026-06-07-core-obedience-loop-m8-safety.md"
```

---

## Verification (end-to-end for M8)

1. **Deterministic & LLM-independent:** safeword and crisis are intercepted in `generate_reply` *before* any provider call (`provider.calls == []` in tests); the stop service touches only Postgres.
2. **Safeword:** halts the scene, lifts all denial timers, applies **no** merit penalty; returns a calm out-of-persona receipt + aftercare (per prefs).
3. **Limit enforcement:** hard limits are injected every turn (existing) **and** the model's reply is scanned; a violation triggers one corrective regenerate, then a safe deterministic redaction.
4. **Intensity ceiling:** regression test proves severity stays clamped at rock-bottom merit.
5. **Well-being:** hiatus (no penalty — the sweep skips frozen profiles), lower-a-limit (honored immediately via authoritative-state injection), periodic consent check-in.
6. **Crisis fallback:** distress language breaks character and surfaces real resources.
7. **Data control:** `DELETE /profile/{id}` purges every related row.
8. **CI green** on the pushed branch.

**M8 is done when** every spec §9 control exists as a deterministic backend service with REST endpoints and tests, wired into the turn path, with the loop respecting halt/hiatus — leaving the **safety shell UI** to M9b (which can now bind to these endpoints).

---

## Self-Review

**Spec §9 coverage:**
- 18+ gate + consent → M3 (pre-existing; noted). ✓
- Safeword/panic (control + phrases, pre-LLM, halt + timers/denial + caring mode + aftercare) → Tasks 2,4,8,9. ✓
- Limit enforcement (inject every turn + output check that blocks/regenerates) → injection pre-existing; output filter Tasks 3,8. ✓
- Intensity ceiling (clamped even at zero merit) → pre-existing clamp + regression test Task 8. ✓
- Aftercare (on safeword, per prefs) → Task 4. ✓
- Well-being (hiatus w/o penalty, lower a limit immediately, periodic consent check-in) → Tasks 5,6,9. ✓
- Crisis fallback (break character + resources) → Tasks 2,4,8. ✓
- Data control (one-tap delete-everything) → Tasks 7,9. ✓

**§10 testing coverage:** limit-checking unit tests (Task 3), safeword fires with the LLM stubbed (Task 8, `MockLLMProvider`, `provider.calls == []`), hard-limit output filter blocks (Task 8), ceiling clamp holds (Task 8). ✓ (E2E Playwright remains a frontend concern → M9b.)

**Placeholder scan:** every code step contains complete, runnable code; no TODO/"handle errors"/"similar to" left. The one deferred item is explicitly out of scope (Phase-2 device actuation kill — spec §9 itself marks it Phase 2).

**Type/name consistency:** `SafetyState(is_halted, on_hiatus, last_safeword_at, last_consent_check_at)` used identically across model, service, schema, API. `safety_svc.get_or_create_state / trigger_stop / resume / is_frozen / set_hiatus / lower_limit / consent_check_due / record_consent_check / aftercare_message / crisis_message`, plus constants `CALM_STOP_MESSAGE / HOLD_MESSAGE / CRISIS_MESSAGE` — referenced consistently by `generate_reply` (Task 8) and the API (Task 9). `filter.scan_violations / corrective_note / SAFE_REPLY` and `detect.detect_safeword / detect_crisis` match call sites. `profile_svc.delete_profile` matches the DELETE route. Migration `down_revision='2c12f7878811'` chains the current head.

---

## Notes for execution
- **Branch:** `feat/m8-safety` (not `master`). After merge, realign: `git checkout master && git fetch origin --prune && git reset --hard origin/master`.
- **Backend dev caveat:** clear `PYTHONHOME`/`PYTHONPATH` before `uv` (broken global Python on the dev box). CI/clean machines unaffected.
- **No PG enums** in the new migration — `SafetyState` uses plain Boolean/DateTime columns (M5/M6 convention) so the round-trip test needs no `_ENUM_TYPES` change.
- **Import direction:** `loop → safety` and `persona → safety` are one-way; `safety` imports only `economy` + `profile` services + models. No cycles.
- **`lower_limit` only tightens** (SOFT/HARD limit ratings); loosening a limit is a normal profile edit (M9b), deliberately not a "safety" action.
- **Phase-2 deferrals (per spec):** device-actuation kill on safeword, and the safety-shell UI (M9b). Not in M8.
```
