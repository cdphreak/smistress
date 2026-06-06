# Milestone 7 — Privilege Economy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the merit-centered privilege economy (spec §7) — one `EconomyService` that enforces invariants (merit bounded, tokens never negative, atomic), computes rank from merit, grants/spends tokens, sets/clears denial timers, and **applies task-outcome stakes** (wiring M6's `TODO(M7)`) with a streak multiplier — plus REST endpoints for standing/tokens/denial-timers.

**Architecture:** A single `app/economy/service.py` is the only place economy state mutates (spec §7: "all economy mutations flow … through a single economy service, merit bounded, tokens never negative, atomic"). It operates on the M2 `EconomyState` (merit/rank/tokens, one-per-profile) and `DenialTimer` rows. `apply_task_outcome(task)` maps a verified/missed task's merit stakes onto merit (pass scaled by a recent-pass **streak multiplier**); the loop service (M6) calls it at the terminal transition. Difficulty/promptness/honesty scaling are deferred tunable hooks. Endpoints (`app/api/economy.py`) expose standing + token + denial-timer ops explicitly (no autonomous tool-calling). Services flush; endpoints commit.

**Tech Stack:** SQLAlchemy 2.0 async, FastAPI, pytest. **No new models, no migration** (reuses M2 `EconomyState`/`DenialTimer`).

---

## Context

M6 merged: a task is verified to `verified_pass`/`verified_fail` or swept to `missed`, and each `Task` carries flat merit stakes (`merit_reward`, `merit_fail_penalty`, `merit_miss_penalty`). `loop/service.py::verify_task` has an explicit `# TODO(M7): apply the task's merit stakes … via the economy service`, and `sweep_missed` transitions to `missed`. M4's disposition reads `EconomyState.merit` for **standing** and recent resolved task statuses for **mood** — so once M7 moves merit, disposition's standing shifts too (no M4 change needed). M2's `EconomyState` (merit=0, rank="novice", tokens=0; one-per-profile, seeded by `create_profile`) and `DenialTimer` (reason, ends_at tz-aware, active) already exist.

