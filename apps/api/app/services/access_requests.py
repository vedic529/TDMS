"""Role access requests and direct role management.

Every rule that protects TDMS access is enforced here, inside the transaction,
rather than in a route handler or a disabled button:

* only a *higher* role may be requested;
* one pending request per user;
* nobody decides their own request;
* the **first** decision closes a request — a second decision cannot overwrite it;
* a Super Admin cannot change their own role;
* the last active Super Admin cannot be demoted or disabled.

Approving a request changes the user's level *and* closes the request in one
transaction, so the system can never end up with a role granted against a request
that still looks pending, or the reverse.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import rbac
from app.models.access_request import AccessRequest
from app.models.user import User
from app.services.activity import record_activity


class AccessRequestError(Exception):
    """A refusal the caller should see. `status_code` is the HTTP status."""

    status_code = 400

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class InvalidRequestedRole(AccessRequestError):
    status_code = 422


class RequestAlreadyPending(AccessRequestError):
    status_code = 409

    def __init__(self, requested_role: str) -> None:
        super().__init__(
            f"You already have a pending request for "
            f"{rbac.ROLE_LABELS.get(requested_role, requested_role)}. "
            "Wait for a decision, or cancel it before requesting a different role."
        )


class RequestAlreadyDecided(AccessRequestError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("This access request has already been decided.")


class CannotDecideOwnRequest(AccessRequestError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__("You cannot decide your own access request.")


class CannotChangeOwnRole(AccessRequestError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__(
            "You cannot change your own access level. Ask another Super Admin to make this change."
        )


class LastSuperAdminError(AccessRequestError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            "This change would leave TDMS with no active Super Admin. "
            "Grant Super Admin to another account first."
        )


# ---------------------------------------------------------------------------
# Requesting
# ---------------------------------------------------------------------------


def pending_request_for(session: Session, user_id: int) -> AccessRequest | None:
    return session.execute(
        select(AccessRequest).where(
            AccessRequest.requester_user_id == user_id,
            AccessRequest.status == "PENDING",
        )
    ).scalar_one_or_none()


def submit_request(session: Session, user: User, requested_role: str) -> AccessRequest:
    """Create a pending request. The caller commits."""
    allowed = rbac.requestable_roles_for(user.access_level)
    if requested_role not in allowed:
        raise InvalidRequestedRole(
            f"{rbac.ROLE_LABELS.get(requested_role, requested_role)} is not a role you can "
            f"request from {rbac.ROLE_LABELS[user.access_level]}. "
            f"You may request: {', '.join(rbac.ROLE_LABELS[r] for r in allowed) or 'nothing'}."
        )

    existing = pending_request_for(session, user.id)
    if existing is not None:
        raise RequestAlreadyPending(existing.requested_role)

    request = AccessRequest(
        requester_user_id=user.id,
        role_at_request=user.access_level,
        requested_role=requested_role,
        status="PENDING",
        requested_at=_now(),
    )
    session.add(request)
    try:
        session.flush()
    except IntegrityError as exc:
        # Two submissions raced. The partial unique index settled it; report the
        # same refusal the loser would have got from the check above.
        session.rollback()
        raise RequestAlreadyPending(requested_role) from exc

    record_activity(
        session,
        user=user,
        action="ACCESS_REQUEST_SUBMITTED",
        page_or_function="Account access",
        record_reference=f"REQ-{request.id:06d}",
        detail=(
            f"Requested {rbac.ROLE_LABELS[requested_role]} access "
            f"from {rbac.ROLE_LABELS[user.access_level]}."
        ),
    )
    return request


def cancel_request(session: Session, user: User, request_id: int) -> AccessRequest:
    """Withdraw one's own pending request. The row is kept, never deleted."""
    request = session.get(AccessRequest, request_id)
    if request is None or request.requester_user_id != user.id:
        raise AccessRequestError("Access request not found.")
    if request.status != "PENDING":
        raise RequestAlreadyDecided()

    request.status = "CANCELLED"
    request.decided_at = _now()
    request.decided_by_user_id = user.id
    session.flush()

    record_activity(
        session,
        user=user,
        action="ACCESS_REQUEST_CANCELLED",
        page_or_function="Account access",
        record_reference=f"REQ-{request.id:06d}",
        detail=f"Cancelled their own request for {rbac.ROLE_LABELS[request.requested_role]}.",
    )
    return request


# ---------------------------------------------------------------------------
# Deciding
# ---------------------------------------------------------------------------


