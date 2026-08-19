"""Approved student business rules — Intake and Group.

**This module is the single source of truth.** Nothing else in the API hard-codes
a qualification code, a group name or an intake format. When the business changes
the maximum group number, exactly one constant here changes.

The frontend mirrors these rules in `apps/web/src/lib/student-rules.ts` so the
interface does not offer values the API will refuse. The API is authoritative:
`validate_group` is what actually decides, and it runs regardless of what the
browser sent.
"""

from __future__ import annotations

import datetime as dt
import re

# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

#: Qualifications that use numbered Groups. Every other qualification uses N/A.
#: Approved 11 August 2026.
GROUP_ENABLED_QUALIFICATIONS: frozenset[str] = frozenset(
    {
        "SIT40721",
        "SIT40521",
        "SIT30821",
        "SIT31021",
        "SIT50422",
        "SIT60322",
        "SIT50122",
        "SIT60122",
        "RII50520",
        "RII60520",
    }
)

#: The highest numbered Group currently approved.
#:
#: **Raising the limit is a one-line change here.** The group list, the frontend
#: options, the validators and the tests all derive from this value, so 15 -> 16
#: never means hunting through components for a literal array.
MAX_NUMBERED_GROUP: int = 15

#: The value used when a qualification does not use numbered Groups.
NO_GROUP = "N/A"

_GROUP_PREFIX = "Group "
#: Accepts exactly "Group <n>" with no leading zeros and no extra spacing, so
#: "G1", "group 1", "Group 01" and " Group 1 " are all rejected rather than
#: quietly normalised into something the user did not type.
_GROUP_PATTERN = re.compile(r"^Group (?P<number>[1-9][0-9]*)$")


def numbered_groups(maximum: int = MAX_NUMBERED_GROUP) -> tuple[str, ...]:
    """`("Group 1", …, "Group N")` — generated, never a literal list."""
    return tuple(f"{_GROUP_PREFIX}{n}" for n in range(1, maximum + 1))


def uses_numbered_groups(qualification_code: str | None) -> bool:
    """Does this qualification use numbered Groups?"""
    return (qualification_code or "").strip().upper() in GROUP_ENABLED_QUALIFICATIONS


def group_options_for(qualification_code: str | None) -> tuple[str, ...]:
    """The Group values a user may choose for this qualification.

    A group-enabled qualification offers the numbered range. Everything else
    offers only `N/A`, which the interface shows as read-only.
    """
    if uses_numbered_groups(qualification_code):
        return numbered_groups()
    return (NO_GROUP,)


def group_number(group: str | None) -> int | None:
    """The numeric part of a well-formed group name, or None."""
    match = _GROUP_PATTERN.match((group or "").strip())
    return int(match.group("number")) if match else None


class GroupValidationError(ValueError):
    """The Group value is not valid for the qualification."""


def validate_group(qualification_code: str | None, group: str | None) -> str:
    """Return the accepted Group value, or raise `GroupValidationError`.

    Enforced in the API, not only by a dropdown: a direct API call with
    `"Group 16"` or free text must be refused just as surely as a hand-edited
    form.
    """
    value = (group or "").strip()

    if not uses_numbered_groups(qualification_code):
        # Both an explicit N/A and an omitted value are accepted, because a
        # qualification without groups genuinely has nothing to choose.
        if value in {"", NO_GROUP}:
            return NO_GROUP
        raise GroupValidationError(
            f"{qualification_code} does not use numbered groups. Expected {NO_GROUP}, got {value!r}."
        )

    if not value or value == NO_GROUP:
        raise GroupValidationError(
            f"{qualification_code} requires a group. Choose one of "
            f"{numbered_groups()[0]}–{numbered_groups()[-1]}."
        )

    number = group_number(value)
    if number is None or not (1 <= number <= MAX_NUMBERED_GROUP):
        raise GroupValidationError(
            f"{value!r} is not a valid group. Choose one of "
            f"{numbered_groups()[0]}–{numbered_groups()[-1]}."
        )
    return value


def group_after_qualification_change(
    new_qualification_code: str | None, current_group: str | None
) -> str | None:
    """The Group value to hold after the qualification changes.

    Switching away from a group-enabled qualification must not leave `Group 5`
    behind on a qualification that has no groups, and switching *into* one must
    not leave `N/A` sitting in a field that now requires a real choice. Returning
    `None` means "the user must now choose".
    """
    if not uses_numbered_groups(new_qualification_code):
        return NO_GROUP

    number = group_number(current_group)
    if number is not None and 1 <= number <= MAX_NUMBERED_GROUP:
        # A still-valid numbered group carries over between two group-enabled
        # qualifications rather than being cleared for no reason.
        return current_group
    return None


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------

#: English three-letter month labels used by the approved `DD-MMM-YYYY` format.
#: Written out rather than taken from `strftime('%b')`, which is locale
#: dependent and would silently produce "août" on a French-locale machine.
MONTH_LABELS: tuple[str, ...] = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

INTAKE_DISPLAY_FORMAT = "DD-MMM-YYYY"


def derive_intake(proposed_start_date: dt.date | None) -> dt.date | None:
    """Intake = the first day of the proposed start month.

    `18-Aug-2026` -> `01-Aug-2026`; `03-Jan-2027` -> `01-Jan-2027`.
    """
    if proposed_start_date is None:
        return None
    return proposed_start_date.replace(day=1)


def format_intake(value: dt.date | None) -> str:
    """Render an intake as the approved `DD-MMM-YYYY`, e.g. `01-Aug-2026`."""
    if value is None:
        return ""
    return f"{value.day:02d}-{MONTH_LABELS[value.month - 1]}-{value.year}"


def parse_intake(value: str | None) -> dt.date | None:
    """Read `DD-MMM-YYYY`, or an ISO date, back into a date.

    Both are accepted because imported source files are not consistent, and
    rejecting a legitimate `2026-08-01` would help nobody.
    """
    text = (value or "").strip()
    if not text:
        return None

    match = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$", text)
    if match:
        day, month_label, year = match.groups()
        labels = [m.lower() for m in MONTH_LABELS]
        if month_label.lower() not in labels:
            return None
        return dt.date(int(year), labels.index(month_label.lower()) + 1, int(day))

    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def intake_for_display(proposed_start_date: dt.date | None) -> str:
    """Convenience: proposed start date straight to the displayed intake."""
    return format_intake(derive_intake(proposed_start_date))
