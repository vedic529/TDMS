"""Format profiles — the only thing that varies per training package."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.allocation import AllocationPackageProfile


ALLOCATION_COLUMNS = (
    "College",
    "Campus Location",
    "Qualification Id",
    "Qualification Name",
    "Duration in Weeks",
    "Group",
    "Classroom Size",
    "Units of Competency ID",
    "Units of Competency Title",
    "UoC Type",
    "Mode of Delivery",
    "Unit of Competency Start Date",
    "Unit of Competency End Date",
    "Theory Class Days and Times",
    "Theory Classroom Name",
    "Theory Classroom Capacity",
    "Theory Trainer",
    "Practical Classroom Name",
    "Practical Class Capacity",
    "Practical Class Days and Times",
    "Practical Trainers",
    "MSCRIS Class Name",
    "MSCRIS Days and Times",
    "MSCRIS Trainers",
    "Remarks",
)

REQUIRED_COLUMNS = ALLOCATION_COLUMNS[:13]
OPTIONAL_COLUMNS = ALLOCATION_COLUMNS[13:]


@dataclass(frozen=True)
class PackageProfile:
    training_package: str
    columns: tuple[str, ...]
    required: tuple[str, ...]
    has_practical: bool
    has_group: bool


PROFILES: dict[str, PackageProfile] = {
    "BSB": PackageProfile(
        training_package="BSB",
        columns=ALLOCATION_COLUMNS,
        required=tuple(name for name in REQUIRED_COLUMNS if name not in {"Group", "Classroom Size"}),
        has_practical=False,
        has_group=False,
    )
}


def profile_for(training_package: str) -> PackageProfile | None:
    return PROFILES.get(training_package.upper())


def list_packages(session: Session) -> list[dict]:
    rows = session.execute(select(AllocationPackageProfile)).scalars().all()
    by_code = {row.training_package: row.enabled for row in rows}
    from app.db.enums import TRAINING_PACKAGE_VALUES

    return [
        {
            "training_package": code,
            "enabled": bool(by_code.get(code, False)) and code in PROFILES,
            "has_profile": code in PROFILES,
        }
        for code in TRAINING_PACKAGE_VALUES
    ]
