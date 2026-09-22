"""Trainer list, detail and unit coverage (checks 3.3, 3.4, 3.5).

The fixtures are built from the **real shapes** in `Trainer Data - BSB.xlsx`,
not a happy path: a trainer at two campuses, an offshore trainer, a unit taught
under two qualifications, a unit no trainer covers, and an inactive trainer.
A happy-path fixture would pass every one of these checks while the defects they
exist to catch stayed in place.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text

from app.api import deps
from app.auth.mock import mock_claims_for
from app.core.config import Settings, get_settings
from app.main import app
from app.models.trainer import Trainer, TrainerAvailability, TrainerUnit
from app.models.user import User
from app.services import trainers as service

pytestmark = pytest.mark.database

VIEWER = "trn.viewer@chelsongordon.com"
EDITOR = "trn.editor@chelsongordon.com"
ADMIN = "trn.admin@chelsongordon.com"

NINE_TO_FIVE = (dt.time(9, 0), dt.time(17, 0))


def as_user(email: str) -> dict[str, str]:
    return {"X-TDMS-Mock-User": email}


@pytest.fixture()
def people(session):
    session.execute(text("TRUNCATE TABLE user_activity_records, users RESTART IDENTITY CASCADE"))
    for email, level in ((VIEWER, "VIEWER"), (EDITOR, "DATA_EDITOR"), (ADMIN, "ADMIN")):
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
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="development", auth_mode="mock"
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def refs(session, people):
    """Campuses, qualifications and units, cleared of any prior trainer data.

    The trainer tables are not in the shared truncate set, so this clears what
    it is about to write rather than colliding with the previous test's copy.
    """
    for table in ("trainer_units", "trainer_qualifications", "trainer_availability"):
        session.execute(text(f"DELETE FROM {table}"))
    session.execute(text("DELETE FROM trainers"))
    # Only this fixture's own campuses are touched. `campuses` is shared — other
    # suites' facilities and offerings point at it — so wiping the table would
    # break them, and every assertion below is scoped to the `T_` codes.
    session.execute(
        text(
            "DELETE FROM campus_source_addresses WHERE campus_id IN "
            "(SELECT id FROM campuses WHERE campus_code IN ('T_BT', 'T_HM', 'T_HB', 'T_NC'))"
        )
    )
    session.commit()

    # Since 15 September 2026 `campuses.city` references the City Dictionary.
    session.execute(
        text(
            "INSERT INTO cities (city_name, state) VALUES ('Sydney', 'NSW'), ('Hobart', 'TAS') "
            "ON CONFLICT (city_name) DO NOTHING"
        )
    )

    def campus(code, name, location, state, city, address=None):
        """Get-or-create, then set the dictionary columns to a known state."""
        found = session.execute(
            text("SELECT id FROM campuses WHERE campus_code = :c"), {"c": code}
        ).scalar_one_or_none()
        if found:
            session.execute(
                text(
                    "UPDATE campuses SET campus_name = :n, campus_location = :l, state = :s, "
                    "city = :city, approved_address = :a WHERE id = :id"
                ),
                {"n": name, "l": location, "s": state, "city": city, "a": address, "id": found},
            )
            return found
        return session.execute(
            text(
                "INSERT INTO campuses (campus_code, campus_name, campus_location, state, city, "
                "approved_address, is_active) VALUES (:c, :n, :l, :s, :city, :a, true) RETURNING id"
            ),
            {"c": code, "n": name, "l": location, "s": state, "city": city, "a": address},
        ).scalar_one()

    blacktown = campus("T_BT", "Blacktown", "125 Main St BLACKTOWN", "NSW", "Sydney", "125 Main St")
    haymarket = campus("T_HM", "Haymarket", "841 George St", "NSW", "Sydney", "841 George St")
    hobart = campus("T_HB", "Hobart", "132 Elizabeth St", "TAS", "Hobart")
    # A campus with no city, so the dictionary must report it rather than guess.
    nocity = campus("T_NC", "Bundaberg Central", "10 Quay St", "QLD", None)

    session.execute(
        text("INSERT INTO campus_source_addresses (campus_id, source_address) VALUES (:p, :a)"),
        [
            {"p": haymarket, "a": "841 George St, Haymarket NSW 2000"},
            {"p": haymarket, "a": "Level 2, 8 Quay St"},
        ],
    )

    def qualification(code, title):
        # Get-or-create: `qualifications` is not in the shared truncate set and
        # is referenced by other subsystems, so it is reused rather than deleted.
        found = session.execute(
            text("SELECT id FROM qualifications WHERE qualification_code = :c"), {"c": code}
        ).scalar_one_or_none()
        if found:
            return found
        return session.execute(
            text(
                "INSERT INTO qualifications (qualification_code, qualification_title, is_active) "
                "VALUES (:c, :t, true) RETURNING id"
            ),
            {"c": code, "t": title},
        ).scalar_one()

    def unit(code, title):
        found = session.execute(
            text("SELECT id FROM units WHERE unit_code = :c"), {"c": code}
        ).scalar_one_or_none()
        if found:
            return found
        return session.execute(
            text("INSERT INTO units (unit_code, unit_title, is_active) VALUES (:c, :t, true) RETURNING id"),
            {"c": code, "t": title},
        ).scalar_one()

    bsb40920 = qualification("BSB40920", "Certificate IV in Project Management")
    bsb50820 = qualification("BSB50820", "Diploma of Project Management")
    fns40222 = qualification("FNS40222", "Certificate IV in Accounting")

    shared = unit("BSBPMG533", "Manage project cost")
    only40920 = unit("BSBPMG421", "Apply project scope")
    fns_unit = unit("FNSACC601", "Prepare tax documentation")
    # A unit no trainer covers — the gap Unit Coverage exists to show.
    orphan = unit("T_BSBUNCOV", "Nobody teaches this")

    session.execute(
        text("DELETE FROM qualification_units WHERE qualification_id IN (:a, :b, :c)"),
        {"a": bsb40920, "b": bsb50820, "c": fns40222},
    )
    for qual, unit_id in (
        (bsb40920, shared),
        (bsb40920, only40920),
        (bsb40920, orphan),
        (bsb50820, shared),
        (fns40222, fns_unit),
    ):
        session.execute(
            text(
                # `delivery_order` stays NULL: membership is what these tests
                # need, and a sequence comes from an approved timetable source.
                "INSERT INTO qualification_units (qualification_id, unit_id, is_deleted) "
                "VALUES (:q, :u, false)"
            ),
            {"q": qual, "u": unit_id},
        )
    session.commit()
    return {
        "blacktown": blacktown,
        "haymarket": haymarket,
        "hobart": hobart,
        "nocity": nocity,
        "bsb40920": bsb40920,
        "bsb50820": bsb50820,
        "fns40222": fns40222,
        "shared": shared,
        "only40920": only40920,
        "fns_unit": fns_unit,
        "orphan": orphan,
    }


@pytest.fixture()
def loaded(session, refs):
    """Nine-trainer shapes drawn from the real file, in miniature."""

    def trainer(code, name, active=True):
        row = Trainer(trainer_id=code, trainer_name=name, is_active=active)
        session.add(row)
        session.flush()
        return row.id

    def location(trainer_pk, campus_id=None, *, offshore=False, text_value=None):
        session.add(
            TrainerAvailability(
                trainer_id=trainer_pk,
                campus_id=campus_id,
                is_offshore=offshore,
                location_text="Offshore" if offshore else text_value,
                location_type="Campus",
                class_type="THEORY",
                working_time_start=NINE_TO_FIVE[0],
                working_time_end=NINE_TO_FIVE[1],
                working_time_text="9:00 AM to 5:00 PM AEST/AEDT",
                monday="PHYSICAL",
                tuesday="PHYSICAL",
                wednesday="NOT_AVAILABLE",
                thursday="NOT_AVAILABLE",
                friday="VIRTUAL",
            )
        )

    # Two campuses, one trainer — still one row in the list (1.5).
    two = trainer("TI_002_EN", "Ertajul Noorani")
    location(two, refs["blacktown"])
    location(two, refs["haymarket"])

    # Offshore: no campus at all, and not an unresolved one (1.3).
    off = trainer("TI_008_NK", "Dr. Nisha Kalra")
    location(off, None, offshore=True)

    solo = trainer("TI_003_MS", "M. Sajed")
    location(solo, refs["hobart"])

    # Inactive, so unit coverage must not count them (U4).
    idle = trainer("TI_009_SH", "Sleepy Trainer", active=False)
    location(idle, refs["hobart"])

    session.flush()
    # The shared unit under two qualifications — two rows, never collapsed.
    session.add_all(
        [
            TrainerUnit(trainer_id=two, qualification_id=refs["bsb40920"], unit_id=refs["shared"]),
            TrainerUnit(trainer_id=two, qualification_id=refs["bsb50820"], unit_id=refs["shared"]),
            TrainerUnit(trainer_id=two, qualification_id=refs["bsb40920"], unit_id=refs["only40920"]),
            # A trainer whose only qualification is FNS, from a BSB file (1.7).
            TrainerUnit(trainer_id=off, qualification_id=refs["fns40222"], unit_id=refs["fns_unit"]),
            TrainerUnit(trainer_id=solo, qualification_id=refs["bsb40920"], unit_id=refs["shared"]),
            TrainerUnit(trainer_id=idle, qualification_id=refs["bsb40920"], unit_id=refs["only40920"]),
        ]
    )
    session.flush()
    service.rebuild_trainer_qualifications(session, [two, off, solo, idle])
    session.commit()
    return {"two": two, "off": off, "solo": solo, "idle": idle}


def _count_queries(session, work):
    """How many statements a call issues. Flatness is the whole point."""
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(session.bind, "before_cursor_execute", record)
    try:
        result = work()
    finally:
        event.remove(session.bind, "before_cursor_execute", record)
    return result, len(seen)


# ===========================================================================
# 3.3 Trainer list and detail
# ===========================================================================


def test_t1_one_row_per_trainer_not_per_location(session, loaded):
    """T1 — a trainer at two campuses is still one row (1.5)."""
    items, total = service.list_trainers(session)
    assert total == 4, "four trainers, not five rows for five locations"
    codes = [item["trainer_id"] for item in items]
    assert codes.count("TI_002_EN") == 1


def test_t2_two_locations_are_summarised_on_one_row(session, loaded):
    """T2 — location_count 2, and both campuses named."""
    items, _ = service.list_trainers(session, search="TI_002_EN")
    row = items[0]
    assert row["location_count"] == 2
    assert "Blacktown" in row["location_summary"]
    assert "Haymarket" in row["location_summary"]


def test_t3_training_packages_are_derived_never_stored(session, loaded, refs):
    """T3 — a trainer in a BSB file who teaches only FNS reads as FNS.

    The real file contains exactly this: `TI_008_NK` teaches three FNS
    qualifications and nothing else. Nothing anywhere stores a package.
    """
    items, _ = service.list_trainers(session, search="TI_008_NK")
    assert items[0]["training_packages"] == ["FNS"], "an FNS-only trainer in a BSB file"
    detail = service.get_trainer(session, loaded["off"])
    assert detail["training_packages"] == ["FNS"]

    # A second qualification from another package appears alongside, not instead.
    # The real file has no such trainer, so the case is built rather than assumed.
    session.add(
        TrainerUnit(
            trainer_id=loaded["off"], qualification_id=refs["bsb40920"], unit_id=refs["shared"]
        )
    )
    session.flush()
    items, _ = service.list_trainers(session, search="TI_008_NK")
    assert items[0]["training_packages"] == ["BSB", "FNS"], "a trainer is not tied to one package"

    # And nothing stores it: the column simply does not exist.
    columns = {
        row[0]
        for row in session.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'trainers'")
        ).all()
    }
    assert not any("package" in name for name in columns)


def test_t4_detail_is_one_round_trip_with_everything_nested(session, loaded):
    """T4 — locations with their weekdays, qualifications with their units."""
    detail = service.get_trainer(session, loaded["two"])
    assert len(detail["locations"]) == 2
    first = detail["locations"][0]
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        assert day in first, "every weekday is present without a second request"
    assert len(detail["qualifications"]) == 2
    assert all("units" in group for group in detail["qualifications"])
    assert sum(len(g["units"]) for g in detail["qualifications"]) == 3


def test_t5_list_query_count_does_not_grow_with_the_data(session, loaded, refs):
    """T5 — flat. The allocation importer's per-row lookup is the mistake."""
    _, few = _count_queries(session, lambda: service.list_trainers(session))

    for index in range(20):
        pk = session.execute(
            text(
                "INSERT INTO trainers (trainer_id, trainer_name, is_active, is_deleted) "
                "VALUES (:c, 'Bulk', true, false) RETURNING id"
            ),
            {"c": f"BULK{index:03d}"},
        ).scalar_one()
        session.add(
            TrainerAvailability(
                trainer_id=pk,
                campus_id=refs["hobart"],
                class_type="THEORY",
                working_time_start=NINE_TO_FIVE[0],
                working_time_end=NINE_TO_FIVE[1],
                monday="PHYSICAL",
                tuesday="PHYSICAL",
                wednesday="PHYSICAL",
                thursday="PHYSICAL",
                friday="PHYSICAL",
            )
        )
        session.add(
            TrainerUnit(
                trainer_id=pk, qualification_id=refs["bsb40920"], unit_id=refs["only40920"]
            )
        )
    session.flush()

    result, many = _count_queries(session, lambda: service.list_trainers(session, limit=100))
    assert result[1] == 24, "the extra trainers really are in the list"
    assert many == few, f"query count grew from {few} to {many} with the data"


