"""Rolling Timetable — Database View, Visualizer, and import."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_maintain_timetable, require_viewer_or_above
from app.models.user import User
from app.schemas.rolling_timetable import (
    ImportApplyRead,
    ImportReviewRead,
    RollingFacetsRead,
    RollingScopeRead,
    RollingWeekBulkPatch,
    RollingWeekBulkRead,
    RollingWeekList,
    RollingWeekRead,
    VisualizerRead,
)
from app.services import rolling_timetable_store as store
from app.services.rolling_timetable_import import RollingImportError, apply_rows, review_to_dict, validate_bytes

router = APIRouter(prefix="/rolling-timetable", tags=["rolling timetable"])
READ_RESPONSES = {403: {"description": "Requires an active TDMS account."}}
WRITE_RESPONSES = {
    403: {"description": "Requires Data Editor access or above."},
    400: {"description": "The file was refused."},
    404: {"description": "Record not found."},
}


@router.get("/scopes", response_model=list[RollingScopeRead], responses=READ_RESPONSES)
def list_scopes(
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return [RollingScopeRead.model_validate(item) for item in store.list_scopes(session)]


@router.get("/facets", response_model=RollingFacetsRead, responses=READ_RESPONSES)
def list_facets(
    training_package: str = Query(...),
    qualification_code: str = Query(...),
    duration_weeks: int = Query(...),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return RollingFacetsRead.model_validate(
        store.list_facets(session, training_package, qualification_code, duration_weeks)
    )


@router.get("/weeks", response_model=RollingWeekList, responses=READ_RESPONSES)
def list_weeks(
    training_package: str | None = Query(default=None),
    qualification_code: str | None = Query(default=None),
    duration_weeks: int | None = Query(default=None),
    intake_label: str | None = Query(default=None),
    week_no: int | None = Query(default=None),
    schedule_type: str | None = Query(default=None),
    unit_code: str | None = Query(default=None),
    week_start_from: dt.date | None = Query(default=None),
    week_start_to: dt.date | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="week_no"),
    direction: str = Query(default="asc"),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    rows, total = store.list_weeks(
        session,
        store.WeekQuery(
            training_package=training_package,
            qualification_code=qualification_code,
            duration_weeks=duration_weeks,
            intake_label=intake_label,
            week_no=week_no,
            schedule_type=schedule_type,
            unit_code=unit_code,
            week_start_from=week_start_from,
            week_start_to=week_start_to,
            search=search,
            limit=limit,
            offset=offset,
            sort=sort,
            direction=direction,
        ),
    )
    return RollingWeekList(
        items=[RollingWeekRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/weeks", response_model=RollingWeekBulkRead, responses=WRITE_RESPONSES)
def update_weeks(
    payload: RollingWeekBulkPatch,
    actor: User = Depends(require_maintain_timetable),
    session: Session = Depends(get_db),
):
    try:
        rows = store.update_weeks(
            session,
            actor,
            [(item.id, item.schedule_type, item.schedule_value) for item in payload.items],
        )
        session.commit()
    except store.RollingStoreError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        session.rollback()
        raise
    return RollingWeekBulkRead(items=[RollingWeekRead.model_validate(row) for row in rows])


@router.get("/visualizer", response_model=VisualizerRead, responses=READ_RESPONSES)
def read_visualizer(
    training_package: str = Query(...),
    qualification_code: str = Query(...),
    duration_weeks: int = Query(...),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    payload = store.visualizer_grid(session, training_package, qualification_code, duration_weeks)
    return VisualizerRead.model_validate(payload)


async def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    name = file.filename or "upload.csv"
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The file is empty.")
    return name, payload


@router.post("/import/validate", response_model=ImportReviewRead, responses=WRITE_RESPONSES)
async def validate_import(
    training_package: str = Form(...),
    file: UploadFile = File(...),
    _: User = Depends(require_maintain_timetable),
    session: Session = Depends(get_db),
):
    name, payload = await _read_upload(file)
    try:
        review, _rows = validate_bytes(
            session, training_package=training_package, file_name=name, payload=payload
        )
    except RollingImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ImportReviewRead.model_validate(review_to_dict(review))


@router.post("/import/apply", response_model=ImportApplyRead, responses=WRITE_RESPONSES)
async def apply_import(
    training_package: str = Form(...),
    proceed_with_matching: bool = Form(default=False),
    file: UploadFile = File(...),
    user: User = Depends(require_maintain_timetable),
    session: Session = Depends(get_db),
):
    name, payload = await _read_upload(file)
    try:
        result = apply_rows(
            session,
            training_package=training_package,
            file_name=name,
            payload=payload,
            proceed_with_matching=proceed_with_matching,
            user=user,
        )
        session.commit()
    except RollingImportError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        session.rollback()
        raise
    return ImportApplyRead(
        rows_written=result.rows_written,
        qualifications_replaced=result.qualifications_replaced,
        qualifications_skipped=result.qualifications_skipped,
        rows_read=result.rows_read,
    )
