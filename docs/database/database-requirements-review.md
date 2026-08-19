# TDMS database requirements review

**Step 1 — requirements analysis feeding Database Schema v1.**
Design and review only. No database, model or migration is created by this document.

---

## 1. Sources reviewed

| Source | Notes |
| --- | --- |
| `TDSM%20SRS_10-Aug-2026_1913-SGT.docx` (10 Aug 2026, **19:13**) | **Primary source of truth — current.** Adds the RTO definition (see C-13). |
| `TDSM SRS.docx` (10 Aug 2026, 15:50) | Superseded by the 19:13 file. Restructured SRS, 12 parts, 16 open decisions; newer than the SRS the frontend was built against. |
| `TDMS SRS (2).docx` (10 Aug 2026, 09:29) | Earlier v1.1 the frontend was built from. Used only to identify what changed. |
| `apps/web/src/types/*` | Frontend domain types (8 files) |
| `apps/web/src/mock-data/*` | Seeded demo dataset (12 files) |
| `apps/web/src/services/tdms-client.ts`, `mock-tdms-client.ts`, `api-tdms-client.ts` | Service contract and route map |
| `apps/web/src/types/auth.ts`, `lib/permissions.ts` | Access model |
| `apps/web/src/lib/open-decisions.ts` | Current open-decision working record (13 entries) |
| `README.md`, `docs/architecture/*` | Architecture and traceability |

All three SRS files are titled "Version 1.1". The 19:13 file is treated as current; the other two are
used only to detect what changed.

---

## 2. Changes in the current SRS that affect the database

These are changes against the SRS the frontend was built from. **The SRS wins.** Nothing in the
frontend has been modified in this step; the conflicts are recorded so Schema v1 follows the SRS
and the frontend can be realigned in a later, separate step.

> **C-1…C-6 RESOLVED 11 August 2026 (Step 5B §51).** All six turned out to be naming or
> format mappings against a schema that already modelled the SRS correctly — none needed a
> Schema v1 change. What was done, and the classification of each:
>
> | # | Frontend field (before) | Database field | Classification | Action taken |
> | --- | --- | --- | --- | --- |
> | C-1 | `QualificationUnitSequence.sequenceId`, displayed | `qualification_units.delivery_order` | NAMING MAPPING | Renamed to `deliveryOrder`. SRS §8.3 says a separate Sequence ID is not a Page 4B field, and the model already documents the ordinal as internal, so it orders rows and is no longer presented as a "Sequence ID" field. TT-08 still depends on it. |
> | C-2 | `CourseRecord.vetCode`, `.courseName` | `qualifications.qualification_code`, `.qualification_title` | NAMING MAPPING | Renamed to `qualificationCode` / `qualificationTitle` across types, forms, tables, exports and mock data. |
> | C-3 | `CourseRecord.location` free text | `campuses.campus_location` via `campus_id` | FORMAT MAPPING | Column removed. SRS §8.2: "Location represents the Campus value", and `campusId` already carried it. Location is now derived and shown read-only, so the two can no longer disagree. |
> | C-4 | RTO and Source URL absent | RTO = `colleges` (DBQ-06); `qualifications.source_url` | NAMING MAPPING | Both already existed in the schema. `sourceUrl` added to the Page 4B type; RTO remains the College. |
> | C-5 | `TrainerRecord.deliveryType` | `class_type` enum | NAMING MAPPING | Renamed to `classType` / `TrainerClassType` to match SRS §7.3. |
> | C-6 | single `result` field | `result`, `microsoft_sign_in_result`, `tdms_access_decision` | FORMAT MAPPING | The two separate outcome fields added to the frontend type. LOG-02 requires them distinct: "did Microsoft verify them?" and "did TDMS let them in?" are different questions, and a blocked account is a denial reason rather than a failed sign-in. |
>
> No REAL BUSINESS/SCHEMA CONFLICT was found among C-1…C-6, so nothing was asked and nothing
> in Schema v1 changed.

