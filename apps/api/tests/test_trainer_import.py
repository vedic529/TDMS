"""Trainer bulk import (checks 3.6 and 3.7), including the query-count checks.

Every fixture below is a shape the real `Trainer Data - BSB.xlsx` actually
contains — a trainer at two locations, an offshore row, a unit under two
qualifications, a timezone suffix on the working time — plus the shapes it does
not, which the importer must still refuse well: an unparseable time, an unknown
trainer id, a unit that is not part of its qualification.
"""

from __future__ import annotations

import csv
import io

import pytest
from sqlalchemy import event, func, select, text

from app.models.allocation import ReferenceSuggestion
from app.models.trainer import Trainer, TrainerAvailability, TrainerQualification, TrainerUnit
from app.models.user import User
from app.services import trainer_import as service

from tests.test_trainer_api import (  # reuse the approved fixtures
    ADMIN,
    client,  # noqa: F401 - fixture
    people,  # noqa: F401 - fixture
    refs,  # noqa: F401 - fixture
)

pytestmark = pytest.mark.database

LOCATION_COLUMNS = [
    "SL No.",
    "Trainer id",
    "Trainer name",
    "Trainer Campus",
    "Location",
    "Location Type",
    "Working Time",
    "Delivery Type",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
]
UNITS_COLUMNS = ["Trainer ID", "Qualifications They Can Teach", "Units They Can Teach"]

NINE_TO_FIVE = "9:00 AM to 5:00 PM AEST/AEDT"
ONE_TO_NINE = "1:00 PM to 9:00 PM AEST/AEDT"


