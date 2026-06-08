# Offline-First Milestone 2 — Drone Engine & Offline Dossier Surface — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the LLM is offline, replace the live-chat home with a deterministic "standing orders" surface: cold, mechanical **drone** notices (assignment + reminder duty-units) read from existing authoritative state, with chat dimmed ("she is away").

**Architecture:** A backend `drones` service produces deterministic, hand-written, state-keyed notices from existing data (active task, denial timers) — no LLM, no new content generation. A new `GET /profile/{id}/standing-orders` exposes them. The frontend reads availability (`GET /llm/availability`, from M1) and switches the home surface: **online → existing chat**; **offline → DossierBar + StandingOrders + a disabled composer**. The live-chat 503 (from M1) is also caught client-side to flip to the offline surface mid-session.

**Tech Stack:** Backend — Python 3.12, FastAPI, SQLAlchemy 2.0 async, pytest (`asyncio_mode=auto`, live Postgres `smistress_test`), ruff (line-length 100). Frontend — SvelteKit 2 + Svelte 5 runes, TypeScript, Vitest + @testing-library/svelte (jsdom), Playwright (API mocked via `page.route`).

**Scope note (honest to Addendum B):** M2 surfaces drones over **existing** state only. The LLM **batch-generated** content pools (task pool / drone line bank / punishment pool / standing orders) are **M3**; the **debt/punishment discipline unit** is **M4**. So M2 implements exactly two duty-units — **assignment** (surfaces the active task, or its absence) and **reminder** (denial timers + task-deadline proximity) — with hand-written templated lines.

