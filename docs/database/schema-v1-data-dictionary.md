# TDMS Schema v1 — data dictionary

**APPROVED — Schema v1, 10 August 2026, Project Owner.** Types are PostgreSQL.

**Length policy.** No `VARCHAR(n)` limit is invented. PostgreSQL `text` has no performance penalty
over `varchar(n)`, and an arbitrary cap becomes a production defect the first time real data exceeds
it. A limit is applied only where the value has a genuine external format (an ISO code, a fixed
enum). Where a maximum is genuinely unknown — names, titles, references, remarks — `text` is used and
the reason is stated.

Status key: **C** confirmed by SRS · **T** technical recommendation · **P** pending decision

---

## Enum types

| Type | Values | Source |
| --- | --- | --- |
| `access_level` | `DATA_EDITOR`, `ADMIN`, `SUPER_ADMIN` (declared in ascending privilege order) | ACC-01 |
| `data_editor_assignment` | `STUDENT_DATA_OFFICER`, `TIMETABLE_OFFICER` | ACC-02 |
| `account_status` | `ACTIVE`, `INACTIVE`, `DISABLED` | SRS §4.4 |
| `coe_status` | `COE`, `NON_COE` | SRS §6.1.3 |
| `uoc_type` | `THEORY`, `THEORY_AND_PRACTICAL` | SRS §5.3 |
| `mode_of_delivery` | `PHYSICAL`, `VIRTUAL` | SRS §5.3 |
| `weekday_mode` | `NOT_AVAILABLE`, `PHYSICAL`, `VIRTUAL` | SRS §7.3 |
| `weekday` | `MONDAY`…`FRIDAY` | SRS §7.3 |
| `class_type` | `THEORY`, `PRACTICAL` | SRS §7.3 (renamed from Delivery Type — conflict C-5) |
| `session_type` | `THEORY`, `PRACTICAL`, `ADDITIONAL` | SRS §5.3, §13 of proposal |
| `staged_row_status` | `READY`, `NEEDS_CORRECTION`, `DUPLICATE`, `UNMATCHED_REFERENCE`, `EXCLUDED_BY_USER` | SRS §6.2.3 |
| `activity_action` | `SIGN_IN`, `SIGN_OUT`, `CREATE`, `UPDATE`, `DELETE`, `RESTORE`, `IMPORT`, `EXPORT`, `TIMETABLE_SAVE`, `TIMETABLE_GENERATION`, `CANCELLATION_AFTER_UPDATE`, `OVERRIDE`, `ACCESS_DENIED` | LOG-01 |
| `activity_result` | `COMPLETED`, `REJECTED_BY_VALIDATION`, `CANCELLED_BY_USER`, `FAILED_SYSTEM_ERROR` | SRS §4.5 |
| `ms_sign_in_result` | `SUCCESS`, `FAILURE` | SRS §4.2 |
| `access_decision` | `GRANTED`, `DENIED` | SRS §4.2 |

Enums are used where the domain is **closed and stable**. Open-ended domains (course status, reason
codes) use lookup tables instead — see the proposal §7.5 and §16.

---

## Identity and access

### `users` — approved TDMS user accounts · Status C

| Column | Type | Null | Key | Meaning | Source | St |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | Internal key | technical | T |
| `entra_object_id` | `uuid` | Y | UQ | Stable Microsoft Entra identity. Null until first sign-in | AUTH-04 | C |
| `entra_tenant_id` | `uuid` | Y | | Only if guest tenants are ever admitted; otherwise configuration | AUTH-02 | T |
| `organisation_email` | `citext` | N | UQ | Organisation Microsoft account | AUTH-04 | C |
| `display_name` | `text` | N | | Name shown in TDMS. No length known | §4.5 | C |
| `access_level` | `access_level` | N | | Super Admin / Admin / Data Editor | ACC-01 | C |
| `data_editor_assignment` | `data_editor_assignment` | Y | | Only when `access_level = DATA_EDITOR` | ACC-02 | C |
| `account_status` | `account_status` | N | | Active / Inactive / Disabled | §4.4 | C |
| `last_sign_in_at` | `timestamptz` | Y | | Convenience for user management; the authoritative history is the activity record | §21 admin screen | T |
| `created_at` / `updated_at` | `timestamptz` | N | | | technical | T |

