# TDMS database

**Database Schema v1 was approved on 10 August 2026** and is implemented as
SQLAlchemy 2 models plus an Alembic migration — see
[`docs/database/`](../docs/database/).

TDMS is still **not** connected to Supabase or any other production database.
The SRS makes that a gate rather than a task:

- **DATA-07** — the final database schema and relationships must be approved
  before Supabase or another production hosting service is connected.
- **OD-13** — the final PostgreSQL schema, Supabase configuration or an
  alternative host must be approved before a production connection is made.

## Where the schema actually lives

Migrations are **not** in this folder. They live with the code that generates
them, so a model change and its migration can be reviewed in one commit:

```
apps/api/app/models/     # SQLAlchemy 2 models — 27 tables
apps/api/alembic/versions/   # migration scripts, applied with `alembic upgrade head`
```

Changing the schema: [`docs/database/migration-workflow.md`](../docs/database/migration-workflow.md).

## Structure

```
database/
├── migrations/   # unused — kept empty; migrations live in apps/api/alembic/versions
└── seeds/        # unused — kept empty; the account bootstrap lives in
                  # apps/api/app/db/seeds/ so it can use the ORM models
```

The initial TDMS accounts are pre-provisioned by an explicit seed command rather
than a migration, so a schema rebuild never silently re-inserts business data:
[`docs/database/initial-access-seeding.md`](../docs/database/initial-access-seeding.md).

## Required data groups (SRS 10.1)

The approved schema must cover:

| Data group | What it stores |
| --- | --- |
| User, role and session | Approved TDMS users, the three hierarchy levels, Data Editor work assignments, account status, active sessions |
| User activity record | Important access and data actions for authorised review |
| Student | Approved student record, course relationship, contact values, active/deleted status |
| Import batch and staged row | Uploaded file information, temporary rows, validation results, final result |
| Trainer, availability and trainer unit | Trainer details, locations, working times, delivery types, approved qualifications and units |
| College and campus | Approved college and campus reference values and their relationship |
| Course and qualification offering | Course details, approved duration, college/campus offering, active status |
| Qualification, unit and sequence | Approved units for a qualification and the delivery sequence used by timetable rules |
| Facility | Room or resource reference, campus, facility type, capacity, active status |
| Timetable session and assignments | Scheduled delivery with assigned group, trainer, facility, dates, times and delivery mode |
| Recycle area | Soft-deleted records and the deletion date so recovery can be controlled |

## Rules the schema must support

- **DATA-01** — Student ID uniquely identifies a student record; duplicates are rejected.
- **DATA-02** — every timetable assignment references approved reference data rather than duplicated free text.
- **DATA-03** — inactive and superseded values are retained for history and excluded from new selections.
- **DATA-04** — soft-deleted records store the deletion date, deleting user, reason and recovery deadline.
- **DATA-05** — a save that changes several related records uses a transaction.
- **DATA-06** — local development data is separated from production data.

## Local development

A local PostgreSQL 17 database (`tdms_dev`) runs in Docker and holds the approved
schema — 27 tables, 1 view, 15 enum types — with **no rows**. No reference data
and no user accounts have been inserted.

The frontend is not yet connected to it. It still uses the prototype dataset held
in browser storage under the `tdms.prototype.v1` keys, which contains demo records
only and is never production information.