def test_t6_detail_query_count_is_a_small_fixed_number(session, loaded):
    """T6 — not one query per qualification."""
    _, count = _count_queries(session, lambda: service.get_trainer(session, loaded["two"]))
    assert count <= 4, f"{count} statements for one side panel"


def test_t7_the_offshore_trainer_is_offshore_not_unresolved(session, loaded):
    """T7 — no campus, marked Offshore, and not marked unresolved."""
    detail = service.get_trainer(session, loaded["off"])
    location = detail["locations"][0]
    assert location["campus_id"] is None
    assert location["is_offshore"] is True
    assert location["campus_name"] is None
    assert location["location_text"] == "Offshore"

    items, _ = service.list_trainers(session, search="TI_008_NK")
    assert items[0]["location_summary"] == "Offshore"


def test_t8_filter_by_qualification_uses_the_join(session, loaded, refs):
    """T8 — only trainers approved for it, through `trainer_qualifications`."""
    items, total = service.list_trainers(session, qualification_id=refs["fns40222"])
    assert total == 1
    assert items[0]["trainer_id"] == "TI_008_NK"


def test_a_trainer_filter_by_campus_finds_both_of_their_locations(session, loaded, refs):
    for campus in ("blacktown", "haymarket"):
        items, _ = service.list_trainers(session, campus_id=refs[campus])
        assert "TI_002_EN" in [i["trainer_id"] for i in items]


