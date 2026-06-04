# smistress v1 — Core Obedience Loop — Implementation Plan (Milestone 1: Foundation)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the smistress backend foundation — a Python/FastAPI service with a swappable, OpenAI-compatible `LLMProvider` (plus a mock), config, infra (Postgres + FalkorDB via docker-compose), a SvelteKit PWA shell, and CI — so every later milestone builds on a tested skeleton.

**Architecture:** Python 3.12 + FastAPI backend; SvelteKit PWA frontend (pure client). All model calls go through one `LLMProvider` interface speaking the OpenAI Chat Completions API, so OpenAI or any local server (Ollama/vLLM/LM Studio) is pure config. Graphiti (Python) is chosen for memory in a later milestone, which is *why* the backend is Python. Single VPS; docker-compose orchestrates Postgres + FalkorDB.

**Tech Stack:** Python 3.12, `uv`, FastAPI, uvicorn, pydantic-settings, `openai` SDK, pytest + pytest-asyncio, ruff; SvelteKit + `@vite-pwa/sveltekit`; Postgres 16, FalkorDB; GitHub Actions CI.

---

## Context

smistress is a single-user, chat-first AI "mistress" training app (full design: `docs/superpowers/specs/2026-06-04-core-obedience-loop-design.md`). v1 is the **Core Obedience Loop**. Because v1 spans several large subsystems, it is built as a **sequence of milestone plans**, each producing working, testable software. This document fully specifies **Milestone 1 (Foundation)** and outlines the roadmap for M2–M9, which will be written as their own plans once the milestones they depend on exist.

The two design risks (persona quality, strict proof verification) are de-risked later via an eval harness (M4/M6); M1's job is the swappable provider seam + a clean, CI-backed skeleton so nothing downstream is blocked.

---

## v1 Milestone Roadmap (each becomes its own plan)

| M | Name | Produces | Spec § |
|---|------|----------|--------|
| **M1** | **Foundation** (this plan) | FastAPI skeleton, `LLMProvider` + mock, config, compose, PWA shell, CI | §2 |
| M2 | Data layer | Postgres schema + migrations: profile/economy/task/character_model entities | §4, §7 |
| M3 | Onboarding & Profile | BDSM test, kink/limits sheet, toys, SO, goals, character model | §4, §5A |
| M4 | Persona engine | prompt compilation, character-model→prompt, merit/mood disposition, persona eval harness | §5, §5A |
| M5 | Memory | Graphiti/FalkorDB integration, episode write/retrieve, degradation | §3 |
| M6 | The loop | task lifecycle, proof submission, configurable strict verification, verification eval harness | §6 |
| M7 | Economy | merit/rank/tokens/denial timers, invariants service | §7 |
| M8 | Safety | safeword/panic, limit output-filter, aftercare, ceiling clamp | §9 |
| M9 | PWA & E2E | SvelteKit screens, camera/notifications, Playwright E2E | §1, §2 |

---

## File Structure (Milestone 1)

```
smistress/
├─ backend/
│  ├─ pyproject.toml              # uv project, deps, pytest/ruff config
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ config.py                # Settings (pydantic-settings); vision_enabled derived
│  │  ├─ main.py                  # FastAPI app, /health, /llm/ping, provider DI
│  │  └─ llm/
│  │     ├─ __init__.py
│  │     ├─ types.py              # ChatMessage, ToolCall, ChatResult
│  │     ├─ provider.py           # LLMProvider Protocol
│  │     ├─ mock.py               # MockLLMProvider
│  │     ├─ openai_provider.py    # OpenAICompatibleProvider (wraps openai SDK)
│  │     └─ factory.py            # build_provider(settings) -> LLMProvider
│  └─ tests/
│     ├─ test_config.py
│     ├─ llm/test_mock.py
│     ├─ llm/test_openai_provider.py
│     ├─ llm/test_factory.py
│     └─ test_main.py
├─ frontend/                      # SvelteKit PWA (scaffolded in Task 9)
├─ docker-compose.yml             # postgres + falkordb
├─ .env.example
└─ .github/workflows/ci.yml
```

Responsibilities: `llm/` is the swap seam (the only place that knows about OpenAI wire format); `config.py` is the single source of runtime config; `main.py` wires them with FastAPI dependency injection so tests inject the mock.

---

