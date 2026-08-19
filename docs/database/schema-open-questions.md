# TDMS Schema v1 — questions requiring approval

Fifteen questions — **all answered**. Schema v1 was **approved on 10 August 2026**. Each one materially changes table structure, cardinality, keys, stored fields,
constraints or historical behaviour. Questions answerable from the SRS, the repository or normal
database practice are **not** asked here — they are decided in the proposal with the reason stated.

Asked in groups, highest risk first. **All four groups are answered; no schema question remains open.**

| ID | OD link | Subject | Group | Risk |
| --- | --- | --- | --- | --- |
| DBQ-01 | **OD-08** | Credit Transfer storage and duration rules | 1 | ✅ **ANSWERED — C** |
| DBQ-02 | OD-03 | Whether session state is persisted at all | 1 | ✅ **ANSWERED — A** |
| DBQ-03 | — | Duration: one value or approved options | 1 | ✅ **ANSWERED — A** |
| DBQ-04 | — | College ↔ Campus cardinality | 1 | ✅ **ANSWERED — M:N** |
| DBQ-05 | — | Storing an internal unit delivery order | 2 | ✅ **ANSWERED — internal only** |
| DBQ-06 | — | Is RTO a separate entity from College? | 2 | ✅ **ANSWERED — RTO = College** |
| DBQ-07 | — | Unit sequence per qualification or per campus | 2 | ✅ **ANSWERED — per qualification** |
| DBQ-08 | — | Student ID reuse after soft deletion | 2 | ✅ **ANSWERED — reserved** |
| DBQ-09 | — | Duplicate resolution values in bulk import | 3 | ✅ **ANSWERED — exclude only** |
| DBQ-10 | — | Student group as an entity or a text value | 3 | ✅ **ANSWERED — entity** |
| DBQ-11 | — | Trainer weekday availability shape | 3 | ✅ **ANSWERED — five columns** |
| DBQ-12 | — | Timetable: normalized three levels or one wide table | 3 | ✅ **ANSWERED — normalised** |
| DBQ-13 | OD-09 | Facility reference uniqueness scope | 4 | ✅ **ANSWERED — per campus** |
| DBQ-14 | OD-11 | MSCRIS representation and trainer source | 4 | ✅ **ANSWERED — earlier approvals stand** |
| DBQ-15 | — | Campus identity now that a campus is shared | 4 | ✅ **ANSWERED — campus code** |

---

## Group 1 — ✅ ANSWERED

**Outcome summary**

| Question | Answer | Effect on the schema |
| --- | --- | --- |
| DBQ-01 | **C** — earlier approvals stand | `students.ct_student boolean`; `actual_course_duration_weeks` becomes a GENERATED column using inclusive dates; Course Duration Option always shown and staff-selected. **OD-08 is now fully resolved and no longer blocks Schema v1.** |
| DBQ-02 | **A** — no session table | `user_sessions` removed from the design. Access level is read from `users` per request. Deviates from SRS §9.1's "active sessions" wording by explicit approval. |
| DBQ-03 | **A** — approved options child table | `offering_duration_options` confirmed; `students.course_duration_option_id` FK guarantees the option belongs to the student's own offering. |
| DBQ-04 | **M:N** — a campus can be shared | `campuses.college_id` **removed**; `college_campuses` junction added; `course_offerings` gains a **composite FK** to `(college_id, campus_id)` so COL-01 is enforced by the database. Prevents duplicate campuses, duplicate facilities and a facility clash check that could not see two colleges booking the same room. |

The original question text is retained below for the record.

---

### DBQ-01 / OD-08 — Credit Transfer storage and duration rules · ✅ ANSWERED (was the schema blocker)

**The issue.** In an earlier session these were approved verbally: CT is a flag only, staff select the
duration option, the option is always shown, and weeks are counted inclusively. The instruction
opening this database step states the opposite — that the exact CT data requirements, whether
transferred units are stored, the Course Duration Option behaviour and the duration calculation are
**not** approved. The current SRS agrees with the instruction: §6.1.3 still says the option "is hidden
when the approved CT rule says it is not required", SST-10 still lists all three as unapproved, and
OD-08 is still open.

I have not silently picked a side. This question exists to settle which record stands.

**Options.**

