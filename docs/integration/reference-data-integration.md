# College and Course Reference Data — Real Backend Integration (Step 6)

**Status:** implemented. First TDMS operational module on the real
Next.js → FastAPI → SQLAlchemy → PostgreSQL stack.
**Date:** 11 August 2026

No new migration was required: Schema v1 already contains every entity this
module needs. `alembic check` is clean.

---

## 1. Scope

In scope — the entities that belong to this reference-data area:

College · Campus · College/Campus approval · Qualification · Course
(offering) · Course status · Approved durations · Unit · Qualification/Unit
delivery sequence.

Deliberately out of scope: Trainers, Facilities, Students, Bulk Import
execution, Timetable generation and clash detection. Those migrate in their own
steps.

---

## 2. Business concept → database entity

| Business concept | Model | Table |
| --- | --- | --- |
| College (Page 4A **RTO**) | `College` | `colleges` |
| Campus (Page 4A **Location**) | `Campus` | `campuses` |
| College/Campus approval (COL-01) | `CollegeCampus` | `college_campuses` |
| Qualification | `Qualification` | `qualifications` |
| Course record (Page 4A) | `CourseOffering` | `course_offerings` |
| Course status (COL-05) | `CourseStatus` | `course_statuses` |
| Approved durations (DBQ-03) | `OfferingDurationOption` | `offering_duration_options` |
| Unit | `Unit` | `units` |
| Delivery sequence (Page 4B) | `QualificationUnit` | `qualification_units` |

Three earlier resolutions are carried through unchanged:

- **RTO is the College** (DBQ-06). There is no free-text RTO field.
- **Location IS the Campus value** (C-3) — derived in the response, never stored
  twice, so the two cannot drift apart.
- **Source URL is its own field** on the qualification (C-4), never combined
  with RTO.
- **Delivery order** is the ordinal TT-08 depends on; the SRS states a separate
  "Sequence ID" is not a Page 4B field (C-1), so it orders rows rather than
  being presented as one.

---

## 3. API

`/reference/*` — 16 routes.

| Resource | Routes |
| --- | --- |
| Colleges | `GET` list · `GET {id}` · `POST` · `PATCH {id}` |
| Campuses | `GET` list (`?college_id` applies COL-01 **in SQL**) · `GET {id}` · `POST` · `PATCH {id}` |
| College/Campus | `GET` list · `POST` approve |
| Qualifications | `GET` list · `GET {id}` · `POST` · `PATCH {id}` |
| Units | `GET` list (`?qualification_id` returns the sequence, in order) · `GET {id}` · `POST` · `PATCH {id}` |
| Qualification units | `GET` list · `POST` · `PATCH {id}` · `DELETE {id}` · `POST {id}/restore` |
| Courses | `GET` list · `GET {id}` · `POST` · `PATCH {id}` · `DELETE {id}` · `POST {id}/restore` |
| Course statuses | `GET` list |

**Schemas.** Create, update and read are separate Pydantic types. Fields the
backend owns — `id`, `is_deleted`, `deleted_by_user_id`, audit timestamps — do
not exist on the create/update types, so the browser cannot send them. SQLAlchemy
models are never returned directly.

**Actor.** Every write derives the acting user from the verified Microsoft
token (`tid + oid` → TDMS user). No endpoint accepts a `userId` or `email` in the
body as proof of who acted.

**Errors.**

| Status | Meaning |
| --- | --- |
| 401 | Not authenticated |
| 403 | Insufficient TDMS access level |
| 404 | Record not found |
| 409 | Duplicate or conflicting approved reference |
| 422 | Invalid value or relationship |

No SQL, constraint name, driver text or stack trace reaches the caller —
asserted by test.

---

## 4. Permissions

| | Viewer | Data Editor | Admin | Super Admin |
| --- | :-: | :-: | :-: | :-: |
| List / detail / search / filter | ✓ | ✓ | ✓ | ✓ |
| Export | ✓ | ✓ | ✓ | ✓ |
| Create / edit | | | ✓ | ✓ |
| Delete / restore | | | ✓ | ✓ |

