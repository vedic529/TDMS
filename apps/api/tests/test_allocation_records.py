"""Allocation records — parse, model, import, calendar."""

from __future__ import annotations

import csv
import io
from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text

from app.api import deps
from app.auth.mock import mock_claims_for
from app.core.config import Settings, get_settings
from app.main import app
from app.models.activity import UserActivityRecord
from app.models.allocation import AllocationDelivery, AllocationSession, ReferenceSuggestion
from app.models.user import User
from app.services.allocation_calendar import CALENDAR_QUERY_COUNT, calendar_month
from app.services.allocation_import import ImportOverrides, apply_rows, issue_id, parse_days_and_times, validate_bytes
from app.services.allocation_profiles import ALLOCATION_COLUMNS
from app.services.allocation_rules import is_standard_class_length, mode_matrix
from app.services.allocation_edit import update_session

pytestmark = pytest.mark.database

VIEWER = "alloc.viewer@chelsongordon.com"
EDITOR = "alloc.editor@chelsongordon.com"
MONDAY = date(2026, 1, 19)


def csv_bytes(rows: list[list]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(ALLOCATION_COLUMNS)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def base_row(refs: dict | None = None, **overrides) -> list:
    times = "Wednesday- 9 am to 5 pm\nThursday- 9 am to 5 pm"
    names = refs or {}
    row = [
        names.get("college_full_name", "Test College"),
        names.get("campus_location", "Somewhere"),
        "BSB50420",
        "Diploma",
        52,
        "NA",
        20,
        "BSBCRT511",
        "Critical thinking",
        "Theory Only",
        "F2FP",
        "2026-01-19",
        "2026-02-08",
        times,
        names.get("facility_reference", "Room 1"),
        "NA",
        names.get("trainer_name", "Pat Trainer"),
        "NA",
        "NA",
        "NA",
        "NA",
        "NA",
        "NA",
        "NA",
        "NA",
    ]
    mapping = {name: index for index, name in enumerate(ALLOCATION_COLUMNS)}
    for key, value in overrides.items():
        row[mapping[key]] = value
    return row


@pytest.fixture()
def people(session):
    session.execute(text("TRUNCATE TABLE user_activity_records, users RESTART IDENTITY CASCADE"))
    for email, level in ((VIEWER, "VIEWER"), (EDITOR, "DATA_EDITOR")):
        claims = mock_claims_for(email)
        session.add(
            User(
                organisation_email=email,
                display_name=email.split("@")[0],
                access_level=level,
                account_status="ACTIVE",
                entra_object_id=claims.object_id,
                entra_tenant_id=claims.tenant_id,
            )
        )
    session.commit()


@pytest.fixture()
def client(test_factory, people):
    def _get_db():
        db = test_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = _get_db
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="development", auth_mode="mock")
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def as_user(email: str) -> dict[str, str]:
    return {"X-TDMS-Mock-User": email}


