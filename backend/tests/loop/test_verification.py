from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.db.models.loop import TaskTimer
from app.loop.verification import verify_media, verify_none, verify_timer


def test_verify_none_auto_passes():
    v = verify_none()
    assert v.verdict == "pass"


def test_verify_timer_pass_when_enough_elapsed():
    start = datetime.now(timezone.utc)
    timer = TaskTimer(required_seconds=600, started_at=start, stopped_at=start + timedelta(seconds=700))
    v = verify_timer(timer)
    assert v.verdict == "pass"
    assert v.confidence == 100


def test_verify_timer_fail_when_too_short():
    start = datetime.now(timezone.utc)
    timer = TaskTimer(required_seconds=600, started_at=start, stopped_at=start + timedelta(seconds=120))
    v = verify_timer(timer)
    assert v.verdict == "fail"
    assert "insufficient" in v.issues[0].lower()


def test_verify_timer_reproof_when_not_stopped():
    timer = TaskTimer(required_seconds=600, started_at=datetime.now(timezone.utc), stopped_at=None)
    v = verify_timer(timer)
    assert v.verdict == "re_proof"


def test_verify_media_autopasses_without_vision():
    v = verify_media(Settings(vision_model=None))
    assert v.verdict == "pass"
    assert v.confidence is None
    assert "auto" in v.reasoning.lower()


def test_verify_media_pending_when_vision_configured():
    v = verify_media(Settings(vision_model="qwen2.5-vl"))
    assert v.verdict == "pending"   # real vision verification is M6b
