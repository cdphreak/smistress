# M9b — Profile/Character Spokes + Safety Shell + Playwright Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Phase-A frontend slice: the Sub Profile and Character Model view-edit spokes, the always-on Safety shell (SAFE button → pre-halt → confirm → calm stop screen, well-being controls, delete-everything), and a Playwright E2E suite — all binding to the M3/M8 backend endpoints.

**Architecture:** Continues the M9 SvelteKit app (Svelte 5 runes, adapter-node, same-origin BFF proxy, Severe Editorial design tokens). Adds a typed `safety` API module + a global `safety` runes store; the SAFE button + stop sheet mount in the root layout as a global overlay (per Addendum A6: deterministic, never routed through the persona). Spokes are deep-linkable routes (`/profile`, `/character`, `/settings`) reachable from a minimal home hub at `/` (full chat home is Phase B). Editing reuses the existing onboarding step components. Playwright drives the real UI with `/api/*` stubbed via route interception, so the E2E job needs no backend.

**Tech Stack:** SvelteKit 2 · Svelte 5 runes · TypeScript · Vite · Vitest + `@testing-library/svelte` · `@playwright/test` · adapter-node.

---

## Background (already in place — do not rebuild)

From **M9** (`frontend/`): the BFF proxy (`/api/[...path]`), `lib/api/client.ts` (`makeClient` → `{get, post, put}`, `ApiError`), `lib/api/onboarding.ts` (`getQuestionnaire`, `createProfile`), `lib/api/profile.ts` (`getProfile`, `getCharacter`, `putCharacter`, `putKinks`, `addToy`, `addGoal`, `putSoContext`, `putPreferences`, `submitArchetype`, `KinkRating`), `lib/stores/session.svelte.ts` (`session.profileId`), the design primitives (`Button`, `SegmentedControl`, `Scale`, `TextField`, `TextArea`, `NumberField`, `ProgressRail`) + `tokens.css`, and the onboarding step components (`KinkSheet`, `Toys`, `Goals`, `SoContext`, `Character`, `Preferences`, `Archetype`, `Reveal`). The root `+layout.svelte` imports tokens; `+page.svelte` (`/`) currently redirects to `/onboarding/consent` when there's no profile and otherwise shows a placeholder.

From **M8** (backend): safety REST endpoints exist — `POST /profile/{id}/safeword` (returns `{scene_halted, denial_lifted, merit_penalty, aftercare, message}`), `POST /profile/{id}/resume`, `GET /profile/{id}/safety` (returns `{is_halted, on_hiatus, consent_check_due}`), `POST /profile/{id}/hiatus` (`{on}`), `POST /profile/{id}/lower-limit` (`{kink, rating}`; 422 on non-limit rating), `POST /profile/{id}/consent-check`, and `DELETE /profile/{id}` (204).

Backend response shapes used here:
- `GET /profile/{id}` → `{id, intensity_ceiling, aftercare_prefs, archetype_scores: Record<string,number>, kinks: {kink, rating}[], toys: {name, type, intiface_capable, notes}[], goals: {title, description, status}[], so_context: {description, values, dynamic}|null, character: CharacterOut}`.
- `CharacterOut` = `{name, honorific, address_term, pronouns, archetype_blend: Record<string,number>, warmth, strictness, sadism, formality, verbosity, crudeness, wit, signature_flavor}`.

**Branch:** `feat/m9b-spokes-safety`. **Work from `frontend/`.** No backend needed for any test (Vitest mocks the api module; Playwright stubs `/api/*`). Commit messages end without a backend caveat. The frontend toolchain is npm (Node 22).

---

## File structure

**Create:**
- `src/lib/api/safety.ts` — typed safety endpoint wrappers
- `src/lib/stores/safety.svelte.ts` — global safety runes store (client pre-halt + server state mirror + actions)
- `src/lib/safety/SafeButton.svelte` — always-pinned SAFE control
- `src/lib/safety/StopSheet.svelte` — pre-halt + confirm + calm stop receipt + resume + crisis resources
- `src/lib/spokes/SpokeHeader.svelte` — shared spoke chrome (title + back-to-home)
- `src/routes/profile/+page.svelte` — Sub Profile spoke (view + edit)
- `src/routes/character/+page.svelte` — Character Model spoke (view + edit)
- `src/routes/settings/+page.svelte` — well-being controls + delete-everything
- `playwright.config.ts`, `e2e/onboarding.spec.ts`, `e2e/spokes.spec.ts`, `e2e/safety.spec.ts`, `e2e/fixtures.ts`
- Tests: `src/lib/api/safety.test.ts`, `src/lib/stores/safety.test.ts`, `src/lib/safety/StopSheet.test.ts`, `src/lib/safety/SafeButton.test.ts`

**Modify:**
- `src/lib/api/client.ts` — add a `del` (DELETE) method
- `src/lib/api/profile.ts` — add typed `Profile`/`Character` interfaces + a `lowerLimit`-free re-export is N/A (safety owns that); add `Questionnaire` reuse note
- `src/lib/onboarding/Character.svelte` — accept an optional `initial` prop (seed from current character for the spoke)
- `src/routes/+layout.svelte` — mount the global `<SafeButton/>` + `<StopSheet/>` overlay
- `src/routes/+page.svelte` — minimal guarded home hub linking the spokes
- `package.json` — add `@playwright/test`, `test:e2e` script
- `.github/workflows/ci.yml` — add an `e2e` job (Playwright, no backend)

---

## Task 1: Safety API module + DELETE client method + safety store

**Files:** Modify `src/lib/api/client.ts`; create `src/lib/api/safety.ts`, `src/lib/api/safety.test.ts`, `src/lib/stores/safety.svelte.ts`, `src/lib/stores/safety.test.ts`.

- [ ] **Step 1: Write the failing tests**

`src/lib/api/safety.test.ts`:
```ts
import { describe, expect, test, vi } from 'vitest';
import { makeClient } from './client';

describe('client.del', () => {
  test('issues a DELETE and returns parsed body (or null on empty)', async () => {
    const fetchFn = vi.fn(async () => new Response('', { status: 204 }));
    const api = makeClient('', fetchFn);
    expect(await api.del('/api/profile/x')).toBeNull();
    expect(fetchFn.mock.calls[0][1]?.method).toBe('DELETE');
  });
});
```

