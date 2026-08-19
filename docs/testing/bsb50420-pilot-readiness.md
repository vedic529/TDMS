# BSB50420 Vertical Slice — Rolling Timetable Readiness

**Pilot:** AIBT · 104262B · BSB50420 Diploma of Leadership and Management ·
Blacktown · 52 weeks · Group **N/A**
**Date:** 12 August 2026
**Status:** reference and trainer data **written**; rolling timetable **parsed,
validated and blocked on a schema gap** (§5 below).

---

## 1. Sources

| File | Used for |
| --- | --- |
| `Location Data (1).xlsx` | RTO, Course Code, VET Code, Course Name, status, duration, cost, course/location relationship |
| `Qualification Data.xlsx` | Qualification title, unit membership, unit codes and titles, Source URL |
| `Trainer Data - BSB.xlsx` | Trainer id/name, campus, working time, weekday availability, qualification and unit competencies |
| `Rolling TT Data - BSB.xlsx` | Rolling weekly pattern, intake entry points, unit periods, breaks, assessment weeks |

Qualification Data defines **which** units belong to the package. It does **not**
define teaching order — that comes only from the rolling timetable.

---

## 2. The BSB50420 sheet

| | |
| --- | --- |
| Week rows | 277 (weeks 1–277, strictly consecutive, every row exactly 7 days) |
| Calendar | 19-Jan-2026 → 11-May-2031 |
| Intake columns | 52 (D…BC) |
| Explicit `Intake` markers | 51 — column D is a stream already under way when the calendar opens |
| Distinct cell values | 15: twelve unit codes, `BREAK`, `ASSESSMENT WEEK`, `Intake` |

Column A is Week No., B is Start Date, C is End Date, and every column from D on
is one rolling intake.

**This is a rolling timetable.** Intakes join the cycle at different points and
wrap around. The cohort marked at week 3 begins with BSBLDR523 — not with the
first unit of the cycle — and meets BSBCRT511 a year later. Any model that
assumes every cohort starts at unit one produces a wrong timetable.

### Base rolling cycle

Read from the earliest complete stream (column D), not from spreadsheet row
order in Qualification Data:

```
BSBCRT511 → BSBLDR523 → BSBCRT611 → BSBOPS502 → BSBPEF502 → BSBOPS601
→ BSBTWK502 → BSBCMM511 → BSBPEF501 → BSBOPS505 → BSBTWK501 → BSBLDR522
```

### Intake date semantics — resolved, not assumed

Every marked column's first unit sits in the row **directly below** its marker,
without exception across all 51 markers. So:

- the intake date is the **Start Date of the marked week** (a Monday);
- **delivery begins the following week**.

Both statements are true simultaneously, which is why the two readings the
question could have had turn out not to conflict. Column E: marker week 3
(02-Feb-2026), first unit BSBLDR523 from 09-Feb-2026, running 52 weeks to
07-Feb-2027.

### Every intake is identical in shape

All 52 intakes: **43 teaching weeks + 8 break weeks + 1 assessment week = 52**,
covering 12 unit deliveries. That matches the 52 weeks in Location Data exactly
— the figure was not forced.

### A unit crossing a break

BSBPEF502 in the base stream:

| | |
| --- | --- |
| Taught | 27-Apr-2026 → 10-May-2026 (2 weeks) |
| BREAK | 11-May-2026 → 07-Jun-2026 (4 weeks) |
| Taught | 08-Jun-2026 → 14-Jun-2026 (1 week) |
| **Result** | **one delivery**, 3 active weeks, 7-week calendar span |

41 of the 624 unit deliveries are interrupted this way. They are stored as one
delivery with the break preserved as its own period — two deliveries would
double-count the unit, and dropping the break would lose four weeks of calendar.

### Breaks and assessment weeks are calendar events, not units

10 distinct BREAK blocks, all 4 weeks, twice a year (May–June and December–
January), affecting 5–12 intakes each. 5 distinct ASSESSMENT WEEK blocks, all in
early January.

**Assessment week is calendar-anchored, not completion-anchored.** It falls at
the end of the base stream's 52 weeks, but mid-cycle for every rolling intake —
cohort E sits its assessment week at week 52 and then continues teaching to week
55. This is a whole-of-college event, not a per-cohort milestone.

---

## 3. Cross-file consistency