def csv_bytes(columns: list[str], rows: list[list]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def location_row(number, trainer_id, name, city, location, **overrides):
    row = {
        "SL No.": number,
        "Trainer id": trainer_id,
        "Trainer name": name,
        "Trainer Campus": city,
        "Location": location,
        "Location Type": "Campus",
        "Working Time": NINE_TO_FIVE,
        "Delivery Type": "Theory",
        "Monday": "Physical",
        "Tuesday": "Physical",
        "Wednesday": "NA",
        "Thursday": "NA",
        "Friday": "Virtual",
    }
    row.update(overrides)
    return [row[column] for column in LOCATION_COLUMNS]


@pytest.fixture()
def admin(session, people):
    return session.execute(select(User).where(User.organisation_email == ADMIN)).scalar_one()


def stage(session, admin, data_type, columns, rows, file_name="trainers.csv"):
    return service.stage_file(
        session,
        data_type=data_type,
        file_name=file_name,
        payload=csv_bytes(columns, rows),
        user=admin,
    )


def issues_for(review, row_number):
    row = next(r for r in review["rows"] if r["row_number"] == row_number)
    return row, [i["message"] for i in row["issues"]]


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


# ===========================================================================
# 3.6 Trainer Location and Details
# ===========================================================================


def test_a1_the_real_sheet_shape_stages_and_writes(session, refs, admin):
    """A1 — 11 rows, 9 trainers, 11 availability rows. One row per location."""
    rows = [
        location_row(1, "TI_002_EN", "Ertajul Noorani", "Sydney", "Blacktown"),
        location_row(2, "TI_002_EN", "Ertajul Noorani", "Sydney", "Haymarket"),
        location_row(3, "TI_003_MS", "M. Sajed", "Sydney", "Haymarket"),
        location_row(4, "TI_006_WA", "W. Ahmed", "Hobart", "Hobart"),
    ]
    review = stage(session, admin, "LOCATION", LOCATION_COLUMNS, rows)
    assert review["rows_read"] == 4
    assert review["can_apply"] is True

    result = service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    assert result["trainers_written"] == 3, "three distinct trainers from four rows"
    assert result["locations_written"] == 4

    assert session.execute(select(func.count()).select_from(Trainer)).scalar_one() == 3
    assert session.execute(select(func.count()).select_from(TrainerAvailability)).scalar_one() == 4


def test_a2_sl_no_is_ignored_and_says_so(session, refs, admin):
    """A2 — a row number is not data. Noted per row, never stored."""
    review = stage(
        session,
        admin,
        "LOCATION",
        LOCATION_COLUMNS,
        [location_row(7, "TI_001_AK", "A K", "Sydney", "Haymarket")],
    )
    row, messages = issues_for(review, 2)
    assert any("Ignored" in message for message in messages)
    assert row["status"] == "READY", "a note never blocks"

    service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    stored = session.execute(select(TrainerAvailability)).scalars().all()
    assert not any("7" == str(getattr(row, "location", "")) for row in stored)


def test_a3_weekday_cells_are_a_mode_not_a_yes_or_no(session, refs, admin):
    """A3 — Physical, Virtual and NA each map to their stored mode."""
    review = stage(
        session,
        admin,
        "LOCATION",
        LOCATION_COLUMNS,
        [
            location_row(
                1,
                "TI_005_NS",
                "N S",
                "Hobart",
                "Hobart",
                Monday="Physical",
                Tuesday="Virtual",
                Wednesday="NA",
                Thursday="",
                Friday="Physical",
            )
        ],
    )
    service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    stored = session.execute(select(TrainerAvailability)).scalars().one()
    assert stored.monday == "PHYSICAL"
    assert stored.tuesday == "VIRTUAL"
    assert stored.wednesday == "NOT_AVAILABLE"
    assert stored.thursday == "NOT_AVAILABLE", "a blank cell is not available, not a guess"
    assert stored.friday == "PHYSICAL"


@pytest.mark.parametrize(
    ("raw", "start", "end"),
    [
        (NINE_TO_FIVE, "09:00:00", "17:00:00"),
        (ONE_TO_NINE, "13:00:00", "21:00:00"),
        ("9:00 AM to 5:00 PM AEST", "09:00:00", "17:00:00"),
    ],
)
def test_a4_a5_working_time_parses_and_keeps_its_timezone(session, refs, admin, raw, start, end):
    """A4, A5 — parsed for comparison, and the raw string kept for the timezone."""
    review = stage(
        session,
        admin,
        "LOCATION",
        LOCATION_COLUMNS,
        [location_row(1, "TI_007_NV", "N V", "Hobart", "Hobart", **{"Working Time": raw})],
    )
    service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    stored = session.execute(select(TrainerAvailability)).scalars().one()
    assert str(stored.working_time_start) == start
    assert str(stored.working_time_end) == end
    assert stored.working_time_text == raw, "the timezone is not lost from the record"


def test_a6_an_unreadable_working_time_blocks_and_names_the_cell(session, refs, admin):
    """A6 — never a guess, never a default."""
    review = stage(
        session,
        admin,
        "LOCATION",
        LOCATION_COLUMNS,
        [location_row(1, "TI_001_AK", "A K", "Sydney", "Haymarket", **{"Working Time": "whenever"})],
    )
    row, messages = issues_for(review, 2)
    assert row["status"] == "NEEDS_CORRECTION"
    assert any("whenever" in message for message in messages), "the cell is named"
    assert review["can_apply"] is False

    with pytest.raises(service.TrainerImportError):
        service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)


def test_a7_the_offshore_row_is_valid_and_raises_no_suggestion(session, refs, admin):
    """A7 — offshore is a state, not a failure to resolve."""
    review = stage(
        session,
        admin,
        "LOCATION",
        LOCATION_COLUMNS,
        [
            location_row(
                1,
                "TI_008_NK",
                "Dr. Nisha Kalra",
                "Offshore",
                "Offshore",
                **{"Working Time": ONE_TO_NINE},
            )
        ],
    )
    row, messages = issues_for(review, 2)
    assert row["status"] == "READY"
    assert not any("approved campus" in message for message in messages)

    service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    stored = session.execute(select(TrainerAvailability)).scalars().one()
    assert stored.campus_id is None
    assert stored.is_offshore is True
    assert stored.location_text == "Offshore"

    raised = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.source == "TRAINER_IMPORT")
    ).scalars().all()
    assert raised == [], "offshore must not be reported as an unresolved campus"


def test_a8_a_location_resolves_case_insensitively(session, refs, admin):
    """A8 — `haymarket`, `HAYMARKET` and `Haymarket` are one place."""
    for spelling in ("haymarket", "HAYMARKET", " Haymarket "):
        review = stage(
            session,
            admin,
            "LOCATION",
            LOCATION_COLUMNS,
            [location_row(1, f"TI_{spelling.strip().upper()}", "X", "Sydney", spelling)],
        )
        row, _ = issues_for(review, 2)
        assert row["status"] == "READY", f"{spelling!r} did not resolve"


