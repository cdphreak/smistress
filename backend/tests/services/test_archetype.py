from app.services.archetype import (
    ARCHETYPES,
    MAX_ANSWER,
    QUESTIONNAIRE,
    score_archetypes,
    unknown_answer_ids,
)


def test_questionnaire_ids_unique_and_archetypes_known():
    ids = [q["id"] for q in QUESTIONNAIRE]
    assert len(ids) == len(set(ids))  # no duplicate ids
    assert all(q["archetype"] in ARCHETYPES for q in QUESTIONNAIRE)


def test_all_max_answers_score_100_for_that_archetype():
    answers = {q["id"]: MAX_ANSWER for q in QUESTIONNAIRE}
    scores = score_archetypes(answers)
    assert set(scores) == set(ARCHETYPES)
    assert all(v == 100 for v in scores.values())


def test_unanswered_and_zero_score_zero():
    assert all(v == 0 for v in score_archetypes({}).values())


def test_partial_answers_scale_linearly():
    # answer every 'submissive' statement at 2 of 4 -> 50%
    answers = {q["id"]: 2 for q in QUESTIONNAIRE if q["archetype"] == "submissive"}
    scores = score_archetypes(answers)
    assert scores["submissive"] == 50
    assert scores["slave"] == 0  # untouched archetype stays 0


def test_unknown_answer_ids_detected():
    assert unknown_answer_ids({"q1": 3, "bogus": 1}) == {"bogus"}
    assert unknown_answer_ids({"q1": 3}) == set()
