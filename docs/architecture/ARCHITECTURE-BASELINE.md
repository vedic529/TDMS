# TDMS — Backend Architecture Baseline

**Generated:** Sunday, 30 August 2026, 01:37 SGT (UTC+8)
**Commit:** `27ad35c930a9daa17a577138d84f96e0f42bbdf0` (`main`)
**Purpose:** A portable, self-contained specification of this project's stack, layering and conventions, so a standalone interim application can be built to match it and later folded back in as a straight adaptation rather than a re-architecture.

---

## How to read this document

You are expected to have **no access to the TDMS repository**. Every claim below was
verified against a real file at the commit named above, and the path is cited so a
reader who *does* have the repo can check it.

- **Architecture and conventions only.** Business rules, domain meaning and data
  content are deliberately excluded — the standalone app has a different domain.
- Where two patterns genuinely coexist, both are described and the **canonical**
  one is named. Nothing has been silently harmonised.
- Anything that could not be determined is in
  [§14 Unresolved / needs my decision](#14-unresolved--needs-my-decision), not guessed.

---

## 1. Stack inventory

Every version below is read from a manifest or lockfile. **No version is inferred.**

### 1.1 Python — backend

There is **no `pyproject.toml`, no `poetry.lock`, no `uv.lock`, no `.python-version`
and no `setup.cfg`.** The single manifest is `apps/api/requirements.txt`, and every
line is `==` pinned:

| Package | Version | Note |
|---|---|---|
| `fastapi` | 0.115.6 | |
| `uvicorn[standard]` | 0.34.0 | |
| `pydantic` | 2.10.4 | |
| `python-dotenv` | 1.0.1 | |
| `SQLAlchemy` | 2.0.51 | 2.x declarative style |
| `alembic` | 1.19.1 | |
| `psycopg[binary]` | 3.3.4 | **Psycopg 3**, URL scheme `postgresql+psycopg://` |
| `pyjwt[crypto]` | 2.10.1 | |
| `pytest` | 8.3.4 | |
| `httpx` | 0.28.1 | FastAPI `TestClient` transport |
| `python-multipart` | 0.0.20 | multipart uploads |
| `openpyxl` | 3.1.5 | XLSX parsing, server-side |

**Python version** is not declared in any manifest. Three independent sources agree
on **3.12**: `apps/api/Dockerfile:7` (`FROM python:3.12-slim`), `.github/workflows/ci.yml`
(`python-version: '3.12'`), and the local virtualenv (`3.12.10`).

**There is no Python linter, formatter or type checker.** `ruff`, `black` and `mypy`
are absent from the manifest, from CI and from every config file. The only backend
gate is `pytest`.

### 1.2 Node / TypeScript — frontend

Manifest `apps/web/package.json`; resolved versions read from
`apps/web/package-lock.json` (`lockfileVersion: 3`). Ranges are carets; the
**resolved** column is what is actually installed.

| Package | Range | Resolved |
|---|---|---|
| `next` | `^15.5.0` | **15.5.23** |
| `react` / `react-dom` | `^19.0.0` | **19.2.8** |
| `typescript` | `^5.7.2` | **5.9.3** |
| `tailwindcss` / `@tailwindcss/postcss` | `^4.1.0` | **4.3.3** |
| `zod` | `^3.24.1` | **3.25.76** |
| `react-hook-form` | `^7.54.0` | **7.85.0** |
| `@hookform/resolvers` | `^3.10.0` | **3.10.0** |
| `sonner` | `^1.7.1` | **1.7.4** |
| `lucide-react` | `^0.460.0` | **0.460.0** |
| `@azure/msal-browser` | `^4.7.0` | **4.7.0** |
| `class-variance-authority` | `^0.7.1` | **0.7.1** |
| `clsx` | `^2.1.1` | **2.1.1** |
| `tailwind-merge` | `^3.0.0` | **3.6.0** |
| `date-fns` | `^4.1.0` | **4.4.0** |
| `eslint` | `^9.17.0` | **9.39.5** |
| `eslint-config-next` | `^15.5.0` | **15.5.23** |
| `@eslint/eslintrc` | `^3.2.0` | **3.3.6** |
| `@types/node` | `^22.10.0` | **22.20.1** |
| `@types/react` | `^19.0.0` | **19.2.18** |
| `@types/react-dom` | `^19.0.0` | **19.2.4** |
| `tw-animate-css` | `^1.2.5` | **1.4.0** |

Radix primitives (all `@radix-ui/react-*`), resolved:
`checkbox` 1.3.11, `dialog` 1.1.23, `dropdown-menu` 2.1.24, `label` 2.1.15,
`select` 2.3.7, `separator` 1.1.15, `slot` 1.3.3, `switch` 1.3.7, `tabs` 1.1.21,
`tooltip` 1.2.16.

**shadcn/ui is not an npm dependency.** `apps/web/components.json` records the
generator settings (`style: new-york`, `rsc: true`, `baseColor: slate`,
`cssVariables: true`, `iconLibrary: lucide`); the components are vendored into
`apps/web/src/components/ui/` and **hand-edited afterwards**. Treat that folder as
project-owned source, not regenerate-safe.

**Node version — three different values, a real inconsistency:**

| Source | Value |
|---|---|
| `.nvmrc` | `24` ← CI uses this |
| `apps/web/Dockerfile` | `node:22-alpine` ← the shipped container |
| `apps/web/package.json` `engines.node` | `>=20.0.0` (floor only) |

Canonical for a new project: **pin one version in `.nvmrc` and use the same tag in
the Dockerfile.** This repo does not, and it is a latent bug.

### 1.3 Infrastructure

`docker-compose.yml` at the repo root, no `version:` key, three services:

- **`db`** — `postgres:17-bookworm`, container `tdms-db`, `restart: unless-stopped`.
  Port bound to loopback only: `127.0.0.1:${TDMS_POSTGRES_PORT:-5432}:5432`.
  `POSTGRES_INITDB_ARGS: '--encoding=UTF8 --locale=C'`. Named volume
  `tdms_postgres_data`. Healthcheck `pg_isready`, 10s/5s/5 retries, 20s start period.
  `POSTGRES_PASSWORD` uses the `${VAR:?message}` form so Compose **hard-fails** when
  unset rather than starting an insecure database.
- **`api`** — built from `apps/api/Dockerfile`, single stage on `python:3.12-slim`,
  non-root user `tdms` (uid 1001), `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- **`web`** — 3-stage build (`deps` → `builder` → `runner`) on `node:22-alpine`,
  non-root `nextjs` (uid 1001), `output: 'standalone'`, `CMD node server.js`.

**Two infrastructure facts a new project should not copy blindly:**
1. `apps/api/Dockerfile` copies **only `app/`** — `alembic/`, `alembic.ini`, `tests/`
   and `scripts/` are excluded, so migrations *cannot* be run from inside the API
   container.
2. The compose `api` service has **no `depends_on: db` and no `DATABASE_URL`**
   (deliberate, per an in-file comment), so the composed stack's API cannot reach the
   composed database. Compose is used for the database; the API and web are run
   natively in development.

### 1.4 CI

`.github/workflows/ci.yml`, on push to `main` and all pull requests, concurrency
group per ref with `cancel-in-progress: true`. Two independent jobs:

- **Frontend** (`apps/web`): `npm ci` → `npm run lint` → `npm run typecheck` →
  `npm test` → `npm run build`.
- **Backend** (`apps/api`): `pip install -r requirements.txt` → `pytest -q`.

No deploy job. **Note:** the backend job runs without a PostgreSQL service container,
so every database-backed test *skips* in CI rather than running (see §10.3).

---

## 2. Repository layout

```
<root>/
├── .github/workflows/ci.yml
├── .nvmrc                       # Node version for CI
├── .env.example                 # docker-compose + shared vars
├── docker-compose.yml
├── apps/
│   ├── api/                     # FastAPI backend
│   │   ├── app/
│   │   │   ├── main.py          # app construction ONLY
│   │   │   ├── api/
│   │   │   │   ├── deps.py      # DI: get_db, require_* policies
│   │   │   │   └── routes/      # one module per area + __init__ registry
│   │   │   ├── auth/            # token verification, claims, identity
│   │   │   ├── core/            # config.py, rbac.py — no DB, no HTTP
│   │   │   ├── db/              # base.py (Base, mixins), enums.py, session.py
│   │   │   ├── models/          # SQLAlchemy models, one module per area
│   │   │   ├── schemas/         # Pydantic wire types — pure leaf
│   │   │   └── services/        # ALL business logic
│   │   ├── alembic/versions/    # THE migrations location
│   │   ├── scripts/             # one-off data importers/exporters
│   │   ├── tests/
│   │   ├── alembic.ini, pytest.ini, requirements.txt, Dockerfile
│   └── web/                     # Next.js frontend
│       ├── src/
│       │   ├── app/             # App Router: routes only
│       │   ├── components/ui/       # design-system primitives (vendored)
│       │   ├── components/common/   # reusable app components
│       │   ├── features/<area>/     # one folder per work area
│       │   ├── lib/             # pure logic, no React, no fetch
│       │   ├── services/        # API clients + auth adapters
│       │   ├── types/           # shared domain types (camelCase)
│       │   └── mock-data/       # demo dataset
│       ├── tests/               # *.test.mjs, node:test
│       ├── package.json, tsconfig.json, next.config.ts,
│       │   eslint.config.mjs, postcss.config.mjs, components.json
├── database/roles/              # SQL for the least-privilege runtime role
├── data/source/                 # real source files — git-ignored except README
└── docs/                        # design records, decisions, this file
```

**What must never go where:**

| Directory | Never |
|---|---|
| `apps/api/app/main.py` | business logic, route bodies, per-feature imports |
| `apps/api/app/api/routes/` | business rules, `session.commit()` outside the helper, role comparisons, audit writes |
| `apps/api/app/schemas/` | any `from app.` import — it is a leaf |
| `apps/api/app/models/` | business logic, query helpers |
| `apps/api/app/services/` | `session.commit()`, any `from app.api` import |
| `apps/api/app/core/` | database access, HTTP concerns |
| `apps/web/src/app/` | business logic, service calls — a page renders one feature component |
| `apps/web/src/lib/` | React components, `fetch` |
| `apps/web/src/mock-data/` | **never imported by a UI component** — only the mock client reads it |
| `database/migrations/`, `database/seeds/` | anything — kept empty on purpose; migrations live under `apps/api/alembic/versions/` |
| `data/source/` | anything committed — it holds real personal records and the repo is public |
| `docs/` | secrets, tenant or client identifiers |

**`.gitignore` — the deliberate exclusions worth copying:** `.env`, `.env.local`,
`.env.*.local`, `*.pem`, `secrets/`, with `!*.env.example` re-included; `data/source/*`
with only its README tracked; `*.zip` except under `docs/`; `.venv/`, `node_modules/`,
`.next/`, `*.tsbuildinfo`, `*.sqlite*`, `*.db`. Force-tracked: the lockfile, the
requirements file, every `Dockerfile`, and `docker-compose.yml`.

---

## 3. Backend layering

### 3.1 The path a request takes

```
main.py                     app construction, CORS, lifespan validation
   │
   └─ api/routes/__init__.py    aggregate router registry
        │
        └─ api/routes/<area>.py     handler: authorise → one service call → translate
             │   ├─ api/deps.py          Depends(get_db), Depends(require_*)
             │   └─ schemas/<entity>.py  request parsed, response serialised
             │
             └─ services/<area>.py       ALL business logic; flushes, never commits
                  │
                  └─ models/<area>.py    SQLAlchemy 2 declarative
                       │
                       └─ PostgreSQL
```

The transaction boundary is the **route helper**, not the service. Read §3.4.

### 3.2 Naming rules per layer

| Layer | Path | File name | Symbol names |
|---|---|---|---|
| Route | `app/api/routes/<area>.py` | plural area, snake_case (`trainers.py`, `students.py`, `reference.py`) | module-level `router` |
| Schema | `app/schemas/<entity>.py` | **singular** entity (`trainer.py`, `student.py`) | `XRead`, `XDetailRead`, `XCreate`, `XUpdate`, `XList`, `XWrite` |
| Service | `app/services/<area>.py` | plural area; a distinct pipeline gets `<area>_<concern>.py` (`trainer_import.py`) | free functions, `session` first positional |
| Model | `app/models/<area>.py` | domain area, several classes each | singular PascalCase class, plural snake_case `__tablename__` |

**Note the deliberate asymmetry:** routes and services are *plural*, schemas are
*singular*. This is consistent across the codebase and is the convention to copy.

### 3.3 Import direction — the rule

Higher may import lower. Never the reverse.

```
main  →  api/routes  →  api/deps  →  services  →  models / db / core
                     ↘  schemas (pure leaf)      ↘  core, db.enums
```

Verified by grep at the cited commit:

- `app/schemas/*.py` contains **zero** `from app.` imports. It is a leaf.
- `app/services/`, `app/models/`, `app/core/`, `app/auth/`, `app/db/` contain
  **zero** `from app.api` imports.
- `app/models/*.py` imports only `app.db.base` and `app.db.enums`.
- `app/main.py` imports only the aggregate `api_router`, `app.auth.tokens` and
  `app.core.config`.

**Example:** `app/api/routes/trainers.py` imports `app.api.deps`,
`app.schemas.trainer`, `app.services.trainers`, `app.services.trainer_import`, and
`app.models.user` (for the type annotation on the injected user only).

**One known violation.** `app/services/reference_data.py` imports
`app.schemas.reference` and takes Pydantic payloads directly. `app/services/trainers.py`
is the clean form: the route converts first and passes `data=payload.model_dump()`,
so the service depends only on dicts and can also be called from importers and
scripts that have no Pydantic object. **Canonical: the trainers form.**

**Secondary deviation.** `routes/admin.py` and `routes/allocation.py` build
`select()` statements inline in handlers instead of calling a service. These are the
exceptions; the stated rule is handler → single service call.

### 3.4 Layer responsibilities

**Route.** Authorise via a `Depends(require_*)` parameter, call exactly one service
function, translate the outcome. Every route declares `response_model` explicitly and
passes `responses=READ_RESPONSES` or `WRITE_RESPONSES` (module-level dicts documenting
403/404/409/422 for OpenAPI only).

Every module defines two or three private helpers immediately after the router:

- `_commit(session, call)` — runs the callable, `session.commit()`, translates
  refusals. Wraps **every write**.
- `_read(call)` / `_handle(call)` — no commit; translates refusals on read paths.

Both always `session.rollback()` on every exception branch, including a final bare
`except Exception: session.rollback(); raise`, and both translate
`sqlalchemy.exc.IntegrityError` → **409** with an area-specific sentence.
`IntegrityError` is caught in the route as well as the service because a
`DEFERRABLE INITIALLY DEFERRED` constraint fires at COMMIT, after the service returned.

**Route ordering is load-bearing.** Every literal path segment must be declared
*before* the parameterised `/{id}` route or the parameterised route swallows it.
This is enforced by banner comments in the source, e.g. in
`app/api/routes/trainers.py` the order is `/unit-coverage`, `/next-id`,
`/records/clear-preview`, `/records`, `/import/*`, then `""`, then `/{trainer_id}`.

**Schema.** Pure Pydantic. snake_case on the wire, no alias generator. Separate
Read/Create/Update types — an `Update` is applied with
`payload.model_dump(exclude_unset=True)` so an omitted field is not a null, while a
`Create` uses plain `model_dump()`. `model_config = ConfigDict(from_attributes=True)`
appears only where the service returns ORM objects; services that return dicts are
constructed as `XRead(**item)`.

**Service.** Owns query construction, business rules, validation, mutation, and
audit logging. Signature convention: `session` first positional, the acting user as a
keyword. **Services never commit** — verified, `grep "session.commit()" app/services/`
returns zero hits. They `session.flush()` when they need an id.

Each service declares a module-level `PAGE` constant naming the page for audit records.

**A tested performance invariant:** the service layer must not issue a query per row.
`app/services/trainers.py` states it in its module docstring and
`tests/test_trainer_api.py` pins the query counts with a
`before_cursor_execute` listener.

**Model.** SQLAlchemy 2 declarative only. No business logic, no query helpers.

### 3.5 Service error classes — two forms, one canonical

| Form | Example | Behaviour |
|---|---|---|
| **Status-carrying (canonical)** | `ReferenceDataError` in `app/services/reference_data.py` — base with `status_code = 400`, subclasses `NotFound` (404), `Duplicate` (409), `InvalidReference` (422), `InUse` (409) | The route helper reads `exc.status_code` and `exc.detail`; the exception expresses the intent once |
| Simple | `class TrainerError(ValueError)` in `app/services/trainers.py` — no status | The route helper hardcodes: 400 from `_commit`, 404 from `_read`. The meaning depends on which helper caught it |

`app/services/students.py` uses `StudentServiceError(status_code, detail)`, a
per-instance variant of the canonical form.

**Copy the status-carrying base with semantic subclasses.** A new project should not
reproduce the simple form.

---

## 4. Database & migrations

**ORM:** SQLAlchemy 2.0.51, synchronous by explicit decision (`app/db/session.py`
states the approved architecture does not call for async). Process-wide lazily
created engine with `pool_pre_ping=True`.

### 4.1 The naming convention — copy this verbatim

`app/db/base.py` — this is the single most load-bearing snippet in the schema layer,
because it decides every constraint name Alembic and PostgreSQL will use:

```python
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

Consequence: a `CheckConstraint(..., name="course_dates_ordered")` on `students`
materialises as `ck_students_course_dates_ordered`. **Never hand-write the `ck_`
prefix** — pass the bare predicate name. `%(column_0_N_name)s` is used to keep
composite names inside PostgreSQL's 63-character identifier limit.

### 4.2 Primary keys and mixins

```python
def pk_column() -> Mapped[int]:
    return mapped_column(BigInteger, primary_key=True, autoincrement=True)
```

**Business identifiers are never primary keys.** A Student ID or Trainer ID is a
separate `UNIQUE NOT NULL` column; the PK is always a surrogate bigint identity.

`TimestampMixin` — `created_at` / `updated_at`, both
`DateTime(timezone=True)`, `server_default=func.now()`, `updated_at` with
`onupdate=func.now()`. Applied only to operationally edited tables.
**`created_by` / `updated_by` are deliberately absent everywhere** — the audit table
is the single source of who did what.

`SoftDeleteMixin` — six columns: `is_deleted` (bool, NOT NULL,
`server_default="false"`), `deleted_at` (timestamptz), `deleted_by_user_id` (FK
`users.id`, RESTRICT), `delete_reason_id` (FK `reason_codes.id`, RESTRICT),
`delete_reason_detail` (text), `recovery_deadline` (date). The deadline is **stored,
not computed**, so records already deleted keep their original deadline if the policy
period changes.

The paired check constraint, verbatim:

```python
def soft_delete_check() -> CheckConstraint:
    return CheckConstraint(
        "is_deleted = false OR ("
        "deleted_at IS NOT NULL AND deleted_by_user_id IS NOT NULL "
        "AND delete_reason_id IS NOT NULL AND recovery_deadline IS NOT NULL)",
        name="soft_delete_metadata_complete",
    )
```

It is **not** added automatically — every soft-deletable model must put it in its own
`__table_args__`.

### 4.3 Model conventions

- `from __future__ import annotations` at the top of every model module.
- `Mapped[T]` / `mapped_column(...)` for every column. **Nullability is expressed
  twice and must agree**: `Mapped[X | None]` plus an explicit `nullable=True`.
  `nullable` is never left implicit, and a test compares model nullability against
  `information_schema` per table.
- FK columns are always `BigInteger` + `ForeignKey("<table>.id", ondelete=...)`.
- **`ondelete` rule:** `RESTRICT` by default for references to reference/master data;
  `CASCADE` only for true compositions where the child is meaningless without the
  parent. `SET NULL` is **forbidden** — a test enforces this with a single named
  exception.
- `__table_args__` is a tuple: constraints first, then indexes, with a dialect dict
  **last** if needed.
- `UniqueConstraint` when all columns are NOT NULL and the rule is unconditional.
  `Index(..., unique=True, postgresql_where=text(...))` — a **partial unique index** —
  in two situations: (a) soft-delete-aware uniqueness,
  `postgresql_where=text("is_deleted = false")` so a deleted row never blocks
  re-creation; (b) any nullable column in the key, because PostgreSQL treats NULLs as
  distinct and a plain constraint would let duplicates through.
- **Expression indexes** via `text(...)` where a column may hold an unresolved text
  fallback. The repo-wide normalising form is
  `upper(btrim(regexp_replace(col, '\s+', ' ', 'g')))` and it must match the Python
  normaliser exactly, or a resolution silently matches nothing.
- `CheckConstraint` names are bare snake_case predicates
  (`working_time_ordered`, `offshore_has_no_campus`).
- Relationships always use `back_populates`, never `backref`; add
  `cascade="all, delete-orphan", passive_deletes=True` where the FK is `ON DELETE CASCADE`.
- **Enums are native PostgreSQL types**, created via a helper:
  ```python
  _KW = {"create_type": True, "native_enum": True}
  def _pg_enum(*values: str, name: str) -> Enum:
      return Enum(*values, name=name, **_KW)
  ```
  The Python side is typed `str`, not a Python `Enum`. Declaration order is
  meaningful where the enum is ordered (an access ladder), so `>=` means the same in
  Python and SQL. Every enum name is appended to an `ALL_ENUM_NAMES` tuple used by the
  initial migration's downgrade. Native enums are used only for **closed, stable**
  domains; open-ended lists use lookup tables so they can change without a migration.
- **Table partitioning**, where used, is a trailing dialect dict:
  `{"postgresql_partition_by": "LIST (<column>)"}`. A partitioned table needs a
  **composite PK** including the partition key, so it uses
  `mapped_column(BigInteger, Identity(), primary_key=True)` rather than `pk_column()`,
  and children reference it with a composite `ForeignKeyConstraint`. The partitions
  themselves are created in raw SQL inside the migration.

**Registration is mandatory.** Every model module must be imported in
`app/models/__init__.py` and its table name added to the `EXPECTED_TABLES` tuple.
Alembic autogenerate compares `Base.metadata`; an unimported model silently drops its
table from the next migration.

**One inconsistency:** most tables are plural snake_case, but the newer
`allocation_*`, `reference_suggestion` and `trainer_availability` tables are singular.
**Canonical: plural snake_case.**

### 4.4 Migrations

Alembic 1.19.1. `apps/api/alembic.ini` sets `script_location = alembic` and
`prepend_sys_path = .`, and **leaves `sqlalchemy.url` deliberately blank** so no
credential sits in a tracked file. `alembic/env.py` resolves the URL in order:
`-x db_url=...` → `settings.migration_database_url` → raise.

`target_metadata = Base.metadata`, and both offline and online modes set
`compare_type=True` and `compare_server_default=True` so `alembic check` detects type
and default drift.

**The migration chain is a single linear head.** Verified across all 20 revision
files at this commit: every `down_revision` is referenced exactly once, no two files
share one, no branches. Siblings are forbidden unless intentionally merged.

File naming: `<revision_id>_<snake_case_slug>.py`, revision ids being 12 lowercase
hex characters (hand-chosen mnemonics are acceptable).

**The docstring convention is unusual and worth copying.** The top docstring is a
*design rationale essay*, not a changelog line. It must state why the change is right,
what alternative was rejected and why, the approval date, and anything deliberately
left unimplemented.

**Adding an enum value — two patterns, both in use:**

| Pattern | Mechanism | Reversible? |
|---|---|---|
| A | `ALTER TYPE t ADD VALUE IF NOT EXISTS 'X'` | **No.** PostgreSQL cannot drop a label; the downgrade leaves it with a comment saying so |
| B (canonical) | rename type → create new → cast columns → drop old | **Yes** |

The documented hard constraint on Pattern A, repeated in the source: *a new enum value
may not be **used** in the transaction that adds it*, so a migration that adds a value
must reference it nowhere else. Use **Pattern B** where a genuine downgrade matters and
the `(table, column)` pairs using the type are enumerable; Pattern A is the accepted
shortcut for a widely-used type, at the cost of a one-way downgrade.

**Alembic cannot autogenerate** and these must be hand-written, marked with a
`# MANUAL ADDITION` comment: extensions, views (dropped *before* their tables on
downgrade), enum type drops (after the tables, or the next upgrade fails), enum value
additions, and data migrations.

**Downgrade conventions.** A downgrade that silently drops data is worse than one that
refuses. When a downgrade cannot represent existing rows there are exactly two
sanctioned outcomes, both explicit and commented:
1. **Refuse** — count the offending rows and `raise RuntimeError` naming the count and
   the reason.
2. **Delete, stated up front** — `op.execute("DELETE FROM ...")` with a comment
   explaining why there is no representable alternative.

Otherwise a downgrade reverses the upgrade in exact reverse order, dropping indexes
before columns.

**Accepted drift.** `alembic check` is expected to report *No new upgrade operations
detected*. The only tolerated extra tables in the live database are `alembic_version`
and the **partition child tables**, which the schema test excludes by querying
`pg_inherits` rather than by hard-coding names.

### 4.5 How a new table is added

1. Confirm the change against the approved design record; do not resolve a design
   question inside a migration.
2. Write the model in the right domain module: subclass `Base`, add `TimestampMixin`
   if operationally edited and `SoftDeleteMixin` if an operational record, plural
   snake_case `__tablename__`, `id = pk_column()`, FK columns `BigInteger` with an
   explicit `ondelete`, every column `Mapped[T|None]` plus explicit `nullable=`.
3. `__table_args__`: `soft_delete_check()` first if the mixin is used, then named
   `CheckConstraint`s, then uniques/partial uniques, then supporting indexes; dialect
   dict last.
4. New enums into `app/db/enums.py` via `_pg_enum(...)`, name appended to
   `ALL_ENUM_NAMES`.
5. **Register** the class in `app/models/__init__.py` (`__all__` *and* the
   `EXPECTED_TABLES` tuple).
6. `alembic revision --autogenerate -m "short description"` from `apps/api`.
7. **Review the generated file line by line** — this step is explicitly not optional.
   Look for unintended drops, a rename rendered as drop+add (replace with
   `op.alter_column(..., new_column_name=...)`), a `server_default` on a new NOT NULL
   column on a populated table, and everything autogenerate cannot see.
8. Write the rationale docstring.
9. `alembic upgrade head`.
10. Prove the round trip: `alembic downgrade -1`, `alembic upgrade head`,
    `alembic check`.
11. Update the schema test's inventory and parametrised lists; run `pytest`.
12. Commit the model change and the migration **in the same commit**.

Never edit an already-applied migration, never use `Base.metadata.create_all()`
against a real database, and never `docker compose down -v`.

---

## 5. API surface conventions

**No versioning.** `include_router(api_router)` carries no prefix; there is no `/v1`
anywhere. URLs are `/{area}/...` directly off the root. Each router module owns its
own prefix and tags:

```python
router = APIRouter(prefix="/trainers", tags=["trainer data"])
```

Registration is one line per area in `app/api/routes/__init__.py` — a tuple import
plus `api_router.include_router(<area>.router)`.

- **Path style:** kebab-case for multi-word segments (`/rolling-timetable`,
  `/unit-coverage`, `/next-id`, `/records/clear-preview`); path params are snake_case
  ints (`{trainer_id}`, `{batch_id}`).
- **The collection root is `""`, not `"/"`**, so the URL carries no trailing slash.
- **Pagination:** `limit: int = Query(default=D, ge=1, le=MAX)` and
  `offset: int = Query(default=0, ge=0)`. Canonical default for a records list is
  **50, max 500**; grid-loading views use larger ceilings (up to 2000).
- **Filtering:** all optional `Query(default=None)`, snake_case, `int | None` for
  foreign keys and `str | None` for search. Where the wire name collides with a Python
  or FastAPI name, use the alias form:
  `status_filter: str | None = Query(default=None, alias="status")`.
- **List envelope:** `{items, total, limit, offset}` for anything paginated. Small
  reference tables return a **bare `list[...]`** with no envelope, because they are
  fully loaded.

**Error envelope.** There are **zero custom exception handlers** in the codebase — a
grep for `exception_handler` returns nothing. The wire format is therefore FastAPI's
stock `{"detail": "<sentence>"}` for `HTTPException`, and FastAPI's default validation
array for a 422 body failure.

The frontend contract makes one demand of this: it takes `body.detail` **only if it is
a string**, and otherwise substitutes a generic message. So **any 400/404/409/422
`detail` must be a complete, user-facing sentence** — it is shown to the user verbatim.

| Status | Used for |
|---|---|
| 200 | success with a `response_model` |
| 201 | creation (`status.HTTP_201_CREATED` is the canonical spelling) |
| 204 | delete / abandon; handler returns `None`, no `response_model` |
| 400 | a service refusal that carries no status of its own |
| 401 | authentication only, always with `WWW-Authenticate: Bearer` |
| 403 | authorisation — raised **only** by the `require_*` dependencies |
| 404 | record not found |
| 409 | duplicate or conflict — **and every caught `IntegrityError`** |
| 422 | invalid value or unresolved reference; also FastAPI's own body validation |
| 503 | authentication not configured on the server |

**Middleware:** CORS is the only middleware in the entire backend. Origins come from
a comma-split `CORS_ORIGINS` setting.

---

## 6. Auth, roles and permissions

### 6.1 Identity

Two modes, selected by `TDMS_AUTH_MODE` (default `mock`):

- **`entra`** — validates real Microsoft v2 access tokens: signature, `aud` (the API's
  own client id, *not* the SPA's), `azp` against an authorised-client list, the
  delegated scope, and a tenant allow-list.
- **`mock`** — reads a development identity header. Fenced twice: the settings object
  refuses it when `APP_ENV=production` (checked at startup *and* per request → 503),
  and every mock identity carries a reserved tenant UUID that no real token could have.

Token verification produces a **frozen `VerifiedClaims` dataclass**
(`tenant_id`, `object_id`, `username`, `display_name`, `token_reference`) so
downstream code receives already-verified values rather than a raw token dict.

**The identity key is `tenant_id + object_id`, never the mailbox.** An email address
can be reassigned; the object id cannot. The tenant is the security boundary.

### 6.2 The ladder and the capability map

`app/core/rbac.py` is the single policy module.

```python
class AccessLevel(str, Enum):   # ascending, order matches the PG enum
    VIEWER, DATA_EDITOR, ADMIN, SUPER_ADMIN
```

Capabilities are named for the **action, never the role**, and their values are
camelCase strings because they cross the wire to the frontend. The entire policy is
one dict mapping capability → minimum level. Accessors: `can(level, capability)`,
`at_least(level, minimum)`, `capabilities_for(level)` (returns the full
`{capability: bool}` map so the frontend never has to guess), and
`minimum_level_for(capability)` (used to build the 403 message).

### 6.3 Where role checks live — the hard rule

> Every access decision resolves through the rbac module. Route handlers never test
> `user.access_level == "ADMIN"` themselves — scattering that comparison across dozens
> of handlers is how one of them ends up spelled differently and quietly lets the wrong
> people in.

Two dependency **factories** in `app/api/deps.py` close over the rule and return an
injectable that raises 403 with a message built from the role labels:

```python
require_capability(capability)   # capability-based
require_level(minimum)           # level-based
```

Routes import only the **named policy constants** built from those factories, never
the factories themselves. Bind to `user` when the service needs the actor, or to `_`
when only the gate matters:

```python
_:    User = Depends(require_viewer_or_above)          # read
user: User = Depends(require_maintain_trainer_data)    # write
```

**Verified:** no handler compares `access_level` to a literal anywhere. The only two
comparison sites in the whole `app/api/` tree are inside the two factories.

Rules that cannot be expressed as a dependency — "you may not decide your own
request", "you may not change your own role", "the last super admin may not be
demoted" — live in the **service** as semantic exception subclasses, not in the route.

The frontend mirrors this policy for UI affordances only. Hiding a button is a
courtesy, not a control; the API is authoritative and both files must change together.

### 6.4 Audit logging

A single writer function, keyword-only after `session`:

```python
record_activity(session, *, user, action, page_or_function, detail,
                record_reference=None, result="COMPLETED", ...) -> UserActivityRecord
```

It adds and flushes; **it does not commit** — the caller does. Snapshot rule: the
user's reference and access level are stored *at write time* so history stays true
after a role change. The table is append-only and must never carry a password, token
or secret.

**Call sites are services only** — a grep of `app/api/` for `record_activity(` returns
zero hits. Logging accompanies the mutation, inside the service, inside the route's
transaction.

Append-only is enforced at the **database privilege level**, not by convention: the
runtime application role cannot UPDATE or DELETE the audit table. Denial records are
written in their own separate transaction, after the caller's was rolled back, wrapped
so a logging failure can never break the response.

---

## 7. Configuration & environments

### 7.1 Mechanism

`app/core/config.py` — a **frozen dataclass**, not `pydantic-settings`, exposed
through an `@lru_cache`-decorated `get_settings()`. At import it loads `apps/api/.env`
then the repo-root `.env`; because python-dotenv does not overwrite already-set keys,
**the app-local file wins** and the root file supplies shared Docker values.

Startup validation lives in the FastAPI `lifespan` handler, not at import time: it
calls `settings.auth_configuration_error()` and **raises** when the configuration is
broken *and* the environment is production, otherwise logs an error.

### 7.2 Backend settings

| Setting | Env var | Default | Purpose |
|---|---|---|---|
| `app_env` | `APP_ENV` | `development` | Drives `is_production` |
| `database_url` | `DATABASE_URL` or composed | — | Runtime URL; contains a password, never logged |
| `migration_database_url` | `DATABASE_URL` or composed from admin creds | — | Admin URL for Alembic and the test harness only |
| `auth_mode` | `TDMS_AUTH_MODE` | `mock` | `entra` \| `mock`; mock refused in production |
| `entra_client_id` | `ENTRA_CLIENT_ID` | `""` | The **API's** client id = the `aud` validated |
| `entra_authorized_client_ids` | `ENTRA_AUTHORIZED_CLIENT_IDS` | `[]` | Clients allowed to obtain a token; blank disables the check |
| `entra_allowed_tenant_ids` | `ENTRA_ALLOWED_TENANT_IDS` | `[]` | The security boundary |
| `entra_redirect_uri` | `ENTRA_REDIRECT_URI` | `""` | |
| `entra_api_scope` | `ENTRA_API_SCOPE` | `""` | Stops cross-API token replay |
| `entra_authority_host` | `ENTRA_AUTHORITY_HOST` | `https://login.microsoftonline.com` | Sovereign-cloud override |
| `session_inactivity_minutes` | `TDMS_SESSION_INACTIVITY_MINUTES` | `30` | |
| `notification_mode` | `TDMS_NOTIFICATION_MODE` | `development` | `graph` sends mail; anything else logs |
| `graph_tenant_id` / `graph_client_id` | `GRAPH_*` | `""` | |
| `graph_client_secret` | `GRAPH_CLIENT_SECRET` | `""`, **`repr=False`** | A real secret; excluded from the dataclass repr |
| `app_base_url` | `TDMS_APP_BASE_URL` | `http://localhost:3000` | Where emailed links point; not a security boundary |
| `cors_origins` | `CORS_ORIGINS` | `localhost:3000`, `127.0.0.1:3000` | Comma-split |

Database URL composition reads `TDMS_POSTGRES_HOST` (default `127.0.0.1`), `_PORT`
(5432), `_DB` (`tdms_dev`), `_ADMIN_USER` / `_ADMIN_PASSWORD`, and
`_APP_USER` / `_APP_PASSWORD`, percent-encoding credentials. The runtime URL falls
back to the admin role when the application role's password is blank.

**Two-role design worth copying:** migrations run as an admin role, the application
runs as a least-privilege role that cannot DDL and cannot mutate the audit table.
`safe_database_target` and `runtime_identity` properties exist so the configuration
can be *reported* without leaking the password.

### 7.3 Frontend settings

`apps/web/src/lib/env.ts` is the only place `process.env` is read. It validates,
applies defaults, and exposes a typed `env` object. **No secret may ever be a
`NEXT_PUBLIC_` variable.**

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_APP_NAME` | `TDMS` | Display name |
| `NEXT_PUBLIC_APP_ENV` | `development` | `development \| staging \| production` |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend base URL |
| **`NEXT_PUBLIC_TDMS_DATA_MODE`** | `mock` | **The mock-vs-live switch.** `mock` → in-browser dataset in localStorage; `api` → real backend |
| `NEXT_PUBLIC_TDMS_AUTH_MODE` | `mock` | `mock` \| `entra`. **No silent downgrade** — entra + unconfigured disables sign-in rather than falling back |
| `NEXT_PUBLIC_ENTRA_*` | `''` | Client id, allowed tenants, authority, redirect uri, api scope |
| `NEXT_PUBLIC_TDMS_DEV_TOOLS` | `true` | Dev panel; requires **all three** of development env, mock auth, and the flag |

Derived exports include `isEntraConfigured`, `authConfigurationError` (names the exact
missing variables) and `canSignIn`.

---

## 8. Frontend contract

Only what a new project must replicate.

**Framework:** Next.js 15 App Router, React 19, TypeScript `strict: true`, single path
alias `@/* → ./src/*`. `noUncheckedIndexedAccess` is explicitly **off**.

**Routing.** `src/app/` holds routes only. A page is a **server component** that
exports `metadata` and renders one feature component inside `<Suspense>`. Page
functions are named `<Area>Page`. `'use client'` goes on the *feature component*, not
the route file — verified: only 4 files under `app/` carry the directive.
An authenticated shell lives in a route group `(app)/layout.tsx`, which is a client
component that redirects to `/login` when signed out.

**Styling.** Tailwind v4 with **no `tailwind.config.*` file** — configuration is
CSS-first in `globals.css` via `@import 'tailwindcss'` and an `@theme inline { }`
block mapping `--color-*` onto raw `:root` variables declared in **oklch**. One light
theme by design. A global `:focus-visible` outline is declared once in `@layer base`.

**Component placement:**

| Folder | Holds |
|---|---|
| `components/ui/` | design-system primitives, vendored and hand-edited |
| `components/common/` | reusable app components used by more than one area |
| `features/<area>/` | everything owned by one work area |

File naming is **kebab-case** throughout; hook files are prefixed `use-`. **Named
exports only** — a repo-wide scan of `features/**` and `components/**` finds zero
`export default`. Default exports appear only in `app/**`, where Next.js requires them.

### 8.1 How the frontend talks to the backend

**Two styles coexist. The canonical one for new work is the direct-fetch module.**

- *(legacy, transitional)* A unified client interface with Mock and Api
  implementations, selected by `NEXT_PUBLIC_TDMS_DATA_MODE`. Still used by 8 files.
- *(canonical)* **"Always-real" direct-fetch modules** — one per area, e.g.
  `services/trainers-api.ts`. These **always call the backend**, do not consult the
  data-mode switch, and have no mock fallback. ~30 feature files use them.

The module headers state this explicitly; note that the repo's own README and
`docs/architecture/frontend-architecture.md` are **stale** on this point and still
describe the unified client as universal.

**The direct-fetch module template** — copy this shape:

```ts
import { env } from '@/lib/env';
import { getAuthProvider } from './auth';
import { ApiError } from './errors';

// --- Wire types: snake_case, mirroring the Pydantic schemas, hand-written ---
export interface ThingRow { id: number; some_field: string | null; }
export interface ThingList { items: ThingRow[]; total: number; limit: number; offset: number; }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has('Content-Type') && !(init?.body instanceof FormData) && init?.body) {
    headers.set('Content-Type', 'application/json');
  }
  const token = await getAuthProvider().getApiAccessToken();   // in memory only
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(`${env.apiUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = '';
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;   // string only
    } catch { /* ignore a non-JSON error body */ }
    throw new ApiError(response.status, detail || defaultMessage(response.status));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const thingsApi = {
  list: (params = {}) => request<ThingList>(`/things${query(params)}`),
  create: (payload: ThingInput) =>
    request<ThingRow>('/things', { method: 'POST', body: JSON.stringify(payload) }),
};
```

Details that matter:

- **One error class**, carrying `readonly status: number` and a
  `get isConflict()` returning `status === 409 || status === 422` — the signal to show
  the message inline next to a field rather than as a toast.
- The token is attached in exactly one place, held in memory for that call only,
  **never written to localStorage**.
- A `query()` helper skips `undefined`, `''` and `false`; repeats a key per array item
  for a FastAPI `list[int]`; and **omits an empty array entirely** (Select All = no
  restriction).
- **Uploads** build a `FormData` and pass it as `body` with no explicit Content-Type
  so the browser sets the multipart boundary. The file is parsed **server-side** — the
  browser cannot open a workbook, and one server code path handles CSV and XLSX alike.
- Binary downloads bypass `request<T>` and check `response.ok` directly.

**Wire types are hand-written, not generated.** There is no codegen step. They are
snake_case interfaces declared in the same file as the service, under a
`// Wire types` banner, with a comment naming the Pydantic module they mirror.

