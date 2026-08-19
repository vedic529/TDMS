"""Request and response shapes for College and Course Reference Data.

Read, create and update payloads are separate types on purpose. A single shared
model would let the browser send `id`, `is_deleted` or `deleted_by_user_id` and
rely on the service to ignore them — which works right up until one endpoint
forgets. Values the backend owns simply do not exist on the create/update types.

SQLAlchemy models are never returned directly: an ORM object carries every
relationship it can reach, and serialising one is how internal structure leaks
into a public contract.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean(value: str | None) -> str | None:
    """Trim, and treat an all-whitespace string as absent."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


# ---------------------------------------------------------------------------
# College
# ---------------------------------------------------------------------------


class CollegeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    college_short_name: str
    college_full_name: str
    #: Used only to build a proposed student College Email (SRS §6.1.3).
    #: It is not, and must never become, an access rule.
    email_domain: str | None = None
    is_active: bool


class CollegeCreate(BaseModel):
    college_short_name: str = Field(..., min_length=1, max_length=50)
    college_full_name: str = Field(..., min_length=1, max_length=200)
    email_domain: str | None = Field(default=None, max_length=200)
    is_active: bool = True

    @field_validator("college_short_name", "college_full_name")
    @classmethod
    def _required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field is required.")
        return cleaned

    @field_validator("email_domain")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        return _clean(value)


class CollegeUpdate(BaseModel):
    """Every field optional: this is a PATCH, not a full replacement."""

    college_short_name: str | None = Field(default=None, min_length=1, max_length=50)
    college_full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email_domain: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Campus
# ---------------------------------------------------------------------------


class CampusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campus_code: str
    campus_name: str
    campus_location: str
    state: str
    is_active: bool
    #: Every spelling of this campus's address found in a source system,
    #: including `campus_location` itself. Incoming student and course data
    #: resolves whichever form it arrives in.
    source_addresses: list[str] = Field(default_factory=list)

    @field_validator("source_addresses", mode="before")
    @classmethod
    def _flatten(cls, value):
        """Accept the ORM relationship or a plain list of strings.

        `from_attributes` hands over `CampusSourceAddress` rows; the contract is
        a list of addresses, and the relationship shape is not the API's business.
        """
        if not value:
            return []
        return [getattr(item, "source_address", item) for item in value]


class CampusCreate(BaseModel):
    campus_code: str = Field(..., min_length=1, max_length=50)
    campus_name: str = Field(..., min_length=1, max_length=200)
    campus_location: str = Field(..., min_length=1, max_length=200)
    state: str = Field(..., min_length=1, max_length=50)
    is_active: bool = True

    @field_validator("campus_code", "campus_name", "campus_location", "state")
    @classmethod
    def _required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field is required.")
        return cleaned


class CampusUpdate(BaseModel):
    campus_code: str | None = Field(default=None, min_length=1, max_length=50)
    campus_name: str | None = Field(default=None, min_length=1, max_length=200)
    campus_location: str | None = Field(default=None, min_length=1, max_length=200)
    state: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None = None


class CollegeCampusLink(BaseModel):
    """One approved college/campus combination (COL-01).

    A campus can be operated by more than one college (DBQ-04), so this is a
    relationship in its own right rather than a column on `campuses`.
    """

    college_id: int
    campus_id: int
    is_active: bool = True


class CollegeCampusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    college_id: int
    campus_id: int
    is_active: bool


# ---------------------------------------------------------------------------
# Qualification
# ---------------------------------------------------------------------------


class QualificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    #: The business key. C-2: the SRS calls this Qualification Code; it is the
    #: VET Code. The internal `id` remains the database key.
    #:
    #: `None` where no code has been issued (ELICOS). The interface displays
    #: `NA`; the API stays honest about the absence rather than inventing a
    #: value, so a caller can tell "no code" from a code that happens to read
    #: "NA".
    qualification_code: str | None = None
    qualification_title: str
    course_level: str | None = None
    field_of_education_broad: str | None = None
    field_of_education_narrow: str | None = None
    course_sector: str | None = None
    #: C-4: Source URL is its own field, separate from the RTO relationship.
    source_url: str | None = None
    is_active: bool


#: Text that means "no Qualification Code has been issued". Accepted on input so
#: a spreadsheet or a user can type what they see, normalised to NULL on the way
#: in — one representation of absence in the database, not four.
NO_CODE_VALUES = {"", "NA", "N/A", "N.A.", "NONE", "NIL", "-"}


