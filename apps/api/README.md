# TDMS API

FastAPI application service for the Timetable Database Management System.

The HTTP surface is still a **skeleton**, but the service now owns the approved
**Database Schema v1** — SQLAlchemy 2 models and the Alembic migration that builds
them. No endpoint reads or writes the database yet, and the frontend continues to
use `MockTdmsClient`.

## What is implemented

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Returns `{"status": "ok", "service": "tdms-api"}` |
| `GET /` | Points at `/docs` and reports the current environment |
| `GET /docs` | Interactive OpenAPI documentation |

## Database

`app/models/` holds the approved Schema v1 — 27 tables, 1 view, 15 enum types —
and `alembic/versions/` holds the migration that creates them. With the Docker
database running and the virtual environment activated:

```bash
alembic upgrade head
```

```bash
alembic current
```

```bash
alembic check
```

`alembic.ini` contains **no credentials**: `alembic/env.py` resolves the URL at
runtime from `app.core.config`, which reads the git-ignored `.env`. Never add a
password to `alembic.ini` or to any tracked file.

Full workflow: [`docs/database/migration-workflow.md`](../../docs/database/migration-workflow.md).

## Initial access seed

Pre-provisions the approved initial TDMS accounts (5 Super Admin, 1 Admin, 0 Data
Editor). Insert-only, transactional, idempotent:

```bash
python -m app.db.seeds.initial_access --dry-run
```

```bash
python -m app.db.seeds.initial_access --apply
```

Currently refuses to apply: `users.display_name` is NOT NULL and the six names
have not been supplied by the business. See
[`docs/database/initial-access-seeding.md`](../../docs/database/initial-access-seeding.md).

## What is deliberately not implemented

Student operations, timetable generation, authentication and bulk import
processing. No endpoint connects to the database, no seed data or user account has
been inserted, and the production database is not connected — DATA-07 and OD-13
require the hosting configuration to be approved first.

## Local setup

**Windows**

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**macOS / Linux**

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Deactivate the environment with `deactivate`.

The service runs on <http://localhost:8000>; the health check is at
<http://localhost:8000/health>.

`.venv/` is ignored by Git. The repository stores the dependency definition
(`requirements.txt`), never a developer's virtual environment.

## Tests

```bash
pytest -q
```

116 of these check the **live** development database against the approved schema,
so the `db` container must be running and migrations applied. They write nothing
permanent — integrity tests run inside transactions that are rolled back.

## Structure

```
apps/api/
├── app/
│   ├── main.py          # application entry point
│   ├── api/             # routers, one per SRS page
│   ├── core/            # configuration and cross-cutting concerns
│   ├── db/              # Base, naming convention, enum types, session factory
│   │   └── seeds/       # environment bootstrap data (initial TDMS accounts)
│   ├── models/          # SQLAlchemy 2 models — approved Schema v1, 27 tables
│   ├── schemas/         # Pydantic request/response schemas
│   ├── services/        # validation, permissions, timetable rules
│   └── repositories/    # data access
├── alembic/
│   ├── env.py           # resolves the database URL at runtime
│   └── versions/        # migration scripts
├── alembic.ini          # no credentials
├── tests/
├── requirements.txt
├── Dockerfile
└── .env.example
```

## Route contract

`apps/web/src/services/api-tdms-client.ts` already maps every frontend call to a
route path (`/students`, `/timetable`, `/trainers`, `/courses`,
`/qualification-units`, `/student-imports/...`, `/users`, `/activity-records`,
`/reference-data`). Implementing those paths is all the frontend needs in order
to switch from `mock` to `api`.
