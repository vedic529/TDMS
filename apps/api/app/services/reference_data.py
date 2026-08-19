"""College and Course Reference Data — business rules and data access.

Route handlers stay thin: they authorise, call one function here, and translate
the result. Every rule that decides whether a write is legal lives in this
module, so there is one place to read when asking "can that happen?".

Two habits run through it:

* **Database constraints are the backstop, not the message.** Each rule is
  pre-checked so the user gets "Course Code CRS-001 is already used" rather than
  a `UniqueViolation`. The constraint still exists and still fires under a race —
  it is caught and translated, never leaked.
* **One transaction per operation.** A multi-entity write (an offering plus its
  duration options) either lands whole or not at all.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field as dc_field
from typing import Iterable, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.college import Campus, College, CollegeCampus
from app.models.course import CourseOffering, CourseStatus, OfferingDurationOption
from app.models.qualification import Qualification, QualificationUnit, Unit
from app.models.reason import ReasonCode
from app.models.user import User
from app.schemas import reference as schemas
from app.services.activity import record_activity

PAGE_COURSE_DATA = "Page 4A - Course Data"
PAGE_QUALIFICATION_UNITS = "Page 4B - Qualification and Unit Sequence Data"
PAGE_REFERENCE = "College and Course Reference Data"

#: How a missing Qualification Code reads in an activity record or a message.
#: The database stores NULL; people read "NA".
NO_CODE_LABEL = "NA"

# ---------------------------------------------------------------------------
# Course status of a supplied course (approved 12 August 2026)
# ---------------------------------------------------------------------------
#
# **Every course supplied in an approved source workbook is ACTIVE in TDMS.**
#
# The source's own wording — "Registered", "Current", "Approved", "Listed" —
# describes an *external* registration state, not TDMS operational availability.
# The two are different things and must not be confused: a course registered
# with a regulator is exactly the course TDMS should offer for selection.
#
# This rule lives here, once. It is not repeated in the workbook parser, the
# route, or the browser: a status transformation duplicated across layers is one
# that will disagree with itself, which is precisely how 104262B came to display
# as Inactive.
SUPPLIED_COURSE_STATUS_CODE = "ACTIVE"
SUPPLIED_COURSE_STATUS_LABEL = "Active"

#: Source wordings seen in supplied workbooks. Recorded so the mapping is
#: legible, **not** so it can be reversed — anything supplied maps to ACTIVE,
#: including a term never seen before.
KNOWN_SOURCE_REGISTRATION_TERMS = frozenset(
    {"REGISTERED", "CURRENT", "APPROVED", "LISTED", "ACTIVE"}
)


def status_for_supplied_course(session: Session) -> CourseStatus:
    """The TDMS course status every project-supplied course carries.

    Creates the approved ACTIVE value on first use. The source's registration
    wording is deliberately not stored: there is no approved field for an
    external registration state, and inventing a column to hold one would be a
    schema change made for a spreadsheet's vocabulary.
    """
    status = session.execute(
        select(CourseStatus).where(
            func.upper(CourseStatus.code) == SUPPLIED_COURSE_STATUS_CODE
        )
    ).scalar_one_or_none()
    if status is not None:
        return status

    status = CourseStatus(
        code=SUPPLIED_COURSE_STATUS_CODE,
        label=SUPPLIED_COURSE_STATUS_LABEL,
        selectable_for_new_records=True,
        is_active=True,
    )
    session.add(status)
    session.flush()
    return status


def code_label(code: str | None) -> str:
    """Display form of a Qualification Code that may not have been issued."""
    return code or NO_CODE_LABEL


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ReferenceDataError(Exception):
    """A refusal the caller should see. `status_code` is the HTTP status."""

    status_code = 400

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NotFound(ReferenceDataError):
    status_code = 404


class Duplicate(ReferenceDataError):
    status_code = 409


class InvalidReference(ReferenceDataError):
    """A submitted value or relationship the business rules do not allow."""

    status_code = 422


class InUse(ReferenceDataError):
    """Refused because historical records depend on the row (DATA-03)."""

    status_code = 409


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_or_404(session: Session, model, pk: int, label: str):
    row = session.get(model, pk)
    if row is None:
        raise NotFound(f"{label} not found.")
    return row


def _apply_search(stmt: Select, term: str | None, *columns) -> Select:
    if not term or not term.strip():
        return stmt
    pattern = f"%{term.strip()}%"
    clause = columns[0].ilike(pattern)
    for column in columns[1:]:
        clause = clause | column.ilike(pattern)
    return stmt.where(clause)


def _require_reason(session: Session, reason_code_id: int | None, detail: str | None) -> ReasonCode:
    """Validate the supplied deletion reason against the approved list.

    A reason is **mandatory**. The approved soft-delete CHECK constraint requires
    the whole metadata group — timestamp, actor, reason and recovery deadline —
    so a delete without a reason is not merely discouraged, it cannot be stored.
    That is DATA-04 and LOG-03 working as designed.

    A consequence worth stating plainly: until the approved reason list (OD-06)
    is settled and `reason_codes` holds values, **deletion is unavailable**. The
    error below says so rather than failing with a constraint violation.
    """
    approved_exist = session.execute(
        select(func.count()).select_from(ReasonCode).where(ReasonCode.is_active.is_(True))
    ).scalar_one()

    if not approved_exist:
        raise InvalidReference(
            "Deletion is unavailable: no approved deletion reasons are configured yet. "
            "The approved reason list (OD-06) must be confirmed before records can be deleted."
        )

    if reason_code_id is None:
        raise InvalidReference("Select an approved reason for this deletion.")

    reason = session.get(ReasonCode, reason_code_id)
    if reason is None or not reason.is_active:
        raise InvalidReference("That deletion reason is not an approved value.")
    if reason.requires_detail and not (detail or "").strip():
        raise InvalidReference(f"The reason '{reason.label}' requires a written explanation.")
    return reason


def _log(
    session: Session,
    *,
    actor: User,
    action: str,
    page: str,
    record: str,
    detail: str,
    reason_code_id: int | None = None,
    reason_detail: str | None = None,
) -> None:
    record_activity(
        session,
        user=actor,
        action=action,
        page_or_function=page,
        record_reference=record,
        detail=detail,
    )
    if reason_code_id is not None:
        # The reason belongs on the record just written.
        session.flush()


# ===========================================================================
# College
# ===========================================================================


def list_colleges(
    session: Session, *, search: str | None = None, active_only: bool = False
) -> Sequence[College]:
    stmt = select(College).order_by(College.college_short_name)
    if active_only:
        stmt = stmt.where(College.is_active.is_(True))
    stmt = _apply_search(stmt, search, College.college_short_name, College.college_full_name)
    return session.execute(stmt).scalars().all()


def get_college(session: Session, college_id: int) -> College:
    return _get_or_404(session, College, college_id, "College")


def create_college(session: Session, actor: User, payload: schemas.CollegeCreate) -> College:
    _reject_duplicate_college_name(session, payload.college_short_name)

    college = College(
        college_short_name=payload.college_short_name,
        college_full_name=payload.college_full_name,
        email_domain=payload.email_domain,
        is_active=payload.is_active,
    )
    session.add(college)
    _flush_translating_conflicts(session, "College short name", payload.college_short_name)

    _log(
        session,
        actor=actor,
        action="CREATE",
        page=PAGE_REFERENCE,
        record=college.college_short_name,
        detail=f"College created: {college.college_full_name} ({college.college_short_name}).",
    )
    return college


def update_college(
    session: Session, actor: User, college_id: int, payload: schemas.CollegeUpdate
) -> College:
    college = get_college(session, college_id)
    changes = _assign(
        college,
        payload,
        ("college_short_name", "college_full_name", "email_domain", "is_active"),
    )
    if not changes:
        return college

    if "college_short_name" in changes:
        _reject_duplicate_college_name(session, college.college_short_name, exclude_id=college.id)

    _flush_translating_conflicts(session, "College short name", college.college_short_name)
    _log(
        session,
        actor=actor,
        action="UPDATE",
        page=PAGE_REFERENCE,
        record=college.college_short_name,
        detail=f"College updated: {_describe(changes)}.",
    )
    return college


def _reject_duplicate_college_name(
    session: Session, short_name: str, *, exclude_id: int | None = None
) -> None:
    stmt = select(College.id).where(func.lower(College.college_short_name) == short_name.lower())
    if exclude_id is not None:
        stmt = stmt.where(College.id != exclude_id)
    if session.execute(stmt).first():
        raise Duplicate(f"A college with the short name '{short_name}' already exists.")


# ===========================================================================
# Campus
# ===========================================================================


def _ids(values: Iterable[int] | None) -> list[int]:
    """Normalise a repeated query parameter. Empty means "no restriction"."""
    return sorted({int(v) for v in values}) if values else []


def list_campuses(
    session: Session,
    *,
    search: str | None = None,
    active_only: bool = False,
    college_id: int | None = None,
    college_ids: Iterable[int] | None = None,
) -> Sequence[Campus]:
    """Campuses, optionally restricted to those approved for the given colleges.

    The college filter is applied **here**, in SQL, not left to the browser: a
    college/campus pair is only valid if `college_campuses` says so, and trusting
    the client to filter would mean trusting it to enforce COL-01.

    Several colleges give the **union** of their campuses, deduplicated. Two
    colleges sharing one site produce one option, not two — the approved model
    is many-to-many (DBQ-04), so a campus is a single row however many colleges
    operate there.
    """
    stmt = select(Campus).order_by(Campus.campus_name)

    wanted = _ids(college_ids) or ([college_id] if college_id is not None else [])
    if wanted:
        stmt = (
            stmt.join(CollegeCampus, CollegeCampus.campus_id == Campus.id)
            .where(
                CollegeCampus.college_id.in_(wanted),
                CollegeCampus.is_active.is_(True),
            )
            .distinct()
        )
    if active_only:
        stmt = stmt.where(Campus.is_active.is_(True))

    stmt = _apply_search(
        stmt, search, Campus.campus_code, Campus.campus_name, Campus.campus_location
    )
    return session.execute(stmt).scalars().all()


def get_campus(session: Session, campus_id: int) -> Campus:
    return _get_or_404(session, Campus, campus_id, "Campus")


def create_campus(session: Session, actor: User, payload: schemas.CampusCreate) -> Campus:
    _reject_duplicate_campus_code(session, payload.campus_code)

    campus = Campus(
        campus_code=payload.campus_code,
        campus_name=payload.campus_name,
        campus_location=payload.campus_location,
        state=payload.state,
        is_active=payload.is_active,
    )
    session.add(campus)
    _flush_translating_conflicts(session, "Campus code", payload.campus_code)

    _log(
        session,
        actor=actor,
        action="CREATE",
        page=PAGE_REFERENCE,
        record=campus.campus_code,
        detail=f"Campus created: {campus.campus_name} ({campus.campus_code}), {campus.state}.",
    )
    return campus


def update_campus(
    session: Session, actor: User, campus_id: int, payload: schemas.CampusUpdate
) -> Campus:
    campus = get_campus(session, campus_id)
    changes = _assign(
        campus, payload, ("campus_code", "campus_name", "campus_location", "state", "is_active")
    )
    if not changes:
        return campus

    if "campus_code" in changes:
        _reject_duplicate_campus_code(session, campus.campus_code, exclude_id=campus.id)

    _flush_translating_conflicts(session, "Campus code", campus.campus_code)
    _log(
        session,
        actor=actor,
        action="UPDATE",
        page=PAGE_REFERENCE,
        record=campus.campus_code,
        detail=f"Campus updated: {_describe(changes)}.",
    )
    return campus


def _reject_duplicate_campus_code(
    session: Session, code: str, *, exclude_id: int | None = None
) -> None:
    stmt = select(Campus.id).where(func.lower(Campus.campus_code) == code.lower())
    if exclude_id is not None:
        stmt = stmt.where(Campus.id != exclude_id)
    if session.execute(stmt).first():
        raise Duplicate(f"A campus with the code '{code}' already exists.")


# ---------------------------------------------------------------------------
# College / campus approval (COL-01)
# ---------------------------------------------------------------------------


def list_college_campuses(session: Session, *, college_id: int | None = None):
    stmt = select(CollegeCampus)
    if college_id is not None:
        stmt = stmt.where(CollegeCampus.college_id == college_id)
    return session.execute(stmt).scalars().all()


def link_college_campus(
    session: Session, actor: User, payload: schemas.CollegeCampusLink
) -> CollegeCampus:
    college = get_college(session, payload.college_id)
    campus = get_campus(session, payload.campus_id)

    existing = session.get(CollegeCampus, (payload.college_id, payload.campus_id))
    if existing is not None:
        if existing.is_active == payload.is_active:
            raise Duplicate(
                f"{campus.campus_name} is already an approved campus for {college.college_short_name}."
            )
        existing.is_active = payload.is_active
        session.flush()
        _log(
            session,
            actor=actor,
            action="UPDATE",
            page=PAGE_REFERENCE,
            record=f"{college.college_short_name}/{campus.campus_code}",
            detail=(
                f"College/campus approval {'reactivated' if payload.is_active else 'retired'}: "
                f"{college.college_short_name} / {campus.campus_name}."
            ),
        )
        return existing

    link = CollegeCampus(
        college_id=payload.college_id, campus_id=payload.campus_id, is_active=payload.is_active
    )
    session.add(link)
    _flush_translating_conflicts(session, "College/campus combination", str(payload.campus_id))

    _log(
        session,
        actor=actor,
        action="CREATE",
        page=PAGE_REFERENCE,
        record=f"{college.college_short_name}/{campus.campus_code}",
        detail=f"Campus approved for college: {college.college_short_name} / {campus.campus_name}.",
    )
    return link


def require_approved_combination(session: Session, college_id: int, campus_id: int) -> None:
    """COL-01: the campus must be approved for this college.

    Checked server-side even though the interface only offers valid pairs. Two
    IDs that each exist separately are not evidence that the *combination* was
    approved, and a hand-made request can pair anything with anything.
    """
    link = session.get(CollegeCampus, (college_id, campus_id))
    if link is None or not link.is_active:
        college = session.get(College, college_id)
        campus = session.get(Campus, campus_id)
        raise InvalidReference(
            f"{campus.campus_name if campus else 'That campus'} is not an approved campus for "
            f"{college.college_short_name if college else 'that college'}."
        )


# ===========================================================================
# Qualification
# ===========================================================================


def list_qualifications(
    session: Session, *, search: str | None = None, active_only: bool = False
) -> Sequence[Qualification]:
    stmt = select(Qualification).order_by(Qualification.qualification_code)
    if active_only:
        stmt = stmt.where(Qualification.is_active.is_(True))
    stmt = _apply_search(
        stmt, search, Qualification.qualification_code, Qualification.qualification_title
    )
    return session.execute(stmt).scalars().all()


def list_offered_qualifications(
    session: Session,
    *,
    college_ids: Iterable[int] | None = None,
    campus_ids: Iterable[int] | None = None,
    active_only: bool = False,
) -> Sequence[Qualification]:
    """Qualifications actually offered within a college/campus scope.

    This is what the Page 4 Qualification filter must be built from. Listing
    every qualification in the table instead offers the user AHC and AUR
    qualifications when they have selected HJ at Hobart, which delivers five
    business and ICT qualifications and none of those.

    Two properties matter and are easy to get wrong:

    * **Real pairs only, never a cross-product.** With AIBT+AVTA selected and
      Blacktown+Hobart selected, the answer is the qualifications on offerings
      that genuinely exist among those four combinations — not every
      qualification of either college crossed with either campus.
    * **Offering, not unit membership.** The join is to `course_offerings`, never
      to `qualification_units`. A qualification whose unit data has not been
      supplied yet — HJ's BSB50120, AVTA's CPPBDN6106 and MEM23109 — is still
      offered, and hiding it would misreport the catalogue as smaller than it is.
    """
    stmt = (
        select(Qualification)
        .join(CourseOffering, CourseOffering.qualification_id == Qualification.id)
        .where(CourseOffering.is_deleted.is_(False))
        .distinct()
        .order_by(Qualification.qualification_code, Qualification.qualification_title)
    )
    colleges = _ids(college_ids)
    campuses = _ids(campus_ids)
    if colleges:
        stmt = stmt.where(CourseOffering.college_id.in_(colleges))
    if campuses:
        stmt = stmt.where(CourseOffering.campus_id.in_(campuses))
    if active_only:
        stmt = stmt.where(Qualification.is_active.is_(True))
    return session.execute(stmt).scalars().all()


def get_qualification(session: Session, qualification_id: int) -> Qualification:
    return _get_or_404(session, Qualification, qualification_id, "Qualification")


def create_qualification(
    session: Session, actor: User, payload: schemas.QualificationCreate
) -> Qualification:
    _reject_duplicate_qualification_code(session, payload.qualification_code)

    qualification = Qualification(**payload.model_dump())
    session.add(qualification)
    _flush_translating_conflicts(
        session, "Qualification Code", code_label(payload.qualification_code)
    )

    _log(
        session,
        actor=actor,
        action="CREATE",
        page=PAGE_REFERENCE,
        record=code_label(qualification.qualification_code),
        detail=(
            f"Qualification created: {code_label(qualification.qualification_code)} "
            f"{qualification.qualification_title}."
        ),
    )
    return qualification


def update_qualification(
    session: Session, actor: User, qualification_id: int, payload: schemas.QualificationUpdate
) -> Qualification:
    qualification = get_qualification(session, qualification_id)
    changes = _assign(qualification, payload, tuple(schemas.QualificationUpdate.model_fields))
    if not changes:
        return qualification

    if "qualification_code" in changes:
        _reject_duplicate_qualification_code(
            session, qualification.qualification_code, exclude_id=qualification.id
        )

    _flush_translating_conflicts(
        session, "Qualification Code", code_label(qualification.qualification_code)
    )
    _log(
        session,
        actor=actor,
        action="UPDATE",
        page=PAGE_REFERENCE,
        record=code_label(qualification.qualification_code),
        detail=f"Qualification updated: {_describe(changes)}.",
    )
    return qualification


def _reject_duplicate_qualification_code(
    session: Session, code: str | None, *, exclude_id: int | None = None
) -> None:
    """Unique only where a code is supplied.

    A code-less qualification (ELICOS) does not conflict with another code-less
    one — the uniqueness in the database is a partial index over non-null values,
    and this pre-check mirrors it exactly.
    """
    if code is None:
        return
    stmt = select(Qualification.id).where(
        func.lower(Qualification.qualification_code) == code.lower()
    )
    if exclude_id is not None:
        stmt = stmt.where(Qualification.id != exclude_id)
    if session.execute(stmt).first():
        raise Duplicate(f"Qualification Code '{code}' already exists.")


# ===========================================================================
# Unit
# ===========================================================================


def list_units(
    session: Session,
    *,
    search: str | None = None,
    active_only: bool = False,
    qualification_id: int | None = None,
) -> Sequence[Unit]:
    stmt = select(Unit).order_by(Unit.unit_code)

    if qualification_id is not None:
        stmt = (
            stmt.join(QualificationUnit, QualificationUnit.unit_id == Unit.id)
            .where(
                QualificationUnit.qualification_id == qualification_id,
                QualificationUnit.is_deleted.is_(False),
            )
            .order_by(None)
            .order_by(QualificationUnit.delivery_order)
        )
    if active_only:
        stmt = stmt.where(Unit.is_active.is_(True))

    stmt = _apply_search(stmt, search, Unit.unit_code, Unit.unit_title)
    return session.execute(stmt).scalars().all()


def get_unit(session: Session, unit_id: int) -> Unit:
    return _get_or_404(session, Unit, unit_id, "Unit")


def create_unit(session: Session, actor: User, payload: schemas.UnitCreate) -> Unit:
    _reject_duplicate_unit_code(session, payload.unit_code)

    unit = Unit(**payload.model_dump())
    session.add(unit)
    _flush_translating_conflicts(session, "Unit Code", payload.unit_code)

    _log(
        session,
        actor=actor,
        action="CREATE",
        page=PAGE_REFERENCE,
        record=unit.unit_code,
        detail=f"Unit created: {unit.unit_code} {unit.unit_title}.",
    )
    return unit


def update_unit(session: Session, actor: User, unit_id: int, payload: schemas.UnitUpdate) -> Unit:
    unit = get_unit(session, unit_id)
    changes = _assign(unit, payload, tuple(schemas.UnitUpdate.model_fields))
    if not changes:
        return unit

    if "unit_code" in changes:
        _reject_duplicate_unit_code(session, unit.unit_code, exclude_id=unit.id)

    _flush_translating_conflicts(session, "Unit Code", unit.unit_code)
    _log(
        session,
        actor=actor,
        action="UPDATE",
        page=PAGE_REFERENCE,
        record=unit.unit_code,
        detail=f"Unit updated: {_describe(changes)}.",
    )
    return unit


def _reject_duplicate_unit_code(
    session: Session, code: str, *, exclude_id: int | None = None
) -> None:
    stmt = select(Unit.id).where(func.lower(Unit.unit_code) == code.lower())
    if exclude_id is not None:
        stmt = stmt.where(Unit.id != exclude_id)
    if session.execute(stmt).first():
        raise Duplicate(f"Unit Code '{code}' already exists.")


# ===========================================================================
# Qualification / Unit delivery sequence (Page 4B)
# ===========================================================================


def list_qualification_units(
    session: Session,
    *,
    qualification_id: int | None = None,
    college_ids: Iterable[int] | None = None,
    campus_ids: Iterable[int] | None = None,
    qualification_ids: Iterable[int] | None = None,
    search: str | None = None,
    include_deleted: bool = False,
) -> Sequence[QualificationUnit]:
    """The approved delivery sequence, ordered by `delivery_order` (C-1, TT-08).

    `selectinload` on both relationships: the list renders qualification and unit
    text for every row, so lazy loading would issue two queries per row.
    """
    stmt = (
        select(QualificationUnit)
        .options(
            selectinload(QualificationUnit.qualification),
            selectinload(QualificationUnit.unit),
        )
        .join(Qualification, Qualification.id == QualificationUnit.qualification_id)
        .join(Unit, Unit.id == QualificationUnit.unit_id)
        .order_by(Qualification.qualification_code, QualificationUnit.delivery_order)
    )
    if not include_deleted:
        stmt = stmt.where(QualificationUnit.is_deleted.is_(False))
    if qualification_id is not None:
        stmt = stmt.where(QualificationUnit.qualification_id == qualification_id)
    if _ids(qualification_ids):
        stmt = stmt.where(QualificationUnit.qualification_id.in_(_ids(qualification_ids)))

    # College and campus are not columns on a delivery sequence — a
    # qualification's unit order is the same wherever it is taught (DBQ-07). They
    # scope the *sequence* by restricting it to qualifications actually offered
    # in that college/campus, which is why this reaches through
    # `course_offerings` rather than pretending the sequence carries a campus.
    colleges, campuses = _ids(college_ids), _ids(campus_ids)
    if colleges or campuses:
        offered = select(CourseOffering.qualification_id).where(
            CourseOffering.is_deleted.is_(False)
        )
        if colleges:
            offered = offered.where(CourseOffering.college_id.in_(colleges))
        if campuses:
            offered = offered.where(CourseOffering.campus_id.in_(campuses))
        stmt = stmt.where(QualificationUnit.qualification_id.in_(offered))

    stmt = _apply_search(
        stmt,
        search,
        Qualification.qualification_code,
        Qualification.qualification_title,
        Unit.unit_code,
        Unit.unit_title,
    )
    return session.execute(stmt).scalars().all()


def get_qualification_unit(session: Session, link_id: int) -> QualificationUnit:
    return _get_or_404(session, QualificationUnit, link_id, "Qualification unit")


def create_qualification_unit(
    session: Session, actor: User, payload: schemas.QualificationUnitCreate
) -> QualificationUnit:
    qualification = get_qualification(session, payload.qualification_id)
    unit = get_unit(session, payload.unit_id)

    _reject_duplicate_sequence(session, payload.qualification_id, payload.delivery_order)
    _reject_duplicate_unit_in_qualification(session, payload.qualification_id, payload.unit_id)

    link = QualificationUnit(
        qualification_id=payload.qualification_id,
        unit_id=payload.unit_id,
        delivery_order=payload.delivery_order,
    )
    session.add(link)
    _flush_translating_conflicts(session, "Delivery order", str(payload.delivery_order))

    _log(
        session,
        actor=actor,
        action="CREATE",
        page=PAGE_QUALIFICATION_UNITS,
        record=f"{code_label(qualification.qualification_code)}/{unit.unit_code}",
        detail=(
            f"Unit {unit.unit_code} added to {code_label(qualification.qualification_code)} "
            f"at delivery order {payload.delivery_order}."
        ),
    )
    return link


def update_qualification_unit(
    session: Session, actor: User, link_id: int, payload: schemas.QualificationUnitUpdate
) -> QualificationUnit:
    link = get_qualification_unit(session, link_id)
    changes = _assign(link, payload, ("unit_id", "delivery_order"))
    if not changes:
        return link

    if "delivery_order" in changes:
        _reject_duplicate_sequence(
            session, link.qualification_id, link.delivery_order, exclude_id=link.id
        )
    if "unit_id" in changes:
        get_unit(session, link.unit_id)
        _reject_duplicate_unit_in_qualification(
            session, link.qualification_id, link.unit_id, exclude_id=link.id
        )

    _flush_translating_conflicts(session, "Delivery order", str(link.delivery_order))
    _log(
        session,
        actor=actor,
        action="UPDATE",
        page=PAGE_QUALIFICATION_UNITS,
        record=str(link.id),
        detail=f"Qualification unit updated: {_describe(changes)}.",
    )
    return link


def delete_qualification_unit(
    session: Session, actor: User, link_id: int, request: schemas.DeleteRequest
) -> QualificationUnit:
    """Soft delete, per the approved design for this table (DATA-04)."""
    link = get_qualification_unit(session, link_id)
    if link.is_deleted:
        raise ReferenceDataError("That qualification unit is already deleted.")

    reason = _require_reason(session, request.reason_code_id, request.reason_detail)

    link.is_deleted = True
    link.deleted_at = dt.datetime.now(dt.timezone.utc)
    link.deleted_by_user_id = actor.id
    link.delete_reason_id = reason.id
    link.delete_reason_detail = (request.reason_detail or "").strip() or None
    link.recovery_deadline = dt.date.today() + dt.timedelta(days=RECOVERY_PERIOD_DAYS)
    session.flush()

    _log(
        session,
        actor=actor,
        action="DELETE",
        page=PAGE_QUALIFICATION_UNITS,
        record=str(link.id),
        detail=(
            f"Qualification unit deleted. Recoverable until "
            f"{link.recovery_deadline.isoformat()}."
        ),
    )
    return link


def restore_qualification_unit(
    session: Session, actor: User, link_id: int, request: schemas.RestoreRequest
) -> QualificationUnit:
    link = get_qualification_unit(session, link_id)
    if not link.is_deleted:
        raise ReferenceDataError("That qualification unit is not deleted.")

    # No collision check is needed: the approved uniqueness is not partial, so
    # the deleted row kept its delivery order and its unit slot. Nothing else
    # can have taken them.

    link.is_deleted = False
    link.deleted_at = None
    link.deleted_by_user_id = None
    link.delete_reason_id = None
    link.delete_reason_detail = None
    link.recovery_deadline = None
    session.flush()

    _log(
        session,
        actor=actor,
        action="RESTORE",
        page=PAGE_QUALIFICATION_UNITS,
        record=str(link.id),
        detail="Qualification unit restored from the recycle area.",
    )
    return link


def _reject_duplicate_sequence(
    session: Session, qualification_id: int, delivery_order: int, *, exclude_id: int | None = None
) -> None:
    """Mirror `uq_qualification_units_qualification_id_delivery_order`.

    Deleted rows are **included**, because the approved constraint is not
    partial: a soft-deleted row keeps its slot so that restoring it cannot
    collide. A pre-check that excluded them would tell the user the order is
    free and then fail at commit — worse than refusing up front.
    """
    stmt = select(QualificationUnit.id).where(
        QualificationUnit.qualification_id == qualification_id,
        QualificationUnit.delivery_order == delivery_order,
    )
    if exclude_id is not None:
        stmt = stmt.where(QualificationUnit.id != exclude_id)
    row = session.execute(
        select(QualificationUnit).where(
            QualificationUnit.qualification_id == qualification_id,
            QualificationUnit.delivery_order == delivery_order,
            *([QualificationUnit.id != exclude_id] if exclude_id is not None else []),
        )
    ).scalars().first()
    if row is not None:
        if row.is_deleted:
            raise Duplicate(
                f"Delivery order {delivery_order} is held by a deleted unit for this "
                "qualification. Restore or permanently remove that record first."
            )
        raise Duplicate(f"Delivery order {delivery_order} is already used for this qualification.")


def _reject_duplicate_unit_in_qualification(
    session: Session, qualification_id: int, unit_id: int, *, exclude_id: int | None = None
) -> None:
    # Deleted rows included: `uq_qualification_units_qualification_id_unit_id`
    # is not partial either.
    stmt = select(QualificationUnit.id).where(
        QualificationUnit.qualification_id == qualification_id,
        QualificationUnit.unit_id == unit_id,
    )
    if exclude_id is not None:
        stmt = stmt.where(QualificationUnit.id != exclude_id)
    if session.execute(stmt).first():
        unit = session.get(Unit, unit_id)
        raise Duplicate(
            f"{unit.unit_code if unit else 'That unit'} is already in this qualification's "
            "sequence, or is held there by a deleted record."
        )


# ===========================================================================
# Course offering (Page 4A)
# ===========================================================================

#: DATA-04: the proposed recovery period. 14 days is the SRS proposal; OD-06 has
#: not fixed it, so it lives here rather than being scattered.
RECOVERY_PERIOD_DAYS = 14


def _offering_query() -> Select:
    """Loads exactly what the list and detail views render, and nothing more."""
    return select(CourseOffering).options(
        selectinload(CourseOffering.duration_options),
        selectinload(CourseOffering.course_status),
    )


def list_course_offerings(
    session: Session,
    *,
    search: str | None = None,
    college_id: int | None = None,
    campus_id: int | None = None,
    qualification_id: int | None = None,
    college_ids: Iterable[int] | None = None,
    campus_ids: Iterable[int] | None = None,
    qualification_ids: Iterable[int] | None = None,
    course_status_code: str | None = None,
    include_deleted: bool = False,
) -> Sequence[CourseOffering]:
    stmt = (
        _offering_query()
        .join(College, College.id == CourseOffering.college_id)
        .join(Campus, Campus.id == CourseOffering.campus_id)
        .join(Qualification, Qualification.id == CourseOffering.qualification_id)
        .join(CourseStatus, CourseStatus.id == CourseOffering.course_status_id)
        .order_by(CourseOffering.course_code)
    )
    stmt = stmt.where(CourseOffering.is_deleted.is_(include_deleted))
    if college_id is not None:
        stmt = stmt.where(CourseOffering.college_id == college_id)
    if campus_id is not None:
        stmt = stmt.where(CourseOffering.campus_id == campus_id)
    if qualification_id is not None:
        stmt = stmt.where(CourseOffering.qualification_id == qualification_id)
    # Multi-select scope. An empty list means "no restriction at that level",
    # which is what Select All has to mean — not "match nothing".
    if _ids(college_ids):
        stmt = stmt.where(CourseOffering.college_id.in_(_ids(college_ids)))
    if _ids(campus_ids):
        stmt = stmt.where(CourseOffering.campus_id.in_(_ids(campus_ids)))
    if _ids(qualification_ids):
        stmt = stmt.where(CourseOffering.qualification_id.in_(_ids(qualification_ids)))
    if course_status_code:
        # Matched against the stored status, so the filter and the displayed
        # badge can never disagree — both come from the same column.
        stmt = stmt.where(func.upper(CourseStatus.code) == course_status_code.strip().upper())

    stmt = _apply_search(
        stmt,
        search,
        CourseOffering.course_code,
        Qualification.qualification_code,
        Qualification.qualification_title,
        College.college_short_name,
        Campus.campus_name,
    )
    return session.execute(stmt).scalars().unique().all()


def get_course_offering(session: Session, offering_id: int) -> CourseOffering:
    row = session.execute(
        _offering_query().where(CourseOffering.id == offering_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFound("Course record not found.")
    return row


def create_course_offering(
    session: Session, actor: User, payload: schemas.CourseOfferingCreate
) -> CourseOffering:
    """Create an offering and its approved durations in one transaction."""
    college = get_college(session, payload.college_id)
    campus = get_campus(session, payload.campus_id)
    qualification = get_qualification(session, payload.qualification_id)
    status = _get_or_404(session, CourseStatus, payload.course_status_id, "Course status")

    require_approved_combination(session, payload.college_id, payload.campus_id)
    _reject_unselectable_status(status)
    # Course Code is deliberately NOT checked for uniqueness: one CRICOS code is
    # offered at many campuses. Offering identity is COL-04 below.
    _reject_duplicate_offering(
        session, payload.college_id, payload.campus_id, payload.qualification_id
    )

    offering = CourseOffering(
        college_id=payload.college_id,
        campus_id=payload.campus_id,
        qualification_id=payload.qualification_id,
        course_code=payload.course_code,
        course_status_id=payload.course_status_id,
        total_course_cost=payload.total_course_cost,
    )
    session.add(offering)
    _flush_translating_conflicts(session, "This course record", "")

    for weeks in payload.duration_options:
        session.add(
            OfferingDurationOption(course_offering_id=offering.id, duration_weeks=weeks)
        )
    _flush_translating_conflicts(session, "Duration", "")

    _log(
        session,
        actor=actor,
        action="CREATE",
        page=PAGE_COURSE_DATA,
        record=offering.course_code,
        detail=(
            f"Course record created: {code_label(qualification.qualification_code)} at "
            f"{college.college_short_name} / {campus.campus_name}."
        ),
    )
    return offering


def update_course_offering(
    session: Session, actor: User, offering_id: int, payload: schemas.CourseOfferingUpdate
) -> CourseOffering:
    offering = get_course_offering(session, offering_id)
    changes = _assign(
        offering, payload, ("course_code", "course_status_id", "total_course_cost")
    )

    if "course_status_id" in changes:
        status = _get_or_404(session, CourseStatus, offering.course_status_id, "Course status")
        # An existing record may be *moved into* a non-selectable status such as
        # Superseded; COL-05 only forbids choosing one for a new record.
        if not status.is_active:
            raise InvalidReference(f"'{status.label}' is not an active course status.")

    if payload.duration_options is not None:
        _replace_duration_options(session, offering, payload.duration_options)
        changes["duration_options"] = payload.duration_options

    if not changes:
        return offering

    _flush_translating_conflicts(session, "This course record", "")
    _log(
        session,
        actor=actor,
        action="UPDATE",
        page=PAGE_COURSE_DATA,
        record=offering.course_code,
        detail=f"Course record updated: {_describe(changes)}.",
    )
    return offering


def _replace_duration_options(
    session: Session, offering: CourseOffering, weeks: list[int]
) -> None:
    """Replace the approved durations wholesale, inside the caller's transaction."""
    wanted = sorted({w for w in weeks if w > 0})
    existing = {option.duration_weeks: option for option in offering.duration_options}

    for value, option in existing.items():
        if value not in wanted:
            session.delete(option)
    for value in wanted:
        if value not in existing:
            session.add(
                OfferingDurationOption(course_offering_id=offering.id, duration_weeks=value)
            )
    session.flush()