## Task 1: Project scaffold & tooling

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py` (empty), `backend/app/llm/__init__.py` (empty)
- Create: `backend/tests/__init__.py` (empty), `backend/tests/llm/__init__.py` (empty)

- [ ] **Step 1: Create `backend/pyproject.toml`**

```toml
[project]
name = "smistress-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic-settings>=2.4",
  "openai>=1.40",
  "httpx>=0.27",
]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "ruff>=0.6"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

- [ ] **Step 2: Create the empty package/init files** listed above (so `app`, `app.llm`, `tests`, `tests.llm` are importable packages).

- [ ] **Step 3: Install and verify the toolchain**

Run (from `backend/`): `uv sync` then `uv run pytest -q`
Expected: dependencies install; pytest runs and reports **"no tests ran"** (exit 5) — confirms the harness works before any tests exist.

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/app backend/tests
git commit -m "chore: scaffold Python/FastAPI backend with uv + pytest"
```

---

## Task 2: Infra — docker-compose + env example

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: smistress
      POSTGRES_PASSWORD: smistress
      POSTGRES_DB: smistress
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  falkordb:
    image: falkordb/falkordb:latest
    ports: ["6379:6379"]
    volumes: ["falkordata:/data"]
volumes:
  pgdata:
  falkordata:
```

- [ ] **Step 2: Create `.env.example`**

```dotenv
# LLM provider (OpenAI-compatible). Use "mock" as base_url to force the in-memory mock.
SMISTRESS_LLM_BASE_URL=http://localhost:11434/v1
SMISTRESS_LLM_API_KEY=not-needed
SMISTRESS_CHAT_MODEL=llama3.1
# Leave SMISTRESS_VISION_MODEL unset to disable photo/video verification (auto-pass).
# SMISTRESS_VISION_MODEL=gpt-4o
SMISTRESS_DATABASE_URL=postgresql+psycopg://smistress:smistress@localhost:5432/smistress
SMISTRESS_FALKORDB_URL=redis://localhost:6379
```

- [ ] **Step 3: Verify infra starts**

Run: `docker compose up -d` then `docker compose ps`
Expected: `postgres` and `falkordb` both show state `running`/`healthy`. Then `docker compose down`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "chore: add docker-compose (postgres + falkordb) and env example"
```

---

## Task 3: Settings module (config + vision_enabled derivation)

**Files:**
- Create: `backend/app/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config.py
from app.config import Settings


def test_vision_disabled_when_no_vision_model():
    s = Settings(vision_model=None)
    assert s.vision_enabled is False


def test_vision_enabled_when_vision_model_set():
    s = Settings(vision_model="gpt-4o")
    assert s.vision_enabled is True


def test_defaults_present():
    s = Settings()
    assert s.chat_model
    assert s.database_url.startswith("postgresql")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="SMISTRESS_", extra="ignore"
    )

    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "not-needed"
    chat_model: str = "llama3.1"
    vision_model: str | None = None
    database_url: str = "postgresql+psycopg://smistress:smistress@localhost:5432/smistress"
    falkordb_url: str = "redis://localhost:6379"

    @property
    def vision_enabled(self) -> bool:
        return self.vision_model is not None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat: add Settings with derived vision_enabled flag"
```

---

## Task 4: LLM data types

**Files:**
- Create: `backend/app/llm/types.py`
- Test: `backend/tests/llm/test_types.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/llm/test_types.py
from app.llm.types import ChatMessage, ChatResult, ToolCall


def test_chat_result_defaults_to_no_tool_calls():
    r = ChatResult(content="hi")
    assert r.content == "hi"
    assert r.tool_calls == []


def test_tool_call_fields():
    tc = ToolCall(id="1", name="assign_task", arguments='{"x": 1}')
    assert tc.name == "assign_task"


def test_chat_message_role_content():
    m = ChatMessage(role="user", content="ping")
    assert m.role == "user"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm/test_types.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm.types'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/llm/types.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string as returned by the model


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm/test_types.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/types.py backend/tests/llm/test_types.py
git commit -m "feat: add LLM message/result/tool-call types"
```

---

## Task 5: LLMProvider Protocol + MockLLMProvider

**Files:**
- Create: `backend/app/llm/provider.py`
- Create: `backend/app/llm/mock.py`
- Test: `backend/tests/llm/test_mock.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/llm/test_mock.py
import pytest

from app.llm.mock import MockLLMProvider
from app.llm.provider import LLMProvider
from app.llm.types import ChatMessage, ChatResult


