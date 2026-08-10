# TDMS database

No schema is committed yet, and TDMS is **not** connected to Supabase or any
other production database.

The SRS makes this a gate rather than a task:

- **DATA-07** — the final database schema and relationships must be approved
  before Supabase or another production hosting service is connected.
- **OD-13** — the final PostgreSQL schema, Supabase configuration or an
  alternative host must be approved before a production connection is made.

## Structure

```
database/
├── migrations/   # versioned schema changes, added after the schema is approved
├── seeds/        # approved non-personal reference data for staging/testing
└── README.md
```

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

Local development currently uses the frontend prototype dataset held in browser
storage under the `tdms.prototype.v1` keys. It contains demo records only and is
never production information.
