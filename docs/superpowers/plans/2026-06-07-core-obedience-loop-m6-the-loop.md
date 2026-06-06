# Milestone 6 — The Loop (Task Lifecycle + Verification) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Core Obedience Loop mechanics (spec §6) — the task lifecycle (assign → in_progress → proof_submitted → verifying → verified_pass/verified_fail, deadline → missed), a `VerificationService` with three proof routes (timer = deterministic server-side; honor = strict LLM interrogation; photo/video = configurable-vision **seam** that auto-passes when no vision model), explicit REST endpoints driving the transitions, Graphiti outcome episodes (fulfilling the M5 seam), and a verification eval harness.

**Architecture:** A stateless `VerificationService` (`app/loop/verification.py`) that returns a `VerdictResult` per proof route — timer/none/media are pure, honor calls the chat `LLMProvider` and parses a strict JSON verdict. A DB-backed loop service (`app/loop/service.py`) owns the status transitions, records `Proof`/`TaskTimer` rows, and enqueues a Graphiti episode on assign/verify/miss via the M5 outbox. Endpoints (`app/api/tasks.py`) expose the loop explicitly (no autonomous LLM tool-calling — that is a later integration). **Merit/economy mutation is deferred to M7** (a documented hook in `verify_task`); M6 only transitions task status, which M4's disposition already reads as "recent outcomes."

**Tech Stack:** SQLAlchemy 2.0 async, FastAPI, the existing swappable `LLMProvider` (MockLLMProvider for tests), the M5 memory outbox (`enqueue_episode`), Alembic (two new tables, no enums). No media upload and no real vision call — those are the **M6b** slice.

---

## Context