def test_mock_satisfies_protocol():
    assert isinstance(MockLLMProvider(), LLMProvider)


async def test_mock_returns_scripted_result_and_records_calls():
    p = MockLLMProvider(scripted=[ChatResult(content="hello")])
    r = await p.chat([ChatMessage(role="user", content="hi")])
    assert r.content == "hello"
    assert p.calls[0][0].content == "hi"


async def test_mock_default_result_when_unscripted():
    p = MockLLMProvider()
    r = await p.chat([ChatMessage(role="user", content="hi")])
    assert r.content == "ok"


def test_mock_vision_flag():
    assert MockLLMProvider(supports_vision=True).supports_vision is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm/test_mock.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm.provider'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/llm/provider.py
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.llm.types import ChatMessage, ChatResult


@runtime_checkable
class LLMProvider(Protocol):
    supports_vision: bool

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> ChatResult: ...
```

```python
# backend/app/llm/mock.py
from __future__ import annotations

from app.llm.types import ChatMessage, ChatResult


class MockLLMProvider:
    """In-memory provider for tests and the "mock" base_url. Records calls; replays scripted results."""

    def __init__(
        self,
        *,
        supports_vision: bool = False,
        scripted: list[ChatResult] | None = None,
    ) -> None:
        self.supports_vision = supports_vision
        self._scripted = list(scripted or [])
        self.calls: list[list[ChatMessage]] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> ChatResult:
        self.calls.append(list(messages))
        if self._scripted:
            return self._scripted.pop(0)
        return ChatResult(content="ok")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm/test_mock.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/provider.py backend/app/llm/mock.py backend/tests/llm/test_mock.py
git commit -m "feat: add LLMProvider protocol and MockLLMProvider"
```

---

## Task 6: OpenAICompatibleProvider

**Files:**
- Create: `backend/app/llm/openai_provider.py`
- Test: `backend/tests/llm/test_openai_provider.py`

- [ ] **Step 1: Write the failing test** (injects a fake client; no network)

```python
# backend/tests/llm/test_openai_provider.py
from types import SimpleNamespace

from app.llm.openai_provider import OpenAICompatibleProvider
from app.llm.types import ChatMessage


class _FakeCompletions:
    def __init__(self, message):
        self._message = message
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=self._message)])


def _fake_client(message):
    return SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(message)))


async def test_parses_plain_content():
    client = _fake_client(SimpleNamespace(content="hi there", tool_calls=None))
    p = OpenAICompatibleProvider(
        base_url="x", api_key="x", default_model="m", supports_vision=False, client=client
    )
    r = await p.chat([ChatMessage(role="user", content="yo")])
    assert r.content == "hi there"
    assert r.tool_calls == []
    assert client.chat.completions.kwargs["model"] == "m"


async def test_parses_tool_calls_and_model_override():
    tc = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="assign_task", arguments='{"title":"x"}'),
    )
    client = _fake_client(SimpleNamespace(content=None, tool_calls=[tc]))
    p = OpenAICompatibleProvider(
        base_url="x", api_key="x", default_model="m", supports_vision=True, client=client
    )
    r = await p.chat([ChatMessage(role="user", content="yo")], model="other")
    assert r.content == ""
    assert r.tool_calls[0].name == "assign_task"
    assert client.chat.completions.kwargs["model"] == "other"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm/test_openai_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm.openai_provider'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/llm/openai_provider.py
from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from app.llm.types import ChatMessage, ChatResult, ToolCall


