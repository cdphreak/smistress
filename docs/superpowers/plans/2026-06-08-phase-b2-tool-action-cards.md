# Phase B2 — Tool-Action Cards (assign / denial / tokens) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the mistress *act* mid-conversation — assign a task, set a denial timer, or grant tokens — via a model-agnostic structured directive the backend parses and executes against the real loop/economy, rendered as an inline card in the chat stream.

**Architecture:** The persona prompt invites an optional fenced ` ```action {json}``` ` block at the end of a reply. After `generate_reply`, the chat service parses that block (pure function), executes the named tool against the existing `loop`/`economy` services, **strips it from the displayed text**, and stores the executed result as the message's `action` (a JSONB column). The frontend renders an `ActionCard` under the bubble; the dossier already refreshes after each turn. No native LLM tool-calling — works with any provider (incl. the local Gemma) and is deterministic to test.

**Tech Stack:** Backend — Python 3.12, FastAPI, SQLAlchemy 2.0 async (JSONB), Alembic, pytest (`MockLLMProvider`). Frontend — SvelteKit 2, Svelte 5 runes, Vitest, Playwright (API mocked).

---

## Scope (B2 of Phase B)

**In:** the `action` directive parser; execution of `assign_task`, `set_denial_timer`, `grant_tokens` against the live services; persisted per-message `action`; the persona prompt's tool instructions; inline `ActionCard` rendering; dossier refresh (already wired).

