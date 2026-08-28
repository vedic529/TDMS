"""The Location Dictionary (checks L1 to L5).

State -> City -> Campus -> Full Address, built on `campuses` rather than a
second location table. The check that matters most is L2: a campus with no city
must appear and say so, because inventing one would be indistinguishable from
data.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event, text

from app.services import trainers as service

from tests.test_trainer_api import (  # reuse the approved fixtures
    ADMIN,
    VIEWER,
    as_user,
    client,  # noqa: F401 - fixture
    people,  # noqa: F401 - fixture
    refs,  # noqa: F401 - fixture
)

pytestmark = pytest.mark.database


def _count_queries(session, work):
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(session.bind, "before_cursor_execute", record)
    try:
        result = work()
    finally:
        event.remove(session.bind, "before_cursor_execute", record)
    return result, len(seen)


def test_l1_the_dictionary_is_state_then_city_then_campus(session, refs):
    """L1 — the nesting the display needs, in one query."""
    states, count = _count_queries(session, lambda: service.location_dictionary(session))
    assert count == 1, f"{count} statements; not one query per state"

    nsw = next(entry for entry in states if entry["state"] == "NSW")
    sydney = next(city for city in nsw["cities"] if city["city"] == "Sydney")
    # Scoped to this fixture's campuses: `campuses` is shared with other suites.
    names = [
        campus["campus_name"]
        for campus in sydney["campuses"]
        if campus["campus_code"].startswith("T_")
    ]
    assert names == ["Blacktown", "Haymarket"]


def test_l2_a_campus_with_no_city_appears_and_is_not_invented(session, refs):
    """L2 — grouped under a null city. The client renders "City not recorded"."""
    states = service.location_dictionary(session)
    qld = next(entry for entry in states if entry["state"] == "QLD")
    unnamed = [city for city in qld["cities"] if city["city"] is None]
    assert len(unnamed) == 1, "the campus must appear, under a null city"
    assert "Bundaberg Central" in [c["campus_name"] for c in unnamed[0]["campuses"]]

    # And nothing was written into the column to make it tidy.
    stored = session.execute(
        text("SELECT city FROM campuses WHERE campus_code = 'T_NC'")
    ).scalar_one()
    assert stored is None


def test_l3_every_spelling_of_an_address_is_returned(session, refs):
    """L3 — one site is written several ways across the sources."""
    states = service.location_dictionary(session)
    haymarket = next(
        campus
        for entry in states
        for city in entry["cities"]
        for campus in city["campuses"]
        if campus["campus_name"] == "Haymarket"
    )
    assert sorted(haymarket["source_addresses"]) == [
        "841 George St, Haymarket NSW 2000",
        "Level 2, 8 Quay St",
    ]
    assert haymarket["approved_address"] == "841 George St", "the one approved form"


def test_l4_ordering_is_state_then_city_then_campus_name(session, refs):
    states = service.location_dictionary(session)
    assert [entry["state"] for entry in states] == sorted(entry["state"] for entry in states)
    for entry in states:
        cities = [city["city"] for city in entry["cities"]]
        # A null city sorts last, so "City not recorded" sits at the foot.
        assert cities == sorted(cities, key=lambda value: (value is None, value or ""))
        for city in entry["cities"]:
            names = [campus["campus_name"] for campus in city["campuses"]]
            assert names == sorted(names)


def test_l5_a_viewer_may_read_the_dictionary(client, refs):
    """L5 — reading reference data is Viewer and above."""
    response = client.get("/reference/locations", headers=as_user(VIEWER))
    assert response.status_code == 200
    states = response.json()
    assert any(entry["state"] == "NSW" for entry in states)

    # And an Admin sees the same thing; this is not a maintenance endpoint.
    assert client.get("/reference/locations", headers=as_user(ADMIN)).status_code == 200


def test_the_dictionary_is_not_a_second_location_table(session):
    """A parallel table would split one place across two records."""
    tables = {
        row[0]
        for row in session.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        ).all()
    }
    assert not any(
        name in tables for name in ("locations", "location_dictionary", "campus_locations")
    ), "the dictionary extends `campuses`; a second table would break the clash checks"