def delete_course_offering(
    session: Session, actor: User, offering_id: int, request: schemas.DeleteRequest
) -> CourseOffering:
    offering = get_course_offering(session, offering_id)
    if offering.is_deleted:
        raise ReferenceDataError("That course record is already deleted.")

    reason = _require_reason(session, request.reason_code_id, request.reason_detail)

    offering.is_deleted = True
    offering.deleted_at = dt.datetime.now(dt.timezone.utc)
    offering.deleted_by_user_id = actor.id
    offering.delete_reason_id = reason.id
    offering.delete_reason_detail = (request.reason_detail or "").strip() or None
    offering.recovery_deadline = dt.date.today() + dt.timedelta(days=RECOVERY_PERIOD_DAYS)
    session.flush()

    _log(
        session,
        actor=actor,
        action="DELETE",
        page=PAGE_COURSE_DATA,
        record=offering.course_code,
        detail=(
            f"Course record deleted. Recoverable until {offering.recovery_deadline.isoformat()}."
        ),
    )
    return offering


def restore_course_offering(
    session: Session, actor: User, offering_id: int, request: schemas.RestoreRequest
) -> CourseOffering:
    offering = get_course_offering(session, offering_id)
    if not offering.is_deleted:
        raise ReferenceDataError("That course record is not deleted.")

    _reject_duplicate_offering(
        session,
        offering.college_id,
        offering.campus_id,
        offering.qualification_id,
        exclude_id=offering.id,
    )

    offering.is_deleted = False
    offering.deleted_at = None
    offering.deleted_by_user_id = None
    offering.delete_reason_id = None
    offering.delete_reason_detail = None
    offering.recovery_deadline = None
    session.flush()

    _log(
        session,
        actor=actor,
        action="RESTORE",
        page=PAGE_COURSE_DATA,
        record=offering.course_code,
        detail="Course record restored from the recycle area.",
    )
    return offering


