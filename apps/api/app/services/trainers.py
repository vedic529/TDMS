"""Trainer Data — list, detail, unit coverage, and the manual add actions.

**Nothing here issues a query per trainer, per location or per unit.** The list
is one statement with two grouped subqueries; the detail is three; unit coverage
is one. The allocation importer's per-row `_match_intakes` is the mistake this
module exists not to repeat, and `test_trainer_api.py` pins the counts.

A trainer's **training packages are derived** — the distinct first three
characters of the qualification codes they teach, upper-cased. They are never
stored, because a trainer is not tied to one training package: the real BSB
source file contains a trainer who teaches only FNS qualifications.
"""

from __future__ import annotations

import re

from sqlalchemy import Integer as sa_Integer
from sqlalchemy import update
from sqlalchemy import Select, Text, and_, case, delete, func, or_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session

from app.models.allocation import AllocationDelivery, AllocationSession
from app.models.college import Campus, CampusSourceAddress, College
from app.models.qualification import Qualification, QualificationUnit, Unit
from app.models.trainer import Trainer, TrainerAvailability, TrainerQualification, TrainerUnit
from app.models.user import User
from app.services.activity import record_activity

PAGE = "Page 3 - Trainer Data"


class TrainerError(ValueError):
    """A refusal the route turns into a 4xx."""


# ---------------------------------------------------------------------------
# The generated trainer id
# ---------------------------------------------------------------------------

#: `TI_010_AY` — the tag, the sequence, the initials.
TRAINER_ID_PATTERN = re.compile(r"^TI_(\d+)_[A-Z]+$", re.IGNORECASE)

#: Titles that are not part of a name. Stripped before taking initials, so
#: `Dr. Navdeep Verma` gives NV rather than DN.
_TITLES = {"DR", "PROF", "MR", "MRS", "MS", "MISS", "A/PROF", "ASSOC"}

#: Three digits, so the sequence sorts and reads consistently to 999.
_SEQUENCE_WIDTH = 3


def trainer_initials(name: str) -> str:
    """The third section of a trainer id.

    One word gives its first two letters; two or more give the first letter of
    each of the first two. A title is not part of the name.

    `M. Sajed` -> MS, `Dr. Nisha Kalra` -> NK, `Arsalan` -> AR.
    """
    words = [word for word in re.split(r"\s+", (name or "").strip()) if word]
    words = [w for w in words if w.strip(".").upper() not in _TITLES] or words
    letters = ["".join(ch for ch in word if ch.isalpha()) for word in words]
    letters = [part for part in letters if part]
    if not letters:
        return "XX"
    if len(letters) == 1:
        # A single name gives two letters, padded if it is one character long.
        return (letters[0][:2].upper()).ljust(2, "X")
    return (letters[0][0] + letters[1][0]).upper()


def next_trainer_sequence(session: Session) -> int:
    """One past the highest number ever assigned.

    Read from `trainers` itself, **including soft-deleted rows**, so a retired
    id is never handed to anyone else. Clearing the trainer database empties the
    table and numbering restarts at 1, which is the approved behaviour — and
    keeping the counter in the rows rather than beside them means the two can
    never drift apart.
    """
    highest = session.execute(
        select(
            func.max(
                func.cast(
                    func.substring(Trainer.trainer_id, r"^TI_(\d+)_"), sa_Integer
                )
            )
        )
    ).scalar()
    return int(highest or 0) + 1


def generate_trainer_id(session: Session, name: str) -> str:
    """The id a trainer with this name would be given next."""
    return f"TI_{next_trainer_sequence(session):0{_SEQUENCE_WIDTH}d}_{trainer_initials(name)}"


# ---------------------------------------------------------------------------
# The Location Dictionary (2.4)
# ---------------------------------------------------------------------------


