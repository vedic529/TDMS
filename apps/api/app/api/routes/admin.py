"""Super Admin administration: access requests, users and roles, activity records.

Every route here requires SUPER_ADMIN. An Admin reaching these addresses directly
receives 403 — hiding the navigation item is not what protects them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.api.deps import (
    get_db,
    require_manage_user_roles,
    require_super_admin,
    require_super_admin_request_approver,
    require_view_activity_records,
)
from app.api.routes.me import _request_summary, _user_summary
from app.models.access_request import AccessRequest
from app.models.activity import UserActivityRecord
from app.models.user import User
from app.schemas.access import (
    AccessRequestSummary,
    AccountStatusChangeRequest,
    DashboardOverview,
    DecisionRequest,
    ProvisionUserRequest,
    RoleChangeRequest,
    UserSummary,
)
from app.services import access_requests as service

router = APIRouter(prefix="/admin", tags=["administration"])


def _load_requests(session: Session, statuses: list[str] | None) -> list[AccessRequestSummary]:
    requester = aliased(User)
    decider = aliased(User)
    stmt = (
        select(AccessRequest, requester, decider)
        .join(requester, AccessRequest.requester_user_id == requester.id)
        .outerjoin(decider, AccessRequest.decided_by_user_id == decider.id)
        .order_by(AccessRequest.requested_at.desc())
    )
    if statuses:
        stmt = stmt.where(AccessRequest.status.in_(statuses))
    return [
        _request_summary(request, req_user, dec_user)
        for request, req_user, dec_user in session.execute(stmt).all()
    ]


@router.get("/overview", response_model=DashboardOverview)
def read_overview(
    _: User = Depends(require_super_admin),
    session: Session = Depends(get_db),
) -> DashboardOverview:
    by_level = dict(
        session.execute(
            select(User.access_level, func.count()).group_by(User.access_level)
        ).all()
    )
    by_status = dict(
        session.execute(
            select(User.account_status, func.count()).group_by(User.account_status)
        ).all()
    )
    pending = session.execute(
        select(func.count()).select_from(AccessRequest).where(AccessRequest.status == "PENDING")
    ).scalar_one()

    return DashboardOverview(
        pending_access_requests=pending,
        active_users=by_status.get("ACTIVE", 0),
        viewer_count=by_level.get("VIEWER", 0),
        data_editor_count=by_level.get("DATA_EDITOR", 0),
        admin_count=by_level.get("ADMIN", 0),
        super_admin_count=by_level.get("SUPER_ADMIN", 0),
        inactive_or_disabled_users=by_status.get("INACTIVE", 0) + by_status.get("DISABLED", 0),
    )


@router.get("/access-requests", response_model=list[AccessRequestSummary])
def list_access_requests(
    status: list[str] | None = Query(default=None),
    _: User = Depends(require_super_admin_request_approver),
    session: Session = Depends(get_db),
) -> list[AccessRequestSummary]:
    return _load_requests(session, status)


@router.post("/access-requests/{request_id}/approve", response_model=AccessRequestSummary)
def approve_access_request(
    request_id: int,
    payload: DecisionRequest | None = None,
    approver: User = Depends(require_super_admin_request_approver),
    session: Session = Depends(get_db),
) -> AccessRequestSummary:
    try:
        request = service.approve_request(session, approver, request_id)
        if payload and payload.decision_note:
            request.decision_note = payload.decision_note
        session.commit()
    except service.AccessRequestError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        session.rollback()
        raise

    session.refresh(request)
    requester = session.get(User, request.requester_user_id)
    return _request_summary(request, requester, approver)


@router.post("/access-requests/{request_id}/deny", response_model=AccessRequestSummary)
def deny_access_request(
    request_id: int,
    payload: DecisionRequest | None = None,
    approver: User = Depends(require_super_admin_request_approver),
    session: Session = Depends(get_db),
) -> AccessRequestSummary:
    try:
        request = service.deny_request(session, approver, request_id)
        if payload and payload.decision_note:
            request.decision_note = payload.decision_note
        session.commit()
    except service.AccessRequestError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        session.rollback()
        raise

    session.refresh(request)
    requester = session.get(User, request.requester_user_id)
    return _request_summary(request, requester, approver)


@router.get("/users", response_model=list[UserSummary])
def list_users(
    search: str | None = Query(default=None),
    access_level: list[str] | None = Query(default=None),
    account_status: list[str] | None = Query(default=None),
    _: User = Depends(require_super_admin),
    session: Session = Depends(get_db),
) -> list[UserSummary]:
    stmt = select(User).order_by(User.display_name)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            User.display_name.ilike(pattern) | User.organisation_email.ilike(pattern)
        )
    if access_level:
        stmt = stmt.where(User.access_level.in_(access_level))
    if account_status:
        stmt = stmt.where(User.account_status.in_(account_status))
    return [_user_summary(user) for user in session.execute(stmt).scalars().all()]


@router.post("/users", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
def provision_user(
    payload: ProvisionUserRequest,
    actor: User = Depends(require_manage_user_roles),
    session: Session = Depends(get_db),
) -> UserSummary:
    """Grant a person TDMS access directly. Super Admin only.

    Authorisation is the dependency above, not the absence of a button: a
    hidden control is a UI convenience, and this endpoint is reachable without
    one.
    """
    try:
        user = service.provision_user(
            session, actor, payload.organisation_email, payload.access_level
        )
        # The account and its audit record commit together. An unaudited
        # privileged grant is worse than no grant, so a failure to record the
        # activity takes the account with it.
        session.commit()
    except service.AccessRequestError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        session.rollback()
        raise

    session.refresh(user)
    return _user_summary(user)


@router.post("/users/{user_id}/role", response_model=UserSummary)
def change_user_role(
    user_id: int,
    payload: RoleChangeRequest,
    actor: User = Depends(require_manage_user_roles),
    session: Session = Depends(get_db),
) -> UserSummary:
    try:
        target = service.change_role(session, actor, user_id, payload.access_level)
        session.commit()
    except service.AccessRequestError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        session.rollback()
        raise

    session.refresh(target)
    return _user_summary(target)


@router.post("/users/{user_id}/status", response_model=UserSummary)
def change_user_status(
    user_id: int,
    payload: AccountStatusChangeRequest,
    actor: User = Depends(require_manage_user_roles),
    session: Session = Depends(get_db),
) -> UserSummary:
    try:
        target = service.change_account_status(session, actor, user_id, payload.account_status)
        session.commit()
    except service.AccessRequestError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        session.rollback()
        raise

    session.refresh(target)
    return _user_summary(target)


@router.get("/activity-records")
def list_activity_records(
    limit: int = Query(default=100, le=500),
    _: User = Depends(require_view_activity_records),
    session: Session = Depends(get_db),
) -> list[dict]:
    rows = (
        session.execute(
            select(UserActivityRecord)
            .order_by(UserActivityRecord.occurred_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": f"ACT-{row.id:06d}",
            "occurredAt": row.occurred_at.isoformat(),
            "userReference": row.user_reference_snapshot,
            "accessLevel": row.access_level_snapshot,
            "pageOrFunction": row.page_or_function,
            "action": row.action,
            "recordReference": row.record_reference,
            "result": row.result,
            "microsoftSignInResult": row.microsoft_sign_in_result,
            "tdmsAccessDecision": row.tdms_access_decision,
            "detail": row.plain_language_detail,
        }
        for row in rows
    ]
