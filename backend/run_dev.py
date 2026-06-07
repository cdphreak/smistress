"""Local dev launcher (Windows-safe).

uvicorn's default event-loop setup on Windows uses the ProactorEventLoop, which
psycopg's async driver cannot use. We explicitly create a SelectorEventLoop and
run the server inside it. Harmless on other platforms. Dev-only; not used in prod
(the VPS runs Linux, where the default loop is already selector-based).
"""
from __future__ import annotations

import asyncio
import selectors

import uvicorn

loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
asyncio.set_event_loop(loop)

config = uvicorn.Config("app.main:app", host="127.0.0.1", port=8000, log_level="info")
server = uvicorn.Server(config)
loop.run_until_complete(server.serve())