def test_a9_an_unknown_location_is_offered_for_a_suggestion_with_no_exception_path(
    session, refs, admin
):
    """A9 — Create Record and Map Record only (1.8).

    Changed 27 August 2026: staging **detects** the value and offers it; it does
    not raise behind the user's back. A value they recognise as a typo is
    corrected, not added to the reference data — and an abandoned review now
    leaves nothing in the queue.
    """
    review = stage(
        session,
        admin,
        "LOCATION",
        LOCATION_COLUMNS,
        [location_row(1, "TI_001_AK", "A K", "Sydney", "Nowhere Campus")],
    )
    row, messages = issues_for(review, 2)
    assert row["status"] == "NEEDS_CORRECTION"
    assert any("Create the campus or map it" in message for message in messages)
    # The allocation import's third choice is deliberately absent here.
    assert not any("exception" in message.lower() for message in messages)

    # Offered, not written.
    offered = review["unresolved_values"]
    assert [(e["entity_type"], e["raw_value"]) for e in offered] == [("CAMPUS", "Nowhere Campus")]
    assert offered[0]["in_queue"] is False
    assert offered[0]["row_count"] == 1
    assert session.execute(select(ReferenceSuggestion)).scalars().all() == []

    # Raising is the user's action.
    service.raise_values(session, review["batch_id"], keys=[offered[0]["key"]], user=admin)
    raised = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.entity_type == "CAMPUS")
    ).scalars().all()
    assert [r.raw_value for r in raised] == ["Nowhere Campus"]
    assert raised[0].status == "PENDING", "never EXCEPTION — there is no exception path"
    assert raised[0].source == "TRAINER_IMPORT"

    # And the row now imports, keeping the raw value — the same behaviour the
    # allocation import has always had.
    after = service.read_batch(session, review["batch_id"])
    assert after["unresolved_values"][0]["in_queue"] is True
    assert after["can_apply"] is True, "raising lets the data in"
    service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    stored = session.execute(select(TrainerAvailability)).scalars().one()
    assert stored.campus_id is None
    assert stored.location_text == "Nowhere Campus", "found again when the suggestion resolves"


def test_a10_a_disagreeing_city_warns_rather_than_refusing(session, refs, admin):
    """A10 — the city is new data and may simply be missing."""
    review = stage(
        session,
        admin,
        "LOCATION",
        LOCATION_COLUMNS,
        [location_row(1, "TI_001_AK", "A K", "Melbourne", "Haymarket")],
    )
    row, messages = issues_for(review, 2)
    assert row["status"] == "READY", "a disagreement must not block the file"
    warning = next(message for message in messages if "Melbourne" in message)
    assert "Sydney" in warning, "the warning names both"
    assert review["can_apply"] is True


def test_a11_theory_and_practical_stores_as_the_third_value(session, refs, admin):
    """A11 — the option the form offered and the database could not hold."""
    review = stage(
        session,
        admin,
        "LOCATION",
        LOCATION_COLUMNS,
        [
            location_row(
                1, "TI_009_SH", "S H", "Hobart", "Hobart", **{"Delivery Type": "Theory and Practical"}
            )
        ],
    )
    service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    stored = session.execute(select(TrainerAvailability)).scalars().one()
    assert stored.class_type == "THEORY_AND_PRACTICAL"


def test_a12_re_uploading_the_same_file_in_merge_adds_no_duplicate(session, refs, admin):
    """A12 — the partial unique holds, and the importer does not fight it."""
    rows = [
        location_row(1, "TI_002_EN", "Ertajul Noorani", "Sydney", "Blacktown"),
        location_row(2, "TI_002_EN", "Ertajul Noorani", "Sydney", "Haymarket"),
    ]
    first = stage(session, admin, "LOCATION", LOCATION_COLUMNS, rows)
    service.apply_batch(session, first["batch_id"], apply_mode="MERGE", user=admin)

    second = stage(session, admin, "LOCATION", LOCATION_COLUMNS, rows)
    result = service.apply_batch(session, second["batch_id"], apply_mode="MERGE", user=admin)

    assert result["locations_written"] == 0, "nothing new to write"
    assert session.execute(select(func.count()).select_from(TrainerAvailability)).scalar_one() == 2
    assert session.execute(select(func.count()).select_from(Trainer)).scalar_one() == 1


