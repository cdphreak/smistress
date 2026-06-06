# Milestone 5 — Memory (Graphiti / FalkorDB) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the evolving-memory tier (spec §3) — a `MemoryStore` seam with a real Graphiti/FalkorDB adapter and a no-op fallback, a **transactional outbox** so episode writes are durable and retried, retrieval wired into the persona prompt's M4 memory slot, and an onboarding seed episode — all degrading gracefully to Postgres-only when Graphiti/FalkorDB is unavailable.

**Architecture:** A `MemoryStore` Protocol (`app/memory/store.py`) with `NullMemoryStore` (no-op) and `GraphitiMemoryStore` (wraps `graphiti-core`, OpenAI-compatible LLM + embedder via the same provider config, lazily imported). Episode writes go through a durable Postgres **outbox** (`memory_episode`): `enqueue_episode` inserts a row in the caller's transaction; `drain_outbox` pushes pending rows to the store and retries failures. Retrieval (`retrieve_memory`) degrades to an empty string on any store error, so a turn never breaks. `graphiti_enabled` defaults **off** → the app, tests, and CI run on `NullMemoryStore` with no FalkorDB/LLM needed; the real adapter has a gated integration test.

**Tech Stack:** `graphiti-core[falkordb]` (FalkorDB driver + `OpenAIGenericClient`/`OpenAIEmbedder` for local/custom base_urls), SQLAlchemy 2.0 async, Alembic (one new table), the existing `LLMProvider`/Settings config, pytest with an in-memory `FakeMemoryStore`.

---

## Context

M4 merged: the persona engine compiles a system prompt with a **memory seam** — `compile_system_prompt(..., memory: str | None)` renders a `## MEMORY` section (`(none yet)` when empty), and `app/persona/service.py::generate_reply(session, profile_id, conversation, provider, *, memory=None)` is the chat-turn seam. M5 fills that slot. Spec **§3** defines two memory tiers: Tier 1 (Postgres authoritative — already built and injected verbatim) and **Tier 2 (Graphiti temporal KG on FalkorDB)** — episodes ingested, entities/time-valid relationships extracted, queried for continuity. Graphiti's LLM + embedder are OpenAI-compatible and ride the same swappable provider config. **Degradation:** if Graphiti/FalkorDB is down, retrieval falls back to Postgres-only and **writes queue + retry**.

### Verified `graphiti-core` API (researched; the adapter is isolated so drift touches one file)
```python
from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.nodes import EpisodeType
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient   # local/custom base_url
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient

driver = FalkorDriver(host="localhost", port="6379", username=None, password=None)
graphiti = Graphiti(graph_driver=driver, llm_client=..., embedder=..., cross_encoder=...)
await graphiti.build_indices_and_constraints()      # once
await graphiti.add_episode(name=..., episode_body=..., source=EpisodeType.text,
                           source_description=..., reference_time=<tz-aware dt>, group_id=<str>)
results = await graphiti.search(query=..., group_ids=[<str>], num_results=...)  # -> edges with .fact
```
**`group_id` is the per-tenant scope** → use `str(profile_id)`.

### Decisions locked (from M5 planning)
- **Transactional outbox** for durable writes + retry (a `memory_episode` Postgres table; needs one migration).
- **Scope:** M5 builds the mechanism + retrieval wiring + **one onboarding seed episode** (spec §4). Task/proof/reaction episodes are wired in **M6**, where those events are produced.
- **`graphiti_enabled` defaults False** → `NullMemoryStore`; CI/local need no FalkorDB or LLM. Real adapter import is **lazy** (inside `GraphitiMemoryStore`) so the heavy dep never loads on the Null path.

### Patterns to follow
- Services flush; **endpoints commit**; reads don't commit (M3/M4). `enqueue_episode` only flushes — the caller's transaction owns the commit, making the outbox write atomic with the state change.
- Async safety: explicit `select(...)`; no lazy relationship IO.
- Status fields elsewhere use PG enums, but to keep this migration simple the outbox `status` is a plain `String` with documented values `"pending"`/`"done"` (no new PG enum).
- Local dev caveat: clear `PYTHONHOME`/`PYTHONPATH` before `uv` (see `smistress-dev-environment`). Run: `$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; $uv=(Get-Command uv).Source; $bk="C:\Users\phrea\OneDrive\claude\smistress\backend"; & $uv --directory $bk run pytest -q`. Postgres up via `docker compose up -d`. CI unaffected.

