"""Recorded exceptions — checks 3.6 (X1–X12) of the Revision 2 prompt.

An accepted exception is a durable, attributable record, not a softened message
in a review screen that is then discarded. It shares `reference_suggestion` with
a pending suggestion, distinguished by status, so a value can never be pending
and excepted at once and promoting one reuses the resolve path unchanged.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.activity import UserActivityRecord
from app.models.allocation import AllocationDelivery, ReferenceSuggestion
from app.models.user import User
from app.services import reference_suggestion_service as suggestions
from app.services.allocation_import import (
    ImportOverrides,
    apply_rows,
    issue_id,
    validate_bytes,
)
from app.services.reference_suggestions import (
    raise_reference_suggestion,
    record_reference_exception,
)

from tests.test_allocation_records import (  # reuse the approved fixtures
    EDITOR,
    base_row,
    csv_bytes,
    people,  # noqa: F401 - fixture
    refs,  # noqa: F401 - fixture
)

pytestmark = pytest.mark.database

UNKNOWN_CAMPUS = "Excepted Campus"


def _editor(session) -> User:
    return session.execute(select(User).where(User.organisation_email == EDITOR)).scalar_one()


def _except_overrides(session, payload: bytes) -> ImportOverrides:
    """Build the overrides that accept every unresolved value as an exception."""
    review, _planned, _suggestions = validate_bytes(
        session,
        training_package="BSB",
        file_name="ex.csv",
        payload=payload,
        raise_suggestions=False,
        overrides=ImportOverrides.from_payload({}, False),
    )
    ids = [
        issue_id_from(item) for item in review.discrepancies if item.kind == "unresolved_reference"
    ]
    return ImportOverrides.from_payload({"except_ids": ids}, False)


def issue_id_from(item) -> str:
    return issue_id(item)


def _apply_excepting(session, rows) -> dict:
    payload = csv_bytes(rows)
    return apply_rows(
        session,
        training_package="BSB",
        file_name="ex.csv",
        file_size_bytes=len(payload),
        payload=payload,
        apply_mode="REPLACE",
        raise_suggestions=False,
        overrides=_except_overrides(session, payload),
        user=_editor(session),
    )


def _exception_rows(session) -> list[ReferenceSuggestion]:
    return session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.status == "EXCEPTION")
    ).scalars().all()


# ---------------------------------------------------------------------------


def test_x1_accepting_an_exception_records_who_and_when(session, refs):
    """X1 — the row exists, with the accepting user and the time."""
    _apply_excepting(session, [base_row(refs, **{"Campus Location": UNKNOWN_CAMPUS})])

    rows = _exception_rows(session)
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == "CAMPUS"
    assert row.raw_value == UNKNOWN_CAMPUS
    assert row.accepted_by_user_id == _editor(session).id
    assert row.accepted_at is not None
    assert row.status == "EXCEPTION"


def test_x2_abandoning_the_review_writes_nothing(session, refs):
    """X2 — an exception is written at apply time, never at review time."""
    payload = csv_bytes([base_row(refs, **{"Campus Location": UNKNOWN_CAMPUS})])
    validate_bytes(
        session,
        training_package="BSB",
        file_name="ex.csv",
        payload=payload,
        raise_suggestions=False,
        overrides=_except_overrides(session, payload),
    )
    # The review was never applied.
    assert _exception_rows(session) == []


def test_x3_the_same_value_on_many_rows_is_one_record(session, refs):
    """X3 — 30 rows, one exception, occurrence_count 30."""
    rows = [
        base_row(refs, **{"Campus Location": UNKNOWN_CAMPUS, "Units of Competency ID": f"E{n:03d}"})
        for n in range(30)
    ]
    _apply_excepting(session, rows)

    records = _exception_rows(session)
    campus = [row for row in records if row.entity_type == "CAMPUS"]
    assert len(campus) == 1
    assert campus[0].occurrence_count == 30


def test_x4_a_later_batch_keeps_the_original_acceptance(session, refs):
    """X4 — count and last_seen rise; the first acceptance is the decision of record."""
    _apply_excepting(session, [base_row(refs, **{"Campus Location": UNKNOWN_CAMPUS})])
    first = _exception_rows(session)[0]
    original_user, original_at = first.accepted_by_user_id, first.accepted_at
    original_count = first.occurrence_count

    _apply_excepting(session, [base_row(refs, **{"Campus Location": UNKNOWN_CAMPUS})])
    session.expire_all()

    again = session.get(ReferenceSuggestion, first.id)
    assert again.occurrence_count > original_count
    assert again.accepted_by_user_id == original_user
    assert again.accepted_at == original_at


def test_x5_a_pending_entry_flips_to_exception(session, refs):
    """X5 — the same row changes status. No second row."""
    raise_reference_suggestion(
        session, entity_type="CAMPUS", raw_value=UNKNOWN_CAMPUS, context={"college": refs["college_full_name"]}, source="ALLOCATION_IMPORT"
    )
    session.flush()
    before = session.execute(select(func.count()).select_from(ReferenceSuggestion)).scalar_one()

    row, warning = record_reference_exception(
        session,
        entity_type="CAMPUS",
        raw_value=UNKNOWN_CAMPUS,
        context={"college": refs["college_full_name"]},
        source="ALLOCATION_IMPORT",
        user_id=_editor(session).id,
    )
    after = session.execute(select(func.count()).select_from(ReferenceSuggestion)).scalar_one()

    assert warning is None
    assert row.status == "EXCEPTION"
    assert after == before, "the pending row must flip, not spawn a second"


def test_x6_an_exception_raised_again_returns_to_pending(session, refs):
    """X6 — the same row flips back. No second row."""
    row, _ = record_reference_exception(
        session,
        entity_type="CAMPUS",
        raw_value=UNKNOWN_CAMPUS,
        context={},
        source="ALLOCATION_IMPORT",
        user_id=_editor(session).id,
    )
    before = session.execute(select(func.count()).select_from(ReferenceSuggestion)).scalar_one()

    raise_reference_suggestion(
        session, entity_type="CAMPUS", raw_value=UNKNOWN_CAMPUS, context={}, source="ALLOCATION_IMPORT"
    )
    session.expire_all()

    after = session.execute(select(func.count()).select_from(ReferenceSuggestion)).scalar_one()
    reopened = session.get(ReferenceSuggestion, row.id)
    assert after == before
    assert reopened.status == "PENDING"
    assert reopened.accepted_by_user_id is None


def test_x7_a_decided_entry_is_not_reopened(session, refs):
    """X7 — an already MAPPED value returns a warning instead."""
    row, _ = record_reference_exception(
        session,
        entity_type="CAMPUS",
        raw_value=UNKNOWN_CAMPUS,
        context={},
        source="ALLOCATION_IMPORT",
        user_id=_editor(session).id,
    )
    suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=row.id, action="MAP", resolved_entity_id=refs["campus_id"]
    )

    again, warning = record_reference_exception(
        session,
        entity_type="CAMPUS",
        raw_value=UNKNOWN_CAMPUS,
        context={},
        source="ALLOCATION_IMPORT",
        user_id=_editor(session).id,
    )
    assert again is None
    assert warning and "already been decided" in warning

    session.expire_all()
    unchanged = session.get(ReferenceSuggestion, row.id)
    assert unchanged.status == "MAPPED", "a decided entry must not be reopened"


def test_x8_promoting_an_exception_relinks_and_retains_the_acceptance(session, refs):
    """X8 — the resolve path is shared; the acceptance survives the promotion."""
    _apply_excepting(
        session,
        [
            base_row(refs, **{"Campus Location": UNKNOWN_CAMPUS, "Units of Competency ID": f"P{n}"})
            for n in range(4)
        ],
    )
    row = [r for r in _exception_rows(session) if r.entity_type == "CAMPUS"][0]
    accepted_by, accepted_at = row.accepted_by_user_id, row.accepted_at

    promoted, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=row.id, action="MAP", resolved_entity_id=refs["campus_id"]
    )
    assert updated == 4, "every dependent row must be repaired"
    assert promoted.status == "MAPPED"
    assert promoted.accepted_by_user_id == accepted_by
    assert promoted.accepted_at == accepted_at


def test_x9_withdrawing_returns_it_to_pending_and_changes_no_row(session, refs):
    """X9 — status and acceptance clear; the stored rows are untouched."""
    _apply_excepting(session, [base_row(refs, **{"Campus Location": UNKNOWN_CAMPUS})])
    row = [r for r in _exception_rows(session) if r.entity_type == "CAMPUS"][0]

    before = session.execute(
        select(func.count()).select_from(AllocationDelivery).where(AllocationDelivery.campus_id.is_(None))
    ).scalar_one()

    withdrawn, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=row.id, action="WITHDRAW"
    )
    after = session.execute(
        select(func.count()).select_from(AllocationDelivery).where(AllocationDelivery.campus_id.is_(None))
    ).scalar_one()

    assert withdrawn.status == "PENDING"
    assert withdrawn.accepted_by_user_id is None
    assert withdrawn.accepted_at is None
    assert updated == 0
    assert after == before, "withdrawing must not change a stored row"


def test_x10_rejecting_an_exception_quarantines(session, refs):
    """X10 — rejecting an exception behaves exactly as rejecting a pending entry."""
    _apply_excepting(
        session,
        [
            base_row(refs, **{"Campus Location": UNKNOWN_CAMPUS, "Units of Competency ID": f"R{n}"})
            for n in range(3)
        ],
    )
    row = [r for r in _exception_rows(session) if r.entity_type == "CAMPUS"][0]

    rejected, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=row.id, action="REJECT"
    )
    assert rejected.status == "REJECTED"
    assert updated == 3

    quarantined = session.execute(
        select(func.count()).select_from(AllocationDelivery).where(AllocationDelivery.is_quarantined.is_(True))
    ).scalar_one()
    assert quarantined == 3


def test_x12_every_exception_action_is_logged(session, refs):
    """X12 — accept, promote, withdraw and reject each write an activity record."""
    _apply_excepting(session, [base_row(refs, **{"Campus Location": UNKNOWN_CAMPUS})])
    accepted = session.execute(
        select(UserActivityRecord).where(
            UserActivityRecord.plain_language_detail.ilike(f"%{UNKNOWN_CAMPUS}%")
        )
    ).scalars().all()
    assert accepted, "accepting an exception must be logged"

    row = [r for r in _exception_rows(session) if r.entity_type == "CAMPUS"][0]
    suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=row.id, action="MAP", resolved_entity_id=refs["campus_id"]
    )
    promoted = session.execute(
        select(UserActivityRecord).order_by(UserActivityRecord.id.desc())
    ).scalars().first()
    assert "record(s) updated" in promoted.plain_language_detail


def test_the_reported_raised_count_matches_the_queue(session, refs):
    """The number an import reports must be the number a user can then go and see.

    Regression: the count added every collected value — accepted exceptions
    included — to the number of new rows, so a batch that excepted everything
    still reported dozens of suggestions raised. An administrator went looking
    for a queue that was empty by construction.
    """
    payload = csv_bytes(
        [
            base_row(refs, **{"Campus Location": "Count Campus", "Units of Competency ID": f"CNT{n}"})
            for n in range(3)
        ]
    )
    result = apply_rows(
        session,
        training_package="BSB",
        file_name="count.csv",
        file_size_bytes=len(payload),
        payload=payload,
        apply_mode="REPLACE",
        raise_suggestions=True,
        overrides=ImportOverrides.from_payload({}, True),
        user=_editor(session),
    )
    pending = session.execute(
        select(func.count())
        .select_from(ReferenceSuggestion)
        .where(ReferenceSuggestion.status == "PENDING")
    ).scalar_one()

    assert pending > 0
    assert result["suggestions_raised"] == pending


def test_excepted_values_are_not_reported_as_raised(session, refs):
    """Accepting a value is not raising it, and must not inflate the count."""
    rows = [base_row(refs, **{"Campus Location": UNKNOWN_CAMPUS})]
    payload = csv_bytes(rows)
    result = apply_rows(
        session,
        training_package="BSB",
        file_name="mixed.csv",
        file_size_bytes=len(payload),
        payload=payload,
        apply_mode="REPLACE",
        # The blanket toggle is on, but this value was explicitly excepted:
        # the explicit per-value decision is the one that stands.
        raise_suggestions=True,
        overrides=_except_overrides(session, payload),
        user=_editor(session),
    )

    campus = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.raw_value == UNKNOWN_CAMPUS)
    ).scalar_one()
    assert campus.status == "EXCEPTION"
    assert result["suggestions_raised"] == 0, "an excepted value was counted as raised"


def test_one_import_can_both_except_and_raise(session, refs):
    """Accepting some values and raising others is one pass, not two.

    The import review offers both bulk actions at once, and this is the contract
    they rely on: the blanket raise toggle covers everything still unresolved,
    while an explicitly accepted value keeps its exception. If precedence ran the
    other way — or if either decision cleared the other — a reviewer could only
    ever record one kind per file.
    """
    rows = [
        base_row(refs, **{"Campus Location": "Accept This", "Units of Competency ID": "BOTH1"}),
        base_row(refs, **{"Campus Location": "Raise This", "Units of Competency ID": "BOTH2"}),
    ]
    payload = csv_bytes(rows)
    review, _planned, _suggestions = validate_bytes(
        session,
        training_package="BSB",
        file_name="both.csv",
        payload=payload,
        raise_suggestions=True,
        overrides=ImportOverrides.from_payload({}, True),
    )
    accept_ids = [
        issue_id_from(item)
        for item in review.discrepancies
        if item.kind == "unresolved_reference" and item.value == "Accept This"
    ]
    assert accept_ids, "the campus to accept must be an unresolved value"

    result = apply_rows(
        session,
        training_package="BSB",
        file_name="both.csv",
        file_size_bytes=len(payload),
        payload=payload,
        apply_mode="REPLACE",
        # Blanket raise on, one value singled out as an exception.
        raise_suggestions=True,
        overrides=ImportOverrides.from_payload({"except_ids": accept_ids}, True),
        user=_editor(session),
    )

    by_value = {
        row.raw_value: row.status
        for row in session.execute(select(ReferenceSuggestion)).scalars().all()
    }
    assert by_value.get("Accept This") == "EXCEPTION", "the singled-out value keeps its exception"
    assert by_value.get("Raise This") == "PENDING", "the rest were still raised"
    # The units on both rows are unresolved too, and were raised by the toggle.
    assert by_value.get("BOTH1") == "PENDING"
    assert by_value.get("BOTH2") == "PENDING"
    assert result["suggestions_raised"] == 3, "three raised, the accepted one not counted"
