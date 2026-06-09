# Offline-First M4a — Chastity Time + the Debt Ledger (economy core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the old denial timer into a single per-profile **Chastity Time** countdown and introduce the three-quantity economy's **debt** dimension — a persistent debt balance plus a **punishment ledger** whose entries (penance task / chastity extension / token confiscation) accrue debt on a miss/fail and settle by serving penance (through the existing task loop) or a punishing token buy-down.

**Architecture:** `DenialTimer` (plural, per-event) becomes `ChastityTimer` (one row per profile: a release time, or "not locked"; extensions push the release out, only she lifts it). `EconomyState` gains a non-negative `debt` balance. A new `Punishment` ledger records issued consequences. A new **`app/discipline/service.py`** owns issuance + penance settlement: it imports `economy` + models and creates penance `Task`s directly, so the `loop` can call *into* it at terminal task points without an import cycle (discipline never imports loop). This milestone is **backend-only**; the dossier/safeword API keep their existing field shapes (e.g. `denial_timers`, `denial_lifted`) as compatibility-preserving computed values, and `debt`/chastity detail are added as *additive* fields — the user-facing relabel and debt/discipline UI land in **M4b** alongside the punishment pool and discipline drone unit.

**Scope (locked):** Three punishment types — **penance task** (covers lines/writing as content), **chastity extension**, **token confiscation**. Penance is served through the existing submit-proof → verify loop (on `VERIFIED_PASS` the linked punishment settles: debt cleared + a small merit recovery for an honest, on-time serve). Debt is also clearable by **token buy-down** at a punishing rate (no merit). Deferred to **M4b**: the generated punishment pool (3rd batch artifact) + deterministic fallback selection, the **discipline drone unit** in `standing_orders`, and the dossier/offline **UI** surfacing of debt + chastity. Deferred to a later milestone: the **privilege-lock** punishment type (no consumer until audiences/comforts exist).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async (psycopg3), Alembic, Pydantic v2, pytest (asyncio_mode=auto, live Postgres `smistress_test`), ruff line-length=100. Conventions: **services flush, endpoints commit**; PG enums referenced with `postgresql.ENUM(create_type=False)` in migrations.

---

## File Structure

**New (backend/):**
- `app/db/models/economy.py` — `ChastityTimer` replaces `DenialTimer`; `EconomyState` gains `debt`. (modify)
- `app/db/models/punishment.py` — `Punishment` ledger model.
- `alembic/versions/c3d4e5f6a7b8_chastity_debt_punishment.py` — one migration: drop `denial_timer`, create `chastity_timer`, add `economy_state.debt`, create `punishment` (+ its PG enums).
- `app/discipline/__init__.py`, `app/discipline/service.py` — `issue_punishment`, `settle_penance` (the discipline unit's mechanics).
- `tests/discipline/__init__.py`, `tests/discipline/test_service.py`.

**Modified (backend/):**
- `app/db/enums.py` — `PunishmentType`, `PunishmentStatus`.
- `app/config.py` — severity → debt/chastity-hours/confiscation maps; buy-down rate; penance merit recovery.
- `app/db/models/__init__.py` — register `ChastityTimer`, `Punishment`; drop `DenialTimer`.
- `app/economy/service.py` — chastity ops (replace denial fns); `adjust_debt`; `buy_down_debt`.
- `app/loop/service.py` — call discipline at fail/miss (issue) and pass (settle penance).
- `app/safety/service.py` — safeword lifts chastity (keeps `denial_lifted` int as a compat count).
- `app/persona/service.py`, `app/persona/compiler.py` — state block + tool copy: chastity + debt.
- `app/chat/service.py` (dossier), `app/chat/tools.py` (`set_chastity`).
- `app/drones/service.py` — reminder unit reads chastity status, not the old timer list.
- `app/api/economy.py`, `app/schemas/economy.py` — chastity endpoints, `debt` in standing, buy-down endpoint.
- `app/services/profile.py` — delete cascade: `ChastityTimer` + `Punishment`.
- Tests: `tests/economy/test_denial_timers.py` → chastity; `tests/db/test_economy_models.py`; `tests/chat/test_tools.py`, `tests/chat/test_chat_service.py`; `tests/safety/test_service.py`; `tests/persona/test_compiler.py`; `tests/drones/test_drone_service.py`; `tests/api/test_economy_api.py`.

---

## Task 1: Enums + config constants

**Files:**
- Modify: `backend/app/db/enums.py`, `backend/app/config.py`
- Test: `backend/tests/discipline/__init__.py`, `backend/tests/discipline/test_service.py` (constants portion)

- [ ] **Step 1: Create the test package marker**

Create `backend/tests/discipline/__init__.py` (empty).

- [ ] **Step 2: Write the failing test**

Create `backend/tests/discipline/test_service.py`:

```python
from app.config import Settings
from app.db.enums import PunishmentStatus, PunishmentType


def test_punishment_enums_have_expected_members():
    assert {t.value for t in PunishmentType} == {
        "penance_task", "chastity_extension", "token_confiscation"
    }
    assert {s.value for s in PunishmentStatus} == {
        "issued", "served", "bought_down", "expired"
    }


def test_severity_maps_cover_1_to_3():
    s = Settings()
    for sev in (1, 2, 3):
        assert sev in s.debt_by_severity
        assert sev in s.chastity_hours_by_severity
        assert sev in s.confiscation_by_severity
    assert s.buydown_tokens_per_debt >= 1
    assert s.penance_merit_recovery >= 0
```

- [ ] **Step 3: Run it to verify it fails**

Run (PowerShell, clear the broken env per `smistress-dev-environment`; Postgres is required for the suite but these two tests are pure):
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/discipline/test_service.py -q
```
Expected: FAIL — `ImportError: cannot import name 'PunishmentType'`.

- [ ] **Step 4: Add the enums**

In `backend/app/db/enums.py`, append:

```python
class PunishmentType(str, enum.Enum):
    """A discipline-unit consequence (Addendum B7). Three types with live effects;
    privilege-lock is deferred until audiences/comforts exist."""

    PENANCE_TASK = "penance_task"  # a punitive Task (also covers lines/writing)
    CHASTITY_EXTENSION = "chastity_extension"  # pushes the chastity release out
    TOKEN_CONFISCATION = "token_confiscation"  # removes tokens from the purse


class PunishmentStatus(str, enum.Enum):
    ISSUED = "issued"  # debt accrued, awaiting penance
    SERVED = "served"  # penance completed (debt cleared via the task loop)
    BOUGHT_DOWN = "bought_down"  # cleared by spending tokens (no merit)
    EXPIRED = "expired"  # reserved for a future sweep; unused in M4a
```

- [ ] **Step 5: Add config constants**

In `backend/app/config.py`, add these fields after `batch_line_low` (use `Field(default_factory=...)` for the dict defaults so the mutable default is per-instance):

```python
    # Debt / punishment tuning (Addendum B7). Severity 1 (light) .. 3 (heavy).
    debt_by_severity: dict[int, int] = Field(
        default_factory=lambda: {1: 5, 2: 15, 3: 40}
    )
    chastity_hours_by_severity: dict[int, int] = Field(
        default_factory=lambda: {1: 12, 2: 24, 3: 72}
    )
    confiscation_by_severity: dict[int, int] = Field(
        default_factory=lambda: {1: 5, 2: 15, 3: 40}
    )
    buydown_tokens_per_debt: int = 3  # punishing: 3 tokens clears 1 debt point, no merit
    penance_merit_recovery: int = 3  # small recovery for an honest, on-time penance serve
```

Add the import at the top of `config.py` if not present: change `from pydantic_settings import BaseSettings, SettingsConfigDict` to also import `Field` from pydantic:
```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
```

- [ ] **Step 6: Run it to verify it passes**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/discipline/test_service.py -q
```
Expected: PASS (2 passed).

- [ ] **Step 7: Lint + commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/db/enums.py app/config.py tests/discipline/
```
```bash
git add backend/app/db/enums.py backend/app/config.py backend/tests/discipline/__init__.py backend/tests/discipline/test_service.py
git commit -m "feat(discipline): punishment enums + debt/chastity tuning constants"
```

---

## Task 2: Models — `ChastityTimer` (single), `EconomyState.debt`, `Punishment`

**Files:**
- Modify: `backend/app/db/models/economy.py`, `backend/app/db/models/__init__.py`, `backend/app/services/profile.py`
- Create: `backend/app/db/models/punishment.py`
- Test: `backend/tests/db/test_economy_models.py` (add cases)

- [ ] **Step 1: Write the failing model tests**

Append to `backend/tests/db/test_economy_models.py` (keep existing tests; if any reference `DenialTimer`, they are replaced in Task 10 — do not worry about them failing yet):

```python
async def test_chastity_timer_is_single_per_profile(session):
    from datetime import datetime, timedelta, timezone

    from app.db.models.chastity import ChastityTimer  # noqa: F401 (see import note)
    from app.db.models.economy import ChastityTimer
    from app.schemas.onboarding import ProfileCreate
    from app.services import profile as profile_svc

    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    ends = datetime.now(timezone.utc) + timedelta(hours=8)
    timer = ChastityTimer(profile_id=p.id, ends_at=ends, note="overnight")
    session.add(timer)
    await session.flush()
    await session.refresh(timer)
    assert timer.ends_at == ends
    assert timer.note == "overnight"


async def test_economy_state_has_debt_defaulting_zero(session):
    from app.db.models.economy import EconomyState
    from app.schemas.onboarding import ProfileCreate
    from app.services import profile as profile_svc

    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    econ = (await session.execute(
        __import__("sqlalchemy").select(EconomyState).where(EconomyState.profile_id == p.id)
    )).scalar_one()
    assert econ.debt == 0


async def test_punishment_round_trip(session):
    from app.db.enums import PunishmentStatus, PunishmentType
    from app.db.models.punishment import Punishment
    from app.schemas.onboarding import ProfileCreate
    from app.services import profile as profile_svc

    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    pun = Punishment(
        profile_id=p.id, type=PunishmentType.CHASTITY_EXTENSION, severity=2,
        reason="missed posture drill", debt_amount=15, status=PunishmentStatus.ISSUED,
    )
    session.add(pun)
    await session.flush()
    await session.refresh(pun)
    assert pun.status is PunishmentStatus.ISSUED
    assert pun.penance_task_id is None
    assert pun.resolved_at is None
```

> Import note: delete the stray `from app.db.models.chastity import ChastityTimer` line above — `ChastityTimer` lives in `app/db/models/economy.py`. (It was a thinking artifact; keep only the `from app.db.models.economy import ChastityTimer` import.)

- [ ] **Step 2: Run to verify it fails**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/db/test_economy_models.py -q
```
Expected: FAIL — `ImportError`/`AttributeError` (no `ChastityTimer`, no `debt`, no `Punishment`).

- [ ] **Step 3: Replace `DenialTimer` with `ChastityTimer` and add `debt`**

In `backend/app/db/models/economy.py`, **replace the entire `DenialTimer` class** with `ChastityTimer`, and add `debt` to `EconomyState`. The file becomes:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.profile import SubProfile


class EconomyState(Base):
    """One per profile. The three quantities (Addendum B7): merit (standing),
    tokens (reward purse), and debt (owed penance). Merit also drives disposition."""

    __tablename__ = "economy_state"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sub_profile.id"), unique=True
    )
    merit: Mapped[int] = mapped_column(default=0)
    rank: Mapped[str] = mapped_column(String, default="novice")
    tokens: Mapped[int] = mapped_column(default=0)
    debt: Mapped[int] = mapped_column(default=0)  # owed penance; never negative

    profile: Mapped[SubProfile] = relationship()


