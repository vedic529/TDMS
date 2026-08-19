"""Full reference-data importer.

Fixtures are written inline rather than read from the supplied workbooks: a test
that depends on a file in someone's Downloads folder is not a test, and the
importer's job is the shape of the data, not one delivery of it.
"""

from __future__ import annotations

import pytest

from app.models.college import Campus, College, CollegeCampus
from app.models.course import CourseOffering
from app.models.qualification import Qualification, QualificationUnit, Unit
from app.services.reference_import import (
    ReferenceImporter,
    derive_campus,
    qualification_key,
    repair_text,
)

from tests.test_reference_data_api import client, people, seed  # noqa: F401


def location_row(**overrides):
    row = {
        "RTO": "TSTRTO",
        "Course Code": "TST001",
        "VET Code": "TSTQUAL01",
        "Course Status": "Registered",
        "Course Name": "Test Qualification",
        "Course Level": "Diploma",
        "Field Of Education Broard": "Management and Commerce",
        "Field Of Education Narrow": "Business and Management",
        "Course Sector": "VET",
        "Duration In Weeks": 52,
        "Total Course Cost": 1000,
        "Location": "1 Test St TESTVILLE NSW 2000",
    }
    row.update(overrides)
    return row


def qualification_row(**overrides):
    row = {
        "RTO": "TSTRTO",
        "Qualification Code": "TSTQUAL01",
        "Qualification Title": "Test Qualification",
        "Unit Code": "TSTUNIT01",
        "Unit Title": "Test Unit One",
        "Source URL": "https://example.invalid/course",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestTextRepair:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Support children’s health", "Support children's health"),
            ("Support children's health", "Support children's health"),
            ("132–146 Elizabeth St", "132-146 Elizabeth St"),
            ("HOBART, Tasmania", "HOBART, Tasmania"),
            ("  spaced   out  ", "spaced out"),
        ],
    )
    def test_typography_is_normalised(self, raw, expected):
        assert repair_text(raw) == expected

    def test_two_spellings_of_one_title_become_one(self):
        """`units.unit_code` is unique, so an unrepaired variant silently wins."""
        assert repair_text("Analyse children’s learning") == repair_text(
            "Analyse children's learning"
        )

    def test_only_typography_changes(self):
        assert repair_text("Diploma Of Management") == "Diploma Of Management"


class TestCampusDerivation:
    @pytest.mark.parametrize(
        ("address", "code", "name", "state"),
        [
            ("125 Main St BLACKTOWN NSW 2148", "BLACKTOWN", "Blacktown", "NSW"),
            ("125 Main St, Blacktown, NSW", "BLACKTOWN", "Blacktown", "NSW"),
            ("132-146 Elizabeth Street, HOBART, Tasmania 7000", "HOBART", "Hobart", "TAS"),
            ("841 George St, Haymarket NSW 2000", "HAYMARKET", "Haymarket", "NSW"),
            ("Level 1 620 Bourke St, MELBOURNE, Victoria 3000", "MELBOURNE", "Melbourne", "VIC"),
        ],
    )
    def test_a_campus_is_read_out_of_the_address(self, address, code, name, state):
        derived = derive_campus(address)
        assert (derived.code, derived.name, derived.state) == (code, name, state)

    def test_the_street_type_is_not_part_of_the_campus_name(self):
        """"125 Main St BLACKTOWN" must not become "St Blacktown"."""
        assert derive_campus("125 Main St BLACKTOWN NSW 2148").name == "Blacktown"

    def test_a_multi_word_suburb_survives(self):
        assert derive_campus("2 Test Rd SOUTH MELBOURNE VIC 3205").name == "South Melbourne"

    def test_the_same_site_written_two_ways_derives_one_campus(self):
        a = derive_campus("125 Main St BLACKTOWN NSW 2148")
        b = derive_campus("125 Main St, Blacktown, NSW")
        assert a.code == b.code

    def test_an_address_without_a_state_yields_no_state(self):
        """`campuses.state` is NOT NULL and is never guessed from a suburb name."""
        assert derive_campus("18 Some Road, Upper Mt Gravatt").state == ""

    def test_the_address_is_stored_verbatim(self):
        address = "132-146 Elizabeth Street, HOBART, Tasmania 7000"
        assert derive_campus(address).location == address


