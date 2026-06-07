from app.db.enums import TaskStatus
from app.persona.disposition import DispositionBand, compute_disposition


def test_ceiling_clamps_severity_at_rock_bottom_merit():
    # worst case: min merit, all misses, but a low ceiling forbids full severity
    disp = compute_disposition(
        -100, [TaskStatus.MISSED] * 5, warmth=30, ceiling=30
    )
    # severity == 100 - standing must not exceed the ceiling (30) -> standing >= 70
    assert disp.standing >= 70
    assert disp.band in (DispositionBand.PLEASED, DispositionBand.WARM)


def test_no_ceiling_allows_full_severity():
    disp = compute_disposition(
        -100, [TaskStatus.MISSED] * 5, warmth=30, ceiling=100
    )
    assert disp.band is DispositionBand.SEVERE