def location_dictionary(session: Session) -> list[dict]:
    """State -> City -> Campus -> Address, in one query.

    A campus with no city is grouped under `None` and rendered "City not
    recorded" by the client. No city is invented here: the column is new, most
    campuses predate it, and a guess would be indistinguishable from data.
    """
    addresses = (
        select(
            CampusSourceAddress.campus_id.label("campus_id"),
            func.array_agg(
                aggregate_order_by(
                    CampusSourceAddress.source_address, CampusSourceAddress.source_address
                )
            ).label("spellings"),
        )
        .group_by(CampusSourceAddress.campus_id)
        .subquery()
    )
    rows = session.execute(
        select(
            Campus.id,
            Campus.campus_code,
            Campus.campus_name,
            Campus.campus_location,
            Campus.state,
            Campus.city,
            Campus.approved_address,
            Campus.is_active,
            addresses.c.spellings,
        )
        .outerjoin(addresses, addresses.c.campus_id == Campus.id)
        # Ordering is the display order: state, then city, then campus name.
        # NULLS LAST keeps "City not recorded" at the foot of its state.
        .order_by(Campus.state, Campus.city.nulls_last(), Campus.campus_name)
    ).all()

    states: list[dict] = []
    for row in rows:
        if not states or states[-1]["state"] != row.state:
            states.append({"state": row.state, "cities": []})
        cities = states[-1]["cities"]
        if not cities or cities[-1]["city"] != row.city:
            cities.append({"city": row.city, "campuses": []})
        cities[-1]["campuses"].append(
            {
                "id": row.id,
                "campus_code": row.campus_code,
                "campus_name": row.campus_name,
                "campus_location": row.campus_location,
                "approved_address": row.approved_address,
                "is_active": row.is_active,
                "source_addresses": list(row.spellings or []),
            }
        )
    return states


# ---------------------------------------------------------------------------
# Shared expressions
# ---------------------------------------------------------------------------


def _package(code_column) -> object:
    """The training package a qualification code belongs to."""
    return func.upper(func.substr(code_column, 1, 3))


# ---------------------------------------------------------------------------
# List (2.6)
# ---------------------------------------------------------------------------


def _location_summary_subquery():
    """Per trainer: how many locations, and their names in one line."""
    label = func.coalesce(
        Campus.campus_name,
        func.nullif(TrainerAvailability.location_text, ""),
        "Unresolved location",
    )
    offshore = case((TrainerAvailability.is_offshore, "Offshore"), else_=label)
    return (
        select(
            TrainerAvailability.trainer_id.label("trainer_id"),
            func.count().label("location_count"),
            func.string_agg(offshore, ", ").label("location_summary"),
        )
        .outerjoin(Campus, Campus.id == TrainerAvailability.campus_id)
        .group_by(TrainerAvailability.trainer_id)
        .subquery()
    )


def _teaching_subquery():
    """Per trainer: qualification count, unit count and derived packages."""
    return (
        select(
            TrainerUnit.trainer_id.label("trainer_id"),
            # Coalesced, so a link held as text still counts. Counting the id
            # alone would under-report every raised value.
            func.count(
                func.distinct(
                    func.coalesce(
                        func.cast(TrainerUnit.qualification_id, Text),
                        TrainerUnit.qualification_text,
                    )
                )
            ).label("qualification_count"),
            func.count(
                func.distinct(
                    func.coalesce(func.cast(TrainerUnit.unit_id, Text), TrainerUnit.unit_text)
                )
            ).label("unit_count"),
            func.array_agg(
                func.distinct(
                    _package(
                        func.coalesce(
                            Qualification.qualification_code, TrainerUnit.qualification_text
                        )
                    )
                )
            ).label("packages"),
        )
        .outerjoin(Qualification, Qualification.id == TrainerUnit.qualification_id)
        .group_by(TrainerUnit.trainer_id)
        .subquery()
    )


