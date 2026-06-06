# Milestone 3 — Onboarding & Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the onboarding flow and profile API that populates the M2 schema — consent gate, BDSM-archetype questionnaire with scoring, kink/limits sheet, toy inventory, SO context, goals, and editable character model — so later milestones have a real, user-populated profile to read from.

**Architecture:** A thin FastAPI API layer (`app/api/`) over small pure-Python services (`app/services/`) and Pydantic DTOs (`app/schemas/`). The `sub_profile` row is the aggregate root: creating a profile also creates its default `character_model` and `economy_state`. Archetype scoring is a pure, unit-tested function over a built-in questionnaire; everything else is CRUD against the async session. No auth/users table yet (single-user v1) — the profile id is the handle.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.0 async (psycopg3), pytest + httpx `AsyncClient`. Schema/models already exist from M2.

---

## Context

M2 merged: all ten tables exist as SQLAlchemy models (`SubProfile`, `ArchetypeResult`, `KinkEntry`, `Toy`, `SoContext`, `Goal`, `CharacterModel`, `EconomyState`, `DenialTimer`, `Task`), with an Alembic migration, async `get_session` dependency, and a Postgres-backed test harness (`tests/conftest.py` provides a `session` fixture against `smistress_test`). The CI `backend` job already has a `postgres:16` service. M3 implements spec **§4** (Sub Profile & Onboarding) and the editing half of **§5A** (character model — the schema exists; M3 lets the user read/edit it). The *consumption* of this data by the persona engine is M4; M3 is data in.

### Patterns to follow (already established)

- **Endpoints get the DB via `Depends(get_session)`** (see `app/main.py::db_health`). Tests override it: `app.dependency_overrides[get_session] = lambda: session` then drive requests with `httpx.AsyncClient(transport=ASGITransport(app=app))` (see `tests/test_db_health.py`).
- **Models** use SQLAlchemy 2.0 typed `Mapped`/`mapped_column`, UUID PKs (`default=uuid.uuid4`), native PG enums, JSONB for dicts. `SubProfile` owns `kinks`/`toys`/`goals`/`archetype_results`/`so_context` via `cascade="all, delete-orphan"`. `CharacterModel` and `EconomyState` are `unique` one-to-one on `profile_id` but are **not** declared as relationships on `SubProfile` — query them directly by `profile_id`.
- **Enums** live in `app/db/enums.py`: `KinkRating` (favorite/like/curious/soft_limit/hard_limit/na), `GoalStatus`, `ProofRequirement`, `TaskStatus`.
- **Local dev caveat:** clear `PYTHONHOME`/`PYTHONPATH` in-session before running `uv` (see `smistress-dev-environment` memory). CI/clean machines unaffected. Commands below are shown in their canonical `uv run …` form.

## File Structure

New (all under `backend/`):

- `app/services/archetype.py` — built-in archetype questionnaire + pure `score_archetypes()`.
- `app/services/kink_catalog.py` — built-in kink list for the limits sheet.
- `app/schemas/__init__.py`, `app/schemas/onboarding.py` — Pydantic request/response DTOs.
- `app/services/__init__.py`, `app/services/profile.py` — profile aggregate operations (create profile + defaults, upserts).
- `app/api/__init__.py`, `app/api/onboarding.py` — questionnaire/profile-creation routes.
- `app/api/profile.py` — profile sub-resource routes (archetype, kinks, toys, goals, SO, character, read).
- Tests: `tests/services/test_archetype.py`, `tests/services/test_profile_service.py`, `tests/api/test_onboarding.py`, `tests/api/test_profile_api.py`.

Modify:

- `app/main.py` — include the two routers.

Each file has one responsibility; routes are split into "onboarding entry" (`onboarding.py`) vs "profile sub-resources" (`profile.py`) so neither grows unwieldy.

---

## Task 1: Archetype questionnaire + scoring service (pure)

**Files:**
- Create: `backend/app/services/__init__.py` (empty), `backend/app/services/archetype.py`
- Test: `backend/tests/services/__init__.py` (empty), `backend/tests/services/test_archetype.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_archetype.py
import pytest

from app.services.archetype import (
    ARCHETYPES,
    MAX_ANSWER,
    QUESTIONNAIRE,
    score_archetypes,
    unknown_answer_ids,
)


def test_questionnaire_ids_unique_and_archetypes_known():
    ids = [q["id"] for q in QUESTIONNAIRE]
    assert len(ids) == len(set(ids))  # no duplicate ids
    assert all(q["archetype"] in ARCHETYPES for q in QUESTIONNAIRE)


def test_all_max_answers_score_100_for_that_archetype():
    answers = {q["id"]: MAX_ANSWER for q in QUESTIONNAIRE}
    scores = score_archetypes(answers)
    assert set(scores) == set(ARCHETYPES)
    assert all(v == 100 for v in scores.values())


def test_unanswered_and_zero_score_zero():
    assert all(v == 0 for v in score_archetypes({}).values())


def test_partial_answers_scale_linearly():
    # answer every 'submissive' statement at 2 of 4 -> 50%
    answers = {q["id"]: 2 for q in QUESTIONNAIRE if q["archetype"] == "submissive"}
    scores = score_archetypes(answers)
    assert scores["submissive"] == 50
    assert scores["slave"] == 0  # untouched archetype stays 0


def test_unknown_answer_ids_detected():
    assert unknown_answer_ids({"q1": 3, "bogus": 1}) == {"bogus"}
    assert unknown_answer_ids({"q1": 3}) == set()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_archetype.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services'`.

