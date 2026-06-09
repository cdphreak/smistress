# Offline-First M5a — Supervision Modes (control-depth axis) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the second axis from Addendum B1/B6 — a manually-switched **supervision mode** (full / discreet / task / homeoffice / vacation) with a per-mode free-text "what's possible right now" note, where **vacation freezes the economy** (no task drops, no miss penalties, no debt accrual) and every mode is surfaced to the live Mistress so she binds to it.

**Architecture:** `SubProfile` gains a `supervision_mode` enum column (default `FULL`) and a `supervision_notes` JSONB map (mode → note). A new `app/supervision/service.py` owns reads/writes and the `economy_frozen` predicate (mode == vacation). The loop's miss-sweep and discipline issuance, and the drone's task-drop, consult `economy_frozen` so vacation pauses accrual deterministically (offline-safe, like the existing safety freeze). The persona's authoritative-state block injects the active mode + note so the live Mistress respects it. **Backend-only** (mirrors M3/M4a): the mode is settable via API and read every turn; the mode-switch UI ships in **M5b** alongside the discreetness tagging UI. The **content filter itself** (toy/task/punishment discreetness tags + mode-filtered drawing) is **M5b** — M5a only establishes the axis + vacation freeze + persona awareness.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async (psycopg3), Alembic, Pydantic v2, pytest (live Postgres `smistress_test`), ruff line-length=100. Conventions: **services flush, endpoints commit**; PG enums created via `postgresql.ENUM` in migrations; JSONB for the notes map.

**Scope (locked):** Manual switch only (schedule/calendar deferred per B6). Vacation freeze covers the automatic accrual paths (miss-sweep, fail/miss punishment issuance, offline task drops); a sub-initiated verify-pass during vacation still settles (positive, not frozen). Deferred to **M5b**: discreetness flags on toys, intensity/discreet/required-toy tags on tasks **and punishments**, the mode-filtered task **and punishment** draw, and all M5 frontend (mode switcher + tagging UI). Deferred further: schedule/calendar view.

---

## File Structure

**New (backend/):**
- `app/supervision/__init__.py`, `app/supervision/service.py` — mode/notes reads+writes + `economy_frozen`.
- `app/api/supervision.py` — GET supervision, PUT mode, PUT note.
- `app/schemas/supervision.py` — `SupervisionOut`, `SetModeIn`, `SetNoteIn`.
- `tests/supervision/__init__.py`, `tests/supervision/test_service.py`, `tests/api/test_supervision_api.py`, `tests/supervision/test_vacation_freeze.py`.
- `alembic/versions/e5f6a7b8c9d0_add_supervision_mode.py`.

**Modified (backend/):**
- `app/db/enums.py` — `SupervisionMode`.
- `app/db/models/profile.py` — `SubProfile.supervision_mode` + `supervision_notes`.
- `app/main.py` — mount the supervision router.
- `app/loop/service.py` — vacation freeze in `sweep_missed` + `apply_terminal_discipline`.
- `app/drones/service.py` — skip the task drop + add a paused notice under vacation.
- `app/persona/service.py` — inject the supervision mode + note (+ vacation directive).
- Tests: `tests/drones/test_drone_service.py` (a vacation case), `tests/persona/test_compiler.py` only if it asserts the block shape (it does not — the block is built in `persona/service.py`).

---

## Task 1: `SupervisionMode` enum

**Files:**
- Modify: `backend/app/db/enums.py`
- Test: `backend/tests/supervision/__init__.py`, `backend/tests/supervision/test_service.py` (enum portion)

- [ ] **Step 1: Create the test package marker**

Create `backend/tests/supervision/__init__.py` (empty).

- [ ] **Step 2: Write the failing test**

Create `backend/tests/supervision/test_service.py`:
```python
from app.db.enums import SupervisionMode


def test_supervision_mode_members():
    assert {m.value for m in SupervisionMode} == {
        "full", "discreet", "task", "homeoffice", "vacation"
    }
```

- [ ] **Step 3: Run to verify it fails**

