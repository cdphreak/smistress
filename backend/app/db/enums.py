from __future__ import annotations

import enum


class KinkRating(str, enum.Enum):
    FAVORITE = "favorite"
    LIKE = "like"
    CURIOUS = "curious"
    SOFT_LIMIT = "soft_limit"
    HARD_LIMIT = "hard_limit"
    NA = "na"


class ToyType(str, enum.Enum):
    """Controlled vocabulary for the toy inventory (spec 4).

    A fixed set so toy types can be referenced as task requirements (e.g. the
    mistress requiring a specific implement). Stored as a plain string column;
    this enum validates input and is exposed to the UI via the questionnaire.
    """

    VIBRATOR = "vibrator"
    WAND = "wand"
    DILDO = "dildo"
    BUTT_PLUG = "butt_plug"
    ANAL_BEADS = "anal_beads"
    COCK_RING = "cock_ring"
    CHASTITY_CAGE = "chastity_cage"
    NIPPLE_CLAMPS = "nipple_clamps"
    COLLAR = "collar"
    LEASH = "leash"
    GAG = "gag"
    BLINDFOLD = "blindfold"
    RESTRAINTS = "restraints"
    ROPE = "rope"
    SPREADER_BAR = "spreader_bar"
    PADDLE = "paddle"
    CROP = "crop"
    FLOGGER = "flogger"
    OTHER = "other"


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


class LLMAvailability(str, enum.Enum):
    """System-wide presence of the home-box LLM (Addendum B2). Computed from the
    last heartbeat's freshness, not stored as a column."""

    OFFLINE = "offline"
    ONLINE = "online"