# ===========================================================================
# 3.7 Trainer Units
# ===========================================================================


@pytest.fixture()
def trainers_exist(session, refs, admin):
    """The location file runs first, as it must: units never create a trainer."""
    rows = [
        location_row(1, "TI_001_AK", "A K", "Sydney", "Haymarket"),
        location_row(2, "TI_002_EN", "E N", "Sydney", "Blacktown"),
    ]
    review = stage(session, admin, "LOCATION", LOCATION_COLUMNS, rows)
    service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    return {
        row.trainer_id: row.id
        for row in session.execute(select(Trainer)).scalars().all()
    }


def test_b1_b2_the_same_unit_under_two_qualifications_is_two_rows(
    session, refs, admin, trainers_exist
):
    """B1, B2 — never collapsed, and never reported as a duplicate (1.2)."""
    rows = [
        ["TI_001_AK", "BSB40920", "BSBPMG533"],
        ["TI_001_AK", "BSB50820", "BSBPMG533"],
        ["TI_001_AK", "BSB40920", "BSBPMG421"],
    ]
    review = stage(session, admin, "UNITS", UNITS_COLUMNS, rows)
    assert review["rows_read"] == 3
    assert all(row["status"] == "READY" for row in review["rows"]), "none is a duplicate"

    result = service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    assert result["unit_links_written"] == 3, "three rows in, three rows stored"
    assert session.execute(select(func.count()).select_from(TrainerUnit)).scalar_one() == 3


def test_b3_the_same_triple_twice_is_one_duplicate(session, refs, admin, trainers_exist):
    """B3 — reported once, on the repeat."""
    rows = [
        ["TI_001_AK", "BSB40920", "BSBPMG533"],
        ["TI_001_AK", "BSB40920", "BSBPMG533"],
    ]
    review = stage(session, admin, "UNITS", UNITS_COLUMNS, rows)
    statuses = [row["status"] for row in review["rows"]]
    assert statuses == ["READY", "DUPLICATE"]


def test_b4_an_unknown_unit_blocks_until_it_is_raised_resolved_or_excluded(
    session, refs, admin, trainers_exist
):
    """B4 — Create or Map only, and Confirm stays shut until a decision."""
    rows = [
        ["TI_001_AK", "BSB40920", "BSBPMG533"],
        ["TI_001_AK", "BSB40920", "BSBNOTREAL"],
    ]
    review = stage(session, admin, "UNITS", UNITS_COLUMNS, rows)
    assert review["can_apply"] is False
    row, messages = issues_for(review, 3)
    assert row["status"] == "NEEDS_CORRECTION"
    assert any("Create it or map it" in message for message in messages)
    assert not any("exception" in message.lower() for message in messages)

    offered = review["unresolved_values"]
    assert [e["raw_value"] for e in offered] == ["BSBNOTREAL"]
    # 2.13.4: a UNIT is scoped by its qualification.
    assert offered[0]["context"] == {"qualification": "BSB40920"}
    assert offered[0]["in_queue"] is False

    service.raise_values(session, review["batch_id"], keys=[offered[0]["key"]], user=admin)
    raised = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.entity_type == "UNIT")
    ).scalars().all()
    assert [r.raw_value for r in raised] == ["BSBNOTREAL"]
    assert raised[0].context == {"qualification": "BSB40920"}

    # Raising lets the whole file in, the unmatched value kept as written.
    after = service.read_batch(session, review["batch_id"])
    assert after["can_apply"] is True
    result = service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    assert result["unit_links_written"] == 2, "both rows imported, not just the matched one"
    assert result["unit_links_unresolved"] == 1

    stored = session.execute(
        select(TrainerUnit).where(TrainerUnit.unit_id.is_(None))
    ).scalars().one()
    assert stored.unit_text == "BSBNOTREAL", "the raw value is what a resolution repairs"
    assert stored.qualification_id is not None, "the qualification did resolve"


