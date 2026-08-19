# TDMS Schema v1 — proposed ERD

**APPROVED — Schema v1, 10 August 2026, Project Owner.** Documentation only — no DDL is generated from this file.

Mermaid cannot style entities conditionally, so **entities that depend on an unresolved decision are
listed beneath the diagram** rather than shown differently inside it.

---

## 1. Identity, access and audit

```mermaid
erDiagram
    users ||--o{ user_activity_records : "acted (nullable)"
    users ||--o{ import_batches : uploaded
    reason_codes ||--o{ user_activity_records : "reason for"
    reason_codes ||--o{ reason_code_contexts : "applies in"

    users {
        bigint id PK
        uuid entra_object_id UK "nullable until first sign-in"
        citext organisation_email UK
        text display_name
        access_level access_level "3 values only"
        data_editor_assignment data_editor_assignment "null unless Data Editor"
        account_status account_status
        timestamptz last_sign_in_at
    }
    user_activity_records {
        bigint id PK
        timestamptz occurred_at
        bigint user_id FK "null = Unmatched user"
        text user_reference_snapshot
        access_level access_level_snapshot "level AT TIME OF ACTION"
        data_editor_assignment assignment_snapshot
        text page_or_function
        activity_action action
        text record_reference
        bigint reason_code_id FK
        text reason_detail
        activity_result result
        ms_sign_in_result microsoft_sign_in_result
        access_decision tdms_access_decision
        text technical_reference
        text plain_language_detail
    }
    reason_codes {
        bigint id PK
        text code UK
        text label
        boolean requires_detail
        boolean is_active
    }
    reason_code_contexts {
        bigint reason_code_id PK_FK
        text context PK
    }
```

## 2. Reference data

```mermaid
erDiagram
    colleges ||--o{ college_campuses : "operates at"
    campuses ||--o{ college_campuses : "shared by"
    college_campuses ||--o{ course_offerings : "approved pair offers"
    qualifications ||--o{ course_offerings : "offered as"
    campuses ||--o{ facilities : contains
    qualifications ||--o{ qualification_units : includes
    units ||--o{ qualification_units : "used in"
    course_statuses ||--o{ course_offerings : classifies
    course_offerings ||--o{ offering_duration_options : "approved durations"

    colleges {
        bigint id PK
        text college_short_name UK
        text college_full_name "= Page 4 RTO value"
        text email_domain "email generation only, never access"
        boolean is_active
    }
    campuses {
        bigint id PK
        text campus_code UK "stable identity"
        text campus_name "free to change"
        text campus_location
        text state "source of student State"
        boolean is_active
    }
    college_campuses {
        bigint college_id PK_FK
        bigint campus_id PK_FK
        boolean is_active
    }
    qualifications {
        bigint id PK
        text qualification_code UK "= VET Code"
        text qualification_title "= Course Name"
        text course_level
        text field_of_education_broad
        text field_of_education_narrow
        text course_sector
        text source_url
        boolean is_active
    }
    units {
        bigint id PK
        text unit_code UK
        text unit_title
        uoc_type uoc_type
        boolean is_active
    }
    qualification_units {
        bigint id PK
        bigint qualification_id FK
        bigint unit_id FK
        int delivery_order "internal ordinal, not displayed"
    }
    course_offerings {
        bigint id PK
        bigint college_id FK "Page 4A RTO - composite FK"
        bigint campus_id FK "Page 4A Location - composite FK"
        bigint qualification_id FK
        text course_code UK
        bigint course_status_id FK
        numeric total_course_cost "nullable, OD-16"
    }
    offering_duration_options {
        bigint id PK
        bigint course_offering_id FK
        int duration_weeks
        boolean is_active
    }
    facilities {
        bigint id PK
        text facility_reference
        bigint campus_id FK
        text facility_type
        int capacity
        boolean is_active
    }
    course_statuses {
        bigint id PK
        text code UK
        text label
        boolean selectable_for_new_records
    }
```

## 3. Students and bulk import

```mermaid
erDiagram
    course_offerings ||--o{ student_groups : "group of"
    course_offerings ||--o{ students : "enrolled in"
    student_groups ||--o{ students : contains
    offering_duration_options ||--o{ students : "selected duration"
    import_batches ||--o{ import_staged_rows : contains
    import_staged_rows ||--o{ import_row_issues : "has issues"

    student_groups {
        bigint id PK
        text group_code UK
        bigint course_offering_id FK
        text intake
        int expected_class_size
        boolean is_active
    }
    students {
        bigint id PK
        text student_id UK "BUSINESS KEY - permanently reserved"
        bigint student_group_id FK
        bigint course_offering_id FK "carries college, campus, qualification"
        bigint course_duration_option_id FK
        citext college_email
        text first_name
        text last_name "optional per SRS"
        coe_status coe_status
        date proposed_start_date
        date proposed_end_date
        int actual_course_duration_weeks "GENERATED - inclusive dates"
        boolean ct_student "Credit Transfer - flag only"
        citext personal_email
        text primary_phone
        text primary_country "OD-15"
        text remarks
        boolean is_deleted
    }
    import_batches {
        bigint id PK
        text batch_reference UK
        text file_name
        timestamptz uploaded_at
        bigint uploaded_by_user_id FK
        int row_count
        int inserted_count
        int excluded_count
        int duplicate_count
        int corrected_count
        int rejected_count
        int unmatched_count
    }
    import_staged_rows {
        bigint id PK
        bigint import_batch_id FK
        int source_row_number
        jsonb raw_values "original cells as uploaded"
        text student_id_value
        bigint resolved_offering_id FK
        staged_row_status status
        boolean duplicate_detected "keeps BULK-09 counts correct"
        boolean corrected
    }
    import_row_issues {
        bigint id PK
        bigint import_staged_row_id FK
        text field_name
        text message
        text issue_status
    }
```