| | Structure | Consequence |
| --- | --- | --- |
| **A** | `students.ct_student boolean` only | One column. Timetable generation can never skip transferred units, because TDMS does not know which they are. |
| **B** | `student_credit_transfers` + `student_credit_transfer_units` | Two extra tables and a link to `units`. Enables per-unit CT and future duration derivation. |
| **C** | Confirm the earlier verbal approvals stand | Same as A, plus: Actual Course Duration becomes a generated column using inclusive dates, Course Duration Option is always shown and validated against the calculated duration. |

**Recommendation: C — confirm the earlier approvals.** They are consistent, they match what the
prototype already demonstrates, and they give the simplest schema that satisfies every current
requirement. Option B should be chosen only if a course can genuinely be shortened per transferred
unit.

**What changes in the database.**
- A or C: one boolean on `students`; `actual_course_duration_weeks` can be a `GENERATED` column.
- B: two new tables, a new FK path `students → units`, and duration becomes derived from CT data —
  which also means it cannot be a simple generated column.

Retrofitting B later is additive (the boolean becomes derived), so this is recoverable — but the
duration rule must be settled before `students` is created either way.

**Please approve A, B or C.**

---

### DBQ-02 / OD-03 — Is a `user_sessions` table required at all?

**The issue.** SRS §9.1 lists "active sessions" among the stored data groups. The instruction asks me
not to create a sessions table simply because the word appears, and to determine whether persistence
is genuinely needed given Microsoft Entra + FastAPI.

**Analysis.** With Entra ID, identity is proven per request by a token. A 30-minute inactivity timeout
is enforced by token lifetime and sliding refresh. ACC-07 and AUTH-12 require an access-level change
to take effect by the next sign-in or refresh — which is *better* served by reading `users.access_level`
on each request than by caching it in a session row that could go stale. Sign-in and sign-out are
already durably recorded in `user_activity_records`.

A session table is genuinely required only for: forced server-side revocation before token expiry, an
administrative "who is signed in right now" screen, or concurrent-session limits. **None of these
appears in the SRS requirements.**

**Options.**

| | |
| --- | --- |
| **A** | No session table in Schema v1. Sessions are token-based; the activity record is the history. |
| **B** | Add `user_sessions` now (id, user, issued_at, last_seen_at, expires_at, revoked_at). |

**Recommendation: A.** It removes a table, removes a write on every request, and removes a source of
truth that can disagree with `users`. If revocation or an active-session screen is later required, B
is purely additive.

**What changes in the database.** A: no table. B: one table plus an update on every authenticated
request, and a purge job.

**Note.** Choosing A means the interface does **not** implement SRS §9.1's "active sessions" literally.
That is why this is a question and not a silent decision.

**Please approve A or B.**

---

### DBQ-03 — Duration in Weeks: one value per course, or approved options?

**The issue.** Page 4A shows a single **Duration in Weeks** per course row. But §6.1.3 has the user
selecting a *Course Duration Option* from an approved dropdown, and TT-11 refers to 26-, 52-, 78- and
104-week courses. Those only reconcile if one offering can carry more than one approved duration —
and COL-04 makes college + campus + qualification unique, so separate rows per duration are not
allowed.

**Options.**

| | Structure | Consequence |
| --- | --- | --- |
| **A** | `offering_duration_options` child table | A student's duration is constrained by FK to their own offering's approved options. Page 4A edits a list. |
| **B** | `course_offerings.duration_weeks` single column | Simpler, but "Course Duration Option" then has no source, and a 26- and 52-week version of the same qualification at the same campus cannot both exist without breaching COL-04. |

**Recommendation: A.**

**What changes in the database.** A: one extra table, one FK from `students`. B: one integer column,
and the Course Duration Option dropdown has nothing approved to read from.

**Please approve A or B.**

---

### DBQ-04 — Can one campus belong to more than one college?

**The issue.** COL-01 says the user selects a College and then only a Campus "approved for that
College". The SRS never states that a campus belongs to exactly one college. In RTO groups a single
delivery site is sometimes shared between brands.

**Options.**

| | Structure | Consequence |
| --- | --- | --- |
| **A** | `campuses.college_id` (1:N) | Simplest. Every query is one join. Wrong if a site is shared — the campus would have to be entered twice, creating duplicate facilities and duplicate offerings. |
| **B** | `college_campuses` junction (M:N) | Correct if sharing occurs. Adds a join to most reference queries and to the student's State derivation. |

**Recommendation: A**, unless a shared site already exists or is expected. Changing A → B later is a
real migration: new junction, backfill, and every `campus_id` consumer re-checked — which is why it is
worth one minute now.

