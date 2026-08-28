"""Clear the allocation records.

A deliberate, irreversible reset of the Allocation Records side of Timetable
View and Management, so a bad import can be undone and the tab re-imported from
scratch. Super Admin only.

**What it deliberately does not touch.** Approved scope, 26 August 2026:

* **The rolling timetable.** It is the authoritative statement of what each
  intake studies, and 762 students carry `rolling_intake_label` values that
  point into it. Clearing it would leave every one of them with an intake whose
  weeks no longer exist.
* **Students and student groups.** Student Data is a separate work area; a
  button on the timetable tab must not reach into it.
* **Suggestions raised by the rolling or student imports.** Only the entries the
  allocation import itself raised are cleared, because only the rows that raised
  them are being removed. Clearing a student-import suggestion here would
  discard a decision nobody asked to discard.

Soft deletion does not apply. These rows are not business records with a
recovery period (DATA-04); they are the product of a re-runnable import, and the
approved remedy is to import the file again.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.allocation import (
    AllocationDelivery,
    AllocationDeliveryIntake,
    AllocationImportBatch,
    AllocationSession,
    AllocationSourceRow,
    ReferenceSuggestion,
)
from app.models.user import User
from app.services.activity import record_activity

#: Only the entries the allocation import raised. A rolling-import or
#: student-import entry belongs to rows this operation does not delete.
_ALLOCATION_SOURCE = "ALLOCATION_IMPORT"


def clear_preview(session: Session) -> dict:
    """What a clear would remove, counted before anything is deleted.

    Shown in the confirmation so the decision is made against real numbers
    rather than a vague warning.
    """

    def count(model) -> int:
        return session.execute(select(func.count()).select_from(model)).scalar_one()

    suggestions = session.execute(
        select(ReferenceSuggestion.status, func.count())
        .where(ReferenceSuggestion.source == _ALLOCATION_SOURCE)
        .group_by(ReferenceSuggestion.status)
    ).all()
    by_status = {status: total for status, total in suggestions}

    return {
        "deliveries": count(AllocationDelivery),
        "sessions": count(AllocationSession),
        "intake_links": count(AllocationDeliveryIntake),
        "import_batches": count(AllocationImportBatch),
        "source_rows": count(AllocationSourceRow),
        "suggestions": by_status.get("PENDING", 0),
        "exceptions": by_status.get("EXCEPTION", 0),
        "resolved_suggestions": sum(
            total for status, total in by_status.items() if status not in {"PENDING", "EXCEPTION"}
        ),
    }


def clear_allocation_records(session: Session, user: User) -> dict:
    """Delete every allocation record and the suggestions its import raised.

    One transaction. The caller commits.

    Order matters, and follows the foreign keys rather than fighting them:
    deleting the batches cascades their source rows, and deleting the deliveries
    cascades their sessions and intake links.
    """
    removed = clear_preview(session)

    # Cascades allocation_source_row.
    session.execute(delete(AllocationImportBatch))
    # Cascades allocation_session and allocation_delivery_intake.
    session.execute(delete(AllocationDelivery))
    # Any source row orphaned by an earlier batch deletion.
    session.execute(delete(AllocationSourceRow))
    # Every entry the allocation import raised, whatever its state: the rows
    # that raised them no longer exist, so a pending decision has nothing left
    # to decide and a recorded exception nothing left to except.
    session.execute(
        delete(ReferenceSuggestion).where(ReferenceSuggestion.source == _ALLOCATION_SOURCE)
    )
    session.flush()

    record_activity(
        session,
        user=user,
        action="DELETE",
        page_or_function="Page 1 - Timetable View and Management",
        detail=(
            "Cleared the allocation records: "
            f"{removed['deliveries']} deliveries, {removed['sessions']} sessions, "
            f"{removed['intake_links']} intake links, {removed['import_batches']} import batches, "
            f"{removed['source_rows']} source rows, and "
            f"{removed['suggestions'] + removed['exceptions'] + removed['resolved_suggestions']} "
            "allocation suggestions and exceptions. The rolling timetable and student records "
            "were not affected."
        ),
        record_reference="allocation-records:clear",
        result="COMPLETED",
    )
    return removed