Run (PowerShell; clear env per `smistress-dev-environment`):
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_service.py -q
```
Expected: FAIL — `ImportError: cannot import name 'SupervisionMode'`.

- [ ] **Step 4: Add the enum**

In `backend/app/db/enums.py`, append:
```python
class SupervisionMode(str, enum.Enum):
    """How deeply the sub can be controlled right now (Addendum B6). Set manually;
    binds both the drones and the live Mistress. Vacation freezes the economy."""

    FULL = "full"  # fully available, at her mercy anytime
    DISCREET = "discreet"  # family/kids around: only quiet, discreet content
    TASK = "task"  # only tasks with graceful fulfillment timers
    HOMEOFFICE = "homeoffice"  # working/meetings: discreetly-usable content only
    VACATION = "vacation"  # training paused; economy frozen
```

- [ ] **Step 5: Run to verify it passes, lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_service.py -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/db/enums.py tests/supervision/
```
```bash
git add backend/app/db/enums.py backend/tests/supervision/__init__.py backend/tests/supervision/test_service.py
git commit -m "feat(supervision): SupervisionMode enum"
```

---

## Task 2: Profile columns + migration

**Files:**
- Modify: `backend/app/db/models/profile.py`
- Create: `backend/alembic/versions/e5f6a7b8c9d0_add_supervision_mode.py`
- Test: `backend/tests/db/test_profile_models.py` (add a case) — if that file doesn't exist, add the case to `backend/tests/supervision/test_service.py` instead.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/supervision/test_service.py`:
```python
from app.db.enums import SupervisionMode as _SM
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def test_profile_defaults_to_full_supervision(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await session.refresh(p)
    assert p.supervision_mode is _SM.FULL
    assert p.supervision_notes == {}
```

- [ ] **Step 2: Run to verify it fails**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_service.py::test_profile_defaults_to_full_supervision -q
```
Expected: FAIL — `AttributeError: ... 'supervision_mode'`.

- [ ] **Step 3: Add the columns**

In `backend/app/db/models/profile.py`, on `SubProfile` (the file already imports `Enum`, `JSONB`, `Mapped`, `mapped_column`; add `from app.db.enums import GoalStatus, KinkRating, SupervisionMode` — extend the existing enums import), add after `aftercare_prefs`:
```python
    supervision_mode: Mapped[SupervisionMode] = mapped_column(
        Enum(SupervisionMode, name="supervision_mode"), default=SupervisionMode.FULL
    )
    supervision_notes: Mapped[dict] = mapped_column(JSONB, default=dict)  # mode -> note
