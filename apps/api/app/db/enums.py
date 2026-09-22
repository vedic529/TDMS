"""PostgreSQL enum types for the approved Schema v1 (data dictionary, "Enum types").

Enums are used where the domain is **closed and stable**. Open-ended domains —
course status and reason codes — use lookup tables instead (proposal §7.5, §16),
so that the approved list can change without a schema migration.

`access_level` is deliberately an enum rather than a lookup table: Access Model
v1.1 states TDMS uses exactly four access levels, and an enum makes a fifth one
require a reviewed migration instead of an `INSERT`. The declaration order is
ascending privilege, so PostgreSQL's own enum ordering answers "at least this
level" — `access_level >= 'ADMIN'` — and the "may only request a *higher* role"
rule becomes a CHECK constraint rather than application code.
"""

from __future__ import annotations

from sqlalchemy import Enum

_KW = {"create_type": True, "native_enum": True}


def _pg_enum(*values: str, name: str) -> Enum:
    return Enum(*values, name=name, **_KW)


# -- Identity and access -----------------------------------------------------
# Ascending privilege. VIEWER is the default for an authenticated user from an
# approved tenant (Access Model v1.1 §3).
access_level = _pg_enum("VIEWER", "DATA_EDITOR", "ADMIN", "SUPER_ADMIN", name="access_level")
account_status = _pg_enum("ACTIVE", "INACTIVE", "DISABLED", name="account_status")

# A user may request a higher role. CANCELLED exists so a requester can withdraw
# without the row being deleted — request history is never destroyed.
access_request_status = _pg_enum(
    "PENDING", "APPROVED", "DENIED", "CANCELLED", name="access_request_status"
)

# -- Students ----------------------------------------------------------------
coe_status = _pg_enum("COE", "NON_COE", name="coe_status")

# A student record's lifecycle. ACTIVE is the default; the partial unique index
# on `students` permits at most one ACTIVE (non-deleted) row per Student ID, so a
# person enrolled in two qualifications carries one ACTIVE and one other status.
student_status = _pg_enum(
    "ACTIVE", "COMPLETED", "CANCELLED", "NOT_YET_STARTED", name="student_status"
)

# How the rolling-timetable intake was resolved for a student.
# MATCHED — an intake was found. TBD — the qualification has no rolling timetable
# yet, so no intake could be worked out. NOT_APPLICABLE — a Credit Transfer
# student, who has no intake by the approved rule of 13 August 2026.
# `student_group_id` stays NULL in the TBD and NOT_APPLICABLE cases.
student_intake_match = _pg_enum("MATCHED", "TBD", "NOT_APPLICABLE", name="student_intake_match")

# -- Reference data ----------------------------------------------------------
# `PRACTICAL` added 10 September 2026. A unit that is entirely practical had
# no honest value: `THEORY_AND_PRACTICAL` asserts theory it does not have.
# `uoc_type_allocation` below has always had `PRACTICAL_ONLY`, so a class
# could be scheduled that way while the unit could not be described that way.
uoc_type = _pg_enum("THEORY", "THEORY_AND_PRACTICAL", "PRACTICAL", name="uoc_type")

# -- Delivery ----------------------------------------------------------------
mode_of_delivery = _pg_enum("PHYSICAL", "VIRTUAL", name="mode_of_delivery")
weekday_mode = _pg_enum("NOT_AVAILABLE", "PHYSICAL", "VIRTUAL", name="weekday_mode")
weekday = _pg_enum("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", name="weekday")
# THEORY_AND_PRACTICAL (27 August 2026): "Theory and Practical" on a trainer
# record means eligible for **both**, and the form already offered the option.
class_type = _pg_enum("THEORY", "PRACTICAL", "THEORY_AND_PRACTICAL", name="class_type")
session_type = _pg_enum("THEORY", "PRACTICAL", "ADDITIONAL", name="session_type")

# -- Rolling timetable -------------------------------------------------------
# One stored value per Intake and Week that carries a requirement. NA is not a
# stored type: absence of a row is what NA means.
rolling_schedule_type = _pg_enum("UNIT", "BREAK", "ASSESSMENT_WEEK", name="rolling_schedule_type")

# Closed list of training packages. A twelfth value needs a reviewed migration.
TRAINING_PACKAGE_VALUES: tuple[str, ...] = (
    "CHC",
    "BSB",
    "FNS",
    "SIT",
    "AUR",
    "CPC",
    "ICT",
    "RII",
    "TLI",
    "UEE",
    "AHC",
)
training_package = _pg_enum(*TRAINING_PACKAGE_VALUES, name="training_package")

