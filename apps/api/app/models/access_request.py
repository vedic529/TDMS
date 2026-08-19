"""Role access requests (Access Model v1.1).

A user asks for a higher TDMS access level; a Super Admin approves or denies it.

Four rules are enforced by the **database**, not only by application code,
because each of them is a way someone could otherwise gain access they were
never granted:

1. *Only a higher role may be requested.* The `access_level` enum is declared in
   ascending privilege, so `requested_role > role_at_request` is a plain
   comparison PostgreSQL can check.
2. *Only one pending request per user.* A partial unique index means two
   simultaneous submissions cannot both land — the second fails at the database,
   not at a check that raced.
3. *Nobody decides their own request.* A CHECK forbids
   `decided_by_user_id = requester_user_id` on an approval or denial.
4. *A decided request carries who decided it and when.*
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import enums
from app.db.base import Base, TimestampMixin, pk_column
from app.models.user import User


class AccessRequest(Base, TimestampMixin):
    """One request to be granted a higher access level."""

    __tablename__ = "access_requests"
    __table_args__ = (
        # VIEWER is the default level, so it is never something to request.
        CheckConstraint("requested_role <> 'VIEWER'", name="requested_role_not_viewer"),
        # Ascending-privilege enum ordering does the work: a request must go up.
        # Requesting your current role, or a lower one, is not a request — a
        # reduction is an administrative action performed by a Super Admin.
        CheckConstraint("requested_role > role_at_request", name="requested_role_is_higher"),
        # A pending request has no decision; a closed one always records both
        # who closed it and when.
        CheckConstraint(
            "(status = 'PENDING' AND decided_at IS NULL AND decided_by_user_id IS NULL)"
            " OR (status <> 'PENDING' AND decided_at IS NOT NULL AND decided_by_user_id IS NOT NULL)",
            name="decision_fields_match_status",
        ),
        # Self-approval is impossible even if a route forgets to check.
        # CANCELLED is excluded: cancelling is exactly the requester closing
        # their own request.
        CheckConstraint(
            "status IN ('PENDING', 'CANCELLED') OR decided_by_user_id <> requester_user_id",
            name="approver_is_not_the_requester",
        ),
        # One pending request per user. Partial, so the closed history of a user
        # who has requested before does not block a new request.
        Index(
            "uq_access_requests_requester_id_pending",
            "requester_user_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index("ix_access_requests_status_requested_at", "status", "requested_at"),
    )

    id: Mapped[int] = pk_column()

    # RESTRICT: a request is part of the access audit trail and must not vanish
    # because an account was removed.
    requester_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # The level held when the request was made. Stored rather than derived: an
    # approved request must still read truthfully after the level changes.
    role_at_request: Mapped[str] = mapped_column(enums.access_level, nullable=False)
    requested_role: Mapped[str] = mapped_column(enums.access_level, nullable=False)

    status: Mapped[str] = mapped_column(
        enums.access_request_status, nullable=False, server_default="PENDING"
    )

    requested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    # Optional, for the approver's own reference. No reason is required from the
    # requester (Access Model v1.1 §11) and none is required to deny.
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    requester: Mapped[User] = relationship(foreign_keys=[requester_user_id])
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_user_id])

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<AccessRequest id={self.id} user={self.requester_user_id} "
            f"{self.role_at_request}->{self.requested_role} {self.status}>"
        )
