# TDMS Student Rules v1.1 — Approved Schema Amendment

**Status:** APPROVED and implemented.
**Approval date:** 11 August 2026 · **Approval authority:** Project Owner
**Amends:** Database Schema v1 (10 Aug 2026), after Access Model v1.1 (11 Aug 2026)
**Migration:** `0e8b41dd1b13` — *student group uniqueness and date intake*, revises `805d65b129f2`

A controlled amendment. Schema v1 and the Access Model v1.1 migration are
unchanged; this records what changed after them, and why.

---

## 1. The business rules being served

### Intake

Derived from the Proposed Start Date as the **first day of that month**, and
displayed as **`DD-MMM-YYYY`** with English three-letter month labels.

| Proposed start | Intake stored | Intake shown |
| --- | --- | --- |
| 18-Aug-2026 | `2026-08-01` | `01-Aug-2026` |
| 03-Jan-2027 | `2027-01-01` | `01-Jan-2027` |

Never shown as `AUG-2026`, `08/01/2026`, `01/08/2026` or `2026-08-01`.

### Group

Ten qualifications use numbered groups; every other qualification uses `N/A`.

```
SIT40721  SIT40521  SIT30821  SIT31021  SIT50422
SIT60322  SIT50122  SIT60122  RII50520  RII60520
```

The current range is **Group 1 … Group 15**, chosen by staff — never generated
from campus, qualification, intake, date or course code. The old generated form
(`BSB80120-HOB-AUG2026`) is gone.

---

## 2. What changed in the database

### 2.1 `student_groups.group_code` is no longer globally unique

**Before:** `UNIQUE (group_code)`.

That was correct while group codes were generated and globally distinct. Under
the new rule the codes are `Group 1`…`Group 15`, so a global constraint would
allow `Group 1` to exist **exactly once in the entire system** — and the second
qualification, campus or intake that needed one would fail to save.

**After:** `UNIQUE (course_offering_id, intake, group_code)`.

All three of these now coexist, which is the approved requirement:

```
SIT40721 / 01-Aug-2026 / Group 1
SIT40721 / 01-Jan-2027 / Group 1
RII50520 / 01-Aug-2026 / Group 1
```

A true duplicate — same offering, same intake, same name — is still rejected,
because that is genuinely one group entered twice.

### 2.2 `student_groups.intake` is now `date`

**Before:** `text`. **After:** `date`, holding the first of the month.

Text was wrong in a way that would have surfaced later as a bug report rather
than an error: `'01-Jan-2027'` sorts *before* `'01-Aug-2026'` as a string, and no
date-range filter can work without parsing every row. The column is a date;
`DD-MMM-YYYY` is applied at the display and export boundary only.

### 2.3 New: `CHECK (EXTRACT(DAY FROM intake) = 1)`

The approved rule is the first day of the month, so `2026-08-18` is a bug rather
than a variation worth storing. Named
`ck_student_groups_intake_is_first_of_month`.

*Not separately requested — added because it encodes the approved rule directly.
Say the word and it comes out.*

### 2.4 Migration safety

`student_groups` was verified empty before the migration was written, so the cast
could not lose anything. The `USING` clause still handles both the ISO and
`DD-MMM-YYYY` spellings, because a migration that only works on an empty table is
one that fails the first time it matters.

`downgrade()` reverses all three changes. Restoring the global UNIQUE fails
loudly if two offerings by then share a group name — the correct outcome, since
the data would not fit the old shape and quietly dropping rows to make it fit
would be worse.

---

## 3. Where the rules live in code

**One source of truth per side, and a test that keeps them equal.**

| | |
| --- | --- |
| Backend | `apps/api/app/core/student_rules.py` |
| Frontend | `apps/web/src/lib/student-rules.ts` |

Raising the maximum group number is **one constant**:

```python
MAX_NUMBERED_GROUP: int = 15
```

The option list, validators, form dropdown and tests all derive from it, so
15 → 16 is a single controlled change rather than an edit across components. A
frontend test reads both files and fails if the constant or the qualification
list disagree.

Enforced in the API, not only by a dropdown: `validate_group()` refuses
`Group 0`, `Group 16`, `G1`, `group 1`, `Group 01`, arbitrary text, a blank on a
group-enabled qualification, and a numbered group on one that has none.

**Qualification switching** clears stale values in both directions:

| Change | Result |
| --- | --- |
| SIT40721 (Group 5) → BSB50420 | Group becomes `N/A` |
| BSB50420 (`N/A`) → RII50520 | Cleared; the user must choose |
| SIT40721 (Group 5) → SIT50422 | Group 5 carries over — still valid |

---

## 4. Verification

| Check | Result |
| --- | --- |
| `alembic upgrade head` | applied; 28 tables, 15 enum types |
| `alembic check` | No new upgrade operations detected |
| `downgrade -1` → `upgrade head` | round-trips to an identical shape |
| Blank database → v1 → v1.1 → 5B | reproduces head exactly |
| `downgrade base` → `upgrade head` | full rebuild reproduces head |
| Three `Group 1` rows across offerings/intakes | accepted |
| Exact duplicate | rejected |
| Group 1…15 in one intake | accepted |
| Mid-month intake (2nd, 15th, 18th, 31st) | rejected |
| Intake sorting and date-range filtering | correct |
| Backend tests | 421 passed |
| Frontend | typecheck, lint, 24 tests, build all clean |

---

## 5. What did not change

No other table, column, constraint or index. `students.student_group_id` still
points at `student_groups`, and the timetable's use of the group is unaffected.
`students` itself was not touched: Intake is derived through the group, exactly
as Schema v1 §8.1 specifies.
