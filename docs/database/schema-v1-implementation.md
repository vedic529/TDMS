# TDMS Database Schema v1 — Implementation Record (STEP 3)

**Status:** Implemented and verified against the local development database.
**Date:** 10 August 2026
**Source of truth:** the APPROVED Schema v1 documents in this folder. Nothing in this
record introduces, removes or reinterprets a design decision; it records how the
approved design was expressed in code.

| Item | Value |
| --- | --- |
| ORM | SQLAlchemy 2.0.51 (2.0 declarative style) |
| Migrations | Alembic 1.19.1 |
| Driver | Psycopg 3.3.4 (`postgresql+psycopg://`) |
| Database | PostgreSQL 17.10 (Docker service `db`, database `tdms_dev`) |
| Initial revision | `6266b57ea53e` — *initial tdms schema v1* |
| Business tables | 27 |
| Views | 1 (`trainer_availability_days`) |
| Enum types | 15 |
| Constraints created | 28 PK · 54 FK · 24 UNIQUE · 17 CHECK |
| Indexes | 66 |
| Extensions | `citext` |

---

## 1. What was built

### 1.1 Layout

```
apps/api/
├── alembic.ini                     # sqlalchemy.url deliberately EMPTY
├── alembic/
│   ├── env.py                      # resolves the URL at runtime; -x db_url override
│   ├── script.py.mako
│   └── versions/
│       └── 6266b57ea53e_initial_tdms_schema_v1.py
├── app/
│   ├── core/config.py              # composes the URL from TDMS_POSTGRES_* / DATABASE_URL
│   ├── db/
│   │   ├── base.py                 # Base, naming convention, mixins, helpers
│   │   ├── enums.py                # the 15 native PostgreSQL enum types
│   │   └── session.py              # engine + session factory
│   └── models/                     # 11 modules, 27 tables
└── tests/test_schema_v1.py         # 116 tests
```

### 1.2 Model modules → approved tables

| Module | Tables |
| --- | --- |
| `user.py` | `users` |
| `reason.py` | `reason_codes`, `reason_code_contexts` |
| `activity.py` | `user_activity_records` |
| `college.py` | `colleges`, `campuses`, `college_campuses` |
| `qualification.py` | `qualifications`, `units`, `qualification_units` |
| `course.py` | `course_statuses`, `course_offerings`, `offering_duration_options` |
| `facility.py` | `facilities` |
| `student.py` | `student_groups`, `students` |
| `trainer.py` | `trainers`, `trainer_availability`, `trainer_qualifications`, `trainer_units` |
| `timetable.py` | `timetable_plans`, `timetable_unit_deliveries`, `timetable_sessions`, `timetable_clash_overrides` |
| `import_batch.py` | `import_batches`, `import_staged_rows`, `import_row_issues` |

`app/models/__init__.py` imports every module and publishes `EXPECTED_TABLES` (27)
and `EXPECTED_VIEWS` (1). **Any new model module must be imported there.** Alembic
compares `Base.metadata` against the database; a module that is never imported is
invisible to autogeneration, and its table would silently vanish from the next
migration.

---

## 2. Conventions

### 2.1 Constraint naming

`app/db/base.py` installs a `MetaData` naming convention so every constraint has a
deterministic, readable name in both the model and the database:

| Kind | Pattern | Example |
| --- | --- | --- |
| Primary key | `pk_%(table_name)s` | `pk_students` |
| Foreign key | `fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s` | `fk_students_campus_id_campuses` |
| Unique | `uq_%(table_name)s_%(column_0_N_name)s` | `uq_users_organisation_email` |
| Check | `ck_%(table_name)s_%(constraint_name)s` | `ck_users_assignment_only_for_data_editor` |
| Index | `ix_%(table_name)s_%(column_0_N_name)s` | `ix_students_college_id` |

Without this, PostgreSQL invents names, and a later `alembic downgrade` cannot
reliably find the constraint it needs to drop.

### 2.2 Primary keys

`pk_column()` produces a `BigInteger` identity primary key. `college_campuses`,
`qualification_units`, `trainer_qualifications` and `trainer_units` are junctions
with **composite** primary keys instead, as approved.

### 2.3 Soft delete

`SoftDeleteMixin` supplies the approved column group — `is_deleted`, `deleted_at`,
`deleted_by_user_id`, `delete_reason_id`, `delete_reason_detail`,
`recovery_deadline` — and `soft_delete_check()` supplies the CHECK constraint that
makes the group internally consistent (a deleted row must carry a timestamp, an
actor and a reason; a live row must carry none of them). This is what stops a
delete from being recorded without an approved reason (DATA-03).

Uniqueness that must ignore soft-deleted rows uses **partial** indexes
(`postgresql_where=text("is_deleted = false")`), so recycling a student reference
after a recovery period does not collide with the deleted row.

### 2.4 Enum types

