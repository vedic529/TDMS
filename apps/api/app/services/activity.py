"""Write user activity records (SRS §4.5, LOG-01…LOG-06).

Append-only, and never carrying a secret: LOG-06 forbids passwords and
unnecessary personal information, and no access token, refresh token or client
secret goes anywhere near this table.

The access level is snapshotted at write time so history keeps telling the truth
after somebody's role changes.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models.activity import UserActivityRecord
from app.models.user import User


def record_activity(
    session: Session,
    *,
    user: User | None,
    action: str,
    page_or_function: str,
    detail: str,
    record_reference: str | None = None,
    result: str | None = "COMPLETED",
    microsoft_sign_in_result: str | None = None,
    tdms_access_decision: str | None = None,
    technical_reference: str | None = None,
    user_reference: str | None = None,
) -> UserActivityRecord:
    """Append one activity record. The caller commits."""
    record = UserActivityRecord(
        occurred_at=dt.datetime.now(dt.timezone.utc),
        user_id=user.id if user else None,
        # SRS §4.3: a failed sign-in with no verified identity is recorded
        # without being attached to any account.
        user_reference_snapshot=(
            user_reference or (user.organisation_email if user else "Unmatched user")
        ),
        access_level_snapshot=user.access_level if user else None,
        page_or_function=page_or_function,
        action=action,
        record_reference=record_reference,
        result=result,
        microsoft_sign_in_result=microsoft_sign_in_result,
        tdms_access_decision=tdms_access_decision,
        technical_reference=technical_reference,
        plain_language_detail=detail,
    )
    session.add(record)
    session.flush()
    return record


def record_sign_in(session: Session, user: User, *, technical_reference: str | None = None) -> None:
    """Record a successful TDMS access (SRS §4.2: two separate outcomes)."""
    record_activity(
        session,
        user=user,
        action="SIGN_IN",
        page_or_function="Sign in",
        detail=f"Signed in to TDMS as {user.access_level}.",
        result=None,
        microsoft_sign_in_result="SUCCESS",
        tdms_access_decision="GRANTED",
        technical_reference=technical_reference,
    )


def record_access_denied(
    session: Session,
    *,
    user: User | None,
    reason: str,
    user_reference: str | None = None,
    technical_reference: str | None = None,
) -> None:
    """Record a denial. Microsoft may have succeeded; TDMS still said no."""
    record_activity(
        session,
        user=user,
        action="ACCESS_DENIED",
        page_or_function="Sign in",
        detail=f"TDMS access denied: {reason}.",
        result=None,
        microsoft_sign_in_result="SUCCESS",
        tdms_access_decision="DENIED",
        user_reference=user_reference,
        technical_reference=technical_reference,
    )