@pytest.fixture()
def refs(session, people):
    suffix = str(session.execute(text("SELECT nextval('colleges_id_seq')")).scalar_one())
    session.execute(text("TRUNCATE TABLE allocation_session, allocation_delivery, allocation_delivery_intake, allocation_source_row, allocation_import_batch, reference_suggestion RESTART IDENTITY CASCADE"))
    college_id = session.execute(
        text(
            "INSERT INTO colleges (college_short_name, college_full_name, is_active) "
            "VALUES (:short, :full, true) RETURNING id"
        ),
        {"short": f"T_CO_{suffix}", "full": f"Test College {suffix}"},
    ).scalar_one()
    campus_id = session.execute(
        text(
            "INSERT INTO campuses (campus_code, campus_name, campus_location, state, is_active) "
            "VALUES (:code, 'Test Campus', :loc, 'TAS', true) RETURNING id"
        ),
        {"code": f"T_CA_{suffix}", "loc": f"Somewhere {suffix}"},
    ).scalar_one()
    session.execute(text("INSERT INTO college_campuses (college_id, campus_id, is_active) VALUES (:c, :p, true)"), {"c": college_id, "p": campus_id})
    unit_id = session.execute(text("SELECT id FROM units WHERE unit_code = 'BSBCRT511'")).scalar_one_or_none()
    if unit_id is None:
        unit_id = session.execute(
            text("INSERT INTO units (unit_code, unit_title, is_active) VALUES ('BSBCRT511', 'Critical thinking', true) RETURNING id")
        ).scalar_one()
    else:
        session.execute(text("UPDATE units SET unit_title = 'Critical thinking' WHERE id = :id"), {"id": unit_id})
    qual_id = session.execute(text("SELECT id FROM qualifications WHERE qualification_code = 'BSB50420'")).scalar_one_or_none()
    if qual_id is None:
        qual_id = session.execute(
            text("INSERT INTO qualifications (qualification_code, qualification_title, is_active) VALUES ('BSB50420', 'Diploma', true) RETURNING id")
        ).scalar_one()
    else:
        session.execute(text("UPDATE qualifications SET qualification_title = 'Diploma' WHERE id = :id"), {"id": qual_id})
    facility_id = session.execute(
        text(
            "INSERT INTO facilities (facility_reference, campus_id, source_location, facility_type, capacity, is_active) "
            "VALUES ('Room 1', :p, '', 'Classroom', 30, true) RETURNING id"
        ),
        {"p": campus_id},
    ).scalar_one()
    session.execute(text("INSERT INTO facility_colleges (facility_id, college_id) VALUES (:f, :c)"), {"f": facility_id, "c": college_id})
    trainer_id = session.execute(
        text("INSERT INTO trainers (trainer_id, trainer_name, is_active, is_deleted) VALUES (:tid, :name, true, false) RETURNING id"),
        {"tid": f"TR_{suffix}", "name": f"Pat Trainer {suffix}"},
    ).scalar_one()
    session.commit()
    return {
        "college_id": college_id,
        "campus_id": campus_id,
        "qual_id": qual_id,
        "unit_id": unit_id,
        "facility_id": facility_id,
        "trainer_id": trainer_id,
        "college_full_name": f"Test College {suffix}",
        "campus_location": f"Somewhere {suffix}",
        "facility_reference": "Room 1",
        "trainer_name": f"Pat Trainer {suffix}",
        "trainer_code": f"TR_{suffix}",
    }


def test_p1_two_days_one_cell():
    issues = []
    parsed = parse_days_and_times("Wednesday- 9 am to 5 pm\nThursday- 9 am to 5 pm", 2, "Theory Class Days and Times", issues)
    assert not issues
    assert [(day, start, end) for day, start, end in parsed] == [
        ("WEDNESDAY", time(9, 0), time(17, 0)),
        ("THURSDAY", time(9, 0), time(17, 0)),
    ]


def test_p11_bad_time_names_the_text():
    issues = []
    parse_days_and_times("Wednesday 9-5", 4, "Theory Class Days and Times", issues)
    assert issues[0].kind == "unparseable_days_and_times"
    assert "Wednesday 9-5" in issues[0].message


def test_p12_ambiguous_date_refused(session, refs):
    payload = csv_bytes([base_row(refs, **{"Unit of Competency Start Date": "1/2/2026"})])
    review, _, _ = validate_bytes(session, training_package="BSB", file_name="bad.csv", payload=payload)
    assert review.refused
    assert any(item.kind == "unreadable_or_ambiguous_date" for item in review.discrepancies)


def test_mode_matrix_rows():
    assert mode_matrix(False, "F2FP")["theory_physical"] == 2
    assert mode_matrix(False, "F2FV")["theory_virtual"] == 2
    assert mode_matrix(True, "F2FV") is None
    assert mode_matrix(True, "F2FPV")["theory_virtual"] == 1


def test_mscris_five_hours_is_standard():
    assert is_standard_class_length(time(9, 0), time(14, 0), "MSCRIS")
    assert not is_standard_class_length(time(9, 0), time(17, 0), "MSCRIS")
    assert is_standard_class_length(time(9, 0), time(17, 0), "THEORY")


