# TDMS Schema v1 — relationship matrix

**APPROVED — Schema v1, 10 August 2026, Project Owner.**

Default foreign-key behaviour is **`ON DELETE RESTRICT`**. `CASCADE` appears only where the child is
a true composition of its parent, and each instance is justified below.

---

## 1. Relationship matrix

| # | Parent | Child | Card. | FK location | On delete | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **`colleges` ↔ `campuses`** | — | **M:N** | via `college_campuses` | RESTRICT both sides | **DBQ-04 approved.** A physical campus can be operated by more than one college. `course_offerings` carries a *composite* FK to `college_campuses (college_id, campus_id)`, so COL-01 is enforced by the database |
| 2 | `qualifications` | `qualification_units` | 1:N | `qualification_units.qualification_id` | RESTRICT | COL-05 — a qualification in use is retired, never deleted |
| 3 | `units` | `qualification_units` | 1:N | `qualification_units.unit_id` | RESTRICT | Same |
| 4 | **`qualifications` ↔ `units`** | — | **M:N** | via `qualification_units` | — | A unit is reused across qualifications; the junction carries `delivery_order` (**DBQ-05**) |
| 5 | `college_campuses` | `course_offerings` | 1:N | **composite FK** `(college_id, campus_id)` | RESTRICT | COL-01 + COL-02. One composite FK replaces two separate ones so an unapproved college/campus pair cannot be offered |
| 6 | `qualifications` | `course_offerings` | 1:N | `course_offerings.qualification_id` | RESTRICT | §8.2 |
| 7 | `course_statuses` | `course_offerings` | 1:N | `course_offerings.course_status_id` | RESTRICT | COL-05 |
| 8 | `course_offerings` | `offering_duration_options` | 1:N | `offering_duration_options.course_offering_id` | CASCADE | Composition — an option has no meaning without its offering. **DBQ-03** |
| 9 | `campuses` | `facilities` | 1:N | `facilities.campus_id` | RESTRICT | TT-15 |
| 10 | `course_offerings` | `student_groups` | 1:N | `student_groups.course_offering_id` | RESTRICT | §5.3, **DBQ-10** |
| 11 | **`course_offerings` → `students`** | | 1:N | `students.course_offering_id` | RESTRICT | Carries college, campus and qualification for the student (proposal §8.1) |
| 12 | **`student_groups` → `students`** | | 1:N | `students.student_group_id` | RESTRICT | §6.1.3 Group |
| 13 | `offering_duration_options` | `students` | 1:N | `students.course_duration_option_id` | RESTRICT | §6.1.3. Database guarantees the option belongs to the student's own offering |
| 14 | **`student_groups` → `timetable_plans`** | | 1:N | `timetable_plans.student_group_id` | RESTRICT | §5.3 Group. Shared group entity is why the student-group clash check works |
| 15 | `course_offerings` | `timetable_plans` | 1:N | `timetable_plans.course_offering_id` | RESTRICT | §5.3 |
| 16 | **`timetable_plans` → `timetable_unit_deliveries`** | | 1:N | `…unit_deliveries.timetable_plan_id` | **CASCADE** | Composition. Deletion is normally soft; cascade applies only to a genuine hard cleanup |
| 17 | `units` | `timetable_unit_deliveries` | 1:N | `…unit_deliveries.unit_id` | RESTRICT | DATA-02, TRN-04-style history protection |
| 18 | **`timetable_unit_deliveries` → `timetable_sessions`** | | 1:N | `…sessions.timetable_unit_delivery_id` | **CASCADE** | Composition — a slot cannot exist without its unit delivery |
| 19 | **`trainers` → `timetable_sessions`** | | 1:N | `timetable_sessions.trainer_id` | RESTRICT | TRN-04 — an inactive trainer must remain resolvable in historical records |
| 20 | **`facilities` → `timetable_sessions`** | | 1:N | `timetable_sessions.facility_id` | RESTRICT | DATA-03 |
| 21 | `timetable_sessions` | `timetable_clash_overrides` | 1:N | `…overrides.timetable_session_id` | CASCADE | Composition — the override describes that session |
| 22 | `trainers` | `trainer_availability` | 1:N | `trainer_availability.trainer_id` | CASCADE | Composition — availability belongs to the trainer |
| 23 | `campuses` | `trainer_availability` | 1:N | `trainer_availability.campus_id` | RESTRICT | §7.3 Trainer Campus |
| 24 | **`trainers` ↔ `qualifications`** | — | **M:N** | via `trainer_qualifications` | CASCADE from trainer, RESTRICT to qualification | §7.4. Replaces the comma-separated list |
| 25 | **`trainers` ↔ `units`** | — | **M:N** | via `trainer_units` | CASCADE from trainer, RESTRICT to unit | §7.4 |
| 26 | **`import_batches` → `import_staged_rows`** | | 1:N | `import_staged_rows.import_batch_id` | **CASCADE** | Composition. Staged rows are transient working data with no independent meaning |
| 27 | **`import_staged_rows` → `import_row_issues`** | | 1:N | `import_row_issues.import_staged_row_id` | **CASCADE** | Issues are recomputed on every revalidation |
| 28 | `users` | `import_batches` | 1:N | `import_batches.uploaded_by_user_id` | RESTRICT | BULK-03 — the uploading user must stay resolvable |
| 29 | `course_offerings` | `import_staged_rows` | 1:N | `…rows.resolved_offering_id` | RESTRICT | BULK-04 mapping result |
| 30 | **`users` → `user_activity_records`** | | 1:N | `user_activity_records.user_id` (nullable) | **RESTRICT** | LOG-05. The audit trail must survive; users are deactivated, never deleted. Nullable for "Unmatched user" (§4.3) |
| 31 | `reason_codes` | `user_activity_records` | 1:N | `…records.reason_code_id` | RESTRICT | LOG-03 |
| 32 | `reason_codes` | `reason_code_contexts` | 1:N | `reason_code_contexts.reason_code_id` | CASCADE | Composition |
| 33 | `reason_codes` | soft-deleted rows | 1:N | `*.delete_reason_id` | RESTRICT | DATA-04 — a used reason is deactivated, not deleted |
| 34 | `users` | soft-deleted rows | 1:N | `*.deleted_by_user_id` | RESTRICT | DATA-04 |

