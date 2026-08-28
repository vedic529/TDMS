'use client';

import * as React from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Download,
  FileSpreadsheet,
  Lightbulb,
  ListChecks,
  Loader2,
  RefreshCw,
  Save,
  Undo2,
  X,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { FileDropzone } from '@/components/common/file-dropzone';
import { ImportStatusBadge } from '@/components/common/status-badge';
import { ConfirmationDialog } from '@/components/common/confirmation-dialog';
import { CountTile } from '@/components/common/import-summary';
import { EmptyState, ReadOnlyNotice } from '@/components/common/states';
import { useAuth } from '@/features/auth/auth-context';
import {
  isBlockingStagedStatus,
  STAGED_STATUS_LABELS,
  studentsApi,
  type ImportApplyResult,
  type ImportReview,
  type RowPatch,
  type StagedRow,
} from '@/services/students-api';
import { exportRows } from '@/lib/export';
import { today } from '@/lib/format';
import { readOnlyReason } from '@/lib/permissions';
import { INTERFACE_NAMES } from '@/lib/interface-names';
import type { ExportFormat } from '@/types/common';
import type { StagedRowStatus } from '@/types/import';

/**
 * The working columns, in the approved template's order. The label is the same
 * string the API accepts as a correction column, so a corrected cell needs no
 * translation table on the way back.
 *
 * **Group is not here.** Group is derived from the matched rolling-timetable
 * intake and is never typed; a Group column in the uploaded file is ignored and
 * reported as a note (rule 2.2).
 */
const EDITABLE_COLUMNS: Array<{ label: string; field: keyof StagedRow; width?: string }> = [
  { label: 'Student ID', field: 'student_id_value', width: 'w-36' },
  { label: 'First Name', field: 'first_name_value', width: 'w-32' },
  { label: 'Last Name', field: 'last_name_value', width: 'w-32' },
  { label: 'College', field: 'college_value', width: 'w-40' },
  { label: 'Campus', field: 'campus_value', width: 'w-32' },
  { label: 'Qualification', field: 'qualification_value', width: 'w-32' },
  { label: 'CT Student', field: 'ct_student_value', width: 'w-24' },
  { label: 'CoE / Non-CoE', field: 'coe_status_value', width: 'w-28' },
  { label: 'Status', field: 'status_value', width: 'w-32' },
  { label: 'Proposed Start Date', field: 'proposed_start_date_value', width: 'w-36' },
  { label: 'Proposed End Date', field: 'proposed_end_date_value', width: 'w-36' },
];

const EXCLUDED = 'EXCLUDED_BY_USER';

/** The API's staged-row status rendered with the existing badge vocabulary. */
function statusLabel(status: string): StagedRowStatus {
  return (STAGED_STATUS_LABELS[status] ?? status) as StagedRowStatus;
}

function draftValue(row: StagedRow, field: keyof StagedRow, drafts: Drafts): string {
  const pending = drafts[row.id]?.[field as string];
  if (pending !== undefined) return pending;
  const value = row[field];
  return value == null ? '' : String(value);
}

type Drafts = Record<number, Record<string, string>>;

/**
 * Bulk Student Import (SRS 7) — on the real TDMS API.
 *
 * The uploaded file is sent to `POST /students/import/stage`, which parses
 * **CSV and XLSX with the same code path**, resolves the references, derives the
 * Intake and Group from the rolling timetable, and returns the staged rows. The
 * browser never parses a workbook, and no demo data is ever substituted.
 *
 * Nothing reaches `students` until the confirmation is accepted (BULK-02).
 */
