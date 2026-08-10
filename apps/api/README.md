# TDMS API

FastAPI application service for the Timetable Database Management System.

At this stage the service is a **skeleton only**. It exists so the Python
environment, the repository layout and future deployment health checks are in
place before the business endpoints are written. The frontend continues to use
`MockTdmsClient`.

## What is implemented

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Returns `{"status": "ok", "service": "tdms-api"}` |
| `GET /` | Points at `/docs` and reports the current environment |
| `GET /docs` | Interactive OpenAPI documentation |

## What is deliberately not implemented

Student operations, timetable generation, authentication, bulk import
processing and any database connection. DATA-07 and OD-13 require the final
schema and hosting configuration to be approved first.

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

## Structure

```
apps/api/
├── app/
│   ├── main.py          # application entry point
│   ├── api/             # routers, one per SRS page
│   ├── core/            # configuration and cross-cutting concerns
│   ├── models/          # database models (added after schema approval)
│   ├── schemas/         # Pydantic request/response schemas
│   ├── services/        # validation, permissions, timetable rules
│   └── repositories/    # data access
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
