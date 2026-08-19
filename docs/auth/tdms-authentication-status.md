# TDMS Authentication — Configuration Status

**Non-secret status only.** No tenant ID, client ID, secret or credential value
appears in this file. Actual values live in the git-ignored `.env` and
`apps/web/.env.local`.

**Last reviewed:** 11 August 2026 (Step 5C — live SSO)
**Current rollout:** Chelson Gordon, single tenant — covers both
`@chelsongordon.com` and `@vconsultancy.com.au`

---

## 1. Status at a glance

| Item | Status |
| --- | --- |
| Chelson Gordon Tenant ID | **Configured** (local git-ignored config only) |
| TDMS Web (SPA) app registration | **Configured** |
| SPA Client ID | **Configured** |
| SPA redirect URI | **Configured** — `http://localhost:3000/login` (development) |
| TDMS API app registration | **Configured** |
| API Client ID | **Configured** |
| API Application ID URI | **Configured** — `api://<api-client-id>` |
| API delegated scope | **Configured** — `access_as_user` |
| TDMS Web pre-authorisation | **Configured** — delegated `access_as_user` |
| `requestedAccessTokenVersion` | **2** |
| MSAL (`@azure/msal-browser` 4.7) | **Configured** — authorisation code + PKCE, `sessionStorage` |
| Backend token validation | **Configured** — signature, v2 issuer, audience, expiry, tenant, `ver`, scope, `azp`, `oid` |
| `tid + oid` durable identity | **Configured and proven live** |
| JIT Viewer provisioning | **Configured** |
| Elevated bootstrap binding | **Configured and proven live** — 4 Super Admin, 2 Admin |
| Live Microsoft SSO test | **PASS** — real Chelson Gordon sign-in, token accepted by FastAPI |
| Graph `Mail.Send` | **Pending** — next external Microsoft work item |
| Notification sender | `v.yadav@chelsongordon.com` |
| V Consultancy | **Resolved — same tenant**, no separate tenant ID |
| Staging redirect | **Pending** |
| Production redirect | **Pending** |

**Authentication mode in force:** `entra` — real Microsoft token validation. The
development adapter is refused: `X-TDMS-Mock-User` returns 401 in this mode, and
mock is refused outright when `APP_ENV=production`.

---

## 2. Live SSO result

A real Chelson Gordon organisational account signed in against the local stack
and FastAPI validated the resulting TDMS API access token.

| Stage | Result |
| --- | --- |
| Authorisation request (code + PKCE S256) | PASS |
| Microsoft token endpoint | PASS |
| FastAPI `GET /me` with the bearer token | **200 OK** |
| Token validation (signature, v2 issuer, audience, tenant, scope, `azp`, `oid`) | PASS |
| TDMS user provisioned | PASS — created once |
| Durable identity `tid + oid` stored | PASS |
| Display name from Microsoft claims | PASS |
| Role from the elevated bootstrap rule | PASS |
| Second sign-in | PASS — no duplicate row |
| No password stored anywhere | PASS |

**Audience note.** For a v2 access token Microsoft sets `aud` to the API's
**application (client) ID**, not the `api://…` Application ID URI. The URI is how
the client *asks* for the scope. The backend validates the client ID, and refuses
a v1 token outright, because v1 carries different claim semantics and supporting
both would mean two validation paths — the weaker of which would eventually be
the one that mattered.

---

## 3. Configuration keys

Names only — values are never recorded here.

**Backend** (repository-root `.env`, git-ignored)

| Key | Status |
| --- | --- |
| `TDMS_AUTH_MODE` | `entra` |
| `ENTRA_ALLOWED_TENANT_IDS` | **configured** (1 tenant) |
| `ENTRA_CLIENT_ID` | **configured** — the **API** client ID (the v2 `aud`) |
| `ENTRA_AUTHORIZED_CLIENT_IDS` | **configured** — the TDMS SPA only (`azp`) |
| `ENTRA_API_SCOPE` | `access_as_user` (the bare `scp` value, not the URI) |
| `ENTRA_REDIRECT_URI` | `http://localhost:3000/login` |
| `TDMS_SESSION_INACTIVITY_MINUTES` | 30 |
| `TDMS_NOTIFICATION_MODE` | `development` |
| `GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` | blank |

**Frontend** (`apps/web/.env.local`, git-ignored)

| Key | Status |
| --- | --- |
| `NEXT_PUBLIC_TDMS_AUTH_MODE` | `entra` |
| `NEXT_PUBLIC_ENTRA_ALLOWED_TENANT_IDS` | **configured** (1 tenant) |
| `NEXT_PUBLIC_ENTRA_CLIENT_ID` | **configured** — the **SPA** client ID |
| `NEXT_PUBLIC_ENTRA_API_SCOPE` | **configured** — the full `api://…/access_as_user` |
| `NEXT_PUBLIC_ENTRA_REDIRECT_URI` | `http://localhost:3000/login` |

`NEXT_PUBLIC_` values are embedded in the browser bundle. A client ID, tenant ID
and authority are public identifiers and belong there. A **client secret** never
does.

Check the live state at any time:

```bash
curl http://localhost:8000/auth/configuration
```

It reports mode, whether Entra is configured, how many tenants are allowed and
any configuration error — and no secret.

---

## 4. What is already proven

Verified by automated tests against test-only verified-claim fixtures:

| Scenario | Result |
| --- | --- |
| Correct CG tenant | accepted |
| Unknown tenant | denied |
| Personal/consumer Microsoft tenant | denied, even if allow-listed by mistake |
| Correct email domain in the wrong tenant | denied |
| Missing `tid` or unusable `oid` | denied |
| Unsigned or wrongly-signed token | denied |
| Token without the required scope | denied |
| Same `tid + oid`, changed mailbox | same TDMS user, role unchanged |
| Normal first sign-in | provisioned as VIEWER |
| Approved elevated address, first binding | expected elevated role |
| Elevated account later demoted | **not** re-elevated at next sign-in |
| Disabled TDMS account | denied |

---

## 5. Session

Inactivity timeout **30 minutes** (OD-03, confirmed). After it expires the TDMS
session ends and the user re-enters the Microsoft flow; Microsoft may complete it
without a prompt if the organisational session is still valid. TDMS stores no
Microsoft password. MSAL caches tokens in `sessionStorage`, so they do not
outlive the browser tab on a shared machine.

---

## 6. Deployment checklist — not configured yet

**Staging**

- [ ] Staging HTTPS domain decided
- [ ] Staging SPA redirect URI registered
- [ ] Staging environment configuration
- [ ] Decide: reuse the app registration or register separately per environment

**Production**

- [ ] Final TDMS HTTPS domain
- [ ] Production redirect URI registered
- [ ] Production app-registration decision
- [ ] Cloudflare environment variables and secret storage
- [ ] Backend deployment environment
- [ ] Graph secret or certificate in a managed secret store, never in `.env`

**V Consultancy** — resolved 11 August 2026: the same Entra tenant. Users at
`@chelsongordon.com` and `@vconsultancy.com.au` are both admitted by the one
configured tenant ID, and the registration stays single-tenant. No further
configuration.