class OpenAICompatibleProvider:
    """Talks to any OpenAI Chat Completions-compatible endpoint (OpenAI, Ollama, vLLM, ...)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        default_model: str,
        supports_vision: bool,
        client: Any | None = None,
    ) -> None:
        self._client = client or AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._default_model = default_model
        self.supports_vision = supports_vision

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> ChatResult:
        resp = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            tools=tools or None,
        )
        choice = resp.choices[0].message
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
            for tc in (choice.tool_calls or [])
        ]
        return ChatResult(content=choice.content or "", tool_calls=tool_calls)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm/test_openai_provider.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/openai_provider.py backend/tests/llm/test_openai_provider.py
git commit -m "feat: add OpenAI-compatible LLM provider"
```

---

## Task 7: Provider factory

**Files:**
- Create: `backend/app/llm/factory.py`
- Test: `backend/tests/llm/test_factory.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/llm/test_factory.py
from app.config import Settings
from app.llm.factory import build_provider
from app.llm.mock import MockLLMProvider
from app.llm.openai_provider import OpenAICompatibleProvider


def test_factory_returns_mock_when_base_url_is_mock():
    p = build_provider(Settings(llm_base_url="mock", vision_model="gpt-4o"))
    assert isinstance(p, MockLLMProvider)
    assert p.supports_vision is True  # mirrors vision_enabled


def test_factory_returns_openai_provider_otherwise():
    p = build_provider(Settings(llm_base_url="http://localhost:11434/v1", vision_model=None))
    assert isinstance(p, OpenAICompatibleProvider)
    assert p.supports_vision is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm/test_factory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm.factory'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/llm/factory.py
from __future__ import annotations

from app.config import Settings
from app.llm.mock import MockLLMProvider
from app.llm.openai_provider import OpenAICompatibleProvider
from app.llm.provider import LLMProvider


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_base_url == "mock":
        return MockLLMProvider(supports_vision=settings.vision_enabled)
    return OpenAICompatibleProvider(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        default_model=settings.chat_model,
        supports_vision=settings.vision_enabled,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm/test_factory.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/factory.py backend/tests/llm/test_factory.py
git commit -m "feat: add LLM provider factory (mock vs openai-compatible)"
```

---

## Task 8: FastAPI app — /health and /llm/ping with DI

**Files:**
- Create: `backend/app/main.py`
- Test: `backend/tests/test_main.py`

- [ ] **Step 1: Write the failing test** (overrides the provider dependency with the mock)

```python
# backend/tests/test_main.py
from httpx import ASGITransport, AsyncClient

from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.main import app, get_provider


async def test_health_reports_ok_and_vision_flag():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "vision_enabled" in body


async def test_llm_ping_uses_injected_provider():
    app.dependency_overrides[get_provider] = lambda: MockLLMProvider(
        scripted=[ChatResult(content="pong")]
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            r = await ac.post("/llm/ping")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["content"] == "pong"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/main.py
from __future__ import annotations

from fastapi import Depends, FastAPI

from app.config import Settings
from app.llm.factory import build_provider
from app.llm.provider import LLMProvider
from app.llm.types import ChatMessage

settings = Settings()
app = FastAPI(title="smistress")


def get_provider() -> LLMProvider:
    return build_provider(settings)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "vision_enabled": settings.vision_enabled}


@app.post("/llm/ping")
async def llm_ping(provider: LLMProvider = Depends(get_provider)) -> dict:
    result = await provider.chat([ChatMessage(role="user", content="ping")])
    return {"content": result.content}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_main.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the whole suite + lint**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all tests pass; ruff reports no errors.

- [ ] **Step 6: Smoke-run the server manually (optional but recommended)**

Run: `SMISTRESS_LLM_BASE_URL=mock uv run uvicorn app.main:app --port 8000` then in another shell `curl localhost:8000/health` and `curl -X POST localhost:8000/llm/ping`
Expected: `/health` → `{"status":"ok",...}`; `/llm/ping` → `{"content":"ok"}`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/tests/test_main.py
git commit -m "feat: add FastAPI app with /health and /llm/ping via provider DI"
```

---

## Task 9: SvelteKit PWA shell

**Files:**
- Create: `frontend/` (scaffolded), `frontend/vite.config.ts` (PWA plugin), `frontend/src/routes/+page.svelte`, `frontend/src/lib/health.ts`
- Test: `frontend/src/lib/health.test.ts`

- [ ] **Step 1: Scaffold SvelteKit + PWA plugin**

Run (from repo root):
```bash
npx sv create frontend --template minimal --types ts --no-add-ons
cd frontend && npm i && npm i -D @vite-pwa/sveltekit vitest
```
Expected: `frontend/` created; deps install.

- [ ] **Step 2: Write the failing test**

```typescript
// frontend/src/lib/health.test.ts
import { describe, it, expect, vi } from 'vitest';
import { fetchHealth } from './health';

describe('fetchHealth', () => {
  it('returns parsed health json', async () => {
    const mockFetch = vi.fn(async () =>
      new Response(JSON.stringify({ status: 'ok', vision_enabled: false }), { status: 200 })
    );
    const result = await fetchHealth('http://api', mockFetch as unknown as typeof fetch);
    expect(result.status).toBe('ok');
    expect(result.vision_enabled).toBe(false);
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `frontend/`): `npx vitest run src/lib/health.test.ts`
Expected: FAIL — cannot resolve `./health`.

- [ ] **Step 4: Write minimal implementation**

```typescript
// frontend/src/lib/health.ts
export interface Health {
  status: string;
  vision_enabled: boolean;
}

export async function fetchHealth(
  apiBase: string,
  fetchFn: typeof fetch = fetch
): Promise<Health> {
  const res = await fetchFn(`${apiBase}/health`);
  if (!res.ok) throw new Error(`health check failed: ${res.status}`);
  return (await res.json()) as Health;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run (from `frontend/`): `npx vitest run src/lib/health.test.ts`
Expected: 1 passed.

- [ ] **Step 6: Enable the PWA plugin and a minimal landing page**

```typescript
// frontend/vite.config.ts
import { sveltekit } from '@sveltejs/kit/vite';
import { SvelteKitPWA } from '@vite-pwa/sveltekit';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [
    sveltekit(),
    SvelteKitPWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'smistress',
        short_name: 'smistress',
        display: 'standalone',
        background_color: '#000000',
        theme_color: '#000000'
      }
    })
  ]
});
```

```svelte
<!-- frontend/src/routes/+page.svelte -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchHealth, type Health } from '$lib/health';

  let health: Health | null = $state(null);
  let error: string | null = $state(null);
  const apiBase = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

  onMount(async () => {
    try {
      health = await fetchHealth(apiBase);
    } catch (e) {
      error = (e as Error).message;
    }
  });
</script>

<h1>smistress</h1>
{#if error}<p>backend unreachable: {error}</p>
{:else if health}<p>backend: {health.status}</p>
{:else}<p>connecting…</p>{/if}
```

- [ ] **Step 7: Verify build**

Run (from `frontend/`): `npm run build`
Expected: build succeeds; a service worker is emitted (PWA plugin output in the build log).

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat: scaffold SvelteKit PWA shell with backend health check"
```

---

## Task 10: CI (GitHub Actions)

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflow**

```yaml
name: CI
on:
  push:
    branches: ["**"]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run pytest -q

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - run: npm ci
      - run: npx vitest run
      - run: npm run build
```

- [ ] **Step 2: Validate the YAML locally**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"` *(if Python yaml is unavailable, skip — CI itself will validate on push)*
Expected: no error.

- [ ] **Step 3: Commit and push the branch to trigger CI**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add backend + frontend GitHub Actions workflow"
git push -u origin <branch>
```
Expected: both CI jobs go green on GitHub.

---

## Verification (end-to-end for Milestone 1)

1. **Backend unit/integration:** from `backend/`, `uv run pytest -q` → all tests pass (config, llm types, mock, openai provider, factory, main).
2. **Lint:** `uv run ruff check .` → clean.
3. **Provider swap is real:** `SMISTRESS_LLM_BASE_URL=mock uv run uvicorn app.main:app --port 8000`, then `curl -X POST localhost:8000/llm/ping` → `{"content":"ok"}` (no network). Point `SMISTRESS_LLM_BASE_URL`/`SMISTRESS_CHAT_MODEL` at a running Ollama and the same call returns a real completion — proving the seam.
4. **Vision flag derivation:** `/health` with `SMISTRESS_VISION_MODEL` unset → `vision_enabled:false`; set it → `true`.
5. **Infra:** `docker compose up -d` → postgres + falkordb running; `docker compose down` cleans up.
6. **Frontend:** from `frontend/`, `npx vitest run` passes and `npm run build` emits a service worker; `npm run dev` with the backend running shows "backend: ok".
7. **CI:** pushed branch shows both jobs green.

**Milestone 1 is done when:** all of the above pass, and the swappable provider seam + tested skeleton exist for M2 to build the data layer on.

---

## Notes for execution

- This plan file lives in the plans workspace; at execution time, copy it to `docs/superpowers/plans/2026-06-04-core-obedience-loop-m1-foundation.md` in the repo and commit it (plan mode prevented writing there directly).
- Work on a branch (e.g., `feat/m1-foundation`), not `master`.
- M2–M9 each get their own plan, written when reached, reflecting what earlier milestones actually produced.
- `npx sv create` flags can shift between versions; if the exact invocation in Task 9 Step 1 differs, accept the interactive defaults for a **minimal, TypeScript** skeleton — the rest of the task is unaffected.
