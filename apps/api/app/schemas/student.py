"""Student Data request and response shapes.

snake_case on the wire, matching the newer always-real modules (allocation and
rolling timetable) that the frontend `students-api.ts` client mirrors.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


class StudentRead(BaseModel):
    """A student record with its reference values resolved for display.

    College, Campus, State, Qualification and Intake are reached through foreign
    keys (DATA-02); the service joins them so the client never re-resolves.
    """

    id: int
    student_id: str
    first_name: str
    last_name: str | None = None
    college_email: str
    coe_status: str
    ct_student: bool
    status: str
    intake_match_status: str

    proposed_start_date: dt.date
    proposed_end_date: dt.date
    actual_course_duration_weeks: int

    personal_email: str | None = None
    primary_phone: str | None = None
    remarks: str | None = None

    course_offering_id: int
    student_group_id: int | None = None

    # Derived / joined display values (never stored on the student row).
    college: str
    campus: str
    state: str | None = None
    qualification_code: str
    qualification_title: str
    intake_label: str | None = None
    group_code: str | None = None
    course_duration_option_weeks: int | None = None

    # DATA-04 soft-delete metadata, shown in the recycle area.
    is_deleted: bool = False
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None
    delete_reason: str | None = None
    delete_reason_detail: str | None = None
    recovery_deadline: dt.date | None = None


class StudentList(BaseModel):
    items: list[StudentRead]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Single-entry writes
# ---------------------------------------------------------------------------


class StudentCreate(BaseModel):
    student_id: str
    first_name: str
    last_name: str | None = None
    college_id: int
    campus_id: int
    #: Either the qualification's id, or its code — the interface holds the code
    #: on the approved offering, so requiring the id would force a second lookup
    #: in the browser purely to satisfy the wire format.
    qualification_id: int | None = None
    qualification_code: str | None = None
    coe_status: str
    ct_student: bool = False
    proposed_start_date: dt.date
    proposed_end_date: dt.date
    personal_email: str | None = None
    primary_phone: str | None = None
    status: str = "ACTIVE"
    # Optional override; derived from the college's email domain when absent.
    college_email: str | None = None
    remarks: str | None = None
    #: The staff-selected approved Course Duration Option, in weeks (OD-08).
    #: Validated against the approved options for the student's own offering. A
    #: Credit Transfer student carries none, by the approved rule of 13 Aug 2026.
    course_duration_option_weeks: int | None = None


class StudentUpdate(StudentCreate):
    """A single-entry edit is a full replacement of the editable fields."""


class StudentDeleteRequest(BaseModel):
    reason_code: str
    reason_detail: str | None = None


# ---------------------------------------------------------------------------
# Bulk import — staging, review, decisions, apply
# ---------------------------------------------------------------------------


class RowIssueRead(BaseModel):
    field_name: str
    message: str
    issue_status: str


class StagedRowRead(BaseModel):
    id: int
    source_row_number: int
    status: str

    student_id_value: str | None = None
    first_name_value: str | None = None
    last_name_value: str | None = None
    college_value: str | None = None
    campus_value: str | None = None
    qualification_value: str | None = None
    coe_status_value: str | None = None
    ct_student_value: str | None = None
    status_value: str | None = None
    proposed_start_date_value: str | None = None
    proposed_end_date_value: str | None = None
    personal_email_value: str | None = None
    primary_phone_value: str | None = None

    resolved_college_id: int | None = None
    resolved_campus_id: int | None = None
    resolved_qualification_id: int | None = None
    resolved_offering_id: int | None = None

    # Derived preview (rule 2.5), shown before Confirm.
    derived_intake_label: str | None = None
    derived_group_code: str | None = None
    intake_match_status: str | None = None
    #: An approved Course Duration Option chosen to resolve a TBD intake (OD-08).
    duration_override_weeks: int | None = None

    # Duplicate handling (rule 2.6).
    duplicate_scope: str | None = None
    existing_student_id: int | None = None
    duplicate_decision: str | None = None
    existing_status_value: str | None = None

    # Reference resolution choices (rule 2.4).
    college_choice: str | None = None
    campus_choice: str | None = None
    qualification_choice: str | None = None

    issues: list[RowIssueRead] = []


class DuplicateComparisonField(BaseModel):
    field: str
    stored: str | None = None
    incoming: str | None = None
    differs: bool = False


class DuplicateContextRead(BaseModel):
    """Both versions of a same-Student-ID conflict, shown side by side (2.6)."""

    staged_row_id: int
    scope: str  # SAME_QUALIFICATION | DIFFERENT_QUALIFICATION
    existing_student_id: int
    existing_status: str
    existing_qualification_code: str
    incoming_qualification_code: str
    fields: list[DuplicateComparisonField] = []


class ImportReviewRead(BaseModel):
    batch_id: int
    batch_reference: str
    file_name: str
    status: str
    training_context: str | None = None

    rows_read: int
    counts: dict[str, int]

    can_apply: bool
    blocking_reasons: list[str] = []

    rows: list[StagedRowRead] = []
    duplicates: list[DuplicateContextRead] = []
    #: Qualification code -> the rolling-timetable durations it offers, so a TBD
    #: row can be resolved by choosing one rather than guessing.
    duration_options: dict[str, list[int]] = {}


class RowCorrection(BaseModel):
    column: str
    value: str


class RowPatch(BaseModel):
    row_id: int
    # Field corrections, keyed by the working column name.
    corrections: list[RowCorrection] | None = None
    # Row lifecycle: exclude or re-include a row.
    exclude: bool | None = None
    #: Resolve a TBD intake by choosing an approved duration (OD-08). 0 clears it.
    duration_weeks: int | None = None
    # Duplicate decisions (2.6).
    duplicate_decision: str | None = None  # KEEP_STORED | KEEP_INCOMING
    status_value: str | None = None  # incoming record's status (different qualification)
    existing_status_value: str | None = None  # re-status the stored record
    # Reference resolution (2.4). entity in {college, campus, qualification}.
    reference_entity: str | None = None
    reference_choice: str | None = None  # RAISE | EXCEPT | RESOLVE
    reference_resolved_id: int | None = None


class RowsPatch(BaseModel):
    items: list[RowPatch]


class ImportApplyRead(BaseModel):
    batch_id: int
    rows_read: int
    inserted: int
    updated: int
    excluded: int
    duplicates: int
    unmatched: int
    suggestions_raised: int
    #: Values accepted as exceptions and recorded (section 2.9).
    exceptions_recorded: int = 0
    #: Values already decided, so not reopened as exceptions (2.9.2).
    warnings: list[str] = []
    intakes_matched: int
    intakes_tbd: int
    intakes_not_applicable: int
    groups_created: int


# ---------------------------------------------------------------------------
# Show Timetable — derived on every call, never stored
# ---------------------------------------------------------------------------


class TimetableClassRead(BaseModel):
    """One real class occurrence, on its own calendar date."""

    date: dt.date
    weekday: str
    #: "HH:MM" strings, never `datetime.time`.
    start_time: str
    end_time: str
    stream: str
    delivery_mode: str
    mode_label: str
    classroom: str
    #: True when the classroom is the file's text rather than an approved record.
    classroom_unresolved: bool
    campus: str
    campus_unresolved: bool


class TimetableRowRead(BaseModel):
    """One unit, break or assessment week in the intake's delivery order."""

    row_type: str  # UNIT | BREAK | ASSESSMENT_WEEK
    week_from: dt.date
    week_to: dt.date
    #: Where the row sits against the student's own enrolment dates.
    timing: str  # BEFORE_JOINING | DURING | AFTER_END

    # UNIT rows only.
    unit_code: str | None = None
    unit_title: str | None = None
    allocation_status: str | None = None  # ALLOCATED | UNALLOCATED
    mode_of_delivery: str | None = None
    uoc_type: str | None = None
    #: Set when the rolling span and the allocation range disagree materially.
    span_note: str | None = None
    #: True when a delivery's range was too long to expand safely.
    expansion_refused: bool = False
    classes: list[TimetableClassRead] = []


