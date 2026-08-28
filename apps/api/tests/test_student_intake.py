"""Rule 2.5 intake assignment — the pure-algorithm checks (3.1 A1–A8, A10, A12).

These need no database: `build_windows` and `assign_intake` are pure. The
service-level cases (A9 Credit Transfer, A11 shared group row) are proven in
`test_students_import.py`, which exercises the real tables.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.core.intake_assignment import (
    CONFLICT,
    MATCHED,
    TBD,
    assign_intake,
    build_windows,
)

QUAL = "BSB50420"
DURATION = 10


@dataclass
class W:
    """A stand-in rolling week, carrying only what matching reads."""

    intake_label: str
    intake_group: str
    intake_start_date: dt.date
    week_start_date: dt.date
    schedule_type: str
    unit_code: str | None
    unit_slot: int = 1
    qualification_code: str = QUAL
    duration_weeks: int = DURATION

    @property
    def week_end_date(self) -> dt.date:
        return self.week_start_date + dt.timedelta(days=6)


def mon(y: int, m: int, d: int) -> dt.date:
    day = dt.date(y, m, d)
    assert day.weekday() == 0, f"{day} is not a Monday"
    return day


def intake(label: str, group: str, start: dt.date, weeks: list[tuple[dt.date, str, str | None]]) -> list[W]:
    """weeks = list of (monday, schedule_type, unit_code)."""
    return [
        W(intake_label=label, intake_group=group, intake_start_date=start, week_start_date=monday, schedule_type=stype, unit_code=unit)
        for monday, stype, unit in weeks
    ]


# --- A shared, staggered calendar covering the direct/before/break cases -----
# Intake A: first unit U1 over 3 weeks (02-Feb .. 16-Feb), then U2.
INTAKE_A = intake(
    "BSB50420_10_02 Feb 2026_NA_Intake", "NA", mon(2026, 2, 2),
    [(mon(2026, 2, 2), "UNIT", "U1"), (mon(2026, 2, 9), "UNIT", "U1"),
     (mon(2026, 2, 16), "UNIT", "U1"), (mon(2026, 2, 23), "UNIT", "U2")],
)
# Intake B: first unit U1 begins the week A's first unit ends + 1 (23-Feb).
INTAKE_B = intake(
    "BSB50420_10_23 Feb 2026_NA_Intake", "NA", mon(2026, 2, 23),
    [(mon(2026, 2, 23), "UNIT", "U1"), (mon(2026, 3, 2), "UNIT", "U1"),
     (mon(2026, 3, 9), "UNIT", "U1"), (mon(2026, 3, 16), "UNIT", "U2")],
)
# Intake C: an INTERIOR break inside the first unit — U1 resumes after it.
INTAKE_C = intake(
    "BSB50420_10_06 Apr 2026_NA_Intake", "NA", mon(2026, 4, 6),
    [(mon(2026, 4, 6), "UNIT", "U1"), (mon(2026, 4, 13), "UNIT", "U1"),
     (mon(2026, 4, 20), "BREAK", None), (mon(2026, 4, 27), "UNIT", "U1"),
     (mon(2026, 5, 4), "UNIT", "U2")],
)
# Intake D: a TRAILING break — U1 does NOT resume (U2 follows the break).
INTAKE_D = intake(
    "BSB50420_10_01 Jun 2026_NA_Intake", "NA", mon(2026, 6, 1),
    [(mon(2026, 6, 1), "UNIT", "U1"), (mon(2026, 6, 8), "UNIT", "U1"),
     (mon(2026, 6, 15), "BREAK", None), (mon(2026, 6, 22), "UNIT", "U2")],
)
# Intake E: begins immediately after D's break.
INTAKE_E = intake(
    "BSB50420_10_15 Jun 2026_NA_Intake", "NA", mon(2026, 6, 15),
    [(mon(2026, 6, 15), "UNIT", "U1"), (mon(2026, 6, 22), "UNIT", "U1"),
     (mon(2026, 6, 29), "UNIT", "U1")],
)

CALENDAR = INTAKE_A + INTAKE_B + INTAKE_C + INTAKE_D + INTAKE_E


def windows_for(rows, qual=QUAL, duration=DURATION):
    return build_windows(rows).get((qual, duration), [])


def label(result):
    return result.intake_label


def test_a1_middle_of_first_unit():
    result = assign_intake(windows_for(CALENDAR), mon(2026, 2, 9))  # week 2 of 3
    assert result.status == MATCHED
    assert label(result) == "BSB50420_10_02 Feb 2026_NA_Intake"


def test_a2_last_week_still_counts():
    result = assign_intake(windows_for(CALENDAR), mon(2026, 2, 16))  # final week of U1
    assert result.status == MATCHED
    assert label(result) == "BSB50420_10_02 Feb 2026_NA_Intake"


def test_a3_too_late_does_not_join_that_intake():
    result = assign_intake(windows_for(CALENDAR), mon(2026, 2, 23))  # week after A's U1
    assert result.status == MATCHED
    assert label(result) != "BSB50420_10_02 Feb 2026_NA_Intake"
    assert label(result) == "BSB50420_10_23 Feb 2026_NA_Intake"  # joins the next intake


def test_a4_break_unit_resumes_joins_last_intake_before_break():
    result = assign_intake(windows_for(CALENDAR), mon(2026, 4, 20))  # interior break of C
    assert result.status == MATCHED
    assert label(result) == "BSB50420_10_06 Apr 2026_NA_Intake"


def test_a5_break_unit_does_not_resume_joins_next_intake():
    result = assign_intake(windows_for(CALENDAR), mon(2026, 6, 15))  # D's trailing break
    assert result.status == MATCHED
    assert label(result) == "BSB50420_10_15 Jun 2026_NA_Intake"  # the intake after the break


def test_a6_before_the_calendar_assigns_first_intake():
    result = assign_intake(windows_for(CALENDAR), mon(2026, 1, 5))  # before everything
    assert result.status == MATCHED
    assert label(result) == "BSB50420_10_02 Feb 2026_NA_Intake"  # earliest intake


def test_a7_no_rolling_timetable_is_tbd():
    assert assign_intake([], mon(2026, 2, 9)).status == TBD
    assert assign_intake(None, mon(2026, 2, 9)).status == TBD


def test_a8_group_comes_from_the_intake_label():
    result = assign_intake(windows_for(CALENDAR), mon(2026, 2, 9))
    assert result.intake_group == "NA"  # every BSB intake's group portion is NA


def test_a10_two_intakes_matching_refuses_and_names_both():
    clash = intake(
        "BSB50420_10_03 Aug 2026_NA_Intake", "NA", mon(2026, 8, 3),
        [(mon(2026, 8, 3), "UNIT", "U1"), (mon(2026, 8, 10), "UNIT", "U2")],
    ) + intake(
        "BSB50420_10_03 Aug 2026_G2_Intake", "NA", mon(2026, 8, 3),
        [(mon(2026, 8, 3), "UNIT", "U9"), (mon(2026, 8, 10), "UNIT", "U8")],
    )
    result = assign_intake(windows_for(clash), mon(2026, 8, 3))
    assert result.status == CONFLICT
    assert result.conflict_labels == [
        "BSB50420_10_03 Aug 2026_G2_Intake",
        "BSB50420_10_03 Aug 2026_NA_Intake",
    ]


def test_a12_wrong_duration_is_tbd_not_matched_to_another_duration():
    built = build_windows(CALENDAR)
    assert (QUAL, DURATION) in built
    # A student whose duration has no rolling timetable gets no windows → TBD.
    assert assign_intake(built.get((QUAL, 20), []), mon(2026, 2, 9)).status == TBD


def test_window_boundaries_are_correct():
    windows = {w.intake_label: w for w in windows_for(CALENDAR)}
    a = windows["BSB50420_10_02 Feb 2026_NA_Intake"]
    assert a.first_week == mon(2026, 2, 2)
    assert a.last_week == mon(2026, 2, 16)  # 3-week first unit
    c = windows["BSB50420_10_06 Apr 2026_NA_Intake"]
    assert c.first_week == mon(2026, 4, 6)
    assert c.last_week == mon(2026, 4, 27)  # break included, U1 resumes to 27 Apr
    d = windows["BSB50420_10_01 Jun 2026_NA_Intake"]
    assert d.last_week == mon(2026, 6, 8)  # trailing break excluded
