"""The City Dictionary (approved 15 September 2026).

A separate list of approved cities, each holding the campuses located in it.
`campuses.city` references `cities.city_name`, so a campus can only name a city
the dictionary holds, and renaming a city carries through to its campuses.

Nothing is seeded. A city is added by a person who knows where a campus is; a
city read off an address would be a guess indistinguishable from data.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.college import Campus, City
from app.models.trainer import Trainer
from app.models.user import User
from app.services.activity import record_activity
from app.services.reference_data import NotFound, ReferenceDataError

PAGE = "College and Course Reference Data - City Dictionary"


class CityConflict(ReferenceDataError):
    status_code = 409


def _plain(value: object) -> str:
    return " ".join(str(value or "").split())


def _normalised(column):
    return func.upper(func.btrim(func.regexp_replace(column, r"\s+", " ", "g")))


def _campus_read(campus: Campus) -> dict:
    return {
        "id": campus.id,
        "campus_code": campus.campus_code,
        "campus_name": campus.campus_name,
        "state": campus.state,
    }


def _city_read(city: City, campuses: list[Campus]) -> dict:
    return {
        "id": city.id,
        "city_name": city.city_name,
        "state": city.state,
        "is_active": city.is_active,
        "campuses": [_campus_read(campus) for campus in campuses],
    }


def list_cities(session: Session) -> list[dict]:
    """Every city with its campuses - two queries, whatever the size."""
    cities = session.execute(select(City).order_by(City.state, City.city_name)).scalars().all()
    by_city: dict[str, list[Campus]] = defaultdict(list)
    for campus in session.execute(
        select(Campus).where(Campus.city.is_not(None)).order_by(Campus.campus_name)
    ).scalars():
        by_city[campus.city].append(campus)
    return [_city_read(city, by_city.get(city.city_name, [])) for city in cities]


def city_named(session: Session, name: object) -> City | None:
    """The dictionary entry for a spelling, ignoring case and spacing."""
    key = _plain(name).upper()
    if not key:
        return None
    return session.execute(select(City).where(_normalised(City.city_name) == key)).scalars().first()


def _validated(
    session: Session, values: dict, *, current_id: int | None = None
) -> tuple[str, str, list[Campus]]:
    name = _plain(values.get("city_name"))
    state = _plain(values.get("state")).upper()
    if not name:
        raise ReferenceDataError("A city name is required.")
    if not state:
        raise ReferenceDataError("A state is required.")

    clash = city_named(session, name)
    if clash is not None and clash.id != current_id:
        raise CityConflict(f"{clash.city_name} is already in the City Dictionary.")

    ids = list(dict.fromkeys(int(value) for value in values.get("campus_ids") or []))
    campuses = (
        list(session.execute(select(Campus).where(Campus.id.in_(ids))).scalars()) if ids else []
    )
    if len(campuses) != len(ids):
        raise NotFound("A chosen campus was not found.")
    # A campus's state is recorded already. A city in another state cannot hold
    # it, and saying so here is cheaper than a wrong dictionary.
    elsewhere = [campus.campus_name for campus in campuses if _plain(campus.state).upper() != state]
    if elsewhere:
        raise ReferenceDataError(
            f"{', '.join(elsewhere)} {'is' if len(elsewhere) == 1 else 'are'} not in {state}. "
            "A campus can only belong to a city in its own state."
        )
    return name, state, campuses


def create_city(session: Session, user: User, values: dict) -> dict:
    name, state, campuses = _validated(session, values)
    city = City(city_name=name, state=state, is_active=True)
    session.add(city)
    session.flush()
    if campuses:
        session.execute(
            update(Campus)
            .where(Campus.id.in_([campus.id for campus in campuses]))
            .values(city=name)
            .execution_options(synchronize_session=False)
        )
    session.flush()
    session.expire_all()
    record_activity(
        session,
        user=user,
        action="CREATE",
        page_or_function=PAGE,
        detail=f"Added {name} ({state}) with {len(campuses)} campus(es).",
        record_reference=str(city.id),
        result="COMPLETED",
    )
    return _city_read(city, sorted(campuses, key=lambda campus: campus.campus_name))


def update_city(session: Session, user: User, city_id: int, values: dict) -> dict:
    city = session.get(City, city_id)
    if city is None:
        raise NotFound("That city was not found.")
    previous = city.city_name
    name, state, campuses = _validated(session, values, current_id=city.id)
    chosen = [campus.id for campus in campuses]

    city.city_name = name
    city.state = state
    # The rename reaches the campuses through ON UPDATE CASCADE.
    session.flush()

    if previous != name:
        # A trainer's city is text a file supplied, not a reference, so the
        # cascade does not reach it. Rewritten here, or every trainer based in the
        # renamed city would turn into an unmatched value.
        session.execute(
            update(Trainer)
            .where(_normalised(Trainer.city) == previous.upper())
            .values(city=name)
            .execution_options(synchronize_session=False)
        )

    # Campuses taken out of the city lose it; the chosen ones gain it.
    released = update(Campus).where(Campus.city == name)
    if chosen:
        released = released.where(Campus.id.not_in(chosen))
    session.execute(released.values(city=None).execution_options(synchronize_session=False))
    if chosen:
        session.execute(
            update(Campus)
            .where(Campus.id.in_(chosen))
            .values(city=name)
            .execution_options(synchronize_session=False)
        )
    session.flush()
    session.expire_all()

    record_activity(
        session,
        user=user,
        action="UPDATE",
        page_or_function=PAGE,
        detail=(
            f"Updated {previous}"
            + (f" (renamed {name})" if previous != name else "")
            + f": {len(chosen)} campus(es)."
        ),
        record_reference=str(city_id),
        result="COMPLETED",
    )
    refreshed = session.get(City, city_id)
    return _city_read(refreshed, sorted(campuses, key=lambda campus: campus.campus_name))
