# M5c — M5 Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the M5a supervision modes + M5b discreetness filter in the SvelteKit PWA (mode bottom-sheet, dossier mode badge + task tags, per-toy discreetness flags with edit), plus two small backend extensions and a generated-types resync.

**Architecture:** Backend gains a toy `PATCH` endpoint and three new read-only dossier fields. Frontend adds a `supervision` API client + rune store, a store-backed `ModeSheet` bottom sheet opened from the `DossierBar` mode badge, intensity/discreetness tags on the active-task line, three discreetness checkboxes on the `Toys` form (reused as an edit form on the Profile page), and a regenerated `openapi.json` / `src/lib/types/api.ts`.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / pytest (backend); SvelteKit 2 / Svelte 5 runes / Vitest + Testing-Library (frontend).

---

## Conventions for this plan

**Backend tests** (run from `backend/`, this machine's uv-trampoline workaround):
```
PYTHONHOME= PYTHONPATH= uv run python -m pytest <args> -q
```
Requires Postgres up (`docker compose up -d` from repo root). Services **flush**; endpoints **commit**. PG enums store member NAMES; the `discreetness` column is an `Enum(Discreetness)`.

**Frontend tests** (run from `frontend/`):
```
"C:\Program Files\nodejs\npm.cmd" run test -- <path>
```
Store-backed components are tested by `vi.mock`-ing the API module and driving the store directly (see `src/lib/safety/StopSheet.test.ts`).

**Commits:** one per task, end the message with:
```
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

## File Structure

**Backend**
- Modify `backend/app/schemas/onboarding.py` — add `ToyPatch`.
- Modify `backend/app/services/profile.py` — add `ToyNotFound` + `update_toy`.
- Modify `backend/app/api/profile.py` — add `PATCH /{profile_id}/toys/{toy_id}`.
- Modify `backend/app/schemas/chat.py` — extend `ActiveTask`, `DossierOut`.
- Modify `backend/app/chat/service.py` — populate new dossier fields in `build_dossier`.

**Frontend**
- Create `frontend/src/lib/api/supervision.ts` — API client + types.
- Create `frontend/src/lib/stores/supervision.svelte.ts` — rune store.
- Create `frontend/src/lib/chat/ModeSheet.svelte` (+ `.test.ts`) — mode bottom sheet.
- Modify `frontend/src/lib/api/dossier.ts` — extend `Dossier` type.
- Modify `frontend/src/lib/chat/DossierBar.svelte` (+ `.test.ts`) — mode badge + task tags + sheet.
- Modify `frontend/src/routes/+page.svelte` — refresh supervision on mount.
- Modify `frontend/src/lib/onboarding/Toys.svelte` (+ `.test.ts`) — 3 flags + `initial` prop.
- Modify `frontend/src/lib/api/profile.ts` — `updateToy`.
- Modify `frontend/src/routes/profile/+page.svelte` (+ `page.test.ts`) — per-toy flags + edit.
- Regenerate `frontend/openapi.json` + `frontend/src/lib/types/api.ts`.

---

## Task 1: Toy update — schema + service

**Files:**
- Modify: `backend/app/schemas/onboarding.py` (after `ToyOut`, ~line 81)
- Modify: `backend/app/services/profile.py` (add error class near `ProfileNotFound` ~line 37; add fn after `add_toy` ~line 158)
- Test: `backend/tests/services/test_profile_service.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/services/test_profile_service.py`:

```python
async def test_update_toy_patches_flags(session):
    from app.schemas.onboarding import ToyIn, ToyPatch
    from app.services import profile as svc

    p = await svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    toy = await svc.add_toy(session, p.id, ToyIn(name="Apex", type="vibrator"))
    await session.flush()

    updated = await svc.update_toy(
        session, p.id, toy.id, ToyPatch(discreet_capable=True, noise=True, name="Apex 2")
    )
    assert updated.discreet_capable is True
    assert updated.noise is True
    assert updated.visibility is False  # untouched
    assert updated.name == "Apex 2"


async def test_update_toy_wrong_profile_raises(session):
    import uuid

    import pytest

    from app.schemas.onboarding import ToyIn, ToyPatch
    from app.services import profile as svc

    p = await svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    toy = await svc.add_toy(session, p.id, ToyIn(name="Apex", type="vibrator"))
    await session.flush()

    with pytest.raises(svc.ToyNotFound):
        await svc.update_toy(session, uuid.uuid4(), toy.id, ToyPatch(noise=True))
```

Confirm `ProfileCreate` is already imported at the top of this test file; if not, add `from app.schemas.onboarding import ProfileCreate`.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/services/test_profile_service.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'update_toy'` / `ImportError: ToyPatch`.

- [ ] **Step 3: Add the `ToyPatch` schema**

In `backend/app/schemas/onboarding.py`, immediately after the `ToyOut` class:

```python
class ToyPatch(BaseModel):
    """Partial update for an existing toy — every field optional."""

    name: str | None = None
    type: ToyType | None = None
    notes: str | None = None
    intiface_capable: bool | None = None
    noise: bool | None = None
    visibility: bool | None = None
    discreet_capable: bool | None = None
```

- [ ] **Step 4: Add the error class + service function**

In `backend/app/services/profile.py`, add next to `ProfileNotFound`:

```python
class ToyNotFound(Exception):
    pass
```

Then after `add_toy` (and add `ToyPatch` to the `from app.schemas.onboarding import ...` line):

```python
async def update_toy(
    session: AsyncSession, profile_id: uuid.UUID, toy_id: uuid.UUID, patch: ToyPatch
) -> Toy:
    toy = (await session.execute(
        select(Toy).where(Toy.id == toy_id, Toy.profile_id == profile_id)
    )).scalar_one_or_none()
    if toy is None:
        raise ToyNotFound(f"toy {toy_id} not found for profile {profile_id}")
    data = patch.model_dump(exclude_unset=True)
    if "type" in data and data["type"] is not None:
        data["type"] = data["type"].value  # String column stores the plain enum value
    for field, value in data.items():
        setattr(toy, field, value)
    await session.flush()
    return toy
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/services/test_profile_service.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/onboarding.py backend/app/services/profile.py backend/tests/services/test_profile_service.py
git commit -m "feat(profile): update_toy service + ToyPatch schema"
```

---

## Task 2: Toy update — PATCH endpoint

**Files:**
- Modify: `backend/app/api/profile.py` (after `add_toy`, ~line 88; `ToyPatch` to the schema import line)
- Test: `backend/tests/api/test_profile_api.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/api/test_profile_api.py`:

```python
async def test_patch_toy_updates_flags(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/toys", json={"name": "Apex", "type": "vibrator"})
    toy_id = r.json()["id"]

    r = await client.patch(
        f"/profile/{pid}/toys/{toy_id}", json={"discreet_capable": True, "noise": True}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["discreet_capable"] is True
    assert body["noise"] is True
    assert body["visibility"] is False


async def test_patch_toy_unknown_id_404(client):
    pid = await _new_profile(client)
    r = await client.patch(f"/profile/{pid}/toys/{uuid.uuid4()}", json={"noise": True})
    assert r.status_code == 404
```

Confirm `import uuid` is present at the top of this test file; if not, add it.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/api/test_profile_api.py -q`
Expected: FAIL — `405 Method Not Allowed` (no PATCH route).

- [ ] **Step 3: Add the endpoint**

In `backend/app/api/profile.py`, add `ToyPatch` to the existing `from app.schemas.onboarding import ...` line, then add after the `add_toy` endpoint:

```python
@router.patch("/{profile_id}/toys/{toy_id}", response_model=ToyOut)
async def update_toy(
    profile_id: uuid.UUID,
    toy_id: uuid.UUID,
    body: ToyPatch,
    session: AsyncSession = Depends(get_session),
) -> ToyOut:
    try:
        toy = await svc.update_toy(session, profile_id, toy_id, body)
    except svc.ToyNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"toy {toy_id} not found"
        )
    await session.commit()
    return ToyOut.model_validate(toy)
