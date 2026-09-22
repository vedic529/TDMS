"""A predefined rule accepted as an exception can be stored.

Revision ID: e2b7c4d19f63
Revises: d8e4f2a61c35
Create Date: 2026-09-15

Approved 15 September 2026: a broken predefined rule offers the same three
choices everywhere - accept it as an exception for this import, exclude the row,
or edit it - and an accepted row is stored as written.

Five CHECK constraints restated import rules as hard database rules, so an
accepted row could not be written and the review fell back to offering Exclude
only. MSCRIS on a Friday was the case that showed it. They are dropped; the
import still checks every one of these rules, and nothing reaches the database
without either passing it or being accepted by a person.

* `allocation_session.mscris_saturday_virtual` becomes `mscris_virtual`. MSCRIS
  being virtual is not a rule a file can break - the importer always stores it
  virtual - so that half stays an integrity check. The Saturday half goes.
* `allocation_session.non_mscris_not_saturday` - a weekday rule.
* `allocation_session.practical_is_physical` - practical is never virtual.
* `allocation_session.session_times_ordered` - a class ending before it starts.
* `allocation_delivery.delivery_dates_ordered` - an end date before the start.
* `students.course_dates_ordered` - a proposed end date not after the start.

The downgrade restores them, and fails if an accepted row now breaks one - which
is the correct outcome: those rows would have to be corrected first.
"""

from __future__ import annotations

from alembic import op

revision = "e2b7c4d19f63"
down_revision = "d8e4f2a61c35"
branch_labels = None
depends_on = None


_DROPPED = (
    ("allocation_session", "ck_allocation_session_mscris_saturday_virtual"),
    ("allocation_session", "ck_allocation_session_non_mscris_not_saturday"),
    ("allocation_session", "ck_allocation_session_practical_is_physical"),
    ("allocation_session", "ck_allocation_session_session_times_ordered"),
    ("allocation_delivery", "ck_allocation_delivery_delivery_dates_ordered"),
    ("students", "ck_students_course_dates_ordered"),
)

_RESTORED = {
    "ck_allocation_session_mscris_saturday_virtual": "stream <> 'MSCRIS' OR (weekday = 'SATURDAY' AND delivery_mode = 'VIRTUAL')",
    "ck_allocation_session_non_mscris_not_saturday": "stream = 'MSCRIS' OR weekday <> 'SATURDAY'",
    "ck_allocation_session_practical_is_physical": "stream <> 'PRACTICAL' OR delivery_mode = 'PHYSICAL'",
    "ck_allocation_session_session_times_ordered": "end_time > start_time",
    "ck_allocation_delivery_delivery_dates_ordered": "end_date >= start_date",
    "ck_students_course_dates_ordered": "proposed_end_date > proposed_start_date",
}


def upgrade() -> None:
    for table, name in _DROPPED:
        op.drop_constraint(op.f(name), table, type_="check")
    op.create_check_constraint(
        op.f("ck_allocation_session_mscris_virtual"),
        "allocation_session",
        "stream <> 'MSCRIS' OR delivery_mode = 'VIRTUAL'",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_allocation_session_mscris_virtual"), "allocation_session", type_="check")
    for table, name in _DROPPED:
        op.create_check_constraint(op.f(name), table, _RESTORED[name])