## File Structure (all under `backend/`)
New:
- `app/memory/__init__.py` (empty)
- `app/memory/store.py` — `MemoryStore` Protocol, `NullMemoryStore`, `GraphitiMemoryStore` (lazy graphiti import), `build_memory_store(settings)`, `retrieve_memory(store, group_id, query)` (degrading). No imports from persona/profile (avoids cycles).
- `app/memory/service.py` — `enqueue_episode`, `drain_outbox`, `seed_profile_episode` (imports `profile`/`persona` services for the summary). DB-backed.
- `app/db/models/memory.py` — `MemoryEpisode` outbox model.
- `app/api/memory.py` — `POST /profile/{id}/memory/seed`.
- `alembic/versions/<rev>_add_memory_episode_outbox.py` — generated migration.
- Tests: `tests/memory/__init__.py`, `tests/memory/fakes.py` (`FakeMemoryStore`), `tests/memory/test_store.py`, `tests/memory/test_memory_service.py`, `tests/memory/test_seed.py`, `tests/memory/test_graphiti_store_integration.py` (gated), `tests/persona/test_reply_with_memory.py`, `tests/api/test_memory_api.py`.

Modify:
- `app/config.py` — add `graphiti_enabled`, `embedding_model`, `embedding_dim`, `falkordb_host`, `falkordb_port`.
- `app/db/models/__init__.py` — register `MemoryEpisode`.
- `app/persona/service.py` — `generate_reply` accepts an optional `store` and fills the memory slot.
- `app/main.py` — mount the memory router.
- `pyproject.toml` — add `graphiti-core[falkordb]`.

---

## Task 1: Dependency + config

**Files:**
- Modify: `backend/pyproject.toml`, `backend/app/config.py`
- Test: `backend/tests/test_config_memory.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_config_memory.py`:

```python
from app.config import Settings


def test_memory_settings_defaults():
    s = Settings()
    assert s.graphiti_enabled is False          # default off -> NullMemoryStore
    assert s.embedding_model                      # has a default
    assert s.embedding_dim > 0
    assert s.falkordb_host
    assert s.falkordb_port > 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_config_memory.py -v`
Expected: FAIL — `AttributeError` (settings don't exist yet).

- [ ] **Step 3a: Add the dependency** to `backend/pyproject.toml` `dependencies` list (after `psycopg[binary]>=3.2`):

```toml
  "graphiti-core[falkordb]>=0.3",
```

- [ ] **Step 3b: Add settings** to `backend/app/config.py` (inside `Settings`, after `falkordb_url`):

```python
    graphiti_enabled: bool = False  # off -> NullMemoryStore; no FalkorDB/LLM needed
    embedding_model: str = "nomic-embed-text"  # local default (Ollama); OpenAI: text-embedding-3-small
    embedding_dim: int = 768  # nomic-embed-text dim; text-embedding-3-small = 1536
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
```

- [ ] **Step 3c: Sync deps**

Run: `uv --directory <backend> sync`
Expected: resolves and installs `graphiti-core` + the FalkorDB extra. If resolution is slow that's normal (it pulls openai/tiktoken/numpy/falkordb). If it fails, STOP and report the resolver error — do not pin random versions.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_config_memory.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/config.py backend/tests/test_config_memory.py
git commit -m "feat: add graphiti-core dep and memory/embedder settings (spec 3)"
```

---

## Task 2: Memory outbox model + migration

**Files:**
- Create: `backend/app/db/models/memory.py`
- Modify: `backend/app/db/models/__init__.py`
- Create (generated): `backend/alembic/versions/<rev>_add_memory_episode_outbox.py`
- Test: `backend/tests/db/test_memory_model.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/db/test_memory_model.py`:

```python
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models.memory import MemoryEpisode
from app.db.models.profile import SubProfile


async def test_memory_episode_defaults(session):
    profile = SubProfile(intensity_ceiling=50)
    session.add(profile)
    await session.flush()
    session.add(
        MemoryEpisode(
            profile_id=profile.id,
            name="seed",
            body="A profile summary.",
            source="text",
            source_description="onboarding",
            reference_time=datetime.now(timezone.utc),
        )
    )
    await session.commit()

    ep = (await session.execute(select(MemoryEpisode))).scalar_one()
    assert ep.status == "pending"      # default
    assert ep.attempts == 0
    assert ep.last_error is None
    assert ep.source == "text"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/db/test_memory_model.py -v`
Expected: FAIL — `ModuleNotFoundError: app.db.models.memory`.

- [ ] **Step 3a: Implement** — `backend/app/db/models/memory.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.profile import SubProfile


class MemoryEpisode(Base):
    """Transactional outbox for Graphiti episodes (spec 3 'writes queue and retry').

    A row is written in the same transaction as the state change it records, then a
    drainer pushes it to the memory store and retries on failure. status: pending|done.
    """

    __tablename__ = "memory_episode"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))
    name: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String, default="text")  # EpisodeType value
    source_description: Mapped[str] = mapped_column(String, default="")
    reference_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String, default="pending")  # pending | done
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    profile: Mapped[SubProfile] = relationship()
```

- [ ] **Step 3b: Register it** — in `backend/app/db/models/__init__.py` add (keep alphabetical-ish with the others):

```python
from app.db.models.memory import MemoryEpisode  # noqa: F401
```

- [ ] **Step 4: Run to verify the model test passes**

Run: `uv run pytest tests/db/test_memory_model.py -v`
Expected: PASS (the `session` fixture builds the schema with `Base.metadata.create_all`, so it sees the new table).

- [ ] **Step 5: Autogenerate the migration**

The test DB must be at head first. From `backend/` (with `SMISTRESS_DATABASE_URL` pointed at the test DB):
```bash
SMISTRESS_DATABASE_URL=postgresql+psycopg://smistress:smistress@localhost:5432/smistress_test uv run alembic upgrade head
SMISTRESS_DATABASE_URL=postgresql+psycopg://smistress:smistress@localhost:5432/smistress_test uv run alembic revision --autogenerate -m "add memory_episode outbox"
```
(PowerShell: set `$env:SMISTRESS_DATABASE_URL=...` first, then run each `& $uv --directory $bk run alembic ...`.)

- [ ] **Step 6: Inspect the generated migration**

Open `backend/alembic/versions/<rev>_add_memory_episode_outbox.py`. Confirm `upgrade()` contains **only** `op.create_table('memory_episode', ...)` (all columns above, FK to `sub_profile.id`, PK on `id`) and `downgrade()` is `op.drop_table('memory_episode')`. There are **no enum types** (status is a String), so no `DROP TYPE` is needed. If `upgrade()` contains anything else (e.g., spurious drops because the test DB drifted), drop the stray tables and re-run Step 5. The `down_revision` must be the M2 initial-schema revision id.

- [ ] **Step 7: Round-trip the migration**

The existing `tests/db/test_migration.py` clears the schema then runs `upgrade head` → `downgrade base` → `upgrade head`. Run it to confirm the new migration is reversible end-to-end:
Run: `uv run pytest tests/db/test_migration.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/db/models/memory.py backend/app/db/models/__init__.py \
        backend/alembic/versions/ backend/tests/db/test_memory_model.py