```

Confirm `HTTPException` and `status` are already imported in this file (they are — used by `_not_found`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/api/test_profile_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/profile.py backend/tests/api/test_profile_api.py
git commit -m "feat(api): PATCH /profile/{id}/toys/{toy_id}"
```

---

## Task 3: Dossier surfacing — mode badge + task tags

**Files:**
- Modify: `backend/app/schemas/chat.py` (`ActiveTask` ~line 27; `DossierOut` ~line 40)
- Modify: `backend/app/chat/service.py` (`build_dossier` ~lines 68-94)
- Test: `backend/tests/chat/test_chat_service.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/chat/test_chat_service.py`:

```python
async def test_build_dossier_surfaces_mode_and_task_tags(session):
    from app.db.enums import Discreetness, SupervisionMode
    from app.db.models.task import Task
    from app.supervision import service as sup_svc

    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.DISCREET)
    session.add(
        Task(
            profile_id=p.id,
            description="Quiet kneel",
            intensity=40,
            discreetness=Discreetness.DISCREET,
        )
    )
    await session.flush()

    d = await chat_svc.build_dossier(session, p.id)
    assert d["supervision_mode"] == "discreet"
    assert d["active_task"]["intensity"] == 40
    assert d["active_task"]["discreetness"] == "discreet"


async def test_build_dossier_mode_defaults_to_full(session):
    p = await _profile(session)
    d = await chat_svc.build_dossier(session, p.id)
    assert d["supervision_mode"] == "full"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/chat/test_chat_service.py -q`
Expected: FAIL — `KeyError: 'supervision_mode'`.

- [ ] **Step 3: Extend the schemas**

