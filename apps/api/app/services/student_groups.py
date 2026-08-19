"""Cohort identity: intakes, groups, and the rolling timetable label.

The hierarchy, as approved on 13 August 2026:

    Qualification -> Intake (always) -> Group (SIT/RII only)

An **intake** exists for every qualification and follows from the student's
proposed start date. A **group** is a collection of intakes — usually about four,
but that is not fixed — and only qualifications beginning `SIT` or `RII` have
them. Everything else carries `N/A`.

`student_groups` already models this correctly despite its name: one row is one
intake, and `group_code` says which group that intake belongs to. A group is
therefore the set of rows sharing a `group_code`, not a table of its own. Four
SIT intakes share `Group 3`; a BSB intake sits alone with `N/A`.

Identity is `rolling_intake_label` wherever a rolling timetable exists, and the
`intake` date otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.student_rules import GROUP_ENABLED_QUALIFICATIONS, NO_GROUP
from app.models.course import CourseOffering
from app.models.qualification import Qualification
from app.models.student import StudentGroup


def uses_numbered_groups(qualification_code: str | None) -> bool:
    """Whether this qualification's intakes are gathered into numbered groups.

    Ten approved qualifications do; every other one — and every code-less ELICOS
    course — carries `N/A`. The list is the approved one, not a prefix match on
    `SIT`/`RII`: a future SIT qualification is not automatically group-enabled.
    """
    if not qualification_code:
        return False
    return qualification_code.strip().upper() in GROUP_ENABLED_QUALIFICATIONS


def cohort_identity(group: StudentGroup, qualification_code: str | None) -> str:
    """The cohort key for timetable and clash rules.

    Group for the ten group-enabled qualifications, intake for everything else —
    the single definition, so no module invents its own. A group spans several
    intakes, so for SIT/RII the group is the wider cohort and the one a clash
    rule must reason about.
    """
    if uses_numbered_groups(qualification_code) and group.group_code != NO_GROUP:
        return group.group_code
    return group.rolling_intake_label or group.intake.isoformat()


@dataclass
class LabelCoverage:
    """How far the rolling timetable has been supplied."""

    total_intakes: int
    with_label: int
    without_label: int
    qualifications_missing: list[str]

    @property
    def is_complete(self) -> bool:
        """True once every intake carries a rolling timetable label.

        Until then `student_groups.intake` remains the only identity most
        cohorts have, and the date column cannot safely be dropped.
        """
        return self.total_intakes > 0 and self.without_label == 0


def report_intakes_missing_a_label(session: Session) -> LabelCoverage:
    """Which cohorts still have no rolling timetable label.

    Exists to answer one question with evidence rather than opinion: *is it yet
    safe to drop `student_groups.intake` and keep only the label?* It is safe
    exactly when this reports zero. Today 69 of the 82 qualifications have no
    rolling timetable, so it will not.
    """
    total = session.execute(select(func.count()).select_from(StudentGroup)).scalar_one()
    with_label = session.execute(
        select(func.count())
        .select_from(StudentGroup)
        .where(StudentGroup.rolling_intake_label.is_not(None))
    ).scalar_one()

    missing = session.execute(
        select(Qualification.qualification_code)
        .join(CourseOffering, CourseOffering.qualification_id == Qualification.id)
        .join(StudentGroup, StudentGroup.course_offering_id == CourseOffering.id)
        .where(StudentGroup.rolling_intake_label.is_(None))
        .distinct()
        .order_by(Qualification.qualification_code)
    ).scalars().all()

    return LabelCoverage(
        total_intakes=total,
        with_label=with_label,
        without_label=total - with_label,
        qualifications_missing=[code for code in missing if code],
    )
