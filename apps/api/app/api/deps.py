"""FastAPI dependencies: database session, authentication, authorisation.

Route handlers declare what they need — `Depends(require_super_admin)` — and get
either a user who satisfies it or an HTTP error. No handler decides for itself.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.claims import AuthenticationError, VerifiedClaims
from app.auth.identity import AccessDeniedError, find_user_by_identity, resolve_user
from app.auth.mock import mock_claims_for
from app.auth.tokens import verify_access_token
from app.core import rbac
from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.models.user import User
from app.services.activity import record_access_denied, record_sign_in

#: `auto_error=False` so a missing header produces our own 401 with a
#: `WWW-Authenticate` header rather than FastAPI's default shape.
_bearer = HTTPBearer(auto_error=False)

#: Development-only header naming the mock user. Only ever read when auth mode is
#: `mock`, which `Settings.auth_configuration_error()` forbids in production.
MOCK_USER_HEADER = "X-TDMS-Mock-User"


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _unauthenticated(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _mock_claims(request: Request) -> VerifiedClaims:
    """Build claims from a development header.

    This is a real backdoor, so it is fenced twice: `auth_configuration_error()`
    refuses mock mode in production, and the tenant used is an obviously fake
    one that no genuine Microsoft token could carry.
    """
    username = (request.headers.get(MOCK_USER_HEADER) or "").strip()
    if not username:
        raise _unauthenticated(
            f"Mock authentication is active. Supply the {MOCK_USER_HEADER} header."
        )
    try:
        return mock_claims_for(username)
    except ValueError as exc:
        raise _unauthenticated(str(exc)) from exc


def get_verified_claims(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> VerifiedClaims:
    """Authenticate the caller. Raises 401 if that is not possible."""
    error = settings.auth_configuration_error()
    if error:
        # A misconfigured deployment must not serve requests as if it were fine.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this server.",
        )

    if not settings.is_entra_mode:
        return _mock_claims(request)

    if credentials is None or not credentials.credentials:
        raise _unauthenticated("Not authenticated")

    try:
        return verify_access_token(credentials.credentials, settings)
    except AuthenticationError as exc:
        raise _unauthenticated(exc.detail) from exc


def get_current_user(
    claims: VerifiedClaims = Depends(get_verified_claims),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """The TDMS account for the authenticated caller, provisioned on first sign-in."""
    try:
        previous_sign_in = _previous_sign_in(session, claims)
        user = resolve_user(session, claims)

        # LOG-01 / SRS §4.2: record the sign-in — but only a real one. `/me` is
        # called on every page load, so recording unconditionally would bury the
        # audit trail under one row per render. A gap longer than the session
        # inactivity window means this is a new session rather than a refresh.
        if _is_new_session(previous_sign_in, settings):
            record_sign_in(session, user, technical_reference=claims.token_reference or None)

        session.commit()
    except AccessDeniedError as exc:
        session.rollback()
        _record_denial(session, claims, exc)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.detail) from exc
    except Exception:
        session.rollback()
        raise
    return user


def _previous_sign_in(session: Session, claims: VerifiedClaims) -> dt.datetime | None:
    """The stored last-sign-in time, read before `resolve_user` overwrites it."""
    existing = find_user_by_identity(session, claims)
    return existing.last_sign_in_at if existing else None


def _is_new_session(previous: dt.datetime | None, settings: Settings) -> bool:
    if previous is None:
        return True
    if previous.tzinfo is None:  # pragma: no cover - defensive
        previous = previous.replace(tzinfo=dt.timezone.utc)
    gap = dt.datetime.now(dt.timezone.utc) - previous
    return gap > dt.timedelta(minutes=settings.session_inactivity_minutes)


def _record_denial(session: Session, claims: VerifiedClaims, exc: AccessDeniedError) -> None:
    """Record a denial against the account, in its own transaction.

    Separate because the caller's transaction has already been rolled back, and
    a denial that goes unrecorded is exactly the event an audit needs.
    """
    try:
        user = find_user_by_identity(session, claims)
        record_access_denied(
            session,
            user=user,
            reason=exc.reason,
            user_reference=claims.normalised_username or None,
            technical_reference=claims.token_reference or None,
        )
        session.commit()
    except Exception:  # pragma: no cover - never let logging break the response
        session.rollback()


# ---------------------------------------------------------------------------
# Authorisation
# ---------------------------------------------------------------------------


def require_capability(capability: rbac.Capability) -> Callable[..., User]:
    """Build a dependency that admits only users holding `capability`."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if not rbac.can(user.access_level, capability):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action requires "
                    f"{rbac.ROLE_LABELS[rbac.minimum_level_for(capability)]} access or above."
                ),
            )
        return user

    return dependency


def require_level(minimum: rbac.AccessLevel) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not rbac.at_least(user.access_level, minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires {rbac.ROLE_LABELS[minimum]} access or above.",
            )
        return user

    return dependency


# Named policies, so a route reads as the rule it enforces.
require_authenticated_user = get_current_user
require_viewer_or_above = require_level(rbac.AccessLevel.VIEWER)
require_data_editor_or_above = require_level(rbac.AccessLevel.DATA_EDITOR)
require_admin_or_super_admin = require_level(rbac.AccessLevel.ADMIN)
require_super_admin = require_level(rbac.AccessLevel.SUPER_ADMIN)

require_maintain_student_data = require_capability(rbac.Capability.MAINTAIN_STUDENT_DATA)
require_maintain_timetable = require_capability(rbac.Capability.MAINTAIN_TIMETABLE)
require_maintain_trainer_data = require_capability(rbac.Capability.MAINTAIN_TRAINER_DATA)
require_maintain_reference_data = require_capability(rbac.Capability.MAINTAIN_REFERENCE_DATA)
require_view_activity_records = require_capability(rbac.Capability.VIEW_ACTIVITY_RECORDS)
require_manage_user_roles = require_capability(rbac.Capability.MANAGE_USER_ROLES)

#: Deciding an access request is Super Admin work. An Admin is refused here, and
#: the requester is refused separately inside the service — being a Super Admin
#: does not entitle anyone to decide their own request.
require_super_admin_request_approver = require_capability(rbac.Capability.DECIDE_ACCESS_REQUESTS)
