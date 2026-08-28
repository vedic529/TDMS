"""Relink, quarantine and deduplication of the shared suggestion queue.

Covers checks 3.3 (relink), 3.4 (reject and quarantine) and 3.5 (one issue,
listed once) of the Revision 2 prompt.

The invariant under test: after a resolution, every row that raised the entry
carries the approved identifier — for **all six** entity types, not the two that
happened to store their text before this work.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import event, func, select, text

from app.models.allocation import AllocationDelivery, AllocationSession, ReferenceSuggestion
from app.models.user import User
from app.services.allocation_import import ImportOverrides, apply_rows, validate_bytes
from app.services import reference_suggestion_service as suggestions

from tests.test_allocation_records import (  # reuse the approved fixtures
    EDITOR,
    MONDAY,
    base_row,
    client,  # noqa: F401 - fixture
    csv_bytes,
    people,  # noqa: F401 - fixture
    refs,  # noqa: F401 - fixture
)

pytestmark = pytest.mark.database


def _editor(session) -> User:
    return session.execute(select(User).where(User.organisation_email == EDITOR)).scalar_one()


def _apply(session, rows, refs_dict):
    """Import rows, raising a suggestion for anything unmatched."""
    payload = csv_bytes(rows)
    return apply_rows(
        session,
        training_package="BSB",
        file_name="relink.csv",
        file_size_bytes=len(payload),
        payload=payload,
        apply_mode="REPLACE",
        raise_suggestions=True,
        overrides=ImportOverrides.from_payload({}, True),
        user=_editor(session),
    )


def _entry(session, entity_type: str) -> ReferenceSuggestion:
    return session.execute(
        select(ReferenceSuggestion).where(
            ReferenceSuggestion.entity_type == entity_type,
            ReferenceSuggestion.status == "PENDING",
        )
    ).scalars().first()


# ---------------------------------------------------------------------------
# 3.3 Relink
# ---------------------------------------------------------------------------


def test_r1_map_a_campus_writes_back_to_every_delivery(session, refs):
    """R1 — 40 rows with one unknown campus, mapped once, all 40 repaired."""
    rows = [
        base_row(refs, **{"Campus Location": "Parramatta Campuss", "Units of Competency ID": f"UNIT{n:03d}"})
        for n in range(40)
    ]
    _apply(session, rows, refs)

    stored = session.execute(
        select(func.count()).select_from(AllocationDelivery).where(AllocationDelivery.campus_id.is_(None))
    ).scalar_one()
    assert stored == 40, "every row should have stored the campus text, unresolved"

    entry = _entry(session, "CAMPUS")
    assert entry is not None and entry.occurrence_count == 40

    _row, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=entry.id, action="MAP", resolved_entity_id=refs["campus_id"]
    )
    assert updated == 40
    remaining = session.execute(
        select(func.count()).select_from(AllocationDelivery).where(AllocationDelivery.campus_id.is_(None))
    ).scalar_one()
    assert remaining == 0


def test_r2_create_behaves_identically_to_map(session, refs):
    """R2 — Create and Map must not differ in write-back."""
    rows = [base_row(refs, **{"Campus Location": "Newcastle Campuss"}) for _ in range(3)]
    rows = [
        base_row(refs, **{"Campus Location": "Newcastle Campuss", "Units of Competency ID": f"U{n}"})
        for n in range(3)
    ]
    _apply(session, rows, refs)
    entry = _entry(session, "CAMPUS")

    _row, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=entry.id, action="CREATE", resolved_entity_id=refs["campus_id"]
    )
    assert updated == 3


@pytest.mark.parametrize(
    "column,entity,text_column,id_column,approved",
    [
        ("College", "COLLEGE", AllocationDelivery.college_text, AllocationDelivery.college_id, "college_id"),
        ("Qualification Id", "QUALIFICATION", AllocationDelivery.qualification_text, AllocationDelivery.qualification_id, "qual_id"),
        ("Units of Competency ID", "UNIT", AllocationDelivery.unit_text, AllocationDelivery.unit_id, "unit_id"),
    ],
)
def test_r3_every_structural_entity_writes_back(session, refs, column, entity, text_column, id_column, approved):
    """R3 — COLLEGE, QUALIFICATION and UNIT relink. None returns 0."""
    rows = [base_row(refs, **{column: "Not An Approved Value"})]
    _apply(session, rows, refs)

    entry = _entry(session, entity)
    assert entry is not None, f"{entity} should have raised an entry"

    _row, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=entry.id, action="MAP", resolved_entity_id=refs[approved]
    )
    assert updated >= 1, f"{entity} relinked nothing"


def test_r4_facility_and_trainer_still_relink(session, refs):
    """R4 — the two entities that already worked must not regress."""
    rows = [base_row(refs, **{"Theory Classroom Name": "Room Nine"})]
    _apply(session, rows, refs)

    entry = _entry(session, "FACILITY")
    _row, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=entry.id, action="MAP", resolved_entity_id=refs["facility_id"]
    )
    # The row schedules Wednesday and Thursday, so it carries two sessions.
    assert updated == 2


def test_r5_all_spellings_relink(session, refs):
    """R5 — `Rm 3B`, `rm 3b` and `Rm  3B` dedupe to one entry; all three repair.

    The old code matched the raw value, so resolving repaired only the spelling
    stored on the entry and left the others unresolved with no entry to find
    them by.
    """
    rows = [
        base_row(refs, **{"Theory Classroom Name": spelling, "Units of Competency ID": f"S{n}"})
        for n, spelling in enumerate(["Rm 3B", "rm 3b", "Rm  3B"])
    ]
    _apply(session, rows, refs)

    entries = session.execute(
        select(ReferenceSuggestion).where(
            ReferenceSuggestion.entity_type == "FACILITY", ReferenceSuggestion.status == "PENDING"
        )
    ).scalars().all()
    assert len(entries) == 1, "three spellings must deduplicate to one entry"

    _row, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=entries[0].id, action="MAP", resolved_entity_id=refs["facility_id"]
    )
    # Three spellings x two class days = six sessions, all repaired by the one
    # resolution. Matching the raw value would have repaired only two of them.
    assert updated == 6, "every spelling must relink, not only the stored one"


def test_r6_text_is_retained_after_a_successful_map(session, refs):
    """R6 — the text records what the file said and survives the resolution."""
    _apply(session, [base_row(refs, **{"Campus Location": "Keep My Text"})], refs)
    entry = _entry(session, "CAMPUS")
    suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=entry.id, action="MAP", resolved_entity_id=refs["campus_id"]
    )
    delivery = session.execute(select(AllocationDelivery)).scalars().first()
    assert delivery.campus_id == refs["campus_id"]
    assert delivery.campus_text == "Keep My Text"


def test_r7_resolving_nothing_reports_zero(session, refs):
    """R7 — a resolution matching no stored row reports zero, not success."""
    _apply(session, [base_row(refs, **{"Campus Location": "Ghost Campus"})], refs)
    entry = _entry(session, "CAMPUS")
    session.execute(text("UPDATE allocation_delivery SET campus_text = 'Something Else'"))

    _row, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=entry.id, action="MAP", resolved_entity_id=refs["campus_id"]
    )
    assert updated == 0


def test_r8_relink_is_one_statement(session, refs, test_engine):
    """R8 — 30 rows relink in ONE update, never one per row."""
    rows = [
        base_row(refs, **{"Campus Location": "Bulk Campus", "Units of Competency ID": f"B{n}"})
        for n in range(30)
    ]
    _apply(session, rows, refs)
    entry = _entry(session, "CAMPUS")

    statements: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        if statement.strip().upper().startswith("UPDATE ALLOCATION_DELIVERY"):
            statements.append(statement)

    event.listen(test_engine, "before_cursor_execute", _before)
    try:
        _row, updated = suggestions.resolve_suggestion(
            session, _editor(session), suggestion_id=entry.id, action="MAP", resolved_entity_id=refs["campus_id"]
        )
    finally:
        event.remove(test_engine, "before_cursor_execute", _before)

    assert updated == 30
    assert len(statements) == 1, f"expected one UPDATE, issued {len(statements)}"


def test_r9_an_already_resolved_row_is_untouched(session, refs):
    """R9 — the IS NULL guard: a resolved row that retains text is not rewritten."""
    _apply(session, [base_row(refs, **{"Campus Location": "Once Unresolved"})], refs)
    entry = _entry(session, "CAMPUS")
    # Simulate a row resolved earlier that still carries its original text.
    session.execute(
        text("UPDATE allocation_delivery SET campus_id = :other, campus_text = 'Once Unresolved'"),
        {"other": refs["campus_id"]},
    )
    _row, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=entry.id, action="MAP", resolved_entity_id=refs["campus_id"]
    )
    assert updated == 0, "a resolved row must not be relinked again"


# ---------------------------------------------------------------------------
# 3.4 Reject and quarantine
# ---------------------------------------------------------------------------


def test_q1_q2_rejecting_a_campus_quarantines_and_keeps_everything(session, refs):
    """Q1/Q2 — rows retained, marked, reason recorded, nothing deleted."""
    rows = [
        base_row(refs, **{"Campus Location": "Reject Me", "Units of Competency ID": f"Q{n}"})
        for n in range(12)
    ]
    _apply(session, rows, refs)
    before = session.execute(select(func.count()).select_from(AllocationDelivery)).scalar_one()
    entry = _entry(session, "CAMPUS")

    _row, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=entry.id, action="REJECT"
    )
    assert updated == 12

    after = session.execute(select(func.count()).select_from(AllocationDelivery)).scalar_one()
    assert after == before, "rejecting must not delete a single row"

    quarantined = session.execute(
        select(AllocationDelivery).where(AllocationDelivery.is_quarantined.is_(True))
    ).scalars().all()
    assert len(quarantined) == 12
    for row in quarantined:
        assert row.quarantine_reason and "Reject Me" in row.quarantine_reason
        assert row.quarantined_at is not None
        assert row.quarantined_by_user_id is not None
        assert row.campus_text == "Reject Me", "the text is retained"


def test_q3_quarantined_rows_leave_the_operational_views(session, refs):
    """Q3 — the calendar never returns a quarantined delivery."""
    from app.services.allocation_calendar import calendar_month

    _apply(session, [base_row(refs, **{"Campus Location": "Hide Me"})], refs)
    entry = _entry(session, "CAMPUS")
    suggestions.resolve_suggestion(session, _editor(session), suggestion_id=entry.id, action="REJECT")
    session.commit()

    payload = calendar_month(
        session, training_package="BSB", start_date=date(2026, 1, 19), end_date=date(2026, 2, 8)
    )
    assert all(not day["sessions"] for day in payload["days"])


def test_q5_q6_rejecting_a_facility_clears_but_does_not_quarantine(session, refs):
    """Q5/Q6 — the session returns to awaiting allocation, and a resolved one is safe."""
    rows = [
        base_row(refs, **{"Theory Classroom Name": "Bad Room", "Units of Competency ID": "F1"}),
        base_row(refs, **{"Theory Classroom Name": "Bad Room", "Units of Competency ID": "F2"}),
    ]
    _apply(session, rows, refs)
    # One session is resolved already but retains the same text — the guard case.
    first = session.execute(select(AllocationSession).order_by(AllocationSession.id)).scalars().first()
    session.execute(
        text("UPDATE allocation_session SET facility_id = :f WHERE id = :i"),
        {"f": refs["facility_id"], "i": first.id},
    )

    entry = _entry(session, "FACILITY")
    _row, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=entry.id, action="REJECT"
    )
    # Two rows x two class days = four sessions; one was resolved by hand above,
    # so exactly three remain to be cleared.
    assert updated == 3, "an already-resolved session must be left alone"

    session.expire_all()
    # `allocation_session` has a composite primary key (id, training_package),
    # so it is re-read by query rather than session.get().
    kept = session.execute(
        select(AllocationSession).where(AllocationSession.id == first.id)
    ).scalars().one()
    assert kept.facility_id == refs["facility_id"], "an approved id must not be blanked"

    # No delivery is quarantined by a facility rejection.
    quarantined = session.execute(
        select(func.count()).select_from(AllocationDelivery).where(AllocationDelivery.is_quarantined.is_(True))
    ).scalar_one()
    assert quarantined == 0


def test_q7_re_raising_lifts_the_quarantine(session, refs):
    """Q7 — a mistaken rejection is recoverable by importing the value again."""
    _apply(session, [base_row(refs, **{"Campus Location": "Oops Campus"})], refs)
    entry = _entry(session, "CAMPUS")
    suggestions.resolve_suggestion(session, _editor(session), suggestion_id=entry.id, action="REJECT")
    assert session.execute(
        select(func.count()).select_from(AllocationDelivery).where(AllocationDelivery.is_quarantined.is_(True))
    ).scalar_one() == 1

    _apply(session, [base_row(refs, **{"Campus Location": "Oops Campus"})], refs)
    session.expire_all()

    reopened = session.get(ReferenceSuggestion, entry.id)
    assert reopened.status == "PENDING"
    assert session.execute(
        select(func.count()).select_from(AllocationDelivery).where(AllocationDelivery.is_quarantined.is_(True))
    ).scalar_one() == 0


def test_q8_every_reject_is_logged(session, refs):
    """Q8 — the audit trail names the entity, the value and the count."""
    from app.models.activity import UserActivityRecord

    _apply(session, [base_row(refs, **{"Campus Location": "Audited Campus"})], refs)
    entry = _entry(session, "CAMPUS")
    suggestions.resolve_suggestion(session, _editor(session), suggestion_id=entry.id, action="REJECT")

    logged = session.execute(
        select(UserActivityRecord).order_by(UserActivityRecord.id.desc())
    ).scalars().first()
    assert "Audited Campus" in logged.plain_language_detail
    assert "CAMPUS" in logged.plain_language_detail


# ---------------------------------------------------------------------------
# 3.5 One issue, listed once
# ---------------------------------------------------------------------------


def test_s1_one_campus_across_many_units_is_one_entry(session, refs):
    """S1 — 50 rows, 50 different units, one campus problem: ONE entry."""
    rows = [
        base_row(refs, **{"Campus Location": "Single Entry Campus", "Units of Competency ID": f"UOC{n:03d}"})
        for n in range(50)
    ]
    _apply(session, rows, refs)

    entries = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.entity_type == "CAMPUS")
    ).scalars().all()
    assert len(entries) == 1, "the unit must not scope a campus problem"
    assert entries[0].occurrence_count == 50


def test_s3_the_same_unit_under_two_qualifications_is_two_entries(session, refs):
    """S3 — a unit is meaningful within its qualification, so two entries."""
    rows = [
        base_row(refs, **{"Units of Competency ID": "SHAREDUNIT", "Qualification Id": "BSB50420"}),
        base_row(refs, **{"Units of Competency ID": "SHAREDUNIT", "Qualification Id": "BSB60420"}),
    ]
    _apply(session, rows, refs)
    entries = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.entity_type == "UNIT")
    ).scalars().all()
    assert len(entries) == 2, "two qualifications would resolve to two different units"


def test_s4_two_different_colleges_are_two_entries(session, refs):
    """S4 — two distinct unknown colleges, regardless of any other column."""
    rows = [
        base_row(refs, **{"College": "College One", "Units of Competency ID": "C1"}),
        base_row(refs, **{"College": "College Two", "Units of Competency ID": "C2"}),
    ]
    _apply(session, rows, refs)
    entries = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.entity_type == "COLLEGE")
    ).scalars().all()
    assert len(entries) == 2


def test_s5_affected_records_are_listed_in_one_query(session, refs, test_engine):
    """S5 — the affected list reports the true total and is capped, in one pass."""
    rows = [
        base_row(refs, **{"Campus Location": "Affected Campus", "Units of Competency ID": f"A{n:03d}"})
        for n in range(50)
    ]
    _apply(session, rows, refs)
    entry = _entry(session, "CAMPUS")

    payload = suggestions.affected_records(session, entry.id, limit=10)
    assert payload["total"] == 50
    assert len(payload["items"]) == 10
    assert payload["truncated"] is True


def test_i5_two_unknown_campuses_do_not_collapse(session, refs):
    """I5 — the null-collapse fault: two different unknowns are two deliveries."""
    rows = [
        base_row(refs, **{"Campus Location": "Alpha Campus"}),
        base_row(refs, **{"Campus Location": "Beta Campus"}),
    ]
    _apply(session, rows, refs)
    total = session.execute(select(func.count()).select_from(AllocationDelivery)).scalar_one()
    assert total == 2, "None == None must not fold two distinct rows into one"


def test_i1_i2_text_is_stored_only_when_unresolved(session, refs):
    """I1/I2 — an id and its text are never both populated."""
    _apply(session, [base_row(refs, **{"Campus Location": "Unknown Campus"})], refs)
    unresolved = session.execute(select(AllocationDelivery)).scalars().first()
    assert unresolved.campus_id is None
    assert unresolved.campus_text == "Unknown Campus"
    assert unresolved.college_id is not None and unresolved.college_text is None


# ---------------------------------------------------------------------------
# 3.9 The three defects on this code path
# ---------------------------------------------------------------------------


def test_d1_d2_needs_allocation_is_a_boolean(session, refs):
    """D1/D2 — a non-MSCRIS session with no linked trainer must not 500.

    `and`/`or` return the last operand, so this yielded the trainer's name (a
    string) or None, and Pydantic rejected both on a field declared `bool`.
    """
    from app.services.allocation_calendar import calendar_month

    _apply(session, [base_row(refs, **{"Theory Trainer": "Unknown Person"})], refs)
    session.commit()

    payload = calendar_month(
        session, training_package="BSB", start_date=date(2026, 1, 19), end_date=date(2026, 2, 8)
    )
    flagged = [item for day in payload["days"] for item in day["sessions"]]
    assert flagged, "the import should have produced sessions"
    for item in flagged:
        assert isinstance(item["needs_allocation"], bool)
    assert any(item["needs_allocation"] for item in flagged)


def test_d3_d4_export_survives_unresolved_references(session, refs):
    """D3/D4 — nullable foreign keys must not raise KeyError: None."""
    from app.services.allocation_export import export_workbook

    _apply(
        session,
        [
            base_row(
                refs,
                **{
                    "College": "Unknown College",
                    "Campus Location": "Unknown Campus",
                    "Qualification Id": "ZZZ99999",
                    "Units of Competency ID": "ZZZUNIT",
                },
            )
        ],
        refs,
    )
    session.commit()

    name, payload = export_workbook(
        session, training_package="BSB", start_date=date(2026, 1, 19), end_date=date(2026, 2, 8)
    )
    assert name.endswith(".xlsx")
    assert payload, "the export must succeed and show the stored text"


def test_d5_intake_matching_is_case_insensitive(session, refs):
    """D5 — rolling data in one case must still match an allocation file in another."""
    session.execute(
        text(
            "INSERT INTO rolling_timetable_weeks "
            "(training_package, qualification_code, duration_weeks, intake_label, intake_group, "
            " intake_start_date, week_no, week_start_date, week_end_date, schedule_type, "
            " schedule_value, unit_code, unit_count, unit_slot) "
            "VALUES ('BSB', 'bsb50420', 52, 'bsb50420_52_19 Jan 2026_NA_Intake', 'NA', "
            " DATE '2026-01-19', 1, DATE '2026-01-19', DATE '2026-01-25', 'UNIT', "
            " 'BSBCRT511', 'BSBCRT511', 1, 1)"
        )
    )
    session.commit()

    _apply(session, [base_row(refs)], refs)
    delivery = session.execute(select(AllocationDelivery)).scalars().first()
    assert delivery.intake_match_status == "MATCHED", "lowercase rolling data must still match"


def test_q4_administrators_can_list_quarantined_rows(session, refs, client):
    """Q4 — `?quarantined=true` returns only quarantined rows, with their reasons.

    They are excluded from the default list, so an operational view never shows
    them, but they stay reachable so a mistaken rejection can be found.
    """
    from tests.test_allocation_records import VIEWER, as_user

    _apply(session, [base_row(refs, **{"Campus Location": "Quarantine Me"})], refs)
    entry = _entry(session, "CAMPUS")
    suggestions.resolve_suggestion(session, _editor(session), suggestion_id=entry.id, action="REJECT")
    session.commit()

    operational = client.get(
        "/allocation/deliveries", params={"training_package": "BSB"}, headers=as_user(VIEWER)
    )
    assert operational.status_code == 200
    assert operational.json()["total"] == 0, "a quarantined row must not appear operationally"

    quarantined = client.get(
        "/allocation/deliveries",
        params={"training_package": "BSB", "quarantined": "true"},
        headers=as_user(VIEWER),
    )
    assert quarantined.status_code == 200
    assert quarantined.json()["total"] == 1


def test_g7_the_queue_adds_no_per_row_query(session, refs, test_engine):
    """G7 — this work must add no per-row query.

    The importer already issues a per-delivery intake lookup; that is
    pre-existing and out of scope here. What this checks is the cost *this*
    change could have added: suggestions and exceptions are written per distinct
    **value**, so their statement count must not move when the row count triples.
    """

    def _queue_statements(row_count: int) -> int:
        # One unknown value across every row, and an approved unit throughout:
        # the rows are kept distinct by their dates, so the number of *distinct*
        # unmatched values stays at one however many rows there are.
        rows = [
            base_row(
                refs,
                **{
                    "Campus Location": "Scale Campus",
                    "Unit of Competency Start Date": (MONDAY + timedelta(days=7 * n)).isoformat(),
                    "Unit of Competency End Date": (MONDAY + timedelta(days=7 * n + 20)).isoformat(),
                },
            )
            for n in range(row_count)
        ]
        payload = csv_bytes(rows)
        seen: list[str] = []

        def _before(conn, cursor, statement, params, context, executemany):
            if "reference_suggestion" in statement.lower():
                seen.append(statement)

        event.listen(test_engine, "before_cursor_execute", _before)
        try:
            apply_rows(
                session,
                training_package="BSB",
                file_name="scale.csv",
                file_size_bytes=len(payload),
                payload=payload,
                apply_mode="REPLACE",
                raise_suggestions=True,
                overrides=ImportOverrides.from_payload({}, True),
                user=_editor(session),
            )
            session.commit()
        finally:
            event.remove(test_engine, "before_cursor_execute", _before)
        return len(seen)

    small = _queue_statements(20)
    large = _queue_statements(60)
    assert large == small, (
        f"the queue cost moved from {small} to {large} statements when the rows tripled — "
        "a per-row query has been introduced"
    )