The 15 approved enums are native PostgreSQL types, declared once in
`app/db/enums.py` and reused. `access_level` is declared in **ascending privilege
order** (`DATA_EDITOR`, `ADMIN`, `SUPER_ADMIN`) so a future comparison in SQL sorts
correctly. Open-ended domains (course status, reason codes) remain lookup tables,
exactly as the proposal specifies.

---

## 3. The three manual additions to the initial migration

Autogeneration produced the tables, but three things it cannot produce were added
by hand and are commented in place in
`alembic/versions/6266b57ea53e_initial_tdms_schema_v1.py`:

**1. `CREATE EXTENSION IF NOT EXISTS citext`** — Alembic does not emit extensions.
`users.organisation_email`, `students.college_email` and `students.personal_email`
are `citext`, so without the extension `CREATE TABLE` fails outright.
Case-insensitive uniqueness is what stops `A.Person@…` and `a.person@…` becoming
two accounts (AUTH-04).

**2. The `trainer_availability_days` view** — Alembic does not handle views. DBQ-11
approved five weekday columns on `trainer_availability`, which makes the weekday a
*column* rather than a *value*, so "is this trainer free on the session's weekday?"
cannot be one indexed predicate. The view unpivots the five columns via
`CROSS JOIN LATERAL (VALUES …)` into one row per trainer per weekday, giving clash
checking a normalized shape to query without changing the approved storage.

**3. Ordered teardown in `downgrade()`** — the view is dropped *before* its table,
and the 15 enum types are dropped *after* the tables. Alembic creates enum types
implicitly with the tables that use them but `drop_table` does not remove them;
without the explicit loop, `downgrade base` followed by `upgrade head` fails with
"type already exists" — which is precisely what the rebuild test exercises.

---

## 4. One correction made during implementation

`college_campuses` initially declared a `UniqueConstraint("college_id",
"campus_id")` alongside its composite primary key, on the assumption that a
composite foreign key needs an explicit unique target. PostgreSQL accepts a primary
key as a composite-FK target, so the constraint was redundant; SQLAlchemy suppressed
it in the emitted DDL, leaving the model claiming a constraint the database did not
have. `alembic check` reported the drift correctly.

Resolved at the root: the redundant constraint was removed from both the model and
the initial migration, and the schema was rebuilt. This changed no approved design
decision — the composite key, its column order and the composite FK from
`course_offerings` are unchanged.

---

## 5. Verification performed

| Check | Result |
| --- | --- |
| `alembic upgrade head` on the development database | 27 tables, 1 view, 15 enums created |
| `alembic current` | `6266b57ea53e (head)` |
| `alembic check` | **No new upgrade operations detected** |
| `alembic downgrade base` | 0 business tables, 0 views, 0 enum types remaining |
| `alembic upgrade head` again | identical inventory restored |
| Blank-database rebuild (`tdms_migration_test`, created empty, migrated, verified, dropped) | 27 tables · 1 view · 15 enums · `citext` · 28 PK / 54 FK / 24 UQ / 17 CK · 66 indexes · head `6266b57ea53e` |
| `pytest` (`apps/api`) | 116 passed |
| Frontend `tsc --noEmit` / `node --test` / `next build` | clean · 6 passed · 10 routes built |
| FastAPI `GET /health` | `200 {"status":"ok","service":"tdms-api"}` |

The blank-database counts are identical to the development database, which is the
point of the test: the migration alone reproduces the approved schema, with no
manual step and no drift.

`tests/test_schema_v1.py` covers table and view inventory, per-table columns and
primary keys, the approved UNIQUE and CHECK constraints, the soft-delete column
group, enum membership, and integrity behaviour (FK RESTRICT, CHECK rejection,
partial-index uniqueness) exercised inside transactions that are rolled back, so
the tests leave no rows behind. Tests needing a live database carry the
`database` marker.

---

## 6. Recorded discrepancy — RESOLVED 11 August 2026

`schema-v1-proposal.md` and `local-postgresql-development.md` previously said
**"16 enum types"**. The data dictionary — the authority for every column and
type — defines exactly **15**, the migration creates 15, and 15 exist in
`tdms_dev`. No sixteenth enum was ever named or described anywhere.

Confirmed a typo in summary prose and **corrected to 15** under Step 5B §50.
Documentation correction only: no schema change, no migration, and no enum was
invented to make the number match.

---

## 7. Deliberately not done in Step 3

No seed or reference data was inserted. No user accounts were created — including
none of the named `@chelsongordon.com` or `@vconsultancy.com.au` addresses. No CRUD
endpoints, no Microsoft Entra integration, no frontend-to-database connection. The
frontend still runs entirely on `MockTdmsClient`.

The pre-SRS field-name differences between the frontend prototype and Schema v1
(conflicts C-1…C-6 in `database-requirements-review.md`) remain open and need a
separate realignment step before the frontend can talk to this schema.
