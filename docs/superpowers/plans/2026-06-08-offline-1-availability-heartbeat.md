# Offline-First Milestone 1 — LLM Availability & Heartbeat Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the 24/7 VPS a system-wide notion of whether the home GPU box (the LLM) is reachable, fed by an outbound heartbeat from a small agent on the home box, and gate the live-chat endpoint on it.

**Architecture:** A single-row `llm_availability` record stores the last heartbeat timestamp. The home box runs an agent that, while its local OpenAI-compatible LLM endpoint answers, POSTs heartbeats to the VPS (`POST /llm/heartbeat`) — NAT/dynamic-IP safe because the box always initiates. The VPS computes `online` iff the last heartbeat is fresher than a TTL. The live-chat endpoint (`POST /profile/{id}/chat`) is gated: when offline it returns `503` ("the Mistress is away") instead of calling the LLM. This is the substrate the later offline milestones (drones, batch generation) build on.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async (psycopg3), Alembic, `httpx` (already a dependency), pytest (`asyncio_mode=auto`, live Postgres `smistress_test`), ruff (line-length 100).

**Scope note (honest to Addendum B):** This milestone delivers the binary **OFFLINE / ONLINE** substrate plus the heartbeat agent and the chat gate. The richer three-state distinction (a *batch window* vs a deliberately-opened *live audience*, B2/B8) and the offline drone surface (B3) are **later milestones** — when offline, this milestone simply blocks live chat with a 503; routing offline turns to drones comes next.

**Local dev caveat:** On Windows clear `$env:PYTHONHOME=$null; $env:PYTHONPATH=$null` before every `uv` call (see `smistress-dev-environment` memory). All commands below run from `backend/`. CI/Linux is unaffected.

---

### Task 1: Config — heartbeat TTL setting

