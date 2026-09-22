"""What each allocation-import issue offers (approved 15 September 2026).

Suggestions and exceptions are separate, and the kind of issue decides which:

* a value that matches no approved record, or a class no rolling-timetable
  intake accounts for, is raised as a suggestion - never accepted as an
  exception;
* a broken rule on a row that can still be stored is accepted as an exception
  for this import only - never raised;
* a value the database cannot hold is edited, or its row is excluded.

Replaces `test_reference_exceptions.py`, which covered the retired rule that an
unmatched value could be accepted and recorded as an exception.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text

from app.models.allocation import AllocationDelivery, AllocationDeliveryIntake, ReferenceSuggestion
from app.models.user import User
from app.services import reference_suggestion_service as suggestions
from app.services.allocation_import import ImportOverrides, apply_rows, review_to_dict, validate_bytes

from tests.test_allocation_records import (  # reuse the approved fixtures
    EDITOR,
    base_row,
    csv_bytes,
    people,  # noqa: F401 - fixture
    refs,  # noqa: F401 - fixture
)

pytestmark = pytest.mark.database

TEST_INTAKE = "ZZ_RULES_TEST_52_Intake"


def _editor(session) -> User:
    return session.execute(select(User).where(User.organisation_email == EDITOR)).scalar_one()


def _review(session, rows, *, raise_suggestions=False, **decisions):
    payload = csv_bytes(rows)
    review, planned, collected = validate_bytes(
        session,
        training_package="BSB",
        file_name="rules.csv",
        payload=payload,
        raise_suggestions=raise_suggestions,
        overrides=ImportOverrides.from_payload(decisions, raise_suggestions),
    )
    return payload, review, planned, collected


def _apply(session, payload, *, raise_suggestions=False, **decisions) -> dict:
    return apply_rows(
        session,
        training_package="BSB",
        file_name="rules.csv",
        file_size_bytes=len(payload),
        payload=payload,
        apply_mode="REPLACE",
        raise_suggestions=raise_suggestions,
        overrides=ImportOverrides.from_payload(decisions, raise_suggestions),
        user=_editor(session),
    )


def _offered(review, kind: str) -> list[dict]:
    return [item for item in review_to_dict(review)["discrepancies"] if item["kind"] == kind]


def _contradiction(refs) -> list:
    """F2FV promises two virtual theory days; the row names a physical room for both."""
    return base_row(refs, **{"Mode of Delivery": "F2FV"})


@pytest.fixture()
def intake(session):
    """An intake of BSB50420 (52 weeks) far from the base row's dates.

    Its first week is returned: an intake has no row of its own, and Map is given
    one of its weeks. Removed afterwards, because rolling weeks are not among
    the tables the suite empties before each test.
    """
    params = {"label": TEST_INTAKE}
    session.execute(text("DELETE FROM rolling_timetable_weeks WHERE intake_label = :label"), params)
    week_id = session.execute(
        text(
            "INSERT INTO rolling_timetable_weeks "
            "(training_package, qualification_code, duration_weeks, intake_label, intake_group, "
            " intake_start_date, week_no, week_start_date, week_end_date, schedule_type, "
            " schedule_value, unit_code, unit_count, unit_slot) "
            "VALUES ('BSB', 'BSB50420', 52, :label, 'NA', DATE '2031-01-06', 1, "
            " DATE '2031-01-06', DATE '2031-01-12', 'BREAK', 'Break', NULL, 0, 1) RETURNING id"
        ),
        params,
    ).scalar_one()
    session.commit()
    yield week_id
    session.rollback()
    session.execute(text("DELETE FROM rolling_timetable_weeks WHERE intake_label = :label"), params)
    session.commit()


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------


def test_an_unmatched_value_is_raised_and_never_accepted(session, refs):
    rows = [base_row(refs, **{"Theory Classroom Name": "Ghost Room"})]
    _payload, review, _planned, _collected = _review(session, rows)
    room = next(item for item in _offered(review, "unresolved_reference") if item["value"] == "Ghost Room")
    assert room["category"] == "SUGGESTION"
    assert room["can_raise_suggestion"]
    assert not room["can_except"]
    assert not room["can_exclude"]

    # An exception id for it settles nothing.
    _payload, excepted, _planned, _collected = _review(session, rows, except_ids=[room["issue_id"]])
    assert excepted.refused
    assert any(
        item.kind == "unresolved_reference" and item.value == "Ghost Room" and item.severity == "refuse"
        for item in excepted.discrepancies
    )


def test_raised_suggestions_carry_the_row_values_for_add(session, refs):
    rows = [
        base_row(
            refs,
            **{
                "Units of Competency ID": "ZZNEW01",
                "Units of Competency Title": "A brand new unit",
                "Theory Classroom Name": "Room Nine",
                "Theory Trainer": "Nobody Known",
            },
        )
    ]
    _apply(session, csv_bytes(rows), raise_suggestions=True)
    by_type = {row.entity_type: row for row in session.execute(select(ReferenceSuggestion)).scalars()}

    unit = by_type["UNIT"]
    assert unit.context == {"qualification": "BSB50420"}
    assert unit.attributes["unit_title"] == "A brand new unit"
    assert unit.attributes["uoc_type"]

    room = by_type["FACILITY"]
    assert room.attributes["colleges"] == [refs["college_full_name"]]
    assert room.attributes["streams"] == ["THEORY"]

    trainer = by_type["TRAINER"]
    assert trainer.attributes["campuses"] == [refs["campus_location"]]
    assert trainer.attributes["units"] == [{"qualification": "BSB50420", "unit": "ZZNEW01"}]


def test_a_class_no_intake_accounts_for_is_raised_to_the_rolling_timetable(session, refs, intake):
    rows = [
        base_row(
            refs,
            **{"Units of Competency ID": "ZZROLL1", "Units of Competency Title": "Rolling test unit"},
        )
    ]
    # The unit is unmatched too, and an unraised unit refuses the row before its
    # intake is looked for - so the unit alone is raised first.
    _payload, first, _planned, _collected = _review(session, rows)
    [unit] = [item for item in _offered(first, "unresolved_reference") if item["value"] == "ZZROLL1"]
    _payload, review, _planned, _collected = _review(session, rows, raise_ids=[unit["issue_id"]])
    [gap] = _offered(review, "no_rolling_intake")
    assert gap["category"] == "SUGGESTION"
    assert gap["can_raise_suggestion"] and not gap["can_except"]
    assert gap["severity"] == "refuse", "an unraised gap blocks the import"

    _apply(session, csv_bytes(rows), raise_suggestions=True)
    entry = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.entity_type == "ROLLING")
    ).scalars().one()
    assert entry.context == {
        "qualification": "BSB50420",
        "duration_weeks": "52",
        "start_date": "2026-01-19",
        "end_date": "2026-02-08",
    }
    assert entry.attributes["unit_title"] == "Rolling test unit"
    assert suggestions.unresolved_total(session, "ROLLING", entry.normalised_value, entry.context) == 1

    options = suggestions.map_options(session, entry.id)
    assert intake in [item["id"] for item in options["items"]]

    _row, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=entry.id, action="MAP", resolved_entity_id=intake
    )
    assert updated == 1
    delivery = session.execute(select(AllocationDelivery)).scalars().one()
    session.refresh(delivery)
    assert delivery.intake_match_status == "MATCHED"
    assert session.execute(select(AllocationDeliveryIntake.intake_label)).scalars().all() == [TEST_INTAKE]
    assert suggestions.unresolved_total(session, "ROLLING", entry.normalised_value, entry.context) == 0


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


def test_a_broken_rule_is_accepted_and_never_raised(session, refs):
    _payload, review, _planned, collected = _review(session, [_contradiction(refs)], raise_suggestions=True)
    [rule] = _offered(review, "mode_contradicts_classrooms")
    assert rule["category"] == "EXCEPTION"
    assert rule["can_except"]
    assert rule["can_exclude"], "every broken rule offers Exclude too"
    assert not rule["can_raise_suggestion"]
    assert rule["severity"] == "refuse"
    assert review.refused
    assert collected == {}, "raising everything must not raise a broken rule"


def test_an_accepted_exception_is_stored_as_written(session, refs):
    payload, review, _planned, _collected = _review(session, [_contradiction(refs)], raise_suggestions=True)
    [rule] = _offered(review, "mode_contradicts_classrooms")

    result = _apply(session, payload, raise_suggestions=True, except_ids=[rule["issue_id"]])
    assert result["deliveries_written"] == 1
    assert result["exceptions_accepted"] == 1
    stored = session.execute(select(AllocationDelivery)).scalars().one()
    assert stored.mode_of_delivery == "F2FV"
    # The acceptance is not recorded in the suggestion queue.
    held = session.execute(
        select(func.count()).select_from(ReferenceSuggestion).where(ReferenceSuggestion.status == "EXCEPTION")
    ).scalar_one()
    assert held == 0


def test_an_acceptance_lasts_for_this_import_only(session, refs):
    payload, review, _planned, _collected = _review(session, [_contradiction(refs)], raise_suggestions=True)
    [rule] = _offered(review, "mode_contradicts_classrooms")
    _apply(session, payload, raise_suggestions=True, except_ids=[rule["issue_id"]])

    _payload, again, _planned, _collected = _review(session, [_contradiction(refs)], raise_suggestions=True)
    [asked_again] = _offered(again, "mode_contradicts_classrooms")
    assert asked_again["severity"] == "refuse", "the next import must ask again"
    assert again.refused


# ---------------------------------------------------------------------------
# Values the database cannot hold
# ---------------------------------------------------------------------------


def test_a_value_the_database_cannot_hold_is_edited_or_excluded(session, refs):
    rows = [base_row(refs, **{"Unit of Competency Start Date": "1/2/2026"})]
    _payload, review, _planned, _collected = _review(session, rows, raise_suggestions=True)
    [bad] = _offered(review, "unreadable_or_ambiguous_date")
    assert bad["category"] == "UNSTORABLE"
    assert bad["can_exclude"] and bad["can_edit"]
    assert not bad["can_except"] and not bad["can_raise_suggestion"]

    _payload, excepted, _planned, _collected = _review(
        session, rows, raise_suggestions=True, except_ids=[bad["issue_id"]]
    )
    assert excepted.refused, "a value that cannot be stored cannot be accepted"


def test_excluding_a_row_imports_the_rest_and_raises_nothing_from_it(session, refs):
    rows = [
        base_row(refs),
        base_row(
            refs,
            **{
                "Unit of Competency Start Date": "1/2/2026",
                "Theory Classroom Name": "Excluded Room",
                "Units of Competency ID": "ZZEXCL1",
            },
        ),
    ]
    _payload, review, _planned, _collected = _review(session, rows, raise_suggestions=True)
    assert review.refused

    payload, excluded, _planned, collected = _review(session, rows, raise_suggestions=True, exclude_rows=[3])
    assert not excluded.refused
    assert [item.kind for item in excluded.discrepancies if item.row_number == 3] == ["row_excluded"]
    assert all(entry["raw_value"] != "Excluded Room" for entry in collected.values())

    result = _apply(session, payload, raise_suggestions=True, exclude_rows=[3])
    assert result["deliveries_written"] == 1
    assert result["rows_excluded"] == 1


# ---------------------------------------------------------------------------
# Every predefined rule is handled alike (amended 15 September 2026)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "kind"),
    [
        ({"MSCRIS Class Name": "Face to Face Virtual", "MSCRIS Days and Times": "Friday- 9 am to 2 pm"}, "weekday_not_allowed"),
        ({"Theory Class Days and Times": "Wednesday- 5 pm to 9 am\nThursday- 9 am to 5 pm"}, "class_ends_before_it_starts"),
        ({"Unit of Competency Start Date": "2026-02-08", "Unit of Competency End Date": "2026-01-19"}, "end_before_start"),
        ({"Theory Classroom Name": "Wednesday- Room 1\nFriday- Room 1"}, "classroom_or_trainer_day_without_class"),
    ],
)
def test_every_broken_rule_offers_accept_exclude_and_edit(session, refs, overrides, kind):
    _payload, review, _planned, _collected = _review(session, [base_row(refs, **overrides)], raise_suggestions=True)
    [rule] = _offered(review, kind)
    assert rule["category"] == "EXCEPTION"
    assert rule["can_except"] and rule["can_exclude"] and rule["can_edit"]
    assert not rule["can_raise_suggestion"]


def test_an_accepted_mscris_friday_is_stored_on_friday(session, refs):
    """MSCRIS runs on Saturday. Accepted for this import, the class is stored on the day the file gave."""
    from app.models.allocation import AllocationSession

    row = base_row(
        refs,
        **{"MSCRIS Class Name": "Face to Face Virtual", "MSCRIS Days and Times": "Friday- 9 am to 2 pm"},
    )
    payload, review, _planned, _collected = _review(session, [row], raise_suggestions=True)
    [rule] = _offered(review, "weekday_not_allowed")
    # The whole days-and-times cell is offered for editing, not the day alone.
    assert rule["edit_fields"] == [{"column": "MSCRIS Days and Times", "value": "Friday- 9 am to 2 pm"}]

    result = _apply(session, payload, raise_suggestions=True, except_ids=[rule["issue_id"]])
    assert result["exceptions_accepted"] >= 1
    mscris = session.execute(
        select(AllocationSession).where(AllocationSession.stream == "MSCRIS")
    ).scalars().one()
    assert mscris.weekday == "FRIDAY"
    assert mscris.delivery_mode == "VIRTUAL"


def test_editing_one_line_keeps_the_rest_of_the_cell(session, refs):
    """A problem on one line of a multi-day cell offers the whole cell."""
    cell = "Wednesday- Room 1\nFriday- Room 1"
    _payload, review, _planned, _collected = _review(
        session, [base_row(refs, **{"Theory Classroom Name": cell})], raise_suggestions=True
    )
    [rule] = _offered(review, "classroom_or_trainer_day_without_class")
    assert rule["edit_fields"] == [{"column": "Theory Classroom Name", "value": cell}]


# ---------------------------------------------------------------------------
# One entry per value (15 September 2026)
# ---------------------------------------------------------------------------


def test_one_unknown_trainer_is_one_entry_whatever_the_college(session, refs):
    """A trainer is not held per college, so the same name at two colleges is one entry."""
    rows = [
        base_row(refs, **{"Theory Trainer": "Nobody Known", "Units of Competency ID": "BSBCRT511"}),
        base_row(
            refs,
            **{
                "College": "Another College",
                "Theory Trainer": "Nobody Known",
                "Units of Competency ID": "ZZTWO01",
            },
        ),
    ]
    _apply(session, csv_bytes(rows), raise_suggestions=True)
    entries = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.entity_type == "TRAINER")
    ).scalars().all()
    assert len(entries) == 1
    assert entries[0].context == {}
    assert sorted(entries[0].attributes["colleges"]) == sorted([refs["college_full_name"], "Another College"])


def test_resolving_an_entry_closes_the_siblings_it_emptied(session, refs):
    """An older entry for the same name, keyed by college, goes when Map repairs its rows."""
    from app.services.reference_suggestions import raise_reference_suggestion

    _apply(session, csv_bytes([base_row(refs, **{"Theory Trainer": "Sibling Trainer"})]), raise_suggestions=True)
    raise_reference_suggestion(
        session, entity_type="TRAINER", raw_value="Sibling Trainer", context={"college": "OLD"}, source="ALLOCATION_IMPORT"
    )
    current = session.execute(
        select(ReferenceSuggestion).where(
            ReferenceSuggestion.entity_type == "TRAINER", ReferenceSuggestion.context_key == "{}"
        )
    ).scalars().one()

    suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=current.id, action="MAP", resolved_entity_id=refs["trainer_id"]
    )
    remaining = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.raw_value == "Sibling Trainer")
    ).scalars().all()
    assert [entry.id for entry in remaining] == [current.id], "the emptied sibling was removed"


def test_affected_records_name_the_class_they_belong_to(session, refs):
    _apply(session, csv_bytes([base_row(refs, **{"Theory Trainer": "Listed Trainer"})]), raise_suggestions=True)
    entry = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.entity_type == "TRAINER")
    ).scalars().one()
    affected = suggestions.affected_records(session, entry.id)
    assert affected["total"] == 2
    first = affected["items"][0]
    assert first["kind"] == "session"
    assert first["qualification_code"] == "BSB50420"
    assert first["unit_code"] == "BSBCRT511"
    assert first["campus"] == "Test Campus"
    assert first["start_date"] == "2026-01-19"
    assert first["weekday"] in {"WEDNESDAY", "THURSDAY"}
    assert first["start_time"] == "09:00" and first["end_time"] == "17:00"


def test_rejecting_a_rolling_gap_deletes_the_classes_no_intake_accounts_for(session, refs, intake):
    """Approved 16 September 2026: an unapproved class is removed, not left unmatched."""
    rows = [
        base_row(
            refs,
            **{"Units of Competency ID": "ZZROLL9", "Units of Competency Title": "Rolling reject unit"},
        )
    ]
    _apply(session, csv_bytes(rows), raise_suggestions=True)
    entry = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.entity_type == "ROLLING")
    ).scalars().one()
    before = session.execute(select(func.count()).select_from(AllocationDelivery)).scalar_one()

    _row, updated = suggestions.resolve_suggestion(
        session, _editor(session), suggestion_id=entry.id, action="REJECT"
    )
    assert updated == 1
    assert session.execute(select(func.count()).select_from(AllocationDelivery)).scalar_one() == before - 1
    # The rolling timetable itself is never touched by a rejection.
    assert session.execute(
        text("SELECT count(*) FROM rolling_timetable_weeks WHERE intake_label = :label"),
        {"label": TEST_INTAKE},
    ).scalar_one() == 1
