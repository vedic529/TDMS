"""Student Data import — the database-backed checks (3.2–3.6, plus A9, A11).

Runs against the temporary `tdms_test` database from conftest, seeding its own
reference data and a small BSB rolling calendar. The pure intake-rule cases live
in `test_student_intake.py`.
"""

from __future__ import annotations

import datetime as dt
import io

import pytest
from sqlalchemy import event, func, select, text

from app.core.student_rules import NO_GROUP  # noqa: F401 - documents the N/A group
from app.models.college import Campus, College, CollegeCampus
from app.models.course import CourseOffering, CourseStatus, OfferingDurationOption
from app.models.qualification import Qualification
from app.models.student import Student, StudentGroup
from app.models.timetable import RollingTimetableWeek
from app.models.user import User
from app.models.reason import ReasonCode
from app.services import student_import as imp
from app.services import students as student_service

HEADERS = [
    "Student ID", "First Name", "Last Name", "College", "Campus", "Qualification",
    "CT Student", "CoE / Non-CoE", "Proposed Start Date", "Proposed End Date",
    "Personal Email", "Primary Phone",
]

COLLEGE = "AIBT"
CAMPUS = "Sydney"
QUAL = "BSB50420"
DOMAIN = "aibtglobal.edu.au"

# A 10-week course: start Monday, end = start + 69 days (inclusive weeks = 10).
START = "09-02-2026"   # 9 Feb 2026, inside intake A's first-unit window
END = "19-04-2026"     # +69 days → duration 10


def _monday(y, m, d):
    day = dt.date(y, m, d)
    assert day.weekday() == 0
    return day


@pytest.fixture()
def db(test_factory, test_engine):
    with test_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE students, student_groups, import_batches, import_staged_rows, "
                "import_row_issues, reference_suggestion, course_offerings, offering_duration_options, "
                "college_campuses, campus_source_addresses, campuses, colleges, course_statuses, "
                "qualifications, rolling_timetable_weeks, users, reason_codes, user_activity_records "
                "RESTART IDENTITY CASCADE"
            )
        )
    session = test_factory()
    try:
        _seed(session)
        yield session
    finally:
        session.rollback()
        session.close()


def _seed(session):
    college = College(college_short_name=COLLEGE, college_full_name="AIBT Global", email_domain=DOMAIN, is_active=True)
    campus = Campus(campus_code="SYD", campus_name=CAMPUS, campus_location="Sydney CBD", state="NSW", is_active=True)
    session.add_all([college, campus])
    session.flush()
    session.add(CollegeCampus(college_id=college.id, campus_id=campus.id, is_active=True))
    status = CourseStatus(code="ACTIVE", label="Active", selectable_for_new_records=True, is_active=True)
    qual = Qualification(qualification_code=QUAL, qualification_title="Diploma of Business", is_active=True)
    session.add_all([status, qual])
    session.flush()
    offering = CourseOffering(
        college_id=college.id, campus_id=campus.id, qualification_id=qual.id,
        course_code="BSB50420-SYD", course_status_id=status.id,
    )
    user = User(organisation_email="editor@aibtglobal.edu.au", display_name="Editor", access_level="DATA_EDITOR", account_status="ACTIVE")
    reason = ReasonCode(code="ENTERED_IN_ERROR", label="Entered in error", requires_detail=False, is_active=True)
    session.add_all([offering, user, reason])
    session.flush()
    _seed_rolling(session)
    session.commit()
    # Stash ids the tests reuse.
    session.info["ids"] = {
        "college": college.id, "campus": campus.id, "qual": qual.id,
        "offering": offering.id, "user": user.id, "reason": reason.id,
    }


def _seed_rolling(session):
    """BSB50420, duration 10, one intake whose first unit (U1) spans 3 weeks."""
    label = "BSB50420_10_02 Feb 2026_NA_Intake"
    start = _monday(2026, 2, 2)
    weeks = [
        (1, _monday(2026, 2, 2), "UNIT", "BSBOPS501"),
        (2, _monday(2026, 2, 9), "UNIT", "BSBOPS501"),
        (3, _monday(2026, 2, 16), "UNIT", "BSBOPS501"),
        (4, _monday(2026, 2, 23), "UNIT", "BSBOPS502"),
    ]
    for week_no, monday, stype, unit in weeks:
        session.add(
            RollingTimetableWeek(
                training_package="BSB",
                qualification_code=QUAL,
                duration_weeks=10,
                intake_label=label,
                intake_group="NA",
                intake_start_date=start,
                week_no=week_no,
                week_start_date=monday,
                week_end_date=monday + dt.timedelta(days=6),
                schedule_type=stype,
                schedule_value=unit,
                unit_code=unit,
                unit_count=1,
                unit_slot=1,
            )
        )


def _user(session):
    return session.get(User, session.info["ids"]["user"])


def _csv(rows: list[dict], headers=None) -> bytes:
    headers = headers or HEADERS
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(_q(row.get(h, "")) for h in headers))
    return ("\n".join(lines)).encode("utf-8")


def _q(value: str) -> str:
    value = str(value)
    if "," in value or '"' in value:
        return '"' + value.replace('"', '""') + '"'
    return value


