import pytest

from app.persona.compiler import compile_system_prompt
from app.persona.disposition import compute_disposition
from tests.persona.fixtures import SCENARIOS


@pytest.mark.parametrize("scn", SCENARIOS, ids=lambda s: s.name)
def test_disposition_band_matches_golden(scn):
    disp = compute_disposition(scn.merit, scn.outcomes, warmth=scn.warmth, ceiling=scn.ceiling)
    assert disp.band is scn.expected_band, f"{scn.name}: got {disp.band}"
    assert scn.expected_reason_contains in disp.reason


@pytest.mark.parametrize("scn", SCENARIOS, ids=lambda s: s.name)
def test_compiled_prompt_invariants_hold(scn):
    disp = compute_disposition(scn.merit, scn.outcomes, warmth=scn.warmth, ceiling=scn.ceiling)
    state = "HARD LIMITS (never cross): " + ", ".join(scn.hard_limits)
    prompt = compile_system_prompt(
        character_block="## WHO YOU ARE\nYou are Headmistress.",
        authoritative_state=state,
        disposition=disp,
        memory=None,
    )
    # Identity, safety contract, and EVERY hard limit must always be present.
    assert "Headmistress" in prompt
    assert "SAFETY" in prompt
    assert "safeword" in prompt.lower()
    for limit in scn.hard_limits:
        assert limit in prompt, f"{scn.name}: hard limit {limit!r} missing from prompt"
    # Severity never exceeds the ceiling.
    assert (100 - disp.standing) <= scn.ceiling
