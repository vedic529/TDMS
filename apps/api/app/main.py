"""TDMS API service.

This is a deliberately minimal FastAPI skeleton. Its only purpose at this stage
is to prove that:

  * the Python virtual environment works from the committed requirements file;
  * FastAPI starts successfully;
  * the frontend can later be pointed at a real service;
  * a deployment platform has a stable health-check endpoint.

Student, timetable, trainer, reference-data, bulk-import and authentication
endpoints are NOT implemented yet. The frontend continues to use
``MockTdmsClient`` until they exist (see ``apps/web/src/services``).

Nothing here connects to a database. DATA-07 requires the final schema to be
approved before Supabase or another production host is connected.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="TDMS API",
    description=(
        "Timetable Database Management System application service. "
        "Skeleton only - business endpoints are added as each SRS page is implemented."
    ),
    version="0.1.0",
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