def test_import_two_physical_theory_days(session, refs, people):
    payload = csv_bytes([base_row(refs)])
    user = session.execute(select(User).where(User.organisation_email == EDITOR)).scalar_one()
    result = apply_rows(session, training_package="BSB", file_name="ok.csv", file_size_bytes=len(payload), payload=payload, apply_mode="REPLACE", user=user)
    session.commit()
    assert result["deliveries_written"] == 1
    assert result["sessions_written"] == 2
    days = session.execute(select(AllocationSession.weekday)).scalars().all()
    assert sorted(days) == ["THURSDAY", "WEDNESDAY"]
    assert all(row == "PHYSICAL" for row in session.execute(select(AllocationSession.delivery_mode)).scalars())
    again, _, _ = validate_bytes(session, training_package="BSB", file_name="ok.csv", payload=payload)
    assert again.existing_deliveries == 1


def test_rows_without_mode_of_delivery_are_ignored(session, refs):
    payload = csv_bytes(
        [
            base_row(refs),
            base_row(
                refs,
                **{
                    "Mode of Delivery": "",
                    "Qualification Name": "This is not an allocation row",
                    "Theory Class Days and Times": "Friday- 9 am to 5 pm",
                },
            ),
            base_row(
                refs,
                **{
                    "Mode of Delivery": "NA",
                    "Qualification Name": "Also not an allocation row",
                },
            ),
        ]
    )
    review, planned, _ = validate_bytes(session, training_package="BSB", file_name="s.csv", payload=payload)
    assert len(planned) == 1
    assert planned[0].mode_of_delivery == "F2FP"
    assert not any(item.row_number in {3, 4} for item in review.discrepancies)


def test_virtual_keywords_and_shared_classroom(session, refs, people):
    payload = csv_bytes(
        [
            base_row(
                refs,
                **{
                    "Mode of Delivery": "F2FPV",
                    "Theory Class Days and Times": "Monday- 9 am to 5 pm\nWednesday- 9 am to 5 pm",
                    "Theory Classroom Name": "Monday- Face to Face VC\nWednesday- Room 1",
                },
            )
        ]
    )
    user = session.execute(select(User).where(User.organisation_email == EDITOR)).scalar_one()
    apply_rows(session, training_package="BSB", file_name="mix.csv", file_size_bytes=10, payload=payload, apply_mode="REPLACE", user=user)
    session.commit()
    rows = session.execute(select(AllocationSession).order_by(AllocationSession.weekday)).scalars().all()
    monday = next(row for row in rows if row.weekday == "MONDAY")
    wednesday = next(row for row in rows if row.weekday == "WEDNESDAY")
    assert monday.delivery_mode == "VIRTUAL" and monday.facility_id is None and monday.virtual_kind == "FACE_TO_FACE_VC"
    assert wednesday.delivery_mode == "PHYSICAL" and wednesday.facility_id == refs["facility_id"]


def test_mscris_five_hour_session_is_not_a_length_warning(session, refs):
    payload = csv_bytes(
        [
            base_row(
                refs,
                **{
                    "MSCRIS Class Name": "Face to Face Virtual",
                    "MSCRIS Days and Times": "Saturday- 9 am to 2 pm",
                },
            )
        ]
    )
    review, planned, _ = validate_bytes(session, training_package="BSB", file_name="ok.csv", payload=payload)
    assert not any(item.kind == "not_eight_hours" for item in review.discrepancies)
    mscris = [item for item in planned[0].sessions if item.stream == "MSCRIS"]
    assert mscris
    assert mscris[0].start_time == time(9, 0)
    assert mscris[0].end_time == time(14, 0)


def test_na_optional_columns_raise_nothing(session, refs):
    payload = csv_bytes([base_row(refs)])
    review, planned, _ = validate_bytes(session, training_package="BSB", file_name="ok.csv", payload=payload)
    assert not review.refused
    assert review.existing_deliveries == 0
    assert all(item.stream != "PRACTICAL" for item in planned[0].sessions)


