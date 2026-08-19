"""Cohort identity: intake, group, and the rolling timetable label.

    Qualification -> Intake (always) -> Group (SIT/RII only)

An intake exists for every qualification. A group gathers several intakes —
usually about four, not fixed — and only the ten approved qualifications have
them. `student_groups` holds one row per intake; a group is the set of rows
sharing a `group_code`.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.models.student import StudentGroup
from app.services.student_groups import (
    cohort_identity,
    report_intakes_missing_a_label,
    uses_numbered_groups,
)

from tests.test_reference_data_api import ADMIN, as_user, client, people, seed  # noqa: F401

LABEL = "BSB50420_52_9 Feb 2026_NA_Intake"


@pytest.fixture
def offering(session, seed):
    """One course offering, so a student group has something to belong to."""
    from app.models.course import CourseOffering

    row = CourseOffering(
        college_id=seed["college"]["id"],
        campus_id=seed["campus"]["id"],
        qualification_id=seed["qualification"]["id"],
        course_code="TSTCOHORT1",
        course_status_id=seed["status_id"],
    )
    session.add(row)
    session.commit()
    return row


def group(**overrides) -> StudentGroup:
    defaults = dict(
        group_code="N/A",
        course_offering_id=1,
        intake=dt.date(2026, 2, 2),
        rolling_intake_label=None,
    )
    return StudentGroup(**{**defaults, **overrides})


class TestGroupsGatherIntakes:
    @pytest.mark.parametrize("code", ["SIT40721", "SIT50422", "RII50520", "RII60520"])
    def test_the_approved_qualifications_use_numbered_groups(self, code):
        assert uses_numbered_groups(code)

    @pytest.mark.parametrize("code", ["BSB50420", "CHC33021", "AUR40226", "FNS40222"])
    def test_every_other_qualification_does_not(self, code):
        assert not uses_numbered_groups(code)

    def test_a_code_less_qualification_does_not(self):
        """ELICOS courses have no code and no groups."""
        assert not uses_numbered_groups(None)

    def test_membership_is_the_approved_list_not_a_prefix_match(self):
        """A future SIT qualification is not automatically group-enabled.

        Matching on the letters would silently enrol a new qualification into
        numbered groups the moment its code was added.
        """
        assert not uses_numbered_groups("SIT99999")
        assert not uses_numbered_groups("RII99999")


class TestCohortIdentity:
    def test_a_grouped_qualification_uses_its_group(self):
        """For SIT/RII the group is the cohort — it spans several intakes."""
        assert cohort_identity(group(group_code="Group 3"), "SIT40721") == "Group 3"

    def test_several_intakes_share_one_group(self):
        """The point of a group: about four intakes, one cohort."""
        intakes = [
            group(group_code="Group 3", intake=dt.date(2026, 2, 2)),
            group(group_code="Group 3", intake=dt.date(2026, 3, 2)),
            group(group_code="Group 3", intake=dt.date(2026, 4, 6)),
            group(group_code="Group 3", intake=dt.date(2026, 5, 4)),
        ]
        assert {cohort_identity(g, "SIT40721") for g in intakes} == {"Group 3"}

    def test_an_ungrouped_qualification_uses_its_intake(self):
        assert cohort_identity(group(rolling_intake_label=LABEL), "BSB50420") == LABEL

    def test_the_label_is_preferred_over_the_date(self):
        """The label leads wherever it exists — approved 13 August 2026."""
        row = group(intake=dt.date(2026, 2, 2), rolling_intake_label=LABEL)
        assert cohort_identity(row, "BSB50420") == LABEL
        assert cohort_identity(row, "BSB50420") != row.intake.isoformat()

    def test_the_date_is_the_fallback_when_no_label_exists(self):
        """69 of the 82 qualifications have no rolling timetable, so no label."""
        row = group(intake=dt.date(2026, 2, 2), rolling_intake_label=None)
        assert cohort_identity(row, "CHC33021") == "2026-02-02"

    def test_a_grouped_qualification_marked_na_falls_back_to_the_intake(self):
        assert cohort_identity(group(group_code="N/A", rolling_intake_label=LABEL), "SIT40721") == LABEL


class TestLabelIsNotDerivableFromTheDate:
    def test_the_label_carries_a_different_date_from_the_intake(self):
        """Why both columns exist.

        The label names the first teaching week (9 Feb); the intake's marked week
        began a week earlier (2 Feb). Converting one into the other lands on the
        wrong cohort, so neither can replace the other.
        """
        row = group(intake=dt.date(2026, 2, 2), rolling_intake_label=LABEL)
        assert "9 Feb 2026" in row.rolling_intake_label
        assert row.intake == dt.date(2026, 2, 2)
        assert "2 Feb 2026" not in row.rolling_intake_label


class TestStorage:
    def test_the_label_is_stored_verbatim(self, session, offering):
        row = StudentGroup(
            group_code="N/A",
            course_offering_id=offering.id,
            intake=dt.date(2026, 2, 9),
            rolling_intake_label=LABEL,
        )
        session.add(row)
        session.commit()

        stored = session.get(StudentGroup, row.id)
        assert stored.rolling_intake_label == LABEL
        assert stored.intake == dt.date(2026, 2, 9)

    def test_the_label_may_be_absent(self, session, offering):
        """A qualification with no rolling timetable still gets an intake."""
        row = StudentGroup(
            group_code="N/A",
            course_offering_id=offering.id,
            intake=dt.date(2026, 3, 2),
        )
        session.add(row)
        session.commit()
        assert session.get(StudentGroup, row.id).rolling_intake_label is None


class TestCoverageReport:
    def test_it_reports_when_the_date_column_is_still_needed(self, session, offering):
        """The evidence for "is it safe to drop the intake date yet?"."""
        session.add_all([
            StudentGroup(
                group_code="N/A", course_offering_id=offering.id,
                intake=dt.date(2026, 2, 9), rolling_intake_label=LABEL,
            ),
            StudentGroup(
                group_code="N/A", course_offering_id=offering.id,
                intake=dt.date(2026, 3, 2),
            ),
        ])
        session.commit()

        coverage = report_intakes_missing_a_label(session)
        assert coverage.total_intakes == 2
        assert coverage.with_label == 1
        assert coverage.without_label == 1
        assert not coverage.is_complete

    def test_an_empty_database_is_not_reported_as_complete(self, session, seed):
        """Nothing to check is not the same as everything checked."""
        assert not report_intakes_missing_a_label(session).is_complete

