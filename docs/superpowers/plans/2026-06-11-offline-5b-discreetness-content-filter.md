# Offline-First M5b — Discreetness Content Filter (mode-filtered draws) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the **deterministic content filter** from Addendum B6 — discreetness flags on toys, an intensity/discreetness/required-toy profile on tasks and punishments, and a mode-aware draw so the offline drones (and the data the live Mistress reads) only ever surface content that fits the active supervision mode (set in M5a), all without an LLM.

**Architecture:** A new pure-function module `app/supervision/filter.py` owns the predicate logic (`task_allowed`, `punishment_allowed`, the mode→minimum-discreetness map, the task-mode grace, and a persona directive string) with **no DB access** — it consumes already-loaded ORM objects. Toys gain three discreetness booleans; `Task`/`TaskPoolItem` and `Punishment`/`PunishmentPoolItem` gain a `discreetness` enum + `required_toy_ids` (and tasks an `intensity`). The assignment draw (`batch.draw_and_assign`) and the discipline draw (`discipline.draw_punishment`) load the active mode + toys and pick the first pooled item the filter allows; **task mode** additionally stamps a graceful deadline. Batch generation parses the new task/punishment fields. The persona's authoritative-state block gains a one-line content-filter directive so the live Mistress honors the same constraints (B1 "binds her too"). **Backend-only** (mirrors M3/M4a/M5a): the filter works fully offline; all M5 **frontend** (the mode switcher + toy/tag tagging UI) is deferred to **M5c**.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async (psycopg3), Alembic, Pydantic v2, pytest (live Postgres `smistress_test`), ruff line-length=100. Conventions: **services flush, endpoints commit**; PG enums created via `postgresql.ENUM` storing **member NAMES** (uppercase, matching the M5a `supervision_mode` migration); JSONB for list/map columns; bare-UUID cross-aggregate refs stored as strings in JSONB (cf. `Punishment.penance_task_id`).

**Scope (locked):** Discreetness is a 3-level ordinal (`overt < discreet < silent`). The filter covers: (a) **discreetness floor per mode** — full→overt, discreet→discreet, homeoffice→silent, task→overt; (b) **intensity ceiling** — pooled tasks above the profile's `intensity_ceiling` are skipped (safety §9); (c) **required-toy discreetness** — under discreet/homeoffice, every required toy must be `discreet_capable`; (d) **task-mode grace** — under task mode every dropped task gets a `task_mode_grace_hours` deadline. Vacation is already gated upstream (M5a `economy_frozen`) so the filter is never reached under vacation. **Deferred to M5c:** the supervision-mode switcher UI, the per-toy discreetness tagging UI, and surfacing task/punishment tags in the offline dossier. **Deferred further:** schedule/calendar (B6); the `punitive` flag + `pending_review` proof state (B10 — those belong to the queued-proof milestone, M6).

---

## File Structure

**New (backend/):**
- `app/supervision/filter.py` — pure predicates: `Discreetness` rank, `mode_min_discreetness`, `task_allowed`, `punishment_allowed`, `content_filter_directive`. No DB, no session.
- `alembic/versions/f6a7b8c9d0e1_add_toy_discreetness.py` — toy flags.
- `alembic/versions/a7b8c9d0e1f2_add_task_discreetness.py` — `discreetness` PG enum + task/pool columns.
- `alembic/versions/b8c9d0e1f2a3_add_punishment_discreetness.py` — punishment/pool columns (reuse enum).
- `tests/supervision/test_filter.py` — pure-function filter tests.
- `tests/supervision/test_mode_filtered_draw.py` — draw integration (assignment + discipline) tests.

**Modified (backend/):**
- `app/db/enums.py` — `Discreetness` enum.
- `app/db/models/profile.py` — `Toy.noise` / `Toy.visibility` / `Toy.discreet_capable`.
- `app/db/models/task.py` — `Task.intensity` / `Task.discreetness` / `Task.required_toy_ids`.
- `app/db/models/batch.py` — `TaskPoolItem.intensity/discreetness/required_toy_ids`; `PunishmentPoolItem.discreetness/required_toy_ids`.
- `app/db/models/punishment.py` — `Punishment.discreetness/required_toy_ids`.
- `app/schemas/onboarding.py` — `ToyIn`/`ToyOut` gain the three flags.
- `app/services/profile.py` — `add_toy` persists the flags.
- `app/config.py` — `task_mode_grace_hours`.
- `app/batch/service.py` — `draw_and_assign` mode-filters + stamps task-mode deadline + carries the profile onto the Task; `_TaskGen`/`_PunishmentGen` + persistence parse the new fields.
- `app/discipline/service.py` — `draw_punishment` mode-filters.
- `app/drones/service.py` — pass `now=` into `draw_and_assign`.
- `app/persona/service.py` — inject the content-filter directive.
- Tests touched: `tests/batch/test_batch_service.py` (draw still works in FULL; parse new fields), `tests/discipline/test_discipline_service.py` (draw still works in FULL), `tests/onboarding/` toy test (flags round-trip), `tests/persona/test_state_block.py` (directive line).

---

## Task 1: `Discreetness` enum + the pure filter module