**Feature component consumption pattern:**

```ts
const [rows, setRows] = React.useState<Row[]>([]);
const [loading, setLoading] = React.useState(true);
const [error, setError] = React.useState<string | null>(null);

const load = React.useCallback(async () => {
  setLoading(true); setError(null);
  try { const result = await thingsApi.list({ limit: PAGE_SIZE, offset: page * PAGE_SIZE });
        setRows(result.items); setTotal(result.total); }
  catch (caught) { setRows([]);
        setError(caught instanceof Error ? caught.message : 'Things could not be loaded.'); }
  finally { setLoading(false); }
}, [page]);

React.useEffect(() => { void load(); }, [load]);
```

`import * as React` with `React.useState` (never destructured hook imports).
Server-side pagination with a module-level `PAGE_SIZE`. Tab state in the URL via
`useSearchParams` + `router.replace(..., { scroll: false })`.

Loading/empty/error states come from shared components, never ad-hoc markup.
**Toasts are for mutations only** — a load failure renders an error state, not a
toast. Toast titles are plain sentences with no exclamation marks.
`window.confirm` is never used; confirmation is a dialog component.

**Auth on the frontend.** A provider exposes `status`, `session`, `user`,
`permissions`, `signIn()`, `signOut()`. Session restore races a bounded timeout so a
hung identity iframe still reaches a decision. `permissions` is derived **once** so
every consumer sees the same answer. Components never test a role directly — they read
a capability flag, or wrap the control in a guard component whose `disable` mode keeps
the control visible with a tooltip reason, because a visible button never implies the
action is allowed.