def test_unallocated_unit_is_not_a_mode_contradiction(session, refs):
    payload = csv_bytes(
        [
            base_row(
                refs,
                **{
                    "Mode of Delivery": "F2FPV",
                    "Theory Class Days and Times": "NA",
                    "Theory Classroom Name": "NA",
                    "Theory Trainer": "NA",
                },
            )
        ]
    )
    review, planned, _ = validate_bytes(session, training_package="BSB", file_name="s.csv", payload=payload)
    assert not any(item.kind == "mode_contradicts_classrooms" for item in review.discrepancies)
    assert planned
    assert planned[0].sessions == []
    with_days = csv_bytes(
        [
            base_row(
                refs,
                **{
                    "Mode of Delivery": "F2FPV",
                    "Theory Classroom Name": "NA",
                    "Theory Trainer": "NA",
                },
            )
        ]
    )
    review, planned, _ = validate_bytes(session, training_package="BSB", file_name="s.csv", payload=with_days)
    assert not any(item.kind == "mode_contradicts_classrooms" for item in review.discrepancies)
    assert planned


def test_mode_contradiction_edits_mode_and_classroom(session, refs):
    payload = csv_bytes(
        [
            base_row(
                refs,
                **{
                    "Mode of Delivery": "F2FPV",
                    "Theory Classroom Name": refs["facility_reference"],
                },
            )
        ]
    )
    review, _, _ = validate_bytes(session, training_package="BSB", file_name="s.csv", payload=payload)
    item = next(issue for issue in review.discrepancies if issue.kind == "mode_contradicts_classrooms")
    assert [field["column"] for field in item.edit_fields] == ["Mode of Delivery", "Theory Classroom Name"]
    assert item.edit_fields[0]["value"] == "F2FPV"
    assert item.edit_fields[1]["value"] == refs["facility_reference"]


def test_name_mismatch_edits_id_and_name(session, refs):
    payload = csv_bytes([base_row(refs, **{"Qualification Name": "Advance Diploma of Leadership and management"})])
    review, _, _ = validate_bytes(session, training_package="BSB", file_name="s.csv", payload=payload)
    item = next(issue for issue in review.discrepancies if issue.kind == "name_disagrees_with_id")
    assert [field["column"] for field in item.edit_fields] == ["Qualification Id", "Qualification Name"]
    assert item.edit_fields[0]["value"] == "BSB50420"
    assert item.edit_fields[1]["value"] == "Advance Diploma of Leadership and management"


def test_unit_title_mismatch_edits_id_and_title(session, refs):
    payload = csv_bytes([base_row(refs, **{"Units of Competency Title": "Wrong title"})])
    review, _, _ = validate_bytes(session, training_package="BSB", file_name="s.csv", payload=payload)
    item = next(issue for issue in review.discrepancies if "Unit title disagrees" in issue.message)
    assert [field["column"] for field in item.edit_fields] == [
        "Units of Competency ID",
        "Units of Competency Title",
    ]


def test_unapproved_room_raises_one_suggestion(session, refs, people):
    payload = csv_bytes([base_row(refs, **{"Theory Classroom Name": "Unknown Room"})])
    review, _, _ = validate_bytes(session, training_package="BSB", file_name="s.csv", payload=payload)
    rooms = [
        item
        for item in review.discrepancies
        if item.kind == "unresolved_reference" and item.column == "Theory Classroom Name"
    ]
    assert len(rooms) == 1
    user = session.execute(select(User).where(User.organisation_email == EDITOR)).scalar_one()
    apply_rows(session, training_package="BSB", file_name="s.csv", file_size_bytes=10, payload=payload, apply_mode="REPLACE", user=user)
    session.commit()
    suggestions = session.execute(select(ReferenceSuggestion)).scalars().all()
    assert len(suggestions) == 1
    assert suggestions[0].entity_type == "FACILITY"
    assert suggestions[0].occurrence_count == 2
    assert session.execute(select(AllocationSession.facility_id)).scalars().all() == [None, None]


def test_viewer_cannot_import(client, refs):
    payload = csv_bytes([base_row(refs)])
    response = client.post(
        "/allocation/import/validate",
        headers=as_user(VIEWER),
        data={"training_package": "BSB"},
        files={"file": ("ok.csv", payload, "text/csv")},
    )
    assert response.status_code == 403


def test_only_bsb_enabled(client):
    packages = client.get("/allocation/packages", headers=as_user(EDITOR)).json()
    enabled = [item["training_package"] for item in packages if item["enabled"]]
    assert enabled == ["BSB"]
    assert len(packages) == 11


