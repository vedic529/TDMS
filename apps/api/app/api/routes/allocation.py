"""Allocation Records — calendar, import, edit, download, suggestions."""

from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db,
    require_maintain_timetable,
    require_super_admin,
    require_viewer_or_above,
)
from app.models.allocation import AllocationDelivery, AllocationSession
from app.models.qualification import Qualification, Unit
from app.models.user import User
from app.schemas.allocation import (
    ClearAllocationRead,
    AllocationPackageRead,
    CalendarRead,
    DeliveryList,
    DeliveryListItem,
    ImportApplyRead,
    ImportReviewRead,
    MscrisGroupPatch,
    MscrisGroupRead,
    SessionAdd,
    SessionPatch,
    SessionRead,
    SpreadsheetChoicesRead,
    SpreadsheetListRead,
)
from app.services import allocation_calendar as calendar_service
from app.services import allocation_edit as edit_service
from app.services import allocation_export as export_service
from app.services import allocation_import as import_service
from app.services import allocation_maintenance as maintenance_service
from app.services import allocation_profiles as profiles
from app.services import allocation_spreadsheet as spreadsheet_service

router = APIRouter(prefix="/allocation", tags=["allocation records"])
READ_RESPONSES = {403: {"description": "Requires an active TDMS account."}}
WRITE_RESPONSES = {403: {"description": "Requires Data Editor access or above."}, 400: {"description": "Refused."}}


def _overrides_from_form(raw: str, raise_suggestions: bool) -> import_service.ImportOverrides:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="overrides must be a JSON object.") from exc
    if payload is not None and not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="overrides must be a JSON object.")
    return import_service.ImportOverrides.from_payload(payload or {}, raise_suggestions)


def _time(value: str) -> dt.time:
    try:
        hour, minute = value.split(":")
        return dt.time(int(hour), int(minute))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Times must be HH:MM.") from exc


@router.get("/packages", response_model=list[AllocationPackageRead], responses=READ_RESPONSES)
def list_packages(_: User = Depends(require_viewer_or_above), session: Session = Depends(get_db)):
    return [AllocationPackageRead.model_validate(item) for item in profiles.list_packages(session)]