def test_b4b_excluding_the_row_is_still_a_way_through(session, refs, admin, trainers_exist):
    """Raising is a third route, beside resolving the value and dropping the row."""
    review = stage(
        session,
        admin,
        "UNITS",
        UNITS_COLUMNS,
        [
            ["TI_001_AK", "BSB40920", "BSBPMG533"],
            ["TI_001_AK", "BSB40920", "BSBNOTREAL"],
        ],
    )
    row, _ = issues_for(review, 3)
    review = service.patch_rows(
        session,
        review["batch_id"],
        corrections={},
        excluded_row_ids=[row["id"]],
        exclude_missing_trainers=False,
        user=admin,
    )
    assert review["can_apply"] is True
    result = service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    assert result["unit_links_written"] == 1
    assert result["unit_links_unresolved"] == 0


def test_b5_an_unknown_qualification_is_offered_the_same_way(session, refs, admin, trainers_exist):
    review = stage(
        session, admin, "UNITS", UNITS_COLUMNS, [["TI_001_AK", "XXX99999", "BSBPMG533"]]
    )
    assert review["can_apply"] is False
    offered = [e for e in review["unresolved_values"] if e["entity_type"] == "QUALIFICATION"]
    assert [e["raw_value"] for e in offered] == ["XXX99999"]

    service.raise_values(session, review["batch_id"], keys=[e["key"] for e in offered], user=admin)
    raised = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.entity_type == "QUALIFICATION")
    ).scalars().all()
    assert [r.raw_value for r in raised] == ["XXX99999"]
    assert raised[0].status == "PENDING"


def test_abandoning_after_staging_leaves_nothing_in_the_queue(session, refs, admin, trainers_exist):
    """The reason staging stops writing: an abandoned review must leave no trace.

    This is how the student and allocation importers already behave, and the
    trainer import raised on upload until 27 August 2026.
    """
    review = stage(
        session, admin, "UNITS", UNITS_COLUMNS, [["TI_001_AK", "BSB40920", "BSBNOTREAL"]]
    )
    assert review["unresolved_values"][0]["in_queue"] is False
    service.abandon(session, review["batch_id"], user=admin)
    assert session.execute(select(ReferenceSuggestion)).scalars().all() == []


def test_raise_all_takes_every_offered_value_at_once(session, refs, admin, trainers_exist):
    review = stage(
        session,
        admin,
        "UNITS",
        UNITS_COLUMNS,
        [
            ["TI_001_AK", "XXX99999", "BSBPMG533"],
            ["TI_001_AK", "BSB40920", "BSBNOTREAL"],
        ],
    )
    keys = [entry["key"] for entry in review["unresolved_values"]]
    assert len(keys) == 2, "one qualification and one unit"
    assert service.raise_values(session, review["batch_id"], keys=keys, user=admin) == 2

    after = service.read_batch(session, review["batch_id"])
    assert all(entry["in_queue"] for entry in after["unresolved_values"])
    assert after["suggestions_raised"] == 2


def test_b6_a_unit_outside_its_qualification_warns(session, refs, admin, trainers_exist):
    """B6 — the reference data may be incomplete; refusing would block a good file."""
    review = stage(
        session, admin, "UNITS", UNITS_COLUMNS, [["TI_001_AK", "FNS40222", "BSBPMG533"]]
    )
    row, messages = issues_for(review, 2)
    assert row["status"] == "READY"
    warning = next(message for message in messages if "not recorded as part of" in message)
    assert "BSBPMG533" in warning and "FNS40222" in warning, "the warning names both"
    assert review["can_apply"] is True


def test_b7_b8_b9_an_unknown_trainer_is_flagged_and_the_rest_still_import(
    session, refs, admin, trainers_exist
):
    """B7, B8, B9 — flagged, grouped, counted; excluded on request; never created."""
    rows = [
        ["TI_001_AK", "BSB40920", "BSBPMG533"],
        ["TI_999_XX", "BSB40920", "BSBPMG533"],
        ["TI_999_XX", "BSB40920", "BSBPMG421"],
        ["TI_888_YY", "BSB40920", "BSBPMG533"],
    ]
    review = stage(session, admin, "UNITS", UNITS_COLUMNS, rows)

    assert review["can_apply"] is False
    assert review["missing_trainers"] == [
        {"trainer_id": "TI_888_YY", "row_count": 1},
        {"trainer_id": "TI_999_XX", "row_count": 2},
    ]
    assert "2 trainer id(s)" in review["blocking_message"]
    assert "3 row(s)" in review["blocking_message"]
    unmatched = [r for r in review["rows"] if r["status"] == "UNMATCHED_REFERENCE"]
    assert len(unmatched) == 3

    # B8 — the single offered action.
    review = service.patch_rows(
        session,
        review["batch_id"],
        corrections={},
        excluded_row_ids=[],
        exclude_missing_trainers=True,
        user=admin,
    )
    assert review["can_apply"] is True
    assert review["rows_excluded"] == 3

    before = session.execute(select(func.count()).select_from(Trainer)).scalar_one()
    result = service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    assert result["unit_links_written"] == 1, "only the row for the trainer that exists"
    # B9 — a units file has no name, campus or availability, so it cannot make
    # a complete trainer record and must not try.
    assert session.execute(select(func.count()).select_from(Trainer)).scalar_one() == before


