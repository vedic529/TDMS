# Local PostgreSQL development database

How to run, inspect and reset the TDMS development database on your own machine.

> **Development only.** This database is not staging, not production and is never connected to
> Supabase. It contains no real student, trainer or timetable data. The database name carries a
> `_dev` suffix so it is obvious at a glance which environment you are attached to.

---

## 1. Purpose

Step 2 of the database work establishes a reliable, persistent local PostgreSQL instance so that
Step 3 can implement the approved **Database Schema v1** through SQLAlchemy and Alembic.

**This database currently contains no TDMS business tables** — only PostgreSQL's own system
catalogues and default schemas. That is deliberate. Tables are created exclusively by Alembic
migrations, so that hand-written SQL and migrations never become competing sources of truth.

## 2. Architecture

```
C:\TDMS
  ├── apps/web        Next.js frontend   → still MockTdmsClient, not connected to PostgreSQL
  ├── apps/api        FastAPI service    → /health only, DATABASE_URL still blank
  └── docker compose
        └── db  →  PostgreSQL 17  →  tdms_dev  →  volume tdms_postgres_data
```

A browser never talks to PostgreSQL. The intended path stays:

```
Next.js frontend  →  FastAPI API  →  PostgreSQL
```

## 3. What is configured

| Item | Value |
| --- | --- |
| Docker image | `postgres:17-bookworm` — a pinned major version, never `postgres:latest` |
| Resolved version | **PostgreSQL 17.10** (Debian 17.10-1.pgdg12+1), verified 10 Aug 2026 |
| Compose service | `db` |
| Container name | `tdms-db` |
| Database | `tdms_dev` |
| Admin user | `postgres` (PostgreSQL bootstrap superuser) |
| Host binding | `127.0.0.1` — loopback only, never `0.0.0.0` |
| Host port | `${TDMS_POSTGRES_PORT}`, default `5432` |
| Container port | `5432` |
| Encoding | UTF8 |
| Named volume | `tdms_postgres_data` → `/var/lib/postgresql/data` |
| Health check | `pg_isready -U <user> -d <database>` |
| Restart policy | `unless-stopped` |
| Authentication | Password. `POSTGRES_HOST_AUTH_METHOD=trust` is **not** used |

`postgres:17-bookworm` pins the **major** version. Patch releases still arrive with `docker compose
pull`, but PostgreSQL will not jump to 18 on its own — a major upgrade needs a deliberate migration
of the data directory.

> **The PostgreSQL `postgres` superuser is not a TDMS access level.** Super Admin, Admin and Data
> Editor are *application* access levels stored in the `users` table (Schema v1 §5). They are never
> modelled as PostgreSQL server roles. A least-privilege application database user is introduced in
> Step 3; FastAPI must not run permanently as the superuser.

> **Before staging or production**, the PostgreSQL major version must be checked against the selected
> Supabase project (or other approved host). 17 is a local development choice, not a production
> commitment.

## 4. Secrets

The database password is **never** written into `docker-compose.yml`, a Dockerfile, Python,
TypeScript, this document, or any Git-tracked file.

| File | Contains | Tracked by Git |
| --- | --- | --- |
| `.env.example` | Variable names and a **blank** password | Yes |
| `.env` | Your real local password | **No — ignored** |

`docker-compose.yml` uses `${TDMS_POSTGRES_ADMIN_PASSWORD:?...}`, so Compose stops with a clear error
if the variable is missing instead of starting the database with a blank password.

First-time setup:

```bash
cp .env.example .env
```

Then set `TDMS_POSTGRES_ADMIN_PASSWORD` in `.env` to any local value. Confirm it is ignored:

```bash
git check-ignore -v .env
```

## 5. Everyday commands

Run all of these from `C:\TDMS`.

Start the database only:

```bash
docker compose up -d db
```

