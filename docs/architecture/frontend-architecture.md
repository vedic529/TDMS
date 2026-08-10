# TDMS frontend architecture

## Layering

```
 app/            Routes only. A page file resolves metadata and renders one
                 feature component. No business logic lives here.
   │
 features/       One folder per work area: timetable, students, trainers,
                 reference-data, administration, auth, dev-tools, shared.
   │
 components/     ui/     design-system primitives (button, dialog, table…)
                 common/ reusable application components (DataTable,
                         ConfirmationDialog, PermissionGuard, states…)
   │
 lib/            Pure logic: permissions, environment, formatting, export,
                 CSV, student generation rules, open-decision register.
   │
 services/       TdmsClient interface, MockTdmsClient, ApiTdmsClient,
                 prototype storage, authentication adapters.
   │
 types/          SRS data types shared by everything above.
 mock-data/      Seeded demo dataset. Imported only by MockTdmsClient.
```

Two rules keep the layers honest:

1. **A page component never imports `mock-data/` and never touches
   `localStorage`.** It calls `getTdmsClient()`.
2. **A component never tests a role directly.** It calls a capability helper
   from `lib/permissions.ts` or uses `PermissionGuard` / `useCapability`.

## Data service

```
UI components
      │
      ▼
TdmsClient (services/tdms-client.ts)
      ├── MockTdmsClient   services/mock-tdms-client.ts
      └── ApiTdmsClient    services/api-tdms-client.ts
```

Every method is asynchronous, so replacing the prototype implementation with
HTTPS calls to FastAPI needs no change in any page. `getTdmsClient()` chooses the
implementation from `NEXT_PUBLIC_TDMS_DATA_MODE`.

`MockTdmsClient` reproduces the SRS behaviour that matters for review:

- soft deletion into a recycle area with deletion date, deleting user, reason and
  recovery deadline (DATA-04);
- a staging area for bulk import that is validated before anything is written
  (BULK-02);
- a user activity record for every action listed in LOG-01.

## Authentication

```
AuthProvider (services/auth/auth-provider.ts)
      ├── MockAuthProvider              development, no Microsoft call
      └── MicrosoftEntraAuthProvider    production, MSAL (wired after OD-01)
```

`TdmsAuthProvider` (a React context) holds the session, exposes `signIn`,
`signOut` and `refreshSession`, and derives the permission set once so every
consumer sees the same answer.

The Microsoft sign-in result and the TDMS access decision are separate values
(SRS 4.2). `MockAuthProvider` denies access for an `INACTIVE` or `DISABLED`
account even after a successful sign-in, and records the denial.

## Permissions

`lib/permissions.ts` is the only place a role is interpreted. It exports:

- capability helpers — `canCreateStudent`, `canCreateTimetable`,
  `canMaintainTrainerData`, `canManageUsers`, `canViewActivityRecords`, …
- `getPermissions(user)` returning the whole set for a page;
- `hasCapability(user, capability)` for the guard component;
- `canManageTargetUser(actor, target)` for the OD-05 Admin boundary;
- the role and assignment option lists — the role list contains exactly the
  three hierarchy levels, and work assignments are a separate list.

## Confirmation pattern

Every database-changing action follows the same shape, and no action happens on
a first click:

| Action | Sequence |
| --- | --- |
| Create | Form → Preview → Confirm → Save |
| Edit | Edit → Preview Changes → Confirm → Update |
| Delete | Select record → Display record → Mandatory reason → Confirm Delete → Soft delete |
| Import | Upload → Staging → Validation → Preview → Confirm → Save |
| Timetable generation | Generate → Preview → Validate → Confirm → Save |

The dialogs are shared components: `ConfirmationDialog`,
`ChangeSummaryDialog`, `DeleteConfirmationDialog`, plus `PreviewPanel` and
`ValidationPanel`. `window.confirm` is never used.

## Validation and unresolved rules

`ValidationIssue.severity` has three values:

| Severity | Meaning |
| --- | --- |
| `blocking` | Save stays unavailable until it is resolved |
| `advisory` | Shown for attention; does not block a save |
| `pending-approval` | The rule is an SRS open decision; the check is displayed and no pass/fail result is produced |

`features/timetable/validation.ts` separates checks derived from approved
reference data (trainer/facility/student-group clashes, capacity, approved
duration options, approved unit sequence, inactive trainer) from the checks
whose rules are not approved (break placement — OD-07; trainer physical/virtual
rule — OD-10; MSCRIS field rules — OD-11).

## Prototype storage

`services/prototype-storage.ts` owns every browser-storage key, all prefixed
`tdms.prototype.v1.`:

| Key | Contents |
| --- | --- |
| `tdms.prototype.v1.dataset` | The demo dataset with any changes made in the prototype |
| `tdms.prototype.v1.session` | The demo session |
| `tdms.prototype.v1.dev-identity` | The identity chosen in the development access preview |

Nothing else in the application reads or writes storage.

## Accessibility

- Semantic `<table>` markup with a sticky `<thead>`, `aria-sort` on sortable
  columns and an `aria-label` on every table.
- Every form control has a `<label>`; errors are announced with `role="alert"`
  and linked through `aria-describedby`.
- Dialogs are Radix primitives: focus trapping, `Esc` to close and restored
  focus on close.
- Status is always text plus an icon, never colour alone.
- A visible focus ring is applied globally through `:focus-visible`.
