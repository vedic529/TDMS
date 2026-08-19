# Page 4A Source Data Review — `Location Data.xlsx`

**Status:** reviewed, **not imported**. Three schema conflicts and two data-quality
issues require business decisions first.
**Date:** 11 August 2026
**Source:** `Location Data.xlsx`, sheet "Course Location Export", 442 data rows.

---

## 1. What the export contains

| Column | Distinct | Intended target |
| --- | --- | --- |
| RTO | 6 — AIBT, AVTA, BIC, HJ, NPA, REACH | `colleges.college_short_name` |
| Course Code | 183 | `course_offerings.course_code` |
| VET Code | 76 | `qualifications.qualification_code` |
| Course Name | 79 | `qualifications.qualification_title` |
| Course Status | 1 — Registered | `course_statuses` |
| Course Level | 8 | `qualifications.course_level` |
| Field Of Education Broad / Narrow | — | `qualifications.field_of_education_*` |
| Course Sector | 2 — ELICOS, VET | `qualifications.course_sector` |
| Duration In Weeks | — | `offering_duration_options` |
| Total Course Cost | — | `course_offerings.total_course_cost` |
| Location | 16 | `campuses` |

The shape confirms three earlier resolutions were correct: **RTO is the College**
(DBQ-06), **Location is the Campus** (C-3), and **duration is a set, not a
column** — five course codes carry more than one duration, which
`offering_duration_options` already models (DBQ-03).

---

## 2. Schema conflicts — decisions required

### CONFLICT 1 — `course_offerings.course_code` is UNIQUE, the data is not

**163 of 183** Course Codes appear at more than one Location; one appears at six.
A CRICOS code identifies the *course*, not the offering of that course at one
campus.

Schema v1 already carries `UNIQUE (college_id, campus_id, qualification_id)`,
which is the correct grain. The standalone `UNIQUE (course_code)` contradicts it
and blocks the real data.

**Recommendation:** drop the standalone unique constraint, keep the composite.
Requires approval and a new migration. Not done.

### CONFLICT 2 — `qualifications.qualification_code` is UNIQUE NOT NULL, ELICOS has no code

Eight rows carry `VET Code = 'NA'` and others are blank, spanning four distinct
course names (General English, IELTS Preparation). Loading them all as `'NA'`
collides on the unique constraint.

**Options:** (a) make the code nullable with uniqueness over non-null values
only; (b) agree a coding convention for ELICOS. Both are business decisions —
codes will not be invented.

### CONFLICT 3 — `campuses` needs structured fields the export does not have

`campuses` requires `campus_code`, `campus_name`, `campus_location` and `state`.
The export has one free-text address. `colleges` likewise requires
`college_full_name`; the export has only the short form (`AIBT`).

**Decision required:** the approved campus list with codes, names and states, and
the colleges' full legal names.

---

## 3. Data quality — resolve before import

**The 16 Locations are not 16 campuses.** Several are one site written several
ways:

- `125 Main St BLACKTOWN NSW 2148` · `125 Main St, Blacktown, NSW`
- `132-146 Elizabeth St HOBART TAS 7000` · `132-146 Elizabeth Street, HOBART, TAS, 7000` · `Hobart Campus - 132-146 Elizabeth St HOBART TAS 7000`
- `841 George St - 841 George St HAYMARKET NSW 2000` · `841 George St, Haymarket NSW 2000`

**Encoding damage in the source file.** `132 ? 146 Elizabeth St, Hobart, TAS`
lost an en-dash in an earlier conversion. Importing as-is would persist mojibake
into permanent reference data.

---

## 4. Position

No row of this file has been written to `tdms_dev`. Importing it would mean
inventing campus codes, campus names, states, college full names and ELICOS
qualification codes — none of which the source contains. Once conflicts 1–3 are
resolved and the campus/college lists confirmed, the import can run as its own
reviewable step with a dry-run report before any write.
