# Offline-First M3 — Batch Generation (task pool + drone line bank) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the home box is online, the LLM pre-generates a **task pool** and a **drone line bank** that the deterministic offline drones then serve — varied in-persona lines and an auto-dropped daily task — with no LLM present, plus a "pools are low, grant a batch window" reminder when stores deplete.

**Architecture:** Batch generation runs **in the backend through the existing OpenAI-compatible provider seam** (Addendum B2: *"the agent is transport/availability only"*), gated on the LLM being `online`. Two new profile-scoped Postgres tables (`task_pool_item`, `drone_line`) hold the artifacts. The M2 drone engine is wired to (a) source its assignment line from the bank with a deterministic event × merit-band × time-of-day pick, (b) **draw and materialize** the day's task from the pool when none is active (the assignment unit *drops* the task — no LLM), and (c) emit a batch-window reminder when a pool runs low. Reminder lines that embed live state (denial timers, deadlines) stay deterministic and unchanged from M2. Empty bank / empty pool degrades gracefully to M2's hardcoded behavior, so the drones always work.

**Scope (locked):** Only the **two artifacts with live consumers** — task pool + drone line bank. The punishment pool ships with M4's discipline unit; standing orders ship with the audience-lifecycle milestone. The task pool's intensity/discreetness/required-toy profile (B6) is deferred to M5; M3 task-pool items carry description, proof type, and **merit** stakes only (debt is M4). **Trigger:** a manual `POST …/batch/generate` endpoint (503 when offline) + a refill-when-low reminder; no scheduler. **Frontend is unchanged** — the existing offline `StandingOrders` surface renders the new bank-sourced lines, the auto-dropped task, and the low-pool reminder through the unchanged `GET …/standing-orders` contract.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async (psycopg3), Alembic, Pydantic v2, pytest (asyncio_mode=auto, live Postgres `smistress_test`), ruff line-length=100. Convention: **services flush, endpoints commit**; reuse the existing `proof_requirement` PG enum.

---

## File Structure

**New (backend/):**
- `app/db/models/batch.py` — `TaskPoolItem`, `DroneLine` ORM models.
- `alembic/versions/b2c3d4e5f6a7_add_batch_artifacts.py` — creates both tables (down_revision `a1b2c3d4e5f6`).
- `app/batch/__init__.py` — empty package marker.
- `app/batch/prompt.py` — builds the generation prompt (`list[ChatMessage]`) from profile/character/economy.
- `app/batch/service.py` — `merit_band`, `time_of_day`, `pick_line`, `pool_status`, `parse_batch`, `generate_batch`, `draw_and_assign`.
- `app/schemas/batch.py` — `GenerateBatchOut`, `PoolStatusOut`.
- `app/api/batch.py` — `POST …/batch/generate` (online-gated), `GET …/batch/status`.
- `tests/batch/__init__.py`, `tests/batch/test_helpers.py`, `tests/batch/test_pool_status.py`, `tests/batch/test_generate.py`, `tests/batch/test_draw.py`, `tests/api/test_batch_api.py`.

**Modified (backend/):**
- `app/config.py` — pool targets/thresholds.
- `app/db/models/__init__.py` — register the two new models.
- `app/drones/service.py` — bank-sourced assignment line, auto-draw, batch-window reminder; hardcoded fallback preserved.
- `app/api/drones.py` — commit after `standing_orders` (it may now draw a task).
- `app/main.py` — include `batch_router`.
- `tests/drones/test_drone_service.py` — adjust the one emptiness assertion for the new batch-window reminder; add bank/draw coverage.

---

## Task 1: New ORM models — `TaskPoolItem` and `DroneLine`

**Files:**
- Create: `backend/app/db/models/batch.py`
- Modify: `backend/app/db/models/__init__.py`
- Test: `backend/tests/batch/__init__.py`, `backend/tests/batch/test_helpers.py` (model round-trip portion)

- [ ] **Step 1: Create the test package marker**

Create `backend/tests/batch/__init__.py` (empty file).

- [ ] **Step 2: Write the failing model round-trip test**

Create `backend/tests/batch/test_helpers.py`:

```python
from app.db.enums import ProofRequirement
from app.db.models.batch import DroneLine, TaskPoolItem
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_task_pool_item_round_trip(session):
    p = await _profile(session)
    item = TaskPoolItem(
        profile_id=p.id,
        description="Ten slow squats, posture held.",
        proof_requirement=ProofRequirement.HONOR,
        difficulty="standard",
        merit_reward=8,
        merit_miss_penalty=4,
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    assert item.consumed is False
    assert item.proof_requirement is ProofRequirement.HONOR


async def test_drone_line_round_trip(session):
    p = await _profile(session)
    line = DroneLine(
        profile_id=p.id,
        unit="assignment",
        event="task_drop",
        merit_band="mid",
        time_of_day="morning",
        text="Mistress has set you: {task}. Report when complete.",
    )
    session.add(line)
    await session.flush()
    await session.refresh(line)
    assert "{task}" in line.text
    assert line.merit_band == "mid"
```

- [ ] **Step 3: Run the test to verify it fails**

Run (PowerShell, clear the broken Python env first per the `smistress-dev-environment` memory):
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/batch/test_helpers.py -q
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db.models.batch'`.

- [ ] **Step 4: Create the models**

Create `backend/app/db/models/batch.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import ProofRequirement
from app.db.models.profile import SubProfile


class TaskPoolItem(Base):
    """A pre-generated, undropped task template (Addendum B4 task pool).

    The assignment drone draws one and materializes it into a real Task while
    offline — no LLM present. Carries merit stakes only; debt stakes (M4) and
    the intensity/discreetness profile (B6/M5) are added by later milestones.
    """

    __tablename__ = "task_pool_item"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))

    description: Mapped[str] = mapped_column(String)
    proof_requirement: Mapped[ProofRequirement] = mapped_column(
        Enum(ProofRequirement, name="proof_requirement")
    )
    difficulty: Mapped[str] = mapped_column(String, default="standard")

    merit_reward: Mapped[int] = mapped_column(default=0)
    merit_fail_penalty: Mapped[int] = mapped_column(default=0)
    merit_miss_penalty: Mapped[int] = mapped_column(default=0)

    consumed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    profile: Mapped[SubProfile] = relationship()


class DroneLine(Base):
    """A pre-generated in-persona drone line (Addendum B4 line bank).

    Drawn by event x merit band x time-of-day so offline lines vary day to day
    without an LLM. ``text`` may contain a ``{task}`` placeholder (task_drop).
    """

    __tablename__ = "drone_line"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))

    unit: Mapped[str] = mapped_column(String)  # "assignment" | "reminder"
    event: Mapped[str] = mapped_column(String)  # "task_drop" | "no_task" | "batch_window"
    merit_band: Mapped[str] = mapped_column(String, default="any")  # low|mid|high|any
    time_of_day: Mapped[str] = mapped_column(String, default="any")  # morning|day|evening|night|any
    text: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    profile: Mapped[SubProfile] = relationship()
```

