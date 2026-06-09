# Offline-First M4b — Punishment Pool + Discipline Drone Unit + Debt/Chastity UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the discipline picture from M4a: the LLM pre-generates a **punishment pool** (the 4th batch artifact), the discipline unit issues **varied** punishments drawn from it on a miss/fail (deterministic fallback when empty), the offline **discipline drone unit** surfaces the debt ledger + outstanding penance, token **buy-down** now resolves ledger entries to `BOUGHT_DOWN`, and the dossier/UI finally show **debt + chastity** (retiring the `denial_timers` compat field).

**Architecture:** A new `PunishmentPoolItem` joins the M3 batch artifacts; `generate_batch` tops it up alongside the task pool and line bank. Because `batch/service.py` already imports `loop` (for `draw_and_assign`), the punishment **draw** lives in `discipline/service.py` (it queries the pool model directly and issues via the existing `issue_punishment`) — `batch` only generates + counts pool items, so there is no import cycle (`loop → discipline → {economy, models}`; `batch → loop`; discipline never imports batch or loop). The discipline drone unit is **deterministic/state-derived** (like the M3 reminder unit), reading the debt balance and outstanding-penance count. The dossier drops the `denial_timers` compat field and exposes a `chastity` block + `debt`, which the `DossierBar` renders.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async (psycopg3), Alembic, Pydantic v2, pytest (live Postgres `smistress_test`), ruff line-length=100; SvelteKit 2 + Svelte 5 runes, Vitest. Conventions: **services flush, endpoints commit**; PG enums referenced with `postgresql.ENUM(create_type=False)` in migrations; frontend hand-writes API interfaces (never imports generated `api.ts`).

**Scope (locked):** Pool-fed **varied** issuance — on a miss/fail draw a pool item matching the offence severity (fail→2, miss→1), of ANY of the three types, issue with its flavored reason; deterministic chastity-extension fallback when the pool is empty. **Remove** the dossier `denial_timers` compat field; surface `chastity` + `debt`. Buy-down marks whole `Punishment` rows `BOUGHT_DOWN` FIFO. Deferred: merit-scaled severity (severity stays outcome-derived); the safeword receipt's `denial_lifted` field/copy stays as-is (separate concern); regenerating the stale generated `frontend/src/lib/types/api.ts` (not imported at runtime); the privilege-lock punishment type (no consumer yet).

---

## File Structure

**New (backend/):**
- `app/db/models/batch.py` — add `PunishmentPoolItem` (modify).
- `alembic/versions/d4e5f6a7b8c9_add_punishment_pool.py` — `punishment_pool_item` table.
- `tests/batch/test_punishment_pool.py`, `tests/discipline/test_draw.py`, `tests/drones/test_discipline_unit.py`, `tests/economy/test_buydown_ledger.py`.

**Modified (backend/):**
- `app/config.py` — `batch_punishment_target` / `batch_punishment_low`.
- `app/db/models/__init__.py` — register `PunishmentPoolItem`; `app/services/profile.py` — delete cascade.
- `app/batch/prompt.py` — punishments in the JSON schema + prompt.
- `app/batch/service.py` — `_PunishmentGen` + parse + generate (top-up) + `pool_status` punishment count; `PoolStatus`/`GenerateResult` gain punishment fields.
- `app/discipline/service.py` — `draw_punishment` + `draw_and_issue`.
- `app/loop/service.py` — `apply_terminal_discipline` uses `draw_and_issue`.
- `app/economy/service.py` — `buy_down_debt` marks punishments `BOUGHT_DOWN` FIFO.
- `app/drones/service.py` — discipline unit notices.
- `app/chat/service.py` (dossier), `app/schemas/chat.py` (DossierOut), `app/schemas/batch.py` (punishment counts).
- `app/api/economy.py` — (no change; standing already returns debt+chastity).
- Tests: `tests/batch/test_pool_status.py`, `tests/batch/test_generate.py`, `tests/api/test_batch_api.py`, `tests/chat/test_chat_service.py`.

**Frontend:**
- `src/lib/api/dossier.ts`, `src/lib/chat/DossierBar.svelte`, `src/lib/chat/ActionCard.svelte`, and tests `DossierBar.test.ts`, `stores/dossier.test.ts`, `routes/page.test.ts`, `e2e/fixtures.ts`.

---

## Task 1: `PunishmentPoolItem` model + migration + config

**Files:**
- Modify: `backend/app/db/models/batch.py`, `backend/app/db/models/__init__.py`, `backend/app/services/profile.py`, `backend/app/config.py`
- Create: `backend/alembic/versions/d4e5f6a7b8c9_add_punishment_pool.py`, `backend/tests/batch/test_punishment_pool.py`

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/batch/test_punishment_pool.py`:

```python
from app.db.enums import PunishmentType
from app.db.models.batch import PunishmentPoolItem
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_punishment_pool_item_round_trip(session):
    p = await _profile(session)
    item = PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.PENANCE_TASK, severity=2,
        reason="Write 30 lines: I will not keep her waiting.",
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    assert item.consumed is False
    assert item.type is PunishmentType.PENANCE_TASK
    assert item.severity == 2
