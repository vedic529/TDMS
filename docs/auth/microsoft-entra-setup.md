# Microsoft Entra ID — Configuration Checklist for IT

What TDMS needs before real Microsoft sign-in can be switched on, and what it
does with each value.

**No secret value appears in this document.** Client secrets and the like belong
in the git-ignored `.env` files and nowhere else.

---

## 1. Current status

| Item | Status |
| --- | --- |
| Chelson Gordon tenant ID | **Configured.** Held in the git-ignored `.env` / `apps/web/.env.local` |
| **TDMS Web (SPA) registration** | **CONFIGURED** (§A) |
| SPA Application (Client) ID | **CONFIGURED** |
| Development redirect URI | **CONFIGURED** — `http://localhost:3000/login` |
| TDMS API registration | **CONFIGURED** (§B) |
| API Application (Client) ID | **CONFIGURED** |
| API Application ID URI | **CONFIGURED** — `api://<api-client-id>` |
| `access_as_user` scope | **CONFIGURED** |
| SPA pre-authorised for the API | **CONFIGURED** (§C) |
| `requestedAccessTokenVersion` | **2** |
| MSAL in the frontend | **CONFIGURED** — `@azure/msal-browser` 4.7, code + PKCE |
| Backend token validation | **CONFIGURED** |
| **Live SSO test** | **PASS — 11 August 2026** |
| V Consultancy tenant ID | **RESOLVED — same tenant.** No separate tenant exists (see §3) |
| Staging / production redirect URIs | **Not needed yet** |
| Graph `Mail.Send` for `v.yadav@chelsongordon.com` | **Outstanding (§D)** — next external work item |
| Graph `User.Read` on the SPA registration | **Unused** — optional cleanup, see §6a |

**Live Microsoft SSO is operational locally.** `TDMS_AUTH_MODE=entra`, real
tokens validated, users provisioned from verified `tid + oid`.

Sections §A–§C are kept as the record of what was configured, and as the
instructions for repeating it in another environment.

---

## §A. Create the TDMS Web (SPA) registration

**Purpose.** The browser needs its own application identity to start a Microsoft
sign-in. Without it there is nothing for MSAL to identify itself as.

**Who needs permission.** Someone who can create app registrations in the Chelson
Gordon tenant — typically **Application Administrator**, **Cloud Application
Administrator** or **Global Administrator**.

**Where to go.** <https://entra.microsoft.com> → **Applications** →
**App registrations** → **+ New registration**

**Steps**

1. **Name:** `TDMS Web`
2. **Supported account types:** *Accounts in this organisational directory only
   (Chelson Gordon only — Single tenant)*.
   Do **not** choose multitenant. TDMS is organisation-only for this phase, and
   V Consultancy is deferred.
3. **Redirect URI:** choose platform **Single-page application (SPA)** and enter
   exactly:

   ```
   http://localhost:3000/login
   ```

   Exactly that — no trailing slash. It is the address the running application
   uses, and Microsoft matches redirect URIs character for character.
   **Platform must be SPA**, not "Web": a Web platform expects a client secret,
   and a browser cannot keep one.
4. **Register.**
5. On the app's **Authentication** page, confirm under *Single-page application*
   that the URI is listed. Leave *Implicit grant* checkboxes **unticked** — MSAL
   uses the authorisation code flow with PKCE, which needs neither.

**Value to bring back**

- **Application (client) ID** — from the app's **Overview** page.

**SAFE TO PROVIDE TO CLAUDE:** the Application (client) ID. It is a public
identifier that appears in every authorisation URL.

**DO NOT PROVIDE TO CLAUDE:** any client secret, certificate or credential. The
SPA does not need one, so do not create one.

**How to verify it worked.** The Overview page shows the app name, an
Application (client) ID, and a Directory (tenant) ID matching the tenant already
configured. The Authentication page lists your SPA redirect URI.

---

## §B. Create the TDMS API registration *(after §A)*

**Purpose.** FastAPI is a separate protected resource. The browser must obtain a
token whose **audience is the API**, not an ID token for the SPA — an ID token
authenticates the client application, not the caller, and the API refuses it.

**Where to go.** **App registrations** → **+ New registration**

1. **Name:** `TDMS API`
2. **Supported account types:** *Single tenant* (as above).
3. **Redirect URI:** leave blank — an API has no sign-in redirect.
4. **Register.**

Then **Expose an API** on the new registration:

5. Next to *Application ID URI*, click **Add** and accept the default
   `api://<API-CLIENT-ID>`.
6. **+ Add a scope**:
   - **Scope name:** `access_as_user`
   - **Who can consent:** *Admins and users*
   - **Admin consent display name:** `Access TDMS as the signed-in user`
   - **Admin consent description:** `Allows the TDMS web application to call the
     TDMS API on behalf of the signed-in user.`
   - **User consent display name:** `Access TDMS on your behalf`
   - **User consent description:** `Allows TDMS to read and change timetable and
     student data according to your TDMS access level.`
   - **State:** *Enabled*
   - **Add scope.**