**Local dev caveats:**
- Backend: run `uv`/`pytest` from `backend/`. On this Windows box clear two env vars before EVERY `uv` call, via **PowerShell**: `$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest ...`. Live Postgres is available; tests use `smistress_test`.
- Frontend: run from `frontend/`. `npm run test` (vitest), `npm run check` (svelte-check), `npm run build`. **Playwright browser install hangs on this box** — do NOT run `npm run test:e2e` locally; the CI `e2e` job is the authoritative Playwright gate. Write the e2e spec, verify it by inspection, and rely on CI.
- git from repo root with repo-root-relative paths. Work on a feature branch (the executor's worktree/branch), never `master`.

---

### Task 1: Drone service — assignment unit

**Files:**
- Create: `backend/app/drones/__init__.py` (empty)
- Create: `backend/app/drones/service.py`
- Test: `backend/tests/drones/__init__.py` (empty)
- Test: `backend/tests/drones/test_drone_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/drones/__init__.py` (empty file).

Create `backend/tests/drones/test_drone_service.py`:

```python
from datetime import datetime, timedelta, timezone

from app.drones import service as drone_svc
from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.task import Task
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_assignment_notice_when_no_active_task(session):
    p = await _profile(session)
    notices = await drone_svc.standing_orders(session, p.id)
    assert notices[0].unit == "assignment"
    assert "no standing assignment" in notices[0].line.lower()


async def test_assignment_notice_surfaces_active_task(session):
    p = await _profile(session)
    session.add(
        Task(
            profile_id=p.id,
            description="Posture drill",
            proof_requirement=ProofRequirement.HONOR,
            status=TaskStatus.ASSIGNED,
        )
    )
    await session.flush()
    notices = await drone_svc.standing_orders(session, p.id)
    assignment = [n for n in notices if n.unit == "assignment"]
    assert len(assignment) == 1
    assert "Posture drill" in assignment[0].line
    assert "mistress has assigned" in assignment[0].line.lower()


async def test_standing_orders_raises_for_unknown_profile(session):
    import uuid

    import pytest

    with pytest.raises(profile_svc.ProfileNotFound):
        await drone_svc.standing_orders(session, uuid.uuid4())
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/drones/test_drone_service.py -v`
Expected: FAIL with `ModuleNotFoundError: app.drones`.

- [ ] **Step 3: Write the service (assignment unit only for now)**

Create `backend/app/drones/__init__.py` (empty file).

Create `backend/app/drones/service.py`:

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import TaskStatus
from app.db.models.task import Task
from app.services import profile as profile_svc

# Task statuses that count as a live, outstanding assignment (mirrors app.chat.service).
_ACTIVE_STATUSES = (
    TaskStatus.ASSIGNED,
    TaskStatus.IN_PROGRESS,
    TaskStatus.PROOF_SUBMITTED,
    TaskStatus.VERIFYING,
)


@dataclass
class DroneNotice:
    """One cold, mechanical line from a drone duty-unit (Addendum B3)."""

    unit: str  # "assignment" | "reminder"
    line: str


def _assignment_line(task: Task | None) -> str:
    if task is None:
        return "No standing assignment. Await Mistress's instruction."
    return f"Mistress has assigned: {task.description}. Report when complete."


async def _active_task(session: AsyncSession, profile_id: uuid.UUID) -> Task | None:
    return (await session.execute(
        select(Task)
        .where(Task.profile_id == profile_id, Task.status.in_(_ACTIVE_STATUSES))
        .order_by(Task.created_at.desc())
        .limit(1)
    )).scalars().first()


async def standing_orders(
    session: AsyncSession, profile_id: uuid.UUID, *, now: datetime | None = None
) -> list[DroneNotice]:
    """Deterministic offline notices from existing state (Addendum B3).

    No LLM and no content generation: the drones only surface what is already
    true. ``now`` is injectable for deterministic deadline tests.
    """
    now = now or datetime.now(timezone.utc)
    await profile_svc.get_profile(session, profile_id)  # raises ProfileNotFound
    task = await _active_task(session, profile_id)
    notices = [DroneNotice(unit="assignment", line=_assignment_line(task))]
    return notices
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/drones/test_drone_service.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/drones backend/tests/drones
git commit -m "feat(drones): assignment-unit standing-orders service"
```

---

### Task 2: Drone service — reminder unit (denial timers + deadline proximity)

**Files:**
- Modify: `backend/app/drones/service.py`
- Test: `backend/tests/drones/test_drone_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/drones/test_drone_service.py`:

```python
async def test_reminder_notice_for_active_denial_timer(session):
    from app.economy import service as econ_svc

    p = await _profile(session)
    ends = datetime.now(timezone.utc) + timedelta(hours=8)
    await econ_svc.set_denial_timer(session, p.id, reason="overnight discipline", ends_at=ends)
    notices = await drone_svc.standing_orders(session, p.id)
    reminders = [n for n in notices if n.unit == "reminder"]
    assert any("denial" in n.line.lower() for n in reminders)
    assert any("overnight discipline" in n.line for n in reminders)


async def test_reminder_notice_for_passed_deadline(session):
    p = await _profile(session)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    session.add(
        Task(
            profile_id=p.id,
            description="Late drill",
            proof_requirement=ProofRequirement.HONOR,
            status=TaskStatus.ASSIGNED,
            deadline=past,
        )
    )
    await session.flush()
    notices = await drone_svc.standing_orders(session, p.id)
    reminders = [n for n in notices if n.unit == "reminder"]
    assert any("deadline has passed" in n.line.lower() for n in reminders)


async def test_reminder_notice_for_deadline_due_soon(session):
    p = await _profile(session)
    soon = datetime.now(timezone.utc) + timedelta(hours=3)
    session.add(
        Task(
            profile_id=p.id,
            description="Soon drill",
            proof_requirement=ProofRequirement.HONOR,
            status=TaskStatus.ASSIGNED,
            deadline=soon,
        )
    )
    await session.flush()
    notices = await drone_svc.standing_orders(session, p.id)
    reminders = [n for n in notices if n.unit == "reminder"]
    assert any("due within the day" in n.line.lower() for n in reminders)


async def test_no_reminder_when_no_timers_or_deadline(session):
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
    assert [n for n in notices if n.unit == "reminder"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/drones/test_drone_service.py -v`
Expected: the 4 new tests FAIL (no reminder notices produced yet); the 3 Task-1 tests still PASS.

- [ ] **Step 3: Extend the service with the reminder unit**

In `backend/app/drones/service.py`, update the imports to add `timedelta` and the economy service:

```python
from datetime import datetime, timedelta, timezone
```

and (with the other `app.` imports):

```python
from app.db.models.economy import DenialTimer
from app.economy import service as econ_svc
```

Add the deadline window constant near `_ACTIVE_STATUSES`:

```python
# A task deadline within this window earns a "due soon" reminder.
_DUE_SOON = timedelta(hours=24)
```

Add the reminder helper (after `_assignment_line`):

```python
def _reminder_lines(
    timers: list[DenialTimer], task: Task | None, now: datetime
) -> list[str]:
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
```

Update `standing_orders` to append reminder notices (replace the `notices = [...]; return notices` tail):

```python
    task = await _active_task(session, profile_id)
    timers = await econ_svc.active_denial_timers(session, profile_id)
    notices = [DroneNotice(unit="assignment", line=_assignment_line(task))]
    notices += [
        DroneNotice(unit="reminder", line=line)
        for line in _reminder_lines(timers, task, now)
    ]
    return notices
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/drones/test_drone_service.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/drones/service.py backend/tests/drones/test_drone_service.py
git commit -m "feat(drones): reminder-unit notices for denial timers and deadlines"
```

---

### Task 3: Standing-orders schema + API endpoint

**Files:**
- Create: `backend/app/schemas/drones.py`
- Create: `backend/app/api/drones.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_drones_api.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/api/test_drones_api.py`:

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
    assert r.status_code == 201
    return r.json()["id"]


async def test_standing_orders_returns_assignment_notice(client):
    pid = await _new_profile(client)
    r = await client.get(f"/profile/{pid}/standing-orders")
    assert r.status_code == 200
    notices = r.json()["notices"]
    assert notices[0]["unit"] == "assignment"
    assert "no standing assignment" in notices[0]["line"].lower()


async def test_standing_orders_404_for_unknown_profile(client):
    r = await client.get(f"/profile/{uuid.uuid4()}/standing-orders")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/api/test_drones_api.py -v`
Expected: FAIL — route returns 404 for the valid-profile case too (endpoint not registered).

- [ ] **Step 3: Write the schema**

Create `backend/app/schemas/drones.py`:

```python
from __future__ import annotations

from pydantic import BaseModel


class DroneNoticeOut(BaseModel):
    unit: str
    line: str


class StandingOrdersOut(BaseModel):
    notices: list[DroneNoticeOut]
```

- [ ] **Step 4: Write the API router**

Create `backend/app/api/drones.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.drones import service as drone_svc
from app.schemas.drones import DroneNoticeOut, StandingOrdersOut
from app.services import profile as profile_svc

router = APIRouter(prefix="/profile", tags=["drones"])


@router.get("/{profile_id}/standing-orders", response_model=StandingOrdersOut)
async def standing_orders(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> StandingOrdersOut:
    try:
        notices = await drone_svc.standing_orders(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"profile {profile_id} not found"
        )
    return StandingOrdersOut(
        notices=[DroneNoticeOut(unit=n.unit, line=n.line) for n in notices]
    )
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, add the import alongside the other routers:

```python
from app.api.drones import router as drones_router
```

and include it (after `availability_router`):

```python
app.include_router(drones_router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest tests/api/test_drones_api.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/drones.py backend/app/api/drones.py backend/app/main.py backend/tests/api/test_drones_api.py
git commit -m "feat(api): GET /profile/{id}/standing-orders endpoint"
```

---

### Task 4: Frontend — availability & drones API modules + stores

**Files:**
- Create: `frontend/src/lib/api/availability.ts`
- Create: `frontend/src/lib/api/drones.ts`
- Create: `frontend/src/lib/stores/availability.svelte.ts`
- Create: `frontend/src/lib/stores/drones.svelte.ts`
- Test: `frontend/src/lib/stores/availability.test.ts`
- Test: `frontend/src/lib/stores/drones.test.ts`

All frontend commands run from `frontend/`.

- [ ] **Step 1: Write the failing store tests**

Create `frontend/src/lib/stores/availability.test.ts`:

```typescript
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/availability', () => ({
  getAvailability: vi.fn()
}));