```

- [ ] **Step 2: Run to verify it fails**

Run (PowerShell; clear env per `smistress-dev-environment`; Postgres up):
```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/batch/test_punishment_pool.py -q
```
Expected: FAIL — `ImportError: cannot import name 'PunishmentPoolItem'`.

- [ ] **Step 3: Add the model**

In `backend/app/db/models/batch.py`, add the import for the enum at the top (it already imports `ProofRequirement` from `app.db.enums` — extend that line to `from app.db.enums import ProofRequirement, PunishmentType`), then append:

```python
class PunishmentPoolItem(Base):
    """A pre-generated, undrawn punishment (Addendum B4 punishment pool). The
    discipline unit draws one matching the offence severity and issues it; carries
    the same merit/debt-free flavor as the drone line bank — debt stakes come from
    the severity at issue time."""

    __tablename__ = "punishment_pool_item"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))

    type: Mapped[PunishmentType] = mapped_column(Enum(PunishmentType, name="punishment_type"))
    severity: Mapped[int] = mapped_column(default=1)  # 1 (light) .. 3 (heavy)
    reason: Mapped[str] = mapped_column(String)

    consumed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    profile: Mapped[SubProfile] = relationship()
```

(The file already imports `Enum`, `ForeignKey`, `String`, `func`, `Mapped`, `mapped_column`, `relationship`, `uuid`, `datetime`, and `SubProfile` for the existing models — reuse them.)

- [ ] **Step 4: Register the model + delete cascade**

In `backend/app/db/models/__init__.py`, change the batch import line to:
```python
from app.db.models.batch import DroneLine, PunishmentPoolItem, TaskPoolItem  # noqa: F401
```

In `backend/app/services/profile.py` `delete_profile`: add `PunishmentPoolItem` to the per-profile delete batch (it FKs only to `sub_profile.id`, same phase as `TaskPoolItem`/`DroneLine`). Read the function; import it (`from app.db.models.batch import DroneLine, PunishmentPoolItem, TaskPoolItem` or extend the existing batch import) and add it to the deletion sequence wherever `TaskPoolItem`/`DroneLine` are deleted.

- [ ] **Step 5: Add config thresholds**

In `backend/app/config.py`, after `batch_line_low`:
```python
    batch_punishment_target: int = 6  # top the punishment pool up to this many unconsumed items
    batch_punishment_low: int = 2