| Check | Result |
| --- | --- |
| Location Data → AIBT / 104262B / BSB50420 / Blacktown | ✅ exactly one row, 52 weeks, $14,600 |
| Qualification Data → AIBT BSB50420 | ✅ 12 units, title and Source URL present |
| Rolling TT unit codes vs Qualification Data | ✅ identical sets |
| Qualification units missing from Rolling TT | **NONE** |
| Rolling TT codes not in Qualification Data | **NONE** |
| Non-unit scheduling values | only `BREAK`, `ASSESSMENT WEEK`, `Intake` |

One observation outside the pilot: Qualification Data lists `Brooklyn` as an RTO
offering BSB50420, while Location Data uses `BIC` for what appears to be the same
provider. Not mapped — similar-looking codes are not the same code.

---

## 4. Trainer coverage — all 12 units COVERED

Blacktown-rostered trainers: **BSBQT02 Ertajul Noorani** and
**BSBQT04 Minhaj Chowdhury**. Eligibility is per **unit**, not per qualification.

| Unit | Eligible | Blacktown | Coverage |
| --- | --- | --- | --- |
| BSBCMM511 | QT01, QT02, QT03, QT05 | QT02 | COVERED |
| BSBCRT511 | QT01, QT02, QT03, QT05 | QT02 | COVERED |
| BSBCRT611 | QT01, QT02, QT03, QT05 | QT02 | COVERED |
| BSBLDR522 | QT01, QT02 | QT02 | COVERED |
| BSBLDR523 | QT01, QT02 | QT02 | COVERED |
| BSBOPS502 | QT01, QT02 | QT02 | COVERED |
| BSBOPS505 | QT01, QT02 | QT02 | COVERED |
| BSBOPS601 | QT01–QT05 | QT02, QT04 | COVERED |
| BSBPEF501 | QT01, QT02, QT03, QT05 | QT02 | COVERED |
| BSBPEF502 | QT01, QT02, QT03, QT04 | QT02, QT04 | COVERED |
| BSBTWK501 | QT01, QT02 | QT02 | COVERED |
| BSBTWK502 | QT01, QT03, QT04 | **QT04 only** | COVERED |

BSBQT02 covers 11 of 12; BSBTWK502 rests entirely on BSBQT04 at this campus.
Both trainers work 09:00–17:00, class type Theory. BSBQT02 is at Blacktown
Mon/Tue/Fri, BSBQT04 Mon/Wed/Thu — physical, from the workbook.

---

## 5. ROLLING TIMETABLE MODEL GAP

The rolling timetable is parsed, validated and internally consistent. It **cannot
be stored** — four blockers, none of which application code can work around.

| # | Blocker | Why it blocks |
| --- | --- | --- |
| 1 | `student_groups.intake` has `CHECK (EXTRACT(day FROM intake) = 1)` | Real intake dates are **Mondays**: 02-Feb-2026, 23-Feb-2026, 30-Mar-2026… 50 of the 51 would be rejected |
| 2 | `timetable_plans.student_group_id` is NOT NULL | A rolling intake exists as a plan before any student group does |
| 3 | Nothing can represent `BREAK` or `ASSESSMENT WEEK` | `timetable_unit_deliveries.unit_id` is NOT NULL, and creating a Unit `BREAK` is forbidden |
| 4 | `timetable_unit_deliveries.mode_of_delivery` is NOT NULL | The rolling timetable never states Physical or Virtual |

Classification per §33:

| Capability | Status |
| --- | --- |
| Multiple concurrently active intakes | **SUPPORTED** |
| Unit periods with start/end dates | **MAPPING CHANGE ONLY** (blocked by #4) |
| Unit spanning a break | **MAPPING CHANGE ONLY** — one delivery row spans it, but active weeks vs calendar span is not stored |
| Rolling intake identity | **SCHEMA GAP** (#1, #2) |
| Break periods | **SCHEMA GAP** (#3) |
| Assessment periods | **SCHEMA GAP** (#3) |
| Future session allocation | **SUPPORTED** — no data yet |

### Smallest proposed change

Not implemented. Awaiting approval.

1. **Relax the intake CHECK** to any date, or to "must be a Monday". The
   first-of-month rule contradicts the operational calendar.
2. **Make `timetable_plans.student_group_id` nullable**, so a plan can exist for
   an intake before enrolment.
3. **Add a course-calendar period table** — plan, period type
   (`UNIT`/`BREAK`/`ASSESSMENT`), nullable unit, start/end date, active weeks —
   giving breaks and assessment weeks a home without polluting `units`.
4. **Make `mode_of_delivery` nullable** on unit deliveries, or move it to the
   session layer where the data actually lives.

Nothing else in the timetable schema needs to move.

---

## 6. Two data layers

| Layer | Defines | State |
| --- | --- | --- |
| **Rolling planning** | which units run in which weeks, intake progression, breaks, assessment weeks | parsed and validated; **not storable** |
| **Actual session** | exact date, start/end time, trainer, room, delivery mode | schema ready; **no source data** |

The rolling timetable contains **no** daily start time, end time, trainer
assignment, room, facility, capacity, cohort size or Physical/Virtual session
assignment. Verified column by column: the sheet has Week No., Start Date, End
Date and intake columns, nothing else.

---

## 7. Clash engine

**No backend clash engine exists.** `app/services/` contains no timetable or
clash module. The only clash logic in the repository is
`apps/web/src/features/timetable/validation.ts` — TypeScript, frontend-only, run
against the mock client, never against PostgreSQL.

| Check | Algorithm | PostgreSQL-backed | Needs session time | Needs allocation | Real BSB50420 test possible |
| --- | --- | --- | --- | --- | --- |
| Trainer clash | frontend only | No | Yes | Yes | No |
| Facility clash | frontend only | No | Yes | Yes | No |
| Cohort clash | frontend only | No | Yes | No | No |
| Trainer availability | frontend only | No | Yes | Yes | No |
| Capacity | frontend only | No | No | facility + cohort size | No |

The schema supports all of it — `timetable_sessions` carries weekday, times,
trainer and facility with the indexes TT-06 needs. The service layer is absent.

**Weekly overlap is not a clash.** Two units in the same calendar week may run on
different days, at different times, with different trainers; two active intakes
in the same week is the normal state of a rolling timetable, not a conflict. A
real clash needs date, start time, end time and the shared resource.

---

## 8. What was written

Idempotent, via `scripts/import_bsb50420_pilot.py`, running as the
least-privilege `tdms_app` role. Re-running produces 51 reuses and 0 creates.

| Entity | Count |
| --- | --- |
| College AIBT | 1 |
| Campus Blacktown | 1 |
| AIBT ↔ Blacktown approval | 1 |
| Qualification BSB50420 | 1 |
| Units | 12 |
| Qualification/unit sequence (base cycle) | 12 |
| Course status `REGISTERED` | 1 |
| Course offering 104262B | 1 (+ 52-week duration option) |
| Trainers | 2 |
| Trainer unit competencies | 14 |
| Trainer availability | 2 |

`qualification_units.delivery_order` holds the **base rolling cycle** order from
the workbook. It is not a claim about any intake's progression — intakes enter at
different points, which this field does not express and was never asked to.

### Reported, not invented

- **`colleges.college_full_name`** — no supplied file has AIBT's full legal name.
  The short name was stored rather than one invented. **Correction required.**
- **`campuses.campus_code`** — no supplied file has campus codes. `BLACKTOWN` was
  used. **Confirmation required.**
- **`units.uoc_type`** — no source states Theory / Theory and Practical. Left
  empty.
- **Haymarket availability** for both trainers was not imported: that campus is
  outside the approved pilot scope.

---

## 9. Parser

`app/services/rolling_timetable.py`, 24 tests in
`tests/test_rolling_timetable_parser.py`.

- Columns are located **by heading**, not by coordinate — the workbook can gain
  rows, intake columns or calendar years without a parser change.
- **No unit code is hard-coded.** The parser reports what it read; whether a code
  is a unit of the qualification is decided against the database, so a
  spreadsheet cannot introduce a unit TDMS has not approved.
- Column letters are kept for traceability only. The business identity of an
  intake is its **date**.
- One named sheet is read per run, so an import cannot stray outside its scope.

---

## 10. Outstanding

**Required for the real session-level clash test** — none of it exists in any
supplied file:

| Field | Needed for |
| --- | --- |
| Class date | all three clash types |
| Start and end time | all three clash types |
| Trainer assignment per session | trainer clash |
| Facility / room per session | facility clash |
| Delivery mode per session | facility clash (virtual needs no room) |
| Facility records with capacity | facility clash and capacity |
| Cohort size per intake | capacity |

There are **no facility records anywhere in the database**, so the facility
clash test has no resource to contend over even with times supplied.

Not outstanding: unit sequence (derived), intake dates (derived), unit durations
(derived), break periods (derived), trainer competencies (imported).