def _normalise_code(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    return None if cleaned in NO_CODE_VALUES else cleaned


class QualificationCreate(BaseModel):
    #: Optional: ELICOS courses have no VET Code. Absent, blank or "NA" all
    #: become NULL, and uniqueness applies only where a code is present.
    qualification_code: str | None = Field(default=None, max_length=50)
    qualification_title: str = Field(..., min_length=1, max_length=300)
    course_level: str | None = Field(default=None, max_length=100)
    field_of_education_broad: str | None = Field(default=None, max_length=200)
    field_of_education_narrow: str | None = Field(default=None, max_length=200)
    course_sector: str | None = Field(default=None, max_length=100)
    source_url: str | None = Field(default=None, max_length=500)
    is_active: bool = True

    @field_validator("qualification_code")
    @classmethod
    def _code(cls, value: str | None) -> str | None:
        return _normalise_code(value)

    @field_validator("qualification_title")
    @classmethod
    def _title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Qualification Title is required.")
        return cleaned


class QualificationUpdate(BaseModel):
    #: Editable: a code-less ELICOS qualification is given its real code here
    #: once one is issued. Sending "NA" clears it back to no code.
    qualification_code: str | None = Field(default=None, max_length=50)
    qualification_title: str | None = Field(default=None, min_length=1, max_length=300)
    course_level: str | None = Field(default=None, max_length=100)
    field_of_education_broad: str | None = Field(default=None, max_length=200)
    field_of_education_narrow: str | None = Field(default=None, max_length=200)
    course_sector: str | None = Field(default=None, max_length=100)
    source_url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None

    @field_validator("qualification_code")
    @classmethod
    def _code(cls, value: str | None) -> str | None:
        return _normalise_code(value)


# ---------------------------------------------------------------------------
# Unit
# ---------------------------------------------------------------------------


class UnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    unit_code: str
    unit_title: str
    #: SRS §5.3 "UoC Type": THEORY or THEORY_AND_PRACTICAL.
    uoc_type: str | None = None
    is_active: bool


class UnitCreate(BaseModel):
    unit_code: str = Field(..., min_length=1, max_length=50)
    unit_title: str = Field(..., min_length=1, max_length=300)
    uoc_type: str | None = None
    is_active: bool = True

    @field_validator("unit_code")
    @classmethod
    def _code(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Unit Code is required.")
        return cleaned

    @field_validator("unit_title")
    @classmethod
    def _title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Unit Title is required.")
        return cleaned


class UnitUpdate(BaseModel):
    unit_code: str | None = Field(default=None, min_length=1, max_length=50)
    unit_title: str | None = Field(default=None, min_length=1, max_length=300)
    uoc_type: str | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Qualification / Unit delivery sequence (Page 4B)
# ---------------------------------------------------------------------------


class QualificationUnitRead(BaseModel):
    """One unit's place in a qualification's approved delivery sequence.

    C-1: the SRS states a separate "Sequence ID" is not a Page 4B field. A
    relational table has no inherent row order, so the ordinal is persisted as
    `delivery_order` and used for ordering — TT-08 depends on it — rather than
    presented as a field of its own.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    qualification_id: int
    qualification_code: str | None = None
    #: Retired codes that this qualification replaced. A student enrolled under
    #: `CHC30121` belongs to `CHC30125`, so both resolve here.
    qualification_superseded_codes: list[str] = Field(default_factory=list)
    qualification_title: str
    unit_id: int
    unit_code: str
    unit_title: str
    uoc_type: str | None = None
    delivery_order: int
    is_deleted: bool = False


class QualificationUnitCreate(BaseModel):
    qualification_id: int
    unit_id: int
    delivery_order: int = Field(..., ge=1, le=999)


class QualificationUnitUpdate(BaseModel):
    unit_id: int | None = None
    delivery_order: int | None = Field(default=None, ge=1, le=999)


# ---------------------------------------------------------------------------
# Course offering (Page 4A "Course Data")
# ---------------------------------------------------------------------------


class CourseOfferingRead(BaseModel):
    """A qualification offered by one college at one campus.

    Composed rather than mapped one-to-one from the table: the qualification
    attributes and the campus location live on their own entities, and the
    approved durations are a child table. `location` is **derived** from the
    campus (C-3) — there is no second free-text column to disagree with it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    course_code: str

    college_id: int
    #: Page 4A "RTO" is this college (DBQ-06, SRS §1.4/§8.2).
    college_short_name: str
    college_full_name: str

    campus_id: int
    campus_name: str
    #: C-3: Page 4A "Location" IS the campus value.
    location: str
    state: str

    qualification_id: int
    qualification_code: str | None = None
    qualification_title: str
    course_level: str | None = None
    field_of_education_broad: str | None = None
    field_of_education_narrow: str | None = None
    course_sector: str | None = None
    source_url: str | None = None

    course_status_id: int
    course_status_code: str
    course_status_label: str
    selectable_for_new_records: bool

    total_course_cost: Decimal | None = None
    #: DBQ-03: approved durations are a child table, so a 26-week and a 52-week
    #: version of the same offering are options rather than separate rows.
    duration_options: list[int] = Field(default_factory=list)

    is_deleted: bool = False
    deleted_at: dt.datetime | None = None
    recovery_deadline: dt.date | None = None
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None


class CourseOfferingCreate(BaseModel):
    college_id: int
    campus_id: int
    qualification_id: int
    course_code: str = Field(..., min_length=1, max_length=50)
    course_status_id: int
    total_course_cost: Decimal | None = Field(default=None, ge=0)
    duration_options: list[int] = Field(default_factory=list)

    @field_validator("course_code")
    @classmethod
    def _code(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Course Code is required.")
        return cleaned

    @field_validator("duration_options")
    @classmethod
    def _durations(cls, value: list[int]) -> list[int]:
        for weeks in value:
            if weeks <= 0:
                raise ValueError("A duration must be a positive number of weeks.")
        # De-duplicated here so the database constraint is not the first thing
        # to notice a repeated value the user typed twice.
        return sorted(set(value))


class CourseOfferingUpdate(BaseModel):
    course_code: str | None = Field(default=None, min_length=1, max_length=50)
    course_status_id: int | None = None
    total_course_cost: Decimal | None = Field(default=None, ge=0)
    duration_options: list[int] | None = None


class CourseStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    label: str
    #: COL-05: a superseded status stays visible on historical records but is
    #: not offered for new ones.
    selectable_for_new_records: bool
    is_active: bool


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


class DeleteRequest(BaseModel):
    """DATA-04 / LOG-03: a deletion carries an approved reason.

    `reason_code_id` is optional only because the approved reason list (OD-06)
    has not been settled and `reason_codes` may legitimately be empty. Once it
    is populated the service requires one.
    """

    reason_code_id: int | None = None
    reason_detail: str | None = Field(default=None, max_length=1000)


class RestoreRequest(BaseModel):
    reason_code_id: int | None = None
    reason_detail: str | None = Field(default=None, max_length=1000)
