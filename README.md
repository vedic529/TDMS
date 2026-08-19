# TDMS — Timetable Database Management System

Internal web application for viewing and managing timetable information and the
approved student, trainer, college, course and unit data needed to create
reliable timetables.

This repository currently contains a **complete, interactive frontend
prototype** built against the TDMS Software Requirements Specification (SRS)
Version 1.1, plus a minimal FastAPI skeleton so the backend can be added later
without restructuring the project.

> **Demo data only.** No production student, trainer or timetable information is
> stored in this repository. Prototype changes are held in browser storage under
> keys prefixed `tdms.prototype.v1` and are never production data (DATA-06).

---

## 1. Project overview

TDMS replaces disconnected manual files with controlled pages, clear validation
and consistent permissions. The SRS defines seven approved interfaces:

| Sequence | Approved interface name |
| --- | --- |
| Entry point | Login and Authentication |
| Page 1 | Timetable View and Management |
| Page 2A | Single Student Entry |
| Page 2B | Bulk Student Import |
| Page 3 | Trainer Data |
| Page 4A | Course Data |
| Page 4B | Qualification and Unit Sequence Data |

In the application these are grouped into **four primary operational work
areas** reached from a sticky top navigation bar:

1. **Timetable View and Management**
2. **Student Data** — tabs: *Single Student Entry*, *Bulk Student Import*
3. **Trainer Data**
4. **College and Course Reference Data** — tabs: *Course Data*, *Qualification and Unit Sequence Data*

Administration and User Activity Records are reached from the account menu, not
from the primary navigation.

### Access model — v1.1 (approved 11 August 2026)

TDMS has exactly four access levels, in ascending privilege:

| Level | Role | May do |
| --- | --- | --- |
| 1 | **Viewer** | View, search, filter and download every work area. Read-only. |
| 2 | **Data Editor** | Everything a Viewer can, plus maintaining **Student Data** and **Timetables**. |
| 3 | **Admin** | All operational work, including Trainer Data and reference data. |
| 4 | **Super Admin** | Everything, plus the administration dashboard, roles and access requests. |

**Viewer is the default.** An authenticated user from an approved Microsoft
tenant is provisioned as a Viewer at their first sign-in. Anything higher comes
from an approved access request or a Super Admin role change.

The Data Editor work assignment (Student Data Officer / Timetable Officer) was
**removed** in Access Model v1.1: a Data Editor maintains both areas, so the
distinction no longer decided anything. Trainer and reference data stay
view-and-download for a Data Editor.

Only a **Super Admin** approves access requests or assigns roles — an Admin does
neither. Full detail:
[`docs/database/access-model-v1.1.md`](docs/database/access-model-v1.1.md).

---

## 2. Technology stack

**Frontend (implemented)**

- Next.js 15 (App Router) · React 19 · TypeScript (strict)
- Tailwind CSS v4 · shadcn/ui-style components · Lucide icons
- React Hook Form · Zod
- Sonner for toast notifications

**Backend (skeleton only)**

- FastAPI · Uvicorn · Pydantic · python-dotenv

**Planned**

- PostgreSQL, hosted on Supabase after schema approval
- Microsoft Entra ID single sign-on
- Cloudflare hosting for the frontend

---

## 3. Repository structure

