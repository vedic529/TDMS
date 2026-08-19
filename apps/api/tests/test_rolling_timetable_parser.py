"""Rolling timetable parser.

Every fixture here is written inline rather than read from the operational
workbook: a test that depends on `Rolling TT Data - BSB.xlsx` sitting in a
Downloads folder is not a test, and the parser's job is to handle the *shape*,
not one file.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.services.rolling_timetable import (
    ASSESSMENT,
    BREAK,
    PERIOD_ASSESSMENT,
    PERIOD_BREAK,
    PERIOD_UNIT,
    RollingTimetableError,
    parse_sheet,
    validate_against_units,
)

HEADER = ["Week No.", "Start Date", "End Date", "Intake", None, None]


def week(n: int) -> tuple[dt.datetime, dt.datetime]:
    """Week n of a Monday-aligned calendar starting 19 Jan 2026."""
    start = dt.datetime(2026, 1, 19) + dt.timedelta(weeks=n - 1)
    return start, start + dt.timedelta(days=6)


def row(n: int, *cells: str | None) -> list:
    start, end = week(n)
    return [n, start, end, *cells]


class TestStructure:
    def test_columns_are_found_by_heading_not_position(self):
        """A workbook that gains a leading column must not need a new parser."""
        header = ["Notes", "Week No.", "Start Date", "End Date", "Intake"]
        start, end = week(1)
        sheet = parse_sheet("TESTQUAL", [header, [None, 1, start, end, "TESTUNIT001"]])

        assert len(sheet.weeks) == 1
        assert sheet.weeks[0].start_date == start.date()
        assert sheet.unit_codes == {"TESTUNIT001"}
        assert len(sheet.intakes) == 1

    def test_any_other_valued_column_is_read_as_an_intake(self):
        """Deliberate: intakes are found by having values, not by a fixed range.

        The operational workbook grows a column each time an intake is added, so
        the parser cannot depend on knowing where the intakes stop. The cost is
        that a stray annotation column would be reported as an intake — which is
        the safe direction, because it surfaces rather than silently drops data.
        """
        header = ["Week No.", "Start Date", "End Date", "Intake", "Notes"]
        start, end = week(1)
        sheet = parse_sheet("TESTQUAL", [header, [1, start, end, "TESTUNIT001", "check this"]])

        assert [i.source_column for i in sheet.intakes] == ["D", "E"]
        assert "CHECK THIS" in sheet.unit_codes
        # ...and validation against the database is what catches it.
        assert validate_against_units(sheet, ["TESTUNIT001"]).unknown_unit_codes == ["CHECK THIS"]

    def test_a_sheet_without_the_required_headings_is_refused(self):
        with pytest.raises(RollingTimetableError, match="Week No."):
            parse_sheet("TESTQUAL", [["A", "B", "C"], [1, 2, 3]])

    def test_an_empty_sheet_is_refused(self):
        with pytest.raises(RollingTimetableError, match="empty"):
            parse_sheet("TESTQUAL", [])

    def test_a_sheet_with_no_dated_rows_is_refused(self):
        with pytest.raises(RollingTimetableError, match="no dated week rows"):
            parse_sheet("TESTQUAL", [HEADER, [None, None, None, None]])

    def test_a_reversed_week_is_refused(self):
        start, end = week(1)
        with pytest.raises(RollingTimetableError, match="before Start Date"):
            parse_sheet("TESTQUAL", [HEADER, [1, end, start, "TESTUNIT001"]])

    def test_a_non_numeric_week_is_refused(self):
        start, end = week(1)
        with pytest.raises(RollingTimetableError, match="not a whole number"):
            parse_sheet("TESTQUAL", [HEADER, ["one", start, end, "TESTUNIT001"]])

    def test_blank_rows_are_skipped(self):
        sheet = parse_sheet(
            "TESTQUAL",
            [HEADER, row(1, "TESTUNIT001"), [None, None, None, None], row(2, "TESTUNIT001")],
        )
        assert len(sheet.weeks) == 2


class TestRollingEntry:
    """The point of a rolling timetable: cohorts do not all start at unit one."""

    def test_an_intake_enters_mid_cycle(self):
        sheet = parse_sheet(
            "TESTQUAL",
            [
                HEADER,
                row(1, "UNITA", None),
                row(2, "UNITA", "Intake"),
                row(3, "UNITB", "UNITB"),
                row(4, "UNITC", "UNITC"),
            ],
        )
        base, joiner = sheet.intakes

        # The base stream starts at the beginning of the cycle...
        assert base.marker_week is None
        assert base.first_delivered_unit == "UNITA"

        # ...the joiner enters at week 2 and begins with UNITB, not UNITA.
        assert joiner.intake_date == dt.date(2026, 1, 26)
        assert joiner.first_delivered_unit == "UNITB"

    def test_the_intake_date_is_the_marked_week_and_delivery_starts_the_next(self):
        """The marker is the entry point, not the first teaching week."""
        sheet = parse_sheet(
            "TESTQUAL", [HEADER, row(1, "UNITA", "Intake"), row(2, "UNITB", "UNITB")]
        )
        joiner = sheet.intakes[1]
        assert joiner.intake_date == dt.date(2026, 1, 19)
        assert joiner.unit_deliveries[0].start_date == dt.date(2026, 1, 26)

    def test_the_literal_word_intake_is_never_treated_as_a_unit(self):
        sheet = parse_sheet("TESTQUAL", [HEADER, row(1, "Intake"), row(2, "UNITA")])
        assert sheet.unit_codes == {"UNITA"}
        assert all(p.value != "INTAKE" for i in sheet.intakes for p in i.periods)

    def test_a_stream_already_running_has_no_marker(self):
        sheet = parse_sheet("TESTQUAL", [HEADER, row(1, "UNITA")])
        assert sheet.intakes[0].marker_week is None
        assert sheet.intakes[0].intake_date is None


class TestBreaksAndAssessment:
    def test_a_unit_interrupted_by_a_break_is_one_delivery(self):
        """BSBPEF502 → BREAK → BSBPEF502 is a single interrupted delivery.

        Two deliveries would double-count the unit against the qualification;
        one delivery with the break removed would lose four weeks of calendar.
        """
        sheet = parse_sheet(
            "TESTQUAL",
            [
                HEADER,
                row(1, "UNITA"),
                row(2, "UNITA"),
                row(3, BREAK),
                row(4, BREAK),
                row(5, BREAK),
                row(6, BREAK),
                row(7, "UNITA"),
            ],
        )
        deliveries = sheet.intakes[0].unit_deliveries
        assert len(deliveries) == 1

        delivery = deliveries[0]
        assert delivery.unit_code == "UNITA"
        assert delivery.active_weeks == 3
        assert delivery.calendar_weeks == 7
        assert delivery.is_interrupted
        assert [p.active_weeks for p in delivery.interruptions] == [4]

    def test_the_break_survives_as_its_own_period(self):
        """The break is preserved, not absorbed into the unit."""
        sheet = parse_sheet(
            "TESTQUAL", [HEADER, row(1, "UNITA"), row(2, BREAK), row(3, "UNITA")]
        )
        breaks = [p for p in sheet.intakes[0].periods if p.period_type == PERIOD_BREAK]
        assert len(breaks) == 1
        assert breaks[0].start_date == dt.date(2026, 1, 26)
        assert breaks[0].active_weeks == 1

    def test_the_same_unit_after_a_different_unit_is_a_second_delivery(self):
        """The cycle coming round again is genuinely a new delivery."""
        sheet = parse_sheet(
            "TESTQUAL", [HEADER, row(1, "UNITA"), row(2, "UNITB"), row(3, "UNITA")]
        )
        deliveries = sheet.intakes[0].unit_deliveries
        assert [d.unit_code for d in deliveries] == ["UNITA", "UNITB", "UNITA"]
        assert all(not d.is_interrupted for d in deliveries)

    def test_break_and_assessment_are_never_units(self):
        sheet = parse_sheet(
            "TESTQUAL", [HEADER, row(1, "UNITA"), row(2, BREAK), row(3, ASSESSMENT)]
        )
        assert sheet.unit_codes == {"UNITA"}
        types = [p.period_type for p in sheet.intakes[0].periods]
        assert types == [PERIOD_UNIT, PERIOD_BREAK, PERIOD_ASSESSMENT]

    def test_active_weeks_and_calendar_span_are_distinguished(self):
        sheet = parse_sheet(
            "TESTQUAL",
            [HEADER, row(1, "UNITA"), row(2, BREAK), row(3, BREAK), row(4, "UNITA")],
        )
        intake = sheet.intakes[0]
        assert intake.teaching_weeks == 2
        assert intake.break_weeks == 2
        assert intake.unit_deliveries[0].active_weeks == 2
        assert intake.unit_deliveries[0].calendar_weeks == 4


class TestValidationAgainstApprovedUnits:
    """The database decides what a unit is — never the spreadsheet."""

    def test_a_code_not_in_the_qualification_is_reported(self):
        sheet = parse_sheet("TESTQUAL", [HEADER, row(1, "UNITA"), row(2, "NOTAUNIT")])
        result = validate_against_units(sheet, ["UNITA"])
        assert result.unknown_unit_codes == ["NOTAUNIT"]
        assert not result.is_consistent

    def test_an_approved_unit_missing_from_the_sheet_is_reported(self):
        sheet = parse_sheet("TESTQUAL", [HEADER, row(1, "UNITA")])
        result = validate_against_units(sheet, ["UNITA", "UNITB"])
        assert result.units_missing_from_sheet == ["UNITB"]
        assert not result.is_consistent

    def test_a_matching_sheet_is_consistent(self):
        sheet = parse_sheet("TESTQUAL", [HEADER, row(1, "UNITA"), row(2, "UNITB")])
        result = validate_against_units(sheet, ["UNITA", "UNITB"])
        assert result.is_consistent
        assert result.unknown_unit_codes == []

    def test_break_and_assessment_never_count_as_unknown_units(self):
        sheet = parse_sheet(
            "TESTQUAL", [HEADER, row(1, "UNITA"), row(2, BREAK), row(3, ASSESSMENT)]
        )
        assert validate_against_units(sheet, ["UNITA"]).is_consistent

    def test_unit_codes_are_matched_case_insensitively(self):
        sheet = parse_sheet("TESTQUAL", [HEADER, row(1, "unita")])
        assert validate_against_units(sheet, ["UNITA"]).is_consistent


class TestTraceability:
    def test_the_source_column_is_recorded_but_is_not_the_identity(self):
        """Column letters trace back to the workbook; the intake date identifies."""
        sheet = parse_sheet("TESTQUAL", [HEADER, row(1, "UNITA", "Intake"), row(2, "UNITB", "UNITB")])
        joiner = sheet.intakes[1]
        assert joiner.source_column == "E"
        # The business identity is the date, which is what a later import keys on.
        assert joiner.intake_date == dt.date(2026, 1, 19)

    def test_column_letters_pass_z(self):
        header = HEADER + [None] * 25
        cells = [None] * 25 + ["UNITA"]
        sheet = parse_sheet("TESTQUAL", [header, row(1, *cells)])
        assert sheet.intakes[0].source_column == "AC"