**Values to bring back (all non-secret)**

- API **Application (client) ID**
- **Application ID URI** (e.g. `api://<API-CLIENT-ID>`)
- the full scope value: `api://<API-CLIENT-ID>/access_as_user`

**DO NOT PROVIDE:** any client secret. Validating incoming user tokens needs none.

---

## §C. Let the SPA call the API *(after §A and §B)*

**Where to go.** **App registrations** → **TDMS Web** → **API permissions** →
**+ Add a permission** → **My APIs** → **TDMS API** → **Delegated permissions**
→ tick **access_as_user** → **Add permissions**.

Because the scope allows *Admins and users* to consent, each user can consent at
first sign-in. If the tenant has **user consent disabled** — common in managed
organisations — click **Grant admin consent for Chelson Gordon** once, which
needs Privileged Role Administrator or Global Administrator.

**How to verify.** The API permissions table lists `TDMS API / access_as_user`
with status *Granted* (or blank, if you are relying on per-user consent).

**Value to bring back:** none. Just confirm it is added.

---

---

## 2. What IT needs to provide

### 2.1 Application registration

A single-tenant (or multi-tenant, see §3) app registration for TDMS.

| Value | Where it goes | Secret? |
| --- | --- | --- |
| Application (Client) ID | `ENTRA_CLIENT_ID`, `NEXT_PUBLIC_ENTRA_CLIENT_ID` | No — it appears in every authorisation URL |
| Directory (Tenant) ID | `ENTRA_ALLOWED_TENANT_IDS`, `NEXT_PUBLIC_ENTRA_ALLOWED_TENANT_IDS` | No |
| Client secret | **Not used by TDMS sign-in.** Only Graph email needs one (§5) | **Yes** |

**Supported account types must be work/school accounts only.** TDMS is
organisation-only, and personal Microsoft accounts (Outlook.com, Hotmail) are
refused by the API regardless of registration settings.

The frontend is a **public client** — a browser cannot keep a secret. Sign-in
uses the authorisation code flow with PKCE, so no secret is needed and none may
ever be placed in a `NEXT_PUBLIC_` variable.

### 2.2 Redirect URIs

Register one per environment, as **SPA** redirect URIs:

| Environment | URI |
| --- | --- |
| Development | `http://localhost:3000/login` |
| Staging | *(to be decided)* |
| Production | *(to be decided)* |

### 2.3 API exposure

The API validates that a token was minted for TDMS, not for some other
application the same person also signed in to. Expose an API scope on the
registration (for example `api://<client-id>/access_as_user`) so the frontend can
request a token whose audience is the TDMS Client ID.

---

## 3. V Consultancy — resolved

**Confirmed 11 August 2026: Chelson Gordon and V Consultancy use the SAME
Microsoft Entra tenant.** There is no separate V Consultancy tenant ID.

TDMS users may hold an address at either domain:

- `@chelsongordon.com`
- `@vconsultancy.com.au`

Both resolve to the one configured tenant, so **one** tenant ID covers everyone
and the app registration stays **single-tenant**. Nothing extra to configure.

This changes nothing about how access is decided. The `tid` claim remains the
admission boundary and `tid + oid` the durable identity; the email domain is
still only display, provisioning and the one-time elevated bootstrap match. A
`@vconsultancy.com.au` user is admitted because their verified tenant is
approved — not because of their address — and, like everyone else, arrives as a
**Viewer** unless they are on the elevated bootstrap list.

---

## 4. Why tenant, not email domain

Anybody can create `finance@chelsongordon.com.example` — or even a domain that
looks identical — inside a tenant they control, and Microsoft will happily issue
them a valid token. The email address in a token proves nothing about which
organisation the person belongs to.

The `tid` claim does. It is issued by Microsoft, covered by the token signature,
and cannot be chosen by the user. TDMS therefore admits on `tid` and uses the
email only for display, provisioning and the one-time elevated bootstrap match.

Personal Microsoft accounts all live in the fixed consumer tenant
`9188040d-6c67-4c5b-b112-36a304b66dad`, which TDMS refuses outright — even if it
were added to the allow-list by mistake.

---

## 5. Microsoft Graph — access request notifications

When a user requests a higher role, the four Super Admins are notified by email.

| | |
| --- | --- |
| Sender mailbox | `v.yadav@chelsongordon.com` |
| Recipients | `a.chattopadhyay@`, `w.rajjak@`, `v.yadav@`, `d.panda@` (all `chelsongordon.com`) |
| Permission needed | **`Mail.Send` (application), admin consent** — and nothing else |

Deliberately **not** requested: any mailbox-read permission. TDMS never reads a
mailbox, never stores a mailbox password, and implements no email-reading
feature.

Configuration (`GRAPH_CLIENT_SECRET` is a genuine secret — git-ignored `.env`
only):

```
TDMS_NOTIFICATION_MODE=graph
GRAPH_TENANT_ID=
GRAPH_CLIENT_ID=
GRAPH_CLIENT_SECRET=
```

