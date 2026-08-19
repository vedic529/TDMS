"""Page 4 cascading filters: College -> Campus -> Qualification -> results.

The defect these pin down: the Qualification filter was populated from the whole
`qualifications` table, so selecting HJ at Hobart offered AHC and AUR
qualifications that HJ does not deliver anywhere. The scope has to come from
real offerings, and it has to come from the server — a browser that filters its
own list is a browser that can be wrong about what exists.
"""

from __future__ import annotations

import pytest

from app.models.college import Campus, College, CollegeCampus
from app.models.course import CourseOffering
from app.models.qualification import Qualification, QualificationUnit, Unit
from app.services import reference_data as service

from tests.test_reference_data_api import ADMIN, as_user, client, people, seed  # noqa: F401


@pytest.fixture
def catalogue(session, seed):
    """A miniature of the real catalogue: two colleges sharing one campus.

    Shaped after the live data so the tests mean something — HJ delivers a small
    business set at one campus, AVTA delivers agriculture and automotive at
    another, and both operate at a shared site.
    """
    colleges = {code: College(college_short_name=code, college_full_name=code)
                for code in ("TSTHJ", "TSTAVTA")}
    campuses = {
        "HOB": Campus(campus_code="TSTHOB", campus_name="Hobart",
                      campus_location="Hobart", state="TAS"),
        "BUN": Campus(campus_code="TSTBUN", campus_name="Bundaberg",
                      campus_location="Bundaberg", state="QLD"),
        "SHARED": Campus(campus_code="TSTSHARED", campus_name="Shared",
                         campus_location="Shared", state="NSW"),
    }
    session.add_all([*colleges.values(), *campuses.values()])
    session.flush()

    links = [
        ("TSTHJ", "HOB"), ("TSTHJ", "SHARED"),
        ("TSTAVTA", "BUN"), ("TSTAVTA", "SHARED"),
    ]
    for college, campus in links:
        session.add(CollegeCampus(college_id=colleges[college].id, campus_id=campuses[campus].id))

    quals = {
        code: Qualification(qualification_code=code, qualification_title=f"Test {code}")
        for code in ("TSTBSB1", "TSTBSB2", "TSTAHC1", "TSTAUR1", "TSTSHARED1", "TSTNOWHERE")
    }
    session.add_all(quals.values())
    session.flush()

    # TSTNOWHERE exists in the table but is offered by nobody — it must never
    # appear in a scoped filter.
    offerings = [
        ("TSTHJ", "HOB", "TSTBSB1"), ("TSTHJ", "HOB", "TSTBSB2"),
        ("TSTAVTA", "BUN", "TSTAHC1"), ("TSTAVTA", "BUN", "TSTAUR1"),
        ("TSTHJ", "SHARED", "TSTSHARED1"), ("TSTAVTA", "SHARED", "TSTSHARED1"),
    ]
    for index, (college, campus, qual) in enumerate(offerings):
        session.add(CourseOffering(
            college_id=colleges[college].id, campus_id=campuses[campus].id,
            qualification_id=quals[qual].id, course_code=f"TSTC{index:03d}",
            course_status_id=seed["status_id"],
        ))
    session.commit()
    return {"colleges": colleges, "campuses": campuses, "quals": quals}


def codes(rows):
    return sorted(r.qualification_code for r in rows)


class TestCollegeToCampusCascade:
    def test_one_college_sees_only_its_own_campuses(self, session, catalogue):
        hj = catalogue["colleges"]["TSTHJ"].id
        rows = service.list_campuses(session, college_ids=[hj])
        assert sorted(c.campus_code for c in rows) == ["TSTHOB", "TSTSHARED"]
        assert "TSTBUN" not in [c.campus_code for c in rows]

    def test_several_colleges_give_the_union(self, session, catalogue):
        ids = [catalogue["colleges"]["TSTHJ"].id, catalogue["colleges"]["TSTAVTA"].id]
        rows = service.list_campuses(session, college_ids=ids)
        assert sorted(c.campus_code for c in rows) == ["TSTBUN", "TSTHOB", "TSTSHARED"]

    def test_a_shared_campus_appears_once(self, session, catalogue):
        """DBQ-04: one physical site, however many colleges operate there."""
        ids = [catalogue["colleges"]["TSTHJ"].id, catalogue["colleges"]["TSTAVTA"].id]
        rows = service.list_campuses(session, college_ids=ids)
        shared = [c for c in rows if c.campus_code == "TSTSHARED"]
        assert len(shared) == 1

    def test_no_college_means_every_campus(self, session, catalogue):
        """Select All is "no restriction", never "match nothing"."""
        rows = service.list_campuses(session, college_ids=[])
        assert {"TSTHOB", "TSTBUN", "TSTSHARED"} <= {c.campus_code for c in rows}


