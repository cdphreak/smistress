# Phase B1 — Chat Surface + Live Dossier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the home screen into a working chat with the mistress — persisted conversation over the existing `generate_reply` turn path — with a live read-only dossier (rank / merit / tokens / disposition / active task) pinned on top.

**Architecture:** A new `message` table persists each turn; a chat service stores the user message, runs `persona.generate_reply` against the recent history, stores the reply, and returns it (non-streaming). A composed `GET /dossier` endpoint reads economy + disposition + active task. The frontend adds `chat`/`dossier` runes stores, `Bubble`/`DossierBar` primitives, and rebuilds `/` as the chat surface with a pinned input; the typed-safeword phrase is intercepted on the input and short-circuits to the existing safety stop **before** any chat call (Addendum A5/A6).

**Tech Stack:** Backend — Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, pytest (live `smistress_test` Postgres), `MockLLMProvider` for tests. Frontend — SvelteKit 2, Svelte 5 runes, TypeScript, Vitest + `@testing-library/svelte`, Playwright (API mocked).

---

## Scope (B1 of Phase B)

**In:** chat endpoint + server-persisted messages (non-streaming), chat surface (bubbles + input + typed-safeword interceptor), live read-only dossier (rank/merit/tokens, disposition line, active task, denial-timer count), dossier expands to the spokes.

**Out (deferred to B2):** the mistress's tool-calls → inline action cards (assign task / set denial / grant-revoke tokens), proof capture, economy mutations from chat, token streaming (SSE). `generate_reply` is used as-is (it already gates safeword/crisis/hard-limit-filter); B1 does **not** add tool-calling.

---

## Background (already in place — do not rebuild)

