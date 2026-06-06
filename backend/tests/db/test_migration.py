import os
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
TEST_URL = "postgresql+psycopg://smistress:smistress@localhost:5432/smistress_test"


def _alembic(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "SMISTRESS_DATABASE_URL": TEST_URL}
    return subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )


def test_migration_upgrade_then_downgrade_is_clean():
    down = _alembic("downgrade", "base")
    assert down.returncode == 0, down.stderr
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    # tables exist after upgrade
    check = _alembic("current")
    assert check.returncode == 0, check.stderr
    assert check.stdout.strip()  # a revision is applied