def _reject_unselectable_status(status: CourseStatus) -> None:
    if not status.is_active:
        raise InvalidReference(f"'{status.label}' is not an active course status.")
    if not status.selectable_for_new_records:
        raise InvalidReference(
            f"'{status.label}' cannot be chosen for a new course record (COL-05)."
        )


@dataclass
class SuppliedStatusCorrection:
    """What a status correction found and changed."""

    supplied_offerings: int = 0
    already_active: int = 0
    incorrectly_inactive: int = 0
    corrected: list[str] = dc_field(default_factory=list)
    untraceable_left_alone: list[str] = dc_field(default_factory=list)
    retired_status_codes: list[str] = dc_field(default_factory=list)


def correct_supplied_course_statuses(
    session: Session,
    supplied_course_codes: Iterable[str],
    *,
    actor: User | None = None,
) -> SuppliedStatusCorrection:
    """Move project-supplied courses onto the approved ACTIVE status.

    `supplied_course_codes` comes from the approved source workbook. Only those
    offerings are touched: an offering whose provenance cannot be traced to the
    supplied dataset is reported and left exactly as it is, because "everything
    supplied is active" says nothing about a record entered by hand.

    The caller owns the transaction, so the whole correction commits or none of
    it does.
    """
    supplied = {code.strip().upper() for code in supplied_course_codes if code and code.strip()}
    active = status_for_supplied_course(session)
    report = SuppliedStatusCorrection()

    offerings = session.execute(select(CourseOffering)).scalars().all()
    for offering in offerings:
        if offering.course_code.strip().upper() not in supplied:
            report.untraceable_left_alone.append(offering.course_code)
            continue

        report.supplied_offerings += 1
        if offering.course_status_id == active.id:
            report.already_active += 1
            continue

        report.incorrectly_inactive += 1
        offering.course_status_id = active.id
        report.corrected.append(offering.course_code)
        if actor is not None:
            _log(
                session,
                actor=actor,
                action="UPDATE",
                page=PAGE_COURSE_DATA,
                record=offering.course_code,
                detail=(
                    f"Course status corrected to {SUPPLIED_COURSE_STATUS_LABEL}: every course "
                    "supplied in an approved source is active in TDMS."
                ),
            )

    session.flush()

    # A status value that only ever held a source registration term, and that
    # nothing references any more, is removed rather than left in the approved
    # vocabulary where someone could select it again.
    for status in session.execute(select(CourseStatus)).scalars().all():
        if status.id == active.id:
            continue
        if status.code.strip().upper() not in KNOWN_SOURCE_REGISTRATION_TERMS:
            continue
        still_used = session.execute(
            select(CourseOffering.id).where(CourseOffering.course_status_id == status.id).limit(1)
        ).first()
        if still_used:
            continue
        report.retired_status_codes.append(status.code)
        session.delete(status)

    session.flush()
    return report