import { getAvailability } from '$lib/api/availability';
import { availability } from './availability.svelte';

beforeEach(() => {
  availability.online = false;
  vi.clearAllMocks();
});

test('refresh sets online from the api', async () => {
  (getAvailability as ReturnType<typeof vi.fn>).mockResolvedValue({
    state: 'online',
    online: true,
    last_heartbeat_at: 'now'
  });
  await availability.refresh();
  expect(availability.online).toBe(true);
});

test('refresh treats an api error as offline', async () => {
  (getAvailability as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'));
  availability.online = true;
  await availability.refresh();
  expect(availability.online).toBe(false);
});

test('setOffline flips online to false', () => {
  availability.online = true;
  availability.setOffline();
  expect(availability.online).toBe(false);
});
```

Create `frontend/src/lib/stores/drones.test.ts`:

```typescript
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/drones', () => ({
  getStandingOrders: vi.fn()
}));

import { getStandingOrders } from '$lib/api/drones';
import { drones } from './drones.svelte';
import { session } from './session.svelte';

beforeEach(() => {
  drones.notices = [];
  session.setProfileId('p1');
  vi.clearAllMocks();
});

test('refresh loads notices for the current profile', async () => {
  (getStandingOrders as ReturnType<typeof vi.fn>).mockResolvedValue({
    notices: [{ unit: 'assignment', line: 'No standing assignment.' }]
  });
  await drones.refresh();
  expect(drones.notices).toEqual([{ unit: 'assignment', line: 'No standing assignment.' }]);
});

