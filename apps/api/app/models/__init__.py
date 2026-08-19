"""TDMS ORM models — the approved Database Schema v1.

**Every model module must be imported here.** Alembic autogeneration compares
`Base.metadata` against the database, and a model that was never imported is
invisible to it — the table would silently disappear from the next migration.
Importing them all in one place is what makes that impossible.
"""

from __future__ import annotations

from app.db.base import Base

# Identity and access
from app.models.user import User
from app.models.access_request import AccessRequest

# Audit and control
from app.models.reason import ReasonCode, ReasonCodeContext
from app.models.activity import UserActivityRecord

# Reference data
from app.models.college import Campus, College, CollegeCampus
from app.models.qualification import Qualification, QualificationUnit, Unit
from app.models.course import CourseOffering, CourseStatus, OfferingDurationOption
from app.models.facility import Facility

# Students
from app.models.student import Student, StudentGroup

# Trainers
from app.models.trainer import Trainer, TrainerAvailability, TrainerQualification, TrainerUnit

# Timetables
from app.models.timetable import (
    TimetableClashOverride,
    TimetablePlan,
    TimetableSession,
    TimetableUnitDelivery,
)

# Imports
from app.models.import_batch import ImportBatch, ImportRowIssue, ImportStagedRow

__all__ = [
    "Base",
    # identity and access
    "User",
    "AccessRequest",
    # audit and control
    "ReasonCode",
    "ReasonCodeContext",
    "UserActivityRecord",
    # reference data
    "College",
    "Campus",
    "CollegeCampus",
    "Qualification",
    "Unit",
    "QualificationUnit",
    "CourseStatus",
    "CourseOffering",
    "OfferingDurationOption",
    "Facility",
    # students
    "StudentGroup",
    "Student",
    # trainers
    "Trainer",
    "TrainerAvailability",
    "TrainerQualification",
    "TrainerUnit",
    # timetables
    "TimetablePlan",
    "TimetableUnitDelivery",
    "TimetableSession",
    "TimetableClashOverride",
    # imports
    "ImportBatch",
    "ImportStagedRow",
    "ImportRowIssue",
]

#: The approved business tables, in dependency order. 27 from Schema v1 plus
#: `access_requests` from Access Model v1.1.
#: `alembic_version` is Alembic's bookkeeping and is not a business table.
EXPECTED_TABLES: tuple[str, ...] = (
    "users",
    "access_requests",
    "reason_codes",
    "reason_code_contexts",
    "user_activity_records",
    "colleges",
    "campuses",
    "campus_source_addresses",
    "college_campuses",
    "qualifications",
    "units",
    "qualification_units",
    "qualification_supersessions",
    "course_statuses",
    "course_offerings",
    "offering_duration_options",
    "facilities",
    "student_groups",
    "students",
    "trainers",
    "trainer_availability",
    "trainer_qualifications",
    "trainer_units",
    "timetable_plans",
    "timetable_unit_deliveries",
    "timetable_sessions",
    "timetable_clash_overrides",
    "import_batches",
    "import_staged_rows",
    "import_row_issues",
)

#: Database views created by migration (Alembic does not autogenerate views).
EXPECTED_VIEWS: tuple[str, ...] = ("trainer_availability_days",)