def test_b10_trainer_qualifications_is_derived_and_kept_current(
    session, refs, admin, trainers_exist
):
    """B10 — exactly one row per distinct (trainer, qualification)."""
    rows = [
        ["TI_001_AK", "BSB40920", "BSBPMG533"],
        ["TI_001_AK", "BSB40920", "BSBPMG421"],
        ["TI_001_AK", "BSB50820", "BSBPMG533"],
    ]
    review = stage(session, admin, "UNITS", UNITS_COLUMNS, rows)
    service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)

    held = session.execute(
        select(TrainerQualification.qualification_id).where(
            TrainerQualification.trainer_id == trainers_exist["TI_001_AK"]
        )
    ).scalars().all()
    assert len(held) == 2, "three unit rows, two qualifications, two links"
    assert len(set(held)) == 2


def test_b11_a_large_file_does_not_issue_a_query_per_row(session, refs, admin, trainers_exist):
    """B11 — flat. 363 rows must not mean 363 inserts.

    Measured against a file an order of magnitude apart: if the count tracks the
    row count, the loop is issuing per-row work.
    """
    def rows_for(count):
        codes = ["BSBPMG533", "BSBPMG421"]
        return [
            ["TI_001_AK", "BSB40920" if index % 2 else "BSB50820", codes[index % 2]]
            for index in range(count)
        ]

    small = stage(session, admin, "UNITS", UNITS_COLUMNS, rows_for(4), file_name="small.csv")
    _, few = _count_queries(
        session,
        lambda: service.apply_batch(session, small["batch_id"], apply_mode="MERGE", user=admin),
    )

    session.execute(text("DELETE FROM trainer_units"))
    session.execute(text("DELETE FROM trainer_qualifications"))
    session.flush()

    big = stage(session, admin, "UNITS", UNITS_COLUMNS, rows_for(400), file_name="big.csv")
    _, many = _count_queries(
        session,
        lambda: service.apply_batch(session, big["batch_id"], apply_mode="MERGE", user=admin),
    )
    assert many == few, f"query count grew from {few} to {many} between a 4-row and a 400-row file"
    assert many < 40, f"{many} statements is not a bulk apply"


def test_b12_replace_touches_only_the_trainers_named_in_the_file(
    session, refs, admin, trainers_exist
):
    """B12 — re-uploading a corrected BSB file must not delete CHC trainers."""
    first = stage(
        session,
        admin,
        "UNITS",
        UNITS_COLUMNS,
        [
            ["TI_001_AK", "BSB40920", "BSBPMG533"],
            ["TI_002_EN", "BSB40920", "BSBPMG421"],
        ],
    )
    service.apply_batch(session, first["batch_id"], apply_mode="MERGE", user=admin)
    assert session.execute(select(func.count()).select_from(TrainerUnit)).scalar_one() == 2

    # A corrected file naming only the first trainer.
    second = stage(
        session, admin, "UNITS", UNITS_COLUMNS, [["TI_001_AK", "BSB50820", "BSBPMG533"]]
    )
    service.apply_batch(session, second["batch_id"], apply_mode="REPLACE", user=admin)

    held = {
        (row.trainer_id, row.qualification_id)
        for row in session.execute(select(TrainerUnit)).scalars().all()
    }
    assert len(held) == 2, "the untouched trainer keeps their row"
    assert any(t == trainers_exist["TI_002_EN"] for t, _ in held), (
        "a trainer absent from the file was not cleared"
    )
    first_rows = [
        row
        for row in session.execute(select(TrainerUnit)).scalars().all()
        if row.trainer_id == trainers_exist["TI_001_AK"]
    ]
    assert len(first_rows) == 1, "the named trainer's rows were replaced, not added to"