test('refresh is a no-op without a profile', async () => {
  session.setProfileId('');
  await drones.refresh();
  expect(getStandingOrders).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run src/lib/stores/availability.test.ts src/lib/stores/drones.test.ts`
Expected: FAIL — cannot resolve `./availability.svelte` / `./drones.svelte` (and their api modules).

- [ ] **Step 3: Write the API modules**

Create `frontend/src/lib/api/availability.ts`:

```typescript
import { api } from './client';

export interface Availability {
  state: string;
  online: boolean;
  last_heartbeat_at: string | null;
}

// System-wide (single-user); not scoped to a profile.
export const getAvailability = () => api.get('/api/llm/availability') as Promise<Availability>;
```

Create `frontend/src/lib/api/drones.ts`:

```typescript
import { api } from './client';

export interface DroneNotice {
  unit: string;
  line: string;
}

export interface StandingOrders {
  notices: DroneNotice[];
}

export const getStandingOrders = (id: string) =>
  api.get(`/api/profile/${id}/standing-orders`) as Promise<StandingOrders>;
```

- [ ] **Step 4: Write the stores**

Create `frontend/src/lib/stores/availability.svelte.ts`:

```typescript
import { getAvailability } from '$lib/api/availability';

// System-wide presence of the home-box LLM (Addendum B2). The home surface
// switches on this: online -> live chat; offline -> the drone standing-orders.
class Availability {
  online = $state(false);

  async refresh() {
    try {
      this.online = (await getAvailability()).online;
    } catch {
      this.online = false; // unreachable backend reads as offline
    }
  }

  setOffline() {
    this.online = false;
  }
}

export const availability = new Availability();
```

Create `frontend/src/lib/stores/drones.svelte.ts`:

```typescript
import { getStandingOrders, type DroneNotice } from '$lib/api/drones';
import { session } from './session.svelte';

class Drones {
  notices = $state<DroneNotice[]>([]);

  async refresh() {
    const pid = session.profileId;
    if (!pid) return;
    this.notices = (await getStandingOrders(pid)).notices;
  }
}

export const drones = new Drones();
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npx vitest run src/lib/stores/availability.test.ts src/lib/stores/drones.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api/availability.ts frontend/src/lib/api/drones.ts frontend/src/lib/stores/availability.svelte.ts frontend/src/lib/stores/drones.svelte.ts frontend/src/lib/stores/availability.test.ts frontend/src/lib/stores/drones.test.ts
git commit -m "feat(frontend): availability + drones api modules and stores"
```

---

### Task 5: Frontend — StandingOrders component

**Files:**
- Create: `frontend/src/lib/offline/StandingOrders.svelte`
- Test: `frontend/src/lib/offline/StandingOrders.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/offline/StandingOrders.test.ts`:

```typescript
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';

import StandingOrders from './StandingOrders.svelte';

test('renders the away header and each drone notice', () => {
  render(StandingOrders, {
    notices: [
      { unit: 'assignment', line: 'Mistress has assigned: Posture drill. Report when complete.' },
      { unit: 'reminder', line: 'Denial remains in effect. Endure it until she lifts it.' }
    ]
  });
  expect(screen.getByText(/she is away/i)).toBeInTheDocument();
  expect(screen.getByText(/Posture drill/)).toBeInTheDocument();
  expect(screen.getByText(/Denial remains in effect/)).toBeInTheDocument();
  // unit labels are surfaced
  expect(screen.getByText('assignment')).toBeInTheDocument();
  expect(screen.getByText('reminder')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/offline/StandingOrders.test.ts`
Expected: FAIL — cannot resolve `./StandingOrders.svelte`.

- [ ] **Step 3: Write the component**

Create `frontend/src/lib/offline/StandingOrders.svelte`:

```svelte
<script lang="ts">
  import type { DroneNotice } from '$lib/api/drones';
  let { notices }: { notices: DroneNotice[] } = $props();
</script>

<section class="orders">
  <p class="away label">She is away. Her drones hold your standing orders.</p>
  {#each notices as n, i (i)}
    <div class="notice">
      <span class="unit">{n.unit}</span>
      <span class="line">{n.line}</span>
    </div>
  {/each}
</section>

<style>
  .orders {
    max-width: 720px;
    width: 100%;
    margin: 0 auto;
    padding: 16px;
  }
  .away {
    color: var(--muted);
    margin: 8px 0 16px;
  }
  /* Cold, mechanical: gray, monospace, unit-labeled — deliberately unlike her
     crimson-hairline bubbles, so her live presence reads as earned (Addendum B3). */
  .notice {
    display: flex;
    gap: 12px;
    align-items: baseline;
    background: var(--raised);
    border-left: 2px solid var(--muted);
    padding: 10px 14px;
    margin: 8px 0;
    font-family: var(--font-mono);
  }
  .unit {
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.7rem;
    color: var(--muted);
    flex: 0 0 auto;
  }
  .line {
    color: var(--paper);
    font-size: 0.85rem;
    line-height: 1.5;
  }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/offline/StandingOrders.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/offline/StandingOrders.svelte frontend/src/lib/offline/StandingOrders.test.ts
git commit -m "feat(frontend): cold drone StandingOrders component"
```

---

### Task 6: Frontend — availability-gated home surface

**Files:**
- Modify: `frontend/src/routes/+page.svelte`
- Test: `frontend/src/routes/page.test.ts`

- [ ] **Step 1: Update the home-page tests (online keeps chat; offline shows drones)**

Replace the entire contents of `frontend/src/routes/page.test.ts` with:

```typescript
import { render, screen } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/chat', () => ({
  getMessages: vi.fn(async () => []),
  sendMessage: vi.fn(async (_id, content) => ({
    id: '2',
    role: 'assistant',
    content: 'Acknowledged.',
    created_at: 'now'
  }))
}));
vi.mock('$lib/api/dossier', () => ({
  getDossier: vi.fn(async () => ({
    rank: 'novice',
    merit: 0,
    tokens: 0,
    disposition: { band: 'cool', line: 'cool · exacting — no recent activity', reason: 'x', standing: 30 },
    active_task: null,
    denial_timers: 0
  }))
}));
vi.mock('$lib/api/availability', () => ({
  getAvailability: vi.fn()
}));
vi.mock('$lib/api/drones', () => ({
  getStandingOrders: vi.fn(async () => ({
    notices: [{ unit: 'assignment', line: 'No standing assignment. Await Mistress.' }]
  }))
}));
vi.mock('$lib/api/safety', () => ({
  safeword: vi.fn(async () => ({
    scene_halted: true,
    denial_lifted: 0,
    merit_penalty: 0,
    aftercare: 'rest',
    message: 'stopping'
  })),
  resume: vi.fn(),
  getSafety: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: false }))
}));

