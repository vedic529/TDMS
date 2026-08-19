# TDMS Access Model v1.1 — Approved Schema Amendment

**Status:** APPROVED and implemented.
**Approval date:** 11 August 2026 · **Approval authority:** Project Owner
**Amends:** Database Schema v1 (approved 10 August 2026)
**Migration:** `805d65b129f2` — *access model v1.1*, revises `6266b57ea53e`

This is a **controlled amendment**, not a correction. Schema v1 remains the
approved baseline and its initial migration is unchanged; this document records
what changed after it, and why.

---

## 1. Why the model changed

Two things turned out to be wrong in practice:

**There was no read-only access level.** Schema v1 assumed every approved user
maintained something. In reality most people who need TDMS need to *look at*
timetables and student data — and giving them Data Editor to achieve that hands
out delete rights nobody asked for.

**The Data Editor work assignment no longer separated anything.** Student Data
Officer and Timetable Officer were modelled as work assignments that also gated
access. The business confirmed a Data Editor maintains **both** Student Data and
Timetables, so the column decided nothing while still being a place where an
authorisation bug could live.

---

## 2. Previous model → new model

| | Schema v1 | Access Model v1.1 |
| --- | --- | --- |
| Access levels | 3 — DATA_EDITOR, ADMIN, SUPER_ADMIN | **4** — VIEWER, DATA_EDITOR, ADMIN, SUPER_ADMIN |
| Default for a new user | none (accounts pre-provisioned) | **VIEWER**, provisioned at first verified sign-in |
| Data Editor work assignment | STUDENT_DATA_OFFICER / TIMETABLE_OFFICER, gating access | **Removed entirely** |
| Who approves access requests | n/a | **SUPER_ADMIN only** — not Admin |
| Who assigns roles | Admin (delegated) and Super Admin | **SUPER_ADMIN only** |
| Super Admin accounts | 5 | **4** |
| Admin accounts | 1 | **2** — N. Verma moved from Super Admin to Admin |

The declaration order of `access_level` is ascending privilege, which is load
bearing: "at least this level" is a comparison, and "may only request a higher
role" is a CHECK constraint rather than application code.

---

## 3. What each level may do

| Capability | Viewer | Data Editor | Admin | Super Admin |
| --- | :-: | :-: | :-: | :-: |
| Sign in, open all four work areas | ✓ | ✓ | ✓ | ✓ |
| Search, filter, view | ✓ | ✓ | ✓ | ✓ |
| Download / export filtered data | ✓ | ✓ | ✓ | ✓ |
| Maintain **Student Data** (single entry + bulk import) | | ✓ | ✓ | ✓ |
| Maintain **Timetables** (create, generate, preview, save) | | ✓ | ✓ | ✓ |
| Maintain **Trainer Data** | | | ✓ | ✓ |
| Maintain **College and Course Reference Data** | | | ✓ | ✓ |
| Override a timetable clash | | | ✓ | ✓ |
| View user activity records | | | | ✓ |
| Administration dashboard | | | | ✓ |
| Change another user's access level | | | | ✓ |
| Approve or deny an access request | | | | ✓ |

Trainer and reference data stay **view-and-download** for a Data Editor. Viewer
is genuinely read-only: no create, edit, delete, restore, import, generate or
save, enforced in the API and mirrored in the interface.

---

## 4. Requestable roles

VIEWER is the default and is never requested. A user may request a **strictly
higher** role only — requesting your current role or a lower one is not a
request, and a reduction is an administrative action a Super Admin performs.

| Current | May request |
| --- | --- |
| VIEWER | DATA_EDITOR, ADMIN, SUPER_ADMIN |
| DATA_EDITOR | ADMIN, SUPER_ADMIN |
| ADMIN | SUPER_ADMIN |
| SUPER_ADMIN | *(nothing higher)* |

**No reason is required.** A request carries who, from what, to what — nothing
more.

---

## 5. Approval process

1. The user submits a request from their account menu. One pending request at a
   time.
2. The four Super Admins are notified by email. The email is a **notification
   only** — it carries no approval link or token, because an emailed decision
   link would convert "can read this mailbox" into "can grant TDMS access".
3. A Super Admin signs in to TDMS and approves or denies it in the dashboard.
4. **The first decision closes the request.** A second Super Admin acting
   afterwards receives *"This access request has already been decided."* and
   does not overwrite the first decision.
5. Approval changes the access level and closes the request **in one
   transaction**. If either half fails, neither is committed.
6. Denial leaves the access level unchanged. The request stays in history and
   the user may request again later.

**Nobody decides their own request** — enforced in the service *and* by a
database CHECK constraint, so it holds even if a route forgets to ask.

---

## 6. Super Admin direct role management

Independent of the request system, a Super Admin can set any user's level to
any of the four, up or down, through preview → confirm → save. Every change is
recorded in the user activity records.

Two administrative lockout protections, validated server-side inside the
transaction:

1. **A Super Admin cannot change their own role.**
2. **A change may never leave TDMS with zero active Super Admins.** This counts
   the remaining active Super Admins rather than assuming there are four — it
   has to hold when there is exactly one left. Disabling a Super Admin goes
   through the same check, because that removes an active Super Admin just as
   surely as demoting one.

---

## 7. Affected tables, columns and types

### Changed

| Object | Change |
| --- | --- |
| type `access_level` | Recreated as `VIEWER, DATA_EDITOR, ADMIN, SUPER_ADMIN` |
| type `data_editor_assignment` | **Dropped** |
| type `activity_action` | Recreated with six new values (below) |
| `users.data_editor_assignment` | **Dropped** |
| `users` CHECK `assignment_only_for_data_editor` | **Dropped** with the column |
| `user_activity_records.assignment_snapshot` | **Dropped** |

New `activity_action` values: `ACCESS_REQUEST_SUBMITTED`,
`ACCESS_REQUEST_APPROVED`, `ACCESS_REQUEST_DENIED`, `ACCESS_REQUEST_CANCELLED`,
`ROLE_CHANGED`, `ACCOUNT_STATUS_CHANGED`.

### Added

**type `access_request_status`** — `PENDING`, `APPROVED`, `DENIED`, `CANCELLED`.
Completed requests are never deleted; the history stays available.

**table `access_requests`** (28th business table)

| Column | Type | Null | Meaning |
| --- | --- | --- | --- |
| `id` | `bigint` identity | N | PK |
| `requester_user_id` | `bigint` → users | N | RESTRICT: an access audit trail must not vanish |
| `role_at_request` | `access_level` | N | Stored, not derived, so an approved request still reads truthfully later |
| `requested_role` | `access_level` | N | |
| `status` | `access_request_status` | N | Defaults to `PENDING` |
| `requested_at` | `timestamptz` | N | |
| `decided_at` | `timestamptz` | Y | |
| `decided_by_user_id` | `bigint` → users | Y | |
| `decision_note` | `text` | Y | Optional, for the approver's reference |
| `created_at` / `updated_at` | `timestamptz` | N | |

Constraints — each one closes a way somebody could otherwise gain access they
were never granted:

- `CHECK requested_role <> 'VIEWER'` — the default level is not requestable.
- `CHECK requested_role > role_at_request` — only upward, using enum ordering.
- `CHECK` decision fields match status — a closed request always records who
  decided it and when.
- `CHECK status IN ('PENDING','CANCELLED') OR decided_by_user_id <> requester_user_id`
  — self-approval is impossible at the database level. CANCELLED is excluded
  because cancelling *is* the requester closing their own request.
- **Partial unique index** on `requester_user_id WHERE status = 'PENDING'` —
  one pending request per user, so two simultaneous submissions cannot both
  land. A race is settled by the database, not by a check that raced.

---

## 8. Why the enum types were recreated rather than altered

`ALTER TYPE ... ADD VALUE` can only append, and PostgreSQL cannot remove an enum
value at all. Appending would have put `VIEWER` **last** in a type whose declared
order *is* the privilege order, and would have left `downgrade()` unable to
reverse itself.

The migration instead renames the old type, creates the new one, and recasts the
dependent columns through `text`. That keeps the ordering meaningful, runs inside
one transaction, and downgrades cleanly — verified by an actual
`downgrade` → `upgrade` round trip.

No production data existed at the time: `users` and `user_activity_records` were
both empty, and no `data_editor_assignment` value had ever been written. This was
checked before the destructive part of the migration was written.

---

## 9. Effect on the Step 4 account bootstrap

Step 4 was blocked because `users.display_name` is NOT NULL and no
business-supplied names existed. Access Model v1.1 supersedes that approach
rather than working around it.

The bootstrap list now declares **email → role only**. The account itself is
created at the first verified Microsoft sign-in, where the display name arrives
from the Entra profile claims instead of from a guess. See
[`initial-access-seeding.md`](initial-access-seeding.md) and
[`../auth/microsoft-entra-setup.md`](../auth/microsoft-entra-setup.md).

`python -m app.db.seeds.initial_access --status` now reports binding status and
writes nothing. The `--apply` mode was removed: there is nothing left for it to
insert.

---

## 10. Verification

| Check | Result |
| --- | --- |
| `alembic upgrade head` on `tdms_dev` | 28 tables, 1 view, 15 enum types |
| `alembic check` | No new upgrade operations detected |
| `alembic downgrade -1` | Assignment column, CHECK and enum restored; `access_requests` removed; 27 tables |
| `alembic upgrade head` again | Identical to the first upgrade |
| `access_level` order | `VIEWER < DATA_EDITOR < ADMIN < SUPER_ADMIN` in PostgreSQL |
| `data_editor_assignment` type | Absent |

---

## 11. What did not change

No other Schema v1 table, column, constraint or index. The soft-delete column
group, the `trainer_availability_days` view, the composite college/campus key
and every reference-data relationship are exactly as approved on 10 August 2026.
