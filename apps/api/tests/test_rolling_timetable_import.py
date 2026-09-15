"""Rolling timetable — flat import, Visualizer, and package constraint."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, insert, select, text
from sqlalchemy.exc import IntegrityError

from app.api import deps
from app.auth.mock import mock_claims_for
from app.core.config import Settings, get_settings
from app.main import app
from app.models.activity import UserActivityRecord
from app.models.qualification import Qualification
from app.models.timetable import RollingTimetableWeek
from app.models.user import User
from app.services.rolling_timetable_import import (
    FLAT_COLUMNS,
    KIND_PACKAGE_MISMATCH,
    apply_rows,
    export_flat,
    validate_bytes,
)
from app.services.rolling_timetable_store import list_scopes, visualizer_grid

pytestmark = pytest.mark.database

VIEWER = "rt.viewer@chelsongordon.com"
EDITOR = "rt.editor@chelsongordon.com"
MONDAY = date(2026, 1, 19)


def week_dates(week_no: int) -> tuple[str, str]:
    start = MONDAY + timedelta(weeks=week_no - 1)
    return start.isoformat(), (start + timedelta(days=6)).isoformat()


def row(
    qualification: str,
    week_no: int,
    schedule_type: str,
    schedule_value: str,
    unit_code: str = "",
    unit_count: int = 0,
    duration: int = 52,
    intake_date: str = "19 Jan 2026",
) -> list:
    start, end = week_dates(week_no)
    intake = f"{qualification}_{duration}_{intake_date}_NA_Intake"
    return [
        qualification,
        duration,
        intake,
        "NA",
        "2026-01-19",
        week_no,
        start,
        end,
        schedule_type,
        schedule_value,
        unit_code,
        unit_count,
        1 if schedule_type == "UNIT" else "",
    ]


def csv_bytes(rows: list[list]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FLAT_COLUMNS)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


@pytest.fixture()
def people(session):
    session.execute(text("TRUNCATE TABLE user_activity_records, users, rolling_timetable_weeks RESTART IDENTITY CASCADE"))
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


#: Every qualification code these tests put in a rolling timetable file.
#:
#: A rolling timetable naming a qualification College and Course Reference Data
#: does not hold is refused (KIND_UNKNOWN_QUALIFICATION), so the fixtures have to
#: supply what the files reference. `CHC30121` is deliberately included even
#: though it is superseded in the real data - one test uses it to check package
#: routing, and that test is about the package, not the supersession.
ROLLING_TEST_QUALIFICATIONS = (
    "BSB50120",
    "BSB50420",
    "BSB80120",
    "CHC30121",
    "FNS40222",
    "FNS60222",
)


@pytest.fixture(autouse=True)
def clear_rolling(session):
    session.rollback()
    session.execute(text("TRUNCATE TABLE rolling_timetable_weeks RESTART IDENTITY CASCADE"))

    # Get-or-create, never delete: `qualifications` is shared with every other
    # test module and is not in the truncate set, so removing a row here would
    # break whichever test happens to run next.
    for code in ROLLING_TEST_QUALIFICATIONS:
        exists = session.execute(
            select(Qualification).where(Qualification.qualification_code == code)
        ).scalars().first()
        if exists is None:
            session.add(
                Qualification(
                    qualification_code=code,
                    qualification_title=f"{code} (rolling timetable test fixture)",
                    is_active=True,
                )
            )
    session.commit()


def test_mixed_file_offers_proceed_and_writes_only_matching(session):
    payload = csv_bytes(
        [
            row("BSB50420", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1),
            row("FNS40222", 1, "UNIT", "FNSACC311", "FNSACC311", 1),
        ]
    )
    review, matching = validate_bytes(session, training_package="BSB", file_name="mixed.csv", payload=payload)
    assert review.status == "mixed"
    assert review.can_proceed_with_package
    assert [item.qualification_code for item in review.non_matching_qualifications] == ["FNS40222"]
    assert any(item.kind == KIND_PACKAGE_MISMATCH for item in review.discrepancies)
    assert [item.qualification_code for item in matching] == ["BSB50420"]

    result = apply_rows(
        session,
        training_package="BSB",
        file_name="mixed.csv",
        payload=payload,
        proceed_with_matching=True,
        user=None,
    )
    session.commit()
    assert result.rows_written == 1
    stored = session.execute(select(RollingTimetableWeek.qualification_code)).scalars().all()
    assert stored == ["BSB50420"]


def test_discard_is_not_apply(session):
    payload = csv_bytes([row("BSB50420", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1)])
    review, _ = validate_bytes(session, training_package="BSB", file_name="ok.csv", payload=payload)
    assert review.status == "accepted"
    assert session.execute(select(RollingTimetableWeek)).scalars().all() == []


def test_clustered_unit_is_one_row(session):
    payload = csv_bytes(
        [row("FNS60222", 1, "UNIT", "FNSACC522/FNSACC526", "FNSACC522/FNSACC526", 2)]
    )
    apply_rows(
        session,
        training_package="FNS",
        file_name="cluster.csv",
        payload=payload,
        proceed_with_matching=False,
        user=None,
    )
    session.commit()
    stored = session.execute(select(RollingTimetableWeek)).scalar_one()
    assert stored.unit_code == "FNSACC522/FNSACC526"
    assert stored.unit_count == 2
    assert stored.unit_slot == 1
    grid = visualizer_grid(session, "FNS", "FNS60222", 52)
    assert grid["intake_columns"][0]["heading"].startswith("FNS60222")
    assert grid["grid"][0] == ["FNSACC522/FNSACC526"]


def test_two_units_in_one_week_use_slots(session):
    payload = csv_bytes(
        [
            row("BSB50420", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1),
            row("BSB50420", 1, "UNIT", "BSBOPS501", "BSBOPS501", 1),
        ]
    )
    apply_rows(
        session,
        training_package="BSB",
        file_name="slots.csv",
        payload=payload,
        proceed_with_matching=False,
        user=None,
    )
    session.commit()
    slots = session.execute(select(RollingTimetableWeek.unit_slot, RollingTimetableWeek.unit_code)).all()
    assert sorted(slots) == [(1, "BSBCRT511"), (2, "BSBOPS501")]
    grid = visualizer_grid(session, "BSB", "BSB50420", 52)
    assert len(grid["intake_columns"]) == 2
    assert grid["grid"][0] == ["BSBCRT511", "BSBOPS501"]


def test_na_is_not_stored_and_visualizer_cell_is_blank(session):
    payload = csv_bytes(
        [
            row("BSB50420", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1),
            row("BSB50420", 3, "BREAK", "Break", "", 0),
        ]
    )
    apply_rows(
        session,
        training_package="BSB",
        file_name="gap.csv",
        payload=payload,
        proceed_with_matching=False,
        user=None,
    )
    session.commit()
    assert session.execute(select(RollingTimetableWeek)).scalars().all().__len__() == 2
    grid = visualizer_grid(session, "BSB", "BSB50420", 52)
    assert [week["week_no"] for week in grid["weeks"]] == [1, 2, 3]
    assert grid["grid"][1] == [""]


def test_database_refuses_mismatched_package(session):
    with pytest.raises(IntegrityError):
        session.execute(
            insert(RollingTimetableWeek),
            [
                {
                    "training_package": "BSB",
                    "qualification_code": "FNS40222",
                    "duration_weeks": 52,
                    "intake_label": "FNS40222_52_19 Jan 2026_NA_Intake",
                    "intake_group": "NA",
                    "intake_start_date": MONDAY,
                    "week_no": 1,
                    "week_start_date": MONDAY,
                    "week_end_date": MONDAY + timedelta(days=6),
                    "schedule_type": "UNIT",
                    "schedule_value": "FNSACC311",
                    "unit_code": "FNSACC311",
                    "unit_count": 1,
                    "unit_slot": 1,
                }
            ],
        )


def test_visualizer_issues_one_select(session):
    payload = csv_bytes([row("BSB50420", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1)])
    apply_rows(
        session,
        training_package="BSB",
        file_name="one.csv",
        payload=payload,
        proceed_with_matching=False,
        user=None,
    )
    session.commit()

    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    event.listen(session.bind, "before_cursor_execute", before_cursor_execute)
    try:
        visualizer_grid(session, "BSB", "BSB50420", 52)
    finally:
        event.remove(session.bind, "before_cursor_execute", before_cursor_execute)

    selects = [item for item in statements if "rolling_timetable_weeks" in item.lower() and item.lstrip().lower().startswith("select")]
    assert len(selects) == 1, statements


def test_scopes_default_order_is_enum_then_code(session):
    payload = csv_bytes(
        [
            row("BSB50420", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1),
            row("CHC30121", 1, "UNIT", "CHCDIV001", "CHCDIV001", 1),
        ]
    )
    apply_rows(session, training_package="BSB", file_name="b.csv", payload=payload, proceed_with_matching=True, user=None)
    apply_rows(session, training_package="CHC", file_name="c.csv", payload=payload, proceed_with_matching=True, user=None)
    session.commit()
    scopes = list_scopes(session)
    assert scopes[0]["training_package"] == "CHC"
    assert scopes[0]["qualification_code"] == "CHC30121"


def test_round_trip_values(session):
    payload = csv_bytes(
        [
            row("BSB50420", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1),
            row("BSB50420", 2, "BREAK", "Break", "", 0),
            row("BSB50420", 3, "ASSESSMENT_WEEK", "Assessment Week", "", 0),
        ]
    )
    apply_rows(session, training_package="BSB", file_name="rt.csv", payload=payload, proceed_with_matching=False, user=None)
    session.commit()
    headers, body = export_flat(session.execute(select(RollingTimetableWeek)).scalars().all())
    assert headers == list(FLAT_COLUMNS)
    exported = {tuple(item) for item in body}
    original = {tuple(str(cell) for cell in line) for line in csv.reader(io.StringIO(payload.decode()))}
    original.remove(tuple(FLAT_COLUMNS))
    assert exported == original


def test_structural_fault_writes_nothing(session):
    good = csv_bytes([row("BSB50420", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1)])
    apply_rows(session, training_package="BSB", file_name="good.csv", payload=good, proceed_with_matching=False, user=None)
    session.commit()
    before = session.execute(select(RollingTimetableWeek)).scalars().all()
    assert len(before) == 1
    broken = csv_bytes(
        [
            row("BSB50420", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1),
            row("BSB50420", 2, "NOPE", "x", "x", 1),
        ]
    )
    review, _ = validate_bytes(session, training_package="BSB", file_name="bad.csv", payload=broken)
    assert review.refused
    with pytest.raises(Exception):
        apply_rows(
            session,
            training_package="BSB",
            file_name="bad.csv",
            payload=broken,
            proceed_with_matching=False,
            user=None,
        )
    session.rollback()
    after = session.execute(select(RollingTimetableWeek)).scalars().all()
    assert len(after) == 1


def test_scoped_replace_leaves_other_qualification(session):
    first = csv_bytes(
        [
            row("BSB50420", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1),
            row("BSB50120", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1),
        ]
    )
    apply_rows(session, training_package="BSB", file_name="both.csv", payload=first, proceed_with_matching=False, user=None)
    session.commit()
    second = csv_bytes([row("BSB50420", 1, "UNIT", "BSBOPS501", "BSBOPS501", 1)])
    apply_rows(session, training_package="BSB", file_name="one.csv", payload=second, proceed_with_matching=False, user=None)
    session.commit()
    values = dict(session.execute(select(RollingTimetableWeek.qualification_code, RollingTimetableWeek.schedule_value)).all())
    assert values["BSB50420"] == "BSBOPS501"
    assert values["BSB50120"] == "BSBCRT511"


def test_tae_unit_in_bsb_is_not_a_package_mismatch(session):
    payload = csv_bytes([row("BSB80120", 1, "UNIT", "TAELED803", "TAELED803", 1)])
    review, _ = validate_bytes(session, training_package="BSB", file_name="tae.csv", payload=payload)
    assert review.status == "accepted"
    assert not any(item.kind == KIND_PACKAGE_MISMATCH for item in review.discrepancies)


def test_viewer_cannot_import(client):
    payload = csv_bytes([row("BSB50420", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1)])
    response = client.post(
        "/rolling-timetable/import/validate",
        headers=as_user(VIEWER),
        data={"training_package": "BSB"},
        files={"file": ("ok.csv", payload, "text/csv")},
    )
    assert response.status_code == 403


def test_editor_can_validate_and_activity_is_written_on_apply(client, session):
    payload = csv_bytes([row("BSB50420", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1)])
    review = client.post(
        "/rolling-timetable/import/validate",
        headers=as_user(EDITOR),
        data={"training_package": "BSB"},
        files={"file": ("ok.csv", payload, "text/csv")},
    )
    assert review.status_code == 200, review.text
    applied = client.post(
        "/rolling-timetable/import/apply",
        headers=as_user(EDITOR),
        data={"training_package": "BSB", "proceed_with_matching": "false"},
        files={"file": ("ok.csv", payload, "text/csv")},
    )
    assert applied.status_code == 200, applied.text
    actions = session.execute(select(UserActivityRecord.action)).scalars().all()
    assert "IMPORT" in actions


def test_weeks_are_paginated(client, session):
    payload = csv_bytes([row("BSB50420", week, "UNIT", "BSBCRT511", "BSBCRT511", 1) for week in range(1, 6)])
    apply_rows(session, training_package="BSB", file_name="p.csv", payload=payload, proceed_with_matching=False, user=None)
    session.commit()
    response = client.get(
        "/rolling-timetable/weeks?training_package=BSB&qualification_code=BSB50420&duration_weeks=52&limit=2",
        headers=as_user(EDITOR),
    )
    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


def test_editor_can_update_intake_stack_and_viewer_cannot(client, session):
    payload = csv_bytes(
        [
            row("BSB50420", 1, "UNIT", "BSBCRT511", "BSBCRT511", 1),
            row("BSB50420", 2, "UNIT", "BSBCRT511/BSBCRT412", "BSBCRT511/BSBCRT412", 1),
        ]
    )
    apply_rows(session, training_package="BSB", file_name="stack.csv", payload=payload, proceed_with_matching=False, user=None)
    session.commit()
    weeks = client.get(
        "/rolling-timetable/weeks?training_package=BSB&qualification_code=BSB50420&duration_weeks=52&limit=20",
        headers=as_user(EDITOR),
    ).json()["items"]
    first, second = weeks[0], weeks[1]

    refused = client.patch(
        "/rolling-timetable/weeks",
        headers=as_user(VIEWER),
        json={"items": [{"id": first["id"], "schedule_type": "BREAK", "schedule_value": "BREAK"}]},
    )
    assert refused.status_code == 403

    na = client.patch(
        "/rolling-timetable/weeks",
        headers=as_user(EDITOR),
        json={"items": [{"id": first["id"], "schedule_type": "UNIT", "schedule_value": "NA"}]},
    )
    assert na.status_code == 400

    updated = client.patch(
        "/rolling-timetable/weeks",
        headers=as_user(EDITOR),
        json={
            "items": [
                {"id": first["id"], "schedule_type": "BREAK", "schedule_value": "BREAK"},
                {"id": second["id"], "schedule_type": "UNIT", "schedule_value": "BSBCRT511/BSBCRT412"},
            ]
        },
    )
    assert updated.status_code == 200, updated.text
    body = {item["id"]: item for item in updated.json()["items"]}
    assert body[first["id"]]["schedule_type"] == "BREAK"
    assert body[first["id"]]["unit_code"] is None
    assert body[second["id"]]["schedule_value"] == "BSBCRT511/BSBCRT412"
    assert body[second["id"]]["unit_code"] == "BSBCRT511/BSBCRT412"
    actions = session.execute(select(UserActivityRecord.action)).scalars().all()
    assert "UPDATE" in actions


def test_missing_header_refuses(session):
    payload = b"qualification_code\nBSB50420\n"
    review, _ = validate_bytes(session, training_package="BSB", file_name="bad.csv", payload=payload)
    assert review.refused