```
tdms/
├── apps/
│   ├── web/                       # Next.js frontend
│   │   ├── src/
│   │   │   ├── app/               # App Router routes
│   │   │   │   ├── login/
│   │   │   │   └── (app)/         # authenticated shell: timetable, students,
│   │   │   │                      # trainers, reference-data, administration
│   │   │   ├── components/
│   │   │   │   ├── ui/            # design-system primitives
│   │   │   │   └── common/        # TopNavigation, DataTable, dialogs, states…
│   │   │   ├── features/          # one folder per work area
│   │   │   ├── lib/               # permissions, env, formatting, export, rules
│   │   │   ├── services/          # TdmsClient + Mock/Api implementations, auth
│   │   │   ├── types/             # SRS data types
│   │   │   └── mock-data/         # seeded demo dataset
│   │   ├── tests/
│   │   ├── public/
│   │   ├── package.json
│   │   ├── package-lock.json
│   │   ├── next.config.ts
│   │   ├── Dockerfile
│   │   └── .env.example
│   │
│   └── api/                       # FastAPI skeleton
│       ├── app/
│       │   ├── main.py
│       │   ├── db/                # Base, naming convention, enums, session
│       │   ├── models/            # SQLAlchemy 2 models — Schema v1, 27 tables
│       │   ├── api/  core/  schemas/  services/  repositories/
│       ├── alembic/               # migration environment
│       │   └── versions/          # migration scripts (in Git)
│       ├── alembic.ini            # no credentials — URL resolved at runtime
│       ├── tests/
│       ├── requirements.txt
│       ├── Dockerfile
│       └── .env.example
│
├── database/                      # reserved for seeds; migrations live in apps/api/alembic/versions
├── docs/architecture/
├── docs/database/                 # approved schema design + implementation record
├── docs/auth/                     # Microsoft Entra configuration checklist
├── .github/workflows/ci.yml
├── docker-compose.yml
├── .nvmrc
├── .env.example
└── README.md
```

---

## 4. Required Node version

Node **22 or later** (`.nvmrc` pins 24; `package.json` requires `>=20`).

```bash
nvm use
```

## 5. Required Python version

Python **3.12** or later.

---

## 6. Frontend setup

```bash
cd apps/web
npm install
npm run dev
```

Open <http://localhost:3000>. You will land on the sign-in screen.

For a clean, reproducible install (CI and deployment):

```bash
npm ci
```

`package-lock.json` is committed. `node_modules/` is ignored.

---

## 7. Python virtual environment setup

**Windows**

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**macOS / Linux**

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.venv/` is ignored by Git — the repository stores the dependency definition,
not a developer's environment.

---

## 8. Backend setup

```bash
cd apps/api
uvicorn app.main:app --reload
```

Open <http://localhost:8000/health> — it returns:

```json
{ "status": "ok", "service": "tdms-api" }
```

Interactive documentation is at <http://localhost:8000/docs>.

---

## 9. Activating and deactivating the virtual environment

| Action | Windows | macOS / Linux |
| --- | --- | --- |
| Create | `python -m venv .venv` | `python3 -m venv .venv` |
| Activate | `.venv\Scripts\activate` | `source .venv/bin/activate` |
| Deactivate | `deactivate` | `deactivate` |

---

## 10. Environment variables

Copy the example files and edit locally. Real `.env` files are ignored by Git.

```bash
cp apps/web/.env.example apps/web/.env.local
cp apps/api/.env.example apps/api/.env
```

**Frontend (`apps/web/.env.local`)**

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_APP_NAME` | Display name |
| `NEXT_PUBLIC_APP_ENV` | `development` \| `staging` \| `production` |
| `NEXT_PUBLIC_API_URL` | Base URL of the TDMS API |
| `NEXT_PUBLIC_TDMS_DATA_MODE` | `mock` → `MockTdmsClient`, `api` → `ApiTdmsClient` |
| `NEXT_PUBLIC_TDMS_AUTH_MODE` | `mock` → `MockAuthProvider`, `entra` → `MicrosoftEntraAuthProvider` |
| `NEXT_PUBLIC_ENTRA_CLIENT_ID` | Supplied after OD-01 is approved |
| `NEXT_PUBLIC_ENTRA_TENANT_ID` | Supplied after OD-01 is approved |
| `NEXT_PUBLIC_ENTRA_REDIRECT_URI` | Approved redirect address |
| `NEXT_PUBLIC_TDMS_DEV_TOOLS` | Development access preview; must be `false` outside development |

**Backend (`apps/api/.env`)**

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `development` \| `staging` \| `production` |
| `DATABASE_URL` | Left blank until DATA-07 / OD-13 are approved |
| `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID` | Supplied after OD-01 is approved |
| `CORS_ORIGINS` | Browser origins allowed to call the API |

> A Microsoft **client secret** never belongs in a `NEXT_PUBLIC_` variable —
> every `NEXT_PUBLIC_` value is embedded in the browser bundle.