M5 merged: `Task` (M2) carries `description`, `proof_requirement` (`ProofRequirement`: photo/video/timer/honor/none), `deadline`, merit stakes (`merit_reward`/`merit_fail_penalty`/`merit_miss_penalty`), `status` (`TaskStatus`: assigned/in_progress/proof_submitted/verifying/verified_pass/verified_fail/missed), `created_at`/`updated_at`. M4's disposition reads recent **resolved** task statuses (verified_pass/fail/missed). M5's `enqueue_episode(session, profile_id, *, name, body, source="text", source_description="", reference_time)` durably queues Graphiti episodes (committed with the caller's txn). The chat `LLMProvider.chat(messages, *, model=None, tools=None) -> ChatResult` and `MockLLMProvider(scripted=[...])` exist. `settings.vision_enabled` is the configurable-vision flag.

### Decisions locked (M6 planning)
- **Slice:** lifecycle + timer + honor verification + the configurable-vision **seam** (photo/video → auto-pass when `vision_enabled` is False, per §2) + eval harness + Graphiti episodes. **Media upload (local disk) + the real vision-model image call are M6b** — out of scope here.
- **Explicit services + REST endpoints** drive the loop; the persona *reacts* in character but does not autonomously call tools yet (deferred integration).
- **Merit application is M7.** M6 transitions status only; `verify_task` carries a clear `TODO(M7)` where the economy service will apply the task's merit stakes.

### Patterns to follow
- Services flush; **endpoints commit**; reads don't commit. Async-safe: explicit `select(...)`, no lazy relationship IO.
- New status/verdict persisted fields use **plain `String`** (matching M5's `memory_episode`), so the migration needs **no PG enum / no DROP TYPE**. (`Task.status`/`proof_requirement` remain the existing native enums — unchanged.)
- 404s: raise a service exception (`TaskNotFound`, reuse `profile_svc.ProfileNotFound`), map to `HTTPException(404)` in the endpoint (M3/M4/M5 idiom).
- Graphiti episodes go through `mem_svc.enqueue_episode` (durable outbox) — no direct store calls in the loop.
- Local dev: clear `PYTHONHOME`/`PYTHONPATH` before `uv`. Run `$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; $uv=(Get-Command uv).Source; $bk="C:\Users\phrea\OneDrive\claude\smistress\backend"; & $uv --directory $bk run pytest -q`. Postgres up via `docker compose up -d`. CI unaffected (no vision model → media route auto-passes; honor route uses the mock in tests).

## File Structure (all under `backend/`)
New:
- `app/loop/__init__.py` (empty)
- `app/loop/verification.py` — `VerdictResult` + `verify_timer`/`verify_none`/`verify_media` (pure) + `verify_honor` (LLM) + `verify` router + `_parse_verdict`.
- `app/loop/service.py` — `TaskNotFound`, `assign_task`, `start_task`, `submit_proof`, `verify_task`, `sweep_missed`.
- `app/db/models/loop.py` — `Proof`, `TaskTimer` models.
- `app/schemas/task.py` — `TaskCreate`, `TaskOut`, `ProofIn`, `VerdictOut`.
- `app/api/tasks.py` — the loop endpoints.
- `alembic/versions/<rev>_add_proof_and_task_timer.py` — generated migration.
- Tests: `tests/loop/__init__.py`, `tests/loop/test_verification.py`, `tests/loop/test_verification_honor.py`, `tests/loop/test_loop_service.py`, `tests/loop/test_sweep.py`, `tests/loop/fixtures.py`, `tests/loop/test_verification_eval.py`, `tests/db/test_loop_models.py`, `tests/api/test_tasks_api.py`.

Modify:
- `app/db/models/__init__.py` — register `Proof`, `TaskTimer`.
- `app/main.py` — mount the tasks router.

---

## Task 1: Proof + TaskTimer models + migration

**Files:**
- Create: `backend/app/db/models/loop.py`
- Modify: `backend/app/db/models/__init__.py`
- Create (generated): `backend/alembic/versions/<rev>_add_proof_and_task_timer.py`
- Test: `backend/tests/db/test_loop_models.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/db/test_loop_models.py`:

```python
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.enums import ProofRequirement
from app.db.models.loop import Proof, TaskTimer
from app.db.models.profile import SubProfile
from app.db.models.task import Task


async def _task(session) -> Task:
    p = SubProfile(intensity_ceiling=50)
    session.add(p)
    await session.flush()
    t = Task(profile_id=p.id, description="make the bed", proof_requirement=ProofRequirement.HONOR)
    session.add(t)
    await session.flush()
    return t


async def test_proof_defaults(session):
    t = await _task(session)
    session.add(Proof(task_id=t.id, profile_id=t.profile_id, content="I did it."))
    await session.commit()
    pr = (await session.execute(select(Proof))).scalar_one()
    assert pr.verdict == "pending"
    assert pr.confidence is None
    assert pr.reasoning == ""
    assert pr.issues == []


async def test_task_timer_defaults(session):
    t = await _task(session)
    session.add(TaskTimer(task_id=t.id, required_seconds=600))
    await session.commit()
    tt = (await session.execute(select(TaskTimer))).scalar_one()
    assert tt.required_seconds == 600
    assert tt.started_at is None
    assert tt.stopped_at is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/db/test_loop_models.py -v`
Expected: FAIL — `ModuleNotFoundError: app.db.models.loop`.

- [ ] **Step 3a: Implement** — `backend/app/db/models/loop.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.task import Task


class Proof(Base):
    """A single proof submission for a task and its verification verdict (spec 6).

    verdict is a plain string: pending | pass | fail | re_proof (no PG enum).
    """

    __tablename__ = "proof"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task.id"))
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))
    content: Mapped[str] = mapped_column(Text, default="")  # honor report / timer note

    verdict: Mapped[str] = mapped_column(String, default="pending")
    confidence: Mapped[int | None] = mapped_column(default=None)  # 0-100, None when n/a
    reasoning: Mapped[str] = mapped_column(Text, default="")
    issues: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    task: Mapped[Task] = relationship()


class TaskTimer(Base):
    """Server-side timer for a timer-proof task (deterministic, hard to fudge; spec 6)."""

    __tablename__ = "task_timer"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task.id"), unique=True)
    required_seconds: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    task: Mapped[Task] = relationship()
```

- [ ] **Step 3b: Register** — in `backend/app/db/models/__init__.py` add:
```python
from app.db.models.loop import Proof, TaskTimer  # noqa: F401
```

- [ ] **Step 4: Run the model test** → PASS (the `session` fixture builds the schema via `create_all`).

Run: `uv run pytest tests/db/test_loop_models.py -v`

- [ ] **Step 5: Autogenerate the migration** (test DB at head first; PowerShell):
```
$env:SMISTRESS_DATABASE_URL="postgresql+psycopg://smistress:smistress@localhost:5432/smistress_test"
& $uv --directory $bk run alembic upgrade head
& $uv --directory $bk run alembic revision --autogenerate -m "add proof and task_timer"
```
If autogenerate emits an empty `upgrade()` (the test DB already has the tables from a prior `create_all`), drop them first and re-run:
```
& $uv --directory $bk run python -c "from sqlalchemy import create_engine, text; e=create_engine('postgresql+psycopg://smistress:smistress@localhost:5432/smistress_test')
with e.begin() as c:
    c.execute(text('DROP TABLE IF EXISTS proof')); c.execute(text('DROP TABLE IF EXISTS task_timer'))
print('dropped')"
```
(alembic logs to stderr; PowerShell may red-wrap them — not a failure if the revision file is created.)

- [ ] **Step 6: Inspect** the generated migration: `upgrade()` creates ONLY `proof` and `task_timer` (columns matching the models; FKs to `task.id` and `sub_profile.id`; `task_timer.task_id` unique; `issues` as JSONB; no enum types). `downgrade()` drops both. `down_revision` is the M5 `memory_episode` migration revision id (the current head — confirm with `& $uv --directory $bk run alembic heads`). No `DROP TYPE` needed.

- [ ] **Step 7: Round-trip** — `uv run pytest tests/db/test_migration.py -v` (clears schema → upgrade → downgrade → upgrade) → PASS.

- [ ] **Step 8: Commit**
```bash
git add backend/app/db/models/loop.py backend/app/db/models/__init__.py \
        backend/alembic/versions/ backend/tests/db/test_loop_models.py
git commit -m "feat: add proof + task_timer models and migration (spec 6)"
```

---

## Task 2: VerificationService — VerdictResult + timer/none/media (pure)

**Files:**
- Create: `backend/app/loop/__init__.py` (empty), `backend/app/loop/verification.py`
- Test: `backend/tests/loop/__init__.py` (empty), `backend/tests/loop/test_verification.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/loop/test_verification.py`:

```python
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.db.models.loop import TaskTimer
from app.loop.verification import verify_media, verify_none, verify_timer


def test_verify_none_auto_passes():
    v = verify_none()
    assert v.verdict == "pass"


def test_verify_timer_pass_when_enough_elapsed():
    start = datetime.now(timezone.utc)
    timer = TaskTimer(required_seconds=600, started_at=start, stopped_at=start + timedelta(seconds=700))
    v = verify_timer(timer)
    assert v.verdict == "pass"
    assert v.confidence == 100


def test_verify_timer_fail_when_too_short():
    start = datetime.now(timezone.utc)
    timer = TaskTimer(required_seconds=600, started_at=start, stopped_at=start + timedelta(seconds=120))
    v = verify_timer(timer)
    assert v.verdict == "fail"
    assert "insufficient" in v.issues[0].lower()


def test_verify_timer_reproof_when_not_stopped():
    timer = TaskTimer(required_seconds=600, started_at=datetime.now(timezone.utc), stopped_at=None)
    v = verify_timer(timer)
    assert v.verdict == "re_proof"


def test_verify_media_autopasses_without_vision():
    v = verify_media(Settings(vision_model=None))
    assert v.verdict == "pass"
    assert v.confidence is None
    assert "auto" in v.reasoning.lower()


def test_verify_media_pending_when_vision_configured():
    v = verify_media(Settings(vision_model="qwen2.5-vl"))
    assert v.verdict == "pending"   # real vision verification is M6b
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/loop/test_verification.py -v`
Expected: FAIL — `ModuleNotFoundError: app.loop.verification`.

- [ ] **Step 3: Implement** — `backend/app/loop/verification.py` (the honor/router parts come in Task 3; write the full file now with all functions so Task 3 only adds tests — BUT to keep TDD honest, write only what these tests need now plus the stubs `verify_honor`/`verify`/`_parse_verdict` are added in Task 3). For this task implement exactly:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings
from app.db.models.loop import TaskTimer

# Allowed verdicts (plain strings; persisted on Proof.verdict).
PASS = "pass"
FAIL = "fail"
RE_PROOF = "re_proof"
PENDING = "pending"


@dataclass
class VerdictResult:
    verdict: str  # pass | fail | re_proof | pending
    confidence: int | None  # 0-100, or None when not applicable
    reasoning: str
    issues: list[str] = field(default_factory=list)


def verify_none() -> VerdictResult:
    return VerdictResult(PASS, None, "no proof required", [])


def verify_timer(timer: TaskTimer) -> VerdictResult:
    if timer.started_at is None or timer.stopped_at is None:
        return VerdictResult(RE_PROOF, None, "timer was not started and stopped", ["timer not completed"])
    elapsed = (timer.stopped_at - timer.started_at).total_seconds()
    required = timer.required_seconds
    if elapsed >= required:
        return VerdictResult(PASS, 100, f"elapsed {elapsed:.0f}s >= required {required}s", [])
    return VerdictResult(
        FAIL, 100, f"elapsed {elapsed:.0f}s < required {required}s", ["insufficient duration"]
    )


def verify_media(settings: Settings) -> VerdictResult:
    # Configurable vision (spec 2): no vision model -> auto-pass (honor system for media).
    if not settings.vision_enabled:
        return VerdictResult(PASS, None, "no vision model configured — auto-passed", [])
    # Real image verification is M6b; until then a configured-vision media proof is pending.
    return VerdictResult(PENDING, None, "vision verification pending (M6b)", ["vision pending"])
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/loop/test_verification.py -v`
Expected: PASS (6 tests). Create empty `backend/app/loop/__init__.py` and `backend/tests/loop/__init__.py`.

- [ ] **Step 5: Commit**
```bash
git add backend/app/loop/__init__.py backend/app/loop/verification.py \
        backend/tests/loop/__init__.py backend/tests/loop/test_verification.py
git commit -m "feat: add VerificationService timer/none/media routes (configurable vision seam)"
```

---

## Task 3: VerificationService — honor (LLM) + verify router

**Files:**
- Modify: `backend/app/loop/verification.py`
- Test: `backend/tests/loop/test_verification_honor.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/loop/test_verification_honor.py`:

```python
from app.config import Settings
from app.db.enums import ProofRequirement
from app.db.models.task import Task
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.loop.verification import verify, verify_honor


def _task(pr=ProofRequirement.HONOR) -> Task:
    return Task(description="20 push-ups", proof_requirement=pr)


async def test_verify_honor_parses_strict_json_pass():
    provider = MockLLMProvider(scripted=[ChatResult(
        content='{"verdict": "pass", "confidence": 82, "reasoning": "credible", "issues": []}'
    )])
    v = await verify_honor("I did all twenty, slowly.", _task(), provider)
    assert v.verdict == "pass"
    assert v.confidence == 82
    # the strict rubric was sent to the model as the system prompt
    assert provider.calls[0][0].role == "system"
    assert "20 push-ups" in provider.calls[0][1].content


async def test_verify_honor_parses_fenced_json():
    provider = MockLLMProvider(scripted=[ChatResult(
        content='```json\n{"verdict": "fail", "confidence": 30, "reasoning": "vague", "issues": ["no detail"]}\n```'
    )])
    v = await verify_honor("did it", _task(), provider)
    assert v.verdict == "fail"
    assert v.issues == ["no detail"]


async def test_verify_honor_unparseable_demands_reproof():
    provider = MockLLMProvider(scripted=[ChatResult(content="I think that's fine, sure.")])
    v = await verify_honor("did it", _task(), provider)
    assert v.verdict == "re_proof"   # can't trust an unparseable verdict


async def test_verify_router_dispatches_by_requirement():
    # none -> pass without touching the provider
    provider = MockLLMProvider(scripted=[])
    v = await verify(_task(ProofRequirement.NONE), report="", timer=None,
                     provider=provider, settings=Settings())
    assert v.verdict == "pass"
    assert provider.calls == []  # router didn't call the LLM for a no-proof task
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/loop/test_verification_honor.py -v`
Expected: FAIL — `verify`/`verify_honor` not defined.

- [ ] **Step 3: Implement** — append to `backend/app/loop/verification.py`.

Add imports at the top (with the others):
```python
import json

from app.db.enums import ProofRequirement
from app.db.models.task import Task
from app.llm.provider import LLMProvider
from app.llm.types import ChatMessage
```
Append:
```python
_HONOR_SYSTEM = (
    "You are a strict, fair verifier of a completed real-world task. Judge ONLY whether the "
    "written report credibly demonstrates the task was completed as required. Be exacting: "
    "vague, evasive, or internally inconsistent reports fail or require re-proof. "
    'Respond with ONLY a JSON object: {"verdict": "pass"|"fail"|"re_proof", '
    '"confidence": <0-100 integer>, "reasoning": "<one sentence>", "issues": ["<short>", ...]}'
)

_ALLOWED = {PASS, FAIL, RE_PROOF}


def _parse_verdict(raw: str) -> VerdictResult:
    text = raw.strip()
    if text.startswith("```"):
        # strip a ```json ... ``` fence
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    try:
        data = json.loads(text)
        verdict = str(data["verdict"]).lower()
        if verdict not in _ALLOWED:
            raise ValueError("verdict out of range")
        confidence = data.get("confidence")
        confidence = int(confidence) if confidence is not None else None
        return VerdictResult(
            verdict=verdict,
            confidence=confidence,
            reasoning=str(data.get("reasoning", "")),
            issues=[str(i) for i in data.get("issues", [])],
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        # an unparseable verdict can't be trusted -> demand re-proof
        return VerdictResult(RE_PROOF, None, "verifier response was not valid JSON", ["unparseable verdict"])


async def verify_honor(report: str, task: Task, provider: LLMProvider) -> VerdictResult:
    messages = [
        ChatMessage(role="system", content=_HONOR_SYSTEM),
        ChatMessage(
            role="user",
            content=f"TASK: {task.description}\nHONOR REPORT:\n{report}",
        ),
    ]
    result = await provider.chat(messages)
    return _parse_verdict(result.content)


async def verify(
    task: Task,
    *,
    report: str,
    timer: TaskTimer | None,
    provider: LLMProvider,
    settings: Settings,
) -> VerdictResult:
    """Route a proof to its verification strategy by the task's proof requirement."""
    pr = task.proof_requirement
    if pr is ProofRequirement.NONE:
        return verify_none()
    if pr is ProofRequirement.TIMER:
        if timer is None:
            return VerdictResult(RE_PROOF, None, "no timer recorded", ["timer missing"])
        return verify_timer(timer)
    if pr is ProofRequirement.HONOR:
        return await verify_honor(report, task, provider)
    # PHOTO or VIDEO
    return verify_media(settings)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/loop/test_verification_honor.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**
```bash
git add backend/app/loop/verification.py backend/tests/loop/test_verification_honor.py
git commit -m "feat: add strict honor verification (LLM verdict + parse) and verify router (spec 6)"
```

---

## Task 4: Loop service — assign + start

**Files:**
- Create: `backend/app/loop/service.py`
- Test: `backend/tests/loop/test_loop_service.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/loop/test_loop_service.py`:

```python
import uuid

import pytest
from sqlalchemy import select

from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.loop import TaskTimer
from app.db.models.memory import MemoryEpisode
from app.loop import service as loop_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_assign_task_creates_assigned_and_seeds_episode(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="make the bed", proof_requirement=ProofRequirement.HONOR,
        merit_reward=5, merit_miss_penalty=8,
    )
    await session.commit()

    assert task.status is TaskStatus.ASSIGNED
    assert task.merit_reward == 5
    # assignment is recorded as a memory episode (M5 outbox)
    ep = (await session.execute(select(MemoryEpisode))).scalars().all()
    assert any("make the bed" in e.body for e in ep)


async def test_assign_timer_task_creates_timer(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="meditate", proof_requirement=ProofRequirement.TIMER,
        required_seconds=600,
    )
    await session.commit()
    tt = (await session.execute(select(TaskTimer).where(TaskTimer.task_id == task.id))).scalar_one()
    assert tt.required_seconds == 600
    assert tt.started_at is None


async def test_start_task_sets_in_progress_and_starts_timer(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="meditate", proof_requirement=ProofRequirement.TIMER,
        required_seconds=600,
    )
    await session.commit()
    started = await loop_svc.start_task(session, task.id)
    await session.commit()
    assert started.status is TaskStatus.IN_PROGRESS
    tt = (await session.execute(select(TaskTimer).where(TaskTimer.task_id == task.id))).scalar_one()
    assert tt.started_at is not None


async def test_start_unknown_task_raises(session):
    with pytest.raises(loop_svc.TaskNotFound):
        await loop_svc.start_task(session, uuid.uuid4())
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/loop/test_loop_service.py -v`
Expected: FAIL — `ModuleNotFoundError: app.loop.service`.

- [ ] **Step 3: Implement** — `backend/app/loop/service.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.loop import TaskTimer
from app.db.models.task import Task
from app.memory import service as mem_svc
from app.services import profile as profile_svc


class TaskNotFound(Exception):
    pass


async def _get_task(session: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise TaskNotFound(str(task_id))
    return task


async def assign_task(
    session: AsyncSession,
    profile_id: uuid.UUID,
    *,
    description: str,
    proof_requirement: ProofRequirement,
    deadline: datetime | None = None,
    merit_reward: int = 0,
    merit_fail_penalty: int = 0,
    merit_miss_penalty: int = 0,
    required_seconds: int | None = None,
) -> Task:
    await profile_svc.get_profile(session, profile_id)  # 404 guard
    task = Task(
        profile_id=profile_id,
        description=description,
        proof_requirement=proof_requirement,
        deadline=deadline,
        merit_reward=merit_reward,
        merit_fail_penalty=merit_fail_penalty,
        merit_miss_penalty=merit_miss_penalty,
        status=TaskStatus.ASSIGNED,
    )
    session.add(task)
    await session.flush()
    if proof_requirement is ProofRequirement.TIMER:
        session.add(TaskTimer(task_id=task.id, required_seconds=required_seconds or 0))
    await mem_svc.enqueue_episode(
        session,
        profile_id,
        name="task assigned",
        body=f"Assigned task: {description} (proof: {proof_requirement.value}).",
        source="text",
        source_description="task",
        reference_time=datetime.now(timezone.utc),
    )
    await session.flush()
    return task


async def start_task(session: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await _get_task(session, task_id)
    task.status = TaskStatus.IN_PROGRESS
    if task.proof_requirement is ProofRequirement.TIMER:
        timer = (await session.execute(
            select(TaskTimer).where(TaskTimer.task_id == task.id)
        )).scalar_one_or_none()
        if timer is not None and timer.started_at is None:
            timer.started_at = datetime.now(timezone.utc)
    await session.flush()
    return task
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/loop/test_loop_service.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**
```bash
git add backend/app/loop/service.py backend/tests/loop/test_loop_service.py
git commit -m "feat: add loop service assign_task + start_task (timer start, assign episode)"
```

---

## Task 5: Loop service — submit_proof + verify_task

**Files:**
- Modify: `backend/app/loop/service.py`
- Test: `backend/tests/loop/test_loop_service.py` (append)

- [ ] **Step 1: Append the failing tests** to `backend/tests/loop/test_loop_service.py`:

```python
from datetime import timedelta

from app.config import Settings
from app.db.models.loop import Proof
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult


async def test_submit_proof_records_proof_and_proof_submitted(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="tidy desk", proof_requirement=ProofRequirement.HONOR,
    )
    await session.commit()
    await loop_svc.start_task(session, task.id)
    await session.commit()
    proof = await loop_svc.submit_proof(session, task.id, report="Cleared and wiped it.")
    await session.commit()

    assert proof.content == "Cleared and wiped it."
    refreshed = await session.get(type(task), task.id)
    assert refreshed.status is TaskStatus.PROOF_SUBMITTED


async def test_verify_task_honor_pass_sets_verified_pass(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="tidy desk", proof_requirement=ProofRequirement.HONOR,
    )
    await session.commit()
    await loop_svc.submit_proof(session, task.id, report="Cleared, wiped, and organized the cables.")
    await session.commit()

    provider = MockLLMProvider(scripted=[ChatResult(
        content='{"verdict": "pass", "confidence": 90, "reasoning": "detailed", "issues": []}'
    )])
    verified = await loop_svc.verify_task(session, task.id, provider, Settings())
    await session.commit()

    assert verified.status is TaskStatus.VERIFIED_PASS
    pr = (await session.execute(select(Proof).where(Proof.task_id == task.id))).scalar_one()
    assert pr.verdict == "pass"
    assert pr.confidence == 90


async def test_verify_task_honor_fail_sets_verified_fail(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="tidy desk", proof_requirement=ProofRequirement.HONOR,
    )
    await session.commit()
    await loop_svc.submit_proof(session, task.id, report="meh")
    await session.commit()

    provider = MockLLMProvider(scripted=[ChatResult(
        content='{"verdict": "fail", "confidence": 20, "reasoning": "no detail", "issues": ["vague"]}'
    )])
    verified = await loop_svc.verify_task(session, task.id, provider, Settings())
    await session.commit()
    assert verified.status is TaskStatus.VERIFIED_FAIL


async def test_verify_timer_task_passes_on_sufficient_elapsed(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="meditate", proof_requirement=ProofRequirement.TIMER,
        required_seconds=1,
    )
    await session.commit()
    await loop_svc.start_task(session, task.id)
    await session.commit()
    # backdate the timer start so elapsed >= required without sleeping
    tt = (await session.execute(select(TaskTimer).where(TaskTimer.task_id == task.id))).scalar_one()
    tt.started_at = tt.started_at - timedelta(seconds=10)
    await session.commit()
    await loop_svc.submit_proof(session, task.id)  # stops the timer
    await session.commit()

    verified = await loop_svc.verify_task(session, task.id, MockLLMProvider(), Settings())
    await session.commit()
    assert verified.status is TaskStatus.VERIFIED_PASS
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/loop/test_loop_service.py -k "submit or verify" -v`
Expected: FAIL — `submit_proof`/`verify_task` not defined.

- [ ] **Step 3: Implement** — append to `backend/app/loop/service.py`.

Add imports at the top (with the others):
```python
from app.config import Settings
from app.db.models.loop import Proof
from app.llm.provider import LLMProvider
from app.loop import verification
```
Append:
```python
async def submit_proof(
    session: AsyncSession, task_id: uuid.UUID, *, report: str = ""
) -> Proof:
    task = await _get_task(session, task_id)
    if task.proof_requirement is ProofRequirement.TIMER:
        timer = (await session.execute(
            select(TaskTimer).where(TaskTimer.task_id == task.id)
        )).scalar_one_or_none()
        if timer is not None and timer.stopped_at is None:
            timer.stopped_at = datetime.now(timezone.utc)
    proof = Proof(task_id=task.id, profile_id=task.profile_id, content=report)
    session.add(proof)
    task.status = TaskStatus.PROOF_SUBMITTED
    await session.flush()
    return proof


async def verify_task(
    session: AsyncSession, task_id: uuid.UUID, provider: LLMProvider, settings: Settings
) -> Task:
    task = await _get_task(session, task_id)
    task.status = TaskStatus.VERIFYING

    proof = (await session.execute(
        select(Proof).where(Proof.task_id == task.id).order_by(Proof.created_at.desc())
    )).scalars().first()
    timer = (await session.execute(
        select(TaskTimer).where(TaskTimer.task_id == task.id)
    )).scalar_one_or_none()

    result = await verification.verify(
        task,
        report=proof.content if proof is not None else "",
        timer=timer,
        provider=provider,
        settings=settings,
    )

    if proof is not None:
        proof.verdict = result.verdict
        proof.confidence = result.confidence
        proof.reasoning = result.reasoning
        proof.issues = result.issues

    if result.verdict == verification.PASS:
        task.status = TaskStatus.VERIFIED_PASS
    elif result.verdict == verification.FAIL:
        task.status = TaskStatus.VERIFIED_FAIL
    else:
        task.status = TaskStatus.PROOF_SUBMITTED  # re_proof/pending -> awaiting another attempt

    # TODO(M7): apply the task's merit stakes (reward/fail penalty) via the economy service.
    await mem_svc.enqueue_episode(
        session,
        task.profile_id,
        name="task verified",
        body=(
            f"Task '{task.description}' verification: {result.verdict} "
            f"(confidence {result.confidence}). {result.reasoning}"
        ),
        source="text",
        source_description="task",
        reference_time=datetime.now(timezone.utc),
    )
    await session.flush()
    return task
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/loop/test_loop_service.py -v`
Expected: PASS (all loop-service tests).

- [ ] **Step 5: Commit**
```bash
git add backend/app/loop/service.py backend/tests/loop/test_loop_service.py
git commit -m "feat: add submit_proof + verify_task (routes to VerificationService, records verdict + episode)"
```

---

## Task 6: Loop service — sweep_missed

**Files:**
- Modify: `backend/app/loop/service.py`
- Test: `backend/tests/loop/test_sweep.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/loop/test_sweep.py`:

```python
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.enums import ProofRequirement, TaskStatus
from app.loop import service as loop_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_sweep_marks_overdue_unstarted_tasks_missed(session):
    p = await _profile(session)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    overdue = await loop_svc.assign_task(
        session, p.id, description="overdue", proof_requirement=ProofRequirement.HONOR,
        deadline=past,
    )
    on_time = await loop_svc.assign_task(
        session, p.id, description="future", proof_requirement=ProofRequirement.HONOR,
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    await session.commit()

    count = await loop_svc.sweep_missed(session)
    await session.commit()

    assert count == 1
    refreshed = await session.get(type(overdue), overdue.id)
    assert refreshed.status is TaskStatus.MISSED
    still = await session.get(type(on_time), on_time.id)
    assert still.status is TaskStatus.ASSIGNED


async def test_sweep_ignores_tasks_awaiting_verification(session):
    p = await _profile(session)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    task = await loop_svc.assign_task(
        session, p.id, description="submitted late but submitted", proof_requirement=ProofRequirement.HONOR,
        deadline=past,
    )
    await session.commit()
    await loop_svc.submit_proof(session, task.id, report="done")  # now proof_submitted
    await session.commit()

    count = await loop_svc.sweep_missed(session)
    await session.commit()
    assert count == 0  # proof_submitted is not "missed"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/loop/test_sweep.py -v`
Expected: FAIL — `sweep_missed` not defined.

- [ ] **Step 3: Implement** — append to `backend/app/loop/service.py`:

```python
# Statuses that can still lapse into "missed" (no proof submitted yet).
_LAPSABLE = (TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS)


async def sweep_missed(session: AsyncSession, profile_id: uuid.UUID | None = None) -> int:
    """Mark overdue, un-submitted tasks as missed (deadline passed with no proof; spec 6).

    Tasks already in proof_submitted/verifying are awaiting verification, not missed.
    """
    now = datetime.now(timezone.utc)
    stmt = select(Task).where(
        Task.deadline.is_not(None),
        Task.deadline < now,
        Task.status.in_(_LAPSABLE),
    )
    if profile_id is not None:
        stmt = stmt.where(Task.profile_id == profile_id)
    overdue = (await session.execute(stmt)).scalars().all()
    for task in overdue:
        task.status = TaskStatus.MISSED
        await mem_svc.enqueue_episode(
            session,
            task.profile_id,
            name="task missed",
            body=f"Task '{task.description}' was missed (deadline passed with no proof).",
            source="text",
            source_description="task",
            reference_time=now,
        )
    await session.flush()
    return len(overdue)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/loop/test_sweep.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**
```bash
git add backend/app/loop/service.py backend/tests/loop/test_sweep.py
git commit -m "feat: add sweep_missed for overdue un-submitted tasks (spec 6)"
```

---

## Task 7: Schemas + REST endpoints

**Files:**
- Create: `backend/app/schemas/task.py`, `backend/app/api/tasks.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_tasks_api.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/api/test_tasks_api.py`:

```python
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.db.session import get_session
from app.llm.factory import build_provider
from app.main import app, get_provider
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult


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


async def test_assign_list_get_task(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/tasks", json={
        "description": "make the bed", "proof_requirement": "honor", "merit_reward": 5,
    })
    assert r.status_code == 201
    tid = r.json()["id"]
    assert r.json()["status"] == "assigned"

    r = await client.get(f"/profile/{pid}/tasks")
    assert r.status_code == 200 and len(r.json()) == 1

    r = await client.get(f"/tasks/{tid}")
    assert r.status_code == 200 and r.json()["description"] == "make the bed"


async def test_full_honor_loop_via_api(client):
    pid = await _new_profile(client)
    tid = (await client.post(f"/profile/{pid}/tasks", json={
        "description": "20 push-ups", "proof_requirement": "honor",
    })).json()["id"]

    assert (await client.post(f"/tasks/{tid}/start")).status_code == 200
    assert (await client.post(f"/tasks/{tid}/proof", json={"report": "did all twenty"})).status_code == 200

    # override the persona provider with a scripted strict-pass verdict
    app.dependency_overrides[get_provider] = lambda: MockLLMProvider(scripted=[ChatResult(
        content='{"verdict": "pass", "confidence": 88, "reasoning": "ok", "issues": []}'
    )])
    try:
        r = await client.post(f"/tasks/{tid}/verify")
    finally:
        app.dependency_overrides.pop(get_provider, None)
    assert r.status_code == 200
    assert r.json()["status"] == "verified_pass"


async def test_task_404(client):
    r = await client.get(f"/tasks/{uuid.uuid4()}")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_tasks_api.py -v`
Expected: FAIL — endpoints not mounted (404/405); possibly import error for `get_provider` (added below).

- [ ] **Step 3a: Implement schemas** — `backend/app/schemas/task.py`:

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.enums import ProofRequirement, TaskStatus


class TaskCreate(BaseModel):
    description: str
    proof_requirement: ProofRequirement = ProofRequirement.HONOR
    deadline: datetime | None = None
    merit_reward: int = 0
    merit_fail_penalty: int = 0
    merit_miss_penalty: int = 0
    required_seconds: int | None = None  # for timer proofs


class TaskOut(BaseModel):
    id: UUID
    description: str
    proof_requirement: ProofRequirement
    status: TaskStatus
    deadline: datetime | None
    merit_reward: int
    merit_fail_penalty: int
    merit_miss_penalty: int
    model_config = ConfigDict(from_attributes=True)


class ProofIn(BaseModel):
    report: str = ""


class VerdictOut(BaseModel):
    task_id: UUID
    status: TaskStatus
    verdict: str | None
    confidence: int | None
    reasoning: str
```

- [ ] **Step 3b: Ensure `get_provider` is importable** — it already exists in `backend/app/main.py` (`def get_provider() -> LLMProvider: return build_provider(settings)`). The tasks router will depend on it. No change needed if it's defined at module scope in `main.py` (it is). The verify endpoint imports it from `app.main`.

> Importing `get_provider` from `app.main` into `app.api.tasks` is safe only if `app.main` does not import `app.api.tasks` at module top in a way that cycles. To avoid any cycle, **define the provider dependency locally in the tasks router** instead of importing from main:

```python
# in app/api/tasks.py
from app.config import Settings
from app.llm.factory import build_provider
from app.llm.provider import LLMProvider

_settings = Settings()

def get_task_provider() -> LLMProvider:
    return build_provider(_settings)
```
and the test overrides `get_task_provider` (not `app.main.get_provider`). **Update the test accordingly**: import `from app.api.tasks import get_task_provider` and override that. (Adjust Step 1's test: replace the two `get_provider` references with `get_task_provider`, and import it from `app.api.tasks` instead of `app.main`. Drop the unused `build_provider`/`get_provider`/`Settings` imports from the test.)

- [ ] **Step 3c: Implement the router** — `backend/app/api/tasks.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.loop import Proof
from app.db.models.task import Task
from app.db.session import get_session
from app.llm.factory import build_provider
from app.llm.provider import LLMProvider
from app.loop import service as loop_svc
from app.schemas.task import ProofIn, TaskCreate, TaskOut, VerdictOut
from app.services import profile as profile_svc

router = APIRouter(tags=["tasks"])
_settings = Settings()


def get_task_provider() -> LLMProvider:
    return build_provider(_settings)


def _task_404(task_id: uuid.UUID) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"task {task_id} not found")


@router.post("/profile/{profile_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def assign(
    profile_id: uuid.UUID, body: TaskCreate, session: AsyncSession = Depends(get_session)
) -> TaskOut:
    try:
        task = await loop_svc.assign_task(
            session, profile_id,
            description=body.description, proof_requirement=body.proof_requirement,
            deadline=body.deadline, merit_reward=body.merit_reward,
            merit_fail_penalty=body.merit_fail_penalty, merit_miss_penalty=body.merit_miss_penalty,
            required_seconds=body.required_seconds,
        )
    except profile_svc.ProfileNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    await session.commit()
    return TaskOut.model_validate(task)


@router.get("/profile/{profile_id}/tasks", response_model=list[TaskOut])
async def list_tasks(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[TaskOut]:
    rows = (await session.execute(
        select(Task).where(Task.profile_id == profile_id).order_by(Task.created_at)
    )).scalars().all()
    return [TaskOut.model_validate(t) for t in rows]


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> TaskOut:
    task = await session.get(Task, task_id)
    if task is None:
        raise _task_404(task_id)
    return TaskOut.model_validate(task)


@router.post("/tasks/{task_id}/start", response_model=TaskOut)
async def start(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> TaskOut:
    try:
        task = await loop_svc.start_task(session, task_id)
    except loop_svc.TaskNotFound:
        raise _task_404(task_id)
    await session.commit()
    return TaskOut.model_validate(task)


@router.post("/tasks/{task_id}/proof", response_model=TaskOut)
async def submit_proof(
    task_id: uuid.UUID, body: ProofIn, session: AsyncSession = Depends(get_session)
) -> TaskOut:
    try:
        await loop_svc.submit_proof(session, task_id, report=body.report)
        task = await session.get(Task, task_id)
    except loop_svc.TaskNotFound:
        raise _task_404(task_id)
    await session.commit()
    return TaskOut.model_validate(task)


@router.post("/tasks/{task_id}/verify", response_model=VerdictOut)
async def verify(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    provider: LLMProvider = Depends(get_task_provider),
) -> VerdictOut:
    try:
        task = await loop_svc.verify_task(session, task_id, provider, _settings)
    except loop_svc.TaskNotFound:
        raise _task_404(task_id)
    await session.commit()
    proof = (await session.execute(
        select(Proof).where(Proof.task_id == task_id).order_by(Proof.created_at.desc())
    )).scalars().first()
    return VerdictOut(
        task_id=task_id,
        status=task.status,
        verdict=proof.verdict if proof else None,
        confidence=proof.confidence if proof else None,
        reasoning=proof.reasoning if proof else "",
    )


@router.post("/profile/{profile_id}/tasks/sweep-missed")
async def sweep(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    missed = await loop_svc.sweep_missed(session, profile_id)
    await session.commit()
    return {"missed": missed}
```

- [ ] **Step 3d: Mount** in `backend/app/main.py`: add `from app.api.tasks import router as tasks_router` with the other router imports and `app.include_router(tasks_router)` with the others. Do not disturb existing routes.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/api/test_tasks_api.py -v`
Expected: PASS (3 tests). Then full suite for no regressions.

- [ ] **Step 5: Commit**
```bash
git add backend/app/schemas/task.py backend/app/api/tasks.py backend/app/main.py \
        backend/tests/api/test_tasks_api.py
git commit -m "feat: add task loop REST endpoints (assign/start/proof/verify/sweep)"
```

---

## Task 8: Verification eval harness

**Files:**
- Create: `backend/tests/loop/fixtures.py`, `backend/tests/loop/test_verification_eval.py`

The harness pins the **deterministic** verification contract (spec §10): routing by proof requirement, timer math, the vision-off auto-pass invariant, and strict parsing of a scripted honor verdict. (Scoring a real LLM's judgement quality is non-deterministic and out of automated CI scope.)

- [ ] **Step 1: Write the fixtures** — `backend/tests/loop/fixtures.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class HonorCase:
    name: str
    report: str
    scripted_json: str
    expected_verdict: str


# Golden honor-verification cases: the model's scripted JSON is what a strict verifier
# *should* return; the harness asserts our parsing + routing produce that verdict.
HONOR_CASES: tuple[HonorCase, ...] = (
    HonorCase(
        name="detailed_pass",
        report="I made the bed: hospital corners, pillows squared, throw folded.",
        scripted_json='{"verdict": "pass", "confidence": 90, "reasoning": "specific", "issues": []}',
        expected_verdict="pass",
    ),
    HonorCase(
        name="vague_fail",
        report="yeah did it",
        scripted_json='{"verdict": "fail", "confidence": 25, "reasoning": "no specifics", "issues": ["vague"]}',
        expected_verdict="fail",
    ),
    HonorCase(
        name="evasive_reproof",
        report="mostly, will finish later",
        scripted_json='{"verdict": "re_proof", "confidence": 40, "reasoning": "incomplete", "issues": ["partial"]}',
        expected_verdict="re_proof",
    ),
    HonorCase(
        name="garbage_response_reproof",
        report="done",
        scripted_json="sure, looks fine to me",  # unparseable -> must become re_proof
        expected_verdict="re_proof",
    ),
)
```

- [ ] **Step 2: Write the eval test** — `backend/tests/loop/test_verification_eval.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.db.enums import ProofRequirement
from app.db.models.loop import TaskTimer
from app.db.models.task import Task
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.loop.verification import verify
from tests.loop.fixtures import HONOR_CASES


@pytest.mark.parametrize("case", HONOR_CASES, ids=lambda c: c.name)
async def test_honor_verdict_parsing_matches_golden(case):
    provider = MockLLMProvider(scripted=[ChatResult(content=case.scripted_json)])
    task = Task(description="t", proof_requirement=ProofRequirement.HONOR)
    v = await verify(task, report=case.report, timer=None, provider=provider, settings=Settings())
    assert v.verdict == case.expected_verdict


async def test_timer_route_is_deterministic_no_llm():
    start = datetime.now(timezone.utc)
    timer = TaskTimer(required_seconds=300, started_at=start, stopped_at=start + timedelta(seconds=301))
    task = Task(description="t", proof_requirement=ProofRequirement.TIMER)
    provider = MockLLMProvider(scripted=[])  # must not be called
    v = await verify(task, report="", timer=timer, provider=provider, settings=Settings())
    assert v.verdict == "pass"
    assert provider.calls == []


async def test_media_autopass_invariant_without_vision():
    task = Task(description="t", proof_requirement=ProofRequirement.PHOTO)
    v = await verify(task, report="", timer=None,
                     provider=MockLLMProvider(), settings=Settings(vision_model=None))
    assert v.verdict == "pass"  # configurable-vision seam: auto-pass when no vision model
```

- [ ] **Step 3: Run to verify it passes**

Run: `uv run pytest tests/loop/test_verification_eval.py -v`
Expected: PASS (4 honor cases + 2 = 6 cases).

- [ ] **Step 4: Commit**
```bash
git add backend/tests/loop/fixtures.py backend/tests/loop/test_verification_eval.py
git commit -m "test: add verification eval harness (routing, timer math, honor parsing, vision-off)"
```

---

## Task 9: Full verification + milestone wrap

**Files:** none (verification only).

- [ ] **Step 1: Infra up** — `docker compose up -d`.
- [ ] **Step 2: Full suite** — `uv run pytest -q`. Expected: all M1–M6 tests pass (107 from M5 + the new loop model/verification/service/sweep/eval/api tests; the gated Graphiti IT still skips).
- [ ] **Step 3: Lint** — `uv run ruff check .`. Fix any unused imports (esp. the test-import adjustments in Task 7) / E501.
- [ ] **Step 4: Push + CI green**
```bash
git push -u origin feat/m6-the-loop
```
Both jobs must pass (no vision model in CI → media auto-pass; honor uses the mock; Postgres service runs the DB tests).
- [ ] **Step 5: Open the PR**
```bash
gh pr create --base master --head feat/m6-the-loop \
  --title "M6: The Loop — task lifecycle + configurable strict verification" \
  --body "Implements spec §6 (sliced: media upload + real vision are M6b). See docs/superpowers/plans/2026-06-07-core-obedience-loop-m6-the-loop.md"
```

---

## Verification (end-to-end for Milestone 6)

1. **Infra up:** `docker compose up -d`.
2. **Suite green:** `uv run pytest -q` — loop models + migration round-trip, verification routes (timer/none/media/honor + parsing), loop service (assign/start/submit/verify/sweep), the REST endpoints, and the eval harness.
3. **Lint clean:** `uv run ruff check .`.
4. **The loop runs end-to-end via the API:** assign a honor task → start → submit proof → verify (scripted strict pass) → `verified_pass`; assign a timer task → start → (elapsed) → submit → verify → `verified_pass`/`verified_fail` by the math; an overdue un-submitted task → `sweep-missed` → `missed`. Each assign/verify/miss enqueues a Graphiti episode (M5 outbox), and the resulting statuses feed M4's disposition as recent outcomes.
5. **Configurable vision holds:** a photo/video task auto-passes when no vision model is configured.
6. **CI green** on the pushed branch.

**Milestone 6 is done when:** tasks move through the full lifecycle via explicit services + endpoints, the three proof routes verify correctly (timer deterministic, honor via strict LLM judgement, photo/video auto-pass under the configurable-vision seam), outcomes are recorded and emitted as Graphiti episodes, and the eval harness pins the deterministic verification contract — giving M7 verified-pass/fail/missed outcomes (with merit stakes on each task) to apply economy consequences to, and M6b the seam to add media upload + real vision verification.

---

## Self-Review

**Spec coverage (§6 + §2 vision + §10 eval):**
- Task lifecycle assigned→in_progress→proof_submitted→verifying→verified_pass/fail; deadline→missed → Tasks 4/5/6 (status transitions) + the existing `TaskStatus`. ✓
- Task carries description, proof requirement, deadline, merit stakes → uses the M2 `Task`; `assign_task` sets them. ✓
- Created via assign_task (derived from goals/profile) → Task 4 (`assign_task`; goal-derivation is a caller concern / future). ✓ (mechanism)
- Proof routes to a VerificationService; photo/video → vision rubric `{pass, confidence, reasoning, issues}`, low confidence → re-proof; **no vision model → auto-pass** → Tasks 2/3 (`verify_media` auto-pass; the real rubric call is **M6b**; `VerdictResult` carries verdict/confidence/reasoning/issues). ✓ (seam; real image call deferred per slice)
- Timer → server-side timestamps, deterministic → Tasks 1/2/4/5 (`TaskTimer` start/stop; `verify_timer`). ✓
- Honor → written report interrogated strictly, pass/fail → Task 3 (`verify_honor` strict LLM verdict + parse). ✓ (single-shot strict judgement; multi-turn interrogation is a chat-integration follow-up)
- React fires consequences (adjust merit, economy, denial, aftercare) → **merit/economy is M7** (documented `TODO(M7)` hook in `verify_task`); aftercare/denial are M7/M8. M6 records the outcome + a Graphiti episode. ✓ (scoped)
- Every outcome logged to Postgres + Graphiti episode → Task 4/5/6 (`enqueue_episode` on assign/verify/miss) — fulfils the M5 task/proof/reaction seam. ✓
- Verification eval harness (§10) → Task 8. ✓
- Autonomous LLM tool-calling → deferred (explicit endpoints per the locked decision). ✓ (scoped)

**Placeholder scan:** complete code per step; the one cross-task note (Task 7 test import adjustment for `get_task_provider`) is spelled out explicitly; no TODO except the intentional `TODO(M7)` merit hook.

**Type consistency:** `VerdictResult` (verdict/confidence/reasoning/issues) is produced by all `verify_*` and consumed identically by `verify_task`. `verify(task, *, report, timer, provider, settings)` matches its callers (service + eval). Loop service names (`assign_task`/`start_task`/`submit_proof`/`verify_task`/`sweep_missed`/`TaskNotFound`) match the endpoints and tests. `Proof`/`TaskTimer` fields match the model, migration, service, and `VerdictOut`/`TaskOut` schemas. The verdict string constants (`PASS`/`FAIL`/`RE_PROOF`/`PENDING`) are shared between `verification.py` and `verify_task`.

---

## Notes for execution
- **Branch:** `feat/m6-the-loop` (not `master`).
- **M7 boundary:** M6 transitions status only; it does **not** mutate merit/economy. The `TODO(M7)` in `verify_task` is where the economy service will apply stakes. Disposition (M4) already reflects M6 outcomes via recent task statuses.
- **No PG enums added** (Proof.verdict is a String) → the migration is a plain two-table create/drop, no DROP TYPE.
- **Configurable vision:** the media route's live path in M6 is auto-pass (no vision model, the default). The pending/real-rubric path is **M6b**, along with media upload to local disk (size/type caps + disk guard per §10).
- **Graphiti episodes** ride the M5 outbox (`enqueue_episode`) — durable, default-off store, no FalkorDB needed in tests/CI.
- **Local dev caveat:** clear `PYTHONHOME`/`PYTHONPATH` before `uv`. CI unaffected.
- **Frontend (Addendum A):** none here; the Today/Task and Standing spokes consume these endpoints in the frontend milestone.
