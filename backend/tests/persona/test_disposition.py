from app.db.enums import TaskStatus
from app.persona.disposition import (
    DispositionBand,
    compute_disposition,
)

# Governess default: warmth 30. Ceiling 100 = no clamp unless stated.
WARMTH = 30


def test_neutral_default_band_reflects_low_warmth():
    # merit 0, no history, warmth 30 -> standing 30 -> cool register.
    d = compute_disposition(0, [], warmth=WARMTH, ceiling=100)
    assert d.band is DispositionBand.COOL
    assert d.standing == 30
    assert "no recent activity" in d.reason


def test_high_merit_and_passes_warm():
    d = compute_disposition(
        100, [TaskStatus.VERIFIED_PASS] * 5, warmth=WARMTH, ceiling=100
    )
    # 30 + 100*0.4 + min(10, 2*5)*2.0 = 30 + 40 + 20 = 90 -> warm
    assert d.band is DispositionBand.WARM
    assert d.standing == 90
    assert "on-time" in d.reason


def test_low_merit_and_misses_severe():
    d = compute_disposition(
        -100, [TaskStatus.MISSED, TaskStatus.MISSED], warmth=WARMTH, ceiling=100
    )
    # 30 - 40 + (-6)*2.0 = 30 - 40 - 12 = -22 -> clamp 0 -> severe
    assert d.band is DispositionBand.SEVERE
    assert d.standing == 0
    assert "2 recent misses" in d.reason


def test_ceiling_clamps_severity_even_at_rock_bottom():
    # ceiling 40 => severity (100 - standing) may not exceed 40 => standing >= 60.
    d = compute_disposition(-100, [TaskStatus.MISSED] * 5, warmth=WARMTH, ceiling=40)
    assert d.standing == 60
    assert d.band is DispositionBand.PLEASED  # clamped up, can't go cold


def test_warmth_center_shifts_band():
    # A high-warmth character swings warmer at neutral merit.
    d = compute_disposition(0, [], warmth=80, ceiling=100)
    assert d.standing == 80
    assert d.band is DispositionBand.WARM


def test_line_is_band_register_and_reason():
    d = compute_disposition(0, [TaskStatus.MISSED], warmth=WARMTH, ceiling=100)
    # standing 30 - 2*2 = 26 -> cool; line: "cool · exacting — 1 recent miss"
    assert d.line == f"{d.band.value} · exacting — 1 recent miss"


def test_merit_and_mood_are_clamped_to_bounds():
    # Out-of-range merit is clamped (defensive; economy service enforces bounds in M7).
    d_hi = compute_disposition(9999, [], warmth=WARMTH, ceiling=100)
    d_cap = compute_disposition(100, [], warmth=WARMTH, ceiling=100)
    assert d_hi.standing == d_cap.standing
