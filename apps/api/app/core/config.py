"""Application configuration.

Values come from environment variables so development, staging and production
configuration never mix. No secret, tenant identifier or database connection
string is committed to this repository.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

# `apps/api/.env` wins for backend-specific values; the repository-root `.env`
# supplies the shared Docker/PostgreSQL settings. Both are ignored by Git.
_API_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _API_DIR.parents[1]

load_dotenv(_API_DIR / ".env")
load_dotenv(_REPO_ROOT / ".env")


def _split(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _compose_url(user: str, password: str) -> str:
    """Build a SQLAlchemy URL from the shared host/port/database settings.

    Percent-encodes the credentials so a password containing URL-reserved
    characters cannot corrupt the connection string. Nothing here is logged.
    """
    if not password:
        return ""
    host = os.getenv("TDMS_POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("TDMS_POSTGRES_PORT", "5432")
    name = os.getenv("TDMS_POSTGRES_DB", "tdms_dev")
    return f"postgresql+psycopg://{quote(user)}:{quote(password)}@{host}:{port}/{name}"


def _migration_database_url() -> str:
    """The **administrator** URL. Used by Alembic and by the test harness.

    Migrations create and drop objects, so they need privileges the running
    application must never have.
    """
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit
    return _compose_url(
        os.getenv("TDMS_POSTGRES_ADMIN_USER", "postgres"),
        os.getenv("TDMS_POSTGRES_ADMIN_PASSWORD", ""),
    )


def _database_url_from_environment() -> str:
    """The **runtime** URL FastAPI connects with.

    Prefers the least-privilege `tdms_app` role: it cannot create, alter or drop
    anything, and cannot UPDATE or DELETE `user_activity_records`, so LOG-05 is
    a privilege rather than a convention.

    Falls back to the administrator credentials when the application role has
    not been created yet, so an existing development machine keeps working. That
    fallback is reported by `runtime_identity`, not hidden.
    """
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit

    app_url = _compose_url(
        os.getenv("TDMS_POSTGRES_APP_USER", "tdms_app"),
        os.getenv("TDMS_POSTGRES_APP_PASSWORD", ""),
    )
    return app_url or _migration_database_url()


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the TDMS API."""

    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))

    # Composed from TDMS_POSTGRES_* when DATABASE_URL is not set explicitly.
    # NEVER log or print either of these: they contain a password.
    database_url: str = field(default_factory=_database_url_from_environment)
    #: The administrator URL, for Alembic and the test harness only.
    migration_database_url: str = field(default_factory=_migration_database_url)

    # -- Microsoft Entra ID --------------------------------------------------
    # `entra` validates real Microsoft tokens. `mock` accepts a development
    # identity header and is refused outright in production (see
    # `auth_configuration_error`).
    auth_mode: str = field(
        default_factory=lambda: os.getenv("TDMS_AUTH_MODE", "mock").strip().lower()
    )
    #: The **TDMS API** application (client) ID. This is the `aud` a v2 access
    #: token carries, so it is what the API validates against — not the SPA's
    #: client ID, which identifies the caller instead (see
    #: `entra_authorized_client_ids`).
    entra_client_id: str = field(default_factory=lambda: os.getenv("ENTRA_CLIENT_ID", "").strip())
    #: Client applications permitted to obtain a token for the TDMS API, matched
    #: against the v2 `azp` claim.
    #:
    #: Audience and scope alone are not enough: any application the tenant
    #: pre-authorises, or that a user consents to, could hold a token with the
    #: same `aud` and `scp`. Pinning `azp` means only the TDMS SPA can call the
    #: API on a user's behalf. Blank disables the check.
    entra_authorized_client_ids: list[str] = field(
        default_factory=lambda: _split(os.getenv("ENTRA_AUTHORIZED_CLIENT_IDS"), [])
    )
    #: Every tenant permitted to reach TDMS. This — not the email suffix — is the
    #: security boundary, so a personal Microsoft account or a lookalike domain in
    #: someone else's tenant is refused.
    entra_allowed_tenant_ids: list[str] = field(
        default_factory=lambda: _split(os.getenv("ENTRA_ALLOWED_TENANT_IDS"), [])
    )
    entra_redirect_uri: str = field(
        default_factory=lambda: os.getenv("ENTRA_REDIRECT_URI", "").strip()
    )
    #: The delegated scope an access token must carry, e.g. `access_as_user`.
    #: Checking it is what stops a token minted for a *different* API in the same
    #: tenant from being replayed against TDMS. Left blank until the API app
    #: registration exposes a scope; the audience check still applies.
    entra_api_scope: str = field(
        default_factory=lambda: os.getenv("ENTRA_API_SCOPE", "").strip()
    )

    #: Optional override for sovereign or test clouds.
    entra_authority_host: str = field(
        default_factory=lambda: os.getenv(
            "ENTRA_AUTHORITY_HOST", "https://login.microsoftonline.com"
        ).strip().rstrip("/")
    )

    #: OD-03, confirmed: 30 minutes of inactivity ends the TDMS session.
    session_inactivity_minutes: int = field(
        default_factory=lambda: int(os.getenv("TDMS_SESSION_INACTIVITY_MINUTES", "30"))
    )

    # -- Notifications -------------------------------------------------------
    #: `graph` sends through Microsoft Graph; anything else logs a development
    #: notification instead of pretending a message was delivered.
    notification_mode: str = field(
        default_factory=lambda: os.getenv("TDMS_NOTIFICATION_MODE", "development").strip().lower()
    )
    graph_tenant_id: str = field(default_factory=lambda: os.getenv("GRAPH_TENANT_ID", "").strip())
    graph_client_id: str = field(default_factory=lambda: os.getenv("GRAPH_CLIENT_ID", "").strip())
    # Read from the environment only; never logged, never returned by an endpoint.
    graph_client_secret: str = field(
        default_factory=lambda: os.getenv("GRAPH_CLIENT_SECRET", "").strip(), repr=False
    )
    #: Where an emailed link should point. Not a security boundary — the link
    #: opens TDMS, which authenticates the approver normally.
    app_base_url: str = field(
        default_factory=lambda: os.getenv("TDMS_APP_BASE_URL", "http://localhost:3000").strip()
    )

    cors_origins: list[str] = field(
        default_factory=lambda: _split(
            os.getenv("CORS_ORIGINS"),
            ["http://localhost:3000", "http://127.0.0.1:3000"],
        )
    )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def has_database(self) -> bool:
        return bool(self.database_url)

    @property
    def safe_database_target(self) -> str:
        """Host/port/database with the credentials stripped, safe to display."""
        if not self.database_url:
            return "(not configured)"
        tail = self.database_url.rsplit("@", 1)[-1]
        return tail or "(not configured)"

    @property
    def runtime_identity(self) -> str:
        """The database role the application connects as. Safe to display."""
        if not self.database_url:
            return "(not configured)"
        try:
            return self.database_url.split("://", 1)[1].split(":", 1)[0]
        except IndexError:  # pragma: no cover - malformed URL
            return "(unknown)"

    @property
    def uses_least_privilege_runtime_role(self) -> bool:
        """False when the application is still falling back to the admin role."""
        return self.runtime_identity != os.getenv("TDMS_POSTGRES_ADMIN_USER", "postgres")

    # -- Authentication state ------------------------------------------------

    @property
    def is_entra_mode(self) -> bool:
        return self.auth_mode == "entra"

    @property
    def is_entra_configured(self) -> bool:
        return bool(self.entra_client_id and self.entra_allowed_tenant_ids)

    def auth_configuration_error(self) -> str | None:
        """Why authentication cannot run, or None when it can.

        Production never falls back to mock: a deployment missing its Entra
        configuration must fail loudly, because the quiet alternative is an
        application that lets anyone in while looking like it is working.
        """
        if self.is_entra_mode:
            missing = []
            if not self.entra_client_id:
                missing.append("ENTRA_CLIENT_ID")
            if not self.entra_allowed_tenant_ids:
                missing.append("ENTRA_ALLOWED_TENANT_IDS")
            if missing:
                return (
                    "Microsoft Entra sign-in is selected but not configured. "
                    f"Missing: {', '.join(missing)}."
                )
            return None

        if self.is_production:
            return (
                "TDMS_AUTH_MODE must be 'entra' in production. Mock authentication "
                "is a development tool and is never a production fallback."
            )
        return None

    @property
    def is_graph_configured(self) -> bool:
        return bool(self.graph_tenant_id and self.graph_client_id and self.graph_client_secret)


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