```

- [ ] **Step 4: Write the migration**

Head is `d4e5f6a7b8c9`. The `supervision_mode` enum is new — let Alembic create it (`postgresql.ENUM` WITHOUT `create_type=False`).

Create `backend/alembic/versions/e5f6a7b8c9d0_add_supervision_mode.py`:
```python
"""add supervision mode + notes

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-09 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    mode = postgresql.ENUM(
        'FULL', 'DISCREET', 'TASK', 'HOMEOFFICE', 'VACATION', name='supervision_mode'
    )
    mode.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'sub_profile',
        sa.Column('supervision_mode', mode, server_default='FULL', nullable=False),
    )
    op.add_column(
        'sub_profile',
        sa.Column(
            'supervision_notes', postgresql.JSONB(astext_type=sa.Text()),
            server_default='{}', nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sub_profile', 'supervision_notes')
    op.drop_column('sub_profile', 'supervision_mode')
    op.execute('DROP TYPE supervision_mode')
```

- [ ] **Step 5: Round-trip the migration**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic downgrade -1
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
```
Expected: each exits 0; upgrade logs `d4e5f6a7b8c9 -> e5f6a7b8c9d0`. (Defer to CI if Postgres is down.)

- [ ] **Step 6: Run the test (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_service.py -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/db/models/profile.py
```
```bash
git add backend/app/db/models/profile.py backend/alembic/versions/e5f6a7b8c9d0_add_supervision_mode.py backend/tests/supervision/test_service.py
git commit -m "feat(supervision): SubProfile.supervision_mode + notes + migration"
```

---

## Task 3: Supervision service

**Files:**
- Create: `backend/app/supervision/__init__.py`, `backend/app/supervision/service.py`
- Test: `backend/tests/supervision/test_service.py` (add cases)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/supervision/test_service.py`:
```python
from app.supervision import service as sup_svc


async def test_set_mode_and_economy_frozen(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    assert await sup_svc.economy_frozen(session, p.id) is False
    await sup_svc.set_mode(session, p.id, _SM.VACATION)
    assert (await sup_svc.get_mode(session, p.id)) is _SM.VACATION
    assert await sup_svc.economy_frozen(session, p.id) is True


async def test_set_note_per_mode(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await sup_svc.set_note(session, p.id, _SM.HOMEOFFICE, "back-to-back meetings until 5")
    notes = await sup_svc.get_notes(session, p.id)
    assert notes["homeoffice"] == "back-to-back meetings until 5"
    # setting another mode's note does not clobber the first
    await sup_svc.set_note(session, p.id, _SM.DISCREET, "kids home")
    notes = await sup_svc.get_notes(session, p.id)
    assert notes["homeoffice"] == "back-to-back meetings until 5"
    assert notes["discreet"] == "kids home"
```

- [ ] **Step 2: Run to verify it fails**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_service.py -q
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.supervision'`.

- [ ] **Step 3: Create the service**

Create `backend/app/supervision/__init__.py` (empty).

Create `backend/app/supervision/service.py`:
```python
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db.enums import SupervisionMode
from app.db.models.profile import SubProfile
from app.services import profile as profile_svc


async def get_mode(session: AsyncSession, profile_id: uuid.UUID) -> SupervisionMode:
    profile = await profile_svc.get_profile(session, profile_id)  # raises ProfileNotFound
    return profile.supervision_mode


async def get_notes(session: AsyncSession, profile_id: uuid.UUID) -> dict[str, str]:
    profile = await profile_svc.get_profile(session, profile_id)
    return dict(profile.supervision_notes or {})


async def set_mode(
    session: AsyncSession, profile_id: uuid.UUID, mode: SupervisionMode
) -> SubProfile:
    """Set the supervision mode. Honored immediately (read every turn); no merit
    penalty — lowering control depth / entering vacation is a consent control
    (spec 9). Caller commits."""
    profile = await profile_svc.get_profile(session, profile_id)
    profile.supervision_mode = mode
    await session.flush()
    return profile


async def set_note(
    session: AsyncSession, profile_id: uuid.UUID, mode: SupervisionMode, note: str
) -> SubProfile:
    """Set the free-text 'what's possible right now' note for one mode. Caller commits."""
    profile = await profile_svc.get_profile(session, profile_id)
    notes = dict(profile.supervision_notes or {})
    notes[mode.value] = note
    profile.supervision_notes = notes
    flag_modified(profile, "supervision_notes")  # JSONB dict reassignment -> mark dirty
    await session.flush()
    return profile


async def economy_frozen(session: AsyncSession, profile_id: uuid.UUID) -> bool:
    """Vacation freezes the economy (Addendum B6): no task drops, no miss
    penalties, no debt accrual while active."""
    return (await get_mode(session, profile_id)) is SupervisionMode.VACATION
```

- [ ] **Step 4: Run (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_service.py -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/supervision/
```
```bash
git add backend/app/supervision/__init__.py backend/app/supervision/service.py backend/tests/supervision/test_service.py
git commit -m "feat(supervision): mode/notes service + economy_frozen predicate"
```

---

## Task 4: Supervision API

**Files:**
- Create: `backend/app/api/supervision.py`, `backend/app/schemas/supervision.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_supervision_api.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/api/test_supervision_api.py` (mirrors `tests/api/test_economy_api.py`'s client fixture):
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
        "/onboarding/profile", json={"is_adult": True, "consent_acknowledged": True}
    )
    return r.json()["id"]


async def test_supervision_defaults_to_full(client):
    pid = await _new_profile(client)
    r = await client.get(f"/profile/{pid}/supervision")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "full"
    assert body["notes"] == {}