---

## 11. Mock authentication

TDMS offers exactly one authentication action:

```
[ Microsoft logo ] Sign in with Microsoft
```

There is no email/password form, no "forgot password" and no social sign-in.
The application never asks for, receives or stores a Microsoft password
(AUTH-03).

Authentication goes through an adapter:

```
AuthProvider
   ├── MockAuthProvider               (development, no Microsoft call)
   └── MicrosoftEntraAuthProvider     (production, MSAL — wired after OD-01)
```

While `NEXT_PUBLIC_ENTRA_CLIENT_ID` / `NEXT_PUBLIC_ENTRA_TENANT_ID` are empty,
`env.authMode` falls back to `mock`, the same button creates a demo session, and
the sign-in screen states that the tenant is not configured.

The Microsoft sign-in result and the TDMS access decision are stored separately
(SRS 4.2). An account with status `INACTIVE` or `DISABLED` is denied even after a
successful sign-in (AUTH-05) — the seeded users include one of each so this can
be demonstrated.

After a granted sign-in the user lands on **Timetable View and Management**
(AUTH-07).

---

## 12. Development role simulation

Because Microsoft Entra ID is not connected, a **development-only** access
preview is available. It is *not* a production authentication mechanism and does
not appear in the normal interface.

- Enabled only when `NEXT_PUBLIC_APP_ENV=development`, `NEXT_PUBLIC_TDMS_AUTH_MODE=mock`
  **and** `NEXT_PUBLIC_TDMS_DEV_TOOLS=true`. It disappears the moment real
  Microsoft sign-in is switched on.
- Opened from a discreet **Dev tools** button in the bottom-right corner.
- Lets you preview all four access levels — Viewer · Data Editor · Admin ·
  Super Admin — plus the Inactive and Disabled account states.
- Also offers **Reset demo data**, which restores the seeded dataset.

Users can never choose their own role in the application itself. The role badge
in the account area is display-only.

---

## 13. Mock data

The seeded dataset lives in `apps/web/src/mock-data/` and covers colleges,
campuses, qualification offerings, qualification/unit sequences, courses,
facilities, trainers, students, timetable sessions, TDMS users and user activity
records. Values follow the codes visible in the existing TDMS prototype
(AIBT Global, BSB/SIT/CHC/AUR/FBP qualifications) so the interface can be
reviewed against familiar data.

Mock data is **never imported by a UI component**. Pages read through
`TdmsClient`:

```
UI components
      │
      ▼
TdmsClient (interface)
      ├── MockTdmsClient   (prototype dataset in browser storage)
      └── ApiTdmsClient    (future FastAPI service)
```

Demo changes persist across a page refresh in `localStorage` under
`tdms.prototype.v1.*`. Only the service layer touches that storage, so removing
it later changes nothing in the pages.

---

## 14. Running the frontend only

```bash
cd apps/web
npm install
npm run dev          # http://localhost:3000
```

Docker is not required for frontend work.

## 15. Running the backend only

```bash
cd apps/api
source .venv/bin/activate      # or .venv\Scripts\activate on Windows
uvicorn app.main:app --reload  # http://localhost:8000
```

## 16. Running both services

Two terminals, or:

```bash
docker compose up --build
```

| Service | URL |
| --- | --- |
| Frontend | <http://localhost:3000> |
| Backend | <http://localhost:8000> |
| Backend health | <http://localhost:8000/health> |

---

## 16a. Local PostgreSQL development database

Database Schema v1 was approved on 10 August 2026 and is now implemented as SQLAlchemy 2 models plus
an Alembic migration. A local PostgreSQL 17 instance runs in Docker for development. Every structural
change reaches the database through a migration in Git — never through `psql`, a GUI, or
`create_all()`.

First-time setup — copy the example environment file and set a local password:

```bash
cp .env.example .env
```

Start the database only:

```bash
docker compose up -d db
```

Check it is healthy:

```bash
docker compose ps
```

Open a psql session:

```bash
docker compose exec db psql -U postgres -d tdms_dev
```

Stop it, keeping the data:

```bash
docker compose down
```

