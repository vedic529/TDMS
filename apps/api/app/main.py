"""TDMS API service.

Step 5 adds the first real endpoints: Microsoft Entra authentication, the
central authorisation policy, the role access-request workflow and the Super
Admin administration surface.

Student, timetable, trainer, reference-data and bulk-import endpoints are NOT
implemented yet. The frontend continues to use ``MockTdmsClient`` for those (see
``apps/web/src/services``).

Supabase is not connected. DATA-07 requires the hosting configuration to be
approved before a production database is used.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.auth.tokens import EXPECTED_TOKEN_VERSION
from app.core.config import get_settings

logger = logging.getLogger("tdms")

settings = get_settings()


def _configure_logging() -> None:
    """Make TDMS log records visible under uvicorn.

    Uvicorn configures its own loggers and leaves the root logger without a
    handler, so anything TDMS logs is silently dropped. Attaching one handler to
    the `tdms` logger keeps our records visible without touching uvicorn's.
    """
    tdms_logger = logging.getLogger("tdms")
    if not tdms_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     [%(name)s] %(message)s"))
        tdms_logger.addHandler(handler)
    tdms_logger.setLevel(logging.INFO)
    tdms_logger.propagate = False


_configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Refuse to look healthy when authentication cannot work.

    A production deployment missing its Entra configuration must fail loudly.
    The quiet alternative — falling back to mock authentication — is an
    application that lets anyone in while appearing to work perfectly.
    """
    error = settings.auth_configuration_error()
    if error is None:
        if not settings.is_entra_mode:
            logger.warning(
                "TDMS_AUTH_MODE=mock: development authentication is active. "
                "This is never permitted in production."
            )
    elif settings.is_production:
        raise RuntimeError(f"TDMS cannot start: {error}")
    else:
        logger.error("Authentication is not usable: %s", error)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="TDMS API",
    description=(
        "Timetable Database Management System application service. "
        "Authentication, authorisation and access requests are implemented; "
        "operational endpoints are added as each SRS page is connected."
    ),
    version="0.2.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# The frontend runs on a different origin during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness endpoint used by developers and future deployment health checks."""
    return {"status": "ok", "service": "tdms-api"}


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    """Points a curious browser at the interactive documentation."""
    return {
        "service": "tdms-api",
        "environment": settings.app_env,
        "documentation": "/docs",
        "health": "/health",
    }


@app.get("/auth/configuration", tags=["system"])
def auth_configuration() -> dict[str, object]:
    """What the frontend needs to render sign-in, and nothing secret.

    Client IDs are public identifiers — they appear in every authorisation URL.
    No secret is here and none may ever be: the browser is not a confidential
    client. The tenant ID is deliberately reported as a count, not a value.
    """
    error = settings.auth_configuration_error()
    return {
        "authMode": settings.auth_mode,
        "entraConfigured": settings.is_entra_configured,
        # The audience the API validates: the TDMS API application, not the SPA.
        "apiClientId": settings.entra_client_id or None,
        "authorizedClientCount": len(settings.entra_authorized_client_ids),
        "requiredScope": settings.entra_api_scope or None,
        "expectedTokenVersion": EXPECTED_TOKEN_VERSION,
        "allowedTenantCount": len(settings.entra_allowed_tenant_ids),
        "redirectUri": settings.entra_redirect_uri or None,
        "sessionInactivityMinutes": settings.session_inactivity_minutes,
        "configurationError": error,
    }