- `persona.service.generate_reply(session, profile_id, conversation, provider, *, memory=None, store=None) -> ChatResult` — the single turn entry point. It derives the latest user message, intercepts crisis/safeword **before** the LLM, holds when halted, else compiles the persona prompt + calls `provider.chat`, then runs the hard-limit output filter. `ChatMessage(role, content)` and `ChatResult(content, tool_calls=[])` live in `app/llm/types.py` (roles: "system"|"user"|"assistant"|"tool").
- `economy.service.get_economy` → `EconomyState(merit, rank, tokens)`; `active_denial_timers(session, id) -> list`. `GET /profile/{id}/standing` returns `StandingOut(merit, rank, tokens, denial_timers[])`.
- `persona.service.get_disposition(session, id) -> Disposition(band, standing, reason, line)`; `GET /profile/{id}/disposition` → `DispositionOut(band, standing, reason, line)`.
- `app/llm/factory.build_provider(settings)` and `app/memory/store.build_memory_store(settings)` (returns `NullMemoryStore` when graphiti disabled). `main.py` has a `get_provider()` pattern (don't import from `main` — re-declare a dep locally to avoid a cycle).
- Current Alembic head: `f3a9c1b2d4e5` (safety_state).
- Frontend: `lib/api/client.ts` (`api` = `{get, post, put, del}`), `lib/stores/session.svelte.ts` (`session.profileId`), `lib/stores/safety.svelte.ts` (`safety.confirmStop()` posts `/safeword` and shows the global StopSheet), the design tokens + primitives, and the global SAFE overlay mounted in `+layout.svelte`. `/` is currently a static hub linking the spokes — B1 replaces it with the chat surface.

**Branch:** `feat/phase-b1-chat`. Backend dev caveat: clear `PYTHONHOME`/`PYTHONPATH` before `uv` on this machine. Frontend = npm (Node 22). No backend needed for frontend tests (Vitest mocks `$lib/api/*`; Playwright stubs `/api/*`).

---

## File structure

**Backend — create:** `app/db/models/message.py`, `alembic/versions/c4d5e6f7a8b9_add_message.py`, `app/chat/__init__.py`, `app/chat/service.py`, `app/schemas/chat.py`, `app/api/chat.py`, tests `tests/db/test_message_model.py`, `tests/chat/__init__.py`, `tests/chat/test_chat_service.py`, `tests/api/test_chat_api.py`.
**Backend — modify:** `app/db/models/__init__.py` (register Message), `app/main.py` (include chat router).
**Frontend — create:** `src/lib/api/chat.ts`, `src/lib/api/dossier.ts`, `src/lib/safety/phrases.ts` (client-side safeword detection), `src/lib/stores/chat.svelte.ts`, `src/lib/stores/dossier.svelte.ts`, `src/lib/design/components/Bubble.svelte`, `src/lib/chat/DossierBar.svelte`, tests for each + `src/lib/safety/phrases.test.ts`.
**Frontend — modify:** `src/routes/+page.svelte` (chat surface), `e2e/fixtures.ts` + `e2e/chat.spec.ts`.

---

## Task 1: Message model + migration

**Files:** Create `app/db/models/message.py`, `alembic/versions/c4d5e6f7a8b9_add_message.py`, `tests/db/test_message_model.py`; modify `app/db/models/__init__.py`.

- [ ] **Step 1: Write the failing test** — `tests/db/test_message_model.py`:
```python
from sqlalchemy import select

from app.db.models.message import Message
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def test_message_persists_role_and_content(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    session.add(Message(profile_id=p.id, role="user", content="hello"))
    session.add(Message(profile_id=p.id, role="assistant", content="kneel."))
    await session.flush()
    rows = (await session.execute(
        select(Message).where(Message.profile_id == p.id).order_by(Message.created_at)
    )).scalars().all()
    assert [m.role for m in rows] == ["user", "assistant"]
    assert rows[1].content == "kneel."
```

- [ ] **Step 2: Run** — `uv run pytest tests/db/test_message_model.py -q` → FAIL (no module).

- [ ] **Step 3a: Model** — `app/db/models/message.py`:
```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.profile import SubProfile


class Message(Base):
    """A single chat turn (spec 5A / Addendum A5). role is 'user' | 'assistant'.

    The system prompt is recompiled per turn and never stored; only the visible
    conversation is persisted, so reload and memory can reference it.
    """

    __tablename__ = "message"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    profile: Mapped[SubProfile] = relationship()
```

- [ ] **Step 3b: Register** — add to `app/db/models/__init__.py`:
```python
from app.db.models.message import Message  # noqa: F401
```

- [ ] **Step 3c: Migration** — `alembic/versions/c4d5e6f7a8b9_add_message.py`:
```python
"""add message

Revision ID: c4d5e6f7a8b9
Revises: f3a9c1b2d4e5
Create Date: 2026-06-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'f3a9c1b2d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'message',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('message')
```

- [ ] **Step 3d: Delete cascade** — in `app/services/profile.py::delete_profile`, add `Message` so a full wipe removes chat history. Add the import `from app.db.models.message import Message` and include `Message` in the per-model delete loop (the tuple that already lists `Task, DenialTimer, EconomyState, CharacterModel, MemoryEpisode, SafetyState, KinkEntry, Toy, Goal, ArchetypeResult, SoContext`). Insert `Message,` into that tuple.

- [ ] **Step 4: Run** — `uv run pytest tests/db/test_message_model.py tests/db/test_migration.py tests/services/test_delete_profile.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/db/models/message.py backend/app/db/models/__init__.py backend/app/services/profile.py backend/alembic/versions/c4d5e6f7a8b9_add_message.py backend/tests/db/test_message_model.py
git commit -m "feat(chat): Message model + migration; include in profile delete"
```

---

## Task 2: Chat service (post turn + history + dossier)

**Files:** Create `app/chat/__init__.py` (empty), `app/chat/service.py`, `tests/chat/__init__.py` (empty), `tests/chat/test_chat_service.py`.

- [ ] **Step 1: Write the failing test** — `tests/chat/test_chat_service.py`:
```python
from app.chat import service as chat_svc
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.memory.store import NullMemoryStore
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_post_message_stores_turn_and_returns_reply(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[ChatResult(content="On the board, pet.")])
    reply = await chat_svc.post_message(
        session, p.id, "what is my task?", provider, NullMemoryStore()
    )
    assert reply.role == "assistant"
    assert reply.content == "On the board, pet."

    history = await chat_svc.list_messages(session, p.id)
    assert [(m.role, m.content) for m in history] == [
        ("user", "what is my task?"),
        ("assistant", "On the board, pet."),
    ]


async def test_post_message_sends_prior_history_to_the_model(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[ChatResult(content="one"), ChatResult(content="two")])
    await chat_svc.post_message(session, p.id, "first", provider, NullMemoryStore())
    await chat_svc.post_message(session, p.id, "second", provider, NullMemoryStore())
    # the 2nd call's conversation (sans system prompt) carries the full prior turns
    sent = provider.calls[1]
    contents = [m.content for m in sent if m.role != "system"]
    assert contents == ["first", "one", "second"]


async def test_build_dossier_composes_economy_disposition_active_task(session):
    p = await _profile(session)
    d = await chat_svc.build_dossier(session, p.id)
    assert d["rank"] == "novice"
    assert d["merit"] == 0
    assert d["tokens"] == 0
    assert "band" in d["disposition"] and "line" in d["disposition"]
    assert d["active_task"] is None
    assert d["denial_timers"] == 0
```

- [ ] **Step 2: Run** — `uv run pytest tests/chat/test_chat_service.py -q` → FAIL (no module).

- [ ] **Step 3: Implement** — `app/chat/service.py`:
```python
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import TaskStatus
from app.db.models.message import Message
from app.db.models.task import Task
from app.economy import service as econ_svc
from app.llm.provider import LLMProvider
from app.llm.types import ChatMessage
from app.memory.store import MemoryStore
from app.persona import service as persona_svc
from app.services import profile as profile_svc

# Most-recent turns sent back to the model as context (bounds the prompt size).
HISTORY_LIMIT = 20

_ACTIVE = (
    TaskStatus.ASSIGNED,
    TaskStatus.IN_PROGRESS,
    TaskStatus.PROOF_SUBMITTED,
    TaskStatus.VERIFYING,
)


async def list_messages(
    session: AsyncSession, profile_id: uuid.UUID, *, limit: int | None = None
) -> list[Message]:
    stmt = select(Message).where(Message.profile_id == profile_id).order_by(Message.created_at)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows[-limit:]) if limit else list(rows)


async def post_message(
    session: AsyncSession,
    profile_id: uuid.UUID,
    content: str,
    provider: LLMProvider,
    store: MemoryStore,
) -> Message:
    """Persist the user turn, generate the reply over recent history, persist + return it.

    Caller commits. ``generate_reply`` already gates safeword/crisis/hard-limits.
    """
    await profile_svc.get_profile(session, profile_id)  # 404 guard
    session.add(Message(profile_id=profile_id, role="user", content=content))
    await session.flush()

    recent = await list_messages(session, profile_id, limit=HISTORY_LIMIT)
    conversation = [ChatMessage(role=m.role, content=m.content) for m in recent]
    result = await persona_svc.generate_reply(
        session, profile_id, conversation, provider, store=store
    )

    reply = Message(profile_id=profile_id, role="assistant", content=result.content)
    session.add(reply)
    await session.flush()
    return reply


async def build_dossier(session: AsyncSession, profile_id: uuid.UUID) -> dict:
    """Read-only live status: economy + disposition + active task (Addendum A5)."""
    econ = await econ_svc.get_economy(session, profile_id)  # raises EconomyNotFound
    disposition = await persona_svc.get_disposition(session, profile_id)
    timers = await econ_svc.active_denial_timers(session, profile_id)
    active = (await session.execute(
        select(Task)
        .where(Task.profile_id == profile_id, Task.status.in_(_ACTIVE))
        .order_by(Task.created_at.desc())
        .limit(1)
    )).scalars().first()
    return {
        "rank": econ.rank,
        "merit": econ.merit,
        "tokens": econ.tokens,
        "disposition": {
            "band": disposition.band.value,
            "line": disposition.line,
            "reason": disposition.reason,
            "standing": disposition.standing,
        },
        "active_task": (
            {"description": active.description, "status": active.status.value}
            if active is not None
            else None
        ),
        "denial_timers": len(timers),
    }
```

- [ ] **Step 4: Run** — `uv run pytest tests/chat/test_chat_service.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/chat/ backend/tests/chat/
git commit -m "feat(chat): chat service — persist turns, run generate_reply, build dossier"
```

---

## Task 3: Chat + dossier REST API

**Files:** Create `app/schemas/chat.py`, `app/api/chat.py`, `tests/api/test_chat_api.py`; modify `app/main.py`.

- [ ] **Step 1: Write the failing test** — `tests/api/test_chat_api.py`:
```python
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api import chat as chat_api
from app.db.session import get_session
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.main import app


@pytest_asyncio.fixture
async def client(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[chat_api.get_provider] = lambda: MockLLMProvider(
        scripted=[ChatResult(content="Kneel and report, pet.")]
    )
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


async def test_chat_round_trip_and_history(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/chat", json={"content": "what now?"})
    assert r.status_code == 200
    assert r.json()["role"] == "assistant"
    assert r.json()["content"] == "Kneel and report, pet."

    r = await client.get(f"/profile/{pid}/messages")
    assert r.status_code == 200
    msgs = r.json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]


async def test_dossier_reads_live_status(client):
    pid = await _new_profile(client)
    r = await client.get(f"/profile/{pid}/dossier")
    assert r.status_code == 200
    body = r.json()
    assert body["rank"] == "novice"
    assert body["disposition"]["line"]
    assert body["active_task"] is None


async def test_chat_unknown_profile_404(client):
    r = await client.post(f"/profile/{uuid.uuid4()}/chat", json={"content": "hi"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run** — `uv run pytest tests/api/test_chat_api.py -q` → FAIL (routes not registered).

- [ ] **Step 3a: Schemas** — `app/schemas/chat.py`:
```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ChatPost(BaseModel):
    content: str


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DispositionBlock(BaseModel):
    band: str
    line: str
    reason: str
    standing: int


class ActiveTask(BaseModel):
    description: str
    status: str


class DossierOut(BaseModel):
    rank: str
    merit: int
    tokens: int
    disposition: DispositionBlock
    active_task: ActiveTask | None
    denial_timers: int
```

- [ ] **Step 3b: Router** — `app/api/chat.py`:
```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import service as chat_svc
from app.config import Settings
from app.db.session import get_session
from app.economy import service as econ_svc
from app.llm.factory import build_provider
from app.llm.provider import LLMProvider
from app.memory.store import MemoryStore, build_memory_store
from app.schemas.chat import ChatPost, DossierOut, MessageOut
from app.services import profile as profile_svc

router = APIRouter(prefix="/profile", tags=["chat"])

# Re-declared here (not imported from app.main) to avoid an import cycle.
_settings = Settings()


def get_provider() -> LLMProvider:
    return build_provider(_settings)


def get_memory_store() -> MemoryStore:
    return build_memory_store(_settings)


def _not_found(profile_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"profile {profile_id} not found"
    )


@router.post("/{profile_id}/chat", response_model=MessageOut)
async def post_chat(
    profile_id: uuid.UUID,
    body: ChatPost,
    session: AsyncSession = Depends(get_session),
    provider: LLMProvider = Depends(get_provider),
    store: MemoryStore = Depends(get_memory_store),
) -> MessageOut:
    try:
        reply = await chat_svc.post_message(session, profile_id, body.content, provider, store)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return MessageOut.model_validate(reply)


@router.get("/{profile_id}/messages", response_model=list[MessageOut])
async def list_messages(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[MessageOut]:
    try:
        await profile_svc.get_profile(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    msgs = await chat_svc.list_messages(session, profile_id)
    return [MessageOut.model_validate(m) for m in msgs]


@router.get("/{profile_id}/dossier", response_model=DossierOut)
async def dossier(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> DossierOut:
    try:
        data = await chat_svc.build_dossier(session, profile_id)
    except (profile_svc.ProfileNotFound, econ_svc.EconomyNotFound):
        raise _not_found(profile_id)
    return DossierOut.model_validate(data)
```

- [ ] **Step 3c: Register** — in `app/main.py`, add `from app.api.chat import router as chat_router` with the other router imports and `app.include_router(chat_router)` after the others.

- [ ] **Step 4: Run** — `uv run pytest tests/api/test_chat_api.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/schemas/chat.py backend/app/api/chat.py backend/app/main.py backend/tests/api/test_chat_api.py
git commit -m "feat(chat): POST /chat, GET /messages, GET /dossier endpoints"
```

---

## Task 4: Frontend chat/dossier API modules + client safeword phrases

**Files:** Create `src/lib/api/chat.ts`, `src/lib/api/dossier.ts`, `src/lib/safety/phrases.ts`, `src/lib/safety/phrases.test.ts`.

- [ ] **Step 1: Write the failing test** — `src/lib/safety/phrases.test.ts`:
```ts
import { expect, test } from 'vitest';
import { isSafeword } from './phrases';

test('matches recognized safeword phrases and the standalone token', () => {
  expect(isSafeword('safeword')).toBe(true);
  expect(isSafeword('I want to stop')).toBe(true);
  expect(isSafeword('  RED  ')).toBe(true);
  expect(isSafeword('the red dress')).toBe(false);
  expect(isSafeword('what is my task?')).toBe(false);
});
```

- [ ] **Step 2: Run** — `npx vitest run src/lib/safety/phrases.test.ts` → FAIL.

- [ ] **Step 3a: Client safeword phrases** — `src/lib/safety/phrases.ts` (mirrors the backend `app/safety/detect.py`; the input interceptor short-circuits before sending, Addendum A6):
```ts
const PHRASES = ['safeword', 'stop the scene', 'end the scene', 'i want to stop', 'i need to stop'];
const STANDALONE = ['red', "i'm done"];

export function isSafeword(text: string): boolean {
  const t = text.trim().toLowerCase();
  if (STANDALONE.includes(t)) return true;
  return PHRASES.some((p) => t.includes(p));
}
```

- [ ] **Step 3b: Chat API** — `src/lib/api/chat.ts`:
```ts
import { api } from './client';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export const getMessages = (id: string) =>
  api.get(`/api/profile/${id}/messages`) as Promise<Message[]>;
export const sendMessage = (id: string, content: string) =>
  api.post(`/api/profile/${id}/chat`, { content }) as Promise<Message>;
```

- [ ] **Step 3c: Dossier API** — `src/lib/api/dossier.ts`:
```ts
import { api } from './client';

export interface Dossier {
  rank: string;
  merit: number;
  tokens: number;
  disposition: { band: string; line: string; reason: string; standing: number };
  active_task: { description: string; status: string } | null;
  denial_timers: number;
}

export const getDossier = (id: string) => api.get(`/api/profile/${id}/dossier`) as Promise<Dossier>;
```

- [ ] **Step 4: Run** — `npx vitest run src/lib/safety/phrases.test.ts` → PASS; `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/api/chat.ts frontend/src/lib/api/dossier.ts frontend/src/lib/safety/phrases.ts frontend/src/lib/safety/phrases.test.ts
git commit -m "feat(fe): chat/dossier API modules + client-side safeword phrase detection"
```

---

## Task 5: chat + dossier runes stores

**Files:** Create `src/lib/stores/chat.svelte.ts`, `src/lib/stores/dossier.svelte.ts`, `src/lib/stores/chat.test.ts`, `src/lib/stores/dossier.test.ts`.

- [ ] **Step 1: Write the failing tests** — `src/lib/stores/chat.test.ts`:
```ts
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/chat', () => ({
  getMessages: vi.fn(async () => [{ id: '1', role: 'user', content: 'hi', created_at: 'now' }]),
  sendMessage: vi.fn(async (_id, content) => ({
    id: '2', role: 'assistant', content: `re: ${content}`, created_at: 'now'
  }))
}));

import { chat } from './chat.svelte';
import { session } from './session.svelte';

beforeEach(() => {
  session.setProfileId('p1');
  chat.messages = [];
});

test('load fetches history', async () => {
  await chat.load();
  expect(chat.messages.map((m) => m.content)).toEqual(['hi']);
});

test('send appends the user message then the reply', async () => {
  await chat.send('what now?');
  expect(chat.messages.map((m) => `${m.role}:${m.content}`)).toEqual([
    'user:what now?',
    'assistant:re: what now?'
  ]);
});
```

`src/lib/stores/dossier.test.ts`:
```ts
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/dossier', () => ({
  getDossier: vi.fn(async () => ({
    rank: 'adept', merit: 50, tokens: 3,
    disposition: { band: 'neutral', line: 'neutral · measured — strong standing', reason: 'x', standing: 60 },
    active_task: null, denial_timers: 0
  }))
}));