def list_trainers(
    session: Session,
    *,
    search: str | None = None,
    campus_id: int | None = None,
    qualification_id: int | None = None,
    unit_id: int | None = None,
    is_active: bool | None = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """One row per trainer (1.5), however many locations they work at."""
    locations = _location_summary_subquery()
    teaching = _teaching_subquery()

    stmt: Select = (
        select(
            Trainer.id,
            Trainer.trainer_id,
            Trainer.trainer_name,
            Trainer.city,
            Trainer.is_active,
            func.coalesce(locations.c.location_count, 0).label("location_count"),
            func.coalesce(locations.c.location_summary, "").label("location_summary"),
            func.coalesce(teaching.c.qualification_count, 0).label("qualification_count"),
            func.coalesce(teaching.c.unit_count, 0).label("unit_count"),
            teaching.c.packages,
        )
        .outerjoin(locations, locations.c.trainer_id == Trainer.id)
        .outerjoin(teaching, teaching.c.trainer_id == Trainer.id)
    )

    conditions = []
    if not include_deleted:
        conditions.append(Trainer.is_deleted.is_(False))
    if is_active is not None:
        conditions.append(Trainer.is_active.is_(is_active))
    if search:
        needle = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(Trainer.trainer_id).like(needle),
                func.lower(Trainer.trainer_name).like(needle),
                func.lower(func.coalesce(Trainer.city, "")).like(needle),
            )
        )
    if campus_id is not None:
        conditions.append(
            Trainer.id.in_(
                select(TrainerAvailability.trainer_id).where(
                    TrainerAvailability.campus_id == campus_id
                )
            )
        )
    if qualification_id is not None:
        # TRN-01: the indexed join, not a scan through the units table (2.3).
        conditions.append(
            Trainer.id.in_(
                select(TrainerQualification.trainer_id).where(
                    TrainerQualification.qualification_id == qualification_id
                )
            )
        )
    if unit_id is not None:
        conditions.append(
            Trainer.id.in_(select(TrainerUnit.trainer_id).where(TrainerUnit.unit_id == unit_id))
        )
    if conditions:
        stmt = stmt.where(and_(*conditions))

    total = session.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()

    rows = session.execute(
        stmt.order_by(Trainer.trainer_id).limit(limit).offset(offset)
    ).all()

    return [
        {
            "id": row.id,
            "trainer_id": row.trainer_id,
            "trainer_name": row.trainer_name,
            "city": row.city,
            "is_active": row.is_active,
            "location_count": row.location_count,
            "location_summary": row.location_summary,
            "qualification_count": row.qualification_count,
            "unit_count": row.unit_count,
            "training_packages": sorted(p for p in (row.packages or []) if p),
        }
        for row in rows
    ], total


# ---------------------------------------------------------------------------
# Detail (2.6) — the whole side panel in one round trip
# ---------------------------------------------------------------------------


