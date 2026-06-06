# Milestone 9 (Phase A slice) — PWA Foundation + Onboarding Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Frontend implementers should also use the **frontend-design** skill when crafting the Severe Editorial components.

**Goal:** Stand up the binding Addendum A7 frontend architecture (adapter-node + a SvelteKit BFF proxy to FastAPI + OpenAPI-generated types + runes stores), the **Severe Editorial** design system (CSS-custom-property tokens + the primitives the wizard needs), and the full **onboarding wizard** (consent → archetype → kink/limits sheet → toys → SO → goals → character → preferences → reveal) wired to the M3 endpoints with save-and-resume.

**Architecture:** The browser talks only to SvelteKit; a catch-all server route (`/api/[...path]`) proxies to FastAPI with the API base URL kept server-side (BFF). A typed `client.ts` + per-resource API modules call the same-origin proxy, using types generated from the backend's `openapi.json`. Runes stores hold the created profile id (`session`) and the per-step draft (`onboardingDraft`, localStorage-persisted for save-and-resume). The wizard is a guarded `/onboarding/[step]` flow; the mistress does **not** appear until the post-assembly **reveal**. Tests are Vitest + `@testing-library/svelte` (jsdom); Playwright E2E is M9b.

**Tech Stack:** SvelteKit 2 + Svelte 5 (runes) + TypeScript + Vite + `@vite-pwa/sveltekit` (already scaffolded), `@sveltejs/adapter-node`, `openapi-typescript`, `@testing-library/svelte` + `jsdom`. Backend: one small FastAPI endpoint added (`PUT /profile/{id}/preferences`).

---

## Context

M1 scaffolded `frontend/` (SvelteKit 2, Svelte 5 runes forced, `@vite-pwa/sveltekit`, Vitest, `adapter-auto`) — currently a single page calling `/health` directly. M3–M7 built the backend the wizard targets: `POST /onboarding/profile` (consent gate → `{id, intensity_ceiling}`), `GET /onboarding/questionnaire` (`{statements, kinks, answer_scale}`), `POST /profile/{id}/archetype`, `PUT /profile/{id}/kinks`, `POST/GET /profile/{id}/toys`, `.../goals`, `PUT /profile/{id}/so-context`, `GET/PUT /profile/{id}/character`, `GET /profile/{id}` (assembled). Addendum A is the binding frontend direction.

### Decisions locked (M9 planning)
- **Slice:** foundation (A7 tech architecture) + Severe Editorial design system + the full onboarding wizard. **Profile/Character view-edit spokes + the safety shell are M9b.**
- **Testing:** Vitest + `@testing-library/svelte` component/store/proxy unit tests. **Playwright E2E is deferred** (needs browser binaries + a live backend in CI).
- **Backend gap:** add `PUT /profile/{id}/preferences` (intensity_ceiling, aftercare_prefs) so the late preferences step persists per A4's "each step POSTs to its matching endpoint."
- **Design language:** Severe Editorial (Addendum A1) — CSS custom properties, condensed uppercase display type, monospace for ledger data, sharp corners/hairlines, crimson `#C20E1A` as accent **and** danger. No Tailwind; vanilla CSS + tokens + Svelte components.

### Patterns / constraints
- **Svelte 5 runes** (`$state`/`$derived`/`$props`/`$effect`); runes are forced on in `svelte.config.js`. TypeScript everywhere.
- **BFF:** the client never calls FastAPI directly; it calls same-origin `/api/...` which the server proxies. The FastAPI base URL is a server env var (`API_ORIGIN`, default `http://localhost:8000`), never shipped to the browser.
- **OpenAPI types are committed** (`src/lib/types/api.ts`), regenerated via `npm run gen:api`; CI doesn't need a running backend.
- **CI:** the existing `frontend` job runs `npm ci` → `npx vitest run` → `npm run build`. Keep it; `build` now uses adapter-node (still a static-ish node build). Node 24 is installed.
- **Local dev:** `cd frontend; npm install; npm run dev` (Vite). The backend runs separately (`uv run uvicorn app.main:app`). The Windows broken-Python caveat is backend-only; the frontend uses Node.

## File Structure (under `frontend/` unless noted)
New/changed:
- `svelte.config.js` (→ adapter-node), `vite.config.ts` (test/jsdom block), `package.json` (deps + `gen:api`), `vitest-setup.ts`.
- `src/lib/types/api.ts` (generated), `openapi.json` (committed snapshot), `scripts/dump-openapi.*` (backend openapi export).
- `src/routes/api/[...path]/+server.ts` (BFF proxy).
- `src/lib/api/client.ts`, `src/lib/api/onboarding.ts`, `src/lib/api/profile.ts`.
- `src/lib/design/tokens.css` + `src/lib/design/components/{Button,ProgressRail,SegmentedControl,Scale,TextField,TextArea,NumberField}.svelte`.
- `src/lib/stores/session.svelte.ts`, `src/lib/stores/onboardingDraft.svelte.ts`.
- `src/routes/+layout.svelte` (guard + global styles), `src/routes/onboarding/[step]/+page.svelte` + `steps/` components, `src/routes/onboarding/+layout.ts` (step registry/guard).
- Backend: `backend/app/schemas/onboarding.py` (+`PreferencesIn`), `backend/app/services/profile.py` (+`update_preferences`), `backend/app/api/profile.py` (+`PUT /profile/{id}/preferences`), `backend/tests/api/test_profile_api.py` (append).

---

## Task 1: Toolchain — adapter-node, deps, Vitest component harness

**Files:** `frontend/package.json`, `frontend/svelte.config.js`, `frontend/vite.config.ts`, `frontend/vitest-setup.ts`, `frontend/src/lib/design/components/Hello.svelte` (throwaway harness probe — delete in this task after proving), `frontend/src/lib/smoke.svelte.test.ts`

- [ ] **Step 1: Add deps + scripts.** In `frontend/package.json` add devDependencies: `"@sveltejs/adapter-node": "^5"`, `"openapi-typescript": "^7"`, `"@testing-library/svelte": "^5"`, `"@testing-library/jest-dom": "^6"`, `"jsdom": "^25"`. Add scripts: `"test": "vitest run"`, `"gen:api": "node scripts/dump-openapi.mjs && openapi-typescript openapi.json -o src/lib/types/api.ts"`. Run `npm install`.

- [ ] **Step 2: Switch to adapter-node** in `frontend/svelte.config.js`: replace `import adapter from '@sveltejs/adapter-auto';` with `import adapter from '@sveltejs/adapter-node';` (keep the runes `compilerOptions`).

