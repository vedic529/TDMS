'use client';

import * as React from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
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
import { ImportSummary, CountTile } from '@/components/common/import-summary';
import { EmptyState, ReadOnlyNotice } from '@/components/common/states';
import { ImportErrorReview } from '@/features/students/import-error-review';
import { isBlockingStatus } from '@/features/students/import-error-selection';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient } from '@/services';
import { countByStatus } from '@/services/import-validation';
import { parseCsvToObjects } from '@/lib/csv';
import { exportRows } from '@/lib/export';
import { formatDateTime, formatFileSize, today } from '@/lib/format';
import { readOnlyReason } from '@/lib/permissions';
import { INTERFACE_NAMES, SRS_PAGE_REFERENCE } from '@/lib/interface-names';
import { DEMO_IMPORT_CSV, IMPORT_TEMPLATE_COLUMNS } from '@/mock-data';
import type { ImportBatch, ImportResult, StagedStudentRow } from '@/types/import';
import type { ExportFormat } from '@/types/common';

const EDITABLE_COLUMNS: Array<{ key: keyof StagedStudentRow & string; label: string; width?: string }> = [
  { key: 'studentId', label: 'Student ID', width: 'w-36' },
  { key: 'firstName', label: 'First Name', width: 'w-32' },
  { key: 'lastName', label: 'Last Name', width: 'w-32' },
  { key: 'collegeValue', label: 'College', width: 'w-40' },
  { key: 'campusValue', label: 'Campus', width: 'w-32' },
  { key: 'qualificationValue', label: 'Qualification', width: 'w-32' },
  // Before Group, matching the template: CT decides whether Group applies.
  { key: 'ctStudent', label: 'CT Student', width: 'w-24' },
  { key: 'group', label: 'Group', width: 'w-28' },
  { key: 'coeStatus', label: 'CoE / Non-CoE', width: 'w-28' },
  { key: 'proposedStartDate', label: 'Proposed Start Date', width: 'w-36' },
  { key: 'proposedEndDate', label: 'Proposed End Date', width: 'w-36' },
];

/**
 * Bulk Student Import (SRS 7).
 *
 * Select file -> upload information -> preview -> staging table -> validate ->
 * correct/exclude -> revalidate -> confirmation -> save to database.
 * Nothing is written until the confirmation is accepted (BULK-02, BULK-07).
 */