class TestCampusToQualificationCascade:
    def test_a_college_and_campus_see_only_what_is_offered_there(self, session, catalogue):
        """The reported defect: HJ at Hobart must not be offered AHC or AUR."""
        rows = service.list_offered_qualifications(
            session,
            college_ids=[catalogue["colleges"]["TSTHJ"].id],
            campus_ids=[catalogue["campuses"]["HOB"].id],
        )
        assert codes(rows) == ["TSTBSB1", "TSTBSB2"]
        assert "TSTAHC1" not in codes(rows)
        assert "TSTAUR1" not in codes(rows)

    def test_a_qualification_offered_by_nobody_never_appears(self, session, catalogue):
        rows = service.list_offered_qualifications(
            session, college_ids=[catalogue["colleges"]["TSTAVTA"].id]
        )
        assert "TSTNOWHERE" not in codes(rows)

    def test_all_campuses_gives_that_college_only(self, session, catalogue):
        """AVTA with every campus: AVTA's qualifications, not HJ's."""
        rows = service.list_offered_qualifications(
            session, college_ids=[catalogue["colleges"]["TSTAVTA"].id]
        )
        assert codes(rows) == ["TSTAHC1", "TSTAUR1", "TSTSHARED1"]
        assert "TSTBSB1" not in codes(rows)

    def test_multiple_colleges_and_campuses_use_real_pairs_not_a_cross_product(
        self, session, catalogue
    ):
        """HJ+AVTA with Hobart+Bundaberg.

        The cross-product would also claim HJ/Bundaberg and AVTA/Hobart, which do
        not exist. Only genuine offerings count.
        """
        rows = service.list_offered_qualifications(
            session,
            college_ids=[catalogue["colleges"]["TSTHJ"].id,
                         catalogue["colleges"]["TSTAVTA"].id],
            campus_ids=[catalogue["campuses"]["HOB"].id,
                        catalogue["campuses"]["BUN"].id],
        )
        assert codes(rows) == ["TSTAHC1", "TSTAUR1", "TSTBSB1", "TSTBSB2"]
        # TSTSHARED1 is only offered at the shared campus, which was not selected.
        assert "TSTSHARED1" not in codes(rows)

    def test_a_shared_qualification_is_not_duplicated(self, session, catalogue):
        """Offered by both colleges at one campus — one option, not two."""
        rows = service.list_offered_qualifications(
            session,
            college_ids=[catalogue["colleges"]["TSTHJ"].id,
                         catalogue["colleges"]["TSTAVTA"].id],
            campus_ids=[catalogue["campuses"]["SHARED"].id],
        )
        assert codes(rows) == ["TSTSHARED1"]

    def test_an_invalid_college_campus_pairing_returns_nothing(self, session, catalogue):
        """HJ does not operate at Bundaberg."""
        rows = service.list_offered_qualifications(
            session,
            college_ids=[catalogue["colleges"]["TSTHJ"].id],
            campus_ids=[catalogue["campuses"]["BUN"].id],
        )
        assert rows == []


class TestOfferingNotUnitMembership:
    def test_a_qualification_without_unit_data_is_still_offered(self, session, catalogue, seed):
        """HJ's BSB50120 and AVTA's CPPBDN6106 have no unit rows yet.

        The filter must list what is *offered*, not what happens to have complete
        unit data — otherwise a real offering disappears because a second
        workbook is behind.
        """
        # TSTBSB1 deliberately has no qualification_units row at all.
        assert session.query(QualificationUnit).filter_by(
            qualification_id=catalogue["quals"]["TSTBSB1"].id
        ).count() == 0

        rows = service.list_offered_qualifications(
            session,
            college_ids=[catalogue["colleges"]["TSTHJ"].id],
            campus_ids=[catalogue["campuses"]["HOB"].id],
        )
        assert "TSTBSB1" in codes(rows)

    def test_selecting_it_shows_no_units_rather_than_another_qualifications(
        self, session, catalogue
    ):
        unit = Unit(unit_code="TSTU900", unit_title="Test unit")
        session.add(unit)
        session.flush()
        session.add(QualificationUnit(
            qualification_id=catalogue["quals"]["TSTBSB2"].id,
            unit_id=unit.id, delivery_order=1,
        ))
        session.commit()

        rows = service.list_qualification_units(
            session, qualification_ids=[catalogue["quals"]["TSTBSB1"].id]
        )
        assert rows == []

        # ...and the qualification that does have units is unaffected.
        rows = service.list_qualification_units(
            session, qualification_ids=[catalogue["quals"]["TSTBSB2"].id]
        )
        assert [r.unit.unit_code for r in rows] == ["TSTU900"]