In `backend/app/schemas/chat.py`, replace the `ActiveTask` class:

```python
class ActiveTask(BaseModel):
    description: str
    status: str
    intensity: int
    discreetness: str
```

and add a field to `DossierOut` (after `chastity`):

```python
    supervision_mode: str
```

- [ ] **Step 4: Populate the fields in `build_dossier`**

In `backend/app/chat/service.py`, add the supervision import at the top with the other service imports:

```python
from app.supervision import service as sup_svc
```

Then in `build_dossier`, after the `active = (...)` query, compute the mode and extend the returned dict. Replace the `active_task` entry and add `supervision_mode`:

```python
    mode = await sup_svc.get_mode(session, profile_id)
```
(place this line just before the `return {` statement), and update the dict:

```python
        "active_task": (
            {
                "description": active.description,
                "status": active.status.value,
                "intensity": active.intensity,
                "discreetness": active.discreetness.value,
            }
            if active is not None
            else None
        ),
        "supervision_mode": mode.value,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/chat/test_chat_service.py tests/api/test_chat_api.py -q`
Expected: PASS (the existing `test_build_dossier_*` tests still pass — they don't assert on the new keys).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/chat.py backend/app/chat/service.py backend/tests/chat/test_chat_service.py
git commit -m "feat(dossier): surface supervision mode + active-task tags"
```

---

## Task 4: Supervision API client + store

**Files:**
- Create: `frontend/src/lib/api/supervision.ts`
- Create: `frontend/src/lib/stores/supervision.svelte.ts`
- Test: `frontend/src/lib/api/supervision.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/api/supervision.test.ts`:

```ts
import { afterEach, expect, test, vi } from 'vitest';

vi.mock('./client', () => ({
  api: { get: vi.fn(), put: vi.fn() }
}));

import { api } from './client';
import { getSupervision, setMode, setNote } from './supervision';

afterEach(() => vi.clearAllMocks());

test('getSupervision GETs the supervision resource', () => {
  getSupervision('p1');
  expect(api.get).toHaveBeenCalledWith('/api/profile/p1/supervision');
});

test('setMode PUTs the chosen mode', () => {
  setMode('p1', 'discreet');
  expect(api.put).toHaveBeenCalledWith('/api/profile/p1/supervision/mode', { mode: 'discreet' });
});

test('setNote PUTs the mode + note', () => {
  setNote('p1', 'task', 'be quick');
  expect(api.put).toHaveBeenCalledWith('/api/profile/p1/supervision/note', {
    mode: 'task',
    note: 'be quick'
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"C:\Program Files\nodejs\npm.cmd" run test -- src/lib/api/supervision.test.ts`
Expected: FAIL — cannot resolve `./supervision`.

- [ ] **Step 3: Write the API client**

Create `frontend/src/lib/api/supervision.ts`:

```ts
import { api } from './client';

export type SupervisionMode = 'full' | 'discreet' | 'task' | 'homeoffice' | 'vacation';

export interface Supervision {
  mode: SupervisionMode;
  notes: Record<string, string>;
}

export const getSupervision = (id: string) =>
  api.get(`/api/profile/${id}/supervision`) as Promise<Supervision>;
export const setMode = (id: string, mode: SupervisionMode) =>
  api.put(`/api/profile/${id}/supervision/mode`, { mode }) as Promise<Supervision>;
export const setNote = (id: string, mode: SupervisionMode, note: string) =>
  api.put(`/api/profile/${id}/supervision/note`, { mode, note }) as Promise<Supervision>;
```

- [ ] **Step 4: Write the store**

Create `frontend/src/lib/stores/supervision.svelte.ts`:

```ts
import {
  getSupervision,
  setMode as apiSetMode,
  setNote as apiSetNote,
  type SupervisionMode
} from '$lib/api/supervision';
import { session } from './session.svelte';

class SupervisionStore {
  mode = $state<SupervisionMode>('full');
  notes = $state<Record<string, string>>({});

  async refresh() {
    const pid = session.profileId;
    if (!pid) return;
    const s = await getSupervision(pid);
    this.mode = s.mode;
    this.notes = s.notes;
  }
  async setMode(mode: SupervisionMode) {
    const pid = session.profileId;
    if (!pid) return;
    const s = await apiSetMode(pid, mode);
    this.mode = s.mode;
    this.notes = s.notes;
  }
  async setNote(mode: SupervisionMode, note: string) {
    const pid = session.profileId;
    if (!pid) return;
    const s = await apiSetNote(pid, mode, note);
    this.mode = s.mode;
    this.notes = s.notes;
  }
}

export const supervision = new SupervisionStore();
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `"C:\Program Files\nodejs\npm.cmd" run test -- src/lib/api/supervision.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api/supervision.ts frontend/src/lib/api/supervision.test.ts frontend/src/lib/stores/supervision.svelte.ts
git commit -m "feat(fe): supervision API client + store"
```

---

## Task 5: ModeSheet bottom sheet

**Files:**
- Create: `frontend/src/lib/chat/ModeSheet.svelte`
- Test: `frontend/src/lib/chat/ModeSheet.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/chat/ModeSheet.test.ts`:

```ts
import { render, screen } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/supervision', () => ({
  getSupervision: vi.fn(async () => ({ mode: 'full', notes: {} })),
  setMode: vi.fn(async (_id: string, mode: string) => ({ mode, notes: {} })),
  setNote: vi.fn(async () => ({ mode: 'full', notes: {} }))
}));
vi.mock('$lib/stores/dossier.svelte', () => ({
  dossier: { refresh: vi.fn(async () => {}) }
}));

import ModeSheet from './ModeSheet.svelte';
import { supervision } from '$lib/stores/supervision.svelte';
import { setMode } from '$lib/api/supervision';
import { session } from '$lib/stores/session.svelte';

beforeEach(() => {
  vi.clearAllMocks();
  session.setProfileId('p1');
  supervision.mode = 'full';
  supervision.notes = {};
});

test('renders nothing when closed', () => {
  render(ModeSheet, { open: false, onclose: () => {} });
  expect(screen.queryByText(/supervision/i)).not.toBeInTheDocument();
});

test('lists all modes and switches on click', async () => {
  render(ModeSheet, { open: true, onclose: () => {} });
  expect(screen.getByRole('button', { name: /discreet/i })).toBeInTheDocument();
  screen.getByRole('button', { name: /homeoffice/i }).click();
  await vi.waitFor(() => expect(setMode).toHaveBeenCalledWith('p1', 'homeoffice'));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"C:\Program Files\nodejs\npm.cmd" run test -- src/lib/chat/ModeSheet.test.ts`
Expected: FAIL — cannot resolve `./ModeSheet.svelte`.

- [ ] **Step 3: Write the component**

Create `frontend/src/lib/chat/ModeSheet.svelte`:

```svelte
<script lang="ts">
  import TextArea from '$lib/design/components/TextArea.svelte';
  import { supervision } from '$lib/stores/supervision.svelte';
  import { dossier } from '$lib/stores/dossier.svelte';
  import type { SupervisionMode } from '$lib/api/supervision';

  let { open = false, onclose }: { open?: boolean; onclose: () => void } = $props();

  const MODES: { value: SupervisionMode; label: string; meaning: string }[] = [
    { value: 'full', label: 'Full', meaning: 'Fully available — at her mercy anytime.' },
    { value: 'discreet', label: 'Discreet', meaning: 'Family around — quiet, low-visibility only.' },
    { value: 'task', label: 'Task', meaning: 'Tasks only, with graceful fulfilment timers.' },
    { value: 'homeoffice', label: 'Homeoffice', meaning: 'Meetings — fully covert content only.' },
    { value: 'vacation', label: 'Vacation', meaning: 'Training paused — economy frozen.' }
  ];

  let note = $state('');
  // Keep the note box in sync with the active mode's stored note.
  $effect(() => {
    note = supervision.notes[supervision.mode] ?? '';
  });

  async function choose(mode: SupervisionMode) {
    await supervision.setMode(mode);
    await dossier.refresh(); // badge reads the dossier
  }
  async function saveNote() {
    await supervision.setNote(supervision.mode, note);
  }
</script>

{#if open}
  <div class="scrim" role="dialog" aria-modal="true" aria-label="Supervision mode">
    <section class="sheet">
      <p class="label">Supervision mode</p>
      <ul class="modes">
        {#each MODES as m}
          <li>
            <button
              class="mode"
              class:active={supervision.mode === m.value}
              class:frozen={m.value === 'vacation'}
              onclick={() => choose(m.value)}
            >
              <span class="name">{m.label}</span>
              <span class="meaning">{m.meaning}</span>
            </button>
          </li>
        {/each}
      </ul>

      <TextArea
        label={`Note for "${supervision.mode}" mode`}
        value={note}
        oninput={(v) => (note = v)}
      />
      <div class="actions">
        <button class="ghost" onclick={onclose}>Close</button>
        <button onclick={saveNote}>Save note</button>
      </div>
    </section>
  </div>
{/if}

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 50;
    background: rgba(0, 0, 0, 0.85);
    display: flex;
    align-items: flex-end;
    justify-content: center;
    padding: 16px;
  }
  .sheet {
    background: var(--paper);
    color: var(--ink);
    max-width: 460px;
    width: 100%;
    padding: 24px;
  }
  .label {
    color: var(--accent);
  }
  .modes {
    list-style: none;
    padding: 0;
    display: grid;
    gap: 8px;
    margin: 12px 0;
  }
  .mode {
    width: 100%;
    text-align: left;
    display: grid;
    gap: 2px;
    background: transparent;
    border: 1px solid var(--hairline);
    color: var(--ink);
    padding: 10px 12px;
    cursor: pointer;
  }
  .mode.active {
    border-color: var(--accent);
    background: var(--accent);
    color: var(--paper);
  }
  .mode.frozen .name::after {
    content: ' · frozen';
    color: var(--accent);
  }
  .name {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .meaning {
    font-size: 0.8rem;
    color: var(--muted);
  }
  .mode.active .meaning {
    color: var(--paper);
  }
  .actions {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
    margin-top: 12px;
  }
  button {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    border: 1px solid var(--ink);
    background: var(--ink);
    color: var(--paper);
    padding: 10px 16px;
    cursor: pointer;
  }
  .ghost {
    background: transparent;
    color: var(--ink);
  }
</style>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `"C:\Program Files\nodejs\npm.cmd" run test -- src/lib/chat/ModeSheet.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/chat/ModeSheet.svelte frontend/src/lib/chat/ModeSheet.test.ts
git commit -m "feat(fe): ModeSheet supervision bottom sheet"
```

---

## Task 6: DossierBar — mode badge + task tags

**Files:**
- Modify: `frontend/src/lib/api/dossier.ts` (the `Dossier` interface)
- Modify: `frontend/src/lib/chat/DossierBar.svelte`
- Test: `frontend/src/lib/chat/DossierBar.test.ts`

- [ ] **Step 1: Update the type + write the failing test**

In `frontend/src/lib/api/dossier.ts`, extend the interface:

```ts
export interface Dossier {
  rank: string;
  merit: number;
  tokens: number;
  debt: number;
  disposition: { band: string; line: string; reason: string; standing: number };
  active_task: { description: string; status: string; intensity: number; discreetness: string } | null;
  chastity: { locked: boolean; ends_at: string | null; seconds_remaining: number };
  supervision_mode: string;
}
```

Replace `frontend/src/lib/chat/DossierBar.test.ts` with:

```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';

vi.mock('$lib/api/supervision', () => ({
  getSupervision: vi.fn(async () => ({ mode: 'full', notes: {} })),
  setMode: vi.fn(async () => ({ mode: 'full', notes: {} })),
  setNote: vi.fn(async () => ({ mode: 'full', notes: {} }))
}));
vi.mock('$lib/stores/dossier.svelte', () => ({ dossier: { refresh: vi.fn() } }));

import DossierBar from './DossierBar.svelte';

const data = {
  rank: 'adept',
  merit: 50,
  tokens: 3,
  disposition: {
    band: 'cool',
    line: 'cool · exacting — 2 recent misses',
    reason: '2 recent misses',
    standing: 30
  },
  active_task: { description: 'Posture drill', status: 'assigned', intensity: 40, discreetness: 'discreet' },
  debt: 0,
  chastity: { locked: false, ends_at: null, seconds_remaining: 0 },
  supervision_mode: 'discreet'
};

test('shows rank, disposition line, mode badge and task tags', () => {
  render(DossierBar, { data });
  expect(screen.getByText(/adept/i)).toBeInTheDocument();
  expect(screen.getByText(/cool · exacting/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /discreet/i })).toBeInTheDocument(); // mode badge
  expect(screen.getByText(/intensity 40/i)).toBeInTheDocument();
});

test('renders nothing-fatal when data is null', () => {
  render(DossierBar, { data: null });
  expect(screen.getByText(/…|loading/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"C:\Program Files\nodejs\npm.cmd" run test -- src/lib/chat/DossierBar.test.ts`
Expected: FAIL — no mode badge / no `intensity 40` text.

- [ ] **Step 3: Update DossierBar**

In `frontend/src/lib/chat/DossierBar.svelte`, replace the `<script>` block and the markup inside the `{:else}` branch. New `<script>`:

```svelte
<script lang="ts">
  import type { Dossier } from '$lib/api/dossier';
  import { supervision } from '$lib/stores/supervision.svelte';
  import ModeSheet from './ModeSheet.svelte';
  let { data }: { data: Dossier | null } = $props();
  let expanded = $state(false);
  let modeOpen = $state(false);

  async function openModes() {
    await supervision.refresh();
    modeOpen = true;
  }
</script>
```

Replace the `<button class="summary">…</button>` and the `.disposition` paragraph with:

```svelte
    <button class="summary" onclick={() => (expanded = !expanded)}>
      <span class="ledger">{data.rank} · merit {data.merit} · tokens {data.tokens} · debt {data.debt}</span>
      <span class="task">
        {#if data.active_task}
          {data.active_task.description} · intensity {data.active_task.intensity} · {data.active_task.discreetness}
        {:else}
          no active task
        {/if}
      </span>
    </button>
    <div class="meta">
      <button class="mode-badge" onclick={openModes}>mode · {data.supervision_mode}</button>
      <p class="disposition ledger">{data.disposition.line}</p>
    </div>
```

Add the sheet just before the closing `</header>`:

```svelte
  <ModeSheet open={modeOpen} onclose={() => (modeOpen = false)} />
```

Add these styles inside the `<style>` block:

```css
  .meta {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-top: 6px;
  }
  .mode-badge {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.7rem;
    background: transparent;
    color: var(--accent);
    border: 1px solid var(--accent);
    padding: 2px 8px;
    cursor: pointer;
  }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `"C:\Program Files\nodejs\npm.cmd" run test -- src/lib/chat/DossierBar.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/dossier.ts frontend/src/lib/chat/DossierBar.svelte frontend/src/lib/chat/DossierBar.test.ts
git commit -m "feat(fe): dossier mode badge + active-task tags"
```

---

## Task 7: Refresh supervision on chat mount

**Files:**
- Modify: `frontend/src/routes/+page.svelte` (`onMount`, ~lines 20-28)
- Test: `frontend/src/routes/page.test.ts` (extend if it already mocks stores; otherwise this is a wiring-only change verified by `svelte-check`)

- [ ] **Step 1: Wire the store**

In `frontend/src/routes/+page.svelte`, add the import alongside the other store imports:

```ts
  import { supervision } from '$lib/stores/supervision.svelte';
```

In `onMount`, add a supervision refresh next to the dossier refresh:

```ts
    await availability.refresh();
    await dossier.refresh();
    await supervision.refresh();
```

- [ ] **Step 2: Type-check**

Run: `"C:\Program Files\nodejs\npm.cmd" run check`
Expected: no new errors.

- [ ] **Step 3: Run the existing page test**

Run: `"C:\Program Files\nodejs\npm.cmd" run test -- src/routes/page.test.ts`
Expected: PASS (existing assertions unaffected). If the test mocks API modules and now errors on an unmocked `$lib/api/supervision`, add to its mocks:
```ts
vi.mock('$lib/api/supervision', () => ({
  getSupervision: vi.fn(async () => ({ mode: 'full', notes: {} })),
  setMode: vi.fn(),
  setNote: vi.fn()
}));
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/+page.svelte frontend/src/routes/page.test.ts
git commit -m "feat(fe): refresh supervision on chat mount"
```

---

## Task 8: Toys form — discreetness flags + edit mode

**Files:**
- Modify: `frontend/src/lib/onboarding/Toys.svelte`
- Test: `frontend/src/lib/onboarding/Toys.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/lib/onboarding/Toys.test.ts`:

```ts
test('emits the three discreetness flags', async () => {
  const onnext = vi.fn();
  render(Toys, { types: ['vibrator'], onnext });

  await fireEvent.input(screen.getByLabelText('Name'), { target: { value: 'Apex' } });
  await fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'vibrator' } });
  await fireEvent.click(screen.getByLabelText(/discreet-capable/i));
  await fireEvent.click(screen.getByLabelText(/makes noise/i));
  flushSync();

  screen.getByRole('button', { name: /add & continue/i }).click();
  expect(onnext).toHaveBeenCalledWith({
    name: 'Apex',
    type: 'vibrator',
    intiface_capable: false,
    noise: true,
    visibility: false,
    discreet_capable: true
  });
});

test('prefills from initial for editing', () => {
  const onnext = vi.fn();
  render(Toys, {
    types: ['vibrator'],
    onnext,
    initial: { name: 'Old', type: 'vibrator', intiface_capable: false, noise: true, visibility: false, discreet_capable: false }
  });
  expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('Old');
  expect((screen.getByLabelText(/makes noise/i) as HTMLInputElement).checked).toBe(true);
  expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"C:\Program Files\nodejs\npm.cmd" run test -- src/lib/onboarding/Toys.test.ts`
Expected: FAIL — no `discreet-capable` / `makes noise` checkboxes; `onnext` payload lacks the flags.

- [ ] **Step 3: Update the component**

Replace `frontend/src/lib/onboarding/Toys.svelte` with:

```svelte
<script lang="ts">
  import TextField from '$lib/design/components/TextField.svelte';
  import Select from '$lib/design/components/Select.svelte';
  type Toy = {
    name: string;
    type: string;
    intiface_capable?: boolean;
    notes?: string;
    noise?: boolean;
    visibility?: boolean;
    discreet_capable?: boolean;
  };
  let {
    onnext,
    types = [],
    initial = null
  }: { onnext: (toy: Toy | null) => void; types?: string[]; initial?: Toy | null } = $props();

  let name = $state(initial?.name ?? '');
  let type = $state(initial?.type ?? '');
  let intiface = $state(initial?.intiface_capable ?? false);
  let noise = $state(initial?.noise ?? false);
  let visibility = $state(initial?.visibility ?? false);
  let discreet = $state(initial?.discreet_capable ?? false);
  const editing = $derived(initial !== null);
  const ready = $derived(name.trim().length > 0 && type.length > 0);
  const options = $derived([
    { value: '', label: 'Select a type…' },
    ...types.map((t) => ({ value: t, label: t.replaceAll('_', ' ') }))
  ]);

  function submit() {
    onnext({
      name,
      type,
      intiface_capable: intiface,
      noise,
      visibility,
      discreet_capable: discreet
    });
  }
</script>

<h2 class="display">{editing ? 'Edit toy' : 'Your toys'}</h2>
<p class="label">{editing ? 'Update its details.' : 'Add one now, or skip — you can add more later.'}</p>
<TextField label="Name" value={name} oninput={(v) => (name = v)} />
<Select label="Type" value={type} {options} onchange={(v) => (type = v)} />
<div class="flags">
  <label><input type="checkbox" bind:checked={intiface} /> Intiface-capable</label>
  <label><input type="checkbox" bind:checked={discreet} /> Discreet-capable (usable unseen)</label>
  <label><input type="checkbox" bind:checked={noise} /> Makes noise</label>
  <label><input type="checkbox" bind:checked={visibility} /> Visible when worn</label>
</div>
<div class="actions">
  {#if !editing}
    <button class="ghost" onclick={() => onnext(null)}>Skip</button>
  {/if}
  <button disabled={!ready} onclick={submit}>{editing ? 'Save' : 'Add & continue'}</button>
</div>

<style>
  .flags {
    display: grid;
    gap: 6px;
    margin: 12px 0;
  }
  .actions {
    display: flex;
    gap: 12px;
    margin-top: 16px;
  }
  .ghost {
    background: transparent;
    color: var(--paper);
    border: 1px solid var(--paper);
  }
</style>
```

Note: the original `intiface_capable`-only payload changes to always include the flags. The existing `'selecting a prefilled type + name submits the toy'` test asserts a payload **without** the flag keys, so update its expectation to include `noise: false, visibility: false, discreet_capable: false` (and keep `intiface_capable: false`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `"C:\Program Files\nodejs\npm.cmd" run test -- src/lib/onboarding/Toys.test.ts`
Expected: PASS (all tests, including the updated original).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/onboarding/Toys.svelte frontend/src/lib/onboarding/Toys.test.ts
git commit -m "feat(fe): toy discreetness flags + edit mode"
```

---

## Task 9: Profile page — per-toy flags + edit

**Files:**
- Modify: `frontend/src/lib/api/profile.ts` (`addToy` type widen + add `updateToy`)
- Modify: `frontend/src/routes/profile/+page.svelte`
- Test: `frontend/src/routes/profile/page.test.ts`

- [ ] **Step 1: Add a `patch` method to the client, the API call, and write the failing test**

The client (`frontend/src/lib/api/client.ts`) has `get/post/put/del` but no `patch`. Add it to the returned object (after the `put` line):

```ts
    patch: (p: string, b?: unknown) => request('PATCH', p, b),
```

In `frontend/src/lib/api/profile.ts`, widen the `addToy` toy type and add `updateToy`:

```ts
type ToyInput = {
  name: string;
  type: string;
  intiface_capable?: boolean;
  notes?: string;
  noise?: boolean;
  visibility?: boolean;
  discreet_capable?: boolean;
};
export const addToy = (id: string, toy: ToyInput) =>
  api.post(`/api/profile/${id}/toys`, toy);
export const updateToy = (id: string, toyId: string, patch: Partial<ToyInput>) =>
  api.patch(`/api/profile/${id}/toys/${toyId}`, patch);
```

Append to `frontend/src/routes/profile/page.test.ts` a test that the toy list renders discreetness flags. Match the file's existing mock style; the key assertion:

```ts
test('shows toy discreetness flags', async () => {
  // (reuse the file's existing getProfile mock, returning a toy with discreet_capable: true)
  // then:
  expect(await screen.findByText(/discreet/i)).toBeInTheDocument();
});
```

If the existing `page.test.ts` defines its profile fixture inline, extend that fixture's `toys` entry to `{ name: 'Apex', type: 'vibrator', noise: false, visibility: false, discreet_capable: true, intiface_capable: false }` rather than adding a brand-new mock.

- [ ] **Step 2: Run test to verify it fails**

Run: `"C:\Program Files\nodejs\npm.cmd" run test -- src/routes/profile/page.test.ts`
Expected: FAIL — flags not rendered.

- [ ] **Step 3: Update the profile page**

In `frontend/src/routes/profile/+page.svelte`:

1. Extend the `Profile` type's `toys` entry:
```ts
    toys: {
      id: string;
      name: string;
      type: string;
      noise: boolean;
      visibility: boolean;
      discreet_capable: boolean;
      intiface_capable: boolean;
    }[];
```

2. Import `updateToy` and add edit state:
```ts
  import { getProfile, putKinks, addToy, updateToy, addGoal, putSoContext, putPreferences, type KinkRating } from '$lib/api/profile';
```
```ts
  let editingToyId = $state<string | null>(null);
```

3. Replace `onToy` and add an edit handler (widen the toy param type to include the flags):
```ts
  async function onToy(toy: {
    name: string; type: string; intiface_capable?: boolean;
    noise?: boolean; visibility?: boolean; discreet_capable?: boolean;
  } | null) {
    if (toy) {
      if (editingToyId) await updateToy(session.profileId!, editingToyId, toy);
      else await addToy(session.profileId!, toy);
    }
    editing = null;
    editingToyId = null;
    await load();
    flash('toys');
  }
  async function openToyEdit(toy: Profile['toys'][number]) {
    await ensureVocab();
    editingToyId = toy.id;
    editing = 'toys';
  }
```

4. Replace the Toys `<section>` body. When `editing === 'toys'`, pass `initial` for an edit (the toy being edited) or nothing for an add; render flags + an Edit button per toy:
```svelte
      {#if editing === 'toys'}
        <Toys
          types={toyTypes}
          onnext={onToy}
          initial={editingToyId ? (profile.toys.find((t) => t.id === editingToyId) ?? null) : null}
        />
      {:else}
        <ul class="list">
          {#each profile.toys as t}
            <li>
              <span>{t.name}</span> · {t.type}
              {#if t.discreet_capable}· discreet{/if}{#if t.noise}· noisy{/if}{#if t.visibility}· visible{/if}
              <button class="edit small" onclick={() => openToyEdit(t)}>Edit</button>
            </li>
          {/each}
        </ul>
      {/if}
```

5. Ensure the "Add" button clears edit state: change its handler to `onclick={() => { editingToyId = null; openToys(); }}`.

- [ ] **Step 4: Run tests + type-check**

Run: `"C:\Program Files\nodejs\npm.cmd" run test -- src/routes/profile/page.test.ts`
Then: `"C:\Program Files\nodejs\npm.cmd" run check`
Expected: PASS; no new type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/profile.ts frontend/src/routes/profile/+page.svelte frontend/src/routes/profile/page.test.ts
git commit -m "feat(fe): per-toy discreetness flags + edit on profile"
```

---

## Task 10: Regenerate generated OpenAPI types

**Files:**
- Modify: `frontend/openapi.json`, `frontend/src/lib/types/api.ts` (generated)

- [ ] **Step 1: Ensure backend imports cleanly**

Run from `backend/`: `PYTHONHOME= PYTHONPATH= uv run python -c "from app.main import app; print(len(app.openapi()['paths']))"`
Expected: prints a path count (no import error). Confirms the PATCH route is registered.

- [ ] **Step 2: Regenerate**

Run from `frontend/`: `"C:\Program Files\nodejs\npm.cmd" run gen:api`
Expected: `wrote openapi.json` then openapi-typescript writes `src/lib/types/api.ts`.

- [ ] **Step 3: Sanity-check the diff**

Run: `git diff --stat frontend/openapi.json frontend/src/lib/types/api.ts`
Expected: the new `/profile/{profile_id}/toys/{toy_id}` PATCH path, `supervision_mode` on the dossier schema, and `intensity`/`discreetness` on `ActiveTask` appear. (Pre-existing M4/M5 drift will also collapse into this commit — that is the intended resync; the file is imported nowhere in `src/`.)

- [ ] **Step 4: Verify the frontend still builds**

Run: `"C:\Program Files\nodejs\npm.cmd" run check`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/openapi.json frontend/src/lib/types/api.ts
git commit -m "chore(fe): regenerate OpenAPI types (M5c resync)"
```

---

## Final verification (whole branch)

- [ ] Backend suite: from `backend/`, `PYTHONHOME= PYTHONPATH= uv run python -m pytest -q` (the pre-existing `tests/db/test_migration.py` subprocess test fails on this machine only — see dev-env notes; it passes in CI).
- [ ] Frontend suite: from `frontend/`, `"C:\Program Files\nodejs\npm.cmd" run test`
- [ ] Lint: from `backend/`, `PYTHONHOME= PYTHONPATH= uv run python -m ruff check .` ; from `frontend/`, `"C:\Program Files\nodejs\npm.cmd" run lint`
- [ ] Type-check: from `frontend/`, `"C:\Program Files\nodejs\npm.cmd" run check`
- [ ] Open PR; confirm CI green before merge.

---

## Self-review notes

- **No new migration:** Task 1/2 add no columns (the toy flags already exist from M5b). The dossier fields (Task 3) are read-only schema/response additions. ✓
- **Spec coverage:** §1 toy PATCH → T1–T2; §2 dossier surfacing → T3; §3 supervision client/store → T4; §4 ModeSheet → T5; §5 DossierBar badge+tags → T6 (+ T7 mount wiring); §6 Toys flags → T8; §7 profile toy editing → T9; §8 gen:api → T10. ✓
- **Out of scope (unchanged):** required-toy names in dossier; schedule/calendar; `punitive` flag + `pending_review`. ✓