def _row(**over) -> dict:
    base = {
        "Student ID": "S001", "First Name": "Ann", "Last Name": "Lee",
        "College": COLLEGE, "Campus": CAMPUS, "Qualification": QUAL,
        "CT Student": "No", "CoE / Non-CoE": "CoE",
        "Proposed Start Date": START, "Proposed End Date": END,
        "Personal Email": "ann@example.com", "Primary Phone": "0400000000",
    }
    base.update(over)
    return base


def _stage(session, rows, file_name="students.csv", headers=None):
    batch = imp.stage_file(session, user=_user(session), file_name=file_name, payload=_csv(rows, headers))
    session.commit()
    return batch


def _review(session, batch):
    return imp.review_dict(session, batch)


def _apply(session, batch):
    result = imp.apply_batch(session, batch, _user(session))
    session.commit()
    return result


def _row_by_source(review, source_no):
    return next(r for r in review["rows"] if r["source_row_number"] == source_no)


# ===========================================================================
# 3.3 Parsing and staging
# ===========================================================================


def test_p1_csv_and_xlsx_import_identically(db):
    from openpyxl import Workbook

    batch_csv = _stage(db, [_row()])
    review_csv = _review(db, batch_csv)

    wb = Workbook()
    ws = wb.active
    ws.append(HEADERS)
    r = _row()
    ws.append([r[h] for h in HEADERS])
    buffer = io.BytesIO()
    wb.save(buffer)
    batch_xlsx = imp.stage_file(db, user=_user(db), file_name="students.xlsx", payload=buffer.getvalue())
    db.commit()
    review_xlsx = _review(db, batch_xlsx)

    assert _row_by_source(review_csv, 2)["status"] == "READY"
    assert _row_by_source(review_xlsx, 2)["status"] == "READY"
    assert _row_by_source(review_csv, 2)["derived_intake_label"] == _row_by_source(review_xlsx, 2)["derived_intake_label"]


def test_p2_dates_are_day_first(db):
    batch = _stage(db, [_row(**{"Proposed Start Date": "05-06-2026", "Proposed End Date": "13-09-2026"})])
    review = _review(db, batch)
    # 05-06-2026 must read as 5 June, never 6 May: derived from the working value.
    assert imp.parse_day_first_date("05-06-2026")[0] == dt.date(2026, 6, 5)
    assert _row_by_source(review, 2)["status"] in {"READY", "DUPLICATE"}


def test_p3_excel_date_cell_parses(db):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(HEADERS)
    r = _row()
    values = [r[h] for h in HEADERS]
    values[HEADERS.index("Proposed Start Date")] = dt.date(2026, 2, 9)
    values[HEADERS.index("Proposed End Date")] = dt.date(2026, 4, 19)
    ws.append(values)
    buffer = io.BytesIO()
    wb.save(buffer)
    batch = imp.stage_file(db, user=_user(db), file_name="students.xlsx", payload=buffer.getvalue())
    db.commit()
    assert _row_by_source(_review(db, batch), 2)["status"] == "READY"


def test_p4_bad_date_refuses_the_row(db):
    batch = _stage(db, [_row(**{"Proposed Start Date": "not-a-date"})])
    row = _row_by_source(_review(db, batch), 2)
    assert row["status"] == "NEEDS_CORRECTION"
    assert any("Proposed Start Date" in i["field_name"] for i in row["issues"])


def test_p5_end_before_start_is_a_rule_that_can_be_accepted(db):
    """Amended 15 September 2026: a broken rule, so accepted, excluded or corrected."""
    batch = _stage(db, [_row(**{"Proposed Start Date": "19-04-2026", "Proposed End Date": "09-02-2026"})])
    row = _row_by_source(_review(db, batch), 2)
    assert row["status"] == "NEEDS_CORRECTION"
    assert any(issue["issue_status"] == "EXCEPTION" for issue in row["issues"])

    imp.patch_rows(db, batch, [_patch(row["id"], accept_exception=True)])
    db.commit()
    assert _row_by_source(_review(db, batch), 2)["status"] == "READY"
    imp.patch_rows(db, batch, [_patch(row["id"], accept_exception=False)])
    db.commit()
    assert _row_by_source(_review(db, batch), 2)["status"] == "NEEDS_CORRECTION", "Undo asks again"

    imp.patch_rows(db, batch, [_patch(row["id"], accept_exception=True)])
    db.commit()
    assert _apply(db, batch)["inserted"] == 1
    student = db.execute(select(Student)).scalar_one()
    assert student.proposed_end_date < student.proposed_start_date, "stored as written"


def test_p6_duration_is_derived_not_read(db):
    batch = _stage(db, [_row()])
    _apply(db, batch)
    student = db.execute(select(Student)).scalar_one()
    assert student.actual_course_duration_weeks == 10  # (69 + 1) / 7


def test_p7_group_column_ignored_as_note(db):
    headers = HEADERS + ["Group"]
    batch = _stage(db, [{**_row(), "Group": "Group 9"}], headers=headers)
    review = _review(db, batch)
    row = _row_by_source(review, 2)
    assert row["status"] == "READY"
    assert any("Group" in i["field_name"] and i["issue_status"] == "NOTE" for i in row["issues"])
    _apply(db, batch)
    student = db.execute(select(Student)).scalar_one()
    group = db.get(StudentGroup, student.student_group_id)
    assert group.group_code == "NA"  # derived, not the file's "Group 9"


