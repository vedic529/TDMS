"""Query the rolling timetable. The Visualizer issues exactly one SELECT."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.enums import TRAINING_PACKAGE_VALUES
from app.models.timetable import RollingTimetableWeek
from app.models.user import User
from app.services.activity import record_activity
from app.services.rolling_timetable_import import (
    SCHEDULE_TYPES,
    TYPE_ASSESSMENT,
    TYPE_BREAK,
    TYPE_UNIT,
    VISUALIZER_QUERY_COUNT,
)

assert VISUALIZER_QUERY_COUNT == 1


class RollingStoreError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass
class WeekQuery:
    training_package: str | None = None
    qualification_code: str | None = None
    duration_weeks: int | None = None
    intake_label: str | None = None
    week_no: int | None = None
    schedule_type: str | None = None
    unit_code: str | None = None
    week_start_from: dt.date | None = None
    week_start_to: dt.date | None = None
    search: str | None = None
    limit: int = 100
    offset: int = 0
    sort: str = "week_no"
    direction: str = "asc"


SORTABLE = {
    "qualification_code": RollingTimetableWeek.qualification_code,
    "intake_label": RollingTimetableWeek.intake_label,
    "week_no": RollingTimetableWeek.week_no,
    "week_start_date": RollingTimetableWeek.week_start_date,
    "schedule_type": RollingTimetableWeek.schedule_type,
    "unit_code": RollingTimetableWeek.unit_code,
}


def _filtered(query: WeekQuery) -> Select:
    stmt = select(RollingTimetableWeek)
    if query.training_package:
        stmt = stmt.where(RollingTimetableWeek.training_package == query.training_package.upper())
    if query.qualification_code:
        stmt = stmt.where(
            func.upper(RollingTimetableWeek.qualification_code) == query.qualification_code.upper()
        )
    if query.duration_weeks is not None:
        stmt = stmt.where(RollingTimetableWeek.duration_weeks == query.duration_weeks)
    if query.intake_label:
        stmt = stmt.where(RollingTimetableWeek.intake_label == query.intake_label)
    if query.week_no is not None:
        stmt = stmt.where(RollingTimetableWeek.week_no == query.week_no)
    if query.schedule_type:
        stmt = stmt.where(RollingTimetableWeek.schedule_type == query.schedule_type)
    if query.unit_code:
        stmt = stmt.where(RollingTimetableWeek.unit_code == query.unit_code)
    if query.week_start_from:
        stmt = stmt.where(RollingTimetableWeek.week_start_date >= query.week_start_from)
    if query.week_start_to:
        stmt = stmt.where(RollingTimetableWeek.week_start_date <= query.week_start_to)
    if query.search:
        pattern = f"%{query.search.strip()}%"
        stmt = stmt.where(
            RollingTimetableWeek.intake_label.ilike(pattern)
            | RollingTimetableWeek.schedule_value.ilike(pattern)
            | RollingTimetableWeek.qualification_code.ilike(pattern)
        )
    return stmt


def list_weeks(session: Session, query: WeekQuery) -> tuple[list[RollingTimetableWeek], int]:
    filtered = _filtered(query)
    total = session.execute(select(func.count()).select_from(filtered.subquery())).scalar_one()
    column = SORTABLE.get(query.sort, RollingTimetableWeek.week_no)
    order = column.desc() if query.direction == "desc" else column.asc()
    rows = session.execute(
        filtered.order_by(
            order,
            RollingTimetableWeek.intake_label,
            RollingTimetableWeek.week_no,
            RollingTimetableWeek.unit_slot,
        )
        .limit(min(query.limit, 2000))
        .offset(max(query.offset, 0))
    ).scalars().all()
    return list(rows), total


def list_scopes(session: Session) -> list[dict]:
    """Distinct loops with intake and row counts. One query. Does not fetch week rows."""
    stmt = (
        select(
            RollingTimetableWeek.training_package,
            RollingTimetableWeek.qualification_code,
            RollingTimetableWeek.duration_weeks,
            func.count(func.distinct(RollingTimetableWeek.intake_label)),
            func.count(),
        )
        .group_by(
            RollingTimetableWeek.training_package,
            RollingTimetableWeek.qualification_code,
            RollingTimetableWeek.duration_weeks,
        )
        .order_by(
            RollingTimetableWeek.training_package,
            RollingTimetableWeek.qualification_code,
            RollingTimetableWeek.duration_weeks,
        )
    )
    rows = session.execute(stmt).all()
    package_rank = {name: index for index, name in enumerate(TRAINING_PACKAGE_VALUES)}
    ordered = sorted(
        rows,
        key=lambda item: (package_rank.get(item[0], 99), item[1], item[2]),
    )
    return [
        {
            "training_package": package,
            "qualification_code": code,
            "duration_weeks": duration,
            "intake_count": intakes,
            "row_count": count,
        }
        for package, code, duration, intakes, count in ordered
    ]


def default_scope(scopes: list[dict]) -> dict | None:
    return scopes[0] if scopes else None


def list_facets(
    session: Session, training_package: str, qualification_code: str, duration_weeks: int
) -> dict:
    stmt = select(
        RollingTimetableWeek.intake_label,
        RollingTimetableWeek.unit_code,
    ).where(
        RollingTimetableWeek.training_package == training_package.upper(),
        func.upper(RollingTimetableWeek.qualification_code) == qualification_code.upper(),
        RollingTimetableWeek.duration_weeks == duration_weeks,
    )
    intakes: set[str] = set()
    units: set[str] = set()
    for intake, unit in session.execute(stmt):
        intakes.add(intake)
        if unit:
            units.add(unit)
    return {
        "intake_labels": sorted(intakes),
        "unit_codes": sorted(units),
    }


def visualizer_grid(
    session: Session,
    training_package: str,
    qualification_code: str,
    duration_weeks: int,
) -> dict:
    """One SELECT. Pivot in memory. Empty cells are blank, never NA."""
    stmt = (
        select(
            RollingTimetableWeek.week_no,
            RollingTimetableWeek.week_start_date,
            RollingTimetableWeek.intake_label,
            RollingTimetableWeek.intake_start_date,
            RollingTimetableWeek.schedule_value,
            RollingTimetableWeek.schedule_type,
            RollingTimetableWeek.unit_slot,
        )
        .where(
            RollingTimetableWeek.training_package == training_package.upper(),
            func.upper(RollingTimetableWeek.qualification_code) == qualification_code.upper(),
            RollingTimetableWeek.duration_weeks == duration_weeks,
        )
        .order_by(
            RollingTimetableWeek.week_no,
            RollingTimetableWeek.intake_start_date,
            RollingTimetableWeek.intake_label,
            RollingTimetableWeek.unit_slot,
        )
    )
    rows = session.execute(stmt).all()
    if not rows:
        return {
            "training_package": training_package.upper(),
            "qualification_code": qualification_code.upper(),
            "duration_weeks": duration_weeks,
            "weeks": [],
            "intake_columns": [],
            "grid": [],
            "counts": {"unit": 0, "break_count": 0, "assessment_week": 0},
        }

    lowest = min(row.week_no for row in rows)
    highest = max(row.week_no for row in rows)
    origin = min(row.week_start_date for row in rows if row.week_no == lowest)
    weeks = []
    for week_no in range(lowest, highest + 1):
        start = origin + dt.timedelta(days=7 * (week_no - lowest))
        weeks.append(
            {
                "week_no": week_no,
                "week_start_date": start.isoformat(),
                "week_end_date": (start + dt.timedelta(days=6)).isoformat(),
            }
        )

    slots_for_intake: dict[str, set[int]] = defaultdict(set)
    first_delivery: dict[str, dt.date] = {}
    lookup: dict[tuple[int, str, int], str] = {}
    counts = {"unit": 0, "break_count": 0, "assessment_week": 0}
    for row in rows:
        slots_for_intake[row.intake_label].add(row.unit_slot)
        first_delivery.setdefault(row.intake_label, row.intake_start_date)
        lookup[(row.week_no, row.intake_label, row.unit_slot)] = row.schedule_value
        if row.schedule_type == TYPE_UNIT:
            counts["unit"] += 1
        elif row.schedule_type == TYPE_BREAK:
            counts["break_count"] += 1
        elif row.schedule_type == TYPE_ASSESSMENT:
            counts["assessment_week"] += 1

    intake_order = sorted(slots_for_intake, key=lambda label: (first_delivery[label], label))
    columns: list[dict] = []
    for label in intake_order:
        slots = sorted(slots_for_intake[label])
        for slot in slots:
            heading = label if len(slots) == 1 else f"{label} · {slot}"
            columns.append({"intake_label": label, "unit_slot": slot, "heading": heading})

    grid = [
        [lookup.get((week["week_no"], column["intake_label"], column["unit_slot"]), "") for column in columns]
        for week in weeks
    ]
    return {
        "training_package": training_package.upper(),
        "qualification_code": qualification_code.upper(),
        "duration_weeks": duration_weeks,
        "weeks": weeks,
        "intake_columns": columns,
        "grid": grid,
        "counts": counts,
    }


def _unit_fields(schedule_type: str, schedule_value: str) -> tuple[str, str | None, int]:
    kind = schedule_type.strip().upper()
    value = schedule_value.strip()
    if kind not in SCHEDULE_TYPES:
        raise RollingStoreError(400, "Schedule type must be Unit, Break, or Assessment Week.")
    if not value:
        raise RollingStoreError(400, "Every week in the intake needs a value.")
    if value.upper() == "NA":
        raise RollingStoreError(400, "NA is not stored. Keep the week as a unit, a break, or an assessment week.")
    if kind == TYPE_UNIT:
        return value, value, max(1, value.count("/") + 1)
    return value, None, 0


def _restamp_delivery_spans(rows: list[RollingTimetableWeek]) -> None:
    rows.sort(key=lambda row: (row.week_no, row.unit_slot))
    pending_value: str | None = None
    pending_rows: list[RollingTimetableWeek] = []
    pending_start: dt.date | None = None
    pending_end: dt.date | None = None

    def close() -> None:
        nonlocal pending_value, pending_rows, pending_start, pending_end
        if pending_value is None or pending_start is None or pending_end is None:
            pending_value = None
            pending_rows = []
            return
        span = ((pending_end - pending_start).days + 1) // 7
        for item in pending_rows:
            item.unit_delivery_span_weeks = span
        pending_value = None
        pending_rows = []
        pending_start = None
        pending_end = None

    for row in rows:
        if row.schedule_type == TYPE_UNIT:
            if pending_value is None:
                pending_value = row.schedule_value
                pending_rows = [row]
                pending_start = row.week_start_date
                pending_end = row.week_end_date
            elif row.schedule_value == pending_value:
                pending_rows.append(row)
                pending_end = row.week_end_date
            else:
                close()
                pending_value = row.schedule_value
                pending_rows = [row]
                pending_start = row.week_start_date
                pending_end = row.week_end_date
        else:
            row.unit_delivery_span_weeks = None
            if pending_value is not None:
                pending_end = row.week_end_date
    close()


def update_weeks(
    session: Session,
    user: User,
    items: list[tuple[int, str, str]],
) -> list[RollingTimetableWeek]:
    if not items:
        raise RollingStoreError(400, "Nothing was sent to update.")

    updated: list[RollingTimetableWeek] = []
    intakes: set[tuple[str, str, int, str]] = set()
    for week_id, schedule_type, schedule_value in items:
        row = session.get(RollingTimetableWeek, week_id)
        if row is None:
            raise RollingStoreError(404, "That rolling timetable week was not found.")
        value, unit_code, unit_count = _unit_fields(schedule_type, schedule_value)
        row.schedule_type = schedule_type.strip().upper()
        row.schedule_value = value
        row.unit_code = unit_code
        row.unit_count = unit_count
        updated.append(row)
        intakes.add((row.training_package, row.qualification_code, row.duration_weeks, row.intake_label))

    if len(intakes) != 1:
        raise RollingStoreError(400, "Edits must stay within a single intake.")

    package, qualification, duration, intake_label = next(iter(intakes))
    stack = list(
        session.execute(
            select(RollingTimetableWeek)
            .where(
                RollingTimetableWeek.training_package == package,
                RollingTimetableWeek.qualification_code == qualification,
                RollingTimetableWeek.duration_weeks == duration,
                RollingTimetableWeek.intake_label == intake_label,
            )
            .order_by(RollingTimetableWeek.week_no, RollingTimetableWeek.unit_slot)
        ).scalars().all()
    )
    _restamp_delivery_spans(stack)
    session.flush()
    record_activity(
        session,
        user=user,
        action="UPDATE",
        page_or_function="Page 1 - Timetable View and Management",
        detail=f"Updated {len(updated)} week(s) in {intake_label}.",
        record_reference=intake_label,
        result="COMPLETED",
    )
    return stack


def rows_for_export(session: Session, training_package: str | None = None) -> list[RollingTimetableWeek]:
    stmt = select(RollingTimetableWeek)
    if training_package:
        stmt = stmt.where(RollingTimetableWeek.training_package == training_package.upper())
    return list(
        session.execute(
            stmt.order_by(
                RollingTimetableWeek.training_package,
                RollingTimetableWeek.qualification_code,
                RollingTimetableWeek.duration_weeks,
                RollingTimetableWeek.week_no,
                RollingTimetableWeek.intake_label,
                RollingTimetableWeek.unit_slot,
            )
        ).scalars().all()
    )