- [ ] **Step 3: Implement the questionnaire + scorer**

```python
# backend/app/services/archetype.py
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
    {"id": "q1", "archetype": "submissive", "text": "I feel most at ease when someone else is in charge."},
    {"id": "q2", "archetype": "submissive", "text": "Following clear instructions brings me satisfaction."},
    {"id": "q3", "archetype": "slave", "text": "I want to devote myself entirely to another's service."},
    {"id": "q4", "archetype": "slave", "text": "Being owned and used for someone's benefit appeals to me."},
    {"id": "q5", "archetype": "brat", "text": "I enjoy provoking a reaction by misbehaving."},
    {"id": "q6", "archetype": "brat", "text": "Being made to comply after I resist is exciting."},
    {"id": "q7", "archetype": "pet", "text": "I like being cared for and treated as a cherished pet."},
    {"id": "q8", "archetype": "pet", "text": "Affection and praise motivate me more than strictness."},
    {"id": "q9", "archetype": "masochist", "text": "Physical discomfort can be pleasurable to me."},
    {"id": "q10", "archetype": "masochist", "text": "I crave intense sensation, including pain."},
    {"id": "q11", "archetype": "degradee", "text": "Humiliation and verbal degradation arouse me."},
    {"id": "q12", "archetype": "degradee", "text": "Being talked down to during a scene excites me."},
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
```

Also create empty `backend/app/services/__init__.py` and `backend/tests/services/__init__.py`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/services/test_archetype.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/__init__.py backend/app/services/archetype.py \
        backend/tests/services/__init__.py backend/tests/services/test_archetype.py
git commit -m "feat: add archetype questionnaire and scoring service (spec 4)"
```

---

## Task 2: Kink catalog (built-in limits-sheet list)

**Files:**
- Create: `backend/app/services/kink_catalog.py`
- Test: `backend/tests/services/test_kink_catalog.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_kink_catalog.py
from app.services.kink_catalog import KINK_CATALOG, is_known_kink


def test_catalog_is_nonempty_and_unique():
    assert len(KINK_CATALOG) > 0
    assert len(KINK_CATALOG) == len(set(KINK_CATALOG))


def test_is_known_kink():
    assert is_known_kink(KINK_CATALOG[0]) is True
    assert is_known_kink("not_a_real_kink") is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_kink_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# backend/app/services/kink_catalog.py
from __future__ import annotations

# Built-in kink-sheet vocabulary for v1. The user rates each (favorite/like/
# curious/soft_limit/hard_limit/na); custom kinks may be added later.
KINK_CATALOG: tuple[str, ...] = (
    "bondage",
    "spanking",
    "impact_play",
    "orgasm_control",
    "chastity",
    "service",
    "humiliation",
    "exhibitionism",
    "sensory_deprivation",
    "roleplay",
    "discipline",
    "edging",
    "worship",
    "tasks_and_chores",
)

_KNOWN = frozenset(KINK_CATALOG)


def is_known_kink(name: str) -> bool:
    return name in _KNOWN
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/services/test_kink_catalog.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/kink_catalog.py backend/tests/services/test_kink_catalog.py
git commit -m "feat: add built-in kink catalog for limits sheet"
```

---

## Task 3: Pydantic schemas (onboarding DTOs)

**Files:**
- Create: `backend/app/schemas/__init__.py` (empty), `backend/app/schemas/onboarding.py`
- Test: `backend/tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_schemas.py
import pytest
from pydantic import ValidationError

from app.db.enums import KinkRating
from app.schemas.onboarding import (
    ArchetypeSubmission,
    CharacterUpdate,
    KinkItem,
    KinkSheetIn,
    ProfileCreate,
)


def test_profile_create_defaults_and_bounds():
    p = ProfileCreate(is_adult=True, consent_acknowledged=True)
    assert p.intensity_ceiling == 50
    with pytest.raises(ValidationError):
        ProfileCreate(is_adult=True, consent_acknowledged=True, intensity_ceiling=101)


def test_archetype_submission_rejects_out_of_range_answer():
    ArchetypeSubmission(answers={"q1": 4})  # ok
    with pytest.raises(ValidationError):
        ArchetypeSubmission(answers={"q1": 5})


def test_kink_item_uses_enum():
    item = KinkItem(kink="bondage", rating=KinkRating.FAVORITE)
    assert item.rating is KinkRating.FAVORITE
    sheet = KinkSheetIn(entries=[item])
    assert len(sheet.entries) == 1


def test_character_update_dials_bounded_and_optional():
    c = CharacterUpdate(strictness=90)
    assert c.strictness == 90
    assert c.warmth is None  # unset fields stay None (partial update)
    with pytest.raises(ValidationError):
        CharacterUpdate(sadism=200)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas'`.

- [ ] **Step 3: Implement the DTOs**

