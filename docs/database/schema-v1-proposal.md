# TDMS Database Schema v1 — APPROVED

**Status: APPROVED — Database Schema v1.**
Approval date: **10 August 2026** · Approval authority: **Project Owner**

Schema v1 is frozen. Structural changes now require a new approval, not an edit to this document.
Implementation proceeds through Alembic migrations (Step 3) — never through manual SQL.

No SQLAlchemy model, migration or Supabase configuration has been created by this document.

---

## 1. Scope

Produced a normalized relational design for PostgreSQL, derived from the current SRS, sufficient to
support: data integrity, migration management, referential relationships, auditability, soft
deletion, controlled reference data, transactional imports, timetable generation, clash detection,
historical records, Microsoft Entra identity mapping and access control.

Out of scope for this step: physical database creation, ORM models, migrations, hosting.

## 2. Sources reviewed

See [`database-requirements-review.md`](database-requirements-review.md) §1. In summary: the current
SRS (`TDSM%20SRS_10-Aug-2026_1913-SGT.docx`, 10 Aug 2026 **19:13**), the two prior SRS revisions for
change detection, and the full
frontend repository — 8 type modules, 12 mock-data modules, the `TdmsClient` contract, the access
model and the open-decision register.

## 3. Design principles

1. **Traceability.** Every table maps to an SRS requirement, an SRS field, or a technical
   requirement that is labelled as such. No table exists because it "seems normal".
2. **The SRS wins.** Where the frontend and the SRS disagree, the SRS is followed and the conflict
   is recorded (review §2).
3. **Reference, don't copy.** DATA-02 requires assignments to reference approved data. A value that
   can be reached by a foreign key is not duplicated unless a historical requirement demands it.
4. **Unapproved rules produce no structure.** An open decision never becomes an invented column.
5. **Integrity in the database.** Uniqueness, nullability and referential rules are declared in
   PostgreSQL, not left to FastAPI alone.
6. **Reference data ages, it does not vanish.** DATA-03 / COL-05: status changes, never deletion.
7. **Restraint.** No index, audit column or status lookup is added without a stated use.

## 4. Entity inventory

**27 tables · 1 view · 15 enum types.** No table remains conditional.

<!-- Corrected 11 August 2026 (Step 5B §50): these summary lines previously said 16. The data dictionary — the authority for every type — defines 15, and 15 exist in the database. Documentation correction only; no schema change. -->

*After Group 1: `college_campuses` added (DBQ-04); `user_sessions` withdrawn (DBQ-02);
`student_credit_transfers*` withdrawn (DBQ-01); `offering_duration_options` confirmed (DBQ-03).*
*After Group 2: `rtos` withdrawn — RTO is the College (DBQ-06); `qualification_units.delivery_order`
confirmed as an internal column (DBQ-05); unit sequence confirmed per qualification (DBQ-07);
`students.student_id` confirmed as a plain UNIQUE (DBQ-08).*
*After Group 3: timetable normalised into three tables (DBQ-12); `trainer_availability` keeps five
weekday columns with a `trainer_availability_days` **view** for clash queries (DBQ-11);
`student_groups` confirmed (DBQ-10); `duplicate_resolution` replaced by `duplicate_detected` (DBQ-09).*
*After Group 4: MSCRIS confirmed as `session_type = 'ADDITIONAL'` with `session_title` and
`trainer_name_text` (DBQ-14); `campuses.campus_code` added (DBQ-15); facility reference unique per
campus (DBQ-13).*

**All 15 schema questions are answered. No open decision blocks Schema v1.**

| # | Domain | Table | Status |
| --- | --- | --- | --- |
| 1 | Identity & access | `users` | Confirmed |
| 2 | Reference | `colleges` | Confirmed |
| 3 | Reference | `campuses` | Confirmed |
| 3a | Reference | `college_campuses` | **Approved — DBQ-04 (M:N)** |
| ~~4~~ | ~~Reference~~ | ~~`rtos`~~ | **Withdrawn — DBQ-06, now confirmed by SRS §1.4/§8.2: RTO *is* the College** |
| 5 | Reference | `qualifications` | Confirmed |
| 6 | Reference | `units` | Confirmed |
| 7 | Reference | `qualification_units` | Confirmed |
| 8 | Reference | `course_offerings` | Confirmed |
| 9 | Reference | `offering_duration_options` | **Approved — DBQ-03** |
| 10 | Reference | `course_statuses` | Technical recommendation |
| 11 | Reference | `facilities` | Confirmed (minimum set, TT-15) |
| 12 | Students | `student_groups` | **Approved — DBQ-10** |
| 13 | Students | `students` | Confirmed |
| 14 | Imports | `import_batches` | Confirmed |
| 15 | Imports | `import_staged_rows` | Confirmed |
| 16 | Imports | `import_row_issues` | Technical recommendation (separate table, proposal §10) |
| 17 | Trainers | `trainers` | Confirmed |
| 18 | Trainers | `trainer_availability` | **Approved — DBQ-11 (five weekday columns)** |
| 19 | Trainers | `trainer_qualifications` | Confirmed |
| 20 | Trainers | `trainer_units` | Confirmed |
| 21 | Timetables | `timetable_plans` | **Approved — DBQ-12** |
| 22 | Timetables | `timetable_unit_deliveries` | **Approved — DBQ-12** |
| 23 | Timetables | `timetable_sessions` | **Approved — DBQ-12** |
| 24 | Timetables | `timetable_clash_overrides` | Technical recommendation |
| 25 | Audit & control | `user_activity_records` | Confirmed |
| 26 | Audit & control | `reason_codes` | Confirmed (list pending OD-06) |
| 27 | Audit & control | `reason_code_contexts` | Technical recommendation |

Plus one **view**: `trainer_availability_days` (DBQ-11).

15 enum types — see the data dictionary.

Tables **excluded by an approved decision**:

| Table | Decision |
| --- | --- |
| `user_sessions` | **DBQ-02 — not built.** Sessions are token-based; access level is read from `users` per request |
| `student_credit_transfers`, `student_credit_transfer_units` | **DBQ-01 — not built.** CT is a flag only |
| `academic_calendar_breaks` | OD-07 unapproved — would be additive |

## 5. Identity and access model

### 5.1 Access level representation

Three candidates were considered.

| Option | Guarantees exactly three levels? | Adds a value without a migration? | Ordered? |
| --- | --- | --- | --- |
| A. PostgreSQL `ENUM` | **Yes** — a fourth value needs `ALTER TYPE` in a reviewed migration | No (this is desirable here) | **Yes** — enums order by declaration |
| B. Lookup table `access_levels` | No — any `INSERT` creates a fourth level | Yes | Only via a rank column |
| C. `TEXT` + `CHECK` | Yes | No | No |