def _reject_duplicate_offering(
    session: Session,
    college_id: int,
    campus_id: int,
    qualification_id: int,
    *,
    exclude_id: int | None = None,
) -> None:
    """COL-04: one offering per college + campus + qualification."""
    stmt = select(CourseOffering.id).where(
        CourseOffering.college_id == college_id,
        CourseOffering.campus_id == campus_id,
        CourseOffering.qualification_id == qualification_id,
    )
    if exclude_id is not None:
        stmt = stmt.where(CourseOffering.id != exclude_id)
    if session.execute(stmt).first():
        raise Duplicate(
            "A course record already exists for this college, campus and qualification."
        )


# ===========================================================================
# Course status
# ===========================================================================


def list_course_statuses(session: Session, *, active_only: bool = False):
    stmt = select(CourseStatus).order_by(CourseStatus.label)
    if active_only:
        stmt = stmt.where(CourseStatus.is_active.is_(True))
    return session.execute(stmt).scalars().all()


# ===========================================================================
# Shared helpers
# ===========================================================================


def _assign(row, payload, fields: Sequence[str]) -> dict[str, object]:
    """Apply the set fields of a PATCH payload, returning what actually changed.

    `exclude_unset` matters: a field the client omitted must keep its stored
    value, while a field explicitly sent as `null` must clear it. Treating those
    the same is how a PATCH quietly wipes data.
    """
    supplied = payload.model_dump(exclude_unset=True)
    changes: dict[str, object] = {}
    for field in fields:
        if field not in supplied:
            continue
        new = supplied[field]
        if getattr(row, field) != new:
            setattr(row, field, new)
            changes[field] = new
    return changes


def _describe(changes: dict[str, object]) -> str:
    return ", ".join(f"{k} -> {v!r}" for k, v in changes.items())


def _flush_translating_conflicts(session: Session, label: str, value: str) -> None:
    """Flush, turning a database uniqueness failure into a domain message.

    The pre-checks above catch the ordinary cases. This catches the race: two
    admins submitting the same new code at the same moment both pass the check,
    and the database decides. The loser gets a sentence, not a `UniqueViolation`.
    """
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        text = str(exc.orig).lower()
        if "unique" in text or "duplicate key" in text:
            raise Duplicate(
                f"{label}{f' {value!r}' if value else ''} is already used. "
                "Another user may have just saved the same value."
            ) from exc
        if "foreign key" in text:
            raise InvalidReference(
                "That record refers to reference data that does not exist or is not approved."
            ) from exc
        if "check constraint" in text:
            raise InvalidReference("That value is not allowed by the approved business rules.") from exc
        raise
