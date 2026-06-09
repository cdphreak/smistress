from __future__ import annotations

import asyncio
import sys

import psycopg
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# psycopg's async driver cannot run on Windows' default ProactorEventLoop.
# No-op on Linux (VPS/CI), where the default loop is already selector-based.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import app.db.models  # noqa: F401  -- registers all models on Base.metadata
from app.config import Settings
from app.db.base import Base

settings = Settings()

# Admin DSN to the always-present "postgres" maintenance DB (libpq keyword form).
_ADMIN_DSN = "host=localhost port=5432 user=smistress password=smistress dbname=postgres"


def _ensure_test_database() -> None:
    with psycopg.connect(_ADMIN_DSN, autocommit=True) as conn:
        row = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'smistress_test'"
        ).fetchone()
        if row is None:
            conn.execute("CREATE DATABASE smistress_test")


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    _ensure_test_database()
    engine = create_async_engine(settings.test_database_url)
    async with engine.begin() as conn:
        # Drop tables that were removed from Base.metadata but may still exist in the
        # test DB from a previous run (e.g. denial_timer, removed in M4a Task 2).
        await conn.execute(
            __import__("sqlalchemy").text("DROP TABLE IF EXISTS denial_timer CASCADE")
        )
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()
