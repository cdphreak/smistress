from __future__ import annotations

import enum


class KinkRating(str, enum.Enum):
    FAVORITE = "favorite"
    LIKE = "like"
    CURIOUS = "curious"
    SOFT_LIMIT = "soft_limit"
    HARD_LIMIT = "hard_limit"
    NA = "na"


class GoalStatus(str, enum.Enum):
    ACTIVE = "active"
    ACHIEVED = "achieved"
    ABANDONED = "abandoned"


class ProofRequirement(str, enum.Enum):
    PHOTO = "photo"
    VIDEO = "video"
    TIMER = "timer"
    HONOR = "honor"
    NONE = "none"


class TaskStatus(str, enum.Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PROOF_SUBMITTED = "proof_submitted"
    VERIFYING = "verifying"
    VERIFIED_PASS = "verified_pass"
    VERIFIED_FAIL = "verified_fail"
    MISSED = "missed"
