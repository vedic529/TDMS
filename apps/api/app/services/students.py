"""Student Data — single-entry CRUD and the shared reference helpers.

The bulk importer (`student_import.py`) reuses `derive_college_email`,
`resolve_offering` and `upsert_student_group` so the two entry paths agree on
how a student is placed. Nothing here reads a file from disk — data arrives only
through the API (rule 2.10).
"""

from __future__ import annotations

import datetime as dt
import math

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core import intake_assignment
from app.core.intake_assignment import assign_intake, build_windows
from app.models.college import Campus, College, CollegeCampus
from app.models.course import CourseOffering, OfferingDurationOption
from app.models.qualification import Qualification
from app.models.reason import ReasonCode
from app.models.student import Student, StudentGroup
from app.models.timetable import RollingTimetableWeek
from app.models.user import User
from app.services.activity import record_activity

STUDENT_PAGE = "Page 2A - Single Student Entry"
COE_VALUES = {"COE", "NON_COE"}
STATUS_VALUES = {"ACTIVE", "COMPLETED", "CANCELLED", "NOT_YET_STARTED"}


class StudentServiceError(Exception):
    """A refusal that maps to an HTTP status, mirroring ReferenceDataError."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ---------------------------------------------------------------------------
# Shared helpers (used by single entry and by bulk import)
# ---------------------------------------------------------------------------


def derive_college_email(student_id: str, college: College) -> str:
    """`studentid@domain`, matching the frontend rule. Editable afterwards."""
    return f"{student_id.strip().lower()}@{college.email_domain}"


def inclusive_course_weeks(start: dt.date, end: dt.date) -> int:
    """Actual Course Duration: (end - start + 1) / 7, inclusive (OD-08).

    Rounded the same way the `students.actual_course_duration_weeks` generated
    column rounds — half away from zero — so the duration used to look up a
    rolling loop is the duration shown on the record.
    """
    days = (end - start).days + 1
    return int(math.floor(days / 7 + 0.5))


def resolve_offering(
    session: Session, college_id: int, campus_id: int, qualification_id: int
) -> CourseOffering | None:
    """The approved offering for a (college, campus, qualification) triple."""
    return session.execute(
        select(CourseOffering).where(
            CourseOffering.college_id == college_id,
            CourseOffering.campus_id == campus_id,
            CourseOffering.qualification_id == qualification_id,
            CourseOffering.is_deleted.is_(False),
        )
    ).scalar_one_or_none()


def upsert_student_group(
    session: Session,
    *,
    course_offering_id: int,
    rolling_intake_label: str,
    group_code: str,
    intake_start_date: dt.date,
) -> int:
    """Return the group row for this intake label, creating it once.

    Reused by every student in the same intake and offering, so two students
    matching one label share a single `student_groups` row (check A11).
    """
    existing = session.execute(
        select(StudentGroup).where(
            StudentGroup.course_offering_id == course_offering_id,
            StudentGroup.rolling_intake_label == rolling_intake_label,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id

    group = StudentGroup(
        group_code=group_code,
        course_offering_id=course_offering_id,
        intake=intake_start_date,
        rolling_intake_label=rolling_intake_label,
        is_active=True,
    )
    session.add(group)
    session.flush()
    return group.id


def assign_one_intake(
    session: Session,
    *,
    qualification_code: str,
    duration_weeks: int,
    proposed_start_date: dt.date,
) -> intake_assignment.IntakeAssignment:
    """Match a single student. Loads only this loop's rolling weeks."""
    weeks = list(
        session.execute(
            select(RollingTimetableWeek).where(
                func.upper(RollingTimetableWeek.qualification_code) == qualification_code.upper(),
                RollingTimetableWeek.duration_weeks == duration_weeks,
            )
        ).scalars()
    )
    windows = build_windows(weeks).get((qualification_code.upper(), duration_weeks), [])
    return assign_intake(windows, proposed_start_date)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def _base_read_query() -> Select:
    return (
        select(
            Student,
            College.college_short_name,
            Campus.campus_name,
            Campus.state,
            Qualification.qualification_code,
            Qualification.qualification_title,
            StudentGroup.rolling_intake_label,
            StudentGroup.group_code,
            OfferingDurationOption.duration_weeks,
            User.organisation_email,
            ReasonCode.code,
        )
        .join(CourseOffering, CourseOffering.id == Student.course_offering_id)
        .join(College, College.id == CourseOffering.college_id)
        .join(Campus, Campus.id == CourseOffering.campus_id)
        .join(Qualification, Qualification.id == CourseOffering.qualification_id)
        .outerjoin(StudentGroup, StudentGroup.id == Student.student_group_id)
        .outerjoin(
            OfferingDurationOption, OfferingDurationOption.id == Student.course_duration_option_id
        )
        # DATA-04: the recycle area shows who deleted a record, when, why, and
        # by when it can be recovered.
        .outerjoin(User, User.id == Student.deleted_by_user_id)
        .outerjoin(ReasonCode, ReasonCode.id == Student.delete_reason_id)
    )