- [ ] **Step 5: Register the models so SQLAlchemy/`Base.metadata` sees them**

In `backend/app/db/models/__init__.py`, add after the `availability` import line:

```python
from app.db.models.batch import DroneLine, TaskPoolItem  # noqa: F401
```

- [ ] **Step 6: Run the test to verify it passes**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/batch/test_helpers.py -q
```
Expected: PASS (2 passed). The `session` fixture creates the schema from `Base.metadata`, so the tables exist for the test even before the migration.

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/models/batch.py backend/app/db/models/__init__.py backend/tests/batch/__init__.py backend/tests/batch/test_helpers.py
git commit -m "feat(batch): TaskPoolItem + DroneLine models for offline batch artifacts"
```

---

## Task 2: Alembic migration for the two tables

**Files:**
- Create: `backend/alembic/versions/b2c3d4e5f6a7_add_batch_artifacts.py`

- [ ] **Step 1: Write the migration**

The current migration head is `a1b2c3d4e5f6` (verified via the revision chain). The `proof_requirement` PG enum already exists from the initial schema — reference it with `create_type=False` so the migration does **not** try to recreate it.

Create `backend/alembic/versions/b2c3d4e5f6a7_add_batch_artifacts.py`:

```python
"""add batch artifacts (task pool + drone line bank)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    proof = sa.Enum(
        'photo', 'video', 'timer', 'honor', 'none',
        name='proof_requirement', create_type=False,
    )
    op.create_table(
        'task_pool_item',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('proof_requirement', proof, nullable=False),
        sa.Column('difficulty', sa.String(), server_default='standard', nullable=False),
        sa.Column('merit_reward', sa.Integer(), server_default='0', nullable=False),
        sa.Column('merit_fail_penalty', sa.Integer(), server_default='0', nullable=False),
        sa.Column('merit_miss_penalty', sa.Integer(), server_default='0', nullable=False),
        sa.Column('consumed', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'drone_line',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('unit', sa.String(), nullable=False),
        sa.Column('event', sa.String(), nullable=False),
        sa.Column('merit_band', sa.String(), server_default='any', nullable=False),
        sa.Column('time_of_day', sa.String(), server_default='any', nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('drone_line')
    op.drop_table('task_pool_item')
```

- [ ] **Step 2: Apply and round-trip the migration against a scratch DB**

The `smistress_test` DB is recreated per test run, so exercise the migration against the dev `smistress` DB. Run from `backend/`:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run alembic upgrade head
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run alembic downgrade -1
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run alembic upgrade head
```
Expected: each command exits 0; `upgrade head` logs `Running upgrade a1b2c3d4e5f6 -> b2c3d4e5f6a7`, the downgrade logs the reverse, and the second upgrade re-applies cleanly. (If Postgres is not running locally, this gate is deferred to CI — note it and proceed; CI's `backend` job runs migrations against its Postgres service.)

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/b2c3d4e5f6a7_add_batch_artifacts.py
git commit -m "feat(batch): migration for task_pool_item + drone_line"
```

---

## Task 3: Batch helpers — `merit_band`, `time_of_day`, `pick_line`, `pool_status`

**Files:**
- Create: `backend/app/batch/__init__.py` (empty), `backend/app/batch/service.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/batch/test_helpers.py`, `backend/tests/batch/test_pool_status.py`

- [ ] **Step 1: Add pool targets/thresholds to Settings**

In `backend/app/config.py`, add these fields after `heartbeat_ttl_seconds`:

```python
    batch_task_target: int = 8  # top the task pool up to this many unconsumed items
    batch_task_low: int = 2  # at/below this, the reminder unit asks for a batch window
    batch_line_target: int = 24  # top the drone line bank up to this many lines
    batch_line_low: int = 6
```

- [ ] **Step 2: Write the failing helper + pool-status tests**

Append to `backend/tests/batch/test_helpers.py`:

```python
from datetime import datetime, timezone

from app.batch import service as batch_svc
from app.db.models.batch import DroneLine as _DL


def test_merit_band_thresholds():
    assert batch_svc.merit_band(60) == "high"
    assert batch_svc.merit_band(0) == "mid"
    assert batch_svc.merit_band(49) == "mid"
    assert batch_svc.merit_band(-1) == "low"


def test_time_of_day_buckets():
    def at(h):
        return batch_svc.time_of_day(datetime(2026, 6, 9, h, tzinfo=timezone.utc))

    assert at(7) == "morning"
    assert at(14) == "day"
    assert at(19) == "evening"
    assert at(2) == "night"


def _line(event, band, tod, text):
    return _DL(unit="assignment", event=event, merit_band=band, time_of_day=tod, text=text)


def test_pick_line_prefers_exact_band_and_tod():
    lines = [
        _line("task_drop", "any", "any", "generic"),
        _line("task_drop", "high", "evening", "exact"),
        _line("task_drop", "high", "any", "band-only"),
        _line("no_task", "high", "evening", "wrong-event"),
    ]
    picked = batch_svc.pick_line(lines, event="task_drop", band="high", tod="evening", rotation=0)
    assert picked.text == "exact"


def test_pick_line_excludes_mismatched_band():
    lines = [_line("task_drop", "low", "any", "wrong-band")]
    assert batch_svc.pick_line(lines, event="task_drop", band="high", tod="day", rotation=0) is None


def test_pick_line_rotation_is_stable_and_varies():
    lines = [
        _line("task_drop", "any", "any", "a"),
        _line("task_drop", "any", "any", "b"),
    ]
    first = batch_svc.pick_line(lines, event="task_drop", band="mid", tod="day", rotation=0)
    same = batch_svc.pick_line(lines, event="task_drop", band="mid", tod="day", rotation=0)
    other = batch_svc.pick_line(lines, event="task_drop", band="mid", tod="day", rotation=1)
    assert first.text == same.text
    assert {first.text, other.text} == {"a", "b"}
```