- [ ] **Step 3: Configure Vitest for components** — `frontend/vite.config.ts` add a `test` block:
```ts
import { sveltekit } from '@sveltejs/kit/vite';
import { SvelteKitPWA } from '@vite-pwa/sveltekit';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [
    sveltekit(),
    SvelteKitPWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'smistress', short_name: 'smistress', display: 'standalone',
        background_color: '#0E0E0E', theme_color: '#0E0E0E'
      }
    })
  ],
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest-setup.ts'],
    include: ['src/**/*.{test,spec}.{js,ts}'],
    globals: true
  }
});
```
And `frontend/vitest-setup.ts`:
```ts
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 4: Prove the component harness** — `frontend/src/lib/design/components/Hello.svelte`:
```svelte
<script lang="ts">
  let { name = 'world' }: { name?: string } = $props();
</script>
<p>hello {name}</p>
```
Test `frontend/src/lib/smoke.svelte.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import Hello from './design/components/Hello.svelte';

test('renders a svelte component under jsdom', () => {
  render(Hello, { name: 'student' });
  expect(screen.getByText('hello student')).toBeInTheDocument();
});
```

- [ ] **Step 5: Run** — from `frontend/`: `npx vitest run`. Expected: the smoke test + the existing `health.test.ts` pass. Then `npm run build` (adapter-node) succeeds. Then delete `Hello.svelte` + `smoke.svelte.test.ts` (they were only to prove the harness) — OR keep them; if you delete, re-run `vitest run` to confirm only `health.test.ts` remains green. **Keep them** is simpler; leave both.

- [ ] **Step 6: Commit**
```bash
git add frontend/package.json frontend/package-lock.json frontend/svelte.config.js \
        frontend/vite.config.ts frontend/vitest-setup.ts frontend/src/lib/design/components/Hello.svelte \
        frontend/src/lib/smoke.svelte.test.ts
