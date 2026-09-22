"""Allocation records request and response shapes."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class AllocationPackageRead(BaseModel):
    training_package: str
    enabled: bool
    has_profile: bool


class DiscrepancyRead(BaseModel):
    kind: str
    severity: str
    row_number: int | None = None
    column: str | None = None
    value: str | None = None
    message: str
    issue_id: str = ""
    can_edit: bool = False
    #: What the issue offers, decided by its kind (15 September 2026):
    #: SUGGESTION, EXCEPTION, UNSTORABLE, or EXCLUDED for a row taken out.
    category: str = "UNSTORABLE"
    can_raise_suggestion: bool = False
    can_except: bool = False
    can_exclude: bool = False
    edit_fields: list[dict] = []


class ImportReviewRead(BaseModel):
    status: str
    training_package: str
    file_name: str
    rows_read: int
    deliveries_that_would_be_written: int
    sessions_that_would_be_written: int
    qualifications: list[str]
    units: list[str]
    intakes_matched: int
    intakes_not_matched: int
    suggestions_that_would_be_raised: int
    discrepancies: list[DiscrepancyRead]
    discrepancies_by_kind: dict[str, list[DiscrepancyRead]]
    refused: bool
    can_apply: bool
    raise_suggestions: bool = True
    existing_deliveries: int = 0
    exceptions_accepted: int = 0
    rows_excluded: int = 0


class ImportApplyRead(BaseModel):
    rows_read: int
    deliveries_written: int
    sessions_written: int
    deliveries_removed: int
    suggestions_raised: int
    #: Broken rules accepted for this import only (15 September 2026). Nothing
    #: about an acceptance is kept for the next import.
    exceptions_accepted: int = 0
    rows_excluded: int = 0
    warnings: list[str] = []
    apply_mode: str


class CoveredClassRead(BaseModel):
    """One unit's class day inside a merged MSCRIS entry."""

    session_id: int
    delivery_id: int
    unit_code: str
    unit_title: str
    qualification_code: str
    college: str
    campus: str
    intakes: list[str]
    student_count: int = 0


class CalendarSessionRead(BaseModel):
    session_id: int
    delivery_id: int
    stream: str
    weekday: str
    start_time: str
    end_time: str
    unit_code: str
    unit_title: str
    qualification_code: str
    college: str = ""
    campus: str = ""
    duration_weeks: int | None = None
    #: The delivery's dates: one stored row is one unit's delivery.
    unit_start_date: str = ""
    unit_end_date: str = ""
    classroom: str
    trainer: str
    delivery_mode: str
    virtual_kind: str | None = None
    intakes: list[str]
    intake_match_status: str
    needs_allocation: bool
    not_found: bool
    #: Active students attending: their college, campus and qualification are the
    #: class's, and their rolling intake is one the class was matched to.
    student_count: int = 0
    #: Every stored class day this entry stands for: one, or each class day of a
    #: merged MSCRIS entry. An edit to the entry applies to all of them.
    session_ids: list[int] = []
    #: The units a merged MSCRIS entry covers. Empty for any other entry.
    covered: list[CoveredClassRead] = []


class ExpectedUnitRead(BaseModel):
    """A unit the rolling timetable schedules this week that no class teaches yet."""

    unit_code: str
    qualification_codes: list[str]
    intake_labels: list[str]


class CalendarDayRead(BaseModel):
    date: str
    weekday: str
    sessions: list[CalendarSessionRead]
    #: Unique units with a Theory or Practical class this day. MSCRIS is not counted.
    allocated_unit_count: int = 0
    #: A weekly figure, the same on every day of the week (approved 17 September 2026).
    expected_unit_count: int = 0
    expected_units: list[ExpectedUnitRead]


class CalendarRead(BaseModel):
    training_package: str
    start_date: str
    end_date: str
    days: list[CalendarDayRead]
    query_cost: int
    empty: bool


class SpreadsheetSessionRead(BaseModel):
    session_id: int
    stream: str
    weekday: str
    start_time: str
    end_time: str
    delivery_mode: str
    facility_id: int | None = None
    classroom: str = ""
    classroom_capacity: int | None = None
    trainer: str = ""
    trainer_id: int | None = None


class SpreadsheetRowRead(BaseModel):
    sl_no: int
    delivery_id: int
    college: str
    campus: str
    qualification_code: str
    qualification_title: str
    duration_weeks: int
    group: str
    intakes: list[str]
    total_students: int
    coe_students: int
    non_coe_students: int
    unit_code: str
    unit_title: str
    unit_start_date: dt.date
    unit_end_date: dt.date
    uoc_type: str
    mode_of_delivery: str
    sessions: list[SpreadsheetSessionRead]


class SpreadsheetListRead(BaseModel):
    items: list[SpreadsheetRowRead]
    total: int
    limit: int
    offset: int


class SpreadsheetClassroomChoice(BaseModel):
    id: int | None = None
    name: str
    capacity: int | None = None


