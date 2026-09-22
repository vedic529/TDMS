"""Clearing the allocation records — scope, permission and audit.

The value of these tests is the **boundary**: what the clear must not touch.
A destructive button that quietly took the rolling timetable or a student's
intake with it would be discovered only after the data was gone.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select, text

from app.models.activity import UserActivityRecord
from app.models.allocation import (
    AllocationDelivery,
    AllocationDeliveryIntake,
    AllocationImportBatch,
    AllocationSession,
    AllocationSourceRow,
    ReferenceSuggestion,
)
from app.models.timetable import RollingTimetableWeek
from app.models.user import User
from app.services.allocation_maintenance import clear_allocation_records, clear_preview
from app.services.reference_suggestions import raise_reference_suggestion

from tests.test_allocation_records import (  # reuse the approved fixtures
    EDITOR,
    VIEWER,
    as_user,
    base_row,
    client,  # noqa: F401 - fixture
    csv_bytes,
    people,  # noqa: F401 - fixture
    refs,  # noqa: F401 - fixture
)

pytestmark = pytest.mark.database

SUPER = "clear.super@chelsongordon.com"


@pytest.fixture()
def super_admin(session, people):
    from app.auth.mock import mock_claims_for

    claims = mock_claims_for(SUPER)
    if session.execute(select(User).where(User.organisation_email == SUPER)).scalar_one_or_none() is None:
        session.add(
            User(
                organisation_email=SUPER,
                display_name="Clear Super",
                access_level="SUPER_ADMIN",
                account_status="ACTIVE",
                entra_object_id=claims.object_id,
                entra_tenant_id=claims.tenant_id,
            )
        )
        session.commit()
    return SUPER


def _editor(session) -> User:
    return session.execute(select(User).where(User.organisation_email == EDITOR)).scalar_one()


@pytest.fixture()
def loaded(session, refs):
    """Allocation rows, suggestions from three sources, and rolling weeks."""
    from app.services.allocation_import import ImportOverrides, apply_rows

    # `rolling_timetable_weeks` is not in the shared truncate set, so this
    # fixture clears what it is about to insert rather than colliding with the
    # previous test's copy.
    session.execute(text("TRUNCATE TABLE rolling_timetable_weeks RESTART IDENTITY CASCADE"))

    payload = csv_bytes(
        [
            base_row(refs, **{"Campus Location": "Unknown Campus", "Units of Competency ID": f"CL{n}"})
            for n in range(3)
        ]
    )
    apply_rows(
        session,
        training_package="BSB",
        file_name="clear.csv",
        file_size_bytes=len(payload),
        payload=payload,
        apply_mode="REPLACE",
        raise_suggestions=True,
        overrides=ImportOverrides.from_payload({}, True),
        user=_editor(session),
    )

    # Entries from the two other sources, which must survive.
    raise_reference_suggestion(
        session, entity_type="COLLEGE", raw_value="Student Side", context={}, source="STUDENT_IMPORT"
    )
    raise_reference_suggestion(
        session, entity_type="QUALIFICATION", raw_value="Rolling Side", context={}, source="ROLLING_IMPORT"
    )

    # A rolling week, which the clear must leave alone.
    session.execute(
        text(
            "INSERT INTO rolling_timetable_weeks "
            "(training_package, qualification_code, duration_weeks, intake_label, intake_group, "
            " intake_start_date, week_no, week_start_date, week_end_date, schedule_type, "
            " schedule_value, unit_code, unit_count, unit_slot) "
            "VALUES ('BSB', 'BSB50420', 52, 'KEEP_ME_Intake', 'NA', DATE '2026-01-19', 1, "
            " DATE '2026-01-19', DATE '2026-01-25', 'UNIT', 'BSBCRT511', 'BSBCRT511', 1, 1)"
        )
    )
    session.commit()
    return True


def _count(session, model) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def test_preview_counts_before_anything_is_deleted(session, loaded):
    preview = clear_preview(session)
    assert preview["deliveries"] > 0
    assert preview["sessions"] > 0
    assert preview["suggestions"] >= 1
    # Recorded exceptions went on 15 September 2026; the count stays, at zero.
    assert preview["exceptions"] == 0
    # Counting must not delete.
    assert _count(session, AllocationDelivery) == preview["deliveries"]


def test_clear_removes_every_allocation_row(session, loaded):
    removed = clear_allocation_records(session, _editor(session))
    session.commit()

    assert _count(session, AllocationDelivery) == 0
    assert _count(session, AllocationSession) == 0, "sessions cascade with their delivery"
    assert _count(session, AllocationDeliveryIntake) == 0, "intake links cascade too"
    assert _count(session, AllocationImportBatch) == 0
    assert _count(session, AllocationSourceRow) == 0
    assert removed["deliveries"] > 0


def test_clear_removes_only_allocation_suggestions(session, loaded):
    """The boundary that matters: another import's decisions are not discarded."""
    clear_allocation_records(session, _editor(session))
    session.commit()

    remaining = session.execute(select(ReferenceSuggestion)).scalars().all()
    sources = {row.source for row in remaining}
    assert "ALLOCATION_IMPORT" not in sources, "allocation entries go with their rows"
    assert "STUDENT_IMPORT" in sources, "a student-import decision must survive"
    assert "ROLLING_IMPORT" in sources, "a rolling-import decision must survive"