def test_p8_unknown_header_refuses_the_file(db):
    with pytest.raises(imp.StudentImportError):
        _stage(db, [_row()], headers=HEADERS + ["Favourite Colour"])


def test_p9_staging_holds_text(db):
    batch = _stage(db, [_row(**{"Proposed Start Date": "banana"})])
    review = _review(db, batch)
    assert _row_by_source(review, 2)["proposed_start_date_value"] == "banana"  # kept for correction


def test_p10_nothing_written_before_confirm(db):
    _stage(db, [_row()])
    assert db.execute(select(func.count()).select_from(Student)).scalar_one() == 0


def test_p11_correction_clears_the_issue(db):
    batch = _stage(db, [_row(**{"Proposed Start Date": "bad"})])
    review = _review(db, batch)
    row_id = _row_by_source(review, 2)["id"]
    imp.patch_rows(db, batch, [_patch(row_id, corrections=[("Proposed Start Date", START)])])
    db.commit()
    assert _row_by_source(_review(db, batch), 2)["status"] == "READY"


def test_revalidation_preserves_the_derived_intake(db):
    """A patch must not blank the qualification code and lose the intake.

    Regression: `_resolve_references` used to carry the not-yet-populated
    `ev.qualification_code` over whenever `resolved_qualification_id` was already
    set, so every re-validation silently downgraded a MATCHED student to TBD.
    """
    batch = _stage(db, [_row()])
    first = _row_by_source(_review(db, batch), 2)
    assert first["intake_match_status"] == "MATCHED"
    assert first["derived_intake_label"]

    # Any patch triggers a full re-validation.
    imp.patch_rows(db, batch, [_patch(first["id"], corrections=[("Last Name", "Changed")])])
    db.commit()

    again = _row_by_source(_review(db, batch), 2)
    assert again["intake_match_status"] == "MATCHED"
    assert again["derived_intake_label"] == first["derived_intake_label"]

    result = _apply(db, batch)
    assert result["intakes_matched"] == 1
    stored = db.execute(select(Student)).scalar_one()
    assert stored.intake_match_status == "MATCHED"
    assert stored.student_group_id is not None


def test_tbd_row_is_resolved_by_choosing_an_approved_duration(db):
    """A TBD intake is resolvable: choose an available duration (OD-08).

    The chosen duration finds the rolling loop and is stored as the student's
    approved Course Duration Option. The uploaded dates, and the Actual Course
    Duration generated from them, are never rewritten.
    """
    ids = db.info["ids"]
    # An approved 10-week option for this offering, matching the seeded loop.
    db.add(OfferingDurationOption(course_offering_id=ids["offering"], duration_weeks=10, is_active=True))
    db.commit()

    # Dates implying 5 weeks — no rolling timetable exists for that duration.
    short = _row(**{"Proposed Start Date": "09-02-2026", "Proposed End Date": "15-03-2026"})
    batch = _stage(db, [short])
    row = _row_by_source(_review(db, batch), 2)
    assert row["intake_match_status"] == "TBD"
    assert row["derived_intake_label"] is None

    # The review offers the durations this qualification actually runs.
    assert _review(db, batch)["duration_options"][QUAL] == [10]

    imp.patch_rows(db, batch, [_patch(row["id"], duration_weeks=10)])
    db.commit()

    resolved = _row_by_source(_review(db, batch), 2)
    assert resolved["intake_match_status"] == "MATCHED"
    assert resolved["derived_intake_label"] == "BSB50420_10_02 Feb 2026_NA_Intake"

    _apply(db, batch)
    student = db.execute(select(Student)).scalar_one()
    assert student.intake_match_status == "MATCHED"
    assert student.student_group_id is not None
    # The Course Duration Option is stored...
    assert student.course_duration_option_id is not None
    # ...and the uploaded dates are untouched, so the generated duration still
    # reflects what the file actually said.
    assert student.proposed_start_date == dt.date(2026, 2, 9)
    assert student.proposed_end_date == dt.date(2026, 3, 15)
    assert student.actual_course_duration_weeks == 5


def test_p12_excluded_row_not_written(db):
    batch = _stage(db, [_row(**{"Proposed Start Date": "bad"})])
    review = _review(db, batch)
    row_id = _row_by_source(review, 2)["id"]
    imp.patch_rows(db, batch, [_patch(row_id, exclude=True)])
    db.commit()
    assert _row_by_source(_review(db, batch), 2)["status"] == "EXCLUDED_BY_USER"
    result = _apply(db, batch)
    assert result["inserted"] == 0
    assert result["excluded"] == 1


# ===========================================================================
# 3.2 Duplicates and status
# ===========================================================================


def test_d1_default_status_is_active(db):
    _apply(db, _stage(db, [_row()]))
    assert db.execute(select(Student)).scalar_one().status == "ACTIVE"


