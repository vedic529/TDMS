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

### Access model

TDMS has exactly three hierarchy levels (ACC-01):

| Level | Role |
| --- | --- |
| 1 | Super Admin |
| 2 | Admin |
| 3 | Data Editor |

**Student Data Officer** and **Timetable Officer** are Data Editor *work
assignments*, not roles (ACC-02). They never appear in a role selection control.
A Data Editor can view and download every operational page; only create, edit
and delete are limited to the assigned work area.

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
│       │   ├── api/  core/  models/  schemas/  services/  repositories/
│       ├── tests/
│       ├── requirements.txt
│       ├── Dockerfile
│       └── .env.example
│
├── database/                      # migrations, seeds (empty until approval)
├── docs/architecture/
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

- Enabled only when `NEXT_PUBLIC_APP_ENV=development` **and**
  `NEXT_PUBLIC_TDMS_DEV_TOOLS=true`.
- Opened from a discreet **Dev tools** button in the bottom-right corner.
- Lets you preview: Super Admin · Admin · Data Editor / Student Data Officer ·
  Data Editor / Timetable Officer, plus the Inactive and Disabled account states.
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

# Backend
cd apps/api
pytest -q
```

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

## 20. Future Microsoft Entra integration

1. Approve OD-01: tenant, app registration, redirect addresses, permitted users,
   role mapping and production support owner.
2. Add `@azure/msal-browser` and complete
   `apps/web/src/services/auth/entra-auth-provider.ts`. The flow is documented in
   that file and follows SRS 4.1.
3. Set `NEXT_PUBLIC_ENTRA_CLIENT_ID`, `NEXT_PUBLIC_ENTRA_TENANT_ID`,
   `NEXT_PUBLIC_ENTRA_REDIRECT_URI` and `NEXT_PUBLIC_TDMS_AUTH_MODE=entra`.
4. Match the verified account to one internal TDMS user record and apply the
   access level and work assignment (AUTH-04).
5. Retain the correlation ID for authorised investigation (AUTH-11).

No page component changes: everything goes through `getAuthProvider()`.

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
validation check is displayed without producing a pass or fail result. The full
register is available in the application under **Administration → Open
decisions**, and in `apps/web/src/lib/open-decisions.ts`.

Most visible examples:

| Decision | Effect in the interface |
| --- | --- |
| OD-03 Session timeout | No session timeout is applied; stated in Account information |
| OD-05 Admin role boundary | Admin authority over other Admin/Super Admin accounts is gated by an explicit delegation flag |
| OD-06 Delete and override reasons | The reason list is labelled as the SRS *proposed* list |
| OD-07 Break rules | The break check appears in every timetable validation panel as "Awaiting approval" |
| OD-08 Student calculations | Actual Course Duration, the Course Duration Option display rule and the CT definition are marked provisional |
| OD-09 Facility data | Facilities support selection, capacity and clash checks only; no fifth navigation page is created |
| OD-10 Trainer delivery rule | Physical-to-virtual availability is not derived |
| OD-11 MSCRIS | Fields are captured and displayed; no MSCRIS business rule is applied |

---

## Documentation

- [`docs/architecture/frontend-architecture.md`](docs/architecture/frontend-architecture.md)
- [`docs/architecture/srs-traceability.md`](docs/architecture/srs-traceability.md)
- [`apps/api/README.md`](apps/api/README.md)
- [`database/README.md`](database/README.md)