git commit -m "feat: add memory_episode outbox table + migration"
```

---

## Task 3: MemoryStore protocol, NullMemoryStore, factory, retrieve degradation

**Files:**
- Create: `backend/app/memory/__init__.py` (empty), `backend/app/memory/store.py`
- Create: `backend/tests/memory/__init__.py` (empty), `backend/tests/memory/fakes.py`, `backend/tests/memory/test_store.py`

- [ ] **Step 1: Write the test fakes** — `backend/tests/memory/fakes.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RecordedEpisode:
    group_id: str
    name: str
    body: str
    source: str
    source_description: str
    reference_time: datetime


class FakeMemoryStore:
    """In-memory MemoryStore for tests. Optionally raises to simulate FalkorDB down."""

    def __init__(self, *, facts: list[str] | None = None, fail: bool = False) -> None:
        self.episodes: list[RecordedEpisode] = field(default_factory=list).default_factory()
        self._facts = facts or []
        self.fail = fail

    async def add_episode(
        self, *, group_id, name, body, source, source_description, reference_time
    ) -> None:
        if self.fail:
            raise RuntimeError("FalkorDB unavailable")
        self.episodes.append(
            RecordedEpisode(group_id, name, body, source, source_description, reference_time)
        )

    async def retrieve(self, *, group_id, query, num_results=10) -> str:
        if self.fail:
            raise RuntimeError("FalkorDB unavailable")
        return "\n".join(f"- {f}" for f in self._facts)
```

> Note: replace the awkward `field(...)` line above with a plain `self.episodes: list[RecordedEpisode] = []` — write it that way directly.

So Step 1's `__init__` body is actually:
```python
    def __init__(self, *, facts: list[str] | None = None, fail: bool = False) -> None:
        self.episodes: list[RecordedEpisode] = []
        self._facts = facts or []
        self.fail = fail
```

- [ ] **Step 2: Write the failing test** — `backend/tests/memory/test_store.py`:

```python
import pytest

from app.config import Settings
from app.memory.store import NullMemoryStore, build_memory_store, retrieve_memory
from tests.memory.fakes import FakeMemoryStore


def test_factory_returns_null_when_disabled():
    store = build_memory_store(Settings(graphiti_enabled=False))
    assert isinstance(store, NullMemoryStore)


async def test_null_store_is_noop():
    store = NullMemoryStore()
    await store.add_episode(
        group_id="g", name="n", body="b", source="text",
        source_description="d", reference_time=__import__("datetime").datetime.now(),
    )
    assert await store.retrieve(group_id="g", query="q") == ""


async def test_retrieve_memory_returns_facts_block():
    store = FakeMemoryStore(facts=["she prefers morning tasks", "missed Tuesday"])
    block = await retrieve_memory(store, group_id="g", query="patterns?")
    assert "morning tasks" in block
    assert "missed Tuesday" in block


async def test_retrieve_memory_degrades_to_empty_on_error():
    store = FakeMemoryStore(fail=True)
    # a store failure must NEVER break the turn -> empty memory, no exception
    assert await retrieve_memory(store, group_id="g", query="x") == ""
```

- [ ] **Step 3: Implement** — `backend/app/memory/store.py`:

```python
from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.config import Settings

logger = logging.getLogger(__name__)