**Files:**
- Modify: `backend/app/db/enums.py`
- Create: `backend/app/supervision/filter.py`
- Test: `backend/tests/supervision/test_filter.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/supervision/test_filter.py`:
```python
import uuid
from dataclasses import dataclass

from app.db.enums import Discreetness, SupervisionMode
from app.supervision import filter as sup_filter


@dataclass
class _Toy:
    id: uuid.UUID
    discreet_capable: bool


def _toys(*flags: bool) -> dict[str, _Toy]:
    out = {}
    for cap in flags:
        tid = uuid.uuid4()
        out[str(tid)] = _Toy(id=tid, discreet_capable=cap)
    return out


def test_discreetness_members():
    assert {d.value for d in Discreetness} == {"overt", "discreet", "silent"}


def test_mode_min_discreetness():
    M, D = SupervisionMode, Discreetness
    assert sup_filter.mode_min_discreetness(M.FULL) is D.OVERT
    assert sup_filter.mode_min_discreetness(M.DISCREET) is D.DISCREET
    assert sup_filter.mode_min_discreetness(M.HOMEOFFICE) is D.SILENT
    assert sup_filter.mode_min_discreetness(M.TASK) is D.OVERT


def test_full_mode_allows_everything():
    # the intensity ceiling is a safety invariant that applies in ALL modes (§9),
    # so "everything" here means within the ceiling.
    assert sup_filter.task_allowed(
        SupervisionMode.FULL, discreetness=Discreetness.OVERT, intensity=100,
        required_toy_ids=[], toys_by_id={}, intensity_ceiling=100,
    ) is True


def test_discreet_mode_rejects_overt_task():
    assert sup_filter.task_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.OVERT, intensity=0,
        required_toy_ids=[], toys_by_id={}, intensity_ceiling=100,
    ) is False


def test_discreet_mode_allows_discreet_and_silent():
    for d in (Discreetness.DISCREET, Discreetness.SILENT):
        assert sup_filter.task_allowed(
            SupervisionMode.DISCREET, discreetness=d, intensity=0,
            required_toy_ids=[], toys_by_id={}, intensity_ceiling=100,
        ) is True


def test_homeoffice_requires_silent():
    assert sup_filter.task_allowed(
        SupervisionMode.HOMEOFFICE, discreetness=Discreetness.DISCREET, intensity=0,
        required_toy_ids=[], toys_by_id={}, intensity_ceiling=100,
    ) is False
    assert sup_filter.task_allowed(
        SupervisionMode.HOMEOFFICE, discreetness=Discreetness.SILENT, intensity=0,
        required_toy_ids=[], toys_by_id={}, intensity_ceiling=100,
    ) is True


def test_intensity_ceiling_rejects_too_intense():
    assert sup_filter.task_allowed(
        SupervisionMode.FULL, discreetness=Discreetness.OVERT, intensity=80,
        required_toy_ids=[], toys_by_id={}, intensity_ceiling=50,
    ) is False


def test_required_toy_must_be_discreet_capable_under_discreet():
    toys = _toys(False)  # one non-discreet toy
    tid = next(iter(toys))
    assert sup_filter.task_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.SILENT, intensity=0,
        required_toy_ids=[tid], toys_by_id=toys, intensity_ceiling=100,
    ) is False
    toys2 = _toys(True)
    tid2 = next(iter(toys2))
    assert sup_filter.task_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.SILENT, intensity=0,
        required_toy_ids=[tid2], toys_by_id=toys2, intensity_ceiling=100,
    ) is True


def test_missing_required_toy_rejected_under_discreet():
    assert sup_filter.task_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.SILENT, intensity=0,
        required_toy_ids=[str(uuid.uuid4())], toys_by_id={}, intensity_ceiling=100,
    ) is False


def test_required_toy_ignored_under_full():
    # full mode never checks required-toy discreetness
    toys = _toys(False)
    tid = next(iter(toys))
    assert sup_filter.task_allowed(
        SupervisionMode.FULL, discreetness=Discreetness.OVERT, intensity=0,
        required_toy_ids=[tid], toys_by_id=toys, intensity_ceiling=100,
    ) is True


def test_punishment_allowed_mirrors_discreetness_floor():
    assert sup_filter.punishment_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.OVERT,
        required_toy_ids=[], toys_by_id={},
    ) is False
    assert sup_filter.punishment_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.SILENT,
        required_toy_ids=[], toys_by_id={},
    ) is True


def test_content_filter_directive_per_mode():
    assert sup_filter.content_filter_directive(SupervisionMode.FULL) is None
    assert "discreet" in sup_filter.content_filter_directive(SupervisionMode.DISCREET).lower()
    assert "silent" in sup_filter.content_filter_directive(SupervisionMode.HOMEOFFICE).lower()
    assert "deadline" in sup_filter.content_filter_directive(SupervisionMode.TASK).lower()
```

- [ ] **Step 2: Run to verify it fails**

Run (PowerShell; clear env per `smistress-dev-environment`):
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_filter.py -q
```
Expected: FAIL — `ImportError: cannot import name 'Discreetness'`.

- [ ] **Step 3: Add the enum**

In `backend/app/db/enums.py`, append:
```python
class Discreetness(str, enum.Enum):
    """How quiet/covert a piece of content is (Addendum B6). Ordinal: overt is the
    least discreet, silent the most. The active supervision mode sets a floor."""

    OVERT = "overt"  # loud and/or visible — full supervision only
    DISCREET = "discreet"  # quiet, low-visibility — safe with family around
    SILENT = "silent"  # fully covert — safe in meetings / homeoffice
```

- [ ] **Step 4: Create the filter module**

Create `backend/app/supervision/filter.py`:
```python
"""Deterministic, offline content filter (Addendum B6). Pure functions over
already-loaded objects — no DB, no session. The active supervision mode sets a
discreetness floor; tasks above the intensity ceiling are skipped (safety §9);
required toys must be discreet-capable when the mode demands discretion."""
from __future__ import annotations

from typing import Protocol

from app.db.enums import Discreetness, SupervisionMode

# Ordinal rank — higher is more discreet. A mode's floor admits anything at or
# above its rank.
_RANK: dict[Discreetness, int] = {
    Discreetness.OVERT: 0,
    Discreetness.DISCREET: 1,
    Discreetness.SILENT: 2,
}

_MODE_FLOOR: dict[SupervisionMode, Discreetness] = {
    SupervisionMode.FULL: Discreetness.OVERT,
    SupervisionMode.DISCREET: Discreetness.DISCREET,
    SupervisionMode.HOMEOFFICE: Discreetness.SILENT,
    SupervisionMode.TASK: Discreetness.OVERT,  # task mode constrains timing, not discretion
    SupervisionMode.VACATION: Discreetness.OVERT,  # never reached (gated upstream)
}


class _ToyLike(Protocol):
    discreet_capable: bool


def mode_min_discreetness(mode: SupervisionMode) -> Discreetness:
    return _MODE_FLOOR[mode]


def _meets_floor(discreetness: Discreetness, mode: SupervisionMode) -> bool:
    return _RANK[discreetness] >= _RANK[_MODE_FLOOR[mode]]


def _demands_discretion(mode: SupervisionMode) -> bool:
    """True when the mode requires required-toys to be discreet-capable."""
    return _RANK[_MODE_FLOOR[mode]] >= _RANK[Discreetness.DISCREET]


def _required_toys_ok(
    required_toy_ids: list[str], toys_by_id: dict[str, _ToyLike], mode: SupervisionMode
) -> bool:
    if not _demands_discretion(mode):
        return True
    for tid in required_toy_ids:
        toy = toys_by_id.get(str(tid))
        if toy is None or not toy.discreet_capable:
            return False
    return True