def _close_if_pending(session: Session, request_id: int, new_status: str, approver: User) -> bool:
    """Atomically move a request out of PENDING. False if somebody got there first.

    A conditional UPDATE ... WHERE status = 'PENDING' is what makes "the first
    decision wins" true. Reading the row, deciding in Python and then writing
    would leave a window in which two Super Admins both see PENDING and both
    write — and the second would silently overwrite the first.
    """
    result = session.execute(
        update(AccessRequest)
        .where(AccessRequest.id == request_id, AccessRequest.status == "PENDING")
        .values(status=new_status, decided_at=_now(), decided_by_user_id=approver.id)
    )
    return bool(result.rowcount)


def _load_pending(session: Session, request_id: int, approver: User) -> AccessRequest:
    request = session.get(AccessRequest, request_id)
    if request is None:
        raise AccessRequestError("Access request not found.")
    if request.status != "PENDING":
        raise RequestAlreadyDecided()
    # Checked here as well as by the database CHECK constraint: a clear message
    # is better than an integrity error, and the constraint is the backstop.
    if request.requester_user_id == approver.id:
        raise CannotDecideOwnRequest()
    return request


def approve_request(session: Session, approver: User, request_id: int) -> AccessRequest:
    """Approve a request and apply the new access level, in one transaction."""
    request = _load_pending(session, request_id, approver)

    requester = session.get(User, request.requester_user_id)
    if requester is None:  # pragma: no cover - FK guarantees this
        raise AccessRequestError("The requesting account no longer exists.")

    if not _close_if_pending(session, request_id, "APPROVED", approver):
        raise RequestAlreadyDecided()

    previous_level = requester.access_level
    requester.access_level = request.requested_role
    session.flush()
    session.refresh(request)

    record_activity(
        session,
        user=approver,
        action="ACCESS_REQUEST_APPROVED",
        page_or_function="Administration - Access Requests",
        record_reference=f"REQ-{request.id:06d}",
        detail=(
            f"Approved {requester.organisation_email}: "
            f"{rbac.ROLE_LABELS[previous_level]} -> {rbac.ROLE_LABELS[request.requested_role]}."
        ),
    )
    return request


def deny_request(session: Session, approver: User, request_id: int) -> AccessRequest:
    """Deny a request. The requester's access level is unchanged."""
    request = _load_pending(session, request_id, approver)

    requester = session.get(User, request.requester_user_id)
    if not _close_if_pending(session, request_id, "DENIED", approver):
        raise RequestAlreadyDecided()

    session.flush()
    session.refresh(request)

    record_activity(
        session,
        user=approver,
        action="ACCESS_REQUEST_DENIED",
        page_or_function="Administration - Access Requests",
        record_reference=f"REQ-{request.id:06d}",
        detail=(
            f"Denied {requester.organisation_email if requester else 'unknown'}: "
            f"request for {rbac.ROLE_LABELS[request.requested_role]}. "
            "Their access level is unchanged."
        ),
    )
    return request


# ---------------------------------------------------------------------------
# Direct role management
# ---------------------------------------------------------------------------


def change_role(session: Session, actor: User, target_user_id: int, new_role: str) -> User:
    """Set a user's access level directly. Super Admin only."""
    if new_role not in rbac.ROLE_LABELS:
        raise InvalidRequestedRole(f"{new_role!r} is not a TDMS access level.")

    target = session.get(User, target_user_id)
    if target is None:
        raise AccessRequestError("User not found.")

    # Two administrative lockout protections.
    if target.id == actor.id:
        raise CannotChangeOwnRole()

    if target.access_level == new_role:
        raise AccessRequestError(
            f"{target.organisation_email} already has {rbac.ROLE_LABELS[new_role]} access."
        )

    if target.access_level == "SUPER_ADMIN" and new_role != "SUPER_ADMIN":
        _require_another_active_super_admin(session, excluding_user_id=target.id)

    previous = target.access_level
    target.access_level = new_role
    session.flush()

    record_activity(
        session,
        user=actor,
        action="ROLE_CHANGED",
        page_or_function="Administration - User & Role Management",
        record_reference=target.organisation_email,
        detail=(
            f"Changed {target.organisation_email}: "
            f"{rbac.ROLE_LABELS[previous]} -> {rbac.ROLE_LABELS[new_role]}."
        ),
    )
    return target


