"""Validate a Microsoft Entra ID access token.

The API validates the token itself. It never trusts the browser's word about who
the user is, and never accepts a decoded-but-unverified JWT: anyone can produce
one of those.

Checked, in order:

1. **Signature** against the issuing tenant's published JWKS.
2. **Audience** — the token was minted for *this* API, not for some other app
   the same user also signed in to.
3. **Issuer** — matches the tenant that the `tid` claim declares, so a token
   cannot claim one tenant while being signed by another.
4. **Expiry**, with a small clock skew allowance.
5. **Tenant allow-list** — the actual security boundary. An email suffix is not
   one: anybody can create `finance@chelsongordon.com.attacker.example` in their
   own tenant, and a personal Microsoft account lives in the fixed consumer
   tenant, which is simply not on the list.
6. **Token version** — the TDMS API registration sets
   `requestedAccessTokenVersion = 2`, so a v1 token is not one of ours.
7. **The required delegated scope**, when one is configured — so a token minted
   for a different API in the same tenant cannot be replayed against TDMS.
8. **The authorised client** (`azp`) — audience and scope alone would admit any
   application the tenant pre-authorises or a user consents to. Pinning `azp`
   means only the TDMS SPA can call the API on a user's behalf.
9. **A usable `oid`**, since that is the durable identity everything else hangs
   off.

Note on `aud`: for a **v2** access token Microsoft sets `aud` to the API's
**application (client) ID**, not to the `api://…` Application ID URI. The URI is
how the *client* asks for the scope; it is not what arrives in the token.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import jwt
from jwt import PyJWKClient

from app.auth.claims import AuthenticationError, TenantNotAllowedError, VerifiedClaims
from app.core.config import Settings, get_settings

#: The fixed tenant that issues tokens for personal Microsoft accounts
#: (Outlook.com, Hotmail, Xbox). TDMS is organisation-only, so it is refused
#: even if someone adds it to the allow-list by mistake.
CONSUMER_TENANT_ID = "9188040d-6c67-4c5b-b112-36a304b66dad"

logger = logging.getLogger("tdms.auth")

_ALLOWED_ALGORITHMS = ("RS256",)
_LEEWAY_SECONDS = 60

# One JWKS client per tenant. PyJWKClient caches signing keys, so a request does
# not fetch Microsoft's key set every time.
_jwk_clients: dict[str, PyJWKClient] = {}


def reset_jwk_clients() -> None:
    """Drop cached JWKS clients. Used by tests and after a config change."""
    _jwk_clients.clear()


def _issuer(tenant_id: str, settings: Settings) -> str:
    return f"{settings.entra_authority_host}/{tenant_id}/v2.0"


def _jwks_url(tenant_id: str, settings: Settings) -> str:
    return f"{settings.entra_authority_host}/{tenant_id}/discovery/v2.0/keys"


def _jwk_client(tenant_id: str, settings: Settings) -> PyJWKClient:
    url = _jwks_url(tenant_id, settings)
    client = _jwk_clients.get(url)
    if client is None:
        client = PyJWKClient(url, cache_keys=True)
        _jwk_clients[url] = client
    return client


def _unverified_tenant_id(token: str) -> str:
    """Read `tid` without trusting it, only to choose which key set to fetch.

    Nothing is authorised on this value. It selects a JWKS endpoint; if the token
    was not signed by that tenant, signature verification fails, and the issuer
    check below re-derives the issuer from this same claim so the two cannot
    disagree.
    """
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise AuthenticationError(log_detail=f"token is not a readable JWT: {exc}") from exc

    tenant_id = str(unverified.get("tid") or "").strip()
    if not tenant_id:
        raise AuthenticationError(
            "Your organisation is not approved for TDMS access.",
            log_detail="token carries no 'tid' claim; not an organisational account",
        )
    return tenant_id


def _require_uuid(value: Any, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise AuthenticationError(log_detail=f"claim {field!r} is not a UUID: {value!r}") from exc


def verify_access_token(token: str, settings: Settings | None = None) -> VerifiedClaims:
    """Verify a Microsoft access token and return the identity it proves."""
    settings = settings or get_settings()

    error = settings.auth_configuration_error()
    if error:
        raise AuthenticationError(
            "Microsoft sign-in is not configured on this server.", log_detail=error
        )

    if not token or not token.strip():
        raise AuthenticationError(log_detail="no bearer token supplied")

    tenant_id = _unverified_tenant_id(token)

    # The allow-list is checked before any network call, so an unknown tenant
    # cannot make the API fetch arbitrary JWKS URLs on its behalf.
    allowed = {t.strip().lower() for t in settings.entra_allowed_tenant_ids if t.strip()}
    if tenant_id.lower() == CONSUMER_TENANT_ID:
        raise TenantNotAllowedError(tenant_id)
    if tenant_id.lower() not in allowed:
        raise TenantNotAllowedError(tenant_id)

    try:
        signing_key = _jwk_client(tenant_id, settings).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=list(_ALLOWED_ALGORITHMS),
            audience=settings.entra_client_id,
            issuer=_issuer(tenant_id, settings),
            leeway=_LEEWAY_SECONDS,
            # `nbf` is validated automatically by PyJWT when present.
            options={"require": ["exp", "aud", "iss", "tid", "oid"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError(
            "Your sign-in has expired. Please sign in again.", log_detail="token expired"
        ) from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError(log_detail=f"token rejected: {type(exc).__name__}: {exc}") from exc

    _require_token_version(payload)
    _require_scope(payload, settings)
    _require_authorized_client(payload, settings)

    # A safe record that validation succeeded and on what shape of token.
    # Deliberately omits the token, the tenant value and the object ID: the
    # first is a credential, and the other two are identifiers this project
    # keeps out of logs. `tid` and `oid` are reported as booleans instead.
    logger.info(
        "token accepted: ver=%s aud=%s scp=%r azp=%s tenant_allowed=%s oid_present=%s",
        payload.get("ver"),
        payload.get("aud"),
        payload.get("scp"),
        payload.get("azp") or payload.get("appid"),
        True,
        bool(payload.get("oid")),
    )
    return claims_from_payload(payload)


#: The TDMS API registration requests v2 access tokens.
EXPECTED_TOKEN_VERSION = "2.0"


def _require_token_version(payload: dict[str, Any]) -> None:
    """Refuse anything that is not a v2 access token.

    A v1 token carries different claim semantics — notably `aud` as the
    `api://…` URI rather than the client ID — so accepting both would mean two
    validation paths, and the weaker one would eventually be the one that
    mattered.
    """
    version = str(payload.get("ver") or "").strip()
    if version != EXPECTED_TOKEN_VERSION:
        raise AuthenticationError(
            log_detail=f"expected a v{EXPECTED_TOKEN_VERSION} access token, got ver={version!r}"
        )


def _require_authorized_client(payload: dict[str, Any], settings: Settings) -> None:
    """Confirm the token was issued to a client application TDMS trusts.

    Skipped when no client is configured. `azp` is the v2 claim naming the
    application the token was issued to; `appid` is its v1 spelling and is
    accepted as a fallback rather than assumed absent.
    """
    allowed = {c.strip().lower() for c in settings.entra_authorized_client_ids if c.strip()}
    if not allowed:
        return

    client_id = str(payload.get("azp") or payload.get("appid") or "").strip().lower()
    if not client_id:
        raise AuthenticationError(
            log_detail="token carries no 'azp'/'appid' claim; cannot identify the calling client"
        )
    if client_id not in allowed:
        raise AuthenticationError(
            log_detail=f"token was issued to client {client_id!r}, which is not authorised for TDMS"
        )


def _require_scope(payload: dict[str, Any], settings: Settings) -> None:
    """Confirm the token carries the delegated scope TDMS exposes.

    Skipped when no scope is configured, because the audience check already
    limits the token to this application and refusing every request would help
    nobody while the API registration is still being created.
    """
    required = settings.entra_api_scope.strip()
    if not required:
        return

    # Microsoft puts delegated scopes in `scp` as a space-separated string.
    # `roles` carries application permissions, which a *user* token never has.
    granted = str(payload.get("scp") or "").split()
    if required not in granted:
        raise AuthenticationError(
            log_detail=f"token does not carry the required scope {required!r}; got {granted}"
        )


def claims_from_payload(payload: dict[str, Any]) -> VerifiedClaims:
    """Build `VerifiedClaims` from an already-verified token payload."""
    tenant_id = _require_uuid(payload.get("tid"), "tid")
    object_id = _require_uuid(payload.get("oid"), "oid")

    username = str(
        payload.get("preferred_username") or payload.get("upn") or payload.get("email") or ""
    ).strip()
    display_name = str(payload.get("name") or "").strip() or username

    if not username:
        raise AuthenticationError(
            log_detail="token carries no username claim; cannot provision an account"
        )
    if not display_name:
        raise AuthenticationError(log_detail="token carries no display name claim")

    return VerifiedClaims(
        tenant_id=tenant_id,
        object_id=object_id,
        username=username,
        display_name=display_name,
        # `uti`/`jti` identify the token, not the person. Safe to record.
        token_reference=str(payload.get("uti") or payload.get("jti") or "")[:64],
    )