import { dossier } from './dossier.svelte';
import { session } from './session.svelte';

beforeEach(() => session.setProfileId('p1'));

test('refresh loads live status', async () => {
  await dossier.refresh();
  expect(dossier.data?.rank).toBe('adept');
  expect(dossier.data?.disposition.line).toContain('measured');
});
```

- [ ] **Step 2: Run** — `npx vitest run src/lib/stores/chat.test.ts src/lib/stores/dossier.test.ts` → FAIL.

- [ ] **Step 3a: chat store** — `src/lib/stores/chat.svelte.ts`:
```ts
import { getMessages, sendMessage, type Message } from '$lib/api/chat';
import { session } from './session.svelte';

class Chat {
  messages = $state<Message[]>([]);
  sending = $state(false);

  async load() {
    const pid = session.profileId;
    if (!pid) return;
    this.messages = await getMessages(pid);
  }
  async send(content: string) {
    const pid = session.profileId;
    if (!pid) return;
    this.sending = true;
    // optimistic user bubble
    this.messages = [
      ...this.messages,
      { id: `local-${Date.now()}`, role: 'user', content, created_at: new Date().toISOString() }
    ];
    try {
      const reply = await sendMessage(pid, content);
      this.messages = [...this.messages, reply];
    } finally {
      this.sending = false;
    }
  }
}