def test_d2_same_qualification_blocks_until_decided(db):
    _apply(db, _stage(db, [_row()]))
    batch = _stage(db, [_row(**{"First Name": "Anne"})])
    review = _review(db, batch)
    row = _row_by_source(review, 2)
    assert row["status"] == "DUPLICATE"
    assert review["can_apply"] is False
    assert review["duplicates"] and review["duplicates"][0]["scope"] == "SAME_QUALIFICATION"


def test_d3_keep_stored_excludes_incoming(db):
    _apply(db, _stage(db, [_row(**{"First Name": "Ann"})]))
    batch = _stage(db, [_row(**{"First Name": "CHANGED"})])
    row_id = _row_by_source(_review(db, batch), 2)["id"]
    imp.patch_rows(db, batch, [_patch(row_id, duplicate_decision="KEEP_STORED")])
    db.commit()
    _apply(db, batch)
    stored = db.execute(select(Student)).scalars().all()
    assert len(stored) == 1 and stored[0].first_name == "Ann"  # untouched


def test_d4_keep_incoming_replaces_stored(db):
    _apply(db, _stage(db, [_row(**{"First Name": "Ann"})]))
    batch = _stage(db, [_row(**{"First Name": "CHANGED"})])
    row_id = _row_by_source(_review(db, batch), 2)["id"]
    imp.patch_rows(db, batch, [_patch(row_id, duplicate_decision="KEEP_INCOMING")])
    db.commit()
    _apply(db, batch)
    stored = db.execute(select(Student)).scalars().all()
    assert len(stored) == 1 and stored[0].first_name == "CHANGED"


def test_d5_different_qualification_requires_two_distinct_statuses(db):
    # An ACTIVE enrolment already exists in BSB50420 for this student.
    _apply(db, _stage(db, [_row(**{"Student ID": "SX"})]))
    second = _second_offering(db)
    db.commit()

    # Import the same Student ID into a different qualification (BSB40120).
    batch = _stage(db, [_row(**{"Student ID": "SX", "Qualification": "BSB40120"})])
    review = _review(db, batch)
    row = _row_by_source(review, 2)
    assert row["status"] == "DUPLICATE"
    assert row["duplicate_scope"] == "DIFFERENT_QUALIFICATION"
    assert review["can_apply"] is False

    # Setting the incoming status equal to the stored ACTIVE is refused.
    imp.patch_rows(db, batch, [_patch(row["id"], status_value="ACTIVE")])
    db.commit()
    assert _row_by_source(_review(db, batch), 2)["status"] == "DUPLICATE"

    # A distinct status is accepted, and both enrolments then store.
    imp.patch_rows(db, batch, [_patch(row["id"], status_value="NOT_YET_STARTED")])
    db.commit()
    assert _row_by_source(_review(db, batch), 2)["status"] == "READY"
    _apply(db, batch)
    both = db.execute(select(Student).where(Student.student_id == "SX")).scalars().all()
    assert {s.status for s in both} == {"ACTIVE", "NOT_YET_STARTED"}


def test_d6_one_active_enforced_by_database(db):
    """The partial unique index refuses a second ACTIVE row, proven by insert."""
    ids = db.info["ids"]
    db.add(Student(student_id="DUP", first_name="A", coe_status="COE", status="ACTIVE",
                   proposed_start_date=dt.date(2026, 2, 9), proposed_end_date=dt.date(2026, 4, 19),
                   college_email="dup@x", course_offering_id=ids["offering"], intake_match_status="TBD"))
    db.flush()
    db.add(Student(student_id="DUP", first_name="B", coe_status="COE", status="ACTIVE",
                   proposed_start_date=dt.date(2026, 2, 9), proposed_end_date=dt.date(2026, 4, 19),
                   college_email="dup2@x", course_offering_id=ids["offering"], intake_match_status="TBD"))
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_d7_two_enrolments_with_different_statuses_store(db):
    ids = db.info["ids"]
    second = _second_offering(db)
    db.add(Student(student_id="TWO", first_name="A", coe_status="COE", status="ACTIVE",
                   proposed_start_date=dt.date(2026, 2, 9), proposed_end_date=dt.date(2026, 4, 19),
                   college_email="a@x", course_offering_id=ids["offering"], intake_match_status="TBD"))
    db.flush()
    db.add(Student(student_id="TWO", first_name="A", coe_status="COE", status="COMPLETED",
                   proposed_start_date=dt.date(2025, 2, 3), proposed_end_date=dt.date(2025, 4, 13),
                   college_email="a2@x", course_offering_id=second, intake_match_status="TBD"))
    db.flush()
    assert db.execute(select(func.count()).select_from(Student).where(Student.student_id == "TWO")).scalar_one() == 2


def _second_offering(session) -> int:
    """A second offering (a different qualification) for two-enrolment tests."""
    ids = session.info["ids"]
    qual = Qualification(qualification_code="BSB40120", qualification_title="Cert IV Business", is_active=True)
    session.add(qual)
    session.flush()
    offering = CourseOffering(
        college_id=ids["college"], campus_id=ids["campus"], qualification_id=qual.id,
        course_code="BSB40120-SYD", course_status_id=session.execute(select(CourseStatus.id)).scalar_one(),
    )
    session.add(offering)
    session.flush()
    return offering.id