| # | Area | Earlier SRS / frontend | Current SRS | Database impact |
| --- | --- | --- | --- | --- |
| C-1 | Page 4B sequence | `Sequence ID` is a stored, displayed field (`QualificationUnitSequence.sequenceId`) | §8.3: "The order of Unit Code rows shown for each qualification represents the approved delivery sequence. **A separate Sequence ID is not used** in the Page 4B data structure." | **High.** A relational table has no inherent row order. TT-08 still requires schedules to follow the approved sequence, so the order *must* be persisted as an ordinal column even though it is not a displayed field. See DBQ-05. |
| C-2 | Page 4A field names | `vetCode`, `courseName` | §8.2: fields are **Qualification Code** and **Qualification Title**; "Qualification Code is the VET Code, and Qualification Title is the Course Name" | Naming only, but it confirms Page 4A rows are qualification-scoped. Feeds the course/qualification split. |
| C-3 | Page 4A location | `location` free text | §8/§8.2: "Location represents the **Campus** value" | Location becomes an FK to `campuses`, not a text column. |
| C-4 | Page 4B new fields | none | **RTO** and **Source URL** added | New attributes. RTO resolved by C-13 below. |
| C-5 | Trainer field name | `deliveryType` ("Delivery Type") | §7.3 **Class Type** (theory or practical); weekdays hold a **Mode of Delivery** value | Renames `class_type`; weekday value is the same domain as timetable Mode of Delivery. |
| C-6 | Activity record | single `result` field | §4.5 adds **Microsoft sign-in result** and **TDMS access decision** as *separate* fields alongside Result | Three distinct columns, not one. LOG-02 requires it. |
| C-7 | LOG-01 scope | sign in, create, edit, delete, import, export, restore, timetable save, override | adds **timetable generation**, **cancellation after updating**, **rejected save/update/import attempts** | More action values; no structural change. |
| C-8 | Bulk deletion | old BULK-12 required bulk deletion of production records | **Removed.** New BULK-12 is the import-result activity record | The bulk-delete gap previously flagged is no longer an SRS requirement. |
| C-9 | Duplicate handling | duplicates simply block the save | §6.2.3 + DATA-01: TDMS must show the duplicate and **require the user to choose how it is handled** before final save | Staged rows need a recorded duplicate *resolution*, not just a status. See DBQ-09. |
| C-10 | Course Duration Option | frontend: always shown, staff-selected (approved in a later session) | §6.1.3: TDMS calculates Actual Course Duration, user selects the option, **TDMS must validate the option against the calculated duration**; "hidden when the approved CT rule says it is not required" | Reintroduces the hidden-when-CT rule. Conflicts with a later verbal approval. See DBQ-01. |
| C-11 | Open decisions | 13 (OD-01…OD-13) | **16** — adds **OD-14 Time zone**, **OD-15 Primary Country entry method**, **OD-16 Course cost scope** | All three are schema-relevant. |
| C-12 | Web interface | Next.js/React built | §9.3 still lists **Streamlit** | No database impact. Flagged for SRS correction only (AC-12 requires document and build to agree). |
| **C-13** | **RTO** *(19:13 SRS)* | RTO undefined; possibly a separate entity | **§1.4: "RTO — The College value used in Page 4 reference data."** §8/§8.2: "RTO represents the College". **RTO added as a Page 4A Course Data field**: "The approved College represented by the RTO value for the course offering." COL-01 restated with the same wording | **None — confirms the existing design.** DBQ-06 already answered that RTO *is* the College, so `rtos` stays withdrawn and Page 4A's RTO column reads `course_offerings.college_id → colleges`. The SRS has now made explicit what was previously an approval. |

---

## 3. Requirements-to-Data Matrix

Status key: **C** = confirmed by SRS · **D** = derived technical requirement · **A** = requires approval

### 3.1 ACC — User access and responsibilities

| Req | Summary | Entities | Fields implied | Relationship | Constraint implied | Status |
| --- | --- | --- | --- | --- | --- | --- |
| ACC-01 | Only three access levels | `users` | `access_level` | — | Domain restricted to exactly 3 values | C |
| ACC-02 | Assignments are within Data Editor, not levels | `users` | `data_editor_assignment` | — | Separate domain from `access_level`; non-null only when level = Data Editor | C |
| ACC-03 | Super Admin ⊇ Admin ⊇ Data Editor | — | ordered access level | — | Ordered domain enables ≥ comparisons | D |
| ACC-04 | Admin ⊇ Data Editor + user mgmt + activity | — | — | — | Application layer | C |
| ACC-05 | Data Editor CRUD only in assigned area | `users` | `data_editor_assignment` | — | Application layer, driven by the column | C |
| ACC-06 | Buttons, nav and URLs enforce the same rules | — | — | — | Application layer | C |
| ACC-07 | Level/assignment change applies by next sign-in or refresh | `users` | `updated_at` | — | Access level read from `users` per request, not cached in a session row | D |
| ACC-08 | Denied action recorded when possible | `user_activity_records` | `tdms_access_decision`, `result` | user → activity | — | C |

### 3.2 AUTH — Login and authentication

