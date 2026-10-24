# Offline-First Milestone 6 — Queued Proof & Memory (settle-on-return) — Design

**Date:** 2026-10-24
**Status:** Design (pending builder check + partner approval)
**Build-order slot:** Addendum B §B11 item 6 — "Queued proof & memory — settle-on-entry at batch/audience."
**Predecessors:** Offline-1 (availability/heartbeat), Offline-2 (drone surface), Offline-3 (batch generation), Offline-4a/4b (chastity/debt + punishment pool), Offline-5a/5b/5c (supervision modes + discreetness filter + M5 frontend).
**Successor (separate milestone):** the live-audience lifecycle (§B8) — merit-gated eligibility, token price, open/close ritual, standing-orders dictation, pool regen at close, and the formal BATCH_WINDOW / LIVE_AUDIENCE presence states.

---

## Intent and the why

Addendum B reframes the whole app around a premise: the LLM lives on an intermittent home box, so **offline is the normal operating case**, not a degraded one. §B5 names the rhythm that follows: *"offline you accrue; when she returns, accounts settle."*

Two kinds of work accrue while she's away:

- **Media proof (photo/video)** — captured offline, stored, stamped **"pending her review."** The vision model judges the backlog when the box is back; merit and debt settle then. A bad backlog can sour an audience.
- **Evolving memory (Graphiti episodes)** — queue offline and **ingest when the box is up.**

Meanwhile **honor reports and timers stay fully deterministic and resolve immediately offline** — they never queue. And §B10 lists a `punitive` flag on `Task` (distinguishing a penance task from a normal assignment) that the discipline unit (Offline-4a) currently infers only via `Punishment.penance_task_id` — there's no way to tell from the Task alone.

This milestone closes that loop. Today the codebase has the *substrate* — a `MemoryEpisode` outbox with `enqueue_episode`/`drain_outbox` (already wired to an endpoint), a `Proof` model with a plain-string `verdict`, a swappable provider seam with a `supports_vision` flag — but the actual promise is unmet: `verify_media` returns `PENDING` forever when a vision model is configured (it never calls one) and auto-passes when none is; memory drains whether the box is up or not; no proof is ever truly "queued for review"; `punitive` doesn't exist.

Why now: this is the literal next item in B11, and it's the prerequisite for the audience lifecycle's **settle-on-entry** step. Landing it as a standalone slice gives B8 a reusable `settle_backlog` hook to call on audience open — without dragging the whole ritual into scope prematurely.

---

## Goals

- **Media proof queues, then settles.** Submitting a photo/video proof offline stamps `verdict = pending_review` and leaves the task in `proof_submitted`. A new `settle_backlog` operation, runnable only when the box is online, invokes the vision model on each pending_review proof, records pass/fail/re_proof, and applies merit/debt via the existing economy + discipline services.
- **Memory ingests only when she's reachable.** `drain_outbox` is gated on availability. The settle operation drains memory as part of the same "accounts settle" beat (matching §B2's batch-window description: *"ingests queued memory, judges queued proof"*).
- **Real vision judge through the swappable seam.** `ChatMessage` carries image content; the mock and OpenAI-compatible providers both handle it; `verify_media` actually calls the model and parses a JSON verdict (reusing the honor-verifier parser).
- **`punitive` task flag.** New `Task.punitive: bool` column; `discipline.issue_punishment` sets it on penance tasks; surfaced in task I/O so downstream (dossier, audience reckoning) can distinguish.
- **Reusable settle hook.** `POST /profile/{id}/backlog/settle` — online-gated (503 offline), returns a summary. This is the exact call site the audience lifecycle will invoke on entry.

## Non-goals (explicit)

