from app.safety import filter as sf


def test_scan_flags_hard_limit_terms_case_insensitively():
    hard = ["blood", "breath_play"]
    assert sf.scan_violations("Bring me your blood.", hard) == ["blood"]
    # underscore term also matches its spaced form in prose
    assert sf.scan_violations("a little breath play tonight", hard) == ["breath_play"]


def test_scan_clean_message_has_no_violations():
    assert sf.scan_violations("Kneel and recite your mantra.", ["blood"]) == []


def test_corrective_note_names_the_limits():
    note = sf.corrective_note(["blood"])
    assert "blood" in note
    assert "hard limit" in note.lower()


def test_safe_reply_is_nonempty_and_limit_free():
    assert sf.SAFE_REPLY
    assert sf.scan_violations(sf.SAFE_REPLY, ["blood", "breath_play"]) == []