class ChastityTimer(Base):
    """A single per-profile chastity countdown (Addendum B7, generalizing the old
    denial timer). ``ends_at`` is the scheduled release; None means not locked.
    Locked iff ends_at is set and in the future; extensions push it out; only she
    lifts it early (serving penance never shortens it)."""

    __tablename__ = "chastity_timer"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sub_profile.id"), unique=True
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    note: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    profile: Mapped[SubProfile] = relationship()
```

- [ ] **Step 4: Create the `Punishment` ledger model**

Create `backend/app/db/models/punishment.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import PunishmentStatus, PunishmentType
from app.db.models.profile import SubProfile


class Punishment(Base):
    """A debt-ledger line item (Addendum B7). Issued on a miss/fail; adds
    ``debt_amount`` to the economy's debt balance; cleared by serving penance
    (a linked Task verified PASS) or a token buy-down."""

    __tablename__ = "punishment"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))

    type: Mapped[PunishmentType] = mapped_column(Enum(PunishmentType, name="punishment_type"))
    severity: Mapped[int] = mapped_column(default=1)  # 1 (light) .. 3 (heavy)
    reason: Mapped[str] = mapped_column(String, default="")
    debt_amount: Mapped[int] = mapped_column(default=0)
    status: Mapped[PunishmentStatus] = mapped_column(
        Enum(PunishmentStatus, name="punishment_status"), default=PunishmentStatus.ISSUED
    )
    # Set when type is PENANCE_TASK — the Task whose PASS settles this punishment.
    penance_task_id: Mapped[uuid.UUID | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    profile: Mapped[SubProfile] = relationship()
```

- [ ] **Step 5: Register models; drop the old `DenialTimer` reference**

In `backend/app/db/models/__init__.py`, change the economy import line and add punishment:
```python
from app.db.models.economy import ChastityTimer, EconomyState  # noqa: F401
from app.db.models.punishment import Punishment  # noqa: F401
```
(Remove `DenialTimer` from that import.)

- [ ] **Step 6: Update the profile delete cascade**

In `backend/app/services/profile.py`, the `delete_profile` function deletes a list of models including `DenialTimer`. Update the import and the delete list: replace `DenialTimer` with `ChastityTimer` and add `Punishment`. Concretely, change the import line `from app.db.models.economy import DenialTimer, EconomyState` to `from app.db.models.economy import ChastityTimer, EconomyState` and add `from app.db.models.punishment import Punishment`; then in the deletion sequence replace `DenialTimer` with `ChastityTimer` and add `Punishment` to the same batch of per-profile deletes (alongside `EconomyState`). Read the function first to place these exactly; `Punishment` and `ChastityTimer` both FK only to `sub_profile.id`, so they delete in the same phase as `EconomyState`.

- [ ] **Step 7: Run the model tests to verify they pass**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/db/test_economy_models.py -q
```
Expected: the three new tests PASS. (Pre-existing tests in that file referencing `DenialTimer` will fail until Task 10; that's acceptable mid-plan — note any such failures and proceed.)

- [ ] **Step 8: Lint + commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/db/models/ app/services/profile.py
```
```bash
git add backend/app/db/models/economy.py backend/app/db/models/punishment.py backend/app/db/models/__init__.py backend/app/services/profile.py backend/tests/db/test_economy_models.py
git commit -m "feat(economy): single ChastityTimer, economy debt, Punishment ledger models"
```

---

## Task 3: Migration — drop `denial_timer`, create `chastity_timer` + `punishment`, add `economy_state.debt`

**Files:**
- Create: `backend/alembic/versions/c3d4e5f6a7b8_chastity_debt_punishment.py`

- [ ] **Step 1: Write the migration**

Current head is `b2c3d4e5f6a7`. New PG enums (`punishment_type`, `punishment_status`) are created by this migration (they don't exist yet) — so use `postgresql.ENUM` and let Alembic create them (do NOT pass `create_type=False` for the *new* enums). `denial_timer` is dropped; this is a single-user pre-production app, so dropping its data is acceptable.

Create `backend/alembic/versions/c3d4e5f6a7b8_chastity_debt_punishment.py`:

```python
"""chastity timer + economy debt + punishment ledger

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-09 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. denial_timer (plural, per-event) -> chastity_timer (single per profile).
    op.drop_table('denial_timer')
    op.create_table(
        'chastity_timer',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('note', sa.String(), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('profile_id', name='uq_chastity_profile'),
    )

    # 2. economy debt balance.
    op.add_column(
        'economy_state',
        sa.Column('debt', sa.Integer(), server_default='0', nullable=False),
    )

    # 3. punishment ledger (+ its enums, created here).
    pun_type = postgresql.ENUM(
        'PENANCE_TASK', 'CHASTITY_EXTENSION', 'TOKEN_CONFISCATION', name='punishment_type'
    )
    pun_status = postgresql.ENUM(
        'ISSUED', 'SERVED', 'BOUGHT_DOWN', 'EXPIRED', name='punishment_status'
    )
    op.create_table(
        'punishment',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('type', pun_type, nullable=False),
        sa.Column('severity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('reason', sa.String(), server_default='', nullable=False),
        sa.Column('debt_amount', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', pun_status, server_default='ISSUED', nullable=False),
        sa.Column('penance_task_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('punishment')
    op.execute('DROP TYPE punishment_status')
    op.execute('DROP TYPE punishment_type')
    op.drop_column('economy_state', 'debt')
    op.drop_table('chastity_timer')
    op.create_table(
        'denial_timer',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('reason', sa.String(), server_default='', nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id']),
        sa.PrimaryKeyConstraint('id'),
    )
```

- [ ] **Step 2: Apply + round-trip**

Run from repo root (Postgres up):
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic downgrade -1
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
```
Expected: each exits 0; upgrade logs `b2c3d4e5f6a7 -> c3d4e5f6a7b8`; downgrade restores `denial_timer` and drops the new objects; re-upgrade is clean. If Postgres isn't running locally, defer to CI and note it.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/c3d4e5f6a7b8_chastity_debt_punishment.py
git commit -m "feat(economy): migration for chastity_timer, debt, punishment ledger"
```

---

## Task 4: Economy service — chastity ops + debt ops

**Files:**
- Modify: `backend/app/economy/service.py`
- Test: `backend/tests/economy/test_chastity.py` (new), `backend/tests/economy/test_debt.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/economy/test_chastity.py`:

```python
from datetime import datetime, timedelta, timezone

from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_unlocked_by_default(session):
    p = await _profile(session)
    status = await econ_svc.chastity_status(session, p.id)
    assert status.locked is False
    assert status.ends_at is None
    assert status.seconds_remaining == 0


async def test_set_then_locked_with_remaining(session):
    p = await _profile(session)
    now = datetime.now(timezone.utc)
    await econ_svc.set_chastity(session, p.id, ends_at=now + timedelta(hours=4), note="lock")
    status = await econ_svc.chastity_status(session, p.id, now=now)
    assert status.locked is True
    assert 14000 < status.seconds_remaining <= 14400  # ~4h


async def test_extend_pushes_release_out(session):
    p = await _profile(session)
    now = datetime.now(timezone.utc)
    await econ_svc.set_chastity(session, p.id, ends_at=now + timedelta(hours=2))
    await econ_svc.extend_chastity(session, p.id, hours=3, now=now)
    status = await econ_svc.chastity_status(session, p.id, now=now)
    assert 17900 < status.seconds_remaining <= 18000  # ~5h (2 + 3)


async def test_extend_from_unlocked_starts_from_now(session):
    p = await _profile(session)
    now = datetime.now(timezone.utc)
    await econ_svc.extend_chastity(session, p.id, hours=6, now=now)
    status = await econ_svc.chastity_status(session, p.id, now=now)
    assert status.locked is True
    assert 21500 < status.seconds_remaining <= 21600  # ~6h


async def test_lift_unlocks(session):
    p = await _profile(session)
    now = datetime.now(timezone.utc)
    await econ_svc.set_chastity(session, p.id, ends_at=now + timedelta(hours=4))
    await econ_svc.lift_chastity(session, p.id)
    assert (await econ_svc.chastity_status(session, p.id)).locked is False


async def test_elapsed_lock_reads_as_unlocked(session):
    p = await _profile(session)
    now = datetime.now(timezone.utc)
    await econ_svc.set_chastity(session, p.id, ends_at=now - timedelta(minutes=1))
    status = await econ_svc.chastity_status(session, p.id, now=now)
    assert status.locked is False
    assert status.seconds_remaining == 0
```

Create `backend/tests/economy/test_debt.py`:

```python
from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_adjust_debt_never_negative(session):
    p = await _profile(session)
    await econ_svc.adjust_debt(session, p.id, 20)
    econ = await econ_svc.adjust_debt(session, p.id, -50)
    assert econ.debt == 0


async def test_buy_down_spends_tokens_at_rate_no_merit(session):
    p = await _profile(session)
    await econ_svc.adjust_debt(session, p.id, 10)
    await econ_svc.grant_tokens(session, p.id, 100)
    before_merit = (await econ_svc.get_economy(session, p.id)).merit
    # default buydown_tokens_per_debt = 3 -> clearing 4 debt costs 12 tokens
    econ = await econ_svc.buy_down_debt(session, p.id, debt_points=4)
    assert econ.debt == 6
    assert econ.tokens == 88
    assert econ.merit == before_merit  # buy-down earns no merit


async def test_buy_down_capped_by_debt_and_tokens(session):
    p = await _profile(session)
    await econ_svc.adjust_debt(session, p.id, 5)
    await econ_svc.grant_tokens(session, p.id, 6)  # 6 tokens / 3 = clears 2 debt
    econ = await econ_svc.buy_down_debt(session, p.id, debt_points=5)
    assert econ.debt == 3  # only 2 affordable
    assert econ.tokens == 0
```

- [ ] **Step 2: Run to verify they fail**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/economy/test_chastity.py tests/economy/test_debt.py -q
```
Expected: FAIL — `AttributeError: module 'app.economy.service' has no attribute 'chastity_status'` etc.

- [ ] **Step 3: Replace the denial functions with chastity ops + add debt ops**

In `backend/app/economy/service.py`:

(a) Update imports: change `from app.db.models.economy import DenialTimer, EconomyState` to `from app.db.models.economy import ChastityTimer, EconomyState`, and add at the top:
```python
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
```
(The file already imports `datetime` from `datetime`; ensure the final import line is `from datetime import datetime, timedelta, timezone` — merge, don't duplicate.) Also add a module-level settings instance near the top (after imports) if not present:
```python
from app.config import Settings

_settings = Settings()
```

(b) **Delete** `set_denial_timer`, `active_denial_timers`, and `clear_denial_timers`. **Add** the chastity ops and debt ops:

```python
@dataclass
class ChastityStatus:
    locked: bool
    ends_at: datetime | None
    seconds_remaining: int


async def _get_or_create_chastity(
    session: AsyncSession, profile_id: uuid.UUID
) -> ChastityTimer:
    row = (await session.execute(
        select(ChastityTimer).where(ChastityTimer.profile_id == profile_id)
    )).scalar_one_or_none()
    if row is None:
        row = ChastityTimer(profile_id=profile_id)
        session.add(row)
        await session.flush()
    return row


async def chastity_status(
    session: AsyncSession, profile_id: uuid.UUID, *, now: datetime | None = None
) -> ChastityStatus:
    now = now or datetime.now(timezone.utc)
    row = (await session.execute(
        select(ChastityTimer).where(ChastityTimer.profile_id == profile_id)
    )).scalar_one_or_none()
    ends = row.ends_at if row else None
    if ends is not None and ends > now:
        return ChastityStatus(True, ends, int((ends - now).total_seconds()))
    return ChastityStatus(False, ends, 0)


async def set_chastity(
    session: AsyncSession, profile_id: uuid.UUID, *, ends_at: datetime, note: str = ""
) -> ChastityTimer:
    """Lock chastity until ``ends_at``. Caller commits."""
    row = await _get_or_create_chastity(session, profile_id)
    row.ends_at = ends_at
    if note:
        row.note = note
    await session.flush()
    return row


async def extend_chastity(
    session: AsyncSession, profile_id: uuid.UUID, *, hours: int, now: datetime | None = None
) -> ChastityTimer:
    """Push the chastity release out by ``hours`` (start from now if not locked).
    Only lengthens — never shortens. Caller commits."""
    now = now or datetime.now(timezone.utc)
    row = await _get_or_create_chastity(session, profile_id)
    base = row.ends_at if (row.ends_at is not None and row.ends_at > now) else now
    row.ends_at = base + timedelta(hours=hours)
    await session.flush()
    return row


async def lift_chastity(session: AsyncSession, profile_id: uuid.UUID) -> bool:
    """She releases the lock (ends_at -> None). Returns True if it was locked."""
    row = (await session.execute(
        select(ChastityTimer).where(ChastityTimer.profile_id == profile_id)
    )).scalar_one_or_none()
    was_locked = bool(row and row.ends_at is not None)
    if row is not None:
        row.ends_at = None
        await session.flush()
    return was_locked


async def adjust_debt(
    session: AsyncSession, profile_id: uuid.UUID, delta: int
) -> EconomyState:
    """Apply a debt change, clamped at zero (debt never negative). Caller commits."""
    econ = await get_economy(session, profile_id)
    econ.debt = max(0, econ.debt + delta)
    await session.flush()
    return econ


async def buy_down_debt(
    session: AsyncSession, profile_id: uuid.UUID, *, debt_points: int
) -> EconomyState:
    """Spend tokens to clear debt at a punishing rate (no merit). Clears as much as
    both the debt balance and the token purse allow. Caller commits."""
    if debt_points < 0:
        raise ValueError("debt_points must be non-negative")
    econ = await get_economy(session, profile_id)
    rate = _settings.buydown_tokens_per_debt
    affordable = econ.tokens // rate
    cleared = min(debt_points, econ.debt, affordable)
    econ.debt -= cleared
    econ.tokens -= cleared * rate
    await session.flush()
    return econ
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/economy/test_chastity.py tests/economy/test_debt.py -q
```
Expected: PASS (all chastity + debt tests). Other callers of the deleted denial functions will fail to import until Tasks 7–10; that's expected mid-plan.

- [ ] **Step 5: Lint + commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/economy/service.py tests/economy/test_chastity.py tests/economy/test_debt.py
```
```bash
git add backend/app/economy/service.py backend/tests/economy/test_chastity.py backend/tests/economy/test_debt.py
git commit -m "feat(economy): chastity countdown ops + debt balance + token buy-down"
```

---

## Task 5: Discipline service — `issue_punishment` + `settle_penance`

**Files:**
- Create: `backend/app/discipline/__init__.py`, `backend/app/discipline/service.py`
- Test: `backend/tests/discipline/test_service.py` (add cases)

> Architecture: `discipline/service.py` imports `economy` + models + `memory` and creates penance `Task`s **directly** (not via `loop`), so the `loop` can import discipline without a cycle.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/discipline/test_service.py`:

```python
from datetime import datetime, timezone

from app.db.enums import ProofRequirement, PunishmentStatus, PunishmentType, TaskStatus
from app.db.models.task import Task
from app.discipline import service as disc_svc
from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from sqlalchemy import select


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_issue_chastity_extension_adds_debt_and_extends(session):
    p = await _profile(session)
    now = datetime.now(timezone.utc)
    pun = await disc_svc.issue_punishment(
        session, p.id, type=PunishmentType.CHASTITY_EXTENSION, severity=2,
        reason="missed drill", now=now,
    )
    assert pun.debt_amount == 15  # severity 2
    assert (await econ_svc.get_economy(session, p.id)).debt == 15
    status = await econ_svc.chastity_status(session, p.id, now=now)
    assert status.locked is True  # extended by 24h (severity 2)


async def test_issue_token_confiscation_removes_tokens(session):
    p = await _profile(session)
    await econ_svc.grant_tokens(session, p.id, 100)
    await disc_svc.issue_punishment(
        session, p.id, type=PunishmentType.TOKEN_CONFISCATION, severity=3, reason="fail",
    )
    econ = await econ_svc.get_economy(session, p.id)
    assert econ.tokens == 60  # confiscation severity 3 = 40
    assert econ.debt == 40


async def test_issue_penance_task_creates_linked_task(session):
    p = await _profile(session)
    pun = await disc_svc.issue_punishment(
        session, p.id, type=PunishmentType.PENANCE_TASK, severity=1,
        reason="Write 20 lines: I will report on time.",
    )
    assert pun.penance_task_id is not None
    task = await session.get(Task, pun.penance_task_id)
    assert task is not None
    assert task.status is TaskStatus.ASSIGNED
    assert task.proof_requirement is ProofRequirement.HONOR


async def test_settle_penance_clears_debt_and_recovers_small_merit(session):
    p = await _profile(session)
    pun = await disc_svc.issue_punishment(
        session, p.id, type=PunishmentType.PENANCE_TASK, severity=2, reason="penance",
    )
    assert (await econ_svc.get_economy(session, p.id)).debt == 15
    merit_before = (await econ_svc.get_economy(session, p.id)).merit

    task = await session.get(Task, pun.penance_task_id)
    settled = await disc_svc.settle_penance(session, task)
    assert settled is not None
    assert settled.status is PunishmentStatus.SERVED
    assert settled.resolved_at is not None
    econ = await econ_svc.get_economy(session, p.id)
    assert econ.debt == 0  # 15 - 15
    assert econ.merit == merit_before + 3  # penance_merit_recovery


async def test_settle_penance_is_none_for_a_non_penance_task(session):
    p = await _profile(session)
    task = Task(
        profile_id=p.id, description="ordinary", proof_requirement=ProofRequirement.HONOR,
        status=TaskStatus.VERIFIED_PASS,
    )
    session.add(task)
    await session.flush()
    assert await disc_svc.settle_penance(session, task) is None
```

- [ ] **Step 2: Run to verify it fails**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/discipline/test_service.py -q
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.discipline'`.

- [ ] **Step 3: Create the discipline service**

Create `backend/app/discipline/__init__.py` (empty).

Create `backend/app/discipline/service.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.enums import ProofRequirement, PunishmentStatus, PunishmentType, TaskStatus
from app.db.models.punishment import Punishment
from app.db.models.task import Task
from app.economy import service as econ_svc
from app.memory import service as mem_svc

_settings = Settings()


async def issue_punishment(
    session: AsyncSession,
    profile_id: uuid.UUID,
    *,
    type: PunishmentType,
    severity: int,
    reason: str = "",
    now: datetime | None = None,
) -> Punishment:
    """The discipline unit issues a consequence (Addendum B7): records a ledger
    entry, accrues debt, and enacts the type's effect. Caller commits."""
    now = now or datetime.now(timezone.utc)
    debt_amount = _settings.debt_by_severity[severity]

    punishment = Punishment(
        profile_id=profile_id, type=type, severity=severity, reason=reason,
        debt_amount=debt_amount, status=PunishmentStatus.ISSUED,
    )
    session.add(punishment)
    await session.flush()
    await econ_svc.adjust_debt(session, profile_id, debt_amount)

    if type is PunishmentType.CHASTITY_EXTENSION:
        hours = _settings.chastity_hours_by_severity[severity]
        await econ_svc.extend_chastity(session, profile_id, hours=hours, now=now)
    elif type is PunishmentType.TOKEN_CONFISCATION:
        amount = _settings.confiscation_by_severity[severity]
        econ = await econ_svc.get_economy(session, profile_id)
        await econ_svc.spend_tokens(session, profile_id, min(amount, econ.tokens))
    elif type is PunishmentType.PENANCE_TASK:
        task = Task(
            profile_id=profile_id,
            description=reason or "Serve your penance.",
            proof_requirement=ProofRequirement.HONOR,
            status=TaskStatus.ASSIGNED,
        )
        session.add(task)
        await session.flush()
        punishment.penance_task_id = task.id
        await mem_svc.enqueue_episode(
            session, profile_id, name="penance issued",
            body=f"Penance assigned: {task.description}.",
            source="text", source_description="discipline", reference_time=now,
        )

    await session.flush()
    return punishment


async def settle_penance(session: AsyncSession, task: Task) -> Punishment | None:
    """Settle the penance linked to a just-passed Task (Addendum B7): clear its
    debt and grant a small merit recovery for an honest serve. Returns None if the
    task is not a penance or is already settled. Caller commits."""
    punishment = (await session.execute(
        select(Punishment).where(
            Punishment.penance_task_id == task.id,
            Punishment.status == PunishmentStatus.ISSUED,
        )
    )).scalar_one_or_none()
    if punishment is None:
        return None
    punishment.status = PunishmentStatus.SERVED
    punishment.resolved_at = datetime.now(timezone.utc)
    await econ_svc.adjust_debt(session, task.profile_id, -punishment.debt_amount)
    await econ_svc.adjust_merit(session, task.profile_id, _settings.penance_merit_recovery)
    await session.flush()
    return punishment
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/discipline/test_service.py -q
```
Expected: PASS (7 passed — 2 from Task 1 + 5 new).

- [ ] **Step 5: Confirm no import cycle + lint**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend python -c "import app.discipline.service, app.loop.service, app.economy.service"
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/discipline/
```
Expected: import line prints nothing (no error); ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/discipline/__init__.py backend/app/discipline/service.py backend/tests/discipline/test_service.py
git commit -m "feat(discipline): issue_punishment (3 types) + penance settlement"
```

---

## Task 6: Loop integration — issue on fail/miss, settle penance on pass

**Files:**
- Modify: `backend/app/loop/service.py`
- Test: `backend/tests/loop/test_discipline_hook.py` (new)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/loop/test_discipline_hook.py`:

```python
from datetime import datetime, timedelta, timezone

from app.db.enums import ProofRequirement, PunishmentStatus, TaskStatus
from app.db.models.punishment import Punishment
from app.discipline import service as disc_svc
from app.economy import service as econ_svc
from app.loop import service as loop_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from sqlalchemy import func, select


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_missed_task_issues_a_punishment(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="drill", proof_requirement=ProofRequirement.HONOR,
        deadline=datetime.now(timezone.utc) - timedelta(hours=1), merit_miss_penalty=5,
    )
    await loop_svc.sweep_missed(session, p.id)
    assert task.status is TaskStatus.MISSED
    count = (await session.execute(
        select(func.count()).select_from(Punishment).where(Punishment.profile_id == p.id)
    )).scalar_one()
    assert count == 1  # the miss issued a punishment -> debt accrued
    assert (await econ_svc.get_economy(session, p.id)).debt > 0


async def test_passing_a_penance_task_settles_it(session):
    p = await _profile(session)
    from app.db.enums import PunishmentType

    pun = await disc_svc.issue_punishment(
        session, p.id, type=PunishmentType.PENANCE_TASK, severity=1, reason="penance",
    )
    task = await session.get(__import__("app.db.models.task", fromlist=["Task"]).Task,
                             pun.penance_task_id)
    # Drive the task to PASS via the economy outcome path the loop uses.
    task.status = TaskStatus.VERIFIED_PASS
    await session.flush()
    await loop_svc.apply_terminal_discipline(session, task)  # loop's settle hook
    settled = (await session.execute(
        select(Punishment).where(Punishment.id == pun.id)
    )).scalar_one()
    assert settled.status is PunishmentStatus.SERVED
```

> Note: the second test exercises a small helper `apply_terminal_discipline` you add in Step 3. The first exercises the existing `sweep_missed` path with the new hook.

- [ ] **Step 2: Run to verify it fails**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/loop/test_discipline_hook.py -q
```
Expected: FAIL — `AttributeError: ... 'apply_terminal_discipline'` / no punishment issued on miss.

- [ ] **Step 3: Wire discipline into the loop's terminal points**

In `backend/app/loop/service.py`:

(a) Add the import near the other `app.*` imports:
```python
from app.discipline import service as disc_svc
from app.db.enums import PunishmentType
```

(b) Add a single helper that both terminal paths call, after `_get_task`:
```python
# Default automatic consequence for a miss/fail until the generated punishment
# pool + deterministic selection lands (M4b). Severity scales with the offence.
_AUTO_PUNISHMENT_TYPE = PunishmentType.CHASTITY_EXTENSION


async def apply_terminal_discipline(session: AsyncSession, task: Task) -> None:
    """At a terminal task status, run the discipline unit (Addendum B7):
    PASS settles a linked penance; FAIL/MISS issues a punishment (debt accrues)."""
    if task.status is TaskStatus.VERIFIED_PASS:
        await disc_svc.settle_penance(session, task)
    elif task.status in (TaskStatus.VERIFIED_FAIL, TaskStatus.MISSED):
        severity = 2 if task.status is TaskStatus.VERIFIED_FAIL else 1
        await disc_svc.issue_punishment(
            session, task.profile_id, type=_AUTO_PUNISHMENT_TYPE, severity=severity,
            reason=f"{task.status.value}: {task.description}",
        )
    await session.flush()
```

(c) Call it in `sweep_missed` — after `await econ_svc.apply_task_outcome(session, task)`:
```python
        await econ_svc.apply_task_outcome(session, task)
        await apply_terminal_discipline(session, task)
```

(d) Call it in `verify_task` — replace the block:
```python
    if task.status in (TaskStatus.VERIFIED_PASS, TaskStatus.VERIFIED_FAIL):
        await econ_svc.apply_task_outcome(session, task)
```
with:
```python
    if task.status in (TaskStatus.VERIFIED_PASS, TaskStatus.VERIFIED_FAIL):
        await econ_svc.apply_task_outcome(session, task)
        await apply_terminal_discipline(session, task)
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/loop/test_discipline_hook.py -q
```
Expected: PASS (2 passed).

> Watch for an import cycle: `loop` now imports `discipline`; `discipline` must NOT import `loop`. Confirm with `python -c "import app.loop.service"` — if it raises a circular import, STOP and report (do not restructure).

- [ ] **Step 5: Lint + commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/loop/service.py tests/loop/test_discipline_hook.py
```
```bash
git add backend/app/loop/service.py backend/tests/loop/test_discipline_hook.py
git commit -m "feat(loop): discipline hook — issue on fail/miss, settle penance on pass"
```

---

## Task 7: Rewire safety — safeword lifts chastity

**Files:**
- Modify: `backend/app/safety/service.py`
- Test: `backend/tests/safety/test_service.py` (update)

- [ ] **Step 1: Update the test**

In `backend/tests/safety/test_service.py`, find the test(s) asserting that `trigger_stop` clears denial timers (they call `econ_svc.set_denial_timer` and assert `receipt.denial_lifted`). Replace the denial-timer setup with chastity, keeping the `denial_lifted` field as the compat count. Concretely, any line like:
```python
await econ_svc.set_denial_timer(session, p.id, reason="x", ends_at=...)
```
becomes:
```python
from datetime import datetime, timedelta, timezone
await econ_svc.set_chastity(session, p.id, ends_at=datetime.now(timezone.utc) + timedelta(hours=4))
```
and an assertion like `assert receipt.denial_lifted == 1` stays valid (one lock lifted → 1). If a test asserted multiple timers lifted (`== 2`), change it to set one chastity lock and assert `== 1`. Read the file first and adjust each occurrence.

- [ ] **Step 2: Run to verify it fails**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/safety/test_service.py -q
```
Expected: FAIL — `set_denial_timer`/`clear_denial_timers` no longer exist.

- [ ] **Step 3: Update `trigger_stop`**

In `backend/app/safety/service.py`, in `trigger_stop`, replace:
```python
    lifted = await econ_svc.clear_denial_timers(session, profile_id)
```
with:
```python
    # Safeword releases the chastity lock too (deterministic safety; spec 9).
    lifted = 1 if await econ_svc.lift_chastity(session, profile_id) else 0
```
The `StopReceipt.denial_lifted: int` field and `CALM_STOP_MESSAGE` copy are unchanged in M4a (the user-facing relabel to "chastity" lands in M4b).

- [ ] **Step 4: Run to verify it passes**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/safety/test_service.py -q
```
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/safety/service.py tests/safety/test_service.py
```
```bash
git add backend/app/safety/service.py backend/tests/safety/test_service.py
git commit -m "refactor(safety): safeword lifts the chastity lock (was: clear denial timers)"
```

---

## Task 8: Rewire persona — state block + tool copy (chastity + debt)

**Files:**
- Modify: `backend/app/persona/service.py`, `backend/app/persona/compiler.py`
- Test: `backend/tests/persona/test_compiler.py` (update)

- [ ] **Step 1: Update the test**

In `backend/tests/persona/test_compiler.py`, find assertions referencing `DenialTimer` / `set_denial_timer` / "ACTIVE DENIAL TIMERS". Read the file; update any state-block assertion from the denial line to the new chastity/debt lines (Step 3 defines the exact strings: `CHASTITY: …` and `DEBT: …`). If a compiler-prompt test asserts the `set_denial_timer` tool is documented, change it to `set_chastity`. Make the minimal assertion edits to match the new copy.

- [ ] **Step 2: Run to verify it fails**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/persona/test_compiler.py -q
```
Expected: FAIL (references to removed `DenialTimer` / old copy).

- [ ] **Step 3: Update the state block**

In `backend/app/persona/service.py`:

(a) Change the import `from app.db.models.economy import DenialTimer, EconomyState` to `from app.db.models.economy import EconomyState` and add `from app.economy import service as econ_svc` if not already imported.

(b) In `build_authoritative_state_block`, replace the `active_denials` query block:
```python
    active_denials = (await session.execute(
        select(DenialTimer).where(
            DenialTimer.profile_id == profile_id, DenialTimer.active.is_(True)
        )
    )).scalars().all()
```
with:
```python
    chastity = await econ_svc.chastity_status(session, profile_id)
```

(c) Replace the `MERIT` and `ACTIVE DENIAL TIMERS` lines in the `lines = [...]` list:
```python
        f"MERIT: {econ.merit} | RANK: {econ.rank} | TOKENS: {econ.tokens}",
        f"ACTIVE DENIAL TIMERS: {len(active_denials)}",
```
with:
```python
        f"MERIT: {econ.merit} | RANK: {econ.rank} | TOKENS: {econ.tokens} | DEBT: {econ.debt}",
        (
            f"CHASTITY: locked, {chastity.seconds_remaining // 3600}h remaining"
            if chastity.locked else "CHASTITY: not locked"
        ),
```

- [ ] **Step 4: Update the persona compiler tool copy**

In `backend/app/persona/compiler.py`, update the denial-timer references to chastity:
- The line `- set_denial_timer — hours (int), reason (str).` → `- set_chastity — hours (int), reason (str). Locks/extends chastity by that many hours.`
- The example `{"tool": "set_denial_timer", "hours": 8, "reason": "overnight discipline"}` → `{"tool": "set_chastity", "hours": 8, "reason": "overnight discipline"}`
- Any prose like "set a denial timer" → "lock chastity" / "set a chastity timer" (lines 16 and 51). Keep wording natural; the tool name `set_chastity` must be exact.

- [ ] **Step 5: Run to verify it passes**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/persona/test_compiler.py -q
```
Expected: PASS.

- [ ] **Step 6: Lint + commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/persona/
```
```bash
git add backend/app/persona/service.py backend/app/persona/compiler.py backend/tests/persona/test_compiler.py
git commit -m "refactor(persona): state block + tool copy use chastity + debt"
```

---

## Task 9: Rewire chat tools, dossier, and economy API

**Files:**
- Modify: `backend/app/chat/tools.py`, `backend/app/chat/service.py`, `backend/app/api/economy.py`, `backend/app/schemas/economy.py`
- Test: `backend/tests/chat/test_tools.py`, `backend/tests/api/test_economy_api.py` (update)

- [ ] **Step 1: Update the chat-tools test**

In `backend/tests/chat/test_tools.py`, find the `set_denial_timer` action test. Change the action dict's `"tool": "set_denial_timer"` to `"tool": "set_chastity"` and assert the resulting card is `{"tool": "set_chastity", "hours": <n>, ...}`, and that chastity is now locked (`await econ_svc.chastity_status(session, pid)` → `locked is True`) instead of asserting a denial timer row exists. Read the file and adjust.

- [ ] **Step 2: Update the chat `set_denial_timer` branch**

In `backend/app/chat/tools.py`, replace the `set_denial_timer` branch:
```python
        if tool == "set_denial_timer":
            hours = int(action["hours"])
            ends_at = datetime.now(timezone.utc) + timedelta(hours=hours)
            await econ_svc.set_denial_timer(
                session, profile_id, reason=str(action.get("reason", "")), ends_at=ends_at
            )
            return {"tool": "set_denial_timer", "hours": hours, "reason": action.get("reason", "")}
```
with:
```python
        if tool == "set_chastity":
            hours = int(action["hours"])
            await econ_svc.extend_chastity(session, profile_id, hours=hours)
            if action.get("reason"):
                await econ_svc.set_chastity_note(session, profile_id, str(action["reason"]))
            return {"tool": "set_chastity", "hours": hours, "reason": action.get("reason", "")}
```
Add a tiny `set_chastity_note` helper to `app/economy/service.py` (it keeps the reason/note on the timer without changing `ends_at`):
```python
async def set_chastity_note(
    session: AsyncSession, profile_id: uuid.UUID, note: str
) -> ChastityTimer:
    row = await _get_or_create_chastity(session, profile_id)
    row.note = note
    await session.flush()
    return row
```
(If `datetime`/`timedelta` imports in `tools.py` become unused after this change, remove them to satisfy ruff.)

- [ ] **Step 3: Update the dossier builder (additive: keep `denial_timers`, add `debt` + `chastity`)**

In `backend/app/chat/service.py` `build_dossier`, replace:
```python
    timers = await econ_svc.active_denial_timers(session, profile_id)
```
with:
```python
    chastity = await econ_svc.chastity_status(session, profile_id)
```
and replace the trailing `"denial_timers": len(timers),` with:
```python
        "debt": econ.debt,
        "chastity": {
            "locked": chastity.locked,
            "ends_at": chastity.ends_at.isoformat() if chastity.ends_at else None,
            "seconds_remaining": chastity.seconds_remaining,
        },
        # compat: existing frontend reads denial_timers as a count (M4b relabels).
        "denial_timers": 1 if chastity.locked else 0,
```
Add the matching fields to `DossierOut` in `backend/app/schemas/chat.py`:
```python
class ChastityBlock(BaseModel):
    locked: bool
    ends_at: str | None
    seconds_remaining: int
```
and in `DossierOut` add (keep `denial_timers: int`):
```python
    debt: int
    chastity: ChastityBlock
```

- [ ] **Step 4: Update the economy API + schemas**

In `backend/app/schemas/economy.py`:
- Remove `DenialTimerOut` and `DenialTimerIn`.
- Add `debt: int` to `StandingOut` and a chastity block + a buy-down input:
```python
class ChastityOut(BaseModel):
    locked: bool
    ends_at: datetime | None
    seconds_remaining: int


class StandingOut(BaseModel):
    merit: int
    rank: str
    tokens: int
    debt: int
    chastity: ChastityOut


class SetChastityIn(BaseModel):
    hours: int = Field(ge=1)
    note: str = ""


class BuyDownIn(BaseModel):
    debt_points: int = Field(ge=1)
```
(Keep `TokenOp`.)

In `backend/app/api/economy.py`:
- Update imports to the new schema names; drop `DenialTimerIn/Out`.
- Rewrite `standing` to return the new shape:
```python
@router.get("/{profile_id}/standing", response_model=StandingOut)
async def standing(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> StandingOut:
    try:
        econ = await econ_svc.get_economy(session, profile_id)
    except econ_svc.EconomyNotFound:
        raise _econ_404(profile_id)
    chastity = await econ_svc.chastity_status(session, profile_id)
    return StandingOut(
        merit=econ.merit, rank=econ.rank, tokens=econ.tokens, debt=econ.debt,
        chastity=ChastityOut(
            locked=chastity.locked, ends_at=chastity.ends_at,
            seconds_remaining=chastity.seconds_remaining,
        ),
    )
```
- Replace the two `denial-timer` routes with chastity + buy-down routes:
```python
@router.post("/{profile_id}/chastity", response_model=StandingOut)
async def set_chastity(
    profile_id: uuid.UUID, body: SetChastityIn, session: AsyncSession = Depends(get_session)
) -> StandingOut:
    await econ_svc.extend_chastity(session, profile_id, hours=body.hours)
    if body.note:
        await econ_svc.set_chastity_note(session, profile_id, body.note)
    await session.commit()
    return await standing(profile_id, session)


@router.post("/{profile_id}/chastity/lift", response_model=StandingOut)
async def lift_chastity(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> StandingOut:
    await econ_svc.lift_chastity(session, profile_id)
    await session.commit()
    return await standing(profile_id, session)


@router.post("/{profile_id}/debt/buy-down", response_model=StandingOut)
async def buy_down_debt(
    profile_id: uuid.UUID, body: BuyDownIn, session: AsyncSession = Depends(get_session)
) -> StandingOut:
    try:
        await econ_svc.buy_down_debt(session, profile_id, debt_points=body.debt_points)
    except econ_svc.EconomyNotFound:
        raise _econ_404(profile_id)
    await session.commit()
    return await standing(profile_id, session)
```
(Keep the existing token grant/spend routes; they already call `standing`, which now returns the new shape.)

- [ ] **Step 5: Update the economy-API test**

In `backend/tests/api/test_economy_api.py`, update for the new shape: assertions on `StandingOut` now include `debt` and `chastity`; replace any `denial-timer` endpoint calls with the new `chastity` / `chastity/lift` / `debt/buy-down` routes and assert `chastity.locked` / `debt`. Read the file and adjust each case; remove `DenialTimerOut`-based assertions.

- [ ] **Step 6: Run the affected tests**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/chat/test_tools.py tests/api/test_economy_api.py -q
```
Expected: PASS.

- [ ] **Step 7: Lint + commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/chat/ app/api/economy.py app/schemas/economy.py app/schemas/chat.py app/economy/service.py
```
```bash
git add backend/app/chat/tools.py backend/app/chat/service.py backend/app/api/economy.py backend/app/schemas/economy.py backend/app/schemas/chat.py backend/app/economy/service.py backend/tests/chat/test_tools.py backend/tests/api/test_economy_api.py
git commit -m "refactor(economy+chat): chastity endpoints, debt in standing/dossier, set_chastity tool"
```

---

## Task 10: Rewire the drone reminder unit + sweep remaining denial references

**Files:**
- Modify: `backend/app/drones/service.py`
- Test: `backend/tests/drones/test_drone_service.py`, `backend/tests/economy/test_denial_timers.py`, `backend/tests/chat/test_chat_service.py`

- [ ] **Step 1: Delete the obsolete denial-timer test module**

`backend/tests/economy/test_denial_timers.py` tests the removed `set_denial_timer`/`active_denial_timers`/`clear_denial_timers`. Its behavior is now covered by `tests/economy/test_chastity.py`. Delete it:
```bash
git rm backend/tests/economy/test_denial_timers.py
```

- [ ] **Step 2: Update the drone reminder logic**

In `backend/app/drones/service.py`, the reminder unit currently lists `DenialTimer`s. Replace it with chastity status. Specifically:
- Remove `from app.db.models.economy import DenialTimer, EconomyState` → keep `EconomyState`, drop `DenialTimer`.
- In `_reminder_lines`, replace the `timers` parameter and its denial loop. Change the signature from `_reminder_lines(timers: list[DenialTimer], task, now)` to `_reminder_lines(chastity, task, now)` where `chastity` is the `ChastityStatus`. Replace the timer loop:
```python
    for timer in timers:
        reason = f": {timer.reason}" if timer.reason else ""
        lines.append(f"Denial remains in effect{reason}. Endure it until she lifts it.")
```
with:
```python
    if chastity.locked:
        hours = chastity.seconds_remaining // 3600
        lines.append(f"Chastity remains locked — {hours}h remaining. Endure until she lifts it.")
```
- In `standing_orders`, replace:
```python
    timers = await econ_svc.active_denial_timers(session, profile_id)
    notices += [
        DroneNotice(unit="reminder", line=line)
        for line in _reminder_lines(timers, task, now)
    ]
```
with:
```python
    chastity = await econ_svc.chastity_status(session, profile_id, now=now)
    notices += [
        DroneNotice(unit="reminder", line=line)
        for line in _reminder_lines(chastity, task, now)
    ]
```

- [ ] **Step 3: Update the drone tests**

In `backend/tests/drones/test_drone_service.py`, the test `test_reminder_notice_for_active_denial_timer` uses `econ_svc.set_denial_timer` and asserts a "denial" reminder. Replace it:
```python
async def test_reminder_notice_for_active_chastity_lock(session):
    from datetime import datetime, timedelta, timezone

    p = await _profile(session)
    await econ_svc.set_chastity(
        session, p.id, ends_at=datetime.now(timezone.utc) + timedelta(hours=8)
    )
    notices = await drone_svc.standing_orders(session, p.id)
    reminders = [n for n in notices if n.unit == "reminder"]
    assert any("chastity remains locked" in n.line.lower() for n in reminders)
```
Add `from app.economy import service as econ_svc` to the test imports if not present. Also update `test_no_state_reminder_when_no_timers_or_deadline` (the assertion now checks no "chastity" reminder rather than no "denial" — change `"denial" not in n.line.lower()` to `"chastity" not in n.line.lower()`).

- [ ] **Step 4: Sweep any remaining denial references in chat-service tests**

In `backend/tests/chat/test_chat_service.py`, if any test references `denial`/`set_denial_timer` (e.g. asserting the dossier `denial_timers`), update it: the dossier still returns `denial_timers` (compat), so a count assertion may still hold; if a test sets a denial timer to make it nonzero, switch to `econ_svc.set_chastity(...)`. Read and adjust minimally.

- [ ] **Step 5: Run the affected suites**

Run:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/drones/ tests/chat/ tests/economy/ -q
```
Expected: PASS.

- [ ] **Step 6: Lint + commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/drones/ tests/
```
```bash
git add -A
git commit -m "refactor(drones): reminder unit reads chastity status; drop denial-timer tests"
```

---

## Task 11: Full verification

**Files:** none.

- [ ] **Step 1: Whole backend suite**

Run from repo root (Postgres up):
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest -q
```
Expected: all green. If any test still references the removed denial API, fix it where it lives (search the failure’s file) — there must be **zero** remaining references to `DenialTimer`, `set_denial_timer`, `active_denial_timers`, or `clear_denial_timers`.

- [ ] **Step 2: Confirm no stragglers**

Run a grep for leftover symbols:
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend python -c "import subprocess,sys; sys.exit(0)"
```
Then use the editor/grep tool to search `backend/app` and `backend/tests` for `DenialTimer`, `set_denial_timer`, `active_denial_timers`, `clear_denial_timers` — expect no matches (the dossier/safeword `denial_timers`/`denial_lifted` *field names* are intentionally kept as compat and are allowed).

- [ ] **Step 3: Ruff (whole backend) + migration head**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check .
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
```
Expected: ruff clean; head `c3d4e5f6a7b8`.

- [ ] **Step 4: Frontend sanity (unchanged contract)**

M4a keeps the dossier/safeword field shapes the frontend reads (`denial_timers`, `denial_lifted`) and only *adds* `debt`/`chastity` (extra JSON fields are ignored by the hand-written API interfaces). Confirm no regression:
```
npm --prefix frontend run test
npm --prefix frontend run build
```
Expected: vitest passes; build succeeds. (Playwright e2e remains the CI `e2e` job's responsibility.)

- [ ] **Step 5: Push + PR; CI is the authoritative gate**

```bash
git push -u origin feat/offline-4a-chastity-debt-ledger
gh pr create --title "Offline-first M4a: Chastity Time + debt ledger (economy core)" --body "$(cat <<'EOF'
## Summary
Generalizes the denial timer into a single per-profile **Chastity Time** countdown and introduces the economy's **debt** dimension + a **punishment ledger**.

- `DenialTimer` (plural) → `ChastityTimer` (one per profile: a release time; extensions push it out, only she lifts it).
- `EconomyState.debt` (never negative) + `Punishment` ledger; migration `c3d4e5f6a7b8`.
- New `app/discipline/service.py`: `issue_punishment` (penance task / chastity extension / token confiscation) + `settle_penance` (debt cleared + small merit recovery on an honest serve). Loop hook issues on fail/miss and settles a passed penance.
- `buy_down_debt` (punishing token rate, no merit).
- Rewired safety (safeword lifts chastity), persona prompt/state block, chat `set_chastity` tool, drone reminder unit, economy API (chastity + debt buy-down endpoints, `debt` in standing).

Backend-only: dossier/safeword keep `denial_timers`/`denial_lifted` as compat fields; `debt`/chastity are additive. Deferred to **M4b**: generated punishment pool + deterministic fallback, the discipline drone unit, and the debt/chastity **UI**. Privilege-lock punishment deferred until audiences/comforts exist.

## Test plan
- [x] `uv run pytest -q` (live Postgres) — green
- [x] `uv run ruff check .` — clean
- [x] `alembic upgrade head` → `c3d4e5f6a7b8` (round-trip verified)
- [x] frontend `npm run test` + `npm run build` — green
- [ ] CI backend / frontend / e2e green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review (against the spec, before executing)

**Spec coverage (Addendum B7 + B3 discipline mechanics, scoped to M4a):**
- Three quantities — merit (existing), tokens (existing), **debt** (`EconomyState.debt`, `adjust_debt`) ✓ (Tasks 2, 4)
- Punishment = debt ledger generalizing the denial timer — `Punishment` model + `issue_punishment` ✓ (Tasks 2, 5)
- Chastity Time (single countdown, extensions add, only she lifts) ✓ (Tasks 2, 4)
- Three punishment types (penance task / chastity extension / token confiscation) ✓ (Task 5)
- Clearing debt: penance via the task loop (+ small merit recovery, honest serve) and token buy-down (no merit) ✓ (Tasks 4, 5, 6)
- Issue on miss/fail; original miss merit hit stands (merit applied by `apply_task_outcome` independently of the punishment) ✓ (Task 6)
- All quantities bounded (merit clamped existing; tokens ≥0 existing; **debt ≥0**) + atomic via the single economy service ✓ (Task 4)
- **Deferred (stated):** generated punishment pool + deterministic fallback selection, discipline drone unit, debt/chastity UI → **M4b**; privilege-lock type → later (no consumer).

**Placeholder scan:** code steps carry full code; rewiring tasks (7–10) give exact before/after edits and name the files/assertions to change (the implementer reads the file to place them — that is a located edit, not a placeholder). Two thinking-artifact lines are explicitly called out for deletion (the stray `app.db.models.chastity` import in Task 2; the `__import__` shim in Task 6's test is intentional to fetch `Task` inline).

**Type consistency:** `chastity_status` returns `ChastityStatus(locked, ends_at, seconds_remaining)` — used identically in persona, dossier, drones, API. `issue_punishment(*, type, severity, reason, now=None)` and `settle_penance(task)` match their callers in Task 6. `buy_down_debt(*, debt_points)` matches the API `BuyDownIn`. `extend_chastity(*, hours, now=None)` matches the chat tool and API. `StandingOut`/`DossierOut` additive fields (`debt`, `chastity`) match the builders.

**Branch:** `feat/offline-4a-chastity-debt-ledger`. Local-env caveat (clear PYTHONHOME before every `uv`; Postgres up) per `smistress-dev-environment`; Playwright/CI gates fall to CI.