# -- Allocation records ------------------------------------------------------
uoc_type_allocation = _pg_enum(
    "THEORY_ONLY", "PRACTICAL_ONLY", "THEORY_AND_PRACTICAL", name="uoc_type_allocation"
)
allocation_mode_of_delivery = _pg_enum("F2FP", "F2FPV", "F2FV", name="allocation_mode_of_delivery")
allocation_stream = _pg_enum("THEORY", "PRACTICAL", "MSCRIS", name="allocation_stream")
allocation_weekday = _pg_enum(
    "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", name="allocation_weekday"
)
session_delivery_mode = _pg_enum("PHYSICAL", "VIRTUAL", name="session_delivery_mode")
virtual_classroom_kind = _pg_enum("FACE_TO_FACE_VC", name="virtual_classroom_kind")
intake_match_status = _pg_enum("MATCHED", "NOT_FOUND", name="intake_match_status")
suggestion_entity_type = _pg_enum(
    "COLLEGE", "CAMPUS", "QUALIFICATION", "UNIT", "FACILITY", "TRAINER",
    # ROLLING and CITY (15 September 2026): a class the rolling timetable does
    # not account for, and a city the City Dictionary does not hold.
    "ROLLING", "CITY",
    name="suggestion_entity_type"
)
# EXCEPTION and WITHDRAWN (26 August 2026): an accepted exception is recorded
# in this same table, distinguished by status, so a value cannot be pending and
# excepted at once and promoting an exception reuses the resolve path unchanged.
# WITHDRAWN exists for a future need and is not written by the current code.
suggestion_status = _pg_enum(
    "PENDING", "ADDED", "MAPPED", "DELETED", "REJECTED", "EXCEPTION", "WITHDRAWN",
    name="suggestion_status",
)
suggestion_source = _pg_enum(
    "ALLOCATION_IMPORT",
    "ROLLING_IMPORT",
    "MANUAL",
    "STUDENT_IMPORT",
    # So the shared queue can say a value came from a trainer file.
    "TRAINER_IMPORT",
    name="suggestion_source",
)
apply_mode = _pg_enum("REPLACE", "MERGE", name="apply_mode")

# -- Imports -----------------------------------------------------------------
staged_row_status = _pg_enum(
    "READY",
    "NEEDS_CORRECTION",
    "DUPLICATE",
    "UNMATCHED_REFERENCE",
    "EXCLUDED_BY_USER",
    name="staged_row_status",
)

# -- Activity records --------------------------------------------------------
activity_action = _pg_enum(
    "SIGN_IN",
    "SIGN_OUT",
    "CREATE",
    "UPDATE",
    "DELETE",
    "RESTORE",
    "IMPORT",
    "EXPORT",
    "TIMETABLE_SAVE",
    "TIMETABLE_GENERATION",
    "CANCELLATION_AFTER_UPDATE",
    "OVERRIDE",
    "ACCESS_DENIED",
    # -- Access Model v1.1 -------------------------------------------------
    "ACCESS_REQUEST_SUBMITTED",
    "ACCESS_REQUEST_APPROVED",
    "ACCESS_REQUEST_DENIED",
    "ACCESS_REQUEST_CANCELLED",
    "ROLE_CHANGED",
    "ACCOUNT_STATUS_CHANGED",
    # A Super Admin granting access directly, distinct from ROLE_CHANGED
    # (nothing changed) and from CREATE (a reference record).
    "USER_PROVISIONED",
    name="activity_action",
)
activity_result = _pg_enum(
    "COMPLETED",
    "REJECTED_BY_VALIDATION",
    "CANCELLED_BY_USER",
    "FAILED_SYSTEM_ERROR",
    name="activity_result",
)
ms_sign_in_result = _pg_enum("SUCCESS", "FAILURE", name="ms_sign_in_result")
access_decision = _pg_enum("GRANTED", "DENIED", name="access_decision")

#: Every enum type name, used by the migration to drop them on downgrade.
ALL_ENUM_NAMES: tuple[str, ...] = (
    "access_level",
    "access_request_status",
    "account_status",
    "coe_status",
    "student_status",
    "student_intake_match",
    "uoc_type",
    "mode_of_delivery",
    "weekday_mode",
    "weekday",
    "class_type",
    "session_type",
    "staged_row_status",
    "activity_action",
    "activity_result",
    "ms_sign_in_result",
    "access_decision",
    "rolling_schedule_type",
    "training_package",
    "uoc_type_allocation",
    "allocation_mode_of_delivery",
    "allocation_stream",
    "allocation_weekday",
    "session_delivery_mode",
    "virtual_classroom_kind",
    "intake_match_status",
    "suggestion_entity_type",
    "suggestion_status",
    "suggestion_source",
    "apply_mode",
)
