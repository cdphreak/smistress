from app.config import Settings
from app.db.enums import PunishmentStatus, PunishmentType


def test_punishment_enums_have_expected_members():
    assert {t.value for t in PunishmentType} == {
        "penance_task", "chastity_extension", "token_confiscation"
    }
    assert {s.value for s in PunishmentStatus} == {
        "issued", "served", "bought_down", "expired"
    }


def test_severity_maps_cover_1_to_3():
    s = Settings()
    for sev in (1, 2, 3):
        assert sev in s.debt_by_severity
        assert sev in s.chastity_hours_by_severity
        assert sev in s.confiscation_by_severity
    assert s.buydown_tokens_per_debt >= 1
    assert s.penance_merit_recovery >= 0