```python
# backend/app/schemas/onboarding.py
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import GoalStatus, KinkRating

Dial = Field(ge=0, le=100)


# ---- create / read profile ------------------------------------------------
class ProfileCreate(BaseModel):
    is_adult: bool
    consent_acknowledged: bool
    intensity_ceiling: int = Field(default=50, ge=0, le=100)
    aftercare_prefs: str | None = None


class ProfileCreated(BaseModel):
    id: UUID
    intensity_ceiling: int


# ---- archetype ------------------------------------------------------------
class ArchetypeSubmission(BaseModel):
    # statement id -> agreement 0..4
    answers: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    def __init__(self, **data):
        super().__init__(**data)
        for v in self.answers.values():
            if not (0 <= v <= 4):
                raise ValueError("answers must be between 0 and 4")


class ArchetypeResultOut(BaseModel):
    scores: dict[str, int]


# ---- kink sheet -----------------------------------------------------------
class KinkItem(BaseModel):
    kink: str
    rating: KinkRating


class KinkSheetIn(BaseModel):
    entries: list[KinkItem]


# ---- toys -----------------------------------------------------------------
class ToyIn(BaseModel):
    name: str
    type: str
    intiface_capable: bool = False
    notes: str | None = None


class ToyOut(ToyIn):
    id: UUID
    model_config = ConfigDict(from_attributes=True)


# ---- goals ----------------------------------------------------------------
class GoalIn(BaseModel):
    title: str
    description: str = ""


class GoalOut(BaseModel):
    id: UUID
    title: str
    description: str
    status: GoalStatus
    model_config = ConfigDict(from_attributes=True)


# ---- SO context -----------------------------------------------------------
class SoContextIn(BaseModel):
    description: str = ""
    values: str | None = None
    dynamic: str | None = None


# ---- character model ------------------------------------------------------
class CharacterUpdate(BaseModel):
    """Partial update — only provided fields change."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    honorific: str | None = None
    address_term: str | None = None
    pronouns: str | None = None
    archetype_blend: dict[str, int] | None = None
    warmth: int | None = Field(default=None, ge=0, le=100)
    strictness: int | None = Field(default=None, ge=0, le=100)
    sadism: int | None = Field(default=None, ge=0, le=100)
    formality: int | None = Field(default=None, ge=0, le=100)
    verbosity: int | None = Field(default=None, ge=0, le=100)
    crudeness: int | None = Field(default=None, ge=0, le=100)
    wit: int | None = Field(default=None, ge=0, le=100)
    signature_flavor: str | None = None


class CharacterOut(BaseModel):
    name: str | None
    honorific: str
    address_term: str
    pronouns: str
    archetype_blend: dict
    warmth: int
    strictness: int
    sadism: int
    formality: int
    verbosity: int
    crudeness: int
    wit: int
    signature_flavor: str | None
    model_config = ConfigDict(from_attributes=True)


# ---- assembled profile read ----------------------------------------------
class KinkOut(BaseModel):
    kink: str
    rating: KinkRating
    model_config = ConfigDict(from_attributes=True)


class ProfileRead(BaseModel):
    id: UUID
    intensity_ceiling: int
    aftercare_prefs: str | None
    archetype_scores: dict[str, int]
    kinks: list[KinkOut]
    toys: list[ToyOut]
    goals: list[GoalOut]
    so_context: SoContextIn | None
    character: CharacterOut
```

Create empty `backend/app/schemas/__init__.py`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/__init__.py backend/app/schemas/onboarding.py backend/tests/test_schemas.py
git commit -m "feat: add onboarding/profile pydantic schemas"
```

---

## Task 4: Profile service — create aggregate + upserts

**Files:**
- Create: `backend/app/services/profile.py`
- Test: `backend/tests/services/test_profile_service.py`

The service owns multi-entity operations so endpoints stay thin. All functions take an `AsyncSession` and **flush but do not commit** (the endpoint/caller controls the transaction boundary), except where a generated id is needed — they `flush()` to populate ids.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_profile_service.py
import pytest
from sqlalchemy import select

from app.db.enums import KinkRating
from app.db.models.character import CharacterModel
from app.db.models.economy import EconomyState
from app.db.models.profile import KinkEntry, SubProfile
from app.schemas.onboarding import KinkItem, ProfileCreate
from app.services import profile as svc


async def test_create_profile_seeds_character_and_economy(session):
    profile = await svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True, intensity_ceiling=70)
    )
    await session.commit()

    assert profile.intensity_ceiling == 70
    char = (await session.execute(select(CharacterModel))).scalar_one()
    assert char.profile_id == profile.id
    assert char.honorific == "Headmistress"  # default persona
    econ = (await session.execute(select(EconomyState))).scalar_one()
    assert econ.profile_id == profile.id
    assert econ.merit == 0


async def test_replace_kinks_is_idempotent(session):
    profile = await svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await svc.replace_kinks(session, profile.id, [
        KinkItem(kink="bondage", rating=KinkRating.FAVORITE),
        KinkItem(kink="humiliation", rating=KinkRating.SOFT_LIMIT),
    ])
    await session.commit()
    # replacing again with one entry leaves exactly one row
    await svc.replace_kinks(session, profile.id, [
        KinkItem(kink="spanking", rating=KinkRating.LIKE),
    ])
    await session.commit()

    rows = (await session.execute(
        select(KinkEntry).where(KinkEntry.profile_id == profile.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].kink == "spanking"


async def test_get_profile_or_404_raises_for_missing(session):
    import uuid
    with pytest.raises(svc.ProfileNotFound):
        await svc.get_profile(session, uuid.uuid4())
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_profile_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.profile'`.

- [ ] **Step 3: Implement the service**

