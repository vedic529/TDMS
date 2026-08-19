"""Central TDMS authorisation policy (Access Model v1.1).

Every access decision in the API resolves through this module. Route handlers
never test `user.access_level == "ADMIN"` themselves — scattering that comparison
across dozens of handlers is how one of them ends up spelled differently and
quietly lets the wrong people in.

The API is authoritative. The frontend mirrors these rules in
`apps/web/src/lib/permissions.ts` so the interface does not offer actions that
will be refused, but hiding a button is a courtesy, not a control.
"""

from __future__ import annotations

from enum import Enum


class AccessLevel(str, Enum):
    """The four TDMS access levels, in ascending privilege.

    The order matches the PostgreSQL `access_level` enum, so "at least this
    level" means the same thing in Python and in SQL.
    """

    VIEWER = "VIEWER"
    DATA_EDITOR = "DATA_EDITOR"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


_ORDER: dict[str, int] = {
    AccessLevel.VIEWER: 0,
    AccessLevel.DATA_EDITOR: 1,
    AccessLevel.ADMIN: 2,
    AccessLevel.SUPER_ADMIN: 3,
}

#: Roles a user may ask for. VIEWER is the default and is never requested.
REQUESTABLE_ROLES: tuple[str, ...] = (
    AccessLevel.DATA_EDITOR,
    AccessLevel.ADMIN,
    AccessLevel.SUPER_ADMIN,
)


def rank(level: str) -> int:
    try:
        return _ORDER[AccessLevel(level)]
    except ValueError as exc:  # pragma: no cover - guarded by the database enum
        raise ValueError(f"unknown access level {level!r}") from exc


def at_least(level: str, minimum: str) -> bool:
    return rank(level) >= rank(minimum)


def requestable_roles_for(level: str) -> tuple[str, ...]:
    """Which roles this user may request: strictly higher ones only.

    A user cannot request their current role, and cannot request a lower one —
    a reduction is an administrative action a Super Admin performs, not
    something a user asks for.
    """
    current = rank(level)
    return tuple(role for role in REQUESTABLE_ROLES if rank(role) > current)


class Capability(str, Enum):
    """What someone may do. Named for the action, not for the role."""

    VIEW = "view"
    EXPORT = "export"

    MAINTAIN_STUDENT_DATA = "maintainStudentData"
    MAINTAIN_TIMETABLE = "maintainTimetable"
    MAINTAIN_TRAINER_DATA = "maintainTrainerData"
    MAINTAIN_REFERENCE_DATA = "maintainReferenceData"
    OVERRIDE_TIMETABLE_CLASH = "overrideTimetableClash"

    VIEW_ACTIVITY_RECORDS = "viewActivityRecords"
    ACCESS_ADMINISTRATION = "accessAdministration"
    MANAGE_USER_ROLES = "manageUserRoles"
    DECIDE_ACCESS_REQUESTS = "decideAccessRequests"


#: The minimum access level each capability requires.
#:
#: Two entries carry the Access Model v1.1 changes that are easy to get wrong:
#: a Data Editor maintains **both** Student Data and Timetable (the work
#: assignment that used to split them is gone), and deciding access requests is
#: SUPER_ADMIN — an Admin does not approve access requests or assign roles.
_MINIMUM_LEVEL: dict[Capability, AccessLevel] = {
    Capability.VIEW: AccessLevel.VIEWER,
    Capability.EXPORT: AccessLevel.VIEWER,
    Capability.MAINTAIN_STUDENT_DATA: AccessLevel.DATA_EDITOR,
    Capability.MAINTAIN_TIMETABLE: AccessLevel.DATA_EDITOR,
    # Reference data stays read-and-download-only for a Data Editor.
    Capability.MAINTAIN_TRAINER_DATA: AccessLevel.ADMIN,
    Capability.MAINTAIN_REFERENCE_DATA: AccessLevel.ADMIN,
    Capability.OVERRIDE_TIMETABLE_CLASH: AccessLevel.ADMIN,
    Capability.VIEW_ACTIVITY_RECORDS: AccessLevel.SUPER_ADMIN,
    Capability.ACCESS_ADMINISTRATION: AccessLevel.SUPER_ADMIN,
    Capability.MANAGE_USER_ROLES: AccessLevel.SUPER_ADMIN,
    Capability.DECIDE_ACCESS_REQUESTS: AccessLevel.SUPER_ADMIN,
}


def can(level: str, capability: Capability) -> bool:
    return at_least(level, _MINIMUM_LEVEL[capability])


def capabilities_for(level: str) -> dict[str, bool]:
    """The full capability map, as sent to the frontend so it cannot guess."""
    return {capability.value: can(level, capability) for capability in Capability}


def minimum_level_for(capability: Capability) -> str:
    return _MINIMUM_LEVEL[capability].value


ROLE_LABELS: dict[str, str] = {
    AccessLevel.VIEWER: "Viewer",
    AccessLevel.DATA_EDITOR: "Data Editor",
    AccessLevel.ADMIN: "Admin",
    AccessLevel.SUPER_ADMIN: "Super Admin",
}
