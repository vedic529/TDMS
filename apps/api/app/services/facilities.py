"""Facility eligibility.

Two rules decide whether a room may host a class, and both are here rather than
in a route or a query so the API, the importer and the tests apply one
implementation:

* **Faculty suitability** — a qualification's faculty is read from the first
  three letters of its code, never from the whole code, because a new
  qualification in an existing faculty must not require a code change here.
* **Weekday availability** — the room's row for that faculty must say the day
  is available.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.college import Campus
from app.models.facility import Facility, FacilityCollege, FacilityFaculty

#: Qualification code prefix -> faculty. Approved with the Facility Data
#: requirement. A prefix is three characters in every approved training package.
FACULTY_BY_PREFIX: dict[str, str] = {
    "BSB": "Business",
    "FNS": "Business",
    "SIT": "Hospitality",
    "CHC": "Community Services",
    "AUR": "Engineering Technology",
    "CPC": "Engineering Technology",
    "ICT": "Engineering Technology",
    "RII": "Engineering Technology",
    "TLI": "Engineering Technology",
    "AHC": "Engineering Technology",
}

#: A facility carrying this faculty is not restricted to one faculty: it is
#: eligible for every qualification. Stored as supplied rather than as NULL —
#: it is a rule, not a missing value.
UNRESTRICTED_FACULTY = "NA"

#: Present in the supplied data but absent from the approved prefix mapping.
#: ELICOS is English-language delivery and has no VET qualification code, so no
#: qualification maps to it. Named here so the gap is visible rather than
#: looking like a matching bug.
FACULTIES_WITHOUT_A_PREFIX = frozenset({"ELICOS"})

PREFIX_LENGTH = 3


def faculty_for_qualification_code(qualification_code: str | None) -> str | None:
    """The faculty a qualification belongs to, or None when its prefix is unmapped.

    Returns None rather than guessing. An unmapped prefix means the approved
    mapping needs extending, which is a decision, not something to infer.
    """
    if not qualification_code:
        return None
    prefix = qualification_code.strip().upper()[:PREFIX_LENGTH]
    return FACULTY_BY_PREFIX.get(prefix)


def is_faculty_eligible(facility_faculty: str, qualification_code: str | None) -> bool:
    """Whether a room's faculty rule admits a qualification.

        facility faculty is NA          -> eligible, whatever the qualification
        facility faculty == mapped one  -> eligible
        otherwise                       -> not eligible

    An unmapped qualification prefix is only eligible for an `NA` room. That is
    deliberate: silently admitting it everywhere would invent a mapping.
    """
    supplied = (facility_faculty or "").strip()
    if supplied.upper() == UNRESTRICTED_FACULTY:
        return True
    mapped = faculty_for_qualification_code(qualification_code)
    return mapped is not None and mapped == supplied


@dataclass(frozen=True)
class EligibleFacility:
    """A room that may host the class, and the faculty rule that admitted it."""

    facility: Facility
    matched_faculty: str


def list_facilities(
    session: Session,
    *,
    campus_ids: list[int] | None = None,
    college_ids: list[int] | None = None,
    faculty: str | None = None,
    active_only: bool = False,
) -> list[Facility]:
    """Facilities with their colleges and faculty rules loaded.

    An empty or absent id list means no restriction, matching
    `reference_data.list_offered_qualifications`.
    """
    statement = (
        select(Facility)
        .options(selectinload(Facility.colleges), selectinload(Facility.faculties))
        .join(Campus, Campus.id == Facility.campus_id)
        .order_by(Campus.campus_name, Facility.source_location, Facility.facility_reference)
    )
    if campus_ids:
        statement = statement.where(Facility.campus_id.in_(campus_ids))
    if college_ids:
        statement = statement.where(
            Facility.id.in_(
                select(FacilityCollege.facility_id).where(
                    FacilityCollege.college_id.in_(college_ids)
                )
            )
        )
    if faculty:
        statement = statement.where(
            Facility.id.in_(
                select(FacilityFaculty.facility_id).where(FacilityFaculty.faculty == faculty)
            )
        )
    if active_only:
        statement = statement.where(Facility.is_active.is_(True))

    return list(session.execute(statement).scalars().unique())


def eligible_facilities(
    session: Session,
    *,
    qualification_code: str,
    weekday: str,
    campus_id: int | None = None,
    college_id: int | None = None,
    active_only: bool = True,
) -> list[EligibleFacility]:
    """Rooms that may host a class of this qualification on this weekday.

    Only the two confirmed rules are applied — faculty suitability and weekday
    availability. Capacity is returned for the caller to display; it does not
    filter, because no capacity rule has been approved. Classroom Type does not
    filter either: nothing in TDMS maps a type to Theory or Practical.
    """
    candidates = list_facilities(
        session,
        campus_ids=[campus_id] if campus_id else None,
        college_ids=[college_id] if college_id else None,
        active_only=active_only,
    )

    eligible: list[EligibleFacility] = []
    for facility in candidates:
        for rule in facility.faculties:
            if not is_faculty_eligible(rule.faculty, qualification_code):
                continue
            if not rule.available_on(weekday):
                continue
            eligible.append(EligibleFacility(facility=facility, matched_faculty=rule.faculty))
            break
    return eligible