## 4. Trainers, facilities and timetables

```mermaid
erDiagram
    trainers ||--o{ trainer_availability : "available at"
    trainers ||--o{ trainer_qualifications : "can teach"
    trainers ||--o{ trainer_units : "can deliver"
    qualifications ||--o{ trainer_qualifications : "taught by"
    units ||--o{ trainer_units : "delivered by"
    campuses ||--o{ trainer_availability : at

    student_groups ||--o{ timetable_plans : "timetabled as"
    course_offerings ||--o{ timetable_plans : for
    timetable_plans ||--o{ timetable_unit_deliveries : schedules
    units ||--o{ timetable_unit_deliveries : "unit delivered"
    timetable_unit_deliveries ||--o{ timetable_sessions : "weekly slots"
    trainers ||--o{ timetable_sessions : teaches
    facilities ||--o{ timetable_sessions : "held in"
    timetable_sessions ||--o{ timetable_clash_overrides : "override recorded"

    trainers {
        bigint id PK
        text trainer_id UK
        text trainer_name
        boolean is_active "TRN-04"
        boolean is_deleted
    }
    trainer_availability {
        bigint id PK
        bigint trainer_id FK
        bigint campus_id FK
        text location
        text location_type
        class_type class_type "Theory or Practical"
        time working_time_start
        time working_time_end
        weekday_mode monday
        weekday_mode tuesday
        weekday_mode wednesday
        weekday_mode thursday
        weekday_mode friday
    }
    trainer_qualifications {
        bigint id PK
        bigint trainer_id FK
        bigint qualification_id FK
    }
    trainer_units {
        bigint id PK
        bigint trainer_id FK
        bigint unit_id FK
    }
    timetable_plans {
        bigint id PK
        text plan_reference UK
        bigint student_group_id FK
        bigint course_offering_id FK
        int duration_weeks
        int class_size_override
        boolean is_deleted
    }
    timetable_unit_deliveries {
        bigint id PK
        bigint timetable_plan_id FK
        bigint unit_id FK
        mode_of_delivery mode_of_delivery
        date start_date
        date end_date
        text remarks
        boolean is_deleted
    }
    timetable_sessions {
        bigint id PK
        bigint timetable_unit_delivery_id FK
        session_type session_type "THEORY PRACTICAL ADDITIONAL"
        text session_title "topic for additional class"
        text trainer_name_text "free text - ADDITIONAL only"
        weekday weekday
        time start_time
        time end_time
        bigint trainer_id FK
        bigint facility_id FK "null when virtual"
        mode_of_delivery delivery_mode
        boolean is_deleted
    }
    timetable_clash_overrides {
        bigint id PK
        bigint timetable_session_id FK
        bigint conflicting_session_id FK
        bigint reason_code_id FK
        text reason_detail
        bigint approved_by_user_id FK
        timestamptz approved_at
    }
```

---

## 5. Entities that depend on an unresolved decision

Mermaid shows these as ordinary entities above. Their real status is:

| Entity / column | Depends on | If the decision goes the other way |
| --- | --- | --- |
| `offering_duration_options` | **DBQ-03** | Replaced by a single `course_offerings.duration_weeks` column |
| `qualification_units.delivery_order` | **DBQ-05** | Removed — but then TT-08 cannot be implemented |
| `student_groups` | **DBQ-10** | Replaced by a `group_code text` column on `students` and `timetable_plans` |
| `trainer_availability` (row per weekday) | **DBQ-11** | Replaced by `monday`…`friday` columns on one availability row |
| `timetable_plans` / `_unit_deliveries` / `_sessions` split | **DBQ-12** | Collapses to one wide table mirroring the current frontend shape |
| `timetable_sessions.session_title`, `trainer_name_text`, facility CHECK | **DBQ-14** | Removed if MSCRIS uses approved trainer data and needs no topic name |
| `students.primary_country` | **OD-15** | Becomes an FK to a controlled country list |
| `course_offerings.total_course_cost` | **OD-16** | Dropped |
| `academic_calendar_breaks` *(not drawn)* | **OD-07** | Added only when break rules are approved |

### Settled by Group 1 — no longer conditional

| Item | Decision |
| --- | --- |
| `college_campuses` junction | **DBQ-04: added.** A campus can be operated by more than one college |
| `rtos` table | **DBQ-06: not built** — and SRS §1.4 now defines RTO as the College value |
| `offering_duration_options` | **DBQ-03: added.** An offering carries several approved durations |
| `students.ct_student` boolean | **DBQ-01: confirmed.** No CT unit tables |
| `students.actual_course_duration_weeks` GENERATED | **DBQ-01: confirmed.** Inclusive dates |
| `user_sessions` | **DBQ-02: not built.** Sessions are token-based |

## 6. Reading the diagram

- `PK` primary key · `FK` foreign key · `UK` unique
- All primary keys are `bigint GENERATED ALWAYS AS IDENTITY`; business codes are separate `UNIQUE`
  columns (proposal §18).
- Soft-delete column groups are abbreviated to `is_deleted` in the diagram; the full six-column group
  is in the data dictionary.
- `created_at` / `updated_at` are omitted from the diagram for readability; the policy is in
  proposal §24.