**Recommendation: Option A.**

```
CREATE TYPE access_level AS ENUM ('DATA_EDITOR', 'ADMIN', 'SUPER_ADMIN');
```

ACC-01 states TDMS *must* use only three access levels. That is a rule that should be hard to break,
so the friction of a migration is a feature, not a cost. Declaration order also gives
`access_level >= 'ADMIN'` for free, which expresses ACC-03 and ACC-04 directly.

A lookup table is rejected here specifically because it would allow a fourth level to be created by
data entry — the exact failure ACC-01 and ACC-02 exist to prevent.

### 5.2 Data Editor work assignment

```
CREATE TYPE data_editor_assignment AS ENUM ('STUDENT_DATA_OFFICER', 'TIMETABLE_OFFICER');
```

Stored in a **separate column of a separate type**:

```
users.access_level             access_level             NOT NULL
users.data_editor_assignment   data_editor_assignment   NULL
CHECK (data_editor_assignment IS NULL OR access_level = 'DATA_EDITOR')
```

This makes ACC-02 structurally true rather than merely documented:

- an assignment value **cannot** be written into `access_level` — the types are incompatible;
- an assignment **cannot** exist on an Admin or Super Admin — the CHECK rejects it;
- a fourth "level" cannot be created by adding an assignment.

An assignment is deliberately **not** made mandatory for a Data Editor: ACC-05 and the permission
table allow a Data Editor with no assignment to view and download every operational page while
having no create/update/delete area.

### 5.3 Account status

`account_status` values Active / Inactive / Disabled come from SRS §4.4 and are closed and stable →
a third enum is justified. "Blocked by security rule" and "No TDMS access level" are *denial
reasons* recorded on the activity record, not account statuses: the first is decided by Microsoft or
a security rule, the second is the absence of `access_level`.

**No role assignment is derived from an email domain anywhere in the schema.** The supplied
`@chelsongordon.com` and `@vconsultancy.com.au` domains are not stored as an access rule.

## 6. Microsoft Entra identity mapping

AUTH-04 requires a verified Microsoft account to match **one** internal user.

| Column | Type | Purpose |
| --- | --- | --- |
| `entra_object_id` | `uuid` NULL, UNIQUE | The stable Entra object identifier. Populated at first successful sign-in once OD-01 is approved. Nullable because accounts are provisioned in TDMS *before* anyone signs in. |
| `entra_tenant_id` | `uuid` NULL | Recorded per user only if the organisation later admits guests from another tenant. Otherwise a single tenant belongs in configuration, not in every row. |
| `organisation_email` | `citext` NOT NULL, UNIQUE | The human-readable account. Used for provisioning and display. |
| `display_name` | `text` NOT NULL | Shown in the interface and snapshotted into activity records. |

**Email must not be the permanent identity key.** People are renamed and mailboxes are reassigned; an
Entra object ID is immutable. The design therefore matches on `entra_object_id` when present and
falls back to `organisation_email` only for the first sign-in, then stores the object ID.

`citext` gives case-insensitive uniqueness so `A.Chattopadhyay@…` and `a.chattopadhyay@…` cannot
become two accounts. It requires `CREATE EXTENSION citext` — noted as a migration prerequisite.

**Explicitly not stored anywhere:** passwords, Microsoft passwords, access or refresh tokens, client
secrets, tenant/client configuration values (AUTH-03, NFR-01). Tenant ID and client ID are
environment configuration; the per-user `entra_tenant_id` above is a different thing and is optional.

## 7. Reference-data model

### 7.1 College and campus — cardinality · **DECIDED: many-to-many**

SRS COL-01 and §6.1.3 only ever say a campus is "approved for" or "connected to" the selected
college. Neither phrase proves exclusive ownership.

**Approved (DBQ-04): a single physical campus can be operated by more than one college.**
A 1:N model would have forced the same site to be entered once per college, producing duplicate
campuses, duplicate facilities and duplicate `state` values — and TT-06's facility clash check would
then fail to see that two colleges had booked the same physical room.

```
colleges          (college_short_name, college_full_name, email_domain, is_active)
campuses          (campus_name, campus_location, state, is_active)      -- no college_id
college_campuses  (college_id, campus_id, is_active)
                  PRIMARY KEY (college_id, campus_id)
```

Consequences carried through the rest of the design:

| Area | Effect |
| --- | --- |
| `course_offerings` | Already carries both `college_id` and `campus_id`. A **composite FK to `college_campuses (college_id, campus_id)`** now guarantees the pair is an approved combination — COL-01 enforced by the database, not by the application. |
| `facilities` | Unchanged: `campus_id` only. A room belongs to the physical site, not to a brand — which is exactly why sharing must be modelled properly. |
| `trainer_availability` | Unchanged: `campus_id` only. A trainer is available at a site. |
| Student `State` | Unchanged: still derived from `campuses.state`. |
| Campus identity | **`campus_code` UNIQUE (DBQ-15)** — a stable code such as `HOB` or `MEL-CBD`. `campus_name` is free to change, which matters because two colleges may refer to the same site by different names. |

The cost is one extra join in College → Campus dropdowns and in Page 4 filtering. That is a small,
permanent price for a model that matches how the sites are actually operated.

### 7.2 Course vs Qualification — the central reference-data decision

These are **not** the same entity, but the current SRS makes the relationship clear:

> §8.2 — "Page 4A terminology: Qualification Code is the VET Code, and Qualification Title is the
> Course Name." · "Location represents the Campus value."

Separating Page 4A's fields by what they actually describe:

| Field | Describes | Belongs to |
| --- | --- | --- |
| Qualification Code, Qualification Title, Course Level, Field of Education Broad/Narrow, Course Sector | the national qualification, identical at every campus | `qualifications` |
| **RTO (= College)**, Course Code, Course Status, Duration in Weeks, Total Course Cost, Location (= Campus) | this college/campus offering it | `course_offerings` |

The 19:13 SRS makes the two aliases explicit — §8.2: "**RTO represents the College, Location
represents the Campus**, Qualification Code is the VET Code, and Qualification Title is the Course
Name." Both aliases resolve to foreign keys that `course_offerings` already carries, so Page 4A needs
no column that does not exist.

**Recommendation: two entities.**

```
qualifications      (qualification_code UNIQUE, qualification_title, course_level,
                     field_of_education_broad, field_of_education_narrow, course_sector,
                     source_url, is_active)

course_offerings    (college_id, campus_id, qualification_id, course_code,
                     course_status_id, total_course_cost)
                     UNIQUE (college_id, campus_id, qualification_id)   -- COL-04
                     FOREIGN KEY (college_id, campus_id) -> college_campuses
```

