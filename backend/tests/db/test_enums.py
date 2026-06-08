from app.db.enums import GoalStatus, KinkRating, ProofRequirement, TaskStatus


def test_kink_rating_members():
    assert {r.value for r in KinkRating} == {
        "favorite", "like", "curious", "soft_limit", "hard_limit", "na"
    }


def test_proof_requirement_members():
    assert {r.value for r in ProofRequirement} == {
        "photo", "video", "timer", "honor", "none"
    }


def test_task_status_members():
    assert {s.value for s in TaskStatus} == {
        "assigned", "in_progress", "proof_submitted",
        "verifying", "verified_pass", "verified_fail", "missed",
    }


def test_goal_status_members():
    assert {s.value for s in GoalStatus} == {"active", "achieved", "abandoned"}


def test_llm_availability_values():
    from app.db.enums import LLMAvailability

    assert LLMAvailability.OFFLINE.value == "offline"
    assert LLMAvailability.ONLINE.value == "online"
    assert LLMAvailability("online") is LLMAvailability.ONLINE
