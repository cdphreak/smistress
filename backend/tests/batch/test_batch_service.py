"""Tests for parse_batch parsing of discreetness profile fields."""
from app.batch.service import parse_batch


def test_parse_batch_reads_discreetness_profile():
    from app.db.enums import Discreetness
    content = """
    {"tasks": [
        {"description": "silent kegels", "proof": "honor", "intensity": 20,
         "discreetness": "silent", "required_toy_ids": []}
     ],
     "lines": [],
     "punishments": [
        {"type": "penance_task", "severity": 1, "reason": "quiet lines",
         "discreetness": "discreet", "required_toy_ids": []}
     ]}
    """
    tasks, _lines, punishments = parse_batch(content)
    assert len(tasks) == 1
    assert tasks[0].intensity == 20
    assert tasks[0].discreetness is Discreetness.SILENT
    assert tasks[0].required_toy_ids == []
    assert len(punishments) == 1
    assert punishments[0].discreetness is Discreetness.DISCREET


def test_parse_batch_defaults_discreetness_overt():
    from app.db.enums import Discreetness
    content = """{"tasks": [{"description": "x", "proof": "honor"}], "lines": [],
                  "punishments": [{"type": "penance_task", "severity": 1, "reason": "y"}]}"""
    tasks, _lines, punishments = parse_batch(content)
    assert tasks[0].discreetness is Discreetness.OVERT
    assert tasks[0].intensity == 0
    assert tasks[0].required_toy_ids == []
    assert punishments[0].discreetness is Discreetness.OVERT


def test_parse_batch_normalizes_capitalized_discreetness():
    from app.db.enums import Discreetness
    content = """{"tasks": [{"description": "x", "proof": "honor",
                  "discreetness": "Silent"}], "lines": [], "punishments": []}"""
    tasks, _lines, _punishments = parse_batch(content)
    assert len(tasks) == 1
    assert tasks[0].discreetness is Discreetness.SILENT


def test_parse_batch_skips_out_of_range_intensity():
    content = """{"tasks": [
        {"description": "too intense", "proof": "honor", "intensity": 9999},
        {"description": "fine", "proof": "honor", "intensity": 30}
     ], "lines": [], "punishments": []}"""
    tasks, _lines, _punishments = parse_batch(content)
    # the out-of-range item is skipped; the valid sibling is retained
    assert [t.description for t in tasks] == ["fine"]


def test_parse_batch_skips_invalid_discreetness():
    content = """{"tasks": [
        {"description": "bad", "proof": "honor", "discreetness": "loud"},
        {"description": "good", "proof": "honor", "discreetness": "discreet"}
     ], "lines": [], "punishments": []}"""
    tasks, _lines, _punishments = parse_batch(content)
    assert [t.description for t in tasks] == ["good"]
