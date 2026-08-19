"""Resolve a verified Microsoft identity to a TDMS user account.

The rule that matters: **`tid + oid` is the identity; the mailbox is not.**

A person is found by the immutable pair. If they are found, their access level is
whatever their `users` row says — the elevated bootstrap list is never consulted
again. That is what stops a mailbox rename from promoting anybody, and what stops
a demotion from being silently reversed at the next sign-in.

The bootstrap list is consulted exactly once, when an approved address signs in
for the very first time and has no account yet.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.claims import VerifiedClaims
from app.db.seeds.manifest import DEFAULT_ACCESS_LEVEL, INITIAL_ACCOUNT_STATUS, bootstrap_role_for
from app.models.user import User


class AccessDeniedError(Exception):
    """Authentication succeeded but TDMS refuses access. Renders as HTTP 403.

    SRS §4.2 keeps these separate on purpose: "Microsoft says you are you" and
    "TDMS lets you in" are two different answers, and a disabled account is a
    denial reason rather than a failed sign-in.
    """

    def __init__(self, detail: str, *, reason: str) -> None:
        self.detail = detail
        self.reason = reason
        super().__init__(detail)


class InactiveAccountError(AccessDeniedError):
    def __init__(self, status: str) -> None:
        super().__init__(
            "Your TDMS account is not active. Contact a TDMS administrator.",
            reason=f"ACCOUNT_{status}",
        )


def find_user_by_identity(session: Session, claims: VerifiedClaims) -> User | None:
    """Find the account bound to this Microsoft identity.

    Both halves are compared. `oid` is unique across Microsoft, but requiring the
    tenant too means a token from a tenant that was later removed from the
    allow-list cannot resolve to an account.
    """
    return session.execute(
        select(User).where(
            User.entra_object_id == claims.object_id,
            User.entra_tenant_id == claims.tenant_id,
        )
    ).scalar_one_or_none()


def _find_unbound_by_email(session: Session, email: str) -> User | None:
    """An account pre-provisioned for this address that no identity has claimed.

    `organisation_email` is `citext`, so the match is case-insensitive.
    `entra_object_id IS NULL` is essential: an account already bound to somebody
    belongs to them, and a mailbox that was later reassigned to a different
    person must never hand over the previous holder's access.
    """
    return session.execute(
        select(User).where(
            User.organisation_email == email,
            User.entra_object_id.is_(None),
        )
    ).scalar_one_or_none()


def resolve_user(session: Session, claims: VerifiedClaims) -> User:
    """Return the TDMS account for a verified Microsoft identity, creating it if needed.

    The caller owns the transaction.
    """
    user = find_user_by_identity(session, claims)

    if user is not None:
        _refresh_profile(user, claims)
        _require_active(user)
        return user

    email = claims.normalised_username

    # An account pre-provisioned for this address: bind this identity to it and
    # keep the access level it was given.
    existing = _find_unbound_by_email(session, email)
    if existing is not None:
        existing.entra_object_id = claims.object_id
        existing.entra_tenant_id = claims.tenant_id
        _refresh_profile(existing, claims)
        session.flush()
        _require_active(existing)
        return existing

    # First sign-in. An approved elevated address binds at its approved role;
    # everyone else from an approved tenant becomes a Viewer. Nothing here reads
    # the domain: tenant admission already happened during token validation.
    access_level = bootstrap_role_for(email) or DEFAULT_ACCESS_LEVEL

    user = User(
        entra_object_id=claims.object_id,
        entra_tenant_id=claims.tenant_id,
        organisation_email=email,
        display_name=claims.display_name,
        access_level=access_level,
        account_status=INITIAL_ACCOUNT_STATUS,
        last_sign_in_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        # Two first sign-ins raced. The unique constraint on entra_object_id (or
        # organisation_email) settled it; re-read the winner rather than failing
        # the person who lost by microseconds.
        session.rollback()
        winner = find_user_by_identity(session, claims)
        if winner is None:
            raise
        _refresh_profile(winner, claims)
        _require_active(winner)
        return winner

    _require_active(user)
    return user


def _refresh_profile(user: User, claims: VerifiedClaims) -> None:
    """Keep display-oriented fields current.

    Safe precisely because the identity already matched: the same person's name
    or mailbox changing is a profile update, never a reason to create a second
    account. The access level is deliberately not touched.
    """
    if claims.display_name and user.display_name != claims.display_name:
        user.display_name = claims.display_name

    email = claims.normalised_username
    if email and user.organisation_email.lower() != email:
        user.organisation_email = email

    user.last_sign_in_at = dt.datetime.now(dt.timezone.utc)


def _require_active(user: User) -> None:
    if user.account_status != "ACTIVE":
        raise InactiveAccountError(user.account_status)


def count_active_super_admins(session: Session, *, excluding_user_id: int | None = None) -> int:
    """How many active Super Admins remain.

    Used by the last-Super-Admin safeguard. Counted inside the caller's
    transaction so the answer cannot go stale between check and write.
    """
    stmt = select(func.count()).select_from(User).where(
        User.access_level == "SUPER_ADMIN", User.account_status == "ACTIVE"
    )
    if excluding_user_id is not None:
        stmt = stmt.where(User.id != excluding_user_id)
    return session.execute(stmt).scalar_one()
