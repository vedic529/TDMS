"""The Campus Address Dictionary (approved 16 September 2026).

A full address is identified by college + campus. The case that matters most is
A1: one campus name holding a different building for each college, which a
single address on the campus could not express.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.models.user import User
from app.services import campus_addresses as service
from app.services.reference_data import NotFound, ReferenceDataError

from tests.test_trainer_api import (  # reuse the approved fixtures
    ADMIN,
    VIEWER,
    as_user,
    client,  # noqa: F401 - fixture
    people,  # noqa: F401 - fixture
    refs,  # noqa: F401 - fixture
)

pytestmark = pytest.mark.database


@pytest.fixture()
def colleges(session, refs):
    """Two test colleges with no approved campuses yet."""

    def college(short):
        found = session.execute(
            text("SELECT id FROM colleges WHERE college_short_name = :s"), {"s": short}
        ).scalar_one_or_none()
        if found is None:
            found = session.execute(
                text(
                    "INSERT INTO colleges (college_short_name, college_full_name, is_active) "
                    "VALUES (:s, :s, true) RETURNING id"
                ),
                {"s": short},
            ).scalar_one()
        session.execute(text("DELETE FROM college_campuses WHERE college_id = :c"), {"c": found})
        return found

    ids = {"quay": college("T_QUAY"), "george": college("T_GEORGE")}
    session.execute(
        text(
            "DELETE FROM campus_source_addresses WHERE source_address IN "
            "('Level 2, 8 Quay St, HAYMARKET, New South Wales 2000', '841 George St Haymarket 2000')"
        )
    )
    session.commit()
    campus = lambda code: session.execute(  # noqa: E731
        text("SELECT id FROM campuses WHERE campus_code = :c"), {"c": code}
    ).scalar_one()
    return {**ids, "haymarket": campus("T_HM"), "blacktown": campus("T_BT")}


def _admin(session) -> User:
    return session.query(User).filter_by(organisation_email=ADMIN).one()


def _entry(session, college_id, campus_id):
    return next(
        row
        for row in service.list_entries(session)
        if row["college_id"] == college_id and row["campus_id"] == campus_id
    )


def test_a1_one_campus_name_is_a_different_building_per_college(session, colleges):
    """A1 - Haymarket is Quay St for one college and George St for another."""
    user = _admin(session)
    quay = "Level 2, 8 Quay St, HAYMARKET, New South Wales 2000"
    george = "841 George St Haymarket 2000"
    service.save_entry(
        session, user, {"college_id": colleges["quay"], "campus_id": colleges["haymarket"], "address": quay},
        creating=True,
    )
    service.save_entry(
        session, user,
        {"college_id": colleges["george"], "campus_id": colleges["haymarket"], "address": george},
        creating=True,
    )
    session.commit()

    assert _entry(session, colleges["quay"], colleges["haymarket"])["address"] == quay
    assert _entry(session, colleges["george"], colleges["haymarket"])["address"] == george


def test_a2_adding_an_address_approves_the_combination_and_records_the_spelling(session, colleges):
    """A2 - the address is the approval, and a file writing it then resolves."""
    service.save_entry(
        session, _admin(session),
        {"college_id": colleges["quay"], "campus_id": colleges["haymarket"],
         "address": "  Level 2,  8 Quay St, HAYMARKET, New South Wales 2000 "},
        creating=True,
    )
    session.commit()

    approved = session.execute(
        text("SELECT address FROM college_campuses WHERE college_id = :c AND campus_id = :p"),
        {"c": colleges["quay"], "p": colleges["haymarket"]},
    ).scalar_one()
    assert approved == "Level 2, 8 Quay St, HAYMARKET, New South Wales 2000", "spacing is tidied"
    spelling_campus = session.execute(
        text("SELECT campus_id FROM campus_source_addresses WHERE source_address = :a"),
        {"a": approved},
    ).scalar_one()
    assert spelling_campus == colleges["haymarket"]


def test_a3_an_address_of_another_campus_is_refused(session, colleges):
    """A3 - one address cannot name two campuses."""
    with pytest.raises(service.AddressConflict) as refused:
        service.save_entry(
            session, _admin(session),
            # Recorded for Haymarket by the shared fixture.
            {"college_id": colleges["quay"], "campus_id": colleges["blacktown"],
             "address": "841 george st, haymarket nsw 2000"},
            creating=True,
        )
    assert "Haymarket" in str(refused.value)


def test_a4_colleges_can_share_one_building(session, colleges):
    """A4 - Hobart is one address for four colleges; sharing is not a conflict."""
    user = _admin(session)
    shared = "Level 2, 8 Quay St, HAYMARKET, New South Wales 2000"
    for key in ("quay", "george"):
        service.save_entry(
            session, user,
            {"college_id": colleges[key], "campus_id": colleges["haymarket"], "address": shared},
            creating=True,
        )
    session.commit()
    assert _entry(session, colleges["george"], colleges["haymarket"])["address"] == shared


def test_a5_an_entry_is_added_once_and_edited_after(session, colleges):
    """A5 - adding the same pair twice is refused; editing changes it."""
    user = _admin(session)
    values = {"college_id": colleges["quay"], "campus_id": colleges["haymarket"],
              "address": "Level 2, 8 Quay St, HAYMARKET, New South Wales 2000"}
    service.save_entry(session, user, values, creating=True)
    with pytest.raises(service.AddressConflict):
        service.save_entry(session, user, values, creating=True)

    edited = service.save_entry(
        session, user, {**values, "address": "841 George St Haymarket 2000"}, creating=False
    )
    assert edited["address"] == "841 George St Haymarket 2000"

    with pytest.raises(NotFound):
        service.save_entry(
            session, user,
            {"college_id": colleges["george"], "campus_id": colleges["blacktown"], "address": "x"},
            creating=False,
        )
    with pytest.raises(ReferenceDataError):
        service.save_entry(session, user, {**values, "address": "   "}, creating=False)


def test_a6_anyone_reads_the_dictionary_and_only_maintainers_change_it(session, colleges, client):
    """A6 - the same access as the City Dictionary."""
    listed = client.get("/reference/campus-addresses", headers=as_user(VIEWER))
    assert listed.status_code == 200

    body = {"college_id": colleges["quay"], "campus_id": colleges["haymarket"],
            "address": "Level 2, 8 Quay St, HAYMARKET, New South Wales 2000"}
    assert client.post("/reference/campus-addresses", json=body, headers=as_user(VIEWER)).status_code == 403

    created = client.post("/reference/campus-addresses", json=body, headers=as_user(ADMIN))
    assert created.status_code == 201, created.text
    assert created.json()["address"] == body["address"]

    moved = client.put(
        f"/reference/campus-addresses/{colleges['quay']}/{colleges['blacktown']}",
        json={**body, "campus_id": colleges["blacktown"]},
        headers=as_user(ADMIN),
    )
    assert moved.status_code == 404, "editing cannot create a pair that is not in the dictionary"