class TestQualificationKey:
    @pytest.mark.parametrize("absent", ["", "NA", "N/A", "nil", "-"])
    def test_a_code_less_qualification_is_keyed_by_its_title(self, absent):
        code, name = qualification_key(absent, "General English")
        assert code is None
        assert name == "GENERAL ENGLISH"

    def test_two_code_less_courses_stay_distinct(self):
        """Four ELICOS courses share "NA"; keying on it would merge them."""
        assert qualification_key("NA", "General English") != qualification_key(
            "NA", "IELTS Preparation"
        )

    def test_a_real_code_is_the_key(self):
        assert qualification_key("BSB50420", "Anything") == ("BSB50420", "")


# ---------------------------------------------------------------------------
# Import behaviour
# ---------------------------------------------------------------------------


class TestImport:
    def test_a_supplied_course_is_active_whatever_the_source_says(self, client, seed, session):
        """The approved rule, applied by the importer rather than by each caller."""
        importer = ReferenceImporter(session)
        importer.run([location_row(**{"Course Status": "Registered"})], [qualification_row()])
        session.commit()

        offering = (
            session.query(CourseOffering).filter(CourseOffering.course_code == "TST001").one()
        )
        assert offering.course_status.code == "ACTIVE"
        assert offering.course_status.label == "Active"

    def test_every_supplied_course_is_active(self, client, seed, session):
        rows = [
            location_row(**{"Course Code": f"TST{n:03d}", "VET Code": f"TSTQ{n:03d}"})
            for n in range(1, 6)
        ]
        ReferenceImporter(session).run(rows, [])
        session.commit()

        statuses = {
            o.course_status.code
            for o in session.query(CourseOffering).all()
            if o.course_code.startswith("TST")
        }
        assert statuses == {"ACTIVE"}

    def test_a_second_run_creates_nothing(self, client, seed, session):
        rows = [location_row()]
        quals = [qualification_row()]

        ReferenceImporter(session).run(rows, quals)
        session.commit()
        before = {
            model.__name__: session.query(model).count()
            for model in (College, Campus, CollegeCampus, Qualification, Unit, CourseOffering)
        }

        second = ReferenceImporter(session)
        report = second.run(rows, quals)
        session.commit()
        after = {
            model.__name__: session.query(model).count()
            for model in (College, Campus, CollegeCampus, Qualification, Unit, CourseOffering)
        }

        assert before == after
        for _, section in report.sections():
            assert section.create == 0

    def test_a_shared_campus_is_stored_once(self, client, seed, session):
        """Several colleges at one site must not produce several campuses."""
        rows = [
            location_row(**{"RTO": "RTOONE", "Course Code": "TST010", "VET Code": "TSTQ010"}),
            location_row(**{"RTO": "RTOTWO", "Course Code": "TST011", "VET Code": "TSTQ011"}),
        ]
        ReferenceImporter(session).run(rows, [])
        session.commit()

        assert session.query(Campus).filter(Campus.campus_code == "TESTVILLE").count() == 1
        assert session.query(CollegeCampus).count() >= 2

    def test_a_unit_is_shared_across_qualifications(self, client, seed, session):
        quals = [
            qualification_row(**{"Qualification Code": "TSTQ020"}),
            qualification_row(**{"Qualification Code": "TSTQ021"}),
        ]
        ReferenceImporter(session).run([], quals)
        session.commit()
        assert session.query(Unit).filter(Unit.unit_code == "TSTUNIT01").count() == 1

    def test_membership_is_stored_with_the_delivery_order_left_pending(
        self, client, seed, session
    ):
        """Membership and delivery order are separate facts from separate sources.

        Qualification Data says which units belong to the qualification, so the
        membership is stored. Only an approved rolling timetable says what order
        they run in, so `delivery_order` stays NULL — spreadsheet row order is
        not a teaching sequence and must never be written as one.
        """
        report = ReferenceImporter(session).run([], [qualification_row()])
        session.commit()

        assert report.qualification_units.create == 1
        assert [i.identifier for i in report.qualification_units.pending] == ["TSTQUAL01"]

        rows = session.query(QualificationUnit).all()
        assert len(rows) == 1
        assert rows[0].delivery_order is None

    def test_several_units_may_await_an_order_in_one_qualification(
        self, client, seed, session
    ):
        """The uniqueness on (qualification, delivery_order) must tolerate NULLs.

        PostgreSQL treats NULLs as distinct, so a whole qualification can sit
        awaiting a timetable while two units still cannot share position 3.
        """
        quals = [
            qualification_row(**{"Unit Code": "TSTUNITA", "Unit Title": "A"}),
            qualification_row(**{"Unit Code": "TSTUNITB", "Unit Title": "B"}),
            qualification_row(**{"Unit Code": "TSTUNITC", "Unit Title": "C"}),
        ]
        ReferenceImporter(session).run([], quals)
        session.commit()

        rows = session.query(QualificationUnit).all()
        assert len(rows) == 3
        assert all(row.delivery_order is None for row in rows)

    def test_an_approved_sequence_source_is_used_in_its_own_order(
        self, client, seed, session
    ):
        """The order comes from the timetable, not from the spreadsheet's rows."""
        quals = [
            qualification_row(**{"Unit Code": "TSTUNITA", "Unit Title": "A"}),
            qualification_row(**{"Unit Code": "TSTUNITB", "Unit Title": "B"}),
            qualification_row(**{"Unit Code": "TSTUNITC", "Unit Title": "C"}),
        ]
        importer = ReferenceImporter(
            session,
            # Deliberately not the row order above.
            sequence_sources={"TSTQUAL01": ["TSTUNITC", "TSTUNITA", "TSTUNITB"]},
        )
        importer.run([], quals)
        session.commit()

        stored = (
            session.query(QualificationUnit)
            .join(Unit, Unit.id == QualificationUnit.unit_id)
            .order_by(QualificationUnit.delivery_order)
            .all()
        )
        assert [(q.delivery_order, q.unit.unit_code) for q in stored] == [
            (1, "TSTUNITC"),
            (2, "TSTUNITA"),
            (3, "TSTUNITB"),
        ]

    def test_disagreeing_unit_sets_are_reported_not_merged(self, client, seed, session):
        """One qualification code, two RTOs, different units — a real conflict."""
        quals = [
            qualification_row(**{"RTO": "RTOONE", "Unit Code": "TSTUNITA"}),
            qualification_row(**{"RTO": "RTOTWO", "Unit Code": "TSTUNITB"}),
        ]
        report = ReferenceImporter(
            session, sequence_sources={"TSTQUAL01": ["TSTUNITA", "TSTUNITB"]}
        ).run([], quals)
        session.commit()

        assert [i.identifier for i in report.qualification_units.conflicts] == ["TSTQUAL01"]
        assert session.query(QualificationUnit).count() == 0

    def test_two_course_codes_for_one_offering_are_reported(self, client, seed, session):
        """COL-04 allows one offering; the discarded code must not vanish silently."""
        rows = [
            location_row(**{"Course Code": "TST030"}),
            location_row(**{"Course Code": "TST031"}),
        ]
        report = ReferenceImporter(session).run(rows, [])
        session.commit()

        assert len(report.courses.conflicts) == 1
        assert "TST030" in report.courses.conflicts[0].reason
        assert "TST031" in report.courses.conflicts[0].reason
        assert session.query(CourseOffering).filter(
            CourseOffering.course_code.in_(["TST030", "TST031"])
        ).count() == 1

    def test_an_address_without_a_state_is_rejected_not_guessed(self, client, seed, session):
        report = ReferenceImporter(session).run(
            [location_row(**{"Location": "18 Some Road, Upper Mt Gravatt"})], []
        )
        session.commit()

        assert len(report.campuses.rejected) == 1
        assert "state" in report.campuses.rejected[0].reason
        assert len(report.courses.rejected) == 1

    def test_code_less_qualifications_are_not_merged(self, client, seed, session):
        rows = [
            location_row(**{"VET Code": "NA", "Course Name": "General English", "Course Code": "TST040"}),
            location_row(**{"VET Code": "NA", "Course Name": "IELTS Preparation", "Course Code": "TST041"}),
        ]
        ReferenceImporter(session).run(rows, [])
        session.commit()

        code_less = session.query(Qualification).filter(
            Qualification.qualification_code.is_(None)
        ).all()
        assert {q.qualification_title for q in code_less} == {
            "General English",
            "IELTS Preparation",
        }

    def test_duration_options_are_a_set_per_offering(self, client, seed, session):
        rows = [
            location_row(**{"Duration In Weeks": 26}),
            location_row(**{"Duration In Weeks": 52}),
            location_row(**{"Duration In Weeks": 52}),
        ]
        ReferenceImporter(session).run(rows, [])
        session.commit()

        offering = (
            session.query(CourseOffering).filter(CourseOffering.course_code == "TST001").one()
        )
        assert sorted(d.duration_weeks for d in offering.duration_options) == [26, 52]
