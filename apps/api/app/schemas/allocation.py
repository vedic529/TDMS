"""Allocation records request and response shapes."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


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
    can_raise_suggestion: bool = False
    can_except: bool = False
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


class ImportApplyRead(BaseModel):
    rows_read: int
    deliveries_written: int
    sessions_written: int
    deliveries_removed: int
    suggestions_raised: int
    #: Values accepted as exceptions and recorded (section 2.9).
    exceptions_recorded: int = 0
    #: Values that were already decided and so were not reopened (2.9.2).
    warnings: list[str] = []
    apply_mode: str


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
    classroom: str
    trainer: str
    delivery_mode: str
    virtual_kind: str | None = None
    intakes: list[str]
    intake_match_status: str
    needs_allocation: bool
    not_found: bool


class ExpectedUnitRead(BaseModel):
    unit_code: str
    intake_label: str
    scheduled: bool


class CalendarDayRead(BaseModel):
    date: str
    weekday: str
    sessions: list[CalendarSessionRead]
    expected_units: list[ExpectedUnitRead]
    student_count: int | None = None


class CalendarRead(BaseModel):
    training_package: str
    start_date: str
    end_date: str
    days: list[CalendarDayRead]
    query_cost: int
    empty: bool


class SessionPatch(BaseModel):
    weekday: str
    start_time: str
    end_time: str
    classroom: str | None = None
    trainer: str | None = None


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
