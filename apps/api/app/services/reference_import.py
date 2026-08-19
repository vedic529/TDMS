"""Full College and Course Reference Data import from the approved workbooks.

Two files, two responsibilities (SRS §4):

* **Location Data** — RTO, Course Code, VET Code, Course Name, status, duration,
  cost, and the course/location relationship.
* **Qualification Data** — qualification title, unit membership, unit titles and
  Source URL.

Neither file defines teaching order. Delivery sequence comes only from an
approved rolling timetable, which is why `qualification_units` is written for a
qualification **only** when such a source exists for it.

Three habits run through this module:

* **Nothing is invented.** Where a source is silent the field is left empty and
  the gap is reported. The two exceptions — a campus code and a college's full
  name — are generated deterministically from the source text, flagged
  provisional in the report, and never presented as approved values.
* **Conflicts are reported, not resolved silently.** Where the sources disagree
  with each other or with an approved constraint, the row is named with its file,
  sheet, row number and the exact reason.
* **Idempotent.** Every entity is looked up before it is created, so a second run
  creates nothing.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.college import Campus, College, CollegeCampus
from app.models.course import CourseOffering, OfferingDurationOption
from app.models.qualification import Qualification, QualificationUnit, Unit
from app.services.reference_data import status_for_supplied_course

# ---------------------------------------------------------------------------
# Text repair
# ---------------------------------------------------------------------------

#: Australian state and territory abbreviations, plus the full names the source
#: sometimes uses instead.
_STATES = {
    "NSW": "NSW", "VIC": "VIC", "QLD": "QLD", "SA": "SA", "WA": "WA",
    "TAS": "TAS", "NT": "NT", "ACT": "ACT",
    "NEW SOUTH WALES": "NSW", "VICTORIA": "VIC", "QUEENSLAND": "QLD",
    "SOUTH AUSTRALIA": "SA", "WESTERN AUSTRALIA": "WA", "TASMANIA": "TAS",
    "NORTHERN TERRITORY": "NT", "AUSTRALIAN CAPITAL TERRITORY": "ACT",
}

#: Typographic characters the workbooks use inconsistently, mapped to their
#: plain equivalents.
#:
#: The same unit title arrives both as "children's" (U+2019) and "children's"
#: (U+0027). They are the same title; without this they become two titles, and
#: `units.unit_code` is unique, so one silently overwrites the other. Non-breaking
#: spaces and en dashes in addresses cause the same problem for campuses.
_PUNCTUATION = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
    " ": " ", " ": " ", " ": " ",
    "�": "'",  # a replacement character left by an earlier conversion
}

_PUNCTUATION_RE = re.compile("|".join(map(re.escape, _PUNCTUATION)))


def repair_text(value: object) -> str:
    """Normalise a source cell so equal values compare equal.

    Only typography is touched — quotes, dashes and spaces. No word is changed,
    nothing is capitalised, and the workbook itself is never modified: this
    repairs the value on the way in, so the same title spelled two ways does not
    become two records.
    """
    if value is None:
        return ""
    text = _PUNCTUATION_RE.sub(lambda m: _PUNCTUATION[m.group()], str(value))
    return re.sub(r"\s+", " ", text).strip()


def _cell(row: dict, key: str) -> str:
    return repair_text(row.get(key))


#: Values that mean "no VET Code has been issued" (ELICOS).
_NO_CODE = {"", "NA", "N/A", "N.A.", "NONE", "NIL", "-"}


def qualification_key(vet_code: str, course_name: str) -> tuple[str | None, str]:
    """Identity of a qualification: its code, or its title when it has none.

    ELICOS courses arrive with `NA`, and four different course names share that
    value. Keying on the raw cell would collapse them into one qualification.
    """
    code = vet_code.strip().upper()
    if code in _NO_CODE:
        return None, course_name.strip().upper()
    return code, ""


# ---------------------------------------------------------------------------
# Campus derivation
# ---------------------------------------------------------------------------


#: Campus details confirmed by the project owner where the source address does
#: not carry them.
#:
#: The Location Data address "Unit 2, Level 1, 18 Mount Gravatt-Capalaba Road,
#: Upper Mt Gravatt" has no state or postcode, and `campuses.state` is NOT NULL.
#: The importer refuses to infer a state from a suburb name — that is geography,
#: not data — so the whole address was rejected, taking 63 AIBT rows, 61 course
#: codes and 51 qualifications with it.
#:
#: This is not a guess and not a default: it is an explicit, reviewable statement
#: of what the project owner confirmed, keyed on the exact source text. An
#: address that is not listed here and carries no state is still rejected.
APPROVED_CAMPUS_DETAILS: dict[str, dict[str, str]] = {
    "unit 2, level 1, 18 mount gravatt-capalaba road, upper mt gravatt": {
        "code": "BRISBANE",
        "name": "Brisbane",
        "location": (
            "Unit 2, Level 1, 18 Mount Gravatt-Capalaba Road, "
            "Upper Mount Gravatt QLD 4122"
        ),
        "state": "QLD",
    },
}


@dataclass(frozen=True)
class DerivedCampus:
    """A campus read out of a free-text address."""

    code: str
    name: str
    location: str
    state: str


def derive_campus(address: str) -> DerivedCampus:
    """Read a campus out of the one free-text address the source provides.

    `campuses` needs a code, a name, an address and a state. The workbook has
    only the address, so the other three are derived from it deterministically —
    the same address always produces the same campus, which is what makes the
    import idempotent and lets a re-run reuse rather than duplicate.

    The generated **code is provisional** and reported as such. The address is
    stored verbatim (after encoding repair), so nothing is lost if the codes are
    later replaced with approved ones.
    """
    cleaned = repair_text(address)

    approved = APPROVED_CAMPUS_DETAILS.get(cleaned.lower())
    if approved is not None:
        return DerivedCampus(
            code=approved["code"],
            name=approved["name"],
            location=approved["location"],
            state=approved["state"],
        )

    upper = cleaned.upper()

    state = ""
    for token, abbreviation in _STATES.items():
        if re.search(rf"(?<![A-Z]){re.escape(token)}(?![A-Z])", upper):
            state = abbreviation
            break

    # The suburb is what follows the last street-type word or street number.
    #
    # Taking "the last two words before the state" looked right and was wrong:
    # "125 Main St BLACKTOWN NSW" yielded "St Blacktown". Splitting at the street
    # type handles both a one-word suburb (Blacktown, Haymarket) and a longer one
    # (Upper Mt Gravatt, South Melbourne) without special-casing either.
    _STREET_WORD = re.compile(
        r"^(st|street|rd|road|ave|avenue|dr|drive|pde|parade|hwy|highway|ln|lane|"
        r"cres|crescent|ct|court|pl|place|tce|terrace|blvd|boulevard|"
        r"level|lvl|unit|suite|shop|floor|tower)$",
        re.I,
    )
    _NUMBERISH = re.compile(r"^[\d]+[a-z]?$|^[\d/\-]+$", re.I)

    name = ""
    if state:
        for token, abbreviation in _STATES.items():
            if abbreviation != state:
                continue
            match = re.search(
                rf"(.+?)[,\s]+{re.escape(token)}(?![A-Za-z])", cleaned, re.I
            )
            if not match:
                continue
            words = [w for w in re.split(r"[\s,]+", match.group(1)) if w]
            last_marker = -1
            for index, word in enumerate(words):
                if _STREET_WORD.match(word) or _NUMBERISH.match(word):
                    last_marker = index
            suburb = words[last_marker + 1:]
            if suburb:
                name = " ".join(suburb).title()
                break
    if not name:
        name = cleaned[:60]

    code = re.sub(r"[^A-Z0-9]+", "", name.upper())[:20] or "CAMPUS"
    return DerivedCampus(code=code, name=name, location=cleaned, state=state or "")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class Issue:
    file: str
    sheet: str
    row: int | str
    identifier: str
    reason: str

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.file} / {self.sheet} / row {self.row} / {self.identifier}: {self.reason}"


@dataclass
class EntityReport:
    source: int = 0
    reuse: int = 0
    create: int = 0
    update: int = 0
    conflicts: list[Issue] = field(default_factory=list)
    rejected: list[Issue] = field(default_factory=list)
    ambiguous: list[Issue] = field(default_factory=list)
    pending: list[Issue] = field(default_factory=list)


@dataclass
class ImportReport:
    colleges: EntityReport = field(default_factory=EntityReport)
    campuses: EntityReport = field(default_factory=EntityReport)
    college_campuses: EntityReport = field(default_factory=EntityReport)
    qualifications: EntityReport = field(default_factory=EntityReport)
    units: EntityReport = field(default_factory=EntityReport)
    qualification_units: EntityReport = field(default_factory=EntityReport)
    courses: EntityReport = field(default_factory=EntityReport)
    provisional: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def sections(self):
        return [
            ("COLLEGES", self.colleges),
            ("CAMPUSES", self.campuses),
            ("COLLEGE-CAMPUS", self.college_campuses),
            ("QUALIFICATIONS", self.qualifications),
            ("UNITS", self.units),
            ("QUALIFICATION-UNIT", self.qualification_units),
            ("COURSES", self.courses),
        ]


LOCATION_FILE = "Location Data (1).xlsx"
LOCATION_SHEET = "Course Location Export"
QUALIFICATION_FILE = "Qualification Data.xlsx"
QUALIFICATION_SHEET = "Qualification Data"


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------


class ReferenceImporter:
    """Imports the complete valid reference dataset. Caller owns the transaction."""

    def __init__(
        self,
        session: Session,
        *,
        sequence_sources: dict[str, Sequence[str]] | None = None,
    ) -> None:
        self.session = session
        self.report = ImportReport()
        #: Qualification code -> approved delivery order, from a rolling
        #: timetable. A qualification absent from here gets its membership left
        #: pending rather than an invented 1..N.
        self.sequence_sources = {k.upper(): v for k, v in (sequence_sources or {}).items()}

    # -- helpers -----------------------------------------------------------

    def _get_or_create(self, model, report: EntityReport, defaults: dict, **lookup):
        existing = self.session.execute(select(model).filter_by(**lookup)).scalar_one_or_none()
        if existing is not None:
            report.reuse += 1
            return existing, False
        row = model(**lookup, **defaults)
        self.session.add(row)
        self.session.flush()
        report.create += 1
        return row, True

    # -- entry point -------------------------------------------------------

    def run(self, location_rows: Sequence[dict], qualification_rows: Sequence[dict]) -> ImportReport:
        colleges = self._import_colleges(location_rows)
        campuses = self._import_campuses(location_rows)
        self._import_college_campuses(location_rows, colleges, campuses)
        qualifications = self._import_qualifications(location_rows, qualification_rows)
        units = self._import_units(qualification_rows)
        self._import_qualification_units(qualification_rows, qualifications, units)
        self._import_courses(location_rows, colleges, campuses, qualifications)
        return self.report

    # -- colleges ----------------------------------------------------------

    def _import_colleges(self, rows: Sequence[dict]) -> dict[str, College]:
        report = self.report.colleges
        names = sorted({_cell(r, "RTO") for r in rows} - {""})
        report.source = len(names)

        out: dict[str, College] = {}
        for short_name in names:
            college, created = self._get_or_create(
                College,
                report,
                # No supplied file contains a college's full legal name. The
                # short name is stored so the NOT NULL column holds something
                # true, rather than a plausible invention.
                {"college_full_name": short_name, "is_active": True},
                college_short_name=short_name,
            )
            out[short_name] = college
            if created:
                self.report.provisional.append(
                    f"colleges.college_full_name for {short_name!r} is the short name: "
                    "no supplied file contains the full legal name."
                )
        return out

    # -- campuses ----------------------------------------------------------

    def _import_campuses(self, rows: Sequence[dict]) -> dict[str, Campus]:
        report = self.report.campuses
        addresses = sorted({_cell(r, "Location") for r in rows} - {""})
        report.source = len(addresses)

        # Two addresses deriving the same code are the same site written two
        # ways. They are reported as ambiguous and share one campus rather than
        # being silently split or silently merged without saying so.
        by_code: dict[str, list[str]] = defaultdict(list)
        for address in addresses:
            by_code[derive_campus(address).code].append(address)

        out: dict[str, Campus] = {}
        for code, variants in sorted(by_code.items()):
            derived = derive_campus(variants[0])
            if len(variants) > 1:
                report.ambiguous.append(
                    Issue(
                        LOCATION_FILE, LOCATION_SHEET, "multiple", code,
                        "one campus derived from several address spellings: "
                        + " | ".join(variants)
                        + ". Confirm these are the same physical site.",
                    )
                )
            if not derived.state:
                report.rejected.append(
                    Issue(
                        LOCATION_FILE, LOCATION_SHEET, "multiple", derived.location,
                        "no Australian state could be read from the address; "
                        "campuses.state is NOT NULL and will not be guessed.",
                    )
                )
                continue

            campus, created = self._get_or_create(
                Campus,
                report,
                {
                    "campus_name": derived.name,
                    "campus_location": derived.location,
                    "state": derived.state,
                    "is_active": True,
                },
                campus_code=derived.code,
            )
            if created:
                self.report.provisional.append(
                    f"campuses.campus_code {derived.code!r} was derived from the address: "
                    "no supplied file contains campus codes."
                )
            for address in variants:
                out[address] = campus
        return out

    # -- college/campus ----------------------------------------------------

    def _import_college_campuses(self, rows, colleges, campuses) -> None:
        report = self.report.college_campuses
        pairs = sorted(
            {(_cell(r, "RTO"), _cell(r, "Location")) for r in rows} - {("", "")}
        )
        report.source = len(pairs)
        for rto, address in pairs:
            college, campus = colleges.get(rto), campuses.get(address)
            if college is None or campus is None:
                report.rejected.append(
                    Issue(LOCATION_FILE, LOCATION_SHEET, "multiple", f"{rto} / {address}",
                          "college or campus could not be resolved.")
                )
                continue
            self._get_or_create(
                CollegeCampus, report, {"is_active": True},
                college_id=college.id, campus_id=campus.id,
            )

    # -- qualifications ----------------------------------------------------

    def _import_qualifications(self, location_rows, qualification_rows):
        report = self.report.qualifications

        # Qualification Data is authoritative for title and Source URL; Location
        # Data supplies the attributes that describe the course offering side.
        titles: dict[str, Counter] = defaultdict(Counter)
        urls: dict[str, str] = {}
        for index, r in enumerate(qualification_rows, start=2):
            code = _cell(r, "Qualification Code").upper()
            if not code:
                continue
            titles[code][_cell(r, "Qualification Title")] += 1
            urls.setdefault(code, _cell(r, "Source URL"))

        for code, counter in titles.items():
            if len(counter) > 1:
                chosen = self._preferred_title(counter)
                report.conflicts.append(
                    Issue(
                        QUALIFICATION_FILE, QUALIFICATION_SHEET, "multiple", code,
                        f"{len(counter)} different titles in the source; stored {chosen!r}. "
                        "Others: " + " | ".join(sorted(t for t in counter if t != chosen)),
                    )
                )

        attributes: dict[tuple[str | None, str], dict] = {}
        for r in location_rows:
            key = qualification_key(_cell(r, "VET Code"), _cell(r, "Course Name"))
            attributes.setdefault(key, {
                "title": _cell(r, "Course Name"),
                "course_level": _cell(r, "Course Level") or None,
                "field_of_education_broad": _cell(r, "Field Of Education Broard") or None,
                "field_of_education_narrow": _cell(r, "Field Of Education Narrow") or None,
                "course_sector": _cell(r, "Course Sector") or None,
            })
        for code in titles:
            attributes.setdefault((code, ""), {
                "title": self._preferred_title(titles[code]),
                "course_level": None,
                "field_of_education_broad": None,
                "field_of_education_narrow": None,
                "course_sector": None,
            })

        report.source = len(attributes)
        out: dict[tuple[str | None, str], Qualification] = {}

        for key, attrs in sorted(attributes.items(), key=lambda kv: (kv[0][0] or "", kv[0][1])):
            code, name_key = key
            title = self._preferred_title(titles[code]) if code in titles else attrs["title"]

            if code is None:
                # Code-less ELICOS: identity is the title, so a lookup by code
                # would collapse four different courses into one.
                existing = self.session.execute(
                    select(Qualification).where(
                        Qualification.qualification_code.is_(None),
                        Qualification.qualification_title == title,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    report.reuse += 1
                    out[key] = existing
                    continue
                qualification = Qualification(
                    qualification_code=None, qualification_title=title,
                    course_level=attrs["course_level"],
                    field_of_education_broad=attrs["field_of_education_broad"],
                    field_of_education_narrow=attrs["field_of_education_narrow"],
                    course_sector=attrs["course_sector"],
                    source_url=None, is_active=True,
                )
                self.session.add(qualification)
                self.session.flush()
                report.create += 1
                out[key] = qualification
                continue

            qualification, created = self._get_or_create(
                Qualification, report,
                {
                    "qualification_title": title,
                    "course_level": attrs["course_level"],
                    "field_of_education_broad": attrs["field_of_education_broad"],
                    "field_of_education_narrow": attrs["field_of_education_narrow"],
                    "course_sector": attrs["course_sector"],
                    "source_url": urls.get(code) or None,
                    "is_active": True,
                },
                qualification_code=code,
            )
            if not created:
                # Fill in anything an earlier, narrower import left empty.
                changed = False
                for attribute, value in (
                    ("source_url", urls.get(code) or None),
                    ("course_level", attrs["course_level"]),
                    ("field_of_education_broad", attrs["field_of_education_broad"]),
                    ("field_of_education_narrow", attrs["field_of_education_narrow"]),
                    ("course_sector", attrs["course_sector"]),
                ):
                    if value and getattr(qualification, attribute) is None:
                        setattr(qualification, attribute, value)
                        changed = True
                if changed:
                    report.update += 1
            out[key] = qualification
        return out

    @staticmethod
    def _preferred_title(counter: Counter) -> str:
        """Pick one title when the source gives several.

        Most frequent wins. A tie is broken toward the properly cased form —
        "Diploma of Community Services" over "Diploma Of Community Services" —
        because the difference in those cases is capitalisation, not meaning.
        """
        best = max(counter.items(), key=lambda kv: (kv[1], -sum(c.isupper() for c in kv[0])))
        return best[0]

    # -- units -------------------------------------------------------------

    def _import_units(self, qualification_rows) -> dict[str, Unit]:
        report = self.report.units
        titles: dict[str, Counter] = defaultdict(Counter)
        for r in qualification_rows:
            code = _cell(r, "Unit Code").upper()
            if code:
                titles[code][_cell(r, "Unit Title")] += 1

        report.source = len(titles)
        out: dict[str, Unit] = {}
        for code, counter in sorted(titles.items()):
            title = self._preferred_title(counter)
            if len(counter) > 1:
                report.conflicts.append(
                    Issue(
                        QUALIFICATION_FILE, QUALIFICATION_SHEET, "multiple", code,
                        f"{len(counter)} different titles; stored {title!r}. "
                        "Others: " + " | ".join(sorted(t for t in counter if t != title)),
                    )
                )
            unit, _ = self._get_or_create(
                Unit, report,
                # Units are shared across qualifications by design: one national
                # unit, many packages. No per-qualification copy is made.
                {"unit_title": title, "uoc_type": None, "is_active": True},
                unit_code=code,
            )
            out[code] = unit
        return out

    # -- qualification/unit membership -------------------------------------

    def _import_qualification_units(self, qualification_rows, qualifications, units) -> None:
        report = self.report.qualification_units

        membership: dict[str, set[str]] = defaultdict(set)
        per_rto: dict[str, dict[str, frozenset]] = defaultdict(dict)
        for r in qualification_rows:
            code = _cell(r, "Qualification Code").upper()
            unit_code = _cell(r, "Unit Code").upper()
            if code and unit_code:
                membership[code].add(unit_code)
        for r in qualification_rows:
            code = _cell(r, "Qualification Code").upper()
            rto = _cell(r, "RTO")
            unit_code = _cell(r, "Unit Code").upper()
            if code and rto and unit_code:
                per_rto[code].setdefault(rto, set()).add(unit_code)

        report.source = sum(len(v) for v in membership.values())

        for code, by_rto in per_rto.items():
            distinct = {frozenset(v) for v in by_rto.values()}
            if len(distinct) > 1:
                report.conflicts.append(
                    Issue(
                        QUALIFICATION_FILE, QUALIFICATION_SHEET, "multiple", code,
                        "RTOs list different unit sets for this national qualification "
                        + "; ".join(f"{rto}={len(u)} units" for rto, u in sorted(by_rto.items()))
                        + ". The approved schema holds one unit set per qualification, "
                        "so membership was not written.",
                    )
                )

        conflicted = {
            issue.identifier for issue in report.conflicts
        }

        for code, unit_codes in sorted(membership.items()):
            qualification = qualifications.get((code, ""))
            if qualification is None or code in conflicted:
                continue

            order = self.sequence_sources.get(code)
            if order is None:
                # Membership is stored; the delivery order is left NULL.
                #
                # Qualification Data says which units belong to the qualification.
                # Only an approved rolling timetable says what order they run in.
                # Writing 1..N here would be indistinguishable from an approved
                # teaching order and would be acted on as one.
                report.pending.append(
                    Issue(
                        QUALIFICATION_FILE, QUALIFICATION_SHEET, "multiple", code,
                        f"{len(unit_codes)} units imported. No approved timetable source "
                        "supplies a delivery order, so it is left pending rather than "
                        "invented.",
                    )
                )
                for unit_code in sorted(unit_codes):
                    unit = units.get(unit_code)
                    if unit is None:
                        continue
                    self._get_or_create(
                        QualificationUnit, report, {"delivery_order": None},
                        qualification_id=qualification.id, unit_id=unit.id,
                    )
                continue

            for position, unit_code in enumerate(order, start=1):
                unit = units.get(unit_code)
                if unit is None:
                    report.rejected.append(
                        Issue(QUALIFICATION_FILE, QUALIFICATION_SHEET, "multiple", unit_code,
                              f"unit in the {code} delivery order is not in Qualification Data.")
                    )
                    continue
                self._get_or_create(
                    QualificationUnit, report, {"delivery_order": position},
                    qualification_id=qualification.id, unit_id=unit.id,
                )

    # -- courses -----------------------------------------------------------

    def _import_courses(self, rows, colleges, campuses, qualifications) -> None:
        report = self.report.courses
        status = status_for_supplied_course(self.session)

        # COL-04 grain: one offering per college + campus + qualification.
        grouped: dict[tuple[str, str, tuple], list[tuple[int, dict]]] = defaultdict(list)
        for index, r in enumerate(rows, start=2):
            rto, address = _cell(r, "RTO"), _cell(r, "Location")
            key = qualification_key(_cell(r, "VET Code"), _cell(r, "Course Name"))
            if not rto or not address:
                report.rejected.append(
                    Issue(LOCATION_FILE, LOCATION_SHEET, index, _cell(r, "Course Code"),
                          "RTO or Location is blank.")
                )
                continue
            grouped[(rto, address, key)].append((index, r))

        report.source = len(grouped)

        for (rto, address, key), entries in sorted(
            grouped.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2][0] or "", kv[0][2][1])
        ):
            college, campus = colleges.get(rto), campuses.get(address)
            qualification = qualifications.get(key)
            if college is None or campus is None or qualification is None:
                report.rejected.append(
                    Issue(LOCATION_FILE, LOCATION_SHEET, entries[0][0],
                          _cell(entries[0][1], "Course Code"),
                          "college, campus or qualification could not be resolved "
                          "(the campus address may have been rejected for a missing state).")
                )
                continue

            codes = sorted({_cell(r, "Course Code") for _, r in entries if _cell(r, "Course Code")})
            if len(codes) > 1:
                report.conflicts.append(
                    Issue(
                        LOCATION_FILE, LOCATION_SHEET,
                        ", ".join(str(i) for i, _ in entries),
                        f"{rto} / {key[0] or key[1]} / {address}",
                        f"{len(codes)} Course Codes for one college+campus+qualification "
                        f"({', '.join(codes)}). COL-04 allows one offering, so {codes[0]} was "
                        f"stored. Confirm which code is current.",
                    )
                )
            if not codes:
                report.rejected.append(
                    Issue(LOCATION_FILE, LOCATION_SHEET, entries[0][0], "(blank)",
                          "Course Code is blank.")
                )
                continue

            first = entries[0][1]
            cost = _cell(first, "Total Course Cost")
            offering, created = self._get_or_create(
                CourseOffering, report,
                {
                    "course_code": codes[0],
                    # Approved rule: every course supplied by the project owner
                    # is ACTIVE in TDMS. The source's "Registered" describes
                    # external registration, not TDMS availability.
                    "course_status_id": status.id,
                    "total_course_cost": cost or None,
                },
                college_id=college.id, campus_id=campus.id, qualification_id=qualification.id,
            )
            if not created and offering.course_status_id != status.id:
                offering.course_status_id = status.id
                report.update += 1

            # DBQ-03: durations are a *set* per offering. The distinct values are
            # collected before any insert — checking the database row by row
            # misses rows added earlier in this same loop, which have not been
            # flushed yet, and the unique constraint then fires at flush.
            wanted: set[int] = set()
            for row_number, r in entries:
                weeks = _cell(r, "Duration In Weeks")
                if not weeks:
                    continue
                try:
                    value = int(float(weeks))
                except ValueError:
                    report.rejected.append(
                        Issue(LOCATION_FILE, LOCATION_SHEET, row_number, codes[0],
                              f"Duration In Weeks {weeks!r} is not a number.")
                    )
                    continue
                if value > 0:
                    wanted.add(value)

            already = {
                d.duration_weeks
                for d in self.session.execute(
                    select(OfferingDurationOption).filter_by(course_offering_id=offering.id)
                ).scalars()
            }
            for value in sorted(wanted - already):
                self.session.add(
                    OfferingDurationOption(
                        course_offering_id=offering.id, duration_weeks=value, is_active=True
                    )
                )
        self.session.flush()


def format_report(report: ImportReport) -> str:
    lines: list[str] = []
    for title, section in report.sections():
        lines.append(f"\n{title}")
        lines.append(f"  Source   : {section.source}")
        lines.append(f"  Reuse    : {section.reuse}")
        lines.append(f"  Create   : {section.create}")
        lines.append(f"  Update   : {section.update}")
        lines.append(f"  Conflict : {len(section.conflicts)}")
        lines.append(f"  Ambiguous: {len(section.ambiguous)}")
        lines.append(f"  Pending  : {len(section.pending)}")
        lines.append(f"  Reject   : {len(section.rejected)}")
        for label, issues in (
            ("CONFLICT", section.conflicts),
            ("AMBIGUOUS", section.ambiguous),
            ("PENDING", section.pending),
            ("REJECT", section.rejected),
        ):
            for issue in issues[:6]:
                lines.append(f"    [{label}] {issue}")
            if len(issues) > 6:
                lines.append(f"    [{label}] ... and {len(issues) - 6} more")
    if report.provisional:
        lines.append("\nPROVISIONAL VALUES (generated, not supplied):")
        for note in sorted(set(report.provisional))[:8]:
            lines.append(f"  - {note}")
        if len(set(report.provisional)) > 8:
            lines.append(f"  - ... and {len(set(report.provisional)) - 8} more")
    return "\n".join(lines)
