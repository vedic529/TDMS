"""The verified identity produced by authentication.

`VerifiedClaims` exists so that everything downstream is handed *already
verified* values. A raw token dict is easy to use by accident; a distinct type
that can only be built by a validator is not.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


class AuthenticationError(Exception):
    """The caller could not be authenticated. Always renders as HTTP 401.

    `detail` is deliberately vague to the caller. Which of "signature",
    "expiry" or "tenant" failed is useful to an attacker probing the endpoint
    and useless to a legitimate user, so the specifics stay in the log.
    """

    def __init__(self, detail: str = "Not authenticated", *, log_detail: str | None = None) -> None:
        self.detail = detail
        self.log_detail = log_detail or detail
        super().__init__(self.log_detail)


class TenantNotAllowedError(AuthenticationError):
    """A genuine Microsoft identity, but not from a tenant TDMS admits."""

    def __init__(self, tenant_id: str) -> None:
        super().__init__(
            "Your organisation is not approved for TDMS access.",
            log_detail=f"tenant {tenant_id!r} is not in the allow-list",
        )


@dataclass(frozen=True)
class VerifiedClaims:
    """Identity values TDMS has verified, not merely received.

    `tenant_id` and `object_id` are the durable pair. Microsoft guarantees `oid`
    is stable for the lifetime of the account and never reused; the email may
    change on any given Tuesday.
    """

    tenant_id: uuid.UUID
    object_id: uuid.UUID
    #: `preferred_username` / `upn` — used for display, provisioning and the
    #: one-time elevated bootstrap match. Never as the authorisation key.
    username: str
    display_name: str
    #: Correlation reference retained for authorised investigation (AUTH-11).
    token_reference: str

    @property
    def normalised_username(self) -> str:
        return (self.username or "").strip().lower()