```

- [ ] **Step 6: Write the migration**

Current head is `c3d4e5f6a7b8`. The `punishment_type` enum already exists (M4a) — reference it with `create_type=False`.

Create `backend/alembic/versions/d4e5f6a7b8c9_add_punishment_pool.py`:
```python
"""add punishment pool

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-09 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pun_type = postgresql.ENUM(
        'PENANCE_TASK', 'CHASTITY_EXTENSION', 'TOKEN_CONFISCATION',
        name='punishment_type', create_type=False,
    )
    op.create_table(
        'punishment_pool_item',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('type', pun_type, nullable=False),
        sa.Column('severity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('consumed', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('punishment_pool_item')
```

- [ ] **Step 7: Round-trip the migration**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic downgrade -1
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
```
Expected: each exits 0; upgrade logs `c3d4e5f6a7b8 -> d4e5f6a7b8c9`. (Defer to CI if Postgres is down.)

- [ ] **Step 8: Run the model test (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/batch/test_punishment_pool.py -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/db/models/ app/config.py app/services/profile.py
```
```bash
git add backend/app/db/models/batch.py backend/app/db/models/__init__.py backend/app/services/profile.py backend/app/config.py backend/alembic/versions/d4e5f6a7b8c9_add_punishment_pool.py backend/tests/batch/test_punishment_pool.py
git commit -m "feat(batch): PunishmentPoolItem model + migration + config"
```

---

## Task 2: Generate the punishment pool (prompt + parse + top-up + pool_status)

**Files:**
- Modify: `backend/app/batch/prompt.py`, `backend/app/batch/service.py`, `backend/app/schemas/batch.py`
- Test: `backend/tests/batch/test_generate.py`, `backend/tests/batch/test_pool_status.py`, `backend/tests/api/test_batch_api.py`

- [ ] **Step 1: Extend the generation test**

In `backend/tests/batch/test_generate.py`, update the `_payload` helper to also emit punishments, and add an assertion. Replace the existing `_payload` with:
```python
def _payload(n_tasks=3, n_lines=4, n_punishments=3):
    return ChatResult(content=json.dumps({
        "tasks": [
            {"description": f"task {i}", "proof": "honor", "merit_reward": 5,
             "merit_miss_penalty": 3, "difficulty": "standard"}
            for i in range(n_tasks)
        ],
        "lines": [
            {"unit": "assignment", "event": "task_drop", "merit_band": "mid",
             "time_of_day": "any", "text": "Mistress has set you: {task}."}
            for _ in range(n_lines)
        ],
        "punishments": [
            {"type": "penance_task", "severity": 2, "reason": f"penance {i}"}
            for i in range(n_punishments)
        ],
    }))
```
And in `test_generate_persists_parsed_artifacts`, after the line-count assertion add:
```python
    from app.db.models.batch import PunishmentPoolItem
    punishments = (await session.execute(
        select(func.count()).select_from(PunishmentPoolItem)
        .where(PunishmentPoolItem.profile_id == p.id)
    )).scalar_one()
    assert punishments == 3
    assert result.punishments_added == 3
```

- [ ] **Step 2: Add a pool-status punishment assertion**

In `backend/tests/batch/test_pool_status.py` `test_pool_status_empty_is_low`, add:
```python
    assert status.punishment_pool == 0
    assert status.punishment_pool_low is True
```

- [ ] **Step 3: Run to verify failure**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/batch/test_generate.py tests/batch/test_pool_status.py -q
```
Expected: FAIL — `punishments_added` / `punishment_pool` attributes don't exist.

- [ ] **Step 4: Extend the prompt**

In `backend/app/batch/prompt.py`:
(a) Extend `_JSON_SCHEMA` — add a `punishments` array to the JSON shape. Replace the closing of the schema (the `"lines": [...]` block and trailing text) so the object includes:
```python
    '  "lines": [\n'
    '    {"unit": "assignment"|"reminder", "event": "task_drop"|"no_task"|"batch_window",\n'
    '     "merit_band": "low"|"mid"|"high"|"any",\n'
    '     "time_of_day": "morning"|"day"|"evening"|"night"|"any", "text": str}\n'
    '  ],\n'
    '  "punishments": [\n'
    '    {"type": "penance_task"|"chastity_extension"|"token_confiscation",\n'
    '     "severity": 1|2|3, "reason": str}\n'
    '  ]\n'
    '}\n'
    'For "task_drop" lines, include the literal placeholder {task}. Lines and '
    'punishment reasons are cold, mechanical, in-persona (never warm). A punishment '
    '"reason" is the penance/consequence text (e.g. "Write 50 lines: ...").'
```
(b) Change `build_generation_prompt` to take `punishment_count: int` and mention it:
```python
def build_generation_prompt(
    profile: SubProfile,
    character: CharacterModel | None,
    econ: EconomyState | None,
    *,
    task_count: int,
    line_count: int,
    punishment_count: int,
) -> list[ChatMessage]:
```
and update the user string's generate line:
```python
        f"Generate {task_count} task-pool items, {line_count} drone lines, and "
        f"{punishment_count} punishments.\n\n"
```

- [ ] **Step 5: Parse + generate + count punishments**

In `backend/app/batch/service.py`:

(a) Import the new model: change `from app.db.models.batch import DroneLine, TaskPoolItem` to `from app.db.models.batch import DroneLine, PunishmentPoolItem, TaskPoolItem`, and add `from app.db.enums import ProofRequirement, PunishmentType` (extend the existing `ProofRequirement` import).

(b) Add the validation sets + a `_PunishmentGen` model (next to `_LineGen`):
```python
_VALID_PUN_TYPES = {"penance_task", "chastity_extension", "token_confiscation"}


class _PunishmentGen(BaseModel):
    type: str
    severity: int
    reason: str

    @field_validator("type", mode="before")
    @classmethod
    def _lower(cls, v: object) -> object:
        return str(v).strip().lower() if v is not None else v

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in _VALID_PUN_TYPES:
            raise ValueError("bad punishment type")
        return v

    @field_validator("severity")
    @classmethod
    def _sev(cls, v: int) -> int:
        if v not in (1, 2, 3):
            raise ValueError("bad severity")
        return v
```

(c) In `parse_batch`, return a third list. Change the signature/return to include punishments:
```python
def parse_batch(content: str) -> tuple[list[_TaskGen], list[_LineGen], list[_PunishmentGen]]:
```
and after the lines loop, before `return`:
```python
    raw_punishments = data.get("punishments")
    punishments: list[_PunishmentGen] = []
    for raw in raw_punishments if isinstance(raw_punishments, list) else []:
        try:
            punishments.append(_PunishmentGen.model_validate(raw))
        except ValidationError:
            continue
    return tasks, lines, punishments
```
(Update the three early `return [], []` guards in `parse_batch` to `return [], [], []`.)

(d) Extend `PoolStatus` and `pool_status`:
```python
@dataclass
class PoolStatus:
    task_pool: int
    line_bank: int
    punishment_pool: int
    task_pool_low: bool
    line_bank_low: bool
    punishment_pool_low: bool
```
In `pool_status`, add the count and fields:
```python
    punishments = (await session.execute(
        select(func.count()).select_from(PunishmentPoolItem)
        .where(PunishmentPoolItem.profile_id == profile_id, PunishmentPoolItem.consumed.is_(False))
    )).scalar_one()
    return PoolStatus(
        task_pool=tasks,
        line_bank=lines,
        punishment_pool=punishments,
        task_pool_low=tasks <= _settings.batch_task_low,
        line_bank_low=lines <= _settings.batch_line_low,
        punishment_pool_low=punishments <= _settings.batch_punishment_low,
    )
```

(e) Extend `GenerateResult` and `generate_batch`:
```python
@dataclass
class GenerateResult:
    tasks_added: int
    lines_added: int
    punishments_added: int
    task_pool: int
    line_bank: int
    punishment_pool: int
```
In `generate_batch`, compute `want_punishments`, pass it to the prompt, persist parsed punishments, and return the new shape:
```python
    want_punishments = max(0, _settings.batch_punishment_target - status.punishment_pool)
    messages = build_generation_prompt(
        profile, character, econ,
        task_count=want_tasks, line_count=want_lines, punishment_count=want_punishments,
    )
    reply = await provider.chat(messages)
    parsed_tasks, parsed_lines, parsed_punishments = parse_batch(reply.content)
```
(persist tasks + lines as before, then:)
```python
    added_punishments = 0
    for gen in parsed_punishments[:want_punishments]:
        session.add(PunishmentPoolItem(
            profile_id=profile_id,
            type=PunishmentType(gen.type),
            severity=gen.severity,
            reason=gen.reason,
        ))
        added_punishments += 1
    await session.flush()
    return GenerateResult(
        added_tasks, added_lines, added_punishments,
        status.task_pool + added_tasks,
        status.line_bank + added_lines,
        status.punishment_pool + added_punishments,
    )
```

- [ ] **Step 6: Extend the batch schemas**

In `backend/app/schemas/batch.py`, add the punishment fields:
```python
class GenerateBatchOut(BaseModel):
    tasks_added: int
    lines_added: int
    punishments_added: int
    task_pool: int
    line_bank: int
    punishment_pool: int


class PoolStatusOut(BaseModel):
    task_pool: int
    line_bank: int
    punishment_pool: int
    task_pool_low: bool
    line_bank_low: bool
    punishment_pool_low: bool
```
In `backend/app/api/batch.py`, update the two response constructions to pass the new fields (`punishments_added=result.punishments_added`, `punishment_pool=result.punishment_pool` for generate; `punishment_pool=s.punishment_pool`, `punishment_pool_low=s.punishment_pool_low` for status).

- [ ] **Step 7: Update the batch-API test**

In `backend/tests/api/test_batch_api.py`, the `_payload` helper and the assertions: extend `_payload` to include `"punishments"` (mirror Step 1), and in `test_generate_when_online_persists_and_returns_counts` assert `body["punishments_added"]` matches; in `test_status_reports_low_pools` assert `r.json()["punishment_pool_low"] is True`.

- [ ] **Step 8: Run the batch suite (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/batch/ tests/api/test_batch_api.py -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/batch/ app/schemas/batch.py app/api/batch.py
```
```bash
git add backend/app/batch/ backend/app/schemas/batch.py backend/app/api/batch.py backend/tests/batch/ backend/tests/api/test_batch_api.py
git commit -m "feat(batch): generate + count the punishment pool (4th artifact)"
```

---

## Task 3: Discipline draw — `draw_punishment` + `draw_and_issue`

**Files:**
- Modify: `backend/app/discipline/service.py`
- Test: `backend/tests/discipline/test_draw.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/discipline/test_draw.py`:
```python
from app.db.enums import PunishmentStatus, PunishmentType
from app.db.models.batch import PunishmentPoolItem
from app.db.models.punishment import Punishment
from app.discipline import service as disc_svc
from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from sqlalchemy import select


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_draw_punishment_prefers_matching_severity_and_consumes(session):
    p = await _profile(session)
    session.add(PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.TOKEN_CONFISCATION, severity=1, reason="light",
    ))
    session.add(PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.PENANCE_TASK, severity=2, reason="match",
    ))
    await session.flush()
    item = await disc_svc.draw_punishment(session, p.id, severity=2)
    assert item is not None and item.severity == 2 and item.reason == "match"
    assert item.consumed is True


async def test_draw_punishment_falls_back_to_any_severity(session):
    p = await _profile(session)
    session.add(PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.PENANCE_TASK, severity=1, reason="only",
    ))
    await session.flush()
    item = await disc_svc.draw_punishment(session, p.id, severity=3)
    assert item is not None and item.reason == "only"


async def test_draw_punishment_none_when_empty(session):
    p = await _profile(session)
    assert await disc_svc.draw_punishment(session, p.id, severity=2) is None


async def test_draw_and_issue_uses_pool_item(session):
    p = await _profile(session)
    session.add(PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.TOKEN_CONFISCATION, severity=2, reason="pooled",
    ))
    await econ_svc.grant_tokens(session, p.id, 100)
    await session.flush()
    pun = await disc_svc.draw_and_issue(session, p.id, severity=2)
    assert pun.type is PunishmentType.TOKEN_CONFISCATION
    assert pun.reason == "pooled"
    assert (await econ_svc.get_economy(session, p.id)).debt == 15  # severity 2


async def test_draw_and_issue_falls_back_when_pool_empty(session):
    p = await _profile(session)
    pun = await disc_svc.draw_and_issue(session, p.id, severity=1)
    # deterministic fallback: a chastity extension
    assert pun.type is PunishmentType.CHASTITY_EXTENSION
    assert (await econ_svc.chastity_status(session, p.id)).locked is True
```

- [ ] **Step 2: Run to verify it fails**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/discipline/test_draw.py -q
```
Expected: FAIL — `draw_punishment` undefined.

- [ ] **Step 3: Implement the draw**

In `backend/app/discipline/service.py`:
(a) Add imports: `from app.db.models.batch import PunishmentPoolItem`.
(b) Append:
```python
# Deterministic fallback when the pool is empty (mirrors the M4a placeholder).
_FALLBACK_TYPE = PunishmentType.CHASTITY_EXTENSION


async def draw_punishment(
    session: AsyncSession, profile_id: uuid.UUID, *, severity: int
) -> PunishmentPoolItem | None:
    """Draw an unconsumed pooled punishment, preferring the requested severity and
    falling back to any. Marks it consumed. Returns None if the pool is empty."""
    base = select(PunishmentPoolItem).where(
        PunishmentPoolItem.profile_id == profile_id,
        PunishmentPoolItem.consumed.is_(False),
    )
    item = (await session.execute(
        base.where(PunishmentPoolItem.severity == severity)
        .order_by(PunishmentPoolItem.created_at, PunishmentPoolItem.id).limit(1)
    )).scalars().first()
    if item is None:
        item = (await session.execute(
            base.order_by(PunishmentPoolItem.created_at, PunishmentPoolItem.id).limit(1)
        )).scalars().first()
    if item is not None:
        item.consumed = True
        await session.flush()
    return item


async def draw_and_issue(
    session: AsyncSession,
    profile_id: uuid.UUID,
    *,
    severity: int,
    reason_prefix: str = "",
    now: datetime | None = None,
) -> Punishment:
    """Draw a varied punishment from the pool and issue it; fall back to a
    deterministic chastity extension when the pool is empty. Caller commits."""
    item = await draw_punishment(session, profile_id, severity=severity)
    if item is not None:
        reason = f"{reason_prefix}{item.reason}" if reason_prefix else item.reason
        return await issue_punishment(
            session, profile_id, type=item.type, severity=item.severity, reason=reason, now=now,
        )
    return await issue_punishment(
        session, profile_id, type=_FALLBACK_TYPE, severity=severity,
        reason=reason_prefix or "Discipline.", now=now,
    )
```

- [ ] **Step 4: Run (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/discipline/ -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/discipline/
```
```bash
git add backend/app/discipline/service.py backend/tests/discipline/test_draw.py
git commit -m "feat(discipline): draw varied punishments from the pool (+deterministic fallback)"
```

---

## Task 4: Loop uses pool-fed issuance

**Files:**
- Modify: `backend/app/loop/service.py`
- Test: `backend/tests/loop/test_discipline_hook.py`

- [ ] **Step 1: Add the failing test**

Append to `backend/tests/loop/test_discipline_hook.py`:
```python
async def test_fail_draws_from_punishment_pool_when_available(session):
    from app.db.enums import PunishmentType
    from app.db.models.batch import PunishmentPoolItem

    p = await _profile(session)
    session.add(PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.TOKEN_CONFISCATION, severity=2, reason="pooled fail",
    ))
    await econ_svc.grant_tokens(session, p.id, 100)
    await session.flush()
    task = await loop_svc.assign_task(
        session, p.id, description="drill", proof_requirement=ProofRequirement.HONOR,
    )
    task.status = TaskStatus.VERIFIED_FAIL
    await session.flush()
    await loop_svc.apply_terminal_discipline(session, task)
    pun = (await session.execute(
        select(Punishment).where(Punishment.profile_id == p.id)
    )).scalar_one()
    assert pun.type is PunishmentType.TOKEN_CONFISCATION  # drawn from the pool, not the fallback
    assert pun.reason == "pooled fail"
```

- [ ] **Step 2: Run to verify it fails**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/loop/test_discipline_hook.py::test_fail_draws_from_punishment_pool_when_available -q
```
Expected: FAIL — the fallback chastity-extension is issued instead of the pooled token-confiscation.

- [ ] **Step 3: Switch the loop hook to `draw_and_issue`**

In `backend/app/loop/service.py`, in `apply_terminal_discipline`, replace the FAIL/MISS branch:
```python
    elif task.status in (TaskStatus.VERIFIED_FAIL, TaskStatus.MISSED):
        severity = 2 if task.status is TaskStatus.VERIFIED_FAIL else 1
        await disc_svc.issue_punishment(
            session, task.profile_id, type=_AUTO_PUNISHMENT_TYPE, severity=severity,
            reason=f"{task.status.value}: {task.description}",
        )
```
with:
```python
    elif task.status in (TaskStatus.VERIFIED_FAIL, TaskStatus.MISSED):
        severity = 2 if task.status is TaskStatus.VERIFIED_FAIL else 1
        await disc_svc.draw_and_issue(
            session, task.profile_id, severity=severity,
            reason_prefix=f"{task.status.value}: ",
        )
```
Remove the now-unused `_AUTO_PUNISHMENT_TYPE` constant and the `from app.db.enums import PunishmentType` import **only if** `PunishmentType` is no longer referenced in the file (check first; if the import line also brought in other names, keep those).

- [ ] **Step 4: Run the loop suite (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/loop/ -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/loop/service.py tests/loop/
```
Expected: existing miss/fail tests still pass (they assert a punishment exists / debt > 0, which holds for both pool and fallback paths). Commit:
```bash
git add backend/app/loop/service.py backend/tests/loop/test_discipline_hook.py
git commit -m "feat(loop): issue varied pooled punishments on fail/miss"
```

---

## Task 5: Buy-down resolves ledger entries to `BOUGHT_DOWN` (FIFO)

**Files:**
- Modify: `backend/app/economy/service.py`
- Test: `backend/tests/economy/test_buydown_ledger.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/economy/test_buydown_ledger.py`:
```python
from app.db.enums import PunishmentStatus, PunishmentType
from app.db.models.punishment import Punishment
from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from sqlalchemy import select


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


def _issued(profile_id, debt_amount):
    return Punishment(
        profile_id=profile_id, type=PunishmentType.CHASTITY_EXTENSION, severity=1,
        reason="x", debt_amount=debt_amount, status=PunishmentStatus.ISSUED,
    )


async def test_buy_down_marks_whole_punishments_bought_down_fifo(session):
    p = await _profile(session)
    session.add(_issued(p.id, 5))
    session.add(_issued(p.id, 15))
    await session.flush()
    await econ_svc.adjust_debt(session, p.id, 20)
    await econ_svc.grant_tokens(session, p.id, 100)

    # buy down 5 debt points -> clears exactly the first (5) punishment, not the 15
    await econ_svc.buy_down_debt(session, p.id, debt_points=5)
    rows = (await session.execute(
        select(Punishment).where(Punishment.profile_id == p.id)
        .order_by(Punishment.debt_amount)
    )).scalars().all()
    assert rows[0].status is PunishmentStatus.BOUGHT_DOWN
    assert rows[0].resolved_at is not None
    assert rows[1].status is PunishmentStatus.ISSUED  # 15 not fully covered
```

- [ ] **Step 2: Run to verify it fails**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/economy/test_buydown_ledger.py -q
```
Expected: FAIL — both punishments remain `ISSUED`.

- [ ] **Step 3: Mark punishments in `buy_down_debt`**

In `backend/app/economy/service.py`:
(a) Add imports: `from datetime import datetime, timezone` is already present; add `from app.db.enums import PunishmentStatus` and `from app.db.models.punishment import Punishment` (place with the other model imports).
(b) Replace the body of `buy_down_debt` so that after clearing the aggregate it marks whole ISSUED punishments FIFO up to the cleared amount, and update the docstring (drop the M4b-deferral note):
```python
async def buy_down_debt(
    session: AsyncSession, profile_id: uuid.UUID, *, debt_points: int
) -> EconomyState:
    """Spend tokens to clear debt at a punishing rate (no merit). Clears as much as
    both the debt balance and the token purse allow, and resolves whole ISSUED
    punishment ledger rows to BOUGHT_DOWN (FIFO) up to the cleared amount. Caller
    commits."""
    if debt_points < 0:
        raise ValueError("debt_points must be non-negative")
    econ = await get_economy(session, profile_id)
    rate = _settings.buydown_tokens_per_debt
    affordable = econ.tokens // rate
    cleared = min(debt_points, econ.debt, affordable)
    econ.debt -= cleared
    econ.tokens -= cleared * rate

    remaining = cleared
    issued = (await session.execute(
        select(Punishment).where(
            Punishment.profile_id == profile_id,
            Punishment.status == PunishmentStatus.ISSUED,
        ).order_by(Punishment.created_at, Punishment.id)
    )).scalars().all()
    for pun in issued:
        if pun.debt_amount <= remaining:
            pun.status = PunishmentStatus.BOUGHT_DOWN
            pun.resolved_at = datetime.now(timezone.utc)
            remaining -= pun.debt_amount
    await session.flush()
    return econ
```

- [ ] **Step 4: Run (PASS) + the existing debt test (no regression), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/economy/ -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/economy/service.py tests/economy/
```
```bash
git add backend/app/economy/service.py backend/tests/economy/test_buydown_ledger.py
git commit -m "feat(economy): buy-down resolves ledger entries to BOUGHT_DOWN (FIFO)"
```

---

## Task 6: Discipline drone unit in `standing_orders`

**Files:**
- Modify: `backend/app/drones/service.py`
- Test: `backend/tests/drones/test_discipline_unit.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/drones/test_discipline_unit.py`:
```python
from app.db.enums import PunishmentType
from app.discipline import service as disc_svc
from app.drones import service as drone_svc
from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_no_discipline_notice_when_debt_free(session):
    p = await _profile(session)
    notices = await drone_svc.standing_orders(session, p.id)
    assert [n for n in notices if n.unit == "discipline"] == []


async def test_discipline_notice_reports_debt(session):
    p = await _profile(session)
    await econ_svc.adjust_debt(session, p.id, 25)
    notices = await drone_svc.standing_orders(session, p.id)
    discipline = [n for n in notices if n.unit == "discipline"]
    assert any("debt of 25" in n.line.lower() for n in discipline)


async def test_discipline_notice_reports_outstanding_penance(session):
    p = await _profile(session)
    await disc_svc.issue_punishment(
        session, p.id, type=PunishmentType.PENANCE_TASK, severity=1, reason="penance",
    )
    notices = await drone_svc.standing_orders(session, p.id)
    discipline = [n for n in notices if n.unit == "discipline"]
    assert any("penance" in n.line.lower() for n in discipline)
```

- [ ] **Step 2: Run to verify it fails**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/drones/test_discipline_unit.py -q
```
Expected: FAIL — no `discipline`-unit notices exist.

- [ ] **Step 3: Add the discipline unit**

In `backend/app/drones/service.py`:
(a) Add imports: `from app.db.enums import PunishmentStatus, PunishmentType` and `from app.db.models.punishment import Punishment`. (The file already imports `select`, `EconomyState`, `econ_svc`.)
(b) Add a helper near `_reminder_lines`:
```python
def _discipline_lines(debt: int, outstanding_penance: int) -> list[str]:
    lines: list[str] = []
    if debt > 0:
        lines.append(
            f"You carry a debt of {debt}. Clear it by serving penance or buying it down."
        )
    if outstanding_penance > 0:
        noun = "penance" if outstanding_penance == 1 else "penances"
        lines.append(f"{outstanding_penance} {noun} await completion.")
    return lines


async def _outstanding_penance_count(session: AsyncSession, profile_id: uuid.UUID) -> int:
    return (await session.execute(
        select(func.count()).select_from(Punishment).where(
            Punishment.profile_id == profile_id,
            Punishment.type == PunishmentType.PENANCE_TASK,
            Punishment.status == PunishmentStatus.ISSUED,
        )
    )).scalar_one()
```
Add `func` to the sqlalchemy import (`from sqlalchemy import func, select`).
(c) In `standing_orders`, fetch the economy once for both merit and debt. Replace the `band = batch_svc.merit_band(await _merit(...))` usage: keep `_merit` for the band, then after the reminder notices, append discipline notices:
```python
    econ = await econ_svc.get_economy(session, profile_id)
    outstanding = await _outstanding_penance_count(session, profile_id)
    notices += [
        DroneNotice(unit="discipline", line=line)
        for line in _discipline_lines(econ.debt, outstanding)
    ]
```
Place this block before the final pool-low `batch_window` reminder block. (Use `econ_svc.get_economy`; a profile always has an economy row from `create_profile`.)
(d) The pool-low `batch_window` reminder should also fire when the punishment pool is low — change its condition:
```python
    if status.task_pool_low or status.line_bank_low or status.punishment_pool_low:
```

- [ ] **Step 4: Run the drone suite (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/drones/ -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/drones/
```
```bash
git add backend/app/drones/service.py backend/tests/drones/test_discipline_unit.py
git commit -m "feat(drones): discipline unit surfaces the debt ledger + outstanding penance"
```

---

## Task 7: Dossier — drop `denial_timers`, surface `chastity` + `debt`

**Files:**
- Modify: `backend/app/chat/service.py`, `backend/app/schemas/chat.py`
- Test: `backend/tests/chat/test_chat_service.py`

- [ ] **Step 1: Update the dossier tests**

In `backend/tests/chat/test_chat_service.py`, in `test_build_dossier_composes_economy_disposition_active_task`, remove `assert d["denial_timers"] == 0` (keep the `debt`/`chastity` assertions added in M4a). In `test_build_dossier_reflects_active_chastity_lock`, remove the `assert d["denial_timers"] == 1` line (the compat field is gone; the `chastity.locked` assertion remains).

- [ ] **Step 2: Run to verify it fails**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/chat/test_chat_service.py -q
```
Expected: PASS is NOT the goal yet — first the tests still reference `denial_timers`? After removing those asserts they should pass against the *current* dossier (which still emits `denial_timers`). To make this a real red→green, instead: keep the test edits, then in Step 3 remove the field from the builder; if a test still asserts the field it fails. Run after Step 3.

- [ ] **Step 3: Remove the compat field**

In `backend/app/chat/service.py` `build_dossier`, delete the trailing compat line:
```python
        # compat: existing frontend reads denial_timers as a count (M4b relabels).
        "denial_timers": 1 if chastity.locked else 0,
```
In `backend/app/schemas/chat.py` `DossierOut`, remove `denial_timers: int`.

- [ ] **Step 4: Run the chat suite (PASS), lint, commit**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest tests/chat/ -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check app/chat/service.py app/schemas/chat.py
```
```bash
git add backend/app/chat/service.py backend/app/schemas/chat.py backend/tests/chat/test_chat_service.py
git commit -m "refactor(dossier): drop denial_timers compat; expose chastity + debt"
```

---

## Task 8: Frontend — dossier debt/chastity + ActionCard chastity

**Files:**
- Modify: `frontend/src/lib/api/dossier.ts`, `frontend/src/lib/chat/DossierBar.svelte`, `frontend/src/lib/chat/ActionCard.svelte`
- Test: `frontend/src/lib/chat/DossierBar.test.ts`, `frontend/src/lib/stores/dossier.test.ts`, `frontend/src/routes/page.test.ts`, `frontend/e2e/fixtures.ts`

- [ ] **Step 1: Update the `Dossier` interface**

In `frontend/src/lib/api/dossier.ts`, replace `denial_timers: number;` with the debt + chastity shape:
```typescript
export interface Dossier {
  rank: string;
  merit: number;
  tokens: number;
  debt: number;
  disposition: { band: string; line: string; reason: string; standing: number };
  active_task: { description: string; status: string } | null;
  chastity: { locked: boolean; ends_at: string | null; seconds_remaining: number };
}
```

- [ ] **Step 2: Update `DossierBar.svelte`**

Replace the summary ledger line and the expand block so debt shows in the summary and chastity in the expand. In `frontend/src/lib/chat/DossierBar.svelte`, change:
```svelte
      <span class="ledger">{data.rank} · merit {data.merit} · tokens {data.tokens}</span>
```
to:
```svelte
      <span class="ledger">{data.rank} · merit {data.merit} · tokens {data.tokens} · debt {data.debt}</span>
```
and change the expand line:
```svelte
        <p class="ledger">denial timers: {data.denial_timers}</p>
```
to:
```svelte
        <p class="ledger">
          chastity: {data.chastity.locked
            ? `locked · ${Math.floor(data.chastity.seconds_remaining / 3600)}h left`
            : 'not locked'}
        </p>
```

- [ ] **Step 3: Update `ActionCard.svelte` for the renamed tool**

In `frontend/src/lib/chat/ActionCard.svelte`, rename the `set_denial_timer` branches to `set_chastity` and relabel:
- title: `action.tool === 'set_denial_timer' ? 'Denial set'` → `action.tool === 'set_chastity' ? 'Chastity set'`
- body: `{:else if action.tool === 'set_denial_timer'}` → `{:else if action.tool === 'set_chastity'}`

(If `frontend/src/lib/api/chat.ts`'s `ActionCard` type enumerates the tool name as a string literal, update `'set_denial_timer'` → `'set_chastity'` there too; read it first to check.)

- [ ] **Step 4: Update the frontend tests + e2e fixtures**

- `frontend/src/lib/chat/DossierBar.test.ts`: in the mock dossier, replace `denial_timers: 1` with `debt: 0` and `chastity: { locked: false, ends_at: null, seconds_remaining: 0 }`; if the test asserts the "denial timers" text, change it to assert the chastity text.
- `frontend/src/lib/stores/dossier.test.ts`: replace `denial_timers: 0` with `debt: 0, chastity: { locked: false, ends_at: null, seconds_remaining: 0 }`.
- `frontend/src/routes/page.test.ts`: in the dossier mock (around the `denial_timers: 0` line) replace with `debt: 0, chastity: { locked: false, ends_at: null, seconds_remaining: 0 }`.
- `frontend/e2e/fixtures.ts`: in the `/dossier` mock, replace `denial_timers: 0` with `debt: 0, chastity: { locked: false, ends_at: null, seconds_remaining: 0 }`.

- [ ] **Step 5: Run vitest + build**

```
npm --prefix frontend run test
npm --prefix frontend run build
```
Expected: vitest passes; build succeeds. (Playwright e2e is the CI `e2e` job.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api/dossier.ts frontend/src/lib/chat/DossierBar.svelte frontend/src/lib/chat/ActionCard.svelte frontend/src/lib/chat/DossierBar.test.ts frontend/src/lib/stores/dossier.test.ts frontend/src/routes/page.test.ts frontend/e2e/fixtures.ts
git commit -m "feat(ui): dossier shows debt + chastity; action card renames to chastity"
```

---

## Task 9: Full verification

**Files:** none.

- [ ] **Step 1: Whole backend suite + ruff + migration head**

```
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend pytest -q
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend ruff check .
$env:PYTHONHOME=$null; $env:PYTHONPATH=$null; uv run --directory backend alembic upgrade head
```
Expected: all green; ruff clean; head `d4e5f6a7b8c9`.

- [ ] **Step 2: Confirm no stale `denial_timers` in app code**

Search `frontend/src` and `backend/app` for `denial_timers` — expect no matches (the safeword receipt's separate `denial_lifted` field is intentionally retained and is allowed; the generated `frontend/src/lib/types/api.ts` is not app code and is out of scope).

- [ ] **Step 3: Frontend test + build**

```
npm --prefix frontend run test
npm --prefix frontend run build
```
Expected: green.

- [ ] **Step 4: Push + PR**

```bash
git push -u origin feat/offline-4b-punishment-pool-discipline-unit
gh pr create --title "Offline-first M4b: punishment pool + discipline drone unit + debt/chastity UI" --body "$(cat <<'EOF'
## Summary
Completes the discipline picture from M4a (Addendum B3/B4/B7).

- **Punishment pool** — `PunishmentPoolItem` is the 4th batch artifact; `generate_batch` tops it up (migration `d4e5f6a7b8c9`).
- **Varied pool-fed issuance** — on a miss/fail the discipline unit draws a pool item matching the offence severity (any of the 3 types) and issues it with its flavored reason; deterministic chastity-extension fallback when empty. The draw lives in `discipline/service.py` (no `loop ↔ batch` cycle).
- **Buy-down** now resolves whole `Punishment` rows to `BOUGHT_DOWN` (FIFO).
- **Discipline drone unit** — `standing_orders` surfaces the debt balance + outstanding-penance count (deterministic, state-derived).
- **UI** — the dossier drops the `denial_timers` compat field and exposes `chastity` + `debt`; `DossierBar` shows them; the chat action card renames `set_denial_timer` → `set_chastity`.

Deferred: merit-scaled severity, the safeword receipt `denial_lifted` relabel, regenerating the stale generated `api.ts`, and the privilege-lock type.

## Test plan
- [x] `uv run pytest -q` (live Postgres) — green
- [x] `uv run ruff check .` — clean
- [x] `alembic upgrade head` → `d4e5f6a7b8c9` (round-trip verified)
- [x] frontend `npm run test` + `npm run build` — green
- [ ] CI backend / frontend / e2e green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review (against the spec, before executing)

**Spec coverage (Addendum B3/B4/B7, M4b scope):**
- Punishment pool = 4th batch artifact, refill-when-low ✓ (Tasks 1, 2)
- Discipline unit issues a *fitting, varied* punishment with no LLM present (B4) ✓ (Tasks 3, 4)
- Discipline unit "maintains the debt ledger, posts penance" offline (B3) ✓ (Task 6)
- Token buy-down clears debt + resolves the ledger (B7) ✓ (Task 5)
- Debt + chastity surfaced to the sub (the dossier/offline surface) ✓ (Tasks 7, 8)
- **Deferred (stated):** merit-scaled severity; `denial_lifted` receipt relabel; `api.ts` regen; privilege-lock type.

**Placeholder scan:** new code is complete; modification tasks give exact before/after edits and name files/assertions (located edits, not placeholders). Task 7 Step 2 explicitly notes the red comes after Step 3 (the test edits + field removal together).

**Type consistency:** `parse_batch` now returns a 3-tuple — every caller (`generate_batch`) is updated in the same task. `PoolStatus`/`GenerateResult` gain punishment fields used by `pool_status`/`generate_batch`/the batch schemas/the API. `draw_punishment(*, severity) -> PunishmentPoolItem | None` and `draw_and_issue(*, severity, reason_prefix, now)` match the loop call. `PunishmentPoolItem(type, severity, reason, consumed)` matches the generator and the draw. Dossier `chastity`/`debt` (Task 7) match the frontend `Dossier` interface (Task 8).

**Branch:** `feat/offline-4b-punishment-pool-discipline-unit`. Local-env caveat (clear PYTHONHOME; Postgres up) per `smistress-dev-environment`; Playwright/CI gates fall to CI.
