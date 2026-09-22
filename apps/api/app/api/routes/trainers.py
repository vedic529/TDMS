"""Trainer Data — list, detail, unit coverage, manual add, and the bulk import.

Reading is VIEWER and above; maintaining is **ADMIN and above**, resolved
through `require_maintain_trainer_data` (MAINTAIN_TRAINER_DATA). No handler
compares `user.access_level` itself.

**Every literal path is declared before `/{trainer_id}`**, or `/unit-coverage`
and `/import/...` would be captured by the parameterised route — the convention
`routes/students.py` documents.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db,
    require_maintain_trainer_data,
    require_super_admin,
    require_viewer_or_above,
)
from app.models.user import User
from app.schemas.trainer import (
    ClearTrainersCounts,
    GeneratedTrainerId,
    ImportApplyRead,
    ImportReviewRead,
    LocationWrite,
    RaiseValuesRequest,
    RowsPatch,
    TrainerCreate,
    TrainerDeleteRequest,
    TrainerDetailRead,
    TrainerList,
    TrainerRead,
    TrainerTimetableRead,
    TrainerTimetableStudentList,
    TrainerUpdate,
    UnitCoverageList,
    UnitsWrite,
)
from app.services import trainer_import as import_service
from app.services import trainers as service
from app.services import trainer_timetable

router = APIRouter(prefix="/trainers", tags=["trainer data"])

READ_RESPONSES = {403: {"description": "Requires an active TDMS account."}}
WRITE_RESPONSES = {
    403: {"description": "Maintaining trainer data requires Admin access or above."},
    404: {"description": "Record not found."},
    409: {"description": "Conflicts with an existing trainer record."},
    422: {"description": "Invalid value or unresolved reference."},
}


def _commit(session: Session, call):
    """Run a service call, translating its refusals into HTTP responses."""
    try:
        result = call()
        session.commit()
        return result
    except (service.TrainerError, import_service.TrainerImportError) as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That change conflicts with an existing trainer record.",
        ) from exc
    except Exception:
        session.rollback()
        raise


def _read(call):
    try:
        return call()
    except (service.TrainerError, import_service.TrainerImportError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ===========================================================================
# Unit coverage — declared before /{trainer_id} so the literal path wins
# ===========================================================================


@router.get("/unit-coverage", response_model=UnitCoverageList, responses=READ_RESPONSES)
def unit_coverage(
    qualification_id: int | None = Query(default=None),
    only_uncovered: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    """Every unit, with how many trainers can teach it.

    A unit no trainer covers still appears — that gap is the point of the view.
    """
    items, total = service.unit_coverage(
        session,
        qualification_id=qualification_id,
        only_uncovered=only_uncovered,
        limit=limit,
        offset=offset,
    )
    return UnitCoverageList(items=items, total=total)


@router.get("/next-id", response_model=GeneratedTrainerId, responses=READ_RESPONSES)
def next_trainer_id(
    name: str = Query(default="", description="The trainer's name, as typed so far."),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    """The id this trainer would be given, previewed while the name is typed.

    Nothing is reserved: the id is generated again when the record is actually
    created, so two people filling the form at once cannot both take TI_010.
    """
    sequence = service.next_trainer_sequence(session)
    initials = service.trainer_initials(name)
    return GeneratedTrainerId(
        trainer_id=f"TI_{sequence:03d}_{initials}", sequence=sequence, initials=initials
    )


# ===========================================================================
# Clearing the trainer database — Super Admin only
# ===========================================================================


@router.get("/records/clear-preview", response_model=ClearTrainersCounts, responses=READ_RESPONSES)
def clear_trainers_preview(
    _: User = Depends(require_super_admin),
    session: Session = Depends(get_db),
):
    return service.clear_preview(session)


@router.delete("/records", response_model=ClearTrainersCounts, responses=WRITE_RESPONSES)
def clear_trainers(
    user: User = Depends(require_super_admin),
    session: Session = Depends(get_db),
):
    """Delete every trainer record. Irreversible.

    Allocation sessions keep the trainer's name and return to the suggestion
    queue rather than losing it, and numbering restarts at TI_001.
    """
    return _commit(session, lambda: service.clear_trainer_records(session, user))


# ===========================================================================
# Bulk import — declared before /{trainer_id}
# ===========================================================================


@router.post("/import/stage", response_model=ImportReviewRead, responses=WRITE_RESPONSES)
async def stage_import(
    data_type: str = Form(..., description="LOCATION or UNITS. Never a training package."),
    file: UploadFile = File(...),
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    payload = await file.read()
    return _commit(
        session,
        lambda: import_service.stage_file(
            session,
            data_type=data_type.upper(),
            file_name=file.filename or "upload.xlsx",
            payload=payload,
            user=user,
        ),
    )


@router.get("/import/{batch_id}", response_model=ImportReviewRead, responses=READ_RESPONSES)
def read_import(
    batch_id: int,
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return _read(lambda: import_service.read_batch(session, batch_id))


@router.patch("/import/{batch_id}/rows", response_model=ImportReviewRead, responses=WRITE_RESPONSES)
def patch_import_rows(
    batch_id: int,
    payload: RowsPatch,
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    return _commit(
        session,
        lambda: import_service.patch_rows(
            session,
            batch_id,
            corrections=payload.corrections,
            excluded_row_ids=payload.excluded_row_ids,
            exclude_missing_trainers=payload.exclude_missing_trainers,
            override_decisions=payload.override_decisions,
            accepted_exception_row_ids=payload.accepted_exception_row_ids,
            withdrawn_exception_row_ids=payload.withdrawn_exception_row_ids,
            included_row_ids=payload.included_row_ids,
            user=user,
        ),
    )


@router.post(
    "/import/{batch_id}/suggestions", response_model=ImportReviewRead, responses=WRITE_RESPONSES
)
def raise_import_suggestions(
    batch_id: int,
    payload: RaiseValuesRequest,
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    """Raise a suggestion for the chosen unmatched values.

    Create Record and Map Record are the only resolutions offered afterwards;
    there is deliberately no accept-as-an-exception path for a qualification or
    a unit (1.8).
    """

    def run():
        keys = payload.keys
        if payload.all:
            keys = [entry["key"] for entry in import_service.collect_unresolved(session, batch_id)]
        import_service.raise_values(session, batch_id, keys=keys, user=user)
        return import_service.read_batch(session, batch_id)

    return _commit(session, run)


@router.post("/import/{batch_id}/apply", response_model=ImportApplyRead, responses=WRITE_RESPONSES)
def apply_import(
    batch_id: int,
    apply_mode: str = Query(default="MERGE", description="MERGE or REPLACE."),
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    return _commit(
        session,
        lambda: import_service.apply_batch(session, batch_id, apply_mode=apply_mode, user=user),
    )


@router.delete("/import/{batch_id}", status_code=status.HTTP_204_NO_CONTENT, responses=WRITE_RESPONSES)
def abandon_import(
    batch_id: int,
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    _commit(session, lambda: import_service.abandon(session, batch_id, user=user))
    return None


# ===========================================================================
# Records
# ===========================================================================


@router.get("/{trainer_id}/timetable", response_model=TrainerTimetableRead, responses=READ_RESPONSES)
def read_trainer_timetable(
    trainer_id: int,
    month: dt.date = Query(description="Any date in the selected month."),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return _read(lambda: trainer_timetable.calendar_month(session, trainer_id, month))


@router.get(
    "/{trainer_id}/timetable/students",
    response_model=TrainerTimetableStudentList,
    responses=READ_RESPONSES,
)
def read_trainer_timetable_students(
    trainer_id: int,
    class_date: dt.date = Query(),
    session_ids: list[int] = Query(),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return _read(
        lambda: trainer_timetable.attending_students(session, trainer_id, class_date, session_ids)
    )


@router.get("", response_model=TrainerList, responses=READ_RESPONSES)
def list_trainers(
    search: str | None = Query(default=None),
    campus_id: int | None = Query(default=None),
    qualification_id: int | None = Query(default=None),
    unit_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    """One row per trainer, however many locations they work at."""
    items, total = service.list_trainers(
        session,
        search=search,
        campus_id=campus_id,
        qualification_id=qualification_id,
        unit_id=unit_id,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return TrainerList(
        items=[TrainerRead(**item) for item in items], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=TrainerDetailRead, responses=WRITE_RESPONSES, status_code=201)
def create_trainer(
    payload: TrainerCreate,
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    return _commit(
        session, lambda: service.create_trainer(session, data=payload.model_dump(), user=user)
    )


@router.get("/{trainer_id}", response_model=TrainerDetailRead, responses=READ_RESPONSES)
def get_trainer(
    trainer_id: int,
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    """The whole side panel in one round trip — locations with their weekdays,
    qualifications with their units nested inside them."""
    return _read(lambda: service.get_trainer(session, trainer_id))


@router.patch("/{trainer_id}", response_model=TrainerDetailRead, responses=WRITE_RESPONSES)
def update_trainer(
    trainer_id: int,
    payload: TrainerUpdate,
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    return _commit(
        session,
        lambda: service.update_trainer(
            session, trainer_id, data=payload.model_dump(exclude_unset=True), user=user
        ),
    )


@router.delete("/{trainer_id}", status_code=status.HTTP_204_NO_CONTENT, responses=WRITE_RESPONSES)
def delete_trainer(
    trainer_id: int,
    payload: TrainerDeleteRequest,
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    """Soft delete with a reason (DATA-04). The record stays recoverable."""
    _commit(
        session,
        lambda: service.delete_trainer(
            session,
            trainer_id,
            reason_code_id=payload.reason_code_id,
            reason_note=payload.reason_note,
            user=user,
        ),
    )
    return None


@router.post("/{trainer_id}/restore", response_model=TrainerDetailRead, responses=WRITE_RESPONSES)
def restore_trainer(
    trainer_id: int,
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    return _commit(session, lambda: service.restore_trainer(session, trainer_id, user=user))


# ===========================================================================
# Locations and units (1.6)
# ===========================================================================


@router.post("/{trainer_id}/locations", response_model=TrainerDetailRead, responses=WRITE_RESPONSES)
def add_location(
    trainer_id: int,
    payload: LocationWrite,
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    return _commit(
        session, lambda: service.add_location(session, trainer_id, data=payload.model_dump(), user=user)
    )


@router.patch(
    "/{trainer_id}/locations/{availability_id}",
    response_model=TrainerDetailRead,
    responses=WRITE_RESPONSES,
)
def update_location(
    trainer_id: int,
    availability_id: int,
    payload: LocationWrite,
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    return _commit(
        session,
        lambda: service.update_location(
            session,
            trainer_id,
            availability_id,
            data=payload.model_dump(exclude_unset=True),
            user=user,
        ),
    )


@router.delete(
    "/{trainer_id}/locations/{availability_id}",
    response_model=TrainerDetailRead,
    responses=WRITE_RESPONSES,
)
def remove_location(
    trainer_id: int,
    availability_id: int,
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    return _commit(
        session, lambda: service.remove_location(session, trainer_id, availability_id, user=user)
    )


@router.post("/{trainer_id}/units", response_model=TrainerDetailRead, responses=WRITE_RESPONSES)
def add_units(
    trainer_id: int,
    payload: UnitsWrite,
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    """One qualification and many units, in one call."""
    return _commit(
        session, lambda: service.add_units(session, trainer_id, data=payload.model_dump(), user=user)
    )


@router.delete(
    "/{trainer_id}/units/{link_id}", response_model=TrainerDetailRead, responses=WRITE_RESPONSES
)
def remove_unit_link(
    trainer_id: int,
    link_id: int,
    user: User = Depends(require_maintain_trainer_data),
    session: Session = Depends(get_db),
):
    return _commit(session, lambda: service.remove_unit_link(session, trainer_id, link_id, user=user))
