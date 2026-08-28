"""Request and response shapes for the Rolling Timetable."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class RollingWeekRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    training_package: str
    qualification_code: str
    duration_weeks: int
    intake_label: str
    intake_group: str
    intake_start_date: dt.date
    week_no: int
    week_start_date: dt.date
    week_end_date: dt.date
    schedule_type: str
    schedule_value: str
    unit_code: str | None = None
    unit_count: int
    unit_delivery_span_weeks: int | None = None
    unit_slot: int


class RollingWeekList(BaseModel):
    items: list[RollingWeekRead]
    total: int
    limit: int
    offset: int


class RollingWeekPatchItem(BaseModel):
    id: int
    schedule_type: str
    schedule_value: str


class RollingWeekBulkPatch(BaseModel):
    items: list[RollingWeekPatchItem] = Field(min_length=1)


class RollingWeekBulkRead(BaseModel):
    items: list[RollingWeekRead]


class RollingScopeRead(BaseModel):
    training_package: str
    qualification_code: str
    duration_weeks: int
    intake_count: int
    row_count: int


class RollingFacetsRead(BaseModel):
    intake_labels: list[str]
    unit_codes: list[str]


class VisualizerWeek(BaseModel):
    week_no: int
    week_start_date: str
    week_end_date: str


class VisualizerColumn(BaseModel):
    intake_label: str
    unit_slot: int
    heading: str


class VisualizerCounts(BaseModel):
    unit: int
    break_count: int
    assessment_week: int


class VisualizerRead(BaseModel):
    training_package: str
    qualification_code: str
    duration_weeks: int
    weeks: list[VisualizerWeek]
    intake_columns: list[VisualizerColumn]
    grid: list[list[str]]
    counts: VisualizerCounts


class DiscrepancyRead(BaseModel):
    kind: str
    severity: str
    row_number: int | None = None
    column: str | None = None
    value: str | None = None
    message: str


class QualificationImportSummary(BaseModel):
    qualification_code: str
    duration_weeks: int
    training_package: str
    row_count: int
    intake_count: int


class ImportReviewRead(BaseModel):
    status: str
    training_package: str
    file_name: str
    rows_read: int
    rows_that_would_be_written: int
    qualifications: list[QualificationImportSummary]
    matching_qualifications: list[QualificationImportSummary]
    non_matching_qualifications: list[QualificationImportSummary]
    counts: VisualizerCounts
    discrepancies: list[DiscrepancyRead]
    discrepancies_by_kind: dict[str, list[DiscrepancyRead]]
    existing_qualifications_replaced: list[str]
    refused: bool
    can_proceed_with_package: bool


class ImportApplyRead(BaseModel):
    rows_written: int
    qualifications_replaced: list[str]
    qualifications_skipped: list[str]
    rows_read: int
