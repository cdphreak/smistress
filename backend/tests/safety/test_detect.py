from app.safety import detect


def test_detects_explicit_safeword_phrases():
    assert detect.detect_safeword("safeword") is True
    assert detect.detect_safeword("I want to stop") is True
    assert detect.detect_safeword("please STOP THE SCENE now") is True
    assert detect.detect_safeword("red") is True            # bare safeword token
    assert detect.detect_safeword("  Red  ") is True         # trimmed + case-insensitive


def test_ignores_incidental_uses():
    assert detect.detect_safeword("the red dress was lovely") is False  # 'red' only stands alone
    assert detect.detect_safeword("what's my next task?") is False
    # "i'm done" is a standalone-only safeword: ignored when it's part of a longer message
    assert detect.detect_safeword("i'm done with my report") is False
    assert detect.detect_safeword("I'm done") is True  # said alone -> a real stop


def test_detects_crisis_language():
    assert detect.detect_crisis("I want to die") is True
    assert detect.detect_crisis("I've been thinking about hurting myself") is True
    assert detect.detect_crisis("feeling suicidal") is True
    assert detect.detect_crisis("what's for dinner") is False