Create `backend/tests/batch/test_pool_status.py`:

```python
from app.batch import service as batch_svc
from app.db.enums import ProofRequirement
from app.db.models.batch import DroneLine, TaskPoolItem
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_pool_status_empty_is_low(session):
    p = await _profile(session)
    status = await batch_svc.pool_status(session, p.id)
    assert status.task_pool == 0
    assert status.line_bank == 0
    assert status.task_pool_low is True
    assert status.line_bank_low is True


async def test_pool_status_counts_only_unconsumed_tasks(session):
    p = await _profile(session)
    session.add(TaskPoolItem(
        profile_id=p.id, description="a", proof_requirement=ProofRequirement.HONOR
    ))
    session.add(TaskPoolItem(
        profile_id=p.id, description="b", proof_requirement=ProofRequirement.HONOR, consumed=True
    ))
    session.add(DroneLine(profile_id=p.id, unit="assignment", event="task_drop", text="x"))
    await session.flush()
    status = await batch_svc.pool_status(session, p.id)
    assert status.task_pool == 1  # consumed item excluded
    assert status.line_bank == 1
```

- [ ] **Step 3: Run the tests to verify they fail**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/batch/test_helpers.py tests/batch/test_pool_status.py -q
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.batch'` (and `pool_status`/helpers undefined).

- [ ] **Step 4: Create the package marker and the helper/status code**

Create `backend/app/batch/__init__.py` (empty file).

Create `backend/app/batch/service.py`:

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.batch import DroneLine, TaskPoolItem

# --- Banding (tunable; mirrors the spirit of the disposition bands) ---------
_HIGH_MERIT = 50
_LOW_MERIT = 0


def merit_band(merit: int) -> str:
    if merit >= _HIGH_MERIT:
        return "high"
    if merit < _LOW_MERIT:
        return "low"
    return "mid"


def time_of_day(now: datetime) -> str:
    h = now.hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "day"
    if 17 <= h < 22:
        return "evening"
    return "night"


def _score(line: DroneLine, band: str, tod: str) -> int:
    """Specificity score for a candidate line; -1 means 'excluded' (wrong band/tod)."""
    score = 0
    if line.merit_band == band:
        score += 2
    elif line.merit_band == "any":
        score += 1
    else:
        return -1
    if line.time_of_day == tod:
        score += 2
    elif line.time_of_day == "any":
        score += 1
    else:
        return -1
    return score


def pick_line(
    lines: list[DroneLine], *, event: str, band: str, tod: str, rotation: int
) -> DroneLine | None:
    """Most-specific matching line for an event, rotated deterministically.

    ``rotation`` (e.g. the day ordinal) selects among equally-specific candidates
    so the line is stable within a render/day but varies day to day. Returns None
    when the bank has no usable line for the event (caller falls back to a
    hardcoded line so the drones always speak).
    """
    scored = [(line, _score(line, band, tod)) for line in lines if line.event == event]
    scored = [(line, s) for line, s in scored if s >= 0]
    if not scored:
        return None
    best = max(s for _, s in scored)
    top = sorted((line for line, s in scored if s == best), key=lambda line: str(line.id))
    return top[rotation % len(top)]


@dataclass
class PoolStatus:
    task_pool: int  # unconsumed task pool items
    line_bank: int  # total drone lines
    task_pool_low: bool
    line_bank_low: bool


async def pool_status(session: AsyncSession, profile_id: uuid.UUID) -> PoolStatus:
    from app.config import Settings  # local import; module-level Settings re-used below

    tasks = (await session.execute(
        select(func.count())
        .select_from(TaskPoolItem)
        .where(TaskPoolItem.profile_id == profile_id, TaskPoolItem.consumed.is_(False))
    )).scalar_one()
    lines = (await session.execute(
        select(func.count()).select_from(DroneLine).where(DroneLine.profile_id == profile_id)
    )).scalar_one()
    return PoolStatus(
        task_pool=tasks,
        line_bank=lines,
        task_pool_low=tasks <= _settings.batch_task_low,
        line_bank_low=lines <= _settings.batch_line_low,
    )


# Module-level Settings instance, matching the convention in availability/service.py.
from app.config import Settings  # noqa: E402

_settings = Settings()
```

Note: keep the single `_settings = Settings()` at the bottom (after imports) and delete the stray `from app.config import Settings` line inside `pool_status` — it was only a thinking aid. The final `pool_status` body must reference the module-level `_settings`. Concretely, `pool_status` should **not** contain any local `Settings` import; ensure the function body is exactly the two counts + the `PoolStatus(...)` return using `_settings`.

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/batch/test_helpers.py tests/batch/test_pool_status.py -q
```
Expected: PASS (all helper + pool-status tests green).

- [ ] **Step 6: Lint**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run ruff check app/batch/service.py app/config.py
```
Expected: no errors. (If ruff flags the `E402` module-level import, the `# noqa: E402` on the `Settings` import line covers it.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/batch/__init__.py backend/app/batch/service.py backend/app/config.py backend/tests/batch/test_helpers.py backend/tests/batch/test_pool_status.py
git commit -m "feat(batch): banding, line-pick, and pool-status helpers"
```

---

## Task 4: `parse_batch` + `generate_batch` (LLM → validated artifacts, top-up)

**Files:**
- Create: `backend/app/batch/prompt.py`
- Modify: `backend/app/batch/service.py`
- Test: `backend/tests/batch/test_generate.py`

- [ ] **Step 1: Write the failing generation test**

Create `backend/tests/batch/test_generate.py`:

```python
import json

from app.batch import service as batch_svc
from app.db.enums import ProofRequirement
from app.db.models.batch import DroneLine, TaskPoolItem
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from sqlalchemy import func, select


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


def _payload(n_tasks=3, n_lines=4):
    return ChatResult(content=json.dumps({
        "tasks": [
            {"description": f"task {i}", "proof": "honor", "merit_reward": 5,
             "merit_miss_penalty": 3, "difficulty": "standard"}
            for i in range(n_tasks)
        ],
        "lines": [
            {"unit": "assignment", "event": "task_drop", "merit_band": "mid",
             "time_of_day": "any", "text": "Mistress has set you: {task}."}
            for _ in range(n_lines)
        ],
    }))