async def test_set_mode_and_note(client):
    pid = await _new_profile(client)
    r = await client.put(f"/profile/{pid}/supervision/mode", json={"mode": "vacation"})
    assert r.status_code == 200 and r.json()["mode"] == "vacation"
    r = await client.put(
        f"/profile/{pid}/supervision/note",
        json={"mode": "homeoffice", "note": "meetings till 5"},
    )
    assert r.status_code == 200
    assert r.json()["notes"]["homeoffice"] == "meetings till 5"


async def test_set_mode_rejects_unknown(client):
    pid = await _new_profile(client)
    r = await client.put(f"/profile/{pid}/supervision/mode", json={"mode": "nonsense"})
    assert r.status_code == 422


async def test_supervision_404(client):
    r = await client.get(f"/profile/{uuid.uuid4()}/supervision")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify it fails (routes 404 / module missing).**

- [ ] **Step 3: Create the schemas**

Create `backend/app/schemas/supervision.py`:
```python
from __future__ import annotations

from app.db.enums import SupervisionMode
from pydantic import BaseModel


class SupervisionOut(BaseModel):
    mode: SupervisionMode
    notes: dict[str, str]


class SetModeIn(BaseModel):
    mode: SupervisionMode


class SetNoteIn(BaseModel):
    mode: SupervisionMode
    note: str = ""
```

- [ ] **Step 4: Create the router**

Create `backend/app/api/supervision.py`:
```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.supervision import SetModeIn, SetNoteIn, SupervisionOut
from app.services import profile as profile_svc
from app.supervision import service as sup_svc

router = APIRouter(prefix="/profile", tags=["supervision"])


def _not_found(profile_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"profile {profile_id} not found"
    )


async def _out(session: AsyncSession, profile_id: uuid.UUID) -> SupervisionOut:
    mode = await sup_svc.get_mode(session, profile_id)
    notes = await sup_svc.get_notes(session, profile_id)
    return SupervisionOut(mode=mode, notes=notes)


@router.get("/{profile_id}/supervision", response_model=SupervisionOut)
async def get_supervision(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> SupervisionOut:
    try:
        return await _out(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)


@router.put("/{profile_id}/supervision/mode", response_model=SupervisionOut)
async def set_mode(
    profile_id: uuid.UUID, body: SetModeIn, session: AsyncSession = Depends(get_session)
) -> SupervisionOut:
    try:
        await sup_svc.set_mode(session, profile_id, body.mode)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return await _out(session, profile_id)


@router.put("/{profile_id}/supervision/note", response_model=SupervisionOut)
async def set_note(
    profile_id: uuid.UUID, body: SetNoteIn, session: AsyncSession = Depends(get_session)
) -> SupervisionOut:
    try:
        await sup_svc.set_note(session, profile_id, body.mode, body.note)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return await _out(session, profile_id)
```

- [ ] **Step 5: Mount the router**

In `backend/app/main.py`, add `from app.api.supervision import router as supervision_router` with the other router imports and `app.include_router(supervision_router)` with the others.