# ===========================================================================
# 3.5 Unit coverage
# ===========================================================================


def test_u1_every_unit_appears_including_those_with_no_trainer(session, loaded, refs):
    """U1 — outer-joined from units. A gap that is invisible is not a gap."""
    items, _ = service.unit_coverage(session)
    codes = {item["unit_code"] for item in items}
    assert "T_BSBUNCOV" in codes, "a unit with no trainer must still be listed"


def test_u2_a_unit_with_no_trainer_reports_zero(session, loaded):
    items, _ = service.unit_coverage(session)
    orphan = next(i for i in items if i["unit_code"] == "T_BSBUNCOV")
    assert orphan["trainer_count"] == 0
    assert orphan["trainer_names"] == []


def test_u3_a_covered_unit_counts_its_trainers(session, loaded, refs):
    items, _ = service.unit_coverage(session, qualification_id=refs["bsb40920"])
    shared = next(i for i in items if i["unit_code"] == "BSBPMG533")
    assert shared["trainer_count"] == 2, "two active trainers teach it under BSB40920"
    assert sorted(shared["trainer_names"]) == ["Ertajul Noorani", "M. Sajed"]


def test_u4_an_inactive_trainer_is_not_counted(session, loaded, refs):
    """U4 — an inactive trainer must not make a gap look covered."""
    items, _ = service.unit_coverage(session, qualification_id=refs["bsb40920"])
    only = next(i for i in items if i["unit_code"] == "BSBPMG421")
    assert only["trainer_count"] == 1, "the inactive trainer is excluded"
    assert "Sleepy Trainer" not in only["trainer_names"]