git commit -m "build(fe): adapter-node + vitest component harness (@testing-library/svelte)"
```

---

## Task 2: Backend — `PUT /profile/{id}/preferences`

**Files:** `backend/app/schemas/onboarding.py`, `backend/app/services/profile.py`, `backend/app/api/profile.py`, `backend/tests/api/test_profile_api.py` (append)

This is the only backend change M9 needs (the wizard's preferences step). Backend TDD; clear `PYTHONHOME`/`PYTHONPATH` per the dev caveat.

- [ ] **Step 1: Append the failing test** to `backend/tests/api/test_profile_api.py`:
```python
async def test_update_preferences(client):
    pid = await _new_profile(client)
    r = await client.put(f"/profile/{pid}/preferences", json={
        "intensity_ceiling": 70, "aftercare_prefs": "tea and quiet",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["intensity_ceiling"] == 70
    assert body["aftercare_prefs"] == "tea and quiet"


async def test_update_preferences_404(client):
    import uuid
    r = await client.put(f"/profile/{uuid.uuid4()}/preferences", json={"intensity_ceiling": 50})
    assert r.status_code == 404
```

- [ ] **Step 2: Run** — `uv run pytest tests/api/test_profile_api.py -k preferences -v` → FAIL (404/route missing).

- [ ] **Step 3a: Schema** — add to `backend/app/schemas/onboarding.py`:
```python
class PreferencesIn(BaseModel):
    intensity_ceiling: int = Field(default=50, ge=0, le=100)
    aftercare_prefs: str | None = None


class PreferencesOut(BaseModel):
    intensity_ceiling: int
    aftercare_prefs: str | None
    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 3b: Service** — add to `backend/app/services/profile.py`:
```python
async def update_preferences(
    session: AsyncSession, profile_id: uuid.UUID, data: "PreferencesIn"
) -> SubProfile:
    profile = await get_profile(session, profile_id)  # raises ProfileNotFound
    profile.intensity_ceiling = data.intensity_ceiling
    profile.aftercare_prefs = data.aftercare_prefs
    await session.flush()
    return profile
```
Add `PreferencesIn` to the existing `from app.schemas.onboarding import (...)` block at the top of `profile.py`.

- [ ] **Step 3c: Endpoint** — add to `backend/app/api/profile.py` (extend the schema import with `PreferencesIn, PreferencesOut`):
```python
@router.put("/{profile_id}/preferences", response_model=PreferencesOut)
async def update_preferences(
    profile_id: uuid.UUID,
    body: PreferencesIn,
    session: AsyncSession = Depends(get_session),
) -> PreferencesOut:
    try:
        profile = await svc.update_preferences(session, profile_id, body)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return PreferencesOut.model_validate(profile)
```

- [ ] **Step 4: Run** — `uv run pytest tests/api/test_profile_api.py -k preferences -v` → PASS; full backend suite green; `ruff check .` clean.

- [ ] **Step 5: Commit**
```bash
git add backend/app/schemas/onboarding.py backend/app/services/profile.py \
        backend/app/api/profile.py backend/tests/api/test_profile_api.py
git commit -m "feat: add PUT /profile/{id}/preferences (ceiling + aftercare) for onboarding"
```

---

## Task 3: OpenAPI type generation

**Files:** `frontend/scripts/dump-openapi.mjs`, `frontend/openapi.json` (committed), `frontend/src/lib/types/api.ts` (generated, committed)

- [ ] **Step 1: Dump script** — `frontend/scripts/dump-openapi.mjs`:
```js
// Exports the FastAPI OpenAPI schema to openapi.json by invoking the backend.
// Requires the backend deps (uv). Run from frontend/: node scripts/dump-openapi.mjs
import { execSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const py = 'import json,sys; from app.main import app; sys.stdout.write(json.dumps(app.openapi()))';
const out = execSync(`uv --directory ../backend run python -c "${py}"`, { encoding: 'utf8' });
writeFileSync('openapi.json', out);
console.log('wrote openapi.json');
```

- [ ] **Step 2: Generate the types** — from `frontend/` run `npm run gen:api` (dumps `openapi.json`, then `openapi-typescript openapi.json -o src/lib/types/api.ts`). This requires the backend importable via `uv` (clear `PYTHONHOME`/`PYTHONPATH` first on Windows). Commit both `openapi.json` and `src/lib/types/api.ts`.

- [ ] **Step 3: Sanity test** — `frontend/src/lib/types/api.test.ts`:
```ts
import { expect, test } from 'vitest';
import type { paths } from './api';

test('generated api types include the onboarding profile path', () => {
  // compile-time check: the path key must exist on the generated type
  type Created = paths['/onboarding/profile']['post'];
  const ok: boolean = true as Created extends never ? false : true;
  expect(ok).toBe(true);
});
```

- [ ] **Step 4: Run** — `npx vitest run src/lib/types/api.test.ts` PASS; `npm run check` (svelte-check) clean.

- [ ] **Step 5: Commit**
```bash
git add frontend/scripts/dump-openapi.mjs frontend/openapi.json frontend/src/lib/types/api.ts frontend/src/lib/types/api.test.ts
git commit -m "build(fe): generate committed OpenAPI types (openapi-typescript)"
```

---

## Task 4: BFF proxy (`/api/[...path]`)

**Files:** `frontend/src/routes/api/[...path]/+server.ts`, `frontend/src/lib/server/proxy.ts`, `frontend/src/lib/server/proxy.test.ts`

- [ ] **Step 1: Write the failing test** — `frontend/src/lib/server/proxy.test.ts`:
```ts
import { describe, expect, test, vi } from 'vitest';
import { proxyRequest } from './proxy';

describe('proxyRequest', () => {
  test('forwards method + path + body to the API origin and returns the upstream response', async () => {
    const fetchFn = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), { status: 201, headers: { 'content-type': 'application/json' } })
    );
    const req = new Request('http://localhost/api/onboarding/profile', {
      method: 'POST', body: JSON.stringify({ is_adult: true }), headers: { 'content-type': 'application/json' }
    });
    const res = await proxyRequest(req, 'onboarding/profile', 'http://api:8000', fetchFn);
    expect(res.status).toBe(201);
    const [calledUrl, init] = fetchFn.mock.calls[0];
    expect(calledUrl).toBe('http://api:8000/onboarding/profile');
    expect(init.method).toBe('POST');
  });

  test('preserves query string', async () => {
    const fetchFn = vi.fn(async () => new Response('{}', { status: 200 }));
    const req = new Request('http://localhost/api/profile/x/disposition?q=1');
    await proxyRequest(req, 'profile/x/disposition', 'http://api:8000', fetchFn);
    expect(fetchFn.mock.calls[0][0]).toBe('http://api:8000/profile/x/disposition?q=1');
  });
});
```

- [ ] **Step 2: Run** — `npx vitest run src/lib/server/proxy.test.ts` → FAIL (no module).

- [ ] **Step 3: Implement** — `frontend/src/lib/server/proxy.ts`:
```ts
// Pure proxy core (testable without SvelteKit). Forwards a request to the API origin.
export async function proxyRequest(
  request: Request,
  path: string,
  apiOrigin: string,
  fetchFn: typeof fetch = fetch
): Promise<Response> {
  const incoming = new URL(request.url);
  const target = `${apiOrigin}/${path}${incoming.search}`;
  const headers = new Headers(request.headers);
  headers.delete('host');
  const method = request.method;
  const body = method === 'GET' || method === 'HEAD' ? undefined : await request.arrayBuffer();
  const upstream = await fetchFn(target, {
    method,
    headers,
    body,
    // forward cookies for a future authed backend; harmless now
    redirect: 'manual'
  });
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: upstream.headers
  });
}
```
And the SvelteKit catch-all `frontend/src/routes/api/[...path]/+server.ts`:
```ts
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';
import { proxyRequest } from '$lib/server/proxy';

const API_ORIGIN = env.API_ORIGIN ?? 'http://localhost:8000';

const handler: RequestHandler = ({ request, params }) =>
  proxyRequest(request, params.path, API_ORIGIN);

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
```

- [ ] **Step 4: Run** — `npx vitest run src/lib/server/proxy.test.ts` PASS; `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/routes/api/ frontend/src/lib/server/
git commit -m "feat(fe): add SvelteKit BFF proxy to FastAPI (API origin server-side)"
```

---

## Task 5: Typed API client + resource modules

**Files:** `frontend/src/lib/api/client.ts`, `frontend/src/lib/api/onboarding.ts`, `frontend/src/lib/api/profile.ts`, `frontend/src/lib/api/client.test.ts`

- [ ] **Step 1: Write the failing test** — `frontend/src/lib/api/client.test.ts`:
```ts
import { describe, expect, test, vi } from 'vitest';
import { ApiError, makeClient } from './client';

describe('api client', () => {
  test('GET returns parsed JSON', async () => {
    const fetchFn = vi.fn(async () => new Response(JSON.stringify({ a: 1 }), { status: 200 }));
    const api = makeClient('', fetchFn);
    expect(await api.get('/api/x')).toEqual({ a: 1 });
  });

  test('non-2xx throws ApiError with status + detail', async () => {
    const fetchFn = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'nope' }), { status: 422 })
    );
    const api = makeClient('', fetchFn);
    await expect(api.post('/api/x', { y: 1 })).rejects.toMatchObject({ status: 422, detail: 'nope' });
    expect(ApiError).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run** — FAIL (no module).

- [ ] **Step 3: Implement** — `frontend/src/lib/api/client.ts`:
```ts
export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(`API ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function parse(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export function makeClient(base = '', fetchFn: typeof fetch = fetch) {
  async function request(method: string, path: string, body?: unknown): Promise<unknown> {
    const res = await fetchFn(`${base}${path}`, {
      method,
      headers: body === undefined ? undefined : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    const data = await parse(res);
    if (!res.ok) {
      const detail = data && typeof data === 'object' && 'detail' in data ? (data as { detail: unknown }).detail : data;
      throw new ApiError(res.status, detail);
    }
    return data;
  }
  return {
    get: (p: string) => request('GET', p),
    post: (p: string, b?: unknown) => request('POST', p, b),
    put: (p: string, b?: unknown) => request('PUT', p, b)
  };
}

// Browser singleton: talks to the same-origin BFF proxy.
export const api = makeClient('');
```
`frontend/src/lib/api/onboarding.ts`:
```ts
import { api } from './client';

export interface Questionnaire {
  statements: { id: string; archetype: string; text: string }[];
  kinks: string[];
  answer_scale: { min: number; max: number };
}
export interface ProfileCreated { id: string; intensity_ceiling: number; }

export const getQuestionnaire = () => api.get('/api/onboarding/questionnaire') as Promise<Questionnaire>;
export const createProfile = (consent: { is_adult: boolean; consent_acknowledged: boolean }) =>
  api.post('/api/onboarding/profile', consent) as Promise<ProfileCreated>;
```
`frontend/src/lib/api/profile.ts`:
```ts
import { api } from './client';

export type KinkRating = 'favorite' | 'like' | 'curious' | 'soft_limit' | 'hard_limit' | 'na';

export const submitArchetype = (id: string, answers: Record<string, number>) =>
  api.post(`/api/profile/${id}/archetype`, { answers });
export const putKinks = (id: string, entries: { kink: string; rating: KinkRating }[]) =>
  api.put(`/api/profile/${id}/kinks`, { entries });
export const addToy = (id: string, toy: { name: string; type: string; intiface_capable?: boolean; notes?: string }) =>
  api.post(`/api/profile/${id}/toys`, toy);
export const addGoal = (id: string, goal: { title: string; description?: string }) =>
  api.post(`/api/profile/${id}/goals`, goal);
export const putSoContext = (id: string, ctx: { description?: string; values?: string; dynamic?: string }) =>
  api.put(`/api/profile/${id}/so-context`, ctx);
export const putCharacter = (id: string, patch: Record<string, unknown>) =>
  api.put(`/api/profile/${id}/character`, patch);
export const getCharacter = (id: string) => api.get(`/api/profile/${id}/character`);
export const putPreferences = (id: string, prefs: { intensity_ceiling: number; aftercare_prefs?: string | null }) =>
  api.put(`/api/profile/${id}/preferences`, prefs);
export const getProfile = (id: string) => api.get(`/api/profile/${id}`);
```

- [ ] **Step 4: Run** — `npx vitest run src/lib/api/client.test.ts` PASS; `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/api/
git commit -m "feat(fe): typed API client + onboarding/profile resource modules"
```

---

## Task 6: Severe Editorial tokens + Button + ProgressRail

**Files:** `frontend/src/lib/design/tokens.css`, `frontend/src/routes/+layout.svelte` (import tokens), `frontend/src/lib/design/components/Button.svelte`, `frontend/src/lib/design/components/ProgressRail.svelte`, tests.

- [ ] **Step 1: Write the failing tests** — `frontend/src/lib/design/components/Button.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import Button from './Button.svelte';

test('renders label and fires onclick', async () => {
  const onclick = vi.fn();
  render(Button, { label: 'NEXT', onclick });
  const btn = screen.getByRole('button', { name: 'NEXT' });
  btn.click();
  expect(onclick).toHaveBeenCalledOnce();
});

test('disabled button does not fire', async () => {
  const onclick = vi.fn();
  render(Button, { label: 'NEXT', onclick, disabled: true });
  screen.getByRole('button').click();
  expect(onclick).not.toHaveBeenCalled();
});
```
`frontend/src/lib/design/components/ProgressRail.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import ProgressRail from './ProgressRail.svelte';

test('marks the current step', () => {
  render(ProgressRail, { total: 9, current: 3 });
  expect(screen.getByText('3 / 9')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run** — FAIL (no modules).

- [ ] **Step 3a: Tokens** — `frontend/src/lib/design/tokens.css` (Addendum A1, verbatim values):
```css
:root {
  --ink: #0E0E0E;
  --raised: #161616;
  --muted: #777;
  --paper: #FAFAFA;
  --accent: #C20E1A;          /* accent AND danger/stop — one color, deliberately */
  --accent-muted: #7d1a20;    /* muted-crimson for soft limits */
  --hairline: #2a2a2a;
  --space: 8px;
  --font-display: ui-sans-serif, 'Arial Narrow', system-ui, sans-serif;
  --font-body: ui-sans-serif, system-ui, sans-serif;
  --font-mono: ui-monospace, 'SFMono-Regular', Menlo, monospace;
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--ink); color: var(--paper); font-family: var(--font-body); }
.display { font-family: var(--font-display); text-transform: uppercase; letter-spacing: 0.06em; }
.label { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.72rem; color: var(--muted); }
.ledger { font-family: var(--font-mono); }
```
Import it in `frontend/src/routes/+layout.svelte`:
```svelte
<script lang="ts">
  import '$lib/design/tokens.css';
  let { children } = $props();
</script>
{@render children()}
```

- [ ] **Step 3b: Button** — `frontend/src/lib/design/components/Button.svelte`:
```svelte
<script lang="ts">
  let {
    label,
    onclick,
    disabled = false,
    variant = 'solid'
  }: { label: string; onclick?: () => void; disabled?: boolean; variant?: 'solid' | 'ghost' | 'danger' } = $props();
</script>

<button class="btn {variant}" {disabled} onclick={() => onclick?.()}>{label}</button>

<style>
  .btn {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    border: 1px solid var(--paper);
    background: var(--paper);
    color: var(--ink);
    padding: 12px 20px;
    cursor: pointer;
    border-radius: 0;
  }
  .ghost { background: transparent; color: var(--paper); }
  .danger { background: var(--accent); border-color: var(--accent); color: var(--paper); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
```

- [ ] **Step 3c: ProgressRail** — `frontend/src/lib/design/components/ProgressRail.svelte`:
```svelte
<script lang="ts">
  let { total, current }: { total: number; current: number } = $props();
</script>

<div class="rail">
  <span class="label ledger">{current} / {total}</span>
  <div class="ticks">
    {#each Array(total) as _, i}
      <span class="tick" class:done={i < current}></span>
    {/each}
  </div>
</div>

<style>
  .rail { display: flex; align-items: center; gap: 12px; }
  .ticks { display: flex; gap: 4px; }
  .tick { width: 18px; height: 2px; background: var(--hairline); }
  .tick.done { background: var(--accent); }
</style>
```

- [ ] **Step 4: Run** — both component tests PASS; `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/design/ frontend/src/routes/+layout.svelte
git commit -m "feat(fe): Severe Editorial tokens + Button + ProgressRail primitives"
```

---

## Task 7: SegmentedControl + Scale + form fields

**Files:** `frontend/src/lib/design/components/{SegmentedControl,Scale,TextField,TextArea,NumberField}.svelte` + tests for SegmentedControl and Scale.

- [ ] **Step 1: Write the failing tests** — `frontend/src/lib/design/components/SegmentedControl.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import SegmentedControl from './SegmentedControl.svelte';

test('selects an option and reports the value', async () => {
  const onchange = vi.fn();
  render(SegmentedControl, {
    options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }],
    value: 'a',
    onchange
  });
  screen.getByRole('button', { name: 'B' }).click();
  expect(onchange).toHaveBeenCalledWith('b');
});
```
`frontend/src/lib/design/components/Scale.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import Scale from './Scale.svelte';

test('renders a slider and reports changes', async () => {
  const onchange = vi.fn();
  render(Scale, { min: 0, max: 4, value: 2, onchange });
  const slider = screen.getByRole('slider') as HTMLInputElement;
  expect(slider.value).toBe('2');
});
```

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement** the five components.

`SegmentedControl.svelte` (used by the kink sheet; supports a per-option `tone` for crimson/muted-crimson):
```svelte
<script lang="ts">
  type Opt = { value: string; label: string; tone?: 'normal' | 'danger' | 'danger-muted' };
  let { options, value, onchange }:
    { options: Opt[]; value: string | null; onchange: (v: string) => void } = $props();
</script>

<div class="seg">
  {#each options as o}
    <button
      class="opt {o.tone ?? 'normal'}"
      class:selected={o.value === value}
      onclick={() => onchange(o.value)}
    >{o.label}</button>
  {/each}
</div>

<style>
  .seg { display: inline-flex; border: 1px solid var(--hairline); }
  .opt {
    font-family: var(--font-mono); font-size: 0.72rem; text-transform: uppercase;
    background: var(--ink); color: var(--muted); border: 0; border-right: 1px solid var(--hairline);
    padding: 6px 10px; cursor: pointer;
  }
  .opt:last-child { border-right: 0; }
  .opt.selected { background: var(--paper); color: var(--ink); }
  .opt.danger.selected { background: var(--accent); color: var(--paper); }
  .opt.danger-muted.selected { background: var(--accent-muted); color: var(--paper); }
</style>
```
`Scale.svelte` (archetype drag scale — a styled range input is the accessible, testable form):
```svelte
<script lang="ts">
  let { min, max, value, onchange }:
    { min: number; max: number; value: number; onchange: (v: number) => void } = $props();
</script>
<input
  type="range" {min} {max} step="1" value={String(value)}
  oninput={(e) => onchange(Number((e.currentTarget as HTMLInputElement).value))}
/>
<style>input { width: 100%; accent-color: var(--accent); }</style>
```
`TextField.svelte`:
```svelte
<script lang="ts">
  let { label, value = '', oninput, placeholder = '' }:
    { label: string; value?: string; oninput: (v: string) => void; placeholder?: string } = $props();
</script>
<label class="field">
  <span class="label">{label}</span>
  <input value={value} placeholder={placeholder}
    oninput={(e) => oninput((e.currentTarget as HTMLInputElement).value)} />
</label>
<style>
  .field { display: block; }
  input { width: 100%; background: var(--raised); color: var(--paper); border: 1px solid var(--hairline); padding: 10px; border-radius: 0; }
</style>
```
`TextArea.svelte` (same as TextField but a `<textarea>`):
```svelte
<script lang="ts">
  let { label, value = '', oninput }:
    { label: string; value?: string; oninput: (v: string) => void } = $props();
</script>
<label class="field">
  <span class="label">{label}</span>
  <textarea value={value} rows="3"
    oninput={(e) => oninput((e.currentTarget as HTMLTextAreaElement).value)}></textarea>
</label>
<style>
  .field { display: block; }
  textarea { width: 100%; background: var(--raised); color: var(--paper); border: 1px solid var(--hairline); padding: 10px; border-radius: 0; font-family: var(--font-body); }
</style>
```
`NumberField.svelte` (intensity ceiling 0–100):
```svelte
<script lang="ts">
  let { label, value, min = 0, max = 100, oninput }:
    { label: string; value: number; min?: number; max?: number; oninput: (v: number) => void } = $props();
</script>
<label class="field">
  <span class="label">{label}</span>
  <input type="number" value={String(value)} {min} {max}
    oninput={(e) => oninput(Number((e.currentTarget as HTMLInputElement).value))} />
</label>
<style>
  .field { display: block; }
  input { width: 100%; background: var(--raised); color: var(--paper); border: 1px solid var(--hairline); padding: 10px; font-family: var(--font-mono); }
</style>
```

- [ ] **Step 4: Run** — both tests PASS; `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/design/components/
git commit -m "feat(fe): SegmentedControl, Scale, and form-field primitives"
```

---

## Task 8: Stores — session + onboardingDraft

**Files:** `frontend/src/lib/stores/session.svelte.ts`, `frontend/src/lib/stores/onboardingDraft.svelte.ts`, tests.

- [ ] **Step 1: Write the failing test** — `frontend/src/lib/stores/onboardingDraft.test.ts`:
```ts
import { beforeEach, expect, test } from 'vitest';
import { onboardingDraft } from './onboardingDraft.svelte';

beforeEach(() => localStorage.clear());

test('persists and reloads draft answers', () => {
  onboardingDraft.set('archetype', { q1: 4 });
  expect(onboardingDraft.get('archetype')).toEqual({ q1: 4 });
  // a fresh read reflects what was written (localStorage-backed)
  expect(JSON.parse(localStorage.getItem('smistress.onboarding') ?? '{}').archetype).toEqual({ q1: 4 });
});

test('clear wipes the draft', () => {
  onboardingDraft.set('toys', [{ name: 'x', type: 'y' }]);
  onboardingDraft.clear();
  expect(onboardingDraft.get('toys')).toBeUndefined();
});
```
`frontend/src/lib/stores/session.test.ts`:
```ts
import { beforeEach, expect, test } from 'vitest';
import { session } from './session.svelte';

beforeEach(() => localStorage.clear());

test('stores and clears the profile id', () => {
  session.setProfileId('abc');
  expect(session.profileId).toBe('abc');
  session.clear();
  expect(session.profileId).toBeNull();
});
```

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement** — `frontend/src/lib/stores/session.svelte.ts`:
```ts
const KEY = 'smistress.profileId';

function load(): string | null {
  if (typeof localStorage === 'undefined') return null;
  return localStorage.getItem(KEY);
}

class Session {
  profileId = $state<string | null>(load());

  setProfileId(id: string) {
    this.profileId = id;
    if (typeof localStorage !== 'undefined') localStorage.setItem(KEY, id);
  }
  clear() {
    this.profileId = null;
    if (typeof localStorage !== 'undefined') localStorage.removeItem(KEY);
  }
}

export const session = new Session();
```
`frontend/src/lib/stores/onboardingDraft.svelte.ts`:
```ts
const KEY = 'smistress.onboarding';

type Draft = Record<string, unknown>;

function load(): Draft {
  if (typeof localStorage === 'undefined') return {};
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}');
  } catch {
    return {};
  }
}

class OnboardingDraft {
  data = $state<Draft>(load());

  get(step: string): unknown {
    return this.data[step];
  }
  set(step: string, value: unknown) {
    this.data = { ...this.data, [step]: value };
    if (typeof localStorage !== 'undefined') localStorage.setItem(KEY, JSON.stringify(this.data));
  }
  clear() {
    this.data = {};
    if (typeof localStorage !== 'undefined') localStorage.removeItem(KEY);
  }
}

export const onboardingDraft = new OnboardingDraft();
```

> `.svelte.ts` files allow runes (`$state`) outside components. Vitest with the svelte plugin compiles them.

- [ ] **Step 4: Run** — both tests PASS; `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/stores/
git commit -m "feat(fe): session + onboardingDraft runes stores (localStorage-backed)"
```

---

## Task 9: Wizard shell + routing guard + consent step

**Files:** `frontend/src/lib/onboarding/steps.ts` (step registry), `frontend/src/routes/onboarding/+layout.svelte` (rail + footer chrome), `frontend/src/routes/onboarding/[step]/+page.svelte` (step dispatcher), `frontend/src/routes/+page.svelte` (guard/redirect), `frontend/src/lib/onboarding/Consent.svelte`, test.

- [ ] **Step 1: Write the failing test** — `frontend/src/lib/onboarding/Consent.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import Consent from './Consent.svelte';

test('next is disabled until both boxes are checked, then calls onnext', async () => {
  const onnext = vi.fn();
  render(Consent, { onnext });
  const next = screen.getByRole('button', { name: /begin/i });
  next.click();
  expect(onnext).not.toHaveBeenCalled();         // gated
  (screen.getByLabelText(/18/i) as HTMLInputElement).click();
  (screen.getByLabelText(/consent/i) as HTMLInputElement).click();
  screen.getByRole('button', { name: /begin/i }).click();
  expect(onnext).toHaveBeenCalledOnce();
});
```

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3a: Step registry** — `frontend/src/lib/onboarding/steps.ts`:
```ts
export const STEPS = [
  'consent', 'archetype', 'kinks', 'toys', 'so', 'goals', 'character', 'preferences', 'reveal'
] as const;
export type Step = (typeof STEPS)[number];

export function stepIndex(step: string): number {
  return STEPS.indexOf(step as Step);
}
export function nextStep(step: Step): Step | null {
  const i = STEPS.indexOf(step);
  return i >= 0 && i < STEPS.length - 1 ? STEPS[i + 1] : null;
}
```

- [ ] **Step 3b: Consent component** — `frontend/src/lib/onboarding/Consent.svelte`:
```svelte
<script lang="ts">
  let { onnext }: { onnext: (data: { is_adult: boolean; consent_acknowledged: boolean }) => void } = $props();
  let adult = $state(false);
  let consent = $state(false);
  const ready = $derived(adult && consent);
</script>

<h2 class="display">The frame</h2>
<p>This is an adult, consensual training tool. Acknowledge to begin.</p>
<label><input type="checkbox" aria-label="I am 18 or older" bind:checked={adult} /> I am 18 or older.</label>
<label><input type="checkbox" aria-label="I consent" bind:checked={consent} /> I consent and understand I may stop at any time.</label>
<button disabled={!ready} onclick={() => onnext({ is_adult: adult, consent_acknowledged: consent })}>Begin</button>
```

- [ ] **Step 3c: Wizard chrome + dispatcher.** `frontend/src/routes/onboarding/+layout.svelte`:
```svelte
<script lang="ts">
  import { page } from '$app/state';
  import ProgressRail from '$lib/design/components/ProgressRail.svelte';
  import { STEPS, stepIndex } from '$lib/onboarding/steps';
  let { children } = $props();
  const current = $derived(stepIndex(page.params.step ?? 'consent') + 1);
</script>

<header class="wiz-head"><span class="label">Intake</span><ProgressRail total={STEPS.length} {current} /></header>
<main class="wiz-body">{@render children()}</main>

<style>
  .wiz-head { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid var(--hairline); }
  .wiz-body { max-width: 720px; margin: 0 auto; padding: 24px 16px; }
</style>
```
`frontend/src/routes/onboarding/[step]/+page.svelte` (dispatches to the step component; consent shown here, others added in Tasks 10–12):
```svelte
<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import Consent from '$lib/onboarding/Consent.svelte';
  import { createProfile } from '$lib/api/onboarding';
  import { session } from '$lib/stores/session.svelte';
  import { nextStep, type Step } from '$lib/onboarding/steps';

  const step = $derived((page.params.step ?? 'consent') as Step);

  async function advance(from: Step) {
    const n = nextStep(from);
    if (n) await goto(`/onboarding/${n}`);
  }

  async function onConsent(data: { is_adult: boolean; consent_acknowledged: boolean }) {
    const created = await createProfile(data);
    session.setProfileId(created.id);
    await advance('consent');
  }
</script>

{#if step === 'consent'}
  <Consent onnext={onConsent} />
{:else}
  <p>step: {step}</p>
{/if}
```
`frontend/src/routes/+page.svelte` (root guard — redirect into the wizard until a profile exists; once it exists, this is where chat home lands in Phase B):
```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores/session.svelte';
  onMount(() => {
    if (!session.profileId) goto('/onboarding/consent');
  });
</script>
<p>…</p>
```

- [ ] **Step 4: Run** — `npx vitest run src/lib/onboarding/Consent.test.ts` PASS; `npm run check` clean; `npm run build` succeeds.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/onboarding/ frontend/src/routes/onboarding/ frontend/src/routes/+page.svelte
git commit -m "feat(fe): onboarding wizard shell, step registry, guard, consent step"
```

---

## Task 10: Archetype questionnaire step

**Files:** `frontend/src/lib/onboarding/Archetype.svelte`, wire it into `[step]/+page.svelte`, test.

- [ ] **Step 1: Write the failing test** — `frontend/src/lib/onboarding/Archetype.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import Archetype from './Archetype.svelte';

const statements = [
  { id: 'q1', archetype: 'submissive', text: 'A' },
  { id: 'q2', archetype: 'slave', text: 'B' }
];

test('renders a scale per statement and submits the answers map', async () => {
  const onnext = vi.fn();
  render(Archetype, { statements, scale: { min: 0, max: 4 }, onnext });
  expect(screen.getAllByRole('slider')).toHaveLength(2);
  screen.getByRole('button', { name: /next/i }).click();
  expect(onnext).toHaveBeenCalledOnce();
  const answers = onnext.mock.calls[0][0];
  expect(Object.keys(answers)).toEqual(['q1', 'q2']);
});
```

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement** — `frontend/src/lib/onboarding/Archetype.svelte`:
```svelte
<script lang="ts">
  import Scale from '$lib/design/components/Scale.svelte';
  type S = { id: string; archetype: string; text: string };
  let { statements, scale, onnext, initial = {} }:
    { statements: S[]; scale: { min: number; max: number };
      onnext: (answers: Record<string, number>) => void; initial?: Record<string, number> } = $props();

  let answers = $state<Record<string, number>>(
    Object.fromEntries(statements.map((s) => [s.id, initial[s.id] ?? scale.min]))
  );
</script>

<h2 class="display">How you lean</h2>
<ol class="cards">
  {#each statements as s}
    <li class="card">
      <p>{s.text}</p>
      <Scale min={scale.min} max={scale.max} value={answers[s.id]}
        onchange={(v) => (answers = { ...answers, [s.id]: v })} />
    </li>
  {/each}
</ol>
<button onclick={() => onnext(answers)}>Next</button>

<style>
  .cards { list-style: none; padding: 0; display: grid; gap: 16px; }
  .card { background: var(--raised); border: 1px solid var(--hairline); padding: 16px; }
</style>
```
Wire into `[step]/+page.svelte`: on entering the `archetype` step, fetch the questionnaire (`getQuestionnaire`) once and render `<Archetype>`; `onnext` → `submitArchetype(session.profileId, answers)` then `onboardingDraft.set('archetype', answers)` then `advance('archetype')`. (Load the questionnaire via `$effect`/`onMount` and hold it in `$state`; guard `session.profileId`.)

- [ ] **Step 4: Run** — test PASS; `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/onboarding/Archetype.svelte frontend/src/routes/onboarding/
git commit -m "feat(fe): archetype questionnaire step (scale per statement)"
```

---

## Task 11: Kink / limits sheet step

**Files:** `frontend/src/lib/onboarding/KinkSheet.svelte`, wire into `[step]/+page.svelte`, test.

- [ ] **Step 1: Write the failing test** — `frontend/src/lib/onboarding/KinkSheet.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import KinkSheet from './KinkSheet.svelte';

test('rates a kink and submits non-NA entries', async () => {
  const onnext = vi.fn();
  render(KinkSheet, { kinks: ['bondage', 'spanking'], onnext });
  // each row defaults to N-A; rate the first row Hard-limit
  const hardButtons = screen.getAllByRole('button', { name: 'Hard' });
  hardButtons[0].click();
  screen.getByRole('button', { name: /next/i }).click();
  expect(onnext).toHaveBeenCalledOnce();
  const entries = onnext.mock.calls[0][0];
  expect(entries).toEqual([{ kink: 'bondage', rating: 'hard_limit' }]);  // NA rows omitted
});
```

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement** — `frontend/src/lib/onboarding/KinkSheet.svelte` (6-way segmented per row; crimson hard / muted-crimson soft; N-A default, omitted on submit):
```svelte
<script lang="ts">
  import SegmentedControl from '$lib/design/components/SegmentedControl.svelte';
  import type { KinkRating } from '$lib/api/profile';

  let { kinks, onnext, initial = {} }:
    { kinks: string[]; onnext: (entries: { kink: string; rating: KinkRating }[]) => void;
      initial?: Record<string, KinkRating> } = $props();

  const OPTIONS = [
    { value: 'favorite', label: 'Fav' },
    { value: 'like', label: 'Like' },
    { value: 'curious', label: 'Curious' },
    { value: 'soft_limit', label: 'Soft', tone: 'danger-muted' as const },
    { value: 'hard_limit', label: 'Hard', tone: 'danger' as const },
    { value: 'na', label: 'N-A' }
  ];

  let ratings = $state<Record<string, KinkRating>>(
    Object.fromEntries(kinks.map((k) => [k, initial[k] ?? 'na']))
  );

  function submit() {
    const entries = kinks
      .filter((k) => ratings[k] !== 'na')
      .map((k) => ({ kink: k, rating: ratings[k] }));
    onnext(entries);
  }
</script>

<h2 class="display">Your limits</h2>
<p class="label">Hard-limits are never crossed. Soft-limits are approached only with care.</p>
<ul class="grid">
  {#each kinks as k}
    <li class="row">
      <span class="name">{k.replaceAll('_', ' ')}</span>
      <SegmentedControl options={OPTIONS} value={ratings[k]}
        onchange={(v) => (ratings = { ...ratings, [k]: v as KinkRating })} />
    </li>
  {/each}
</ul>
<button onclick={submit}>Next</button>

<style>
  .grid { list-style: none; padding: 0; display: grid; gap: 8px; }
  .row { display: flex; justify-content: space-between; align-items: center; gap: 12px; border-bottom: 1px solid var(--hairline); padding: 6px 0; }
  .name { text-transform: capitalize; }
</style>
```
Wire into `[step]/+page.svelte`: on the `kinks` step use the questionnaire's `kinks` list (already fetched for archetype, or refetch); `onnext` → `putKinks(profileId, entries)` → draft + advance.

- [ ] **Step 4: Run** — test PASS; `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/onboarding/KinkSheet.svelte frontend/src/routes/onboarding/
git commit -m "feat(fe): kink/limits sheet step (6-way segmented, crimson hard/soft)"
```

---

## Task 12: Remaining steps (toys, SO, goals, character, preferences) + reveal

**Files:** `frontend/src/lib/onboarding/{Toys,SoContext,Goals,Character,Preferences,Reveal}.svelte`, finish `[step]/+page.svelte`, tests for Preferences + Reveal (representative; the rest are simple forms).

- [ ] **Step 1: Write failing tests** — `frontend/src/lib/onboarding/Preferences.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import Preferences from './Preferences.svelte';

test('submits ceiling + aftercare', async () => {
  const onnext = vi.fn();
  render(Preferences, { onnext });
  screen.getByRole('button', { name: /next/i }).click();
  expect(onnext).toHaveBeenCalledOnce();
  const prefs = onnext.mock.calls[0][0];
  expect(prefs.intensity_ceiling).toBeGreaterThanOrEqual(0);
  expect(prefs).toHaveProperty('aftercare_prefs');
});
```
`frontend/src/lib/onboarding/Reveal.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import Reveal from './Reveal.svelte';

test('shows the mistress honorific from the assembled profile', () => {
  render(Reveal, { character: { honorific: 'Headmistress', address_term: 'student' } });
  expect(screen.getByText(/Headmistress/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement the components.** Each is a simple form calling `onnext` with its payload; the page wires `onnext` → the matching API call → draft → advance. Examples:

`Preferences.svelte`:
```svelte
<script lang="ts">
  import NumberField from '$lib/design/components/NumberField.svelte';
  import TextArea from '$lib/design/components/TextArea.svelte';
  let { onnext, initial = { intensity_ceiling: 50, aftercare_prefs: '' } }:
    { onnext: (p: { intensity_ceiling: number; aftercare_prefs: string | null }) => void;
      initial?: { intensity_ceiling: number; aftercare_prefs: string | null } } = $props();
  let ceiling = $state(initial.intensity_ceiling);
  let aftercare = $state(initial.aftercare_prefs ?? '');
</script>
<h2 class="display">Your boundaries</h2>
<NumberField label="Intensity ceiling (0–100)" value={ceiling} oninput={(v) => (ceiling = v)} />
<TextArea label="Aftercare preferences" value={aftercare} oninput={(v) => (aftercare = v)} />
<button onclick={() => onnext({ intensity_ceiling: ceiling, aftercare_prefs: aftercare || null })}>Next</button>
```
`Reveal.svelte` (the mistress's first appearance — the one warm-ish moment, still severe chrome):
```svelte
<script lang="ts">
  let { character }: { character: { honorific: string; address_term: string } } = $props();
</script>
<section class="reveal">
  <p class="label">Intake complete</p>
  <h1 class="display">{character.honorific}</h1>
  <p>She has read your file, {character.address_term}. She is ready when you are.</p>
</section>
<style>
  .reveal { text-align: center; padding: 48px 0; }
  h1 { font-size: 2.4rem; color: var(--accent); }
</style>
```
`Toys.svelte` (add-one-or-skip: name + type + optional intiface flag → `onnext(toy | null)`), `SoContext.svelte` (description/values/dynamic text areas), `Goals.svelte` (title + description add-one-or-skip), `Character.svelte` (honorific/address_term TextFields + 7 `Scale` dials 0–100 → `onnext(patch)`). Keep each minimal but functional. Wire all into `[step]/+page.svelte`:
- toys → `addToy` (or skip), SO → `putSoContext`, goals → `addGoal` (or skip), character → `putCharacter`, preferences → `putPreferences`.
- On reaching `reveal`: `getProfile(profileId)` (or `getCharacter`) → render `<Reveal>`; provide a "Enter" button that `onboardingDraft.clear()` then `goto('/')`.

- [ ] **Step 4: Run** — Preferences + Reveal tests PASS; the full `vitest run` is green; `npm run check` clean; `npm run build` succeeds.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/onboarding/ frontend/src/routes/onboarding/
git commit -m "feat(fe): toys/SO/goals/character/preferences steps + mistress reveal"
```

---

## Task 13: Full verification + milestone wrap

**Files:** none (verification) — then PR.

- [ ] **Step 1: Frontend checks** — from `frontend/`: `npx vitest run` (all green), `npm run check` (svelte-check clean), `npm run build` (adapter-node build succeeds).
- [ ] **Step 2: Backend** — `uv run pytest -q` (the new preferences endpoint + all prior) green; `uv run ruff check .` clean.
- [ ] **Step 3: Manual smoke (optional, local)** — `uv run uvicorn app.main:app` (backend) + `npm run dev` (frontend); walk consent → … → reveal; confirm each step persists (the backend rows appear) and refresh mid-wizard resumes from the draft.
- [ ] **Step 4: Push + CI green**
```bash
git push -u origin feat/m9-pwa-onboarding
```
The `frontend` CI job runs `npm ci` → `npx vitest run` → `npm run build` (now adapter-node). The `backend` job runs the preferences test too. Confirm both jobs pass.
- [ ] **Step 5: Open the PR**
```bash
gh pr create --base master --head feat/m9-pwa-onboarding \
  --title "M9 (Phase A): PWA foundation + onboarding wizard" \
  --body "Addendum A7 architecture + Severe Editorial design system + onboarding wizard. See docs/superpowers/plans/2026-06-07-core-obedience-loop-m9-pwa-onboarding.md"
```

---

## Verification (end-to-end for M9 Phase-A slice)

1. **Frontend green:** `vitest run` (proxy, client, stores, design primitives, wizard step components), `svelte-check` clean, `npm run build` (adapter-node) succeeds.
2. **BFF works:** the client calls same-origin `/api/...`; the proxy forwards to `API_ORIGIN` server-side (covered by `proxy.test.ts`).
3. **Types are real:** `src/lib/types/api.ts` is generated from the backend schema and committed; `gen:api` regenerates it.
4. **Wizard runs end-to-end (local):** consent (creates the profile) → archetype → kink sheet → toys → SO → goals → character → preferences → reveal; each step POSTs/PUTs to its M3 endpoint; mid-wizard refresh resumes from `onboardingDraft`.
5. **Backend:** `PUT /profile/{id}/preferences` persists ceiling + aftercare; full suite + ruff green.
6. **CI green** on the pushed branch (frontend + backend jobs).

**M9 (Phase A slice) is done when:** the binding A7 architecture is in place (adapter-node + BFF + OpenAPI types + runes stores), the Severe Editorial design system provides the wizard's primitives, and the onboarding wizard collects the full profile through the M3 (+ new preferences) endpoints with save-and-resume, ending on the mistress reveal — leaving M9b to add the Profile/Character view-edit spokes, the safety shell, and Playwright E2E, and Phase B the chat surface + live dossier.

---

## Self-Review

**Addendum A coverage (Phase A foundation + wizard):**
- A7 adapter-node + BFF proxy (API origin server-side) → Tasks 1, 4. ✓
- A7 OpenAPI-generated types → Task 3. ✓
- A7 runes stores (session, onboardingDraft; chat/dossier/safety are Phase B/M9b) → Task 8. ✓
- A7 layered `src/lib/` (api/, types/, stores/, design/) → Tasks 3,5,6,7,8. ✓
- A1 Severe Editorial tokens + primitives (Button, ProgressRail, SegmentedControl, Scale, fields; Bubble/DossierBar/Chip are chat/dossier → Phase B) → Tasks 6,7. ✓ (scoped)
- A4 onboarding pure structured wizard, one concern per screen, numbered progress rail, save-and-resume, back/next, mistress reveal at the end → Tasks 9–12. ✓
- A4 archetype = statement-per-card with a scale → Task 10. ✓
- A4 kink sheet = grouped grid, 6-way segmented, crimson/muted-crimson hard/soft → Task 11. ✓ ("grouped by category" is simplified to a flat list since M3's catalog has no categories yet — noted).
- A2 screen map onboarding `[now]` incl. preferences as its own step → Task 12 + the backend preferences endpoint (Task 2). ✓
- Routing guard (redirect to onboarding until a profile exists) → Task 9. ✓
- Provider config is admin/config-file, not UI → respected (no provider screen). ✓
- Safety shell, Profile/Character view-edit spokes → **M9b** (out of this slice). ✓
- Playwright E2E → **deferred** (Vitest component tests this milestone). ✓

**Placeholder scan:** complete code for the foundational/tricky pieces (proxy, client, stores, tokens, the two hard wizard screens, consent, preferences, reveal); the simpler repetitive steps (toys/SO/goals/character) are specified with their payload + wiring and a representative pattern — the implementer writes the analogous small forms. No TODO left in shipped code beyond the documented Phase-B seams.

**Type/name consistency:** `STEPS`/`Step`/`nextStep`/`stepIndex` (Task 9) used by the dispatcher and chrome. `session.profileId`/`setProfileId`/`clear` and `onboardingDraft.get/set/clear` (Task 8) used across the wizard. `makeClient`/`api`/`ApiError` (Task 5) used by `onboarding.ts`/`profile.ts` and the components. `proxyRequest(request, path, apiOrigin, fetchFn)` (Task 4) matches the catch-all route. The API module function names (`createProfile`, `getQuestionnaire`, `submitArchetype`, `putKinks`, `addToy`, `addGoal`, `putSoContext`, `putCharacter`, `putPreferences`, `getProfile`) match their call sites. `PreferencesIn`/`PreferencesOut` (Task 2) match the backend endpoint.

---

## Notes for execution
- **Branch:** `feat/m9-pwa-onboarding` (not `master`).
- **Use the frontend-design skill** when crafting the Severe Editorial components (Tasks 6–7, 9–12) — the tokens/aesthetic are fixed by Addendum A1, but apply the skill's polish for layout/interaction states.
- **Svelte 5 runes only** (`$state`/`$derived`/`$props`/`$effect`); `.svelte.ts` for runes in stores. No legacy stores/`$:`.
- **The client never imports `API_ORIGIN`** — that's server-only (`$env/dynamic/private` in the proxy route). The browser only knows same-origin `/api/...`.
- **OpenAPI types are committed**; CI never runs the backend for the frontend job. Regenerate with `npm run gen:api` after backend API changes (and commit the diff).
- **Two hard screens** (archetype scale, kink 6-way grid) use accessible native controls (`range` input, button group) so they're testable under jsdom and keyboard-usable; richer drag affordances can be layered later without changing the contract.
- **"Grouped by category" kink sheet** is simplified to a flat list because M3's `kink_catalog` has no category metadata; add grouping when the catalog grows categories (note for a future backend tweak).
- **adapter-node build** produces a Node server (`build/`); deployment (docker-compose alongside FastAPI) is an ops concern for later — M9 just ensures it builds.
- **Backend dev caveat:** clear `PYTHONHOME`/`PYTHONPATH` before `uv` for Tasks 2–3 (the openapi dump invokes the backend). CI unaffected.