- [ ] **Step 6: Run (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/api/test_supervision_api.py -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/api/supervision.py app/schemas/supervision.py app/main.py
```
```bash
git add backend/app/api/supervision.py backend/app/schemas/supervision.py backend/app/main.py backend/tests/api/test_supervision_api.py
git commit -m "feat(supervision): GET/PUT mode + note API"
```

---

## Task 5: Vacation freeze wiring (loop + drones)

**Files:**
- Modify: `backend/app/loop/service.py`, `backend/app/drones/service.py`
- Test: `backend/tests/supervision/test_vacation_freeze.py`, `backend/tests/drones/test_drone_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/supervision/test_vacation_freeze.py`:
```python
from datetime import datetime, timedelta, timezone

from app.db.enums import ProofRequirement, SupervisionMode, TaskStatus
from app.db.models.batch import PunishmentPoolItem
from app.db.models.punishment import Punishment
from app.loop import service as loop_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from app.supervision import service as sup_svc
from sqlalchemy import func, select


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_vacation_freezes_miss_sweep(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.VACATION)
    task = await loop_svc.assign_task(
        session, p.id, description="drill", proof_requirement=ProofRequirement.HONOR,
        deadline=datetime.now(timezone.utc) - timedelta(hours=1), merit_miss_penalty=5,
    )
    await loop_svc.sweep_missed(session, p.id)
    assert task.status is TaskStatus.ASSIGNED  # not missed — frozen


async def test_vacation_blocks_punishment_issuance_on_fail(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.VACATION)
    task = await loop_svc.assign_task(
        session, p.id, description="drill", proof_requirement=ProofRequirement.HONOR,
    )
    task.status = TaskStatus.VERIFIED_FAIL
    await session.flush()
    await loop_svc.apply_terminal_discipline(session, task)
    count = (await session.execute(
        select(func.count()).select_from(Punishment).where(Punishment.profile_id == p.id)
    )).scalar_one()
    assert count == 0  # no debt accrual under vacation
```

Append to `backend/tests/drones/test_drone_service.py`:
```python
async def test_vacation_blocks_task_drop_and_shows_paused(session):
    from app.db.models.batch import TaskPoolItem
    from app.db.models.task import Task as TaskModel
    from app.db.enums import SupervisionMode
    from app.supervision import service as sup_svc
    from sqlalchemy import func, select

    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.VACATION)
    session.add(TaskPoolItem(
        profile_id=p.id, description="Drawn drill", proof_requirement=ProofRequirement.HONOR,
    ))
    await session.flush()
    notices = await drone_svc.standing_orders(session, p.id)
    # no task was drawn
    tasks = (await session.execute(
        select(func.count()).select_from(TaskModel).where(TaskModel.profile_id == p.id)
    )).scalar_one()
    assert tasks == 0
    assert any("paused" in n.line.lower() for n in notices)
```

- [ ] **Step 2: Run to verify they fail**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/test_vacation_freeze.py tests/drones/test_drone_service.py::test_vacation_blocks_task_drop_and_shows_paused -q
```
Expected: FAIL (the task is missed / a punishment is issued / a task is drawn).

- [ ] **Step 3: Freeze the loop under vacation**

In `backend/app/loop/service.py`:
(a) Add the import: `from app.supervision import service as sup_svc`.
(b) In `sweep_missed`, the per-task guard currently reads:
```python
        if await safety_svc.is_frozen(session, task.profile_id):
            continue  # halted by safeword or on hiatus -> no miss, no penalty (spec 9)
```
Change the condition to also skip under vacation:
```python
        if await safety_svc.is_frozen(session, task.profile_id) or await sup_svc.economy_frozen(
            session, task.profile_id
        ):
            continue  # safeword/hiatus/vacation -> no miss, no penalty (spec 9 / B6)
```
(c) In `apply_terminal_discipline`, guard the FAIL/MISS issuance branch so no debt accrues under vacation:
```python
    elif task.status in (TaskStatus.VERIFIED_FAIL, TaskStatus.MISSED):
        if await sup_svc.economy_frozen(session, task.profile_id):
            return  # vacation freezes debt accrual (B6)
        severity = 2 if task.status is TaskStatus.VERIFIED_FAIL else 1
        await disc_svc.draw_and_issue(
            session, task.profile_id, severity=severity,
            reason_prefix=f"{task.status.value}: ",
        )
```
(The PASS/settle branch is unaffected — a sub-initiated penance serve still settles under vacation.)

- [ ] **Step 4: Skip the task drop + add a paused notice in the drones**