export function BulkStudentImport() {
  const { user, permissions } = useAuth();
  const [review, setReview] = React.useState<ImportReview | null>(null);
  const [drafts, setDrafts] = React.useState<Drafts>({});
  const [result, setResult] = React.useState<ImportApplyResult | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [confirmOpen, setConfirmOpen] = React.useState(false);

  const canImport = permissions.maintainStudentData;
  const errorsRef = React.useRef<HTMLDivElement>(null);

  const rows = React.useMemo(() => review?.rows ?? [], [review]);
  const errorRows = React.useMemo(() => rows.filter((row) => isBlockingStagedStatus(row.status)), [rows]);
  const pendingCorrections = React.useMemo(
    () => Object.values(drafts).reduce((total, columns) => total + Object.keys(columns).length, 0),
    [drafts],
  );

  /**
   * Blocking problems gathered by field and message.
   *
   * One systemic mistake — a college spelled differently from the approved
   * record — produces one problem repeated across hundreds of rows. Showing the
   * distinct problems and how many rows each affects makes that visible at a
   * glance instead of asking the user to scroll a long table.
   */
  const errorGroups = React.useMemo(() => {
    const groups = new Map<string, { field: string; message: string; rows: number[] }>();
    errorRows.forEach((row) => {
      row.issues
        .filter((issue) => issue.issue_status !== 'NOTE')
        .forEach((issue) => {
          const key = `${issue.field_name}||${issue.message}`;
          const existing = groups.get(key);
          if (existing) existing.rows.push(row.source_row_number);
          else groups.set(key, { field: issue.field_name, message: issue.message, rows: [row.source_row_number] });
        });
    });
    return [...groups.values()].sort((a, b) => b.rows.length - a.rows.length);
  }, [errorRows]);

  /**
   * Rows stored with no intake because the qualification has no rolling
   * timetable at the duration their dates imply (rule 2.5 Step 3).
   *
   * These do not block the save — the approved rule is "report, and store" —
   * but they are a real problem to fix, so they are listed with the durations
   * that qualification actually runs.
   */
  const tbdRows = React.useMemo(
    () => rows.filter((row) => row.intake_match_status === 'TBD' && row.status !== EXCLUDED),
    [rows],
  );

  /** TBD rows gathered by qualification, so one choice can settle them all. */
  const tbdByQualification = React.useMemo(() => {
    const groups = new Map<string, StagedRow[]>();
    tbdRows.forEach((row) => {
      const code = (row.qualification_value ?? '').trim().toUpperCase();
      groups.set(code, [...(groups.get(code) ?? []), row]);
    });
    return [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [tbdRows]);

  function chooseDuration(targets: StagedRow[], weeks: number, label: string) {
    void patch(
      targets.map((row) => ({ row_id: row.id, duration_weeks: weeks })),
      label,
    );
  }

  /**
   * Unmatched College / Campus / Qualification values, gathered by the value
   * itself rather than by row.
   *
   * One campus spelled differently from the approved record is a single problem
   * on hundreds of rows, and it is settled once: raise it as a suggestion for an
   * admin to add or map, or accept it as an exception. Grouping is what makes
   * that one click instead of hundreds.
   *
   * A row whose three references all resolved but has no approved offering is
   * deliberately excluded — that is a correction, not a value to suggest.
   */
  const unmatchedGroups = React.useMemo(() => {
    const byEntity: Record<string, { entity: 'college' | 'campus' | 'qualification'; resolved: keyof StagedRow; value: keyof StagedRow }> = {
      College: { entity: 'college', resolved: 'resolved_college_id', value: 'college_value' },
      Campus: { entity: 'campus', resolved: 'resolved_campus_id', value: 'campus_value' },
      Qualification: { entity: 'qualification', resolved: 'resolved_qualification_id', value: 'qualification_value' },
    };
    const groups = new Map<
      string,
      { entity: 'college' | 'campus' | 'qualification'; label: string; value: string; rows: StagedRow[] }
    >();

    rows
      .filter((row) => row.status === 'UNMATCHED_REFERENCE')
      .forEach((row) => {
        row.issues
          .filter((issue) => issue.issue_status === 'BLOCK')
          .forEach((issue) => {
            const mapping = byEntity[issue.field_name];
            // Only a genuinely unresolved entity can be suggested.
            if (!mapping || row[mapping.resolved] != null) return;
            const value = String(row[mapping.value] ?? '').trim();
            if (!value) return;
            const key = `${mapping.entity}||${value.toUpperCase()}`;
            const existing = groups.get(key);
            if (existing) existing.rows.push(row);
            else groups.set(key, { entity: mapping.entity, label: issue.field_name, value, rows: [row] });
          });
      });
    return [...groups.values()].sort((a, b) => b.rows.length - a.rows.length);
  }, [rows]);

  function resolveReferenceForAll(
    group: { entity: 'college' | 'campus' | 'qualification'; label: string; value: string; rows: StagedRow[] },
    choice: 'RAISE' | 'EXCEPT',
  ) {
    void patch(
      group.rows.map((row) => ({ row_id: row.id, reference_entity: group.entity, reference_choice: choice })),
      choice === 'RAISE'
        ? `${group.label} “${group.value}” raised as a suggestion`
        : `${group.label} “${group.value}” accepted as an exception`,
    );
  }

  /** Exclude every blocking row at once, so a large file can still be saved. */
  function excludeAllBlocking() {
    void patch(
      errorRows.map((row) => ({ row_id: row.id, exclude: true })),
      `${errorRows.length} blocking ${errorRows.length === 1 ? 'row' : 'rows'} excluded`,
    );
  }

  function goToErrors() {
    errorsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    errorsRef.current?.focus({ preventScroll: true });
  }

  function describe(error: unknown): string {
    return error instanceof Error ? error.message : 'Try again, or contact the TDMS administrator.';
  }

  async function handleFile(file: File) {
    if (!user) return;
    setBusy(true);
    setResult(null);
    setDrafts({});
    try {
      const staged = await studentsApi.stageImport(file);
      setReview(staged);
      toast.success('File loaded into the staging area', {
        description: `${staged.rows_read} rows were read from ${staged.file_name}. Nothing has been written to the database.`,
      });
    } catch (error) {
      toast.error('The file could not be read', { description: describe(error) });
    } finally {
      setBusy(false);
    }
  }

  /** Send row changes and replace the review with the API's re-validated one. */
  async function patch(items: RowPatch[], successMessage?: string) {
    if (!review || items.length === 0) return;
    setBusy(true);
    try {
      const updated = await studentsApi.patchImportRows(review.batch_id, items);
      setReview(updated);
      setDrafts({});
      if (successMessage) {
        const blocking = updated.rows.filter((row) => isBlockingStagedStatus(row.status)).length;
        toast.success(successMessage, {
          description: `${updated.counts['Ready'] ?? 0} ready, ${blocking} still blocking, ${updated.counts['Excluded by user'] ?? 0} excluded.`,
        });
      }
    } catch (error) {
      toast.error('The change could not be applied', { description: describe(error) });
    } finally {
      setBusy(false);
    }
  }

  function editCell(rowId: number, field: keyof StagedRow, value: string) {
    setDrafts((current) => ({ ...current, [rowId]: { ...(current[rowId] ?? {}), [field as string]: value } }));
  }

  /** Send every edited cell as a correction, then re-validate (checks P11). */
  async function revalidate() {
    if (!review) return;
    const items: RowPatch[] = Object.entries(drafts).map(([rowId, columns]) => ({
      row_id: Number(rowId),
      corrections: Object.entries(columns).map(([field, value]) => ({
        column: EDITABLE_COLUMNS.find((column) => column.field === field)?.label ?? field,
        value,
      })),
    }));
    if (items.length === 0) {
      // Nothing edited: ask the API to re-check the batch as it stands.
      await patch([{ row_id: review.rows[0]?.id ?? 0 }], 'Validation complete');
      return;
    }
    await patch(items, 'Validation complete');
  }

  function toggleExclude(row: StagedRow) {
    void patch([{ row_id: row.id, exclude: row.status !== EXCLUDED }]);
  }

  function decideDuplicate(rowId: number, decision: 'KEEP_STORED' | 'KEEP_INCOMING') {
    void patch([{ row_id: rowId, duplicate_decision: decision }], 'Duplicate decision recorded');
  }

  function setEnrolmentStatus(rowId: number, statusValue: string) {
    void patch([{ row_id: rowId, status_value: statusValue }], 'Enrolment status recorded');
  }

  function resolveReference(
    rowId: number,
    entity: 'college' | 'campus' | 'qualification',
    choice: 'RAISE' | 'EXCEPT',
  ) {
    void patch(
      [{ row_id: rowId, reference_entity: entity, reference_choice: choice }],
      choice === 'RAISE' ? 'Suggestion raised' : 'Exception accepted',
    );
  }

  async function save() {
    if (!review) return;
    setBusy(true);
    try {
      const applied = await studentsApi.applyImport(review.batch_id);
      setResult(applied);
      setReview(null);
      setConfirmOpen(false);
      toast.success('Bulk student import saved', {
        description: `${applied.inserted} student ${applied.inserted === 1 ? 'record was' : 'records were'} added and a user activity record was created.`,
      });
    } catch (error) {
      toast.error('The import could not be saved', { description: describe(error) });
    } finally {
      setBusy(false);
    }
  }

  function downloadPreview(format: ExportFormat) {
    if (!review) return;
    const outcome = exportRows({
      format,
      baseFileName: `tdms-bulk-import-preview-${today()}`,
      sheetName: 'Staged rows',
      rows,
      columns: [
        { header: 'Source Row Number', value: (row) => row.source_row_number },
        ...EDITABLE_COLUMNS.map((column) => ({
          header: column.label,
          value: (row: StagedRow) => String(row[column.field] ?? ''),
        })),
        { header: 'Intake (derived)', value: (row) => row.derived_intake_label ?? '' },
        { header: 'Group (derived)', value: (row) => row.derived_group_code ?? '' },
        { header: 'Status', value: (row) => statusLabel(row.status) },
      ],
    });
    toast.success('Preview downloaded', { description: `${outcome.rowCount} staged rows in ${outcome.fileName}.` });
  }

  function downloadIssues(format: ExportFormat) {
    if (!review) return;
    const issueRows = rows.flatMap((row) =>
      row.issues.map((issue) => ({
        sourceRowNumber: row.source_row_number,
        studentId: row.student_id_value ?? '',
        status: statusLabel(row.status),
        field: issue.field_name,
        message: issue.message,
      })),
    );
    const outcome = exportRows({
      format,
      baseFileName: `tdms-bulk-import-issues-${today()}`,
      sheetName: 'Validation issues',
      rows: issueRows,
      columns: [
        { header: 'Source Row Number', value: (row) => row.sourceRowNumber },
        { header: 'Student ID', value: (row) => row.studentId },
        { header: 'Issue Status', value: (row) => row.status },
        { header: 'Field', value: (row) => row.field },
        { header: 'Validation Message', value: (row) => row.message },
      ],
    });
    toast.success('Issue report downloaded', { description: `${outcome.rowCount} issues in ${outcome.fileName}.` });
  }

  function downloadTemplate() {
    exportRows({
      format: 'csv',
      baseFileName: 'tdms-bulk-student-import-template',
      rows: [] as Array<Record<string, string>>,
      columns: EDITABLE_COLUMNS.filter((column) => column.label !== 'Status')
        .map((column) => ({ header: column.label, value: () => '' }))
        .concat([
          { header: 'Personal Email', value: () => '' },
          { header: 'Primary Phone', value: () => '' },
        ]),
    });
    toast.success('Template downloaded', {
      description: 'Use this template for the bulk student import. CSV and XLSX are both accepted.',
    });
  }

  const counts = review?.counts ?? null;
  const blocking = errorRows.length;
  const canSave = Boolean(review?.can_apply) && (counts?.['Ready'] ?? 0) > 0;

  return (
    <div className="space-y-5">
      {!canImport && <ReadOnlyNotice message={readOnlyReason(user, INTERFACE_NAMES.bulkStudentImport)} />}

      <Card>
        <CardHeader className="flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>Upload a student file</CardTitle>
            <CardDescription>
              CSV and XLSX are both read by the TDMS API. Uploaded rows are held in a staging area and checked before
              anything is written to the database.
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={downloadTemplate}>
            <Download aria-hidden="true" />
            Download template
          </Button>
        </CardHeader>
        <CardContent>
          <FileDropzone
            onFileSelected={(file) => void handleFile(file)}
            hint="Preview does not write to the database."
            disabled={!canImport || busy}
            disabledMessage={
              canImport ? undefined : 'Processing a bulk student import is outside your assigned work area.'
            }
          />
        </CardContent>
      </Card>

      {review && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Upload information</CardTitle>
              <CardDescription>Batch reference {review.batch_reference}</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <p className="text-[12px] text-muted-foreground">File name</p>
                <p className="truncate text-[13px] font-medium" title={review.file_name}>
                  {review.file_name}
                </p>
              </div>
              <div>
                <p className="text-[12px] text-muted-foreground">Uploading user</p>
                <p className="text-[13px] font-medium">{user?.displayName ?? '—'}</p>
              </div>
              <div>
                <p className="text-[12px] text-muted-foreground">Number of rows</p>
                <p className="text-[13px] font-medium tabular">{review.rows_read}</p>
              </div>
              <div>
                <p className="text-[12px] text-muted-foreground">Batch status</p>
                <p className="text-[13px] font-medium">{review.status}</p>
              </div>
            </CardContent>
          </Card>

          {counts && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              <CountTile label="Ready" value={counts['Ready'] ?? 0} tone="success" />
              <CountTile label="Needs correction" value={counts['Needs correction'] ?? 0} tone="warning" />
              <CountTile label="Duplicate" value={counts['Duplicate'] ?? 0} tone="destructive" />
              <CountTile label="Unmatched reference" value={counts['Unmatched reference'] ?? 0} tone="destructive" />
              <CountTile label="Excluded by user" value={counts['Excluded by user'] ?? 0} tone="muted" />
            </div>
          )}

          {review.duplicates.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Duplicate Student IDs need a decision</CardTitle>
                <CardDescription>
                  A repeat Student ID is never resolved silently. Choose which record survives, or set a different
                  status on each enrolment.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {review.duplicates.map((duplicate) => {
                  const row = rows.find((item) => item.id === duplicate.staged_row_id);
                  const sameQualification = duplicate.scope === 'SAME_QUALIFICATION';
                  return (
                    <div key={duplicate.staged_row_id} className="rounded-lg border border-border p-4">
                      <div className="mb-3 flex flex-wrap items-center gap-2">
                        <Copy aria-hidden="true" className="size-4 text-muted-foreground" />
                        <span className="text-[13px] font-medium">
                          Source row {row?.source_row_number} · {row?.student_id_value}
                        </span>
                        <Badge variant={sameQualification ? 'destructive' : 'info'}>
                          {sameQualification ? 'Same qualification' : 'Different qualification'}
                        </Badge>
                      </div>

                      <TableContainer className="mb-3">
                        <Table aria-label={`Stored and incoming values for ${row?.student_id_value}`}>
                          <TableHeader>
                            <TableRow className="hover:bg-transparent">
                              <TableHead className="w-48">Field</TableHead>
                              <TableHead>Stored record ({duplicate.existing_qualification_code})</TableHead>
                              <TableHead>Incoming row ({duplicate.incoming_qualification_code})</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {duplicate.fields.map((field) => (
                              <TableRow key={field.field} className={field.differs ? 'bg-warning/10' : undefined}>
                                <TableCell className="text-[12px] text-muted-foreground">{field.field}</TableCell>
                                <TableCell className="text-[13px]">{field.stored || '—'}</TableCell>
                                <TableCell className="text-[13px] font-medium">{field.incoming || '—'}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>

                      {sameQualification ? (
                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            variant={row?.duplicate_decision === 'KEEP_STORED' ? 'default' : 'outline'}
                            onClick={() => decideDuplicate(duplicate.staged_row_id, 'KEEP_STORED')}
                            disabled={!canImport || busy}
                          >
                            Keep the stored record
                          </Button>
                          <Button
                            size="sm"
                            variant={row?.duplicate_decision === 'KEEP_INCOMING' ? 'default' : 'outline'}
                            onClick={() => decideDuplicate(duplicate.staged_row_id, 'KEEP_INCOMING')}
                            disabled={!canImport || busy}
                          >
                            Keep the incoming record
                          </Button>
                        </div>
                      ) : (
                        <div className="space-y-2">
                          <p className="text-[12px] text-muted-foreground">
                            The stored enrolment is <strong>{duplicate.existing_status}</strong>. Set a different status
                            for this new enrolment — only one may be ACTIVE.
                          </p>
                          <div className="flex flex-wrap gap-2">
                            {['ACTIVE', 'COMPLETED', 'CANCELLED', 'NOT_YET_STARTED']
                              .filter((value) => value !== duplicate.existing_status)
                              .map((value) => (
                                <Button
                                  key={value}
                                  size="sm"
                                  variant={row?.status_value === value ? 'default' : 'outline'}
                                  onClick={() => setEnrolmentStatus(duplicate.staged_row_id, value)}
                                  disabled={!canImport || busy}
                                >
                                  {value.replace(/_/g, ' ')}
                                </Button>
                              ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle>Staging area</CardTitle>
                <CardDescription>
                  Correct a value directly in the table, or exclude a row. Intake and Group are derived by the system
                  from the rolling timetable and cannot be typed.
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm">
                      <Download aria-hidden="true" />
                      Download preview
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuLabel>Staged rows</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onSelect={() => downloadPreview('csv')}>Export CSV</DropdownMenuItem>
                    <DropdownMenuItem onSelect={() => downloadPreview('xlsx')}>Export XLSX</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm">
                      <Download aria-hidden="true" />
                      Download issue report
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuLabel>Validation issues</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onSelect={() => downloadIssues('csv')}>Export CSV</DropdownMenuItem>
                    <DropdownMenuItem onSelect={() => downloadIssues('xlsx')}>Export XLSX</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>

                <Button variant="outline" size="sm" onClick={() => void revalidate()} disabled={busy || !canImport}>
                  {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RefreshCw aria-hidden="true" />}
                  {pendingCorrections > 0 ? `Apply ${pendingCorrections} correction(s)` : 'Revalidate'}
                </Button>
                <Button size="sm" onClick={() => setConfirmOpen(true)} disabled={!canSave || busy || !canImport}>
                  <Save aria-hidden="true" />
                  Save to Database
                </Button>
              </div>
            </CardHeader>

            <CardContent className="space-y-4">
              {blocking > 0 ? (
                <Alert variant="warning">
                  <AlertTriangle aria-hidden="true" />
                  <div className="space-y-2">
                    <AlertTitle>
                      {blocking} {blocking === 1 ? 'row has' : 'rows have'} a blocking problem
                    </AlertTitle>
                    <AlertDescription>
                      Save to Database stays unavailable until every staged row is Ready or excluded.
                    </AlertDescription>
                    <Button variant="outline" size="sm" onClick={goToErrors}>
                      <ListChecks aria-hidden="true" />
                      Go to the {blocking} identified {blocking === 1 ? 'error' : 'errors'}
                    </Button>
                  </div>
                </Alert>
              ) : (
                <Alert variant="success">
                  <CheckCircle2 aria-hidden="true" />
                  <div className="space-y-2">
                    <AlertTitle>No blocking problem remains</AlertTitle>
                    <AlertDescription>
                      {counts?.['Ready'] ?? 0} rows will be written when you confirm the save.
                      {tbdRows.length > 0 &&
                        ` ${tbdRows.length} of them have no intake yet and would save as TBD.`}
                    </AlertDescription>
                    {tbdRows.length > 0 && (
                      <Button variant="outline" size="sm" onClick={goToErrors}>
                        <ListChecks aria-hidden="true" />
                        Resolve the {tbdRows.length} TBD {tbdRows.length === 1 ? 'intake' : 'intakes'}
                      </Button>
                    )}
                  </div>
                </Alert>
              )}

              <TableContainer className="max-h-[32rem]">
                <Table aria-label="Bulk student import staging area">
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="w-16">Source row</TableHead>
                      {EDITABLE_COLUMNS.map((column) => (
                        <TableHead key={column.label} className={column.width}>
                          {column.label}
                        </TableHead>
                      ))}
                      <TableHead className="w-56">Intake (derived)</TableHead>
                      <TableHead className="w-24">Group</TableHead>
                      <TableHead className="w-40">Status</TableHead>
                      <TableHead className="min-w-72">Issue</TableHead>
                      <TableHead className="w-28 text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((row) => {
                      const excluded = row.status === EXCLUDED;
                      const issueFields = new Set(row.issues.map((issue) => issue.field_name));
                      return (
                        <TableRow key={row.id} className={excluded ? 'opacity-60' : undefined}>
                          <TableCell className="tabular">{row.source_row_number}</TableCell>
                          {EDITABLE_COLUMNS.map((column) => (
                            <TableCell key={column.label}>
                              <Input
                                value={draftValue(row, column.field, drafts)}
                                onChange={(event) => editCell(row.id, column.field, event.target.value)}
                                disabled={excluded || !canImport}
                                aria-invalid={issueFields.has(column.label) || undefined}
                                aria-label={`${column.label} for source row ${row.source_row_number}`}
                                className="h-8 text-[13px]"
                              />
                            </TableCell>
                          ))}
                          <TableCell className="text-[12px]">
                            {row.derived_intake_label ? (
                              <span title={row.derived_intake_label}>{row.derived_intake_label}</span>
                            ) : (
                              <Badge variant={row.intake_match_status === 'NOT_APPLICABLE' ? 'neutral' : 'warning'}>
                                {row.intake_match_status === 'NOT_APPLICABLE' ? 'Credit Transfer' : 'TBD'}
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell className="text-[13px]">{row.derived_group_code ?? '—'}</TableCell>
                          <TableCell>
                            <span className="flex flex-col items-start gap-1">
                              <ImportStatusBadge status={statusLabel(row.status)} />
                            </span>
                          </TableCell>
                          <TableCell>
                            {row.issues.length === 0 ? (
                              <span className="text-[12px] text-muted-foreground">—</span>
                            ) : (
                              <ul className="space-y-1">
                                {row.issues.map((issue, index) => (
                                  <li
                                    key={index}
                                    className={`text-[12px] leading-relaxed ${
                                      issue.issue_status === 'NOTE' ? 'text-muted-foreground' : 'text-destructive'
                                    }`}
                                  >
                                    <span className="font-medium">{issue.field_name}:</span> {issue.message}
                                  </li>
                                ))}
                              </ul>
                            )}
                            {row.status === 'UNMATCHED_REFERENCE' && canImport && (
                              <div className="mt-2 flex flex-wrap gap-1">
                                {(['college', 'campus', 'qualification'] as const)
                                  .filter((entity) =>
                                    row.issues.some((issue) =>
                                      issue.field_name.toLowerCase().includes(entity === 'qualification' ? 'qualification' : entity),
                                    ),
                                  )
                                  .map((entity) => (
                                    <React.Fragment key={entity}>
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        className="h-6 text-[11px]"
                                        onClick={() => resolveReference(row.id, entity, 'RAISE')}
                                        disabled={busy}
                                      >
                                        Raise {entity}
                                      </Button>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-6 text-[11px]"
                                        onClick={() => resolveReference(row.id, entity, 'EXCEPT')}
                                        disabled={busy}
                                      >
                                        Except
                                      </Button>
                                    </React.Fragment>
                                  ))}
                              </div>
                            )}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button variant="ghost" size="sm" onClick={() => toggleExclude(row)} disabled={!canImport || busy}>
                              {excluded ? (
                                <>
                                  <Undo2 aria-hidden="true" />
                                  Include
                                </>
                              ) : (
                                <>
                                  <X aria-hidden="true" />
                                  Exclude
                                </>
                              )}
                            </Button>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>

          {(blocking > 0 || tbdRows.length > 0) && (
            // The scroll target for "Go to the identified errors". A plain
            // wrapper holds the ref so it never depends on a styled component
            // forwarding one; `scroll-mt-24` keeps the sticky header clear.
            <div ref={errorsRef} tabIndex={-1} className="scroll-mt-24 outline-none">
            <Card>
              <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>
                    Errors identified
                    {blocking > 0 && ` · ${blocking} blocking`}
                    {tbdRows.length > 0 && ` · ${tbdRows.length} to resolve`}
                  </CardTitle>
                  <CardDescription>
                    A blocking row stops the save until it is corrected or excluded. A row to resolve will save as it
                    stands, but is worth settling first.
                  </CardDescription>
                </div>
                {blocking > 0 && (
                  <Button variant="outline" size="sm" onClick={excludeAllBlocking} disabled={!canImport || busy}>
                    <X aria-hidden="true" />
                    Exclude all {blocking}
                  </Button>
                )}
              </CardHeader>

              <CardContent className="space-y-5">
                {unmatchedGroups.length > 0 && (
                  <div className="space-y-3">
                    <div>
                      <p className="text-[13px] font-medium">
                        Values that are not approved records · {unmatchedGroups.length}{' '}
                        {unmatchedGroups.length === 1 ? 'value' : 'values'}
                      </p>
                      <p className="text-[12px] text-muted-foreground">
                        Correct the spelling in the staging area, or settle the value here for every row at once.
                        <strong> Raise suggestion</strong> sends it to the reference-data queue, where an admin adds it
                        for the college or maps it to the approved record. <strong>Accept exception</strong> leaves the
                        value unapproved, and those rows are not written.
                      </p>
                    </div>

                    {unmatchedGroups.map((group) => (
                      <div
                        key={`${group.entity}-${group.value}`}
                        className="rounded-md border border-border bg-muted/40 px-3 py-3"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="destructive" className="tabular">
                            {group.rows.length}
                          </Badge>
                          <span className="text-[13px] font-medium">{group.label}</span>
                          <span className="text-[13px]">“{group.value}”</span>
                          <span className="text-[11px] text-muted-foreground">
                            is not an approved record · rows{' '}
                            {group.rows.slice(0, 8).map((row) => row.source_row_number).join(', ')}
                            {group.rows.length > 8 ? `, +${group.rows.length - 8} more` : ''}
                          </span>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <span className="text-[12px] font-medium">
                            Apply to all {group.rows.length} {group.rows.length === 1 ? 'row' : 'rows'}:
                          </span>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 text-[12px]"
                            onClick={() => resolveReferenceForAll(group, 'RAISE')}
                            disabled={!canImport || busy}
                          >
                            <Lightbulb aria-hidden="true" />
                            Raise suggestion
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 text-[12px]"
                            onClick={() => resolveReferenceForAll(group, 'EXCEPT')}
                            disabled={!canImport || busy}
                          >
                            Accept exception
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {tbdRows.length > 0 && (
                  <div className="space-y-3">
                    <div>
                      <p className="text-[13px] font-medium">
                        No rolling timetable at the uploaded duration · {tbdRows.length}{' '}
                        {tbdRows.length === 1 ? 'row' : 'rows'}
                      </p>
                      <p className="text-[12px] text-muted-foreground">
                        These rows save with Intake <strong>TBD</strong>. Choose a duration the qualification actually
                        runs and the intake is assigned. The uploaded Proposed Start and End dates are never changed —
                        the choice is stored as the student&apos;s approved Course Duration Option.
                      </p>
                    </div>

                    {tbdByQualification.map(([code, group]) => {
                      const options = review.duration_options?.[code] ?? [];
                      const shown = group.slice(0, 25);
                      return (
                        <div key={code || 'unknown'} className="rounded-md border border-border bg-muted/40 px-3 py-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="warning" className="tabular">
                              {group.length}
                            </Badge>
                            <span className="text-[13px] font-medium">{code || '(no qualification)'}</span>
                            <span className="text-[11px] text-muted-foreground">
                              rows {group.slice(0, 8).map((row) => row.source_row_number).join(', ')}
                              {group.length > 8 ? `, +${group.length - 8} more` : ''}
                            </span>
                          </div>

                          {options.length === 0 ? (
                            <p className="mt-2 text-[12px] text-muted-foreground">
                              No rolling timetable has been loaded for {code || 'this qualification'}, so there is
                              nothing to choose. These rows can only be saved as TBD until it is supplied.
                            </p>
                          ) : (
                            <>
                              <div className="mt-2 flex flex-wrap items-center gap-2">
                                <span className="text-[12px] font-medium">Apply to all {group.length}:</span>
                                {options.map((weeks) => (
                                  <Button
                                    key={weeks}
                                    size="sm"
                                    variant="outline"
                                    className="h-7 text-[12px]"
                                    onClick={() =>
                                      chooseDuration(
                                        group,
                                        weeks,
                                        `${group.length} ${code} ${group.length === 1 ? 'row' : 'rows'} set to ${weeks} weeks`,
                                      )
                                    }
                                    disabled={!canImport || busy}
                                  >
                                    {weeks} weeks
                                  </Button>
                                ))}
                              </div>

                              <ul className="mt-3 space-y-1">
                                {shown.map((row) => (
                                  <li key={row.id} className="flex flex-wrap items-center gap-2">
                                    <span className="tabular w-16 text-[11px] text-muted-foreground">
                                      Row {row.source_row_number}
                                    </span>
                                    <span className="w-32 truncate text-[12px]">{row.student_id_value}</span>
                                    {options.map((weeks) => (
                                      <Button
                                        key={weeks}
                                        size="sm"
                                        variant={row.duration_override_weeks === weeks ? 'default' : 'ghost'}
                                        className="h-6 text-[11px]"
                                        onClick={() =>
                                          chooseDuration([row], weeks, `Row ${row.source_row_number} set to ${weeks} weeks`)
                                        }
                                        disabled={!canImport || busy}
                                      >
                                        {weeks}w
                                      </Button>
                                    ))}
                                  </li>
                                ))}
                                {group.length > shown.length && (
                                  <li className="text-[11px] text-muted-foreground">
                                    +{group.length - shown.length} more — use “Apply to all” above.
                                  </li>
                                )}
                              </ul>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}

                {errorGroups.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-[12px] font-medium text-muted-foreground">
                      {errorGroups.length} distinct {errorGroups.length === 1 ? 'problem' : 'problems'}
                    </p>
                    <ul className="space-y-1.5">
                      {errorGroups.map((group) => (
                        <li
                          key={`${group.field}-${group.message}`}
                          className="flex flex-wrap items-baseline gap-2 rounded-md border border-border bg-muted/40 px-3 py-2"
                        >
                          <Badge variant="destructive" className="tabular">
                            {group.rows.length}
                          </Badge>
                          <span className="text-[13px] font-medium">{group.field}</span>
                          <span className="text-[13px] text-muted-foreground">{group.message}</span>
                          <span className="text-[11px] text-muted-foreground">
                            (rows {group.rows.slice(0, 8).join(', ')}
                            {group.rows.length > 8 ? `, +${group.rows.length - 8} more` : ''})
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {blocking > 0 && (
                <TableContainer className="max-h-[28rem]">
                  <Table aria-label="Errors identified">
                    <TableHeader>
                      <TableRow className="hover:bg-transparent">
                        <TableHead className="w-20">Source row</TableHead>
                        <TableHead className="w-36">Student ID</TableHead>
                        <TableHead className="w-44">Status</TableHead>
                        <TableHead>Problem</TableHead>
                        <TableHead className="w-28 text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {errorRows.map((row) => (
                        <TableRow key={row.id}>
                          <TableCell className="tabular">{row.source_row_number}</TableCell>
                          <TableCell className="text-[13px]">{row.student_id_value || '—'}</TableCell>
                          <TableCell>
                            <ImportStatusBadge status={statusLabel(row.status)} />
                          </TableCell>
                          <TableCell>
                            <ul className="space-y-1">
                              {row.issues
                                .filter((issue) => issue.issue_status !== 'NOTE')
                                .map((issue, index) => (
                                  <li key={index} className="text-[12px] leading-relaxed text-destructive">
                                    <span className="font-medium">{issue.field_name}:</span> {issue.message}
                                  </li>
                                ))}
                            </ul>
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => toggleExclude(row)}
                              disabled={!canImport || busy}
                            >
                              <X aria-hidden="true" />
                              Exclude
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                )}
              </CardContent>
            </Card>
            </div>
          )}
        </>
      )}

      {!review && !busy && !result && (
        <EmptyState
          title="No file has been uploaded"
          description="Select or drop an approved CSV or XLSX file to start the import. Rows are staged and validated before anything is saved."
          icon={FileSpreadsheet}
        />
      )}

      {result && (
        <Card>
          <CardHeader>
            <CardTitle>Import result</CardTitle>
            <CardDescription>A user activity record was created for this import.</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <CountTile label="Inserted" value={result.inserted} tone="success" />
            <CountTile label="Updated" value={result.updated} tone="default" />
            <CountTile label="Excluded" value={result.excluded} tone="muted" />
            <CountTile label="Intake matched" value={result.intakes_matched} tone="success" />
            <CountTile label="Intake TBD" value={result.intakes_tbd} tone="warning" />
            <CountTile label="Credit Transfer" value={result.intakes_not_applicable} tone="muted" />
            <CountTile label="Groups created" value={result.groups_created} tone="default" />
            <CountTile label="Suggestions raised" value={result.suggestions_raised} tone="warning" />
          </CardContent>
        </Card>
      )}

      {review && counts && (
        <ConfirmationDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Save Bulk Student Import?"
          description="The confirmed staged rows are written together in one transaction. Excluded rows are reported but not written."
          confirmLabel="Confirm Save"
          busy={busy}
          onConfirm={save}
        >
          <dl className="space-y-1.5 rounded-lg border border-border bg-muted/40 px-4 py-3 text-[13px]">
            <div className="flex gap-2">
              <dt className="w-32 text-muted-foreground">File:</dt>
              <dd className="font-medium">{review.file_name}</dd>
            </div>
            {Object.entries(counts).map(([label, value]) => (
              <div key={label} className="flex gap-2">
                <dt className="w-32 text-muted-foreground">{label}:</dt>
                <dd className="font-medium tabular">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="text-[13px] text-foreground">
            {counts['Ready'] ?? 0} student {(counts['Ready'] ?? 0) === 1 ? 'record' : 'records'} will be added.
          </p>
        </ConfirmationDialog>
      )}
    </div>
  );
}