---

## 9. Cross-cutting conventions

**Logging.** One named logger configured at startup with a single handler and
`propagate = False`. Never `print`.

**Error handling.** No custom exception handlers; errors are shaped per route by the
`_commit` / `_read` helpers. Every exception branch rolls the session back.

**Validation.** Three layers, each with a distinct job: Pydantic validates *shape* at
the boundary; the service validates *rules*; the database enforces *invariants* with
CHECK constraints and partial unique indexes. A rule that must always hold belongs in
the database, not only in Python.

**Timezone and dates.** `dt.datetime.now(dt.timezone.utc)` is the **only** wall-clock
call in the codebase — `datetime.utcnow()` appears zero times. Import style is
`import datetime as dt`, then `dt.datetime` / `dt.date` / `dt.time`. Every timestamp
column is `DateTime(timezone=True)`; calendar dates are `Date`, clock times `Time`.
Naive values read from the database are defensively treated as UTC rather than trusted.

On the frontend, **every formatter lives in one module** so screen, export and audit
record agree. Formatters are built on module-level `Intl.DateTimeFormat` constants
with an explicit `timeZone`, and **every one returns an em dash `—` for null**.

**ID generation.** Surrogate PKs are database identities. A human-facing identifier is
a separate unique column, and where one is generated it is derived from the table
itself (`MAX` over existing rows including soft-deleted ones) rather than from a
separate counter — a counter beside the rows can drift out of step with them.