@router.get("/calendar", response_model=CalendarRead, responses=READ_RESPONSES)
def read_calendar(
    training_package: str = Query(...),
    start_date: dt.date = Query(...),
    end_date: dt.date = Query(...),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return CalendarRead.model_validate(
        calendar_service.calendar_month(
            session, training_package=training_package, start_date=start_date, end_date=end_date
        )
    )


@router.get("/spreadsheet", response_model=SpreadsheetListRead, responses=READ_RESPONSES)
def read_spreadsheet(
    training_package: str = Query(...),
    start_date: dt.date = Query(...),
    end_date: dt.date | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return SpreadsheetListRead.model_validate(
        spreadsheet_service.list_rows(
            session,
            training_package=training_package,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/spreadsheet/{delivery_id}/choices", response_model=SpreadsheetChoicesRead, responses=READ_RESPONSES)
def spreadsheet_choices(
    delivery_id: int,
    training_package: str = Query(...),
    stream: str = Query(...),
    weekday: str = Query(...),
    start_time: str = Query(...),
    end_time: str = Query(...),
    delivery_mode: str = Query(...),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    try:
        return SpreadsheetChoicesRead.model_validate(
            spreadsheet_service.choices(
                session,
                delivery_id=delivery_id,
                training_package=training_package,
                stream=stream.upper(),
                weekday=weekday.upper(),
                start_time=_time(start_time),
                end_time=_time(end_time),
                delivery_mode=delivery_mode.upper(),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/deliveries", response_model=DeliveryList, responses=READ_RESPONSES)
def list_deliveries(
    training_package: str = Query(...),
    quarantined: bool = Query(
        default=False,
        description="False returns operational rows only; True returns only quarantined rows.",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    package = training_package.upper()
    # A quarantined delivery is retained and auditable but never operational, so
    # it is excluded by default and reachable only by asking for it.
    filtered = select(AllocationDelivery).where(
        AllocationDelivery.training_package == package,
        AllocationDelivery.is_quarantined.is_(quarantined),
    )
    total = session.execute(select(func.count()).select_from(filtered.subquery())).scalar_one()
    rows = list(
        session.execute(
            filtered.order_by(AllocationDelivery.start_date, AllocationDelivery.id).limit(limit).offset(offset)
        ).scalars()
    )
    counts = dict(
        session.execute(
            select(AllocationSession.delivery_id, func.count())
            .where(AllocationSession.training_package == package)
            .group_by(AllocationSession.delivery_id)
        ).all()
    )
    quals = {row.id: row.qualification_code for row in session.execute(select(Qualification)).scalars()}
    units = {row.id: row.unit_code for row in session.execute(select(Unit)).scalars()}
    items = [
        DeliveryListItem(
            id=row.id,
            training_package=row.training_package,
            qualification_code=quals.get(row.qualification_id) or "",
            unit_code=units.get(row.unit_id) or "",
            group_code=row.group_code,
            start_date=row.start_date,
            end_date=row.end_date,
            intake_match_status=row.intake_match_status,
            session_count=counts.get(row.id, 0),
        )
        for row in rows
    ]
    return DeliveryList(items=items, total=total, limit=limit, offset=offset)


@router.post("/import/validate", response_model=ImportReviewRead, responses=WRITE_RESPONSES)
async def validate_import(
    training_package: str = Form(...),
    file: UploadFile = File(...),
    raise_suggestions: bool = Form(True),
    overrides: str = Form("{}"),
    _: User = Depends(require_maintain_timetable),
    session: Session = Depends(get_db),
):
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="The file is empty.")
    try:
        review, _planned, _suggestions = import_service.validate_bytes(
            session,
            training_package=training_package,
            file_name=file.filename or "upload.xlsx",
            payload=payload,
            raise_suggestions=raise_suggestions,
            overrides=_overrides_from_form(overrides, raise_suggestions),
        )
    except import_service.AllocationImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportReviewRead.model_validate(import_service.review_to_dict(review))


@router.post("/import/apply", response_model=ImportApplyRead, responses=WRITE_RESPONSES)
async def apply_import(
    training_package: str = Form(...),
    apply_mode: str = Form(...),
    raise_suggestions: bool = Form(True),
    overrides: str = Form("{}"),
    file: UploadFile = File(...),
    user: User = Depends(require_maintain_timetable),
    session: Session = Depends(get_db),
):
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="The file is empty.")
    if apply_mode.upper() not in {"REPLACE", "MERGE"}:
        raise HTTPException(status_code=400, detail="Choose Replace or Merge.")
    try:
        result = import_service.apply_rows(
            session,
            training_package=training_package,
            file_name=file.filename or "upload.xlsx",
            file_size_bytes=len(payload),
            payload=payload,
            apply_mode=apply_mode.upper(),
            raise_suggestions=raise_suggestions,
            overrides=_overrides_from_form(overrides, raise_suggestions),
            user=user,
        )
        session.commit()
    except import_service.AllocationImportError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        session.rollback()
        raise
    return ImportApplyRead.model_validate(result)


@router.patch("/sessions/{session_id}", response_model=SessionRead, responses=WRITE_RESPONSES)
def patch_session(
    session_id: int,
    payload: SessionPatch,
    training_package: str = Query(...),
    actor: User = Depends(require_maintain_timetable),
    session: Session = Depends(get_db),
):
    try:
        row = edit_service.update_session(
            session,
            actor,
            session_id=session_id,
            training_package=training_package,
            weekday=payload.weekday,
            start_time=_time(payload.start_time),
            end_time=_time(payload.end_time),
            classroom=payload.classroom,
            trainer=payload.trainer,
            facility_id=payload.facility_id,
            trainer_id=payload.trainer_id,
        )
        session.commit()
    except edit_service.AllocationEditError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        session.rollback()
        raise
    return SessionRead.model_validate(row)


@router.patch("/mscris-groups", response_model=MscrisGroupRead, responses=WRITE_RESPONSES)
def patch_mscris_group(
    payload: MscrisGroupPatch,
    training_package: str = Query(...),
    actor: User = Depends(require_maintain_timetable),
    session: Session = Depends(get_db),
):
    """Edit a merged MSCRIS calendar entry: every class day it covers changes together."""
    try:
        updated = edit_service.update_mscris_group(
            session,
            actor,
            session_ids=payload.session_ids,
            training_package=training_package,
            start_time=_time(payload.start_time),
            end_time=_time(payload.end_time),
            classroom=payload.classroom,
            trainer=payload.trainer,
        )
        session.commit()
    except edit_service.AllocationEditError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        session.rollback()
        raise
    return MscrisGroupRead(updated=updated)


@router.post("/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED, responses=WRITE_RESPONSES)
def add_session(
    payload: SessionAdd,
    training_package: str = Query(...),
    actor: User = Depends(require_maintain_timetable),
    session: Session = Depends(get_db),
):
    try:
        row = edit_service.add_session(
            session,
            actor,
            delivery_id=payload.delivery_id,
            training_package=training_package,
            stream=payload.stream,
            weekday=payload.weekday,
            start_time=_time(payload.start_time),
            end_time=_time(payload.end_time),
            classroom=payload.classroom,
            trainer=payload.trainer,
        )
        session.commit()
    except edit_service.AllocationEditError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        session.rollback()
        raise
    return SessionRead.model_validate(row)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, responses=WRITE_RESPONSES)
def delete_session(
    session_id: int,
    training_package: str = Query(...),
    actor: User = Depends(require_maintain_timetable),
    session: Session = Depends(get_db),
):
    try:
        edit_service.remove_session(session, actor, session_id=session_id, training_package=training_package)
        session.commit()
    except edit_service.AllocationEditError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        session.rollback()
        raise


@router.get("/export")
def export_allocations(
    training_package: str = Query(...),
    start_date: dt.date = Query(...),
    end_date: dt.date | None = Query(default=None),
    file_format: str = Query(default="xlsx", alias="format", pattern="^(xlsx|csv)$"),
    layout: str = Query(
        default="spreadsheet",
        pattern="^(spreadsheet|source)$",
        description="spreadsheet: the Allocation Records view as shown. source: the uploaded file's own columns.",
    ),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    """Download the allocation records.

    The default is the spreadsheet view exactly as the screen shows it
    (21 September 2026); `layout=source` still rebuilds the uploaded workbook's
    own column order for a re-import.
    """
    if layout == "source":
        name, payload = export_service.export_workbook(
            session, training_package=training_package, start_date=start_date, end_date=end_date
        )
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        name, payload, media_type = export_service.export_spreadsheet(
            session,
            training_package=training_package,
            start_date=start_date,
            end_date=end_date,
            file_format=file_format,
        )
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# ===========================================================================
# Clear the allocation records — Super Admin only
# ===========================================================================


@router.get(
    "/records/clear-preview",
    response_model=ClearAllocationRead,
    responses={403: {"description": "Clearing the allocation records requires Super Admin access."}},
)
def preview_clear_allocation_records(
    _: User = Depends(require_super_admin),
    session: Session = Depends(get_db),
):
    """What a clear would remove, counted before anything is deleted."""
    return ClearAllocationRead.model_validate(maintenance_service.clear_preview(session))


@router.delete(
    "/records",
    response_model=ClearAllocationRead,
    responses={403: {"description": "Clearing the allocation records requires Super Admin access."}},
)
def clear_allocation_records(
    actor: User = Depends(require_super_admin),
    session: Session = Depends(get_db),
):
    """Delete every allocation record and the suggestions its import raised.

    Irreversible: these rows are the product of a re-runnable import, not
    business records with a recovery period. The rolling timetable, student
    records, and rolling/student-import suggestions are deliberately untouched.
    """
    try:
        removed = maintenance_service.clear_allocation_records(session, actor)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return ClearAllocationRead.model_validate(removed)
