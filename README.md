# smistress

A single-user, **chat-first** application in which an AI "mistress" acts as a trainer/coach
running a real, structured habit-building program themed as consensual D/s training. The AI
designs the program, assigns real-world tasks, verifies completion from proof, reacts in
persona, and administers a merit economy — all driven from a chat surface.

> **smistress is an adult, consensual D/s productivity/habit tool for a single owner-operator.**
> Consent and safety are first-class, deterministic features — not afterthoughts. It is intended
> for use by adults (18+) and assumes informed, ongoing consent that can be withdrawn at any time.

---

## The Core Obedience Loop

```
  ONBOARD ──► build PROFILE (archetype test + kink/limits sheet + toys + SO context + goals)
     │
     ▼
  PROGRAM ──► derive training GOALS from the profile
     │
     ▼
  ┌───────────────── daily cycle ─────────────────┐
  │  ASSIGN  → mistress gives a task (chat-first)  │
  │  DO      → user completes it in the real world │
  │  PROVE   → photo / video / timer / honor report│
  │  VERIFY  → strict scrutiny of proof            │
  │  REACT   → praise or displeasure, in-persona   │
  │  ADJUST  → merit/economy + memory update       │
  └────────────────────────────────────────────────┘
     │
     ▼
  SAFETY always live: safeword/panic, limit enforcement, aftercare
```

The full design is in [`docs/superpowers/specs/2026-06-04-core-obedience-loop-design.md`](docs/superpowers/specs/2026-06-04-core-obedience-loop-design.md).

---

## Architecture

| Layer | Stack |
|-------|-------|
| **Backend** | Python 3.12 · FastAPI · SQLAlchemy 2.0 (async, psycopg3) · Alembic · [`uv`](https://docs.astral.sh/uv/) |
| **Database** | PostgreSQL 16 (system of record) |
| **Memory** | Graphiti temporal knowledge graph over FalkorDB (optional; off by default) |
| **LLM** | Any OpenAI-compatible provider (Ollama, OpenAI, …) behind a swappable seam; an in-memory mock for offline dev |
| **Frontend** | SvelteKit 2 · Svelte 5 runes · TypeScript · Vite · PWA · `@sveltejs/adapter-node` |

The browser never talks to FastAPI directly. The SvelteKit server exposes a **same-origin BFF
proxy** (`/api/[...path]`) that forwards to the backend; the backend origin (`API_ORIGIN`) stays
server-side. Frontend types are generated from the backend's OpenAPI schema and committed, so the
frontend builds without a running backend.

---

## Status & roadmap

Built milestone-by-milestone from the approved spec. Merged to `master`:

- **M1** Foundation — FastAPI app, config, swappable LLM provider seam, CI
- **M2** Data Layer — schema, migrations, async session
- **M3** Onboarding & Profile — consent gate, archetype scoring, profile API
- **M4** Persona Engine — computed disposition + prompt compilation
- **M5** Memory — Graphiti/FalkorDB outbox, retrieval, graceful degradation
- **M6** The Loop — task lifecycle + configurable strict verification
- **M7** Economy — merit / rank / tokens / denial timers
- **M9 (Phase A)** PWA foundation + Severe Editorial design system + onboarding wizard

**Not yet built:** M8 Safety (limit enforcement, safeword/panic, aftercare), M9b
(profile/character view-edit, safety shell, Playwright E2E), and **Phase B** (the chat surface +
live dossier). Photo/video proof verification is stubbed until a vision model is configured.

---

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** (backend Python toolchain)
- **Node.js 22+** (frontend)
- **PostgreSQL 16** — easiest via Docker (`docker compose up -d`); a local install works too
- **FalkorDB** — only if you enable the memory graph (see below); the bundled compose file provides it
- An **OpenAI-compatible LLM endpoint** — or set the mock (see Configuration) to run fully offline

---

## Quickstart

### 1. Start infrastructure

```bash
cp .env.example .env          # adjust as needed
docker compose up -d          # Postgres + FalkorDB
```

(No Docker? Run a local Postgres matching `SMISTRESS_DATABASE_URL` and create a `smistress_test`
database for the test suite.)

### 2. Backend

```bash
cd backend
uv sync                       # install dependencies
uv run alembic upgrade head   # apply migrations
uv run uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000` — interactive docs at `http://localhost:8000/docs`,
health check at `http://localhost:8000/health`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

In dev, the BFF proxy forwards `/api/*` to `http://localhost:8000` by default. Point it elsewhere
by setting `API_ORIGIN` for the SvelteKit server. Open the app and the root route guides you into
the onboarding wizard.

---

## Configuration

All backend settings are environment variables prefixed `SMISTRESS_` (loaded from `.env`). See
[`.env.example`](.env.example):

| Variable | Purpose | Default |
|----------|---------|---------|
| `SMISTRESS_LLM_BASE_URL` | OpenAI-compatible base URL. Set to `mock` to force the in-memory provider (no real LLM). | `http://localhost:11434/v1` (Ollama) |
| `SMISTRESS_LLM_API_KEY` | API key for the provider | `not-needed` |
| `SMISTRESS_CHAT_MODEL` | Chat model name | `llama3.1` |
| `SMISTRESS_VISION_MODEL` | Vision model for proof verification. Unset ⇒ photo/video proof auto-passes. | *(unset)* |
| `SMISTRESS_DATABASE_URL` | PostgreSQL DSN | `postgresql+psycopg://smistress:smistress@localhost:5432/smistress` |
| `SMISTRESS_GRAPHITI_ENABLED` | Enable the Graphiti/FalkorDB memory graph. Off ⇒ a no-op memory store (no FalkorDB/embeddings needed). | `false` |
| `SMISTRESS_FALKORDB_URL` | FalkorDB connection (when memory is enabled) | `redis://localhost:6379` |

Frontend: `API_ORIGIN` (SvelteKit server, server-only) sets the backend the BFF proxy targets.

---

## Testing

**Backend** (requires a running Postgres; the suite manages its own `smistress_test` schema):

```bash
cd backend
uv run pytest -q
uv run ruff check .
```

**Frontend** (no backend needed — types are committed):

```bash
cd frontend
npm run test          # Vitest component/unit tests
npm run check         # svelte-check (type + a11y)
npm run build         # adapter-node production build
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs both jobs on every push and PR.

### Regenerating API types

After changing a backend endpoint, refresh the committed OpenAPI types:

```bash
cd frontend
npm run gen:api       # dumps backend openapi.json → src/lib/types/api.ts
```

---

## Project layout

```
backend/
  app/
    api/            # FastAPI routers: onboarding, profile, persona, memory, tasks, economy
    db/             # SQLAlchemy models, session, enums
    services/       # domain logic (profile, archetype, economy, …)
    llm/            # swappable LLM provider seam + mock
    memory/         # Graphiti/FalkorDB store (+ null store)
    config.py       # Settings (env-driven)
    main.py         # app entrypoint + health routes
  alembic/          # migrations
  tests/
frontend/
  src/
    lib/
      api/          # typed client + per-resource modules
      types/        # generated OpenAPI types (committed)
      stores/       # Svelte 5 runes stores (session, onboarding draft)
      design/       # Severe Editorial tokens + component primitives
      onboarding/   # wizard step components
      server/       # BFF proxy
    routes/         # SvelteKit routes (incl. /api/[...path] proxy, /onboarding/[step])
docs/               # design specs & plans
docker-compose.yml  # Postgres + FalkorDB
```

---

## License

See [`LICENSE`](LICENSE).
