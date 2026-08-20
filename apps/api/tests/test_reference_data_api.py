"""College and Course Reference Data — the real API (Step 6).

Two things are under test:

* **Authorisation.** Reading is Viewer and above; maintaining is **Admin and
  above**. A Data Editor maintains Student Data and Timetables and is
  read-and-download only here, so its write attempts must be refused by the
  server — not merely hidden in the interface. Every write verb is exercised
  directly.
* **Business integrity.** The approved constraints, checked through the API so
  the user-facing message is verified alongside the rule.

Fixture records are obviously artificial (`TEST…`) and live in the temporary
`tdms_test` database, which the harness drops. Nothing here touches `tdms_dev`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api import deps
from app.auth.mock import mock_claims_for
from app.core.config import Settings, get_settings
from app.main import app
from app.models.user import User

pytestmark = pytest.mark.database

VIEWER = "ref.viewer@chelsongordon.com"
EDITOR = "ref.editor@chelsongordon.com"
ADMIN = "ref.admin@chelsongordon.com"
SUPER = "a.chattopadhyay@chelsongordon.com"

LEVELS = {VIEWER: "VIEWER", EDITOR: "DATA_EDITOR", ADMIN: "ADMIN", SUPER: "SUPER_ADMIN"}


@pytest.fixture()
def client(test_factory, test_engine, session):
    """A TestClient on the temporary database, using development authentication.

    Settings are pinned rather than inherited: the developer's `.env` now selects
    real Entra mode, and these tests exercise the authorisation layer, which is
    identical either way.
    """

    def _get_db():
        db = test_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = _get_db
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="development", auth_mode="mock"
    )
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def people(session):
    """One account per access level."""
    session.execute(
        text(
            # `reason_codes` too: its `code` is unique, so a fixture that
            # re-creates the same test reason would collide on the second test.
            "TRUNCATE TABLE offering_duration_options, course_offerings, course_statuses, "
            "qualification_units, units, qualifications, college_campuses, campuses, colleges, "
            "reason_codes RESTART IDENTITY CASCADE"
        )
    )
    for email, level in LEVELS.items():
        claims = mock_claims_for(email)
        session.add(
            User(
                organisation_email=email,
                display_name=f"Test {email}",
                access_level=level,
                account_status="ACTIVE",
                entra_object_id=claims.object_id,
                entra_tenant_id=claims.tenant_id,
            )
        )
    session.commit()


def as_user(email: str) -> dict[str, str]:
    return {deps.MOCK_USER_HEADER: email}


@pytest.fixture()
def seed(client, people):
    """Minimal artificial reference data, created through the real API."""
    college = client.post(
        "/reference/colleges",
        json={"college_short_name": "TSTC", "college_full_name": "Test College A"},
        headers=as_user(ADMIN),
    ).json()
    campus = client.post(
        "/reference/campuses",
        json={
            "campus_code": "TSTCAM",
            "campus_name": "Test Campus",
            "campus_location": "Test Location",
            "state": "VIC",
        },
        headers=as_user(ADMIN),
    ).json()
    client.post(
        "/reference/college-campuses",
        json={"college_id": college["id"], "campus_id": campus["id"]},
        headers=as_user(ADMIN),
    )
    qualification = client.post(
        "/reference/qualifications",
        json={"qualification_code": "TESTQUAL001", "qualification_title": "Test Qualification"},
        headers=as_user(ADMIN),
    ).json()
    unit = client.post(
        "/reference/units",
        json={"unit_code": "TESTUNIT001", "unit_title": "Test Unit One"},
        headers=as_user(ADMIN),
    ).json()

    # A course status and an approved deletion reason. Neither is exposed as a
    # maintenance endpoint in this step, and DATA-04 makes a reason mandatory for
    # any soft delete, so both are created directly as test fixtures.
    from app.models.course import CourseStatus
    from app.models.reason import ReasonCode

    db = next(client.app.dependency_overrides[deps.get_db]())
    status_row = CourseStatus(code="ACTIVE", label="Active", selectable_for_new_records=True)
    reason_row = ReasonCode(code="TEST_REASON", label="Test reason", requires_detail=False)
    db.add_all([status_row, reason_row])
    db.commit()
    status_id, reason_id = status_row.id, reason_row.id
    db.close()

    return {
        "college": college,
        "campus": campus,
        "qualification": qualification,
        "unit": unit,
        "status_id": status_id,
        "reason_id": reason_id,
    }


# ===========================================================================
# Authorisation — the server, not the interface, decides
# ===========================================================================


READ_ENDPOINTS = [
    "/reference/colleges",
    "/reference/campuses",
    "/reference/college-campuses",
    "/reference/qualifications",
    "/reference/units",
    "/reference/qualification-units",
    "/reference/courses",
    "/reference/course-statuses",
]


class TestViewer:
    @pytest.mark.parametrize("path", READ_ENDPOINTS)
    def test_may_read_every_reference_list(self, client, people, path):
        assert client.get(path, headers=as_user(VIEWER)).status_code == 200

    def test_may_not_create(self, client, people):
        for path, body in (
            ("/reference/colleges", {"college_short_name": "X", "college_full_name": "X"}),
            (
                "/reference/campuses",
                {"campus_code": "X", "campus_name": "X", "campus_location": "X", "state": "VIC"},
            ),
            ("/reference/qualifications", {"qualification_code": "X", "qualification_title": "X"}),
            ("/reference/units", {"unit_code": "X", "unit_title": "X"}),
        ):
            assert client.post(path, json=body, headers=as_user(VIEWER)).status_code == 403, path

    def test_may_not_edit_or_delete(self, client, seed):
        assert (
            client.patch(
                f"/reference/colleges/{seed['college']['id']}",
                json={"college_full_name": "Renamed"},
                headers=as_user(VIEWER),
            ).status_code
            == 403
        )
        assert (
            client.request(
                "DELETE", "/reference/courses/1", json={}, headers=as_user(VIEWER)
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/reference/courses/1/restore", json={}, headers=as_user(VIEWER)
            ).status_code
            == 403
        )


class TestDataEditor:
    """A Data Editor maintains Student Data and Timetables — not reference data."""

    @pytest.mark.parametrize("path", READ_ENDPOINTS)
    def test_may_read(self, client, people, path):
        assert client.get(path, headers=as_user(EDITOR)).status_code == 200

    def test_may_not_create_any_reference_record(self, client, people):
        for path, body in (
            ("/reference/colleges", {"college_short_name": "X", "college_full_name": "X"}),
            (
                "/reference/campuses",
                {"campus_code": "X", "campus_name": "X", "campus_location": "X", "state": "VIC"},
            ),
            ("/reference/qualifications", {"qualification_code": "X", "qualification_title": "X"}),
            ("/reference/units", {"unit_code": "X", "unit_title": "X"}),
            ("/reference/college-campuses", {"college_id": 1, "campus_id": 1}),
            (
                "/reference/qualification-units",
                {"qualification_id": 1, "unit_id": 1, "delivery_order": 1},
            ),
        ):
            assert client.post(path, json=body, headers=as_user(EDITOR)).status_code == 403, path

    def test_may_not_edit_delete_or_restore(self, client, seed):
        assert (
            client.patch(
                f"/reference/units/{seed['unit']['id']}",
                json={"unit_title": "Changed"},
                headers=as_user(EDITOR),
            ).status_code
            == 403
        )
        assert (
            client.request(
                "DELETE", "/reference/qualification-units/1", json={}, headers=as_user(EDITOR)
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/reference/qualification-units/1/restore", json={}, headers=as_user(EDITOR)
            ).status_code
            == 403
        )

    def test_the_refusal_names_the_level_required(self, client, people):
        response = client.post(
            "/reference/colleges",
            json={"college_short_name": "X", "college_full_name": "X"},
            headers=as_user(EDITOR),
        )
        assert "Admin" in response.json()["detail"]


class TestAdmin:
    def test_may_create_edit_and_read(self, client, people):
        created = client.post(
            "/reference/colleges",
            json={"college_short_name": "ADM", "college_full_name": "Admin College"},
            headers=as_user(ADMIN),
        )
        assert created.status_code == 201

        updated = client.patch(
            f"/reference/colleges/{created.json()['id']}",
            json={"college_full_name": "Admin College Renamed"},
            headers=as_user(ADMIN),
        )
        assert updated.status_code == 200
        assert updated.json()["college_full_name"] == "Admin College Renamed"

    def test_may_not_reach_super_admin_governance(self, client, people):
        """Maintaining reference data is not administration access."""
        for path in ("/admin/overview", "/admin/users", "/admin/access-requests"):
            assert client.get(path, headers=as_user(ADMIN)).status_code == 403, path


class TestSuperAdmin:
    def test_may_maintain_reference_data(self, client, people):
        response = client.post(
            "/reference/units",
            json={"unit_code": "TESTUNIT900", "unit_title": "Super Admin Unit"},
            headers=as_user(SUPER),
        )
        assert response.status_code == 201

    def test_retains_administration_access(self, client, people):
        for path in ("/admin/overview", "/admin/users", "/admin/access-requests"):
            assert client.get(path, headers=as_user(SUPER)).status_code == 200, path


def test_unauthenticated_requests_are_refused(client):
    assert client.get("/reference/colleges").status_code == 401
    assert client.post("/reference/colleges", json={}).status_code == 401


# ===========================================================================
# Business integrity
# ===========================================================================


class TestBusinessRules:
    def test_duplicate_college_short_name_is_refused(self, client, seed):
        response = client.post(
            "/reference/colleges",
            json={"college_short_name": "tstc", "college_full_name": "Another"},
            headers=as_user(ADMIN),
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_duplicate_campus_code_is_refused(self, client, seed):
        response = client.post(
            "/reference/campuses",
            json={
                "campus_code": "TSTCAM",
                "campus_name": "Other",
                "campus_location": "Other",
                "state": "NSW",
            },
            headers=as_user(ADMIN),
        )
        assert response.status_code == 409

    def test_duplicate_qualification_code_is_refused(self, client, seed):
        response = client.post(
            "/reference/qualifications",
            json={"qualification_code": "TESTQUAL001", "qualification_title": "Duplicate"},
            headers=as_user(ADMIN),
        )
        assert response.status_code == 409
        assert "TESTQUAL001" in response.json()["detail"]

    def test_qualification_code_is_optional_and_shows_as_na(self, client, seed):
        """ELICOS courses have no VET Code (approved 11 August 2026).

        Absent, blank and "NA" all mean the same thing and must land as one
        representation, or the same course arrives four ways from four
        spreadsheets.
        """
        for supplied in (None, "", "NA", "n/a"):
            payload = {"qualification_title": f"General English {supplied!r}"}
            if supplied is not None:
                payload["qualification_code"] = supplied

            response = client.post(
                "/reference/qualifications", json=payload, headers=as_user(ADMIN)
            )
            assert response.status_code == 201, response.text
            # The API reports the absence honestly; the interface renders "NA".
            assert response.json()["qualification_code"] is None

    def test_code_less_qualifications_do_not_collide(self, client, seed):
        """Several ELICOS qualifications coexist without codes..."""
        first = client.post(
            "/reference/qualifications",
            json={"qualification_title": "General English"},
            headers=as_user(ADMIN),
        )
        second = client.post(
            "/reference/qualifications",
            json={"qualification_code": "NA", "qualification_title": "IELTS Preparation"},
            headers=as_user(ADMIN),
        )
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] != second.json()["id"]

        # ...but two qualifications still cannot share a real code.
        clash = client.post(
            "/reference/qualifications",
            json={"qualification_code": "TESTQUAL001", "qualification_title": "Clash"},
            headers=as_user(ADMIN),
        )
        assert clash.status_code == 409

    def test_missing_qualification_code_can_be_supplied_later(self, client, seed):
        """"Editable where required" — the field is not frozen at creation."""
        created = client.post(
            "/reference/qualifications",
            json={"qualification_code": "NA", "qualification_title": "General English"},
            headers=as_user(ADMIN),
        ).json()
        assert created["qualification_code"] is None

        updated = client.patch(
            f"/reference/qualifications/{created['id']}",
            json={"qualification_code": "ELI12345"},
            headers=as_user(ADMIN),
        )
        assert updated.status_code == 200
        assert updated.json()["qualification_code"] == "ELI12345"

        # And it can be cleared back to "no code issued".
        cleared = client.patch(
            f"/reference/qualifications/{created['id']}",
            json={"qualification_code": "NA"},
            headers=as_user(ADMIN),
        )
        assert cleared.status_code == 200
        assert cleared.json()["qualification_code"] is None

    def test_supplying_an_existing_code_to_a_code_less_qualification_is_refused(
        self, client, seed
    ):
        created = client.post(
            "/reference/qualifications",
            json={"qualification_title": "General English"},
            headers=as_user(ADMIN),
        ).json()
        response = client.patch(
            f"/reference/qualifications/{created['id']}",
            json={"qualification_code": "TESTQUAL001"},
            headers=as_user(ADMIN),
        )
        assert response.status_code == 409

    def test_duplicate_unit_code_is_refused(self, client, seed):
        response = client.post(
            "/reference/units",
            json={"unit_code": "TESTUNIT001", "unit_title": "Duplicate"},
            headers=as_user(ADMIN),
        )
        assert response.status_code == 409

    def test_campuses_are_filtered_to_the_approved_college(self, client, seed):
        """COL-01, applied in SQL rather than trusted to the browser."""
        other = client.post(
            "/reference/colleges",
            json={"college_short_name": "OTHER", "college_full_name": "Other College"},
            headers=as_user(ADMIN),
        ).json()

        approved = client.get(
            f"/reference/campuses?college_id={seed['college']['id']}", headers=as_user(VIEWER)
        ).json()
        unapproved = client.get(
            f"/reference/campuses?college_id={other['id']}", headers=as_user(VIEWER)
        ).json()

        assert [c["campus_code"] for c in approved] == ["TSTCAM"]
        assert unapproved == []

    def test_an_unapproved_college_campus_pair_is_refused(self, client, seed):
        """Two IDs that each exist are not evidence the combination was approved."""
        other = client.post(
            "/reference/colleges",
            json={"college_short_name": "OTHER", "college_full_name": "Other College"},
            headers=as_user(ADMIN),
        ).json()

        response = client.post(
            "/reference/courses",
            json={
                "college_id": other["id"],
                "campus_id": seed["campus"]["id"],
                "qualification_id": seed["qualification"]["id"],
                "course_code": "TESTCRS001",
                "course_status_id": seed["status_id"],
            },
            headers=as_user(ADMIN),
        )
        assert response.status_code == 422
        assert "not an approved campus" in response.json()["detail"]

    def test_duplicate_offering_is_refused(self, client, seed):
        """COL-04: one offering per college + campus + qualification."""
        body = {
            "college_id": seed["college"]["id"],
            "campus_id": seed["campus"]["id"],
            "qualification_id": seed["qualification"]["id"],
            "course_code": "TESTCRS001",
            "course_status_id": seed["status_id"],
            "duration_options": [26, 52],
        }
        assert client.post("/reference/courses", json=body, headers=as_user(ADMIN)).status_code == 201

        body["course_code"] = "TESTCRS002"
        second = client.post("/reference/courses", json=body, headers=as_user(ADMIN))
        assert second.status_code == 409
        assert "already exists for this college, campus and qualification" in second.json()["detail"]

    def test_the_same_course_code_may_be_offered_at_several_campuses(self, client, seed):
        """Approved 11 August 2026: Course Code is not unique.

        A CRICOS code identifies the course, not its delivery at one campus. The
        real Page 4A export repeats 163 of 183 codes across campuses, so a UNIQUE
        here would make the approved data unloadable.
        """
        second_campus = client.post(
            "/reference/campuses",
            json={
                "campus_code": "TSTCAM2",
                "campus_name": "Test Campus Two",
                "campus_location": "Second Location",
                "state": "NSW",
            },
            headers=as_user(ADMIN),
        ).json()
        client.post(
            "/reference/college-campuses",
            json={"college_id": seed["college"]["id"], "campus_id": second_campus["id"]},
            headers=as_user(ADMIN),
        )

        body = {
            "college_id": seed["college"]["id"],
            "campus_id": seed["campus"]["id"],
            "qualification_id": seed["qualification"]["id"],
            "course_code": "TESTCRS900",
            "course_status_id": seed["status_id"],
            "duration_options": [52],
        }
        first = client.post("/reference/courses", json=body, headers=as_user(ADMIN))
        assert first.status_code == 201

        body["campus_id"] = second_campus["id"]
        second = client.post("/reference/courses", json=body, headers=as_user(ADMIN))
        assert second.status_code == 201, second.text

        # Two distinct offerings sharing one Course Code, at different campuses.
        assert first.json()["id"] != second.json()["id"]
        assert first.json()["course_code"] == second.json()["course_code"] == "TESTCRS900"
        assert first.json()["campus_id"] != second.json()["campus_id"]

    def test_an_unknown_qualification_is_refused(self, client, seed):
        response = client.post(
            "/reference/courses",
            json={
                "college_id": seed["college"]["id"],
                "campus_id": seed["campus"]["id"],
                "qualification_id": 999999,
                "course_code": "TESTCRS003",
                "course_status_id": seed["status_id"],
            },
            headers=as_user(ADMIN),
        )
        assert response.status_code == 404

    def test_duplicate_delivery_order_is_refused_with_a_plain_message(self, client, seed):
        second_unit = client.post(
            "/reference/units",
            json={"unit_code": "TESTUNIT002", "unit_title": "Test Unit Two"},
            headers=as_user(ADMIN),
        ).json()

        first = client.post(
            "/reference/qualification-units",
            json={
                "qualification_id": seed["qualification"]["id"],
                "unit_id": seed["unit"]["id"],
                "delivery_order": 4,
            },
            headers=as_user(ADMIN),
        )
        assert first.status_code == 201

        clash = client.post(
            "/reference/qualification-units",
            json={
                "qualification_id": seed["qualification"]["id"],
                "unit_id": second_unit["id"],
                "delivery_order": 4,
            },
            headers=as_user(ADMIN),
        )
        assert clash.status_code == 409
        assert clash.json()["detail"] == (
            "Delivery order 4 is already used for this qualification."
        )
        # No SQL, constraint name or driver text leaks to the caller.
        for leak in ("UniqueViolation", "psycopg", "uq_", "SELECT", "INSERT"):
            assert leak not in clash.json()["detail"]

    def test_the_same_unit_cannot_appear_twice_in_one_qualification(self, client, seed):
        body = {
            "qualification_id": seed["qualification"]["id"],
            "unit_id": seed["unit"]["id"],
            "delivery_order": 1,
        }
        assert client.post(
            "/reference/qualification-units", json=body, headers=as_user(ADMIN)
        ).status_code == 201

        body["delivery_order"] = 2
        duplicate = client.post(
            "/reference/qualification-units", json=body, headers=as_user(ADMIN)
        )
        assert duplicate.status_code == 409
        assert "already in this qualification" in duplicate.json()["detail"]

    def test_a_unit_may_belong_to_several_qualifications(self, client, seed):
        """One Unit row, reused — not duplicated per qualification."""
        other = client.post(
            "/reference/qualifications",
            json={"qualification_code": "TESTQUAL002", "qualification_title": "Second"},
            headers=as_user(ADMIN),
        ).json()

        for qualification_id in (seed["qualification"]["id"], other["id"]):
            assert client.post(
                "/reference/qualification-units",
                json={
                    "qualification_id": qualification_id,
                    "unit_id": seed["unit"]["id"],
                    "delivery_order": 1,
                },
                headers=as_user(ADMIN),
            ).status_code == 201

        units = client.get("/reference/units", headers=as_user(VIEWER)).json()
        assert [u["unit_code"] for u in units].count("TESTUNIT001") == 1


class TestActiveAndDeleted:
    def test_inactive_records_are_excluded_from_new_selection_lists(self, client, seed):
        client.patch(
            f"/reference/colleges/{seed['college']['id']}",
            json={"is_active": False},
            headers=as_user(ADMIN),
        )
        assert client.get("/reference/colleges?active_only=true", headers=as_user(VIEWER)).json() == []
        # …but the historical record is still retrievable (DATA-03).
        assert len(client.get("/reference/colleges", headers=as_user(VIEWER)).json()) == 1
        assert (
            client.get(
                f"/reference/colleges/{seed['college']['id']}", headers=as_user(VIEWER)
            ).status_code
            == 200
        )

    def test_a_deleted_course_leaves_the_active_list_and_can_be_restored(self, client, seed):
        offering = client.post(
            "/reference/courses",
            json={
                "college_id": seed["college"]["id"],
                "campus_id": seed["campus"]["id"],
                "qualification_id": seed["qualification"]["id"],
                "course_code": "TESTCRS010",
                "course_status_id": seed["status_id"],
                "duration_options": [52],
            },
            headers=as_user(ADMIN),
        ).json()

        deleted = client.request(
            "DELETE",
            f"/reference/courses/{offering['id']}",
            json={"reason_code_id": seed["reason_id"], "reason_detail": "Test deletion"},
            headers=as_user(ADMIN),
        )
        assert deleted.status_code == 200
        assert deleted.json()["is_deleted"] is True
        assert deleted.json()["recovery_deadline"] is not None

        assert client.get("/reference/courses", headers=as_user(VIEWER)).json() == []
        recycled = client.get(
            "/reference/courses?include_deleted=true", headers=as_user(VIEWER)
        ).json()
        assert [c["course_code"] for c in recycled] == ["TESTCRS010"]

        restored = client.post(
            f"/reference/courses/{offering['id']}/restore", json={}, headers=as_user(ADMIN)
        )
        assert restored.status_code == 200
        assert restored.json()["is_deleted"] is False
        assert len(client.get("/reference/courses", headers=as_user(VIEWER)).json()) == 1

    def test_a_deleted_sequence_row_keeps_its_delivery_order(self, client, seed):
        """The approved uniqueness is not partial, so the slot is not released.

        That is coherent: the row is recoverable, and freeing its order would let
        another unit take the slot and make the restore impossible. The refusal
        says which situation the user is in rather than reporting a bare clash.
        """
        link = client.post(
            "/reference/qualification-units",
            json={
                "qualification_id": seed["qualification"]["id"],
                "unit_id": seed["unit"]["id"],
                "delivery_order": 3,
            },
            headers=as_user(ADMIN),
        ).json()

        client.request(
            "DELETE",
            f"/reference/qualification-units/{link['id']}",
            json={"reason_code_id": seed["reason_id"], "reason_detail": "Test"},
            headers=as_user(ADMIN),
        )

        other = client.post(
            "/reference/units",
            json={"unit_code": "TESTUNIT003", "unit_title": "Third"},
            headers=as_user(ADMIN),
        ).json()
        taken = client.post(
            "/reference/qualification-units",
            json={
                "qualification_id": seed["qualification"]["id"],
                "unit_id": other["id"],
                "delivery_order": 3,
            },
            headers=as_user(ADMIN),
        )
        assert taken.status_code == 409
        assert "held by a deleted unit" in taken.json()["detail"]

        # A different order is free, and the deleted row still restores cleanly.
        assert client.post(
            "/reference/qualification-units",
            json={
                "qualification_id": seed["qualification"]["id"],
                "unit_id": other["id"],
                "delivery_order": 4,
            },
            headers=as_user(ADMIN),
        ).status_code == 201

        restored = client.post(
            f"/reference/qualification-units/{link['id']}/restore",
            json={},
            headers=as_user(ADMIN),
        )
        assert restored.status_code == 200
        assert restored.json()["is_deleted"] is False
        assert restored.json()["delivery_order"] == 3


class TestComposition:
    def test_course_location_is_derived_from_the_campus(self, client, seed):
        """C-3: Location IS the campus value, not a second free-text column."""
        offering = client.post(
            "/reference/courses",
            json={
                "college_id": seed["college"]["id"],
                "campus_id": seed["campus"]["id"],
                "qualification_id": seed["qualification"]["id"],
                "course_code": "TESTCRS020",
                "course_status_id": seed["status_id"],
            },
            headers=as_user(ADMIN),
        ).json()
        assert offering["location"] == "Test Location"

        client.patch(
            f"/reference/campuses/{seed['campus']['id']}",
            json={"campus_location": "Moved Location"},
            headers=as_user(ADMIN),
        )
        refreshed = client.get(
            f"/reference/courses/{offering['id']}", headers=as_user(VIEWER)
        ).json()
        assert refreshed["location"] == "Moved Location"

    def test_rto_is_the_college_and_source_url_is_its_own_field(self, client, seed):
        """C-4: two separate concepts, never combined."""
        client.patch(
            f"/reference/qualifications/{seed['qualification']['id']}",
            json={"source_url": "https://training.gov.au/TESTQUAL001"},
            headers=as_user(ADMIN),
        )
        offering = client.post(
            "/reference/courses",
            json={
                "college_id": seed["college"]["id"],
                "campus_id": seed["campus"]["id"],
                "qualification_id": seed["qualification"]["id"],
                "course_code": "TESTCRS021",
                "course_status_id": seed["status_id"],
            },
            headers=as_user(ADMIN),
        ).json()

        assert offering["college_short_name"] == "TSTC"
        assert offering["source_url"] == "https://training.gov.au/TESTQUAL001"

    def test_duration_options_are_managed_as_a_set(self, client, seed):
        offering = client.post(
            "/reference/courses",
            json={
                "college_id": seed["college"]["id"],
                "campus_id": seed["campus"]["id"],
                "qualification_id": seed["qualification"]["id"],
                "course_code": "TESTCRS022",
                "course_status_id": seed["status_id"],
                "duration_options": [52, 26, 26],
            },
            headers=as_user(ADMIN),
        ).json()
        assert offering["duration_options"] == [26, 52]

        updated = client.patch(
            f"/reference/courses/{offering['id']}",
            json={"duration_options": [78]},
            headers=as_user(ADMIN),
        ).json()
        assert updated["duration_options"] == [78]

    def test_the_sequence_is_returned_in_delivery_order(self, client, seed):
        units = []
        for n in (1, 2, 3):
            units.append(
                client.post(
                    "/reference/units",
                    json={"unit_code": f"TESTUNIT10{n}", "unit_title": f"Unit {n}"},
                    headers=as_user(ADMIN),
                ).json()
            )
        for unit, order in zip(units, (3, 1, 2)):
            client.post(
                "/reference/qualification-units",
                json={
                    "qualification_id": seed["qualification"]["id"],
                    "unit_id": unit["id"],
                    "delivery_order": order,
                },
                headers=as_user(ADMIN),
            )

        rows = client.get(
            f"/reference/qualification-units?qualification_id={seed['qualification']['id']}",
            headers=as_user(VIEWER),
        ).json()
        assert [r["delivery_order"] for r in rows] == [1, 2, 3]
        assert [r["unit_code"] for r in rows] == ["TESTUNIT102", "TESTUNIT103", "TESTUNIT101"]


class TestWriteSafety:
    def test_the_browser_cannot_set_backend_owned_fields(self, client, people):
        """`id` and audit fields are simply absent from the create payload."""
        response = client.post(
            "/reference/colleges",
            json={
                "college_short_name": "OWN",
                "college_full_name": "Owned",
                "id": 999,
                "is_deleted": True,
                "deleted_by_user_id": 1,
            },
            headers=as_user(ADMIN),
        )
        assert response.status_code == 201
        assert response.json()["id"] != 999

    def test_a_failed_write_leaves_nothing_behind(self, client, seed, session):
        """The offering and its durations are one transaction."""
        before = session.execute(text("SELECT count(*) FROM course_offerings")).scalar_one()
        response = client.post(
            "/reference/courses",
            json={
                "college_id": seed["college"]["id"],
                "campus_id": seed["campus"]["id"],
                "qualification_id": seed["qualification"]["id"],
                "course_code": "TESTCRS030",
                "course_status_id": 999999,
                "duration_options": [26],
            },
            headers=as_user(ADMIN),
        )
        assert response.status_code == 404
        session.rollback()
        after = session.execute(text("SELECT count(*) FROM course_offerings")).scalar_one()
        assert after == before
        assert (
            session.execute(
                text("SELECT count(*) FROM offering_duration_options")
            ).scalar_one()
            == 0
        )

    def test_no_error_response_leaks_database_internals(self, client, seed):
        responses = [
            client.post(
                "/reference/colleges",
                json={"college_short_name": "TSTC", "college_full_name": "Dup"},
                headers=as_user(ADMIN),
            ),
            client.post(
                "/reference/units",
                json={"unit_code": "TESTUNIT001", "unit_title": "Dup"},
                headers=as_user(ADMIN),
            ),
            client.get("/reference/colleges/999999", headers=as_user(VIEWER)),
        ]
        for response in responses:
            body = str(response.json())
            for leak in ("Traceback", "psycopg", "sqlalchemy", "SELECT ", "INSERT ", "pg_"):
                assert leak not in body


class TestActivityRecords:
    def test_create_edit_and_delete_are_recorded(self, client, seed, session):
        offering = client.post(
            "/reference/courses",
            json={
                "college_id": seed["college"]["id"],
                "campus_id": seed["campus"]["id"],
                "qualification_id": seed["qualification"]["id"],
                "course_code": "TESTCRS040",
                "course_status_id": seed["status_id"],
            },
            headers=as_user(ADMIN),
        ).json()
        client.patch(
            f"/reference/courses/{offering['id']}",
            json={"course_code": "TESTCRS041"},
            headers=as_user(ADMIN),
        )
        client.request(
            "DELETE",
            f"/reference/courses/{offering['id']}",
            json={"reason_code_id": seed["reason_id"], "reason_detail": "Test"},
            headers=as_user(ADMIN),
        )
        client.post(
            f"/reference/courses/{offering['id']}/restore", json={}, headers=as_user(ADMIN)
        )

        actions = session.execute(
            text(
                "SELECT action FROM user_activity_records "
                "WHERE page_or_function = 'Page 4A - Course Data'"
            )
        ).scalars().all()
        for expected in ("CREATE", "UPDATE", "DELETE", "RESTORE"):
            assert expected in actions, expected

    def test_the_actor_comes_from_the_verified_identity(self, client, seed, session):
        client.post(
            "/reference/units",
            json={"unit_code": "TESTUNIT200", "unit_title": "Actor test"},
            headers=as_user(ADMIN),
        )
        row = session.execute(
            text(
                "SELECT user_reference_snapshot, access_level_snapshot "
                "FROM user_activity_records WHERE record_reference = 'TESTUNIT200'"
            )
        ).one()
        assert row.user_reference_snapshot == ADMIN
        assert row.access_level_snapshot == "ADMIN"

    def test_reads_do_not_create_activity_records(self, client, seed, session):
        """Ordinary GETs are not logged.

        Counted per reference-data page rather than across the whole table: a
        first authentication legitimately writes a SIGN_IN record (LOG-01), and
        including it would make this assert the opposite of what it means.
        """
        count = text(
            "SELECT count(*) FROM user_activity_records "
            "WHERE page_or_function LIKE '%Course Data%' "
            "   OR page_or_function LIKE '%Qualification and Unit%' "
            "   OR page_or_function = 'College and Course Reference Data'"
        )
        before = session.execute(count).scalar_one()
        for path in READ_ENDPOINTS:
            client.get(path, headers=as_user(VIEWER))
        assert session.execute(count).scalar_one() == before


class TestEmptyDatabase:
    def test_every_list_returns_an_empty_array_not_an_error(self, client, people):
        """An empty real database means an empty UI, never mock data."""
        for path in READ_ENDPOINTS:
            response = client.get(path, headers=as_user(VIEWER))
            assert response.status_code == 200, path
            assert response.json() == [], path


# ------------------------------------- membership without a delivery sequence


@pytest.mark.database
def test_page_4b_lists_a_membership_that_has_no_approved_order(client, people, seed):
    """A unit in a qualification with no approved teaching order must still list.

    Migration `d58f1a4c7e93` made `delivery_order` nullable so a unit's
    *membership* of a qualification could be stored without inventing an order:
    membership comes from Qualification Data, the order comes from an approved
    rolling timetable, and only some qualifications have one.

    The read contract stayed `int` and rejected every such row, so the endpoint
    returned an error and Page 4B rendered empty while 1,012 real memberships
    sat in the database. This pins the contract to the column it describes.
    """
    from app.models.qualification import QualificationUnit

    created = client.post(
        "/reference/qualification-units",
        json={
            "qualification_id": seed["qualification"]["id"],
            "unit_id": seed["unit"]["id"],
            "delivery_order": 1,
        },
        headers=as_user(ADMIN),
    )
    assert created.status_code == 201, created.text

    # Clear the order the way an import does: membership recorded, sequence not
    # supplied. No maintenance route removes one, so this is written directly.
    db = next(client.app.dependency_overrides[deps.get_db]())
    link = db.query(QualificationUnit).one()
    link.delivery_order = None
    db.commit()

    response = client.get("/reference/qualification-units", headers=as_user(VIEWER))
    assert response.status_code == 200, response.text

    rows = response.json()
    assert len(rows) == 1, "the unsequenced membership was dropped from the response"
    assert rows[0]["delivery_order"] is None
    assert rows[0]["unit_code"] == "TESTUNIT001"