**Totals: 34 relationships — 30 one-to-many, 4 many-to-many (via junctions), 0 one-to-one.**
9 CASCADE (all compositions), 25 RESTRICT, 0 SET NULL.

The four many-to-many relationships are: college ↔ campus, qualification ↔ unit,
trainer ↔ qualification, trainer ↔ unit. Each junction carries either business data
(`delivery_order`) or an approval flag (`is_active`), so none is a bare link table.

## 2. Why no `SET NULL` anywhere

Every nullable foreign key in this design is nullable because the value is **genuinely optional**, not
because a parent might disappear:

- `timetable_sessions.facility_id` — a virtual session has no room.
- `timetable_sessions.trainer_id` — a slot may be scheduled before a trainer is assigned.
- `user_activity_records.user_id` — an unmatched sign-in has no verified user (§4.3).
- `students.student_group_id` — the group is generated and may not exist at first save.
- `students.course_duration_option_id` — nullable because the SRS marks Course Duration Option Conditional (§6.1.3); the value is staff-selected, not derived (DBQ-01).

`SET NULL` would silently erase a real relationship when a parent is removed. Since no parent in this
schema is ever hard-deleted, the situation should not arise; `RESTRICT` makes that guarantee explicit
rather than hoping.

## 3. Relationships the brief asked to be reviewed

| Asked | Answer |
| --- | --- |
| College → Campus | **M:N** via `college_campuses` — approved under DBQ-04 |
| Qualification ↔ Unit | **M:N** via `qualification_units`, junction carries `delivery_order` |
| Trainer ↔ Qualification | **M:N** via `trainer_qualifications` |
| Trainer ↔ Unit | **M:N** via `trainer_units` |
| Qualification Offering → Student | **1:N** — and it replaces four columns on `students` |
| RTO → anything | **No relationship.** RTO is the College (SRS §1.4), read through `course_offerings.college_id` |
| Student Group → Student | **1:N** |
| Student Group → Timetable | **1:N** to `timetable_plans` |
| Timetable → Unit schedule | `timetable_plans` **1:N** `timetable_unit_deliveries` |
| Timetable Session → Trainer | **N:1**, RESTRICT, nullable |
| Timetable Session → Facility | **N:1**, RESTRICT, nullable for virtual |
| Import Batch → Staged Rows | **1:N**, CASCADE |
| User → Activity Records | **1:N**, RESTRICT, nullable child FK |

## 4. Cardinality notes worth confirming

| Relationship | Assumption made | Risk if wrong | Question |
| --- | --- | --- | --- |
| Campus can be shared between colleges | **M:N — decided** | — | DBQ-04 ✔ |
| Unit sequence is per qualification, not per campus | one `qualification_units` set | Would need `course_offering_id` in the key and duplicate rows per campus | **DBQ-07** |
| An offering has several approved durations | **child table — decided** | — | DBQ-03 ✔ |
| A student belongs to one group | 1:N | A student moving group loses history unless a history table is added | none raised — no SRS requirement for group history |
| A group belongs to one offering | 1:N | — | none raised |
