# Offline-First Milestone 6 — Queued Proof & Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land Addendum B §B5's "offline accrues / online settles" rhythm for media proof and evolving memory: media proofs queue as `pending_review` and a real vision model judges them when the box is back; the Graphiti outbox drains only when she's reachable; a `punitive` flag distinguishes penance tasks; a manual online-gated `POST /profile/{id}/backlog/settle` is the settle beat and the reusable hook the audience-lifecycle milestone (B8) calls on entry.

**Architecture:** One additive Alembic migration adds `proof.media_uri` and `task.punitive` (with a backfill joining `punishment.penance_task_id`). `ChatMessage` gains an optional `images` list; the OpenAI-compatible provider formats the multipart content payload, the mock records it. `verify_media` becomes a real multimodal judge (called only by the new `settle_backlog`, never by the synchronous `verify_task`); `verify()`'s PHOTO/VIDEO branch returns `pending_review` when a vision model is configured, or auto-passes (today's honor-system behavior) when none is. A new `app/backlog/service.py` owns `settle_backlog`: per-task dedup (latest `pending_review` proof wins; older ones stamped `supuperseded`), misconfig (skipped+logged) vs. transient (errored,left pending) split, memory drain. A new `app/api/backlog.py` exposes the online-gated endpoint. `drain_outbox` gains an optional `profile_id` filter. No audience lifecycle, no presence-state-machine, no frontend surfacing (deferred to Offline-6b).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async (psycopg3), Alembic, Pydantic v2, pytest (asyncio_mode=auto, live Postgres `smistress_test`), ruff line-length=100.

**Spec:** [`docs/superpowers/specs/2026-10-24-offline-6-queued-proof-memory-design.md`](../specs/2026-10-24-offline-6-queued-proof-memory-design.md) — argues from Addendum B §B2/B3/B4/B5/B7/B9/B10/B11 of [`docs/superpowers/specs/2026-06-04-core-obedience-loop-design.md`](../specs/2026-06-04-core-obedience-loop-design.md).

---

## Global Constraints

