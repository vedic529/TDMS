"""Where the approved source workbooks live.

One resolver for every importer. Before this, four scripts each hardcoded a
path into a personal `Downloads` folder, so moving the data meant editing four
files and missing one.

Resolution order:

1. ``TDMS_SOURCE_DATA_DIR`` when set — an absolute path, for a shared drive or
   for trying a revised workbook without disturbing the approved one.
2. ``<repo>/data/source`` otherwise.

The folder is git-ignored. It holds real student, staff and college records and
the repository is public, so the files are never committed.
"""

from __future__ import annotations

import os
from pathlib import Path

#: `<repo>/apps/api/scripts/_source_data.py` -> `<repo>`
REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_SOURCE_DIR = REPO_ROOT / "data" / "source"

LOCATION_FILE_NAME = "Location Data.xlsx"
QUALIFICATION_FILE_NAME = "Qualification Data.xlsx"
TRAINER_FILE_NAME = "Trainer Data - BSB.xlsx"
ROLLING_FILE_NAME = "Rolling TT Data.xlsx"


def source_dir() -> Path:
    """The directory holding the approved workbooks."""
    override = os.environ.get("TDMS_SOURCE_DATA_DIR", "").strip()
    return Path(override).expanduser() if override else DEFAULT_SOURCE_DIR


def source_file(name: str) -> Path:
    """Path to one workbook. Existence is checked by `require`, not here."""
    return source_dir() / name


def require(*names: str) -> None:
    """Fails before any work starts when a workbook is missing.

    Reporting every missing file at once, by name and with the directory that
    was searched, beats discovering the second one after the first has already
    been read.
    """
    directory = source_dir()
    missing = [name for name in names if not (directory / name).is_file()]
    if not missing:
        return

    listing = "\n".join(f"  - {name}" for name in missing)
    hint = (
        "Set TDMS_SOURCE_DATA_DIR to point somewhere else, or copy the files in. "
        "See data/source/README.md."
    )
    raise SystemExit(
        f"Source data not found in {directory}\n\nMissing:\n{listing}\n\n{hint}"
    )


# Convenience handles. These are evaluated on import, so a script that sets
# TDMS_SOURCE_DATA_DIR must do so before importing this module — which is why
# it is read from the environment rather than parsed from an argument.
LOCATION_FILE = source_file(LOCATION_FILE_NAME)
QUALIFICATION_FILE = source_file(QUALIFICATION_FILE_NAME)
TRAINER_FILE = source_file(TRAINER_FILE_NAME)
ROLLING_FILE = source_file(ROLLING_FILE_NAME)