import Page from './+page.svelte';
import { session } from '$lib/stores/session.svelte';
import { chat } from '$lib/stores/chat.svelte';
import { getAvailability } from '$lib/api/availability';

beforeEach(() => {
  session.setProfileId('p1');
  chat.messages = [];
  vi.clearAllMocks();
});

test('online: shows the dossier and sends a message', async () => {
  (getAvailability as ReturnType<typeof vi.fn>).mockResolvedValue({
    state: 'online',
    online: true,
    last_heartbeat_at: 'now'
  });
  render(Page);
  expect(await screen.findByText(/cool · exacting/)).toBeInTheDocument();

  const input = screen.getByPlaceholderText(/say something/i) as HTMLTextAreaElement;
  input.value = 'what now?';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  screen.getByRole('button', { name: /send/i }).click();

  expect(await screen.findByText('Acknowledged.')).toBeInTheDocument();
});

test('offline: shows drone standing orders and no chat composer', async () => {
  (getAvailability as ReturnType<typeof vi.fn>).mockResolvedValue({
    state: 'offline',
    online: false,
    last_heartbeat_at: null
  });
  render(Page);
  expect(await screen.findByText(/she is away/i)).toBeInTheDocument();
  expect(screen.getByText(/no standing assignment/i)).toBeInTheDocument();
  // the live composer is not rendered when she is away
  expect(screen.queryByPlaceholderText(/say something/i)).toBeNull();
});
```

- [ ] **Step 2: Run tests to verify the offline test fails**

Run: `npx vitest run src/routes/page.test.ts`
Expected: the offline test FAILS (the page always renders the chat composer today); the online test still PASSES.

- [ ] **Step 3: Rewrite the home page to switch surfaces on availability**

Replace the entire contents of `frontend/src/routes/+page.svelte` with:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores/session.svelte';
  import { chat } from '$lib/stores/chat.svelte';
  import { dossier } from '$lib/stores/dossier.svelte';
  import { availability } from '$lib/stores/availability.svelte';
  import { drones } from '$lib/stores/drones.svelte';
  import { safety } from '$lib/stores/safety.svelte';
  import { isSafeword } from '$lib/safety/phrases';
  import { ApiError } from '$lib/api/client';
  import Bubble from '$lib/design/components/Bubble.svelte';
  import ActionCard from '$lib/chat/ActionCard.svelte';
  import DossierBar from '$lib/chat/DossierBar.svelte';
  import StandingOrders from '$lib/offline/StandingOrders.svelte';

  let draft = $state('');

  onMount(async () => {
    if (!session.profileId) {
      await goto('/onboarding/consent');
      return;
    }
    await availability.refresh();
    await dossier.refresh();
    if (availability.online) await chat.load();
    else await drones.refresh();
  });

  async function send() {
    const text = draft.trim();
    if (!text) return;
    draft = '';
    // Typed safeword = emergency exit: intercept before any chat call (Addendum A6).
    if (isSafeword(text)) {
      await safety.confirmStop();
      return;
    }
    try {
      await chat.send(text);
      await dossier.refresh(); // her reply may have shifted standing
    } catch (e) {
      // She went offline mid-session (M1 gate -> 503): drop to the drone surface.
      if (e instanceof ApiError && e.status === 503) {
        availability.setOffline();
        await drones.refresh();
      } else {
        throw e;
      }
    }
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }
</script>

<div class="home">
  <DossierBar data={dossier.data} />

  {#if availability.online}
    <main class="stream">
      {#each chat.messages as m (m.id)}
        <Bubble role={m.role} content={m.content} />
        {#if m.action}
          <ActionCard action={m.action} />
        {/if}
      {/each}
      {#if chat.messages.length === 0}
        <p class="empty label">She is waiting. Say something.</p>
      {/if}
    </main>

    <footer class="composer">
      <textarea
        placeholder="Say something to her…"
        value={draft}
        oninput={(e) => (draft = (e.currentTarget as HTMLTextAreaElement).value)}
        onkeydown={onKey}
        rows="2"
      ></textarea>
      <button class="send" disabled={chat.sending} onclick={send}>Send</button>
    </footer>
  {:else}
    <main class="stream">
      <StandingOrders notices={drones.notices} />
    </main>
    <footer class="composer away">
      <p class="label">She is away — an audience requires her presence.</p>
    </footer>
  {/if}
</div>

<style>
  .home {
    display: flex;
    flex-direction: column;
    height: 100dvh;
  }
  .stream {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    max-width: 720px;
    width: 100%;
    margin: 0 auto;
    padding: 16px;
  }
  .empty {
    margin: auto;
    color: var(--muted);
  }
  .composer {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    border-top: 1px solid var(--hairline);
    max-width: 720px;
    width: 100%;
    margin: 0 auto;
  }
  .composer.away {
    justify-content: center;
    color: var(--muted);
  }
  textarea {
    flex: 1;
    background: var(--raised);
    color: var(--paper);
    border: 1px solid var(--hairline);
    padding: 10px;
    border-radius: 0;
    resize: none;
    font-family: var(--font-body);
  }
  .send {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: var(--paper);
    color: var(--ink);
    border: 0;
    padding: 0 20px;
    cursor: pointer;
  }
  .send:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run src/routes/page.test.ts`