async def test_generate_persists_parsed_artifacts(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[_payload(3, 4)])
    result = await batch_svc.generate_batch(session, p.id, provider)
    assert result.tasks_added == 3
    assert result.lines_added == 4
    tasks = (await session.execute(
        select(func.count()).select_from(TaskPoolItem).where(TaskPoolItem.profile_id == p.id)
    )).scalar_one()
    assert tasks == 3


async def test_generate_tops_up_only_to_target(session):
    p = await _profile(session)
    # Pretend the pool is already near target: target default 8, add 2 lines short of nothing.
    for i in range(7):
        session.add(TaskPoolItem(
            profile_id=p.id, description=f"have {i}", proof_requirement=ProofRequirement.HONOR
        ))
    await session.flush()
    provider = MockLLMProvider(scripted=[_payload(5, 0)])
    result = await batch_svc.generate_batch(session, p.id, provider)
    assert result.tasks_added == 1  # 8 target - 7 existing


async def test_generate_skips_malformed_items(session):
    p = await _profile(session)
    bad = ChatResult(content=json.dumps({
        "tasks": [
            {"description": "ok", "proof": "honor"},
            {"description": "bad proof", "proof": "telepathy"},  # invalid -> skipped
            {"proof": "honor"},  # missing description -> skipped
        ],
        "lines": [{"unit": "assignment", "event": "task_drop", "text": "x"}],
    }))
    provider = MockLLMProvider(scripted=[bad])
    result = await batch_svc.generate_batch(session, p.id, provider)
    assert result.tasks_added == 1  # only the valid task


async def test_generate_handles_non_json_gracefully(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[ChatResult(content="I am away; no JSON here.")])
    result = await batch_svc.generate_batch(session, p.id, provider)
    assert result.tasks_added == 0
    assert result.lines_added == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/batch/test_generate.py -q
```
Expected: FAIL — `AttributeError: module 'app.batch.service' has no attribute 'generate_batch'`.

- [ ] **Step 3: Write the prompt builder**

Create `backend/app/batch/prompt.py`:

```python
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
    '  ]\n'
    '}\n'
    'For "task_drop" lines, include the literal placeholder {task} where the task '
    'description belongs. Lines are cold, mechanical, impersonal drone announcements '
    '(e.g. "Mistress has assigned: {task}. Report when complete."), never warm.'
)


def _profile_brief(profile: SubProfile, character: CharacterModel | None) -> str:
    goals = ", ".join(g.title for g in profile.goals if g.title) or "none recorded"
    favs = ", ".join(
        k.kink for k in profile.kinks if k.rating and k.rating.value in ("favorite", "like")
    ) or "none recorded"
    voice = "the Mistress"
    if character is not None:
        voice = f"{character.honorific or 'the Mistress'} (strict={character.strictness}, warmth={character.warmth})"
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
        f"Generate {task_count} task-pool items and {line_count} drone lines.\n\n"
        f"{_JSON_SCHEMA}"
    )
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]
```

- [ ] **Step 4: Add `parse_batch` and `generate_batch` to the service**

Add these imports to the top of `backend/app/batch/service.py` (alongside the existing ones):

```python
import json
import re

from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy.orm import selectinload

from app.batch.prompt import build_generation_prompt
from app.db.enums import ProofRequirement
from app.db.models.character import CharacterModel
from app.db.models.economy import EconomyState
from app.db.models.profile import SubProfile
from app.llm.provider import LLMProvider
```

Then add the parse models, parser, the `GenerateResult` dataclass, and `generate_batch` (place above the `_settings` line at the bottom):

```python
# First top-level JSON object in the model's reply (it may add prose around it).
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_VALID_BANDS = {"low", "mid", "high", "any"}
_VALID_TODS = {"morning", "day", "evening", "night", "any"}
_VALID_UNITS = {"assignment", "reminder"}


class _TaskGen(BaseModel):
    description: str
    proof: ProofRequirement
    merit_reward: int = 0
    merit_fail_penalty: int = 0
    merit_miss_penalty: int = 0
    difficulty: str = "standard"

    @field_validator("proof", mode="before")
    @classmethod
    def _lower(cls, v: object) -> object:
        return str(v).strip().lower() if v is not None else v


class _LineGen(BaseModel):
    unit: str
    event: str
    text: str
    merit_band: str = "any"
    time_of_day: str = "any"

    @field_validator("unit")
    @classmethod
    def _unit(cls, v: str) -> str:
        if v not in _VALID_UNITS:
            raise ValueError("bad unit")
        return v

    @field_validator("merit_band")
    @classmethod
    def _band(cls, v: str) -> str:
        if v not in _VALID_BANDS:
            raise ValueError("bad band")
        return v

    @field_validator("time_of_day")
    @classmethod
    def _tod(cls, v: str) -> str:
        if v not in _VALID_TODS:
            raise ValueError("bad tod")
        return v


def parse_batch(content: str) -> tuple[list[_TaskGen], list[_LineGen]]:
    """Best-effort parse of the model's reply. Malformed JSON or invalid items are
    skipped (never raises) so a bad generation simply adds nothing."""
    match = _JSON_RE.search(content)
    if not match:
        return [], []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return [], []
    if not isinstance(data, dict):
        return [], []
    tasks: list[_TaskGen] = []
    for raw in data.get("tasks", []) or []:
        try:
            tasks.append(_TaskGen.model_validate(raw))
        except ValidationError:
            continue
    lines: list[_LineGen] = []
    for raw in data.get("lines", []) or []:
        try:
            lines.append(_LineGen.model_validate(raw))
        except ValidationError:
            continue
    return tasks, lines


@dataclass
class GenerateResult:
    tasks_added: int
    lines_added: int
    task_pool: int  # unconsumed total after the run
    line_bank: int  # total after the run


async def _profile_for_generation(
    session: AsyncSession, profile_id: uuid.UUID
) -> tuple[SubProfile, CharacterModel | None, EconomyState | None]:
    profile = (await session.execute(
        select(SubProfile)
        .where(SubProfile.id == profile_id)
        .options(selectinload(SubProfile.goals), selectinload(SubProfile.kinks))
    )).scalar_one_or_none()
    if profile is None:
        raise ProfileNotFound(str(profile_id))
    character = (await session.execute(
        select(CharacterModel).where(CharacterModel.profile_id == profile_id)
    )).scalar_one_or_none()
    econ = (await session.execute(
        select(EconomyState).where(EconomyState.profile_id == profile_id)
    )).scalar_one_or_none()
    return profile, character, econ