`src/lib/stores/safety.test.ts`:
```ts
import { beforeEach, expect, test, vi } from 'vitest';

// Mock the api layer so the store can be tested without a network.
vi.mock('$lib/api/safety', () => ({
  safeword: vi.fn(async () => ({
    scene_halted: true, denial_lifted: 2, merit_penalty: 0,
    aftercare: 'rest', message: 'stopping now'
  })),
  resume: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: false })),
  getSafety: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: false }))
}));

import { safety } from './safety.svelte';
import { session } from './session.svelte';

beforeEach(() => {
  localStorage.clear();
  session.setProfileId('p1');
  safety.paused = false;
  safety.isHalted = false;
  safety.receipt = null;
});

test('preHalt sets paused client-side with no network call', async () => {
  const api = await import('$lib/api/safety');
  safety.preHalt();
  expect(safety.paused).toBe(true);
  expect(api.safeword).not.toHaveBeenCalled(); // pre-halt is pure client
});

test('confirmStop posts safeword and records the receipt', async () => {
  const api = await import('$lib/api/safety');
  await safety.confirmStop();
  expect(api.safeword).toHaveBeenCalledWith('p1');
  expect(safety.isHalted).toBe(true);
  expect(safety.receipt?.message).toBe('stopping now');
});

test('resumeScene clears halt and receipt', async () => {
  await safety.confirmStop();
  await safety.resumeScene();
  expect(safety.isHalted).toBe(false);
  expect(safety.paused).toBe(false);
  expect(safety.receipt).toBeNull();
});
```

- [ ] **Step 2: Run** — `npx vitest run src/lib/api/safety.test.ts src/lib/stores/safety.test.ts` → FAIL (no `del`, no safety module/store).

- [ ] **Step 3a: Add `del` to the client** — in `src/lib/api/client.ts`, inside the object returned by `makeClient`, add a `del` method alongside `get/post/put`:
```ts
  return {
    get: (p: string) => request('GET', p),
    post: (p: string, b?: unknown) => request('POST', p, b),
    put: (p: string, b?: unknown) => request('PUT', p, b),
    del: (p: string) => request('DELETE', p)
  };
```

- [ ] **Step 3b: Safety API module** — `src/lib/api/safety.ts`:
```ts
import { api } from './client';
import type { KinkRating } from './profile';

export interface StopReceipt {
  scene_halted: boolean;
  denial_lifted: number;
  merit_penalty: number;
  aftercare: string;
  message: string;
}
export interface SafetyState {
  is_halted: boolean;
  on_hiatus: boolean;
  consent_check_due: boolean;
}

export const safeword = (id: string) =>
  api.post(`/api/profile/${id}/safeword`) as Promise<StopReceipt>;
export const resume = (id: string) =>
  api.post(`/api/profile/${id}/resume`) as Promise<SafetyState>;
export const getSafety = (id: string) =>
  api.get(`/api/profile/${id}/safety`) as Promise<SafetyState>;
export const setHiatus = (id: string, on: boolean) =>
  api.post(`/api/profile/${id}/hiatus`, { on }) as Promise<SafetyState>;
export const lowerLimit = (id: string, kink: string, rating: KinkRating) =>
  api.post(`/api/profile/${id}/lower-limit`, { kink, rating }) as Promise<{
    kink: string;
    rating: KinkRating;
  }>;
export const consentCheck = (id: string) =>
  api.post(`/api/profile/${id}/consent-check`) as Promise<SafetyState>;
export const deleteProfile = (id: string) => api.del(`/api/profile/${id}`);
```

- [ ] **Step 3c: Safety store** — `src/lib/stores/safety.svelte.ts`:
```ts
import { getSafety, resume as apiResume, safeword, type StopReceipt } from '$lib/api/safety';
import { session } from './session.svelte';

// Global, deterministic safety state (Addendum A6). The pre-halt is pure client
// state set the instant the SAFE sheet opens — before any network call.
class Safety {
  paused = $state(false); // client pre-halt OR server-confirmed halt
  isHalted = $state(false); // server-confirmed (after POST /safeword)
  onHiatus = $state(false);
  receipt = $state<StopReceipt | null>(null);

  preHalt() {
    this.paused = true;
  }
  cancelPreHalt() {
    // Only un-pause if the server hasn't confirmed a full stop.
    if (!this.isHalted) this.paused = false;
  }
  async confirmStop() {
    const pid = session.profileId;
    if (!pid) return;
    this.receipt = await safeword(pid);
    this.isHalted = true;
    this.paused = true;
  }
  async refresh() {
    const pid = session.profileId;
    if (!pid) return;
    const s = await getSafety(pid);
    this.isHalted = s.is_halted;
    this.onHiatus = s.on_hiatus;
    this.paused = s.is_halted;
  }
  async resumeScene() {
    const pid = session.profileId;
    if (!pid) return;
    const s = await apiResume(pid);
    this.isHalted = s.is_halted;
    this.paused = false;
    this.receipt = null;
  }
}

export const safety = new Safety();
```

- [ ] **Step 4: Run** — `npx vitest run src/lib/api/safety.test.ts src/lib/stores/safety.test.ts` → PASS; `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add src/lib/api/client.ts src/lib/api/safety.ts src/lib/api/safety.test.ts src/lib/stores/safety.svelte.ts src/lib/stores/safety.test.ts
git commit -m "feat(fe): safety API module + global safety runes store + client DELETE"
```

---

## Task 2: SAFE button + stop sheet, mounted globally

**Files:** Create `src/lib/safety/SafeButton.svelte`, `src/lib/safety/StopSheet.svelte`, `src/lib/safety/StopSheet.test.ts`, `src/lib/safety/SafeButton.test.ts`; modify `src/routes/+layout.svelte`.

- [ ] **Step 1: Write the failing tests**

`src/lib/safety/SafeButton.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test, beforeEach } from 'vitest';
import SafeButton from './SafeButton.svelte';
import { safety } from '$lib/stores/safety.svelte';

beforeEach(() => {
  safety.paused = false;
  safety.isHalted = false;
});

test('clicking SAFE pre-halts immediately (client-side) and opens the sheet', async () => {
  render(SafeButton);
  screen.getByRole('button', { name: /safe/i }).click();
  expect(safety.paused).toBe(true); // pre-halt fired before any network
});
```

`src/lib/safety/StopSheet.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/safety', () => ({
  safeword: vi.fn(async () => ({
    scene_halted: true, denial_lifted: 1, merit_penalty: 0,
    aftercare: 'tea and quiet', message: "Okay — we're stopping now."
  })),
  resume: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: false })),
  getSafety: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: false }))
}));

import StopSheet from './StopSheet.svelte';
import { safety } from '$lib/stores/safety.svelte';
import { session } from '$lib/stores/session.svelte';
import { flushSync } from 'svelte';

beforeEach(() => {
  session.setProfileId('p1');
  safety.paused = false;
  safety.isHalted = false;
  safety.receipt = null;
});

test('open sheet shows the confirm prompt; confirming shows the calm receipt', async () => {
  safety.preHalt(); // sheet is shown when paused
  render(StopSheet);
  expect(screen.getByText(/stop everything/i)).toBeInTheDocument();

  screen.getByRole('button', { name: /stop everything/i }).click();
  // allow the awaited confirmStop + reactive flush
  await vi.waitFor(() => {
    expect(screen.getByText(/stopping now/i)).toBeInTheDocument();
  });
  expect(screen.getByText(/tea and quiet/i)).toBeInTheDocument();
  expect(safety.isHalted).toBe(true);
});

test('nothing renders when not paused', () => {
  render(StopSheet);
  expect(screen.queryByText(/stop everything/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run** — `npx vitest run src/lib/safety` → FAIL (no components).

- [ ] **Step 3a: SafeButton** — `src/lib/safety/SafeButton.svelte`:
```svelte
<script lang="ts">
  import { safety } from '$lib/stores/safety.svelte';