Expected: PASS (both online and offline tests).

- [ ] **Step 5: Type-check**

Run: `npm run check`
Expected: svelte-check passes (0 errors). Fix any type errors before committing.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/+page.svelte frontend/src/routes/page.test.ts
git commit -m "feat(frontend): switch home to drone surface when she is offline"
```

---

### Task 7: E2E — offline surface (Playwright, API-mocked)

**Files:**
- Modify: `frontend/e2e/fixtures.ts` (add availability + standing-orders routes, default online)
- Create: `frontend/e2e/offline.spec.ts`

**Note:** Do NOT run Playwright locally (the browser install hangs on this box). Implement carefully and rely on the CI `e2e` job. After this task, the only verification is reading the code + CI.

- [ ] **Step 1: Extend the shared mock with the new routes (default online)**

In `frontend/e2e/fixtures.ts`, inside `mockApi`'s route handler, add these two handlers (place them near the other `path.endsWith(...)` checks, e.g. just before the `/messages` handler). Default availability is **online** so the existing chat/spokes specs keep working:

```javascript
    if (path.endsWith('/api/llm/availability') && method === 'GET')
      return json({ state: 'online', online: true, last_heartbeat_at: 'now' });
    if (path.endsWith('/standing-orders') && method === 'GET')
      return json({ notices: [{ unit: 'assignment', line: 'No standing assignment. Await Mistress.' }] });
