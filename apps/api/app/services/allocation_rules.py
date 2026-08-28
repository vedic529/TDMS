"""Universal allocation rules.

Every parser, validator, calendar and editor reads these names. A later Admin
settings screen can replace the constants without a hunt through the codebase.

Assumptions confirmed:
- MSCRIS sits outside the two-day weekly teaching count.
- Teaching days are eight hours; MSCRIS is five hours. A different length is a warning, not a refusal.
"""

from __future__ import annotations

import datetime as dt

THEORY_EXISTS_FOR_EVERY_UNIT = True
THEORY_WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY")
THEORY_MAY_BE_VIRTUAL = True
PRACTICAL_WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY")
PRACTICAL_MAY_BE_VIRTUAL = False
MSCRIS_WEEKDAY = "SATURDAY"
MSCRIS_ALWAYS_VIRTUAL = True
MSCRIS_TRAINER_MUST_BE_APPROVED = False
TEACHING_DAYS_PER_WEEK = 2
STANDARD_CLASS_LENGTH = dt.timedelta(hours=8)
MSCRIS_CLASS_LENGTH = dt.timedelta(hours=5)

VIRTUAL_CLASSROOM_LABELS = {
    "FACE TO FACE VC": "FACE_TO_FACE_VC",
    "FACE TO FACE VIRTUAL": "FACE_TO_FACE_VIRTUAL",
}

WEEKDAY_NAMES = {
    "MONDAY": "MONDAY",
    "TUESDAY": "TUESDAY",
    "WEDNESDAY": "WEDNESDAY",
    "THURSDAY": "THURSDAY",
    "FRIDAY": "FRIDAY",
    "SATURDAY": "SATURDAY",
}

UOC_TYPE_VALUES = {
    "THEORY ONLY": "THEORY_ONLY",
    "THEORY_ONLY": "THEORY_ONLY",
    "PRACTICAL ONLY": "PRACTICAL_ONLY",
    "PRACTICAL_ONLY": "PRACTICAL_ONLY",
    "THEORY AND PRACTICAL": "THEORY_AND_PRACTICAL",
    "THEORY_AND_PRACTICAL": "THEORY_AND_PRACTICAL",
}

MODE_VALUES = {"F2FP": "F2FP", "F2FPV": "F2FPV", "F2FV": "F2FV"}

STREAM_WEEKDAYS = {
    "THEORY": THEORY_WEEKDAYS,
    "PRACTICAL": PRACTICAL_WEEKDAYS,
    "MSCRIS": (MSCRIS_WEEKDAY,),
}


def allowed_weekdays(stream: str) -> tuple[str, ...]:
    return STREAM_WEEKDAYS[stream]


def stream_may_be_virtual(stream: str) -> bool:
    if stream == "PRACTICAL":
        return PRACTICAL_MAY_BE_VIRTUAL
    if stream == "MSCRIS":
        return MSCRIS_ALWAYS_VIRTUAL
    return THEORY_MAY_BE_VIRTUAL


def virtual_kind_for(label: str) -> str | None:
    compact = " ".join(label.upper().split())
    return VIRTUAL_CLASSROOM_LABELS.get(compact)


def class_length(start: dt.time, end: dt.time) -> dt.timedelta:
    start_delta = dt.timedelta(hours=start.hour, minutes=start.minute)
    end_delta = dt.timedelta(hours=end.hour, minutes=end.minute)
    return end_delta - start_delta


def expected_class_length(stream: str) -> dt.timedelta:
    if stream == "MSCRIS":
        return MSCRIS_CLASS_LENGTH
    return STANDARD_CLASS_LENGTH


def is_standard_class_length(start: dt.time, end: dt.time, stream: str = "THEORY") -> bool:
    return class_length(start, end) == expected_class_length(stream)


def teaching_day_count(sessions: list[tuple[str, str]]) -> int:
    """Count distinct teaching weekdays, excluding MSCRIS."""
    days = {weekday for stream, weekday in sessions if stream != "MSCRIS"}
    return len(days)


def mode_matrix(has_practical: bool, mode: str) -> dict[str, int] | None:
    """Expected physical/virtual day counts. None means the combination is refused."""
    if not has_practical:
        return {
            "F2FP": {"theory_physical": 2, "theory_virtual": 0, "practical_physical": 0},
            "F2FPV": {"theory_physical": 1, "theory_virtual": 1, "practical_physical": 0},
            "F2FV": {"theory_physical": 0, "theory_virtual": 2, "practical_physical": 0},
        }.get(mode)
    if mode == "F2FV":
        return None
    return {
        "F2FP": {"theory_physical": 1, "theory_virtual": 0, "practical_physical": 1},
        "F2FPV": {"theory_physical": 0, "theory_virtual": 1, "practical_physical": 1},
    }.get(mode)