def test_replace_and_activity(session, refs, people):
    payload = csv_bytes([base_row(refs)])
    user = session.execute(select(User).where(User.organisation_email == EDITOR)).scalar_one()
    apply_rows(session, training_package="BSB", file_name="one.csv", file_size_bytes=10, payload=payload, apply_mode="REPLACE", user=user)
    apply_rows(session, training_package="BSB", file_name="one.csv", file_size_bytes=10, payload=payload, apply_mode="REPLACE", user=user)
    session.commit()
    assert session.execute(select(AllocationDelivery)).scalars().all().__len__() == 1
    assert "IMPORT" in session.execute(select(UserActivityRecord.action)).scalars().all()


def test_fault_in_middle_writes_nothing(session, refs, people):
    good = base_row(refs)
    bad = base_row(refs, **{"Theory Class Days and Times": "nope"})
    payload = csv_bytes([good, bad])
    user = session.execute(select(User).where(User.organisation_email == EDITOR)).scalar_one()
    with pytest.raises(Exception):
        apply_rows(session, training_package="BSB", file_name="mid.csv", file_size_bytes=10, payload=payload, apply_mode="REPLACE", user=user)
    session.rollback()
    assert session.execute(select(AllocationDelivery)).scalars().all() == []


def test_edit_one_day_leaves_the_other(session, refs, people):
    payload = csv_bytes([base_row(refs)])
    user = session.execute(select(User).where(User.organisation_email == EDITOR)).scalar_one()
    apply_rows(session, training_package="BSB", file_name="ok.csv", file_size_bytes=10, payload=payload, apply_mode="REPLACE", user=user)
    session.commit()
    thursday = session.execute(select(AllocationSession).where(AllocationSession.weekday == "THURSDAY")).scalar_one()
    wednesday = session.execute(select(AllocationSession).where(AllocationSession.weekday == "WEDNESDAY")).scalar_one()
    update_session(
        session,
        user,
        session_id=thursday.id,
        training_package="BSB",
        weekday="THURSDAY",
        start_time=thursday.start_time,
        end_time=thursday.end_time,
        classroom="Unknown Room",
        trainer=refs["trainer_name"],
    )
    session.commit()
    thursday = session.execute(select(AllocationSession).where(AllocationSession.weekday == "THURSDAY")).scalar_one()
    wednesday = session.execute(select(AllocationSession).where(AllocationSession.weekday == "WEDNESDAY")).scalar_one()
    assert thursday.facility_id is None
    assert wednesday.facility_id == refs["facility_id"]
    assert "UPDATE" in session.execute(select(UserActivityRecord.action)).scalars().all()