- **No audience lifecycle (§B8).** Merit-gated eligibility, token price, open/close ritual, standing-orders dictation, pool regeneration at close, and the formal BATCH_WINDOW / LIVE_AUDIENCE presence states all stay deferred to the next milestone. Presence remains binary OFFLINE/ONLINE (as in Offline-1).
- **No auto-trigger / scheduler.** Settle is a manual POST. The opportunistic-agent + scheduled-settle concerns belong to the audience milestone (and the home-box agent).
- **No frontend surfacing in this slice.** Pending-review counts, a "pending her review" dossier section, and a settle button ship in a thin follow-up (Offline-6b), mirroring the M5a→M5b→M5c cadence (backend core first, frontend after). The dossier schema is left additive-ready but unchanged here.
- **No new proof states on `TaskStatus`.** `pending_review` lives on `Proof.verdict` only; the task stays `proof_submitted`. Minimizes blast radius into `_LAPSABLE`/`_TERMINAL`/sweep logic.

## Anti-goals (failure even if it technically works)

- Regression of the deterministic paths: honor/timer/none proofs must still resolve immediately and identically.
- Violating "the drones never gate safety" (§B9): settle is an economy/memory beat, never a safety gate.
- Breaking the swappable-seam property: the mock provider must exercise the vision path so the suite runs fully offline.
- Queueing media *forever* when no vision model is configured — that would punish users running honor-system-only.

---

## Constraints

- **Stack unchanged:** Python 3.12, FastAPI, SQLAlchemy 2.0 async (psycopg3), Alembic, Pydantic v2, pytest (asyncio_mode=auto, live Postgres `smistress_test`), ruff line-length=100.
- **Conventions (carried from prior milestones):** services flush, endpoints commit; PG enums store member NAMES; bare-UUID cross-aggregate refs stored as strings in JSONB; frontend hand-writes API interfaces (never imports generated `api.ts`).
- **Swappable seam:** `LLMProvider` is a `Protocol` with `supports_vision: bool` already declared. The mock provider must support the vision path for tests. Real-image verification is only exercised when `SMISTRESS_VISION_MODEL` is set.
- **Graceful degradation (spec §2 / §3):** with no vision model configured, media proof keeps the **existing** auto-pass (honor-system) behavior — no queueing, no regression. `pending_review` is only meaningful when a judge exists.
- **Alembic head at time of writing:** `f6a7b8c9d0e1` (add_toy_discreetness). The new migration chains from it.
- **Windows dev caveat (carry-forward):** clear `PYTHONHOME`/`PYTHONPATH` before every `uv` call; backend commands run from `backend/`.

---

## Approaches

Three ways to scope "finish queued proof & memory." Presented to the partner; **B was chosen.**

### A — States + gate, vision deferred
Adds `pending_review` verdict + `punitive` flag + `media_uri` column; gates `drain_outbox` on availability; adds the manual settle endpoint. But `verify_media` stays a stub, so a configured-vision user watches media proofs sit in `pending_review` forever after settle — the loop never closes.
- **Trades off:** smallest, but ships plumbing without payoff. Dishonest about "settles."

### B — Vertical slice: real vision judge + memory ingest, no audience lifecycle *(chosen)*
Everything in A, plus a real multimodal vision judge: extend `ChatMessage` to carry image content, implement it in the mock + OpenAI providers, and make `verify_media` actually call the vision model and parse pass/fail/re_proof. `settle_backlog` judges each `pending_review` proof and applies merit/debt via the existing `apply_task_outcome` + `apply_terminal_discipline`. Presence stays binary; settle is a manual, online-gated endpoint that doubles as the reusable hook the audience milestone calls on entry.
- **Trades off:** bigger (the provider work is unavoidable), but it's the real feature end-to-end and leaves a clean seam for B8. **Why chosen:** the user asked to *finish* the spine; A queues-but-never-settles, C conflates two milestones.

### C — Full §B8 audience lifecycle too
Pulls in merit-gated eligibility, token price, open-door, settle-on-entry, type-by-merit, close + standing orders + pool regen, and the formal BATCH_WINDOW/LIVE_AUDIENCE presence states.
- **Trades off:** genuinely two milestones' worth; the audience ritual deserves its own brainstorm. Premature. Rejected.

---

## The how (decided)

### 1. Data model deltas — one migration

New migration `g7b8c9d0e1f2_add_queued_proof_memory.py`, `down_revision = 'f6a7b8c9d0e1'`:

- **`proof.media_uri`** — `String, nullable=True`. Pointer to stored media (local path or URI). Nullable so existing text-only proofs are unaffected. No new table — media storage itself is out of scope (the URI is opaque to the backend; the frontend/agent stages the file).
- **`task.punitive`** — `Boolean, server_default=false, nullable=False`. Distinguishes penance tasks. Default false for all existing + new normal tasks. **Backfill** in `upgrade()`: `UPDATE task SET punitive = true WHERE id IN (SELECT penance_task_id FROM punishment WHERE penance_task_id IS NOT NULL)` so historically-issued penance tasks are correctly labeled (otherwise the flag is only truthful for tasks created post-deploy, breaking its stated purpose for the backlog/audience). `downgrade()` just drops the column.
- **Allowed `Proof.verdict` values expand** to include `pending_review` and `superseded` (both plain strings — no enum change). `pending_review` = queued for the vision model; `superseded` = an older `pending_review` proof displaced by a newer one for the same task (see §4). `TaskStatus` is untouched.

### 2. Multimodal provider extension

Extend `ChatMessage` (dataclass) with an optional images field:

```python
@dataclass
class ChatMessage:
    role: str
    content: str
    images: list[str] = field(default_factory=list)  # URIs / base64 data URLs
```

- **`OpenAICompatibleProvider.chat`** — when a message has `images`, format `content` as the OpenAI multipart list (`[{"type":"text","text":...}, {"type":"image_url","image_url":{"url":...}}, ...]`); otherwise keep the current plain-string form. Pass-through otherwise unchanged.
- **`MockLLMProvider`** — records `images` on the call (already records messages); pops scripted `ChatResult`s as today. Tests drive the vision path by constructing a mock with `supports_vision=True` and a scripted pass/fail/re_proof/unparseable result.
- **No new provider method.** `supports_vision` (already on the Protocol) gates usage; a non-vision provider is never asked to judge images (guarded in `verification`, see §3).

### 3. Verification — real vision judge, decoupled from `verify_task`

`verification.py` gains:

```python
def verify_media(task, *, media_uri, provider, settings) -> VerdictResult
```