export const chat = new Chat();
```

- [ ] **Step 3b: dossier store** — `src/lib/stores/dossier.svelte.ts`:
```ts
import { getDossier, type Dossier } from '$lib/api/dossier';
import { session } from './session.svelte';

class DossierStore {
  data = $state<Dossier | null>(null);

  async refresh() {
    const pid = session.profileId;
    if (!pid) return;
    this.data = await getDossier(pid);
  }
}

export const dossier = new DossierStore();
```

- [ ] **Step 4: Run** — `npx vitest run src/lib/stores/chat.test.ts src/lib/stores/dossier.test.ts` → PASS; `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/stores/chat.svelte.ts frontend/src/lib/stores/dossier.svelte.ts frontend/src/lib/stores/chat.test.ts frontend/src/lib/stores/dossier.test.ts
git commit -m "feat(fe): chat + dossier runes stores"
```

---

## Task 6: Bubble + DossierBar components

**Files:** Create `src/lib/design/components/Bubble.svelte`, `src/lib/design/components/Bubble.test.ts`, `src/lib/chat/DossierBar.svelte`, `src/lib/chat/DossierBar.test.ts`.

- [ ] **Step 1: Write the failing tests** — `src/lib/design/components/Bubble.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import Bubble from './Bubble.svelte';