**Import/script patterns.** One-off data tooling lives in `apps/api/scripts/` as
plain modules, entirely separate from the app. A bulk import that a *user* drives is a
service, not a script, and uses a three-table staging pattern:
a batch header, staged rows holding the raw values as JSON, and a row-issue table —
so nothing reaches the real tables until an explicit confirm step, and abandoning the
review leaves nothing behind.

**Code style.** TypeScript: single quotes, 2-space indent, ~110 columns, trailing
commas. **There is no Prettier config** — formatting is by convention. ESLint uses the
flat-config format extending `next/core-web-vitals` and `next/typescript`, with
`@typescript-eslint/no-unused-vars` downgraded to a warning with `^_` ignore patterns.
`next.config.ts` sets `eslint.ignoreDuringBuilds: true` because linting is its own CI
step. Python has **no style gate at all**.

**Accessibility conventions** (observable throughout, worth replicating):
`aria-expanded` + `aria-controls` on every expandable control; semantic `<table>` with
`aria-sort` on sortable columns and an `aria-label` on the table; every form control
labelled, errors with `role="alert"` and `aria-describedby`; dialogs are Radix
primitives so focus trap, Escape and focus restore come free; decorative icons carry
`aria-hidden="true"`; and **status is always text plus an icon, never colour alone**.