Until this is configured, `TDMS_NOTIFICATION_MODE=development` records the
notification locally and reports plainly that **nothing was sent**. It never
claims a delivery it did not achieve — a silently broken approval path is only
discovered on the day somebody needs it.

**The email is a notification only.** It contains no approval token and no link
that grants anything. A Super Admin signs in to TDMS and decides there. An
emailed decision link would turn "can read this mailbox" into "can grant TDMS
access", which is not a trade anyone made knowingly.

---

## 6. What TDMS does with a token

```
Microsoft Entra
      |  verified access token
      v
FastAPI validates: signature (tenant JWKS) -> audience -> issuer
                   -> expiry -> tenant allow-list -> usable oid
      |
      v
tid + oid  ->  TDMS user record
      |
      +-- account ACTIVE?      no  -> denied
      +-- access level?        -> Viewer / Data Editor / Admin / Super Admin
      |
      v
access granted or denied
```

The API validates the token itself. It never accepts a decoded-but-unverified
JWT, and never takes the browser's word for who the user is.

**`tid + oid` is the durable identity.** Microsoft guarantees `oid` is stable for
the life of the account and never reused; an email address changes whenever
somebody marries, or a mailbox is reassigned. So a rename updates the profile and
nothing else — it cannot promote anyone, and it cannot create a second account.

---

## 6a. Microsoft Graph `User.Read` — unused

TDMS does **not** call Microsoft Graph for its own sign-in. The SPA requests
exactly one scope — the TDMS API's `access_as_user` — and every profile value it
needs (`name`, `preferred_username`, `oid`, `tid`) arrives in the access token
Microsoft already issues. There is no `graph.microsoft.com/me` call anywhere in
the frontend.

So if the **TDMS Web** registration carries a delegated `User.Read` permission,
it is unused. Removing it is **optional cleanup**, not a fix, and is best done
after a period of stable operation rather than alongside the initial rollout.

The only Graph reference in the codebase is the backend notification service,
which is a separate application permission (`Mail.Send`) and is not configured
yet (§5).

---

## 7. First sign-in

**Any approved-tenant user with no TDMS account** is created as `VIEWER`,
`ACTIVE`, with their verified `tid` and `oid` and their Microsoft display name.
No password is created, because none exists anywhere in TDMS.

**An address on the elevated bootstrap list** binds at its approved role instead:

| Role | Accounts |
| --- | --- |
| SUPER_ADMIN | `a.chattopadhyay@`, `w.rajjak@`, `v.yadav@`, `d.panda@` |
| ADMIN | `c.dejsakultorn@`, `n.verma@` |

The list is consulted **once**, at that first binding. Afterwards the durable
identity is `tid + oid` and the level is whatever the user record says — so a
later demotion is not silently reversed at the next sign-in, and a mailbox rename
grants nothing.

Belonging to `@chelsongordon.com` or `@vconsultancy.com.au` does not confer Data
Editor or anything above Viewer. Higher access comes from an approved access
request or a Super Admin role change.

---

## 8. Session

Confirmed inactivity timeout: **30 minutes** (`TDMS_SESSION_INACTIVITY_MINUTES`).
After that the TDMS session ends and the user re-enters the sign-in flow;
Microsoft may complete it without a prompt if their organisational session is
still valid. TDMS stores no Microsoft password and no refresh token in the
browser beyond what MSAL manages.

---

## 9. Switching it on

Once the Client ID and tenant IDs are registered:

```
# repository root .env  (git-ignored)
TDMS_AUTH_MODE=entra
ENTRA_CLIENT_ID=<application-client-id>
ENTRA_ALLOWED_TENANT_IDS=<tenant-id>[,<second-tenant-id>]
ENTRA_REDIRECT_URI=<registered redirect uri>
```

```
# apps/web/.env.local  (git-ignored)
NEXT_PUBLIC_TDMS_AUTH_MODE=entra
NEXT_PUBLIC_ENTRA_CLIENT_ID=<application-client-id>
NEXT_PUBLIC_ENTRA_ALLOWED_TENANT_IDS=<tenant-id>[,<second-tenant-id>]
NEXT_PUBLIC_ENTRA_REDIRECT_URI=<registered redirect uri>
```

Then confirm the API agrees:

```bash
curl http://localhost:8000/auth/configuration
```

`configurationError` must be `null`. If it is not, sign-in stays disabled and the
login screen shows the reason — **there is no fallback to the development
adapter**, by design. A production deployment missing this configuration fails
loudly rather than admitting everyone.

---

## 10. Remaining work after activation

The MSAL browser integration (`@azure/msal-browser`) is the last piece: the
adapter at `apps/web/src/services/auth/entra-auth-provider.ts` documents exactly
where `loginRedirect`, `acquireTokenSilent` and `logoutRedirect` connect, and the
token handoff to `GET /me` is already written. It is deliberately not installed
while there is no registration to configure it against.