**A Data Editor has no write access here.** It maintains Student Data and
Timetables; reference data is read-and-download only. One dependency,
`require_maintain_reference_data`, enforces it — no handler decides for itself,
and every write verb is tested directly rather than relying on hidden buttons.

---

## 5. Transactions

One transaction per operation, committed in the route. A course record and its
approved durations are a single multi-entity write: if the status is invalid the
whole thing rolls back, leaving neither the offering nor a stray duration row.

Database constraints are the backstop, not the message. Each rule is pre-checked
so the user reads *"Delivery order 4 is already used for this qualification"*
rather than a `UniqueViolation`. The constraint still fires under a genuine race
and is translated at both flush **and commit** —
`uq_qualification_units_qualification_id_delivery_order` is
`DEFERRABLE INITIALLY DEFERRED`, so it is enforced at COMMIT, and without the
second translation point a race would surface as a 500.

---

## 6. Status, soft delete and recovery

**Active/inactive** applies to colleges, campuses, qualifications and units.
`?active_only=true` returns what may be chosen for new records; the unfiltered
list still returns retired rows so historical references keep resolving
(DATA-03). Nothing is hard-deleted.

**Soft delete** applies to exactly the two tables the approved design gives it —
`course_offerings` and `qualification_units`. It was not added anywhere else.

A deletion records the timestamp, the actor, an approved reason and a 14-day
recovery deadline, and writes an activity record.

> **Deletion is currently unavailable in `tdms_dev`.** The approved soft-delete
> CHECK requires the whole metadata group including `delete_reason_id`, and no
> approved reason codes exist yet (OD-06). The API says so plainly — *"Deletion
> is unavailable: no approved deletion reasons are configured yet"* — rather than
> failing with a constraint violation. Tests supply their own reason fixture.

**A deleted sequence row keeps its delivery order.** The approved uniqueness is
not partial, so the slot is not released — which is coherent, since freeing it
would let another unit take the place and make the restore impossible. The
refusal names that situation specifically.

---

## 7. Activity logging

`CREATE`, `UPDATE`, `DELETE` and `RESTORE` are recorded through the existing
activity service, with the authenticated user, their access level at the time,
the page, the record reference and a plain-language detail.

Ordinary `GET` requests are **not** logged — asserted by test. Logging every read
would bury the audit trail the SRS actually asks for.

---

## 8. Frontend

`apps/web/src/services/reference-api.ts` always calls FastAPI. It does not
consult `NEXT_PUBLIC_TDMS_DATA_MODE` and **has no mock fallback**: an empty
database renders an empty table, and a failure shows an error. Quietly
substituting demo records would be worse than showing nothing.

It sits beside `TdmsClient` rather than inside it, which is what lets one module
be real while the others stay transitional.

The bearer token is attached in one place, from the same MSAL session the rest
of the application uses. It is held in memory for the call, never logged, never
written to `localStorage`.

**No mock/real mixing.** The module — list, filters, dropdowns, add, edit,
delete, restore, export — has no reference to `getTdmsClient` or the mock
`ReferenceDataProvider`. `useReferenceLookups` supplies colleges and campuses
from PostgreSQL, and asks the server for a college's approved campuses rather
than filtering a cached list, because COL-01 approval is not the browser's to
decide.

Preserved: preview → confirm → save, the styled confirmation dialogs (never
`window.confirm`), filters, the recycle area and the existing export utility.

**Empty states** distinguish "nothing has been added yet" from "nothing matches
your filter", and offer the Add action only to those who may use it.

---

## 9. Reusable lookups for later modules

`referenceLookups` in the same file, so Student, Trainer and Timetable do not
each reimplement dependent-dropdown logic:

