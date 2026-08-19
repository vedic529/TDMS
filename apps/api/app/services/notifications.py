"""Notify the Super Admin approval group that an access request was submitted.

The email is **notification only**. It carries no approval token, no link that
grants anything and no secret. A Super Admin approves by signing in to TDMS and
acting there — an emailed decision link would turn "can read this mailbox" into
"can grant TDMS access", which is not a trade anyone made knowingly.

Two implementations behind one interface:

* :class:`DevelopmentNotificationService` records the notification and returns a
  result that says, plainly, that nothing was delivered. It never reports success
  it did not achieve.
* :class:`MicrosoftGraphNotificationService` sends through Graph `Mail.Send` once
  IT has configured the application registration and consented the permission.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from app.core import rbac
from app.core.config import Settings, get_settings
from app.db.seeds.manifest import APPROVAL_NOTIFICATION_RECIPIENTS, NOTIFICATION_SENDER

logger = logging.getLogger("tdms.notifications")


@dataclass(frozen=True)
class AccessRequestNotification:
    """The content of one notification. Nothing here is sensitive."""

    requester_display_name: str
    requester_email: str
    current_role: str
    requested_role: str
    requested_at: str
    administration_url: str

    def subject(self) -> str:
        return f"TDMS access request: {self.requester_display_name} - {rbac.ROLE_LABELS.get(self.requested_role, self.requested_role)}"

    def body(self) -> str:
        return "\n".join(
            [
                "TDMS Access Request",
                "",
                f"Requester      : {self.requester_display_name}",
                f"Email          : {self.requester_email}",
                f"Current role   : {rbac.ROLE_LABELS.get(self.current_role, self.current_role)}",
                f"Requested role : {rbac.ROLE_LABELS.get(self.requested_role, self.requested_role)}",
                f"Requested at   : {self.requested_at}",
                "",
                "Review it in TDMS:",
                self.administration_url,
                "",
                "This message is a notification only. Approve or deny inside TDMS after",
                "signing in; replying to this email does not decide the request.",
            ]
        )


@dataclass
class NotificationResult:
    delivered: bool
    provider: str
    recipients: tuple[str, ...]
    detail: str
    #: Present only when a provider actually accepted the message.
    provider_reference: str | None = None


class NotificationService(Protocol):
    def notify_access_request(self, notification: AccessRequestNotification) -> NotificationResult:
        ...


@dataclass
class DevelopmentNotificationService:
    """Records the notification instead of sending it.

    `delivered` is False, always. Reporting a successful send that never happened
    would hide a broken approval path until the day somebody needed it.
    """

    sender: str = NOTIFICATION_SENDER
    recipients: tuple[str, ...] = APPROVAL_NOTIFICATION_RECIPIENTS
    #: Every notification produced in this process, for tests and local inspection.
    sent: list[AccessRequestNotification] = field(default_factory=list)

    def notify_access_request(self, notification: AccessRequestNotification) -> NotificationResult:
        self.sent.append(notification)
        logger.info(
            "access request notification (development, NOT delivered): %s -> %s",
            notification.requester_email,
            notification.requested_role,
        )
        return NotificationResult(
            delivered=False,
            provider="development",
            recipients=self.recipients,
            detail=(
                "Recorded locally. No email was sent: Microsoft Graph Mail.Send is not "
                "configured for the approved sender."
            ),
        )


@dataclass
class MicrosoftGraphNotificationService:
    """Sends through Microsoft Graph `Mail.Send` as the approved sender.

    Requires the application permission `Mail.Send` on the registration, granted
    with admin consent, and nothing more. TDMS never reads a mailbox and never
    stores a mailbox password.
    """

    settings: Settings
    sender: str = NOTIFICATION_SENDER
    recipients: tuple[str, ...] = APPROVAL_NOTIFICATION_RECIPIENTS

    _GRAPH = "https://graph.microsoft.com/v1.0"
    _SCOPE = "https://graph.microsoft.com/.default"

    def _access_token(self) -> str:
        import httpx

        response = httpx.post(
            f"{self.settings.entra_authority_host}/{self.settings.graph_tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": self.settings.graph_client_id,
                "client_secret": self.settings.graph_client_secret,
                "scope": self._SCOPE,
                "grant_type": "client_credentials",
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def notify_access_request(self, notification: AccessRequestNotification) -> NotificationResult:
        import httpx

        try:
            token = self._access_token()
            response = httpx.post(
                f"{self._GRAPH}/users/{self.sender}/sendMail",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "message": {
                        "subject": notification.subject(),
                        "body": {"contentType": "Text", "content": notification.body()},
                        "toRecipients": [
                            {"emailAddress": {"address": address}} for address in self.recipients
                        ],
                    },
                    "saveToSentItems": True,
                },
                timeout=30,
            )
            response.raise_for_status()
        except Exception as exc:
            # A failed notification must not fail the request itself: the
            # request is recorded and visible in the dashboard regardless.
            logger.exception("Graph Mail.Send failed")
            return NotificationResult(
                delivered=False,
                provider="microsoft-graph",
                recipients=self.recipients,
                detail=f"Graph Mail.Send failed: {type(exc).__name__}. The request was still recorded.",
            )

        return NotificationResult(
            delivered=True,
            provider="microsoft-graph",
            recipients=self.recipients,
            detail="Sent through Microsoft Graph.",
            provider_reference=response.headers.get("request-id"),
        )


_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    """The configured service. Graph only when it is genuinely configured."""
    global _service
    if _service is None:
        settings = get_settings()
        if settings.notification_mode == "graph" and settings.is_graph_configured:
            _service = MicrosoftGraphNotificationService(settings=settings)
        else:
            _service = DevelopmentNotificationService()
    return _service


def reset_notification_service() -> None:
    """Drop the cached service. Used by tests and after a config change."""
    global _service
    _service = None
