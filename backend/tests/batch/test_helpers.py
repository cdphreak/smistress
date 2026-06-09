from datetime import datetime, timezone

from app.batch import service as batch_svc
from app.db.enums import ProofRequirement
from app.db.models.batch import DroneLine
from app.db.models.batch import DroneLine as _DL
from app.db.models.batch import TaskPoolItem
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_task_pool_item_round_trip(session):
    p = await _profile(session)
    item = TaskPoolItem(
        profile_id=p.id,
        description="Ten slow squats, posture held.",
        proof_requirement=ProofRequirement.HONOR,
        difficulty="standard",
        merit_reward=8,
        merit_miss_penalty=4,
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    assert item.consumed is False
    assert item.proof_requirement is ProofRequirement.HONOR


async def test_drone_line_round_trip(session):
    p = await _profile(session)
    line = DroneLine(
        profile_id=p.id,
        unit="assignment",
        event="task_drop",
        merit_band="mid",
        time_of_day="morning",
        text="Mistress has set you: {task}. Report when complete.",
    )
    session.add(line)
    await session.flush()
    await session.refresh(line)
    assert "{task}" in line.text
    assert line.merit_band == "mid"


def test_merit_band_thresholds():
    assert batch_svc.merit_band(60) == "high"
    assert batch_svc.merit_band(0) == "mid"
    assert batch_svc.merit_band(49) == "mid"
    assert batch_svc.merit_band(-1) == "low"


def test_time_of_day_buckets():
    def at(h):
        return batch_svc.time_of_day(datetime(2026, 6, 9, h, tzinfo=timezone.utc))

    assert at(7) == "morning"
    assert at(14) == "day"
    assert at(19) == "evening"
    assert at(2) == "night"


def _line(event, band, tod, text):
    return _DL(unit="assignment", event=event, merit_band=band, time_of_day=tod, text=text)


def test_pick_line_prefers_exact_band_and_tod():
    lines = [
        _line("task_drop", "any", "any", "generic"),
        _line("task_drop", "high", "evening", "exact"),
        _line("task_drop", "high", "any", "band-only"),
        _line("no_task", "high", "evening", "wrong-event"),
    ]
    picked = batch_svc.pick_line(lines, event="task_drop", band="high", tod="evening", rotation=0)
    assert picked.text == "exact"


def test_pick_line_excludes_mismatched_band():
    lines = [_line("task_drop", "low", "any", "wrong-band")]
    assert batch_svc.pick_line(lines, event="task_drop", band="high", tod="day", rotation=0) is None


def test_pick_line_rotation_is_stable_and_varies():
    lines = [
        _line("task_drop", "any", "any", "a"),
        _line("task_drop", "any", "any", "b"),
    ]
    first = batch_svc.pick_line(lines, event="task_drop", band="mid", tod="day", rotation=0)
    same = batch_svc.pick_line(lines, event="task_drop", band="mid", tod="day", rotation=0)
    other = batch_svc.pick_line(lines, event="task_drop", band="mid", tod="day", rotation=1)
    assert first.text == same.text
    assert {first.text, other.text} == {"a", "b"}