@runtime_checkable
class MemoryStore(Protocol):
    async def add_episode(
        self,
        *,
        group_id: str,
        name: str,
        body: str,
        source: str,
        source_description: str,
        reference_time: datetime,
    ) -> None: ...

    async def retrieve(self, *, group_id: str, query: str, num_results: int = 10) -> str: ...


class NullMemoryStore:
    """No-op store: used when graphiti is disabled and as the degradation fallback."""

    async def add_episode(self, **_kwargs) -> None:
        return None

    async def retrieve(self, **_kwargs) -> str:
        return ""


def build_memory_store(settings: Settings) -> MemoryStore:
    if not settings.graphiti_enabled:
        return NullMemoryStore()
    from app.memory.graphiti_store import GraphitiMemoryStore  # lazy: heavy import

    return GraphitiMemoryStore(settings)


async def retrieve_memory(store: MemoryStore, *, group_id: str, query: str) -> str:
    """Retrieve a memory block, degrading to '' on any store failure (spec 3)."""
    try:
        return await store.retrieve(group_id=group_id, query=query)
    except Exception:  # noqa: BLE001 - degradation must catch everything
        logger.warning("memory retrieval failed; degrading to no memory", exc_info=True)
        return ""
```

> Note: the real `GraphitiMemoryStore` lands in Task 7 at `app/memory/graphiti_store.py`. Until then `graphiti_enabled=False` (the default) never imports it, so this task's tests pass without it. Do **not** create `graphiti_store.py` yet.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/memory/test_store.py -v`
Expected: PASS (4 tests). Also create empty `backend/app/memory/__init__.py` and `backend/tests/memory/__init__.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/memory/__init__.py backend/app/memory/store.py \
        backend/tests/memory/__init__.py backend/tests/memory/fakes.py backend/tests/memory/test_store.py
git commit -m "feat: add MemoryStore seam (NullMemoryStore, factory, degrading retrieve)"
```

---

## Task 4: Memory service — outbox enqueue + drain (retry)

**Files:**
- Create: `backend/app/memory/service.py`
- Test: `backend/tests/memory/test_memory_service.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/memory/test_memory_service.py`:

```python
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models.memory import MemoryEpisode
from app.memory import service as mem_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from tests.memory.fakes import FakeMemoryStore


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_enqueue_writes_pending_row(session):
    p = await _profile(session)
    await mem_svc.enqueue_episode(
        session, p.id, name="seed", body="hi", source="text",
        source_description="onboarding", reference_time=datetime.now(timezone.utc),
    )
    await session.commit()
    row = (await session.execute(select(MemoryEpisode))).scalar_one()
    assert row.status == "pending"


async def test_drain_pushes_pending_and_marks_done(session):
    p = await _profile(session)
    await mem_svc.enqueue_episode(
        session, p.id, name="seed", body="hi", source="text",
        source_description="onboarding", reference_time=datetime.now(timezone.utc),
    )
    await session.commit()

    store = FakeMemoryStore()
    pushed = await mem_svc.drain_outbox(session, store)
    await session.commit()

    assert pushed == 1
    assert len(store.episodes) == 1
    assert store.episodes[0].group_id == str(p.id)
    row = (await session.execute(select(MemoryEpisode))).scalar_one()
    assert row.status == "done"


async def test_drain_retries_on_failure_keeps_pending(session):
    p = await _profile(session)
    await mem_svc.enqueue_episode(
        session, p.id, name="seed", body="hi", source="text",
        source_description="onboarding", reference_time=datetime.now(timezone.utc),
    )
    await session.commit()

    store = FakeMemoryStore(fail=True)  # FalkorDB down
    pushed = await mem_svc.drain_outbox(session, store)
    await session.commit()

    assert pushed == 0
    row = (await session.execute(select(MemoryEpisode))).scalar_one()
    assert row.status == "pending"      # still queued for retry
    assert row.attempts == 1
    assert row.last_error
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/memory/test_memory_service.py -v`
Expected: FAIL — `ModuleNotFoundError: app.memory.service`.

- [ ] **Step 3: Implement** — `backend/app/memory/service.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.memory import MemoryEpisode
from app.memory.store import MemoryStore


async def enqueue_episode(
    session: AsyncSession,
    profile_id: uuid.UUID,
    *,
    name: str,
    body: str,
    source: str = "text",
    source_description: str = "",
    reference_time: datetime,
) -> MemoryEpisode:
    """Durably queue an episode (transactional outbox). Caller owns the commit."""
    episode = MemoryEpisode(
        profile_id=profile_id,
        name=name,
        body=body,
        source=source,
        source_description=source_description,
        reference_time=reference_time,
    )
    session.add(episode)
    await session.flush()
    return episode


async def drain_outbox(
    session: AsyncSession, store: MemoryStore, *, limit: int = 50
) -> int:
    """Push pending episodes to the store. Returns how many succeeded.

    Failures leave the row 'pending' with an incremented attempt count + error, so
    the next drain retries them (spec 3 'writes queue and retry'). Caller commits.
    """
    pending = (await session.execute(
        select(MemoryEpisode)
        .where(MemoryEpisode.status == "pending")
        .order_by(MemoryEpisode.created_at)
        .limit(limit)
    )).scalars().all()

    pushed = 0
    for ep in pending:
        try:
            await store.add_episode(
                group_id=str(ep.profile_id),
                name=ep.name,
                body=ep.body,
                source=ep.source,
                source_description=ep.source_description,
                reference_time=ep.reference_time,
            )
        except Exception as exc:  # noqa: BLE001 - keep queued for retry
            ep.attempts += 1
            ep.last_error = str(exc)[:500]
            continue
        ep.status = "done"
        pushed += 1
    await session.flush()
    return pushed
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/memory/test_memory_service.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/memory/service.py backend/tests/memory/test_memory_service.py
git commit -m "feat: add memory outbox enqueue + drain with retry (spec 3)"
```