| Req | Summary | Entities | Fields implied | Relationship | Constraint implied | Status |
| --- | --- | --- | --- | --- | --- | --- |
| AUTH-01/06 | Auth required for every operational route | — | — | — | Application layer | C |
| AUTH-02 | Entra tenant/app registration approved before release | *external config* | — | — | **Not database columns** — environment configuration | D |
| AUTH-03 | Never store or log the password | `users`, `user_activity_records` | — | — | No password/secret/token column may exist | C |
| AUTH-04 | Match verified account to **one** internal user | `users` | `entra_object_id`, `organisation_email` | 1:1 external identity → user | `entra_object_id` UNIQUE; `organisation_email` UNIQUE | C |
| AUTH-05 | Inactive/disabled/no-level denied | `users` | `account_status`, `access_level` | — | `account_status` domain | C |
| AUTH-07 | Land on Page 1 | — | — | — | Application layer | C |
| AUTH-08 | Failed sign-in creates no session | `user_activity_records` | `microsoft_sign_in_result` | — | — | C |
| AUTH-09 | Logout + inactivity expiry (30 min confirmed) | *token layer* | — | — | Evaluated: no session table required. See DBQ-02 | A |
| AUTH-10 | Safe error text | — | — | — | Application layer | C |
| AUTH-11 | Retain correlation ID / safe error reference | `user_activity_records` | `technical_reference` | — | — | C |
| AUTH-12 | Level/status change effective next sign-in/refresh | `users` | — | — | Same as ACC-07 | D |

### 3.3 LOG — User activity records

| Req | Summary | Entities | Fields implied | Relationship | Constraint implied | Status |
| --- | --- | --- | --- | --- | --- | --- |
| LOG-01 | Record for all listed actions | `user_activity_records` | `action` | — | Action domain incl. generation, cancellation-after-update, rejected attempts | C |
| LOG-02 | Required fields incl. **separate** MS result and TDMS decision | `user_activity_records` | 13 columns (§4.5) | user → activity (nullable) | Sign-in rows carry MS result + access decision; operational rows carry `result` | C |
| LOG-03 | Reason required for delete/restore/override; "Other" needs detail | `user_activity_records`, `reason_codes` | `reason_code_id`, `reason_detail` | reason → activity | CHECK: detail present when the reason requires it | C |
| LOG-04 | Only Super Admin/Admin may view | — | — | — | Application layer + DB grants | C |
| LOG-05 | Users must not change or delete activity records | `user_activity_records` | — | — | **No UPDATE/DELETE grant** to the application role | D |
| LOG-06 | No passwords or unnecessary personal data | — | — | — | Field-level discipline | C |
| LOG-07 | 3-month retention proposed, final period unapproved | `user_activity_records` | `occurred_at` | — | Archive strategy pending OD-04 | A |
| LOG-08 | Entra sign-in logs retained 7/30 days externally | *external* | — | — | Outside the TDMS database | C |

### 3.4 TT — Timetable View and Management

| Req | Summary | Entities | Fields implied | Relationship | Constraint implied | Status |
| --- | --- | --- | --- | --- | --- | --- |
| TT-02/03 | Filter by date range; show overlapping sessions | `timetable_unit_deliveries` | `start_date`, `end_date` | — | Index supporting range overlap | C |
| TT-04 | Create/generate then preview | — | — | — | Preview writes nothing | C |
| TT-05 | Use approved college/campus/qualification/unit/trainer/group/facility | all timetable tables | FKs | many | FK to reference data, not text | C |
| TT-06 | Prevent overlapping trainer/facility/group sessions unless approved override | `timetable_sessions`, override record | `weekday`, `start_time`, `end_time`, `trainer_id`, `facility_id` | session → trainer/facility | Overlap detection; override must be *recorded* | C |
| TT-07 | Show the conflicting record | — | — | — | Query returns the clashing row | C |
| TT-08 | Follow approved duration and unit sequence | `course_offerings`, `qualification_units` | `duration_weeks`, `delivery_order` | — | Ordering column required (see C-1) | C/D |
| TT-09/10/11 | Break placement rules | — | — | — | **Unapproved (OD-07).** No break table designed | A |
| TT-12 | Preview never saves | — | — | — | Application layer | C |
| TT-13 | Save/update/delete/cancel/export by access rules | — | — | — | — | C |
| TT-14 | These actions create activity records | `user_activity_records` | — | — | — | C |
| TT-15 | Facility must carry reference, campus, type, capacity, active status | `facilities` | 5 columns | facility → campus | capacity > 0 | C |