---

## 10. Testing & tooling

### 10.1 Commands

| Task | Command | From |
|---|---|---|
| Run API | `uvicorn app.main:app --reload` | `apps/api` |
| Run web | `npm run dev` | `apps/web` |
| Database only | `docker compose up -d db` | root |
| Backend tests | `pytest -q` | `apps/api` |
| Frontend tests | `npm test` | `apps/web` |
| Lint | `npm run lint` | `apps/web` |
| Type check | `npm run typecheck` | `apps/web` |
| Production build | `npm run build` | `apps/web` |
| Migrate | `alembic upgrade head` | `apps/api` |
| Check drift | `alembic check` | `apps/api` |
| Roll back one | `alembic downgrade -1` | `apps/api` |

There is **no Makefile and no task runner.**

### 10.2 Frameworks

- **Backend:** pytest 8.3.4. `pytest.ini` sets `testpaths = tests`, `pythonpath = .`
  and declares exactly one marker, `database`. No `addopts` — `-q` is passed on the
  command line.
- **Frontend:** the **Node built-in test runner**, `node --test "tests/**/*.test.mjs"`.
  No Jest, Vitest or Playwright.

### 10.3 The test database — the important part

Tests run against **real PostgreSQL, never SQLite**, because the schema relies on
citext, native enum ordering, partial unique indexes and CHECK constraints, none of
which SQLite has — a passing SQLite test would prove nothing.

