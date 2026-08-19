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

# -- Reference data ----------------------------------------------------------
uoc_type = _pg_enum("THEORY", "THEORY_AND_PRACTICAL", name="uoc_type")

# -- Delivery ----------------------------------------------------------------
mode_of_delivery = _pg_enum("PHYSICAL", "VIRTUAL", name="mode_of_delivery")
weekday_mode = _pg_enum("NOT_AVAILABLE", "PHYSICAL", "VIRTUAL", name="weekday_mode")
weekday = _pg_enum("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", name="weekday")
class_type = _pg_enum("THEORY", "PRACTICAL", name="class_type")
session_type = _pg_enum("THEORY", "PRACTICAL", "ADDITIONAL", name="session_type")

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
)
