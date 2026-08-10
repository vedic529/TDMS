"""Application configuration.

Values come from environment variables so development, staging and production
configuration never mix. No secret, tenant identifier or database connection
string is committed to this repository.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _split(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the TDMS API."""

    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))

    # Empty until the final schema is approved (DATA-07 / OD-13).
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))

    # Supplied once the Microsoft Entra configuration is approved (OD-01).
    entra_tenant_id: str = field(default_factory=lambda: os.getenv("ENTRA_TENANT_ID", ""))
    entra_client_id: str = field(default_factory=lambda: os.getenv("ENTRA_CLIENT_ID", ""))

    cors_origins: list[str] = field(
        default_factory=lambda: _split(
            os.getenv("CORS_ORIGINS"),
            ["http://localhost:3000", "http://127.0.0.1:3000"],
        )
    )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