**What changes in the database.** A: one FK column. B: one extra table and an extra join in College →
Campus → Offering, Facility and Trainer queries.

**Please answer: can a single physical campus be operated by more than one college?**

---

## Group 2 — ✅ ANSWERED

| Question | Answer | Effect on the schema |
| --- | --- | --- |
| **DBQ-05** | Store it, **never display it** | `qualification_units.delivery_order integer NOT NULL`, populated from row order on import and maintained by drag-reorder. Page 4B still shows no Sequence ID column, so SRS §8.3 holds while TT-08 stays implementable. `UNIQUE (qualification_id, delivery_order) DEFERRABLE`. |
| **DBQ-06** | **RTO is the College** | `rtos` table **withdrawn** and `qualifications.rto_id` removed. Page 4B reads RTO through `qualification_units → qualifications → course_offerings → colleges`. `qualifications` stays national rather than being owned by one college. Table count drops from 28 to 27. |
| **DBQ-07** | One sequence **per qualification** | `qualification_units` has no `course_offering_id`. Page 4's college/campus filter reaches units through `course_offerings`, so the sequence is stored once instead of being duplicated for every campus that offers the qualification. |
| **DBQ-08** | Student ID **permanently reserved** | A plain `UNIQUE (student_id)` covering soft-deleted rows, not a partial index. A Student ID therefore identifies exactly one person forever, so historical activity records and import batches stay unambiguous. A record deleted in error is recovered through Restore. |

## Group 3 — ✅ ANSWERED

| Question | Answer | Effect on the schema |
| --- | --- | --- |
| **DBQ-12** | **Normalised, three levels** | `timetable_plans` → `timetable_unit_deliveries` → `timetable_sessions`, with `session_type` = THEORY / PRACTICAL / ADDITIONAL. TT-06 becomes one self-join answering all three clash types. Trainer and facility become real foreign keys (DATA-02). The `theory_*` / `practical_*` / `mscris_*` triplication disappears. |
| **DBQ-11** | **Five weekday columns** | `trainer_availability` keeps `monday`…`friday` columns, matching the source spreadsheet and the Page 3 grid. To keep clash and availability queries single-predicate, a **view** `trainer_availability_days` unpivots the five columns into rows. The view stores nothing and cannot drift from the table. |
| **DBQ-10** | **A reference entity** | `student_groups (group_code, course_offering_id, intake, expected_class_size, is_active)`, referenced by both `students` and `timetable_plans`. The student-group clash check becomes a foreign-key join, and Intake and Classroom Size get a single home. |
| **DBQ-09** | **Exclude the row — only resolution** | With one permitted resolution, a `duplicate_resolution` enum would carry a single value, so it is replaced by `duplicate_detected boolean`. That flag **survives the exclusion**, which matters because BULK-09 needs both a duplicate count and an excluded count and a row can be in both. Updating an existing student from an import is therefore **not possible** in Schema v1 — consistent with DATA-01. |

## Group 4 — ✅ ANSWERED

| Question | Answer | Effect on the schema |
| --- | --- | --- |
| **DBQ-14** | Earlier approvals stand | MSCRIS is `session_type = 'ADDITIONAL'` on the general session table — **no separate MSCRIS table**. Adds `session_title` (topic) and `trainer_name_text` (free text). Two CHECKs confine the exceptions: ADDITIONAL must be virtual, and free-text trainer is permitted **only** on ADDITIONAL so theory and practical cannot bypass approved trainer data. Clash queries filter `WHERE session_type <> 'ADDITIONAL'`. |
| **DBQ-15** | A campus code | `campuses.campus_code text UNIQUE` becomes the stable identity; `campus_name` is free to change. Survives a rename or rebrand and gives bulk-import mapping a reliable key. |
| **DBQ-13** | Unique per campus | `UNIQUE (campus_id, facility_reference)` — every site may have its own `C1` without an artificial prefix. |

### Recorded consequence of DBQ-14

A free-text MSCRIS trainer that is excluded from clash checking means **TDMS cannot detect a trainer
booked for both an MSCRIS class and a normal class**, and `trainer_name_text` does not satisfy DATA-02
for that field. This is implemented as approved, confined by CHECK constraints to ADDITIONAL sessions
only, and surfaced to the user by the timetable preview warning. It is recorded here so the gap is a
known decision rather than an oversight.