Check status and health:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs db
```

Follow logs:

```bash
docker compose logs -f db
```

Open an interactive `psql` session:

```bash
docker compose exec db psql -U postgres -d tdms_dev
```

Stop the database but keep the container:

```bash
docker compose stop db
```

Start it again:

```bash
docker compose start db
```

Restart it:

```bash
docker compose restart db
```

Stop and remove containers **while keeping the data**:

```bash
docker compose down
```

> `docker compose down` removes containers and the default network. It does **not** remove named
> volumes, so `tdms_postgres_data` and everything in `tdms_dev` survives.

## 6. Inspecting the database

Show the PostgreSQL version:

```bash
docker compose exec db psql -U postgres -d tdms_dev -c "SELECT version();"
```

Confirm which database and user you are connected as:

```bash
docker compose exec db psql -U postgres -d tdms_dev -c "SELECT current_database(), current_user;"
```

Confirm the encoding is UTF8:

```bash
docker compose exec db psql -U postgres -d tdms_dev -c "SHOW server_encoding;"
```

List databases:

```bash
docker compose exec db psql -U postgres -d tdms_dev -c "\l"
```

List schemas:

```bash
docker compose exec db psql -U postgres -d tdms_dev -c "\dn"
```

List tables — expected to be empty until Step 3 runs the first migration:

```bash
docker compose exec db psql -U postgres -d tdms_dev -c "\dt"
```

## 7. Destructive reset — read before running

```bash
docker compose down -v
```

> ⚠️ **This permanently destroys the local database volume and everything in `tdms_dev`.**
> There is no undo. Use it only when you have no development data worth keeping.

**Why you would ever need it.** PostgreSQL applies `POSTGRES_DB`, `POSTGRES_USER`,
`POSTGRES_PASSWORD` and `POSTGRES_INITDB_ARGS` **only when the data directory is first created**. If
you later change the database name, the admin user or the encoding in `.env`, an already-initialised
volume ignores the change — the old values persist and connections fail in confusing ways.

So there are two different operations, and the difference matters:

| | Command | Effect |
| --- | --- | --- |
| **Restart** | `docker compose restart db` | Container restarts. Data kept. Init variables **not** re-applied. |
| **Full reset** | `docker compose down -v` then `docker compose up -d db` | Volume destroyed and recreated. Init variables re-applied. **All data lost.** |

Changing the password alone does not need a reset — change it inside PostgreSQL instead:

```bash
docker compose exec db psql -U postgres -d tdms_dev -c "ALTER USER postgres WITH PASSWORD 'new-value';"
```

…then update `.env` to match.

## 8. Troubleshooting

### Port 5432 already in use

Something else — usually a natively installed PostgreSQL — already holds the port. **Do not kill it.**
Give TDMS a different *host* port instead; the container keeps listening on 5432 internally.

Check what holds the port:

```bash
Get-NetTCPConnection -LocalPort 5432 -ErrorAction SilentlyContinue
```

Then set a free port in `.env`:

```bash
TDMS_POSTGRES_PORT=5433
```

Recreate the container so the new mapping applies (data is preserved):

```bash
docker compose up -d --force-recreate db
```

### Docker is not running

`docker` commands fail with *"cannot connect to the Docker daemon"* or *"the term 'docker' is not
recognized"*. Start Docker Desktop and wait for the whale icon to stop animating, then:

```bash
docker info
```

### The database never becomes healthy

Check the logs first:

```bash
docker compose logs db
```

Common causes:

| Symptom in the logs | Cause |
| --- | --- |
| `TDMS_POSTGRES_ADMIN_PASSWORD is not set` | No `.env`, or the variable is blank |
| `database files are incompatible with server` | The volume was created by a different PostgreSQL major version. A major upgrade needs a dump/restore, or a destructive reset if the data is disposable |
| `role "postgres" does not exist` | `TDMS_POSTGRES_ADMIN_USER` was changed after the volume was initialised — see §7 |
| Healthcheck fails but PostgreSQL is up | `TDMS_POSTGRES_DB` was changed after initialisation, so `pg_isready` probes a database that does not exist |

Inspect the health probe directly:

```bash
docker inspect --format "{{json .State.Health}}" tdms-db
```

## 9. How development differs from staging and production

| | Local development | Staging / production |
| --- | --- | --- |
| Where | Docker on your machine | Supabase or another approved host (**OD-13, not approved**) |
| Database | `tdms_dev` | Separate, approved databases |
| Data | Empty; demo data only | Real operational data |
| Credentials | Local `.env`, disposable | Managed secrets, never in Git |
| Access | Loopback only | Approved network and security configuration |
| Schema changes | Alembic migrations, applied freely | Alembic migrations, applied under change control |

`DATA-06` requires development data to stay separate from production data and never to be presented
as live information. Nothing in this setup reaches a production system: there is no Supabase project,
no production connection string and no production credential anywhere in the repository.

## 10. Docker Desktop licensing

Docker Desktop's commercial-use terms depend on organisation size and revenue. **Its use here must
comply with the organisation's applicable Docker subscription and licensing requirements.** That is a
commercial decision for the organisation — it is recorded here as a note, not resolved in this
document, and no purchasing decision has been made.

If a Docker subscription is not appropriate, the alternatives are a natively installed PostgreSQL 17
or a different OCI runtime (Podman, Rancher Desktop). Both would require this document and
`docker-compose.yml` to be revisited.

## 11. What Step 3 does next

1. Add SQLAlchemy 2.x and Alembic to `apps/api/requirements.txt`.
2. Create the ORM models for the approved **Database Schema v1** — 27 tables, 1 view, 15 enum types.
3. Initialise Alembic and generate the first migration.
4. Apply it to `tdms_dev` and verify the tables against the approved data dictionary.
5. Create a **least-privilege application database user** so FastAPI never runs as the superuser.
6. Set `DATABASE_URL` in `apps/api/.env` and wire the FastAPI database session.

The frontend stays on `MockTdmsClient` until the API exposes real endpoints — that is a later step
again.
