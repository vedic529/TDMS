# SRS traceability — frontend prototype

Where each SRS requirement is implemented in the frontend. Requirements that
depend on the backend, the database or an approved business rule are marked
accordingly.

## Access and permissions (ACC)

| ID | Where |
| --- | --- |
| ACC-01 | `lib/permissions.ts` — `TdmsRole` has exactly three values; `ROLE_OPTIONS` offers only those three |
| ACC-02 | `DataEditorAssignment` is a separate type; `ASSIGNMENT_OPTIONS` is separate from `ROLE_OPTIONS`; `AssignmentBadge` always renders beside `RoleBadge` |
| ACC-03 | Every capability helper returns true for `SUPER_ADMIN` |
| ACC-04 | Admin has every operational capability plus `manageUsers` and `viewActivityRecords` |
| ACC-05 | `canView` / `canExport` are true for every active user; create/edit/delete helpers test the work assignment |
| ACC-06 | `PermissionGuard` for actions, `(app)/layout.tsx` for routes, page-level capability checks before calling the service |
| ACC-07 | `MockAuthProvider.restoreSession()` re-reads the user record on every session refresh |
| ACC-08 | Denied sign-in produces a user activity record with result `Access denied` and no data change |

## Authentication (AUTH)

| ID | Where |
| --- | --- |
| AUTH-01 | `(app)/layout.tsx` redirects to `/login` without a session |
| AUTH-02 | `services/auth/entra-auth-provider.ts` is the Entra seam; `lib/env.ts` reports whether the tenant is configured |
| AUTH-03 | No password field exists anywhere; the login screen states TDMS never receives one |
| AUTH-04 | `MockAuthProvider.signIn()` matches the account to one internal `TdmsUser` |
| AUTH-05 | `accessDecisionFor()` denies `INACTIVE` and `DISABLED` accounts |
| AUTH-06 | The authenticated shell guards every operational route, including direct addresses |
| AUTH-07 | `/` and the login screen both redirect a granted user to `/timetable` |
| AUTH-08 | A failure returns `AuthFailure` and writes no session |
| AUTH-09 | Sign out is in the account menu. **Timeout: OD-03, not implemented** — stated in Account information |
| AUTH-10 | `AuthFailure.userMessage` is a general message; the correlation ID is shown as a reference |
| AUTH-11 | `AuthSession.correlationId` is stored and displayed in Account information |
| AUTH-12 | `restoreSession()` re-reads the user; the development preview demonstrates it |

## User activity records (LOG)

| ID | Where |
| --- | --- |
| LOG-01 | `MockTdmsClient` writes a record for create, edit, delete, restore, import and timetable save; `ExportMenu` and the bulk-import downloads write export records; the auth provider writes sign-in, sign-out and access-denied records |
| LOG-02 | `UserActivityRecord` carries every SRS 4.5 field |
| LOG-03 | `DeleteConfirmationDialog` requires a reason, and requires written detail for "Other" |
| LOG-04 | `canViewActivityRecords` — Super Admin and Admin only; the tab is not rendered otherwise |
| LOG-05 | The records view is read-only; the client exposes no edit or delete method |
| LOG-06 | No password or unnecessary personal data is written |
| LOG-07/08 | Retention — **OD-04, backend concern** |

## Timetable View and Management (TT)

| ID | Where |
| --- | --- |
| TT-01 | Landing route after sign-in |
| TT-02 | `FilterBar`: From Date, To Date, College, Campus, Qualification, Group |
| TT-03 | `MockTdmsClient.listTimetableSessions` uses `rangesOverlap`; the empty state says "No timetable sessions match the selected filters." |
| TT-04 | Create and Generate open `TimetableFormDrawer`; Preview precedes Save |
| TT-05 | Every controlled field is a reference-data dropdown |
| TT-06 | Trainer, facility and student-group clash checks are blocking; override is Admin/Super Admin only and records a reason |
| TT-07 | Each clash message names the conflicting record, day, time and date range |
| TT-08 | Approved duration options and approved unit sequence are checked |
| TT-09/10/11 | **OD-07** — displayed as an "Awaiting approval" check that produces no result |
| TT-12 | Preview never calls a write method; `canSave` gates the Save button |
| TT-13 | Save, edit, delete, cancel and export are all present and permission-gated |
| TT-14 | Every one of those actions writes a user activity record |
| TT-15 | `Facility` carries reference, campus, type, capacity and active status; **no fifth navigation page — OD-09** |