# ===========================================================================
# Shared behaviour
# ===========================================================================


def test_the_import_asks_for_a_data_type_not_a_training_package(session, refs, admin):
    """1.7 — the two shapes, and nothing that names a package."""
    assert service.DATA_TYPES == ("LOCATION", "UNITS")
    with pytest.raises(service.TrainerImportError):
        stage(session, admin, "BSB", LOCATION_COLUMNS, [])


def test_a_missing_required_column_names_it(session, refs, admin):
    with pytest.raises(service.TrainerImportError) as caught:
        stage(session, admin, "UNITS", ["Trainer ID"], [["TI_001_AK"]])
    assert "Units They Can Teach" in str(caught.value) or "unit_code" in str(caught.value)


def test_abandoning_a_batch_writes_nothing(session, refs, admin):
    review = stage(
        session,
        admin,
        "LOCATION",
        LOCATION_COLUMNS,
        [location_row(1, "TI_001_AK", "A K", "Sydney", "Haymarket")],
    )
    service.abandon(session, review["batch_id"], user=admin)
    assert session.execute(select(func.count()).select_from(Trainer)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(TrainerAvailability)).scalar_one() == 0


def test_zero_width_characters_do_not_hide_a_real_unit(session, refs, admin, trainers_exist):
    """The real file carries two U+200B before `FNSACC601`.

    Invisible on screen, and `\\s` does not match them, so without normalisation
    a unit that exists is reported as missing for a reason nobody can see.
    """
    review = stage(
        session,
        admin,
        "UNITS",
        UNITS_COLUMNS,
        [["TI_001_AK", "FNS40222", "​​FNSACC601"]],
    )
    row, messages = issues_for(review, 2)
    assert row["status"] == "READY", f"the unit was not recognised: {messages}"


def test_resolving_the_suggestion_repairs_the_trainer_rows(session, refs, admin, trainers_exist):
    """The loop must close: a raised value imports, and resolving it links up.

    Without this the raise would be a one-way door — the rows would sit holding
    text no resolution ever reached, which is the fault the Rev 2 relink work
    existed to fix on the allocation side.
    """
    from app.models.qualification import Unit
    from app.services import reference_suggestion_service as suggestions

    review = stage(
        session,
        admin,
        "UNITS",
        UNITS_COLUMNS,
        [
            ["TI_001_AK", "BSB40920", "BSBPMG533"],
            ["TI_001_AK", "BSB40920", "BSBNOTREAL"],
            ["TI_002_EN", "BSB40920", "BSBNOTREAL"],
        ],
    )
    offered = review["unresolved_values"]
    service.raise_values(session, review["batch_id"], keys=[offered[0]["key"]], user=admin)
    service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)

    held = session.execute(
        select(TrainerUnit).where(TrainerUnit.unit_id.is_(None))
    ).scalars().all()
    assert len(held) == 2, "both trainers kept the unmatched unit"

    # Create Record: the approved unit now exists, and the queue entry resolves.
    created = Unit(unit_code="BSBNOTREAL", unit_title="Newly approved unit")
    session.add(created)
    session.flush()
    entry = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.raw_value == "BSBNOTREAL")
    ).scalars().one()
    repaired = suggestions._relink(session, entry, created.id)
    session.flush()

    assert repaired == 2, "both trainer rows were found by their text and linked"
    assert (
        session.execute(
            select(func.count()).select_from(TrainerUnit).where(TrainerUnit.unit_id.is_(None))
        ).scalar_one()
        == 0
    )
    linked = session.execute(
        select(TrainerUnit).where(TrainerUnit.unit_id == created.id)
    ).scalars().all()
    assert len(linked) == 2
    assert all(row.unit_text == "BSBNOTREAL" for row in linked), (
        "the text is retained — it records what the source file said"
    )


# ===========================================================================
# Merge: adding is silent, overwriting is not (approved 27 August 2026)
# ===========================================================================


def _import_location(session, admin, rows, mode="MERGE"):
    review = stage(session, admin, "LOCATION", LOCATION_COLUMNS, rows)
    return review, service.apply_batch(session, review["batch_id"], apply_mode=mode, user=admin)