**RTO — approved under DBQ-06 and now stated by the SRS.** §1.4 defines "RTO — The College value used
in Page 4 reference data", and §8.2 lists RTO as a Page 4A field meaning "the approved College
represented by the RTO value for the course offering". So:

| Page | RTO is read from |
| --- | --- |
| **4A** Course Data | `course_offerings.college_id → colleges` — a direct join, one hop |
| **4B** Qualification and Unit Sequence | `qualification_units → qualifications → course_offerings → colleges`, filtered by the selected College |

No `rtos` table and no `rto_id` column. `qualifications` stays national — a qualification is not
owned by one college — while both pages still display the RTO that COL-03 requires.

Which college attribute renders in the RTO column (`college_short_name` or `college_full_name`) is a
display choice, not a schema one. If a formal RTO registration number is ever required, it is an
additive nullable column on `colleges`, not a new table or relationship.

This produces an important simplification: **Page 4A Course Data and the "qualification offering"
concept in §11 of the brief are the same table.** Once qualification-level attributes are factored
out, what remains of a Page 4A row *is* the offering. Creating both a `courses` table and a
`qualification_offerings` table would store the same relationship twice and breach COL-04.

The `UNIQUE (college_id, campus_id, qualification_id)` constraint is COL-04 stated directly in SQL.

### 7.3 Duration in Weeks — attribute or child table?

Page 4A shows one **Duration in Weeks** per course row, but §6.1.3 has the user selecting a *Course
Duration Option* from an approved dropdown, and TT-11 refers to 26-, 52-, 78- and 104-week courses.

The deciding argument is COL-04: uniqueness is on **college + campus + qualification**, and duration
is not part of that key. If each duration were a separate offering row, COL-04 would be violated.
Therefore one offering must be able to carry more than one approved duration.

**Recommendation:** child table `offering_duration_options (course_offering_id, duration_weeks)` with
`UNIQUE (course_offering_id, duration_weeks)`. `students.course_duration_option_id` references it, so
a student can only be given a duration that is approved for their own offering — enforced by the
database, not by application code. Raised as **DBQ-03** because it changes the shape of Page 4A.

### 7.4 Qualifications, units and delivery order

```
units               (unit_code UNIQUE, unit_title, uoc_type, is_active)
qualification_units (qualification_id, unit_id, delivery_order)
                     UNIQUE (qualification_id, unit_id)
                     UNIQUE (qualification_id, delivery_order) DEFERRABLE
```

A unit is reusable across qualifications (BSBCMM511 appears in both BSB50420 and BSB60420 in the
supplied data), so the relationship is M:N and the junction carries business meaning — the order.

