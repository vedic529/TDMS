"""Approved student business rules — Intake and Group (11 August 2026).

These are pure business-rule tests: no database, because the rules do not depend
on one. What they protect is the API refusing values a dropdown would never
offer — a hand-crafted request with `"Group 16"` must fail here, not in a form.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.core.student_rules import (
    GROUP_ENABLED_QUALIFICATIONS,
    MAX_NUMBERED_GROUP,
    MONTH_LABELS,
    NO_GROUP,
    GroupValidationError,
    derive_intake,
    format_intake,
    group_after_qualification_change,
    group_number,
    group_options_for,
    intake_for_display,
    numbered_groups,
    parse_intake,
    uses_numbered_groups,
    validate_group,
)

#: The ten approved group-enabled qualifications, written out rather than
#: imported, so an accidental edit to the source list fails a test.
APPROVED_GROUP_QUALIFICATIONS = [
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
]

NON_GROUP_QUALIFICATIONS = ["BSB50420", "BSB80120", "CHC50125", "AUR30620", "FBP30321"]


# ===========================================================================
# The approved list
# ===========================================================================


def test_exactly_ten_qualifications_use_groups():
    assert len(GROUP_ENABLED_QUALIFICATIONS) == 10


def test_the_group_enabled_list_is_exactly_as_approved():
    assert set(GROUP_ENABLED_QUALIFICATIONS) == set(APPROVED_GROUP_QUALIFICATIONS)


@pytest.mark.parametrize("code", APPROVED_GROUP_QUALIFICATIONS)
def test_each_approved_qualification_uses_numbered_groups(code):
    assert uses_numbered_groups(code) is True


@pytest.mark.parametrize("code", NON_GROUP_QUALIFICATIONS)
def test_other_qualifications_do_not_use_numbered_groups(code):
    assert uses_numbered_groups(code) is False


def test_qualification_matching_ignores_case_and_spacing():
    assert uses_numbered_groups("  sit40721  ") is True


def test_an_unknown_qualification_does_not_use_groups():
    assert uses_numbered_groups("ZZZ99999") is False
    assert uses_numbered_groups(None) is False
    assert uses_numbered_groups("") is False


# ===========================================================================
# The configurable range
# ===========================================================================


def test_the_current_maximum_is_fifteen():
    assert MAX_NUMBERED_GROUP == 15


def test_the_group_list_is_generated_from_the_maximum():
    groups = numbered_groups()
    assert len(groups) == MAX_NUMBERED_GROUP
    assert groups[0] == "Group 1"
    assert groups[-1] == f"Group {MAX_NUMBERED_GROUP}"


def test_raising_the_maximum_needs_no_other_change():
    """Proves the range is derived, not a literal list copied around."""
    assert numbered_groups(20)[-1] == "Group 20"
    assert len(numbered_groups(20)) == 20


@pytest.mark.parametrize("code", APPROVED_GROUP_QUALIFICATIONS)
def test_group_options_for_an_enabled_qualification(code):
    assert group_options_for(code) == numbered_groups()


@pytest.mark.parametrize("code", NON_GROUP_QUALIFICATIONS)
def test_group_options_for_other_qualifications_is_only_na(code):
    assert group_options_for(code) == (NO_GROUP,)


# ===========================================================================
# Validation
# ===========================================================================


@pytest.mark.parametrize("code", APPROVED_GROUP_QUALIFICATIONS)
def test_group_one_is_valid_for_every_enabled_qualification(code):
    assert validate_group(code, "Group 1") == "Group 1"


@pytest.mark.parametrize("code", APPROVED_GROUP_QUALIFICATIONS)
def test_group_fifteen_is_valid_for_every_enabled_qualification(code):
    assert validate_group(code, "Group 15") == "Group 15"


@pytest.mark.parametrize("number", range(1, 16))
def test_every_group_in_the_range_is_accepted(number):
    assert validate_group("SIT40721", f"Group {number}") == f"Group {number}"


def test_group_zero_is_rejected():
    with pytest.raises(GroupValidationError):
        validate_group("SIT40721", "Group 0")


def test_group_sixteen_is_rejected():
    with pytest.raises(GroupValidationError, match="not a valid group"):
        validate_group("SIT40721", "Group 16")


@pytest.mark.parametrize("value", ["G1", "1", "group 1", "Group 01", "Group one", "A-Team", "Morning Group"])
def test_arbitrary_group_text_is_rejected(value):
    with pytest.raises(GroupValidationError):
        validate_group("SIT40721", value)


def test_a_blank_group_is_rejected_for_an_enabled_qualification():
    with pytest.raises(GroupValidationError, match="requires a group"):
        validate_group("SIT40721", "")


def test_na_is_rejected_for_an_enabled_qualification():
    with pytest.raises(GroupValidationError, match="requires a group"):
        validate_group("SIT40721", NO_GROUP)


@pytest.mark.parametrize("code", NON_GROUP_QUALIFICATIONS)
def test_na_is_the_accepted_value_for_other_qualifications(code):
    assert validate_group(code, NO_GROUP) == NO_GROUP
    assert validate_group(code, "") == NO_GROUP
    assert validate_group(code, None) == NO_GROUP


def test_a_numbered_group_is_rejected_for_a_non_group_qualification():
    with pytest.raises(GroupValidationError, match="does not use numbered groups"):
        validate_group("BSB50420", "Group 3")


def test_group_number_extraction():
    assert group_number("Group 7") == 7
    assert group_number("Group 15") == 15
    assert group_number("G7") is None
    assert group_number(None) is None


# ===========================================================================
# Switching qualification
# ===========================================================================


def test_switching_to_a_non_group_qualification_clears_the_group():
    """SIT40721 / Group 5 -> BSB50420 must become N/A, not keep Group 5."""
    assert group_after_qualification_change("BSB50420", "Group 5") == NO_GROUP


def test_switching_to_a_group_qualification_requires_a_choice():
    """BSB50420 / N/A -> RII50520 must clear N/A and ask for a group."""
    assert group_after_qualification_change("RII50520", NO_GROUP) is None
    assert group_after_qualification_change("RII50520", "") is None


def test_a_valid_group_carries_between_two_group_qualifications():
    assert group_after_qualification_change("SIT50422", "Group 5") == "Group 5"


def test_an_out_of_range_group_does_not_carry_over():
    assert group_after_qualification_change("SIT50422", "Group 99") is None


def test_no_stale_value_survives_a_round_trip():
    """SIT40721 Group 5 -> BSB50420 -> RII50520 must not resurrect Group 5."""
    after_non_group = group_after_qualification_change("BSB50420", "Group 5")
    assert after_non_group == NO_GROUP
    assert group_after_qualification_change("RII50520", after_non_group) is None


# ===========================================================================
# Intake
# ===========================================================================


def test_intake_is_the_first_day_of_the_proposed_start_month():
    assert derive_intake(dt.date(2026, 8, 18)) == dt.date(2026, 8, 1)
    assert derive_intake(dt.date(2027, 1, 3)) == dt.date(2027, 1, 1)


def test_a_start_date_already_on_the_first_is_unchanged():
    assert derive_intake(dt.date(2026, 8, 1)) == dt.date(2026, 8, 1)


def test_intake_of_no_date_is_none():
    assert derive_intake(None) is None


@pytest.mark.parametrize("month,label", list(enumerate(MONTH_LABELS, start=1)))
def test_every_month_formats_with_its_english_label(month, label):
    assert format_intake(dt.date(2026, month, 1)) == f"01-{label}-2026"


@pytest.mark.parametrize(
    "start,expected",
    [
        (dt.date(2026, 8, 18), "01-Aug-2026"),
        (dt.date(2027, 1, 3), "01-Jan-2027"),
        (dt.date(2025, 12, 31), "01-Dec-2025"),
        (dt.date(2028, 2, 29), "01-Feb-2028"),
        (dt.date(2026, 6, 1), "01-Jun-2026"),
    ],
)
def test_intake_display_across_months_and_years(start, expected):
    assert intake_for_display(start) == expected


def test_intake_display_uses_the_approved_format_not_an_alternative():
    value = intake_for_display(dt.date(2026, 8, 18))
    assert value == "01-Aug-2026"
    for rejected in ("AUG-2026", "08/01/2026", "01/08/2026", "2026-08-01"):
        assert value != rejected


def test_intake_display_is_zero_padded():
    assert format_intake(dt.date(2026, 8, 1)).startswith("01-")


def test_intake_parses_back_from_the_display_format():
    assert parse_intake("01-Aug-2026") == dt.date(2026, 8, 1)
    assert parse_intake("1-Aug-2026") == dt.date(2026, 8, 1)


def test_intake_also_parses_an_iso_date():
    """Imported source files are not consistent; a valid ISO date is accepted."""
    assert parse_intake("2026-08-01") == dt.date(2026, 8, 1)


def test_intake_rejects_unparseable_text():
    for value in ("AUG-2026", "01/08/2026", "not a date", "01-Zzz-2026", ""):
        assert parse_intake(value) is None


def test_intake_round_trips():
    for start in (dt.date(2026, 8, 18), dt.date(2027, 1, 3), dt.date(2030, 11, 9)):
        assert parse_intake(intake_for_display(start)) == derive_intake(start)