class ProfileNotFound(Exception):
    pass


async def generate_batch(
    session: AsyncSession, profile_id: uuid.UUID, provider: LLMProvider
) -> GenerateResult:
    """Call the LLM to refill the offline pools, topping each up to its target.

    Only as many parsed items as are needed to reach the target are persisted.
    Caller commits.
    """
    profile, character, econ = await _profile_for_generation(session, profile_id)
    status = await pool_status(session, profile_id)
    want_tasks = max(0, _settings.batch_task_target - status.task_pool)
    want_lines = max(0, _settings.batch_line_target - status.line_bank)

    messages = build_generation_prompt(
        profile, character, econ, task_count=want_tasks, line_count=want_lines
    )
    reply = await provider.chat(messages)
    parsed_tasks, parsed_lines = parse_batch(reply.content)

    added_tasks = 0
    for gen in parsed_tasks[:want_tasks]:
        session.add(TaskPoolItem(
            profile_id=profile_id,
            description=gen.description,
            proof_requirement=gen.proof,
            difficulty=gen.difficulty,
            merit_reward=gen.merit_reward,
            merit_fail_penalty=gen.merit_fail_penalty,
            merit_miss_penalty=gen.merit_miss_penalty,
        ))
        added_tasks += 1
    added_lines = 0
    for gen in parsed_lines[:want_lines]:
        session.add(DroneLine(
            profile_id=profile_id,
            unit=gen.unit,
            event=gen.event,
            merit_band=gen.merit_band,
            time_of_day=gen.time_of_day,
            text=gen.text,
        ))
        added_lines += 1
    await session.flush()
    after = await pool_status(session, profile_id)
    return GenerateResult(added_tasks, added_lines, after.task_pool, after.line_bank)
```

Note on the `ProfileNotFound` placement: define the `class ProfileNotFound(Exception)` **near the top** of `service.py` (just after the imports, before the banding helpers) rather than mid-file as shown above — Python needs it defined before `_profile_for_generation` references it. The block above groups it for readability; when implementing, hoist the class to the top.

- [ ] **Step 5: Run the test to verify it passes**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/batch/test_generate.py -q
```
Expected: PASS (4 passed).

- [ ] **Step 6: Lint**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run ruff check app/batch/
```
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/batch/prompt.py backend/app/batch/service.py backend/tests/batch/test_generate.py
git commit -m "feat(batch): LLM generation -> validated, top-up task pool + line bank"
```

---

## Task 5: `draw_and_assign` — the assignment unit drops a pooled task

**Files:**
- Modify: `backend/app/batch/service.py`
- Test: `backend/tests/batch/test_draw.py`

- [ ] **Step 1: Write the failing draw test**

Create `backend/tests/batch/test_draw.py`:

```python
from app.batch import service as batch_svc
from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.batch import TaskPoolItem
from app.db.models.task import Task
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from sqlalchemy import select


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_draw_materializes_a_task_and_consumes_the_item(session):
    p = await _profile(session)
    session.add(TaskPoolItem(
        profile_id=p.id, description="Kneel and breathe, five minutes.",
        proof_requirement=ProofRequirement.TIMER, merit_reward=6, merit_miss_penalty=4,
    ))
    await session.flush()

    task = await batch_svc.draw_and_assign(session, p.id)
    assert task is not None
    assert task.description == "Kneel and breathe, five minutes."
    assert task.status is TaskStatus.ASSIGNED
    assert task.merit_reward == 6

    item = (await session.execute(select(TaskPoolItem))).scalar_one()
    assert item.consumed is True
    # a real Task row now exists
    assert (await session.execute(select(Task))).scalar_one().id == task.id


async def test_draw_returns_none_when_pool_empty(session):
    p = await _profile(session)
    assert await batch_svc.draw_and_assign(session, p.id) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/batch/test_draw.py -q
```
Expected: FAIL — `AttributeError: ... has no attribute 'draw_and_assign'`.

- [ ] **Step 3: Implement `draw_and_assign`**

Add to `backend/app/batch/service.py`. First extend the imports near the top:

```python
from app.db.models.task import Task
from app.loop import service as loop_svc
```

Then add the function (above the `_settings` line):

```python
async def _next_pool_item(session: AsyncSession, profile_id: uuid.UUID) -> TaskPoolItem | None:
    return (await session.execute(
        select(TaskPoolItem)
        .where(TaskPoolItem.profile_id == profile_id, TaskPoolItem.consumed.is_(False))
        .order_by(TaskPoolItem.created_at)
        .limit(1)
    )).scalars().first()


async def draw_and_assign(session: AsyncSession, profile_id: uuid.UUID) -> Task | None:
    """The assignment drone drops the next pooled task as a real Task (Addendum
    B3/B4) — no LLM. Marks the pool item consumed. Returns None if the pool is
    empty. Caller commits."""
    item = await _next_pool_item(session, profile_id)
    if item is None:
        return None
    task = await loop_svc.assign_task(
        session,
        profile_id,
        description=item.description,
        proof_requirement=item.proof_requirement,
        merit_reward=item.merit_reward,
        merit_fail_penalty=item.merit_fail_penalty,
        merit_miss_penalty=item.merit_miss_penalty,
    )
    item.consumed = True
    await session.flush()
    return task
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/batch/test_draw.py -q
```
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/batch/service.py backend/tests/batch/test_draw.py
git commit -m "feat(batch): assignment unit draws + materializes a pooled task"
```

---

## Task 6: Wire the drone engine to the bank, auto-draw, and the batch-window reminder

**Files:**
- Modify: `backend/app/drones/service.py`, `backend/app/api/drones.py`, `backend/tests/drones/test_drone_service.py`
- Test: same test module (new cases + one adjusted assertion)

- [ ] **Step 1: Add the failing/adjusted drone tests**

In `backend/tests/drones/test_drone_service.py`, **replace** `test_no_reminder_when_no_timers_or_deadline` with a version that ignores the new batch-window reminder (an empty pool legitimately prompts for a batch window), then append the new bank/draw cases.

Replace that one test with:

```python
async def test_no_state_reminder_when_no_timers_or_deadline(session):
    p = await _profile(session)
    session.add(
        Task(
            profile_id=p.id,
            description="No deadline drill",
            proof_requirement=ProofRequirement.HONOR,
            status=TaskStatus.ASSIGNED,
        )
    )
    await session.flush()
    notices = await drone_svc.standing_orders(session, p.id)
    reminders = [n for n in notices if n.unit == "reminder"]
    # denial/deadline reminders are absent; only the (empty-pool) batch-window prompt may remain
    assert all("denial" not in n.line.lower() for n in reminders)
    assert all("deadline" not in n.line.lower() for n in reminders)