test('renders content and tags the speaker', () => {
  const { container } = render(Bubble, { role: 'assistant', content: 'Kneel.' });
  expect(screen.getByText('Kneel.')).toBeInTheDocument();
  expect(container.querySelector('.bubble.mistress')).not.toBeNull();
});

test('the sub bubble is right-aligned', () => {
  const { container } = render(Bubble, { role: 'user', content: 'yes' });
  expect(container.querySelector('.bubble.sub')).not.toBeNull();
});
```

`src/lib/chat/DossierBar.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import DossierBar from './DossierBar.svelte';

const data = {
  rank: 'adept', merit: 50, tokens: 3,
  disposition: { band: 'cool', line: 'cool · exacting — 2 recent misses', reason: '2 recent misses', standing: 30 },
  active_task: { description: 'Posture drill', status: 'assigned' },
  denial_timers: 1
};

test('shows rank, merit and the disposition line', () => {
  render(DossierBar, { data });
  expect(screen.getByText(/adept/i)).toBeInTheDocument();
  expect(screen.getByText(/cool · exacting/)).toBeInTheDocument();
});

test('renders nothing-fatal when data is null', () => {
  render(DossierBar, { data: null });
  // a loading placeholder is shown
  expect(screen.getByText(/…|loading/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run** — `npx vitest run src/lib/design/components/Bubble.test.ts src/lib/chat/DossierBar.test.ts` → FAIL.

- [ ] **Step 3a: Bubble** — `src/lib/design/components/Bubble.svelte` (her = `--raised` with crimson left hairline, left; sub = gray, right; Addendum A5):
```svelte
<script lang="ts">
  let { role, content }: { role: 'user' | 'assistant'; content: string } = $props();
  const mine = $derived(role === 'user');
</script>

<div class="bubble {mine ? 'sub' : 'mistress'}">{content}</div>

<style>
  .bubble {
    max-width: 78%;
    padding: 10px 14px;
    margin: 6px 0;
    line-height: 1.5;
    white-space: pre-wrap;
  }
  .mistress {
    align-self: flex-start;
    background: var(--raised);
    color: var(--paper);
    border-left: 2px solid var(--accent);
  }
  .sub {
    align-self: flex-end;
    background: #222;
    color: var(--paper);
  }
</style>
```

- [ ] **Step 3b: DossierBar** — `src/lib/chat/DossierBar.svelte`:
```svelte
<script lang="ts">
  import type { Dossier } from '$lib/api/dossier';
  let { data }: { data: Dossier | null } = $props();
  let expanded = $state(false);
</script>

<header class="dossier">
  {#if !data}
    <span class="label">…</span>
  {:else}
    <button class="summary" onclick={() => (expanded = !expanded)}>
      <span class="ledger">{data.rank} · merit {data.merit} · tokens {data.tokens}</span>
      <span class="task">{data.active_task ? data.active_task.description : 'no active task'}</span>
    </button>
    <p class="disposition ledger">{data.disposition.line}</p>
    {#if expanded}
      <div class="expand">
        <p class="ledger">denial timers: {data.denial_timers}</p>
        <nav class="spokes">
          <a href="/profile">Sub Profile</a>
          <a href="/character">Character</a>
          <a href="/settings">Settings</a>
        </nav>
      </div>
    {/if}
  {/if}
</header>

<style>
  .dossier {
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--ink);
    border-bottom: 1px solid var(--hairline);
    padding: 12px 16px;
  }
  .summary {
    width: 100%;
    display: flex;
    justify-content: space-between;
    gap: 12px;
    background: transparent;
    border: 0;
    color: var(--paper);
    cursor: pointer;
    font: inherit;
    text-align: left;
  }
  .ledger {
    font-family: var(--font-mono);
  }
  .task {
    color: var(--muted);
  }
  .disposition {
    margin: 6px 0 0;
    color: var(--muted);
    font-size: 0.8rem;
  }
  .expand {
    margin-top: 10px;
  }
  .spokes {
    display: flex;
    gap: 16px;
  }
  .spokes a {
    color: var(--accent);
    text-decoration: none;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.75rem;
  }
</style>
```

- [ ] **Step 4: Run** — `npx vitest run src/lib/design/components/Bubble.test.ts src/lib/chat/DossierBar.test.ts` → PASS; `npm run check` clean.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/design/components/Bubble.svelte frontend/src/lib/design/components/Bubble.test.ts frontend/src/lib/chat/DossierBar.svelte frontend/src/lib/chat/DossierBar.test.ts
git commit -m "feat(fe): Bubble + DossierBar chat primitives"
```

---

## Task 7: Chat home surface (`/`)

**Files:** Modify `src/routes/+page.svelte`; create `src/routes/page.test.ts`.

- [ ] **Step 1: Write the failing test** — `src/routes/page.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/chat', () => ({
  getMessages: vi.fn(async () => []),
  sendMessage: vi.fn(async (_id, content) => ({
    id: '2', role: 'assistant', content: 'Acknowledged.', created_at: 'now'
  }))
}));
vi.mock('$lib/api/dossier', () => ({
  getDossier: vi.fn(async () => ({
    rank: 'novice', merit: 0, tokens: 0,
    disposition: { band: 'cool', line: 'cool · exacting — no recent activity', reason: 'x', standing: 30 },
    active_task: null, denial_timers: 0
  }))
}));
// safety store hits the network on confirmStop; stub the api it calls
vi.mock('$lib/api/safety', () => ({
  safeword: vi.fn(async () => ({ scene_halted: true, denial_lifted: 0, merit_penalty: 0, aftercare: 'rest', message: 'stopping' })),
  resume: vi.fn(), getSafety: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: false }))
}));