def test_d8_soft_deleted_does_not_block_new_enrolment(db):
    ids = db.info["ids"]
    gone = Student(student_id="RE", first_name="A", coe_status="COE", status="ACTIVE",
                   proposed_start_date=dt.date(2026, 2, 9), proposed_end_date=dt.date(2026, 4, 19),
                   college_email="a@x", course_offering_id=ids["offering"], intake_match_status="TBD",
                   is_deleted=True, deleted_at=dt.datetime.now(dt.timezone.utc), deleted_by_user_id=ids["user"],
                   delete_reason_id=ids["reason"], recovery_deadline=dt.date(2026, 3, 1))
    db.add(gone)
    db.flush()
    db.add(Student(student_id="RE", first_name="A2", coe_status="COE", status="ACTIVE",
                   proposed_start_date=dt.date(2026, 2, 9), proposed_end_date=dt.date(2026, 4, 19),
                   college_email="a2@x", course_offering_id=ids["offering"], intake_match_status="TBD"))
    db.flush()  # no IntegrityError


# ===========================================================================
# 3.4 References and suggestions
# ===========================================================================


def test_r1_matching_references_store_as_ids(db):
    _apply(db, _stage(db, [_row()]))
    student = db.execute(select(Student)).scalar_one()
    ids = db.info["ids"]
    assert student.course_offering_id == ids["offering"]


def test_r2_campus_not_linked_to_college_is_reported(db):
    other = Campus(campus_code="MEL", campus_name="Melbourne", campus_location="Melbourne CBD", state="VIC", is_active=True)
    db.add(other)
    db.commit()
    batch = _stage(db, [_row(**{"Campus": "Melbourne"})])
    row = _row_by_source(_review(db, batch), 2)
    assert row["status"] == "UNMATCHED_REFERENCE"


def test_r3_unmatched_raises_one_suggestion(db):
    batch = _stage(db, [_row(**{"College": "Nowhere College"})])
    row_id = _row_by_source(_review(db, batch), 2)["id"]
    imp.patch_rows(db, batch, [_patch(row_id, reference_entity="college", reference_choice="RAISE")])
    db.commit()
    result = _apply(db, batch)
    from app.models.allocation import ReferenceSuggestion

    suggestions = db.execute(select(ReferenceSuggestion).where(ReferenceSuggestion.source == "STUDENT_IMPORT")).scalars().all()
    assert len(suggestions) == 1 and suggestions[0].entity_type == "COLLEGE"
    # Amended 15 September 2026: the raised row is stored unverified, not dropped.
    assert result["inserted"] == 1 and result["unverified"] == 1
    student = db.execute(select(Student)).scalar_one()
    assert student.course_offering_id is None
    assert student.college_text == "Nowhere College"


def test_r4_an_exception_is_not_offered_for_an_unmatched_value(db):
    """Amended 15 September 2026: EXCEPT is not honoured - the row still blocks."""
    batch = _stage(db, [_row(**{"College": "Nowhere"})])
    row_id = _row_by_source(_review(db, batch), 2)["id"]
    imp.patch_rows(db, batch, [_patch(row_id, reference_entity="college", reference_choice="EXCEPT")])
    db.commit()
    assert _row_by_source(_review(db, batch), 2)["status"] == "UNMATCHED_REFERENCE"


def test_r4b_resolving_the_suggestion_completes_the_student(db):
    """An unverified student gains its offering, email and intake when the value resolves."""
    from app.models.allocation import ReferenceSuggestion
    from app.services import reference_suggestion_service as suggestions

    ids = db.info["ids"]
    batch = _stage(db, [_row(**{"College": "Nowhere College"})])
    row_id = _row_by_source(_review(db, batch), 2)["id"]
    imp.patch_rows(db, batch, [_patch(row_id, reference_entity="college", reference_choice="RAISE")])
    db.commit()
    _apply(db, batch)

    listed, total = student_service.list_students(db, unverified=True)
    assert total == 1
    assert listed[0]["is_unverified"] is True
    assert listed[0]["unverified_fields"] == ["college"]
    assert listed[0]["college"] == "Nowhere College", "what the file said is shown"

    entry = db.execute(select(ReferenceSuggestion)).scalar_one()
    _resolved, updated = suggestions.resolve_suggestion(
        db, _user(db), suggestion_id=entry.id, action="MAP", resolved_entity_id=ids["college"]
    )
    db.commit()
    assert updated >= 1

    student = db.execute(select(Student)).scalar_one()
    assert student.course_offering_id == ids["offering"]
    assert student.college_text == COLLEGE, "the spelling is corrected everywhere"
    assert student.college_email == f"s001@{DOMAIN}"
    assert student.intake_match_status == "MATCHED"
    assert student_service.list_students(db, unverified=True)[1] == 0