class TimetableStudentRead(BaseModel):
    id: int
    student_id: str
    name: str
    status: str
    ct_student: bool


class TimetableQualificationRead(BaseModel):
    code: str
    title: str | None = None
    duration_weeks: int | None = None


class TimetableIntakeRead(BaseModel):
    label: str | None = None
    group_code: str | None = None
    match_status: str
    start_date: dt.date | None = None


class TimetableScopeRead(BaseModel):
    college: str
    campus: str


class TimetableCourseDatesRead(BaseModel):
    proposed_start_date: dt.date
    proposed_end_date: dt.date


class TimetableSummaryRead(BaseModel):
    units_total: int
    units_allocated: int
    units_unallocated: int
    classes_total: int


class StudentTimetableRead(BaseModel):
    """A student's own timetable, drawn from their intake.

    `empty_reason` distinguishes the three "no timetable" states so the
    interface can explain which one applies rather than saying "not found".
    """

    student: TimetableStudentRead
    qualification: TimetableQualificationRead
    intake: TimetableIntakeRead
    scope: TimetableScopeRead
    course_dates: TimetableCourseDatesRead
    #: null | CREDIT_TRANSFER | NO_ROLLING_TIMETABLE | NO_ROLLING_ROWS
    empty_reason: str | None = None
    summary: TimetableSummaryRead
    rows: list[TimetableRowRead] = []