import Page from './+page.svelte';
import { session } from '$lib/stores/session.svelte';
import { chat } from '$lib/stores/chat.svelte';

beforeEach(() => {
  session.setProfileId('p1');
  chat.messages = [];
});

test('shows the dossier and sends a message', async () => {
  render(Page);
  // dossier line appears after refresh
  expect(await screen.findByText(/cool · exacting/)).toBeInTheDocument();

  const input = screen.getByPlaceholderText(/say something/i) as HTMLTextAreaElement;
  input.value = 'what now?';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  screen.getByRole('button', { name: /send/i }).click();

  expect(await screen.findByText('Acknowledged.')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run** — `npx vitest run src/routes/page.test.ts` → FAIL.

- [ ] **Step 3: Implement** — replace `src/routes/+page.svelte`:
```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores/session.svelte';
  import { chat } from '$lib/stores/chat.svelte';
  import { dossier } from '$lib/stores/dossier.svelte';
  import { safety } from '$lib/stores/safety.svelte';
  import { isSafeword } from '$lib/safety/phrases';
  import Bubble from '$lib/design/components/Bubble.svelte';
  import DossierBar from '$lib/chat/DossierBar.svelte';

  let draft = $state('');

  onMount(async () => {
    if (!session.profileId) {
      await goto('/onboarding/consent');
      return;
    }
    await Promise.all([chat.load(), dossier.refresh()]);
  });

  async function send() {
    const text = draft.trim();
    if (!text) return;
    draft = '';
    // Typed safeword = emergency exit: intercept before any chat call (Addendum A6).
    if (isSafeword(text)) {
      await safety.confirmStop();
      return;
    }
    await chat.send(text);
    await dossier.refresh(); // her reply may have shifted standing
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }
</script>

<div class="home">
  <DossierBar data={dossier.data} />

  <main class="stream">
    {#each chat.messages as m (m.id)}
      <Bubble role={m.role} content={m.content} />
    {/each}
    {#if chat.messages.length === 0}
      <p class="empty label">She is waiting. Say something.</p>
    {/if}
  </main>

  <footer class="composer">
    <textarea
      placeholder="Say something to her…"
      value={draft}
      oninput={(e) => (draft = (e.currentTarget as HTMLTextAreaElement).value)}
      onkeydown={onKey}
      rows="2"
    ></textarea>
    <button class="send" disabled={chat.sending} onclick={send}>Send</button>
  </footer>
</div>

<style>
  .home {
    display: flex;
    flex-direction: column;
    height: 100dvh;
  }
  .stream {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    max-width: 720px;
    width: 100%;
    margin: 0 auto;
    padding: 16px;
  }
  .empty {
    margin: auto;
    color: var(--muted);
  }
  .composer {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    border-top: 1px solid var(--hairline);
    max-width: 720px;
    width: 100%;
    margin: 0 auto;
  }
  textarea {
    flex: 1;
    background: var(--raised);
    color: var(--paper);
    border: 1px solid var(--hairline);
    padding: 10px;
    border-radius: 0;
    resize: none;
    font-family: var(--font-body);
  }
  .send {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: var(--paper);
    color: var(--ink);
    border: 0;
    padding: 0 20px;
    cursor: pointer;
  }
  .send:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
```
(The pinned SAFE button + StopSheet are already mounted globally in `+layout.svelte`; the typed-phrase interceptor here is the second A6 exit.)

- [ ] **Step 4: Run** — `npx vitest run src/routes/page.test.ts` → PASS; `npm run check` clean; `npm run build` succeeds.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/routes/+page.svelte frontend/src/routes/page.test.ts
git commit -m "feat(fe): chat home surface — dossier bar + stream + composer + safeword interceptor"
```

---

## Task 8: Playwright E2E (chat, API mocked)

**Files:** Modify `e2e/fixtures.ts`; create `e2e/chat.spec.ts`.

- [ ] **Step 1: Extend the fixture** — in `e2e/fixtures.ts`, inside `mockApi`'s route handler, add these cases (before the final fallback `return json({}, 200);`):
```ts
    if (path.endsWith('/messages') && method === 'GET') return json([]);
    if (path.endsWith('/chat') && method === 'POST') {
      const body = req.postDataJSON() as { content: string };
      return json({ id: 'm2', role: 'assistant', content: `Heard: ${body.content}`, created_at: 'now' });
    }
    if (path.endsWith('/dossier') && method === 'GET')
      return json({
        rank: 'novice', merit: 0, tokens: 0,
        disposition: { band: 'cool', line: 'cool · exacting — no recent activity', reason: 'x', standing: 30 },
        active_task: null, denial_timers: 0
      });
```

- [ ] **Step 2: Write the spec** — `e2e/chat.spec.ts`:
```ts
import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => localStorage.setItem('smistress.profileId', 'e2e-profile'));
});