export function BulkStudentImport() {
  const { user, permissions } = useAuth();
  const [batch, setBatch] = React.useState<ImportBatch | null>(null);
  const [result, setResult] = React.useState<ImportResult | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [xlsxNotice, setXlsxNotice] = React.useState(false);

  const canImport = permissions.maintainStudentData;

  /** The Errors identified section, so the staging area can scroll to it. */
  const errorsRef = React.useRef<HTMLDivElement>(null);

  const errorRows = React.useMemo(
    () => (batch ? batch.rows.filter((row) => isBlockingStatus(row.status)) : []),
    [batch],
  );

  function goToErrors() {
    errorsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    errorsRef.current?.focus({ preventScroll: true });
  }

  async function handleFile(file: File) {
    if (!user) return;
    setBusy(true);
    setResult(null);
    try {
      let rows: Array<Record<string, string>>;
      const isXlsx = file.name.toLowerCase().endsWith('.xlsx');

      if (isXlsx) {
        // An XLSX workbook cannot be read in the browser prototype. The demo
        // template is staged instead, and the interface says so.
        rows = parseCsvToObjects(DEMO_IMPORT_CSV);
        setXlsxNotice(true);
      } else {
        rows = parseCsvToObjects(await file.text());
        setXlsxNotice(false);
      }

      if (rows.length === 0) {
        toast.error('The file contains no data rows', {
          description: 'Check that the file uses the approved template and contains at least one student row.',
        });
        return;
      }

      const staged = await getTdmsClient().stageImport(
        { fileName: file.name, fileSizeBytes: file.size, rows },
        { actor: user },
      );
      setBatch(staged);
      toast.success('File loaded into the staging area', {
        description: `${staged.rowCount} rows were read. Nothing has been written to the database.`,
      });
    } catch (error) {
      toast.error('The file could not be read', {
        description: error instanceof Error ? error.message : 'Check the file and try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  function updateRow(rowId: string, key: keyof StagedStudentRow & string, value: string) {
    setBatch((current) =>
      current
        ? {
            ...current,
            rows: current.rows.map((row) => (row.id === rowId ? { ...row, [key]: value, corrected: true } : row)),
          }
        : current,
    );
  }

  function toggleExclude(rowId: string) {
    setBatch((current) =>
      current
        ? {
            ...current,
            rows: current.rows.map((row) =>
              row.id === rowId
                ? {
                    ...row,
                    status: row.status === 'Excluded by user' ? 'Needs correction' : 'Excluded by user',
                    issues: [],
                  }
                : row,
            ),
          }
        : current,
    );
  }

  /**
   * Removes staged rows outright.
   *
   * This is not a record deletion: the rows have never been written, so there is
   * nothing to soft-delete and no reason code applies (DATA-04 governs saved
   * records). The uploaded file is untouched, so the rows return by uploading it
   * again.
   */
  function deleteRows(rows: StagedStudentRow[]) {
    const ids = new Set(rows.map((row) => row.id));
    if (ids.size === 0) return;
    setBatch((current) =>
      current ? { ...current, rows: current.rows.filter((row) => !ids.has(row.id)) } : current,
    );
    toast.success(`${ids.size} error ${ids.size === 1 ? 'row' : 'rows'} deleted from the staging area`, {
      description: 'Nothing was written to the database, and your uploaded file is unchanged.',
    });
  }

  async function revalidate() {
    if (!batch) return;
    setBusy(true);
    try {
      const revalidated = await getTdmsClient().revalidateImport(batch);
      setBatch(revalidated);
      const counts = countByStatus(revalidated.rows);
      toast.success('Validation complete', {
        description: `${counts.ready} ready, ${counts.needsCorrection + counts.duplicate + counts.unmatched} still blocking, ${counts.excluded} excluded.`,
      });
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!batch || !user) return;
    setBusy(true);
    try {
      const saved = await getTdmsClient().saveImport(batch, { actor: user });
      setResult(saved);
      setConfirmOpen(false);
      toast.success('Bulk student import saved', {
        description: `${saved.inserted} student ${saved.inserted === 1 ? 'record was' : 'records were'} added and a user activity record was created.`,
      });
    } catch (error) {
      toast.error('The import could not be saved', {
        description: error instanceof Error ? error.message : 'Try again, or contact the TDMS administrator.',
      });
    } finally {
      setBusy(false);
    }
  }

  /** BULK-10 downloads are exports, so they create a user activity record (LOG-01). */
  async function recordDownload(kind: string, rowCount: number, fileName: string) {
    if (!user || !batch) return;
    await getTdmsClient().recordActivity({
      userReference: user.organisationEmail,
      accessLevel: user.role,
      pageOrFunction: SRS_PAGE_REFERENCE.bulkStudentImport,
      action: 'Export',
      recordOrBatchReference: `${batch.batchReference} · ${rowCount} rows`,
      result: 'Completed',
      plainLanguageDetail: `${kind} downloaded as ${fileName} (${rowCount} rows).`,
    });
  }

  function downloadPreview(format: ExportFormat) {
    if (!batch) return;
    const outcome = exportRows({
      format,
      baseFileName: `tdms-bulk-import-preview-${today()}`,
      sheetName: 'Staged rows',
      rows: batch.rows,
      columns: [
        { header: 'Source Row Number', value: (row) => row.sourceRowNumber },
        { header: 'Student ID', value: (row) => row.studentId },
        { header: 'First Name', value: (row) => row.firstName },
        { header: 'Last Name', value: (row) => row.lastName },
        { header: 'College', value: (row) => row.collegeValue },
        { header: 'Campus', value: (row) => row.campusValue },
        { header: 'Qualification', value: (row) => row.qualificationValue },
        { header: 'CT Student', value: (row) => row.ctStudent },
        { header: 'Group', value: (row) => row.group },
        { header: 'CoE / Non-CoE', value: (row) => row.coeStatus },
        { header: 'Proposed Start Date', value: (row) => row.proposedStartDate },
        { header: 'Proposed End Date', value: (row) => row.proposedEndDate },
        { header: 'Status', value: (row) => row.status },
      ],
    });
    void recordDownload('Bulk student import preview', outcome.rowCount, outcome.fileName);
    toast.success('Preview downloaded', { description: `${outcome.rowCount} staged rows in ${outcome.fileName}.` });
  }

  /**
   * The identified error rows, written back in the approved template's own
   * columns and order so the downloaded file can be corrected and uploaded
   * again as it stands. The three diagnostic columns are appended, and the
   * reader matches columns by name, so they are ignored on the way back in.
   */
  function downloadErrorRows(format: ExportFormat, rows: StagedStudentRow[]) {
    if (rows.length === 0) return;
    const outcome = exportRows({
      format,
      baseFileName: `tdms-bulk-import-errors-${today()}`,
      sheetName: 'Errors identified',
      rows,
      columns: [
        { header: 'Source Row Number', value: (row) => row.sourceRowNumber },
        { header: 'Student ID', value: (row) => row.studentId },
        { header: 'First Name', value: (row) => row.firstName },
        { header: 'Last Name', value: (row) => row.lastName },
        { header: 'College', value: (row) => row.collegeValue },
        { header: 'Campus', value: (row) => row.campusValue },
        { header: 'Qualification', value: (row) => row.qualificationValue },
        { header: 'CT Student', value: (row) => row.ctStudent },
        { header: 'Group', value: (row) => row.group },
        { header: 'CoE / Non-CoE', value: (row) => row.coeStatus },
        { header: 'Proposed Start Date', value: (row) => row.proposedStartDate },
        { header: 'Proposed End Date', value: (row) => row.proposedEndDate },
        { header: 'Personal Email', value: (row) => row.personalEmail },
        { header: 'Primary Phone', value: (row) => row.primaryPhone },
        { header: 'Status', value: (row) => row.status },
        { header: 'Fields With A Problem', value: (row) => row.issues.map((issue) => issue.field).join('; ') },
        {
          header: 'Validation Message',
          value: (row) => row.issues.map((issue) => `${issue.field}: ${issue.message}`).join(' | '),
        },
      ],
    });
    void recordDownload('Bulk student import identified errors', outcome.rowCount, outcome.fileName);
    toast.success('Identified errors downloaded', {
      description: `${outcome.rowCount} error ${outcome.rowCount === 1 ? 'row' : 'rows'} in ${outcome.fileName}.`,
    });
  }

  function downloadIssues(format: ExportFormat) {
    if (!batch) return;
    const issueRows = batch.rows.flatMap((row) =>
      row.issues.map((issue) => ({
        sourceRowNumber: row.sourceRowNumber,
        studentId: row.studentId,
        status: row.status,
        field: issue.field,
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
    void recordDownload('Bulk student import issue report', outcome.rowCount, outcome.fileName);
    toast.success('Issue report downloaded', {
      description: `${outcome.rowCount} issues in ${outcome.fileName}.`,
    });
  }

  function downloadTemplate() {
    exportRows({
      format: 'csv',
      baseFileName: 'tdms-bulk-student-import-template',
      rows: [] as Array<Record<string, string>>,
      columns: IMPORT_TEMPLATE_COLUMNS.map((header) => ({ header, value: () => '' })),
    });
    toast.success('Template downloaded', { description: 'Use this CSV template for the bulk student import.' });
  }

  const counts = batch ? countByStatus(batch.rows) : null;
  const blocking = counts ? counts.needsCorrection + counts.duplicate + counts.unmatched : 0;
  const canSave = Boolean(batch) && blocking === 0 && (counts?.ready ?? 0) > 0;

  return (
    <div className="space-y-5">
      {!canImport && <ReadOnlyNotice message={readOnlyReason(user, INTERFACE_NAMES.bulkStudentImport)} />}

      <Card>
        <CardHeader className="flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>Upload a student file</CardTitle>
            <CardDescription>
              Uploaded rows are held in a staging area and checked before anything is written to the database.
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

      {xlsxNotice && (
        <Alert variant="info">
          <FileSpreadsheet aria-hidden="true" />
          <div className="space-y-1">
            <AlertTitle>XLSX workbooks are read by the TDMS API</AlertTitle>
            <AlertDescription>
              The frontend prototype cannot open an XLSX workbook in the browser, so a representative demo file has
              been staged instead. Every later step — validation, correction, exclusion, confirmation and the result
              summary — behaves exactly as it will with a real workbook. Upload a CSV file to stage your own rows.
            </AlertDescription>
          </div>
        </Alert>
      )}

      {batch && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Upload information</CardTitle>
              <CardDescription>Batch reference {batch.batchReference}</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <p className="text-[12px] text-muted-foreground">File name</p>
                <p className="truncate text-[13px] font-medium" title={batch.fileName}>
                  {batch.fileName}
                </p>
                <p className="text-[12px] text-muted-foreground">{formatFileSize(batch.fileSizeBytes)}</p>
              </div>
              <div>
                <p className="text-[12px] text-muted-foreground">Upload date and time</p>
                <p className="text-[13px] font-medium">{formatDateTime(batch.uploadedAt)}</p>
              </div>
              <div>
                <p className="text-[12px] text-muted-foreground">Uploading user</p>
                <p className="text-[13px] font-medium">{batch.uploadedByDisplayName}</p>
              </div>
              <div>
                <p className="text-[12px] text-muted-foreground">Number of rows</p>
                <p className="text-[13px] font-medium tabular">{batch.rowCount}</p>
                {batch.rows.length !== batch.rowCount && (
                  <p className="tabular text-[12px] text-muted-foreground">
                    {batch.rows.length} staged now · {batch.rowCount - batch.rows.length} deleted
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          {counts && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              <CountTile label="Ready" value={counts.ready} tone="success" />
              <CountTile label="Needs correction" value={counts.needsCorrection} tone="warning" />
              <CountTile label="Duplicate" value={counts.duplicate} tone="destructive" />
              <CountTile label="Unmatched reference" value={counts.unmatched} tone="destructive" />
              <CountTile label="Excluded by user" value={counts.excluded} tone="muted" />
            </div>
          )}

          <Card>
            <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle>Staging area</CardTitle>
                <CardDescription>
                  Correct a value directly in the table, or exclude a row. Run validation again after any change.
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
                  Revalidate
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
                      Save to Database stays unavailable until every selected staged row is Ready or excluded.
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
                  <div className="space-y-1">
                    <AlertTitle>No blocking problem remains</AlertTitle>
                    <AlertDescription>
                      {counts?.ready ?? 0} rows will be written when you confirm the save.
                    </AlertDescription>
                  </div>
                </Alert>
              )}

              <TableContainer className="max-h-[32rem]">
                <Table aria-label="Bulk student import staging area">
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="w-16">Source row</TableHead>
                      {EDITABLE_COLUMNS.map((column) => (
                        <TableHead key={column.key} className={column.width}>
                          {column.label}
                        </TableHead>
                      ))}
                      <TableHead className="w-40">Status</TableHead>
                      <TableHead className="min-w-72">Issue</TableHead>
                      <TableHead className="w-28 text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {batch.rows.map((row) => {
                      const excluded = row.status === 'Excluded by user';
                      const issueFields = new Set(row.issues.map((issue) => issue.field));
                      return (
                        <TableRow key={row.id} className={excluded ? 'opacity-60' : undefined}>
                          <TableCell className="tabular">{row.sourceRowNumber}</TableCell>
                          {EDITABLE_COLUMNS.map((column) => (
                            <TableCell key={column.key}>
                              <Input
                                value={String(row[column.key] ?? '')}
                                onChange={(event) => updateRow(row.id, column.key, event.target.value)}
                                disabled={excluded || !canImport}
                                aria-invalid={issueFields.has(column.label) || undefined}
                                aria-label={`${column.label} for source row ${row.sourceRowNumber}`}
                                className="h-8 text-[13px]"
                              />
                            </TableCell>
                          ))}
                          <TableCell>
                            <span className="flex flex-col items-start gap-1">
                              <ImportStatusBadge status={row.status} />
                              {row.corrected && (
                                <Badge variant="info" className="text-[10px]">
                                  Corrected
                                </Badge>
                              )}
                            </span>
                          </TableCell>
                          <TableCell>
                            {row.issues.length === 0 ? (
                              <span className="text-[12px] text-muted-foreground">—</span>
                            ) : (
                              <ul className="space-y-1">
                                {row.issues.map((issue, index) => (
                                  <li key={index} className="text-[12px] leading-relaxed text-destructive">
                                    <span className="font-medium">{issue.field}:</span> {issue.message}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => toggleExclude(row.id)}
                              disabled={!canImport}
                            >
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

          <ImportErrorReview
            ref={errorsRef}
            rows={errorRows}
            canEdit={canImport}
            busy={busy}
            onDownload={downloadErrorRows}
            onDelete={deleteRows}
          />
        </>
      )}

      {!batch && !busy && (
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
            <CardDescription>
              Completed {formatDateTime(result.completedAt)}. A user activity record was created for this import.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ImportSummary result={result} />
          </CardContent>
        </Card>
      )}

      {batch && counts && (
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
              <dd className="font-medium">{batch.fileName}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-32 text-muted-foreground">Ready:</dt>
              <dd className="font-medium tabular">{counts.ready}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-32 text-muted-foreground">Excluded:</dt>
              <dd className="font-medium tabular">{counts.excluded}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-32 text-muted-foreground">Duplicates:</dt>
              <dd className="font-medium tabular">{counts.duplicate}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-32 text-muted-foreground">Unmatched:</dt>
              <dd className="font-medium tabular">{counts.unmatched}</dd>
            </div>
          </dl>
          <p className="text-[13px] text-foreground">
            {counts.ready} student {counts.ready === 1 ? 'record' : 'records'} will be added.
          </p>
        </ConfirmationDialog>
      )}
    </div>
  );
}
