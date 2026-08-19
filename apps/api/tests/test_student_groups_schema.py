"""`student_groups` after the Step 5B correction (migration `0e8b41dd1b13`).

Two rules, both enforced by the database rather than by application convention:

* a group name is unique **within** a course offering and intake, not globally;
* `intake` is a real `date` holding the first day of the month.

The tests build genuine reference data through the ORM, so they exercise the
actual constraints rather than a hand-written INSERT that might not match the
models.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.college import Campus, College, CollegeCampus
from app.models.course import CourseOffering, CourseStatus
from app.models.qualification import Qualification
from app.models.student import StudentGroup

pytestmark = pytest.mark.database


@pytest.fixture()
def offerings(session):
    """Two course offerings at the same college and campus, one per qualification."""
    session.execute(
        text(
            "TRUNCATE TABLE student_groups, course_offerings, course_statuses, "
            "qualifications, college_campuses, campuses, colleges RESTART IDENTITY CASCADE"
        )
    )
    session.commit()

    college = College(college_short_name="TST", college_full_name="Test College")
    campus = Campus(campus_code="TSTC", campus_name="Test", campus_location="Test", state="VIC")
    session.add_all([college, campus])
    session.flush()
    session.add(CollegeCampus(college_id=college.id, campus_id=campus.id))

    status = CourseStatus(code="ACTIVE", label="Active")
    sit = Qualification(qualification_code="SIT40721", qualification_title="Cert IV Kitchen Mgmt")
    rii = Qualification(qualification_code="RII50520", qualification_title="Dip Civil Construction")
    session.add_all([status, sit, rii])
    session.flush()

    made = []
    # Duration is a child table (DBQ-03), not a column on the offering.
    for index, qualification in enumerate((sit, rii)):
        offering = CourseOffering(
            college_id=college.id,
            campus_id=campus.id,
            qualification_id=qualification.id,
            course_code=f"TST-{index + 1:03d}",
            course_status_id=status.id,
        )
        session.add(offering)
        made.append(offering)
    session.flush()
    session.commit()
    return made


def add_group(session, offering, intake: dt.date, group_code: str = "Group 1") -> StudentGroup:
    group = StudentGroup(
        group_code=group_code, course_offering_id=offering.id, intake=intake
    )
    session.add(group)
    session.flush()
    return group


# ---------------------------------------------------------------------------
# Column type
# ---------------------------------------------------------------------------


def test_intake_is_a_date_column(session):
    assert (
        session.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'student_groups' AND column_name = 'intake'"
            )
        ).scalar_one()
        == "date"
    )


def test_group_code_is_not_globally_unique(session):
    """The old global UNIQUE is gone."""
    names = session.execute(
        text(
            "SELECT con.conname FROM pg_constraint con "
            "JOIN pg_class rel ON rel.oid = con.conrelid "
            "WHERE rel.relname = 'student_groups' AND con.contype = 'u'"
        )
    ).scalars().all()
    assert "uq_student_groups_group_code" not in names
    assert "uq_student_groups_offering_intake_group_code" in names


def test_the_unique_constraint_covers_offering_intake_and_code(session):
    definition = session.execute(
        text(
            "SELECT pg_get_constraintdef(con.oid) FROM pg_constraint con "
            "JOIN pg_class rel ON rel.oid = con.conrelid "
            "WHERE rel.relname = 'student_groups' "
            "AND con.conname = 'uq_student_groups_offering_intake_group_code'"
        )
    ).scalar_one()
    assert definition == "UNIQUE (course_offering_id, intake, group_code)"


# ---------------------------------------------------------------------------
# The approved coexistence rule
# ---------------------------------------------------------------------------


def test_the_same_group_name_coexists_across_intakes_and_offerings(session, offerings):
    """The exact scenario the correction was approved for."""
    sit, rii = offerings

    add_group(session, sit, dt.date(2026, 8, 1))   # SIT40721 / Aug 2026 / Group 1
    add_group(session, sit, dt.date(2027, 1, 1))   # SIT40721 / Jan 2027 / Group 1
    add_group(session, rii, dt.date(2026, 8, 1))   # RII50520 / Aug 2026 / Group 1
    session.commit()

    assert session.execute(
        text("SELECT count(*) FROM student_groups WHERE group_code = 'Group 1'")
    ).scalar_one() == 3


def test_a_true_duplicate_is_still_rejected(session, offerings):
    """Same offering, same intake, same name is genuinely one group."""
    sit, _ = offerings
    add_group(session, sit, dt.date(2026, 8, 1))
    session.commit()

    # `add_group` flushes, so the constraint fires there rather than at commit.
    with pytest.raises(IntegrityError):
        add_group(session, sit, dt.date(2026, 8, 1))
    session.rollback()


def test_different_group_numbers_coexist_in_one_intake(session, offerings):
    sit, _ = offerings
    for number in range(1, 16):
        add_group(session, sit, dt.date(2026, 8, 1), f"Group {number}")
    session.commit()

    assert session.execute(text("SELECT count(*) FROM student_groups")).scalar_one() == 15


def test_na_is_storable_for_a_non_group_qualification(session, offerings):
    _, rii = offerings
    add_group(session, rii, dt.date(2026, 8, 1), "N/A")
    session.commit()
    assert session.execute(
        text("SELECT group_code FROM student_groups")
    ).scalar_one() == "N/A"


# ---------------------------------------------------------------------------
# Intake is the real date, stored as a date
# ---------------------------------------------------------------------------


def test_a_first_of_month_intake_is_accepted(session, offerings):
    sit, _ = offerings
    add_group(session, sit, dt.date(2026, 8, 1))
    session.commit()
    assert session.execute(
        text("SELECT intake FROM student_groups")
    ).scalar_one() == dt.date(2026, 8, 1)


@pytest.mark.parametrize(
    "intake",
    [
        dt.date(2026, 2, 2),
        dt.date(2026, 2, 23),
        dt.date(2026, 3, 30),
        dt.date(2026, 4, 20),
        dt.date(2026, 7, 20),
        dt.date(2026, 8, 17),
    ],
)
def test_a_real_rolling_intake_date_is_accepted(session, offerings, intake):
    """Approved 12 August 2026: intakes are not normalised to the first of the month.

    These are the actual BSB50420 rolling intake dates. The superseded
    first-of-month CHECK rejected fifty of the fifty-one markers in the
    operational timetable, and rounding them would have moved every intake off
    its real start.
    """
    sit, _ = offerings
    add_group(session, sit, intake)
    session.commit()
    assert session.execute(text("SELECT intake FROM student_groups")).scalar_one() == intake


def test_intake_is_stored_as_a_native_date(session, offerings):
    """Not text: a formatted string cannot be compared, ordered or ranged."""
    sit, _ = offerings
    add_group(session, sit, dt.date(2026, 2, 2))
    session.commit()
    data_type = session.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'student_groups' AND column_name = 'intake'"
        )
    ).scalar_one()
    assert data_type == "date"


def test_no_first_of_month_constraint_remains(session):
    names = session.execute(
        text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'student_groups'::regclass AND contype = 'c'"
        )
    ).scalars().all()
    assert "ck_student_groups_intake_is_first_of_month" not in names


def test_intakes_sort_chronologically(session, offerings):
    """The point of using a date: text sorted 01-Jan-2027 before 01-Aug-2026."""
    sit, _ = offerings
    for intake in (dt.date(2027, 1, 1), dt.date(2026, 8, 1), dt.date(2026, 12, 1)):
        add_group(session, sit, intake)
    session.commit()

    ordered = session.execute(
        text("SELECT intake FROM student_groups ORDER BY intake")
    ).scalars().all()
    assert ordered == [dt.date(2026, 8, 1), dt.date(2026, 12, 1), dt.date(2027, 1, 1)]


def test_a_date_range_filter_works(session, offerings):
    """Impossible against the old text column without parsing every row."""
    sit, _ = offerings
    for intake in (dt.date(2026, 8, 1), dt.date(2026, 12, 1), dt.date(2027, 1, 1)):
        add_group(session, sit, intake)
    session.commit()

    count = session.execute(
        text("SELECT count(*) FROM student_groups WHERE intake >= '2026-12-01' AND intake < '2027-06-01'")
    ).scalar_one()
    assert count == 2