```

Append these new cases at the end of the file:

```python
async def test_bank_line_used_for_task_drop_when_available(session):
    from app.db.models.batch import DroneLine

    p = await _profile(session)
    session.add(
        Task(
            profile_id=p.id, description="Posture drill",
            proof_requirement=ProofRequirement.HONOR, status=TaskStatus.ASSIGNED,
        )
    )
    session.add(DroneLine(
        profile_id=p.id, unit="assignment", event="task_drop",
        merit_band="any", time_of_day="any", text="DRONE-7 logs your charge: {task}.",
    ))
    await session.flush()
    notices = await drone_svc.standing_orders(session, p.id)
    assignment = [n for n in notices if n.unit == "assignment"][0]
    assert assignment.line == "DRONE-7 logs your charge: Posture drill."


async def test_assignment_unit_drops_a_pooled_task_when_none_active(session):
    from app.db.models.batch import TaskPoolItem
    from app.db.models.task import Task as TaskModel
    from sqlalchemy import select

    p = await _profile(session)
    session.add(TaskPoolItem(
        profile_id=p.id, description="Drawn drill", proof_requirement=ProofRequirement.HONOR,
        merit_reward=5,
    ))
    await session.flush()
    notices = await drone_svc.standing_orders(session, p.id)
    assignment = [n for n in notices if n.unit == "assignment"][0]
    assert "Drawn drill" in assignment.line
    # a real Task now exists and is active
    task = (await session.execute(select(TaskModel))).scalar_one()
    assert task.status is TaskStatus.ASSIGNED


async def test_batch_window_reminder_when_pool_low(session):
    p = await _profile(session)
    notices = await drone_svc.standing_orders(session, p.id)
    reminders = [n for n in notices if n.unit == "reminder"]
    assert any("batch window" in n.line.lower() for n in reminders)
```

- [ ] **Step 2: Run the drone tests to verify the new ones fail**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/drones/ -q
```
Expected: the three new/adjusted tests FAIL (bank line not used; no auto-draw; no batch-window reminder). The other M2 drone tests still pass.

- [ ] **Step 3: Rewrite `standing_orders` to use the bank, auto-draw, and prompt for a batch window**

Replace `backend/app/drones/service.py` entirely with:

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.batch import service as batch_svc
from app.db.enums import TaskStatus
from app.db.models.batch import DroneLine
from app.db.models.economy import DenialTimer, EconomyState
from app.db.models.task import Task
from app.economy import service as econ_svc
from app.services import profile as profile_svc

# Task statuses that count as a live, outstanding assignment (mirrors app.chat.service).
_ACTIVE_STATUSES = (
    TaskStatus.ASSIGNED,
    TaskStatus.IN_PROGRESS,
    TaskStatus.PROOF_SUBMITTED,
    TaskStatus.VERIFYING,
)

# A task deadline within this window earns a "due soon" reminder.
_DUE_SOON = timedelta(hours=24)

# Hardcoded fallbacks — used verbatim when the bank has no matching line, so the
# drones always speak even before the first batch generation (graceful degradation).
_FALLBACK_TASK_DROP = "Mistress has assigned: {task}. Report when complete."
_FALLBACK_NO_TASK = "No standing assignment. Await Mistress's instruction."
_FALLBACK_BATCH_WINDOW = (
    "Her stores run low. Grant her a batch window — keep the box on so she may "
    "replenish your orders."
)


@dataclass
class DroneNotice:
    """One cold, mechanical line from a drone duty-unit (Addendum B3)."""

    unit: str  # "assignment" | "reminder"
    line: str


def _bank_line(
    lines: list[DroneLine], *, event: str, band: str, tod: str, rotation: int, fallback: str
) -> str:
    picked = batch_svc.pick_line(lines, event=event, band=band, tod=tod, rotation=rotation)
    return picked.text if picked is not None else fallback


def _assignment_line(
    task: Task | None, lines: list[DroneLine], *, band: str, tod: str, rotation: int
) -> str:
    if task is None:
        return _bank_line(
            lines, event="no_task", band=band, tod=tod, rotation=rotation,
            fallback=_FALLBACK_NO_TASK,
        )
    template = _bank_line(
        lines, event="task_drop", band=band, tod=tod, rotation=rotation,
        fallback=_FALLBACK_TASK_DROP,
    )
    return template.replace("{task}", task.description)


def _reminder_lines(timers: list[DenialTimer], task: Task | None, now: datetime) -> list[str]:
    lines: list[str] = []
    for timer in timers:
        reason = f": {timer.reason}" if timer.reason else ""
        lines.append(f"Denial remains in effect{reason}. Endure it until she lifts it.")
    if task is not None and task.deadline is not None:
        if now >= task.deadline:
            lines.append(
                "Your task deadline has passed. Mistress will judge the lapse on her return."
            )
        elif task.deadline - now <= _DUE_SOON:
            lines.append("Your task is due within the day. Do not keep her waiting.")
    return lines


async def _active_task(session: AsyncSession, profile_id: uuid.UUID) -> Task | None:
    return (await session.execute(
        select(Task)
        .where(Task.profile_id == profile_id, Task.status.in_(_ACTIVE_STATUSES))
        .order_by(Task.created_at.desc())
        .limit(1)
    )).scalars().first()


async def _bank_lines(session: AsyncSession, profile_id: uuid.UUID) -> list[DroneLine]:
    return list((await session.execute(
        select(DroneLine).where(DroneLine.profile_id == profile_id)
    )).scalars().all())


async def _merit(session: AsyncSession, profile_id: uuid.UUID) -> int:
    econ = (await session.execute(
        select(EconomyState).where(EconomyState.profile_id == profile_id)
    )).scalar_one_or_none()
    return econ.merit if econ is not None else 0