def test_merge_adds_a_new_location_without_asking(session, refs, admin):
    """A genuinely new row is not an override and needs no decision."""
    _import_location(
        session, admin, [location_row(1, "TI_002_EN", "Ertajul Noorani", "Sydney", "Blacktown")]
    )
    review, result = _import_location(
        session,
        admin,
        [
            location_row(1, "TI_002_EN", "Ertajul Noorani", "Sydney", "Blacktown"),
            location_row(2, "TI_002_EN", "Ertajul Noorani", "Sydney", "Haymarket"),
        ],
    )
    assert review["overrides"] == [], "nothing was changed, only added"
    assert result["locations_written"] == 1
    assert result["locations_overwritten"] == 0


def test_merge_flags_a_changed_weekday_and_waits(session, refs, admin):
    """The case you named: the days at a campus differ from what is stored."""
    _import_location(
        session,
        admin,
        [location_row(1, "TI_002_EN", "Ertajul Noorani", "Sydney", "Blacktown", Wednesday="NA")],
    )
    review = stage(
        session,
        admin,
        "LOCATION",
        LOCATION_COLUMNS,
        [
            location_row(
                1, "TI_002_EN", "Ertajul Noorani", "Sydney", "Blacktown", Wednesday="Physical"
            )
        ],
    )
    assert review["can_apply"] is False, "an overwrite waits for a decision"
    assert "would change something already stored" in review["blocking_message"]

    entry = review["overrides"][0]
    assert entry["trainer_id"] == "TI_002_EN"
    assert entry["decision"] is None
    change = next(c for c in entry["changes"] if c["field"] == "wednesday")
    assert change["stored_value"] == "NOT_AVAILABLE"
    assert change["incoming_value"] == "PHYSICAL"

    with pytest.raises(service.TrainerImportError):
        service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)


def test_keeping_the_stored_value_leaves_it_alone(session, refs, admin):
    _import_location(
        session,
        admin,
        [location_row(1, "TI_002_EN", "E N", "Sydney", "Blacktown", Wednesday="NA")],
    )
    review = stage(
        session,
        admin,
        "LOCATION",
        LOCATION_COLUMNS,
        [location_row(1, "TI_002_EN", "E N", "Sydney", "Blacktown", Wednesday="Physical")],
    )
    review = service.patch_rows(
        session,
        review["batch_id"],
        corrections={},
        excluded_row_ids=[],
        exclude_missing_trainers=False,
        override_decisions={review["overrides"][0]["row_id"]: "KEEP_STORED"},
        user=admin,
    )
    assert review["can_apply"] is True
    result = service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    assert result["locations_overwritten"] == 0

    stored = session.execute(select(TrainerAvailability)).scalars().one()
    assert stored.wednesday == "NOT_AVAILABLE", "the stored value stands"


def test_taking_the_file_value_overwrites_it(session, refs, admin):
    _import_location(
        session,
        admin,
        [location_row(1, "TI_002_EN", "E N", "Sydney", "Blacktown", Wednesday="NA")],
    )
    review = stage(
        session,
        admin,
        "LOCATION",
        LOCATION_COLUMNS,
        [location_row(1, "TI_002_EN", "E N", "Sydney", "Blacktown", Wednesday="Physical")],
    )
    review = service.patch_rows(
        session,
        review["batch_id"],
        corrections={},
        excluded_row_ids=[],
        exclude_missing_trainers=False,
        override_decisions={review["overrides"][0]["row_id"]: "TAKE_FROM_FILE"},
        user=admin,
    )
    assert review["can_apply"] is True
    result = service.apply_batch(session, review["batch_id"], apply_mode="MERGE", user=admin)
    assert result["locations_overwritten"] == 1

    stored = session.execute(select(TrainerAvailability)).scalars().one()
    assert stored.wednesday == "PHYSICAL", "the file's value was taken"
    assert (
        session.execute(select(func.count()).select_from(TrainerAvailability)).scalar_one() == 1
    ), "overwritten, not duplicated"


def test_an_identical_re_upload_flags_nothing(session, refs, admin):
    """A12 still holds: nothing changed means nothing to decide."""
    rows = [location_row(1, "TI_002_EN", "E N", "Sydney", "Blacktown")]
    _import_location(session, admin, rows)
    review = stage(session, admin, "LOCATION", LOCATION_COLUMNS, rows)
    assert review["overrides"] == []
    assert review["can_apply"] is True