---

## Task 5: Wire memory retrieval into the persona reply path

**Files:**
- Modify: `backend/app/persona/service.py`
- Test: `backend/tests/persona/test_reply_with_memory.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/persona/test_reply_with_memory.py`:

```python
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatMessage, ChatResult
from app.persona import service as persona_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from tests.memory.fakes import FakeMemoryStore


async def test_reply_injects_retrieved_memory_into_prompt(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.commit()

    store = FakeMemoryStore(facts=["she performs best on Monday mornings"])
    provider = MockLLMProvider(scripted=[ChatResult(content="Noted, student.")])
    conversation = [ChatMessage(role="user", content="How am I doing?")]

    result = await persona_svc.generate_reply(
        session, p.id, conversation, provider, store=store
    )
    assert result.content == "Noted, student."
    system_prompt = provider.calls[0][0].content
    assert "Monday mornings" in system_prompt   # retrieved memory reached the prompt


async def test_reply_degrades_when_store_fails(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.commit()

    store = FakeMemoryStore(fail=True)  # FalkorDB down
    provider = MockLLMProvider(scripted=[ChatResult(content="Still here, student.")])
    conversation = [ChatMessage(role="user", content="Hi")]

    # must not raise; memory section becomes "(none yet)"
    result = await persona_svc.generate_reply(
        session, p.id, conversation, provider, store=store
    )
    assert result.content == "Still here, student."
    assert "(none yet)" in provider.calls[0][0].content
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/persona/test_reply_with_memory.py -v`
Expected: FAIL — `generate_reply` has no `store` parameter.

- [ ] **Step 3: Modify `generate_reply`** in `backend/app/persona/service.py`.

Add the import alongside the existing `from app.llm...` imports:
```python
from app.memory.store import MemoryStore, retrieve_memory
```
Replace the existing `generate_reply` with:
```python
async def generate_reply(
    session: AsyncSession,
    profile_id: uuid.UUID,
    conversation: list[ChatMessage],
    provider: LLMProvider,
    *,
    memory: str | None = None,
    store: MemoryStore | None = None,
) -> ChatResult:
    """Compile the persona prompt and get a plain reply (no tools — tool calls are M6).

    If a memory store is provided and no explicit memory text was passed, retrieve a
    memory block keyed on the latest user message (degrading to none on failure).
    """
    if memory is None and store is not None:
        query = next(
            (m.content for m in reversed(conversation) if m.role == "user"), ""
        )
        memory = await retrieve_memory(store, group_id=str(profile_id), query=query)
    system_prompt = await compile_persona_prompt(session, profile_id, memory=memory)
    messages = [ChatMessage(role="system", content=system_prompt), *conversation]
    return await provider.chat(messages)
```

> `retrieve_memory` already degrades to `""`; `compile_system_prompt` renders `""`/None memory as `(none yet)`. No cycle: `persona.service` imports `memory.store` (which imports neither persona nor profile).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/persona/test_reply_with_memory.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/persona/service.py backend/tests/persona/test_reply_with_memory.py
git commit -m "feat: retrieve and inject Graphiti memory into the persona prompt (spec 3/5)"
```

---

## Task 6: Onboarding seed episode + endpoint

**Files:**
- Modify: `backend/app/memory/service.py` (add `seed_profile_episode`)
- Create: `backend/app/api/memory.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/memory/test_seed.py`, `backend/tests/api/test_memory_api.py`

- [ ] **Step 1: Write the failing tests.**

`backend/tests/memory/test_seed.py`:
```python
from sqlalchemy import select

from app.db.enums import KinkRating
from app.db.models.memory import MemoryEpisode
from app.memory import service as mem_svc
from app.schemas.onboarding import KinkItem, ProfileCreate
from app.services import profile as profile_svc