def test_u5_coverage_is_one_grouped_query(session, loaded):
    """U5 — regardless of unit count."""
    _, count = _count_queries(session, lambda: service.unit_coverage(session))
    assert count <= 2, f"{count} statements; coverage must be one grouped query plus its count"


def test_u6_default_sort_puts_the_gaps_first(session, loaded):
    """U6 — trainer count ascending, so what is uncovered is read first."""
    items, _ = service.unit_coverage(session)
    counts = [item["trainer_count"] for item in items]
    assert counts == sorted(counts)
    assert items[0]["trainer_count"] == 0


def test_only_uncovered_filters_to_the_gaps(session, loaded):
    items, total = service.unit_coverage(session, only_uncovered=True)
    assert total >= 1
    assert all(item["trainer_count"] == 0 for item in items)


# ===========================================================================
# 3.4 Side panel behaviour that the API must support
# ===========================================================================


def test_s8_add_units_takes_one_qualification_and_many_units_in_one_call(
    session, loaded, refs, people
):
    """S8 — and `trainer_qualifications` follows automatically (2.3)."""
    admin = session.execute(select(User).where(User.organisation_email == ADMIN)).scalar_one()
    detail = service.add_units(
        session,
        loaded["solo"],
        data={"qualification_id": refs["bsb50820"], "unit_ids": [refs["shared"], refs["only40920"]]},
        user=admin,
    )
    group = next(
        g for g in detail["qualifications"] if g["qualification_id"] == refs["bsb50820"]
    )
    assert len(group["units"]) == 2
    held = session.execute(
        text("SELECT count(*) FROM trainer_qualifications WHERE trainer_id = :t"),
        {"t": loaded["solo"]},
    ).scalar_one()
    assert held == 2, "the derived join now holds both qualifications"