| | |
| --- | --- |
| Image | `postgres:17-bookworm` (pinned major version) |
| Database | `tdms_dev` |
| Address | `127.0.0.1:5432` — loopback only |
| Volume | `tdms_postgres_data` (survives `docker compose down`) |

> `docker compose down -v` **destroys the database volume.** Full command reference, reset procedure
> and troubleshooting: [`docs/database/local-postgresql-development.md`](docs/database/local-postgresql-development.md).

Development only — no Supabase, no production connection, no real student data. Docker Desktop use
must comply with the organisation's applicable Docker subscription and licensing requirements.

---

## 16b. Applying database migrations

The database must be running (§16a) and the Python virtual environment **must be activated** — the
`alembic` command lives inside it.

```powershell
cd C:\TDMS\apps\api
.\.venv\Scripts\Activate.ps1
```

Apply every outstanding migration:

```bash
alembic upgrade head
```

Check which revision the database is on:

```bash
alembic current
```

Confirm the database matches the models — this must report *No new upgrade operations detected*:

```bash
alembic check
```

Run the backend tests, which verify the live schema against the approved design:

```bash
pytest -q
```

Undo the most recent migration:

```bash
alembic downgrade -1
```

After a successful `alembic upgrade head` the development database holds **28 tables, 1 view and 15
enum types**, at revision `0e8b41dd1b13` (Schema v1, plus the Access Model v1.1 and Student Rules
v1.1 amendments).

FastAPI connects as the least-privilege role **`tdms_app`**, which cannot alter the schema and cannot
UPDATE or DELETE user activity records (LOG-05 by privilege, not by convention). Migrations keep
using the administrator credentials. To create the role on a new machine, see
[`database/roles/create-application-role.sql`](database/roles/create-application-role.sql).

No user accounts exist yet — sign-in still runs entirely on the frontend mock provider.

> The connection string is resolved at runtime from `.env`; `alembic.ini` contains no credentials and
> none may ever be added to it. Creating or reviewing migrations:
> [`docs/database/migration-workflow.md`](docs/database/migration-workflow.md). What was built and how
> it was verified: [`docs/database/schema-v1-implementation.md`](docs/database/schema-v1-implementation.md).

---

## 16c. Initial development access seed

Pre-provisions the approved initial TDMS accounts — **5 Super Admin, 1 Admin, 0 Data Editor**. It
inserts only; it never updates an existing account. Requires the activated virtual environment
(§16b).

Report what would happen, changing nothing:

```bash
python -m app.db.seeds.initial_access --dry-run
```

Insert the missing approved accounts, in one transaction:

```bash
python -m app.db.seeds.initial_access --apply
```

Safe to run more than once. A domain suffix grants nothing — every Data Editor needs an individually
approved account and one approved work assignment, and none have been approved yet.

> **Not yet applied.** `users.display_name` is NOT NULL in Schema v1 and the six people's names have
> not been supplied. The seed refuses rather than deriving a name from an email address. Details and
> how to unblock: [`docs/database/initial-access-seeding.md`](docs/database/initial-access-seeding.md).

## 17. Docker setup

- `apps/web/Dockerfile` — multi-stage build (dependencies → build → runtime)
  producing a Next.js `standalone` server image that runs as a non-root user.
- `apps/api/Dockerfile` — official Python base image, installs from
  `requirements.txt`, never copies a local `.venv`, runs as a non-root user.
- `docker-compose.yml` — runs both services.

No production database container is defined: the final database architecture is
still an open decision (OD-13).

---

## 18. Testing

```bash
# Frontend
cd apps/web
npm run lint
npm run typecheck
npm test

# Backend — activate the virtual environment first
cd apps/api
pytest -q
```

The backend suite includes 116 schema tests that check the **live** development database against the
approved Schema v1. They need the `db` container running and migrations applied (§16a, §16b);
without a database those tests fail rather than silently pass. They write nothing permanent — every
integrity test runs inside a transaction that is rolled back.

---

## 19. Production build commands

```bash
cd apps/web
npm ci
npm run build
npm run start
```