def task_allowed(
    mode: SupervisionMode,
    *,
    discreetness: Discreetness,
    intensity: int,
    required_toy_ids: list[str],
    toys_by_id: dict[str, _ToyLike],
    intensity_ceiling: int,
) -> bool:
    """Whether a pooled task may be dropped under the active mode."""
    if not _meets_floor(discreetness, mode):
        return False
    if intensity > intensity_ceiling:
        return False
    return _required_toys_ok(required_toy_ids, toys_by_id, mode)


def punishment_allowed(
    mode: SupervisionMode,
    *,
    discreetness: Discreetness,
    required_toy_ids: list[str],
    toys_by_id: dict[str, _ToyLike],
) -> bool:
    """Whether a pooled punishment may be drawn under the active mode (no intensity)."""
    if not _meets_floor(discreetness, mode):
        return False
    return _required_toys_ok(required_toy_ids, toys_by_id, mode)


_DIRECTIVES: dict[SupervisionMode, str] = {
    SupervisionMode.DISCREET: (
        "CONTENT FILTER: assign only discreet, quiet content; any required toy must be "
        "discreet-capable."
    ),
    SupervisionMode.HOMEOFFICE: (
        "CONTENT FILTER: she is in meetings — assign only silent, fully-covert content; "
        "expect no immediate reaction."
    ),
    SupervisionMode.TASK: (
        "CONTENT FILTER: assign only tasks with a graceful deadline; expect no immediate "
        "reaction."
    ),
}


def content_filter_directive(mode: SupervisionMode) -> str | None:
    """A one-line directive for the persona's authoritative-state block, or None
    when the mode imposes no content constraint (full/vacation)."""
    return _DIRECTIVES.get(mode)
```

- [ ] **Step 5: Run (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_filter.py -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/db/enums.py app/supervision/filter.py tests/supervision/test_filter.py
```
```bash
git add backend/app/db/enums.py backend/app/supervision/filter.py backend/tests/supervision/test_filter.py
git commit -m "feat(supervision): Discreetness enum + pure content-filter predicates"
```

---

## Task 2: Toy discreetness flags (model + migration + schema + service)

**Files:**
- Modify: `backend/app/db/models/profile.py`, `backend/app/schemas/onboarding.py`, `backend/app/services/profile.py`
- Create: `backend/alembic/versions/f6a7b8c9d0e1_add_toy_discreetness.py`
- Test: `backend/tests/supervision/test_filter.py` (add a round-trip case) — or `tests/onboarding/` if a toy API test module exists.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/supervision/test_filter.py`:
```python
async def test_toy_flags_round_trip(session):
    from app.schemas.onboarding import ProfileCreate, ToyIn
    from app.db.enums import ToyType
    from app.services import profile as profile_svc

    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    toy = await profile_svc.add_toy(
        session, p.id,
        ToyIn(name="quiet bullet", type=ToyType.VIBRATOR,
              noise=False, visibility=False, discreet_capable=True),
    )
    await session.refresh(toy)
    assert toy.noise is False
    assert toy.visibility is False
    assert toy.discreet_capable is True
    # defaults are conservative: an untagged toy is not assumed discreet
    default = await profile_svc.add_toy(
        session, p.id, ToyIn(name="paddle", type=ToyType.PADDLE),
    )
    await session.refresh(default)
    assert default.discreet_capable is False
```

- [ ] **Step 2: Run to verify it fails**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_filter.py::test_toy_flags_round_trip -q
```
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'noise'` (ToyIn) or `AttributeError` (Toy).

- [ ] **Step 3: Add the model columns**

In `backend/app/db/models/profile.py`, on `Toy` (after `intiface_capable`):
```python
    noise: Mapped[bool] = mapped_column(default=False)  # makes audible noise
    visibility: Mapped[bool] = mapped_column(default=False)  # conspicuous / visible
    discreet_capable: Mapped[bool] = mapped_column(default=False)  # usable discreetly
```

- [ ] **Step 4: Add the schema fields**

In `backend/app/schemas/onboarding.py`, extend `ToyIn`:
```python
class ToyIn(BaseModel):
    name: str
    type: ToyType
    intiface_capable: bool = False
    notes: str | None = None
    noise: bool = False
    visibility: bool = False
    discreet_capable: bool = False
```
(`ToyOut(ToyIn)` inherits the new fields with `from_attributes=True`, so the read model carries them automatically.)

- [ ] **Step 5: Persist them in the service**

In `backend/app/services/profile.py` `add_toy`, extend the `Toy(...)` constructor:
```python
    toy = Toy(
        profile_id=profile_id,
        name=data.name,
        type=data.type.value,  # store the plain enum value in the String column
        intiface_capable=data.intiface_capable,
        notes=data.notes,
        noise=data.noise,
        visibility=data.visibility,
        discreet_capable=data.discreet_capable,
    )
