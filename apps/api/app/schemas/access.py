"""Request/response shapes for identity, access requests and role management."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserSummary(BaseModel):
    """A TDMS account as the interface sees it.

    No Entra object ID and no tenant ID: they are internal identity plumbing, and
    an administration screen has no use for them.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    #: `None` until a verified Microsoft sign-in supplies it. The interface
    #: renders that as "Awaiting Microsoft profile"; the API reports the absence
    #: rather than inventing a name from the mailbox.
    display_name: str | None = None
    organisation_email: str
    access_level: str
    account_status: str
    last_sign_in_at: dt.datetime | None = None
    #: Whether a Microsoft identity has been bound yet.
    identity_linked: bool = False


class ProvisionUserRequest(BaseModel):
    """A Super Admin granting access directly.

    Two fields only. A person's name is not asked for and must not be guessed
    from the mailbox — Microsoft supplies it at first sign-in.
    """

    organisation_email: str = Field(..., min_length=3, max_length=320)
    access_level: str

    @field_validator("organisation_email")
    @classmethod
    def _email(cls, value: str) -> str:
        cleaned = value.strip()
        if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
            raise ValueError("Enter a valid organisation email address.")
        if " " in cleaned:
            raise ValueError("An email address cannot contain spaces.")
        return cleaned


class AccessRequestSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requester_user_id: int
    requester_display_name: str | None = None
    requester_email: str | None = None
    role_at_request: str
    requested_role: str
    status: str
    requested_at: dt.datetime
    decided_at: dt.datetime | None = None
    decided_by_user_id: int | None = None
    decided_by_email: str | None = None


class MeResponse(BaseModel):
    """Everything the frontend needs to render correctly for this user."""

    user: UserSummary
    #: The authoritative capability map. The frontend mirrors the policy for UX,
    #: but this is what the API actually enforces.
    capabilities: dict[str, bool]
    requestable_roles: list[str]
    pending_request: AccessRequestSummary | None = None
    session_inactivity_minutes: int
    auth_mode: str


class SubmitAccessRequest(BaseModel):
    # No reason field: Access Model v1.1 §11 states a request needs no
    # justification, and inventing one would be inventing a business rule.
    requested_role: str = Field(..., description="A strictly higher access level.")


class DecisionRequest(BaseModel):
    #: Optional note for the approver's own reference. Never required.
    decision_note: str | None = Field(default=None, max_length=1000)


class RoleChangeRequest(BaseModel):
    access_level: str


class AccountStatusChangeRequest(BaseModel):
    account_status: str


class DashboardOverview(BaseModel):
    pending_access_requests: int
    active_users: int
    viewer_count: int
    data_editor_count: int
    admin_count: int
    super_admin_count: int
    inactive_or_disabled_users: int


class NotificationOutcome(BaseModel):
    """What actually happened to the notification, stated plainly."""

    delivered: bool
    provider: str
    detail: str


class SubmitAccessRequestResponse(BaseModel):
    request: AccessRequestSummary
    notification: NotificationOutcome