def test_s7_add_location_accepts_offshore_and_refuses_a_campus_with_it(session, loaded, people):
    admin = session.execute(select(User).where(User.organisation_email == ADMIN)).scalar_one()
    detail = service.add_location(
        session,
        loaded["solo"],
        data={
            "is_offshore": True,
            "campus_id": None,
            "class_type": "THEORY_AND_PRACTICAL",
            "working_time_start": dt.time(13, 0),
            "working_time_end": dt.time(21, 0),
            "monday": "VIRTUAL",
            "tuesday": "NOT_AVAILABLE",
            "wednesday": "NOT_AVAILABLE",
            "thursday": "NOT_AVAILABLE",
            "friday": "NOT_AVAILABLE",
        },
        user=admin,
    )
    added = [row for row in detail["locations"] if row["is_offshore"]]
    assert len(added) == 1
    assert added[0]["class_type"] == "THEORY_AND_PRACTICAL", "the third class type stores"

    with pytest.raises(service.TrainerError):
        service.add_location(
            session,
            loaded["solo"],
            data={
                "is_offshore": True,
                "campus_id": 1,
                "class_type": "THEORY",
                "working_time_start": dt.time(9, 0),
                "working_time_end": dt.time(17, 0),
            },
            user=admin,
        )


# ===========================================================================
# 3.8 Access (G8)
# ===========================================================================


def test_g8_reading_is_viewer_and_maintaining_is_admin(client, loaded):
    """Reading is Viewer; maintaining resolves through the capability."""
    assert client.get("/trainers", headers=as_user(VIEWER)).status_code == 200
    assert client.get("/trainers/unit-coverage", headers=as_user(VIEWER)).status_code == 200
    assert client.get(f"/trainers/{loaded['two']}", headers=as_user(VIEWER)).status_code == 200

    # No `trainer_id`: it is generated. The city is required.
    payload = {"trainer_name": "New Person", "city": "Sydney"}
    assert client.post("/trainers", json=payload, headers=as_user(VIEWER)).status_code == 403
    # A Data Editor maintains students and timetables, not trainers.
    assert client.post("/trainers", json=payload, headers=as_user(EDITOR)).status_code == 403
    assert client.post("/trainers", json=payload, headers=as_user(ADMIN)).status_code == 201


