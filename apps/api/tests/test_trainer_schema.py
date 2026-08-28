"""Trainer schema guarantees (checks M3 to M8).

These assert against the **live database**, not the model definitions. A model
that declares a constraint the migration never created would pass a test written
against the model and fail in production, which is exactly the class of fault
these checks exist to catch.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.trainer import Trainer, TrainerAvailability

from tests.test_trainer_api import (  # reuse the approved fixtures
    NINE_TO_FIVE,
    client,  # noqa: F401 - fixture
    people,  # noqa: F401 - fixture
    refs,  # noqa: F401 - fixture
)

pytestmark = pytest.mark.database


def _columns(session, table: str) -> dict[str, str]:
    return {
        row[0]: row[1]
        for row in session.execute(
            text(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_name = :t"
            ),
            {"t": table},
        ).all()
    }


def test_m3_campuses_carry_the_location_dictionary_columns(session):
    """M3 — `city` and `approved_address`, both nullable, plus the index."""
    columns = _columns(session, "campuses")
    assert columns.get("city") == "YES", "a campus recorded before this has no city"
    assert columns.get("approved_address") == "YES"

    indexes = {
        row[0]
        for row in session.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'campuses'")
        ).all()
    }
    assert "ix_campuses_state_city" in indexes


def test_m3_campus_location_was_not_repurposed(session):
    """The allocation importer and the export both read `campus_location`."""
    columns = _columns(session, "campuses")
    assert columns.get("campus_location") == "NO", "still required, still its own meaning"


def test_m4_trainer_units_are_scoped_by_qualification(session):
    """M4 — the unique covers the triple, and the old two-column unique is gone.

    Since 27 August 2026 it is an **expression** index rather than a constraint:
    either half may be an unmatched value held as text, and a plain unique would
    stop deduplicating the moment `unit_id` became nullable, because PostgreSQL
    treats NULLs as distinct.
    """
    columns = _columns(session, "trainer_units")
    assert "qualification_id" in columns
    assert columns.get("unit_text") == "YES"
    assert columns.get("qualification_text") == "YES"
    assert columns.get("unit_id") == "YES", "nullable, so a raised value can import"

    uniques = {
        row[0]
        for row in session.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'trainer_units'::regclass AND contype = 'u'"
            )
        ).all()
    }
    assert "uq_trainer_units_trainer_id_unit_id" not in uniques, (
        "the old unique would collapse a unit taught under two qualifications"
    )

    definition = session.execute(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_trainer_units_link'")
    ).scalar_one()
    assert "UNIQUE" in definition
    for fragment in ("trainer_id", "qualification_id", "unit_id", "unit_text", "qualification_text"):
        assert fragment in definition, f"{fragment} is not part of the link identity"


def test_a_link_must_say_what_it_means(session, refs):
    """Neither an approved id nor a raw value is not a state a row may hold."""
    trainer = Trainer(trainer_id="TU_TEXT", trainer_name="Text Holder")
    session.add(trainer)
    session.flush()
    # A raw INSERT is executed at once, so the refusal happens here rather
    # than at flush.
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO trainer_units (trainer_id, qualification_id, unit_id, unit_text, "
                "qualification_text) VALUES (:t, NULL, NULL, NULL, NULL)"
            ),
            {"t": trainer.id},
        )
    session.rollback()


def test_the_same_unmatched_unit_is_not_stored_twice(session, refs):
    """The expression unique holds where a plain one could not: two identical
    unmatched values for one trainer are the same link."""
    from app.models.trainer import TrainerUnit

    trainer = Trainer(trainer_id="TU_DUP", trainer_name="Repeat Text")
    session.add(trainer)
    session.flush()
    for _ in range(2):
        session.add(
            TrainerUnit(
                trainer_id=trainer.id,
                qualification_id=refs["bsb40920"],
                unit_id=None,
                unit_text="BSBNOTREAL",
            )
        )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_m5_availability_supports_a_trainer_with_no_campus(session):
    """M5 — nullable campus, plus the three columns offshore needs."""
    columns = _columns(session, "trainer_availability")
    assert columns.get("campus_id") == "YES"
    assert columns.get("location_text") == "YES"
    assert columns.get("is_offshore") == "NO", "a row is offshore or it is not"
    assert columns.get("working_time_text") == "YES"


def test_m6_two_offshore_rows_for_one_trainer_are_rejected(session, refs):
    """M6 — the partial unique holds where the old constraint could not.

    PostgreSQL treats NULLs as distinct, so the original
    `UNIQUE (trainer_id, campus_id, class_type, working_time_start)` stopped
    deduplicating the moment `campus_id` became nullable.
    """
    trainer = Trainer(trainer_id="M6_ONE", trainer_name="Offshore Person")
    session.add(trainer)
    session.flush()

    def offshore_row():
        return TrainerAvailability(
            trainer_id=trainer.id,
            campus_id=None,
            is_offshore=True,
            location_text="Offshore",
            class_type="THEORY",
            working_time_start=NINE_TO_FIVE[0],
            working_time_end=NINE_TO_FIVE[1],
            monday="PHYSICAL",
            tuesday="PHYSICAL",
            wednesday="PHYSICAL",
            thursday="PHYSICAL",
            friday="PHYSICAL",
        )

    session.add(offshore_row())
    session.flush()
    session.add(offshore_row())
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_m6_the_campus_partial_unique_still_holds(session, refs):
    trainer = Trainer(trainer_id="M6_TWO", trainer_name="Campus Person")
    session.add(trainer)
    session.flush()

    def campus_row():
        return TrainerAvailability(
            trainer_id=trainer.id,
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

    session.add(campus_row())
    session.flush()
    session.add(campus_row())
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_m6_the_same_trainer_may_hold_two_different_campuses(session, refs):
    """The real file's `TI_002_EN`: Blacktown and Haymarket, one trainer."""
    trainer = Trainer(trainer_id="M6_THREE", trainer_name="Two Campuses")
    session.add(trainer)
    session.flush()
    for campus in ("blacktown", "haymarket"):
        session.add(
            TrainerAvailability(
                trainer_id=trainer.id,
                campus_id=refs[campus],
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
    session.flush()  # must not raise


def test_m7_class_type_holds_all_three_values(session):
    """M7 — the form already offered a third option the database could not store."""
    labels = {
        row[0]
        for row in session.execute(
            text("SELECT enumlabel FROM pg_enum WHERE enumtypid = 'class_type'::regtype")
        ).all()
    }
    assert labels == {"THEORY", "PRACTICAL", "THEORY_AND_PRACTICAL"}


def test_the_queue_can_say_a_value_came_from_a_trainer_file(session):
    labels = {
        row[0]
        for row in session.execute(
            text("SELECT enumlabel FROM pg_enum WHERE enumtypid = 'suggestion_source'::regtype")
        ).all()
    }
    assert "TRAINER_IMPORT" in labels


def test_m8_offshore_and_a_campus_cannot_both_be_true(session, refs):
    """M8 — the two states are different, not overlapping."""
    trainer = Trainer(trainer_id="M8_ONE", trainer_name="Confused Person")
    session.add(trainer)
    session.flush()
    session.add(
        TrainerAvailability(
            trainer_id=trainer.id,
            campus_id=refs["hobart"],
            is_offshore=True,  # refused: offshore means no campus
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
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_a_unit_may_be_held_under_two_qualifications(session, refs):
    """The whole reason `qualification_id` was added — 98 such pairs are real."""
    from app.models.trainer import TrainerUnit

    trainer = Trainer(trainer_id="TU_ONE", trainer_name="Two Qualifications")
    session.add(trainer)
    session.flush()
    session.add_all(
        [
            TrainerUnit(
                trainer_id=trainer.id, qualification_id=refs["bsb40920"], unit_id=refs["shared"]
            ),
            TrainerUnit(
                trainer_id=trainer.id, qualification_id=refs["bsb50820"], unit_id=refs["shared"]
            ),
        ]
    )
    session.flush()  # the old unique would have refused this

    held = session.execute(
        text("SELECT count(*) FROM trainer_units WHERE trainer_id = :t"), {"t": trainer.id}
    ).scalar_one()
    assert held == 2


def test_the_same_triple_twice_is_still_refused(session, refs):
    from app.models.trainer import TrainerUnit

    trainer = Trainer(trainer_id="TU_TWO", trainer_name="Repeat")
    session.add(trainer)
    session.flush()
    for _ in range(2):
        session.add(
            TrainerUnit(
                trainer_id=trainer.id, qualification_id=refs["bsb40920"], unit_id=refs["shared"]
            )
        )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_working_time_must_end_after_it_starts(session, refs):
    trainer = Trainer(trainer_id="WT_ONE", trainer_name="Backwards")
    session.add(trainer)
    session.flush()
    session.add(
        TrainerAvailability(
            trainer_id=trainer.id,
            campus_id=refs["hobart"],
            class_type="THEORY",
            working_time_start=dt.time(17, 0),
            working_time_end=dt.time(9, 0),
            monday="PHYSICAL",
            tuesday="PHYSICAL",
            wednesday="PHYSICAL",
            thursday="PHYSICAL",
            friday="PHYSICAL",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