**The delivery-order problem (conflict C-1).** The SRS now says a separate Sequence ID is *not used*
and that row order carries the sequence. A relational table has no inherent row order: without an
ordinal column, "the approved sequence" is not recoverable, and TT-08 ("schedules must follow the
approved unit sequence") becomes unimplementable.

**Approved (DBQ-05):** `delivery_order integer NOT NULL` is stored as an **internal ordering column
that is never displayed as a field**, populated from row order on import and maintained by
drag-reorder. Page 4B still shows no Sequence ID column, so the SRS presentation rule in §8.3 holds
while TT-08 remains implementable.

The uniqueness is **per qualification, not global** — sequence 1 exists once in every qualification.
`DEFERRABLE INITIALLY DEFERRED` allows a reorder to be applied within one transaction without
tripping the constraint mid-update.

**Approved (DBQ-07): one sequence per qualification, not per campus.** The junction therefore has no
`course_offering_id`. Page 4's college/campus filter reaches the units through `course_offerings`,
so filtering still works without duplicating the sequence for every campus that offers the
qualification — which would otherwise mean maintaining the same correction in ten places.

### 7.5 Course status

§8.2 says "active, inactive, superseded **or in another approved status**". That open-ended phrasing
is the opposite of the access-level case, so a lookup table `course_statuses (code, label,
selectable_for_new_records, is_active)` is recommended. `selectable_for_new_records` implements
COL-05 and DATA-03 as data rather than as scattered application conditionals.

For binary cases (`colleges`, `campuses`, `units`, `trainers`, `facilities`) a plain
`is_active boolean NOT NULL DEFAULT true` is sufficient; a lookup would be ceremony.

## 8. Student model

### 8.1 Field-by-field classification

**A** = stored · **B** = foreign key · **C** = derived, not stored · **D** = business decision

| SRS field | Class | Design | Why |
| --- | --- | --- | --- |
| Group | **B** | `student_group_id` | Shared with timetable data (§5.3 "Approved student/group data"). See §9. |
| Intake | **C** | on `student_groups` | Generated from the proposed start date; the group already encodes the intake. Storing it on both invites disagreement. |
| College | **C** | via `course_offerings` | The offering carries college + campus. Storing college on the student duplicates it. |
| Campus | **C** | via `course_offerings` | As above. |
| College Email | **A** | `college_email citext` | Generated *initially*, then editable (§6.1.3). The edited value must persist, so it is stored. |
| First Name | **A** | `first_name text NOT NULL` | |
| Last Name | **A** | `last_name text NULL` | SRS Required = No. |
| Student ID | **A** | `student_id text NOT NULL UNIQUE` | The business key. See §14. |
| CoE / Non-CoE | **A** | `coe_status` enum | Closed two-value domain. |
| Proposed Start Date | **A** | `date NOT NULL` | |
| Proposed End Date | **A** | `date NOT NULL` | CHECK end > start. |
| Actual Course Duration | **C** | `GENERATED ALWAYS AS (round((proposed_end_date - proposed_start_date + 1) / 7.0)) STORED` | **Approved (DBQ-01): inclusive dates.** A generated column cannot drift from the dates it is derived from, which is exactly what §2.4 ("derived by one approved rule and shown consistently") asks for. |
| Course Duration Option | **B** | `course_duration_option_id` | **Approved (DBQ-01): always shown, staff-selected.** FK to the offering's approved options makes an unapproved duration impossible. §6.1.3 additionally requires the selection to be validated against the calculated duration — enforced in the service layer, because the comparison spans two tables. |
| Qualification Title | **C** | via offering → qualification | Duplicate of reference data (DATA-02). |
| Qualification Code | **C** | via offering → qualification | As above. |
| CT Student | **A** | `ct_student boolean NOT NULL` | **Approved (DBQ-01): flag only.** Yes means the student has at least one approved Credit Transfer. No transferred units, unit count or CT reference is stored, and no duration reduction is derived from it. |
| Personal Email | **A** | `citext NULL` | |
| Primary Phone | **A** | `text NULL` | Free-form; international formats make a length limit arbitrary. |
| State | **C** | via campus | §6.1.3 "Generated from campus". |
| Primary Country | **A/D** | `text NULL` now | **OD-15** decides controlled list vs free text. Text now; a FK can be added without losing data. |
| Remarks | **A** | `text NULL` | |

Seven of twenty-one fields are **not** stored on `students`. That is the point of §13 of the brief:
the form is not the table.

### 8.2 What happens if reference data changes later

| Change | Effect on existing students | Acceptable? |
| --- | --- | --- |
| Qualification title corrected | All students show the corrected title | **Yes** — a correction should propagate. A genuinely different qualification receives a new code and a superseded status, so history is preserved by the status model. |
| Campus renamed | State and campus name follow | **Yes** — same reasoning. |
| Offering made inactive | Existing students keep their FK; new students cannot select it | **Yes** — COL-05, DATA-03. |
| Duration option removed | FK prevents deletion (RESTRICT); the option is deactivated instead | **Yes** |

No snapshot columns are proposed on `students`. Snapshots are proposed only where the SRS requires
historical context — the activity record (§12).

## 9. Student groups

Group appears on both the student record and the timetable record, and §5.3 sources it from
"Approved student/group data" — reference data, not free text. A text column repeated on both sides
would breach DATA-02 and make TT-06's student-group clash check a string comparison.

**Recommendation:** `student_groups (group_code UNIQUE, course_offering_id, intake,
expected_class_size, is_active)` — **approved under DBQ-10**.

`expected_class_size` supports §5.3 "Classroom Size — Student/group data **or** authorised entry": the
group carries the expected size and the timetable plan may override it with a nullable
`class_size_override`. Approved under **DBQ-10**: the group becomes real reference data, so TT-06's student-group clash
check is a foreign-key join rather than a string comparison.

## 10. Bulk-import model

Three tables. Uploaded data never touches `students` until the confirmed transaction.

```
import_batches      (file_name, file_size_bytes, uploaded_at, uploaded_by_user_id,
                     row_count, status,
                     inserted_count, excluded_count, duplicate_count,
                     corrected_count, rejected_count, unmatched_count,
                     completed_at)

import_staged_rows  (import_batch_id, source_row_number, raw_values jsonb,
                     student_id_value, ... resolved_*_id, status,
                     duplicate_detected boolean, corrected boolean)

import_row_issues   (import_staged_row_id, field_name, message, issue_status)
```

**Issues in a separate table (Option A), not columns on the row.** One row commonly has several
independent problems — a blank Student ID *and* an unmatched college *and* a malformed date. BULK-05
requires each issue to name its own field and message, and BULK-10 exports an issue report, which is
naturally one row per issue. Columns or a delimited string would have to be parsed apart again.

`raw_values jsonb` keeps the original uploaded cells exactly as supplied, alongside the typed working
columns. This matters because a corrected row must still be traceable to what the file actually
contained, and because the approved template may gain columns without a migration.

**Duplicate handling — approved (DBQ-09): excluding the row is the only permitted resolution.**

Because there is exactly one approved resolution, a `duplicate_resolution` enum would be a column
with a single possible value. It is replaced by a plain flag:

```
duplicate_detected  boolean NOT NULL DEFAULT false
status              staged_row_status          -- becomes EXCLUDED_BY_USER once resolved
```

This is not cosmetic. BULK-09 requires **both** a duplicate count and an excluded count, and a row
that was a duplicate *and* was then excluded belongs in both. A status column alone cannot hold two
facts, so the flag survives the exclusion and keeps the counts correct.

If "update the existing student record" is approved later, a `duplicate_resolution` column is added
then — additive, and the flag still tells us which rows it applies to. Updating an existing student
from an import is deliberately **not** possible in Schema v1: DATA-01 forbids a second record with
the same Student ID, and nothing in the approved set permits a bulk edit.

The batch counts are stored on the batch because BULK-09 requires them to be reported and BULK-12
requires them in the activity record — recomputing them later from rows that have since been deleted
would give a different answer.

## 11. Trainer model

```
trainers               (trainer_id UNIQUE, trainer_name, is_active)
trainer_qualifications (trainer_id, qualification_id)       UNIQUE (trainer_id, qualification_id)
trainer_units          (trainer_id, unit_id)                UNIQUE (trainer_id, unit_id)
trainer_availability   (trainer_id, campus_id, location, location_type, class_type,
                        working_time_start, working_time_end, weekday, mode_of_delivery)
```

`Qualifications They Can Teach` and `Units They Can Teach` become junction tables. A comma-separated
list cannot be indexed, cannot be constrained to approved values, and makes TRN-01 ("select a
qualification before results appear") a `LIKE '%…%'` scan.

### Weekday availability — **DECIDED: five columns**

**Approved (DBQ-11): `monday`…`friday` columns on one availability row**, matching the supplied
spreadsheet and the Page 3 grid one-to-one.

```
trainer_availability (trainer_id, campus_id, location, location_type, class_type,
                      working_time_start, working_time_end,
                      monday, tuesday, wednesday, thursday, friday)   -- each weekday_mode
```

This keeps storage aligned with the source data and makes Page 3 a direct read with no pivot. The
cost is real and is mitigated rather than ignored:

| Consequence | Mitigation |
| --- | --- |
| "Is this trainer available on the session's weekday?" cannot be a single indexed predicate — the weekday is a *column*, not a value | Add a **database view** `trainer_availability_days` that unpivots the five columns into `(availability_id, trainer_id, campus_id, class_type, weekday, mode_of_delivery)`. Clash and availability queries read the view; Page 3 reads the table. A view is not a second copy of the data and cannot drift from it. |
| An "any weekday" search becomes a five-branch `OR` | The same view removes it |
| Adding a weekend day would need a migration | Accepted — the SRS defines Monday to Friday (§7.3) |

The view is a technical recommendation, not a new question: it changes no stored structure and can be
added or dropped freely.

`working_time_start`/`_end` replace the free-text "09:00 - 17:00" so an availability window can
actually be compared with a session time.

`UNIQUE (trainer_id, campus_id, class_type, working_time_start)` — one availability block per trainer,
campus, class type and start time.

## 12. Facility model

`facilities (facility_reference, campus_id, facility_type, capacity, is_active)` — exactly the
minimum TT-15 requires, and nothing beyond it, because OD-09 leaves the wider structure and the
maintenance owner unapproved.

`CHECK (capacity > 0)`. **Approved (DBQ-13): `UNIQUE (campus_id, facility_reference)`** — room codes
such as `C1` are naturally campus-scoped, so every site may reuse them without an artificial prefix.

Facilities are never hard-deleted; `is_active = false` keeps historical timetable rows readable
(DATA-03).

## 13. Timetable model — the central structural decision

### 13.1 Why not one wide table

The frontend's `TimetableSession` carries `theory_*`, `practical_*` and `mscris_*` triplets on one
row. As a database design that has four specific defects:

1. **Clash detection becomes three queries.** TT-06 must compare *every* scheduled slot against every
   other. With triplicated columns each check is a three-way union against three more, and every new
   session type multiplies it again.
2. **Referential integrity weakens.** `theory_classroom_name` is a text copy of a facility reference
   — DATA-02 explicitly forbids "uncontrolled duplicate descriptions".
3. **Nulls carry meaning.** A theory-only unit leaves nine practical columns null; nothing prevents a
   practical trainer with no practical time.
4. **Adding a session type is a migration.** MSCRIS already proves a third type appears; a fourth
   would repeat the exercise.

### 13.2 Recommended three-level model

```
timetable_plans            one per student group — the course timetable
  └─ timetable_unit_deliveries   one per unit scheduled for that group (dates, mode)
       └─ timetable_sessions     one per weekly slot (type, weekday, times, trainer, facility)
```

| Table | Grain | Key fields |
| --- | --- | --- |
| `timetable_plans` | student group | `student_group_id`, `course_offering_id`, `duration_weeks`, `class_size_override`, `remarks`, soft delete |
| `timetable_unit_deliveries` | group × unit | `timetable_plan_id`, `unit_id`, `uoc_type`, `mode_of_delivery`, `start_date`, `end_date`, `remarks` |
| `timetable_sessions` | one weekly slot | `timetable_unit_delivery_id`, `session_type`, `weekday`, `start_time`, `end_time`, `trainer_id`, `facility_id`, `delivery_mode` |

`session_type` is an enum: `THEORY`, `PRACTICAL`, `ADDITIONAL`.

The plan level exists because TT-08 (approved duration and unit sequence) and TT-10 (a course must
not finish on a break) are statements about the **whole course for a group**, not about one unit.
Without it, "does this group's schedule end on a break?" has no anchor.

The mapping from the SRS row is exact:

| SRS field | Lands on |
| --- | --- |
| College, Campus Location, Qualification Code/Name | `course_offerings` via the plan |
| Duration in Weeks | `timetable_plans.duration_weeks` |
| Group | `timetable_plans.student_group_id` |
| Classroom Size | group's `expected_class_size`, or `class_size_override` |
| UoC Code / Title / Type | `units` via `timetable_unit_deliveries.unit_id` |
| Mode of Delivery, UoC Start/End Date | `timetable_unit_deliveries` |
| Theory Days and Times / Classroom / Trainer | `timetable_sessions` where `session_type = 'THEORY'` |
| Practical … | same rows with `session_type = 'PRACTICAL'` |
| MSCRIS … | same rows with `session_type = 'ADDITIONAL'` |
| Theory/Practical Classroom Capacity | derived from `facilities.capacity` — never stored twice |
| Remarks | `timetable_unit_deliveries.remarks` |

TT-06 then becomes **one** self-join over `timetable_sessions`: same weekday, overlapping times,
overlapping parent date ranges, and the same trainer / facility / group. That single query answers
all three clash types.

**Approved (DBQ-12).** This is the largest structural departure from the current frontend shape, and it is what makes TT-06 a single query instead of three.

### 13.3 Clash override

TT-06 permits saving a clash only when an override "has been expressly approved and recorded".
`timetable_clash_overrides (timetable_session_id, conflicting_session_id, reason_code_id,
reason_detail, approved_by_user_id, approved_at)` records it as data rather than as a free-text note,
so "which clashes were overridden and by whom" is answerable. Who may approve is **OD-06**.

## 14. MSCRIS / additional classes

Confirmed business purpose: additional classes, especially topic-specific ones. Detailed field rules
remain unconfirmed.

**Recommendation: represent MSCRIS as `timetable_sessions.session_type = 'ADDITIONAL'`, not as a
separate table.** Assessed against what MSCRIS must support:

| Capability | Supported by the general session model? |
| --- | --- |
| Trainer assignment | Yes — `trainer_id` |
| Delivery mode | Yes — `delivery_mode` |
| Time slot | Yes — `weekday`, `start_time`, `end_time` |
| Facility when physical | Yes — `facility_id`, nullable for virtual |
| Clash checking | Yes — and it can also be *excluded* by a `WHERE session_type <> 'ADDITIONAL'` predicate if that is the approved rule |
| Optional / only when required | Yes — simply no rows of that type |
| Topic name | **Needs one column** — `session_title`, nullable |

A separate `mscris_sessions` table would duplicate every column and force every clash query to union
two tables.

**Approved (DBQ-14).** MSCRIS is `session_type = 'ADDITIONAL'`, with:

```
session_title      text NULL     -- the topic the additional class covers
trainer_name_text  text NULL     -- free-text trainer, ADDITIONAL sessions only

CHECK (session_type <> 'ADDITIONAL' OR delivery_mode = 'VIRTUAL')
CHECK (session_type =  'ADDITIONAL' OR trainer_name_text IS NULL)
```

The second CHECK matters: it confines the free-text exception to additional classes, so a theory or
practical session can never bypass approved trainer data. Clash detection excludes MSCRIS with
`WHERE session_type <> 'ADDITIONAL'`.

**Recorded consequence.** A free-text trainer that is excluded from clash checking means TDMS
**cannot** detect a trainer booked for both an MSCRIS class and a normal class, and
`trainer_name_text` does not satisfy DATA-02 for that field. Implemented as approved, constrained to
ADDITIONAL sessions, and surfaced by the timetable preview warning.

## 15. Date and time model

Sessions repeat weekly inside the unit's date range. Two candidates:

| Option | Storage | Clash detection | Regeneration |
| --- | --- | --- | --- |
| A. Pattern | weekday + times on the session; date range on the parent | Range overlap **and** same weekday **and** time overlap — one query | Change a date, nothing to rebuild |
| B. Materialised occurrences | one row per actual date | Simpler predicate (date + time overlap) | Every edit deletes and regenerates rows; a 52-week unit becomes ~104 rows |

**Recommendation: Option A.** It matches how the SRS states the requirement — "Theory **Days and
Times**" is a weekly pattern, and TT-03 filters by *range overlap*, which Option A answers directly.
Option B multiplies row counts by two orders of magnitude to simplify a predicate that is already
straightforward, and makes every edit a rebuild. If a later requirement needs per-date exceptions
(a public holiday, a one-off room change), a `timetable_session_exceptions` table can be added
without disturbing the pattern.

**Types.** `date` for dates and `time` (without time zone) for session times: a class at 09:00 is
09:00 at that campus, and binding it to an absolute instant would make it shift under a time-zone
change. Activity records are different — they record *when something happened* and use
`timestamptz`.

**OD-14 (new).** The stored and displayed time zone for activity records is unapproved. The
recommendation is `timestamptz` stored in UTC with display time zone applied per OD-14; the storage
type does not change whatever OD-14 decides, so this does not block Schema v1.

## 16. Audit and activity model

### 16.1 Preserving historical context

The requirement is explicit: an old activity record must still show the access level used **at the
time of the action**, even after the user's level changes.

| Option | Behaviour when a role changes |
| --- | --- |
| A. FK to `users` only | History silently rewrites itself — the old record now shows the new level. **Fails the requirement.** |
| B. Snapshot text only | History is safe, but "show me everything this user did" becomes a string match, and a renamed user fragments. |
| C. **FK + snapshot** | History is fixed at write time; the FK still supports reliable per-user queries. |

**Recommendation: Option C.**

```
user_id                     bigint NULL REFERENCES users   -- NULL for "Unmatched user"
user_reference_snapshot     text NOT NULL                  -- email, or 'Unmatched user'
access_level_snapshot       access_level NULL              -- NULL when no verified user
assignment_snapshot         data_editor_assignment NULL
```

`user_id` is nullable because §4.3 requires a failed sign-in with no verified identity to be
recorded as "Unmatched user" **without** attaching it to any account.

### 16.2 The three result fields (conflict C-6)

LOG-02 now requires the Microsoft sign-in result and the TDMS access decision to be stored
*separately* from the operational result:

```
result                    activity_result NULL          -- operational actions
microsoft_sign_in_result  ms_sign_in_result NULL        -- SUCCESS | FAILURE
tdms_access_decision      access_decision NULL          -- GRANTED | DENIED
CHECK (result IS NOT NULL OR microsoft_sign_in_result IS NOT NULL OR tdms_access_decision IS NOT NULL)
```

This is §4.2's rule stated in the schema: a blocked account is a *denial reason*, not a third
universal sign-in status.

### 16.3 Immutability

LOG-05 is enforced by **privilege, not by convention**: the application role receives
`INSERT, SELECT` on `user_activity_records` and no `UPDATE` or `DELETE`. Retention purges run under a
separate maintenance role once OD-04 approves a period.

The activity record number is the `bigint` identity primary key, displayed as `ACT-000123`. A second
sequence would add a failure mode for no benefit.

## 17. Soft-deletion model

| Option | Assessment |
| --- | --- |
| A. Soft-delete columns on operational tables | FKs stay valid; restore is one `UPDATE`; no data movement; partial indexes handle uniqueness |
| B. Separate recycle tables per entity | Doubles the table count, breaks every FK from dependent rows, and restore becomes a re-insert that can fail |
| C. Single polymorphic recycle table | No referential integrity at all — the recycled row cannot be typed |

**Recommendation: Option A.**

```
is_deleted           boolean NOT NULL DEFAULT false
deleted_at           timestamptz NULL
deleted_by_user_id   bigint NULL REFERENCES users
delete_reason_id     bigint NULL REFERENCES reason_codes
delete_reason_detail text NULL
recovery_deadline    date NULL
CHECK (is_deleted = false OR (deleted_at IS NOT NULL AND deleted_by_user_id IS NOT NULL
                              AND delete_reason_id IS NOT NULL AND recovery_deadline IS NOT NULL))
```

That CHECK is DATA-04 stated in SQL: a record cannot be soft-deleted without its full deletion
metadata.

**Applied to** (operational records only): `students`, `timetable_plans`,
`timetable_unit_deliveries`, `timetable_sessions`, `trainers`, `course_offerings`,
`qualification_units`.

**Not applied to** reference data that should age instead of disappear — `colleges`, `campuses`,
`qualifications`, `units`, `facilities` use `is_active` / status (DATA-03, COL-05). The distinction:
*a user deletes a record they created by mistake; an administrator retires a reference value that was
correct at the time.*

`recovery_deadline` is stored rather than computed because the 14-day period is proposed, not
approved — if it changes, records deleted under the old period keep their original deadline.

## 18. ID strategy

**Internal primary keys: `bigint GENERATED ALWAYS AS IDENTITY`,** named `id`, on every table.

| Considered | Assessment |
| --- | --- |
| `bigint` identity | Compact, index- and join-friendly, monotonic (good page locality). No client-side generation needed — every write goes through one FastAPI service. **Recommended.** |
| `uuid` | Needed for multi-master merge, offline clients or IDs generated before insert. TDMS has none of those. Costs 16 bytes vs 8 in every index and every FK, and random v4 values fragment B-tree pages. |
| Business key as PK | See §19. |

One exception is deliberate: `users.entra_object_id` is a `uuid` because Microsoft defines it. It is
a UNIQUE external identifier, not the primary key.

**Business identifiers are never primary keys**, but are always `UNIQUE NOT NULL`:
`students.student_id`, `trainers.trainer_id`, `qualifications.qualification_code`,
`units.unit_code`, `course_offerings.course_code`, `student_groups.group_code`,
`facilities.facility_reference`.

### 19. Student ID specifically

The SRS Key Terms table says: "Primary key — The main field used to distinguish one database record
from another, **such as Student ID** for a student record." That is a statement about the *business*
key.

| Option | Consequence |
| --- | --- |
| A. `student_id` **is** the PK | A mistyped Student ID cannot be corrected without cascading the change through every dependent row. External identifiers also tend to change format over time. |
| B. Internal `id` PK + `student_id` UNIQUE NOT NULL | A correction is a single-column `UPDATE`. FKs never move. DATA-01 is still enforced by the UNIQUE constraint. **Recommended.** |

**Student ID remains the unique business identifier required by DATA-01 and SST-05.** Option B does
not weaken that rule; it enforces it with a constraint instead of with a key, so that correcting a
typo does not require rewriting related records.

## 20. Constraints

Constraints stated below are those the SRS supports. Where the underlying rule is unresolved, the
constraint is listed as **pending**, not invented.

| Constraint | Table | Source |
| --- | --- | --- |
| `UNIQUE (student_id)` | `students` | DATA-01, SST-05 |
| `UNIQUE (organisation_email)`, `UNIQUE (entra_object_id)` | `users` | AUTH-04 |
| `CHECK (data_editor_assignment IS NULL OR access_level = 'DATA_EDITOR')` | `users` | ACC-01, ACC-02 |
| `UNIQUE (college_id, campus_id, qualification_id)` | `course_offerings` | **COL-04** |
| `UNIQUE (qualification_id, unit_id)` | `qualification_units` | COL-03 |
| `UNIQUE (qualification_id, delivery_order)` deferrable | `qualification_units` | TT-08, DBQ-05 |
| `UNIQUE (course_offering_id, duration_weeks)` | `offering_duration_options` | COL-04, DBQ-03 |
| `UNIQUE (campus_id, facility_reference)` | `facilities` | TT-15, DBQ-13 |
| `CHECK (capacity > 0)` | `facilities` | TT-15 |
| `CHECK (end_time > start_time)` | `timetable_sessions`, `trainer_availability` | TT-06 |
| `CHECK (end_date >= start_date)` | `timetable_unit_deliveries` | TT-03 |
| `CHECK (proposed_end_date > proposed_start_date)` | `students` | SST-05 |
| `CHECK (delete metadata complete when is_deleted)` | all soft-deletable | **DATA-04** |
| `CHECK (result OR ms_result OR access_decision IS NOT NULL)` | `user_activity_records` | LOG-02 |
| `UNIQUE (import_batch_id, source_row_number)` | `import_staged_rows` | BULK-03 |
| `UNIQUE (trainer_id, qualification_id)` / `(trainer_id, unit_id)` | trainer junctions | TRN-03 |
| Duration option validated against the calculated duration — **service layer**, spans two tables | `students` | §6.1.3, DBQ-01 |
| **Pending** — break placement | timetable | OD-07 |
| **Pending** — physical/virtual derivation | trainer | OD-10 |
| `UNIQUE (campus_code)` | `campuses` | DBQ-15 |
| `CHECK (ADDITIONAL ⇒ VIRTUAL)`, `CHECK (trainer_name_text only on ADDITIONAL)` | `timetable_sessions` | DBQ-14 |
| `UNIQUE (student_id)` **covering deleted rows** — a Student ID is permanently reserved | `students` | DATA-01, **DBQ-08 approved** |

## 21. Index recommendations

Indexes created automatically by PK and UNIQUE constraints are **not** repeated here.

| Index | Justifies |
| --- | --- |
| `timetable_unit_deliveries (start_date, end_date)` | TT-03 date-range overlap — the most frequent query on Page 1 |
| `timetable_sessions (trainer_id, weekday)` | TT-06 trainer clash |
| `timetable_sessions (facility_id, weekday)` WHERE `facility_id IS NOT NULL` | TT-06 facility clash |
| `timetable_unit_deliveries (timetable_plan_id)` | Group clash and plan expansion |
| `students (student_group_id)`, `students (course_offering_id)` | Student filters and group rosters |
| `students (last_name, first_name)` | Name search on Page 2A |
| `course_offerings (college_id, campus_id)` | COL-01/COL-02 dependent filters |
| `qualification_units (qualification_id, delivery_order)` | TT-08 sequence retrieval |
| `trainer_availability (campus_id, weekday, mode_of_delivery)` | TRN-01/02 availability search |
| `trainer_qualifications (qualification_id)` | TRN-01 — the reverse direction of the PK |
| `import_staged_rows (import_batch_id, status)` | Staging grid and blocking-row counts |
| `user_activity_records (occurred_at DESC)` | Default Administration ordering |
| `user_activity_records (user_id, occurred_at DESC)` | Per-user history |
| Partial `WHERE is_deleted = false` on `students`, timetable tables | Every operational query excludes deleted rows |

Deliberately **not** indexed: `remarks`, every `*_snapshot` column, `raw_values`, and low-cardinality
booleans on small tables — a sequential scan of ten colleges beats an index lookup.

## 22. Historical-data approach

| Event | Behaviour | Snapshot needed? |
| --- | --- | --- |
| Trainer becomes inactive | `is_active = false`; existing sessions keep the FK and stay readable | No |
| Qualification superseded | Status change; existing offerings and students keep the FK | No |
| Facility becomes inactive | `is_active = false`; historical sessions still resolve the room | No |
| Course name changes | Propagates — treated as a correction | No |
| **User changes access level** | Activity records keep `access_level_snapshot` | **Yes** — §16.1 |
| Student soft-deleted | Row remains; activity records and import batches still resolve | No |
| Reason list changes (OD-06) | `reason_codes` deactivated, never deleted; historical FKs resolve | No |
| Student soft-deleted, then a new student needs that ID | **Rejected** — the ID is permanently reserved (DBQ-08). Restore the original record instead | No |

Snapshots are proposed in exactly one place. Everywhere else a foreign key plus a status column
preserves history without duplication.

## 23. Foreign-key delete behaviour

Default is **`ON DELETE RESTRICT`**. Reference and business data is never destroyed by deleting a
parent.

| Child → Parent | Action | Reason |
| --- | --- | --- |
| `import_staged_rows` → `import_batches` | **CASCADE** | True composition — a staged row has no meaning without its batch, and batches are transient working data |
| `import_row_issues` → `import_staged_rows` | **CASCADE** | Same; issues are recomputed on every revalidation |
| `timetable_sessions` → `timetable_unit_deliveries` | **CASCADE** | Composition. In practice deletion is soft, so this fires only during a genuine hard cleanup |
| `timetable_unit_deliveries` → `timetable_plans` | **CASCADE** | Same |
| `user_activity_records` → `users` | **RESTRICT** | An audit trail must not be destroyed by removing a user. Users are deactivated, never deleted |
| `students` → `course_offerings`, `student_groups` | **RESTRICT** | COL-05: retire the offering instead |
| `timetable_sessions` → `trainers`, `facilities` | **RESTRICT** | TRN-04, DATA-03 |
| `qualification_units` → `qualifications`, `units` | **RESTRICT** | COL-05 |
| `*.delete_reason_id` → `reason_codes` | **RESTRICT** | A used reason is deactivated, not removed |
| `users.*` → nothing | — | Users have no parent |

No `SET NULL` is proposed. Every nullable FK is nullable because the value is genuinely optional
(a virtual session has no facility; an unmatched sign-in has no user), not because a parent might
vanish.

## 24. Common technical fields — policy

| Field | Where | Why |
| --- | --- | --- |
| `created_at timestamptz NOT NULL DEFAULT now()` | Operationally edited tables: `users`, `students`, `student_groups`, `trainers`, `course_offerings`, timetable tables, `import_batches` | Basic operational forensics |
| `updated_at timestamptz` | Same set | "What changed recently" |
| `created_by` / `updated_by` | **Nowhere** | LOG-01/LOG-02 already record who did what, when, to which record, with a reason and a result. Duplicating that in every table produces a second, weaker audit trail that can disagree with the first |
| `deleted_by_user_id` | Soft-deletable tables only | **DATA-04 requires it explicitly** — the one place a user column is mandated |
| `is_active` / status | Reference tables only | DATA-03, COL-05 |
| Timestamps on pure junctions | **No** | `trainer_units` has nothing to audit that the activity record does not already cover |

The rule: **an audit column must earn its place.** The user activity record is the audit trail; table
columns exist for operational queries.

## 25. Open-decision impact

| OD | Area | Impact | Reason |
| --- | --- | --- | --- |
| OD-01 | Entra configuration | **C — no structural impact** | Tenant/app registration are configuration. `entra_object_id` accommodates any approved tenant. Access is never derived from a domain. |
| OD-02 | Sign-in record integration | **B** | If Graph retrieval is approved later, it adds a table; it does not change existing ones. |
| OD-03 | Session timeout | **C** | 30-min inactivity confirmed; **DBQ-02 approved: no session table.** Sessions are token-based. A maximum session duration remains unapproved but would not add a table. |
| OD-04 | Retention | **C** | Affects a purge job, not structure. |
| OD-05 | Admin boundary | **C** | Application authorisation. `access_level` already carries what is needed. |
| OD-06 | Reason lists | **B** | `reason_codes` is a lookup precisely so the list can change without redesign. Only the seed data waits. |
| OD-07 | Break rules | **B** | No break table is designed. If an academic calendar is approved it is additive. |
| OD-08 | Student calculations | **RESOLVED** | **DBQ-01 approved:** CT = Credit Transfer, flag only; staff select the approved Course Duration Option; the option is always shown and validated against the calculated duration; weeks are counted inclusively. All three parts of OD-08 are now answered. **Schema v1 is no longer blocked.** |
| OD-09 | Facility data | **C** | TT-15's minimum set is confirmed and DBQ-13 settles uniqueness. Extra approved fields would be additive. |
| OD-10 | Trainer delivery rule | **C** | Weekday mode is stored as entered. The rule is evaluation logic. |
| OD-11 | MSCRIS | **C — settled for schema purposes** | DBQ-14 approved: `session_type = 'ADDITIONAL'`, plus `session_title` and `trainer_name_text` confined by CHECK. Remaining OD-11 detail (when MSCRIS is mandatory) is application validation, not structure. |
| OD-12 | Performance target | **C** | Indexing tuning, not structure. |
| OD-13 | Production hosting | **C** | This schema is the input to that approval. |
| **OD-14** | **Time zone** | **C** | `timestamptz` is correct regardless of the display zone chosen. |
| **OD-15** | **Primary Country** | **B** | `text` now; a controlled list adds a lookup + FK without data loss. |
| **OD-16** | **Course cost scope** | **B** | `total_course_cost` is nullable; dropping it later is a trivial migration. |

**OD-08 was the only decision that blocked Schema v1, and it is now resolved (DBQ-01).** No open
decision currently blocks the design; the remainder are accommodated or additive.

## 26. Questions requiring approval

Fifteen questions were recorded in [`schema-open-questions.md`](schema-open-questions.md) and asked in
four groups, highest risk first. **All fifteen are answered.** Four answers went against the initial
recommendation — DBQ-04 (campus sharing), DBQ-11 (five weekday columns), DBQ-09 (exclude-only
duplicates) and DBQ-06 (RTO is the College) — and each is reflected in the design above.

## 27. Schema v1 approval checklist

All fifteen schema questions are answered and no open decision blocks the design. **The checklist was
confirmed and Schema v1 was approved on 10 August 2026 by the Project Owner.**

```
DATABASE SCHEMA V1 APPROVAL

[x] Entity list                          27 tables, 1 view, 15 enum types
[x] User/access structure                enum access_level, 3 values only            (§5)
[x] Data Editor assignment structure     separate enum + CHECK                       (§5.2)
[x] Entra user mapping structure         entra_object_id UUID, email not the key     (§6)
[x] College/campus structure             M:N via college_campuses                    DBQ-04
[x] Course/qualification relationship    separate; Page 4A IS the offering           (§7.2)
[x] Qualification/unit relationship      M:N + internal delivery_order               DBQ-05, DBQ-07
[x] Qualification offering model         UNIQUE (college, campus, qualification)     COL-04
[x] Student model                        7 of 21 fields derived, not stored          (§8)
[x] Student group model                  reference entity                            DBQ-10
[x] Credit Transfer structure            flag only; duration generated inclusively   DBQ-01
[x] Import staging model                 3 tables; duplicate_detected flag           DBQ-09
[x] Trainer model                        five weekday columns + unpivot view         DBQ-11
[x] Facility model                       TT-15 minimum; unique per campus            DBQ-13
[x] Timetable/session model              plan -> unit delivery -> session            DBQ-12
[x] MSCRIS representation                session_type = ADDITIONAL + 2 CHECKs        DBQ-14
[x] Activity-record model                FK + snapshot; 3 separate result fields     (§16)
[x] Soft-delete model                    columns on operational tables only          (§17)
[x] PK strategy                          bigint identity; business codes UNIQUE      (§18, §19)
[x] FK relationships                     34; 9 CASCADE, 25 RESTRICT, 0 SET NULL      (§23)
[x] Unique constraints                   26 UNIQUE, 11 CHECK                         (§20)
[x] Status/history model                 status over deletion for reference data     (§22)
[x] Session persistence decision         no user_sessions table                      DBQ-02
[x] Remaining schema blockers            none

    APPROVED — 10 August 2026, Project Owner
```

## 28. Known follow-up work (outside Schema v1)

Recorded so none of it is lost, and none of it is done in this step.

| Item | Why it is not part of Schema v1 |
| --- | --- |
| Frontend realignment to the current SRS (conflicts C-1…C-6) | `sequenceId`, `vetCode`/`courseName`, trainer `deliveryType`, the activity-record result fields and the 13-entry open-decision register all pre-date this SRS. A separate, reviewed step. |
| SRS §9.3 still names Streamlit | The build is Next.js. AC-12 requires the document and the build to agree — an SRS correction, not a schema change. |
| SRS §9.1 "active sessions" | Deliberately not implemented (DBQ-02). Worth an SRS note so the deviation is visible. |
| OD-07 break rules | No structure designed. An academic calendar would be additive. |
| OD-04 retention purge | A scheduled job under a maintenance role, not a table. |
| OD-15 Primary Country, OD-16 Course cost | Both accommodated as nullable columns; either can be tightened or dropped later. |