- **Backend tests** (run from `backend/`, this Windows box's uv-trampoline): `PYTHONHOME= PYTHONPATH= uv run python -m pytest <args> -q`. Requires Postgres up (`docker compose up -d` from repo root). The `session` fixture rebuilds schema via `Base.metadata` (drop+create), so model-attribute additions are test-visible without the migration; the migration is CI-authoritative (`tests/db/test_migration.py` may fail locally per dev-env notes — do not debug locally).
- **Services flush, endpoints commit.** PG enums store member NAMES (no new enums this milestone). Bare-UUID cross-aggregate refs stored as strings in JSONB (none added this milestone).
- **Swappable seam:** `LLMProvider` is a `Protocol` with `supports_vision: bool`. The mock provider MUST exercise the vision path so the suite runs fully offline. `build_provider` already wires `supports_vision=settings.vision_enabled`.
- **Graceful degradation (spec §2/§3, flagged call #1):** with no vision model configured, media proof keeps the existing synchronous auto-pass — no queueing, no regression. `vision_enabled` gates both the eager `pending_review` stamp (submit) and the `verify()` routing.
- **Alembic head at time of writing:** `b8c9d0e1f2a3` (`add_punishment_discreetness`) — preflight-corrected; the chain runs … → `f6a7b8c9d0e1` → `a7b8c9d0e1f2` → `b8c9d0e1f2a3`. Confirm with `uv run alembic heads` before writing the migration. The new migration chains from it.
- **Commits:** one per task, conventional-commit messages.

---

## Review Focus

Five input classes / failure modes the spec implies but no task's tests naturally exercise, most likely to bite a person using this software. Each line's test is added to the owning task.

1. **Media proof submitted with no vision model configured** — must auto-pass synchronously at `verify_task` (today's honor-system behavior), NOT queue as `pending_review` forever. → Task 3 (`verify_media` no-vision branch returns PASS) + Task 4 (`submit_proof` leaves `verdict="pending"` when `vision_enabled` is False).
2. **Two media proofs submitted for the same task before any settle** — only the latest `pending_review` proof is judged; the older is `superseded`; merit/debt applied exactly once (§B7 atomic-single-outcome). → Task 6 (dedup test).
3. **Vision model configured but the provider lacks vision support** (permanent misconfig) — proofs stay `pending_review`, counted in `skipped`, logged once per settle; not an infinite silent retry, not a crash. → Task 6 (skipped+log test).
4. **Transient provider exception mid-settle** — the offending proof stays `pending_review` (retriable next settle), counted in `errored`, no partial merit/debt applied for it; other proofs still judged. → Task 6 (errored test).
5. **`settle_backlog` invoked while the box is offline** — 503, no judging, no memory drain. → Task 8 (503 test).

(Cross-profile memory isolation — draining one profile's settle doesn't drain another's — is covered in Task 5 and exercised end-to-end in Task 6.)

---

## File Structure

**New (backend/):**
- `app/backlog/__init__.py` — empty package marker.
- `app/backlog/service.py` — `SettlementSummary` dataclass + `settle_backlog`.
- `app/api/backlog.py` — `POST /profile/{profile_id}/backlog/settle` (online-gated).
- `app/schemas/backlog.py` — `SettlementOut` (Pydantic, `from_attributes=True`).
- `alembic/versions/g7b8c9d0e1f2_add_queued_proof_memory.py` — `proof.media_uri` + `task.punitive` (+ backfill).
- `tests/backlog/__init__.py`, `tests/backlog/test_settle.py`.
- `tests/api/test_backlog_api.py`.

**Modified (backend/):**
- `app/db/models/loop.py` — `Proof.media_uri`.
- `app/db/models/task.py` — `Task.punitive`.
- `app/llm/types.py` — `ChatMessage.images`.
- `app/llm/openai_provider.py` — multipart content formatting.
- `app/llm/mock.py` — (no behavioral change; `images` rides along on recorded messages — add a covering test).
- `app/loop/verification.py` — rewrite `verify_media` signature/body; `verify()` PHOTO/VIDEO branch returns `pending_review` (vision) or `PASS` (no vision).
- `app/loop/service.py` — `submit_proof` gains `media_uri` param + conditional eager `pending_review` stamp.
- `app/memory/service.py` — `drain_outbox` gains `profile_id` filter.
- `app/discipline/service.py` — `issue_punishment` sets `punitive=True` on the penance `Task`.
- `app/schemas/task.py` — `ProofIn.media_uri`; `TaskOut.punitive`; `TaskCreate.punitive`.
- `app/api/tasks.py` — `submit_proof` endpoint passes `media_uri` through.
- `app/main.py` — mount `backlog_router`.
- Tests: `tests/loop/test_verification.py` (rewrite the two `verify_media` tests for the new signature + add vision-judge cases); `tests/loop/test_loop_service.py` (media submit + verify_task routing); `tests/llm/test_openai_provider.py` (multipart); `tests/llm/test_mock.py` (records images); `tests/memory/test_memory_service.py` (scoped drain); `tests/discipline/test_service.py` (penance `punitive=True`); `tests/api/test_tasks_api.py` (endpoint passes `media_uri`; `TaskOut.punitive`).

**Frontend (hygiene only — not imported in `src/`):**
- `frontend/openapi.json`, `frontend/src/lib/types/api.ts` — regenerated (Task 9).

---

## Task 1: Migration — `proof.media_uri` + `task.punitive` (with backfill)

**Files:**
- Modify: `backend/app/db/models/loop.py` (after `content`, ~line 25), `backend/app/db/models/task.py` (after `required_toy_ids`, ~line 38)
- Create: `backend/alembic/versions/g7b8c9d0e1f2_add_queued_proof_memory.py`
- Test: `backend/tests/db/test_loop_models.py` (extend `test_proof_defaults`; add a punitive-default test in `backend/tests/db/test_task_model.py`)

**Interfaces:**
- Produces: `Proof.media_uri: Mapped[str | None]` (nullable, default None); `Task.punitive: Mapped[bool]` (non-null, server_default false). Later tasks rely on these existing.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/db/test_loop_models.py`:

```python
async def test_proof_media_uri_nullable_default(session):
    t = await _task(session)
    session.add(Proof(task_id=t.id, profile_id=t.profile_id, content=""))
    await session.commit()
    pr = (await session.execute(select(Proof))).scalar_one()
    assert pr.media_uri is None
```

Append to `backend/tests/db/test_task_model.py`:

```python
async def test_task_punitive_defaults_false(session):
    # reuse that file's existing _task/_profile helper if present, else construct inline
    from app.db.enums import ProofRequirement
    from app.db.models.profile import SubProfile
    from app.db.models.task import Task

    p = SubProfile(intensity_ceiling=50)
    session.add(p)
    await session.flush()
    t = Task(profile_id=p.id, description="x", proof_requirement=ProofRequirement.HONOR)
    session.add(t)
    await session.flush()
    assert t.punitive is False
```

Confirm `select` and `Proof` are imported in `test_loop_models.py` (they are).

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/db/test_loop_models.py tests/db/test_task_model.py -q`
Expected: FAIL — `AttributeError: 'Proof' object has no attribute 'media_uri'` / `'Task' object has no attribute 'punitive'`.

- [ ] **Step 3: Add the model attributes**

In `backend/app/db/models/loop.py`, after the `content` line:

```python
    media_uri: Mapped[str | None] = mapped_column(String, default=None)
```

(`String` is already imported.)

In `backend/app/db/models/task.py`, after `required_toy_ids`:

```python
    punitive: Mapped[bool] = mapped_column(default=False)
```

(Boolean is not yet imported in that file — add `Boolean` to the `from sqlalchemy import ...` line.)

- [ ] **Step 4: Create the migration**

Create `backend/alembic/versions/g7b8c9d0e1f2_add_queued_proof_memory.py` modeled on `f6a7b8c9d0e1_add_toy_discreetness.py`. Header: `revision = 'g7b8c9d0e1f2'`, `down_revision = 'b8c9d0e1f2a3'` (the actual head — preflight-corrected; confirm first with `uv run alembic heads`). `upgrade()`:

```python
    op.add_column('proof', sa.Column('media_uri', sa.String(), nullable=True))
    op.add_column('task', sa.Column('punitive', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.execute(
        "UPDATE task SET punitive = true WHERE id IN "
        "(SELECT penance_task_id FROM punishment WHERE penance_task_id IS NOT NULL)"
    )
```

`downgrade()`: drop the two columns (`task.punitive`, then `proof.media_uri`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/db/test_loop_models.py tests/db/test_task_model.py -q`
Expected: PASS. (Do not run `tests/db/test_migration.py` locally — it may fail on this Windows box per dev-env notes; CI is authoritative.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models/loop.py backend/app/db/models/task.py backend/alembic/versions/g7b8c9d0e1f2_add_queued_proof_memory.py backend/tests/db/test_loop_models.py backend/tests/db/test_task_model.py
git commit -m "feat(db): proof.media_uri + task.punitive (with backfill)"
```

---

## Task 2: Multimodal `ChatMessage` + provider support

**Files:**
- Modify: `backend/app/llm/types.py` (`ChatMessage`), `backend/app/llm/openai_provider.py` (`chat`)
- Test: `backend/tests/llm/test_types.py`, `backend/tests/llm/test_openai_provider.py`, `backend/tests/llm/test_mock.py`

**Interfaces:**
- Produces: `ChatMessage.images: list[str]` (URIs/data-URLs; default `[]`). `OpenAICompatibleProvider.chat` formats the OpenAI multipart `content` list when any message has non-empty `images`; otherwise unchanged. The mock records `images` on the captured message (automatic via the existing `self.calls.append(list(messages))`).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/llm/test_types.py`:

```python
def test_chatmessage_images_defaults_empty():
    from app.llm.types import ChatMessage
    m = ChatMessage(role="user", content="hi")
    assert m.images == []
```

Append to `backend/tests/llm/test_openai_provider.py`:

```python
async def test_formats_multipart_when_images_present():
    client = _fake_client(SimpleNamespace(content="ok", tool_calls=None))
    p = OpenAICompatibleProvider(
        base_url="x", api_key="x", default_model="m", supports_vision=True, client=client
    )
    await p.chat([ChatMessage(role="user", content="judge this", images=["data:image/png;base64,AAA"])])
    sent = client.chat.completions.kwargs["messages"][0]["content"]
    assert isinstance(sent, list)
    assert any(part.get("type") == "text" for part in sent)
    assert any(part.get("type") == "image_url" for part in sent)


async def test_plain_string_content_when_no_images():
    client = _fake_client(SimpleNamespace(content="ok", tool_calls=None))
    p = OpenAICompatibleProvider(
        base_url="x", api_key="x", default_model="m", supports_vision=False, client=client
    )
    await p.chat([ChatMessage(role="user", content="yo")])
    assert client.chat.completions.kwargs["messages"][0]["content"] == "yo"
```

Append to `backend/tests/llm/test_mock.py`:

```python
async def test_mock_records_images_on_call():
    p = MockLLMProvider()
    await p.chat([ChatMessage(role="user", content="judge", images=["uri1"])])
    assert p.calls[0][0].images == ["uri1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/llm/test_types.py tests/llm/test_openai_provider.py tests/llm/test_mock.py -q`
Expected: FAIL — `TypeError: ChatMessage.__init__() got an unexpected keyword argument 'images'` / multipart assertion failures.

- [ ] **Step 3: Add `images` to `ChatMessage`**

In `backend/app/llm/types.py`, add to the `ChatMessage` dataclass:

```python
    images: list[str] = field(default_factory=list)
```

(`field` is already imported.)

- [ ] **Step 4: Format multipart content in the OpenAI provider**

In `backend/app/llm/openai_provider.py` `chat`, build the per-message `content`:

```python
    def _msg_content(m):
        if not m.images:
            return m.content
        parts = [{"type": "text", "text": m.content}]
        parts += [{"type": "image_url", "image_url": {"url": u}} for u in m.images]
        return parts

    msgs = [{"role": m.role, "content": _msg_content(m)} for m in messages]
```

Replace the inline comprehension in the `create(...)` call with `messages=msgs`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/llm/test_types.py tests/llm/test_openai_provider.py tests/llm/test_mock.py -q`
Expected: PASS (including the pre-existing `test_parses_plain_content` / `test_parses_tool_calls_and_model_override`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/llm/types.py backend/app/llm/openai_provider.py backend/tests/llm/test_types.py backend/tests/llm/test_openai_provider.py backend/tests/llm/test_mock.py
git commit -m "feat(llm): multimodal ChatMessage.images + OpenAI multipart formatting"
```

---

## Task 3: `verify_media` real vision judge + `verify()` routing

**Files:**
- Modify: `backend/app/loop/verification.py` (`verify_media`, `verify`)
- Test: `backend/tests/loop/test_verification.py` (rewrite the two `verify_media` tests; add vision-judge cases)

**Interfaces:**
- Produces: `verify_media(task, *, media_uri, provider, settings) -> VerdictResult` — the real judge (called by `settle_backlog` in Task 6, NEVER by `verify_task`). Branches: no vision model ⇒ `PASS` (auto-pass, unchanged); vision configured but `provider.supports_vision is False` ⇒ `pending_review` ("vision model configured but provider lacks vision support"); both present ⇒ call `provider.chat` with a multimodal message and parse via the existing `_parse_verdict`.
- Produces: `verify()` PHOTO/VIDEO branch returns `pending_review` when `settings.vision_enabled` is True (task stays `proof_submitted`), or `PASS` when False (synchronous auto-pass — today's behavior).
- Consumes: `ChatMessage.images` (Task 2).

- [ ] **Step 1: Rewrite the failing tests**

Replace the two `verify_media` tests at the bottom of `backend/tests/loop/test_verification.py` and append the vision-judge cases. The file already imports `Settings`, `TaskTimer`, `verify_media`, `verify_none`, `verify_timer`; add `from app.llm.mock import MockLLMProvider` and `from app.llm.types import ChatResult` and `from app.db.enums import ProofRequirement` and `from app.db.models.task import Task`. New test block:

```python
def _photo_task():
    from app.db.enums import ProofRequirement
    from app.db.models.task import Task
    return Task(description="send kneeling photo", proof_requirement=ProofRequirement.PHOTO)


def test_verify_media_autopasses_without_vision():
    v = verify_media(_photo_task(), media_uri="u", provider=MockLLMProvider(),
                    settings=Settings(vision_model=None))
    assert v.verdict == "pass"
    assert v.confidence is None
    assert "auto" in v.reasoning.lower()


def test_verify_media_pending_when_vision_configured_but_provider_lacks_vision():
    v = verify_media(_photo_task(), media_uri="u",
                    provider=MockLLMProvider(supports_vision=False),
                    settings=Settings(vision_model="qwen2.5-vl"))
    assert v.verdict == "pending_review"


def test_verify_media_judges_pass_via_vision_provider():
    prov = MockLLMProvider(supports_vision=True, scripted=[ChatResult(
        content='{"verdict": "pass", "confidence": 88, "reasoning": "visible", "issues": []}'
    )])
    v = verify_media(_photo_task(), media_uri="data:image/png;base64,AAA",
                    provider=prov, settings=Settings(vision_model="qwen2.5-vl"))
    assert v.verdict == "pass"
    assert v.confidence == 88
    assert prov.calls and prov.calls[-1][-1].images == ["data:image/png;base64,AAA"]


def test_verify_media_judges_fail_via_vision_provider():
    prov = MockLLMProvider(supports_vision=True, scripted=[ChatResult(
        content='{"verdict": "fail", "confidence": 30, "reasoning": "absent", "issues": ["no subject"]}'
    )])
    v = verify_media(_photo_task(), media_uri="u", provider=prov,
                    settings=Settings(vision_model="qwen2.5-vl"))
    assert v.verdict == "fail"


def test_verify_media_unparseable_vision_response_demands_reproof():
    prov = MockLLMProvider(supports_vision=True, scripted=[ChatResult(content="looks fine")])
    v = verify_media(_photo_task(), media_uri="u", provider=prov,
                    settings=Settings(vision_model="qwen2.5-vl"))
    assert v.verdict == "re_proof"
```

Also add a routing test for `verify()`:

```python
async def test_verify_routes_photo_to_pending_review_when_vision_enabled():
    import asyncio
    from app.db.enums import ProofRequirement
    from app.db.models.task import Task
    from app.loop.verification import verify
    from app.llm.mock import MockLLMProvider

    task = Task(description="x", proof_requirement=ProofRequirement.VIDEO)
    v = await verify(task, report="", timer=None,
                     provider=MockLLMProvider(), settings=Settings(vision_model="qwen2.5-vl"))
    assert v.verdict == "pending_review"


async def test_verify_routes_photo_to_pass_when_no_vision():
    from app.db.enums import ProofRequirement
    from app.db.models.task import Task
    from app.loop.verification import verify
    from app.llm.mock import MockLLMProvider

    task = Task(description="x", proof_requirement=ProofRequirement.PHOTO)
    v = await verify(task, report="", timer=None,
                     provider=MockLLMProvider(), settings=Settings())
    assert v.verdict == "pass"
```

(Note: `verify` is already `async` — it `await`s `verify_honor`. The PHOTO/VIDEO branch becomes a plain return, which is fine inside an `async def`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/loop/test_verification.py -q`
Expected: FAIL — `verify_media` takes `(settings)` (signature mismatch) / `verify` returns `pending` for the vision case.

- [ ] **Step 3: Rewrite `verify_media` and the `verify()` PHOTO/VIDEO branch**

In `backend/app/loop/verification.py`:

Add a constant near the top:

```python
PENDING_REVIEW = "pending_review"
```

Rewrite `verify_media` to the new signature. Body: (a) if `not settings.vision_enabled` → return `VerdictResult(PASS, None, "no vision model configured — auto-passed", [])`; (b) if `not provider.supports_vision` → return `VerdictResult(PENDING_REVIEW, None, "vision model configured but provider lacks vision support", ["provider lacks vision"])`; (c) else build a multimodal message — a `_VISION_SYSTEM` prompt that mirrors `_HONOR_SYSTEM`'s JSON contract (`{"verdict": "pass"|"fail"|"re_proof", "confidence": <0-100>, "reasoning": "...", "issues": [...]}`) and instructs the model to judge the photo/video against the task description — and a user turn with `content=f"TASK: {task.description}\nJudge the submitted media."` and `images=[media_uri]`; call `provider.chat(messages, model=settings.vision_model)` — the judge MUST hit the configured vision model, not the provider's chat-model default; return `_parse_verdict(result.content)`. Wrap the `provider.chat` call so any exception propagates (Task 6's settle handles transients).

In `verify()`, replace the final `# PHOTO or VIDEO` branch:

```python
    if pr in (ProofRequirement.PHOTO, ProofRequirement.VIDEO):
        if settings.vision_enabled:
            return VerdictResult(PENDING_REVIEW, None, "media proof queued for her review", ["pending review"])
        return VerdictResult(PASS, None, "no vision model configured — auto-passed", [])
```

(The exact `_VISION_SYSTEM` wording is yours — mirror `_HONOR_SYSTEM`'s JSON contract and strict-judge posture; the tests pin the contract, not the prose.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/loop/test_verification.py -q`
Expected: PASS (all old + new tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/loop/verification.py backend/tests/loop/test_verification.py
git commit -m "feat(verify): real vision judge + pending_review routing for media"
```

---

## Task 4: `submit_proof` accepts media + conditional eager `pending_review`

**Files:**
- Modify: `backend/app/loop/service.py` (`submit_proof`), `backend/app/schemas/task.py` (`ProofIn`), `backend/app/api/tasks.py` (`submit_proof` endpoint)
- Test: `backend/tests/loop/test_loop_service.py` (append), `backend/tests/api/test_tasks_api.py` (append)

**Interfaces:**
- Produces: `loop_svc.submit_proof(session, task_id, *, report="", media_uri=None, settings: Settings | None = None) -> Proof`. Behavior: stores `proof.media_uri`; if `proof_requirement in (PHOTO, VIDEO)` AND `media_uri` AND the effective settings' `vision_enabled` → `proof.verdict = "pending_review"`; else `verdict` stays the default `"pending"`. Timer-stop logic unchanged. The gate must be test-controllable: `settings=None` falls back to a module-level `_DEFAULT_SETTINGS = Settings()` (vision off under the test env), and tests that want queueing pass `Settings(vision_model="qwen2.5-vl")` explicitly — mirroring `verify_task`'s explicit `(provider, settings)` pattern.
- Produces: `ProofIn.media_uri: str | None = None`.
- Consumes: `Proof.media_uri` (Task 1), `Settings.vision_enabled`.
- **Review-Focus #1:** no-vision media submit leaves `verdict="pending"` (so `verify_task` auto-passes synchronously, unchanged).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/loop/test_loop_service.py`:

```python
async def test_submit_media_proof_queues_pending_review_when_vision_enabled(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="kneeling photo", proof_requirement=ProofRequirement.PHOTO,
    )
    await session.commit()
    await loop_svc.start_task(session, task.id)
    await session.commit()

    proof = await loop_svc.submit_proof(
        session, task.id, media_uri="data:image/png;base64,AAA",
        settings=Settings(vision_model="qwen2.5-vl"),
    )
    await session.commit()

    assert proof.media_uri == "data:image/png;base64,AAA"
    assert proof.verdict == "pending_review"
    refreshed = await session.get(type(task), task.id)
    assert refreshed.status is TaskStatus.PROOF_SUBMITTED


async def test_submit_media_proof_leaves_pending_when_no_vision(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="kneeling photo", proof_requirement=ProofRequirement.PHOTO,
    )
    await session.commit()
    await loop_svc.start_task(session, task.id)
    await session.commit()

    proof = await loop_svc.submit_proof(
        session, task.id, media_uri="data:image/png;base64,AAA",
    )  # default Settings() has vision_model=None
    await session.commit()

    assert proof.verdict == "pending"  # NOT queued — honor-system auto-pass path


async def test_verify_task_on_vision_media_proof_stays_proof_submitted(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="kneeling photo", proof_requirement=ProofRequirement.PHOTO,
    )
    await session.commit()
    await loop_svc.start_task(session, task.id)
    await session.commit()
    await loop_svc.submit_proof(session, task.id, media_uri="data:image/png;base64,AAA")
    await session.commit()

    verified = await loop_svc.verify_task(
        session, task.id, MockLLMProvider(supports_vision=False),
        Settings(vision_model="qwen2.5-vl"),
    )
    await session.commit()
    assert verified.status is TaskStatus.PROOF_SUBMITTED  # awaits settle, not auto-passed
```

Append to `backend/tests/api/test_tasks_api.py`:

```python
async def test_submit_proof_endpoint_accepts_media_uri(client):
    pid = await _new_profile(client)
    tid = (await client.post(f"/profile/{pid}/tasks", json={
        "description": "posture photo", "proof_requirement": "photo",
    })).json()["id"]
    await client.post(f"/tasks/{tid}/start")
    r = await client.post(f"/tasks/{tid}/proof", json={
        "report": "", "media_uri": "data:image/png;base64,AAA",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "proof_submitted"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/loop/test_loop_service.py tests/api/test_tasks_api.py -q`
Expected: FAIL — `submit_proof() got an unexpected keyword argument 'media_uri'` / endpoint ignores `media_uri`.

- [ ] **Step 3: Extend `submit_proof` + schemas + endpoint**

In `backend/app/loop/service.py`, change `submit_proof`'s signature to `*, report: str = "", media_uri: str | None = None, settings: Settings | None = None`. Instantiate `_DEFAULT_SETTINGS = Settings()` at module top (alongside the existing imports); inside the function use `_gate = settings or _DEFAULT_SETTINGS` and gate the stamp on `_gate.vision_enabled`. Updated tail:

```python
    _gate = settings or _DEFAULT_SETTINGS
    proof = Proof(task_id=task.id, profile_id=task.profile_id, content=report, media_uri=media_uri)
    if (
        media_uri is not None
        and task.proof_requirement in (ProofRequirement.PHOTO, ProofRequirement.VIDEO)
        and _gate.vision_enabled
    ):
        proof.verdict = "pending_review"
    session.add(proof)
    task.status = TaskStatus.PROOF_SUBMITTED
    await session.flush()
    return proof
```

(`ProofRequirement` is already imported at the top of `service.py`.)

In `backend/app/schemas/task.py`, add to `ProofIn`:

```python
    media_uri: str | None = None
```

In `backend/app/api/tasks.py` `submit_proof` endpoint, pass it through:

```python
        await loop_svc.submit_proof(session, task_id, report=body.report, media_uri=body.media_uri)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/loop/test_loop_service.py tests/api/test_tasks_api.py -q`
Expected: PASS (all, including the pre-existing honor/timer tests — `media_uri` defaults to None and `vision_enabled` is False under `Settings()`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/loop/service.py backend/app/schemas/task.py backend/app/api/tasks.py backend/tests/loop/test_loop_service.py backend/tests/api/test_tasks_api.py
git commit -m "feat(loop): submit_proof accepts media_uri + conditional pending_review"
```

---

## Task 5: `drain_outbox` profile-scoped

**Files:**
- Modify: `backend/app/memory/service.py` (`drain_outbox`)
- Test: `backend/tests/memory/test_memory_service.py` (append)

**Interfaces:**
- Produces: `drain_outbox(session, store, *, limit=50, profile_id: uuid.UUID | None = None) -> int`. `profile_id=None` preserves the existing global behavior (backward-compatible — `memory/seed` and existing tests unaffected). Non-None restricts the SELECT to that profile.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/memory/test_memory_service.py`:

```python
async def test_drain_scoped_to_profile_only_drains_that_profile(session):
    p1 = await _profile(session)
    p2 = await _profile(session)
    for p, name in ((p1, "p1-ep"), (p2, "p2-ep")):
        await mem_svc.enqueue_episode(
            session, p.id, name=name, body="x", source="text",
            source_description="t", reference_time=datetime.now(timezone.utc),
        )
    await session.commit()

    store = FakeMemoryStore()
    pushed = await mem_svc.drain_outbox(session, store, profile_id=p1.id)
    await session.commit()

    assert pushed == 1
    assert [e.group_id for e in store.episodes] == [str(p1.id)]
    # p2's episode stays pending
    rows = (await session.execute(select(MemoryEpisode).where(MemoryEpisode.profile_id == p2.id))).scalars().all()
    assert len(rows) == 1 and rows[0].status == "pending"


async def test_drain_global_when_profile_id_none(session):
    p1 = await _profile(session)
    p2 = await _profile(session)
    for p in (p1, p2):
        await mem_svc.enqueue_episode(
            session, p.id, name="ep", body="x", source="text",
            source_description="t", reference_time=datetime.now(timezone.utc),
        )
    await session.commit()

    store = FakeMemoryStore()
    pushed = await mem_svc.drain_outbox(session, store)  # default: global
    await session.commit()
    assert pushed == 2  # backward-compatible
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/memory/test_memory_service.py -q`
Expected: FAIL — `drain_outbox() got an unexpected keyword argument 'profile_id'`.

- [ ] **Step 3: Add the `profile_id` filter**

In `backend/app/memory/service.py` `drain_outbox`, add the parameter and a conditional WHERE clause:

```python
async def drain_outbox(
    session: AsyncSession, store: MemoryStore, *,
    limit: int = 50, profile_id: uuid.UUID | None = None,
) -> int:
    ...
    stmt = select(MemoryEpisode).where(MemoryEpisode.status == "pending")
    if profile_id is not None:
        stmt = stmt.where(MemoryEpisode.profile_id == profile_id)
    stmt = stmt.order_by(MemoryEpisode.created_at).limit(limit)
    pending = (await session.execute(stmt)).scalars().all()
```

(`uuid` is already imported.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/memory/test_memory_service.py -q`
Expected: PASS (all, including the pre-existing global-drain tests — they call without `profile_id`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/memory/service.py backend/tests/memory/test_memory_service.py
git commit -m "feat(memory): profile-scoped drain_outbox"
```

---

## Task 6: `settle_backlog` service

**Files:**
- Create: `backend/app/backlog/__init__.py`, `backend/app/backlog/service.py`
- Create: `backend/tests/backlog/__init__.py`, `backend/tests/backlog/test_settle.py`
- Test: `backend/tests/backlog/test_settle.py`

**Interfaces:**
- Produces: `SettlementSummary` (dataclass: `judged, passed, failed, re_proven, skipped, errored, memory_drained: int`).
- Produces: `async def settle_backlog(session, profile_id, *, provider, settings, now=None) -> SettlementSummary`.
- Consumes: `verification.verify_media` (Task 3), `loop_svc.apply_task_outcome` + `loop_svc.apply_terminal_discipline` (existing), `mem_svc.drain_outbox` (Task 5), `MemoryStore` via `build_memory_store(settings)`, `Proof`/`Task` models (Task 1), `TaskStatus`/`ProofRequirement`.

Logic (from spec §4):
1. Build the memory store, `drain_outbox(session, store, profile_id=profile_id)` → `memory_drained`.
2. Per-task dedup: `SELECT DISTINCT ON (task_id) proof.* FROM proof WHERE verdict = 'pending_review' AND profile_id = ? ORDER BY task_id, created_at DESC`. Stamp every OTHER `pending_review` proof for those same tasks `verdict = 'superseded'`.
3. For each latest proof: load its `task`; call `verify_media(task, media_uri=proof.media_uri, provider=provider, settings=settings)`.
   - `pass`/`fail` → set `proof.verdict`/`confidence`/`reasoning`/`issues`; set `task.status = VERIFIED_PASS|VERIFIED_FAIL`; `await loop_svc.apply_task_outcome(session, task)`; `await loop_svc.apply_terminal_discipline(session, task)`.
   - `re_proof` → set `proof.verdict = "re_proof"`; task stays `proof_submitted`.
   - `pending_review` return (misconfig branch) → `skipped += 1`; `logging.getLogger("app.backlog").warning(...)` once per settle naming the profile; proof stays `pending_review`.
   - transient exception from `provider.chat` → `errored += 1`; proof stays `pending_review`; swallow the exception.
   - Enqueue a memory episode per judged (pass/fail/re_proof) proof.
4. Flush; caller commits.

- [ ] **Step 1: Create the test package marker**

Create `backend/tests/backlog/__init__.py` (empty file).

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/backlog/test_settle.py`. Helpers mirror `tests/loop/test_loop_service.py` (`_profile`, assign + start + submit-media). Use `MockLLMProvider(supports_vision=True, scripted=[...])` for the judge, `Settings(vision_model="qwen2.5-vl")`, and `FakeMemoryStore` from `tests/memory/fakes.py`. Cases:

```python
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from app.config import Settings
from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.loop import Proof
from app.db.models.memory import MemoryEpisode
from app.economy import service as econ_svc
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.loop import service as loop_svc
from app.backlog import service as backlog_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from tests.memory.fakes import FakeMemoryStore


VISION_SETTINGS = Settings(vision_model="qwen2.5-vl")


async def _profile(session):
    p = await profile_svc.create_profile(session, ProfileCreate(is_adult=True, consent_acknowledged=True))
    await session.flush()
    return p


async def _media_proof_pending_review(session, p, *, description="photo task"):
    task = await loop_svc.assign_task(
        session, p.id, description=description, proof_requirement=ProofRequirement.PHOTO,
        merit_reward=10,
    )
    await session.flush()
    await loop_svc.start_task(session, task.id)
    await session.flush()
    await loop_svc.submit_proof(
        session, task.id, media_uri="data:image/png;base64,AAA", settings=VISION_SETTINGS,
    )
    await session.flush()
    return task


async def test_settle_judges_pass_and_applies_merit(session):
    p = await _profile(session)
    task = await _media_proof_pending_review(session, p)
    await session.commit()

    provider = MockLLMProvider(supports_vision=True, scripted=[ChatResult(
        content='{"verdict": "pass", "confidence": 90, "reasoning": "visible", "issues": []}'
    )])
    summary = await backlog_svc.settle_backlog(
        session, p.id, provider=provider, settings=VISION_SETTINGS,
    )
    await session.commit()

    assert summary.passed == 1 and summary.judged == 1
    assert (await econ_svc.get_economy(session, p.id)).merit == 10
    refreshed = await session.get(type(task), task.id)
    assert refreshed.status is TaskStatus.VERIFIED_PASS


async def test_settle_judges_fail_issues_discipline(session):
    p = await _profile(session)
    task = await _media_proof_pending_review(session, p)
    await session.commit()

    provider = MockLLMProvider(supports_vision=True, scripted=[ChatResult(
        content='{"verdict": "fail", "confidence": 20, "reasoning": "absent", "issues": ["no subject"]}'
    )])
    summary = await backlog_svc.settle_backlog(session, p.id, provider=provider, settings=VISION_SETTINGS)
    await session.commit()

    assert summary.failed == 1
    refreshed = await session.get(type(task), task.id)
    assert refreshed.status is TaskStatus.VERIFIED_FAIL
    assert (await econ_svc.get_economy(session, p.id)).debt > 0  # discipline issued


async def test_settle_reproof_leaves_task_proof_submitted(session):
    p = await _profile(session)
    task = await _media_proof_pending_review(session, p)
    await session.commit()

    provider = MockLLMProvider(supports_vision=True, scripted=[ChatResult(
        content='{"verdict": "re_proof", "confidence": 40, "reasoning": "unclear", "issues": ["dark"]}'
    )])
    summary = await backlog_svc.settle_backlog(session, p.id, provider=provider, settings=VISION_SETTINGS)
    await session.commit()

    assert summary.re_proven == 1
    refreshed = await session.get(type(task), task.id)
    assert refreshed.status is TaskStatus.PROOF_SUBMITTED


async def test_settle_dedups_duplicate_pending_review_proofs_per_task(session):
    p = await _profile(session)
    task = await _media_proof_pending_review(session, p)  # first pending_review proof
    await session.flush()
    # second, newer pending_review proof for the SAME task
    await loop_svc.submit_proof(
        session, task.id, media_uri="data:image/png;base64,BBB", settings=VISION_SETTINGS,
    )
    await session.commit()

    provider = MockLLMProvider(supports_vision=True, scripted=[
        ChatResult(content='{"verdict": "pass", "confidence": 90, "reasoning": "ok", "issues": []}'),
    ])
    summary = await backlog_svc.settle_backlog(session, p.id, provider=provider, settings=VISION_SETTINGS)
    await session.commit()

    assert summary.judged == 1  # only the latest judged
    assert summary.passed == 1
    proofs = (await session.execute(select(Proof).where(Proof.task_id == task.id))).scalars().all()
    verdicts = sorted(pr.verdict for pr in proofs)
    assert verdicts == ["pass", "superseded"]  # older one superseded, not double-judged
    assert (await econ_svc.get_economy(session, p.id)).merit == 10  # not 20


async def test_settle_skips_and_logs_when_provider_lacks_vision(caplog, session):
    p = await _profile(session)
    await _media_proof_pending_review(session, p)
    await session.commit()

    provider = MockLLMProvider(supports_vision=False)  # permanent misconfig
    with caplog.at_level(logging.WARNING, logger="app.backlog"):
        summary = await backlog_svc.settle_backlog(
            session, p.id, provider=provider, settings=VISION_SETTINGS,
        )
    await session.commit()

    assert summary.skipped == 1 and summary.judged == 0
    assert any("vision" in r.message.lower() for r in caplog.records)


async def test_settle_counts_errored_on_transient_provider_exception_and_leaves_pending(session):
    class _BoomProvider:
        supports_vision = True
        async def chat(self, messages, *, model=None, tools=None):
            raise RuntimeError("vision endpoint down")

    p = await _profile(session)
    task = await _media_proof_pending_review(session, p)
    await session.commit()

    summary = await backlog_svc.settle_backlog(
        session, p.id, provider=_BoomProvider(), settings=VISION_SETTINGS,
    )
    await session.commit()

    assert summary.errored == 1 and summary.judged == 0
    refreshed = await session.get(type(task), task.id)
    assert refreshed.status is TaskStatus.PROOF_SUBMITTED  # untouched, retriable
    proof = (await session.execute(select(Proof).where(Proof.task_id == task.id).order_by(Proof.created_at.desc()))).scalars().first()
    assert proof.verdict == "pending_review"


async def test_settle_drains_memory_for_this_profile_only(session):
    from app.memory import service as mem_svc

    p = await _profile(session)
    other = await _profile(session)
    # queue one episode for p and one for `other`
    await mem_svc.enqueue_episode(session, p.id, name="p-ep", body="x", source="text",
                                  source_description="t", reference_time=datetime.now(timezone.utc))
    await mem_svc.enqueue_episode(session, other.id, name="other-ep", body="x", source="text",
                                  source_description="t", reference_time=datetime.now(timezone.utc))
    await session.commit()

    provider = MockLLMProvider(supports_vision=True)
    summary = await backlog_svc.settle_backlog(session, p.id, provider=provider, settings=VISION_SETTINGS)
    await session.commit()

    assert summary.memory_drained == 1  # only p's episode
    other_rows = (await session.execute(select(MemoryEpisode).where(MemoryEpisode.profile_id == other.id))).scalars().all()
    assert len(other_rows) == 1 and other_rows[0].status == "pending"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/backlog/test_settle.py -q`
Expected: FAIL — `ModuleNotFoundError: app.backlog.service` / `settle_backlog` undefined.

- [ ] **Step 4: Implement `settle_backlog`**

Create `backend/app/backlog/__init__.py` (empty).

Create `backend/app/backlog/service.py`:

```python
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.enums import TaskStatus
from app.db.models.loop import Proof
from app.llm.provider import LLMProvider
from app.loop import service as loop_svc
from app.loop import verification
from app.memory import service as mem_svc
from app.memory.store import build_memory_store

_log = logging.getLogger("app.backlog")


@dataclass
class SettlementSummary:
    judged: int = 0
    passed: int = 0
    failed: int = 0
    re_proven: int = 0
    skipped: int = 0
    errored: int = 0
    memory_drained: int = 0


async def settle_backlog(
    session: AsyncSession, profile_id: uuid.UUID, *,
    provider: LLMProvider, settings: Settings, now: datetime | None = None,
) -> SettlementSummary:
    ...
```

Body (implement per the Logic block above):
- `now = now or datetime.now(timezone.utc)`
- `store = build_memory_store(settings)`; `drained = await mem_svc.drain_outbox(session, store, profile_id=profile_id)`; `summary.memory_drained = drained`.
- Dedup query: use `select(Proof).distinct(Proof.task_id).where(Proof.verdict == "pending_review", Proof.profile_id == profile_id).order_by(Proof.task_id, Proof.created_at.desc())` (SQLAlchemy's `.distinct(*columns)` maps to `DISTINCT ON`). Capture the judged set's `(task_id, proof_id)` pairs.
- Mark superseded: `UPDATE proof SET verdict = 'superseded' WHERE verdict = 'pending_review' AND profile_id = ? AND id NOT IN (<judged ids>)` (skip the UPDATE if the judged set is empty). Execute via `session.execute(text(...))` or a bulk ORM update; flush.
- For each judged proof: load `task = await session.get(Task, proof.task_id)`; `try: result = await verification.verify_media(task, media_uri=proof.media_uri, provider=provider, settings=settings) except Exception: summary.errored += 1; continue`. Branch on `result.verdict`:
  - `pass`/`fail`: persist `proof.verdict/confidence/reasoning/issues`; `task.status = TaskStatus.VERIFIED_PASS if pass else VERIFIED_FAIL`; `await loop_svc.apply_task_outcome(session, task)`; `await loop_svc.apply_terminal_discipline(session, task)`; bump `passed`/`failed`; `judged += 1`.
  - `re_proof`: persist `proof.verdict = "re_proof"`; `re_proven += 1`; `judged += 1`.
  - `pending_review`: `skipped += 1`; `_log.warning("profile %s: %d media proof(s) skipped — vision provider lacks vision support", profile_id, <count-or-1>)` (once is fine per call); proof untouched.
  - Enqueue a memory episode for pass/fail/re_proof (not for skipped/errored): `await mem_svc.enqueue_episode(session, profile_id, name="proof judged", body=f"Proof for '{task.description}' judged: {result.verdict}.", source="text", source_description="backlog", reference_time=now)`.
- `await session.flush()`; `return summary`.

(Imports: `Task` from `app.db.models.task`, `text` from `sqlalchemy` if you use a raw UPDATE. Pick whichever approach you prefer for the supersede — both are unambiguous given the test.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/backlog/test_settle.py -q`
Expected: PASS (all seven cases).

- [ ] **Step 6: Commit**

```bash
git add backend/app/backlog/__init__.py backend/app/backlog/service.py backend/tests/backlog/__init__.py backend/tests/backlog/test_settle.py
git commit -m "feat(backlog): settle_backlog service (vision judge + memory drain)"
```

---

## Task 7: `punitive` flag plumbing in discipline + task schemas

**Files:**
- Modify: `backend/app/discipline/service.py` (`issue_punishment`), `backend/app/schemas/task.py` (`TaskCreate`, `TaskOut`), `backend/app/loop/service.py` (`assign_task` — accept + persist `punitive`), `backend/app/api/tasks.py` (assign endpoint — pass `body.punitive` through)
- Test: `backend/tests/discipline/test_service.py` (extend `test_issue_penance_task_creates_linked_task`), `backend/tests/api/test_tasks_api.py` (assert `TaskOut.punitive`)

**Interfaces:**
- Produces: `issue_punishment` sets `punitive=True` on the penance `Task` it creates. `TaskCreate.punitive: bool = False` (additive, WIRED through `assign_task(punitive=...)` and the assign endpoint — an accepted-but-ignored field would be a dead contract). `TaskOut.punitive: bool` (additive, `from_attributes` populates it).

- [ ] **Step 1: Write the failing tests**

In `backend/tests/discipline/test_service.py`, extend `test_issue_penance_task_creates_linked_task` — add this assertion at the end:

```python
    assert task.punitive is True
```

Append to `backend/tests/api/test_tasks_api.py`:

```python
async def test_task_out_carries_punitive_flag(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/tasks", json={
        "description": "ordinary", "proof_requirement": "honor",
    })
    assert r.status_code == 201
    assert r.json()["punitive"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/discipline/test_service.py tests/api/test_tasks_api.py -q`
Expected: FAIL — `task.punitive is True` (currently False) / `KeyError: 'punitive'` in the API response.

- [ ] **Step 3: Plumb the flag**

In `backend/app/discipline/service.py` `issue_punishment`, in the `PENANCE_TASK` branch, set `punitive=True` on the `Task`:

```python
        task = Task(
            profile_id=profile_id,
            description=reason or "Serve your penance.",
            proof_requirement=ProofRequirement.HONOR,
            status=TaskStatus.ASSIGNED,
            punitive=True,
        )
```

In `backend/app/schemas/task.py`, add to `TaskCreate`:

```python
    punitive: bool = False
```

and to `TaskOut` (anywhere among the int fields):

```python
    punitive: bool
```

(`from_attributes=True` is already set on `TaskOut`, so `TaskOut.model_validate(task)` populates it from the column.)

In `backend/app/loop/service.py` `assign_task`, add keyword-only `punitive: bool = False` and pass `punitive=punitive` to the `Task(...)` constructor. In `backend/app/api/tasks.py`'s assign endpoint, pass `punitive=body.punitive` to `loop_svc.assign_task`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/discipline/test_service.py tests/api/test_tasks_api.py -q`
Expected: PASS (all, including the pre-existing penance-settle tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/discipline/service.py backend/app/schemas/task.py backend/app/loop/service.py backend/app/api/tasks.py backend/tests/discipline/test_service.py backend/tests/api/test_tasks_api.py
git commit -m "feat: punitive flag on penance tasks + task schemas"
```

---

## Task 8: `POST /profile/{id}/backlog/settle` endpoint

**Files:**
- Create: `backend/app/api/backlog.py`, `backend/app/schemas/backlog.py`
- Modify: `backend/app/main.py` (mount the router)
- Test: `backend/tests/api/test_backlog_api.py`

**Interfaces:**
- Produces: `POST /profile/{profile_id}/backlog/settle` → `SettlementOut`. Online-gated: 503 `"The Mistress is away — nothing to settle."` when `not await avail_svc.is_online(session)`. Builds the provider via `build_provider(_settings)`, calls `settle_backlog`, commits, returns `SettlementOut.model_validate(summary)`.
- Consumes: `avail_svc.is_online` (existing), `build_provider` (existing), `settle_backlog` (Task 6).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_backlog_api.py` (mirror the `test_tasks_api.py` client fixture + `_new_profile`):

```python
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.backlog import get_provider
from app.availability import service as avail_svc
from app.db.models.availability import LlmHeartbeat
from app.db.session import get_session
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.main import app


@pytest_asyncio.fixture
async def client(session):
    app.dependency_overrides[get_session] = lambda: session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _new_profile(client) -> str:
    return (await client.post("/onboarding/profile", json={
        "is_adult": True, "consent_acknowledged": True,
    })).json()["id"]


async def _force_online(session):
    from datetime import datetime, timezone
    session.add(LlmHeartbeat(last_seen_at=datetime.now(timezone.utc)))
    await session.flush()


async def test_settle_returns_503_when_offline(client, session):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/backlog/settle")
    assert r.status_code == 503
    assert "away" in r.json()["detail"].lower()


async def test_settle_judges_pending_review_proof_when_online(client, session):
    from app.db.models.loop import Proof
    from sqlalchemy import select

    pid = await _new_profile(client)
    # Stage a media proof. Under default Settings (no vision) submit_proof leaves
    # verdict 'pending'; the endpoint serves the vision-enabled path, so flip the
    # row to 'pending_review' to represent a queued-for-review proof:
    tid = (await client.post(f"/profile/{pid}/tasks", json={
        "description": "photo task", "proof_requirement": "photo",
    })).json()["id"]
    await client.post(f"/tasks/{tid}/start")
    await client.post(f"/tasks/{tid}/proof", json={"media_uri": "data:image/png;base64,AAA"})
    proof = (await session.execute(
        select(Proof).where(Proof.task_id == tid).order_by(Proof.created_at.desc())
    )).scalars().first()
    proof.verdict = "pending_review"
    await session.flush()

    await _force_online(session)
    app.dependency_overrides[get_provider] = lambda: MockLLMProvider(
        supports_vision=True, scripted=[ChatResult(
            content='{"verdict": "pass", "confidence": 90, "reasoning": "ok", "issues": []}',
        )]
    )
    try:
        r = await client.post(f"/profile/{pid}/backlog/settle")
    finally:
        app.dependency_overrides.pop(get_provider, None)
    assert r.status_code == 200
    body = r.json()
    assert body["judged"] == 1 and body["passed"] == 1
```

(The test stages a `pending_review` row directly because the endpoint serves the vision-enabled path; under the default `Settings()` the proof wouldn't queue. This keeps the API test independent of `Settings` env tweaks.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/api/test_backlog_api.py -q`
Expected: FAIL — `404` (route not mounted) / `ModuleNotFoundError: app.api.backlog`.

- [ ] **Step 3: Create the schema, endpoint, and mount**

Create `backend/app/schemas/backlog.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SettlementOut(BaseModel):
    judged: int
    passed: int
    failed: int
    re_proven: int
    skipped: int
    errored: int
    memory_drained: int

    model_config = ConfigDict(from_attributes=True)
```

Create `backend/app/api/backlog.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability import service as avail_svc
from app.backlog import service as backlog_svc
from app.config import Settings
from app.db.session import get_session
from app.llm.factory import build_provider
from app.llm.provider import LLMProvider
from app.schemas.backlog import SettlementOut

router = APIRouter(tags=["backlog"])
_settings = Settings()


def get_provider() -> LLMProvider:
    return build_provider(_settings)


@router.post("/profile/{profile_id}/backlog/settle", response_model=SettlementOut)
async def settle(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    provider: LLMProvider = Depends(get_provider),
) -> SettlementOut:
    if not await avail_svc.is_online(session):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The Mistress is away — nothing to settle.",
        )
    summary = await backlog_svc.settle_backlog(
        session, profile_id, provider=provider, settings=_settings,
    )
    await session.commit()
    return SettlementOut.model_validate(summary)
```

In `backend/app/main.py`, add the import alongside the other router imports and mount it:

```python
from app.api.backlog import router as backlog_router
...
app.include_router(backlog_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONHOME= PYTHONPATH= uv run python -m pytest tests/api/test_backlog_api.py -q`
Expected: PASS (both cases).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/backlog.py backend/app/schemas/backlog.py backend/app/main.py backend/tests/api/test_backlog_api.py
git commit -m "feat(api): POST /profile/{id}/backlog/settle (online-gated)"
```

---

## Task 9: Regenerate OpenAPI types (contract hygiene)

**Files:**
- Modify: `frontend/openapi.json`, `frontend/src/lib/types/api.ts` (generated; not imported in `src/`)

This is a contract-resync, not frontend surfacing (deferred to Offline-6b per the spec's non-goals). Mirrors M5c Task 10.

- [ ] **Step 1: Ensure the backend imports cleanly**

Run from `backend/`: `PYTHONHOME= PYTHONPATH= uv run python -c "from app.main import app; print(len(app.openapi()['paths']))"`
Expected: prints a path count greater than before (the new `/profile/{profile_id}/backlog/settle` path is registered); no import error.

- [ ] **Step 2: Regenerate**

Run from `frontend/`: `"C:\Program Files\nodejs\npm.cmd" run gen:api`
Expected: `wrote openapi.json` then openapi-typescript writes `src/lib/types/api.ts`.

- [ ] **Step 3: Sanity-check the diff**

Run: `git diff --stat frontend/openapi.json frontend/src/lib/types/api.ts`
Expected: the new `/profile/{profile_id}/backlog/settle` path, `media_uri` on `ProofIn`, `punitive` on `TaskOut`/`TaskCreate`, and the `SettlementOut` schema appear. (Pre-existing drift collapses into this commit — intended resync; the file is imported nowhere in `src/`.)

- [ ] **Step 4: Verify the frontend still type-checks**

Run from `frontend/`: `"C:\Program Files\nodejs\npm.cmd" run check`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/openapi.json frontend/src/lib/types/api.ts
git commit -m "chore(fe): regenerate OpenAPI types (Offline-6 resync)"
```

---

## Final verification (whole branch)

- [ ] Backend suite: from `backend/`, `PYTHONHOME= PYTHONPATH= uv run python -m pytest -q` (the pre-existing `tests/db/test_migration.py` subprocess test fails on this Windows box only — passes in CI; do not debug locally).
- [ ] Lint: from `backend/`, `PYTHONHOME= PYTHONPATH= uv run python -m ruff check .`
- [ ] Frontend suite: from `frontend/`, `"C:\Program Files\nodejs\npm.cmd" run test`
- [ ] Type-check: from `frontend/`, `"C:\Program Files\nodejs\npm.cmd" run check`
- [ ] Open PR; confirm CI green before merge.

---

## Self-review notes

- **Spec coverage:** §B5 media-proof queueing → T1 (column) + T3 (judge/routing) + T4 (submit) + T6 (settle) + T8 (endpoint); §B5 memory-ingest-when-online → T5 (scoped drain) + T6 (settle drains) + T8 (online gate); §B10 `punitive` flag → T1 (column+backfill) + T7 (plumbing); §B2 "ingests queued memory, judges queued proof" coupling → T6 step 1; §B7 atomic-single-outcome → T6 dedup/superseded; flagged-call #1 (no-vision auto-pass unchanged) → T3 + T4 + RF#1; flagged-call #4 (no retry columns) → T6 errored-leaves-pending. ✓
- **Builder-check resolutions folded in:** dup-proof dedup (T6), scoped drain (T5), punitive backfill (T1), skipped-vs-errored split (T6). ✓
- **Out of scope (unchanged):** audience lifecycle (§B8 — eligibility/price/open/close/standing-orders/regen); BATCH_WINDOW/LIVE_AUDIENCE presence states; frontend surfacing of pending-review (→ Offline-6b); per-proof retry columns; auto-trigger/scheduler. ✓
- **Type consistency:** `settle_backlog(session, profile_id, *, provider, settings, now=None)` matches across T6/T8; `SettlementSummary` ↔ `SettlementOut` share field names/order; `verify_media(task, *, media_uri, provider, settings)` matches across T3/T6; `submit_proof(..., media_uri=None)` matches across T4; `drain_outbox(..., profile_id=None)` matches across T5/T6. ✓
- **Proportion:** nine tasks, each a single test-cycle + commit; bodies given only where the signature+test don't determine them (the dedup query, the supersede UPDATE, the `_VISION_SYSTEM` prompt prose). ✓
