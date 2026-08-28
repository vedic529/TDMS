"""Student Data — single entry, records, and the bulk import pipeline.

Reading is VIEWER and above; maintaining is DATA_EDITOR and above, resolved
through `require_maintain_student_data` (MAINTAIN_STUDENT_DATA). No handler
compares `user.access_level` itself (rule 2.7).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_maintain_student_data, require_viewer_or_above
from app.models.reason import ReasonCode
from app.models.user import User
from app.schemas.student import (
    ImportApplyRead,
    ImportReviewRead,
    RowsPatch,
    StudentCreate,
    StudentDeleteRequest,
    StudentList,
    StudentRead,
    StudentTimetableRead,
    StudentUpdate,
)
from app.services import student_import as import_service
from app.services import student_timetable as timetable_service
from app.services import students as service

router = APIRouter(prefix="/students", tags=["student data"])

READ_RESPONSES = {403: {"description": "Requires an active TDMS account."}}
WRITE_RESPONSES = {
    403: {"description": "Maintaining student data requires Data Editor access or above."},
    404: {"description": "Record not found."},
    409: {"description": "Conflicts with an existing enrolment."},
    422: {"description": "Invalid value or unresolved reference."},
}


def _handle(call):
    try:
        return call()
    except service.StudentServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _commit(session: Session, call):
    try:
        result = call()
        session.commit()
        return result
    except service.StudentServiceError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except import_service.StudentImportError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That change conflicts with an existing enrolment for this student.",
        ) from exc
    except Exception:
        session.rollback()
        raise


# ===========================================================================
# Records list — declared before /{id} so the literal paths win
# ===========================================================================


@router.get("", response_model=StudentList, responses=READ_RESPONSES)
def list_students(
    search: str | None = Query(default=None),
    college_id: int | None = Query(default=None),
    campus_id: int | None = Query(default=None),
    qualification_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    coe_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    items, total = service.list_students(
        session,
        search=search,
        college_id=college_id,
        campus_id=campus_id,
        qualification_id=qualification_id,
        status=status_filter,
        coe_status=coe_status,
        limit=limit,
        offset=offset,
    )
    return StudentList(items=[StudentRead(**item) for item in items], total=total, limit=limit, offset=offset)


@router.get("/deleted", response_model=StudentList, responses=READ_RESPONSES)
def list_deleted_students(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    items, total = service.list_students(session, include_deleted=True, limit=limit, offset=offset)
    return StudentList(items=[StudentRead(**item) for item in items], total=total, limit=limit, offset=offset)


# ===========================================================================
# Bulk import — declared before /{id}
# ===========================================================================


@router.post("/import/stage", response_model=ImportReviewRead, responses=WRITE_RESPONSES)
async def stage_import(
    file: UploadFile = File(...),
    user: User = Depends(require_maintain_student_data),
    session: Session = Depends(get_db),
):
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="The file is empty.")

    def run():
        batch = import_service.stage_file(
            session, user=user, file_name=file.filename or "students.csv", payload=payload
        )
        return import_service.review_dict(session, batch)

    return ImportReviewRead.model_validate(_commit(session, run))


@router.get("/import/{batch_id}", response_model=ImportReviewRead, responses=READ_RESPONSES)
def read_import(
    batch_id: int,
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    batch = _handle_import(lambda: import_service._load_batch(session, batch_id))
    return ImportReviewRead.model_validate(import_service.review_dict(session, batch))


@router.patch("/import/{batch_id}/rows", response_model=ImportReviewRead, responses=WRITE_RESPONSES)
def patch_import_rows(
    batch_id: int,
    payload: RowsPatch,
    user: User = Depends(require_maintain_student_data),
    session: Session = Depends(get_db),
):
    def run():
        batch = import_service._load_batch(session, batch_id)
        import_service.patch_rows(session, batch, payload.items)
        return import_service.review_dict(session, batch)

    return ImportReviewRead.model_validate(_commit(session, run))


@router.post("/import/{batch_id}/apply", response_model=ImportApplyRead, responses=WRITE_RESPONSES)
def apply_import(
    batch_id: int,
    user: User = Depends(require_maintain_student_data),
    session: Session = Depends(get_db),
):
    def run():
        batch = import_service._load_batch(session, batch_id)
        return import_service.apply_batch(session, batch, user)

    return ImportApplyRead.model_validate(_commit(session, run))


@router.delete("/import/{batch_id}", status_code=status.HTTP_204_NO_CONTENT, responses=WRITE_RESPONSES)
def abandon_import(
    batch_id: int,
    user: User = Depends(require_maintain_student_data),
    session: Session = Depends(get_db),
):
    def run():
        batch = import_service._load_batch(session, batch_id)
        import_service.abandon_batch(session, batch)

    _commit(session, run)


# ===========================================================================
# Show Timetable — declared before /{id} so the literal path wins
# ===========================================================================


@router.get("/{student_id}/timetable", response_model=StudentTimetableRead, responses=READ_RESPONSES)
def read_student_timetable(
    student_id: int,
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    """This student's own units, drawn from their intake.

    Read-only and never cached: the rows are derived when this is called, so a
    resolved suggestion or an edited session appears the next time it opens.
    Costs three queries, or one when the student has no intake at all.
    """
    return StudentTimetableRead.model_validate(
        _handle(lambda: timetable_service.student_timetable(session, student_id))
    )


# ===========================================================================
# Single record
# ===========================================================================


@router.get("/{student_id}", response_model=StudentRead, responses=READ_RESPONSES)
def read_student(
    student_id: int,
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return StudentRead(**_handle(lambda: service.get_student(session, student_id)))


@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED, responses=WRITE_RESPONSES)
def create_student(
    payload: StudentCreate,
    actor: User = Depends(require_maintain_student_data),
    session: Session = Depends(get_db),
):
    return StudentRead(**_commit(session, lambda: service.create_student(session, actor, payload)))


@router.patch("/{student_id}", response_model=StudentRead, responses=WRITE_RESPONSES)
def update_student(
    student_id: int,
    payload: StudentUpdate,
    actor: User = Depends(require_maintain_student_data),
    session: Session = Depends(get_db),
):
    return StudentRead(**_commit(session, lambda: service.update_student(session, actor, student_id, payload)))


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT, responses=WRITE_RESPONSES)
def delete_student(
    student_id: int,
    payload: StudentDeleteRequest,
    actor: User = Depends(require_maintain_student_data),
    session: Session = Depends(get_db),
):
    def run():
        reason = session.execute(
            select(ReasonCode).where(ReasonCode.code == payload.reason_code)
        ).scalar_one_or_none()
        if reason is None:
            raise service.StudentServiceError(422, "A valid deletion reason is required.")
        service.delete_student(
            session, actor, student_id, reason_code_id=reason.id, reason_detail=payload.reason_detail
        )

    _commit(session, run)


@router.post("/{student_id}/restore", response_model=StudentRead, responses=WRITE_RESPONSES)
def restore_student(
    student_id: int,
    actor: User = Depends(require_maintain_student_data),
    session: Session = Depends(get_db),
):
    return StudentRead(**_commit(session, lambda: service.restore_student(session, actor, student_id)))


def _handle_import(call):
    try:
        return call()
    except import_service.StudentImportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