Behavior:
- **No vision model configured** (`settings.vision_enabled is False`) → return `PASS` ("no vision model configured — auto-passed", current honor-system behavior). *Preserves today's degradation.*
- **Vision configured but `provider.supports_vision is False`** → return `pending_review` with reasoning `"vision model configured but provider lacks vision support"`. Defensive; surfaces a misconfiguration without crashing the settle.
- **Both present** → build a multimodal message: a strict verifier system prompt (mirroring `_HONOR_SYSTEM`'s JSON-contract) + a user turn containing the task description and the image(s)); call `provider.chat`; parse with the existing `_parse_verdict` (returns `re_proof` on unparseable JSON, identical to honor).

Routing change in `verify()`:
- `NONE` / `TIMER` / `HONOR` → unchanged (deterministic / immediate).
- `PHOTO` / `VIDEO` → **do not call the vision model here.** Return `pending_review` ("media proof queued for her review"). The task stays `proof_submitted`.

**Key decision:** the vision model is invoked *only* by `settle_backlog`, never by `verify_task`. This mirrors §B5 exactly — media queues at submit, judges at settle — and keeps the synchronous verify path deterministic. `verify_task` for a media task marks the proof `pending_review` and returns the task in `proof_submitted`.

Existing `verify_media` callers/tests (`tests/loop/test_verification.py::test_verify_media_*`) update to the new signature.

### 4. `settle_backlog` — the settle beat

New module `app/backlog/service.py` (mirrors the `drones/`/`discipline/`/`supervision/` package pattern):

```python
@dataclass
class SettlementSummary:
    judged: int        # proofs resolved this run (passed + failed + re_proven)
    passed: int
    failed: int
    re_proven: int
    skipped: int       # permanently un-judgeable (vision configured, provider lacks vision)
    errored: int       # transient provider failures; left pending_review for retry
    memory_drained: int

async def settle_backlog(
    session, profile_id, *, provider, settings, now=None
) -> SettlementSummary
```

Steps:
1. Drain the memory outbox first (`mem_svc.drain_outbox(session, store, profile_id=profile_id)`) — §B2 couples "ingests queued memory, judges queued proof" into one beat. Count toward `memory_drained`. (See §6 for the scoped drain.)
2. **Per-task dedup (single-outcome guarantee):** `SELECT DISTINCT ON (task_id) proof.* FROM proof WHERE verdict = 'pending_review' AND profile_id = ? ORDER BY task_id, created_at DESC` — the latest `pending_review` proof per task. This is the set that gets judged. Any older `pending_review` proofs for those same tasks are stamped `verdict = 'superseded'` so they're never re-judged. This preserves the §B7 atomic-single-outcome-per-task invariant even if the sub submits media twice before a settle (reachable today — `submit_proof` has no guard against a second submission while a task is already `proof_submitted`).
3. For each (latest) proof in the dedup set:
   - Call `verification.verify_media(task, media_uri=proof.media_uri, provider, settings)`.
   - On `pass`/`fail`: set `proof.verdict`, set `task.status = VERIFIED_PASS|VERIFIED_FAIL`, call `loop_svc.apply_task_outcome(session, task)` + `loop_svc.apply_terminal_discipline(session, task)`.
   - On `re_proof`: set `proof.verdict = re_proof`; task stays `proof_submitted` (another attempt due).
   - On the **misconfigured-provider** branch (`vision_enabled` but `provider.supports_vision is False` — a *permanent* condition, not transient): the proof stays `pending_review`; increment `skipped`; emit one `logger.warning` per settle naming the profile. Distinct from a transient error so a config mistake doesn't silently freeze a user's media backlog with no signal.
   - On a **transient exception** from `provider.chat`: leave `proof.verdict = 'pending_review'`; increment `errored`; the next settle retries. No new columns (per flagged call #4).
   - Enqueue a memory episode for each judged proof ("proof judged: pass/fail/re_proof …").
4. Flush; caller commits.

**Placement note:** `backlog/service.py` imports `loop.service` (for `apply_task_outcome`/`apply_terminal_discipline`) and `verification` and `memory.service`. `loop.service` does **not** import `backlog` — no cycle. Matches the existing `discipline → {economy, models}; loop → discipline` layering.

### 5. Endpoint — manual, online-gated

`POST /profile/{profile_id}/backlog/settle` in a new `app/api/backlog.py`:
- Mirror the M1 chat gate: `if not await avail_svc.is_online(session): raise 503 "the Mistress is away — nothing to settle"`.
- Build the provider via `build_provider(settings)`, call `settle_backlog`, commit, return `SettlementSummary`.
- Mount in `main.py`.

### 6. Memory drain gating

- **`mem_svc.drain_outbox` gains an optional `profile_id: uuid.UUID | None = None` filter.** Default `None` preserves the existing global behavior (backward-compatible). The new `backlog/settle` passes the caller's `profile_id` so it drains (and counts) only that profile's queued episodes; `memory/seed` keeps calling it with `None` (global best-effort, unchanged). This keeps the per-profile `SettlementSummary.memory_drained` honest and prevents cross-profile leakage in the multi-profile test DB.
- The existing `POST /profile/{id}/memory/seed` endpoint drains as a side-effect (best-effort). **Leave it** — seeding is rare and the best-effort drain is harmless when offline (NullMemoryStore is a no-op; Graphiti unreachable would just leave rows pending, which is the designed behavior).
- The new `backlog/settle` endpoint is the authoritative online-gated drain.

### 7. `punitive` flag plumbing

- `Task.punitive` column (migration above).
- `discipline.issue_punishment` sets `punitive=True` on the penance `Task` it creates (one-line addition).
- `TaskOut` / `TaskCreate` schemas gain `punitive: bool = False` (additive; existing payloads validate).
- No dossier change in this slice (non-goal).

### 8. Proof submission accepts media

- `ProofIn` gains `media_uri: str | None = None`.
- `loop_svc.submit_proof` gains `media_uri: str | None = None`; sets `proof.media_uri` when provided.
- For a media proof (`PHOTO`/`VIDEO`) with a `media_uri`, `submit_proof` sets `proof.verdict = "pending_review"` eagerly (the act of submitting media marks it for review, per §B5). For honor/timer/none, behavior unchanged (`verdict = "pending"`).
- `tasks.py` `submit_proof` endpoint passes `media_uri` through.

---

## What's left to the builder (the plan)

- Exact `SettlementSummary` field set + Pydantic schema name.
- Per-proof error policy confirmation (leave-pending-and-count vs. add retry columns) — flagged call below.
- Test fixtures: a sample media URI strategy for the suite (base64 data URL is simplest; no real asset files).
- The strict vision-verifier system prompt wording (mirror `_HONOR_SYSTEM`'s JSON contract).
- Whether `settle_backlog` should also re-judge proofs previously left `re_proof` (decision: no — `re_proof` means "another attempt due," which requires a new `submit_proof`, not a re-judge).
- Migration helper for the `proof` table if any index is wanted on `verdict` (likely none at this scale).
- Frontend follow-up (Offline-6b) scope: pending-review count in the dossier, a "pending her review" section, a settle button. Not in this plan.

---

## Resolved during the builder check

A fresh subagent reviewed this doc against the codebase and raised four correctness gaps. All four are internal-semantics refinements within the chosen approach (they don't change the feature shape), so I resolved them as builder calls rather than escalating:

1. **Double merit/debt from duplicate `pending_review` proofs.** `submit_proof` has no guard against a second submission while a task is already `proof_submitted`, so a media task could accumulate multiple `pending_review` proofs. Resolution: `settle_backlog` judges only the **latest** `pending_review` proof per task (`DISTINCT ON (task_id) … ORDER BY created_at DESC`) and stamps older ones `verdict = 'superseded'`. Single outcome per task guaranteed; no `submit_proof` change needed. (Folded into §1 + §4.)
2. **`drain_outbox` was global; settle is per-profile.** Resolution: `drain_outbox` gains an optional `profile_id` filter (default `None` = global, backward-compatible); settle scopes, `memory/seed` stays global. (Folded into §6.)
3. **`punitive` backfill for historical penance tasks.** Resolution: the migration backfills `punitive = true` for tasks already linked via `Punishment.penance_task_id`, so the flag is truthful retroactively. (Folded into §1.)
4. **Permanent vs. transient settle failures.** A `vision_model` configured with a non-vision provider is a *permanent* condition that would otherwise leave proofs `pending_review` forever with no signal. Resolution: `SettlementSummary` splits `skipped` (permanent misconfig, logged once per settle) from `errored` (transient provider exception, left for retry). (Folded into §4.)

## Flagged calls (mine to make; please confirm)

1. **No vision model ⇒ auto-pass (honor system), unchanged.** `pending_review` only arises when a vision model is configured. Rationale: no regression for honor-system-only users; matches §B5's "vision model judges the backlog" framing. Override if you'd prefer media to always queue regardless.
2. **`pending_review` lives on `Proof.verdict` only, not `TaskStatus`.** Task stays `proof_submitted`. Smaller blast radius; the dossier filters by verdict. Override if you want a visible `TaskStatus.PENDING_REVIEW`.
3. **Vision model invoked only by `settle_backlog`, never `verify_task`.** Decouples the synchronous deterministic path from the online-only judgment. Override if you'd prefer `verify_task` to opportunistically judge when online.
4. **No new columns for per-proof retry on settle errors.** Errored proofs stay `pending_review`; the next settle retries. Keeps the migration to two columns. Override if you want `proof.attempts`/`last_error`.
5. **Backend-only this slice; frontend surfacing deferred to Offline-6b.** Follows the M5a→M5c cadence and avoids reshaping the dossier before the audience milestone lands. Override if you want the pending-review surface in this milestone.
6. **Module placement: new `app/backlog/` package.** Mirrors `drones/`/`discipline/`/`supervision/`. Override if you'd rather hang `settle_backlog` off `loop/service.py`.
