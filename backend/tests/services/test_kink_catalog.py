from app.services.kink_catalog import KINK_CATALOG, is_known_kink


def test_catalog_is_nonempty_and_unique():
    assert len(KINK_CATALOG) > 0
    assert len(KINK_CATALOG) == len(set(KINK_CATALOG))


def test_is_known_kink():
    assert is_known_kink(KINK_CATALOG[0]) is True
    assert is_known_kink("not_a_real_kink") is False
