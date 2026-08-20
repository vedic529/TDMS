"""Facility Data — faculty mapping, the NA rule, availability and the API.

The faculty rules are pure functions and are tested without a database. The
shape of the data is tested against real rows, because the design came from the
supplied file rather than from an assumption: a source row is not a room, and
the three tables must reconstruct the file exactly.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api import deps
from app.auth.mock import mock_claims_for
from app.core.config import Settings, get_settings
from app.main import app
from app.models.college import Campus, College
from app.models.facility import Facility, FacilityCollege, FacilityFaculty
from app.models.user import User
from app.services.facilities import (
    FACULTIES_WITHOUT_A_PREFIX,
    FACULTY_BY_PREFIX,
    UNRESTRICTED_FACULTY,
    eligible_facilities,
    faculty_for_qualification_code,
    is_faculty_eligible,
    list_facilities,
)

# ------------------------------------------------------- faculty mapping
# No database: these are the rules, and they must hold on their own.


@pytest.mark.parametrize(
    "code, faculty",
    [
        ("BSB50420", "Business"),
        ("FNS50222", "Business"),
        ("SIT30821", "Hospitality"),
        ("CHC52021", "Community Services"),
        ("AUR30620", "Engineering Technology"),
        ("CPC60220", "Engineering Technology"),
        ("ICT50220", "Engineering Technology"),
        ("RII60520", "Engineering Technology"),
        ("TLI41222", "Engineering Technology"),
        ("AHC30722", "Engineering Technology"),
    ],
)
def test_every_approved_prefix_maps(code, faculty):
    assert faculty_for_qualification_code(code) == faculty


def test_the_faculty_comes_from_the_prefix_not_the_whole_code():
    # A qualification TDMS has never seen must still map, or every new release
    # of a training package would need a code change here.
    assert faculty_for_qualification_code("BSB99999") == "Business"
    assert faculty_for_qualification_code("bsb50420") == "Business"


def test_an_unmapped_prefix_returns_none_rather_than_guessing():
    assert faculty_for_qualification_code("ZZZ99999") is None
    assert faculty_for_qualification_code("") is None
    assert faculty_for_qualification_code(None) is None


def test_elicos_has_no_prefix_and_is_recorded_as_such():
    # ELICOS appears in the supplied file but not in the approved mapping. It is
    # English-language delivery with no VET code, so nothing maps to it. Named
    # explicitly so the gap reads as a known fact, not a matching bug.
    assert "ELICOS" in FACULTIES_WITHOUT_A_PREFIX
    assert "ELICOS" not in FACULTY_BY_PREFIX.values()


# ------------------------------------------------------------ the NA rule


@pytest.mark.parametrize("code", ["BSB50420", "SIT30821", "CHC52021", "AHC30722", "ZZZ99999"])
def test_na_is_eligible_for_every_qualification(code):
    assert is_faculty_eligible(UNRESTRICTED_FACULTY, code) is True


def test_na_is_a_rule_not_missing_data():
    # Lower case, padded — still the rule.
    assert is_faculty_eligible(" na ", "BSB50420") is True


def test_a_named_faculty_admits_only_its_own_qualifications():
    assert is_faculty_eligible("Business", "BSB50420") is True
    assert is_faculty_eligible("Business", "FNS50222") is True
    assert is_faculty_eligible("Hospitality", "BSB50420") is False
    assert is_faculty_eligible("Community Services", "SIT30821") is False


def test_an_unmapped_qualification_is_not_admitted_by_a_named_faculty():
    # Admitting it everywhere would invent a mapping the project has not agreed.
    assert is_faculty_eligible("Business", "ZZZ99999") is False
    assert is_faculty_eligible("ELICOS", "BSB50420") is False


# ------------------------------------------------------------- database


pytestmark_db = pytest.mark.database


@pytest.fixture()
def facility_fixture(session):
    """One campus, two colleges, three rooms covering the interesting cases."""
    session.execute(
        text(
            "TRUNCATE TABLE facility_faculties, facility_colleges, facilities, "
            "college_campuses, campuses, colleges RESTART IDENTITY CASCADE"
        )
    )
    campus = Campus(
        campus_code="TESTCAMPUS",
        campus_name="Test Campus",
        campus_location="1 Test St, Testville NSW 2000",
        state="NSW",
    )
    aibt = College(college_short_name="TESTAIBT", college_full_name="Test AIBT")
    bic = College(college_short_name="TESTBIC", college_full_name="Test BIC")
    session.add_all([campus, aibt, bic])
    session.flush()

    def room(name, location, capacity, faculties, colleges):
        facility = Facility(
            facility_reference=name,
            campus_id=campus.id,
            source_location=location,
            facility_type="Campus",
            capacity=capacity,
        )
        session.add(facility)
        session.flush()
        for college in colleges:
            session.add(FacilityCollege(facility_id=facility.id, college_id=college.id))
        for faculty, days, remarks in faculties:
            session.add(
                FacilityFaculty(
                    facility_id=facility.id,
                    faculty=faculty,
                    monday="MONDAY" in days,
                    tuesday="TUESDAY" in days,
                    wednesday="WEDNESDAY" in days,
                    thursday="THURSDAY" in days,
                    friday="FRIDAY" in days,
                    remarks=remarks,
                )
            )
        return facility

    business = room(
        "Room 1", "Building A", 20, [("Business", {"MONDAY", "TUESDAY"}, None)], [aibt, bic]
    )
    anything = room("Room 2", "Building A", 30, [("NA", {"MONDAY"}, "Shared")], [aibt])
    # Same room name, different building on the same campus — the case the old
    # UNIQUE(campus_id, facility_reference) could not hold.
    other_building = room(
        "Room 1", "Building B", 12, [("Hospitality", {"FRIDAY"}, None)], [bic]
    )
    session.commit()
    return {"campus": campus, "aibt": aibt, "bic": bic,
            "business": business, "anything": anything, "other": other_building}


@pytest.mark.database
def test_one_room_name_can_exist_in_two_buildings_on_one_campus(session, facility_fixture):
    # Nine Hobart room names really do appear in both Elizabeth Street
    # buildings. Splitting the campus would fracture a site that clash checks
    # treat as one place, so the supplied Location joins the key instead.
    rooms = list_facilities(session)
    named = [f for f in rooms if f.facility_reference == "Room 1"]
    assert len(named) == 2
    assert {f.source_location for f in named} == {"Building A", "Building B"}
    assert {f.capacity for f in named} == {20, 12}


@pytest.mark.database
def test_a_room_carries_its_colleges_and_faculties(session, facility_fixture):
    rooms = {(f.facility_reference, f.source_location): f for f in list_facilities(session)}
    shared = rooms[("Room 1", "Building A")]
    assert sorted(link.college.college_short_name for link in shared.colleges) == [
        "TESTAIBT",
        "TESTBIC",
    ]
    assert [rule.faculty for rule in shared.faculties] == ["Business"]


@pytest.mark.database
def test_filtering_by_college_returns_only_that_college_s_rooms(session, facility_fixture):
    only_bic = list_facilities(session, college_ids=[facility_fixture["bic"].id])
    assert {(f.facility_reference, f.source_location) for f in only_bic} == {
        ("Room 1", "Building A"),
        ("Room 1", "Building B"),
    }


@pytest.mark.database
def test_an_empty_filter_means_no_restriction(session, facility_fixture):
    # Matching `list_offered_qualifications`: empty is "everything", never "nothing".
    assert len(list_facilities(session, college_ids=[])) == 3
    assert len(list_facilities(session, campus_ids=[])) == 3


@pytest.mark.database
def test_eligibility_needs_both_the_faculty_and_the_day(session, facility_fixture):
    monday = eligible_facilities(session, qualification_code="BSB50420", weekday="MONDAY")
    # Room 1 Building A (Business, Monday) and Room 2 (NA, Monday).
    assert {e.facility.facility_reference for e in monday} == {"Room 1", "Room 2"}
    assert {e.matched_faculty for e in monday} == {"Business", "NA"}

    # Business is not available on Wednesday, and NA is Monday only.
    wednesday = eligible_facilities(session, qualification_code="BSB50420", weekday="WEDNESDAY")
    assert wednesday == []


@pytest.mark.database
def test_na_admits_a_qualification_no_named_faculty_would(session, facility_fixture):
    got = eligible_facilities(session, qualification_code="ZZZ99999", weekday="MONDAY")
    assert [e.facility.facility_reference for e in got] == ["Room 2"]
    assert [e.matched_faculty for e in got] == ["NA"]


@pytest.mark.database
def test_capacity_and_type_do_not_filter(session, facility_fixture):
    # No capacity rule and no Type-to-Theory/Practical mapping has been
    # approved, so neither may quietly remove a room from the result.
    got = eligible_facilities(session, qualification_code="SIT30821", weekday="FRIDAY")
    assert [e.facility.facility_reference for e in got] == ["Room 1"]
    assert got[0].facility.capacity == 12
    assert got[0].facility.facility_type == "Campus"


@pytest.mark.database
def test_an_unknown_weekday_is_refused_rather_than_treated_as_unavailable(
    session, facility_fixture
):
    with pytest.raises(ValueError):
        eligible_facilities(session, qualification_code="BSB50420", weekday="SATURDAY")


# ------------------------------------------------------------------ API

VIEWER = "fac.viewer@chelsongordon.com"


def as_user(email: str) -> dict[str, str]:
    return {deps.MOCK_USER_HEADER: email}


@pytest.fixture()
def api(test_factory, session):
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
    claims = mock_claims_for(VIEWER)
    session.add(
        User(
            organisation_email=VIEWER,
            display_name="Facility Viewer",
            access_level="VIEWER",
            account_status="ACTIVE",
            entra_object_id=claims.object_id,
            entra_tenant_id=claims.tenant_id,
        )
    )
    session.commit()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.mark.database
def test_facilities_require_a_signed_in_user(api):
    assert api.get("/reference/facilities").status_code == 401


@pytest.mark.database
def test_a_viewer_can_read_facilities(api, facility_fixture):
    response = api.get("/reference/facilities", headers=as_user(VIEWER))
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3

    room = next(r for r in rows if r["facility_reference"] == "Room 2")
    # State and campus name are read through the campus, never stored twice.
    assert room["state"] == "NSW"
    assert room["campus_name"] == "Test Campus"
    assert room["capacity"] == 30
    assert room["college_short_names"] == ["TESTAIBT"]
    assert room["faculties"][0]["faculty"] == "NA"
    assert room["faculties"][0]["monday"] is True
    assert room["faculties"][0]["remarks"] == "Shared"


@pytest.mark.database
def test_the_eligible_endpoint_applies_both_rules(api, facility_fixture):
    response = api.get(
        "/reference/facilities/eligible",
        params={"qualification_code": "BSB50420", "weekday": "MONDAY"},
        headers=as_user(VIEWER),
    )
    assert response.status_code == 200
    assert {r["facility_reference"] for r in response.json()} == {"Room 1", "Room 2"}


@pytest.mark.database
def test_a_weekend_day_is_refused(api, facility_fixture):
    # Saturday and Sunday rules are not part of the supplied schema.
    response = api.get(
        "/reference/facilities/eligible",
        params={"qualification_code": "BSB50420", "weekday": "SUNDAY"},
        headers=as_user(VIEWER),
    )
    assert response.status_code == 422