`CHECK (data_editor_assignment IS NULL OR access_level = 'DATA_EDITOR')`

**Never present:** password, password hash, token, secret, or any domain-based access rule (AUTH-03).

---

## Reference data

### `colleges` · Status C

| Column | Type | Null | Key | Meaning | Source | St |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical | T |
| `college_short_name` | `text` | N | UQ | e.g. `AIBT` | §8 filters | C |
| `college_full_name` | `text` | N | | e.g. `AIBT Global`. Rendered as the Page 4 **RTO** value | §8, C-13 | C |
| `email_domain` | `text` | Y | | Used to generate the initial College Email | §6.1.3 | C |
| `is_active` | `boolean` | N | | DATA-03 | DATA-03 | C |

> `email_domain` is used **only** to build a proposed student email string. It is not, and must not
> become, an access rule (see proposal §5.3).

### `campuses` — a physical delivery site · Status C

**DBQ-04 approved: a campus can be operated by more than one college**, so `college_id` is *not* a
column here. The relationship lives in `college_campuses`.

| Column | Type | Null | Key | Meaning | Source | St |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical | T |
| `campus_code` | `text` | N | UQ | Stable identity, e.g. `HOB`, `MEL-CBD`. Survives a rename or rebrand and gives bulk-import mapping something reliable to match on (**DBQ-15**) | technical | T |
| `campus_name` | `text` | N | | e.g. `Hobart`. Free to change; not the identity | §8 | C |
| `campus_location` | `text` | N | | Full address | §5.3 Campus Location | C |
| `state` | `text` | N | | Source of the student's State | §6.1.3 | C |
| `is_active` | `boolean` | N | | | DATA-03 | C |

### `college_campuses` — approved college/campus combinations · Status C (DBQ-04)

| Column | Type | Null | Key | Meaning | Source | St |
| --- | --- | --- | --- | --- | --- | --- |
| `college_id` | `bigint` | N | PK, FK | | COL-01 | C |
| `campus_id` | `bigint` | N | PK, FK | | COL-01 | C |
| `is_active` | `boolean` | N | | Retire a combination without deleting it | DATA-03 | C |