</script>

<button class="safe" aria-label="SAFE — stop everything" onclick={() => safety.preHalt()}>
  SAFE
</button>

<style>
  .safe {
    position: fixed;
    bottom: 16px;
    right: 16px;
    z-index: 50;
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    background: var(--accent);
    color: var(--paper);
    border: 0;
    border-radius: 0;
    padding: 14px 22px;
    cursor: pointer;
    box-shadow: 0 0 0 2px var(--ink);
  }
</style>
```

- [ ] **Step 3b: StopSheet** — `src/lib/safety/StopSheet.svelte`:
```svelte
<script lang="ts">
  import { safety } from '$lib/stores/safety.svelte';
  import { goto } from '$app/navigation';

  async function confirm() {
    await safety.confirmStop();
  }
  async function resume() {
    await safety.resumeScene();
  }
</script>

{#if safety.paused}
  <div class="scrim" role="dialog" aria-modal="true" aria-label="Safety stop">
    <section class="sheet">
      {#if !safety.receipt}
        <!-- Pre-halt is already in effect (timers/denial pressure paused). Confirm finalizes. -->
        <p class="label">Everything is paused.</p>
        <h2 class="display">Stop everything?</h2>
        <p>Confirming finalizes the stop. There's no penalty, and you can resume when you're ready.</p>
        <div class="actions">
          <button class="ghost" onclick={() => safety.cancelPreHalt()}>Not yet</button>
          <button class="danger" onclick={confirm}>Stop everything</button>
        </div>
      {:else}
        <!-- The one place the severe styling softens: calm, out-of-persona. -->
        <p class="label">Scene halted</p>
        <p class="calm">{safety.receipt.message}</p>
        <p class="calm">{safety.receipt.aftercare}</p>
        <ul class="receipt ledger">
          <li>denial lifted: {safety.receipt.denial_lifted}</li>
          <li>merit penalty: {safety.receipt.merit_penalty}</li>
        </ul>
        <details class="resources">
          <summary>Crisis resources</summary>
          <p>US: call or text 988 (Suicide &amp; Crisis Lifeline), or text HOME to 741741. Elsewhere: your local emergency number.</p>
        </details>
        <div class="actions">
          <button class="ghost" onclick={() => goto('/settings')}>Well-being</button>
          <button onclick={resume}>Resume when ready</button>
        </div>
      {/if}
    </section>
  </div>
{/if}

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 60;
    background: rgba(0, 0, 0, 0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .sheet {
    background: var(--paper);
    color: var(--ink);
    max-width: 460px;
    width: 100%;
    padding: 28px;
  }
  .sheet .label {
    color: var(--accent);
  }
  .calm {
    font-family: var(--font-body);
    line-height: 1.5;
  }
  .receipt {
    list-style: none;
    padding: 0;
    color: var(--muted);
  }
  .actions {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
    margin-top: 16px;
  }
  button {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    border: 1px solid var(--ink);
    background: var(--ink);
    color: var(--paper);
    padding: 12px 18px;
    cursor: pointer;
    border-radius: 0;
  }
  .ghost {
    background: transparent;
    color: var(--ink);
  }
  .danger {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--paper);
  }
  .resources {
    margin-top: 12px;
    font-size: 0.85rem;
  }
</style>
```

- [ ] **Step 3c: Mount globally** — in `src/routes/+layout.svelte`, import and render the overlay after `{@render children()}`:
```svelte
<script lang="ts">
  import '$lib/design/tokens.css';
  import favicon from '$lib/assets/favicon.svg';
  import SafeButton from '$lib/safety/SafeButton.svelte';
  import StopSheet from '$lib/safety/StopSheet.svelte';
  import { session } from '$lib/stores/session.svelte';

  let { children } = $props();
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
</svelte:head>

{@render children()}

<!-- Safety is a global overlay, never a route (Addendum A6). Shown once a profile exists. -->
{#if session.profileId}
  <SafeButton />
  <StopSheet />
{/if}
```

- [ ] **Step 4: Run** — `npx vitest run src/lib/safety` → PASS; `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add src/lib/safety/ src/routes/+layout.svelte
git commit -m "feat(fe): global SAFE button + pre-halt/confirm stop sheet (Addendum A6)"
```

---

## Task 3: Home hub + shared spoke header

**Files:** Create `src/lib/spokes/SpokeHeader.svelte`; modify `src/routes/+page.svelte`.

- [ ] **Step 1: Write the failing test** — `src/lib/spokes/SpokeHeader.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import SpokeHeader from './SpokeHeader.svelte';

test('renders the title and a home link', () => {
  render(SpokeHeader, { title: 'Sub Profile' });
  expect(screen.getByText('Sub Profile')).toBeInTheDocument();
  const home = screen.getByRole('link', { name: /home/i });
  expect(home).toHaveAttribute('href', '/');
});
```

- [ ] **Step 2: Run** — `npx vitest run src/lib/spokes/SpokeHeader.test.ts` → FAIL.

- [ ] **Step 3a: SpokeHeader** — `src/lib/spokes/SpokeHeader.svelte`:
```svelte
<script lang="ts">
  let { title }: { title: string } = $props();
</script>

<header class="spoke-head">
  <a class="label" href="/">← Home</a>
  <h1 class="display">{title}</h1>
</header>

<style>
  .spoke-head {
    display: flex;
    align-items: baseline;
    gap: 16px;
    padding: 16px;
    border-bottom: 1px solid var(--hairline);
  }
  a.label {
    color: var(--muted);
    text-decoration: none;
  }
  h1 {
    margin: 0;
    font-size: 1.4rem;
  }
</style>
```

- [ ] **Step 3b: Home hub** — replace `src/routes/+page.svelte` with a guarded hub linking the spokes (the full chat home is Phase B):
```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores/session.svelte';

  onMount(() => {
    if (!session.profileId) goto('/onboarding/consent');
  });
</script>

<main class="home">
  <p class="label">smistress</p>
  <h1 class="display">Home</h1>
  <p class="muted">The chat surface arrives in a later milestone. For now, your dossier:</p>
  <nav class="spokes">
    <a href="/profile">Sub Profile</a>
    <a href="/character">Character</a>
    <a href="/settings">Settings &amp; well-being</a>
  </nav>
</main>

<style>
  .home {
    max-width: 640px;
    margin: 0 auto;
    padding: 32px 16px;
  }
  .muted {
    color: var(--muted);
  }
  .spokes {
    display: grid;
    gap: 8px;
    margin-top: 16px;
  }
  .spokes a {
    display: block;
    padding: 16px;
    border: 1px solid var(--hairline);
    color: var(--paper);
    text-decoration: none;
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .spokes a:hover {
    border-color: var(--accent);
  }
</style>
```

- [ ] **Step 4: Run** — `npx vitest run src/lib/spokes/SpokeHeader.test.ts` → PASS; `npm run check` clean; `npm run build` succeeds.

- [ ] **Step 5: Commit**
```bash
git add src/lib/spokes/ src/routes/+page.svelte
git commit -m "feat(fe): home hub linking spokes + shared spoke header"
```

---

## Task 4: Sub Profile spoke (view + edit)

**Files:** Create `src/routes/profile/+page.svelte`. Reuses `KinkSheet`, `Toys`, `Goals`, `SoContext`, `Preferences` from `lib/onboarding`, and `getProfile`/`getQuestionnaire`/`putKinks`/`addToy`/`addGoal`/`putSoContext`/`putPreferences`.

- [ ] **Step 1: Write the failing test** — `src/routes/profile/page.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/profile', () => ({
  getProfile: vi.fn(async () => ({
    id: 'p1',
    intensity_ceiling: 60,
    aftercare_prefs: 'tea',
    archetype_scores: { submissive: 80, slave: 20 },
    kinks: [{ kink: 'bondage', rating: 'favorite' }],
    toys: [{ name: 'Apex', type: 'vibrator' }],
    goals: [{ title: 'Posture', description: '', status: 'active' }],
    so_context: { description: 'partner', values: null, dynamic: null },
    character: { honorific: 'Headmistress', address_term: 'student' }
  })),
  putKinks: vi.fn(),
  addToy: vi.fn(),
  addGoal: vi.fn(),
  putSoContext: vi.fn(),
  putPreferences: vi.fn()
}));
vi.mock('$lib/api/onboarding', () => ({
  getQuestionnaire: vi.fn(async () => ({
    statements: [],
    kinks: ['bondage', 'spanking'],
    answer_scale: { min: 0, max: 4 }
  }))
}));

import Page from './+page.svelte';
import { session } from '$lib/stores/session.svelte';

beforeEach(() => session.setProfileId('p1'));

test('renders the assembled profile after load', async () => {
  render(Page);
  expect(await screen.findByText('Headmistress')).toBeInTheDocument();
  expect(screen.getByText(/submissive/i)).toBeInTheDocument();
  expect(screen.getByText('Apex')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run** — `npx vitest run src/routes/profile/page.test.ts` → FAIL.

- [ ] **Step 3: Implement** — `src/routes/profile/+page.svelte`:
```svelte
<script lang="ts">
  import SpokeHeader from '$lib/spokes/SpokeHeader.svelte';
  import KinkSheet from '$lib/onboarding/KinkSheet.svelte';
  import Toys from '$lib/onboarding/Toys.svelte';
  import Goals from '$lib/onboarding/Goals.svelte';
  import SoContext from '$lib/onboarding/SoContext.svelte';
  import Preferences from '$lib/onboarding/Preferences.svelte';
  import { session } from '$lib/stores/session.svelte';
  import { getProfile, putKinks, addToy, addGoal, putSoContext, putPreferences, type KinkRating } from '$lib/api/profile';
  import { getQuestionnaire } from '$lib/api/onboarding';

  type Kink = { kink: string; rating: KinkRating };
  type Profile = {
    intensity_ceiling: number;
    aftercare_prefs: string | null;
    archetype_scores: Record<string, number>;
    kinks: Kink[];
    toys: { name: string; type: string }[];
    goals: { title: string; description?: string }[];
    so_context: { description?: string; values?: string; dynamic?: string } | null;
    character: { honorific: string; address_term: string };
  };

  let profile = $state<Profile | null>(null);
  let kinkVocab = $state<string[]>([]);
  let editing = $state<string | null>(null);
  let saved = $state<string | null>(null);

  async function load() {
    if (!session.profileId) return;
    profile = (await getProfile(session.profileId)) as Profile;
  }
  $effect(() => {
    load();
  });

  async function ensureVocab() {
    if (kinkVocab.length === 0) {
      const q = await getQuestionnaire();
      kinkVocab = q.kinks;
    }
  }
  async function openKinks() {
    await ensureVocab();
    editing = 'kinks';
  }
  function flash(section: string) {
    saved = section;
    setTimeout(() => (saved = null), 2000);
  }

  async function onKinks(entries: Kink[]) {
    await putKinks(session.profileId!, entries);
    editing = null;
    await load();
    flash('kinks');
  }
  async function onToy(toy: { name: string; type: string; intiface_capable?: boolean } | null) {
    if (toy) await addToy(session.profileId!, toy);
    editing = null;
    await load();
    flash('toys');
  }
  async function onGoal(goal: { title: string; description?: string } | null) {
    if (goal) await addGoal(session.profileId!, goal);
    editing = null;
    await load();
    flash('goals');
  }
  async function onSo(ctx: { description?: string; values?: string; dynamic?: string }) {
    await putSoContext(session.profileId!, ctx);
    editing = null;
    await load();
    flash('so');
  }
  async function onPrefs(p: { intensity_ceiling: number; aftercare_prefs: string | null }) {
    await putPreferences(session.profileId!, p);
    editing = null;
    await load();
    flash('preferences');
  }

  // Merge the catalog vocabulary with any kinks the user already rated.
  const kinkRows = $derived(
    Array.from(new Set([...kinkVocab, ...(profile?.kinks.map((k) => k.kink) ?? [])]))
  );
  const kinkInitial = $derived(
    Object.fromEntries((profile?.kinks ?? []).map((k) => [k.kink, k.rating]))
  );
</script>

<SpokeHeader title="Sub Profile" />

{#if !profile}
  <p class="label pad">Loading…</p>
{:else}
  <div class="pad sections">
    <section>
      <h2 class="label">Archetype</h2>
      <ul class="ledger scores">
        {#each Object.entries(profile.archetype_scores) as [name, score]}
          <li>{name}: {score}</li>
        {/each}
      </ul>
    </section>

    <section>
      <div class="row">
        <h2 class="label">Limits {#if saved === 'kinks'}<span class="ok">saved</span>{/if}</h2>
        <button class="edit" onclick={openKinks}>Edit</button>
      </div>
      {#if editing === 'kinks'}
        <KinkSheet kinks={kinkRows} initial={kinkInitial} onnext={onKinks} />
      {:else}
        <ul class="kinks">
          {#each profile.kinks as k}
            <li class:hard={k.rating === 'hard_limit'} class:soft={k.rating === 'soft_limit'}>
              {k.kink.replaceAll('_', ' ')} · {k.rating.replace('_', ' ')}
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <section>
      <div class="row">
        <h2 class="label">Toys {#if saved === 'toys'}<span class="ok">saved</span>{/if}</h2>
        <button class="edit" onclick={() => (editing = 'toys')}>Add</button>
      </div>
      {#if editing === 'toys'}
        <Toys onnext={onToy} />
      {:else}
        <ul class="list">{#each profile.toys as t}<li>{t.name} · {t.type}</li>{/each}</ul>
      {/if}
    </section>

    <section>
      <div class="row">
        <h2 class="label">Goals {#if saved === 'goals'}<span class="ok">saved</span>{/if}</h2>
        <button class="edit" onclick={() => (editing = 'goals')}>Add</button>
      </div>
      {#if editing === 'goals'}
        <Goals onnext={onGoal} />
      {:else}
        <ul class="list">{#each profile.goals as g}<li>{g.title}</li>{/each}</ul>
      {/if}
    </section>

    <section>
      <div class="row">
        <h2 class="label">SO context {#if saved === 'so'}<span class="ok">saved</span>{/if}</h2>
        <button class="edit" onclick={() => (editing = 'so')}>Edit</button>
      </div>
      {#if editing === 'so'}
        <SoContext onnext={onSo} />
      {:else}
        <p>{profile.so_context?.description || '(none)'}</p>
      {/if}
    </section>

    <section>
      <div class="row">
        <h2 class="label">Preferences {#if saved === 'preferences'}<span class="ok">saved</span>{/if}</h2>
        <button class="edit" onclick={() => (editing = 'preferences')}>Edit</button>
      </div>
      {#if editing === 'preferences'}
        <Preferences
          onnext={onPrefs}
          initial={{ intensity_ceiling: profile.intensity_ceiling, aftercare_prefs: profile.aftercare_prefs }}
        />
      {:else}
        <p class="ledger">ceiling {profile.intensity_ceiling} · aftercare: {profile.aftercare_prefs || '—'}</p>
      {/if}
    </section>
  </div>
{/if}

<style>
  .pad {
    max-width: 720px;
    margin: 0 auto;
    padding: 24px 16px;
  }
  .sections {
    display: grid;
    gap: 28px;
  }
  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .edit {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    background: transparent;
    color: var(--paper);
    border: 1px solid var(--paper);
    padding: 6px 12px;
    cursor: pointer;
  }
  .ok {
    color: var(--accent);
    font-size: 0.7rem;
    margin-left: 8px;
  }
  .scores,
  .list,
  .kinks {
    list-style: none;
    padding: 0;
  }
  .kinks .hard {
    color: var(--accent);
  }
  .kinks .soft {
    color: var(--accent-muted);
  }
</style>
```

- [ ] **Step 4: Run** — `npx vitest run src/routes/profile/page.test.ts` → PASS; `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add src/routes/profile/
git commit -m "feat(fe): Sub Profile spoke — view + edit (kinks/toys/goals/SO/preferences)"
```

---

## Task 5: Character Model spoke (view + edit)

**Files:** Modify `src/lib/onboarding/Character.svelte` (accept optional `initial`); create `src/routes/character/+page.svelte`.

- [ ] **Step 1: Write the failing test** — `src/routes/character/page.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/profile', () => ({
  getCharacter: vi.fn(async () => ({
    name: null,
    honorific: 'Headmistress',
    address_term: 'student',
    pronouns: 'she/her',
    archetype_blend: { governess: 70, drill_instructor: 30 },
    warmth: 40, strictness: 80, sadism: 30, formality: 70,
    verbosity: 50, crudeness: 30, wit: 75, signature_flavor: null
  })),
  putCharacter: vi.fn(async () => ({}))
}));

import Page from './+page.svelte';
import { session } from '$lib/stores/session.svelte';

beforeEach(() => session.setProfileId('p1'));

test('shows current character then reveals the edit form', async () => {
  render(Page);
  expect(await screen.findByText('Headmistress')).toBeInTheDocument();
  screen.getByRole('button', { name: /edit/i }).click();
  // edit form seeds the honorific field with the current value
  const sliders = await screen.findAllByRole('slider');
  expect(sliders.length).toBe(7); // 7 voice dials
});
```

- [ ] **Step 2: Run** — `npx vitest run src/routes/character/page.test.ts` → FAIL.

- [ ] **Step 3a: Let `Character.svelte` accept an initial** — modify `src/lib/onboarding/Character.svelte` so the seed comes from an optional `initial` prop (back-compatible — onboarding passes nothing). Replace its `<script>` seed block:
```svelte
<script lang="ts">
  import { untrack } from 'svelte';
  import TextField from '$lib/design/components/TextField.svelte';
  import Scale from '$lib/design/components/Scale.svelte';

  type Patch = {
    honorific: string;
    address_term: string;
    warmth: number;
    strictness: number;
    sadism: number;
    formality: number;
    verbosity: number;
    crudeness: number;
    wit: number;
  };
  let { onnext, initial = {} }: { onnext: (patch: Patch) => void; initial?: Partial<Patch> } =
    $props();

  const DIALS = [
    'warmth', 'strictness', 'sadism', 'formality', 'verbosity', 'crudeness', 'wit'
  ] as const;
  type Dial = (typeof DIALS)[number];
  const DEFAULTS: Record<Dial, number> = {
    warmth: 40, strictness: 80, sadism: 30, formality: 70, verbosity: 50, crudeness: 30, wit: 75
  };

  let honorific = $state(untrack(() => initial.honorific ?? 'Mistress'));
  let address_term = $state(untrack(() => initial.address_term ?? 'pet'));
  let dials = $state<Record<Dial, number>>(
    untrack(() => Object.fromEntries(DIALS.map((d) => [d, initial[d] ?? DEFAULTS[d]])) as Record<Dial, number>)
  );
</script>
```
The markup/`<style>` below the script stay exactly as they are (the `{#each DIALS as d}` block and the `onnext({ honorific, address_term, ...dials })` button are unchanged).

- [ ] **Step 3b: Character spoke** — `src/routes/character/+page.svelte`:
```svelte
<script lang="ts">
  import SpokeHeader from '$lib/spokes/SpokeHeader.svelte';
  import Character from '$lib/onboarding/Character.svelte';
  import { session } from '$lib/stores/session.svelte';
  import { getCharacter, putCharacter } from '$lib/api/profile';

  type Char = {
    name: string | null;
    honorific: string;
    address_term: string;
    pronouns: string;
    archetype_blend: Record<string, number>;
    warmth: number;
    strictness: number;
    sadism: number;
    formality: number;
    verbosity: number;
    crudeness: number;
    wit: number;
  };

  let char = $state<Char | null>(null);
  let editing = $state(false);
  let saved = $state(false);

  async function load() {
    if (!session.profileId) return;
    char = (await getCharacter(session.profileId)) as Char;
  }
  $effect(() => {
    load();
  });

  async function onSave(patch: Record<string, unknown>) {
    await putCharacter(session.profileId!, patch);
    editing = false;
    saved = true;
    setTimeout(() => (saved = false), 2000);
    await load();
  }

  const DIALS = ['warmth', 'strictness', 'sadism', 'formality', 'verbosity', 'crudeness', 'wit'] as const;
</script>

<SpokeHeader title="Character" />

{#if !char}
  <p class="label pad">Loading…</p>
{:else if editing}
  <div class="pad">
    <Character onnext={onSave} initial={char} />
  </div>
{:else}
  <div class="pad">
    <div class="row">
      <h1 class="display">{char.honorific}</h1>
      <button class="edit" onclick={() => (editing = true)}>Edit</button>
    </div>
    {#if saved}<p class="ok label">saved</p>{/if}
    <p>She calls you <strong>{char.address_term}</strong> · {char.pronouns}</p>
    <ul class="ledger dials">
      {#each DIALS as d}
        <li>{d}: {char[d]}</li>
      {/each}
    </ul>
  </div>
{/if}

<style>
  .pad {
    max-width: 720px;
    margin: 0 auto;
    padding: 24px 16px;
  }
  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .edit {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    background: transparent;
    color: var(--paper);
    border: 1px solid var(--paper);
    padding: 6px 12px;
    cursor: pointer;
  }
  .ok {
    color: var(--accent);
  }
  .dials {
    list-style: none;
    padding: 0;
    columns: 2;
  }
</style>
```

- [ ] **Step 4: Run** — `npx vitest run src/routes/character/page.test.ts src/lib/onboarding` → PASS (the character spoke test + the existing onboarding tests, since Character.svelte stays back-compatible); `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add src/lib/onboarding/Character.svelte src/routes/character/
git commit -m "feat(fe): Character spoke — view + edit (honorific/address + 7 dials)"
```

---

## Task 6: Settings — well-being controls + delete-everything

**Files:** Create `src/routes/settings/+page.svelte`, `src/routes/settings/page.test.ts`.

- [ ] **Step 1: Write the failing test** — `src/routes/settings/page.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/safety', () => ({
  getSafety: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: true })),
  setHiatus: vi.fn(async (_id, on) => ({ is_halted: false, on_hiatus: on, consent_check_due: true })),
  lowerLimit: vi.fn(async (_id, kink, rating) => ({ kink, rating })),
  consentCheck: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: false })),
  deleteProfile: vi.fn(async () => null)
}));

import Page from './+page.svelte';
import { session } from '$lib/stores/session.svelte';

beforeEach(() => {
  session.setProfileId('p1');
});

test('shows well-being controls and toggles hiatus', async () => {
  const api = await import('$lib/api/safety');
  render(Page);
  const toggle = await screen.findByRole('button', { name: /pause training/i });
  toggle.click();
  await vi.waitFor(() => expect(api.setHiatus).toHaveBeenCalledWith('p1', true));
});

test('consent check-in surfaces when due', async () => {
  render(Page);
  expect(await screen.findByText(/check-in due/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run** — `npx vitest run src/routes/settings/page.test.ts` → FAIL.

- [ ] **Step 3: Implement** — `src/routes/settings/+page.svelte`:
```svelte
<script lang="ts">
  import { goto } from '$app/navigation';
  import SpokeHeader from '$lib/spokes/SpokeHeader.svelte';
  import TextField from '$lib/design/components/TextField.svelte';
  import SegmentedControl from '$lib/design/components/SegmentedControl.svelte';
  import { session } from '$lib/stores/session.svelte';
  import {
    getSafety, setHiatus, lowerLimit, consentCheck, deleteProfile, type SafetyState
  } from '$lib/api/safety';
  import type { KinkRating } from '$lib/api/profile';

  let state = $state<SafetyState | null>(null);
  let limitKink = $state('');
  let limitRating = $state<'soft_limit' | 'hard_limit'>('hard_limit');
  let confirmingDelete = $state(false);
  let note = $state<string | null>(null);

  async function load() {
    if (!session.profileId) return;
    state = await getSafety(session.profileId);
  }
  $effect(() => {
    load();
  });

  function flash(msg: string) {
    note = msg;
    setTimeout(() => (note = null), 2500);
  }
  async function toggleHiatus() {
    state = await setHiatus(session.profileId!, !(state?.on_hiatus ?? false));
    flash(state.on_hiatus ? 'Training paused.' : 'Training resumed.');
  }
  async function tightenLimit() {
    if (!limitKink.trim()) return;
    await lowerLimit(session.profileId!, limitKink.trim(), limitRating as KinkRating);
    flash(`"${limitKink}" set to ${limitRating.replace('_', ' ')}.`);
    limitKink = '';
  }
  async function acknowledgeConsent() {
    state = await consentCheck(session.profileId!);
    flash('Consent check-in recorded.');
  }
  async function reallyDelete() {
    await deleteProfile(session.profileId!);
    session.clear();
    await goto('/onboarding/consent');
  }
</script>

<SpokeHeader title="Settings & well-being" />

<div class="pad sections">
  {#if note}<p class="ok label">{note}</p>{/if}

  <section>
    <h2 class="label">Hiatus</h2>
    <p class="muted">Pause training with no penalty. Nothing counts against you while paused.</p>
    <button class="ctl" onclick={toggleHiatus}>
      {state?.on_hiatus ? 'Resume training' : 'Pause training (hiatus)'}
    </button>
  </section>

  <section>
    <h2 class="label">Tighten a limit</h2>
    <p class="muted">Honored immediately — she sees the change on her next turn.</p>
    <TextField label="Kink" value={limitKink} oninput={(v) => (limitKink = v)} />
    <div class="seg">
      <SegmentedControl
        options={[
          { value: 'soft_limit', label: 'Soft', tone: 'danger-muted' },
          { value: 'hard_limit', label: 'Hard', tone: 'danger' }
        ]}
        value={limitRating}
        onchange={(v) => (limitRating = v as 'soft_limit' | 'hard_limit')}
      />
    </div>
    <button class="ctl" onclick={tightenLimit}>Apply</button>
  </section>

  <section>
    <h2 class="label">Consent check-in</h2>
    {#if state?.consent_check_due}
      <p class="due">Check-in due — is this still right for you?</p>
    {:else}
      <p class="muted">Up to date.</p>
    {/if}
    <button class="ctl" onclick={acknowledgeConsent}>I'm still in</button>
  </section>

  <section class="danger-zone">
    <h2 class="label">Delete everything</h2>
    <p class="muted">Permanently erases your profile and all data. This cannot be undone.</p>
    {#if !confirmingDelete}
      <button class="ctl danger" onclick={() => (confirmingDelete = true)}>Delete everything</button>
    {:else}
      <p class="due">Are you absolutely sure?</p>
      <div class="actions">
        <button class="ctl" onclick={() => (confirmingDelete = false)}>Cancel</button>
        <button class="ctl danger" onclick={reallyDelete}>Yes, delete it all</button>
      </div>
    {/if}
  </section>
</div>

<style>
  .pad {
    max-width: 640px;
    margin: 0 auto;
    padding: 24px 16px;
  }
  .sections {
    display: grid;
    gap: 28px;
  }
  .muted {
    color: var(--muted);
  }
  .due {
    color: var(--accent);
  }
  .ok {
    color: var(--accent);
  }
  .seg {
    margin: 8px 0;
  }
  .ctl {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: var(--paper);
    color: var(--ink);
    border: 1px solid var(--paper);
    padding: 12px 18px;
    cursor: pointer;
    margin-top: 8px;
  }
  .ctl.danger {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--paper);
  }
  .actions {
    display: flex;
    gap: 12px;
  }
  .danger-zone {
    border: 1px solid var(--accent-muted);
    padding: 16px;
  }
</style>
```

- [ ] **Step 4: Run** — `npx vitest run src/routes/settings/page.test.ts` → PASS; `npm run check` clean; `npm run build` succeeds.

- [ ] **Step 5: Commit**
```bash
git add src/routes/settings/
git commit -m "feat(fe): Settings — hiatus, tighten-a-limit, consent check-in, delete-everything"
```

---

## Task 7: Playwright setup (config + scripts + CI job)

**Files:** Modify `package.json`; create `playwright.config.ts`; modify `.github/workflows/ci.yml`.

- [ ] **Step 1: Add the dependency + script** — install and wire scripts:
```bash
npm install -D @playwright/test@1.49.1
```
In `package.json` `scripts`, add:
```json
    "test:e2e": "playwright test"
```

- [ ] **Step 2: Playwright config** — `playwright.config.ts` (build once, serve the adapter-node/preview server; all `/api/*` is stubbed per-test so no backend is needed):
```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'on-first-retry'
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run build && npm run preview -- --port 4173',
    url: 'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000
  }
});
```

- [ ] **Step 3: Add the CI job** — in `.github/workflows/ci.yml`, add a third job (sibling to `backend` and `frontend`):
```yaml
  e2e:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - run: npm run test:e2e
```

- [ ] **Step 4: Verify config loads** — `npx playwright test --list` prints the (currently empty) test list with no config error. (Tests are added in Task 8.)

- [ ] **Step 5: Commit**
```bash
git add package.json package-lock.json playwright.config.ts .github/workflows/ci.yml
git commit -m "build(fe): Playwright config + e2e CI job (no backend; API mocked per-test)"
```

---

## Task 8: Playwright E2E specs (API mocked via route interception)

**Files:** Create `e2e/fixtures.ts`, `e2e/onboarding.spec.ts`, `e2e/spokes.spec.ts`, `e2e/safety.spec.ts`.

- [ ] **Step 1: Shared route-mock fixture** — `e2e/fixtures.ts`:
```ts
import type { Page } from '@playwright/test';

// Minimal in-memory backend stub. Routes are matched by method + path suffix.
export async function mockApi(page: Page) {
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname; // e.g. /api/onboarding/profile
    const method = req.method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path.endsWith('/api/onboarding/questionnaire') && method === 'GET') {
      return json({
        statements: [
          { id: 'q1', archetype: 'submissive', text: 'I want to be told what to do.' },
          { id: 'q2', archetype: 'slave', text: 'I want to surrender control.' }
        ],
        kinks: ['bondage', 'spanking'],
        answer_scale: { min: 0, max: 4 }
      });
    }
    if (path.endsWith('/api/onboarding/profile') && method === 'POST') {
      return json({ id: 'e2e-profile', intensity_ceiling: 50 }, 201);
    }
    if (path.includes('/archetype') && method === 'POST') return json({ scores: { submissive: 80 } });
    if (path.endsWith('/kinks') && method === 'PUT') return json({ count: 1 });
    if (path.endsWith('/toys') && method === 'POST') return json({ name: 'x', type: 'y' }, 201);
    if (path.endsWith('/goals') && method === 'POST') return json({ title: 'g', description: '', status: 'active' }, 201);
    if (path.endsWith('/so-context') && method === 'PUT') return json({ description: '', values: null, dynamic: null });
    if (path.endsWith('/character') && method === 'GET') return json(CHARACTER);
    if (path.endsWith('/character') && method === 'PUT') return json(CHARACTER);
    if (path.endsWith('/preferences') && method === 'PUT') return json({ intensity_ceiling: 50, aftercare_prefs: null });
    if (path.endsWith('/safeword') && method === 'POST')
      return json({ scene_halted: true, denial_lifted: 0, merit_penalty: 0, aftercare: 'rest a while', message: "Okay — we're stopping now." });
    if (path.endsWith('/resume') && method === 'POST') return json(SAFE_OK);
    if (path.endsWith('/safety') && method === 'GET') return json(SAFE_OK);
    if (path.endsWith('/hiatus') && method === 'POST') return json({ ...SAFE_OK, on_hiatus: true });
    // assembled profile GET (path ends with the bare profile id)
    if (/\/api\/profile\/[^/]+$/.test(path) && method === 'GET') return json(PROFILE);
    return json({}, 200);
  });
}

const CHARACTER = {
  name: null, honorific: 'Headmistress', address_term: 'student', pronouns: 'she/her',
  archetype_blend: { governess: 70, drill_instructor: 30 },
  warmth: 40, strictness: 80, sadism: 30, formality: 70, verbosity: 50, crudeness: 30, wit: 75,
  signature_flavor: null
};
const SAFE_OK = { is_halted: false, on_hiatus: false, consent_check_due: false };
const PROFILE = {
  id: 'e2e-profile', intensity_ceiling: 50, aftercare_prefs: 'tea',
  archetype_scores: { submissive: 80, slave: 20 },
  kinks: [{ kink: 'bondage', rating: 'favorite' }],
  toys: [{ name: 'Apex', type: 'vibrator' }],
  goals: [{ title: 'Posture', description: '', status: 'active' }],
  so_context: { description: 'my partner', values: null, dynamic: null },
  character: CHARACTER
};
```

- [ ] **Step 2: Onboarding happy-path spec** — `e2e/onboarding.spec.ts`:
```ts
import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';

test('consent gate creates a profile and advances the wizard', async ({ page }) => {
  await mockApi(page);
  await page.goto('/onboarding/consent');

  await expect(page.getByRole('heading', { name: /the frame/i })).toBeVisible();
  // Begin is gated until both boxes are checked
  await page.getByRole('button', { name: /begin/i }).click();
  await expect(page).toHaveURL(/\/onboarding\/consent/);

  await page.getByLabel(/18 or older/i).check();
  await page.getByLabel(/i consent/i).check();
  await page.getByRole('button', { name: /begin/i }).click();

  // advances to the archetype step (questionnaire renders scales)
  await expect(page).toHaveURL(/\/onboarding\/archetype/);
  await expect(page.getByRole('slider').first()).toBeVisible();
});
```

- [ ] **Step 3: Spokes spec** — `e2e/spokes.spec.ts`:
```ts
import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';

// Seed a profile id in localStorage so the guard lets us into the spokes.
test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => localStorage.setItem('smistress.profileId', 'e2e-profile'));
});

test('profile spoke shows the assembled dossier', async ({ page }) => {
  await page.goto('/profile');
  await expect(page.getByText('Headmistress')).toBeVisible();
  await expect(page.getByText('Apex')).toBeVisible();
  await expect(page.getByText(/bondage/i)).toBeVisible();
});

test('character spoke reveals the edit form with 7 dials', async ({ page }) => {
  await page.goto('/character');
  await expect(page.getByRole('heading', { name: 'Headmistress' })).toBeVisible();
  await page.getByRole('button', { name: /edit/i }).click();
  await expect(page.getByRole('slider')).toHaveCount(7);
});
```

- [ ] **Step 4: Safety spec** — `e2e/safety.spec.ts`:
```ts
import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => localStorage.setItem('smistress.profileId', 'e2e-profile'));
});

test('SAFE button pre-halts, confirm shows the calm receipt', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: /safe/i }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByText(/stop everything\?/i)).toBeVisible();

  await page.getByRole('button', { name: /stop everything/i }).click();
  await expect(page.getByText(/stopping now/i)).toBeVisible();
  await expect(page.getByText(/rest a while/i)).toBeVisible();
});
```
Run them: `npm run test:e2e`.

- [ ] **Step 5: Commit**
```bash
git add e2e/
git commit -m "test(fe): Playwright E2E — onboarding, spokes, safety stop (API mocked)"
```

---

## Task 9: Full verification + milestone wrap

**Files:** none (verification) — then PR.

- [ ] **Step 1: Frontend checks** — from `frontend/`: `npx vitest run` (all green), `npm run check` (svelte-check clean), `npm run build` (adapter-node build succeeds), `npm run test:e2e` (Playwright green).
- [ ] **Step 2: Push + CI green**
```bash
git push -u origin feat/m9b-spokes-safety
```
CI now runs three jobs: `backend`, `frontend` (vitest + build), `e2e` (Playwright). Confirm all pass.
- [ ] **Step 3: Open the PR**
```bash
gh pr create --base master --head feat/m9b-spokes-safety \
  --title "M9b: Profile/Character spokes + safety shell + Playwright" \
  --body "Completes the Phase-A frontend: view-edit spokes, the always-on safety shell (SAFE button → pre-halt → confirm → calm stop + well-being + delete), and a mocked-API Playwright suite. See docs/superpowers/plans/2026-06-07-core-obedience-loop-m9b-spokes-safety-shell.md"
```

---

## Verification (end-to-end for M9b)

1. **Safety shell (A6):** the SAFE button pre-halts (pure client `safety.paused = true`) the instant the sheet opens; confirming calls `POST /safeword` and shows the calm out-of-persona receipt (halted, denial lifted, no merit penalty) + aftercare + crisis resources + resume. Covered by Vitest (`StopSheet.test.ts`) and Playwright (`safety.spec.ts`).
2. **Sub Profile spoke:** loads the assembled profile via `GET /profile/{id}`, renders archetype scores + kinks (hard/soft in crimson) + toys + goals + SO + preferences, and edits each in place via the existing onboarding components → the matching PUT/POST endpoints → reload.
3. **Character spoke:** loads `GET /character`, view + edit (honorific/address + 7 dials) via the reused `Character.svelte` (now `initial`-seeded) → `PUT /character`.
4. **Well-being (A6):** hiatus toggle (`POST /hiatus`), tighten-a-limit (`POST /lower-limit`), consent check-in (`GET/POST` cadence), delete-everything (`DELETE /profile/{id}` → clears session → back to onboarding).
5. **Playwright:** onboarding happy path + spokes + safety, all with `/api/*` stubbed (no backend), runnable in CI.
6. **Green:** Vitest + svelte-check + adapter-node build + Playwright + CI (backend/frontend/e2e).

**M9b is done when** the two view-edit spokes and the deterministic safety shell are live against the real M3/M8 endpoints, well-being + delete-everything work, and the Playwright suite guards the flows in CI — completing Phase A. Phase B remains: the chat surface, live dossier, the typed-safeword input interceptor, tasks/proof, and economy UI.

---

## Self-Review

**Addendum A coverage (Phase-A remainder):**
- A2 spokes: Sub Profile + Character as deep-linkable routes → Tasks 4,5. ✓ (Today/Standing remain Phase B.)
- A6 safety shell: SAFE button + pre-halt + single confirm + calm stop receipt + resume + crisis resources → Task 2. ✓ Well-being grouped (hiatus, lower-a-limit, consent cadence, intensity ceiling via preferences in the profile spoke, delete-everything) → Task 6. ✓
- A6 "scene pre-halts the instant the sheet opens": `safety.preHalt()` sets client state before any network; confirm finalizes via `POST /safeword`. ✓
- A6 typed-phrase interceptor "sits on the chat input": deferred with the chat surface to **Phase B** (no chat input exists yet; the backend already intercepts typed safewords in `generate_reply`). ✓ (noted)
- A7 global safety overlay mounted in root `+layout` (not a route) → Task 2. ✓
- A7 `safety` runes store → Task 1. ✓
- A7 Playwright E2E (onboarding→profile now) → Tasks 7,8. ✓
- Severe Editorial: stop screen is "the one place the severe styling softens" (paper sheet, body type) → Task 2. ✓

**Placeholder scan:** every step ships complete code. The only deferrals are explicitly Phase B (chat surface, live dossier, typed-safeword input interceptor, Today/Standing spokes) — none are placeholders in shipped code.

**Type/name consistency:** `safety` store API (`preHalt`, `cancelPreHalt`, `confirmStop`, `refresh`, `resumeScene`, `paused`, `isHalted`, `onHiatus`, `receipt`) is used identically by `SafeButton`/`StopSheet`/`settings`. `safety.ts` exports (`safeword`, `resume`, `getSafety`, `setHiatus`, `lowerLimit`, `consentCheck`, `deleteProfile`, `StopReceipt`, `SafetyState`) match their call sites. `client.del` added in Task 1 is used by `deleteProfile`. `Character.svelte`'s new `initial?: Partial<Patch>` prop is back-compatible (onboarding passes nothing) and consumed by the character spoke. Profile/Character JSON shapes match the backend `ProfileRead`/`CharacterOut`.

---

## Notes for execution
- **Branch:** `feat/m9b-spokes-safety` (not `master`). Work from `frontend/`. After merge: `git checkout master && git fetch origin --prune && git reset --hard origin/master`.
- **No backend needed:** Vitest mocks `$lib/api/*`; Playwright stubs `/api/*` via `page.route`. CI's `e2e` job installs only the Chromium browser.
- **Svelte 5 runes only.** Components that seed `$state` from props wrap the read in `untrack(...)` to keep `svelte-check` warning-free (established M9 pattern — see `Character.svelte`, `Preferences.svelte`).
- **`getProfile` returns the whole assembled profile** (kinks/toys/goals/SO/scores/character) in one call — the spoke does not need separate list endpoints for viewing.
- **Reuse, don't duplicate:** the spokes mount the existing onboarding components (`KinkSheet`, `Toys`, `Goals`, `SoContext`, `Preferences`, `Character`) for editing — same payload contracts as onboarding.
- **`api.post(url)` with no body** sends no `content-type`/body (M9 `makeClient` contract) — correct for `safeword`/`resume`/`consent-check`.
- **Phase B (deferred):** chat surface + bubbles, live dossier (rank/merit/timers via economy endpoints), the typed-safeword interceptor on the chat input, Today/Standing spokes, proof capture.
```