class TestResultScope:
    def test_course_results_are_restricted_to_the_selected_scope(self, session, catalogue):
        """The stale-table defect: changing college must change the rows."""
        hj = catalogue["colleges"]["TSTHJ"].id
        avta = catalogue["colleges"]["TSTAVTA"].id

        hj_rows = service.list_course_offerings(session, college_ids=[hj])
        avta_rows = service.list_course_offerings(session, college_ids=[avta])

        assert {r.college_id for r in hj_rows} == {hj}
        assert {r.college_id for r in avta_rows} == {avta}
        assert not ({r.id for r in hj_rows} & {r.id for r in avta_rows})

    def test_qualification_units_are_scoped_by_college_and_campus(self, session, catalogue):
        unit = Unit(unit_code="TSTU901", unit_title="Test unit")
        session.add(unit)
        session.flush()
        session.add(QualificationUnit(
            qualification_id=catalogue["quals"]["TSTAHC1"].id, unit_id=unit.id, delivery_order=1
        ))
        session.commit()

        # AVTA at Bundaberg offers TSTAHC1, so its sequence is in scope.
        rows = service.list_qualification_units(
            session,
            college_ids=[catalogue["colleges"]["TSTAVTA"].id],
            campus_ids=[catalogue["campuses"]["BUN"].id],
        )
        assert [r.unit.unit_code for r in rows] == ["TSTU901"]

        # HJ at Hobart does not, so it is not.
        rows = service.list_qualification_units(
            session,
            college_ids=[catalogue["colleges"]["TSTHJ"].id],
            campus_ids=[catalogue["campuses"]["HOB"].id],
        )
        assert rows == []

    def test_search_stays_inside_the_current_scope(self, client, session, catalogue):
        hj = catalogue["colleges"]["TSTHJ"].id
        rows = service.list_course_offerings(session, college_ids=[hj], search="TSTC")
        assert {r.college_id for r in rows} == {hj}


class TestThroughTheApi:
    """The scope is enforced by the server, not by whoever is calling it."""

    def test_repeated_query_parameters_scope_the_response(self, client, catalogue):
        hj = catalogue["colleges"]["TSTHJ"].id
        hob = catalogue["campuses"]["HOB"].id

        response = client.get(
            f"/reference/qualifications?college_ids={hj}&campus_ids={hob}",
            headers=as_user(ADMIN),
        )
        assert response.status_code == 200
        assert sorted(q["qualification_code"] for q in response.json()) == ["TSTBSB1", "TSTBSB2"]

    def test_several_ids_are_accepted_for_one_filter(self, client, catalogue):
        hj = catalogue["colleges"]["TSTHJ"].id
        avta = catalogue["colleges"]["TSTAVTA"].id
        response = client.get(
            f"/reference/campuses?college_ids={hj}&college_ids={avta}",
            headers=as_user(ADMIN),
        )
        assert sorted(c["campus_code"] for c in response.json()) == [
            "TSTBUN", "TSTHOB", "TSTSHARED",
        ]

    def test_courses_accept_the_full_filter_set(self, client, catalogue):
        hj = catalogue["colleges"]["TSTHJ"].id
        hob = catalogue["campuses"]["HOB"].id
        qual = catalogue["quals"]["TSTBSB1"].id
        response = client.get(
            f"/reference/courses?college_ids={hj}&campus_ids={hob}&qualification_ids={qual}",
            headers=as_user(ADMIN),
        )
        assert [c["qualification_code"] for c in response.json()] == ["TSTBSB1"]

    def test_no_filters_returns_the_whole_valid_set(self, client, catalogue):
        response = client.get("/reference/courses", headers=as_user(ADMIN))
        assert len(response.json()) >= 6

    def test_the_unscoped_qualification_list_still_returns_the_table(self, client, catalogue):
        """A maintenance form needs every qualification, not only offered ones."""
        response = client.get("/reference/qualifications", headers=as_user(ADMIN))
        assert "TSTNOWHERE" in [q["qualification_code"] for q in response.json()]
