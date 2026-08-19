"""The signed-in user's own identity and access requests."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_authenticated_user
from app.core import rbac
from app.core.config import Settings, get_settings
from app.models.user import User
from app.schemas.access import (
    AccessRequestSummary,
    MeResponse,
    NotificationOutcome,
    SubmitAccessRequest,
    SubmitAccessRequestResponse,
    UserSummary,
)
from app.services import access_requests as service
from app.services.notifications import AccessRequestNotification, get_notification_service

router = APIRouter(prefix="/me", tags=["me"])


def _user_summary(user: User) -> UserSummary:
    return UserSummary(
        id=user.id,
        display_name=user.display_name,
        organisation_email=user.organisation_email,
        access_level=user.access_level,
        account_status=user.account_status,
        last_sign_in_at=user.last_sign_in_at,
        identity_linked=user.entra_object_id is not None,
    )


def _request_summary(request, requester: User | None = None, decided_by: User | None = None):
    return AccessRequestSummary(
        id=request.id,
        requester_user_id=request.requester_user_id,
        requester_display_name=requester.display_name if requester else None,
        requester_email=requester.organisation_email if requester else None,
        role_at_request=request.role_at_request,
        requested_role=request.requested_role,
        status=request.status,
        requested_at=request.requested_at,
        decided_at=request.decided_at,
        decided_by_user_id=request.decided_by_user_id,
        decided_by_email=decided_by.organisation_email if decided_by else None,
    )


@router.get("", response_model=MeResponse)
def read_me(
    user: User = Depends(require_authenticated_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MeResponse:
    pending = service.pending_request_for(session, user.id)
    return MeResponse(
        user=_user_summary(user),
        capabilities=rbac.capabilities_for(user.access_level),
        requestable_roles=list(rbac.requestable_roles_for(user.access_level)),
        pending_request=_request_summary(pending, user) if pending else None,
        session_inactivity_minutes=settings.session_inactivity_minutes,
        auth_mode=settings.auth_mode,
    )


@router.get("/access-request", response_model=AccessRequestSummary | None)
def read_my_pending_request(
    user: User = Depends(require_authenticated_user),
    session: Session = Depends(get_db),
) -> AccessRequestSummary | None:
    pending = service.pending_request_for(session, user.id)
    return _request_summary(pending, user) if pending else None


@router.post("/access-requests", response_model=SubmitAccessRequestResponse, status_code=201)
def submit_access_request(
    payload: SubmitAccessRequest,
    user: User = Depends(require_authenticated_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SubmitAccessRequestResponse:
    try:
        request = service.submit_request(session, user, payload.requested_role)
        session.commit()
    except service.AccessRequestError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        session.rollback()
        raise

    session.refresh(request)

    # Notifying happens after the commit: a mail failure must not lose a request
    # that was validly submitted.
    outcome = get_notification_service().notify_access_request(
        AccessRequestNotification(
            requester_display_name=user.display_name,
            requester_email=user.organisation_email,
            current_role=request.role_at_request,
            requested_role=request.requested_role,
            requested_at=request.requested_at.isoformat(),
            administration_url=f"{settings.app_base_url.rstrip('/')}/administration",
        )
    )

    return SubmitAccessRequestResponse(
        request=_request_summary(request, user),
        notification=NotificationOutcome(
            delivered=outcome.delivered, provider=outcome.provider, detail=outcome.detail
        ),
    )


@router.delete("/access-requests/{request_id}", response_model=AccessRequestSummary)
def cancel_access_request(
    request_id: int,
    user: User = Depends(require_authenticated_user),
    session: Session = Depends(get_db),
) -> AccessRequestSummary:
    try:
        request = service.cancel_request(session, user, request_id)
        session.commit()
    except service.AccessRequestError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        session.rollback()
        raise

    session.refresh(request)
    return _request_summary(request, user, user)