def test_unit_coverage_route_is_not_captured_by_the_id_route(client, loaded):
    """The literal path must be declared first, or this returns a 404 or 422."""
    response = client.get("/trainers/unit-coverage", headers=as_user(VIEWER))
    assert response.status_code == 200
    assert "items" in response.json()


# ===========================================================================
# The generated trainer id (approved 27 August 2026)
# ===========================================================================


@pytest.mark.parametrize(
    ("name", "initials"),
    [
        ("Arsalan Yusuf", "AY"),
        ("M. Sajed", "MS"),
        # A title is not part of a name.
        ("Dr. Navdeep Verma", "NV"),
        ("Dr. Nisha Kalra", "NK"),
        ("Prof. Ada Lovelace", "AL"),
        # One word gives its first two letters.
        ("Arsalan", "AR"),
        ("Dr. Nisha", "NI"),
        # Three or more still take only the first two words.
        ("Syed Habibullah Khan", "SH"),
        ("  Waqar   Ahmad  ", "WA"),
    ],
)
def test_initials_follow_the_approved_rule(name, initials):
    assert service.trainer_initials(name) == initials


def test_the_sequence_continues_from_the_highest_ever_used(session, loaded):
    """The fixture's highest is `TI_009_SH`, so a new trainer is TI_010."""
    highest = session.execute(
        select(func.max(Trainer.trainer_id))
    ).scalar_one()
    assert highest == "TI_009_SH"
    assert service.generate_trainer_id(session, "Arsalan Yusuf") == "TI_010_AY"


def test_an_id_is_never_handed_to_a_second_trainer(session, refs, people):
    """Deleting a trainer retires their number with them."""
    admin = session.execute(select(User).where(User.organisation_email == ADMIN)).scalar_one()
    first = service.create_trainer(
        session, data={"trainer_name": "Arsalan Yusuf", "city": "Sydney"}, user=admin
    )
    assert first["trainer_id"] == "TI_001_AY"

    reason = session.execute(text("SELECT id FROM reason_codes LIMIT 1")).scalar_one_or_none()
    if reason is None:
        reason = session.execute(
            text(
                "INSERT INTO reason_codes (code, label, is_active) "
                "VALUES ('T_ERR', 'Entered in error', true) RETURNING id"
            )
        ).scalar_one()
    service.delete_trainer(
        session, first["id"], reason_code_id=reason, reason_note=None, user=admin
    )
    session.flush()

    second = service.create_trainer(
        session, data={"trainer_name": "Bilal Zaman", "city": "Sydney"}, user=admin
    )
    assert second["trainer_id"] == "TI_002_BZ", "the retired number is not reused"


def test_an_imported_id_moves_the_sequence_on(session, refs):
    """Ids also arrive by bulk import, so the highest wins wherever it came from."""
    session.add(Trainer(trainer_id="TI_050_XY", trainer_name="Imported Person"))
    session.flush()
    assert service.generate_trainer_id(session, "New Person") == "TI_051_NP"


def test_a_trainer_needs_a_name_and_a_city(session, refs, people):
    admin = session.execute(select(User).where(User.organisation_email == ADMIN)).scalar_one()
    with pytest.raises(service.TrainerError):
        service.create_trainer(session, data={"trainer_name": "", "city": "Sydney"}, user=admin)
    with pytest.raises(service.TrainerError):
        service.create_trainer(session, data={"trainer_name": "No City", "city": ""}, user=admin)


def test_a_trainer_can_be_created_with_neither_location_nor_units(session, refs, people):
    """Both are optional: a trainer may be recorded before their timetable is."""
    admin = session.execute(select(User).where(User.organisation_email == ADMIN)).scalar_one()
    detail = service.create_trainer(
        session, data={"trainer_name": "Bare Record", "city": "Hobart"}, user=admin
    )
    assert detail["locations"] == []
    assert detail["qualifications"] == []
    assert detail["city"] == "Hobart"


