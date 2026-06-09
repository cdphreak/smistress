from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.batch.prompt import build_generation_prompt
from app.config import Settings
from app.db.enums import ProofRequirement
from app.db.models.batch import DroneLine, TaskPoolItem
from app.db.models.character import CharacterModel
from app.db.models.economy import EconomyState
from app.db.models.profile import SubProfile
from app.llm.provider import LLMProvider

# Module-level Settings instance, matching the convention in availability/service.py.
_settings = Settings()


class ProfileNotFound(Exception):
    pass


# --- Banding (tunable; mirrors the spirit of the disposition bands) ---------
_HIGH_MERIT = 50
_LOW_MERIT = 0


def merit_band(merit: int) -> str:
    if merit >= _HIGH_MERIT:
        return "high"
    if merit < _LOW_MERIT:
        return "low"
    return "mid"


def time_of_day(now: datetime) -> str:
    h = now.hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "day"
    if 17 <= h < 22:
        return "evening"
    return "night"


def _score(line: DroneLine, band: str, tod: str) -> int:
    """Specificity score for a candidate line; -1 means 'excluded' (wrong band/tod)."""
    score = 0
    if line.merit_band == band:
        score += 2
    elif line.merit_band == "any":
        score += 1
    else:
        return -1
    if line.time_of_day == tod:
        score += 2
    elif line.time_of_day == "any":
        score += 1
    else:
        return -1
    return score


def pick_line(
    lines: list[DroneLine], *, event: str, band: str, tod: str, rotation: int
) -> DroneLine | None:
    """Most-specific matching line for an event, rotated deterministically.

    ``rotation`` (e.g. the day ordinal) selects among equally-specific candidates
    so the line is stable within a render/day but varies day to day. Returns None
    when the bank has no usable line for the event (caller falls back to a
    hardcoded line so the drones always speak).
    """
    scored = [(line, _score(line, band, tod)) for line in lines if line.event == event]
    scored = [(line, s) for line, s in scored if s >= 0]
    if not scored:
        return None
    best = max(s for _, s in scored)
    top = sorted((line for line, s in scored if s == best), key=lambda line: str(line.id))
    return top[rotation % len(top)]


@dataclass
class PoolStatus:
    task_pool: int  # unconsumed task pool items
    line_bank: int  # total drone lines
    task_pool_low: bool
    line_bank_low: bool


async def pool_status(session: AsyncSession, profile_id: uuid.UUID) -> PoolStatus:
    tasks = (await session.execute(
        select(func.count())
        .select_from(TaskPoolItem)
        .where(TaskPoolItem.profile_id == profile_id, TaskPoolItem.consumed.is_(False))
    )).scalar_one()
    lines = (await session.execute(
        select(func.count()).select_from(DroneLine).where(DroneLine.profile_id == profile_id)
    )).scalar_one()
    return PoolStatus(
        task_pool=tasks,
        line_bank=lines,
        task_pool_low=tasks <= _settings.batch_task_low,
        line_bank_low=lines <= _settings.batch_line_low,
    )


# First top-level JSON object in the model's reply (it may add prose around it).
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_VALID_BANDS = {"low", "mid", "high", "any"}
_VALID_TODS = {"morning", "day", "evening", "night", "any"}
_VALID_UNITS = {"assignment", "reminder"}


class _TaskGen(BaseModel):
    description: str
    proof: ProofRequirement
    merit_reward: int = 0
    merit_fail_penalty: int = 0
    merit_miss_penalty: int = 0
    difficulty: str = "standard"

    @field_validator("proof", "difficulty", mode="before")
    @classmethod
    def _lower(cls, v: object) -> object:
        return str(v).strip().lower() if v is not None else v


