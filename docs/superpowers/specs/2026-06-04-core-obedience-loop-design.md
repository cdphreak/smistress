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