def test_clear_does_not_touch_the_rolling_timetable(session, loaded):
    """Approved scope: the rolling timetable is what every student's intake needs."""
    before = _count(session, RollingTimetableWeek)
    assert before > 0

    clear_allocation_records(session, _editor(session))
    session.commit()

    assert _count(session, RollingTimetableWeek) == before


def test_clear_does_not_touch_students_or_their_groups(session, refs, loaded):
    """A button on the timetable tab must not reach into Student Data."""
    from app.models.student import Student, StudentGroup

    status_id = session.execute(
        text("SELECT id FROM course_statuses LIMIT 1")
    ).scalar_one_or_none()
    if status_id is None:
        status_id = session.execute(
            text(
                "INSERT INTO course_statuses (code, label, selectable_for_new_records, is_active) "
                "VALUES ('ACTIVE', 'Active', true, true) RETURNING id"
            )
        ).scalar_one()
    offering = session.execute(
        text(
            "INSERT INTO course_offerings (college_id, campus_id, qualification_id, course_code, course_status_id) "
            "VALUES (:c, :p, :q, 'CLR-1', :s) RETURNING id"
        ),
        {"c": refs["college_id"], "p": refs["campus_id"], "q": refs["qual_id"], "s": status_id},
    ).scalar_one()
    group = StudentGroup(
        group_code="NA",
        course_offering_id=offering,
        intake=dt.date(2026, 1, 19),
        rolling_intake_label="KEEP_ME_Intake",
        is_active=True,
    )
    session.add(group)
    session.flush()
    session.add(
        Student(
            student_id="CLR0001",
            first_name="Keep",
            coe_status="COE",
            status="ACTIVE",
            intake_match_status="MATCHED",
            proposed_start_date=dt.date(2026, 1, 19),
            proposed_end_date=dt.date(2027, 1, 17),
            college_email="clr0001@x.test",
            course_offering_id=offering,
            student_group_id=group.id,
        )
    )
    session.commit()

    clear_allocation_records(session, _editor(session))
    session.commit()

    student = session.execute(select(Student).where(Student.student_id == "CLR0001")).scalar_one()
    assert student.intake_match_status == "MATCHED", "the student's intake is untouched"
    assert student.student_group_id is not None
    assert _count(session, StudentGroup) >= 1


def test_clear_writes_an_activity_record(session, loaded):
    clear_allocation_records(session, _editor(session))
    session.commit()

    logged = session.execute(
        select(UserActivityRecord).order_by(UserActivityRecord.id.desc())
    ).scalars().first()
    assert "Cleared the allocation records" in logged.plain_language_detail
    assert "rolling timetable and student records were not affected" in logged.plain_language_detail


def test_only_a_super_admin_may_clear(client, loaded, super_admin):
    """A Data Editor maintains timetables but may not wipe them."""
    assert client.delete("/allocation/records", headers=as_user(VIEWER)).status_code == 403
    assert client.delete("/allocation/records", headers=as_user(EDITOR)).status_code == 403
    assert client.get("/allocation/records/clear-preview", headers=as_user(EDITOR)).status_code == 403

    preview = client.get("/allocation/records/clear-preview", headers=as_user(super_admin))
    assert preview.status_code == 200
    assert preview.json()["deliveries"] > 0

    cleared = client.delete("/allocation/records", headers=as_user(super_admin))
    assert cleared.status_code == 200
    assert cleared.json()["deliveries"] > 0

    after = client.get("/allocation/records/clear-preview", headers=as_user(super_admin))
    assert after.json()["deliveries"] == 0