def test_calendar_query_cost_is_two(session, refs, people):
    payload = csv_bytes([base_row(refs)])
    user = session.execute(select(User).where(User.organisation_email == EDITOR)).scalar_one()
    apply_rows(session, training_package="BSB", file_name="ok.csv", file_size_bytes=10, payload=payload, apply_mode="REPLACE", user=user)
    session.commit()
    queries = []

    def before(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            queries.append(statement)

    event.listen(session.bind, "before_cursor_execute", before)
    try:
        grid = calendar_month(session, training_package="BSB", start_date=MONDAY, end_date=MONDAY + timedelta(days=27))
    finally:
        event.remove(session.bind, "before_cursor_execute", before)
    assert grid["query_cost"] == CALENDAR_QUERY_COUNT
    assert len(queries) == 2
    wednesday = next(day for day in grid["days"] if day["weekday"] == "WEDNESDAY")
    assert wednesday["sessions"]


def test_bsb_partition_only(session, refs, people):
    payload = csv_bytes([base_row(refs)])
    user = session.execute(select(User).where(User.organisation_email == EDITOR)).scalar_one()
    apply_rows(session, training_package="BSB", file_name="ok.csv", file_size_bytes=10, payload=payload, apply_mode="REPLACE", user=user)
    session.commit()
    bsb = session.execute(text("SELECT count(*) FROM allocation_delivery_bsb")).scalar_one()
    chc = session.execute(text("SELECT count(*) FROM allocation_delivery_chc")).scalar_one()
    assert bsb == 1
    assert chc == 0


def test_toggle_off_refuses_unapproved_classroom(session, refs, people):
    payload = csv_bytes([base_row(refs, **{"Theory Classroom Name": "Unknown Room"})])
    review, _, _ = validate_bytes(
        session, training_package="BSB", file_name="s.csv", payload=payload, raise_suggestions=False
    )
    assert review.refused
    assert any(item.kind == "unresolved_reference" and item.severity == "refuse" for item in review.discrepancies)


def test_mscris_class_size_column_is_not_a_schema_error(session, refs):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([*ALLOCATION_COLUMNS, "MSCRIS Class size"])
    writer.writerow([*base_row(refs), "NA"])
    payload = buffer.getvalue().encode("utf-8")
    review, planned, _ = validate_bytes(session, training_package="BSB", file_name="ok.csv", payload=payload)
    assert not review.refused
    assert planned


def test_unknown_header_can_be_excepted(session, refs):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([*ALLOCATION_COLUMNS, "Not A Real Column"])
    writer.writerow([*base_row(refs), "x"])
    payload = buffer.getvalue().encode("utf-8")
    review, _, _ = validate_bytes(session, training_package="BSB", file_name="s.csv", payload=payload)
    assert review.refused
    extra = next(item for item in review.discrepancies if item.kind == "missing_or_unknown_header")
    overrides = ImportOverrides.from_payload({"except_ids": [issue_id(extra)]}, True)
    accepted, planned, _ = validate_bytes(
        session, training_package="BSB", file_name="s.csv", payload=payload, overrides=overrides
    )
    assert not accepted.refused
    assert planned


def test_unresolved_can_be_excepted_or_raised_when_toggle_off(session, refs, people):
    payload = csv_bytes([base_row(refs, **{"Theory Classroom Name": "Unknown Room"})])
    review, _, _ = validate_bytes(
        session, training_package="BSB", file_name="s.csv", payload=payload, raise_suggestions=False
    )
    item = next(issue for issue in review.discrepancies if issue.kind == "unresolved_reference")
    excepted, planned, suggestions = validate_bytes(
        session,
        training_package="BSB",
        file_name="s.csv",
        payload=payload,
        raise_suggestions=False,
        overrides=ImportOverrides.from_payload({"except_ids": [issue_id(item)]}, False),
    )
    assert not excepted.refused
    assert planned
    # Updated 26 August 2026 (section 2.9): an accepted exception is now
    # collected during validation and written at apply time, so it appears here
    # tagged EXCEPT. What it must never be is a *pending suggestion* — which is
    # what the original assertion was really protecting.
    assert all(item["kind"] == "EXCEPT" for item in suggestions.values())
    assert excepted.suggestions_that_would_be_raised == 0
    raised, planned_raised, suggestions_raised = validate_bytes(
        session,
        training_package="BSB",
        file_name="s.csv",
        payload=payload,
        raise_suggestions=False,
        overrides=ImportOverrides.from_payload({"raise_ids": [issue_id(item)]}, False),
    )
    assert not raised.refused
    assert planned_raised
    assert suggestions_raised


def test_cell_correction_clears_unresolved_classroom(session, refs, people):
    payload = csv_bytes([base_row(refs, **{"Theory Classroom Name": "Unknown Room"})])
    review, planned, _ = validate_bytes(
        session,
        training_package="BSB",
        file_name="s.csv",
        payload=payload,
        raise_suggestions=False,
        overrides=ImportOverrides.from_payload(
            {
                "corrections": [
                    {
                        "row_number": 2,
                        "column": "Theory Classroom Name",
                        "value": refs["facility_reference"],
                    }
                ]
            },
            False,
        ),
    )
    assert not review.refused
    assert planned
    assert not any(item.kind == "unresolved_reference" for item in review.discrepancies)


def test_empty_calendar(session):
    grid = calendar_month(session, training_package="BSB", start_date=MONDAY, end_date=MONDAY + timedelta(days=6))
    assert grid["empty"] is True
    assert grid["days"]