`PRIMARY KEY (college_id, campus_id)` · `UNIQUE (college_id, campus_id)` implied by the PK, which is
also the target of the composite foreign key from `course_offerings` — so COL-01 ("only a Campus
approved for that College") is enforced by the database rather than by application code.

### ~~`rtos`~~ — **withdrawn (DBQ-06, confirmed by SRS §1.4)**

The 19:13 SRS defines "RTO — The College value used in Page 4 reference data", so RTO is not a
separate entity. It is read from `colleges`:

| Page | Path |
| --- | --- |
| 4A Course Data | `course_offerings.college_id → colleges` |
| 4B Qualification and Unit Sequence | `qualification_units → qualifications → course_offerings → colleges`, filtered by the selected College |

No table and no `rto_id` column exist, and `qualifications` stays national rather than being owned by
one college. Which college attribute renders in the RTO column is a display choice.

### `qualifications` · Status C

| Column | Type | Null | Key | Meaning | Source | St |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical | T |
| `qualification_code` | `text` | N | UQ | VET qualification code, e.g. `BSB50420` | §8.2 | C |
| `qualification_title` | `text` | N | | = Course Name | §8.2 | C |
| `course_level` | `text` | Y | | e.g. Diploma | §8.2 | C |
| `field_of_education_broad` | `text` | Y | | | §8.2 | C |
| `field_of_education_narrow` | `text` | Y | | | §8.2 | C |
| `course_sector` | `text` | Y | | | §8.2 | C |
| `source_url` | `text` | Y | | Approved verification source | §8.3 Source URL | C |
| `is_active` | `boolean` | N | | | COL-05 | C |

> No `rto_id`: RTO is the College (DBQ-06), reached through `course_offerings`.

> Classification fields are nullable because the SRS does not mark them required and real VET extracts
> are frequently incomplete. Codes follow the national format but no length is imposed — a future
> qualification format change should not require a migration.

### `units` · Status C

| Column | Type | Null | Key | Meaning | Source | St |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical | T |
| `unit_code` | `text` | N | UQ | e.g. `BSBCMM511` | §8.3 | C |
| `unit_title` | `text` | N | | | §8.3 | C |
| `uoc_type` | `uoc_type` | Y | | Theory, or theory and practical | §5.3 UoC Type | C |
| `is_active` | `boolean` | N | | | COL-05 | C |

### `qualification_units` — approved units and their delivery order · Status C

| Column | Type | Null | Key | Meaning | Source | St |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical | T |
| `qualification_id` | `bigint` | N | FK | | §8.3 | C |
| `unit_id` | `bigint` | N | FK | | §8.3 | C |
| `delivery_order` | `integer` | N | | Approved teaching order. **Internal ordinal — never displayed as a Page 4B field** (DBQ-05) | TT-08 · DBQ-05 | C |
| soft-delete columns | | | | | DATA-04 | C |

`UNIQUE (qualification_id, unit_id)` · `UNIQUE (qualification_id, delivery_order) DEFERRABLE INITIALLY DEFERRED`

### `course_statuses` — lookup · Status T

| Column | Type | Null | Key | Meaning | Source | St |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical | T |
| `code` | `text` | N | UQ | `ACTIVE`, `INACTIVE`, `SUPERSEDED`, … | §8.2 | C |
| `label` | `text` | N | | | §8.2 | C |
| `selectable_for_new_records` | `boolean` | N | | Implements COL-05 / DATA-03 as data | COL-05 | T |
| `is_active` | `boolean` | N | | | technical | T |

Lookup rather than enum because §8.2 says "or in another approved status".

### `course_offerings` — Page 4A Course Data · Status C

| Column | Type | Null | Key | Meaning | Source | St |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical | T |
| `college_id` | `bigint` | N | FK* | **Page 4A "RTO"** — §1.4/§8.2: RTO is the College | §8.2, C-13 | C |
| `campus_id` | `bigint` | N | FK* | **Page 4A "Location"** — §8.2: Location is the Campus | §8.2, C-3 | C |
| `qualification_id` | `bigint` | N | FK | | §8.2 | C |
| `course_code` | `text` | N | UQ | Internal/source-system course code | §8.2 | C |
| `course_status_id` | `bigint` | N | FK | | §8.2 | C |
| `total_course_cost` | `numeric(12,2)` | Y | | Nullable — **OD-16** may remove it | §8.2, OD-16 | P |
| soft-delete columns | | | | | DATA-04 | C |
| `created_at` / `updated_at` | `timestamptz` | N | | | technical | T |

`UNIQUE (college_id, campus_id, qualification_id)` — **COL-04**

\* `FOREIGN KEY (college_id, campus_id) REFERENCES college_campuses (college_id, campus_id)` — one
**composite** foreign key rather than two separate ones, so an offering cannot be created for a
college/campus pair that has not been approved (COL-01, DBQ-04).

> `numeric(12,2)` not `float`: currency must not carry binary rounding error.

### `offering_duration_options` · Status T — **DBQ-03**

| Column | Type | Null | Key | Meaning | Source | St |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical | T |
| `course_offering_id` | `bigint` | N | FK | | §6.1.3 | C |
| `duration_weeks` | `integer` | N | | Approved option, e.g. 26/52/78/104 | §8.2, TT-11 | C |
| `is_active` | `boolean` | N | | | COL-05 | C |

`UNIQUE (course_offering_id, duration_weeks)` · `CHECK (duration_weeks > 0)`

### `facilities` · Status C (minimum set only, TT-15)

| Column | Type | Null | Key | Meaning | Source | St |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical | T |
| `facility_reference` | `text` | N | | Room/resource reference. Unique **within its campus** (DBQ-13), so every site may have its own `C1` | TT-15 | C |
| `campus_id` | `bigint` | N | FK | | TT-15 | C |
| `facility_type` | `text` | N | | Classroom, kitchen, workshop… Text not enum: **OD-09** may extend the list | TT-15, OD-09 | C |
| `capacity` | `integer` | N | | | TT-15 | C |
| `is_active` | `boolean` | N | | | TT-15 | C |

`UNIQUE (campus_id, facility_reference)` — **DBQ-13 approved** · `CHECK (capacity > 0)`

---

## Students

### `student_groups` · Status T — **DBQ-10** · amended by [Student Rules v1.1](student-rules-v1.1.md)

| Column | Type | Null | Key | Meaning | Source | St |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical | T |
| `group_code` | `text` | N | | Staff-selected `Group 1`…`Group 15`, or `N/A`. **Not globally unique** — see the constraint below | §6.1.3 Group | C |
| `course_offering_id` | `bigint` | N | FK | | §5.3 | C |
| `intake` | `date` | N | | First day of the proposed start month. Displayed as `DD-MMM-YYYY` | §6.1.3 Intake | C |
| `expected_class_size` | `integer` | Y | | Source for timetable Classroom Size | §5.3 | C |
| `is_active` | `boolean` | N | | | technical | T |
| `created_at` / `updated_at` | `timestamptz` | N | | | technical | T |

`UNIQUE (course_offering_id, intake, group_code)` — a group name is unique within
an offering and intake, so `Group 1` can exist for SIT40721/Aug-2026,
SIT40721/Jan-2027 and RII50520/Aug-2026 at once.

`CHECK (EXTRACT(DAY FROM intake) = 1)` — the intake is the first of the month.

### `students` · Status C

| Column | Type | Null | Key | Meaning | Source | St |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | Internal key | §19 | T |
| `student_id` | `text` | N | UQ | **Business key.** Unique across *all* rows including soft-deleted ones — a Student ID is permanently reserved (DBQ-08) | DATA-01, SST-05 | C |
| `student_group_id` | `bigint` | Y | FK | Group (generated). Nullable until generated | §6.1.3 | C |
| `course_offering_id` | `bigint` | N | FK | Carries college, campus and qualification | SST-02 | C |
| `course_duration_option_id` | `bigint` | Y | FK | Staff-selected approved option. Always shown; service layer validates it against the calculated duration | §6.1.3 · DBQ-01 | C |
| `college_email` | `citext` | N | | Generated, then editable; validated | §6.1.3 | C |
| `first_name` | `text` | N | | | §6.1.3 | C |
| `last_name` | `text` | Y | | SRS Required = No | §6.1.3 | C |
| `coe_status` | `coe_status` | N | | | §6.1.3 | C |
| `proposed_start_date` | `date` | N | | | §6.1.3 | C |
| `proposed_end_date` | `date` | N | | | §6.1.3 | C |
| `actual_course_duration_weeks` | `integer` GENERATED ALWAYS AS `round((proposed_end_date - proposed_start_date + 1) / 7.0)` STORED | N | | **Inclusive** date calculation (DBQ-01) | §6.1.3 · DBQ-01 | C |
| `ct_student` | `boolean` NOT NULL | N | | Credit Transfer: true = at least one approved CT. No unit detail stored (DBQ-01) | §6.1.3 · DBQ-01 | C |
| `personal_email` | `citext` | Y | | | §6.1.3 | C |
| `primary_phone` | `text` | Y | | No length: international formats vary | §6.1.3 | C |
| `primary_country` | `text` | Y | | **OD-15** may make this a FK to a controlled list | §6.1.3, OD-15 | P |
| `remarks` | `text` | Y | | | §6.1.3 | C |
| soft-delete columns | | | | | DATA-04, SST-08 | C |
| `created_at` / `updated_at` | `timestamptz` | N | | | technical | T |

`CHECK (proposed_end_date > proposed_start_date)`

**Not columns** — derived through FKs: College, Campus, State, Qualification Code, Qualification
Title, Intake. See proposal §8.1.

---

## Imports

### `import_batches` · Status C

| Column | Type | Null | Meaning | Source |
| --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | technical |
| `batch_reference` | `text` | N UQ | Displayed batch number | BULK-03 |
| `file_name` | `text` | N | | BULK-03 |
| `file_size_bytes` | `bigint` | Y | | technical |
| `uploaded_at` | `timestamptz` | N | | BULK-03 |
| `uploaded_by_user_id` | `bigint` | N FK | | BULK-03 |
| `row_count` | `integer` | N | Rows read from the file | BULK-03 |
| `status` | `text` | N | `STAGED`, `SAVED`, `ABANDONED` | BULK-02 |
| `inserted_count` … `unmatched_count` | `integer` | Y | Six result counts | **BULK-09** |
| `completed_at` | `timestamptz` | Y | Set when the transaction commits | BULK-08 |

### `import_staged_rows` · Status C

| Column | Type | Null | Meaning | Source |
| --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | technical |
| `import_batch_id` | `bigint` | N FK | CASCADE | BULK-02 |
| `source_row_number` | `integer` | N | Row number in the uploaded file | BULK-03/05 |
| `raw_values` | `jsonb` | N | The original cells exactly as uploaded | BULK-02 |
| `student_id_value` … `proposed_end_date_value` | `text` | Y | Working values, editable during correction | BULK-06 |
| `resolved_college_id` / `_campus_id` / `_qualification_id` / `_offering_id` | `bigint` | Y FK | Set when the mapping matches | BULK-04 |
| `status` | `staged_row_status` | N | | §6.2.3 |
| `duplicate_detected` | `boolean` | N | Set when the Student ID clashes with an existing or repeated row. **Survives exclusion**, so BULK-09's duplicate count and excluded count are both correct | C-9, DBQ-09 |
| `corrected` | `boolean` | N | Feeds the corrected count | BULK-09 |

`UNIQUE (import_batch_id, source_row_number)`

> Working values are `text`, not typed. A staged row exists precisely because the data may be
> invalid; typing the columns would reject the row before it could be shown and corrected.

### `import_row_issues` · Status T

| Column | Type | Null | Meaning | Source |
| --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | technical |
| `import_staged_row_id` | `bigint` | N FK | CASCADE | BULK-05 |
| `field_name` | `text` | N | Affected field | BULK-05 |
| `message` | `text` | N | Plain-language explanation | BULK-05, §2.4 |
| `issue_status` | `text` | N | e.g. `OPEN`, `RESOLVED` | BULK-05 |

---

## Trainers

### `trainers` · Status C

| Column | Type | Null | Key | Meaning | Source |
| --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical |
| `trainer_id` | `text` | N | UQ | Business trainer reference | §7.3 |
| `trainer_name` | `text` | N | | | §7.3 |
| `is_active` | `boolean` | N | | TRN-04 | TRN-04 |
| soft-delete columns | | | | | DATA-04 |

> `Serial Number` (§7.3) is **not** stored — it is a display sequence produced by `ROW_NUMBER()`.

### `trainer_availability` · Status C — **DBQ-11 approved: five weekday columns**

| Column | Type | Null | Key | Meaning | Source |
| --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical |
| `trainer_id` | `bigint` | N | FK | | §7.3 |
| `campus_id` | `bigint` | N | FK | Trainer Campus | §7.3 |
| `location` | `text` | Y | | City / approved location | §7.3 |
| `location_type` | `text` | Y | | Campus, kitchen, workshop… | §7.3 |
| `class_type` | `class_type` | N | | Theory or practical (renamed, C-5) | §7.3 |
| `working_time_start` | `time` | N | | Replaces the free-text "09:00 - 17:00" | §7.3 |
| `working_time_end` | `time` | N | | | §7.3 |
| `monday` | `weekday_mode` | N | | Not Available / Physical / Virtual | §7.3 |
| `tuesday` | `weekday_mode` | N | | | §7.3 |
| `wednesday` | `weekday_mode` | N | | | §7.3 |
| `thursday` | `weekday_mode` | N | | | §7.3 |
| `friday` | `weekday_mode` | N | | | §7.3 |

`UNIQUE (trainer_id, campus_id, class_type, working_time_start)` ·
`CHECK (working_time_end > working_time_start)`

The `weekday` enum is retained — it is still used by `timetable_sessions`.

### `trainer_availability_days` — **view, not a table**

Unpivots the five weekday columns so clash and availability queries stay single-predicate:

```
(availability_id, trainer_id, campus_id, class_type,
 working_time_start, working_time_end, weekday, mode_of_delivery)
```

Page 3 reads the table; TT-06 clash checking and TRN-01/02 availability search read the view. A view
holds no data of its own and cannot drift from the table.

### `trainer_qualifications` / `trainer_units` · Status C

| Column | Type | Null | Key | Source |
| --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | technical |
| `trainer_id` | `bigint` | N | FK | §7.4 |
| `qualification_id` / `unit_id` | `bigint` | N | FK | §7.4 |

`UNIQUE (trainer_id, qualification_id)` · `UNIQUE (trainer_id, unit_id)`

---

## Timetables

### `timetable_plans` · Status T — **DBQ-12**

| Column | Type | Null | Key | Meaning | Source |
| --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical |
| `plan_reference` | `text` | N | UQ | Displayed timetable record number | TT-14 |
| `student_group_id` | `bigint` | N | FK | | §5.3 Group |
| `course_offering_id` | `bigint` | N | FK | College, campus, qualification | §5.3 |
| `duration_weeks` | `integer` | N | | Approved duration for the group | §5.3 |
| `class_size_override` | `integer` | Y | | Only when it differs from the group | §5.3 Classroom Size |
| soft-delete + `created_at`/`updated_at` | | | | | DATA-04 |

### `timetable_unit_deliveries` · Status T — **DBQ-12**

| Column | Type | Null | Key | Meaning | Source |
| --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical |
| `timetable_plan_id` | `bigint` | N | FK | CASCADE | §5.3 |
| `unit_id` | `bigint` | N | FK | | §5.3 UoC Code |
| `mode_of_delivery` | `mode_of_delivery` | N | | | §5.3 |
| `start_date` | `date` | N | | UoC Start Date | §5.3 |
| `end_date` | `date` | N | | UoC End Date | §5.3 |
| `remarks` | `text` | Y | | | §5.3 |
| soft-delete columns | | | | | DATA-04 |

`UNIQUE (timetable_plan_id, unit_id)` · `CHECK (end_date >= start_date)`

> `uoc_type` is **not** duplicated here — it lives on `units`.

### `timetable_sessions` · Status T — **DBQ-12**

| Column | Type | Null | Key | Meaning | Source |
| --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical |
| `timetable_unit_delivery_id` | `bigint` | N | FK | CASCADE | §5.3 |
| `session_type` | `session_type` | N | | THEORY / PRACTICAL / ADDITIONAL | §5.3, §14 |
| `session_title` | `text` | Y | | Topic name for an additional class (DBQ-14) | §14, DBQ-14 |
| `weekday` | `weekday` | N | | | §5.3 Days and Times |
| `start_time` | `time` | N | | | §5.3 |
| `end_time` | `time` | N | | | §5.3 |
| `trainer_id` | `bigint` | Y | FK | Assigned trainer | §5.3 |
| `trainer_name_text` | `text` | Y | | Free-text trainer, **ADDITIONAL sessions only** (DBQ-14). Nullable; `trainer_id` is used for THEORY and PRACTICAL | DBQ-14 |
| `facility_id` | `bigint` | Y | FK | Null for a virtual session | §5.3 |
| `delivery_mode` | `mode_of_delivery` | N | | | §5.3 |

`CHECK (end_time > start_time)`

`CHECK (session_type <> 'ADDITIONAL' OR delivery_mode = 'VIRTUAL')` — MSCRIS is virtual only (DBQ-14)

`CHECK (session_type = 'ADDITIONAL' OR trainer_name_text IS NULL)` — free-text trainer is confined to
additional classes, so THEORY and PRACTICAL cannot bypass approved trainer data (DATA-02)

No "facility required when physical" CHECK: MSCRIS is virtual-only and therefore never needs a room,
and a theory or practical session may legitimately be scheduled before a room is allocated.

> Classroom **Capacity** is not stored — it is read from `facilities.capacity` (DATA-02).

### `timetable_clash_overrides` · Status T

| Column | Type | Null | Key | Meaning | Source |
| --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical |
| `timetable_session_id` | `bigint` | N | FK | Session that was saved despite a clash | TT-06 |
| `conflicting_session_id` | `bigint` | Y | FK | The other session | TT-07 |
| `reason_code_id` | `bigint` | N | FK | | LOG-03 |
| `reason_detail` | `text` | Y | | Required when the reason demands it | LOG-03 |
| `approved_by_user_id` | `bigint` | N | FK | Who approved — **OD-06** | TT-06 |
| `approved_at` | `timestamptz` | N | | | TT-06 |

---

## Audit and control

### `user_activity_records` · Status C

| Column | Type | Null | Meaning | Source |
| --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK; displayed as `ACT-000123` | §4.5 |
| `occurred_at` | `timestamptz` | N | Stored UTC; display zone per **OD-14** | §4.5 |
| `user_id` | `bigint` | Y FK | Null for "Unmatched user" | §4.3, §4.5 |
| `user_reference_snapshot` | `text` | N | Email, or `Unmatched user` | §4.5 |
| `access_level_snapshot` | `access_level` | Y | **Level at the time of the action** | §4.5, §7 of brief |
| `assignment_snapshot` | `data_editor_assignment` | Y | Assignment at the time | §4.5 |
| `page_or_function` | `text` | N | e.g. `Page 2B - Bulk Student Import` | §4.5 |
| `action` | `activity_action` | N | | LOG-01 |
| `record_reference` | `text` | Y | Student ID, timetable reference, batch reference | §4.5 |
| `reason_code_id` | `bigint` | Y FK | | LOG-03 |
| `reason_detail` | `text` | Y | Required when the reason demands it | LOG-03 |
| `result` | `activity_result` | Y | Operational actions | §4.5 |
| `microsoft_sign_in_result` | `ms_sign_in_result` | Y | Sign-in/access rows only | **§4.5, LOG-02** |
| `tdms_access_decision` | `access_decision` | Y | Sign-in/access rows only | **§4.5, LOG-02** |
| `technical_reference` | `text` | Y | Correlation ID or safe error reference | AUTH-11 |
| `plain_language_detail` | `text` | N | No password or unnecessary personal data | LOG-06 |

`CHECK (result IS NOT NULL OR microsoft_sign_in_result IS NOT NULL OR tdms_access_decision IS NOT NULL)`

**No `updated_at`, no `deleted_at`.** The table is append-only; LOG-05 is enforced by withholding
`UPDATE`/`DELETE` from the application role.

### `reason_codes` · Status C (values pending OD-06)

| Column | Type | Null | Key | Meaning | Source |
| --- | --- | --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK | | technical |
| `code` | `text` | N | UQ | | §4.6 |
| `label` | `text` | N | | Text shown in the dropdown | §4.6 |
| `requires_detail` | `boolean` | N | | True for "Other" | LOG-03 |
| `is_active` | `boolean` | N | | Retire, never delete | §4.6 |
| `display_order` | `integer` | N | | | technical |

### `reason_code_contexts` · Status T

| Column | Type | Null | Key | Meaning | Source |
| --- | --- | --- | --- | --- | --- |
| `reason_code_id` | `bigint` | N | FK | | §4.6 |
| `context` | `text` | N | | `STUDENT_DELETE`, `TIMETABLE_DELETE`, `RESTORE`, `OVERRIDE`, … | §4.6 |

`PRIMARY KEY (reason_code_id, context)`

Lets the approved list differ per action without a schema change when OD-06 is settled.

---

## Soft-delete column group

Applied to `students`, `course_offerings`, `qualification_units`, `trainers`, `timetable_plans`,
`timetable_unit_deliveries`, `timetable_sessions`.

| Column | Type | Null | Source |
| --- | --- | --- | --- |
| `is_deleted` | `boolean` NOT NULL DEFAULT false | N | §2.4 |
| `deleted_at` | `timestamptz` | Y | DATA-04 |
| `deleted_by_user_id` | `bigint` FK→users | Y | DATA-04 |
| `delete_reason_id` | `bigint` FK→reason_codes | Y | DATA-04, LOG-03 |
| `delete_reason_detail` | `text` | Y | LOG-03 |
| `recovery_deadline` | `date` | Y | DATA-04 (14 days proposed) |

`CHECK (is_deleted = false OR (deleted_at IS NOT NULL AND deleted_by_user_id IS NOT NULL AND delete_reason_id IS NOT NULL AND recovery_deadline IS NOT NULL))`
