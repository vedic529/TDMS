"""Development-only authentication.

Real Microsoft configuration (client ID, tenant IDs, redirect URIs) has not been
supplied yet, so development needs a way to exercise the four access levels
without inventing fake production values.

Two safeguards keep this out of production:

1. `Settings.auth_configuration_error()` refuses `TDMS_AUTH_MODE=mock` whenever
   `APP_ENV=production`, and the API returns 503 rather than serving requests.
2. Every mock identity carries :data:`MOCK_TENANT_ID`, which is not a real
   Microsoft tenant and would never appear in a genuine token. If a mock user
   somehow reached a real deployment, its tenant would not be on the allow-list.

The identities produced here are deliberately *derived* from the address, so no
fabricated Microsoft object IDs are stored anywhere as if they were real.
"""

from __future__ import annotations

import uuid

from app.auth.claims import VerifiedClaims

#: Not a real Microsoft tenant. Marks every identity produced here as synthetic.
MOCK_TENANT_ID = uuid.UUID("00000000-dead-4000-8000-000000000001")

#: Namespace for deriving a stable synthetic `oid` from an address, so the same
#: mock user is the same TDMS account across restarts.
_MOCK_OID_NAMESPACE = uuid.UUID("00000000-dead-4000-8000-000000000002")


def mock_object_id(username: str) -> uuid.UUID:
    return uuid.uuid5(_MOCK_OID_NAMESPACE, username.strip().lower())


def mock_claims_for(username: str, display_name: str | None = None) -> VerifiedClaims:
    """Build a synthetic verified identity for a development sign-in."""
    username = (username or "").strip().lower()
    if not username or "@" not in username:
        raise ValueError("Supply a full organisational email address for the mock user.")

    return VerifiedClaims(
        tenant_id=MOCK_TENANT_ID,
        object_id=mock_object_id(username),
        username=username,
        # A development placeholder, and visibly one. This is not a claim about
        # anybody's real name — with real Entra, `name` arrives from Microsoft.
        display_name=display_name or f"{username} (development)",
        token_reference="mock",
    )