### 3.5 SST — Single Student Entry

| Req | Summary | Entities | Fields implied | Relationship | Constraint implied | Status |
| --- | --- | --- | --- | --- | --- | --- |
| SST-01 | Create/find/view/update/delete one student | `students` | — | — | — | C |
| SST-02 | College/campus/qualification/duration options from approved data | `course_offerings`, `offering_duration_options` | FKs | student → offering | — | C |
| SST-03 | Generate intake, group, qualification code, state, initial college email, duration | `students`, `student_groups` | derived vs stored split | — | Generated values should not be duplicated where derivable | C |
| SST-05 | Reject blank or duplicate Student ID | `students` | `student_id` | — | NOT NULL + UNIQUE | C |
| SST-06/07 | Save after validation and confirmation; show changed fields | — | — | — | Application layer | C |
| SST-08 | Delete shows record, needs reason, uses soft deletion | `students` | soft-delete columns | reason → student | — | C |
| SST-09 | Create/update/delete/rejected attempt creates an activity record | `user_activity_records` | — | — | — | C |
| SST-10 | CT definition, Course Duration Option rule, week calculation unapproved | `students` | `ct_student`, `course_duration_option_id`, duration | — | **Schema blocker.** See DBQ-01 | A |

### 3.6 BULK — Bulk Student Import

| Req | Summary | Entities | Fields implied | Relationship | Constraint implied | Status |
| --- | --- | --- | --- | --- | --- | --- |
| BULK-01 | Only approved CSV/XLSX | `import_batches` | `file_name` | — | Application layer | C |
| BULK-02 | Staging before any production write | `import_staged_rows` | raw values | rows → batch | Staged rows never write directly to `students` | C |
| BULK-03 | File name, upload time, user, source row number, counts | `import_batches`, `import_staged_rows` | listed columns | batch → user | — | C |
| BULK-04 | Validate columns, values, formats, duplicate IDs, mappings | `import_row_issues` | issue rows | issues → row | — | C |
| BULK-05 | Issue shows row, Student ID, message, status | `import_row_issues` | `field`, `message` | — | — | C |
| BULK-06 | Correct, choose duplicate handling, exclude, revalidate | `import_staged_rows` | `status`, `duplicate_detected`, `corrected` | — | DBQ-09 approved: exclude is the only resolution, so a flag replaces a resolution enum and keeps both BULK-09 counts correct | C |
| BULK-07 | Save blocked while a selected row is blocking | — | — | — | Application layer | C |
| BULK-08 | Confirmed set saved in one transaction | — | — | — | Transaction boundary | C |
| BULK-09 | Report inserted/excluded/duplicate/corrected/rejected/unmatched | `import_batches` | 6 count columns | — | Counts stored on the batch result | C |
| BULK-10 | Download preview and issue report | — | — | — | Read-only queries | C |
| BULK-12 | Import result creates an activity record | `user_activity_records` | — | — | — | C |

### 3.7 TRN — Trainer Data

| Req | Summary | Entities | Fields implied | Relationship | Constraint implied | Status |
| --- | --- | --- | --- | --- | --- | --- |
| TRN-01 | Qualification must be selected first | `trainer_qualifications` | — | trainer ↔ qualification | Junction table, not a text list | C |
| TRN-02 | Show count for the filters | — | — | — | Query | C |
| TRN-03 | Show trainer, units, locations, class type, weekday mode | `trainer_availability`, `trainer_units` | listed columns | junctions | — | C |
| TRN-04 | Inactive trainer kept for history, not selectable for new records | `trainers` | `is_active` | — | Never hard-delete a referenced trainer | C |
| TRN-05 | Export filtered result | — | — | — | — | C |
| TRN-06 | Only Admin/Super Admin maintain trainer data | — | — | — | Application layer | C |
| TRN-07 | Physical-to-virtual rule applied after approval | — | — | — | **Unapproved (OD-10).** No column invented | A |
| TRN-08 | Create/update/delete/export creates an activity record | — | — | — | — | C |

### 3.8 COL — College and Course Reference Data