The session-scoped fixture:
1. Skips cleanly if no database is configured *or* the server is unreachable.
2. Connects as the admin role to the maintenance database in AUTOCOMMIT.
3. `DROP DATABASE IF EXISTS ... WITH (FORCE)` then `CREATE DATABASE`.
4. **Runs the real migration chain** via a subprocess
   (`python -m alembic -x db_url=... upgrade head`) — never `create_all()`, so the
   tests exercise the same DDL production will get.
5. On failure: drops the database and fails with the stderr tail, **with the password
   scrubbed out**.
6. Teardown drops the temporary database.

A function-scoped `session` fixture truncates a hand-maintained list of tables with
`RESTART IDENTITY CASCADE` *before* each test and rolls back afterwards. A new table
written by tests must be added to that list.

**Schema conventions are machine-enforced.** A dedicated schema test asserts, among
others: the live inventory equals the expected table list (catching an unimported
model); no unexpected tables beyond `alembic_version` and partition children; per-table
column and **nullability** parity with the models; every table has a primary key;
`ON DELETE SET NULL` is forbidden; `CASCADE` only appears on an explicit allow-list;
named check and unique constraints exist; and no two indexes cover the same columns.

**Reproduce this idea.** It is the cheapest way to keep conventions true over time —
the rules stop being documentation and start being tests.

