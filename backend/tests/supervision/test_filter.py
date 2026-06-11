from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.db.enums import Discreetness, SupervisionMode
from app.supervision import filter as sup_filter


@dataclass
class _Toy:
    id: uuid.UUID
    discreet_capable: bool


def _toys(*flags: bool) -> dict[str, _Toy]:
    out = {}
    for cap in flags:
        tid = uuid.uuid4()
        out[str(tid)] = _Toy(id=tid, discreet_capable=cap)
    return out


def test_discreetness_members():
    assert {d.value for d in Discreetness} == {"overt", "discreet", "silent"}


def test_mode_min_discreetness():
    M, D = SupervisionMode, Discreetness
    assert sup_filter.mode_min_discreetness(M.FULL) is D.OVERT
    assert sup_filter.mode_min_discreetness(M.DISCREET) is D.DISCREET
    assert sup_filter.mode_min_discreetness(M.HOMEOFFICE) is D.SILENT
    assert sup_filter.mode_min_discreetness(M.TASK) is D.OVERT
    assert sup_filter.mode_min_discreetness(M.VACATION) is D.OVERT


def test_full_mode_allows_everything():
    # the intensity ceiling is a safety invariant that applies in ALL modes (§9),
    # so "everything" here means within the ceiling.
    assert sup_filter.task_allowed(
        SupervisionMode.FULL, discreetness=Discreetness.OVERT, intensity=100,
        required_toy_ids=[], toys_by_id={}, intensity_ceiling=100,
    ) is True


def test_discreet_mode_rejects_overt_task():
    assert sup_filter.task_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.OVERT, intensity=0,
        required_toy_ids=[], toys_by_id={}, intensity_ceiling=100,
    ) is False


def test_discreet_mode_allows_discreet_and_silent():
    for d in (Discreetness.DISCREET, Discreetness.SILENT):
        assert sup_filter.task_allowed(
            SupervisionMode.DISCREET, discreetness=d, intensity=0,
            required_toy_ids=[], toys_by_id={}, intensity_ceiling=100,
        ) is True


def test_homeoffice_requires_silent():
    assert sup_filter.task_allowed(
        SupervisionMode.HOMEOFFICE, discreetness=Discreetness.DISCREET, intensity=0,
        required_toy_ids=[], toys_by_id={}, intensity_ceiling=100,
    ) is False
    assert sup_filter.task_allowed(
        SupervisionMode.HOMEOFFICE, discreetness=Discreetness.SILENT, intensity=0,
        required_toy_ids=[], toys_by_id={}, intensity_ceiling=100,
    ) is True


def test_intensity_ceiling_rejects_too_intense():
    assert sup_filter.task_allowed(
        SupervisionMode.FULL, discreetness=Discreetness.OVERT, intensity=80,
        required_toy_ids=[], toys_by_id={}, intensity_ceiling=50,
    ) is False


def test_required_toy_must_be_discreet_capable_under_discreet():
    toys = _toys(False)  # one non-discreet toy
    tid = next(iter(toys))
    assert sup_filter.task_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.SILENT, intensity=0,
        required_toy_ids=[tid], toys_by_id=toys, intensity_ceiling=100,
    ) is False
    toys2 = _toys(True)
    tid2 = next(iter(toys2))
    assert sup_filter.task_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.SILENT, intensity=0,
        required_toy_ids=[tid2], toys_by_id=toys2, intensity_ceiling=100,
    ) is True


def test_missing_required_toy_rejected_under_discreet():
    assert sup_filter.task_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.SILENT, intensity=0,
        required_toy_ids=[str(uuid.uuid4())], toys_by_id={}, intensity_ceiling=100,
    ) is False


def test_required_toy_ignored_under_full():
    # full mode never checks required-toy discreetness
    toys = _toys(False)
    tid = next(iter(toys))
    assert sup_filter.task_allowed(
        SupervisionMode.FULL, discreetness=Discreetness.OVERT, intensity=0,
        required_toy_ids=[tid], toys_by_id=toys, intensity_ceiling=100,
    ) is True


def test_punishment_allowed_mirrors_discreetness_floor():
    assert sup_filter.punishment_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.OVERT,
        required_toy_ids=[], toys_by_id={},
    ) is False
    assert sup_filter.punishment_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.SILENT,
        required_toy_ids=[], toys_by_id={},
    ) is True


def test_content_filter_directive_per_mode():
    assert sup_filter.content_filter_directive(SupervisionMode.FULL) is None
    assert "discreet" in sup_filter.content_filter_directive(SupervisionMode.DISCREET).lower()
    assert "silent" in sup_filter.content_filter_directive(SupervisionMode.HOMEOFFICE).lower()
    assert "deadline" in sup_filter.content_filter_directive(SupervisionMode.TASK).lower()
    assert sup_filter.content_filter_directive(SupervisionMode.VACATION) is None


def test_punishment_required_toy_must_be_discreet_capable():
    toys = _toys(False)
    tid = next(iter(toys))
    assert sup_filter.punishment_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.SILENT,
        required_toy_ids=[tid], toys_by_id=toys,
    ) is False
    toys2 = _toys(True)
    tid2 = next(iter(toys2))
    assert sup_filter.punishment_allowed(
        SupervisionMode.DISCREET, discreetness=Discreetness.SILENT,
        required_toy_ids=[tid2], toys_by_id=toys2,
    ) is True