test('chat home shows the dossier and exchanges a message', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText(/cool · exacting/)).toBeVisible();

  await page.getByPlaceholder(/say something/i).fill('what now?');
  await page.getByRole('button', { name: /send/i }).click();

  await expect(page.getByText('what now?')).toBeVisible(); // optimistic user bubble
  await expect(page.getByText('Heard: what now?')).toBeVisible(); // her reply
});

test('typed safeword short-circuits to the stop sheet (no chat call)', async ({ page }) => {
  await page.goto('/');
  await page.getByPlaceholder(/say something/i).fill('red');
  await page.getByRole('button', { name: /send/i }).click();
  // the global StopSheet shows the calm receipt; no "Heard: red" bubble
  await expect(page.getByText(/stopping/i)).toBeVisible();
  await expect(page.getByText('Heard: red')).toHaveCount(0);
});
```
(The safeword fixture case already exists from M9b: `/safeword` POST returns the receipt.)

- [ ] **Step 3: Run** — `npm run test:e2e` → all green (M9b specs + the two new chat tests).

- [ ] **Step 4: Commit**
```bash
git add frontend/e2e/fixtures.ts frontend/e2e/chat.spec.ts
git commit -m "test(fe): Playwright E2E — chat exchange + typed-safeword short-circuit"
```

---

## Task 9: Full verification + milestone wrap

**Files:** none — then PR.

- [ ] **Step 1: Backend** — from `backend/`: `uv run pytest -q` (all green incl. new chat tests) and `uv run ruff check .` (clean).
- [ ] **Step 2: Frontend** — from `frontend/`: `npx vitest run`, `npm run check`, `npm run build`, `npm run test:e2e` — all green.
- [ ] **Step 3: Manual smoke (optional, local)** — start backend (`uv run python run_dev.py`) + `npm run dev`; set `SMISTRESS_LLM_BASE_URL=mock` in `backend/.env` if no Ollama is running (the mock provider returns canned replies so the loop is exercisable without an LLM). Walk: onboarding → reveal → chat home; send a message; watch the dossier; type "red" → stop sheet.
- [ ] **Step 4: Push + PR**
```bash
git push -u origin feat/phase-b1-chat
gh pr create --base master --head feat/phase-b1-chat \
  --title "Phase B1: chat surface + live dossier" \
  --body "Chat home over the existing generate_reply turn path (persisted messages, non-streaming) + read-only dossier. Tool-action cards, proof, and economy-from-chat are B2. See docs/superpowers/plans/2026-06-08-phase-b1-chat-and-dossier.md"