**CI caveat:** the backend job provides no PostgreSQL service, so these tests *skip*
in CI. Add a service container in a new project.

---

## 11. Extension points — adding a new domain feature

The definitive checklist, in order. This is what makes a later merge mechanical.

### Backend

| # | File | Action |
|---|---|---|
| 1 | `app/db/enums.py` | *(if needed)* add enum types via `_pg_enum(...)`; append names to `ALL_ENUM_NAMES` |
| 2 | `app/models/<area>.py` | new or extended model classes: `Base`, mixins, `pk_column()`, `__table_args__` |
| 3 | `app/models/__init__.py` | **import the module**, add to `__all__` and to `EXPECTED_TABLES` |
| 4 | `alembic/versions/<rev>_<slug>.py` | `alembic revision --autogenerate`, review by hand, write the rationale docstring |
| 5 | `app/schemas/<entity>.py` | `XRead`, `XDetailRead`, `XCreate`, `XUpdate`, `XList` (four-field envelope) |
| 6 | `app/services/<area>.py` | business logic; error class with `status_code`; `record_activity`; **no commit** |
| 7 | `app/services/<area>_import.py` | *(optional)* bulk import pipeline over the staging tables |
| 8 | `app/core/rbac.py` | *(if a new permission)* `Capability` member + `_MINIMUM_LEVEL` entry |
| 9 | `app/api/deps.py` | *(if a new permission)* `require_x = require_capability(Capability.X)` |
| 10 | `app/api/routes/<area>.py` | `router` with prefix/tags, `READ_RESPONSES`/`WRITE_RESPONSES`, `_commit`/`_read`, **literal paths before `/{id}`** |
| 11 | `app/api/routes/__init__.py` | add to the import tuple **and** add one `include_router` line |
| 12 | `tests/test_<area>_api.py` | list/detail/RBAC + **query-count** assertions |
| 13 | `tests/test_<area>_schema.py` | constraints the generic schema test cannot express |
| 14 | `tests/test_schema_v1.py` | extend the inventory and parametrised constraint lists |
| 15 | `tests/conftest.py` | add any new table to the truncate list |

### Frontend

| # | File | Action |
|---|---|---|
| 16 | `src/services/<area>-api.ts` | wire types + `request<T>` + exported `xApi` object |
| 17 | `src/lib/permissions.ts` | *(if a new permission)* mirror the capability — **change with rbac.py in the same commit** |
| 18 | `src/lib/interface-names.ts` | display names; never hard-code a label in a component |
| 19 | `src/features/<area>/<area>-work-area.tsx` | the tab/work-area shell (`?tab=` pattern if multi-tab) |
| 20 | `src/features/<area>/*.tsx` | panels, dialogs, detail side panel — kebab-case, named exports |
| 21 | `src/app/(app)/<area>/page.tsx` | server component: `metadata` + `<Suspense>` + the work area |
| 22 | `src/components/common/top-navigation.tsx` | *(if a new top-level area)* add the nav entry |

### Order of work

Enums → models → registration → migration → schemas → services → RBAC → routes →
router registry → backend tests → API client → permissions mirror → components →
route page → navigation.

---

## 12. Standalone-project blueprint

### 12.1 Skeleton

```
<standalone>/
├── .nvmrc                       # one Node version, matching your Dockerfile
├── .env.example
├── docker-compose.yml           # postgres:17-bookworm, loopback-bound, healthcheck
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── api/{deps.py,routes/{__init__.py,<area>.py}}
│   │   │   ├── auth/{claims.py,identity.py,tokens.py,mock.py}
│   │   │   ├── core/{config.py,rbac.py}
│   │   │   ├── db/{base.py,enums.py,session.py}
│   │   │   ├── models/{__init__.py,<area>.py}
│   │   │   ├── schemas/<entity>.py
│   │   │   └── services/{activity.py,<area>.py}
│   │   ├── alembic/{env.py,script.py.mako,versions/}
│   │   ├── tests/conftest.py
│   │   ├── alembic.ini, pytest.ini, requirements.txt, Dockerfile
│   └── web/
│       ├── src/{app,components/{ui,common},features,lib,services,types}/
│       ├── tests/
│       └── package.json, tsconfig.json, next.config.ts,
│           eslint.config.mjs, postcss.config.mjs, components.json
└── docs/
```