In `backend/app/drones/service.py`:
(a) Add the import: `from app.supervision import service as sup_svc`.
(b) In `standing_orders`, gate the task drop on the freeze, and surface a paused notice. Replace:
```python
    task = await _active_task(session, profile_id)
    if task is None:
        # The assignment unit drops the day's task from the pool (if any).
        task = await batch_svc.draw_and_assign(session, profile_id)
```
with:
```python
    frozen = await sup_svc.economy_frozen(session, profile_id)
    task = await _active_task(session, profile_id)
    if task is None and not frozen:
        # The assignment unit drops the day's task from the pool (if any).
        task = await batch_svc.draw_and_assign(session, profile_id)
```
(c) At the very end of `standing_orders`, before `return notices`, when frozen prepend a paused notice and skip the batch-window prompt. Wrap the existing `status = await batch_svc.pool_status(...)` / batch-window block so it only runs when not frozen, and add the paused notice:
```python
    if frozen:
        notices.append(DroneNotice(
            unit="reminder",
            line="Training is paused (vacation). Rest — nothing counts against you.",
        ))
        return notices

    status = await batch_svc.pool_status(session, profile_id)
    if status.task_pool_low or status.line_bank_low or status.punishment_pool_low:
        notices.append(DroneNotice(...))  # existing batch_window block, unchanged
    return notices
```
(Keep the existing batch-window block body exactly; only guard it behind the `if frozen: ... return` early-out. The discipline-unit notices block stays as-is above this — under vacation the debt ledger still reflects reality, which is fine to show.)

- [ ] **Step 5: Run the suites (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/supervision/ tests/drones/ tests/loop/ -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/loop/service.py app/drones/service.py tests/supervision/
```
Expected: all pass; the existing drone draw/assignment tests still pass (they run in the default FULL mode, so `frozen` is False).
```bash
git add backend/app/loop/service.py backend/app/drones/service.py backend/tests/supervision/test_vacation_freeze.py backend/tests/drones/test_drone_service.py
git commit -m "feat(supervision): vacation freezes miss-sweep, issuance, and task drops"
```

---

## Task 6: Persona injects the supervision mode + note

**Files:**
- Modify: `backend/app/persona/service.py`
- Test: `backend/tests/persona/test_state_block.py` (new) — or add to an existing persona test module if one targets `build_authoritative_state_block`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/persona/test_state_block.py`:
```python
from app.db.enums import SupervisionMode
from app.persona import service as persona_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from app.supervision import service as sup_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_state_block_shows_supervision_mode_and_note(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.HOMEOFFICE)
    await sup_svc.set_note(session, p.id, SupervisionMode.HOMEOFFICE, "meetings till 5")
    block = await persona_svc.build_authoritative_state_block(session, p.id)
    assert "SUPERVISION: homeoffice" in block
    assert "meetings till 5" in block


async def test_state_block_vacation_directive(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.VACATION)
    block = await persona_svc.build_authoritative_state_block(session, p.id)
    assert "vacation" in block.lower()
    assert "paused" in block.lower()
```

- [ ] **Step 2: Run to verify it fails**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/persona/test_state_block.py -q
```
Expected: FAIL — no SUPERVISION line in the block.

- [ ] **Step 3: Inject the mode + note**

In `backend/app/persona/service.py` `build_authoritative_state_block`:
(a) The function opens with a discarded 404 guard `await profile_svc.get_profile(session, profile_id)`. Capture it: `profile = await profile_svc.get_profile(session, profile_id)`.
(b) After the `CHASTITY` line in the `lines = [...]` list, add a supervision line + optional note:
```python
        f"SUPERVISION: {profile.supervision_mode.value}",
    ]
    _sup_note = (profile.supervision_notes or {}).get(profile.supervision_mode.value, "").strip()
    if _sup_note:
        lines.append(f"WHAT'S POSSIBLE NOW: {_sup_note}")
```
(Restructure cleanly: append the `SUPERVISION:` line inside the list, then conditionally append the note after the list is built — match the file's existing style of appending to `lines`.)
(c) Near the bottom where halt/hiatus directives are `lines.insert(0, ...)`, add a vacation directive in the same place:
```python
    if profile.supervision_mode is SupervisionMode.VACATION:
        lines.insert(0, "VACATION — training is paused; assign nothing and apply no pressure.")
```
(Add `from app.db.enums import ... SupervisionMode` to the imports — extend the existing `from app.db.enums import KinkRating, TaskStatus` line.)

- [ ] **Step 4: Run (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/persona/ -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/persona/service.py tests/persona/test_state_block.py
```
```bash
git add backend/app/persona/service.py backend/tests/persona/test_state_block.py
git commit -m "feat(persona): inject supervision mode + 'what's possible' note (vacation directive)"
```