```

- [ ] **Step 6: Write the migration**

Head is `e5f6a7b8c9d0`. Create `backend/alembic/versions/f6a7b8c9d0e1_add_toy_discreetness.py`:
```python
"""add toy discreetness flags

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    for col in ('noise', 'visibility', 'discreet_capable'):
        op.add_column(
            'toy',
            sa.Column(col, sa.Boolean(), server_default=sa.false(), nullable=False),
        )


def downgrade() -> None:
    """Downgrade schema."""
    for col in ('discreet_capable', 'visibility', 'noise'):
        op.drop_column('toy', col)
```

- [ ] **Step 7: Round-trip the migration**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic downgrade -1
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
```
Expected: each exits 0; upgrade logs `e5f6a7b8c9d0 -> f6a7b8c9d0e1`. (Defer to CI if Postgres is down.)

- [ ] **Step 8: Run the test (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_filter.py -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/db/models/profile.py app/schemas/onboarding.py app/services/profile.py backend/alembic/versions/f6a7b8c9d0e1_add_toy_discreetness.py
```
```bash
git add backend/app/db/models/profile.py backend/app/schemas/onboarding.py backend/app/services/profile.py backend/alembic/versions/f6a7b8c9d0e1_add_toy_discreetness.py backend/tests/supervision/test_filter.py
git commit -m "feat(supervision): toy discreetness flags (noise/visibility/discreet_capable)"
```

---

## Task 3: Task + TaskPoolItem discreetness profile (model + migration)

**Files:**
- Modify: `backend/app/db/models/task.py`, `backend/app/db/models/batch.py`
- Create: `backend/alembic/versions/a7b8c9d0e1f2_add_task_discreetness.py`
- Test: `backend/tests/supervision/test_filter.py` (add a defaults case)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/supervision/test_filter.py`:
```python
async def test_task_and_pool_discreetness_defaults(session):
    from app.db.enums import Discreetness, ProofRequirement
    from app.db.models.batch import TaskPoolItem
    from app.loop import service as loop_svc
    from app.schemas.onboarding import ProfileCreate
    from app.services import profile as profile_svc

    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    task = await loop_svc.assign_task(
        session, p.id, description="drill", proof_requirement=ProofRequirement.HONOR,
    )
    await session.refresh(task)
    assert task.intensity == 0
    assert task.discreetness is Discreetness.OVERT
    assert task.required_toy_ids == []

    item = TaskPoolItem(
        profile_id=p.id, description="pooled", proof_requirement=ProofRequirement.HONOR,
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    assert item.intensity == 0
    assert item.discreetness is Discreetness.OVERT
    assert item.required_toy_ids == []
```

- [ ] **Step 2: Run to verify it fails**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_filter.py::test_task_and_pool_discreetness_defaults -q
```
Expected: FAIL — `AttributeError: ... 'intensity'`.

- [ ] **Step 3: Add the Task columns**

In `backend/app/db/models/task.py`, extend the imports and add columns. Change the enum import line to:
```python
from app.db.enums import Discreetness, ProofRequirement, TaskStatus
```
Add `Enum` is already imported; `JSONB` is not — add to the imports at top:
```python
from sqlalchemy.dialects.postgresql import JSONB
```
Then on `Task`, after the `merit_*` columns:
```python
    intensity: Mapped[int] = mapped_column(default=0)  # 0-100, clamped by the ceiling
    discreetness: Mapped[Discreetness] = mapped_column(
        Enum(Discreetness, name="discreetness"), default=Discreetness.OVERT
    )
    required_toy_ids: Mapped[list] = mapped_column(JSONB, default=list)  # list[str] toy UUIDs
```

- [ ] **Step 4: Add the TaskPoolItem columns**

In `backend/app/db/models/batch.py`, change the enum import to:
```python
from app.db.enums import Discreetness, ProofRequirement, PunishmentType
```
and add `JSONB`:
```python
from sqlalchemy.dialects.postgresql import JSONB
```
On `TaskPoolItem`, after the `merit_*` columns:
```python
    intensity: Mapped[int] = mapped_column(default=0)
    discreetness: Mapped[Discreetness] = mapped_column(
        Enum(Discreetness, name="discreetness"), default=Discreetness.OVERT
    )
    required_toy_ids: Mapped[list] = mapped_column(JSONB, default=list)
```

- [ ] **Step 5: Write the migration (creates the `discreetness` PG enum)**

Create `backend/alembic/versions/a7b8c9d0e1f2_add_task_discreetness.py`:
```python
"""add task + pool discreetness profile

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-11 10:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DISCREETNESS = postgresql.ENUM('OVERT', 'DISCREET', 'SILENT', name='discreetness')