The production build must succeed before a change is considered complete — a
change that only works under `npm run dev` is not done.

---

## 20. Microsoft Entra sign-in

**Implemented. Live activation is blocked on IT configuration** — the
Application (Client) ID has not been supplied yet, so `TDMS_AUTH_MODE` stays
`mock` and sign-in uses the development adapter.

How it works once configured:

```
Microsoft Entra
      |  verified access token
      v
FastAPI validates: signature (tenant JWKS) -> audience -> issuer
                   -> expiry -> tenant allow-list -> usable oid
      |
      v
tid + oid  ->  TDMS user record  ->  access level  ->  granted or denied
```

- **The tenant is the security boundary, not the email domain.** Anybody can
  create a lookalike mailbox in a tenant they control; the `tid` claim is signed
  by Microsoft and cannot be chosen by the user. Personal Microsoft accounts are
  refused outright.
- **`tid + oid` is the durable identity.** A mailbox rename updates the profile
  and nothing else — it cannot promote anyone or create a second account.
- **First sign-in provisions a Viewer.** Six approved addresses bind at an
  elevated role instead, and that list is consulted exactly once.
- **No password, token or secret is ever stored by TDMS.**

### Development mode

`TDMS_AUTH_MODE=mock` uses the development adapter, which never contacts
Microsoft. It is refused when `APP_ENV=production`, and setting
`TDMS_AUTH_MODE=entra` without the configuration **disables sign-in with a clear
message** rather than falling back — a production deployment missing its
configuration must fail loudly, not quietly admit everyone.

What IT still needs to supply, and what each value does:
[`docs/auth/microsoft-entra-setup.md`](docs/auth/microsoft-entra-setup.md).

### Remaining work

Add `@azure/msal-browser` and complete
`apps/web/src/services/auth/entra-auth-provider.ts`. That file documents exactly
where `loginRedirect`, `acquireTokenSilent` and `logoutRedirect` connect; the
token handoff to `GET /me` is already written. No page component changes:
everything goes through `getAuthProvider()`.

## 21. Future FastAPI, Supabase and PostgreSQL integration

1. Approve the schema (DATA-07 / OD-13) and add migrations under `database/`.
2. Implement the routers listed in `apps/api/app/api/`. The paths are already
   fixed by `apps/web/src/services/api-tdms-client.ts`.
3. Set `DATABASE_URL` in the API environment — never in the frontend.
4. Set `NEXT_PUBLIC_TDMS_DATA_MODE=api` and `NEXT_PUBLIC_API_URL`.

No page component changes: everything goes through `getTdmsClient()`.

## 22. Future deployment architecture

```
User browser
     │
     ▼
Cloudflare — Next.js frontend
     │  HTTPS API calls
     ▼
FastAPI backend
     │
     ▼
PostgreSQL / Supabase

Authentication:  User → Microsoft Entra ID → TDMS → internal role/access check
```

The frontend avoids provider-specific features, keeps the API base URL and the
Microsoft configuration external, and keeps the frontend and backend separate, so
a Cloudflare deployment (via the current supported Next.js approach) needs no
redesign.

---

## Open SRS decisions

Section 12 of the SRS lists thirteen unresolved decisions. **TDMS does not invent
a rule for any of them.** Where an unresolved rule would apply, the interface
shows an "Awaiting approval" notice naming the decision, and the matching
validation check is displayed without producing a pass or fail result.

A supplied fact may resolve *part* of a decision. Those are shown as
**Partially resolved · awaiting remaining approval**, never as approved. The
working register — what has been confirmed and what is still outstanding for
each decision — is in the application under **Administration → Open decisions**
and in `apps/web/src/lib/open-decisions.ts`.

### Approved

| Decision | Approved rule, as implemented |
| --- | --- |
| OD-08 Student calculations | CT means **Credit Transfer**, and CT Student is a flag only — TDMS stores no transferred units, count or CT reference. Course duration for a CT student is a staff-selected approved Course Duration Option; TDMS derives no reduction. Course Duration Option is always shown and is validated against the approved options for the offering. Actual Course Duration uses **inclusive** dates: `(end − start + 1 day) ÷ 7`. |