### 12.2 Starter commands

```bash
# backend
mkdir -p apps/api/app/{api/routes,auth,core,db,models,schemas,services} apps/api/tests
cd apps/api && python -m venv .venv && .venv/Scripts/activate
pip install fastapi==0.115.6 "uvicorn[standard]"==0.34.0 pydantic==2.10.4 \
  python-dotenv==1.0.1 SQLAlchemy==2.0.51 alembic==1.19.1 "psycopg[binary]"==3.3.4 \
  "pyjwt[crypto]"==2.10.1 pytest==8.3.4 httpx==0.28.1 python-multipart==0.0.20 openpyxl==3.1.5
pip freeze > requirements.txt        # then re-pin by hand to the list above
alembic init alembic                 # then blank sqlalchemy.url in alembic.ini

# frontend
npx create-next-app@15.5.23 apps/web --ts --app --eslint --tailwind --src-dir \
  --import-alias "@/*" --no-turbopack
cd apps/web && npx shadcn@latest init      # style new-york, slate, CSS variables
```

**The four files to port first, before writing any feature:**
1. `app/db/base.py` — the naming convention, `pk_column()`, both mixins,
   `soft_delete_check()`. Everything downstream depends on it.
2. `app/core/rbac.py` — the ladder, the `Capability` enum, the minimum-level dict.
3. `app/api/deps.py` — `get_db`, the two dependency factories, the named policies.
4. `apps/web/src/services/<area>-api.ts` — one direct-fetch module as the template.

### 12.3 Merge-back checklist

| Standalone path | Destination | Merge action |
|---|---|---|
| `app/models/<area>.py` | `apps/api/app/models/` | copy; add to `__init__.py` **and** `EXPECTED_TABLES` |
| `alembic/versions/*.py` | `apps/api/alembic/versions/` | **re-parent**: set the first revision's `down_revision` to TDMS's current head; the chain must stay single-headed |
| `app/schemas/<entity>.py` | `apps/api/app/schemas/` | copy as-is |
| `app/services/<area>.py` | `apps/api/app/services/` | copy; align the error class to the status-carrying form; set `PAGE` |
| `app/api/routes/<area>.py` | `apps/api/app/api/routes/` | copy; add one line to `routes/__init__.py` |
| `app/core/rbac.py` capabilities | merge into TDMS's `rbac.py` | add the members; do **not** replace the file |
| `app/api/deps.py` policies | merge into TDMS's `deps.py` | add the `require_*` constants |
| `tests/*` | `apps/api/tests/` | copy; extend the shared truncate list and the schema inventory |
| `src/services/<area>-api.ts` | `apps/web/src/services/` | copy as-is |
| `src/features/<area>/**` | `apps/web/src/features/` | copy as-is |
| `src/app/(app)/<area>/page.tsx` | `apps/web/src/app/(app)/` | copy; add the nav entry |
| `src/lib/permissions.ts` | merge | add capabilities only |
| `app/db/base.py`, `app/db/session.py`, `app/main.py`, `config.py` | **discard** | TDMS's own versions win |

**Do not port:** the standalone `docker-compose.yml`, `alembic.ini`, `requirements.txt`
or `package.json` — reconcile dependencies into TDMS's manifests instead.

---

## 13. Non-negotiables vs free choices

| MUST copy exactly | Free to decide differently |
|---|---|
| The `NAMING_CONVENTION` dict in `db/base.py` | Table and column names |
| `pk_column()` — bigint identity surrogate PK; business ids are separate unique columns | How a human-facing id is formatted |
| `SoftDeleteMixin` + `soft_delete_check()`, added explicitly per model | Which tables are soft-deletable |
| `TimestampMixin` shape; **no `created_by`/`updated_by`** | Which tables get timestamps |
| Native PG enums via `_pg_enum`, registered in `ALL_ENUM_NAMES` | The enum values |
| Layer order and import direction; `schemas` stays a leaf | Module granularity within a layer |
| **Services never commit**; the route helper is the only transaction boundary | Service function signatures |
| `_commit` / `_read` helpers on every router, with `IntegrityError` → 409 | The wording of each message |
| Literal routes declared before `/{id}` | The URL vocabulary |
| snake_case wire format; separate Read/Create/Update; `{items,total,limit,offset}` | Field names |
| `detail` must be a complete user-facing sentence | The sentences |
| RBAC: capability enum + minimum-level dict + `require_*` factories; **no `access_level` comparison in a handler** | The capability list and the ladder's rung names |
| `record_activity` keyword-only, service-side, never commits; audit append-only at DB privilege level | The action vocabulary |
| Timezone-aware UTC only; never `utcnow()` | Display formats |
| Single-head Alembic chain; rationale docstring; prove `downgrade -1 && upgrade head` | Revision id style |
| Tests on real PostgreSQL via the migration chain, never `create_all` | Test naming |
| Machine-enforced schema conventions test | Which extra rules it asserts |
| Frontend: direct-fetch module template, one error class, token in memory only | Component library and visual design |
| Named exports, kebab-case files, `'use client'` on the feature not the route | State management inside a component |
| No secret in a `NEXT_PUBLIC_` variable | Which non-secret settings are exposed |
| Status is text + icon, never colour alone | The palette |
| Pin one Node version consistently | Which version |
| Add a linter/formatter/type-checker for Python | Which ones |

---

## 14. Unresolved / needs my decision

These could not be determined from the repository, or are known defects a new project
should decide about deliberately rather than inherit.

1. **Node version.** `.nvmrc` says 24, the Dockerfile says 22, `engines` says ≥20.
   Which is authoritative?
2. **Python tooling.** There is no linter, formatter or type checker for the backend at
   all. Adopt ruff + mypy in the standalone project?
3. **Python version is undeclared** — no `pyproject.toml` or `.python-version`. Should
   the standalone project use `pyproject.toml` (and therefore `ruff`/`mypy` config)
   instead of a bare `requirements.txt`? This would be a deliberate divergence.
4. **Shared HTTP transport.** `request<T>()` exists in six near-identical copies with
   two variants. Extract one shared module in the standalone project, or keep
   duplicating for isolation?
5. **`alembic` is not in the API Docker image**, so migrations cannot run from the
   container. What is the intended production migration mechanism?
6. **The compose `api` service has no `depends_on: db` and no `DATABASE_URL`**, so the
   composed stack is not self-contained. Intentional for a new project?
7. **CI runs backend tests without PostgreSQL**, so they silently skip. Add a service
   container?
8. **`isEntraConfigured` differs between frontend and backend** — the frontend also
   requires the API scope. Which definition is correct?
9. **Two stale documents** (`README.md` §13/§21 and
   `docs/architecture/frontend-architecture.md`) still describe the unified client as
   the universal data path, contradicting the code. Should the standalone project
   document only the direct-fetch pattern?
10. **API versioning.** There is none. Introduce `/v1` in the standalone project, or
    match the current unversioned scheme for an easier merge?
11. **Auth for the standalone app.** Does it need real identity at all, or is a mock
    provider sufficient until merge-back?
12. **Multipart/staging pattern.** Does the standalone app need the three-table bulk
    import staging stack, or only simple CRUD?