def upgrade() -> None:
    """Upgrade schema."""
    _DISCREETNESS.create(op.get_bind(), checkfirst=True)
    for table in ('task', 'task_pool_item'):
        op.add_column(
            table, sa.Column('intensity', sa.Integer(), server_default='0', nullable=False)
        )
        op.add_column(
            table,
            sa.Column(
                'discreetness',
                postgresql.ENUM('OVERT', 'DISCREET', 'SILENT', name='discreetness',
                                create_type=False),
                server_default='OVERT', nullable=False,
            ),
        )
        op.add_column(
            table,
            sa.Column('required_toy_ids', postgresql.JSONB(astext_type=sa.Text()),
                      server_default='[]', nullable=False),
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('task_pool_item', 'task'):
        op.drop_column(table, 'required_toy_ids')
        op.drop_column(table, 'discreetness')
        op.drop_column(table, 'intensity')
    op.execute('DROP TYPE discreetness')
```

- [ ] **Step 6: Round-trip the migration**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic downgrade -1
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
```
Expected: each exits 0; upgrade logs `f6a7b8c9d0e1 -> a7b8c9d0e1f2`.

- [ ] **Step 7: Run the test (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_filter.py -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/db/models/task.py app/db/models/batch.py backend/alembic/versions/a7b8c9d0e1f2_add_task_discreetness.py
```
```bash
git add backend/app/db/models/task.py backend/app/db/models/batch.py backend/alembic/versions/a7b8c9d0e1f2_add_task_discreetness.py backend/tests/supervision/test_filter.py
git commit -m "feat(supervision): task + pool intensity/discreetness/required-toys profile"
```

---

## Task 4: Punishment + PunishmentPoolItem discreetness (model + migration)

**Files:**
- Modify: `backend/app/db/models/punishment.py`, `backend/app/db/models/batch.py`
- Create: `backend/alembic/versions/b8c9d0e1f2a3_add_punishment_discreetness.py`
- Test: `backend/tests/supervision/test_filter.py` (add a defaults case)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/supervision/test_filter.py`:
```python
async def test_punishment_pool_discreetness_defaults(session):
    from app.db.enums import Discreetness, PunishmentType
    from app.db.models.batch import PunishmentPoolItem
    from app.schemas.onboarding import ProfileCreate
    from app.services import profile as profile_svc

    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    item = PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.PENANCE_TASK, severity=1, reason="lines",
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    assert item.discreetness is Discreetness.OVERT
    assert item.required_toy_ids == []
```

- [ ] **Step 2: Run to verify it fails**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_filter.py::test_punishment_pool_discreetness_defaults -q
```
Expected: FAIL — `AttributeError: ... 'discreetness'`.

- [ ] **Step 3: Add the columns**

In `backend/app/db/models/punishment.py`, change the enum import to:
```python
from app.db.enums import Discreetness, PunishmentStatus, PunishmentType
```
add the JSONB import:
```python
from sqlalchemy.dialects.postgresql import JSONB
```
On `Punishment`, after `debt_amount`:
```python
    discreetness: Mapped[Discreetness] = mapped_column(
        Enum(Discreetness, name="discreetness"), default=Discreetness.OVERT
    )
    required_toy_ids: Mapped[list] = mapped_column(JSONB, default=list)
```

In `backend/app/db/models/batch.py`, on `PunishmentPoolItem`, after `reason`:
```python
    discreetness: Mapped[Discreetness] = mapped_column(
        Enum(Discreetness, name="discreetness"), default=Discreetness.OVERT
    )
    required_toy_ids: Mapped[list] = mapped_column(JSONB, default=list)
```
(`Discreetness` and `JSONB` are already imported into `batch.py` from Task 3.)

- [ ] **Step 4: Write the migration (reuses the `discreetness` enum)**

Create `backend/alembic/versions/b8c9d0e1f2a3_add_punishment_discreetness.py`:
```python
"""add punishment + pool discreetness

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-11 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. The `discreetness` enum already exists (a7b8c9d0e1f2)."""
    discreetness = postgresql.ENUM('OVERT', 'DISCREET', 'SILENT', name='discreetness',
                                   create_type=False)
    for table in ('punishment', 'punishment_pool_item'):
        op.add_column(
            table,
            sa.Column('discreetness', discreetness, server_default='OVERT', nullable=False),
        )
        op.add_column(
            table,
            sa.Column('required_toy_ids', postgresql.JSONB(astext_type=sa.Text()),
                      server_default='[]', nullable=False),
        )


def downgrade() -> None:
    """Downgrade schema. Leave the `discreetness` type — task/pool still use it."""
    for table in ('punishment_pool_item', 'punishment'):
        op.drop_column(table, 'required_toy_ids')
        op.drop_column(table, 'discreetness')
```

- [ ] **Step 5: Round-trip the migration**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic downgrade -1
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
```
Expected: each exits 0; upgrade logs `a7b8c9d0e1f2 -> b8c9d0e1f2a3`.

- [ ] **Step 6: Run the test (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_filter.py -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/db/models/punishment.py app/db/models/batch.py backend/alembic/versions/b8c9d0e1f2a3_add_punishment_discreetness.py
```
```bash
git add backend/app/db/models/punishment.py backend/app/db/models/batch.py backend/alembic/versions/b8c9d0e1f2a3_add_punishment_discreetness.py backend/tests/supervision/test_filter.py
git commit -m "feat(supervision): punishment + pool discreetness/required-toys"
```

---

## Task 5: Mode-filtered assignment draw + task-mode grace

**Files:**
- Modify: `backend/app/config.py`, `backend/app/batch/service.py`, `backend/app/drones/service.py`
- Test: `backend/tests/supervision/test_mode_filtered_draw.py`

- [ ] **Step 1: Add the grace setting**

In `backend/app/config.py`, after `penance_merit_recovery`:
```python
    task_mode_grace_hours: int = 24  # task mode: every dropped task gets this deadline
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/supervision/test_mode_filtered_draw.py`:
```python
from datetime import datetime, timezone

from app.batch import service as batch_svc
from app.db.enums import Discreetness, ProofRequirement, SupervisionMode
from app.db.models.batch import TaskPoolItem
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from app.supervision import service as sup_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


def _pool_task(profile_id, **kw):
    kw.setdefault("description", "drill")
    kw.setdefault("proof_requirement", ProofRequirement.HONOR)
    return TaskPoolItem(profile_id=profile_id, **kw)


async def test_discreet_mode_skips_overt_picks_discreet(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.DISCREET)
    session.add(_pool_task(p.id, description="loud", discreetness=Discreetness.OVERT))
    session.add(_pool_task(p.id, description="quiet", discreetness=Discreetness.DISCREET))
    await session.flush()
    task = await batch_svc.draw_and_assign(session, p.id)
    assert task is not None
    assert task.description == "quiet"


async def test_no_allowed_task_returns_none(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.HOMEOFFICE)
    session.add(_pool_task(p.id, discreetness=Discreetness.DISCREET))  # not silent
    await session.flush()
    assert await batch_svc.draw_and_assign(session, p.id) is None


async def test_intensity_ceiling_skips_too_intense(session):
    p = await _profile(session)  # default intensity_ceiling 50
    session.add(_pool_task(p.id, description="brutal", intensity=80))
    session.add(_pool_task(p.id, description="gentle", intensity=10))
    await session.flush()
    task = await batch_svc.draw_and_assign(session, p.id)
    assert task is not None and task.description == "gentle"


async def test_task_mode_stamps_grace_deadline(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.TASK)
    session.add(_pool_task(p.id))
    await session.flush()
    now = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)
    task = await batch_svc.draw_and_assign(session, p.id, now=now)
    assert task is not None
    assert task.deadline is not None
    assert task.deadline > now  # graceful timer set


async def test_task_carries_pool_profile(session):
    p = await _profile(session)
    session.add(_pool_task(
        p.id, intensity=20, discreetness=Discreetness.SILENT, required_toy_ids=[],
    ))
    await session.flush()
    task = await batch_svc.draw_and_assign(session, p.id)
    assert task is not None
    assert task.intensity == 20
    assert task.discreetness is Discreetness.SILENT
```

- [ ] **Step 3: Run to verify they fail**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_mode_filtered_draw.py -q
```
Expected: FAIL — `draw_and_assign` ignores the mode / has no `now` kwarg / does not copy the profile.

- [ ] **Step 4: Rewrite `draw_and_assign`**

In `backend/app/batch/service.py`:
(a) Extend the imports near the top (alongside the existing `from datetime import datetime`):
```python
from datetime import datetime, timedelta
```
and add:
```python
from app.db.enums import ProofRequirement, PunishmentType, SupervisionMode
from app.services import profile as profile_svc
from app.supervision import filter as sup_filter
```
(extend the existing `from app.db.enums import ProofRequirement, PunishmentType` line to add `SupervisionMode`).

(b) Replace the whole `_next_pool_item` + `draw_and_assign` block (lines 343-373) with:
```python
async def _unconsumed_pool_items(
    session: AsyncSession, profile_id: uuid.UUID
) -> list[TaskPoolItem]:
    return list((await session.execute(
        select(TaskPoolItem)
        .where(TaskPoolItem.profile_id == profile_id, TaskPoolItem.consumed.is_(False))
        # id tiebreak: items from one generate_batch share created_at (server now()).
        .order_by(TaskPoolItem.created_at, TaskPoolItem.id)
    )).scalars().all())


async def draw_and_assign(
    session: AsyncSession, profile_id: uuid.UUID, *, now: datetime | None = None
) -> Task | None:
    """The assignment drone drops the next *mode-allowed* pooled task as a real Task
    (Addendum B3/B4/B6) — no LLM. Skips items the active supervision mode forbids
    (discreetness floor, intensity ceiling, required-toy discretion); under task mode
    stamps a graceful deadline; carries the pool item's intensity/discreetness/required
    toys onto the Task. Returns None when nothing in the pool is allowed. Caller commits."""
    now = now or datetime.now(timezone.utc)
    profile = await profile_svc.get_profile(session, profile_id)
    mode = profile.supervision_mode
    toys = await profile_svc.list_toys(session, profile_id)
    toys_by_id = {str(t.id): t for t in toys}

    item = next(
        (
            c for c in await _unconsumed_pool_items(session, profile_id)
            if sup_filter.task_allowed(
                mode,
                discreetness=c.discreetness,
                intensity=c.intensity,
                required_toy_ids=c.required_toy_ids,
                toys_by_id=toys_by_id,
                intensity_ceiling=profile.intensity_ceiling,
            )
        ),
        None,
    )
    if item is None:
        return None

    deadline = (
        now + timedelta(hours=_settings.task_mode_grace_hours)
        if mode is SupervisionMode.TASK else None
    )
    # NB: item.difficulty is retained on the pool row for future use; Task carries
    # no difficulty column yet, so it is intentionally not propagated here.
    task = await loop_svc.assign_task(
        session,
        profile_id,
        description=item.description,
        proof_requirement=item.proof_requirement,
        deadline=deadline,
        merit_reward=item.merit_reward,
        merit_fail_penalty=item.merit_fail_penalty,
        merit_miss_penalty=item.merit_miss_penalty,
    )
    task.intensity = item.intensity
    task.discreetness = item.discreetness
    task.required_toy_ids = list(item.required_toy_ids or [])
    item.consumed = True
    await session.flush()
    return task
```

- [ ] **Step 5: Thread `now` from the drone**

In `backend/app/drones/service.py` `standing_orders`, change the draw call to pass `now`:
```python
    if task is None and not frozen:
        # The assignment unit drops the day's task from the pool (if any).
        task = await batch_svc.draw_and_assign(session, profile_id, now=now)
```

- [ ] **Step 6: Run the suites (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/ tests/batch/ tests/drones/ -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/config.py app/batch/service.py app/drones/service.py tests/supervision/test_mode_filtered_draw.py
```
Expected: all pass; existing batch/drone tests still pass — they run in default FULL mode (everything allowed) and default intensity 0 ≤ ceiling 50.
```bash
git add backend/app/config.py backend/app/batch/service.py backend/app/drones/service.py backend/tests/supervision/test_mode_filtered_draw.py
git commit -m "feat(supervision): mode-filtered assignment draw + task-mode grace deadline"
```

---

## Task 6: Mode-filtered discipline draw

**Files:**
- Modify: `backend/app/discipline/service.py`
- Test: `backend/tests/supervision/test_mode_filtered_draw.py` (add cases)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/supervision/test_mode_filtered_draw.py`:
```python
async def test_discipline_skips_overt_punishment_under_discreet(session):
    from app.db.models.batch import PunishmentPoolItem
    from app.db.enums import PunishmentType
    from app.discipline import service as disc_svc

    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.DISCREET)
    session.add(PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.PENANCE_TASK, severity=1,
        reason="loud lines", discreetness=Discreetness.OVERT,
    ))
    session.add(PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.PENANCE_TASK, severity=1,
        reason="silent kneeling", discreetness=Discreetness.SILENT,
    ))
    await session.flush()
    item = await disc_svc.draw_punishment(session, p.id, severity=1)
    assert item is not None
    assert item.reason == "silent kneeling"


async def test_discipline_draw_none_when_all_forbidden(session):
    from app.db.models.batch import PunishmentPoolItem
    from app.db.enums import PunishmentType
    from app.discipline import service as disc_svc

    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.HOMEOFFICE)
    session.add(PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.PENANCE_TASK, severity=1,
        reason="discreet only", discreetness=Discreetness.DISCREET,  # not silent
    ))
    await session.flush()
    assert await disc_svc.draw_punishment(session, p.id, severity=1) is None
```

- [ ] **Step 2: Run to verify they fail**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_mode_filtered_draw.py -k discipline -q
```
Expected: FAIL — `draw_punishment` ignores the mode.

- [ ] **Step 3: Rewrite `draw_punishment`**

In `backend/app/discipline/service.py`:
(a) Extend the imports:
```python
from app.services import profile as profile_svc
from app.supervision import filter as sup_filter
```
(b) Replace `draw_punishment` (lines 93-113) with:
```python
async def draw_punishment(
    session: AsyncSession, profile_id: uuid.UUID, *, severity: int
) -> PunishmentPoolItem | None:
    """Draw an unconsumed pooled punishment the active mode allows, preferring the
    requested severity and falling back to any. Marks it consumed. Returns None when
    the pool has no mode-allowed item (caller then issues a deterministic fallback)."""
    profile = await profile_svc.get_profile(session, profile_id)
    mode = profile.supervision_mode
    toys = await profile_svc.list_toys(session, profile_id)
    toys_by_id = {str(t.id): t for t in toys}

    def _allowed(it: PunishmentPoolItem) -> bool:
        return sup_filter.punishment_allowed(
            mode,
            discreetness=it.discreetness,
            required_toy_ids=it.required_toy_ids,
            toys_by_id=toys_by_id,
        )

    base = select(PunishmentPoolItem).where(
        PunishmentPoolItem.profile_id == profile_id,
        PunishmentPoolItem.consumed.is_(False),
    ).order_by(PunishmentPoolItem.created_at, PunishmentPoolItem.id)

    severity_items = (await session.execute(
        base.where(PunishmentPoolItem.severity == severity)
    )).scalars().all()
    item = next((it for it in severity_items if _allowed(it)), None)
    if item is None:
        any_items = (await session.execute(base)).scalars().all()
        item = next((it for it in any_items if _allowed(it)), None)
    if item is not None:
        item.consumed = True
        await session.flush()
    return item
```
(The `draw_and_issue` fallback to a deterministic `CHASTITY_EXTENSION` is unchanged — chastity is inherently discreet, so it remains a valid consequence in any mode.)

- [ ] **Step 4: Run the suites (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/ tests/discipline/ -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/discipline/service.py
```
Expected: all pass; existing discipline tests run in default FULL mode (everything allowed).
```bash
git add backend/app/discipline/service.py backend/tests/supervision/test_mode_filtered_draw.py
git commit -m "feat(supervision): mode-filtered discipline draw"
```

---

## Task 7: Batch generation parses the new task/punishment fields

**Files:**
- Modify: `backend/app/batch/service.py`
- Test: `backend/tests/batch/test_batch_service.py` (add a parse case) — or `tests/supervision/test_mode_filtered_draw.py` if the batch test module's helpers don't fit.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/batch/test_batch_service.py` (it already imports `parse_batch`; if not, add `from app.batch.service import parse_batch`):
```python
def test_parse_batch_reads_discreetness_profile():
    from app.db.enums import Discreetness
    content = """
    {"tasks": [
        {"description": "silent kegels", "proof": "honor", "intensity": 20,
         "discreetness": "silent", "required_toy_ids": []}
     ],
     "lines": [],
     "punishments": [
        {"type": "penance_task", "severity": 1, "reason": "quiet lines",
         "discreetness": "discreet", "required_toy_ids": []}
     ]}
    """
    tasks, _lines, punishments = parse_batch(content)
    assert len(tasks) == 1
    assert tasks[0].intensity == 20
    assert tasks[0].discreetness is Discreetness.SILENT
    assert tasks[0].required_toy_ids == []
    assert len(punishments) == 1
    assert punishments[0].discreetness is Discreetness.DISCREET


def test_parse_batch_defaults_discreetness_overt():
    from app.db.enums import Discreetness
    content = """{"tasks": [{"description": "x", "proof": "honor"}], "lines": [],
                  "punishments": [{"type": "penance_task", "severity": 1, "reason": "y"}]}"""
    tasks, _lines, punishments = parse_batch(content)
    assert tasks[0].discreetness is Discreetness.OVERT
    assert tasks[0].intensity == 0
    assert tasks[0].required_toy_ids == []
    assert punishments[0].discreetness is Discreetness.OVERT
```

- [ ] **Step 2: Run to verify it fails**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/batch/test_batch_service.py -k discreetness -q
```
Expected: FAIL — `_TaskGen`/`_PunishmentGen` have no `discreetness`/`intensity`/`required_toy_ids`.

- [ ] **Step 3: Extend the generation models**

In `backend/app/batch/service.py`:
(a) Add the enum import (extend the existing enums import to include `Discreetness`):
```python
from app.db.enums import Discreetness, ProofRequirement, PunishmentType, SupervisionMode
```
(b) Extend `_TaskGen` (add fields + a normalizing validator). After the existing `difficulty` field:
```python
    intensity: int = 0
    discreetness: Discreetness = Discreetness.OVERT
    required_toy_ids: list[str] = []

    @field_validator("discreetness", mode="before")
    @classmethod
    def _discreetness(cls, v: object) -> object:
        return str(v).strip().lower() if v is not None else v
```
(The existing `_lower` validator already covers `proof`/`difficulty`; the new validator normalizes capitalized model output like "Silent" → "silent" so the enum coerces.)

(c) Extend `_PunishmentGen` similarly. After `reason`:
```python
    discreetness: Discreetness = Discreetness.OVERT
    required_toy_ids: list[str] = []

    @field_validator("discreetness", mode="before")
    @classmethod
    def _discreetness(cls, v: object) -> object:
        return str(v).strip().lower() if v is not None else v
```

(d) Persist the new fields. In `generate_batch`, extend the `TaskPoolItem(...)` add:
```python
        session.add(TaskPoolItem(
            profile_id=profile_id,
            description=gen.description,
            proof_requirement=gen.proof,
            difficulty=gen.difficulty,
            merit_reward=gen.merit_reward,
            merit_fail_penalty=gen.merit_fail_penalty,
            merit_miss_penalty=gen.merit_miss_penalty,
            intensity=gen.intensity,
            discreetness=gen.discreetness,
            required_toy_ids=gen.required_toy_ids,
        ))
```
and the `PunishmentPoolItem(...)` add:
```python
        session.add(PunishmentPoolItem(
            profile_id=profile_id,
            type=PunishmentType(gen.type),
            severity=gen.severity,
            reason=gen.reason,
            discreetness=gen.discreetness,
            required_toy_ids=gen.required_toy_ids,
        ))
```

- [ ] **Step 4: Run the suites (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/batch/ tests/supervision/ -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/batch/service.py tests/batch/test_batch_service.py
```
Expected: all pass; existing generation tests still pass (new fields default).
```bash
git add backend/app/batch/service.py backend/tests/batch/test_batch_service.py
git commit -m "feat(supervision): batch generation parses task/punishment discreetness profile"
```

---

## Task 8: Persona injects the content-filter directive

**Files:**
- Modify: `backend/app/persona/service.py`
- Test: `backend/tests/persona/test_state_block.py` (add cases)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/persona/test_state_block.py`:
```python
async def test_state_block_shows_content_filter_directive(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.DISCREET)
    block = await persona_svc.build_authoritative_state_block(session, p.id)
    assert "CONTENT FILTER" in block
    assert "discreet" in block.lower()


async def test_state_block_no_directive_under_full(session):
    p = await _profile(session)  # default FULL
    block = await persona_svc.build_authoritative_state_block(session, p.id)
    assert "CONTENT FILTER" not in block
```

- [ ] **Step 2: Run to verify it fails**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/persona/test_state_block.py -q
```
Expected: FAIL — no CONTENT FILTER line.

- [ ] **Step 3: Inject the directive**

In `backend/app/persona/service.py`:
(a) Add the import:
```python
from app.supervision import filter as sup_filter
```
(b) In `build_authoritative_state_block`, right after the `WHAT'S POSSIBLE NOW` note block (after line 100, before the `if active_task is not None:` block), append the directive when present:
```python
    _filter_directive = sup_filter.content_filter_directive(profile.supervision_mode)
    if _filter_directive is not None:
        lines.append(_filter_directive)
```

- [ ] **Step 4: Run (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/persona/ -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/persona/service.py tests/persona/test_state_block.py
```
```bash
git add backend/app/persona/service.py backend/tests/persona/test_state_block.py
git commit -m "feat(persona): inject mode content-filter directive (binds the live Mistress)"
```

---

## Task 9: Full verification

**Files:** none.

- [ ] **Step 1: Whole backend suite + ruff + migration head**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check .
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
```
Expected: all green; ruff clean; head `b8c9d0e1f2a3`.

- [ ] **Step 2: Frontend sanity (regenerate types; contract grew, did not change)**

M5b adds optional fields to `ToyIn`/`ToyOut` and new pool fields, but changes no existing response shape the frontend consumes. Regenerate types and confirm no regression:
```
npm --prefix frontend run gen:api
npm --prefix frontend run test
npm --prefix frontend run build
```
Expected: green. (If `gen:api` requires a running backend and Postgres is down, defer to CI.)

- [ ] **Step 3: Push + PR**

```bash
git push -u origin feat/offline-5b-discreetness-content-filter
gh pr create --title "Offline-first M5b: discreetness content filter (mode-filtered draws)" --body "$(cat <<'EOF'
## Summary
Builds the deterministic content filter from Addendum B6 — the offline-safe half of the supervision-mode system whose axis landed in M5a.

- `Discreetness` enum (overt < discreet < silent); pure `app/supervision/filter.py` predicates (`task_allowed`, `punishment_allowed`, mode→floor map, `content_filter_directive`).
- Toy discreetness flags (`noise`, `visibility`, `discreet_capable`); migration `f6a7b8c9d0e1`.
- `intensity` + `discreetness` + `required_toy_ids` on `Task`/`TaskPoolItem` (migration `a7b8c9d0e1f2`, creates the `discreetness` PG enum) and `discreetness` + `required_toy_ids` on `Punishment`/`PunishmentPoolItem` (migration `b8c9d0e1f2a3`).
- **Mode-filtered draws:** the assignment draw skips pooled tasks the active mode forbids (discreetness floor, intensity ceiling, required-toy discretion) and stamps a graceful deadline under **task mode**; the discipline draw skips forbidden punishments (falling back to the inherently-discreet chastity extension).
- Batch generation parses the new task/punishment fields.
- The persona's authoritative-state block injects a one-line content-filter directive so the live Mistress honors the same constraints (B1 "binds her too").

Backend-only (mirrors M3/M4a/M5a). Vacation freeze (M5a) gates the draws upstream, so the filter is never reached under vacation. **Deferred to M5c:** all M5 frontend — the supervision-mode switcher + per-toy discreetness tagging + surfacing tags in the dossier. Deferred further: schedule/calendar; the `punitive` flag + `pending_review` proof state (→ M6 queued proof).

## Test plan
- [x] `uv run pytest -q` (live Postgres) — green
- [x] `uv run ruff check .` — clean
- [x] `alembic upgrade head` → `b8c9d0e1f2a3` (round-trip verified for all three)
- [x] frontend `npm run gen:api` + `npm run test` + `npm run build` — green
- [ ] CI backend / frontend / e2e green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review (against the spec, before executing)

**Spec coverage (Addendum B6 / B10 content-filter scope):**
- Toys carry discreetness flags (noise / visibility / discreet_capable) ✓ (Task 2)
- Every generated task carries an intensity + discreetness profile + required toys ✓ (Tasks 3, 7)
- Punishments carry a discreetness profile + required toys ✓ (Tasks 4, 7)
- The active mode is a filter the drone engine applies when selecting tasks ✓ (Task 5) **and** punishments ✓ (Task 6)
- The live Mistress applies the same filter (B1 "binds her too") ✓ (Task 8 — directive injected into the authoritative-state block; the live persona also reads the same merit/limit/ceiling state)
- Vacation freezes (no draw) — already in M5a; the filter is gated behind `economy_frozen`, so it is never reached under vacation ✓ (Task 5 calls happen only when `not frozen` in the drone; the live block shows the VACATION directive from M5a)
- Mode is a consent control honored immediately — unchanged from M5a (a column read every turn) ✓
- **Deferred (stated):** all M5 frontend → **M5c**; schedule/calendar → later; `punitive`/`pending_review` → M6.

**Placeholder scan:** every code step shows complete code. The migrations are full (upgrade + downgrade, round-tripped). Task 5 Step 4 and Task 6 Step 3 give the full rewritten functions (not "similar to"). No "add error handling"/"TBD" left.

**Type consistency:**
- `task_allowed(mode, *, discreetness, intensity, required_toy_ids, toys_by_id, intensity_ceiling) -> bool` — same signature in `test_filter.py` (Task 1), `batch.draw_and_assign` (Task 5).
- `punishment_allowed(mode, *, discreetness, required_toy_ids, toys_by_id) -> bool` — same in `test_filter.py` (Task 1), `discipline.draw_punishment` (Task 6).
- `content_filter_directive(mode) -> str | None` — same in `test_filter.py` (Task 1), `persona.service` (Task 8).
- `Discreetness` members `OVERT/DISCREET/SILENT` (values `overt/discreet/silent`) — consistent across enum (Task 1), models (Tasks 3, 4), migrations (PG enum NAMES `'OVERT'/'DISCREET'/'SILENT'`, matching the M5a convention), and `_TaskGen`/`_PunishmentGen` (Task 7, normalized lower-case before coercion).
- `Toy.discreet_capable: bool` — used by the filter's `_ToyLike` protocol (Task 1), set by `add_toy` (Task 2), read in the draws via `{str(t.id): t}` maps (Tasks 5, 6).
- `required_toy_ids` is `list[str]` everywhere; the draws build `toys_by_id` keyed by `str(toy.id)`, and the filter looks up `str(tid)` — consistent string-keyed UUID comparison.
- `draw_and_assign(session, profile_id, *, now=None)` — new `now` kwarg; the only caller (`drones.standing_orders`) is updated to pass it (Task 5 Step 5).

**Migration chain:** `e5f6a7b8c9d0` → `f6a7b8c9d0e1` (toy) → `a7b8c9d0e1f2` (task/pool + creates `discreetness` enum) → `b8c9d0e1f2a3` (punishment/pool, reuses enum; downgrade leaves the type since task/pool still use it). Head after M5b: `b8c9d0e1f2a3`.

**Branch:** `feat/offline-5b-discreetness-content-filter`. Local-env caveat (clear `PYTHONHOME`/`PYTHONPATH`; Postgres up) per `smistress-dev-environment`; Playwright/CI gates fall to CI.
```