def change_account_status(
    session: Session, actor: User, target_user_id: int, new_status: str
) -> User:
    """Enable or disable an account. Super Admin only."""
    if new_status not in {"ACTIVE", "INACTIVE", "DISABLED"}:
        raise AccessRequestError(f"{new_status!r} is not a TDMS account status.")

    target = session.get(User, target_user_id)
    if target is None:
        raise AccessRequestError("User not found.")
    if target.id == actor.id:
        raise CannotChangeOwnRole()
    if target.account_status == new_status:
        raise AccessRequestError(f"{target.organisation_email} is already {new_status}.")

    # Disabling a Super Admin removes an *active* Super Admin just as surely as
    # demoting one, so it goes through the same safeguard.
    if target.access_level == "SUPER_ADMIN" and new_status != "ACTIVE":
        _require_another_active_super_admin(session, excluding_user_id=target.id)

    previous = target.account_status
    target.account_status = new_status
    session.flush()

    record_activity(
        session,
        user=actor,
        action="ACCOUNT_STATUS_CHANGED",
        page_or_function="Administration - User & Role Management",
        record_reference=target.organisation_email,
        detail=f"Changed {target.organisation_email}: {previous} -> {new_status}.",
    )
    return target


def _require_another_active_super_admin(session: Session, *, excluding_user_id: int) -> None:
    """Refuse a change that would leave zero active Super Admins.

    Counted inside the caller's transaction, and never assuming there happen to
    be four: the protection has to hold when there is exactly one left.
    """
    from app.auth.identity import count_active_super_admins

    if count_active_super_admins(session, excluding_user_id=excluding_user_id) == 0:
        raise LastSuperAdminError()


# ---------------------------------------------------------------------------
# Direct provisioning (approved 13 August 2026)
# ---------------------------------------------------------------------------


class UserAlreadyExists(AccessRequestError):
    """The email already has an account. Add User never overwrites one."""

    status_code = 409


def provision_user(
    session: Session, actor: User, organisation_email: str, access_level: str
) -> User:
    """Create a TDMS account directly, with its access level already set.

    This is not an access request. Nobody asked; a Super Admin decided. The two
    workflows stay separate — no row is written to `access_requests`, because
    that table records *"someone asked and was answered"*, and inventing an
    entry for a decision nobody requested would corrupt the one place that
    answers "who asked for what?".

    The account is created **unlinked**: no `entra_object_id`, no
    `entra_tenant_id`, no display name. Those arrive at first sign-in from
    verified Microsoft claims. Until then the account exists and carries the
    level the Super Admin chose, which is what makes the pre-provisioned role
    survive that first login rather than being reset to the JIT Viewer default.

    The caller owns the transaction, so the account and its audit record commit
    together or not at all — an unaudited privileged grant is worse than no
    grant.
    """
    email = (organisation_email or "").strip()
    if not email:
        raise AccessRequestError("Enter the person's organisation email address.")
    if access_level not in rbac.ROLE_LABELS:
        raise InvalidRequestedRole(f"{access_level!r} is not a TDMS access level.")

    # `organisation_email` is citext, so this comparison is case-insensitive and
    # 'User@x.com' cannot become a second account beside 'user@x.com'.
    existing = session.execute(
        select(User).where(User.organisation_email == email)
    ).scalar_one_or_none()

    if existing is not None:
        if existing.id == actor.id:
            raise CannotChangeOwnRole()
        if existing.account_status != "ACTIVE":
            raise UserAlreadyExists(
                f"{existing.organisation_email} already has a {existing.account_status.lower()} "
                "TDMS account. Reactivate it from the account status action rather than adding "
                "the user again."
            )
        if existing.access_level == access_level:
            raise UserAlreadyExists(
                f"{existing.organisation_email} already exists with "
                f"{rbac.ROLE_LABELS[access_level]} access."
            )
        raise UserAlreadyExists(
            f"{existing.organisation_email} already exists with "
            f"{rbac.ROLE_LABELS[existing.access_level]} access. Use Change role to update "
            "their access level."
        )

    user = User(
        organisation_email=email,
        # Not derived from the mailbox. Microsoft supplies it at first sign-in;
        # until then the interface shows "Awaiting Microsoft profile", which is a
        # display state, not stored data.
        display_name=None,
        access_level=access_level,
        account_status="ACTIVE",
        entra_object_id=None,
        entra_tenant_id=None,
    )
    session.add(user)
    session.flush()

    record_activity(
        session,
        user=actor,
        action="USER_PROVISIONED",
        page_or_function="Administration - User & Role Management",
        record_reference=user.organisation_email,
        detail=(
            f"Direct access granted: {user.organisation_email} provisioned with "
            f"{rbac.ROLE_LABELS[access_level]} access. Microsoft identity will be "
            "linked at first sign-in."
        ),
    )
    return user


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)
