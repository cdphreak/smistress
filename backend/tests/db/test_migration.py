import os
import subprocess
from pathlib import Path

import psycopg
from sqlalchemy import create_engine, text

import app.db.models  # noqa: F401  -- registers all models on Base.metadata
from app.db.base import Base

BACKEND = Path(__file__).resolve().parents[2]
TEST_URL = "postgresql+psycopg://smistress:smistress@localhost:5432/smistress_test"
_ADMIN_DSN = "host=localhost port=5432 user=smistress password=smistress dbname=postgres"
_ENUM_TYPES = ("kink_rating", "goal_status", "proof_requirement", "task_status")


def _ensure_test_database() -> None:
    with psycopg.connect(_ADMIN_DSN, autocommit=True) as conn:
        row = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'smistress_test'"
        ).fetchone()
        if row is None:
            conn.execute("CREATE DATABASE smistress_test")


def _clear_schema() -> None:
    """Drop everything Alembic owns so the round-trip starts from a truly empty DB.

    Other tests build the schema with Base.metadata.create_all (no alembic_version),
    so we cannot assume Alembic is the only thing that has touched this database.
    """
    engine = create_engine(TEST_URL)
    Base.metadata.drop_all(engine)
    with engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS alembic_version"))
        for t in _ENUM_TYPES:
            c.execute(text(f"DROP TYPE IF EXISTS {t} CASCADE"))
    engine.dispose()


def _alembic(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "SMISTRESS_DATABASE_URL": TEST_URL}
    return subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )


def test_migration_upgrade_then_downgrade_is_clean():
    _ensure_test_database()
    _clear_schema()

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    current = _alembic("current")
    assert current.returncode == 0, current.stderr
    assert current.stdout.strip()  # a revision is applied

    down = _alembic("downgrade", "base")
    assert down.returncode == 0, down.stderr

    # Reversible: a second upgrade succeeds (enum types were dropped on downgrade).
    up2 = _alembic("upgrade", "head")
    assert up2.returncode == 0, up2.stderr