| Req | Summary | Entities | Fields implied | Relationship | Constraint implied | Status |
| --- | --- | --- | --- | --- | --- | --- |
| COL-01 | College then only approved Campus. **RTO = College, Location = Campus** | `colleges`, `campuses`, `college_campuses` | composite FK on `course_offerings` | M:N (DBQ-04) | Composite FK to `college_campuses` | C |
| COL-02 | Show only data approved for the College/Campus filters | `course_offerings` | — | offering → college, campus, qualification | — | C |
| COL-03 | Names, codes, locations, durations, source refs and unit order from approved data | `qualifications`, `units`, `qualification_units` | `source_url`, `delivery_order` | — | — | C |
| COL-04 | The same college/campus/qualification offering must not be stored twice | `course_offerings` | — | — | **UNIQUE (college, campus, qualification)** | C |
| COL-05 | Inactive/superseded retained but not selectable for new records | `course_statuses` etc. | status columns | — | Status change, not deletion | C |
| COL-06 | Export by access rules | — | — | — | — | C |
| COL-07 | Only Admin/Super Admin maintain | — | — | — | Application layer | C |
| COL-08 | Create/update/delete/export creates an activity record | — | — | — | — | C |
| COL-09 | Facility structure and maintenance page approved separately | `facilities` | — | — | Minimum set only (TT-15) | A |

### 3.9 DATA — Data requirements

| Req | Summary | Entities | Constraint implied | Status |
| --- | --- | --- | --- | --- |
| DATA-01 | Student ID unique; import must not create a duplicate | `students` | UNIQUE on `student_id`; see DBQ-08 for interaction with soft delete | C |
| DATA-02 | Timetable assignments reference approved data, not duplicate descriptions | timetable tables | FKs, not text | C |
| DATA-03 | Inactive/superseded retained and excluded from new selections | reference tables | status columns + application filter | C |
| DATA-04 | Soft-deleted records store date, deleting user, reason, recovery deadline | all soft-deletable tables | 5 columns | C |
| DATA-05 | Multi-record save uses a transaction | — | Transaction boundary | C |
| DATA-06 | Development data separated from production | — | Separate databases | C |
| DATA-07 | Schema approved before production hosting | — | This document | C |

### 3.10 NFR and AC

| Req | Database consequence | Status |
| --- | --- | --- |
| NFR-01 Security | Least-privilege DB role; no UPDATE/DELETE on activity records; TLS | D |
| NFR-02 Privacy | Store only the SRS fields; no extra personal data | C |
| NFR-03 Reliability | Transactions; FK integrity; no partial import | C |
| NFR-05 Performance | Index recommendations only where a query justifies them. Target unapproved (OD-12) | A |
| NFR-06 Backup | Operational concern, not schema | C |
| NFR-08 Maintainability | Naming convention; migrations under version control | D |
| AC-12 | **Implemented field names must match the SRS.** Drives the C-1…C-6 realignment | C |

---

## 4. Requirements that deliberately produce **no** table

Recorded so the absence is a decision, not an oversight.

| Concept | Why no table in Schema v1 |
| --- | --- |
| Break rules / academic calendar | TT-09/10/11 and OD-07 are unapproved. Designing a calendar table now would encode an invented rule. |
| Microsoft Entra tenant / client / redirect | AUTH-02, OD-01. These are environment configuration, never database columns, and never committed. |
| Passwords, tokens, client secrets | AUTH-03 forbids storage. No column exists in any proposed table. |
| Microsoft sign-in log mirror | OD-02 unapproved; LOG-08 notes retention lives in Entra. Only the safe `technical_reference` is stored. |
| Physical/virtual trainer derivation | TRN-07, OD-10 unapproved. Weekday mode is stored exactly as entered; nothing is derived. |
| Performance/monitoring tables | OD-12 unapproved and not a schema concern. |

---

## 5. Frontend structures that Schema v1 does **not** carry forward

| Frontend structure | Reason |
| --- | --- |
| `QualificationUnitSequence.collegeId` / `campusId` | The frontend scoped the qualification-unit relationship per campus. The SRS scopes units to the **qualification**; Page 4 filtering flows through the offering. Duplicating unit rows per campus would breach DATA-02. See DBQ-07. |
| `CourseRecord.location` as text | Now an FK to `campuses` (C-3). |
| `TrainerRecord.qualificationsCanTeach: string[]`, `unitsCanTeach: string[]` | Arrays become junction tables (`trainer_qualifications`, `trainer_units`). |
| `TimetableSession.theory*/practical*/mscris*` triplication | Replaced by a single session table with a `session_type` discriminator. See §11 of the proposal. |
| `TimetableSession.qualificationName`, `theoryClassroomCapacity` | Derivable through FKs; storing them duplicates reference data (DATA-02). |
| `StudentRecord.state`, `qualificationCode`, `qualificationTitle`, `collegeId` | Derivable from campus / offering. See the student model section of the proposal. |
| `serialNumber` on trainers | A display sequence number, not data. Produced by the query (`ROW_NUMBER()`). |