## Single Student Entry (SST)

| ID | Where |
| --- | --- |
| SST-01 | Search, create, view, edit and delete in `single-student-entry.tsx` |
| SST-02 | College → Campus → Qualification dependent dropdowns from reference data |
| SST-03 | `lib/student-rules.ts` — generated values, **labelled provisional** |
| SST-04 | Preview sheet shows the complete record and every validation message; nothing is written |
| SST-05 | Blank Student ID is a Zod error; duplicates are checked through `isStudentIdAvailable` |
| SST-06 | Save is disabled until `canSave`, then a confirmation dialog is required |
| SST-07 | `ChangeSummaryDialog` lists old → new for every changed field |
| SST-08 | `DeleteConfirmationDialog` with mandatory reason and soft deletion |
| SST-09 | Every outcome writes a user activity record |
| SST-10 | **OD-08** — CT definition, Course Duration Option rule and week calculation marked "Awaiting approval" |

## Bulk Student Import (BULK)

| ID | Where |
| --- | --- |
| BULK-01 | `FileDropzone` accepts only `.csv` and `.xlsx`; anything else is rejected with a message |
| BULK-02 | `stageImport` writes to the staging area only |
| BULK-03 | Upload information card: file name, size, date and time, uploading user, row count, source row numbers |
| BULK-04 | `services/import-validation.ts` checks required columns and values, formats, duplicate Student IDs and approved mappings |
| BULK-05 | Each issue names the source row, Student ID, field, plain-language message and status |
| BULK-06 | Inline correction, row exclusion and Revalidate |
| BULK-07 | Save to Database is disabled while a selected staged row is blocking |
| BULK-08 | `saveImport` writes the confirmed set in one operation |
| BULK-09 | `ImportSummary` reports inserted, excluded, duplicate, corrected, rejected and unmatched |
| BULK-10 | Preview and issue report download as CSV; **XLSX is a documented fallback** |
| BULK-11 | No database-file download exists |
| BULK-12 | Bulk deletion is not in the prototype; single deletion follows the full confirmation flow |
| BULK-13 | The import result writes a user activity record with the file reference and counts |

## Trainer Data (TRN)

| ID | Where |
| --- | --- |
| TRN-01 | No results until a qualification is selected, in both the UI and `listTrainers` |
| TRN-02 | "Number of Trainers Available: X" badge |
| TRN-03 | Table plus detail drawer: units, locations, delivery type, weekday availability |
| TRN-04 | Inactive trainers are shown and marked INACTIVE; selecting one is a blocking timetable validation error |
| TRN-05 | `ExportMenu` on the filtered result |
| TRN-06 | `canMaintainTrainerData` — Admin and Super Admin only |
| TRN-07 | **OD-10** — the rule is displayed as unapproved and is not applied |
| TRN-08 | Create, edit, delete and export write user activity records |

## College and Course Reference Data (COL)

| ID | Where |
| --- | --- |
| COL-01 | Campus depends on College everywhere |
| COL-02 | `offeringsFor(collegeId, campusId)` limits qualifications to the selection |
| COL-03 | All displayed values come from reference data |
| COL-04 | Duplicate offering check in the course form (college + campus + VET code) |
| COL-05 | Inactive and Superseded courses stay visible; only active offerings are selectable |
| COL-06 | `ExportMenu` on both tabs |
| COL-07 | `canMaintainCourseData` — Admin and Super Admin only |
| COL-08 | Every create, edit, delete and export writes a user activity record |
| COL-09 | **OD-09** — facility data is used for selection, capacity and clash checking only |

## Data (DATA) and non-functional (NFR)

| ID | Where |
| --- | --- |
| DATA-01 | Duplicate Student ID checks in single entry and bulk import |
| DATA-02 | Timetable records reference campus, trainer, facility and unit values |
| DATA-03 | Inactive/superseded values retained, excluded from new selections |
| DATA-04 | `SoftDeleteMetadata` on every deletable record; shown in the recycle area |
| DATA-05 | Bulk import saves the confirmed set together |
| DATA-06 | Prototype storage is namespaced and labelled as demo data throughout |
| DATA-07 | No database connection exists |
| NFR-01/02 | No password handled; only the fields the SRS defines are displayed or exported |
| NFR-04 | Consistent page names, controlled selections, preview/confirm steps, plain-language messages |
| NFR-08 | Display, access rules, validation and data services are separate modules |
| NFR-09 | See the accessibility section of `frontend-architecture.md` |
