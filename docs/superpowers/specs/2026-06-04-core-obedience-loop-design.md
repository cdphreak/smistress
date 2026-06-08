# smistress — Core Obedience Loop (Sub-project #1) — Design Spec

**Date:** 2026-06-04
**Status:** Approved design, ready for implementation planning
**Scope:** First of several sub-projects. Seed idea: [issue #1](https://github.com/cdphreak/smistress/issues/1) — "make smistress your BDSM habit builder."

---

## 1. Concept & Product Model

smistress is a **single-user, chat-first application** in which an AI "mistress" acts as a
**trainer/coach** running a real, structured training program themed as consensual sub/slave
training. The program is oriented around the user serving a real-life significant other (SO),
but the SO does **not** use the app — the AI designs the program, assigns real-world tasks,
verifies completion via proof, and administers all consequences itself.

It is an adult, consensual D/s productivity/habit tool. Consent and safety are first-class,
deterministic features (see §9), not afterthoughts.

### The Core Obedience Loop

```
  ONBOARD ──► build PROFILE (BDSM test + kink/limits sheet + toys + SO context + goals)
     │
     ▼
  PROGRAM ──► derive training GOALS from the profile
     │
     ▼
  ┌───────────────── daily cycle ─────────────────┐
  │  ASSIGN  → mistress gives a task (chat-first)   │
  │  DO      → user completes it in the real world  │
  │  PROVE   → photo / video / timer / honor report │
  │  VERIFY  → strict scrutiny of proof             │
  │  REACT   → praise or displeasure, in-persona    │
  │  ADJUST  → merit/economy + memory update        │
  └────────────────────────────────────────────────┘
     │
     ▼
  SAFETY always live: safeword/panic, limit enforcement, aftercare
```

### In scope for v1

- Onboarding + full Sub Profile model (incl. toy inventory **as data** — cataloged, not controlled)
- Adaptive mistress persona (chat-first) with persistent memory
- Goal → daily task assignment
- Proof submission (photo / video / timer / honor) + strict, **configurable** AI verification
- Privilege economy centered on **merit** (rank, tokens, denial timers — all in-app state)
- **Merit/mood → computed disposition** (the persona's intensity is earned, not dialed)
- Safety system (18+ gate, safeword/panic, limit enforcement from the kink sheet, aftercare)

### Deferred (later sub-projects)

- **#2 — Class & Training System** (see §8; designed-for now, built next)
- Intiface/Buttplug **device control** (inventory captured now, actuation later)
- Financial / external real-world stakes
- Optional SO progress report
- Encryption-at-rest hardening (explicitly out of v1 per decision; see §2)

---

## 2. Architecture

> **Amended by [Addendum B](#addendum-b--offline-first--modes-of-control-whole-app-pivot) (2026-06-08).**
> The original assumed an always-available LLM driving chat every turn. Addendum B pivots to
> **offline-first**: the VPS is 24/7 but the LLM (a home GPU box) is reachable only intermittently.
> See B2 for the three her-presence states + the home-box heartbeat agent.

Everything runs on **one VPS**, via docker-compose or systemd. No cloud object store, no managed
services.

| Concern | Choice |
|---|---|
| Frontend + server | **SvelteKit PWA** (mobile-first, installable); responsive enough for desktop device sessions later |
| Proof media | **Local filesystem** (data directory), served only through app-authenticated routes |
| Structured data | **Postgres** (same box) |
| Evolving memory | **Graphiti** temporal knowledge graph on **FalkorDB** (same box) |
| LLM access | **Provider-agnostic, OpenAI-compatible** (see below) |
| Auth | Single-user accounts, passkey/email; no social login (discretion) |
| Encryption | **Deferred for v1.** Note: encryption-at-rest is the obvious first hardening step before any real-world use. |

### Swappable AI backend (OpenAI-compatible)

All model calls go through one internal `LLMProvider` interface speaking the **OpenAI Chat
Completions API**. Provider is pure config: `base_url`, `api_key`, `model`. This supports OpenAI
**and** local servers (Ollama, vLLM, LM Studio, llama.cpp), all of which expose OpenAI-compatible
endpoints.

Two configurable model **roles**:
- **chat model** — the mistress persona
- **vision model** — strict proof verification

**Vision is configurable and degrades gracefully:** a single flag (derived from whether a vision
model is configured, with manual override) controls verification. If **no vision model is
available, photo/video verification is skipped and the proof auto-passes** (effectively
honor-system for media). Timers and honor-report interrogation still function. Consequence:
with vision off, "strict" only bites on timers + chat interrogation — an accepted degradation.

⚠️ Verification quality scales with the chosen vision model: cloud (GPT-4o-class) is strong;
local vision (Qwen2.5-VL / Llava-class) is weaker. The architecture is indifferent; results
are not.

---

## 3. Memory — Two Tiers by Trust Level

The premise (an evolving, full view of the sub with real progress over time) is inherently
temporal, so memory is split by **how much it can be trusted**:

### Tier 1 — Authoritative store (Postgres, system of record)

Hard/soft **limits**, toy inventory, active goals, economy state (merit, rank, tokens, denial
timers), and every task/proof record. Deterministic, queryable, **safety-critical**. Injected
**verbatim** into the persona context each turn. Limits and consent must **never** depend on
fuzzy retrieval.

### Tier 2 — Evolving memory (Graphiti temporal knowledge graph, FalkorDB)

Each session/task/proof/reaction is ingested as an **episode**. Graphiti extracts entities (the
sub, tasks, kinks, moods, milestones) and **time-valid relationships**, enabling reasoning about
*how things changed*: compliance trends, when an interest emerged, what motivation worked
before, how limits shifted. The mistress queries this for continuity and personalization.

**Design rule:** personality & continuity come from the graph (nuanced, historical); consent &
safety come from Postgres (authoritative, never hallucinated).

Graphiti's LLM + embedder clients are themselves OpenAI-compatible, so they ride the same
swappable provider config (including local models). On FalkorDB they co-exist on one server.

**Degradation:** if Graphiti/FalkorDB is unavailable, retrieval falls back to authoritative
Postgres state only — the mistress still functions with less continuity; writes queue and retry.

---

## 4. Sub Profile & Onboarding

The profile is the foundation everything reads from; it evolves, with history in Graphiti.

**Onboarding flow:**
1. **18+ gate + consent** — explicit acknowledgement, sets the frame.
2. **BDSM archetype questionnaire** (bdsmtest.org-style) — statements on a scale → computed
   percentages across archetypes (Submissive, Slave, Brat, Pet, Masochist, Degradee,
   Rope-bunny, …). Store raw answers **and** computed scores.
3. **Kink interest sheet** (kinksheet.com-style) — each kink rated
   **Favorite / Like / Curious / Soft-limit / Hard-limit / N-A**. This **is** the limits system.
4. **Toy inventory** — catalog devices (name, type, Intiface-capable flag, notes). Data only in v1.
5. **SO context** — who you're training for, what they value, the dynamic. Optional, free-text + light structure.
6. **Goals** — what you want to become/achieve; informs task assignment (and classes in #2).
7. **Preferences** — **absolute intensity ceiling**, persona hard-nos (language/themes), aftercare style.

**Postgres entities:** `sub_profile`, `archetype_result`, `kink_entry` (drives limits), `toy`,
`so_context`, `goal`, `character_model` (the configurable persona — see §5A). All injected verbatim
into the persona context; onboarding also seeds the initial Graphiti episodes.

---

## 5. The Mistress Persona Engine

> **Amended by [Addendum B](#addendum-b--offline-first--modes-of-control-whole-app-pivot) (2026-06-08).**
> The full persona engine described here is now the **live audience** experience (LLM present).
> Offline, deterministic **drones** stand in for her (B3). Merit-computed disposition also selects
> the **session type** — low merit → a reckoning, high merit → pleasurable (B8). Her tools fire
> live; offline state changes flow through the deterministic drone/economy services.

A system-prompt-driven chat agent over the swappable OpenAI-compatible provider.

**Each turn assembles context from four sources:**
1. **Persona system prompt** — role, adaptive-intensity rules, hard safety rules.
2. **Authoritative state (Postgres, verbatim)** — profile, active limits, current economy
   (merit/rank/tokens/denial timers), active task. Never paraphrased or fuzzily recalled.
3. **Retrieved memory (Graphiti)** — relevant history/trends for continuity & personalization.
4. **Recent conversation.**

### She acts through tools (function calling)

This is how chat-first drives real state. The mistress calls structured tools, e.g.:
`assign_task`, `request_proof`, `adjust_economy`, `set_denial_timer`, `trigger_aftercare`,
`flag_limit_concern`. Chat actions therefore produce real, logged mechanical effects — chat and
state can never silently disagree.

### Computed disposition via Merit (intensity is earned, not dialed)

- **Merit** — a persistent score reflecting standing. Verified, on-time, honest obedience raises
  it; missed tasks, failed proof, lateness, or dishonesty lower it. (Same currency as the economy
  in §7 — one number drives both her mood and your privileges.)
- **Mood** — a short-term modifier derived from **recent** events (last handful of tasks), so she
  reacts to the moment *and* the history.
- **Computed disposition** = `f(merit standing, recent mood)` → a tone band from
  **warm/pleased ↔ cold/severe**.
- **Bounded by consent, always.** The user sets an **absolute ceiling** + limits at onboarding; the
  merit/mood system only moves the needle within `[floor … ceiling]`. Hard limits are never crossed
  even at rock-bottom merit.
- Each turn the persona prompt receives the **current disposition + the reason** (e.g., "merit low,
  two recent misses → cold and exacting, within limits"), so tone is explainable and consistent.

---

## 5A. Persona Character Model & Voice

The mistress has **one consistent core identity** (a character bible) that stays recognizable across
sessions; the merit/mood **disposition** (§5) only shifts her *register* (warm ↔ severe), never who
she fundamentally is. That identity is **configurable** via a simple character model, so the persona
can evolve without code changes. Presets (archetypes) fill the model in; the user starts from one and
tweaks.

### Character model schema

Stored in Postgres as part of the profile (editable anytime; changes are written as Graphiti episodes
so the mistress is aware "she" has changed).

**A. Identity**
- **Name & honorific** — what she is called (default honorific: *Headmistress* / *Miss*).
- **Address term** — how she addresses the sub (default for Governess: *student*; configurable to
  pet / boy / girl / slave / the user's name).
- **Pronouns.**

**B. Archetype blend** — a weighted mix (not a single pick) of the four archetypes:
*Aristocrat, Governess, Owner, Drill Instructor.* **Default: Governess 70 / Drill Instructor 30.**

**C. Voice dials (0–100):**

| Dial | Controls | Governess+DI default |
|---|---|---|
| **Warmth** | baseline affection | low–moderate |
| **Strictness** | how exacting/demanding (standards, tolerance for slack) | high |
| **Sadism** | relish for the sub's discomfort/humiliation (distinct from strictness) | low–moderate *(raise for a genuinely cruel edge)* |
| **Formality** | proper ↔ casual | high |
| **Verbosity** | terse ↔ explanatory | moderate (pedagogical) |
| **Crudeness** | refined ↔ vulgar language | low |
| **Wit** | humorless ↔ dry/cutting | high |

**Strictness vs. Sadism are deliberately separate axes:** high-strictness/low-sadism = a fair-but-hard
taskmaster; low-strictness/high-sadism = lenient on standards but cruel when she strikes.

**D. Signature flavor** (optional free-text) — a short character premise/backstory, recurring
mannerisms, pet phrases. Fed verbatim into the system prompt.

**E. Guardrails** — the kink-sheet limits + persona hard-nos override **every** dial. Crudeness=100
still never crosses a hard limit or uses a banned theme; Sadism is always clamped by the consent
ceiling (§5).

### Dial → disposition coupling

The dials set her **center**; the merit/mood system swings her *around* that center within the consent
ceiling. Warmth=low means even high-merit praise stays restrained, and low-merit coldness goes properly
icy; a high-Warmth character would swing warmer at both ends. **Dials define who she is; merit defines
what mood she's in.**

### Compilation

At runtime: `character model + current disposition + authoritative state (§5) + retrieved memory (§3)
→ system prompt`. The character model is rendered into a stable persona block; disposition is rendered
as an explicit current-mood instruction with its reason.

### Default character: "Governess + Drill Instructor"

A sharp-tongued, impeccably proper headmistress who holds the sub to high standards with a **dry,
cutting wit** — she wounds with a precise, sardonic remark rather than shouting. The drill-instructor
edge reads as relentlessness; raised Wit makes her genuinely (mockingly) funny; low default Sadism keeps
the cruelty mostly verbal until the user dials it up.

**Illustrative voice across disposition bands** (tasteful, non-explicit):
- **High merit / pleased:** *"Well. Competence two days running — I almost don't recognize you. Don't
  let it go to your head; one swallow doesn't make a summer."*
- **Neutral:** *"Your task is on the board. I'd wish you luck, but luck isn't on the curriculum —
  effort is."*
- **Low merit / displeased:** *"Missed again. How wonderfully consistent of you — the one area where
  you excel. We'll be revisiting this, at length, until it bores us both."*

That cutting-but-controlled register is what high Wit + high Strictness + low Crudeness produces.

---

## 6. The Loop Mechanics

> **Amended by [Addendum B](#addendum-b--offline-first--modes-of-control-whole-app-pivot) (2026-06-08).**
> The loop still holds, but: tasks are now drawn from a **batch-generated pool** and carry an
> **intensity/discreetness/required-toy** profile filtered by the active **supervision mode** (B6);
> offline, media proof is **captured & queued** for judgment at the next batch/audience (B5); and a
> missed/failed task issues a **punishment** into the debt ledger (B7) in addition to the merit hit.

**Task lifecycle:**
```
assigned → in_progress → proof_submitted → verifying → verified_pass
                                                      ↘ verified_fail
        (deadline passes with no proof) ───────────► missed
```

A **task** carries: description, proof requirement (`photo | video | timer | honor | none`),
deadline, and **merit stakes** (reward on pass, penalty on fail, larger penalty on miss). Created
via `assign_task`, derived from goals + profile.

**Proof routes to a `VerificationService`:**
- **Photo/video** → stored on local disk → if a vision model is configured, checked against a
  strict rubric returning `{pass, confidence, reasoning, issues}`; low confidence → **demand
  re-proof**. No vision model → **auto-pass** (per §2 config).
- **Timer** → in-app timer with **server-side timestamps** (start/stop, optional check-ins) —
  deterministic, hard to fudge.
- **Honor** → written report the mistress **interrogates in chat** with follow-ups, judging
  consistency strictly; she rules pass/fail.

**React** → in-persona response, and tools fire consequences: adjust merit, update economy, maybe
impose a denial timer or grant/revoke a privilege, trigger **aftercare** if intense. Every outcome
is logged to Postgres and written as a Graphiti episode.

**Integrity note:** this is solo and partly honor-based, so it ultimately *trusts the user* — a
self-improvement tool, not an adversarial system. Strict verification, interrogation, and
server-side timers deter casual fudging; they do not try to make cheating impossible.

---

## 7. The Privilege Economy (merit-centered)

> **Superseded in part by [Addendum B §B7](#b7-economy-revision--three-quantities) (2026-06-08).**
> The economy now runs on **three** distinct quantities — **merit** (standing), **debt** (owed
> penance), **tokens** (reward purse) — and the denial timer is generalized into a full
> **punishment / debt-ledger** system. Read B7 for the authoritative model; the bullets below
> remain accurate for merit, rank, tokens, and privileges.

One currency runs everything — **merit** — which also computes disposition (§5).

- **Merit** — earned by verified/on-time/honest obedience; lost to fails/misses/lateness/dishonesty.
  Bounded range; tunable constants: `pass +X` (scaled by difficulty & promptness), `fail −Y`,
  `miss −Z` (worst), honesty bonus, streak multiplier.
- **Rank** — tiers derived from sustained merit (e.g., *novice → trainee → …*). Changes how she
  addresses you and what's unlocked.
- **Tokens** — discrete earned currency spent on **requests** (a comfort, a reward, a reprieve).
  Granted/revoked via tools.
- **Privileges** — gated by rank/merit: access to rewards, the right to make requests, leniency.
- **Denial timers** — in-app countdowns withholding rewards/privileges. *(Phase 2: the same timer
  gates Intiface device pleasure — the hook is designed in now.)*

All economy mutations flow only through the mistress's tool calls and are enforced by a single
economy service (merit bounded, tokens never negative, atomic transactions).

---

## 8. Class & Training System — DEFERRED to sub-project #2

Inspired by a school/curriculum model (e.g., sissy-university.com): enroll in classes to improve
specific skills a sub/slave should be good at, mentored by the mistress. **Not built in v1**, but
the v1 data model is designed so this slots in with no rework.

**Hierarchy:**
```
Discipline (skill area)
  └─ Class (a course; has a level + prerequisites)
       └─ Lesson (ordered module)
            └─ Task(s)  ← reuses the §6 loop
```

- **Disciplines** — content-neutral, configurable skill areas (the user defines the catalog and
  what each class trains; the app provides structure + mentorship, not fixed curriculum).
- **Classes** — courses with levels and **prerequisites** (rank/merit, or prior classes), so
  enrollment is earned.
- **Lessons** — ordered modules delivered by the mistress; each spawns tasks through the existing
  proof→verify→merit loop. Verified lessons advance the class.
- **Class completion** → raises a **skill level** in that discipline.

**Two distinct progression axes:**
- **Merit** = standing/behavior (rises and falls daily; drives disposition + economy).
- **Skill levels** = competence per discipline (a transcript; generally only grows).

So a sub can be high-skill / low-merit (well-trained but misbehaving), or green but obedient.

**Mistress as mentor:** introduces classes, recommends enrollments from goals/profile, assigns &
grades lessons, adapts difficulty to merit/skill, tracks the transcript (which the future SO
report can surface).

**Forward-compatible Postgres entities (added in #2):** `discipline`, `class`, `lesson`,
`enrollment`, `skill_level`. In v1, `task` includes a nullable `lesson_id` so tasks can later be
owned by lessons.

**Class authoring (in #2):** hybrid — a small seed catalog of class *templates* the mistress
tailors to the profile/goals, plus on-demand generation.

---

## 9. Safety System (cross-cutting, ships in v1)

> **Reinforced by [Addendum B §B9](#b9-safety-under-offline--modes) (2026-06-08).**
> Offline-first makes "works even if the LLM is down" the *normal* case, not an edge case. The
> drones never gate safety. **Supervision mode** is itself a consent/comfort control: lowering
> control depth (or going on **vacation**) is honored immediately, like lowering a limit (B6).

Safety is deterministic and works **even if the LLM is down**.

- **18+ gate + consent** at onboarding.
- **Safeword / panic stop** — always-available control **and** recognized phrases, **intercepted
  before the LLM**. Instantly: halts the active task/scene, stops timers and denial pressure, drops
  her into a calm out-of-persona caring mode, offers aftercare. (Phase 2: also kills device
  actuation.)
- **Limit enforcement** — hard limits never crossed; soft limits only approached with care +
  check-ins. Limits come from the authoritative kink sheet, injected every turn, **plus an output
  check** that scans her proposed message/tool-calls and blocks/regenerates anything crossing a
  limit.
- **Intensity ceiling** — merit-driven disposition clamped to the configured ceiling; can't exceed
  even at zero merit.
- **Aftercare** — triggered after intense scenes or on safeword; supportive tone, check-in,
  grounding, per aftercare prefs.
- **Well-being controls** — pause/"hiatus" without merit penalty; lower a limit anytime, honored
  immediately; periodic consent check-in.
- **Crisis fallback** — signs of genuine distress/self-harm break character and surface real help
  resources.
- **Data control** — one-tap delete-everything.

---

## 10. Error Handling & Testing

### Error handling
- **Provider failures** (timeout/error) → retry, degrade gracefully, never leave a scene broken.
  The safeword path never depends on the LLM.
- **Vision configured but call fails** → retry once, then fall back to "pending / re-proof," never
  a false fail.
- **Graphiti/FalkorDB down** → retrieval degrades to authoritative Postgres only; writes queue +
  retry.
- **Media on one VPS** → enforce file-type/size caps + disk-space guard + prune policy (no object
  store to absorb growth).
- **Economy invariants** → merit bounded, tokens never negative, all mutations atomic through one
  economy service.

### Testing
- **Unit:** merit math, economy invariants, `disposition = f(merit, mood)`, verification routing,
  limit-checking.
- **Integration:** the full loop against a **mock OpenAI-compatible provider** — also proves the AI
  backend is genuinely swappable.
- **Safety tests:** safeword fires with the LLM stubbed/down; hard-limit injection + output filter
  block violations; ceiling clamp holds.
- **Vision-configurable paths:** vision-on (pass / fail / low-confidence→re-proof) and vision-off
  (auto-pass).
- **Memory:** Graphiti ingest/retrieve on a test instance; graceful degradation when FalkorDB is
  down.
- **E2E:** onboarding → first task → proof → reaction on the PWA (Playwright), incl. install/camera.
- **Eval harness** for the two make-or-break risks: golden fixtures for **persona quality** and
  **strict proof verification**, to measure whether "strict" holds as models/providers change.

---

## Decision Log (key choices)

- Single-user **solo AI domme coach**; SO is outside the app (optional report only, deferred).
- **Chat-first** interaction; persona acts via tool/function calls.
- Consequences: in-app privilege economy + (phase 2) Intiface device pleasure + commitment/
  proof-of-consequence. Proof = photo/video/timer/honor, **strict** but **vision is configurable**
  (auto-pass when no vision model).
- **Mobile-first PWA**, desktop-capable for later device sessions.
- Intensity is **computed from merit + mood**, not dialed; bounded by a consent ceiling + limits.
- Persona is a **configurable character model** (identity + archetype blend + voice dials incl. a
  Sadism dial distinct from Strictness + flavor); default **Governess 70 / Drill Instructor 30**,
  high Wit, low-ish Sadism. Dials set her center; merit/mood swings her around it. See §5A.
- Profile = BDSM archetype test + kink/limits sheet + toy inventory + SO context + goals.
- **One VPS**, no object store, **encryption deferred**.
- AI backend **swappable, OpenAI-compatible**, local-LLM capable.
- Memory = **Postgres (authoritative) + Graphiti/FalkorDB (temporal, evolving)**.
- Class/Training system = **sub-project #2** (designed-for now).

---

# Addendum A — Frontend Vision (whole-app)

**Date:** 2026-06-06
**Status:** Approved design. Applies to **all** frontend work across every milestone — incorporate into every future plan.
**Scope:** The whole-app frontend north star: visual design language, information architecture, key interaction patterns, and the frontend tech architecture. Detailed screen specs are produced per slice; this addendum is the binding direction they must follow. Brainstorm mockups archived in `.superpowers/brainstorm/` (gitignored).

## A1. Design language — "Severe Editorial"

Stark monochrome with a single sharp accent; severe **but considered** (never crude brutalism — it must not feel cheap in an intimate context). Guiding principle: **the chrome stays cold; her words carry the warmth.** Earned intensity comes through the persona's language, not decoration.

**Tokens (CSS custom properties, source of truth for the design layer):**

| Token | Value | Use |
|---|---|---|
| `--ink` | `#0E0E0E` | base background |
| `--raised` | `#161616` | raised surfaces, her bubbles |
| `--muted` | `#777` | secondary text, hairlines context |
| `--paper` | `#FAFAFA` | primary text, inverted surfaces |
| `--accent` | `#C20E1A` (crimson) | accent **and** danger/stop — deliberately one color |

- **Type:** condensed uppercase grotesque for display/headers; clean neutral grotesque for body (generous line-height, restrained); **monospace for ALL "ledger" data** — merit, ranks, tokens, timers — reinforcing the exacting feel.
- **Form:** sharp corners, hairline rules, generous negative space, uppercase letter-spaced labels. Motion minimal and crisp (cuts over bounces).
- **Crimson does double duty** (her accent = the stop color), so the safeword control is always the most visually charged element on screen.

## A2. Information architecture — three zones

1. **Onboarding wizard** (first run only, linear) — see A4.
2. **Core app** — **chat is home**, with an expanding **dossier** header and four spokes.
3. **Safety layer** — always on top of everything (A6).

**Navigation model: chat + expanding dossier.** Chat is the whole home surface. A persistent dossier bar (rank · merit · active task) pins her live status on top and **expands in place** into status + the four spokes. The spokes are real, deep-linkable routes (`/today`, `/standing`, `/profile`, `/character`) rendered as in-place takeovers. Settings holds preferences + delete-everything. **LLM provider configuration is an admin/config-file concern — it is NOT a user-facing screen.**

**Screen map** (`[now]` = backend exists today; `[later]` = future milestone):
- **Onboarding** `[now]`: 18+ gate & consent → archetype questionnaire → kink/limits sheet → toy inventory → SO context → goals → character model → **preferences (its own step)** → reveal/first chat.
- **Core** `[later]`: chat home, dossier header, proof capture, settings (`[partial now]`).
- **Spokes:** Today/Task `[later]`, Standing/Economy `[later]`, Sub Profile `[now]`, Character Model `[now]`.
- **Safety** `[now]`: safeword/panic, aftercare, well-being controls, crisis resources.

## A3. Discretion posture (v1)

**Minimal.** Rely on device-level security; no in-app lock, no disguised identity in v1. Keep the shell simple. (App-lock / neutral identity remain an easy later hardening, alongside the deferred encryption-at-rest.)

## A4. Onboarding — pure structured wizard

A clean, clinical, **structured wizard** (not a chat interview): one concern per screen, a thin numbered progress rail, **save-and-resume** (each step POSTs to its matching per-step backend endpoint as you go), back/next footer. The mistress does **not** appear during intake — her **first appearance is a "reveal"** once the profile is assembled, which suits the severe, earned tone.

**The two hard screens:**
- **Archetype questionnaire:** one statement per card with a drag scale; calm and unrushed across the full statement set.
- **Kink / limits sheet:** a single scrollable grid **grouped by category**, with a **6-way segmented control** per row (Favorite / Like / Curious / Soft-limit / Hard-limit / N-A). **Hard-limits render in crimson, soft-limits in muted-crimson** so this safety-critical data reads at a glance. A legend + search/category-jump keeps the long list manageable.

## A5. Chat surface & dossier

- **Tool actions render as structured cards inline in the stream.** When the mistress acts through a tool (assign task, set denial timer, grant/revoke token, etc.), it appears as a card in the conversation — chat and authoritative state can never silently disagree.
- **Disposition line:** a subtle monospace line under the dossier surfaces her current mood **+ reason** (e.g., "cold · exacting — two recent misses"), making earned intensity legible.
- **Dossier expands in place** into rank, merit-to-next-rank bar, tokens, denial timer, active task, and the four spokes.
- **Bubbles:** her messages = `--raised` with a crimson left hairline (left-aligned); the sub's = filled gray (right-aligned).
- **Safeword pinned to the input bar at all times.**

## A6. Safety layer (UI)

Deterministic; never routed through the persona; works even if the LLM is down.

- **Two exits.**
  - **SAFE button — considered exit:** one tap → **a single confirmation** ("Stop everything?"). The confirmation deliberately carries the weight of *questioning the mistress*. **Critically, the scene pre-halts the instant the sheet opens** — timers and denial pressure lift silently *before* you confirm — so you are never under pressure while deciding; confirming only finalizes the full stop.
  - **Typed safeword phrase — emergency exit:** the recognized phrase, intercepted **before the LLM**, stops **instantly with no confirmation**. The frictionless path for genuine panic.
- Both land on the same **calm, out-of-persona** stop screen: a status receipt (scene halted, timers paused, denial lifted, **no merit penalty**) in a plain caring voice — the one place the severe styling intentionally softens — with aftercare, "just sit a while," resume-when-ready, and one-tap crisis **resources**.
- **Well-being controls** grouped together: pause/hiatus (no penalty), lower-a-limit (honored immediately), consent check-in cadence, the intensity ceiling, and one-tap **delete-everything**.

## A7. Frontend tech architecture

**Stack:** SvelteKit 2 + **Svelte 5 (runes)**, TypeScript, Vite, `@vite-pwa/sveltekit`. Switch `adapter-auto` → **`adapter-node`** to run as a server on the single VPS via docker-compose alongside FastAPI.

**Topology — SvelteKit as a thin BFF:** the browser talks only to SvelteKit; SvelteKit server routes proxy to the FastAPI backend, keeping the session cookie and API base URL server-side.

**Layered `src/lib/`:**
- `api/` — one typed module per backend resource over a single `client.ts` (base URL, error normalization, retry).
- `types/` — **generated from FastAPI's `openapi.json`** via `openapi-typescript` (`npm run gen:api`); backend Pydantic schemas are the source of truth, so types never drift.
- `stores/` (runes) — `session`, `onboardingDraft` (save-and-resume), `chat`, `dossier` (economy/disposition), and a global **`safety`** store.
- `design/` — Severe Editorial tokens (A1) as CSS custom properties + primitive components (`Button`, `Chip`, `Bubble`, `DossierBar`, `SegmentedControl`, `ProgressRail`).

**Routes:** `/onboarding/[step]` (guarded: redirect here until a profile exists); `/` chat home (guarded: needs a profile); `/today` `/standing` `/profile` `/character` `/settings` as deep-linkable spokes rendered as takeovers. **Safety is a global overlay** mounted in the root `+layout` (not a route), plus controls under `/settings`.

**Safety client module:** the pre-halt is pure client state (stop timers, set `paused`) fired *before* any network call; the typed-phrase interceptor sits on the chat input and short-circuits before send.

**PWA:** `adapter-node` + vite-pwa for installability and an offline app shell; neutral-ish manifest. Camera/timer permissions deferred to the proof milestone.

**Testing:** Vitest unit + `@testing-library/svelte` components; **Playwright** E2E (onboarding→profile now, extended to first-task later).

**Build order, honest to the backend:**
- **Phase A — `[now]`:** app shell + design system + onboarding wizard + Sub Profile / Character Model view-edit screens + safety *shell* (client-deterministic controls).
- **Phase B — `[later]`:** chat surface, live dossier data, tasks/proof capture, economy — as those backends land.

## Addendum Decision Log

- Aesthetic = **Severe Editorial** (monochrome + crimson accent, mono data, considered not crude).
- Navigation = **chat home + expanding dossier**; spokes are deep-linkable takeovers; safeword always pinned.
- Onboarding = **pure structured wizard** with save-and-resume; mistress is a post-intake **reveal**.
- Discretion = **minimal in v1** (device security only).
- Preferences = **its own onboarding step**; **provider config = admin/config-file, not UI**.
- Chat = **inline tool-cards** + **disposition line**; dossier expands in place.
- Kink sheet = grouped grid, **6-way segmented control**, **crimson/muted-crimson** for hard/soft limits.
- Safeword = **one confirmation with a pre-halt** (the considered exit, weight of questioning her) **+ instant typed-phrase** (emergency exit); calm out-of-persona stop screen.
- Tech = **SvelteKit (Svelte 5 runes) + adapter-node**, **BFF proxying FastAPI**, **OpenAPI-generated types**, safety as a global client overlay, phased A/B build order.

---

# Addendum B — Offline-First & Modes of Control (whole-app pivot)

**Date:** 2026-06-08
**Status:** Approved design, ready for implementation planning.
**Scope:** A foundational pivot affecting the architecture (§2), persona engine (§5), loop (§6),
economy (§7), and safety (§9). Reframes the existing built work (live LLM chat, tool-cards,
disposition engine, economy) as **session mode** and wraps an **offline-first** layer around it.
Seed ideas: `docs/ideas/offline-ai.md` and `docs/ideas/mode of control.md`.

## B0. Why — the premise

The app must be usable on a 24/7 VPS that has **no GPU**. The LLM runs on a **home gaming box**
that is only powered on intermittently. So a live, LLM-every-turn chat experience cannot be the
*normal* state. Rather than treat this as degradation, we make it the **premise**: **the Mistress
is away; her drones carry out her standing orders, and an audience with her is a privilege you
earn.** The offline/online seam becomes thematic, not apologetic.

A separate real-life constraint also gets first-class support: a sub has families, jobs, and
obligations, so the depth of control she may exert must adapt to the sub's current situation
(`mode of control.md`).

## B1. Two orthogonal axes

The system composes **two independent dimensions**. Almost every behavior is a function of both.

| Axis | Values | Answers | Set by |
|---|---|---|---|
| **Her presence** | offline · batch window · live audience | *Is **she** (the LLM) reachable?* | the home box + the heartbeat agent (B2) |
| **Supervision mode** | full · discreet · task · homeoffice · vacation | *How deeply can the **sub** be controlled right now?* | the sub, manually (B6) |

They stack. *offline + homeoffice* → drones drop only discreet, timer-graced tasks. *live audience
+ discreet* → even **she** keeps it quiet and brief. Supervision mode **binds her too**, not just
the drones — it reflects the sub's real-world capacity, which her presence does not change.

## B2. Her-presence states & connectivity

| State | LLM | What runs | Who is "present" |
|---|---|---|---|
| **OFFLINE** (default) | down | deterministic drone engine serving the batch-generated pools | the drones |
| **BATCH WINDOW** (semi-opportunistic) | up, briefly | LLM regenerates pools, ingests queued memory, judges queued proof — **no live chat** | drones (background) |
| **LIVE AUDIENCE** (deliberate ritual) | up | full LLM chat (the current built experience), settles backlog on entry | **her** |

**Connectivity — home-box agent + outbound heartbeat.** A home gaming box behind NAT / a dynamic
IP cannot be reached *by* the VPS, so the box must initiate. A small **agent** on the gaming box,
on boot, opens an **outbound** connection to the VPS and sends heartbeats while the local
OpenAI-compatible LLM endpoint is reachable. The VPS marks LLM `online` while heartbeats arrive and
`offline` once they lapse. The VPS never needs to reach inward.

- A **live audience** requires the box up **and** the sub deliberately opening an audience in-app.
- A **batch window** is requested by the VPS (a pending-job flag the agent observes); the agent runs
  the job opportunistically while the box is up — including when the app *asks the sub to keep the
  box on a while* to refill thin pools.
- All model traffic still rides the existing swappable OpenAI-compatible provider seam (§2). The
  agent is transport/availability only; it does not change how calls are made.

## B3. The drone layer

Offline, deterministic **drones** stand in for the Mistress. **One cold, mechanical functionary
register**, split by **duty unit**:

- **Assignment unit** — drops the day's task(s) from the task pool.
- **Discipline unit** — issues punishments, maintains the debt ledger, posts penance.
- **Reminder unit** — deadline nudges, denial-timer notices, batch-window requests.

Voice is flat and impersonal ("Mistress has assigned… Report when complete."), **visually distinct**
from her `--raised`/crimson bubbles (a colder, unit-labeled, monospace-leaning treatment) so her
live warmth reads as earned.

**Offline surface = check-in / dossier-led, not freeform chat.** Home offline is a **standing-orders
dossier**: today's task(s), active denial timers, the **debt ledger**, merit standing, and
**pending-her-review** items, each with a short drone line. Interaction is **structured controls**
— *mark complete, submit proof, start timer, acknowledge* — not conversation. Freeform chat is
**dimmed and labeled "she is away"**; dialogue is explicitly a live-audience privilege. (The chat
input offered offline is reduced to structured reporting.)

## B4. Batch generation

When the box is up (a batch window, or at the close of a live audience), the LLM pre-generates the
material the offline drones serve — **four artifacts**:

1. **Task pool** — state-keyed tasks tailored to goals/profile/skill and difficulty band, each
   carrying proof type, merit/debt stakes, and an **intensity/discreetness/required-toy** profile
   (B6). Refilled when low.
2. **Drone line bank** — prefab in-persona lines per drone event (task drop, reminder, completion
   ack, miss notice, punishment issued) × merit band × time-of-day, drawn by state so nothing
   repeats verbatim. Regenerated periodically against staleness.
3. **Punishment pool** — pre-authored consequences tagged by severity, so the discipline unit can
   impose a fitting, varied punishment with no LLM present.
4. **Standing orders** — at the close of each live audience she dictates a short directive set
   (focus areas, special conditions, a personal line or two) that flavors the drones until the next
   audience, tying offline behavior to the last real interaction.

When any pool runs thin, the reminder unit prompts the sub to grant a batch window.

## B5. Offline accrues / online settles

A single consistent rhythm governs everything the LLM is needed for but is absent for:

- **Media proof (photo/video)** → captured offline, stored, marked **"pending her review."** The
  vision model judges the backlog at the next batch window / audience; merit and debt settle then.
  A bad backlog can sour an audience.
- **Evolving memory (Graphiti)** → episodes **queue** offline and **ingest** when the box is up
  (consistent with §3's degradation rule).
- **Honor reports & timers** stay fully deterministic and resolve **immediately** offline.

"Offline you accrue; when she returns, accounts settle."

## B6. Supervision modes

A second axis (B1) describing how deeply the sub can be controlled right now. **Five modes:**

| Mode | Meaning |
|---|---|
| **Full supervision** | Sub fully available; she may use him at her mercy, anytime. |
| **Discreet supervision** | Family/kids around: only quiet, agreed, discreet toys/kinks; no noise. |
| **Task mode** | Only tasks with **graceful fulfillment timers**; no expectation of immediate reaction. |
| **Homeoffice** | A discreet variant flagged *working / in meetings*: can't react instantly; discreetly-usable toys/tasks only. |
| **Vacation** | Pauses training for a period. |

- **Set manually in v1.** A simple in-app mode switch. A **schedule + calendar view** (the file's
  ask) is **deferred** to a later milestone.
- **Deterministic content filter (works offline).** Toys carry **discreetness flags**
  (noise / visibility); every generated task carries an **intensity + discreetness profile +
  required toys**. The active mode is a filter the drone engine *and* the live Mistress apply when
  selecting tasks/punishments. Each mode also has a free-text **"what's possible right now"** note
  the sub writes, so she/the drones understand the constraints (per the file's *"explained by the
  sub"*).
- **Mode × economy:** **Vacation freezes the economy** — no task drops, **no merit decay, no debt
  accrual** while active. All other modes **only filter content**; merit/debt/token stakes are
  unchanged across full/discreet/task/homeoffice.
- **Mode is a consent/comfort control (§9):** lowering control depth, or entering vacation, is
  honored **immediately**, like lowering a limit.

## B7. Economy revision — three quantities

The economy now runs on **three distinct quantities**, each answering a different question:

| | **MERIT** | **DEBT** | **TOKENS** |
|---|---|---|---|
| Answers | *Who you are to her now* (standing) | *What you owe* (unpaid penance) | *What you've banked* (reward purse) |
| Direction | Bidirectional, fluid | Accrues on failure, cleared by penance | Earned in chunks, spent |
| Driven by | On-time honest obedience ↑ / misses & fails ↓ | A miss/fail issues a punishment → debt ↑ | Granted for *exceptional* obedience |
| Controls | Disposition tone (§5) + **audience eligibility & type** (B8) | Offline drone pressure + the **reckoning** audience's substance | Comforts, privileges, and a **pleasurable audience** |

**Punishment system = a debt ledger** (generalizing the old denial timer). A miss/fail drops merit
**and** the discipline unit issues a punishment from the punishment pool — a **denial-timer
extension, mandatory penance task, lines/writing, privilege lock, or token confiscation** — logged
as a line item that adds to a persistent **debt balance**.

**Clearing debt:**
- **Penance** — serve the punishment with proof. This is the primary path.
- **Token buy-down** — she will *occasionally* let the sub spend tokens to buy debt down, at a
  **deliberately punishing exchange rate**. Escapes debt but earns **no merit**.

**Penance × merit (manner of submission matters):** penance served **promptly and honestly** grants
a **small merit recovery**; penance that is dodged, late, or token-bought-down clears the debt with
**no merit gain** (or a further ding). The original miss's merit hit stands regardless.

All three quantities remain enforced by the single economy service (merit bounded, tokens never
negative, **debt never negative**, atomic transactions).

## B8. Live audience lifecycle

A deliberate ritual, available only when the box is up.

1. **Eligibility & price** — gated by **merit band** (eligibility & type) and **tokens** (the price
   to open the door). A pleasurable audience requires good standing **and** saved tokens.
2. **Settle on entry** — the vision model judges queued media proof and Graphiti ingests queued
   episodes; the resulting merit/debt changes apply. *"She reviews what you've done since."*
3. **Type by merit** — **low merit → a reckoning** (she works the debt backlog personally);
   **high merit → pleasurable / rewarding.** This rides the existing merit→disposition engine (§5).
4. **The session** — the existing built chat experience (persona engine, tool-cards), now also
   **bounded by the active supervision mode** as well as limits and the intensity ceiling.
5. **Close** — she dictates fresh **standing orders** (B4) and the agent **regenerates the offline
   pools** while the box is still up, then she withdraws to offline.

## B9. Safety under offline & modes

Offline-first makes "**works even if the LLM is down**" the *normal* operating case, strengthening
§9 rather than changing it.

- Safeword/panic, limit enforcement, intensity ceiling, well-being controls, and delete-everything
  are all deterministic and **fully functional offline**. **The drones never gate safety.**
- **Supervision mode is itself a consent control:** lowering control depth or entering **vacation**
  is honored immediately (B6), with **no merit penalty** (vacation freezes the economy).
- The output filter and limit injection still apply to every live-audience turn; the deterministic
  drone engine selects only mode- and limit-compliant content offline.

## B10. Data-model deltas (forward-compatible)

New / changed Postgres entities and fields (logic lands per milestone):

- **Availability:** `llm_availability` state (offline/batch/audience) + last-heartbeat; the home-box
  **agent** (separate deployable, outbound heartbeat + batch-job runner).
- **Supervision mode:** `supervision_mode` (current) + per-mode **"what's possible"** note on the
  profile. *(Schedule/calendar entities deferred.)*
- **Toy:** discreetness flags (`noise`, `visibility`, `discreet_capable`).
- **Task:** `intensity`, `discreetness`, `required_toy_ids`, a `punitive` flag, and a
  **`pending_review`** proof state.
- **Debt / punishment:** a `debt` balance on the economy state + a `punishment` ledger
  (line items: type, severity, stakes, status — issued/served/bought-down/expired).
- **Batch artifacts:** storage for the task pool, drone line bank, punishment pool, and standing
  orders (with freshness/depletion metadata).

## B11. Build order — reframe built work as "session mode"

The current build (live LLM chat, tool-cards, disposition, economy) is retained as the **live
audience** experience. Milestones replan **forward** from there. Indicative order (the
**writing-plans** step produces the authoritative breakdown):

1. **Availability** — `llm_availability` state + the home-box heartbeat agent; gate live chat on it.
2. **Drone engine + offline surface** — duty units, the standing-orders dossier, dimmed chat.
3. **Batch generation** — the four artifacts + standing orders at audience close.
4. **Debt / punishment system** — three-quantity economy, ledger, penance, token buy-down.
5. **Supervision modes** — manual switch, discreetness tagging on toys/tasks, vacation freeze.
6. **Queued proof & memory** — settle-on-entry at batch/audience.
7. *(Deferred)* mode **schedule + calendar view**.

## Addendum B Decision Log

- Premise = **offline-first**: VPS 24/7, LLM on an intermittent home box → **"the Mistress is
  away; her drones serve; an audience is earned."** Built work becomes **session mode**.
- **Two orthogonal axes:** her-presence (offline/batch/audience) × supervision mode
  (full/discreet/task/homeoffice/vacation); both filter behavior; mode **binds her too**.
- Connectivity = **home-box agent + outbound heartbeat** (NAT/dynamic-IP safe; VPS never reaches in).
- Drones = **one cold functionary register, split by duty unit**; offline surface = **dossier +
  structured controls**, freeform chat dimmed.
- Batch layer = **task pool + drone line bank + punishment pool + standing orders**; refill-when-low.
- Rhythm = **offline accrues / online settles**: media proof **queued for review**, memory queued.
- Economy = **three quantities** (merit / debt / tokens); denial timer generalized into a
  **punishment debt ledger**; cleared by **penance** or **token buy-down** (no merit); honest prompt
  penance gives a **small merit recovery**.
- Live audience = **merit gates eligibility & type, tokens pay**; **settle backlog on entry**;
  **low merit → reckoning, high merit → pleasurable**; close dictates **standing orders** + refills.
- Supervision modes = **manual in v1** (schedule deferred); **vacation freezes the economy**, other
  modes **only filter**; discreetness modeled as **flags on toys + a profile on tasks**.
- Safety = **unchanged and reinforced**; drones never gate safety; mode is a consent control honored
  immediately.