**Out (B3+):** proof capture (DO→PROVE→VERIFY from chat), photo/video media upload + vision, `trigger_aftercare`/`adjust_economy` tools, revoke/spend tokens, streaming. (`revoke` isn't exposed; only grants in B2.)

---

## Background (already in place — do not rebuild)

- B1: `Message(id, profile_id, role, content, created_at)` + `message` table (head migration `c4d5e6f7a8b9`); `app/chat/service.py::post_message(session, profile_id, content, provider, store)` stores the user turn, runs `persona.generate_reply`, stores + returns the assistant `Message`; `build_dossier`; `POST /chat`/`GET /messages`/`GET /dossier`; `MessageOut(id, role, content, created_at)`. Frontend chat surface (`/`), `chat`/`dossier` stores, `Bubble`, `DossierBar`; `Message` TS interface in `src/lib/api/chat.ts`. The chat home calls `dossier.refresh()` after each send.
- `loop.service.assign_task(session, profile_id, *, description, proof_requirement: ProofRequirement, deadline=None, merit_reward=0, merit_fail_penalty=0, merit_miss_penalty=0, required_seconds=None) -> Task`. `ProofRequirement` values: `photo|video|timer|honor|none` (`app/db/enums.py`).
- `economy.service.set_denial_timer(session, profile_id, *, reason, ends_at) -> DenialTimer`; `grant_tokens(session, profile_id, amount) -> EconomyState` (amount must be ≥ 0; raises `ValueError` if negative).
- `persona.compiler.compile_system_prompt(*, character_block, authoritative_state, disposition, memory=None)` joins: character → SAFETY → AUTHORITATIVE STATE → disposition → MEMORY. `generate_reply` runs the hard-limit output filter on the model's text (so an action block naming a hard limit is filtered just like prose).

**Branch:** `feat/phase-b2-tools`. Backend dev: clear `PYTHONHOME`/`PYTHONPATH` before `uv`; run with `uv run python run_dev.py`. No backend needed for frontend tests.

---

## File structure

**Backend — create:** `app/chat/tools.py` (parse + execute), `alembic/versions/d5e6f7a8b9c0_add_message_action.py`, `tests/chat/test_tools.py`.
**Backend — modify:** `app/db/models/message.py` (`action` JSONB), `app/schemas/chat.py` (`MessageOut.action`), `app/persona/compiler.py` (`_TOOLS_BLOCK`), `app/chat/service.py` (parse→execute→persist), `tests/chat/test_chat_service.py`, `tests/api/test_chat_api.py`, `tests/persona/test_compiler.py`, `tests/db/test_message_model.py`.
**Frontend — create:** `src/lib/chat/ActionCard.svelte`, `src/lib/chat/ActionCard.test.ts`, `e2e/chat_actions.spec.ts`.
**Frontend — modify:** `src/lib/api/chat.ts` (`action` on `Message` + `ActionCard` type), `src/routes/+page.svelte` (render card), `e2e/fixtures.ts`.

---

## Task 1: `message.action` column + migration + schema

**Files:** Modify `app/db/models/message.py`, `app/schemas/chat.py`, `tests/db/test_message_model.py`; create `alembic/versions/d5e6f7a8b9c0_add_message_action.py`.

- [ ] **Step 1: Extend the model test** — append to `tests/db/test_message_model.py`:
```python
async def test_message_stores_action_json(session):
    from app.db.models.message import Message
    from app.schemas.onboarding import ProfileCreate
    from app.services import profile as profile_svc

    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    m = Message(profile_id=p.id, role="assistant", content="On the board.",
                action={"tool": "assign_task", "description": "Posture drill"})
    session.add(m)
    await session.flush()
    await session.refresh(m)
    assert m.action["tool"] == "assign_task"
```

- [ ] **Step 2: Run** — `uv run pytest tests/db/test_message_model.py -q` → FAIL (no `action`).

- [ ] **Step 3a: Model** — in `app/db/models/message.py`, add the JSONB import and column. Add to imports:
```python
from sqlalchemy.dialects.postgresql import JSONB
```
and add the column after `content`:
```python
    action: Mapped[dict | None] = mapped_column(JSONB, default=None, nullable=True)
```

- [ ] **Step 3b: Migration** — `alembic/versions/d5e6f7a8b9c0_add_message_action.py`:
```python
"""add message.action

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('message', sa.Column('action', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('message', 'action')
```

- [ ] **Step 3c: Schema** — in `app/schemas/chat.py`, add `action` to `MessageOut`:
```python
class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    action: dict | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 4: Run** — `uv run pytest tests/db/test_message_model.py tests/db/test_migration.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/db/models/message.py backend/app/schemas/chat.py backend/alembic/versions/d5e6f7a8b9c0_add_message_action.py backend/tests/db/test_message_model.py
git commit -m "feat(chat): message.action JSONB column for tool-action cards"
```

---

## Task 2: Action directive — parse + execute

**Files:** Create `app/chat/tools.py`, `tests/chat/test_tools.py`.

- [ ] **Step 1: Write the failing tests** — `tests/chat/test_tools.py`:
```python
from datetime import datetime, timezone

from app.chat import tools
from app.db.enums import TaskStatus
from app.economy import service as econ_svc
from app.loop import service as loop_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


def test_parse_action_extracts_and_strips_block():
    text = 'Kneel and report, pet.\n```action\n{"tool": "grant_tokens", "amount": 2}\n```'
    clean, action = tools.parse_action(text)
    assert clean == "Kneel and report, pet."
    assert action == {"tool": "grant_tokens", "amount": 2}


def test_parse_action_no_block_returns_text_and_none():
    clean, action = tools.parse_action("Just words, no action.")
    assert clean == "Just words, no action."
    assert action is None


def test_parse_action_malformed_json_strips_block_and_returns_none():
    clean, action = tools.parse_action("Hi.\n```action\n{not json}\n```")
    assert clean == "Hi."
    assert action is None


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_execute_assign_task_creates_task(session):
    p = await _profile(session)
    card = await tools.execute_action(
        session, p.id,
        {"tool": "assign_task", "description": "Posture drill", "proof": "honor", "merit_reward": 10},
    )
    assert card["tool"] == "assign_task"
    assert card["description"] == "Posture drill"
    assert card["proof"] == "honor"
    from sqlalchemy import select
    from app.db.models.task import Task
    tasks = (await session.execute(select(Task).where(Task.profile_id == p.id))).scalars().all()
    assert len(tasks) == 1 and tasks[0].status is TaskStatus.ASSIGNED


async def test_execute_grant_tokens_and_denial(session):
    p = await _profile(session)
    card = await tools.execute_action(session, p.id, {"tool": "grant_tokens", "amount": 3})
    assert card == {"tool": "grant_tokens", "amount": 3, "reason": ""}
    assert (await econ_svc.get_economy(session, p.id)).tokens == 3

    card = await tools.execute_action(
        session, p.id, {"tool": "set_denial_timer", "hours": 12, "reason": "discipline"}
    )
    assert card["tool"] == "set_denial_timer" and card["hours"] == 12
    assert len(await econ_svc.active_denial_timers(session, p.id)) == 1


async def test_execute_unknown_or_bad_returns_error_card(session):
    p = await _profile(session)
    assert (await tools.execute_action(session, p.id, {"tool": "nope"}))["error"]
    bad = await tools.execute_action(session, p.id, {"tool": "grant_tokens", "amount": 0})
    assert "error" in bad
```

- [ ] **Step 2: Run** — `uv run pytest tests/chat/test_tools.py -q` → FAIL (no module).

- [ ] **Step 3: Implement** — `app/chat/tools.py`:
```python
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ProofRequirement
from app.economy import service as econ_svc
from app.loop import service as loop_svc

# Optional fenced directive the persona may append to a reply. Parsed + stripped
# server-side, then executed against the loop/economy. Model-agnostic (no native
# tool-calling), so any provider works and tests stay deterministic.
_ACTION_RE = re.compile(r"```action\s*(\{.*?\})\s*```", re.DOTALL)


def parse_action(text: str) -> tuple[str, dict | None]:
    """Return (text_without_block, action_dict_or_None).

    The block is always stripped if present; the action is None when there is no
    block or the JSON is malformed.
    """
    match = _ACTION_RE.search(text)
    if not match:
        return text.strip(), None
    clean = (text[: match.start()] + text[match.end():]).strip()
    try:
        action = json.loads(match.group(1))
    except json.JSONDecodeError:
        return clean, None
    return clean, action if isinstance(action, dict) else None


async def execute_action(
    session: AsyncSession, profile_id: uuid.UUID, action: dict
) -> dict:
    """Execute one tool against the live services; return a card dict (caller commits).

    Bad input never raises — it returns a card carrying an ``error`` so the turn
    still completes and the issue is visible.
    """
    tool = action.get("tool")
    try:
        if tool == "assign_task":
            proof = ProofRequirement(action.get("proof", "honor"))
            deadline = None
            if action.get("deadline_hours"):
                deadline = datetime.now(timezone.utc) + timedelta(
                    hours=int(action["deadline_hours"])
                )
            required_seconds = (
                int(action["timer_seconds"]) if action.get("timer_seconds") else None
            )
            task = await loop_svc.assign_task(
                session,
                profile_id,
                description=str(action["description"]),
                proof_requirement=proof,
                deadline=deadline,
                merit_reward=int(action.get("merit_reward", 0)),
                merit_miss_penalty=int(action.get("merit_miss_penalty", 0)),
                required_seconds=required_seconds,
            )
            return {
                "tool": "assign_task",
                "task_id": str(task.id),
                "description": task.description,
                "proof": proof.value,
                "merit_reward": task.merit_reward,
            }
        if tool == "set_denial_timer":
            hours = int(action["hours"])
            ends_at = datetime.now(timezone.utc) + timedelta(hours=hours)
            await econ_svc.set_denial_timer(
                session, profile_id, reason=str(action.get("reason", "")), ends_at=ends_at
            )
            return {"tool": "set_denial_timer", "hours": hours, "reason": action.get("reason", "")}
        if tool == "grant_tokens":
            amount = int(action["amount"])
            if amount < 1:
                return {"tool": "grant_tokens", "error": "amount must be >= 1"}
            await econ_svc.grant_tokens(session, profile_id, amount)
            return {"tool": "grant_tokens", "amount": amount, "reason": action.get("reason", "")}
    except (KeyError, ValueError, TypeError) as exc:
        return {"tool": tool or "unknown", "error": str(exc)}
    return {"tool": tool or "unknown", "error": "unknown tool"}
```

- [ ] **Step 4: Run** — `uv run pytest tests/chat/test_tools.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/chat/tools.py backend/tests/chat/test_tools.py
git commit -m "feat(chat): action directive parser + executor (assign/denial/tokens)"
```

---

## Task 3: Tool instructions in the persona prompt

**Files:** Modify `app/persona/compiler.py`, `tests/persona/test_compiler.py`.

- [ ] **Step 1: Add the failing test** — append to `tests/persona/test_compiler.py`:
```python
def test_prompt_describes_the_action_tools():
    disp = compute_disposition(0, [], warmth=30, ceiling=100)
    prompt = compile_system_prompt(
        character_block="x", authoritative_state="y", disposition=disp, memory=None
    )
    assert "```action" in prompt
    assert "assign_task" in prompt
    assert "set_denial_timer" in prompt
    assert "grant_tokens" in prompt
```

- [ ] **Step 2: Run** — `uv run pytest tests/persona/test_compiler.py -q` → the new test FAILs.

- [ ] **Step 3: Implement** — in `app/persona/compiler.py`, add the constant after `_SAFETY_BLOCK`:
```python
_TOOLS_BLOCK = """## ACTIONS (optional)
You may act on the training by appending EXACTLY ONE fenced block at the very end of
your reply. The block is parsed by the system and never shown to the user: write your
in-character message first, then the block. Only act when it advances the training, and
never reference a hard limit in a task.

Format:
```action
{"tool": "<name>", ...fields}
```

Tools:
- assign_task — description (str), proof ("photo"|"video"|"timer"|"honor"|"none"),
  merit_reward (int), merit_miss_penalty (int), deadline_hours (int, optional),
  timer_seconds (int, only when proof is "timer").
- set_denial_timer — hours (int), reason (str).
- grant_tokens — amount (int >= 1), reason (str).

Omit the block entirely when you are not acting."""
```
and insert it into the returned join (between the disposition block and the memory block):
```python
    return "\n\n".join(
        [
            character_block,
            _SAFETY_BLOCK,
            "## AUTHORITATIVE STATE (verbatim — never contradict or paraphrase)\n"
            + authoritative_state,
            disposition_block,
            _TOOLS_BLOCK,
            memory_block,
        ]
    )
```

- [ ] **Step 4: Run** — `uv run pytest tests/persona/test_compiler.py tests/persona -q` → PASS (new test + the existing persona suite — substring assertions are unaffected).

- [ ] **Step 5: Commit**
```bash
git add backend/app/persona/compiler.py backend/tests/persona/test_compiler.py
git commit -m "feat(persona): describe the action tools in the system prompt"
```

---

## Task 4: Wire actions into the chat turn + API

**Files:** Modify `app/chat/service.py`, `tests/chat/test_chat_service.py`, `tests/api/test_chat_api.py`.

- [ ] **Step 1: Add the failing tests** — append to `tests/chat/test_chat_service.py`:
```python
async def test_post_message_executes_action_and_strips_block(session):
    from sqlalchemy import select
    from app.db.models.task import Task

    p = await _profile(session)
    scripted = 'On the board, pet.\n```action\n{"tool": "assign_task", "description": "Posture drill", "proof": "honor", "merit_reward": 10}\n```'
    provider = MockLLMProvider(scripted=[ChatResult(content=scripted)])
    reply = await chat_svc.post_message(session, p.id, "give me a task", provider, NullMemoryStore())

    assert reply.content == "On the board, pet."          # block stripped
    assert reply.action["tool"] == "assign_task"          # action recorded
    tasks = (await session.execute(select(Task).where(Task.profile_id == p.id))).scalars().all()
    assert len(tasks) == 1                                # task actually created


async def test_post_message_without_action_has_none(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[ChatResult(content="Just words.")])
    reply = await chat_svc.post_message(session, p.id, "hi", provider, NullMemoryStore())
    assert reply.content == "Just words."
    assert reply.action is None
```
and append to `tests/api/test_chat_api.py` (the fixture's MockLLMProvider returns a plain reply, so override per-test):
```python
async def test_chat_returns_action_card(client, session):
    pid = await _new_profile(client)
    from app.api import chat as chat_api
    from app.llm.mock import MockLLMProvider
    from app.llm.types import ChatResult
    from app.main import app
    app.dependency_overrides[chat_api.get_provider] = lambda: MockLLMProvider(
        scripted=[ChatResult(content='Kneel.\n```action\n{"tool":"grant_tokens","amount":2}\n```')]
    )
    r = await client.post(f"/profile/{pid}/chat", json={"content": "reward me"})
    assert r.status_code == 200
    body = r.json()
    assert body["content"] == "Kneel."
    assert body["action"]["tool"] == "grant_tokens"
    assert body["action"]["amount"] == 2
```
(Note: the `client` fixture already sets a default provider override and clears overrides on teardown; re-overriding inside the test is fine. Add `session` to this test's parameters so it shares the same DB session as the client.)

- [ ] **Step 2: Run** — `uv run pytest tests/chat/test_chat_service.py tests/api/test_chat_api.py -q` → the new tests FAIL (action not parsed/persisted).

- [ ] **Step 3: Implement** — in `app/chat/service.py`, import the tools module and wire parse→execute→persist. Add to imports:
```python
from app.chat import tools
```
Replace the reply-construction tail of `post_message` (everything after the `generate_reply` call) with:
```python
    result = await persona_svc.generate_reply(
        session, profile_id, conversation, provider, store=store
    )

    clean, action = tools.parse_action(result.content)
    card = await tools.execute_action(session, profile_id, action) if action else None

    reply = Message(profile_id=profile_id, role="assistant", content=clean, action=card)
    session.add(reply)
    await session.flush()
    return reply
```

- [ ] **Step 4: Run** — `uv run pytest tests/chat/test_chat_service.py tests/api/test_chat_api.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/chat/service.py backend/tests/chat/test_chat_service.py backend/tests/api/test_chat_api.py
git commit -m "feat(chat): parse + execute the action directive per turn, persist the card"
```

---

## Task 5: Frontend ActionCard + render in the stream

**Files:** Modify `src/lib/api/chat.ts`, `src/routes/+page.svelte`; create `src/lib/chat/ActionCard.svelte`, `src/lib/chat/ActionCard.test.ts`.

- [ ] **Step 1: Write the failing test** — `src/lib/chat/ActionCard.test.ts`:
```ts
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import ActionCard from './ActionCard.svelte';

test('renders an assign_task card', () => {
  render(ActionCard, {
    action: { tool: 'assign_task', description: 'Posture drill', proof: 'honor', merit_reward: 10 }
  });
  expect(screen.getByText(/task assigned/i)).toBeInTheDocument();
  expect(screen.getByText(/Posture drill/)).toBeInTheDocument();
  expect(screen.getByText(/honor/)).toBeInTheDocument();
});

test('renders a grant_tokens card', () => {
  render(ActionCard, { action: { tool: 'grant_tokens', amount: 2 } });
  expect(screen.getByText(/\+2 tokens/i)).toBeInTheDocument();
});

test('renders an error card', () => {
  render(ActionCard, { action: { tool: 'grant_tokens', error: 'amount must be >= 1' } });
  expect(screen.getByText(/couldn’t|error/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run** — `npx vitest run src/lib/chat/ActionCard.test.ts` → FAIL.

- [ ] **Step 3a: Type** — in `src/lib/api/chat.ts`, add the action type and field:
```ts
export interface ActionCard {
  tool: string;
  description?: string;
  proof?: string;
  merit_reward?: number;
  hours?: number;
  reason?: string;
  amount?: number;
  task_id?: string;
  error?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  action?: ActionCard | null;
  created_at: string;
}
```

- [ ] **Step 3b: Component** — `src/lib/chat/ActionCard.svelte`:
```svelte
<script lang="ts">
  import type { ActionCard } from '$lib/api/chat';
  let { action }: { action: ActionCard } = $props();

  const title = $derived(
    action.error
      ? 'Action failed'
      : action.tool === 'assign_task'
        ? 'Task assigned'
        : action.tool === 'set_denial_timer'
          ? 'Denial set'
          : action.tool === 'grant_tokens'
            ? 'Tokens granted'
            : 'Action'
  );
</script>

<div class="card" class:err={!!action.error}>
  <span class="label">{title}</span>
  {#if action.error}
    <p>She couldn’t: {action.error}</p>
  {:else if action.tool === 'assign_task'}
    <p class="ledger">{action.description} · proof: {action.proof} · +{action.merit_reward} merit</p>
  {:else if action.tool === 'set_denial_timer'}
    <p class="ledger">{action.hours}h{action.reason ? ` · ${action.reason}` : ''}</p>
  {:else if action.tool === 'grant_tokens'}
    <p class="ledger">+{action.amount} tokens{action.reason ? ` · ${action.reason}` : ''}</p>
  {/if}
</div>

<style>
  .card {
    align-self: flex-start;
    max-width: 78%;
    margin: 2px 0 10px;
    padding: 8px 12px;
    border: 1px solid var(--accent);
    background: var(--ink);
  }
  .card.err {
    border-color: var(--accent-muted);
  }
  .ledger {
    font-family: var(--font-mono);
    margin: 4px 0 0;
    font-size: 0.85rem;
  }
</style>
```

- [ ] **Step 3c: Render in the stream** — in `src/routes/+page.svelte`, import the card and render it after each assistant bubble. Add the import:
```svelte
  import ActionCard from '$lib/chat/ActionCard.svelte';
```
and replace the `{#each chat.messages ...}` block with:
```svelte
    {#each chat.messages as m (m.id)}
      <Bubble role={m.role} content={m.content} />
      {#if m.action}
        <ActionCard action={m.action} />
      {/if}
    {/each}
```

- [ ] **Step 4: Run** — `npx vitest run src/lib/chat/ActionCard.test.ts` → PASS; `npm run check` clean; `npm run build` succeeds.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/api/chat.ts frontend/src/lib/chat/ActionCard.svelte frontend/src/lib/chat/ActionCard.test.ts frontend/src/routes/+page.svelte
git commit -m "feat(fe): inline ActionCard rendered under the mistress's bubble"
```

---

## Task 6: Playwright — action card e2e

**Files:** Modify `e2e/fixtures.ts`; create `e2e/chat_actions.spec.ts`.

- [ ] **Step 1: Make the chat stub action-aware** — in `e2e/fixtures.ts`, replace the existing `/chat` POST case with one that echoes an action when the user asks for a task:
```ts
    if (path.endsWith('/chat') && method === 'POST') {
      const body = req.postDataJSON() as { content: string };
      const wantsTask = /task/i.test(body.content);
      return json({
        id: 'm2',
        role: 'assistant',
        content: `Heard: ${body.content}`,
        action: wantsTask
          ? { tool: 'assign_task', description: 'Posture drill', proof: 'honor', merit_reward: 10 }
          : null,
        created_at: 'now'
      });
    }
```

- [ ] **Step 2: Write the spec** — `e2e/chat_actions.spec.ts`:
```ts
import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => localStorage.setItem('smistress.profileId', 'e2e-profile'));
});

test('an assign_task reply renders an inline action card', async ({ page }) => {
  await page.goto('/');
  await page.getByPlaceholder(/say something/i).fill('give me a task');
  await page.getByRole('button', { name: /send/i }).click();

  await expect(page.getByText('Heard: give me a task')).toBeVisible(); // her bubble
  await expect(page.getByText(/task assigned/i)).toBeVisible(); // the card
  await expect(page.getByText(/Posture drill/)).toBeVisible();
});
```

- [ ] **Step 3: Run** — `npm run test:e2e` → all green (B1 chat specs + the new action card spec).

- [ ] **Step 4: Commit**
```bash
git add frontend/e2e/fixtures.ts frontend/e2e/chat_actions.spec.ts
git commit -m "test(fe): Playwright E2E — inline action card on assign_task"
```

---

## Task 7: Full verification + milestone wrap

**Files:** none — then PR.

- [ ] **Step 1: Backend** — from `backend/`: `uv run pytest -q` (all green) and `uv run ruff check .` (clean).
- [ ] **Step 2: Frontend** — from `frontend/`: `npx vitest run`, `npm run check`, `npm run build`, `npm run test:e2e` — all green. Then `npm run gen:api` and commit the regenerated `src/lib/types/api.ts` (the `MessageOut.action` field).
- [ ] **Step 3: Manual smoke (optional, local)** — with the dev servers up (Gemma model), tell her "give me a task" and confirm a task card appears and the dossier's active-task line updates; "lock me up for 6 hours" → a denial card + the dossier denial-timer count. (Local models vary — the directive may not always fire; the deterministic tests are the guarantee.)
- [ ] **Step 4: Push + PR**
```bash
git push -u origin feat/phase-b2-tools
gh pr create --base master --head feat/phase-b2-tools \
  --title "Phase B2: tool-action cards (assign / denial / tokens)" \
  --body "The mistress acts via a server-parsed action directive -> loop/economy -> inline cards. Proof capture is B3. See docs/superpowers/plans/2026-06-08-phase-b2-tool-action-cards.md"
```
Confirm CI (backend + frontend + e2e) green.

---

## Verification (end-to-end for B2)

1. **Directive parsed + stripped:** `parse_action` pulls the fenced block out of the reply (malformed JSON → block stripped, action None); the user never sees raw JSON.
2. **Executed against real services:** `assign_task` creates an `ASSIGNED` Task; `set_denial_timer` adds an active timer; `grant_tokens` raises the balance. Bad input returns an error card, never a 500.
3. **Persisted + rendered:** the assistant `Message.action` holds the executed card; `GET /messages` replays it; the frontend renders an `ActionCard` under the bubble; the dossier refresh after each turn reflects the change (new active task / denial count / tokens).
4. **Model-agnostic + safe:** no native tool-calling — works with any provider; the hard-limit output filter still scans the reply (incl. any action block) before it's shown.
5. **Green:** backend pytest + ruff; frontend Vitest + svelte-check + build + Playwright; CI all three jobs.

**B2 is done when** the mistress can assign a task / set denial / grant tokens from chat and you see the card inline with the dossier updating — leaving **B3**: proof capture (DO→PROVE→VERIFY in chat), then media upload + vision, and the remaining tools (`trigger_aftercare`, token spend/revoke), plus optional streaming.

---

## Self-Review

**Spec coverage (Addendum A5 "tool actions render as structured cards inline"; spec §6 tools):**
- A5 tool action → inline card → Tasks 4 (persist), 5 (render). ✓
- §6 `assign_task` (with proof requirement), `set_denial_timer`, `adjust_economy` (grant side) → Task 2. ✓ (`request_proof`/proof flow + `trigger_aftercare` + token spend → B3, explicit.)
- "chat and authoritative state can never silently disagree" (A5): the action mutates the real loop/economy and the dossier refreshes → Tasks 4, 5 + B1 refresh. ✓
- Safety: the action block is part of the model text the hard-limit filter already scans (B1 `generate_reply`); the prompt tells her never to name a hard limit in a task (Task 3). ✓
- Provider-swappability (§10): server-parsed directive, no native tool-calling → Task 2. ✓

**Placeholder scan:** every step ships complete code. Deferrals (proof capture, media/vision, aftercare/spend tools, streaming) are explicit B3 seams, not placeholders.

**Type/name consistency:** `tools.parse_action`/`execute_action` used by `chat.service.post_message`; the card dict shape (`tool`, `description`, `proof`, `merit_reward`, `hours`, `reason`, `amount`, `task_id`, `error`) matches the `ActionCard` TS interface and the `ActionCard.svelte` branches; `MessageOut.action` ↔ `Message.action`. Migration `down_revision='c4d5e6f7a8b9'` chains the B1 head. Prompt tool names (`assign_task`/`set_denial_timer`/`grant_tokens`) match the executor's dispatch and the parser's expectations.

---

## Notes for execution
- **Branch:** `feat/phase-b2-tools` (not `master`). After merge: realign master; the dev backend needs `alembic upgrade head` (the `message.action` migration) + a restart to serve B2.
- **Backend dev caveat:** clear `PYTHONHOME`/`PYTHONPATH` before `uv`; `uv run python run_dev.py`.
- **No PG enums** in the migration (`action` is JSONB). Round-trip test covers it.
- **Local model variance:** whether the Gemma model emits a well-formed `action` block is up to the model; the directive is best-effort in-app. The deterministic tests (MockLLMProvider emitting the block) are the contract. A capable model will act; a weak one simply won't — no crash either way.
- **B3 (deferred):** proof capture (honor/timer submit→verify in chat), media upload + vision verification, `trigger_aftercare`/token-spend/revoke tools, optional SSE streaming.
```