class _LineGen(BaseModel):
    unit: str
    event: str
    text: str
    merit_band: str = "any"
    time_of_day: str = "any"

    # Normalise before the membership checks so capitalised model output
    # (e.g. "Assignment", "Mid") is accepted rather than silently dropped.
    @field_validator("unit", "merit_band", "time_of_day", mode="before")
    @classmethod
    def _lower(cls, v: object) -> object:
        return str(v).strip().lower() if v is not None else v

    @field_validator("unit")
    @classmethod
    def _unit(cls, v: str) -> str:
        if v not in _VALID_UNITS:
            raise ValueError("bad unit")
        return v

    @field_validator("merit_band")
    @classmethod
    def _band(cls, v: str) -> str:
        if v not in _VALID_BANDS:
            raise ValueError("bad band")
        return v

    @field_validator("time_of_day")
    @classmethod
    def _tod(cls, v: str) -> str:
        if v not in _VALID_TODS:
            raise ValueError("bad tod")
        return v


def parse_batch(content: str) -> tuple[list[_TaskGen], list[_LineGen]]:
    """Best-effort parse of the model's reply. Malformed JSON or invalid items are
    skipped (never raises) so a bad generation simply adds nothing."""
    match = _JSON_RE.search(content)
    if not match:
        return [], []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return [], []
    if not isinstance(data, dict):
        return [], []
    raw_tasks = data.get("tasks")
    raw_lines = data.get("lines")
    tasks: list[_TaskGen] = []
    for raw in raw_tasks if isinstance(raw_tasks, list) else []:
        try:
            tasks.append(_TaskGen.model_validate(raw))
        except ValidationError:
            continue
    lines: list[_LineGen] = []
    for raw in raw_lines if isinstance(raw_lines, list) else []:
        try:
            lines.append(_LineGen.model_validate(raw))
        except ValidationError:
            continue
    return tasks, lines


@dataclass
class GenerateResult:
    tasks_added: int
    lines_added: int
    task_pool: int  # unconsumed total after the run
    line_bank: int  # total after the run


async def _profile_for_generation(
    session: AsyncSession, profile_id: uuid.UUID
) -> tuple[SubProfile, CharacterModel | None, EconomyState | None]:
    profile = (await session.execute(
        select(SubProfile)
        .where(SubProfile.id == profile_id)
        .options(selectinload(SubProfile.goals), selectinload(SubProfile.kinks))
    )).scalar_one_or_none()
    if profile is None:
        raise ProfileNotFound(str(profile_id))
    character = (await session.execute(
        select(CharacterModel).where(CharacterModel.profile_id == profile_id)
    )).scalar_one_or_none()
    econ = (await session.execute(
        select(EconomyState).where(EconomyState.profile_id == profile_id)
    )).scalar_one_or_none()
    return profile, character, econ


async def generate_batch(
    session: AsyncSession, profile_id: uuid.UUID, provider: LLMProvider
) -> GenerateResult:
    """Call the LLM to refill the offline pools, topping each up to its target.

    Only as many parsed items as are needed to reach the target are persisted.
    Caller commits.
    """
    profile, character, econ = await _profile_for_generation(session, profile_id)
    status = await pool_status(session, profile_id)
    want_tasks = max(0, _settings.batch_task_target - status.task_pool)
    want_lines = max(0, _settings.batch_line_target - status.line_bank)

    messages = build_generation_prompt(
        profile, character, econ, task_count=want_tasks, line_count=want_lines
    )
    reply = await provider.chat(messages)
    parsed_tasks, parsed_lines = parse_batch(reply.content)

    added_tasks = 0
    for gen in parsed_tasks[:want_tasks]:
        session.add(TaskPoolItem(
            profile_id=profile_id,
            description=gen.description,
            proof_requirement=gen.proof,
            difficulty=gen.difficulty,
            merit_reward=gen.merit_reward,
            merit_fail_penalty=gen.merit_fail_penalty,
            merit_miss_penalty=gen.merit_miss_penalty,
        ))
        added_tasks += 1
    added_lines = 0
    for gen in parsed_lines[:want_lines]:
        session.add(DroneLine(
            profile_id=profile_id,
            unit=gen.unit,
            event=gen.event,
            merit_band=gen.merit_band,
            time_of_day=gen.time_of_day,
            text=gen.text,
        ))
        added_lines += 1
    await session.flush()
    # Post-run totals are the pre-run counts plus what we just added — no re-query.
    return GenerateResult(
        added_tasks,
        added_lines,
        status.task_pool + added_tasks,
        status.line_bank + added_lines,
    )