def test_a_location_and_units_may_be_supplied_on_the_same_form(session, refs, people):
    admin = session.execute(select(User).where(User.organisation_email == ADMIN)).scalar_one()
    detail = service.create_trainer(
        session,
        data={
            "trainer_name": "Full Record",
            "city": "Sydney",
            "locations": [{
                "campus_id": refs["haymarket"],
                "is_offshore": False,
                "class_type": "THEORY",
                "working_time_start": dt.time(9, 0),
                "working_time_end": dt.time(17, 0),
                "monday": "PHYSICAL",
                "tuesday": "NOT_AVAILABLE",
                "wednesday": "NOT_AVAILABLE",
                "thursday": "NOT_AVAILABLE",
                "friday": "NOT_AVAILABLE",
            }],
            "units": [{"qualification_id": refs["bsb40920"], "unit_ids": [refs["shared"]]}],
        },
        user=admin,
    )
    assert len(detail["locations"]) == 1
    assert len(detail["qualifications"]) == 1
    assert detail["locations"][0]["monday"] == "PHYSICAL"


def test_the_preview_reserves_nothing(client, loaded):
    """Two people on the form both see TI_005; only one can take it."""
    first = client.get("/trainers/next-id?name=Arsalan Yusuf", headers=as_user(VIEWER))
    second = client.get("/trainers/next-id?name=Bilal Zaman", headers=as_user(VIEWER))
    assert first.status_code == 200
    assert first.json()["initials"] == "AY"
    assert second.json()["initials"] == "BZ"
    assert first.json()["sequence"] == second.json()["sequence"], "a preview holds nothing"


# ===========================================================================
# Clearing the trainer database
# ===========================================================================


def test_only_a_super_admin_may_clear_the_trainer_database(client, loaded):
    assert client.delete("/trainers/records", headers=as_user(VIEWER)).status_code == 403
    assert client.delete("/trainers/records", headers=as_user(ADMIN)).status_code == 403
    assert client.get("/trainers/records/clear-preview", headers=as_user(ADMIN)).status_code == 403


def test_clearing_empties_the_trainer_database_and_restarts_numbering(session, refs, people, loaded):
    """Approved 27 August 2026: a clear is a fresh start, numbering included."""
    admin = session.execute(select(User).where(User.organisation_email == ADMIN)).scalar_one()
    preview = service.clear_preview(session)
    assert preview["trainers"] == 4
    assert preview["locations"] == 5

    removed = service.clear_trainer_records(session, admin)
    session.flush()
    assert removed["trainers"] == 4

    assert session.execute(select(func.count()).select_from(Trainer)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(TrainerAvailability)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(TrainerUnit)).scalar_one() == 0

    assert service.generate_trainer_id(session, "Arsalan Yusuf") == "TI_001_AY"


def test_several_locations_and_qualifications_may_be_added_before_saving(session, refs, people):
    """The form lists each one as it is added, so a complete record is one pass."""
    admin = session.execute(select(User).where(User.organisation_email == ADMIN)).scalar_one()

    def location(campus_id, start, end):
        return {
            "campus_id": campus_id,
            "is_offshore": False,
            "class_type": "THEORY",
            "working_time_start": start,
            "working_time_end": end,
            "monday": "PHYSICAL",
            "tuesday": "NOT_AVAILABLE",
            "wednesday": "NOT_AVAILABLE",
            "thursday": "NOT_AVAILABLE",
            "friday": "NOT_AVAILABLE",
        }

    detail = service.create_trainer(
        session,
        data={
            "trainer_name": "Many Places",
            "city": "Sydney",
            "locations": [
                location(refs["blacktown"], dt.time(9, 0), dt.time(17, 0)),
                location(refs["haymarket"], dt.time(9, 0), dt.time(17, 0)),
            ],
            "units": [
                {"qualification_id": refs["bsb40920"], "unit_ids": [refs["shared"]]},
                {"qualification_id": refs["bsb50820"], "unit_ids": [refs["shared"]]},
            ],
        },
        user=admin,
    )
    assert len(detail["locations"]) == 2
    assert len(detail["qualifications"]) == 2
    # The same unit under two qualifications is two rows, never collapsed.
    assert sum(len(group["units"]) for group in detail["qualifications"]) == 2
