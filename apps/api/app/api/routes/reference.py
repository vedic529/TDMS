"""College and Course Reference Data — the real API (Step 6).

Route handlers do three things: authorise, call one service function, translate
the outcome. Business rules live in `app.services.reference_data`.

**Authorisation for this module.** Reading and exporting is VIEWER and above.
Maintaining is **ADMIN and above** — a Data Editor maintains Student Data and
Timetables, and is read-and-download only here. `require_maintain_reference_data`
is the single dependency that says so; no handler decides for itself.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db,
    require_maintain_reference_data,
    require_viewer_or_above,
)
from app.models.course import CourseOffering
from app.models.qualification import QualificationUnit
from app.models.user import User
from app.schemas import reference as schemas
from app.services import reference_data as service

router = APIRouter(prefix="/reference", tags=["reference data"])

#: Documented once and reused, so every maintenance route advertises the same
#: failure modes in the OpenAPI document.
WRITE_RESPONSES = {
    403: {"description": "Maintaining reference data requires Admin access or above."},
    404: {"description": "Record not found."},
    409: {"description": "Duplicate or conflicting approved reference."},
    422: {"description": "Invalid value or relationship."},
}
READ_RESPONSES = {403: {"description": "Requires an active TDMS account."}}


def _handle(call):
    """Run a service call, converting its refusals into HTTP responses.

    A single translation point means no route can accidentally return a raw
    database error, and the status codes stay consistent across the module.
    """
    try:
        return call()
    except service.ReferenceDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _commit(session: Session, call):
    """One transaction per write. A failure rolls the whole operation back.

    Integrity errors are translated here as well as in the service, because
    `uq_qualification_units_qualification_id_delivery_order` is DEFERRABLE
    INITIALLY DEFERRED — it is enforced at COMMIT, not at flush. Without this a
    genuine race would surface as a 500 with driver text in it.
    """
    try:
        result = call()
        session.commit()
        return result
    except service.ReferenceDataError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "That change conflicts with an existing approved record. "
                "Another user may have just saved the same value."
            ),
        ) from exc
    except Exception:
        session.rollback()
        raise


# ===========================================================================
# College
# ===========================================================================


@router.get("/colleges", response_model=list[schemas.CollegeRead], responses=READ_RESPONSES)
def list_colleges(
    search: str | None = Query(default=None, description="Matches short or full name."),
    active_only: bool = Query(default=False, description="Only colleges available for new records."),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return service.list_colleges(session, search=search, active_only=active_only)


@router.get("/colleges/{college_id}", response_model=schemas.CollegeRead, responses=READ_RESPONSES)
def read_college(
    college_id: int,
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return _handle(lambda: service.get_college(session, college_id))


@router.post(
    "/colleges",
    response_model=schemas.CollegeRead,
    status_code=status.HTTP_201_CREATED,
    responses=WRITE_RESPONSES,
)
def create_college(
    payload: schemas.CollegeCreate,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    return _commit(session, lambda: service.create_college(session, actor, payload))


@router.patch(
    "/colleges/{college_id}", response_model=schemas.CollegeRead, responses=WRITE_RESPONSES
)
def update_college(
    college_id: int,
    payload: schemas.CollegeUpdate,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    return _commit(session, lambda: service.update_college(session, actor, college_id, payload))


# ===========================================================================
# Campus
# ===========================================================================


@router.get("/campuses", response_model=list[schemas.CampusRead], responses=READ_RESPONSES)
def list_campuses(
    search: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    college_id: int | None = Query(
        default=None,
        description="Restrict to campuses approved for this college (COL-01). Applied in SQL.",
    ),
    college_ids: list[int] | None = Query(
        default=None,
        description=(
            "Repeatable. The union of campuses approved for these colleges, "
            "deduplicated. Empty means every campus."
        ),
    ),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return service.list_campuses(
        session,
        search=search,
        active_only=active_only,
        college_id=college_id,
        college_ids=college_ids,
    )


@router.get("/campuses/{campus_id}", response_model=schemas.CampusRead, responses=READ_RESPONSES)
def read_campus(
    campus_id: int,
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return _handle(lambda: service.get_campus(session, campus_id))


@router.post(
    "/campuses",
    response_model=schemas.CampusRead,
    status_code=status.HTTP_201_CREATED,
    responses=WRITE_RESPONSES,
)
def create_campus(
    payload: schemas.CampusCreate,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    return _commit(session, lambda: service.create_campus(session, actor, payload))


@router.patch("/campuses/{campus_id}", response_model=schemas.CampusRead, responses=WRITE_RESPONSES)
def update_campus(
    campus_id: int,
    payload: schemas.CampusUpdate,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    return _commit(session, lambda: service.update_campus(session, actor, campus_id, payload))


@router.get(
    "/college-campuses", response_model=list[schemas.CollegeCampusRead], responses=READ_RESPONSES
)
def list_college_campuses(
    college_id: int | None = Query(default=None),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return service.list_college_campuses(session, college_id=college_id)


@router.post(
    "/college-campuses",
    response_model=schemas.CollegeCampusRead,
    status_code=status.HTTP_201_CREATED,
    responses=WRITE_RESPONSES,
)
def approve_college_campus(
    payload: schemas.CollegeCampusLink,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    """Approve a campus for a college (COL-01). A campus may serve several."""
    return _commit(session, lambda: service.link_college_campus(session, actor, payload))


# ===========================================================================
# Qualification
# ===========================================================================


@router.get(
    "/qualifications", response_model=list[schemas.QualificationRead], responses=READ_RESPONSES
)
def list_qualifications(
    search: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    college_ids: list[int] | None = Query(
        default=None, description="Restrict to qualifications offered by these colleges."
    ),
    campus_ids: list[int] | None = Query(
        default=None, description="Restrict to qualifications offered at these campuses."
    ),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    """Qualifications, optionally only those actually offered in a scope.

    With a college or campus supplied this answers "what is offered here?" from
    `course_offerings`. Without one it returns the full table, which is what a
    maintenance form needs. The two questions are different and the caller says
    which it is asking.
    """
    if college_ids or campus_ids:
        return service.list_offered_qualifications(
            session, college_ids=college_ids, campus_ids=campus_ids, active_only=active_only
        )
    return service.list_qualifications(session, search=search, active_only=active_only)


@router.get(
    "/qualifications/{qualification_id}",
    response_model=schemas.QualificationRead,
    responses=READ_RESPONSES,
)
def read_qualification(
    qualification_id: int,
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return _handle(lambda: service.get_qualification(session, qualification_id))


@router.post(
    "/qualifications",
    response_model=schemas.QualificationRead,
    status_code=status.HTTP_201_CREATED,
    responses=WRITE_RESPONSES,
)
def create_qualification(
    payload: schemas.QualificationCreate,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    return _commit(session, lambda: service.create_qualification(session, actor, payload))


@router.patch(
    "/qualifications/{qualification_id}",
    response_model=schemas.QualificationRead,
    responses=WRITE_RESPONSES,
)
def update_qualification(
    qualification_id: int,
    payload: schemas.QualificationUpdate,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    return _commit(
        session, lambda: service.update_qualification(session, actor, qualification_id, payload)
    )


# ===========================================================================
# Unit
# ===========================================================================


@router.get("/units", response_model=list[schemas.UnitRead], responses=READ_RESPONSES)
def list_units(
    search: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    qualification_id: int | None = Query(
        default=None, description="Units in this qualification's approved sequence, in order."
    ),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return service.list_units(
        session, search=search, active_only=active_only, qualification_id=qualification_id
    )


@router.get("/units/{unit_id}", response_model=schemas.UnitRead, responses=READ_RESPONSES)
def read_unit(
    unit_id: int,
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return _handle(lambda: service.get_unit(session, unit_id))


@router.post(
    "/units",
    response_model=schemas.UnitRead,
    status_code=status.HTTP_201_CREATED,
    responses=WRITE_RESPONSES,
)
def create_unit(
    payload: schemas.UnitCreate,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    return _commit(session, lambda: service.create_unit(session, actor, payload))


@router.patch("/units/{unit_id}", response_model=schemas.UnitRead, responses=WRITE_RESPONSES)
def update_unit(
    unit_id: int,
    payload: schemas.UnitUpdate,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    return _commit(session, lambda: service.update_unit(session, actor, unit_id, payload))


# ===========================================================================
# Qualification / Unit delivery sequence (Page 4B)
# ===========================================================================


def _qualification_unit_read(link: QualificationUnit) -> schemas.QualificationUnitRead:
    return schemas.QualificationUnitRead(
        id=link.id,
        qualification_id=link.qualification_id,
        qualification_code=link.qualification.qualification_code,
        qualification_title=link.qualification.qualification_title,
        unit_id=link.unit_id,
        unit_code=link.unit.unit_code,
        unit_title=link.unit.unit_title,
        uoc_type=link.unit.uoc_type,
        delivery_order=link.delivery_order,
        is_deleted=link.is_deleted,
    )


@router.get(
    "/qualification-units",
    response_model=list[schemas.QualificationUnitRead],
    responses=READ_RESPONSES,
)
def list_qualification_units(
    qualification_id: int | None = Query(default=None),
    college_ids: list[int] | None = Query(default=None),
    campus_ids: list[int] | None = Query(default=None),
    qualification_ids: list[int] | None = Query(default=None),
    search: str | None = Query(default=None),
    include_deleted: bool = Query(
        default=False, description="Return the recycle area instead of the active sequence."
    ),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    rows = service.list_qualification_units(
        session,
        qualification_id=qualification_id,
        college_ids=college_ids,
        campus_ids=campus_ids,
        qualification_ids=qualification_ids,
        search=search,
        include_deleted=include_deleted,
    )
    return [_qualification_unit_read(row) for row in rows]


@router.post(
    "/qualification-units",
    response_model=schemas.QualificationUnitRead,
    status_code=status.HTTP_201_CREATED,
    responses=WRITE_RESPONSES,
)
def create_qualification_unit(
    payload: schemas.QualificationUnitCreate,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    link = _commit(session, lambda: service.create_qualification_unit(session, actor, payload))
    session.refresh(link)
    return _qualification_unit_read(link)


@router.patch(
    "/qualification-units/{link_id}",
    response_model=schemas.QualificationUnitRead,
    responses=WRITE_RESPONSES,
)
def update_qualification_unit(
    link_id: int,
    payload: schemas.QualificationUnitUpdate,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    link = _commit(
        session, lambda: service.update_qualification_unit(session, actor, link_id, payload)
    )
    session.refresh(link)
    return _qualification_unit_read(link)


@router.delete(
    "/qualification-units/{link_id}",
    response_model=schemas.QualificationUnitRead,
    responses=WRITE_RESPONSES,
)
def delete_qualification_unit(
    link_id: int,
    payload: schemas.DeleteRequest,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    """Soft delete with an approved reason (DATA-04). The row is recoverable."""
    link = _commit(
        session, lambda: service.delete_qualification_unit(session, actor, link_id, payload)
    )
    session.refresh(link)
    return _qualification_unit_read(link)


@router.post(
    "/qualification-units/{link_id}/restore",
    response_model=schemas.QualificationUnitRead,
    responses=WRITE_RESPONSES,
)
def restore_qualification_unit(
    link_id: int,
    payload: schemas.RestoreRequest,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    link = _commit(
        session, lambda: service.restore_qualification_unit(session, actor, link_id, payload)
    )
    session.refresh(link)
    return _qualification_unit_read(link)


# ===========================================================================
# Course offering (Page 4A "Course Data")
# ===========================================================================


def _offering_read(session: Session, offering: CourseOffering) -> schemas.CourseOfferingRead:
    """Compose the Page 4A view.

    The qualification attributes and the campus location live on their own
    entities. C-3: `location` is the campus value, derived rather than stored a
    second time, so the two cannot drift apart.
    """
    college = offering.college if hasattr(offering, "college") else None
    college = college or service.get_college(session, offering.college_id)
    campus = service.get_campus(session, offering.campus_id)
    qualification = service.get_qualification(session, offering.qualification_id)
    status_row = offering.course_status

    return schemas.CourseOfferingRead(
        id=offering.id,
        course_code=offering.course_code,
        college_id=college.id,
        college_short_name=college.college_short_name,
        college_full_name=college.college_full_name,
        campus_id=campus.id,
        campus_name=campus.campus_name,
        location=campus.campus_location,
        state=campus.state,
        qualification_id=qualification.id,
        qualification_code=qualification.qualification_code,
        # Retired codes that resolve to this qualification. A student file still
        # carrying CHC30121 belongs to CHC30125, and the caller should not have
        # to know which codes were superseded to match it.
        qualification_superseded_codes=[
            row.superseded_code for row in qualification.supersessions
        ],
        qualification_title=qualification.qualification_title,
        course_level=qualification.course_level,
        field_of_education_broad=qualification.field_of_education_broad,
        field_of_education_narrow=qualification.field_of_education_narrow,
        course_sector=qualification.course_sector,
        source_url=qualification.source_url,
        course_status_id=status_row.id,
        course_status_code=status_row.code,
        course_status_label=status_row.label,
        selectable_for_new_records=status_row.selectable_for_new_records,
        total_course_cost=offering.total_course_cost,
        duration_options=sorted(o.duration_weeks for o in offering.duration_options if o.is_active),
        is_deleted=offering.is_deleted,
        deleted_at=offering.deleted_at,
        recovery_deadline=offering.recovery_deadline,
        created_at=offering.created_at,
        updated_at=offering.updated_at,
    )


@router.get("/courses", response_model=list[schemas.CourseOfferingRead], responses=READ_RESPONSES)
def list_courses(
    search: str | None = Query(default=None),
    college_id: int | None = Query(default=None),
    campus_id: int | None = Query(default=None),
    qualification_id: int | None = Query(default=None),
    college_ids: list[int] | None = Query(
        default=None, description="Repeatable. Empty means every college."
    ),
    campus_ids: list[int] | None = Query(
        default=None, description="Repeatable. Empty means every campus."
    ),
    qualification_ids: list[int] | None = Query(
        default=None, description="Repeatable. Empty means every qualification."
    ),
    course_status_code: str | None = Query(
        default=None, description="Approved course status code, e.g. ACTIVE."
    ),
    include_deleted: bool = Query(
        default=False, description="Return the recycle area instead of active records."
    ),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    rows = service.list_course_offerings(
        session,
        search=search,
        college_id=college_id,
        campus_id=campus_id,
        qualification_id=qualification_id,
        college_ids=college_ids,
        campus_ids=campus_ids,
        qualification_ids=qualification_ids,
        course_status_code=course_status_code,
        include_deleted=include_deleted,
    )
    return [_offering_read(session, row) for row in rows]


@router.get(
    "/courses/{offering_id}", response_model=schemas.CourseOfferingRead, responses=READ_RESPONSES
)
def read_course(
    offering_id: int,
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    offering = _handle(lambda: service.get_course_offering(session, offering_id))
    return _offering_read(session, offering)


@router.post(
    "/courses",
    response_model=schemas.CourseOfferingRead,
    status_code=status.HTTP_201_CREATED,
    responses=WRITE_RESPONSES,
)
def create_course(
    payload: schemas.CourseOfferingCreate,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    offering = _commit(session, lambda: service.create_course_offering(session, actor, payload))
    session.refresh(offering)
    return _offering_read(session, offering)


@router.patch(
    "/courses/{offering_id}", response_model=schemas.CourseOfferingRead, responses=WRITE_RESPONSES
)
def update_course(
    offering_id: int,
    payload: schemas.CourseOfferingUpdate,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    offering = _commit(
        session, lambda: service.update_course_offering(session, actor, offering_id, payload)
    )
    session.refresh(offering)
    return _offering_read(session, offering)


@router.delete(
    "/courses/{offering_id}", response_model=schemas.CourseOfferingRead, responses=WRITE_RESPONSES
)
def delete_course(
    offering_id: int,
    payload: schemas.DeleteRequest,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    offering = _commit(
        session, lambda: service.delete_course_offering(session, actor, offering_id, payload)
    )
    session.refresh(offering)
    return _offering_read(session, offering)


@router.post(
    "/courses/{offering_id}/restore",
    response_model=schemas.CourseOfferingRead,
    responses=WRITE_RESPONSES,
)
def restore_course(
    offering_id: int,
    payload: schemas.RestoreRequest,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    offering = _commit(
        session, lambda: service.restore_course_offering(session, actor, offering_id, payload)
    )
    session.refresh(offering)
    return _offering_read(session, offering)


@router.get(
    "/course-statuses", response_model=list[schemas.CourseStatusRead], responses=READ_RESPONSES
)
def list_course_statuses(
    active_only: bool = Query(default=False),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    return service.list_course_statuses(session, active_only=active_only)
