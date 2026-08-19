"""TDMS user accounts (Schema v1 §5, §6 — identity and access).

Amended by **Access Model v1.1**: four access levels, and the Data Editor work
assignment removed — see `docs/database/access-model-v1.1.md`.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import enums
from app.db.base import Base, TimestampMixin, pk_column


class User(Base, TimestampMixin):
    """An approved TDMS user account.

    AUTH-03: no password, password hash, token or secret column exists here or
    anywhere else in the schema. Microsoft Entra performs authentication; TDMS
    only decides authorisation.

    `access_level` carries exactly four values in ascending privilege, so
    PostgreSQL's own enum ordering answers "at least this level". Access Model
    v1.1 removed `data_editor_assignment`: a Data Editor now maintains both
    Student Data and Timetable, so the column no longer decided anything.
    """

    __tablename__ = "users"

    id: Mapped[int] = pk_column()

    # AUTH-04: the stable Microsoft identity, and the only durable authorisation
    # key. Null until the first verified sign-in binds it. Email is NOT the
    # permanent key: people are renamed and mailboxes reassigned.
    entra_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True, nullable=True)
    entra_tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # citext: case-insensitive uniqueness, so A.Person@… and a.person@… cannot
    # become two accounts.
    organisation_email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    #: NULL until a verified Microsoft sign-in supplies it.
    #:
    #: A Super Admin provisions an account with an email and an access level
    #: only. Deriving a name from the mailbox would guess at capitalisation,
    #: word order and which part is the surname, then store the guess as fact.
    #: The interface shows "Awaiting Microsoft profile" for NULL; that is a
    #: presentation state and is never written here.
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    access_level: Mapped[str] = mapped_column(enums.access_level, nullable=False)
    account_status: Mapped[str] = mapped_column(enums.account_status, nullable=False)

    # Convenience for the user-management screen. The authoritative sign-in
    # history is `user_activity_records`.
    last_sign_in_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User id={self.id} email={self.organisation_email!r} level={self.access_level}>"