def get_trainer(session: Session, trainer_pk: int) -> dict:
    """The trainer, every location with its weekdays, every qualification with
    its units nested inside it.

    Three statements, whatever the trainer holds. The side panel makes no
    further request when a tray is expanded (2.10).
    """
    trainer = session.get(Trainer, trainer_pk)
    if trainer is None or trainer.is_deleted:
        raise TrainerError("That trainer was not found.")

    locations = session.execute(
        select(TrainerAvailability, Campus.campus_name)
        .outerjoin(Campus, Campus.id == TrainerAvailability.campus_id)
        .where(TrainerAvailability.trainer_id == trainer_pk)
        .order_by(TrainerAvailability.is_offshore, Campus.campus_name, TrainerAvailability.id)
    ).all()

    unit_rows = session.execute(
        select(
            TrainerUnit.id,
            TrainerUnit.qualification_id,
            TrainerUnit.qualification_text,
            Qualification.qualification_code,
            Qualification.qualification_title,
            Unit.id.label("unit_id"),
            Unit.unit_code,
            Unit.unit_title,
            TrainerUnit.unit_text,
        )
        # **Outer** joins on both. A link may hold an unmatched qualification or
        # unit as text with a null id; an inner join would silently drop exactly
        # the rows a raised suggestion exists to keep visible.
        .outerjoin(Unit, Unit.id == TrainerUnit.unit_id)
        .outerjoin(Qualification, Qualification.id == TrainerUnit.qualification_id)
        .where(TrainerUnit.trainer_id == trainer_pk)
        .order_by(
            func.coalesce(Qualification.qualification_code, TrainerUnit.qualification_text),
            func.coalesce(Unit.unit_code, TrainerUnit.unit_text),
        )
    ).all()

    qualifications: list[dict] = []
    index: dict[int | None, dict] = {}
    packages: set[str] = set()
    for row in unit_rows:
        # An unmatched qualification groups by its text, so two different
        # unmatched values do not collapse into one heading.
        group_key = row.qualification_id if row.qualification_id else f"t:{row.qualification_text}"
        group = index.get(group_key)
        if group is None:
            code = row.qualification_code or row.qualification_text
            group = {
                "qualification_id": row.qualification_id,
                "qualification_code": code,
                "qualification_title": row.qualification_title
                or ("Not in the reference data yet" if row.qualification_text else "Qualification not recorded"),
                "qualification_unresolved": row.qualification_id is None,
                "units": [],
            }
            index[group_key] = group
            qualifications.append(group)
        group["units"].append(
            {
                "id": row.id,
                "unit_id": row.unit_id,
                "unit_code": row.unit_code or row.unit_text or "",
                "unit_title": row.unit_title or "Not in the reference data yet",
                "unresolved": row.unit_id is None,
            }
        )
        # Derived from the code either way: a raised qualification still names
        # its package, and hiding it would misreport what the trainer teaches.
        code = row.qualification_code or row.qualification_text
        if code:
            packages.add(code[:3].upper())

    return {
        "id": trainer.id,
        "trainer_id": trainer.trainer_id,
        "trainer_name": trainer.trainer_name,
        "city": trainer.city,
        "is_active": trainer.is_active,
        "training_packages": sorted(packages),
        "locations": [
            {
                "id": row.TrainerAvailability.id,
                "campus_id": row.TrainerAvailability.campus_id,
                "campus_name": row.campus_name,
                "location_text": row.TrainerAvailability.location_text,
                "is_offshore": row.TrainerAvailability.is_offshore,
                "location": row.TrainerAvailability.location,
                "location_type": row.TrainerAvailability.location_type,
                "class_type": row.TrainerAvailability.class_type,
                "working_time_start": row.TrainerAvailability.working_time_start,
                "working_time_end": row.TrainerAvailability.working_time_end,
                "working_time_text": row.TrainerAvailability.working_time_text,
                "monday": row.TrainerAvailability.monday,
                "tuesday": row.TrainerAvailability.tuesday,
                "wednesday": row.TrainerAvailability.wednesday,
                "thursday": row.TrainerAvailability.thursday,
                "friday": row.TrainerAvailability.friday,
            }
            for row in locations
        ],
        "qualifications": qualifications,
    }


# ---------------------------------------------------------------------------
# Unit coverage (2.7)
# ---------------------------------------------------------------------------


