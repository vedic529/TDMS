# TDMS Elevated Account Bootstrap

**Status:** implemented and tested. Superseded the Step 4 seed approach.
**Updated:** 11 August 2026 for [Access Model v1.1](access-model-v1.1.md).

---

## 1. What changed, and why

Step 4 tried to **insert** six accounts and was blocked: `users.display_name` is
NOT NULL and no business-supplied names existed. Deriving a name from the mailbox
was refused — `a.chattopadhyay` is a mailbox, not a person's name, and a guess
written into an authorisation record outlives everyone who remembers it was a
guess.

Access Model v1.1 removes the problem rather than working around it. The list now
declares **email → role only**, and the account is created at the **first
verified Microsoft sign-in**, where the display name arrives from the Entra
profile claims.

| | Step 4 | Now |
| --- | --- | --- |
| What the list holds | email, role, display name | **email + role** |
| Who creates the account | the seed script | **first verified sign-in** |
| Where the name comes from | had to be supplied | **Microsoft profile claims** |
| Command | `--dry-run` / `--apply` | `--status` (read-only) |
| Status | BLOCKED | **Implemented** |

`--apply` was removed: there is nothing left for it to insert. `--dry-run`
remains as an alias for `--status` so the documented command still works.

---

## 2. The approved elevated list

Held in `apps/api/app/db/seeds/manifest.py` — one place, imported by both the
sign-in provisioning path and the tests, so approval and enforcement cannot
drift apart.

| Role | Accounts |
| --- | --- |
| SUPER_ADMIN | `a.chattopadhyay@`, `w.rajjak@`, `v.yadav@`, `d.panda@` (all `chelsongordon.com`) |
| ADMIN | `c.dejsakultorn@chelsongordon.com`, `n.verma@chelsongordon.com` |
| DATA_EDITOR | **none** |
| VIEWER | **none** — it is the default, not a bootstrap role |

`n.verma@chelsongordon.com` moved from Super Admin to **Admin** under Access
Model v1.1 §5.

---

## 3. How an entry is used

**Exactly once**, at initial identity binding:

```
Microsoft verifies the person
  -> their tenant is on the allow-list
  -> no TDMS user has this (tid, oid)
  -> the verified email matches an entry here
  -> the account is created at that entry's role
```

After binding, the durable identity is `tid + oid` and the level is whatever the
user record says. The list is **never consulted again**. That is what makes two
things true:

- a later **demotion is not silently reversed** at the next sign-in;
- a **mailbox rename grants nothing** — the identity already matched, so it is a
  profile update.

A mailbox that has been reassigned to a different person cannot inherit the
previous holder's access either: an account already bound to an `oid` belongs to
that person, and a different `oid` presenting the same address is refused.

---

## 4. Why no Data Editors are bootstrapped

`@chelsongordon.com` and `@vconsultancy.com.au` were supplied as organisational
domains. **A domain is not an authorisation rule.** Belonging to one gets you
Viewer through the normal tenant rule, and nothing more.

Data Editor is granted by approving an access request or by a Super Admin role
change. Zero entries is the correct state, not an oversight.

---

## 5. Checking the status

The virtual environment must be activated — the command is a module inside it.

```powershell
cd C:\TDMS\apps\api
.\.venv\Scripts\Activate.ps1
```

```bash
python -m app.db.seeds.initial_access --status
```

**This writes nothing.** It reports, per approved address:

| Outcome | Meaning |
| --- | --- |
| `AWAITING_FIRST_SIGN_IN` | No account yet. Created when they first sign in. |
| `PROVISIONED_NOT_YET_LINKED` | An account exists but no Microsoft identity is bound. |
| `BOUND` | Account exists at the approved role with a Microsoft identity. |
| `ROLE_DIFFERS` | The account exists at a **different** level than approved. |
| `NOT_ACTIVE` | The account is INACTIVE or DISABLED. |

It also verifies the controlled access values exist as enums, that the obsolete
`data_editor_assignment` type is gone, and that no parallel `roles` table has
appeared alongside them. Exit code `0` when healthy, `1` when something is
flagged. The output never contains a credential or a connection string.

**Flagged items are reported, never repaired.** A role differing from the list
may be a deliberate Super Admin decision, and a bootstrap script that
"corrects" live authorisation is a privilege-escalation path wearing a helpful
face. Change a role in the administration dashboard, where it is recorded in the
activity records.

---

## 6. Notifications

The same file holds the notification routing, so the approver group and the
Super Admin list cannot disagree:

| | |
| --- | --- |
| Recipients | the **four Super Admins** |
| Not notified | `n.verma@chelsongordon.com` — that account is Admin |
| Sender | `v.yadav@chelsongordon.com` |

The email is a **notification only**: no approval token, no link that grants
anything. A Super Admin signs in and decides inside TDMS. Configuration:
[`../auth/microsoft-entra-setup.md`](../auth/microsoft-entra-setup.md) §5.

---

## 7. Adding an approved user later

1. Get the approval in writing.
2. For an **ongoing** change, use the administration dashboard — that is what it
   is for, and the change is recorded.
3. Edit the bootstrap list only when a **new environment** should provision that
   person at an elevated role from their first sign-in. Add the line, update
   `EXPECTED_COUNTS` in the same file, and run `--status`.

---

## 8. Testing

```bash
pytest tests/test_initial_access_seed.py -q
```

Runs against a temporary PostgreSQL database that the fixture creates, migrates
and drops. Covers: the exact four Super Admin and two Admin addresses; N. Verma
as Admin and not a notification recipient; no Viewer or Data Editor bootstrapped;
a domain is not an entry; case-insensitive matching; the four access-level enum
values in privilege order; the assignment type and column both gone; no password
column; and every status outcome including a flagged role that is reported but
not repaired.

Provisioning itself — JIT Viewer creation, elevated binding, tenant admission —
is tested in `tests/test_access_model_v11.py`.