async def test_seed_profile_episode_enqueues_summary(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await profile_svc.replace_kinks(session, p.id, [
        KinkItem(kink="blood", rating=KinkRating.HARD_LIMIT),
    ])
    await session.commit()

    ep = await mem_svc.seed_profile_episode(session, p.id)
    await session.commit()

    assert ep.status == "pending"
    assert ep.source == "text"
    assert "blood" in ep.body            # the summary carries the authoritative state
    row = (await session.execute(select(MemoryEpisode))).scalar_one()
    assert row.id == ep.id
```

`backend/tests/api/test_memory_api.py`:
```python
import pytest
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


async def test_seed_endpoint_queues_episode(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/memory/seed")
    assert r.status_code == 201
    body = r.json()
    assert body["queued"] == 1
    # graphiti disabled by default -> NullMemoryStore -> drained 0 actually pushed
    assert "drained" in body


async def test_seed_endpoint_404(client):
    import uuid
    r = await client.post(f"/profile/{uuid.uuid4()}/memory/seed")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/memory/test_seed.py tests/api/test_memory_api.py -v`
Expected: FAIL — no `seed_profile_episode`; `/memory/seed` 404 (router not mounted).

- [ ] **Step 3a: Add `seed_profile_episode`** to `backend/app/memory/service.py`.

Add imports at the top (with the others):
```python
from datetime import timezone
from app.persona import service as persona_svc
from app.services import profile as profile_svc
```
(Keep the existing `from datetime import datetime` — combine to `from datetime import datetime, timezone`.)

Append the function:
```python
async def seed_profile_episode(
    session: AsyncSession, profile_id: uuid.UUID
) -> MemoryEpisode:
    """Seed the initial Graphiti episode from the assembled profile (spec 4).

    Raises profile_svc.ProfileNotFound if the profile does not exist.
    """
    summary = await persona_svc.build_authoritative_state_block(session, profile_id)
    return await enqueue_episode(
        session,
        profile_id,
        name="onboarding profile",
        body=f"Initial sub profile at onboarding:\n{summary}",
        source="text",
        source_description="onboarding",
        reference_time=datetime.now(timezone.utc),
    )
```

> `build_authoritative_state_block` calls `profile_svc.get_profile` first, so a missing profile raises `ProfileNotFound` before any write. The `profile_svc` import is only needed if you reference it directly; if unused, omit it to keep ruff happy — `persona_svc` is the one actually used. Keep imports minimal: add only `from app.persona import service as persona_svc` and `timezone`.

- [ ] **Step 3b: Implement** — `backend/app/api/memory.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.session import get_session
from app.memory import service as mem_svc
from app.memory.store import build_memory_store
from app.services import profile as profile_svc

router = APIRouter(prefix="/profile", tags=["memory"])

_settings = Settings()


@router.post("/{profile_id}/memory/seed", status_code=status.HTTP_201_CREATED)
async def seed_memory(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await mem_svc.seed_profile_episode(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"profile {profile_id} not found",
        )
    # best-effort drain now; anything not pushed stays queued for a later retry.
    store = build_memory_store(_settings)
    drained = await mem_svc.drain_outbox(session, store)
    await session.commit()
    return {"queued": 1, "drained": drained}
```

- [ ] **Step 3c: Mount the router** in `backend/app/main.py`. Add with the other router imports:
```python
from app.api.memory import router as memory_router
```
and with the other includes:
```python
app.include_router(memory_router)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/memory/test_seed.py tests/api/test_memory_api.py -v`
Expected: PASS. With `graphiti_enabled=False`, the endpoint builds a `NullMemoryStore`; drain pushes the pending row to the no-op store and marks it done → `drained == 1`. (Both assertions in the API test hold: `queued == 1`, `"drained"` present.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/memory/service.py backend/app/api/memory.py backend/app/main.py \
        backend/tests/memory/test_seed.py backend/tests/api/test_memory_api.py
git commit -m "feat: seed onboarding profile episode + POST /profile/{id}/memory/seed (spec 4)"
```

---

## Task 7: GraphitiMemoryStore real adapter (lazy import) + gated integration test

**Files:**
- Create: `backend/app/memory/graphiti_store.py`
- Test: `backend/tests/memory/test_graphiti_store_integration.py`

The adapter is exercised by a **gated** integration test that skips unless `SMISTRESS_GRAPHITI_IT=1` (and FalkorDB + an LLM are reachable). Default CI/local runs skip it; the seam is covered by the fake everywhere else.

- [ ] **Step 1: Write the gated integration test** — `backend/tests/memory/test_graphiti_store_integration.py`:

```python
import os
from datetime import datetime, timezone

import pytest

from app.config import Settings
from app.memory.store import GraphitiMemoryStore

pytestmark = pytest.mark.skipif(
    os.environ.get("SMISTRESS_GRAPHITI_IT") != "1",
    reason="set SMISTRESS_GRAPHITI_IT=1 with FalkorDB + an LLM available to run",
)


async def test_add_then_retrieve_round_trip():
    # Requires a running FalkorDB and a reachable OpenAI-compatible LLM + embedder.
    store = GraphitiMemoryStore(Settings(graphiti_enabled=True))
    gid = "it-" + datetime.now(timezone.utc).isoformat()
    await store.add_episode(
        group_id=gid,
        name="it episode",
        body="The student completed morning stretches on time.",
        source="text",
        source_description="integration test",
        reference_time=datetime.now(timezone.utc),
    )
    block = await store.retrieve(group_id=gid, query="What did the student complete?")
    assert isinstance(block, str)  # content depends on the model; just prove the round-trip
```

- [ ] **Step 2: Run to verify it is collected and skipped**

Run: `uv run pytest tests/memory/test_graphiti_store_integration.py -v`
Expected: 1 skipped (because `SMISTRESS_GRAPHITI_IT` is unset) — and import of `GraphitiMemoryStore` must succeed even when skipped, so the module must import cleanly.

- [ ] **Step 3: Implement** — `backend/app/memory/graphiti_store.py`:

```python
from __future__ import annotations

from datetime import datetime

from app.config import Settings


class GraphitiMemoryStore:
    """Graphiti/FalkorDB adapter (spec 3). Imports graphiti-core lazily so the heavy
    dependency only loads when graphiti is actually enabled."""

    def __init__(self, settings: Settings) -> None:
        from graphiti_core import Graphiti
        from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
        from graphiti_core.driver.falkordb_driver import FalkorDriver
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
        from graphiti_core.nodes import EpisodeType

        self._episode_types = {
            "text": EpisodeType.text,
            "json": EpisodeType.json,
            "message": EpisodeType.message,
        }

        driver = FalkorDriver(
            host=settings.falkordb_host, port=str(settings.falkordb_port)
        )
        llm_config = LLMConfig(
            api_key=settings.llm_api_key,
            model=settings.chat_model,
            small_model=settings.chat_model,
            base_url=settings.llm_base_url,
        )
        llm_client = OpenAIGenericClient(config=llm_config)
        embedder = OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                api_key=settings.llm_api_key,
                embedding_model=settings.embedding_model,
                embedding_dim=settings.embedding_dim,
                base_url=settings.llm_base_url,
            )
        )
        self._graphiti = Graphiti(
            graph_driver=driver,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=OpenAIRerankerClient(client=llm_client, config=llm_config),
        )
        self._indices_ready = False

    async def _ensure_indices(self) -> None:
        if not self._indices_ready:
            await self._graphiti.build_indices_and_constraints()
            self._indices_ready = True

    async def add_episode(
        self,
        *,
        group_id: str,
        name: str,
        body: str,
        source: str,
        source_description: str,
        reference_time: datetime,
    ) -> None:
        await self._ensure_indices()
        await self._graphiti.add_episode(
            name=name,
            episode_body=body,
            source=self._episode_types.get(source, self._episode_types["text"]),
            source_description=source_description,
            reference_time=reference_time,
            group_id=group_id,
        )

    async def retrieve(self, *, group_id: str, query: str, num_results: int = 10) -> str:
        results = await self._graphiti.search(
            query=query, group_ids=[group_id], num_results=num_results
        )
        return "\n".join(f"- {r.fact}" for r in results)
```

- [ ] **Step 4: Verify clean import + skip**

Run: `uv run pytest tests/memory/test_graphiti_store_integration.py -v`
Expected: 1 skipped, no import errors. Then `uv run ruff check .` clean.

> If you have FalkorDB + a local LLM available and want to prove the real path, run:
> `SMISTRESS_GRAPHITI_IT=1 SMISTRESS_GRAPHITI_ENABLED=true uv run pytest tests/memory/test_graphiti_store_integration.py -v`. Not required for the milestone.

- [ ] **Step 5: Commit**

```bash
git add backend/app/memory/graphiti_store.py backend/tests/memory/test_graphiti_store_integration.py
git commit -m "feat: add GraphitiMemoryStore adapter (FalkorDB + OpenAI-compatible clients)"
```

---

## Task 8: Full verification + milestone wrap

**Files:** none (verification only).

- [ ] **Step 1: Infra up (local)** — `docker compose up -d` (Postgres + FalkorDB). CI has only Postgres; the default `graphiti_enabled=False` keeps it on `NullMemoryStore`.

- [ ] **Step 2: Full suite** — `uv run pytest -q`. Expected: all M1–M5 tests pass (the gated Graphiti integration test shows as skipped). The 93 M4 tests plus the new config/model/store/service/seed/persona-memory/api tests.

- [ ] **Step 3: Lint** — `uv run ruff check .`. Expected: clean. Fix unused imports (esp. the `seed_profile_episode` import note) and any E501.

- [ ] **Step 4: Push + confirm CI green**
```bash
git push -u origin feat/m5-memory
```
Watch the run. The CI `backend` job runs `uv sync` (now pulling graphiti-core) + ruff + pytest against the Postgres service; `graphiti_enabled` is unset → `NullMemoryStore`, so no FalkorDB/LLM is needed and the integration test is skipped. Confirm both jobs pass.

- [ ] **Step 5: Open the PR**
```bash
gh pr create --base master --head feat/m5-memory \
  --title "M5: Memory — Graphiti/FalkorDB outbox, retrieval, degradation" \
  --body "Implements spec §3. See docs/superpowers/plans/2026-06-06-core-obedience-loop-m5-memory.md"
```

---

## Verification (end-to-end for Milestone 5)

1. **Infra up:** `docker compose up -d`.
2. **Suite green:** `uv run pytest -q` — config, outbox model + migration round-trip, store seam + degradation, outbox enqueue/drain/retry, persona memory injection, onboarding seed + endpoint; the Graphiti integration test is skipped by default.
3. **Lint clean:** `uv run ruff check .`.
4. **Degradation holds:** with `graphiti_enabled=False` (or FalkorDB down) the seed endpoint still returns 201, `generate_reply` still produces a reply with `(none yet)` memory, and a failing store leaves outbox rows `pending` with incremented `attempts` — nothing breaks.
5. **Real path (optional, local):** with FalkorDB + a local LLM and `graphiti_enabled=true`, seed an episode, drain it, and `retrieve_memory` returns extracted facts injected into the prompt.
6. **CI green** on the pushed branch.

**Milestone 5 is done when:** episodes are durably queued in a Postgres outbox and pushed to Graphiti with retry, memory retrieval is wired into the persona prompt and degrades cleanly to Postgres-only when Graphiti/FalkorDB is unavailable, onboarding seeds the initial episode, and the suite + CI are green on the default no-op path — giving M6 a `MemoryStore` + `enqueue_episode` seam to record task/proof/reaction episodes as the loop produces them.

---

## Self-Review

**Spec coverage (§3):**
- Tier 2 = Graphiti temporal KG on FalkorDB → Task 7 `GraphitiMemoryStore` (FalkorDriver + Graphiti). ✓
- Episodes ingested (session/task/proof/reaction) → mechanism in Tasks 4/6; **task/proof/reaction episode writes are M6** (those events don't exist yet) — documented seam (`enqueue_episode`). ✓ (scoped)
- Mistress queries the graph for continuity/personalization → Task 5 (retrieval injected into the prompt). ✓
- Graphiti LLM + embedder are OpenAI-compatible, ride the swappable provider config incl. local → Task 7 (`OpenAIGenericClient` + `OpenAIEmbedder` from Settings `llm_base_url`/`chat_model`/`embedding_model`). ✓
- Degradation: Graphiti/FalkorDB down → retrieval falls back to Postgres-only; writes queue + retry → Task 3 (`retrieve_memory` degrades to ""), Tasks 2/4 (durable outbox + retrying drain). ✓
- Onboarding seeds the initial episode (§4) → Task 6. ✓
- "Limits/consent never depend on fuzzy retrieval" → unchanged: authoritative state is still injected verbatim by M4; memory is additive only. ✓

**Placeholder scan:** complete code in every step; the one prose correction (the `FakeMemoryStore.__init__` should use `self.episodes = []`, called out explicitly) is fixed inline; no TODO/"handle later" beyond the explicit M6 seam.

**Type consistency:** `MemoryStore` Protocol methods (`add_episode(*, group_id, name, body, source, source_description, reference_time)`, `retrieve(*, group_id, query, num_results=10)`) match `NullMemoryStore`, `FakeMemoryStore`, `GraphitiMemoryStore`, and all call sites (`drain_outbox`, `retrieve_memory`). `enqueue_episode`/`drain_outbox`/`seed_profile_episode` signatures match their tests and the endpoint. `build_memory_store(settings)` and `retrieve_memory(store, *, group_id, query)` match Tasks 3/5/6. `generate_reply(..., *, memory=None, store=None)` matches the M4 call shape plus the new `store`.

**Cycle check:** `app/memory/store.py` imports only `app.config` (no persona/profile). `app/persona/service.py` imports `app.memory.store` (one-way). `app/memory/service.py` imports `app.persona.service` for the seed summary (one-way: memory.service → persona.service → memory.store). No import cycle.

---

## Notes for execution
- **Branch:** `feat/m5-memory` (not `master`).
- **Default-off is the safety net:** `graphiti_enabled=False` means the whole milestone runs (and CI passes) on `NullMemoryStore` with no FalkorDB/LLM. The real adapter is lazily imported and only touched when enabled or by the gated IT.
- **Outbox is the durability story:** `enqueue_episode` only flushes — it commits with the caller's transaction, so an episode is queued atomically with the state change it records. `drain_outbox` is idempotent-ish (only acts on `pending`) and never loses a row on failure.
- **One migration** (`memory_episode`); no PG enum (status is a String) so the downgrade is a plain `drop_table`.
- **graphiti-core install:** `uv sync` pulls it in Task 1; if the resolver struggles, report rather than pinning blindly. The import stays lazy so collection never pays for it on the Null path.
- **Local dev caveat:** clear `PYTHONHOME`/`PYTHONPATH` before `uv` (see `smistress-dev-environment`). CI unaffected.
- **Frontend (Addendum A):** none here. Memory surfaces only as richer persona replies; no new screen.