class SpreadsheetTrainerChoice(BaseModel):
    id: int
    name: str


class SpreadsheetChoicesRead(BaseModel):
    classrooms: list[SpreadsheetClassroomChoice]
    trainers: list[SpreadsheetTrainerChoice]


class SessionPatch(BaseModel):
    weekday: str
    start_time: str
    end_time: str
    classroom: str | None = None
    trainer: str | None = None
    facility_id: int | None = None
    trainer_id: int | None = None


class MscrisGroupPatch(BaseModel):
    """An edit to a merged MSCRIS entry, applied to every class day it covers."""

    session_ids: list[int] = Field(..., min_length=1)
    start_time: str
    end_time: str
    classroom: str | None = None
    trainer: str | None = None


class MscrisGroupRead(BaseModel):
    updated: int


class SessionAdd(BaseModel):
    delivery_id: int
    stream: str
    weekday: str
    start_time: str
    end_time: str
    classroom: str | None = None
    trainer: str | None = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    training_package: str
    delivery_id: int
    stream: str
    weekday: str
    start_time: dt.time
    end_time: dt.time
    delivery_mode: str
    facility_id: int | None = None
    virtual_kind: str | None = None
    classroom_text: str | None = None
    trainer_id: int | None = None
    trainer_text: str | None = None


class SuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    raw_value: str
    context: dict = {}
    #: The raising row's other values, for pre-filling the form Add opens.
    attributes: dict = {}
    source: str
    occurrence_count: int
    first_seen_at: dt.datetime
    last_seen_at: dt.datetime | None = None
    status: str
    resolved_entity_id: int | None = None
    # An accepted exception is the same row with `status = 'EXCEPTION'`; these
    # say who allowed the value to stand unapproved, and when.
    accepted_by_user_id: int | None = None
    accepted_at: dt.datetime | None = None
    exception_note: str | None = None


class SuggestionList(BaseModel):
    items: list[SuggestionRead]
    total: int
    limit: int
    offset: int


class SuggestionResolve(BaseModel):
    #: CREATE, MAP, REJECT or WITHDRAW.
    action: str
    resolved_entity_id: int | None = None
    #: Fields for a record CREATE has to bring into existence, when nothing
    #: stored supplies them. A unit named only by a rolling timetable has no
    #: title anywhere in TDMS - the timetable carries the code twice and no
    #: name - so the title is asked for rather than invented. Where the record
    #: does already exist, CREATE finds it and this stays empty.
    create_values: dict[str, str] | None = None
    #: Required by REJECT when unverified students carry the value: a student
    #: is deleted the approved way, with a reason and a recovery window (DATA-04).
    reason_code: str | None = None
    reason_detail: str | None = None


class SuggestionResolveResult(BaseModel):
    """The outcome, including how many stored rows the decision repaired.

    The count is part of the contract: a resolution that updated nothing must be
    shown as a warning rather than a plain success (2.4.4).
    """

    suggestion: SuggestionRead
    records_updated: int


class SuggestionSummaryRead(BaseModel):
    entity_type: str
    pending: int
    exceptions: int


class MapOptionRead(BaseModel):
    """One record an entry could be mapped to."""

    id: int
    label: str
    #: Anything that tells two similar records apart - for a room, the building.
    detail: str | None = None
    #: Inside the scope the entry was raised with: the qualification's units,
    #: the campus's rooms, the college's locations.
    in_scope: bool = False


class MapOptionsRead(BaseModel):
    suggestion_id: int
    entity_type: str
    #: The scope in words, or `None` when the entry carries no context.
    scope_label: str | None = None
    #: The record the scope resolved to - the college, qualification or campus.
    #: A room entry names its campus by an address spelling only the server can
    #: resolve, so a form pre-filled from the entry takes the campus from here.
    scope_id: int | None = None
    #: The list holds the scope and nothing else - rooms at one campus.
    scope_only: bool = False
    items: list[MapOptionRead] = []
    total: int = 0
    truncated: bool = False


class AffectedRecordsRead(BaseModel):
    suggestion_id: int
    entity_type: str
    raw_value: str
    total: int
    items: list[dict] = []
    truncated: bool = False


class DeliveryListItem(BaseModel):
    id: int
    training_package: str
    qualification_code: str
    unit_code: str
    group_code: str
    start_date: dt.date
    end_date: dt.date
    intake_match_status: str
    session_count: int


class DeliveryList(BaseModel):
    items: list[DeliveryListItem]
    total: int
    limit: int
    offset: int


class ClearAllocationRead(BaseModel):
    """What a clear of the allocation records removed, or would remove.

    Counted before the delete so the confirmation shows real numbers rather
    than a vague warning.
    """

    deliveries: int
    sessions: int
    intake_links: int
    import_batches: int
    source_rows: int
    #: Pending entries the allocation import raised.
    suggestions: int
    #: Accepted exceptions from the allocation import.
    exceptions: int
    #: Already-decided entries (added, mapped or rejected) from that import.
    resolved_suggestions: int