async def standing_orders(
    session: AsyncSession, profile_id: uuid.UUID, *, now: datetime | None = None
) -> list[DroneNotice]:
    """Deterministic offline notices (Addendum B3/B4).

    The assignment unit drops a pooled task when none is active (no LLM); lines
    are drawn from the pre-generated bank (event x merit band x time-of-day),
    falling back to hardcoded lines when the bank is empty. When a pool runs low
    the reminder unit asks the sub to grant a batch window. ``now`` is injectable
    for deterministic tests. Caller commits (a draw mutates state)."""
    now = now or datetime.now(timezone.utc)
    await profile_svc.get_profile(session, profile_id)  # raises ProfileNotFound

    task = await _active_task(session, profile_id)
    if task is None:
        # The assignment unit drops the day's task from the pool (if any).
        task = await batch_svc.draw_and_assign(session, profile_id)

    lines = await _bank_lines(session, profile_id)
    band = batch_svc.merit_band(await _merit(session, profile_id))
    tod = batch_svc.time_of_day(now)
    rotation = date.fromtimestamp(now.timestamp()).toordinal()

    notices = [DroneNotice(
        unit="assignment",
        line=_assignment_line(task, lines, band=band, tod=tod, rotation=rotation),
    )]

    timers = await econ_svc.active_denial_timers(session, profile_id)
    notices += [
        DroneNotice(unit="reminder", line=line)
        for line in _reminder_lines(timers, task, now)
    ]

    status = await batch_svc.pool_status(session, profile_id)
    if status.task_pool_low or status.line_bank_low:
        notices.append(DroneNotice(
            unit="reminder",
            line=_bank_line(
                lines, event="batch_window", band=band, tod=tod, rotation=rotation,
                fallback=_FALLBACK_BATCH_WINDOW,
            ),
        ))
    return notices
```

- [ ] **Step 4: Commit the draw on the endpoint (a GET that may drop a task)**

In `backend/app/api/drones.py`, add a commit after the service call. Replace the body of `standing_orders` with:

```python
    try:
        notices = await drone_svc.standing_orders(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"profile {profile_id} not found"
        )
    await session.commit()
    return StandingOrdersOut(
        notices=[DroneNoticeOut(unit=n.unit, line=n.line) for n in notices]
    )
```

(The `status` name is the FastAPI `status` module already imported — unchanged. The `await session.commit()` persists any task the assignment unit dropped.)

- [ ] **Step 5: Run the full drone + batch suite to verify green**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/drones/ tests/batch/ -q
```
Expected: PASS. The bank line is used when present; the pooled task is auto-dropped; the batch-window reminder appears when low; M2's state-derived reminder tests still pass (those create active tasks/timers and assert specific phrases).

- [ ] **Step 6: Lint**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run ruff check app/drones/ app/api/drones.py
```
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/drones/service.py backend/app/api/drones.py backend/tests/drones/test_drone_service.py
git commit -m "feat(drones): serve bank lines, auto-drop pooled task, prompt batch window when low"
```

---

## Task 7: API — `POST …/batch/generate` (online-gated) and `GET …/batch/status`

**Files:**
- Create: `backend/app/schemas/batch.py`, `backend/app/api/batch.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_batch_api.py`

- [ ] **Step 1: Write the failing API test**

Create `backend/tests/api/test_batch_api.py`:

```python
import json
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.chat import get_provider
from app.availability import service as avail_svc
from app.db.models.batch import DroneLine, TaskPoolItem
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.main import app
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from sqlalchemy import func, select


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.commit()
    return p


def _payload():
    return ChatResult(content=json.dumps({
        "tasks": [{"description": "t", "proof": "honor"} for _ in range(3)],
        "lines": [{"unit": "assignment", "event": "task_drop", "text": "{task}"}
                  for _ in range(4)],
    }))


async def test_generate_requires_llm_online(session, client):
    p = await _profile(session)
    async with client:
        r = await client.post(f"/profile/{p.id}/batch/generate")
    assert r.status_code == 503


async def test_generate_when_online_persists_and_returns_counts(session, client):
    p = await _profile(session)
    await avail_svc.record_heartbeat(session, source="test")  # mark online
    await session.commit()
    app.dependency_overrides[get_provider] = lambda: MockLLMProvider(scripted=[_payload()])
    try:
        async with client:
            r = await client.post(f"/profile/{p.id}/batch/generate")
    finally:
        app.dependency_overrides.pop(get_provider, None)
    assert r.status_code == 200
    body = r.json()
    assert body["tasks_added"] == 3
    assert body["lines_added"] == 4
    count = (await session.execute(
        select(func.count()).select_from(TaskPoolItem).where(TaskPoolItem.profile_id == p.id)
    )).scalar_one()
    assert count == 3


async def test_status_reports_low_pools(session, client):
    p = await _profile(session)
    async with client:
        r = await client.get(f"/profile/{p.id}/batch/status")
    assert r.status_code == 200
    assert r.json()["task_pool_low"] is True


async def test_generate_unknown_profile_404(session, client):
    import uuid

    await avail_svc.record_heartbeat(session, source="test")
    await session.commit()
    app.dependency_overrides[get_provider] = lambda: MockLLMProvider(scripted=[_payload()])
    try:
        async with client:
            r = await client.post(f"/profile/{uuid.uuid4()}/batch/generate")
    finally:
        app.dependency_overrides.pop(get_provider, None)
    assert r.status_code == 404
```

Note: match the project's existing API-test idiom. If other `tests/api/*` files build the `AsyncClient` differently (e.g. a shared fixture, or a different DB-session override), mirror that exact pattern instead of the inline transport above — read one neighbouring file in `tests/api/` first and copy its client/override setup so the live-Postgres session is shared between the request and the assertions.

- [ ] **Step 2: Run the test to verify it fails**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/api/test_batch_api.py -q
```
Expected: FAIL — 404 routes (router not mounted) / `app.api.batch` missing.

- [ ] **Step 3: Create the response schemas**

Create `backend/app/schemas/batch.py`:

```python
from __future__ import annotations

from pydantic import BaseModel


class GenerateBatchOut(BaseModel):
    tasks_added: int
    lines_added: int
    task_pool: int
    line_bank: int


class PoolStatusOut(BaseModel):
    task_pool: int
    line_bank: int
    task_pool_low: bool
    line_bank_low: bool
```

- [ ] **Step 4: Create the router**

Create `backend/app/api/batch.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import get_provider, require_llm_online
from app.batch import service as batch_svc
from app.db.session import get_session
from app.llm.provider import LLMProvider
from app.schemas.batch import GenerateBatchOut, PoolStatusOut
from app.services import profile as profile_svc

router = APIRouter(prefix="/profile", tags=["batch"])