```
getActiveColleges()          getActiveQualifications()
getCampusesForCollege(id)    getUnitsForQualification(id)
getCoursesForCollegeCampus() getSelectableCourseStatuses()
```

---

## 10. Module integration status

| Module | Status |
| --- | --- |
| **College and Course Reference Data** | **REAL** — FastAPI + PostgreSQL |
| Trainer Data | MOCK / TRANSITIONAL |
| Student Data | MOCK / TRANSITIONAL |
| Bulk Student Import | MOCK / TRANSITIONAL |
| Timetable | MOCK / TRANSITIONAL |
| Authentication, RBAC, access requests, administration | REAL |

Nothing hidden: the transitional modules still use `MockTdmsClient` through
`getTdmsClient()`, and each migrates in its own step.

---

## 11. Data

**No fake or mock reference data was inserted into `tdms_dev`.** It may
legitimately hold zero reference records; an Admin or Super Admin enters approved
records through the interface. Test fixtures are obviously artificial
(`TSTC`, `TESTQUAL001`, `TESTUNIT001`) and live only in the temporary `tdms_test`
database, which the harness drops.

The Page 4A export supplied for import is reviewed in
[page-4a-source-data-review.md](page-4a-source-data-review.md). It is **not
imported**: three schema conflicts and the campus/college naming decisions are
outstanding.

> **Course offerings cannot yet be created in `tdms_dev`.** `course_statuses` is
> a controlled vocabulary (COL-05) with a read-only API — deliberately, since a
> status is approved business configuration rather than something a user types.
> No approved values are seeded, so every offering create fails validation at
> `course_status_id`. The real export shows `Registered`; the full approved list
> is still required. This is the same class of gap as OD-06 reason codes blocking
> deletion.

---

## 14. Live walkthrough — 11 August 2026

Run in the browser against live Microsoft SSO, FastAPI and PostgreSQL, signed in
as a real Super Admin. Temporary records prefixed `ZZTEMP` were created, exercised
and then removed; all eight reference tables are back to zero rows.

Verified live: create, edit and retire across colleges, campuses, qualifications,
units and the delivery sequence; the college/campus approval filter applied in
SQL (`?college_id=`); duplicate college code, duplicate delivery order and
duplicate unit-in-qualification each refused with a plain-language 409; unknown
qualification 404; blank code 422; DATA-03 retirement — hidden from
`?active_only=true`, still returned in the full list; the OD-06 deletion refusal;
401 for no token, an invalid token and an unauthenticated write; the browser
rendering the records from PostgreSQL, in delivery order, with edits reflected;
the dependent college → campus dropdown; the edit dialog's preview → confirm
step; and an activity record for every write with the actor's access level, with
**no record for any read**.

**Observation, not a defect.** The Page 4B form shows College and Campus fields,
but `qualification_units` holds only qualification, unit and delivery order — a
delivery sequence belongs to a qualification, not to a campus. In that form the
two act as filters rather than stored values. Worth confirming against the SRS
intent for Page 4B.

---

## 12. Testing

```bash
pytest tests/test_reference_data_api.py -q
```

51 tests against real PostgreSQL through the real API: per-level authorisation on
every write verb; duplicate college, campus, qualification, unit and course
codes; the college/campus approval rule and its SQL filter; duplicate offering;
duplicate delivery order and duplicate unit-in-qualification; a unit shared by
several qualifications without duplication; active/inactive filtering with
historical retrieval; soft delete, recycle listing and restore; derived location;
RTO and Source URL kept separate; duration options as a set; sequence ordering;
rejection of backend-owned fields; transactional rollback; no database internals
in any error; activity records for each change and none for reads; and an empty
database returning empty arrays rather than errors.

---

## 13. Runtime database role

The endpoints run as **`tdms_app`**, the least-privilege role — verified for
SELECT, INSERT and UPDATE across every reference table plus the append-only
activity insert. **No new privilege was required**, and none was granted.
Migrations continue to use the administrator credentials.