```
Confirm CI (backend + frontend + e2e) green.

---

## Verification (end-to-end for B1)

1. **Chat round-trips and persists:** `POST /chat` stores the user turn, runs `generate_reply` over the last 20 turns, stores + returns the reply; `GET /messages` reloads the transcript.
2. **Safety still deterministic:** the typed safeword is intercepted on the input (client `isSafeword`) → `safety.confirmStop()` → the global StopSheet, with no chat call; the backend `generate_reply` independently intercepts safeword/crisis too (defense in depth).
3. **Live dossier:** `GET /dossier` composes rank/merit/tokens + disposition line + active task + denial-timer count; the bar refreshes after each reply and expands to the spokes.
4. **Green:** backend pytest + ruff; frontend Vitest + svelte-check + adapter-node build + Playwright; CI all three jobs.

**B1 is done when** you can hold a persisted conversation with the mistress on the home screen with her live status overhead, and the typed safeword still stops everything instantly — leaving **B2**: her tool-calls → inline action cards (assign task / denial / tokens), proof capture, economy mutations from chat, and (optionally) token streaming.

---

## Self-Review

**Spec coverage (Addendum A5/A7, Phase B "chat + live dossier" slice):**
- A5 chat surface, her bubbles (`--raised` + crimson left hairline) vs sub bubbles (gray, right) → Task 6. ✓
- A5 disposition line (mono, mood + reason) under the dossier → Tasks 3 (dossier.disposition.line) + 6. ✓
- A5 dossier expands in place into status + spokes → Task 6 (`expanded`). ✓
- A5 "safeword pinned to the input bar at all times" → global SAFE button (M9b) + typed-phrase interceptor → Task 7. ✓
- A7 `chat` + `dossier` runes stores → Task 5. ✓
- A7 BFF: chat/dossier go through `/api/...` proxy (existing) → Tasks 4–8. ✓
- Persisted conversation (reload-safe) → Tasks 1–3. ✓
- **Deferred to B2 (explicit, not gaps):** tool-action cards (A5 "tool actions render as structured cards"), proof capture, economy-from-chat, streaming. `generate_reply` is used without tools.

**Placeholder scan:** every step ships complete code. No TODOs in shipped code beyond the documented B2 seams.

**Type/name consistency:** `chat_svc.post_message/list_messages/build_dossier` used by `app/api/chat.py`; `Message(role, content)` consistent model↔schema↔store; `Dossier`/`Message` TS interfaces match `DossierOut`/`MessageOut`; `chat.send/load/messages/sending` and `dossier.refresh/data` used by `+page.svelte` and tests; `isSafeword` used by the composer. Migration `down_revision='f3a9c1b2d4e5'` chains the current head. `get_provider` is re-declared in `app/api/chat.py` (not imported from `main`) and is the override point in the API test.

---

## Notes for execution
- **Branch:** `feat/phase-b1-chat` (not `master`). After merge: `git checkout master && git fetch origin --prune && git reset --hard origin/master`.
- **Backend dev caveat:** clear `PYTHONHOME`/`PYTHONPATH` before `uv`. Run the dev server with `uv run python run_dev.py` (Windows Selector-loop launcher).
- **No PG enums** in the new migration (`message` uses plain String/Text columns).
- **LLM for real replies:** `generate_reply` calls the configured provider. With no Ollama running, set `SMISTRESS_LLM_BASE_URL=mock` to use the in-memory `MockLLMProvider`. Tests always inject `MockLLMProvider` via the `get_provider` dependency override — they never need a real LLM.
- **Regenerate OpenAPI types** after the backend lands: from `frontend/`, `npm run gen:api` (needs the backend importable via `uv`) and commit the `src/lib/types/api.ts` diff. (The hand-typed `chat.ts`/`dossier.ts` modules don't depend on it, but keep the committed types current.)
- **B2 (deferred):** LLM tool-calling → `assign_task`/`set_denial_timer`/`grant_tokens` rendered as inline structured cards, proof capture (photo/video/timer/honor) in the stream, economy mutations from chat, and optional SSE streaming.
```
