"""Trainer Data request and response shapes.

snake_case on the wire, matching the other always-real modules (allocation,
rolling timetable, students) that the frontend clients mirror.

A trainer's **training packages are derived**, never stored and never accepted
on input: they are the distinct first three characters of the qualification
codes the trainer teaches. A BSB file legitimately contains a trainer who
teaches only FNS qualifications, which is why no request shape carries one.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Trainer list and detail (2.6)
# ---------------------------------------------------------------------------


class TrainerRead(BaseModel):
    """One row per trainer, however many locations they work at (1.5)."""

    id: int
    trainer_id: str
    trainer_name: str
    #: The city the trainer is based in — the file's `Trainer Campus`.
    city: str | None = None
    is_active: bool

    location_count: int
    #: "Blacktown, Haymarket" — the campuses, or Offshore, in one line.
    location_summary: str
    qualification_count: int
    unit_count: int
    #: Derived from the qualification codes. Never stored (1.7).
    training_packages: list[str] = []


class TrainerList(BaseModel):
    items: list[TrainerRead]
    total: int
    limit: int
    offset: int


class TrainerLocationRead(BaseModel):
    """One availability row, with its five weekdays."""

    id: int
    campus_id: int | None = None
    campus_name: str | None = None
    #: Set only when the campus could not be resolved, so the panel can mark it
    #: unresolved rather than showing a blank.
    location_text: str | None = None
    is_offshore: bool
    location: str | None = None
    location_type: str | None = None
    class_type: str
    working_time_start: dt.time
    working_time_end: dt.time
    #: The window as the file wrote it, including any timezone suffix.
    working_time_text: str | None = None

    monday: str
    tuesday: str
    wednesday: str
    thursday: str
    friday: str


class TrainerUnitRead(BaseModel):
    #: The `trainer_units` row id, so one link can be removed.
    id: int
    #: None when the unit is not in the reference data yet — the value is held
    #: as text until its suggestion is resolved.
    unit_id: int | None = None
    unit_code: str
    unit_title: str
    unresolved: bool = False


class TrainerQualificationRead(BaseModel):
    qualification_id: int | None = None
    qualification_code: str | None = None
    qualification_title: str
    qualification_unresolved: bool = False
    #: Nested, so expanding a tray in the side panel costs no request (2.10).
    units: list[TrainerUnitRead] = []


class TrainerDetailRead(BaseModel):
    """The whole side panel in one round trip (2.6)."""

    id: int
    trainer_id: str
    trainer_name: str
    city: str | None = None
    is_active: bool
    training_packages: list[str] = []
    locations: list[TrainerLocationRead] = []
    qualifications: list[TrainerQualificationRead] = []


class TrainerTimetableClassRead(BaseModel):
    """One visible calendar item, merged by date, unit and classroom."""

    class_key: str
    session_ids: list[int]
    unit_code: str
    unit_title: str
    classroom: str
    colleges: list[str] = []
    campuses: list[str] = []
    times: list[str] = []
    delivery_modes: list[str] = []
    uoc_types: list[str] = []
    streams: list[str] = []
    co_trainers: list[str] = []
    moodle_link: str | None = None


class TrainerTimetableDayRead(BaseModel):
    date: dt.date
    classes: list[TrainerTimetableClassRead] = []


class TrainerTimetableRead(BaseModel):
    trainer_id: int
    trainer_name: str
    month: str
    days: list[TrainerTimetableDayRead] = []


class TrainerTimetableStudentRead(BaseModel):
    id: int
    student_id: str
    first_name: str
    last_name: str | None = None
    coe_status: str


class TrainerTimetableStudentList(BaseModel):
    items: list[TrainerTimetableStudentRead] = []
    total: int


# ---------------------------------------------------------------------------
# Unit coverage (2.7)
# ---------------------------------------------------------------------------


class UnitCoverageRead(BaseModel):
    unit_id: int
    unit_code: str
    unit_title: str
    qualification_id: int | None = None
    qualification_code: str | None = None
    qualification_title: str | None = None
    #: Distinct active, non-deleted trainers approved for this unit.
    trainer_count: int
    #: Up to five, for a tooltip.
    trainer_names: list[str] = []
    has_more_trainers: bool = False


class UnitCoverageList(BaseModel):
    items: list[UnitCoverageRead]
    total: int


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


class LocationWrite(BaseModel):
    """Add Location (1.6).

    Exactly one of `campus_id` or `is_offshore` carries the place. An offshore
    row has no campus by rule, and the database refuses the combination.
    """

    campus_id: int | None = None
    is_offshore: bool = False
    location: str | None = None
    location_type: str | None = None
    class_type: str
    working_time_start: dt.time
    working_time_end: dt.time
    working_time_text: str | None = None

    monday: str = "NOT_AVAILABLE"
    tuesday: str = "NOT_AVAILABLE"
    wednesday: str = "NOT_AVAILABLE"
    thursday: str = "NOT_AVAILABLE"
    friday: str = "NOT_AVAILABLE"


class UnitsWrite(BaseModel):
    """Add Units (1.6) — one qualification, many units, one call."""

    qualification_id: int
    unit_ids: list[int]




class TrainerCreate(BaseModel):
    """Add a trainer by hand.

    There is **no `trainer_id`**: it is generated from the sequence and the
    name, so a caller cannot mint one. The city is required; the location and
    the units are not.
    """

    trainer_name: str
    city: str
    is_active: bool = True
    #: Both optional and both repeatable — a trainer may be recorded with no
    #: location at all, or with several added before saving.
    locations: list[LocationWrite] = []
    units: list[UnitsWrite] = []


class GeneratedTrainerId(BaseModel):
    """What the form shows while the name is being typed."""

    trainer_id: str
    sequence: int
    initials: str


class TrainerUpdate(BaseModel):
    trainer_name: str | None = None
    city: str | None = None
    is_active: bool | None = None


class ClearTrainersCounts(BaseModel):
    """What clearing the trainer database removes, or removed."""

    trainers: int
    locations: int
    unit_links: int
    qualification_links: int
    #: Sessions that keep their trainer's name and read as unresolved after.
    allocation_sessions_unlinked: int
    #: Suggestions raised so those names are not quietly forgotten.
    trainer_suggestions_raised: int


class TrainerDeleteRequest(BaseModel):
    reason_code_id: int
    reason_note: str | None = None


# ---------------------------------------------------------------------------
# Bulk import (2.13)
# ---------------------------------------------------------------------------


class ImportRowIssueRead(BaseModel):
    severity: str
    code: str
    column_name: str | None = None
    message: str


class ImportStagedRowRead(BaseModel):
    id: int
    row_number: int
    status: str
    values: dict
    issues: list[ImportRowIssueRead] = []


class MissingTrainerGroup(BaseModel):
    """A trainer id in the file that is not in the trainer database (1.9)."""

    trainer_id: str
    row_count: int


class UnresolvedValueRead(BaseModel):
    """A value in the file that matches no approved record.

    Detected at staging but **not** written: raising a suggestion is the user's
    decision. There is no exception path — a qualification or a unit either
    exists in the reference data or it does not, so the only resolutions are
    Create Record and Map Record (1.8).
    """

    key: str
    entity_type: str
    raw_value: str
    context: dict
    row_count: int
    #: True once a queue entry exists for it, whichever import first raised it.
    in_queue: bool
    queue_status: str | None = None
    #: True once **this batch** was told to raise it — the decision that lets
    #: its rows import with the value kept as written.
    raised_here: bool = False


class ImportReviewRead(BaseModel):
    batch_id: int
    data_type: str
    file_name: str
    rows_read: int
    rows_valid: int
    rows_with_errors: int
    rows_excluded: int
    can_apply: bool
    rows: list[ImportStagedRowRead] = []
    #: Grouped so the review can say "4 trainer ids … — 96 rows" (2.13.3).
    missing_trainers: list[MissingTrainerGroup] = []
    #: Every unmatched qualification, unit and campus in this file, with
    #: whether it is already in the queue. Offered for a decision, never
    #: raised behind the user's back.
    unresolved_values: list[UnresolvedValueRead] = []
    #: Rows that would change something already stored (approved 27 Aug 2026).
    overrides: list[OverrideRead] = []
    #: How many of those already have a queue entry.
    suggestions_raised: int = 0
    blocking_message: str | None = None


class RaiseValuesRequest(BaseModel):
    """Which unmatched values to raise. `all` raises every one in the batch."""

    keys: list[str] = []
    all: bool = False


class OverrideChange(BaseModel):
    """One field this file would change on a location already stored."""

    field: str
    label: str
    stored_value: str
    incoming_value: str


class OverrideRead(BaseModel):
    """A row that would overwrite something, waiting for a decision.

    Adding is silent; overwriting is not. Confirm stays shut until every
    one of these says whether to keep the stored value or take the file's.
    """

    row_id: int
    row_number: int
    trainer_id: str
    location: str
    #: KEEP_STORED, TAKE_FROM_FILE, or None while undecided.
    decision: str | None = None
    changes: list[OverrideChange] = []


class RowsPatch(BaseModel):
    """Corrections and decisions applied to staged rows."""

    corrections: dict[int, dict] = {}
    excluded_row_ids: list[int] = []
    #: row id -> KEEP_STORED | TAKE_FROM_FILE
    override_decisions: dict[int, str] = {}
    #: The single action offered for a missing trainer (2.13.3).
    exclude_missing_trainers: bool = False
    #: Rows whose broken rule is accepted for this import, and Undo for it.
    accepted_exception_row_ids: list[int] = []
    withdrawn_exception_row_ids: list[int] = []
    #: Undo for an exclusion.
    included_row_ids: list[int] = []


class ImportApplyRead(BaseModel):
    batch_id: int
    data_type: str
    apply_mode: str
    trainers_written: int
    locations_written: int
    unit_links_written: int
    qualification_links_written: int
    #: Links stored against a value the reference data does not hold yet.
    unit_links_unresolved: int = 0
    #: Stored locations the user chose to replace with the file's version.
    locations_overwritten: int = 0
    rows_excluded: int