```

- [ ] **Step 2: Write the offline e2e spec**

Create `frontend/e2e/offline.spec.ts`:

```typescript
import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => localStorage.setItem('smistress.profileId', 'e2e-profile'));
});

test('offline: home shows drone standing orders, not the chat composer', async ({ page }) => {
  // Override availability to offline (registered after mockApi -> takes precedence).
  await page.route('**/api/llm/availability', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ state: 'offline', online: false, last_heartbeat_at: null })
    })
  );
  await page.route('**/standing-orders', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        notices: [
          { unit: 'assignment', line: 'Mistress has assigned: Posture drill. Report when complete.' },
          { unit: 'reminder', line: 'Denial remains in effect. Endure it until she lifts it.' }
        ]
      })
    })
  );

  await page.goto('/');
  await expect(page.getByText(/she is away/i)).toBeVisible();
  await expect(page.getByText('Mistress has assigned: Posture drill. Report when complete.')).toBeVisible();
  await expect(page.getByText(/an audience requires her presence/i)).toBeVisible();
  // no live composer when she is away
  await expect(page.getByPlaceholder(/say something/i)).toHaveCount(0);
});

test('online: home still shows the live chat composer', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByPlaceholder(/say something/i)).toBeVisible();
});
```

- [ ] **Step 3: Verify by inspection (local Playwright not available)**

Confirm by reading:
- `fixtures.ts` returns `online: true` for `/api/llm/availability` by default (so `chat.spec.ts`, `chat_actions.spec.ts`, `spokes.spec.ts` still exercise the online chat surface).
- `offline.spec.ts` registers its overrides AFTER `mockApi` so Playwright matches them first.
- The selectors match the component text from Tasks 5–6 ("she is away", the notice lines, "an audience requires her presence", the `say something` placeholder).

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/fixtures.ts frontend/e2e/offline.spec.ts
git commit -m "test(e2e): offline drone surface spec + availability mock"
```

