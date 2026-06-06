from dataclasses import dataclass, field

from app.db.enums import TaskStatus
from app.persona.disposition import DispositionBand


@dataclass(frozen=True)
class PersonaScenario:
    name: str
    merit: int
    outcomes: list[TaskStatus]
    warmth: int
    ceiling: int
    hard_limits: list[str] = field(default_factory=list)
    expected_band: DispositionBand = DispositionBand.NEUTRAL
    expected_reason_contains: str = ""


# Golden scenarios spanning the disposition range and the ceiling clamp.
SCENARIOS: tuple[PersonaScenario, ...] = (
    PersonaScenario(
        name="fresh_default",
        merit=0, outcomes=[], warmth=30, ceiling=100,
        hard_limits=["blood"],
        expected_band=DispositionBand.COOL,
        expected_reason_contains="no recent activity",
    ),
    PersonaScenario(
        name="model_student",
        merit=100, outcomes=[TaskStatus.VERIFIED_PASS] * 5, warmth=30, ceiling=100,
        hard_limits=["blood", "breath_play"],
        expected_band=DispositionBand.WARM,
        expected_reason_contains="on-time",
    ),
    PersonaScenario(
        name="repeated_misses",
        merit=-100, outcomes=[TaskStatus.MISSED, TaskStatus.MISSED], warmth=30, ceiling=100,
        hard_limits=["blood"],
        expected_band=DispositionBand.SEVERE,
        expected_reason_contains="2 recent misses",
    ),
    PersonaScenario(
        name="low_ceiling_protects",
        merit=-100, outcomes=[TaskStatus.MISSED] * 5, warmth=30, ceiling=30,
        hard_limits=["blood"],
        expected_band=DispositionBand.PLEASED,  # severity clamped: standing forced to 70
        expected_reason_contains="recent miss",
    ),
)