def test_r4c_a_combination_no_offering_holds_is_a_qualification_suggestion(db):
    """All three values resolve but nothing offers them together: raised, not a dead end."""
    from app.models.allocation import ReferenceSuggestion

    db.add(Qualification(qualification_code="CHC33021", qualification_title="Cert III Individual Support", is_active=True))
    db.commit()
    batch = _stage(db, [_row(**{"Qualification": "CHC33021"})])
    row = _row_by_source(_review(db, batch), 2)
    assert row["status"] == "UNMATCHED_REFERENCE"
    assert any(issue["field_name"] == "Qualification" and issue["issue_status"] == "BLOCK" for issue in row["issues"])

    imp.patch_rows(db, batch, [_patch(row["id"], reference_entity="qualification", reference_choice="RAISE")])
    db.commit()
    assert _row_by_source(_review(db, batch), 2)["status"] == "READY"
    _apply(db, batch)

    entry = db.execute(select(ReferenceSuggestion)).scalar_one()
    assert entry.entity_type == "QUALIFICATION"
    assert entry.attributes == {"locations": [{"college": COLLEGE, "campus": CAMPUS}]}
    assert db.execute(select(Student)).scalar_one().course_offering_id is None


def test_r5_resolve_inline_clears_issue(db):
    ids = db.info["ids"]
    batch = _stage(db, [_row(**{"College": "Nowhere"})])
    row_id = _row_by_source(_review(db, batch), 2)["id"]
    imp.patch_rows(db, batch, [_patch(row_id, reference_entity="college", reference_choice="RESOLVE", reference_resolved_id=ids["college"])])
    db.commit()
    assert _row_by_source(_review(db, batch), 2)["status"] == "READY"


def test_r6_same_value_deduplicated_with_occurrence_count(db):
    rows = [_row(**{"Student ID": f"S{n}", "College": "Nowhere"}) for n in range(5)]
    batch = _stage(db, rows)
    review = _review(db, batch)
    patches = [_patch(r["id"], reference_entity="college", reference_choice="RAISE") for r in review["rows"]]
    imp.patch_rows(db, batch, patches)
    db.commit()
    _apply(db, batch)
    from app.models.allocation import ReferenceSuggestion

    suggestion = db.execute(select(ReferenceSuggestion).where(ReferenceSuggestion.source == "STUDENT_IMPORT")).scalar_one()
    assert suggestion.occurrence_count == 5


# ===========================================================================
# 3.1 service-level (A9 Credit Transfer, A11 shared group)
# ===========================================================================


def test_a9_credit_transfer_has_no_intake(db):
    _apply(db, _stage(db, [_row(**{"CT Student": "Yes"})]))
    student = db.execute(select(Student)).scalar_one()
    assert student.intake_match_status == "NOT_APPLICABLE"
    assert student.student_group_id is None


def test_a11_two_students_one_intake_share_a_group(db):
    rows = [_row(**{"Student ID": "A", "Proposed Start Date": "09-02-2026"}),
            _row(**{"Student ID": "B", "Proposed Start Date": "16-02-2026", "Proposed End Date": "26-04-2026"})]
    _apply(db, _stage(db, rows))
    students = db.execute(select(Student).where(Student.intake_match_status == "MATCHED")).scalars().all()
    assert len(students) == 2
    assert students[0].student_group_id == students[1].student_group_id
    assert db.execute(select(func.count()).select_from(StudentGroup)).scalar_one() == 1


def test_a7_no_rolling_timetable_is_tbd_and_stored(db):
    # A qualification with no rolling weeks loaded stores TBD, not refused.
    q = Qualification(qualification_code="CHC33021", qualification_title="Cert III Individual Support", is_active=True)
    db.add(q)
    db.flush()
    ids = db.info["ids"]
    db.add(CourseOffering(college_id=ids["college"], campus_id=ids["campus"], qualification_id=q.id,
                          course_code="CHC-SYD", course_status_id=db.execute(select(CourseStatus.id)).scalar_one()))
    db.commit()
    batch = _stage(db, [_row(**{"Qualification": "CHC33021"})])
    row = _row_by_source(_review(db, batch), 2)
    assert row["status"] == "READY"
    assert row["intake_match_status"] == "TBD"


# ===========================================================================
# 3.5 Efficiency
# ===========================================================================


def _count_queries(engine):
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    return counter, _before


def test_e1_e3_query_count_is_flat(db, test_engine):
    rows_100 = [_row(**{"Student ID": f"S{n}"}) for n in range(100)]
    rows_1000 = [_row(**{"Student ID": f"T{n}"}) for n in range(1000)]

    counter, listener = _count_queries(test_engine)
    try:
        imp.stage_file(db, user=_user(db), file_name="a.csv", payload=_csv(rows_100))
        db.commit()
        at_100 = counter["n"]
        counter["n"] = 0
        imp.stage_file(db, user=_user(db), file_name="b.csv", payload=_csv(rows_1000))
        db.commit()
        at_1000 = counter["n"]
    finally:
        event.remove(test_engine, "before_cursor_execute", listener)

    # A 10x larger file must not cost ~10x the queries: the difference is a small
    # constant (the two bulk inserts split into batches), not a factor.
    assert at_1000 < at_100 * 3, f"100 rows: {at_100} queries, 1000 rows: {at_1000}"