---

## Task 7: Full verification

**Files:** none.

- [ ] **Step 1: Whole backend suite + ruff + migration head**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check .
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
```
Expected: all green; ruff clean; head `e5f6a7b8c9d0`.

- [ ] **Step 2: Frontend sanity (unchanged contract)**

M5a adds new endpoints but changes no existing API shape, so the frontend is untouched. Confirm no regression:
```
npm --prefix frontend run test
npm --prefix frontend run build
```
Expected: green.

- [ ] **Step 3: Push + PR**

```bash
git push -u origin feat/offline-5a-supervision-modes-core
gh pr create --title "Offline-first M5a: supervision modes (control-depth axis)" --body "$(cat <<'EOF'
## Summary
Adds the second axis from Addendum B1/B6 — a manually-switched **supervision mode** with vacation economy-freeze.

- `SupervisionMode` enum (full/discreet/task/homeoffice/vacation); `SubProfile.supervision_mode` + `supervision_notes` (per-mode 'what's possible' note); migration `e5f6a7b8c9d0`.
- `app/supervision/service.py`: mode/notes reads+writes + `economy_frozen` (mode == vacation).
- `GET /profile/{id}/supervision`, `PUT .../mode`, `PUT .../note`.
- **Vacation freezes the economy**: the miss-sweep, fail/miss punishment issuance, and offline task drops all skip under vacation; the drone surfaces a 'training paused' notice. (A sub-initiated penance serve still settles.)
- The persona's authoritative-state block injects the active mode + note (+ a vacation directive) so the live Mistress binds to it.

Backend-only (mirrors M3/M4a): the mode is settable via API and read every turn. Deferred to **M5b**: the discreetness content filter (toy flags, task + punishment tags, mode-filtered drawing) and all M5 frontend (mode switcher + tagging UI). Schedule/calendar deferred further.

## Test plan
- [x] `uv run pytest -q` (live Postgres) — green
- [x] `uv run ruff check .` — clean
- [x] `alembic upgrade head` → `e5f6a7b8c9d0` (round-trip verified)
- [x] frontend `npm run test` + `npm run build` — green
- [ ] CI backend / frontend / e2e green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review (against the spec, before executing)

**Spec coverage (Addendum B1/B6, M5a scope):**
- Five supervision modes, set manually ✓ (Tasks 1, 2, 4)
- Per-mode free-text "what's possible right now" note the sub writes ✓ (Tasks 2, 3, 4) + surfaced to the live Mistress (Task 6)
- Vacation freezes the economy — no task drops, no miss penalties, no debt accrual ✓ (Task 5)
- Mode is a consent control honored immediately, no merit penalty — setting it is a plain column write read every turn; no economy effect applied ✓ (Task 3)
- Mode binds the live Mistress (B1 "binds her too") — injected into the authoritative-state block ✓ (Task 6)
- **Deferred (stated):** the deterministic content filter (toy/task/punishment discreetness tags + mode-filtered drawing) and all UI → **M5b**; schedule/calendar → later.

**Placeholder scan:** new code is complete; the drone Step 4(c) keeps the existing batch-window block verbatim behind a `if frozen: return` early-out (a located edit, not a placeholder). Task 6 Steps 3a–3c are exact edits naming the lines to add.

**Type consistency:** `economy_frozen(session, profile_id) -> bool` is used identically in `sweep_missed`, `apply_terminal_discipline`, and the drone. `get_mode -> SupervisionMode`, `get_notes -> dict[str,str]`, `set_mode(mode)`, `set_note(mode, note)` match the API + tests. `SupervisionOut(mode, notes)` / `SetModeIn(mode)` / `SetNoteIn(mode, note)` match the endpoints. `SubProfile.supervision_mode` / `supervision_notes` match the model, migration, service, and persona injection.

**Branch:** `feat/offline-5a-supervision-modes-core`. Local-env caveat (clear PYTHONHOME; Postgres up) per `smistress-dev-environment`; Playwright/CI gates fall to CI.