```python
# backend/app/services/profile.py
from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.character import CharacterModel
from app.db.models.economy import EconomyState
from app.db.models.profile import (
    ArchetypeResult,
    Goal,
    KinkEntry,
    SoContext,
    SubProfile,
    Toy,
)
from app.schemas.onboarding import (
    CharacterUpdate,
    GoalIn,
    KinkItem,
    ProfileCreate,
    SoContextIn,
    ToyIn,
)


class ProfileNotFound(Exception):
    pass


async def create_profile(session: AsyncSession, data: ProfileCreate) -> SubProfile:
    """Create the aggregate root plus its default character model and economy."""
    profile = SubProfile(
        intensity_ceiling=data.intensity_ceiling,
        aftercare_prefs=data.aftercare_prefs,
    )
    session.add(profile)
    await session.flush()  # populate profile.id
    session.add(CharacterModel(profile_id=profile.id))  # all-default persona
    session.add(EconomyState(profile_id=profile.id))
    await session.flush()
    return profile


async def get_profile(session: AsyncSession, profile_id: uuid.UUID) -> SubProfile:
    profile = await session.get(SubProfile, profile_id)
    if profile is None:
        raise ProfileNotFound(str(profile_id))
    return profile


async def get_character(session: AsyncSession, profile_id: uuid.UUID) -> CharacterModel:
    await get_profile(session, profile_id)  # 404 if profile missing
    char = (await session.execute(
        select(CharacterModel).where(CharacterModel.profile_id == profile_id)
    )).scalar_one()
    return char


async def latest_archetype_scores(
    session: AsyncSession, profile_id: uuid.UUID
) -> dict[str, int]:
    row = (await session.execute(
        select(ArchetypeResult)
        .where(ArchetypeResult.profile_id == profile_id)
        .order_by(ArchetypeResult.created_at.desc())
    )).scalars().first()
    return dict(row.scores) if row else {}


async def add_archetype_result(
    session: AsyncSession,
    profile_id: uuid.UUID,
    raw_answers: dict[str, int],
    scores: dict[str, int],
) -> ArchetypeResult:
    await get_profile(session, profile_id)
    result = ArchetypeResult(
        profile_id=profile_id, raw_answers=raw_answers, scores=scores
    )
    session.add(result)
    await session.flush()
    return result


async def replace_kinks(
    session: AsyncSession, profile_id: uuid.UUID, entries: list[KinkItem]
) -> None:
    """Full replace — the kink sheet is authoritative, not incremental."""
    await get_profile(session, profile_id)
    await session.execute(delete(KinkEntry).where(KinkEntry.profile_id == profile_id))
    for item in entries:
        session.add(
            KinkEntry(profile_id=profile_id, kink=item.kink, rating=item.rating)
        )
    await session.flush()


async def add_toy(session: AsyncSession, profile_id: uuid.UUID, data: ToyIn) -> Toy:
    await get_profile(session, profile_id)
    toy = Toy(
        profile_id=profile_id,
        name=data.name,
        type=data.type,
        intiface_capable=data.intiface_capable,
        notes=data.notes,
    )
    session.add(toy)
    await session.flush()
    return toy


async def list_toys(session: AsyncSession, profile_id: uuid.UUID) -> list[Toy]:
    await get_profile(session, profile_id)
    return list((await session.execute(
        select(Toy).where(Toy.profile_id == profile_id).order_by(Toy.name)
    )).scalars().all())


async def add_goal(session: AsyncSession, profile_id: uuid.UUID, data: GoalIn) -> Goal:
    await get_profile(session, profile_id)
    goal = Goal(profile_id=profile_id, title=data.title, description=data.description)
    session.add(goal)
    await session.flush()
    return goal


async def list_goals(session: AsyncSession, profile_id: uuid.UUID) -> list[Goal]:
    await get_profile(session, profile_id)
    return list((await session.execute(
        select(Goal).where(Goal.profile_id == profile_id).order_by(Goal.created_at)
    )).scalars().all())


async def upsert_so_context(
    session: AsyncSession, profile_id: uuid.UUID, data: SoContextIn
) -> SoContext:
    await get_profile(session, profile_id)
    so = (await session.execute(
        select(SoContext).where(SoContext.profile_id == profile_id)
    )).scalar_one_or_none()
    if so is None:
        so = SoContext(profile_id=profile_id)
        session.add(so)
    so.description = data.description
    so.values = data.values
    so.dynamic = data.dynamic
    await session.flush()
    return so


async def update_character(
    session: AsyncSession, profile_id: uuid.UUID, data: CharacterUpdate
) -> CharacterModel:
    char = await get_character(session, profile_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(char, field, value)
    await session.flush()
    return char
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/services/test_profile_service.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/profile.py backend/tests/services/test_profile_service.py
git commit -m "feat: add profile service (create aggregate, kink/toy/goal/so/character ops)"
```

---

## Task 5: Onboarding router — questionnaire + create profile

**Files:**
- Create: `backend/app/api/__init__.py` (empty), `backend/app/api/onboarding.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/__init__.py` (empty), `backend/tests/api/test_onboarding.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_onboarding.py
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


async def test_get_questionnaire(client):
    r = await client.get("/onboarding/questionnaire")
    assert r.status_code == 200
    body = r.json()
    assert len(body["statements"]) >= 14
    assert "bondage" in body["kinks"]
    assert body["answer_scale"]["max"] == 4


async def test_create_profile_requires_consent_and_adult(client):
    r = await client.post(
        "/onboarding/profile",
        json={"is_adult": True, "consent_acknowledged": False},
    )
    assert r.status_code == 422

    r = await client.post(
        "/onboarding/profile",
        json={"is_adult": True, "consent_acknowledged": True, "intensity_ceiling": 60},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["intensity_ceiling"] == 60
    assert "id" in body
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_onboarding.py -v`
Expected: FAIL — 404 on `/onboarding/questionnaire` (router not mounted).

- [ ] **Step 3: Implement the router**