---

### Task 8: Full verification & lint

**Files:** none (verification only)

- [ ] **Step 1: Backend suite + lint**

From `backend/`:
`$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run pytest -q`
Expected: all pass (existing + new drones service/API tests).
Then: `$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run ruff check .`
Expected: All checks passed. Fix any line-length>100 / import-order issues and re-run.

- [ ] **Step 2: Frontend unit tests + type-check + build**

From `frontend/`:
- `npm run test` → all vitest suites pass (incl. the new store/component/page tests).
- `npm run check` → svelte-check 0 errors.
- `npm run build` → production build succeeds.

- [ ] **Step 3: Push and confirm CI is green**

```bash
git push -u origin HEAD
```
Watch the three CI jobs: `backend` (Postgres), `frontend` (vitest + build), and `e2e` (Playwright — the authoritative gate for the offline spec, since it can't run locally). All must be green.

---

## Notes for the next milestones (not built here)

- **M3 — Batch generation (B4):** replaces the hand-written drone lines with LLM-generated pools (task pool, drone line bank, punishment pool, standing orders) produced in batch windows / at audience close. The `DroneNotice`/`standing_orders` shape stays; only the line *source* changes.
- **M4 — Debt/punishment (B7):** adds the **discipline** duty-unit and the debt ledger; the reminder unit's denial lines become part of a richer punishment surface.
- **Availability polling:** M2 refreshes availability on mount (and catches the live 503 mid-session). A periodic poll / visibility-change refresh can be added later if desired.
- **Committed OpenAPI types:** the frontend api modules hand-write their interfaces (matching `dossier.ts`/`chat.ts`), so `npm run gen:api` was intentionally not run here. Regenerate `src/lib/types/api.ts` in a later hygiene pass if the committed schema drift matters.
