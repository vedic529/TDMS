"""Assign a student to a rolling-timetable intake and group (rule 2.5).

Pure logic: it reads rolling-timetable week rows and a proposed start date, and
returns which intake a student belongs to. It never touches the database — the
service loads the rolling weeks in **one** query and hands them here, so matching
a thousand students never issues a thousand queries (rule 2.9, check E1).

The rule, restated from the specification:

* Each intake has a **first unit** — the unit delivered in its earliest stored
  week. That unit's delivery runs over a **window** of calendar weeks; a Break
  interrupts the delivery without ending it, so interior break weeks stay inside
  the window. A different unit ends it.
* A student belongs to an intake when their start week falls inside that intake's
  first-unit window: ``first_week <= student_week <= last_week``. Because a week
  is whole, a student starting in the final week still has a week of the first
  unit, so the last week counts.
* Two intakes whose first units run in the same week is a data fault, not a
  choice — it is refused and both are named.
* A start date before the whole rolling calendar assigns the first intake.
* A start date in a Break resolves the same way the window does: an interior
  break is inside the window (the first unit resumes, so the student joins that
  intake); a trailing break is past the window, so the student joins the next
  intake to begin — the one starting immediately after the break.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Iterable, Protocol

# Assignment outcomes.
MATCHED = "MATCHED"
TBD = "TBD"
CONFLICT = "CONFLICT"

TYPE_UNIT = "UNIT"


class RollingWeekLike(Protocol):
    """The rolling-timetable fields intake matching needs."""

    qualification_code: str
    duration_weeks: int
    intake_label: str
    intake_group: str
    intake_start_date: dt.date
    week_start_date: dt.date
    week_end_date: dt.date
    schedule_type: str
    unit_code: str | None
    unit_slot: int


@dataclass(frozen=True)
class IntakeWindow:
    """One intake's first-unit calendar window, in Monday week-start dates."""

    intake_label: str
    intake_group: str
    intake_start_date: dt.date
    first_unit_code: str
    first_week: dt.date
    last_week: dt.date


@dataclass
class IntakeAssignment:
    """The result of matching one student."""

    status: str  # MATCHED | TBD | CONFLICT
    intake_label: str | None = None
    intake_group: str | None = None
    intake_start_date: dt.date | None = None
    conflict_labels: list[str] = field(default_factory=list)
    note: str | None = None


def monday_of(day: dt.date) -> dt.date:
    """The Monday of ``day``'s week. A rolling week always starts on a Monday."""
    return day - dt.timedelta(days=day.weekday())


def _pair(week: RollingWeekLike) -> tuple[str, int]:
    return week.qualification_code.upper(), week.duration_weeks


def build_windows(weeks: Iterable[RollingWeekLike]) -> dict[tuple[str, int], list[IntakeWindow]]:
    """Group rolling weeks into first-unit windows, keyed by (qualification, duration).

    One pass in memory over every week already fetched. No query here.
    """
    by_intake: dict[tuple[str, int, str], list[RollingWeekLike]] = {}
    meta: dict[tuple[str, int, str], tuple[str, dt.date]] = {}
    for week in weeks:
        key = (*_pair(week), week.intake_label)
        by_intake.setdefault(key, []).append(week)
        # intake_group and intake_start_date are constant across an intake.
        meta.setdefault(key, (week.intake_group, week.intake_start_date))

    windows: dict[tuple[str, int], list[IntakeWindow]] = {}
    for (qual, duration, label), intake_weeks in by_intake.items():
        window = _first_unit_window(label, meta[(qual, duration, label)], intake_weeks)
        if window is not None:
            windows.setdefault((qual, duration), []).append(window)
    return windows


def _first_unit_window(
    label: str,
    meta: tuple[str, dt.date],
    weeks: list[RollingWeekLike],
) -> IntakeWindow | None:
    """The calendar window over which this intake's first unit is delivered."""
    unit_weeks = sorted(
        (w for w in weeks if w.schedule_type == TYPE_UNIT and w.unit_code),
        key=lambda w: (w.week_start_date, w.unit_slot),
    )
    if not unit_weeks:
        return None

    first = unit_weeks[0]
    first_unit_code = first.unit_code or ""
    first_week = first.week_start_date
    last_week = first_week
    # Extend across every following week still delivering the same first unit.
    # A Break is simply not a UNIT row, so it never appears here; the same unit
    # resuming after it keeps the window open. A different unit stops it.
    for week in unit_weeks[1:]:
        if week.unit_code != first_unit_code:
            break
        last_week = week.week_start_date

    intake_group, intake_start_date = meta
    return IntakeWindow(
        intake_label=label,
        intake_group=intake_group,
        intake_start_date=intake_start_date,
        first_unit_code=first_unit_code,
        first_week=first_week,
        last_week=last_week,
    )


def assign_intake(
    windows: list[IntakeWindow] | None,
    proposed_start_date: dt.date,
) -> IntakeAssignment:
    """Match one student to an intake within a single (qualification, duration).

    ``windows`` is the list for the student's (qualification, duration) — pass
    ``None`` or an empty list when no rolling timetable exists for it, which
    yields TBD rather than a wrong match.
    """
    if not windows:
        return IntakeAssignment(status=TBD, note="No rolling timetable for this qualification and duration.")

    student_week = monday_of(proposed_start_date)

    direct = [w for w in windows if w.first_week <= student_week <= w.last_week]
    if len(direct) == 1:
        return _matched(direct[0])
    if len(direct) >= 2:
        return IntakeAssignment(
            status=CONFLICT,
            conflict_labels=sorted(w.intake_label for w in direct),
            note="Two intakes' first units run in this week — the rolling timetable is inconsistent.",
        )

    # No intake's first unit is running in the student's week.
    earliest = min(w.first_week for w in windows)
    if student_week < earliest:
        first_intake = min(windows, key=lambda w: (w.intake_start_date, w.first_week, w.intake_label))
        return _matched(first_intake, note="Start date is before the rolling calendar — assigned the first intake.")

    # A gap or a trailing break: the next intake to begin after this week.
    later = [w for w in windows if w.first_week > student_week]
    if later:
        nxt = min(later, key=lambda w: (w.first_week, w.intake_start_date, w.intake_label))
        return _matched(nxt, note="Start date falls after an intake's first unit — assigned the next intake to begin.")

    # Past every intake's first unit and none begins later. Best effort: the most
    # recent cohort. Reaching here needs a start date beyond the last intake in
    # the file, which staggered rolling data does not normally produce.
    latest = max(windows, key=lambda w: (w.intake_start_date, w.first_week, w.intake_label))
    return _matched(latest, note="Start date is beyond the last intake — assigned the most recent cohort.")


def _matched(window: IntakeWindow, note: str | None = None) -> IntakeAssignment:
    return IntakeAssignment(
        status=MATCHED,
        intake_label=window.intake_label,
        intake_group=window.intake_group,
        intake_start_date=window.intake_start_date,
        note=note,
    )
