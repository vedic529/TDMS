"""The Campus Address Dictionary (approved 16 September 2026).

A full address is identified by the combination of college and campus. One
campus name can be a different building for each college - Haymarket is 8 Quay
St for REACH and NPA but 841 George St for AIBT and BIC - so the address is kept
on the approved combination (`college_campuses.address`), not on the campus.

Several combinations can share one address: 132-146 Elizabeth Street is Hobart
for REACH, AVTA, AIBT and HJ.

Every address saved here is also recorded as a spelling of its campus
(`campus_source_addresses`), so a file that writes it resolves to that campus. An
address already recorded for a *different* campus is refused: saving it would
make one address name two sites.

The dictionary was seeded from the project owner's sheet by
`scripts/apply_campus_address_dictionary.py`, and is maintained from the College
Locations tab (Address Dictionary) after that.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.college import Campus, CampusSourceAddress, College, CollegeCampus
from app.models.user import User
from app.services.activity import record_activity
from app.services.reference_data import NotFound, ReferenceDataError

PAGE = "College and Course Reference Data - Campus Address Dictionary"


class AddressConflict(ReferenceDataError):
    status_code = 409


def _plain(value: object) -> str:
    return " ".join(str(value or "").split())


def _normalised(column):
    return func.upper(func.btrim(func.regexp_replace(column, r"\s+", " ", "g")))


def _read(link: CollegeCampus, college: College, campus: Campus) -> dict:
    return {
        "college_id": college.id,
        "college_short_name": college.college_short_name,
        "campus_id": campus.id,
        "campus_code": campus.campus_code,
        "campus_name": campus.campus_name,
        "state": campus.state,
        "address": link.address,
        "is_active": link.is_active,
    }


def list_entries(session: Session) -> list[dict]:
    """Every approved combination with its address, in one query.

    A combination with no address is listed too: it is a gap to fill, and
    hiding it would make the dictionary look complete when it is not.
    """
    rows = session.execute(
        select(CollegeCampus, College, Campus)
        .join(College, College.id == CollegeCampus.college_id)
        .join(Campus, Campus.id == CollegeCampus.campus_id)
        .order_by(Campus.state, Campus.campus_name, College.college_short_name)
    ).all()
    return [_read(link, college, campus) for link, college, campus in rows]


def address_for(session: Session, college_id: int, campus_id: int) -> str | None:
    """The dictionary address for a college at a campus, if one is recorded."""
    link = session.get(CollegeCampus, (college_id, campus_id))
    return link.address if link is not None else None


def _record_spelling(session: Session, campus: Campus, address: str) -> None:
    """Make the address resolve to its campus, refusing one that names another."""
    existing = session.execute(
        select(CampusSourceAddress).where(
            _normalised(CampusSourceAddress.source_address) == address.upper()
        )
    ).scalars().first()
    if existing is None:
        session.add(CampusSourceAddress(campus_id=campus.id, source_address=address))
        return
    if existing.campus_id != campus.id:
        other = session.get(Campus, existing.campus_id)
        raise AddressConflict(
            f"“{address}” is recorded as an address of {other.campus_name if other else 'another campus'}, "
            f"not {campus.campus_name}. One address cannot name two campuses."
        )


def save_entry(
    session: Session,
    user: User,
    values: dict,
    *,
    creating: bool,
) -> dict:
    """Add a combination's address, or change it.

    Adding a combination that is not yet approved approves it: choosing a
    college and a campus and giving the address is the approval.
    """
    address = _plain(values.get("address"))
    if not address:
        raise ReferenceDataError("A full address is required.")
    college = session.get(College, int(values.get("college_id") or 0))
    if college is None:
        raise NotFound("That college was not found.")
    campus = session.get(Campus, int(values.get("campus_id") or 0))
    if campus is None:
        raise NotFound("That campus was not found.")

    link = session.get(CollegeCampus, (college.id, campus.id))
    previous = link.address if link is not None else None
    if creating:
        if link is not None and link.address:
            raise AddressConflict(
                f"{college.college_short_name} / {campus.campus_name} is already in the dictionary. "
                "Edit its address instead."
            )
        if link is None:
            link = CollegeCampus(college_id=college.id, campus_id=campus.id, is_active=True)
            session.add(link)
    elif link is None:
        raise NotFound(
            f"{college.college_short_name} / {campus.campus_name} is not in the dictionary."
        )

    _record_spelling(session, campus, address)
    link.address = address
    session.flush()

    record_activity(
        session,
        user=user,
        action="CREATE" if previous is None else "UPDATE",
        page_or_function=PAGE,
        detail=(
            f"{college.college_short_name} / {campus.campus_name}: "
            + (f"{previous} -> {address}" if previous else address)
        ),
        record_reference=f"{college.college_short_name}/{campus.campus_code}",
        result="COMPLETED",
    )
    return _read(link, college, campus)
