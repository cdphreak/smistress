from app.db.enums import TaskStatus
from app.persona.compiler import compile_system_prompt
from app.persona.disposition import compute_disposition


def test_prompt_has_all_sections_and_disposition_register():
    disp = compute_disposition(-100, [TaskStatus.MISSED, TaskStatus.MISSED], warmth=30, ceiling=100)
    prompt = compile_system_prompt(
        character_block="## WHO YOU ARE\nYou are Headmistress.",
        authoritative_state="HARD LIMITS: blood. MERIT: -100.",
        disposition=disp,
        memory=None,
    )
    assert "## WHO YOU ARE" in prompt
    assert "AUTHORITATIVE STATE" in prompt
    assert "blood" in prompt  # limits carried verbatim
    assert "SAFETY" in prompt
    assert disp.reason in prompt
    assert disp.band.value in prompt
    # memory seam present but empty in M4
    assert "MEMORY" in prompt
    assert "none yet" in prompt.lower()


def test_memory_section_renders_when_provided():
    disp = compute_disposition(0, [], warmth=30, ceiling=100)
    prompt = compile_system_prompt(
        character_block="x",
        authoritative_state="y",
        disposition=disp,
        memory="She has shown a pattern of strong Monday performance.",
    )
    assert "strong Monday performance" in prompt


def test_safety_section_states_nonnegotiable_rules():
    disp = compute_disposition(0, [], warmth=30, ceiling=100)
    prompt = compile_system_prompt(
        character_block="x", authoritative_state="y", disposition=disp, memory=None
    ).lower()
    assert "hard limit" in prompt
    assert "safeword" in prompt
    assert "ceiling" in prompt