def _to_read_dict(row) -> dict:
    student: Student = row[0]
    return {
        "id": student.id,
        "student_id": student.student_id,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "college_email": student.college_email,
        "coe_status": student.coe_status,
        "ct_student": student.ct_student,
        "status": student.status,
        "intake_match_status": student.intake_match_status,
        "proposed_start_date": student.proposed_start_date,
        "proposed_end_date": student.proposed_end_date,
        "actual_course_duration_weeks": student.actual_course_duration_weeks,
        "personal_email": student.personal_email,
        "primary_phone": student.primary_phone,
        "remarks": student.remarks,
        "course_offering_id": student.course_offering_id,
        "student_group_id": student.student_group_id,
        "college": row[1],
        "campus": row[2],
        "state": row[3],
        "qualification_code": row[4],
        "qualification_title": row[5],
        "intake_label": row[6],
        "group_code": row[7],
        "course_duration_option_weeks": row[8],
        "is_deleted": student.is_deleted,
        "deleted_at": student.deleted_at,
        "deleted_by": row[9],
        "delete_reason": row[10],
        "delete_reason_detail": student.delete_reason_detail,
        "recovery_deadline": student.recovery_deadline,
    }


def list_students(
    session: Session,
    *,
    search: str | None = None,
    college_id: int | None = None,
    campus_id: int | None = None,
    qualification_id: int | None = None,
    status: str | None = None,
    coe_status: str | None = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Paginated list (rule 2.9, check E5). Deleted rows are excluded by default."""
    query = _base_read_query()
    if not include_deleted:
        query = query.where(Student.is_deleted.is_(False))
    else:
        query = query.where(Student.is_deleted.is_(True))
    if college_id:
        query = query.where(CourseOffering.college_id == college_id)
    if campus_id:
        query = query.where(CourseOffering.campus_id == campus_id)
    if qualification_id:
        query = query.where(CourseOffering.qualification_id == qualification_id)
    if status:
        query = query.where(Student.status == status.upper())
    if coe_status:
        query = query.where(Student.coe_status == coe_status.upper())
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                Student.student_id.ilike(pattern),
                Student.first_name.ilike(pattern),
                Student.last_name.ilike(pattern),
                Student.college_email.ilike(pattern),
            )
        )

    total = session.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    # Newest first: the most recently added student is the one a user is most
    # likely to be looking for, and `id` is the only strictly increasing value
    # here — `created_at` can tie across a bulk insert.
    rows = session.execute(
        query.order_by(Student.id.desc()).limit(min(limit, 500)).offset(max(offset, 0))
    ).all()
    return [_to_read_dict(row) for row in rows], total


def get_student(session: Session, student_pk: int) -> dict:
    row = session.execute(_base_read_query().where(Student.id == student_pk)).one_or_none()
    if row is None:
        raise StudentServiceError(404, "That student record was not found.")
    return _to_read_dict(row)


# ---------------------------------------------------------------------------
# Single-entry writes
# ---------------------------------------------------------------------------


def _validate_common(payload) -> None:
    if not (payload.student_id or "").strip():
        raise StudentServiceError(422, "Student ID is required.")
    if not (payload.first_name or "").strip():
        raise StudentServiceError(422, "First Name is required.")
    if payload.coe_status.upper() not in COE_VALUES:
        raise StudentServiceError(422, "CoE / Non-CoE must be CoE or Non-CoE.")
    if payload.status.upper() not in STATUS_VALUES:
        raise StudentServiceError(422, "Status is not an approved value.")
    if payload.proposed_end_date <= payload.proposed_start_date:
        raise StudentServiceError(422, "Proposed End Date must be after Proposed Start Date.")


def _place_student(session: Session, student: Student, payload) -> int:
    """Resolve the offering, derive the intake/group, set the placement fields.

    Returns the resolved course_offering_id. Raises on an unresolved offering —
    single entry chooses from approved dropdowns, so this is a genuine 422.
    """
    college = session.get(College, payload.college_id)
    campus = session.get(Campus, payload.campus_id)
    qualification = session.get(Qualification, payload.qualification_id) if payload.qualification_id else None
    if qualification is None and getattr(payload, "qualification_code", None):
        qualification = session.execute(
            select(Qualification).where(
                func.upper(Qualification.qualification_code) == payload.qualification_code.strip().upper()
            )
        ).scalar_one_or_none()
    if college is None or campus is None or qualification is None:
        raise StudentServiceError(422, "College, Campus and Qualification must be approved records.")

    linked = session.execute(
        select(CollegeCampus).where(
            CollegeCampus.college_id == college.id, CollegeCampus.campus_id == campus.id
        )
    ).scalar_one_or_none()
    if linked is None:
        raise StudentServiceError(422, f"{campus.campus_name} is not an approved campus for {college.college_short_name}.")

    offering = resolve_offering(session, college.id, campus.id, qualification.id)
    if offering is None:
        raise StudentServiceError(
            422, "No approved course offering exists for that College, Campus and Qualification."
        )

    student.course_offering_id = offering.id
    student.college_email = (payload.college_email or "").strip() or derive_college_email(
        payload.student_id, college
    )

    if payload.ct_student:
        # Credit Transfer: no Intake, no Group, no Course Duration Option (13 Aug 2026).
        student.intake_match_status = "NOT_APPLICABLE"
        student.student_group_id = None
        student.course_duration_option_id = None
        return offering.id

    # OD-08: the Course Duration Option is staff-selected and must be one the
    # offering actually approves. The FK enforces it too; refusing here gives a
    # message naming the approved values instead of a constraint violation.
    student.course_duration_option_id = None
    chosen_weeks = getattr(payload, "course_duration_option_weeks", None)
    if chosen_weeks:
        option = session.execute(
            select(OfferingDurationOption).where(
                OfferingDurationOption.course_offering_id == offering.id,
                OfferingDurationOption.duration_weeks == chosen_weeks,
            )
        ).scalar_one_or_none()
        if option is None:
            approved = session.execute(
                select(OfferingDurationOption.duration_weeks)
                .where(OfferingDurationOption.course_offering_id == offering.id)
                .order_by(OfferingDurationOption.duration_weeks)
            ).scalars().all()
            raise StudentServiceError(
                422,
                f"{chosen_weeks} weeks is not an approved Course Duration Option for this offering."
                + (f" Approved options: {', '.join(str(week) for week in approved)}." if approved else ""),
            )
        student.course_duration_option_id = option.id

    duration = inclusive_course_weeks(payload.proposed_start_date, payload.proposed_end_date)
    result = assign_one_intake(
        session,
        qualification_code=qualification.qualification_code,
        duration_weeks=duration,
        proposed_start_date=payload.proposed_start_date,
    )
    if result.status == intake_assignment.CONFLICT:
        raise StudentServiceError(
            422,
            "Two intakes' first units run in this student's start week — the rolling timetable is "
            f"inconsistent: {', '.join(result.conflict_labels)}.",
        )
    if result.status == intake_assignment.MATCHED:
        student.intake_match_status = "MATCHED"
        student.student_group_id = upsert_student_group(
            session,
            course_offering_id=offering.id,
            rolling_intake_label=result.intake_label,
            group_code=result.intake_group,
            intake_start_date=result.intake_start_date,
        )
    else:  # TBD — no rolling timetable for this qualification and duration
        student.intake_match_status = "TBD"
        student.student_group_id = None
    return offering.id


def create_student(session: Session, actor: User, payload) -> dict:
    _validate_common(payload)
    student = Student(
        student_id=payload.student_id.strip(),
        first_name=payload.first_name.strip(),
        last_name=(payload.last_name or "").strip() or None,
        coe_status=payload.coe_status.upper(),
        ct_student=bool(payload.ct_student),
        status=payload.status.upper(),
        proposed_start_date=payload.proposed_start_date,
        proposed_end_date=payload.proposed_end_date,
        personal_email=(payload.personal_email or "").strip() or None,
        primary_phone=(payload.primary_phone or "").strip() or None,
        remarks=(payload.remarks or "").strip() or None,
        college_email="",  # set by _place_student
    )
    _place_student(session, student, payload)
    session.add(student)
    session.flush()
    record_activity(
        session,
        user=actor,
        action="CREATE",
        page_or_function=STUDENT_PAGE,
        detail=f"Created student {student.student_id} ({student.status}).",
        record_reference=student.student_id,
        result="COMPLETED",
    )
    return get_student(session, student.id)


def update_student(session: Session, actor: User, student_pk: int, payload) -> dict:
    student = session.get(Student, student_pk)
    if student is None or student.is_deleted:
        raise StudentServiceError(404, "That student record was not found.")
    _validate_common(payload)
    student.student_id = payload.student_id.strip()
    student.first_name = payload.first_name.strip()
    student.last_name = (payload.last_name or "").strip() or None
    student.coe_status = payload.coe_status.upper()
    student.ct_student = bool(payload.ct_student)
    student.status = payload.status.upper()
    student.proposed_start_date = payload.proposed_start_date
    student.proposed_end_date = payload.proposed_end_date
    student.personal_email = (payload.personal_email or "").strip() or None
    student.primary_phone = (payload.primary_phone or "").strip() or None
    student.remarks = (payload.remarks or "").strip() or None
    _place_student(session, student, payload)
    session.flush()
    record_activity(
        session,
        user=actor,
        action="UPDATE",
        page_or_function=STUDENT_PAGE,
        detail=f"Updated student {student.student_id}.",
        record_reference=student.student_id,
        result="COMPLETED",
    )
    return get_student(session, student.id)


RECYCLE_PERIOD_DAYS = 14


def delete_student(
    session: Session, actor: User, student_pk: int, *, reason_code_id: int, reason_detail: str | None
) -> None:
    student = session.get(Student, student_pk)
    if student is None or student.is_deleted:
        raise StudentServiceError(404, "That student record was not found.")
    now = dt.datetime.now(dt.timezone.utc)
    student.is_deleted = True
    student.deleted_at = now
    student.deleted_by_user_id = actor.id
    student.delete_reason_id = reason_code_id
    student.delete_reason_detail = reason_detail
    student.recovery_deadline = (now + dt.timedelta(days=RECYCLE_PERIOD_DAYS)).date()
    session.flush()
    record_activity(
        session,
        user=actor,
        action="DELETE",
        page_or_function=STUDENT_PAGE,
        detail=f"Deleted student {student.student_id}.",
        record_reference=student.student_id,
        result="COMPLETED",
    )


def restore_student(session: Session, actor: User, student_pk: int) -> dict:
    student = session.get(Student, student_pk)
    if student is None or not student.is_deleted:
        raise StudentServiceError(404, "That deleted student record was not found.")
    student.is_deleted = False
    student.deleted_at = None
    student.deleted_by_user_id = None
    student.delete_reason_id = None
    student.delete_reason_detail = None
    student.recovery_deadline = None
    session.flush()
    record_activity(
        session,
        user=actor,
        action="RESTORE",
        page_or_function=STUDENT_PAGE,
        detail=f"Restored student {student.student_id}.",
        record_reference=student.student_id,
        result="COMPLETED",
    )
    return get_student(session, student.id)
