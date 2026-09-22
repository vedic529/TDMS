"""Clear the student records.

A deliberate, irreversible reset of Student Data, so a bad load can be undone and
the tab re-imported from scratch. Super Admin only (approved 21 September 2026).

**What it removes.**

* Every student record, **including the ones in the recycle area**. The approved
  wording is "no deleted record left", so a soft-deleted student is removed too.
* Their intake rows (`student_groups`). One row is one intake of one offering; it
  exists only to hold the students of that intake, so an intake with no students
  is a shell. The **rolling timetable is not touched** - it says what each intake
  studies and belongs to a different work area.
* The student import's uploaded copies: its batches and staged rows. They hold
  names, emails and phone numbers and are reachable from nowhere in the site once
  an import finishes, so leaving them would mean the data was not really cleared.
  **Trainer imports share these tables** and are identified by `data_type`; only
  the student batches (`data_type IS NULL`) are removed.

**Suggestions are settled by recount, not by source.** An entry is keyed by its
value, so a campus spelling a student import raised may also be carried by
timetable rows. Deleting "everything the student import raised" would discard an
entry that still has classes behind it. `prune_empty()` instead removes exactly
the entries whose last stored row has gone - the same rule that turns "4 affected
records" into 3 when one is corrected.

Soft deletion (DATA-04) is deliberately bypassed: this is the bulk reset, and the
per-student Delete button remains the recoverable route.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.import_batch import ImportBatch, ImportStagedRow
from app.models.student import Student, StudentGroup
from app.models.user import User
from app.services.activity import record_activity
from app.services.reference_suggestion_service import prune_empty

PAGE = "Page 2 - Student Data"

#: The student import has no `data_type`; the trainer import sets LOCATION or
#: UNITS in the same tables. Only student batches belong to this operation.
_STUDENT_BATCH = ImportBatch.data_type.is_(None)


def _staged_row_count(session: Session) -> int:
    return session.execute(
        select(func.count())
        .select_from(ImportStagedRow)
        .where(ImportStagedRow.import_batch_id.in_(select(ImportBatch.id).where(_STUDENT_BATCH)))
    ).scalar_one()


def clear_preview(session: Session) -> dict:
    """What a clear would remove, counted before anything is deleted.

    Shown in the confirmation so the decision is made against real numbers rather
    than a vague warning.
    """
    students = session.execute(
        select(Student.is_deleted, func.count()).group_by(Student.is_deleted)
    ).all()
    by_deleted = {is_deleted: total for is_deleted, total in students}
    return {
        "students": by_deleted.get(False, 0),
        "deleted_students": by_deleted.get(True, 0),
        "intakes": session.execute(select(func.count()).select_from(StudentGroup)).scalar_one(),
        "import_batches": session.execute(
            select(func.count()).select_from(ImportBatch).where(_STUDENT_BATCH)
        ).scalar_one(),
        "staged_rows": _staged_row_count(session),
        # Filled in by the clear itself: which entries are left with nothing
        # behind them is only known once the rows have gone.
        "suggestions": 0,
    }


def clear_student_records(session: Session, user: User) -> dict:
    """Delete every student record and everything that exists only for them.

    One transaction. The caller commits.

    Order follows the foreign keys: students reference their intake row, so the
    students go first; deleting a batch cascades its staged rows.
    """
    removed = clear_preview(session)

    session.execute(delete(Student))
    session.execute(delete(StudentGroup))
    # Cascades import_staged_rows.
    session.execute(delete(ImportBatch).where(_STUDENT_BATCH))
    session.flush()

    # Whatever no longer has a stored row behind it, from any source.
    removed["suggestions"] = len(prune_empty(session))
    session.flush()

    record_activity(
        session,
        user=user,
        action="DELETE",
        page_or_function=PAGE,
        detail=(
            "Cleared the student records: "
            f"{removed['students']} students, {removed['deleted_students']} in the recycle area, "
            f"{removed['intakes']} intakes, {removed['import_batches']} import batches, "
            f"{removed['staged_rows']} staged rows, and {removed['suggestions']} suggestion(s) "
            "left with nothing behind them. The rolling timetable, trainer data and allocation "
            "records were not affected."
        ),
        record_reference="student-records:clear",
        result="COMPLETED",
    )
    return removed