### Decisions locked (M7 planning)
- **Flat per-task stakes + streak multiplier.** Apply the explicit `merit_reward`/`merit_fail_penalty`/`merit_miss_penalty` (= §7's pass+X/fail−Y/miss−Z), bounded + atomic, plus a streak multiplier from recent consecutive passes. **Difficulty/promptness/honesty scaling are deferred** (documented hooks; they need signal not yet modeled).
- **EconomyService + REST endpoints** (standing read, grant/spend tokens, set/clear denial timer) + the `apply_task_outcome` wiring into M6. Autonomous tool-calling stays deferred.
- **Rank from current merit bands** (v1 simplification; "sustained merit" smoothing is a tunable refinement).
- **Idempotency:** `verify_task` gains a terminal-state guard so re-verifying a finished task does **not** re-apply merit or re-emit an episode (closing the double-apply risk the M6 review flagged).

### Patterns to follow
- Services flush; **endpoints commit**; reads don't commit. Async-safe: explicit `select(...)`, no lazy IO.
- 404/errors: raise a service exception, map to `HTTPException` in the endpoint (M3–M6 idiom).
- Merit bounds match M4's disposition (`-100..100`) — keep them identical (documented).
- Local dev: clear `PYTHONHOME`/`PYTHONPATH` before `uv`. Run `$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; $uv=(Get-Command uv).Source; $bk="C:\Users\phrea\OneDrive\claude\smistress\backend"; & $uv --directory $bk run pytest -q`. Postgres up. CI unaffected.

## File Structure (all under `backend/`)
New:
- `app/economy/__init__.py` (empty)
- `app/economy/service.py` — invariants, `adjust_merit`, `rank_for`, `grant_tokens`, `spend_tokens`, `set_denial_timer`, `clear_denial_timers`, `active_denial_timers`, `apply_task_outcome`, `get_economy`; exceptions `EconomyNotFound`, `InsufficientTokens`.
- `app/schemas/economy.py` — `StandingOut`, `TokenOp`, `DenialTimerIn`, `DenialTimerOut`.
- `app/api/economy.py` — standing + token + denial-timer endpoints.
- Tests: `tests/economy/__init__.py`, `tests/economy/test_merit_rank.py`, `tests/economy/test_tokens.py`, `tests/economy/test_denial_timers.py`, `tests/economy/test_apply_outcome.py`, `tests/api/test_economy_api.py`, and additions to `tests/loop/test_loop_service.py`.

Modify:
- `app/loop/service.py` — `verify_task` applies the outcome (+ terminal guard); `sweep_missed` applies the miss penalty.
- `app/main.py` — mount the economy router.

---

## Task 1: EconomyService core — merit invariants + rank

**Files:**
- Create: `backend/app/economy/__init__.py` (empty), `backend/app/economy/service.py`
- Test: `backend/tests/economy/__init__.py` (empty), `backend/tests/economy/test_merit_rank.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/economy/test_merit_rank.py`:

```python
import uuid

import pytest

from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


def test_rank_ladder_bands():
    assert econ_svc.rank_for(0) == "novice"
    assert econ_svc.rank_for(20) == "disciplined"
    assert econ_svc.rank_for(50) == "adept"
    assert econ_svc.rank_for(80) == "paragon"
    assert econ_svc.rank_for(-50) == "remedial"


async def test_adjust_merit_clamps_and_recomputes_rank(session):
    p = await _profile(session)
    econ = await econ_svc.adjust_merit(session, p.id, 55)
    await session.commit()
    assert econ.merit == 55
    assert econ.rank == "adept"

    # clamp at the upper bound
    econ = await econ_svc.adjust_merit(session, p.id, 1000)
    await session.commit()
    assert econ.merit == 100
    assert econ.rank == "paragon"

    # clamp at the lower bound
    econ = await econ_svc.adjust_merit(session, p.id, -1000)
    await session.commit()
    assert econ.merit == -100
    assert econ.rank == "remedial"


async def test_get_economy_unknown_profile_raises(session):
    with pytest.raises(econ_svc.EconomyNotFound):
        await econ_svc.get_economy(session, uuid.uuid4())
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/economy/test_merit_rank.py -v`
Expected: FAIL — `ModuleNotFoundError: app.economy.service`.

- [ ] **Step 3: Implement** — `backend/app/economy/service.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.economy import EconomyState

# Merit bounds — identical to app.persona.disposition (the disposition reads this merit).
MERIT_MIN, MERIT_MAX = -100, 100

# Rank ladder by current merit (descending thresholds). Tunable; "sustained merit"
# smoothing is a future refinement.
_RANK_TIERS: tuple[tuple[int, str], ...] = (
    (80, "paragon"),
    (50, "adept"),
    (20, "disciplined"),
    (-20, "novice"),
)
_LOWEST_RANK = "remedial"


class EconomyNotFound(Exception):
    pass


class InsufficientTokens(Exception):
    pass


def rank_for(merit: int) -> str:
    for threshold, name in _RANK_TIERS:
        if merit >= threshold:
            return name
    return _LOWEST_RANK


def _clamp_merit(value: int) -> int:
    return max(MERIT_MIN, min(MERIT_MAX, value))


async def get_economy(session: AsyncSession, profile_id: uuid.UUID) -> EconomyState:
    econ = (await session.execute(
        select(EconomyState).where(EconomyState.profile_id == profile_id)
    )).scalar_one_or_none()
    if econ is None:
        raise EconomyNotFound(str(profile_id))
    return econ


async def adjust_merit(
    session: AsyncSession, profile_id: uuid.UUID, delta: int
) -> EconomyState:
    """Apply a bounded merit change and recompute rank (atomic; caller commits)."""
    econ = await get_economy(session, profile_id)
    econ.merit = _clamp_merit(econ.merit + delta)
    econ.rank = rank_for(econ.merit)
    await session.flush()
    return econ
```

Also create empty `backend/app/economy/__init__.py` and `backend/tests/economy/__init__.py`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/economy/test_merit_rank.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/economy/__init__.py backend/app/economy/service.py \
        backend/tests/economy/__init__.py backend/tests/economy/test_merit_rank.py
git commit -m "feat: add economy service core (bounded merit + rank ladder) (spec 7)"
```

---

## Task 2: Tokens — grant + spend (never negative)

**Files:**
- Modify: `backend/app/economy/service.py`
- Test: `backend/tests/economy/test_tokens.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/economy/test_tokens.py`:

```python
import pytest

from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_grant_then_spend_tokens(session):
    p = await _profile(session)
    econ = await econ_svc.grant_tokens(session, p.id, 3)
    await session.commit()
    assert econ.tokens == 3

    econ = await econ_svc.spend_tokens(session, p.id, 2)
    await session.commit()
    assert econ.tokens == 1


async def test_spend_more_than_held_raises_and_does_not_go_negative(session):
    p = await _profile(session)
    await econ_svc.grant_tokens(session, p.id, 1)
    await session.commit()
    with pytest.raises(econ_svc.InsufficientTokens):
        await econ_svc.spend_tokens(session, p.id, 5)
    # unchanged
    econ = await econ_svc.get_economy(session, p.id)
    assert econ.tokens == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/economy/test_tokens.py -v`
Expected: FAIL — `grant_tokens`/`spend_tokens` not defined.

- [ ] **Step 3: Implement** — append to `backend/app/economy/service.py`:

```python
async def grant_tokens(
    session: AsyncSession, profile_id: uuid.UUID, amount: int
) -> EconomyState:
    """Grant earned tokens (amount must be >= 0; caller commits)."""
    if amount < 0:
        raise ValueError("grant amount must be non-negative")
    econ = await get_economy(session, profile_id)
    econ.tokens += amount
    await session.flush()
    return econ


async def spend_tokens(
    session: AsyncSession, profile_id: uuid.UUID, amount: int
) -> EconomyState:
    """Spend tokens; never goes negative (raises InsufficientTokens). Caller commits."""
    if amount < 0:
        raise ValueError("spend amount must be non-negative")
    econ = await get_economy(session, profile_id)
    if econ.tokens < amount:
        raise InsufficientTokens(f"have {econ.tokens}, need {amount}")
    econ.tokens -= amount
    await session.flush()
    return econ
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/economy/test_tokens.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/economy/service.py backend/tests/economy/test_tokens.py
git commit -m "feat: add token grant/spend with non-negative invariant (spec 7)"
```

---

## Task 3: Denial timers — set + clear + list active

**Files:**
- Modify: `backend/app/economy/service.py`
- Test: `backend/tests/economy/test_denial_timers.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/economy/test_denial_timers.py`:

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


async def test_set_and_list_active_denial_timer(session):
    p = await _profile(session)
    ends = datetime.now(timezone.utc) + timedelta(hours=4)
    timer = await econ_svc.set_denial_timer(session, p.id, reason="missed task", ends_at=ends)
    await session.commit()
    assert timer.active is True

    active = await econ_svc.active_denial_timers(session, p.id)
    assert len(active) == 1
    assert active[0].reason == "missed task"


async def test_clear_deactivates_all_active(session):
    p = await _profile(session)
    ends = datetime.now(timezone.utc) + timedelta(hours=1)
    await econ_svc.set_denial_timer(session, p.id, reason="a", ends_at=ends)
    await econ_svc.set_denial_timer(session, p.id, reason="b", ends_at=ends)
    await session.commit()

    cleared = await econ_svc.clear_denial_timers(session, p.id)
    await session.commit()
    assert cleared == 2
    assert await econ_svc.active_denial_timers(session, p.id) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/economy/test_denial_timers.py -v`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Implement** — append to `backend/app/economy/service.py`.

Add to the imports at the top:
```python
from datetime import datetime

from app.db.models.economy import DenialTimer, EconomyState
```
(Replace the existing `from app.db.models.economy import EconomyState` line with the combined import above, and add the `datetime` import.)

Append:
```python
async def set_denial_timer(
    session: AsyncSession, profile_id: uuid.UUID, *, reason: str, ends_at: datetime
) -> DenialTimer:
    timer = DenialTimer(profile_id=profile_id, reason=reason, ends_at=ends_at, active=True)
    session.add(timer)
    await session.flush()
    return timer


async def active_denial_timers(
    session: AsyncSession, profile_id: uuid.UUID
) -> list[DenialTimer]:
    rows = (await session.execute(
        select(DenialTimer)
        .where(DenialTimer.profile_id == profile_id, DenialTimer.active.is_(True))
        .order_by(DenialTimer.created_at)
    )).scalars().all()
    return list(rows)


async def clear_denial_timers(session: AsyncSession, profile_id: uuid.UUID) -> int:
    timers = await active_denial_timers(session, profile_id)
    for timer in timers:
        timer.active = False
    await session.flush()
    return len(timers)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/economy/test_denial_timers.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/economy/service.py backend/tests/economy/test_denial_timers.py
git commit -m "feat: add denial-timer set/clear/list-active economy ops (spec 7)"
```

---

## Task 4: apply_task_outcome (stakes + streak multiplier)

**Files:**
- Modify: `backend/app/economy/service.py`
- Test: `backend/tests/economy/test_apply_outcome.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/economy/test_apply_outcome.py`:

```python
from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.task import Task
from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def _resolved_task(session, profile_id, status, *, reward=0, fail=0, miss=0):
    t = Task(
        profile_id=profile_id, description="t", proof_requirement=ProofRequirement.HONOR,
        status=status, merit_reward=reward, merit_fail_penalty=fail, merit_miss_penalty=miss,
    )
    session.add(t)
    await session.flush()
    return t


async def test_pass_adds_reward(session):
    p = await _profile(session)
    t = await _resolved_task(session, p.id, TaskStatus.VERIFIED_PASS, reward=10)
    econ = await econ_svc.apply_task_outcome(session, t)
    await session.commit()
    assert econ.merit == 10  # first pass -> streak multiplier x1.0


async def test_fail_subtracts_penalty(session):
    p = await _profile(session)
    t = await _resolved_task(session, p.id, TaskStatus.VERIFIED_FAIL, fail=7)
    econ = await econ_svc.apply_task_outcome(session, t)
    await session.commit()
    assert econ.merit == -7


async def test_miss_subtracts_miss_penalty(session):
    p = await _profile(session)
    t = await _resolved_task(session, p.id, TaskStatus.MISSED, miss=12)
    econ = await econ_svc.apply_task_outcome(session, t)
    await session.commit()
    assert econ.merit == -12


async def test_consecutive_passes_apply_streak_multiplier(session):
    p = await _profile(session)
    # three passes in a row; reward 10 each. Streak multiplier grows: x1.0, x1.25, x1.5
    t1 = await _resolved_task(session, p.id, TaskStatus.VERIFIED_PASS, reward=10)
    await econ_svc.apply_task_outcome(session, t1)
    await session.commit()
    t2 = await _resolved_task(session, p.id, TaskStatus.VERIFIED_PASS, reward=10)
    await econ_svc.apply_task_outcome(session, t2)
    await session.commit()
    t3 = await _resolved_task(session, p.id, TaskStatus.VERIFIED_PASS, reward=10)
    econ = await econ_svc.apply_task_outcome(session, t3)
    await session.commit()
    # 10 + round(10*1.25) + round(10*1.5) = 10 + 13 + 15 = 38
    assert econ.merit == 38


async def test_non_terminal_status_is_noop(session):
    p = await _profile(session)
    t = await _resolved_task(session, p.id, TaskStatus.PROOF_SUBMITTED, reward=10)
    econ = await econ_svc.apply_task_outcome(session, t)
    await session.commit()
    assert econ.merit == 0  # no change for a non-terminal task
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/economy/test_apply_outcome.py -v`
Expected: FAIL — `apply_task_outcome` not defined.

- [ ] **Step 3: Implement** — append to `backend/app/economy/service.py`.

Add to the imports at the top:
```python
from app.db.enums import TaskStatus
from app.db.models.task import Task
```
Add the streak constants near the other constants:
```python
# Streak multiplier on consecutive passes (rewards sustained obedience; tunable).
STREAK_STEP = 0.25
STREAK_MAX_MULT = 2.0
```
Append:
```python
def _streak_multiplier(consecutive_passes: int) -> float:
    """1.0 for a lone pass, growing by STREAK_STEP per consecutive pass, capped."""
    steps = max(consecutive_passes - 1, 0)
    return min(1.0 + STREAK_STEP * steps, STREAK_MAX_MULT)


async def _recent_pass_streak(session: AsyncSession, profile_id: uuid.UUID) -> int:
    """Count the most-recent run of consecutive VERIFIED_PASS tasks (newest first)."""
    statuses = (await session.execute(
        select(Task.status)
        .where(
            Task.profile_id == profile_id,
            Task.status.in_(
                (TaskStatus.VERIFIED_PASS, TaskStatus.VERIFIED_FAIL, TaskStatus.MISSED)
            ),
        )
        .order_by(Task.updated_at.desc())
    )).scalars().all()
    streak = 0
    for status in statuses:
        if status is TaskStatus.VERIFIED_PASS:
            streak += 1
        else:
            break
    return streak


async def apply_task_outcome(session: AsyncSession, task: Task) -> EconomyState:
    """Apply a terminal task's merit stakes to the economy (spec 6 React -> spec 7).

    pass -> +merit_reward * streak_multiplier; fail -> -merit_fail_penalty;
    miss -> -merit_miss_penalty. Non-terminal statuses are a no-op. Caller commits.
    """
    if task.status is TaskStatus.VERIFIED_PASS:
        streak = await _recent_pass_streak(session, task.profile_id)
        delta = round(task.merit_reward * _streak_multiplier(streak))
    elif task.status is TaskStatus.VERIFIED_FAIL:
        delta = -task.merit_fail_penalty
    elif task.status is TaskStatus.MISSED:
        delta = -task.merit_miss_penalty
    else:
        return await get_economy(session, task.profile_id)  # non-terminal -> no change
    return await adjust_merit(session, task.profile_id, delta)
```

> Note: `_recent_pass_streak` is computed *after* the current task's status is already `VERIFIED_PASS` and flushed (the loop sets status before calling apply), so the current pass is included in the count — a first pass yields streak 1 → x1.0. The test inserts each task as `VERIFIED_PASS` before applying, matching that ordering.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/economy/test_apply_outcome.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/economy/service.py backend/tests/economy/test_apply_outcome.py
git commit -m "feat: apply task-outcome merit stakes with streak multiplier (spec 7)"
```

---

## Task 5: Wire economy into the loop (verify_task + sweep_missed) with idempotency guard

**Files:**
- Modify: `backend/app/loop/service.py`
- Test: `backend/tests/loop/test_loop_service.py` (append), `backend/tests/loop/test_sweep.py` (append)

- [ ] **Step 1: Append the failing tests.**

To `backend/tests/loop/test_loop_service.py` (it already imports Settings, Proof, MockLLMProvider, ChatResult, select, TaskStatus, etc.; add `from app.economy import service as econ_svc`):

```python
async def test_verify_pass_applies_merit_reward(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="tidy", proof_requirement=ProofRequirement.HONOR,
        merit_reward=10,
    )
    await session.commit()
    await loop_svc.submit_proof(session, task.id, report="cleaned thoroughly")
    await session.commit()
    provider = MockLLMProvider(scripted=[ChatResult(
        content='{"verdict": "pass", "confidence": 90, "reasoning": "ok", "issues": []}'
    )])
    await loop_svc.verify_task(session, task.id, provider, Settings())
    await session.commit()

    econ = await econ_svc.get_economy(session, p.id)
    assert econ.merit == 10  # reward applied


async def test_reverify_terminal_task_does_not_double_apply(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="tidy", proof_requirement=ProofRequirement.HONOR,
        merit_reward=10,
    )
    await session.commit()
    await loop_svc.submit_proof(session, task.id, report="done well")
    await session.commit()
    provider = MockLLMProvider(scripted=[
        ChatResult(content='{"verdict": "pass", "confidence": 90, "reasoning": "ok", "issues": []}'),
        ChatResult(content='{"verdict": "pass", "confidence": 90, "reasoning": "ok", "issues": []}'),
    ])
    await loop_svc.verify_task(session, task.id, provider, Settings())
    await session.commit()
    # second verify on the now-terminal task must be rejected (no double merit)
    with pytest.raises(loop_svc.TaskNotVerifiable):
        await loop_svc.verify_task(session, task.id, provider, Settings())
    await session.commit()

    econ = await econ_svc.get_economy(session, p.id)
    assert econ.merit == 10  # not 20
```

To `backend/tests/loop/test_sweep.py` (add `from app.economy import service as econ_svc`):

```python
async def test_sweep_applies_miss_penalty(session):
    from datetime import datetime, timedelta, timezone
    p = await _profile(session)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    await loop_svc.assign_task(
        session, p.id, description="overdue", proof_requirement=ProofRequirement.HONOR,
        deadline=past, merit_miss_penalty=8,
    )
    await session.commit()
    await loop_svc.sweep_missed(session)
    await session.commit()

    econ = await econ_svc.get_economy(session, p.id)
    assert econ.merit == -8
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/loop/test_loop_service.py -k "merit or reverify" tests/loop/test_sweep.py -k "penalty" -v`
Expected: FAIL — `TaskNotVerifiable` not defined / merit not applied.

- [ ] **Step 3: Modify `backend/app/loop/service.py`.**

Add the import (with the others):
```python
from app.economy import service as econ_svc
```
Add the exception near `TaskNotFound`:
```python
class TaskNotVerifiable(Exception):
    pass
```
Define the terminal set near `_LAPSABLE`:
```python
_TERMINAL = (TaskStatus.VERIFIED_PASS, TaskStatus.VERIFIED_FAIL, TaskStatus.MISSED)
```
In `verify_task`, add a guard at the very top (after `_get_task`) and apply the outcome where the `# TODO(M7)` comment is. The function becomes:
```python
async def verify_task(
    session: AsyncSession, task_id: uuid.UUID, provider: LLMProvider, settings: Settings
) -> Task:
    task = await _get_task(session, task_id)
    if task.status in _TERMINAL:
        raise TaskNotVerifiable(f"task {task_id} is already {task.status.value}")
    task.status = TaskStatus.VERIFYING
    # ... (unchanged: load proof + timer, run verification.verify, record verdict on proof,
    #      map verdict -> status) ...
```
Then REPLACE the `# TODO(M7): ...` line with:
```python
    if task.status in (TaskStatus.VERIFIED_PASS, TaskStatus.VERIFIED_FAIL):
        await econ_svc.apply_task_outcome(session, task)
```
(Place this after the status mapping and before/after the episode enqueue — either order is fine since both flush; put it before the enqueue.)

In `sweep_missed`, apply the miss penalty for each task right after setting `task.status = TaskStatus.MISSED`:
```python
    for task in overdue:
        task.status = TaskStatus.MISSED
        await session.flush()  # ensure status is set before applying the outcome
        await econ_svc.apply_task_outcome(session, task)
        await mem_svc.enqueue_episode(... )  # unchanged
```

> IMPORT CHAIN: `loop.service` already imports `mem_svc` + `profile_svc` + `verification`; now also `econ_svc`. `economy.service` imports only models (`EconomyState`, `DenialTimer`, `Task`, `TaskStatus`) — NOT loop — so the dependency is one-way (`loop.service → economy.service`). No cycle.

- [ ] **Step 4: Run to verify they pass + no regressions**

Run: `uv run pytest tests/loop/ tests/economy/ -v`
Expected: PASS — the new merit/sweep/idempotency tests plus all existing loop tests (the M6 loop tests don't assert merit, so adding the application doesn't break them; `verify_task` still returns the task and transitions correctly).

- [ ] **Step 5: Commit**

```bash
git add backend/app/loop/service.py backend/tests/loop/test_loop_service.py backend/tests/loop/test_sweep.py
git commit -m "feat: apply economy outcome on verify/miss + terminal-state guard (spec 6/7)"
```

---

## Task 6: Schemas + REST endpoints (standing, tokens, denial timers)

**Files:**
- Create: `backend/app/schemas/economy.py`, `backend/app/api/economy.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_economy_api.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/api/test_economy_api.py`:

```python
import uuid
from datetime import datetime, timedelta, timezone

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


async def test_standing_defaults(client):
    pid = await _new_profile(client)
    r = await client.get(f"/profile/{pid}/standing")
    assert r.status_code == 200
    body = r.json()
    assert body["merit"] == 0
    assert body["rank"] == "novice"
    assert body["tokens"] == 0
    assert body["denial_timers"] == []


async def test_grant_and_spend_tokens(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/tokens/grant", json={"amount": 3})
    assert r.status_code == 200 and r.json()["tokens"] == 3
    r = await client.post(f"/profile/{pid}/tokens/spend", json={"amount": 5})
    assert r.status_code == 409  # insufficient


async def test_set_and_clear_denial_timer(client):
    pid = await _new_profile(client)
    ends = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    r = await client.post(f"/profile/{pid}/denial-timer", json={"reason": "missed", "ends_at": ends})
    assert r.status_code == 201
    r = await client.get(f"/profile/{pid}/standing")
    assert len(r.json()["denial_timers"]) == 1
    r = await client.post(f"/profile/{pid}/denial-timer/clear")
    assert r.status_code == 200 and r.json()["cleared"] == 1


async def test_standing_404(client):
    r = await client.get(f"/profile/{uuid.uuid4()}/standing")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_economy_api.py -v`
Expected: FAIL — routes not mounted.

- [ ] **Step 3a: Implement schemas** — `backend/app/schemas/economy.py`:

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DenialTimerOut(BaseModel):
    id: UUID
    reason: str
    ends_at: datetime
    active: bool
    model_config = ConfigDict(from_attributes=True)


class StandingOut(BaseModel):
    merit: int
    rank: str
    tokens: int
    denial_timers: list[DenialTimerOut]


class TokenOp(BaseModel):
    amount: int = Field(ge=1)


class DenialTimerIn(BaseModel):
    reason: str = ""
    ends_at: datetime
```

- [ ] **Step 3b: Implement the router** — `backend/app/api/economy.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.economy import service as econ_svc
from app.schemas.economy import DenialTimerIn, DenialTimerOut, StandingOut, TokenOp

router = APIRouter(prefix="/profile", tags=["economy"])


def _econ_404(profile_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"economy for profile {profile_id} not found"
    )


@router.get("/{profile_id}/standing", response_model=StandingOut)
async def standing(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> StandingOut:
    try:
        econ = await econ_svc.get_economy(session, profile_id)
    except econ_svc.EconomyNotFound:
        raise _econ_404(profile_id)
    timers = await econ_svc.active_denial_timers(session, profile_id)
    return StandingOut(
        merit=econ.merit, rank=econ.rank, tokens=econ.tokens,
        denial_timers=[DenialTimerOut.model_validate(t) for t in timers],
    )


@router.post("/{profile_id}/tokens/grant", response_model=StandingOut)
async def grant_tokens(
    profile_id: uuid.UUID, body: TokenOp, session: AsyncSession = Depends(get_session)
) -> StandingOut:
    try:
        await econ_svc.grant_tokens(session, profile_id, body.amount)
    except econ_svc.EconomyNotFound:
        raise _econ_404(profile_id)
    await session.commit()
    return await standing(profile_id, session)


@router.post("/{profile_id}/tokens/spend", response_model=StandingOut)
async def spend_tokens(
    profile_id: uuid.UUID, body: TokenOp, session: AsyncSession = Depends(get_session)
) -> StandingOut:
    try:
        await econ_svc.spend_tokens(session, profile_id, body.amount)
    except econ_svc.EconomyNotFound:
        raise _econ_404(profile_id)
    except econ_svc.InsufficientTokens as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    await session.commit()
    return await standing(profile_id, session)


@router.post("/{profile_id}/denial-timer", response_model=DenialTimerOut, status_code=status.HTTP_201_CREATED)
async def set_denial_timer(
    profile_id: uuid.UUID, body: DenialTimerIn, session: AsyncSession = Depends(get_session)
) -> DenialTimerOut:
    timer = await econ_svc.set_denial_timer(
        session, profile_id, reason=body.reason, ends_at=body.ends_at
    )
    await session.commit()
    return DenialTimerOut.model_validate(timer)


@router.post("/{profile_id}/denial-timer/clear")
async def clear_denial_timers(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    cleared = await econ_svc.clear_denial_timers(session, profile_id)
    await session.commit()
    return {"cleared": cleared}
```

> Note: `grant_tokens`/`spend_tokens` re-call `standing(...)` to build the response after committing — `standing` re-reads, which is fine (`expire_on_commit=False`). The denial-timer set endpoint does not guard EconomyNotFound because a `DenialTimer` only needs the profile_id FK; if you prefer a profile-existence guard, add one via `profile_svc.get_profile`, but it is not required by the tests.

- [ ] **Step 3c: Mount** in `backend/app/main.py`: add `from app.api.economy import router as economy_router` and `app.include_router(economy_router)` with the others. Do not disturb existing routes.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/api/test_economy_api.py -v`
Expected: PASS (4 tests). Then full suite for no regressions.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/economy.py backend/app/api/economy.py backend/app/main.py \
        backend/tests/api/test_economy_api.py
git commit -m "feat: add economy REST endpoints (standing, tokens, denial timers) (spec 7)"
```

---

## Task 7: Full verification + milestone wrap

**Files:** none (verification only).

- [ ] **Step 1: Infra up** — `docker compose up -d`.
- [ ] **Step 2: Full suite** — `uv run pytest -q`. Expected: all M1–M7 tests pass (138 from M6 + the new economy core/tokens/timers/outcome/loop-wiring/api tests; the gated Graphiti IT still skips).
- [ ] **Step 3: Lint** — `uv run ruff check .`. Fix any unused imports / E501.
- [ ] **Step 4: Push + CI green**
```bash
git push -u origin feat/m7-economy
```
- [ ] **Step 5: Open the PR**
```bash
gh pr create --base master --head feat/m7-economy \
  --title "M7: Economy — merit/rank/tokens/denial timers + invariants" \
  --body "Implements spec §7; wires M6's merit-stakes hook. See docs/superpowers/plans/2026-06-07-core-obedience-loop-m7-economy.md"
```

---

## Verification (end-to-end for Milestone 7)

1. **Infra up:** `docker compose up -d`.
2. **Suite green:** `uv run pytest -q` — merit invariants/rank, tokens (never negative), denial timers, outcome application + streak, the loop wiring (verify pass → merit up, sweep miss → merit down, re-verify rejected), and the REST endpoints.
3. **Lint clean:** `uv run ruff check .`.
4. **Economy is real end-to-end:** verify a passing task → `GET /profile/{id}/standing` shows merit up + the right rank; consecutive passes apply the streak multiplier; a missed sweep drops merit; spend more tokens than held → 409; set then clear a denial timer. Re-verifying a terminal task → rejected (no double merit). And M4's disposition standing now shifts with merit.
5. **CI green** on the pushed branch.

**Milestone 7 is done when:** all economy mutations flow through the single `EconomyService` with invariants (merit bounded, tokens never negative, atomic), rank derives from merit, task outcomes apply their stakes with a streak multiplier (M6's hook wired, idempotent via the terminal guard), denial timers and tokens are settable via REST, and the suite + CI are green — leaving M8 (Safety) to add safeword/ceiling-clamp/limit-filter on top and M9 the PWA to surface the dossier.

---

## Self-Review

**Spec coverage (§7):**
- One currency = merit, also computes disposition → reuses M4 (disposition reads `EconomyState.merit`); M7 moves it. ✓
- Merit earned/lost, bounded range, tunable constants (pass/fail/miss) → Tasks 1/4 (`adjust_merit` bounded; `apply_task_outcome` applies per-task stakes). Streak multiplier → Task 4. Difficulty/promptness/honesty → **deferred tunable hooks** (per locked decision). ✓ (scoped)
- Rank tiers from merit → Task 1 (`rank_for` ladder; recomputed on every merit change). ✓
- Tokens spent on requests, granted/revoked, never negative → Task 2. ✓
- Denial timers (in-app countdowns) → Task 3. ✓
- Privileges gated by rank/merit → rank is computed and exposed; explicit privilege gating (rewards/requests/leniency) is **deferred** until there is content to gate (no spec entity in v1 loop). ✓ (scoped; rank/merit are the inputs)
- All mutations through a single economy service, merit bounded, tokens never negative, atomic → Tasks 1–4 (the service is the sole mutator; endpoints + loop call it; flush within the caller's txn). ✓
- (Phase 2 Intiface gating) → out of scope, unchanged. ✓
- Unit tests: merit math, economy invariants, disposition=f(merit,mood) (§10) → Tasks 1/2/4 (M4 already tests disposition). ✓

**Placeholder scan:** complete code per step; the only cross-task edit (Task 5's `verify_task`/`sweep_missed` modifications) is spelled out with the exact guard + apply lines; deferred scaling is explicitly documented, not a silent gap.

**Type consistency:** `EconomyService` names (`get_economy`/`adjust_merit`/`rank_for`/`grant_tokens`/`spend_tokens`/`set_denial_timer`/`clear_denial_timers`/`active_denial_timers`/`apply_task_outcome`) and exceptions (`EconomyNotFound`/`InsufficientTokens`) match across Tasks 1–6 and the loop wiring. `TaskNotVerifiable` (Task 5) is raised by `verify_task` and asserted in tests. `StandingOut`/`TokenOp`/`DenialTimerIn`/`DenialTimerOut` (Task 6) match the endpoints. Merit bounds (`-100..100`) match M4's disposition.

---

## Notes for execution
- **Branch:** `feat/m7-economy` (not `master`).
- **No migration** — `EconomyState`/`DenialTimer` already exist (M2).
- **Single mutator:** every merit/token/timer write goes through `app/economy/service.py`. The loop calls `apply_task_outcome`; endpoints call the token/timer ops. Nothing else writes economy state.
- **Idempotency:** the `verify_task` terminal guard (Task 5) means re-verifying a finished task raises `TaskNotVerifiable` — no double merit, no duplicate episode. `sweep_missed` only touches lapsable tasks, so it can't double-apply.
- **Merit bounds are duplicated** (`-100..100` in both `economy.service` and `persona.disposition`) — they must stay equal; a future refactor could centralize them. Documented in both.
- **Deferred (tunable hooks):** difficulty/promptness/honesty merit scaling; "sustained merit" rank smoothing; explicit privilege gating; Intiface denial gating (Phase 2).
- **Local dev caveat:** clear `PYTHONHOME`/`PYTHONPATH` before `uv`. CI unaffected.
- **Frontend (Addendum A):** the Standing/dossier spoke consumes `GET /profile/{id}/standing` in the frontend milestone; M7 only provides the data.
