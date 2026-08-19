"""User activity records (SRS §4.5, LOG-01…LOG-06; Schema v1 §16).

Append-only. LOG-05 is enforced by **privilege** — the application role receives
`INSERT, SELECT` and no `UPDATE` or `DELETE` — not by convention. There is
deliberately no `updated_at` and no soft-delete group on this table.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import enums
from app.db.base import Base, pk_column


class UserActivityRecord(Base):
    """One recorded action.

    **Historical context is preserved by FK + snapshot.** A foreign key alone
    would let history rewrite itself when a user's access level changes; a
    snapshot alone would make "everything this user did" a string match. Both
    together fix the level at write time while keeping per-user queries
    reliable.
    """

    __tablename__ = "user_activity_records"
    __table_args__ = (
        # LOG-02: an operational row carries `result`; a sign-in/access row
        # carries the Microsoft result and the TDMS decision instead. At least
        # one must be present.
        CheckConstraint(
            "result IS NOT NULL OR microsoft_sign_in_result IS NOT NULL "
            "OR tdms_access_decision IS NOT NULL",
            name="outcome_present",
        ),
        Index("ix_user_activity_records_occurred_at", "occurred_at"),
        Index("ix_user_activity_records_user_id_occurred_at", "user_id", "occurred_at"),
    )

    # Displayed as `ACT-000123`. A second sequence would add a failure mode for
    # no benefit.
    id: Mapped[int] = pk_column()

    # Stored UTC; the display time zone is decided by OD-14. The storage type is
    # correct regardless of what OD-14 chooses.
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Nullable: SRS §4.3 requires a failed sign-in with no verified identity to
    # be recorded as "Unmatched user" WITHOUT attaching it to any account.
    # RESTRICT: an audit trail must not be destroyed by removing a user.
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    user_reference_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    # The access level AT THE TIME OF THE ACTION.
    access_level_snapshot: Mapped[str | None] = mapped_column(enums.access_level, nullable=True)

    page_or_function: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(enums.activity_action, nullable=False)
    record_reference: Mapped[str | None] = mapped_column(Text, nullable=True)

    reason_code_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reason_codes.id", ondelete="RESTRICT"), nullable=True
    )
    reason_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    result: Mapped[str | None] = mapped_column(enums.activity_result, nullable=True)
    # SRS §4.2: the Microsoft sign-in result and the TDMS access decision are
    # two separate values. A blocked account is a denial REASON, not a third
    # universal sign-in status.
    microsoft_sign_in_result: Mapped[str | None] = mapped_column(
        enums.ms_sign_in_result, nullable=True
    )
    tdms_access_decision: Mapped[str | None] = mapped_column(enums.access_decision, nullable=True)

    # AUTH-11: correlation ID or safe error reference.
    technical_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    # LOG-06: no password or unnecessary personal information.
    plain_language_detail: Mapped[str] = mapped_column(Text, nullable=False)