```python
# backend/app/api/onboarding.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.onboarding import ProfileCreate, ProfileCreated
from app.services import profile as svc
from app.services.archetype import MAX_ANSWER, QUESTIONNAIRE
from app.services.kink_catalog import KINK_CATALOG

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/questionnaire")
async def get_questionnaire() -> dict:
    return {
        "statements": list(QUESTIONNAIRE),
        "kinks": list(KINK_CATALOG),
        "answer_scale": {"min": 0, "max": MAX_ANSWER},
    }


@router.post("/profile", response_model=ProfileCreated, status_code=status.HTTP_201_CREATED)
async def create_profile(
    data: ProfileCreate, session: AsyncSession = Depends(get_session)
) -> ProfileCreated:
    if not data.is_adult or not data.consent_acknowledged:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="18+ acknowledgement and consent are required to begin.",
        )
    profile = await svc.create_profile(session, data)
    await session.commit()
    return ProfileCreated(id=profile.id, intensity_ceiling=profile.intensity_ceiling)
```

- [ ] **Step 4: Mount the router in `main.py`**

In `backend/app/main.py`, add the import near the other `app.` imports and include the router after `app = FastAPI(...)`:

```python
from app.api.onboarding import router as onboarding_router
```
```python
app.include_router(onboarding_router)
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/api/test_onboarding.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/__init__.py backend/app/api/onboarding.py backend/app/main.py \
        backend/tests/api/__init__.py backend/tests/api/test_onboarding.py
git commit -m "feat: add onboarding router (questionnaire + create profile with consent gate)"
```

---

## Task 6: Profile router — archetype submission

**Files:**
- Create: `backend/app/api/profile.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_profile_api.py`

The profile router holds all `/profile/{profile_id}/…` sub-resources. We build it up across Tasks 6–11 and add one test fixture + helper now, reused by later tasks.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_profile_api.py
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
        "/onboarding/profile",
        json={"is_adult": True, "consent_acknowledged": True},
    )
    assert r.status_code == 201
    return r.json()["id"]


async def test_submit_archetype_returns_scores(client):
    pid = await _new_profile(client)
    answers = {"q1": 4, "q2": 4}  # both 'submissive' statements maxed
    r = await client.post(f"/profile/{pid}/archetype", json={"answers": answers})
    assert r.status_code == 200
    scores = r.json()["scores"]
    assert scores["submissive"] == 100
    assert scores["slave"] == 0


async def test_submit_archetype_rejects_unknown_id(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/archetype", json={"answers": {"bogus": 3}})
    assert r.status_code == 422


async def test_archetype_on_missing_profile_404(client):
    import uuid
    r = await client.post(f"/profile/{uuid.uuid4()}/archetype", json={"answers": {}})
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_profile_api.py -v`
Expected: FAIL — 404 (router not mounted).

- [ ] **Step 3: Implement the router with a shared 404 handler + archetype route**

```python
# backend/app/api/profile.py
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.onboarding import (
    ArchetypeResultOut,
    ArchetypeSubmission,
)
from app.services import profile as svc
from app.services.archetype import score_archetypes, unknown_answer_ids

router = APIRouter(prefix="/profile", tags=["profile"])


def _not_found(profile_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"profile {profile_id} not found",
    )


@router.post("/{profile_id}/archetype", response_model=ArchetypeResultOut)
async def submit_archetype(
    profile_id: uuid.UUID,
    body: ArchetypeSubmission,
    session: AsyncSession = Depends(get_session),
) -> ArchetypeResultOut:
    bad = unknown_answer_ids(body.answers)
    if bad:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown questionnaire ids: {sorted(bad)}",
        )
    scores = score_archetypes(body.answers)
    try:
        await svc.add_archetype_result(session, profile_id, body.answers, scores)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return ArchetypeResultOut(scores=scores)
```

- [ ] **Step 4: Mount the router in `main.py`**

In `backend/app/main.py`:

```python
from app.api.profile import router as profile_router
```
```python
app.include_router(profile_router)
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/api/test_profile_api.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/profile.py backend/app/main.py backend/tests/api/test_profile_api.py
git commit -m "feat: add archetype submission endpoint with scoring"
```

---

## Task 7: Profile router — kink sheet (full replace)

**Files:**
- Modify: `backend/app/api/profile.py`
- Test: `backend/tests/api/test_profile_api.py` (append)

- [ ] **Step 1: Write the failing test (append to `test_profile_api.py`)**

```python
async def test_put_kinks_replaces_sheet(client):
    pid = await _new_profile(client)
    r = await client.put(f"/profile/{pid}/kinks", json={"entries": [
        {"kink": "bondage", "rating": "favorite"},
        {"kink": "humiliation", "rating": "soft_limit"},
    ]})
    assert r.status_code == 200
    assert r.json()["count"] == 2

    # full replace: a smaller sheet wins
    r = await client.put(f"/profile/{pid}/kinks", json={"entries": [
        {"kink": "spanking", "rating": "like"},
    ]})
    assert r.status_code == 200
    assert r.json()["count"] == 1