def unit_coverage(
    session: Session,
    *,
    qualification_id: int | None = None,
    only_uncovered: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Every unit, with how many trainers can teach it.

    **Outer-joined from `units`**, so a unit no trainer covers still appears —
    that gap is the entire point of the view.

    A row is a (unit, qualification) pair, and `trainer_count` is scoped to that
    qualification. `trainer_units` records the qualification a trainer was
    approved under, so "who can teach this unit" is only answerable within one.

    One grouped query, whatever the unit count.
    """
    approved = (
        # Counted here rather than joined into the outer query, so an inactive
        # or soft-deleted trainer is excluded without dropping the unit (U4).
        select(
            TrainerUnit.unit_id.label("unit_id"),
            TrainerUnit.qualification_id.label("qualification_id"),
            func.count(func.distinct(Trainer.id)).label("trainer_count"),
            func.array_agg(func.distinct(Trainer.trainer_name)).label("trainer_names"),
        )
        .join(Trainer, Trainer.id == TrainerUnit.trainer_id)
        .where(Trainer.is_deleted.is_(False), Trainer.is_active.is_(True))
        .group_by(TrainerUnit.unit_id, TrainerUnit.qualification_id)
        .subquery()
    )

    stmt = (
        select(
            Unit.id.label("unit_id"),
            Unit.unit_code,
            Unit.unit_title,
            Qualification.id.label("qualification_id"),
            Qualification.qualification_code,
            Qualification.qualification_title,
            func.coalesce(approved.c.trainer_count, 0).label("trainer_count"),
            approved.c.trainer_names,
        )
        .outerjoin(
            QualificationUnit,
            and_(
                QualificationUnit.unit_id == Unit.id,
                QualificationUnit.is_deleted.is_(False),
            ),
        )
        .outerjoin(Qualification, Qualification.id == QualificationUnit.qualification_id)
        .outerjoin(
            approved,
            and_(
                approved.c.unit_id == Unit.id,
                approved.c.qualification_id == QualificationUnit.qualification_id,
            ),
        )
    )

    conditions = []
    if qualification_id is not None:
        conditions.append(Qualification.id == qualification_id)
    if only_uncovered:
        conditions.append(func.coalesce(approved.c.trainer_count, 0) == 0)
    if conditions:
        stmt = stmt.where(and_(*conditions))

    total = session.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()

    rows = session.execute(
        # The gaps come first (U6).
        stmt.order_by(
            func.coalesce(approved.c.trainer_count, 0), Unit.unit_code
        ).limit(limit).offset(offset)
    ).all()

    items = []
    for row in rows:
        names = [n for n in (row.trainer_names or []) if n]
        items.append(
            {
                "unit_id": row.unit_id,
                "unit_code": row.unit_code,
                "unit_title": row.unit_title,
                "qualification_id": row.qualification_id,
                "qualification_code": row.qualification_code,
                "qualification_title": row.qualification_title,
                "trainer_count": row.trainer_count,
                "trainer_names": sorted(names)[:5],
                "has_more_trainers": len(names) > 5,
            }
        )
    return items, total


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


def create_trainer(session: Session, *, data: dict, user: User) -> dict:
    """Add one trainer by hand.

    The id is **generated**, never supplied: `TI_010_AY`. The city is required —
    it is the one thing a trainer record cannot be read without. A location and
    a set of units are optional, so a trainer can be recorded before their
    timetable is known and completed later from the side panel.
    """
    name = (data.get("trainer_name") or "").strip()
    city = (data.get("city") or "").strip()
    if not name:
        raise TrainerError("A trainer needs a name.")
    if not city:
        raise TrainerError("A trainer needs a city.")

    trainer = Trainer(
        trainer_id=generate_trainer_id(session, name),
        trainer_name=name,
        city=city,
        is_active=bool(data.get("is_active", True)),
    )
    session.add(trainer)
    session.flush()

    record_activity(
        session,
        user=user,
        action="CREATE",
        page_or_function=PAGE,
        detail=f"Created trainer {trainer.trainer_id} ({name}) in {city}.",
        record_reference=str(trainer.id),
        result="COMPLETED",
    )

    # Both optional and both repeatable. Offered on the same form so a complete
    # record can be entered in one pass, without forcing an incomplete one to be
    # saved and then completed twice.
    for location in data.get("locations") or []:
        add_location(session, trainer.id, data=location, user=user)
    for units in data.get("units") or []:
        add_units(session, trainer.id, data=units, user=user)
    return get_trainer(session, trainer.id)


def update_trainer(session: Session, trainer_pk: int, *, data: dict, user: User) -> dict:
    trainer = session.get(Trainer, trainer_pk)
    if trainer is None or trainer.is_deleted:
        raise TrainerError("That trainer was not found.")
    changed = []
    if data.get("trainer_name") is not None:
        trainer.trainer_name = data["trainer_name"].strip()
        changed.append("name")
    if data.get("city") is not None:
        trainer.city = data["city"].strip() or None
        changed.append("city")
    if data.get("is_active") is not None:
        trainer.is_active = bool(data["is_active"])
        changed.append("active state")
    session.flush()
    record_activity(
        session,
        user=user,
        action="UPDATE",
        page_or_function=PAGE,
        detail=f"Updated the {' and '.join(changed) or 'record'} for trainer {trainer.trainer_id}.",
        record_reference=str(trainer.id),
        result="COMPLETED",
    )
    return get_trainer(session, trainer.id)


def add_location(session: Session, trainer_pk: int, *, data: dict, user: User) -> dict:
    trainer = session.get(Trainer, trainer_pk)
    if trainer is None or trainer.is_deleted:
        raise TrainerError("That trainer was not found.")

    is_offshore = bool(data.get("is_offshore"))
    campus_id = data.get("campus_id")
    if is_offshore and campus_id is not None:
        raise TrainerError("An offshore location has no campus.")
    if not is_offshore and campus_id is None:
        raise TrainerError("Choose a campus, or mark the location offshore.")
    if data["working_time_end"] <= data["working_time_start"]:
        raise TrainerError("The working time must end after it starts.")

    row = TrainerAvailability(
        trainer_id=trainer_pk,
        campus_id=campus_id,
        is_offshore=is_offshore,
        location_text="Offshore" if is_offshore else None,
        location=data.get("location"),
        location_type=data.get("location_type"),
        class_type=data["class_type"],
        working_time_start=data["working_time_start"],
        working_time_end=data["working_time_end"],
        working_time_text=data.get("working_time_text"),
        monday=data.get("monday", "NOT_AVAILABLE"),
        tuesday=data.get("tuesday", "NOT_AVAILABLE"),
        wednesday=data.get("wednesday", "NOT_AVAILABLE"),
        thursday=data.get("thursday", "NOT_AVAILABLE"),
        friday=data.get("friday", "NOT_AVAILABLE"),
    )
    session.add(row)
    session.flush()
    record_activity(
        session,
        user=user,
        action="CREATE",
        page_or_function=PAGE,
        detail=f"Added a location for trainer {trainer.trainer_id}.",
        record_reference=str(row.id),
        result="COMPLETED",
    )
    return get_trainer(session, trainer_pk)


def update_location(
    session: Session, trainer_pk: int, availability_id: int, *, data: dict, user: User
) -> dict:
    row = session.get(TrainerAvailability, availability_id)
    if row is None or row.trainer_id != trainer_pk:
        raise TrainerError("That location was not found for this trainer.")
    for field in (
        "location",
        "location_type",
        "class_type",
        "working_time_start",
        "working_time_end",
        "working_time_text",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
    ):
        if data.get(field) is not None:
            setattr(row, field, data[field])
    if data.get("is_offshore") is not None:
        row.is_offshore = bool(data["is_offshore"])
        if row.is_offshore:
            row.campus_id = None
            row.location_text = "Offshore"
    if data.get("campus_id") is not None:
        row.campus_id = data["campus_id"]
        row.is_offshore = False
        row.location_text = None
    if row.working_time_end <= row.working_time_start:
        raise TrainerError("The working time must end after it starts.")
    session.flush()
    record_activity(
        session,
        user=user,
        action="UPDATE",
        page_or_function=PAGE,
        detail=f"Updated a location for trainer {row.trainer_id}.",
        record_reference=str(row.id),
        result="COMPLETED",
    )
    return get_trainer(session, trainer_pk)


def remove_location(
    session: Session, trainer_pk: int, availability_id: int, *, user: User
) -> dict:
    row = session.get(TrainerAvailability, availability_id)
    if row is None or row.trainer_id != trainer_pk:
        raise TrainerError("That location was not found for this trainer.")
    session.delete(row)
    session.flush()
    record_activity(
        session,
        user=user,
        action="DELETE",
        page_or_function=PAGE,
        detail=f"Removed a location from trainer {trainer_pk}.",
        record_reference=str(availability_id),
        result="COMPLETED",
    )
    return get_trainer(session, trainer_pk)


def add_units(session: Session, trainer_pk: int, *, data: dict, user: User) -> dict:
    """One qualification and many units, in one call (1.6)."""
    trainer = session.get(Trainer, trainer_pk)
    if trainer is None or trainer.is_deleted:
        raise TrainerError("That trainer was not found.")
    qualification_id = data["qualification_id"]
    unit_ids = [int(x) for x in data.get("unit_ids") or []]
    if not unit_ids:
        raise TrainerError("Choose at least one unit.")

    existing = set(
        session.execute(
            select(TrainerUnit.unit_id).where(
                TrainerUnit.trainer_id == trainer_pk,
                TrainerUnit.qualification_id == qualification_id,
            )
        ).scalars()
    )
    fresh = [uid for uid in dict.fromkeys(unit_ids) if uid not in existing]
    if fresh:
        session.execute(
            TrainerUnit.__table__.insert(),
            [
                {"trainer_id": trainer_pk, "qualification_id": qualification_id, "unit_id": uid}
                for uid in fresh
            ],
        )
    rebuild_trainer_qualifications(session, [trainer_pk])
    session.flush()
    record_activity(
        session,
        user=user,
        action="CREATE",
        page_or_function=PAGE,
        detail=f"Approved trainer {trainer.trainer_id} for {len(fresh)} unit(s).",
        record_reference=str(trainer_pk),
        result="COMPLETED",
    )
    return get_trainer(session, trainer_pk)


def remove_unit_link(session: Session, trainer_pk: int, link_id: int, *, user: User) -> dict:
    row = session.get(TrainerUnit, link_id)
    if row is None or row.trainer_id != trainer_pk:
        raise TrainerError("That unit was not found for this trainer.")
    session.delete(row)
    session.flush()
    rebuild_trainer_qualifications(session, [trainer_pk])
    record_activity(
        session,
        user=user,
        action="DELETE",
        page_or_function=PAGE,
        detail=f"Removed a unit from trainer {trainer_pk}.",
        record_reference=str(link_id),
        result="COMPLETED",
    )
    return get_trainer(session, trainer_pk)


# ---------------------------------------------------------------------------
# Derived data (2.3)
# ---------------------------------------------------------------------------


def rebuild_trainer_qualifications(session: Session, trainer_pks: list[int]) -> int:
    """Make `trainer_qualifications` match the qualifications in the units.

    Kept rather than dropped: TRN-01 filters trainers by qualification, and that
    must stay an indexed join rather than a scan through the units table. It is
    derived data, never entered by hand — so it is rebuilt here, in bulk, for
    the affected trainers only.
    """
    if not trainer_pks:
        return 0
    pks = list(dict.fromkeys(trainer_pks))

    wanted = {
        (row.trainer_id, row.qualification_id)
        for row in session.execute(
            select(TrainerUnit.trainer_id, TrainerUnit.qualification_id)
            .where(
                TrainerUnit.trainer_id.in_(pks),
                TrainerUnit.qualification_id.is_not(None),
            )
            .distinct()
        ).all()
    }
    held = {
        (row.trainer_id, row.qualification_id): row.id
        for row in session.execute(
            select(TrainerQualification.id, TrainerQualification.trainer_id, TrainerQualification.qualification_id)
            .where(TrainerQualification.trainer_id.in_(pks))
        ).all()
    }

    stale = [link_id for key, link_id in held.items() if key not in wanted]
    if stale:
        session.execute(delete(TrainerQualification).where(TrainerQualification.id.in_(stale)))
    missing = [key for key in wanted if key not in held]
    if missing:
        session.execute(
            TrainerQualification.__table__.insert(),
            [{"trainer_id": t, "qualification_id": q} for t, q in missing],
        )
    session.flush()
    return len(missing)


# ---------------------------------------------------------------------------
# Soft delete (DATA-04)
# ---------------------------------------------------------------------------

#: The recovery window, matching Student Data.
RECYCLE_PERIOD_DAYS = 14


def delete_trainer(
    session: Session, trainer_pk: int, *, reason_code_id: int, reason_note: str | None, user: User
) -> None:
    """Soft delete. A trainer stays recoverable and stays resolvable from the
    historical timetable rows that reference them (DATA-04)."""
    import datetime as dt

    trainer = session.get(Trainer, trainer_pk)
    if trainer is None or trainer.is_deleted:
        raise TrainerError("That trainer was not found.")
    now = dt.datetime.now(dt.timezone.utc)
    trainer.is_deleted = True
    trainer.deleted_at = now
    trainer.deleted_by_user_id = user.id
    trainer.delete_reason_id = reason_code_id
    trainer.delete_reason_detail = reason_note
    trainer.recovery_deadline = (now + dt.timedelta(days=RECYCLE_PERIOD_DAYS)).date()
    session.flush()
    record_activity(
        session,
        user=user,
        action="DELETE",
        page_or_function=PAGE,
        detail=f"Deleted trainer {trainer.trainer_id}.",
        record_reference=trainer.trainer_id,
        result="COMPLETED",
    )


def restore_trainer(session: Session, trainer_pk: int, *, user: User) -> dict:
    trainer = session.get(Trainer, trainer_pk)
    if trainer is None or not trainer.is_deleted:
        raise TrainerError("That deleted trainer was not found.")
    trainer.is_deleted = False
    trainer.deleted_at = None
    trainer.deleted_by_user_id = None
    trainer.delete_reason_id = None
    trainer.delete_reason_detail = None
    trainer.recovery_deadline = None
    session.flush()
    record_activity(
        session,
        user=user,
        action="RESTORE",
        page_or_function=PAGE,
        detail=f"Restored trainer {trainer.trainer_id}.",
        record_reference=trainer.trainer_id,
        result="COMPLETED",
    )
    return get_trainer(session, trainer.id)


# ---------------------------------------------------------------------------
# Clearing the trainer database — Super Admin only
# ---------------------------------------------------------------------------

#: Written on the allocation sessions that lose their link, so the name is kept
#: and the value returns to the shared queue for a decision.
_ALLOCATION_SOURCE = "ALLOCATION_IMPORT"


def clear_preview(session: Session) -> dict:
    """What clearing would remove, counted before anything is deleted."""

    def count(model) -> int:
        return session.execute(select(func.count()).select_from(model)).scalar_one()

    sessions_linked = session.execute(
        select(func.count())
        .select_from(AllocationSession)
        .where(AllocationSession.trainer_id.is_not(None))
    ).scalar_one()
    names = session.execute(
        select(func.count(func.distinct(AllocationSession.trainer_text))).where(
            AllocationSession.trainer_id.is_not(None)
        )
    ).scalar_one()

    return {
        "trainers": count(Trainer),
        "locations": count(TrainerAvailability),
        "unit_links": count(TrainerUnit),
        "qualification_links": count(TrainerQualification),
        "allocation_sessions_unlinked": sessions_linked,
        "trainer_suggestions_raised": names,
    }


def clear_trainer_records(session: Session, user: User) -> dict:
    """Delete every trainer record, keeping the timetable readable.

    `allocation_session.trainer_id` is `ON DELETE RESTRICT`, so the links are
    released first. Every one of those rows already carries the name in
    `trainer_text`, so **no name is lost** — the session simply reads as an
    unresolved trainer, and a suggestion is raised for it so the value is not
    quietly forgotten. Resolving that suggestion re-links the sessions.

    Availability, unit links and qualification links all cascade with the
    trainer. Numbering restarts at TI_001, because the table is empty.
    """
    from app.services.reference_suggestions import raise_reference_suggestion

    removed = clear_preview(session)

    # One row per distinct name - the key a TRAINER value carries, matching what
    # the allocation import raises. Not per college since 15 September 2026: a
    # trainer is not held per college, and one name was split into an entry per
    # college that each resolved the same sessions.
    groups = session.execute(
        select(AllocationSession.trainer_text.label("name"), func.count().label("sessions"))
        .where(AllocationSession.trainer_id.is_not(None))
        .group_by(AllocationSession.trainer_text)
    ).all()

    session.execute(
        update(AllocationSession)
        .where(AllocationSession.trainer_id.is_not(None))
        .values(trainer_id=None)
    )

    raised = 0
    for group in groups:
        if not group.name:
            continue
        raise_reference_suggestion(
            session,
            entity_type="TRAINER",
            raw_value=group.name,
            context={},
            source=_ALLOCATION_SOURCE,
        )
        raised += 1
    session.flush()

    session.execute(delete(Trainer))
    session.flush()

    record_activity(
        session,
        user=user,
        action="DELETE",
        page_or_function=PAGE,
        detail=(
            f"Cleared the trainer database: {removed['trainers']} trainer(s), "
            f"{removed['locations']} location(s), {removed['unit_links']} unit link(s) and "
            f"{removed['qualification_links']} qualification link(s). "
            f"{removed['allocation_sessions_unlinked']} allocation session(s) kept their "
            f"trainer name and returned to the suggestion queue as {raised} unresolved "
            "value(s). Trainer numbering restarts at TI_001."
        ),
        record_reference="trainers:clear",
        result="COMPLETED",
    )
    removed["trainer_suggestions_raised"] = raised
    return removed