### Currently partially resolved

| Decision | Confirmed | Still outstanding |
| --- | --- | --- |
| OD-01 Entra configuration and TDMS access | Super Admin and Admin rosters; the two Data Editor domains. **Access model:** the domains mark eligibility only — every account must still be approved in TDMS. **Work assignment:** manually selected by an Admin or Super Admin, never inferred. | Tenant, app registration, redirect addresses and production support owner |
| OD-03 Session timeout | 30-minute inactivity timeout — **implemented and enforced** | Whether a maximum session duration also applies |
| OD-11 MSCRIS | Additional classes, particularly for specific topics. Spelling stays **MSCRIS**. Virtual only. Class Name is fixed to "Virtual Classroom". Trainer is free text. Excluded from all clash checking. | The exact condition that makes an MSCRIS class mandatory — until supplied, the section is optional and never blocks a save |

> **MSCRIS trade-off, recorded deliberately.** A free-text MSCRIS Trainer combined with exclusion from clash checking means TDMS **cannot** detect a trainer booked for both an MSCRIS class and a normal class, and it does not satisfy DATA-02 for that field. Implemented as approved; the preview panel warns the user to check MSCRIS manually.

**Access is never granted by email domain.** The supplied organisation domains are
recorded for reference only. TDMS grants access solely when the authenticated
identity matches an approved internal user record with a role and, for a Data
Editor, a work assignment (AUTH-04, ACC-05).

### Still fully open

| Decision | Effect in the interface |
| --- | --- |
| OD-05 Admin role boundary | Admin authority over other Admin/Super Admin accounts is gated by an explicit delegation flag |
| OD-06 Delete and override reasons | The reason list is labelled as the SRS *proposed* list |
| OD-07 Break rules | The break check appears in every timetable validation panel as "Awaiting approval" |
| OD-09 Facility data | Facilities support selection, capacity and clash checks only; no fifth navigation page is created |
| OD-10 Trainer delivery rule | Physical-to-virtual availability is not derived |

OD-02, OD-04, OD-12 and OD-13 are backend, retention and hosting decisions and
do not change the current interface.

---

## Documentation

- [`docs/architecture/frontend-architecture.md`](docs/architecture/frontend-architecture.md)
- [`docs/architecture/srs-traceability.md`](docs/architecture/srs-traceability.md)
- [`apps/api/README.md`](apps/api/README.md)
- [`database/README.md`](database/README.md)

Database — approved Schema v1 and its implementation:

- [`docs/database/schema-v1-proposal.md`](docs/database/schema-v1-proposal.md) — the approved design
- [`docs/database/schema-v1-data-dictionary.md`](docs/database/schema-v1-data-dictionary.md) — authority for every column
- [`docs/database/schema-v1-relationships.md`](docs/database/schema-v1-relationships.md)
- [`docs/database/schema-v1-erd.md`](docs/database/schema-v1-erd.md)
- [`docs/database/schema-open-questions.md`](docs/database/schema-open-questions.md) — DBQ-01…15, all answered
- [`docs/database/database-requirements-review.md`](docs/database/database-requirements-review.md) — requirements-to-data matrix
- [`docs/database/local-postgresql-development.md`](docs/database/local-postgresql-development.md) — the Docker database
- [`docs/database/schema-v1-implementation.md`](docs/database/schema-v1-implementation.md) — what was built and how it was verified
- [`docs/database/migration-workflow.md`](docs/database/migration-workflow.md) — how to change the schema
- [`docs/database/access-model-v1.1.md`](docs/database/access-model-v1.1.md) — the approved access amendment
- [`docs/database/student-rules-v1.1.md`](docs/database/student-rules-v1.1.md) — approved Intake and Group rules
- [`docs/auth/tdms-authentication-status.md`](docs/auth/tdms-authentication-status.md) — Microsoft configuration status
- [`docs/database/initial-access-seeding.md`](docs/database/initial-access-seeding.md) — the elevated bootstrap list
- [`docs/auth/microsoft-entra-setup.md`](docs/auth/microsoft-entra-setup.md) — what IT must supply for live SSO