async def test_put_kinks_rejects_bad_rating(client):
    pid = await _new_profile(client)
    r = await client.put(f"/profile/{pid}/kinks", json={"entries": [
        {"kink": "bondage", "rating": "not_a_rating"},
    ]})
    assert r.status_code == 422
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_profile_api.py -k kinks -v`
Expected: FAIL — 404/405 (route missing).

- [ ] **Step 3: Add the route to `profile.py`**

Add the import to the existing schema import block:

```python
from app.schemas.onboarding import (
    ArchetypeResultOut,
    ArchetypeSubmission,
    KinkSheetIn,
)
```

Add the route:

```python
@router.put("/{profile_id}/kinks")
async def put_kinks(
    profile_id: uuid.UUID,
    body: KinkSheetIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await svc.replace_kinks(session, profile_id, body.entries)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return {"count": len(body.entries)}
```

(The invalid enum value is rejected by Pydantic at request parsing → automatic 422.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/api/test_profile_api.py -k kinks -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/profile.py backend/tests/api/test_profile_api.py
git commit -m "feat: add kink-sheet replace endpoint (the limits system)"
```

---

## Task 8: Profile router — toys (add + list)

**Files:**
- Modify: `backend/app/api/profile.py`
- Test: `backend/tests/api/test_profile_api.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
async def test_add_and_list_toys(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/toys", json={
        "name": "Apex", "type": "vibrator", "intiface_capable": True,
    })
    assert r.status_code == 201
    assert r.json()["intiface_capable"] is True

    r = await client.get(f"/profile/{pid}/toys")
    assert r.status_code == 200
    toys = r.json()
    assert len(toys) == 1
    assert toys[0]["name"] == "Apex"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_profile_api.py -k toys -v`
Expected: FAIL — 404/405.

- [ ] **Step 3: Add routes to `profile.py`**

Extend the schema import block with `ToyIn, ToyOut`:

```python
from app.schemas.onboarding import (
    ArchetypeResultOut,
    ArchetypeSubmission,
    KinkSheetIn,
    ToyIn,
    ToyOut,
)
```

Add routes:

```python
@router.post("/{profile_id}/toys", response_model=ToyOut, status_code=status.HTTP_201_CREATED)
async def add_toy(
    profile_id: uuid.UUID,
    body: ToyIn,
    session: AsyncSession = Depends(get_session),
) -> ToyOut:
    try:
        toy = await svc.add_toy(session, profile_id, body)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return ToyOut.model_validate(toy)


@router.get("/{profile_id}/toys", response_model=list[ToyOut])
async def list_toys(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[ToyOut]:
    try:
        toys = await svc.list_toys(session, profile_id)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    return [ToyOut.model_validate(t) for t in toys]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/api/test_profile_api.py -k toys -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/profile.py backend/tests/api/test_profile_api.py
git commit -m "feat: add toy inventory endpoints (add + list)"
```

---

## Task 9: Profile router — goals (add + list)

**Files:**
- Modify: `backend/app/api/profile.py`
- Test: `backend/tests/api/test_profile_api.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
async def test_add_and_list_goals(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/goals", json={
        "title": "Daily posture practice", "description": "10 minutes each morning",
    })
    assert r.status_code == 201
    assert r.json()["status"] == "active"

    r = await client.get(f"/profile/{pid}/goals")
    assert r.status_code == 200
    assert r.json()[0]["title"] == "Daily posture practice"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_profile_api.py -k goals -v`
Expected: FAIL — 404/405.

- [ ] **Step 3: Add routes to `profile.py`**

Extend the schema import block with `GoalIn, GoalOut`:

```python
from app.schemas.onboarding import (
    ArchetypeResultOut,
    ArchetypeSubmission,
    GoalIn,
    GoalOut,
    KinkSheetIn,
    ToyIn,
    ToyOut,
)
```

Add routes:

```python
@router.post("/{profile_id}/goals", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
async def add_goal(
    profile_id: uuid.UUID,
    body: GoalIn,
    session: AsyncSession = Depends(get_session),
) -> GoalOut:
    try:
        goal = await svc.add_goal(session, profile_id, body)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return GoalOut.model_validate(goal)


@router.get("/{profile_id}/goals", response_model=list[GoalOut])
async def list_goals(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[GoalOut]:
    try:
        goals = await svc.list_goals(session, profile_id)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    return [GoalOut.model_validate(g) for g in goals]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/api/test_profile_api.py -k goals -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/profile.py backend/tests/api/test_profile_api.py
git commit -m "feat: add goals endpoints (add + list)"
```

---

## Task 10: Profile router — SO context (upsert) + character model (read/update)

**Files:**
- Modify: `backend/app/api/profile.py`
- Test: `backend/tests/api/test_profile_api.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
async def test_upsert_so_context(client):
    pid = await _new_profile(client)
    r = await client.put(f"/profile/{pid}/so-context", json={
        "description": "Training for my partner", "dynamic": "24/7-lite",
    })
    assert r.status_code == 200
    # upsert again updates in place
    r = await client.put(f"/profile/{pid}/so-context", json={"description": "Updated"})
    assert r.status_code == 200
    assert r.json()["description"] == "Updated"


async def test_get_and_update_character(client):
    pid = await _new_profile(client)
    r = await client.get(f"/profile/{pid}/character")
    assert r.status_code == 200
    body = r.json()
    assert body["honorific"] == "Headmistress"
    assert body["strictness"] == 80
    assert body["archetype_blend"] == {"governess": 70, "drill_instructor": 30}

    r = await client.put(f"/profile/{pid}/character", json={"sadism": 65, "name": "Vesper"})
    assert r.status_code == 200
    assert r.json()["sadism"] == 65
    assert r.json()["name"] == "Vesper"
    assert r.json()["strictness"] == 80  # untouched dial unchanged

    # out-of-range dial rejected
    r = await client.put(f"/profile/{pid}/character", json={"wit": 250})
    assert r.status_code == 422
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_profile_api.py -k "so_context or character" -v`
Expected: FAIL — 404/405.

- [ ] **Step 3: Add routes to `profile.py`**

Extend the schema import block with `CharacterOut, CharacterUpdate, SoContextIn`:

```python
from app.schemas.onboarding import (
    ArchetypeResultOut,
    ArchetypeSubmission,
    CharacterOut,
    CharacterUpdate,
    GoalIn,
    GoalOut,
    KinkSheetIn,
    SoContextIn,
    ToyIn,
    ToyOut,
)
```

Add routes:

```python
@router.put("/{profile_id}/so-context", response_model=SoContextIn)
async def put_so_context(
    profile_id: uuid.UUID,
    body: SoContextIn,
    session: AsyncSession = Depends(get_session),
) -> SoContextIn:
    try:
        so = await svc.upsert_so_context(session, profile_id, body)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return SoContextIn(description=so.description, values=so.values, dynamic=so.dynamic)


@router.get("/{profile_id}/character", response_model=CharacterOut)
async def get_character(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> CharacterOut:
    try:
        char = await svc.get_character(session, profile_id)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    return CharacterOut.model_validate(char)


@router.put("/{profile_id}/character", response_model=CharacterOut)
async def update_character(
    profile_id: uuid.UUID,
    body: CharacterUpdate,
    session: AsyncSession = Depends(get_session),
) -> CharacterOut:
    try:
        char = await svc.update_character(session, profile_id, body)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return CharacterOut.model_validate(char)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/api/test_profile_api.py -k "so_context or character" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/profile.py backend/tests/api/test_profile_api.py
git commit -m "feat: add SO-context upsert and character-model read/update endpoints (spec 5A)"
```

---

## Task 11: Profile router — assembled read (`GET /profile/{id}`)

**Files:**
- Modify: `backend/app/api/profile.py`, `backend/app/services/profile.py`
- Test: `backend/tests/api/test_profile_api.py` (append)

This returns the full profile the persona engine (M4) will read: ceiling, latest archetype scores, kinks, toys, goals, SO context, character model.

- [ ] **Step 1: Write the failing test (append)**

```python
async def test_get_full_profile_assembles_everything(client):
    pid = await _new_profile(client)
    await client.post(f"/profile/{pid}/archetype", json={"answers": {"q1": 4, "q2": 4}})
    await client.put(f"/profile/{pid}/kinks", json={"entries": [
        {"kink": "bondage", "rating": "favorite"},
    ]})
    await client.post(f"/profile/{pid}/toys", json={"name": "Apex", "type": "vibrator"})
    await client.post(f"/profile/{pid}/goals", json={"title": "Practice"})
    await client.put(f"/profile/{pid}/so-context", json={"description": "For my partner"})

    r = await client.get(f"/profile/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == pid
    assert body["archetype_scores"]["submissive"] == 100
    assert body["kinks"][0]["kink"] == "bondage"
    assert body["toys"][0]["name"] == "Apex"
    assert body["goals"][0]["title"] == "Practice"
    assert body["so_context"]["description"] == "For my partner"
    assert body["character"]["honorific"] == "Headmistress"


async def test_get_full_profile_404(client):
    import uuid
    r = await client.get(f"/profile/{uuid.uuid4()}")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_profile_api.py -k full_profile -v`
Expected: FAIL — 404 for the populated profile (route missing).

- [ ] **Step 3: Add an aggregate loader to the service**

Append to `backend/app/services/profile.py`:

```python
from sqlalchemy.orm import selectinload


async def get_profile_full(session: AsyncSession, profile_id: uuid.UUID) -> SubProfile:
    """Profile with child collections eagerly loaded (async-safe, no lazy IO)."""
    profile = (await session.execute(
        select(SubProfile)
        .where(SubProfile.id == profile_id)
        .options(
            selectinload(SubProfile.kinks),
            selectinload(SubProfile.toys),
            selectinload(SubProfile.goals),
            selectinload(SubProfile.so_context),
        )
    )).scalar_one_or_none()
    if profile is None:
        raise ProfileNotFound(str(profile_id))
    return profile
```

(Place the `selectinload` import with the other SQLAlchemy imports at the top of the file rather than mid-module.)

- [ ] **Step 4: Add the route to `profile.py`**

Extend the schema import block with `KinkOut, ProfileRead`:

```python
from app.schemas.onboarding import (
    ArchetypeResultOut,
    ArchetypeSubmission,
    CharacterOut,
    CharacterUpdate,
    GoalIn,
    GoalOut,
    KinkOut,
    KinkSheetIn,
    ProfileRead,
    SoContextIn,
    ToyIn,
    ToyOut,
)
```

Add the route:

```python
@router.get("/{profile_id}", response_model=ProfileRead)
async def get_full_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ProfileRead:
    try:
        profile = await svc.get_profile_full(session, profile_id)
        char = await svc.get_character(session, profile_id)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    scores = await svc.latest_archetype_scores(session, profile_id)
    so = profile.so_context
    return ProfileRead(
        id=profile.id,
        intensity_ceiling=profile.intensity_ceiling,
        aftercare_prefs=profile.aftercare_prefs,
        archetype_scores=scores,
        kinks=[KinkOut.model_validate(k) for k in profile.kinks],
        toys=[ToyOut.model_validate(t) for t in profile.toys],
        goals=[GoalOut.model_validate(g) for g in profile.goals],
        so_context=(
            SoContextIn(description=so.description, values=so.values, dynamic=so.dynamic)
            if so
            else None
        ),
        character=CharacterOut.model_validate(char),
    )
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/api/test_profile_api.py -k full_profile -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/profile.py backend/app/services/profile.py backend/tests/api/test_profile_api.py
git commit -m "feat: add assembled GET /profile/{id} read endpoint"
```

---

## Task 12: Full verification + milestone wrap

**Files:** none (verification only) — then one docs commit.

- [ ] **Step 1: Bring infra up (local)**

Run: `docker compose up -d` (Postgres on 5432). Skip on CI — the `postgres:16` service is already in the `backend` job.

- [ ] **Step 2: Full suite**

Run: `uv run pytest -q`
Expected: all M1 + M2 + M3 tests pass (M2 left 31; M3 adds the archetype, kink-catalog, schema, profile-service, onboarding, and profile-API tests).

- [ ] **Step 3: Lint**

Run: `uv run ruff check .`
Expected: clean. Fix any unused-import / line-length issues in the new files.

- [ ] **Step 4: Push and confirm CI green**

```bash
git push -u origin feat/m3-onboarding-profile
```
Watch the run; confirm both `backend` and `frontend` jobs pass. The DB tests run against the CI Postgres service added in M2.

- [ ] **Step 5: Open the PR**

```bash
gh pr create --base master --head feat/m3-onboarding-profile \
  --title "M3: Onboarding & Profile — consent gate, archetype scoring, profile API" \
  --body "Implements spec §4 + §5A editing. See docs/superpowers/plans/2026-06-06-core-obedience-loop-m3-onboarding-profile.md"
```

---

## Verification (end-to-end for Milestone 3)

1. **Infra up:** `docker compose up -d`.
2. **Suite green:** `uv run pytest -q` — archetype scoring (pure), kink catalog, schemas, profile service, and both API routers all pass against live Postgres.
3. **Lint clean:** `uv run ruff check .`.
4. **Onboarding works end-to-end:** `POST /onboarding/profile` (consent gate enforced) → `POST /profile/{id}/archetype` (scores returned & stored) → `PUT /profile/{id}/kinks` (limits set) → toys/goals/SO added → `PUT /profile/{id}/character` (persona tuned) → `GET /profile/{id}` returns the fully assembled profile.
5. **CI green** on the pushed branch (both jobs).

**Milestone 3 is done when:** a profile can be created behind the consent gate, the archetype questionnaire scores and persists, the kink sheet (limits), toys, goals, SO context, and editable character model are all reachable via the API, and `GET /profile/{id}` returns the assembled profile that M4's persona engine will compile into the system prompt — with the suite and CI green.

---

## Self-Review

**Spec coverage (§4 + §5A editing):**
- 18+ gate + consent → Task 5 (`create_profile` 422s without both). ✓
- BDSM archetype questionnaire, store raw answers **and** computed scores → Tasks 1, 6 (`ArchetypeResult.raw_answers` + `scores`). ✓
- Kink interest sheet = limits system → Tasks 2, 7 (full-replace `KinkEntry`). ✓
- Toy inventory (name/type/intiface flag/notes, data only) → Task 8. ✓
- SO context (free-text + light structure, optional) → Task 10. ✓
- Goals → Task 9. ✓
- Preferences: absolute intensity ceiling + aftercare → Task 5 (`ProfileCreate`). Persona hard-nos (banned language/themes) are an output-filter concern deferred to **M8 (Safety)**; noted, not built here. ✓ (scoped)
- Character model read/edit (identity, archetype blend, 7 dials incl. Sadism, signature flavor) → Tasks 3, 10 (`CharacterOut`/`CharacterUpdate`, dial bounds 0–100). ✓
- "All injected verbatim into the persona context" + "seeds initial Graphiti episodes" → **consumption is M4; Graphiti is M5.** M3 only persists the data. ✓ (scoped)

**Placeholder scan:** No TBD/TODO; every code step shows complete code; no "handle edge cases" hand-waving (validation is concrete: consent gate, dial bounds, unknown-id rejection, enum parsing). ✓

**Type consistency:** Service function names (`create_profile`, `get_profile`, `get_character`, `latest_archetype_scores`, `add_archetype_result`, `replace_kinks`, `add_toy`, `list_toys`, `add_goal`, `list_goals`, `upsert_so_context`, `update_character`, `get_profile_full`) and the `ProfileNotFound` exception are used identically across Tasks 4–11. Schema names (`ProfileCreate`/`ProfileCreated`, `ArchetypeSubmission`/`ArchetypeResultOut`, `KinkItem`/`KinkSheetIn`/`KinkOut`, `ToyIn`/`ToyOut`, `GoalIn`/`GoalOut`, `SoContextIn`, `CharacterUpdate`/`CharacterOut`, `ProfileRead`) match between Task 3 definitions and their later imports. The profile-API import block is shown growing cumulatively per task (final form in Task 11). ✓

---

## Notes for execution

- **Branch:** `feat/m3-onboarding-profile` (not `master`).
- **Transaction boundary:** services `flush()` only; **endpoints `commit()`**. Tests share one session via `dependency_overrides`, so a single commit per request is correct and visible to follow-up requests in the same test.
- **Async eager-loading:** never trigger lazy relationship IO on an `AsyncSession` — Task 11 uses `selectinload` for the collections, and one-to-ones (`character_model`, `economy_state`) are fetched with explicit `select(...)` rather than relationship access.
- **Local dev caveat:** clear `PYTHONHOME`/`PYTHONPATH` in-session before `uv` (see `smistress-dev-environment` memory). CI unaffected.
- **No new dependencies** and **no migration** — M3 reuses the M2 schema and existing libraries (Pydantic ships with FastAPI).