def test_e4_apply_bulk_inserts(db, test_engine):
    batch = _stage(db, [_row(**{"Student ID": f"S{n}"}) for n in range(20)])
    counter, listener = _count_queries(test_engine)
    try:
        imp.apply_batch(db, batch, _user(db))
        db.commit()
    finally:
        event.remove(test_engine, "before_cursor_execute", listener)
    inserts = db.execute(select(func.count()).select_from(Student)).scalar_one()
    assert inserts == 20
    # Far fewer queries than one-insert-per-student would need.
    assert counter["n"] < 20


def test_e5_pagination_caps_results(db):
    _apply(db, _stage(db, [_row(**{"Student ID": f"S{n}"}) for n in range(30)]))
    items, total = student_service.list_students(db, limit=10, offset=0)
    assert len(items) == 10 and total == 30


# ===========================================================================
# 3.6 Clean slate
# ===========================================================================


def test_s6_import_refills_the_tables(db):
    assert db.execute(select(func.count()).select_from(Student)).scalar_one() == 0
    _apply(db, _stage(db, [_row()]))
    assert db.execute(select(func.count()).select_from(Student)).scalar_one() == 1


def _patch(row_id, **kw):
    from app.schemas.student import RowCorrection, RowPatch

    corrections = kw.pop("corrections", None)
    if corrections is not None:
        corrections = [RowCorrection(column=c, value=v) for c, v in corrections]
    return RowPatch(row_id=row_id, corrections=corrections, **kw)


def test_rejecting_a_value_deletes_its_unverified_students_the_approved_way(db):
    """DATA-04 holds however the deletion was decided: a reason, and a way back.

    Approved 16 September 2026: Reject removes what carries an unapproved value.
    A student is never hard-deleted, so the decision is refused until a reason is
    given, and the record stays recoverable for the recycle period.
    """
    import pytest

    from app.models.allocation import ReferenceSuggestion
    from app.services import reference_suggestion_service as suggestions
    from app.services.allocation_import import AllocationImportError

    batch = _stage(db, [_row(**{"College": "Rejected College"})])
    row_id = _row_by_source(_review(db, batch), 2)["id"]
    imp.patch_rows(db, batch, [_patch(row_id, reference_entity="college", reference_choice="RAISE")])
    db.commit()
    _apply(db, batch)

    entry = db.execute(select(ReferenceSuggestion)).scalar_one()
    with pytest.raises(AllocationImportError) as refused:
        suggestions.resolve_suggestion(db, _user(db), suggestion_id=entry.id, action="REJECT")
    assert "deletion reason" in str(refused.value)
    assert db.execute(select(Student)).scalar_one().is_deleted is False, "nothing went without a reason"

    suggestions.resolve_suggestion(
        db,
        _user(db),
        suggestion_id=entry.id,
        action="REJECT",
        reason_code="ENTERED_IN_ERROR",
    )
    db.commit()
    student = db.execute(select(Student)).scalar_one()
    assert student.is_deleted is True
    assert student.recovery_deadline is not None
    assert student.delete_reason_id is not None
    assert "Rejected College" in (student.delete_reason_detail or "")


# ===========================================================================
# Clearing the student records (approved 21 September 2026)
# ===========================================================================


def test_applying_an_import_drops_its_staged_copy_of_the_file(db):
    """The staged rows hold names, emails and phones and are reachable from
    nowhere once the import finishes, so they go. The batch row stays."""
    from app.models.import_batch import ImportBatch, ImportStagedRow

    batch = _stage(db, [_row()])
    assert db.execute(select(func.count()).select_from(ImportStagedRow)).scalar_one() == 1

    _apply(db, batch)

    assert db.execute(select(func.count()).select_from(ImportStagedRow)).scalar_one() == 0
    kept = db.execute(select(ImportBatch)).scalar_one()
    assert kept.status == "APPLIED" and kept.inserted_count == 1, "the upload record survives"
    assert db.execute(select(func.count()).select_from(Student)).scalar_one() == 1


def test_clearing_removes_every_student_its_intake_and_the_import_copies(db):
    """Super Admin's Clear Database: nothing student-shaped is left behind."""
    from app.models.import_batch import ImportBatch, ImportStagedRow
    from app.services import student_maintenance as maintenance

    _apply(db, _stage(db, [_row(), _row(**{"Student ID": "S002", "First Name": "Bob"})]))
    # A soft-deleted student: "no deleted record left" covers the recycle area.
    student = db.execute(select(Student).order_by(Student.id)).scalars().first()
    student_service.delete_student(
        db, _user(db), student.id, reason_code_id=db.info["ids"]["reason"], reason_detail="test"
    )
    db.commit()
    # An upload someone opened and never finished.
    _stage(db, [_row(**{"Student ID": "S003", "First Name": "Cara"})])

    preview = maintenance.clear_preview(db)
    assert preview["students"] == 1 and preview["deleted_students"] == 1
    assert preview["intakes"] >= 1
    assert preview["import_batches"] == 2, "the applied one and the abandoned one"
    assert preview["staged_rows"] == 1, "only the unfinished upload still holds rows"

    removed = maintenance.clear_student_records(db, _user(db))
    db.commit()

    assert removed["students"] == 1 and removed["deleted_students"] == 1
    assert db.execute(select(func.count()).select_from(Student)).scalar_one() == 0
    assert db.execute(select(func.count()).select_from(StudentGroup)).scalar_one() == 0
    assert db.execute(select(func.count()).select_from(ImportBatch)).scalar_one() == 0
    assert db.execute(select(func.count()).select_from(ImportStagedRow)).scalar_one() == 0
    # The rolling timetable says what each intake studies and is not student data.
    assert db.execute(select(func.count()).select_from(RollingTimetableWeek)).scalar_one() > 0


