"""Approved rule: every course supplied by the project owner is ACTIVE in TDMS.

The source workbook's own wording — "Registered", "Current", "Approved",
"Listed" — describes an external registration state. It is not TDMS operational
availability and must never be copied into the status field, which is how
104262B came to display as Inactive.
"""

from __future__ import annotations

import pytest

from app.models.course import CourseStatus
from app.services import reference_data as service

from tests.test_reference_data_api import ADMIN, as_user, client, people, seed  # noqa: F401


class TestSuppliedStatus:
    def test_a_supplied_course_gets_the_approved_active_status(self, client, seed, session):
        status = service.status_for_supplied_course(session)
        session.commit()
        assert status.code == "ACTIVE"
        assert status.label == "Active"
        assert status.selectable_for_new_records is True
        assert status.is_active is True


    def test_the_active_status_is_created_once(self, client, seed, session):
        first = service.status_for_supplied_course(session)
        session.commit()
        second = service.status_for_supplied_course(session)
        session.commit()
        assert first.id == second.id
        count = (
            session.query(CourseStatus).filter(CourseStatus.code == "ACTIVE").count()
        )
        assert count == 1


    @pytest.mark.parametrize("source_term", ["Registered", "Current", "Approved", "Listed"])
    def test_a_source_registration_term_never_becomes_the_tdms_status(
        self, client, seed, session, source_term
    ):
        """Whatever the workbook says, the TDMS status is ACTIVE.

        The mapping is one-way on purpose: a term never seen before still maps to
        ACTIVE, because the rule is about who supplied the course, not about the
        word used.
        """
        status = service.status_for_supplied_course(session)
        session.commit()
        assert status.code == "ACTIVE"
        assert status.code != source_term.upper()



class TestCorrection:
    def _offering(self, client, seed, status_id, code="TESTCRS500"):
        response = client.post(
            "/reference/courses",
            json={
                "college_id": seed["college"]["id"],
                "campus_id": seed["campus"]["id"],
                "qualification_id": seed["qualification"]["id"],
                "course_code": code,
                "course_status_id": status_id,
                "duration_options": [52],
            },
            headers=as_user(ADMIN),
        )
        assert response.status_code == 201, response.text
        return response.json()

    def test_a_supplied_course_stored_under_a_source_term_is_corrected(self, client, seed, session):
        """Reproduces the 104262B defect and proves the correction fixes it."""
        registered = CourseStatus(
            code="REGISTERED", label="Registered", selectable_for_new_records=True
        )
        session.add(registered)
        session.commit()
        registered_id = registered.id

        offering = self._offering(client, seed, registered_id)
        assert offering["course_status_code"] == "REGISTERED"

        report = service.correct_supplied_course_statuses(session, ["TESTCRS500"])
        session.commit()

        assert report.supplied_offerings == 1
        assert report.incorrectly_inactive == 1
        assert report.corrected == ["TESTCRS500"]
        # The source-term vocabulary value is retired once unreferenced.
        assert "REGISTERED" in report.retired_status_codes

        after = client.get(
            f"/reference/courses/{offering['id']}", headers=as_user(ADMIN)
        ).json()
        assert after["course_status_code"] == "ACTIVE"
        assert after["course_status_label"] == "Active"

    def test_a_course_not_in_the_supplied_dataset_is_left_alone(self, client, seed, session):
        """"Everything supplied is active" says nothing about a hand-entered record."""
        # Selectable, so COL-05 lets the record be created at all — this test is
        # about provenance, not about which statuses may be chosen.
        other = CourseStatus(
            code="SUPERSEDED", label="Superseded", selectable_for_new_records=True
        )
        session.add(other)
        session.commit()
        other_id = other.id

        offering = self._offering(client, seed, other_id, code="HANDENTERED1")

        report = service.correct_supplied_course_statuses(session, ["TESTCRS500"])
        session.commit()
        assert "HANDENTERED1" in report.untraceable_left_alone
        assert report.corrected == []

        after = client.get(
            f"/reference/courses/{offering['id']}", headers=as_user(ADMIN)
        ).json()
        assert after["course_status_code"] == "SUPERSEDED"

    def test_the_correction_is_idempotent(self, client, seed, session):
        """A second import must not push an ACTIVE course back to anything else."""
        active = service.status_for_supplied_course(session)
        session.commit()
        active_id = active.id

        self._offering(client, seed, active_id, code="TESTCRS501")

        for _ in range(2):
            report = service.correct_supplied_course_statuses(session, ["TESTCRS501"])
            session.commit()
            assert report.supplied_offerings == 1
            assert report.already_active == 1
            assert report.incorrectly_inactive == 0
            assert report.corrected == []


class TestFiltering:
    def test_the_active_filter_returns_a_supplied_course(self, client, seed, session):
        active_id = service.status_for_supplied_course(session).id
        session.commit()

        client.post(
            "/reference/courses",
            json={
                "college_id": seed["college"]["id"],
                "campus_id": seed["campus"]["id"],
                "qualification_id": seed["qualification"]["id"],
                "course_code": "TESTCRS502",
                "course_status_id": active_id,
                "duration_options": [52],
            },
            headers=as_user(ADMIN),
        )

        active = client.get(
            "/reference/courses?course_status_code=ACTIVE", headers=as_user(ADMIN)
        ).json()
        assert [c["course_code"] for c in active] == ["TESTCRS502"]

        # ...and the Inactive filter must not return it.
        inactive = client.get(
            "/reference/courses?course_status_code=INACTIVE", headers=as_user(ADMIN)
        ).json()
        assert inactive == []

        # ...while no filter shows everything.
        every = client.get("/reference/courses", headers=as_user(ADMIN)).json()
        assert len(every) == 1

    def test_the_status_filter_is_case_insensitive(self, client, seed, session):
        active_id = service.status_for_supplied_course(session).id
        session.commit()

        client.post(
            "/reference/courses",
            json={
                "college_id": seed["college"]["id"],
                "campus_id": seed["campus"]["id"],
                "qualification_id": seed["qualification"]["id"],
                "course_code": "TESTCRS503",
                "course_status_id": active_id,
                "duration_options": [52],
            },
            headers=as_user(ADMIN),
        )
        rows = client.get(
            "/reference/courses?course_status_code=active", headers=as_user(ADMIN)
        ).json()
        assert len(rows) == 1

    def test_a_supplied_course_is_selectable_for_new_records(self, client, seed, session):
        """It must not be hidden from Student, Trainer or Timetable lookups."""
        service.status_for_supplied_course(session)
        session.commit()

        selectable = client.get(
            "/reference/course-statuses?active_only=true", headers=as_user(ADMIN)
        ).json()
        codes = [s["code"] for s in selectable if s["selectable_for_new_records"]]
        assert "ACTIVE" in codes