@router.post("/{profile_id}/batch/generate", response_model=GenerateBatchOut)
async def generate_batch(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    provider: LLMProvider = Depends(get_provider),
    _: None = Depends(require_llm_online),
) -> GenerateBatchOut:
    try:
        result = await batch_svc.generate_batch(session, profile_id, provider)
    except (profile_svc.ProfileNotFound, batch_svc.ProfileNotFound):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"profile {profile_id} not found"
        )
    await session.commit()
    return GenerateBatchOut(
        tasks_added=result.tasks_added,
        lines_added=result.lines_added,
        task_pool=result.task_pool,
        line_bank=result.line_bank,
    )


@router.get("/{profile_id}/batch/status", response_model=PoolStatusOut)
async def batch_status(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> PoolStatusOut:
    try:
        await profile_svc.get_profile(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"profile {profile_id} not found"
        )
    s = await batch_svc.pool_status(session, profile_id)
    return PoolStatusOut(
        task_pool=s.task_pool,
        line_bank=s.line_bank,
        task_pool_low=s.task_pool_low,
        line_bank_low=s.line_bank_low,
    )
```

- [ ] **Step 5: Mount the router**

In `backend/app/main.py`, add the import alongside the other `app.api.*` imports:

```python
from app.api.batch import router as batch_router
```

and register it with the other `app.include_router(...)` calls:

```python
app.include_router(batch_router)
```

- [ ] **Step 6: Run the test to verify it passes**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/api/test_batch_api.py -q
```
Expected: PASS (4 passed).

- [ ] **Step 7: Lint**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run ruff check app/api/batch.py app/schemas/batch.py app/main.py
```
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/batch.py backend/app/schemas/batch.py backend/app/main.py backend/tests/api/test_batch_api.py
git commit -m "feat(batch): online-gated generate + pool-status endpoints"
```

---

## Task 8: Full verification

**Files:** none (verification only).

- [ ] **Step 1: Run the whole backend suite**

Run from `backend/`:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest -q
```
Expected: all M1 + M2 + M3 tests green. (Requires the live Postgres `smistress_test` DB.)

- [ ] **Step 2: Lint the whole backend**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run ruff check .
```
Expected: no errors.

- [ ] **Step 3: Confirm the migration is current**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run alembic upgrade head
```
Expected: exits 0; head is `b2c3d4e5f6a7`. (If Postgres is not running locally, this is the CI `backend` job's responsibility — note it and proceed.)

- [ ] **Step 4: Frontend sanity (unchanged contract)**

M3 makes no frontend changes — the offline `StandingOrders` surface renders the new bank-sourced lines, the auto-dropped task, and the batch-window reminder through the unchanged `GET …/standing-orders` contract. Confirm nothing regressed:
```
cd ../frontend; npm run test; npm run build
```
Expected: vitest passes and the build succeeds. (Playwright e2e is the CI `e2e` job's responsibility — do not run it locally per the `smistress-dev-environment` memory.)

- [ ] **Step 5: Push the branch and open the PR; let CI be the authoritative gate**

```bash
git push -u origin feat/offline-3-batch-generation
gh pr create --title "Offline-first M3: batch generation (task pool + drone line bank)" --body "$(cat <<'EOF'
## Summary
Implements Addendum B4 (scoped): the LLM pre-generates a **task pool** and a **drone line bank** through the existing provider seam (online-gated), and the deterministic offline drones serve them with no LLM present.

- New `task_pool_item` + `drone_line` tables (+ migration `b2c3d4e5f6a7`).
- `app/batch`: banding/time-of-day/line-pick helpers, `pool_status`, robust `parse_batch`, top-up `generate_batch`, and `draw_and_assign` (the assignment unit drops a pooled task).
- Drone engine now sources its assignment line from the bank (event × merit band × time-of-day, hardcoded fallback), **auto-drops** the day's task from the pool, and prompts for a **batch window** when a pool runs low.
- `POST /profile/{id}/batch/generate` (503 offline) + `GET /profile/{id}/batch/status`.
- Frontend unchanged: the offline surface renders the new lines/task/reminder through the existing standing-orders contract.

Scope deferred per plan: punishment pool → M4; standing orders → audience milestone; task intensity/discreetness profile → M5; debt stakes → M4.

## Test plan
- `uv run pytest -q` (live Postgres) — all green.
- `uv run ruff check .` — clean.
- `alembic upgrade head` → `b2c3d4e5f6a7`.
- frontend `npm run test` + `npm run build` — green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: branch pushed, PR opened; the three CI jobs (`backend`, `frontend`, `e2e`) run and pass.

---

## Self-Review (run against the spec before executing)

**Spec coverage (Addendum B4, scoped):**
- Task pool — `TaskPoolItem` + generation + `draw_and_assign` ✓ (Tasks 1, 4, 5)
- Drone line bank — `DroneLine` + generation + `pick_line` by event × merit band × time-of-day ✓ (Tasks 1, 3, 4)
- Refill-when-low — `pool_status` + batch-window reminder ✓ (Tasks 3, 6)
- "Drones drop the day's task" (B3 assignment unit) ✓ (Tasks 5, 6)
- Generation via the provider seam, online-gated (B2) ✓ (Tasks 4, 7)
- Graceful degradation / drones always work (B9) — hardcoded fallbacks preserve M2 behavior on an empty bank/pool ✓ (Task 6)
- **Deferred (not bugs):** punishment pool → M4; standing orders → audience milestone; task intensity/discreetness profile → M5; debt stakes → M4. Stated in the plan header.

**Placeholder scan:** every code step contains complete code; commands have expected output. The two implementer notes (hoist `ProfileNotFound`; match the neighbouring API-test client idiom) are explicit, not deferrals.

**Type consistency:** `pick_line(lines, *, event, band, tod, rotation)` used identically in service tests and the drone engine. `GenerateResult(tasks_added, lines_added, task_pool, line_bank)` matches `GenerateBatchOut`. `PoolStatus(task_pool, line_bank, task_pool_low, line_bank_low)` matches `PoolStatusOut`. `draw_and_assign` returns `Task | None`; `standing_orders` consumes it as `Task | None`. `merit_band`/`time_of_day` return the band/tod strings the `DroneLine` columns and `_VALID_*` sets use.

**Branch:** `feat/offline-3-batch-generation`. Local-env caveat (broken PYTHONHOME → clear it before every `uv` call) per the `smistress-dev-environment` memory; Postgres/Playwright gates fall to CI on clean machines.