**Files:**
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_config.py`:

```python
def test_heartbeat_ttl_default():
    from app.config import Settings

    assert Settings().heartbeat_ttl_seconds == 90
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_heartbeat_ttl_default -v`
Expected: FAIL with `AttributeError` / no attribute `heartbeat_ttl_seconds`.

- [ ] **Step 3: Add the setting**

In `backend/app/config.py`, add the field after `graphiti_enabled` (keep grouping tidy):

```python
    heartbeat_ttl_seconds: int = 90  # online iff last heartbeat is fresher than this
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (all config tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat(config): add heartbeat_ttl_seconds setting"
```

---

### Task 2: `LLMAvailability` enum

**Files:**
- Modify: `backend/app/db/enums.py`
- Test: `backend/tests/db/test_enums.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/db/test_enums.py`:

```python
def test_llm_availability_values():
    from app.db.enums import LLMAvailability

    assert LLMAvailability.OFFLINE.value == "offline"
    assert LLMAvailability.ONLINE.value == "online"
    assert LLMAvailability("online") is LLMAvailability.ONLINE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/db/test_enums.py::test_llm_availability_values -v`
Expected: FAIL with `ImportError` (cannot import `LLMAvailability`).

- [ ] **Step 3: Add the enum**

Append to `backend/app/db/enums.py`:

```python
class LLMAvailability(str, enum.Enum):
    """System-wide presence of the home-box LLM (Addendum B2). Computed from the
    last heartbeat's freshness, not stored as a column."""

    OFFLINE = "offline"
    ONLINE = "online"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/db/test_enums.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/enums.py backend/tests/db/test_enums.py
git commit -m "feat(db): add LLMAvailability enum"
```

---

### Task 3: `LlmHeartbeat` model (single-row availability table)

**Files:**
- Create: `backend/app/db/models/availability.py`
- Modify: `backend/app/db/models/__init__.py`
- Test: `backend/tests/db/test_availability_model.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/db/test_availability_model.py`:

```python
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models.availability import LlmHeartbeat


async def test_heartbeat_row_persists_and_allows_null_timestamp(session):
    row = LlmHeartbeat()  # fresh row: no heartbeat yet
    session.add(row)
    await session.flush()
    assert row.last_heartbeat_at is None
    assert row.source == ""

    row.last_heartbeat_at = datetime.now(timezone.utc)
    row.source = "ollama:qwen"
    await session.flush()

    fetched = (await session.execute(select(LlmHeartbeat))).scalar_one()
    assert fetched.source == "ollama:qwen"
    assert fetched.last_heartbeat_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/db/test_availability_model.py -v`
Expected: FAIL with `ModuleNotFoundError: app.db.models.availability`.

- [ ] **Step 3: Create the model**

Create `backend/app/db/models/availability.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LlmHeartbeat(Base):
    """Single-row, system-wide record of the home-box LLM's last heartbeat
    (Addendum B2). The app is single-user, so availability is global, not
    per-profile. ``last_heartbeat_at`` is None until the agent first reports."""

    __tablename__ = "llm_availability"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    source: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: Register the model**

In `backend/app/db/models/__init__.py`, add (alphabetical-ish, near the top):

```python
from app.db.models.availability import LlmHeartbeat  # noqa: F401
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/db/test_availability_model.py -v`
Expected: PASS (conftest `create_all` builds the new table).

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models/availability.py backend/app/db/models/__init__.py backend/tests/db/test_availability_model.py
git commit -m "feat(db): add LlmHeartbeat single-row availability model"
```

---

### Task 4: Alembic migration for `llm_availability`

**Files:**
- Create: `backend/alembic/versions/a1b2c3d4e5f6_add_llm_availability.py`

- [ ] **Step 1: Confirm the current head**

Run: `uv run alembic heads`
Expected: prints `d5e6f7a8b9c0 (head)`. If it differs, use that value as `down_revision` in Step 2 instead.

- [ ] **Step 2: Write the migration (handwritten, matching the project's style)**

Create `backend/alembic/versions/a1b2c3d4e5f6_add_llm_availability.py`:

```python
"""add llm_availability

Revision ID: a1b2c3d4e5f6
Revises: d5e6f7a8b9c0
Create Date: 2026-06-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'llm_availability',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source', sa.String(), server_default='', nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('llm_availability')
```

- [ ] **Step 3: Apply and verify the round-trip on the dev DB**

Run: `uv run alembic upgrade head`
Then: `uv run alembic downgrade -1`
Then: `uv run alembic upgrade head`
Expected: all three succeed with no error; the final state is at `a1b2c3d4e5f6`.

- [ ] **Step 4: Verify the table exists**

Run: `uv run alembic current`
Expected: `a1b2c3d4e5f6 (head)`.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/a1b2c3d4e5f6_add_llm_availability.py
git commit -m "feat(db): migration for llm_availability table"
```

---

### Task 5: Availability service (record heartbeat, compute online/offline)

**Files:**
- Create: `backend/app/availability/__init__.py` (empty)
- Create: `backend/app/availability/service.py`
- Test: `backend/tests/availability/__init__.py` (empty)
- Test: `backend/tests/availability/test_availability_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/availability/__init__.py` (empty file).

Create `backend/tests/availability/test_availability_service.py`:

```python
from datetime import datetime, timedelta, timezone

from app.availability import service as avail_svc
from app.db.enums import LLMAvailability


async def test_no_heartbeat_is_offline(session):
    snap = await avail_svc.snapshot(session)
    assert snap.state is LLMAvailability.OFFLINE
    assert snap.online is False
    assert snap.last_heartbeat_at is None


async def test_fresh_heartbeat_is_online(session):
    await avail_svc.record_heartbeat(session, source="ollama:qwen")
    snap = await avail_svc.snapshot(session)
    assert snap.state is LLMAvailability.ONLINE
    assert snap.online is True
    assert snap.last_heartbeat_at is not None
    assert await avail_svc.is_online(session) is True


async def test_stale_heartbeat_is_offline(session):
    await avail_svc.record_heartbeat(session)
    future = datetime.now(timezone.utc) + timedelta(seconds=120)
    snap = await avail_svc.snapshot(session, now=future, ttl_seconds=90)
    assert snap.state is LLMAvailability.OFFLINE
    assert snap.online is False


async def test_record_heartbeat_is_idempotent_single_row(session):
    from sqlalchemy import func, select

    from app.db.models.availability import LlmHeartbeat

    await avail_svc.record_heartbeat(session)
    await avail_svc.record_heartbeat(session, source="second")
    count = (await session.execute(select(func.count(LlmHeartbeat.id)))).scalar_one()
    assert count == 1  # upserts the same single row
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/availability/test_availability_service.py -v`
Expected: FAIL with `ModuleNotFoundError: app.availability`.

- [ ] **Step 3: Write the service**

Create `backend/app/availability/__init__.py` (empty file).

Create `backend/app/availability/service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.enums import LLMAvailability
from app.db.models.availability import LlmHeartbeat

# Re-declared here (not imported from app.main) to avoid an import cycle.
_settings = Settings()


@dataclass
class AvailabilitySnapshot:
    state: LLMAvailability
    last_heartbeat_at: datetime | None

    @property
    def online(self) -> bool:
        return self.state is LLMAvailability.ONLINE


async def _get_or_create(session: AsyncSession) -> LlmHeartbeat:
    """The single system-wide availability row. Created lazily on first use."""
    row = (await session.execute(select(LlmHeartbeat))).scalars().first()
    if row is None:
        row = LlmHeartbeat()
        session.add(row)
        await session.flush()
    return row


async def record_heartbeat(
    session: AsyncSession, *, source: str = ""
) -> LlmHeartbeat:
    """The home-box agent reported in. Stamps the single row with now. Caller commits."""
    row = await _get_or_create(session)
    row.last_heartbeat_at = datetime.now(timezone.utc)
    row.source = source
    await session.flush()
    return row


async def snapshot(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    ttl_seconds: int | None = None,
) -> AvailabilitySnapshot:
    """Current availability: ONLINE iff the last heartbeat is fresher than the TTL."""
    now = now or datetime.now(timezone.utc)
    ttl = _settings.heartbeat_ttl_seconds if ttl_seconds is None else ttl_seconds
    row = (await session.execute(select(LlmHeartbeat))).scalars().first()
    last = row.last_heartbeat_at if row else None
    if last is not None and (now - last).total_seconds() <= ttl:
        return AvailabilitySnapshot(LLMAvailability.ONLINE, last)
    return AvailabilitySnapshot(LLMAvailability.OFFLINE, last)


async def is_online(session: AsyncSession, *, now: datetime | None = None) -> bool:
    return (await snapshot(session, now=now)).online
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/availability/test_availability_service.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/availability backend/tests/availability
git commit -m "feat(availability): heartbeat record + online/offline snapshot service"
```

---

### Task 6: Availability schemas + API (`POST /llm/heartbeat`, `GET /llm/availability`)

**Files:**
- Create: `backend/app/schemas/availability.py`
- Create: `backend/app/api/availability.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_availability_api.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/api/test_availability_api.py`:

```python
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


async def test_availability_starts_offline(client):
    r = await client.get("/llm/availability")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "offline"
    assert body["online"] is False
    assert body["last_heartbeat_at"] is None


async def test_heartbeat_makes_online(client):
    r = await client.post("/llm/heartbeat", json={"source": "ollama:qwen"})
    assert r.status_code == 200
    assert r.json()["online"] is True

    r = await client.get("/llm/availability")
    body = r.json()
    assert body["state"] == "online"
    assert body["online"] is True
    assert body["last_heartbeat_at"] is not None


async def test_heartbeat_accepts_empty_body(client):
    r = await client.post("/llm/heartbeat", json={})
    assert r.status_code == 200
    assert r.json()["online"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_availability_api.py -v`
Expected: FAIL — `GET /llm/availability` returns 404 (route not registered yet).

- [ ] **Step 3: Write the schemas**

Create `backend/app/schemas/availability.py`:

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.db.enums import LLMAvailability


class HeartbeatIn(BaseModel):
    source: str = ""  # optional label, e.g. "<host>:<model>"; for display only


class AvailabilityOut(BaseModel):
    state: LLMAvailability
    online: bool
    last_heartbeat_at: datetime | None = None
```

- [ ] **Step 4: Write the API router**

Create `backend/app/api/availability.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability import service as avail_svc
from app.db.session import get_session
from app.schemas.availability import AvailabilityOut, HeartbeatIn

router = APIRouter(prefix="/llm", tags=["availability"])


def _out(snap: avail_svc.AvailabilitySnapshot) -> AvailabilityOut:
    return AvailabilityOut(
        state=snap.state, online=snap.online, last_heartbeat_at=snap.last_heartbeat_at
    )


@router.post("/heartbeat", response_model=AvailabilityOut)
async def heartbeat(
    body: HeartbeatIn, session: AsyncSession = Depends(get_session)
) -> AvailabilityOut:
    await avail_svc.record_heartbeat(session, source=body.source)
    await session.commit()
    return _out(await avail_svc.snapshot(session))


@router.get("/availability", response_model=AvailabilityOut)
async def availability(session: AsyncSession = Depends(get_session)) -> AvailabilityOut:
    return _out(await avail_svc.snapshot(session))
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, add the import alongside the other routers:

```python
from app.api.availability import router as availability_router
```

and include it (after `chat_router` is fine):

```python
app.include_router(availability_router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/api/test_availability_api.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/availability.py backend/app/api/availability.py backend/app/main.py backend/tests/api/test_availability_api.py
git commit -m "feat(api): /llm/heartbeat and /llm/availability endpoints"
```

---

### Task 7: Gate live chat on availability

**Files:**
- Modify: `backend/app/api/chat.py`
- Modify: `backend/tests/api/test_chat_api.py` (seed online so existing live-chat tests stay green)
- Test: `backend/tests/api/test_chat_api.py` (new offline-gating test)

- [ ] **Step 1: Write the failing test (offline → 503) and seed online in the fixture**

In `backend/tests/api/test_chat_api.py`, update the `client` fixture to seed an online heartbeat (these tests represent a live audience), by adding the heartbeat POST right before `yield ac`:

```python
@pytest_asyncio.fixture
async def client(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[chat_api.get_provider] = lambda: MockLLMProvider(
        scripted=[ChatResult(content="Kneel and report, pet.")]
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        await ac.post("/llm/heartbeat", json={"source": "test"})  # live-audience: online
        yield ac
    app.dependency_overrides.clear()
```

Then append a new test that uses a separate offline client (no heartbeat):

```python
async def test_chat_blocked_when_llm_offline(session):
    # A dedicated client that never sends a heartbeat -> the box is "away".
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[chat_api.get_provider] = lambda: MockLLMProvider(
        scripted=[ChatResult(content="should not be reached")]
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        r = await ac.post(
            "/onboarding/profile",
            json={"is_adult": True, "consent_acknowledged": True},
        )
        pid = r.json()["id"]
        r = await ac.post(f"/profile/{pid}/chat", json={"content": "are you there?"})
    app.dependency_overrides.clear()
    assert r.status_code == 503
    assert "away" in r.json()["detail"].lower()
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `uv run pytest tests/api/test_chat_api.py -v`
Expected: `test_chat_blocked_when_llm_offline` FAILS (returns 200, gate not implemented). Other tests in the file still PASS (the seeded heartbeat keeps them online).

- [ ] **Step 3: Add the gate dependency to the chat endpoint**

In `backend/app/api/chat.py`, add the import:

```python
from app.availability import service as avail_svc
```

Add a gate dependency (place it after `get_memory_store`):

```python
async def require_llm_online(session: AsyncSession = Depends(get_session)) -> None:
    """Live chat needs her present (Addendum B2/B8). Offline -> 503; later milestones
    route offline turns to the drones instead."""
    if not await avail_svc.is_online(session):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The Mistress is away — an audience requires her presence.",
        )
```

Wire it into `post_chat` by adding a dependency parameter (it must share the request session, which it does via `Depends(get_session)`):

```python
@router.post("/{profile_id}/chat", response_model=MessageOut)
async def post_chat(
    profile_id: uuid.UUID,
    body: ChatPost,
    session: AsyncSession = Depends(get_session),
    provider: LLMProvider = Depends(get_provider),
    store: MemoryStore = Depends(get_memory_store),
    _: None = Depends(require_llm_online),
) -> MessageOut:
    try:
        reply = await chat_svc.post_message(session, profile_id, body.content, provider, store)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return MessageOut.model_validate(reply)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_chat_api.py -v`
Expected: PASS (all tests, including `test_chat_blocked_when_llm_offline` and the unchanged round-trip/404 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/chat.py backend/tests/api/test_chat_api.py
git commit -m "feat(chat): gate live chat on LLM availability (503 when she is away)"
```

---

### Task 8: Home-box heartbeat agent

**Files:**
- Create: `backend/app/agent/__init__.py` (empty)
- Create: `backend/app/agent/heartbeat.py`
- Create: `backend/app/agent/README.md`
- Test: `backend/tests/agent/__init__.py` (empty)
- Test: `backend/tests/agent/test_heartbeat.py`

**Why under `backend/app/`:** the agent reuses the project's `httpx` dependency and is unit-testable in the same suite. It runs as its own process on the home box (`python -m app.agent.heartbeat`); it does not import the FastAPI app or touch the DB.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/agent/__init__.py` (empty file).

Create `backend/tests/agent/test_heartbeat.py`:

```python
from app.agent import heartbeat


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeClient:
    """Records calls and returns scripted responses; raises if told to."""

    def __init__(self, *, get_status=200, post_status=200, raise_on_get=False):
        self.get_status = get_status
        self.post_status = post_status
        self.raise_on_get = raise_on_get
        self.posts: list[tuple[str, dict]] = []

    async def get(self, url, **kwargs):
        if self.raise_on_get:
            import httpx

            raise httpx.ConnectError("boom")
        return _FakeResponse(self.get_status)

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs.get("json", {})))
        return _FakeResponse(self.post_status)


async def test_llm_reachable_true_on_200():
    client = _FakeClient(get_status=200)
    assert await heartbeat.llm_reachable(client, "http://localhost:11434/v1") is True


async def test_llm_reachable_false_on_error():
    client = _FakeClient(raise_on_get=True)
    assert await heartbeat.llm_reachable(client, "http://localhost:11434/v1") is False


async def test_run_once_beats_when_reachable():
    client = _FakeClient(get_status=200, post_status=200)
    sent = await heartbeat.run_once(
        client,
        llm_base_url="http://localhost:11434/v1",
        vps_url="https://vps.example",
        source="qwen",
    )
    assert sent is True
    assert client.posts == [("https://vps.example/llm/heartbeat", {"source": "qwen"})]


async def test_run_once_skips_when_unreachable():
    client = _FakeClient(raise_on_get=True)
    sent = await heartbeat.run_once(
        client,
        llm_base_url="http://localhost:11434/v1",
        vps_url="https://vps.example",
        source="qwen",
    )
    assert sent is False
    assert client.posts == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_heartbeat.py -v`
Expected: FAIL with `ModuleNotFoundError: app.agent`.

- [ ] **Step 3: Write the agent**

Create `backend/app/agent/__init__.py` (empty file).

Create `backend/app/agent/heartbeat.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import os
import socket

import httpx


async def llm_reachable(client: httpx.AsyncClient, base_url: str, *, timeout: float = 5.0) -> bool:
    """Is the local OpenAI-compatible LLM answering? Probes the cheap /models route."""
    try:
        r = await client.get(f"{base_url.rstrip('/')}/models", timeout=timeout)
        return r.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


async def send_heartbeat(
    client: httpx.AsyncClient, vps_url: str, source: str, *, timeout: float = 5.0
) -> bool:
    """POST one heartbeat to the VPS. Returns True on a 200."""
    try:
        r = await client.post(
            f"{vps_url.rstrip('/')}/llm/heartbeat", json={"source": source}, timeout=timeout
        )
        return r.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


async def run_once(
    client: httpx.AsyncClient, *, llm_base_url: str, vps_url: str, source: str
) -> bool:
    """One cycle: beat only if the local LLM is reachable. Returns True if a beat was sent."""
    if await llm_reachable(client, llm_base_url):
        return await send_heartbeat(client, vps_url, source)
    return False


async def run_forever(
    *, llm_base_url: str, vps_url: str, source: str, interval: float
) -> None:  # pragma: no cover - long-running loop
    async with httpx.AsyncClient() as client:
        while True:
            await run_once(
                client, llm_base_url=llm_base_url, vps_url=vps_url, source=source
            )
            await asyncio.sleep(interval)


def _parse_args() -> argparse.Namespace:  # pragma: no cover - thin CLI wrapper
    p = argparse.ArgumentParser(description="smistress home-box LLM heartbeat agent")
    p.add_argument("--vps-url", default=os.environ.get("SMISTRESS_VPS_URL", ""))
    p.add_argument(
        "--llm-base-url",
        default=os.environ.get("SMISTRESS_LLM_BASE_URL", "http://localhost:11434/v1"),
    )
    p.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("SMISTRESS_HEARTBEAT_INTERVAL", "30")),
    )
    p.add_argument("--source", default=os.environ.get("SMISTRESS_HEARTBEAT_SOURCE", socket.gethostname()))
    return p.parse_args()


def main() -> None:  # pragma: no cover - process entrypoint
    args = _parse_args()
    if not args.vps_url:
        raise SystemExit("set --vps-url or SMISTRESS_VPS_URL (e.g. https://your-vps)")
    asyncio.run(
        run_forever(
            llm_base_url=args.llm_base_url,
            vps_url=args.vps_url,
            source=args.source,
            interval=args.interval,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    main()
```

- [ ] **Step 4: Write the agent README**

Create `backend/app/agent/README.md`:

```markdown
# Home-box heartbeat agent

Runs on the home GPU machine. While the local OpenAI-compatible LLM (Ollama/vLLM/etc.)
answers `GET {llm_base_url}/models`, it POSTs a heartbeat to the VPS so the app knows the
Mistress is reachable (Addendum B2). The box always initiates the connection, so it works
behind NAT / a dynamic IP — the VPS never reaches inward.

## Run

```bash
# from backend/ (needs only httpx, already in the project deps)
SMISTRESS_VPS_URL=https://your-vps \
SMISTRESS_LLM_BASE_URL=http://localhost:11434/v1 \
SMISTRESS_HEARTBEAT_INTERVAL=30 \
uv run python -m app.agent.heartbeat
```

The VPS marks the LLM `online` while heartbeats arrive and `offline` once they are older
than `SMISTRESS_HEARTBEAT_TTL_SECONDS` (default 90s) — keep the interval well under the TTL
so a single missed beat doesn't flip the state.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_heartbeat.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent backend/tests/agent
git commit -m "feat(agent): home-box LLM heartbeat agent + unit tests"
```

---

### Task 9: Full verification & lint

**Files:** none (verification only)

- [ ] **Step 1: Run the whole backend suite**

Run: `uv run pytest -q`
Expected: all tests pass (the existing suite plus the new availability/agent/gating tests).

- [ ] **Step 2: Lint**

Run: `uv run ruff check .`
Expected: no errors. Fix any line-length>100 or import-order issues, then re-run.

- [ ] **Step 3: Sanity-check the running app (optional, manual)**

Start the dev server (`uv run python run_dev.py`) and, in another shell:
- `GET /llm/availability` → `{"state":"offline","online":false,...}` on a cold DB.
- `POST /llm/heartbeat` `{}` → `{"online":true,...}`; then `GET /llm/availability` → online.
- With no recent heartbeat (wait > TTL, or on a fresh DB), `POST /profile/{id}/chat` → `503` "the Mistress is away".

- [ ] **Step 4: Push and confirm CI is green**

```bash
git push -u origin HEAD
```
Then watch the `backend` CI job (Postgres-backed) go green. The `frontend`/`e2e` jobs are unaffected (no frontend changes this milestone).

---

## Notes for the next milestone (not built here)

- **Offline surface (B3):** when `GET /llm/availability` is offline, the frontend should show the standing-orders dossier and dim chat ("she is away"); the 503 from this milestone is the backend signal. Frontend wiring + `npm run gen:api` happen there.
- **Batch window vs live audience (B2/B8):** this milestone exposes only OFFLINE/ONLINE. Opening a deliberate *audience* and flagging *batch jobs* (pending-job flag the agent observes) are layered on top of this substrate later.