def test_clearing_closes_the_suggestions_its_records_were_behind(db):
    """An entry exists only while a stored row still carries its value."""
    from app.models.allocation import ReferenceSuggestion
    from app.services import student_maintenance as maintenance

    batch = _stage(db, [_row(**{"College": "Unknown College"})])
    row_id = _row_by_source(_review(db, batch), 2)["id"]
    imp.patch_rows(db, batch, [_patch(row_id, reference_entity="college", reference_choice="RAISE")])
    db.commit()
    _apply(db, batch)
    entry = db.execute(select(ReferenceSuggestion)).scalars().one()
    assert entry.status == "PENDING"

    removed = maintenance.clear_student_records(db, _user(db))
    db.commit()

    assert removed["suggestions"] == 1
    assert db.execute(select(func.count()).select_from(ReferenceSuggestion)).scalar_one() == 0


def test_clearing_leaves_a_trainer_import_alone(db):
    """Trainer imports share these tables; only student batches belong here."""
    from app.models.import_batch import ImportBatch
    from app.services import student_maintenance as maintenance

    _apply(db, _stage(db, [_row()]))
    trainer_batch = ImportBatch(
        batch_reference="TRN-1", file_name="trainers.xlsx", uploaded_at=dt.datetime.now(dt.timezone.utc),
        uploaded_by_user_id=_user(db).id, row_count=3, status="STAGED", data_type="UNITS",
    )
    db.add(trainer_batch)
    db.commit()

    maintenance.clear_student_records(db, _user(db))
    db.commit()

    kept = db.execute(select(ImportBatch)).scalars().all()
    assert [row.data_type for row in kept] == ["UNITS"]


def test_a_campus_spelling_is_decided_per_college(db):
    """Approved 21 September 2026.

    "Sydney (Haymarket)" is one place at one college and another somewhere else,
    so a campus entry names its college and repairs only that college's rows.
    Mapping one college's entry must not reach the other's students.
    """
    from app.models.allocation import ReferenceSuggestion
    from app.services import reference_suggestion_service as suggestions

    ids = db.info["ids"]
    other_college = College(
        college_short_name="REACH", college_full_name="REACH College", email_domain="reach.edu.au", is_active=True
    )
    other_campus = Campus(
        campus_code="BLK", campus_name="Blacktown", campus_location="Blacktown", state="NSW", is_active=True
    )
    db.add_all([other_college, other_campus])
    db.flush()
    db.add(CollegeCampus(college_id=other_college.id, campus_id=other_campus.id, is_active=True))
    status_id = db.execute(text("SELECT id FROM course_statuses LIMIT 1")).scalar_one()
    db.add(
        CourseOffering(
            college_id=other_college.id, campus_id=other_campus.id, qualification_id=ids["qual"],
            course_code="BSB50420-BLK", course_status_id=status_id,
        )
    )
    db.commit()

    unknown = "Sydney (Haymarket)"
    batch = _stage(
        db,
        [
            _row(**{"Campus": unknown}),
            _row(**{"Student ID": "S002", "First Name": "Bob", "College": "REACH", "Campus": unknown}),
        ],
    )
    review = _review(db, batch)
    imp.patch_rows(
        db,
        batch,
        [
            _patch(_row_by_source(review, 2)["id"], reference_entity="campus", reference_choice="RAISE"),
            _patch(_row_by_source(review, 3)["id"], reference_entity="campus", reference_choice="RAISE"),
        ],
    )
    db.commit()
    _apply(db, batch)

    entries = db.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.entity_type == "CAMPUS")
    ).scalars().all()
    assert len(entries) == 2, "one entry per college, not one shared entry"
    by_college = {(entry.context or {}).get("college"): entry for entry in entries}
    assert set(by_college) == {COLLEGE, "REACH"}
    for entry in entries:
        assert suggestions.unresolved_total(db, "CAMPUS", entry.normalised_value, entry.context) == 1

    # Map only AIBT's entry, to AIBT's own campus.
    suggestions.resolve_suggestion(
        db, _user(db), suggestion_id=by_college[COLLEGE].id, action="MAP", resolved_entity_id=ids["campus"]
    )
    db.commit()

    students = {row.student_id: row for row in db.execute(select(Student)).scalars()}
    assert students["S001"].course_offering_id == ids["offering"], "AIBT's student is completed"
    assert students["S001"].campus_text == CAMPUS, "and its spelling corrected"
    assert students["S002"].course_offering_id is None, "REACH's student is untouched"
    assert students["S002"].campus_text == unknown

    reach = db.get(ReferenceSuggestion, by_college["REACH"].id)
    assert reach.status == "PENDING"
    assert suggestions.unresolved_total(db, "CAMPUS", reach.normalised_value, reach.context) == 1
