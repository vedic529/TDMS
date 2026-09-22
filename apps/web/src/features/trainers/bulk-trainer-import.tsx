'use client';

import * as React from 'react';
import {
  CheckCircle2,
  FileWarning,
  Loader2,
  ShieldAlert,
  TriangleAlert,
  Upload,
  Undo2,
  UserRoundX,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SimpleSelect } from '@/components/common/dependent-select';
import { FileDropzone } from '@/components/common/file-dropzone';
import { EmptyState, ReadOnlyNotice } from '@/components/common/states';
import { useAuth } from '@/features/auth/auth-context';
import {
  IMPORT_DATA_TYPES,
  trainersApi,
  type ImportReview,
  type TrainerImportDataType,
} from '@/services/trainers-api';

type ApplyMode = 'MERGE' | 'REPLACE';

/** The working value behind each field an issue can name, so its cell can be corrected here. */
const EDITABLE_FIELDS: Record<string, string> = {
  'Trainer id': 'trainer_id',
  'Trainer ID': 'trainer_id',
  'Trainer name': 'trainer_name',
  'Trainer Campus': 'trainer_campus',
  Location: 'location',
  'Working Time': 'working_time',
  'Delivery Type': 'delivery_type',
  'Qualifications They Can Teach': 'qualification_code',
  'Units They Can Teach': 'unit_code',
};

function fieldLabel(field: string): string {
  return Object.entries(EDITABLE_FIELDS).find(([, key]) => key === field)?.[0] ?? field;
}

/** One correction made in this review, kept so it can be undone. */
interface RowEdit {
  rowId: number;
  rowNumber: number;
  field: string;
  from: string;
  to: string;
}

const ENTITY_LABEL: Record<string, string> = {
  CAMPUS: 'Campus',
  QUALIFICATION: 'Qualification',
  UNIT: 'Unit',
  CITY: 'City',
};

const SEVERITY_STYLE: Record<string, string> = {
  ERROR: 'text-destructive',
  UNRESOLVED: 'text-destructive',
  UNMATCHED: 'text-destructive',
  RAISED: 'text-info',
  EXCEPTION: 'text-destructive',
  ACCEPTED: 'text-success',
  DUPLICATE: 'text-warning',
  WARNING: 'text-warning',
  NOTE: 'text-muted-foreground',
};

const STATUS_LABEL: Record<string, string> = {
  READY: 'Ready',
  NEEDS_CORRECTION: 'Needs correction',
  DUPLICATE: 'Duplicate',
  UNMATCHED_REFERENCE: 'Trainer not found',
  EXCLUDED_BY_USER: 'Excluded',
};

/**
 * Bulk Trainer Import.
 *
 * **The first question is which kind of data, never which training package**
 * (1.7). A trainer is not tied to one package — the real BSB workbook contains
 * a trainer who teaches only FNS qualifications — so a package selector here
 * would be asking a question the data cannot answer.
 *
 * The choice also selects the worksheet, which is why the supplied two-sheet
 * workbook can be uploaded as-is for either shape.
 *
 * What each issue offers is decided by its kind (approved 15 September 2026):
 * a value that matches no approved record - a campus, qualification, unit or
 * city - is raised as a suggestion; a broken rule, such as a city that disagrees
 * with its campus, is accepted as an exception for this import only; a row that
 * cannot be stored is excluded. Each decision can be undone.
 */
export function BulkTrainerImport() {
  const { permissions } = useAuth();
  const canMaintain = permissions.maintainTrainerData;

  const [dataType, setDataType] = React.useState<TrainerImportDataType | ''>('');
  const [file, setFile] = React.useState<File | null>(null);
  const [applyMode, setApplyMode] = React.useState<ApplyMode>('MERGE');
  const [review, setReview] = React.useState<ImportReview | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [drafts, setDrafts] = React.useState<Record<string, string>>({});
  const [edits, setEdits] = React.useState<RowEdit[]>([]);

  function reset() {
    setFile(null);
    setReview(null);
    setError(null);
    setDrafts({});
    setEdits([]);
  }

  async function stage(next: File) {
    if (!dataType) return;
    setBusy(true);
    setError(null);
    try {
      setReview(await trainersApi.stageImport(dataType, next));
    } catch (caught) {
      setReview(null);
      setError(caught instanceof Error ? caught.message : 'The file could not be read.');
    } finally {
      setBusy(false);
    }
  }

  async function excludeMissingTrainers() {
    if (!review) return;
    setBusy(true);
    try {
      // 1.9: the one offered action — leave the unmatched rows out so the rows
      // for trainers that do exist can still be imported.
      setReview(
        await trainersApi.patchImportRows(review.batch_id, { exclude_missing_trainers: true }),
      );
    } catch (caught) {
      toast.error('The rows could not be excluded', {
        description: caught instanceof Error ? caught.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  async function raise(keys: string[] | 'all') {
    if (!review) return;
    setBusy(true);
    try {
      const next = await trainersApi.raiseSuggestions(
        review.batch_id,
        keys === 'all' ? { all: true } : { keys },
      );
      setReview(next);
      const count = keys === 'all' ? next.unresolved_values.length : keys.length;
      toast.success(`${count} suggestion(s) raised`, {
        description:
          'Resolve each with Create Record or Map Record from the shield on Trainer Location and Details, then re-upload the file.',
      });
    } catch (caught) {
      toast.error('The suggestion could not be raised', {
        description: caught instanceof Error ? caught.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  async function decide(rowId: number, decision: 'KEEP_STORED' | 'TAKE_FROM_FILE') {
    if (!review) return;
    setBusy(true);
    try {
      setReview(
        await trainersApi.patchImportRows(review.batch_id, {
          override_decisions: { [rowId]: decision },
        }),
      );
    } catch (caught) {
      toast.error('The decision could not be saved', {
        description: caught instanceof Error ? caught.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  async function excludeRow(rowId: number) {
    if (!review) return;
    setBusy(true);
    try {
      setReview(
        await trainersApi.patchImportRows(review.batch_id, { excluded_row_ids: [rowId] }),
      );
    } finally {
      setBusy(false);
    }
  }

  async function patchRows(
    payload: Parameters<typeof trainersApi.patchImportRows>[1],
    failure: string,
  ): Promise<boolean> {
    if (!review) return false;
    setBusy(true);
    try {
      setReview(await trainersApi.patchImportRows(review.batch_id, payload));
      return true;
    } catch (caught) {
      toast.error(failure, {
        description: caught instanceof Error ? caught.message : 'Try again.',
      });
      return false;
    } finally {
      setBusy(false);
    }
  }

  /** Send the changed cells of one row; the whole batch is checked again. */
  async function applyEdits(row: ImportReview['rows'][number]) {
    const changes: Record<string, string> = {};
    const made: RowEdit[] = [];
    for (const field of new Set(Object.values(EDITABLE_FIELDS))) {
      const draft = drafts[`${row.id}:${field}`];
      const current = row.values[field] ?? '';
      if (draft === undefined || draft === current) continue;
      changes[field] = draft;
      made.push({ rowId: row.id, rowNumber: row.row_number, field, from: current, to: draft });
    }
    if (made.length === 0) return;
    if (await patchRows({ corrections: { [row.id]: changes } }, 'The edit could not be applied')) {
      setEdits((current) => [
        ...current.filter((edit) => !made.some((next) => next.rowId === edit.rowId && next.field === edit.field)),
        // An edit of an edit still undoes to what the file said.
        ...made.map((next) => ({
          ...next,
          from: current.find((edit) => edit.rowId === next.rowId && edit.field === next.field)?.from ?? next.from,
        })),
      ]);
      setDrafts({});
    }
  }

  async function undoEdit(edit: RowEdit) {
    if (
      await patchRows({ corrections: { [edit.rowId]: { [edit.field]: edit.from } } }, 'The edit could not be undone')
    ) {
      setEdits((current) => current.filter((item) => !(item.rowId === edit.rowId && item.field === edit.field)));
    }
  }

  async function confirm() {
    if (!review) return;
    setBusy(true);
    try {
      const result = await trainersApi.applyImport(review.batch_id, applyMode);
      toast.success('Trainer data imported', {
        description:
          result.data_type === 'LOCATION'
            ? `${result.trainers_written} trainer(s) and ${result.locations_written} location(s) written in ${applyMode.toLowerCase()} mode.` +
              (result.locations_overwritten > 0
                ? ` ${result.locations_overwritten} existing location(s) replaced with the file's version.`
                : "")
            : `${result.unit_links_written} unit link(s) and ${result.qualification_links_written} qualification link(s) written in ${applyMode.toLowerCase()} mode.` +
              (result.unit_links_unresolved > 0
                ? ` ${result.unit_links_unresolved} kept an unmatched value until its suggestion is resolved.`
                : ""),
      });
      reset();
    } catch (caught) {
      toast.error('The import could not be confirmed', {
        description: caught instanceof Error ? caught.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  async function abandon() {
    if (!review) return;
    setBusy(true);
    try {
      await trainersApi.abandonImport(review.batch_id);
      toast.success('Import abandoned. Nothing was written.');
      reset();
    } finally {
      setBusy(false);
    }
  }

  if (!canMaintain) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Bulk Import</CardTitle>
        </CardHeader>
        <CardContent>
          <ReadOnlyNotice message="Importing trainer data requires Admin access or above." />
        </CardContent>
      </Card>
    );
  }

  const blocked = review?.rows.filter(
    (row) => row.status !== 'READY' && row.status !== 'EXCLUDED_BY_USER',
  );
  // Decisions taken on this review, each listed with its Undo.
  const accepted =
    review?.rows.filter(
      (row) => row.status !== 'EXCLUDED_BY_USER' && row.issues.some((issue) => issue.severity === 'ACCEPTED'),
    ) ?? [];
  const excluded = review?.rows.filter((row) => row.status === 'EXCLUDED_BY_USER') ?? [];

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Bulk Import</CardTitle>
          <CardDescription>
            Upload the approved trainer workbook. Choose which kind of data it holds — there is no
            training package to select, because a trainer is not tied to one.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="max-w-md space-y-1">
            <label htmlFor="trainer-data-type" className="text-[13px] font-medium">
              What kind of data is this?
            </label>
            <SimpleSelect
              value={dataType}
              onChange={(value) => {
                setDataType(value as TrainerImportDataType);
                reset();
              }}
              options={IMPORT_DATA_TYPES.map((item) => ({
                value: item.value,
                label: item.label,
              }))}
              placeholder="Choose the data type"
            />
            <p className="text-[12px] text-muted-foreground">
              {dataType === 'UNITS'
                ? 'Trainer Units needs the trainers to exist already — import Trainer Location and Details first.'
                : 'Trainer Location and Details creates the trainers it names.'}
            </p>
          </div>

          <FileDropzone
            file={file}
            onClear={reset}
            disabled={!dataType || busy}
            disabledMessage={
              !dataType ? 'Choose the data type before uploading a file.' : 'Reading the file…'
            }
            title="Drag and drop the trainer workbook here"
            hint="CSV or XLSX. The right worksheet is chosen from the data type above."
            onFileSelected={(next) => {
              setFile(next);
              void stage(next);
            }}
          />

          {busy && !review && (
            <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Reading the file…
            </p>
          )}
          {error && <p className="text-[13px] text-destructive">{error}</p>}
        </CardContent>
      </Card>

      {review && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Staging area</CardTitle>
              <CardDescription>
                {review.rows_read} row(s) read from {review.file_name}. Nothing is written until you
                confirm.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-2 text-[13px]">
                <Badge variant="success">{review.rows_valid} ready</Badge>
                {review.rows_with_errors > 0 && (
                  <Badge variant="destructive">{review.rows_with_errors} need a decision</Badge>
                )}
                {review.rows_excluded > 0 && (
                  <Badge variant="neutral">{review.rows_excluded} excluded</Badge>
                )}
                {review.unresolved_values.length > 0 && (
                  <Badge variant="warning">
                    {review.unresolved_values.length} unmatched value(s)
                  </Badge>
                )}
              </div>


            </CardContent>
          </Card>

          {/* -- Unmatched qualifications, units and campuses -------------- */}
          {review.unresolved_values.length > 0 && (
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <ShieldAlert aria-hidden="true" className="size-4 text-warning" />
                      Not in the reference data
                    </CardTitle>
                    <CardDescription>
                      These values match no approved record.{' '}
                      <strong>Raising a suggestion lets the rows import</strong>, keeping the
                      value exactly as the file wrote it — the same way the timetable import
                      behaves. Resolving it later with <strong>Create Record</strong> or{' '}
                      <strong>Map Record</strong> repairs every row that used it. An unmatched
                      value is never accepted as an exception.
                    </CardDescription>
                  </div>
                  {review.unresolved_values.some((value) => !value.raised_here) && (
                    <Button variant="outline" disabled={busy} onClick={() => void raise('all')}>
                      Raise all and import
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1.5">
                  {review.unresolved_values.map((value) => (
                    <li
                      key={value.key}
                      className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2"
                    >
                      <Badge variant="neutral">{ENTITY_LABEL[value.entity_type]}</Badge>
                      <span className="text-[13px] font-medium">&ldquo;{value.raw_value}&rdquo;</span>
                      {value.context.qualification && (
                        <span className="text-[11px] text-muted-foreground">
                          in {value.context.qualification}
                        </span>
                      )}
                      <span className="text-[12px] text-muted-foreground tabular">
                        {value.row_count} row{value.row_count === 1 ? '' : 's'}
                      </span>
                      {value.raised_here ? (
                        <span className="ml-auto flex items-center gap-1.5 text-[12px] text-info">
                          <CheckCircle2 aria-hidden="true" className="size-3.5" />
                          Raised &mdash; will import as written
                        </span>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          className="ml-auto h-7 text-[12px]"
                          disabled={busy}
                          onClick={() => void raise([value.key])}
                        >
                          Raise suggestion
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-[12px] text-muted-foreground">
                  Raised suggestions appear under the shield on Trainer Location and Details.
                  You do not need to re-upload: the rows import now, and resolving the
                  suggestion repairs them in place. Excluding the rows is still available if you
                  would rather leave them out.
                </p>
              </CardContent>
            </Card>
          )}

          {/* -- Changes to something already stored --------------------- */}
          {review.overrides.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileWarning aria-hidden="true" className="size-4 text-warning" />
                  Would change something already stored
                </CardTitle>
                <CardDescription>
                  Adding is silent; overwriting is not. Each row below changes a value already on
                  record — choose which one to keep. Confirm stays shut until every one is decided.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {review.overrides.map((entry) => (
                    <li key={entry.row_id} className="rounded-md border border-border p-2.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[13px] font-medium tabular">
                          Row {entry.row_number}
                        </span>
                        <Badge variant="neutral">{entry.trainer_id}</Badge>
                        <span className="text-[12px] text-muted-foreground">{entry.location}</span>
                        <div className="ml-auto flex gap-1.5">
                          <Button
                            size="sm"
                            variant={entry.decision === 'KEEP_STORED' ? 'default' : 'outline'}
                            className="h-7 text-[12px]"
                            disabled={busy}
                            onClick={() => void decide(entry.row_id, 'KEEP_STORED')}
                          >
                            Keep stored
                          </Button>
                          <Button
                            size="sm"
                            variant={entry.decision === 'TAKE_FROM_FILE' ? 'default' : 'outline'}
                            className="h-7 text-[12px]"
                            disabled={busy}
                            onClick={() => void decide(entry.row_id, 'TAKE_FROM_FILE')}
                          >
                            Take from file
                          </Button>
                        </div>
                      </div>
                      <table className="mt-2 w-full text-[12px]">
                        <thead>
                          <tr className="text-left text-muted-foreground">
                            <th className="py-0.5 pr-3 font-medium">Field</th>
                            <th className="py-0.5 pr-3 font-medium">Stored</th>
                            <th className="py-0.5 font-medium">In the file</th>
                          </tr>
                        </thead>
                        <tbody>
                          {entry.changes.map((change) => (
                            <tr key={change.field} className="border-t border-border/50">
                              <td className="py-0.5 pr-3">{change.label}</td>
                              <td className="py-0.5 pr-3 text-muted-foreground">
                                {change.stored_value || '—'}
                              </td>
                              <td className="py-0.5 font-medium">{change.incoming_value || '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {/* -- Missing trainers (1.9) ---------------------------------- */}
          {review.missing_trainers.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-destructive">
                  <UserRoundX aria-hidden="true" className="size-4" />
                  Trainers not in the database
                </CardTitle>
                <CardDescription>{review.blocking_message}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <ul className="space-y-1 text-[13px]">
                  {review.missing_trainers.map((group) => (
                    <li key={group.trainer_id} className="flex gap-3">
                      <span className="w-32 font-medium">{group.trainer_id}</span>
                      <span className="text-muted-foreground tabular">
                        {group.row_count} row{group.row_count === 1 ? '' : 's'}
                      </span>
                    </li>
                  ))}
                </ul>
                <div className="space-y-2">
                  <Button variant="outline" onClick={() => void excludeMissingTrainers()} disabled={busy}>
                    Import rows for the trainers that exist
                  </Button>
                  <p className="text-[12px] text-muted-foreground">
                    A units file carries no name, campus or availability, so it cannot create a
                    complete trainer record. Import the Trainer Location and Details file for these
                    trainers first if you want their units.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* -- Errors identified --------------------------------------- */}
          {blocked && blocked.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TriangleAlert aria-hidden="true" className="size-4 text-destructive" />
                  Errors identified
                </CardTitle>
                <CardDescription>
                  Each row below needs a decision before the import can be confirmed.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {blocked.slice(0, 100).map((row) => (
                    <li key={row.id} className="rounded-md border border-border p-2.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[13px] font-medium tabular">Row {row.row_number}</span>
                        <Badge variant="neutral">{STATUS_LABEL[row.status] ?? row.status}</Badge>
                        <span className="truncate text-[12px] text-muted-foreground">
                          {Object.values(row.values).filter(Boolean).slice(0, 4).join(' · ')}
                        </span>
                        {row.issues.some((issue) => issue.severity === 'EXCEPTION') && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="ml-auto h-7 text-[12px]"
                            disabled={busy}
                            onClick={() =>
                              void patchRows(
                                { accepted_exception_row_ids: [row.id] },
                                'The exception could not be accepted',
                              )
                            }
                          >
                            Accept exception
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          className={
                            row.issues.some((issue) => issue.severity === 'EXCEPTION')
                              ? 'h-7 text-[12px]'
                              : 'ml-auto h-7 text-[12px]'
                          }
                          disabled={busy}
                          onClick={() => void excludeRow(row.id)}
                        >
                          Exclude this row
                        </Button>
                      </div>
                      <ul className="mt-1 space-y-0.5">
                        {row.issues
                          .filter((issue) => issue.severity !== 'NOTE')
                          .map((issue, index) => (
                            <li
                              key={index}
                              className={`text-[12px] ${SEVERITY_STYLE[issue.severity] ?? ''}`}
                            >
                              {issue.column_name ? `${issue.column_name}: ` : ''}
                              {issue.message}
                            </li>
                          ))}
                      </ul>
                      <RowEditor
                        row={row}
                        drafts={drafts}
                        busy={busy}
                        onDraft={(field, value) => setDrafts((current) => ({ ...current, [`${row.id}:${field}`]: value }))}
                        onApply={() => void applyEdits(row)}
                      />
                    </li>
                  ))}
                </ul>
                {blocked.length > 100 && (
                  <p className="mt-2 text-[12px] text-muted-foreground">
                    Showing the first 100 of {blocked.length}.
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {/* -- Decided for this import --------------------------------- */}
          {(edits.length > 0 || accepted.length > 0 || excluded.length > 0) && (
            <Card>
              <CardHeader>
                <CardTitle>Decided for this import</CardTitle>
                <CardDescription>
                  Edits, accepted exceptions and excluded rows apply to this import only. Undo reverses
                  each one.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1.5">
                  {edits.map((edit) => (
                    <li
                      key={`edit-${edit.rowId}-${edit.field}`}
                      className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2 text-[12px]"
                    >
                      <span className="font-medium tabular">Row {edit.rowNumber}</span>
                      <span className="min-w-0 break-words">
                        {fieldLabel(edit.field)}: “{edit.from}” → “{edit.to}”
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="ml-auto h-7 gap-1 text-[12px]"
                        disabled={busy}
                        onClick={() => void undoEdit(edit)}
                      >
                        <Undo2 aria-hidden="true" className="size-3.5" />
                        Undo
                      </Button>
                    </li>
                  ))}
                  {accepted.map((row) => (
                    <li
                      key={`accepted-${row.id}`}
                      className="flex flex-wrap items-center gap-2 rounded-md border border-success/35 bg-success-soft px-3 py-2 text-[12px]"
                    >
                      <span className="font-medium tabular">Row {row.row_number}</span>
                      <span className="text-success">
                        {row.issues.find((issue) => issue.severity === 'ACCEPTED')?.message}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="ml-auto h-7 gap-1 text-[12px]"
                        disabled={busy}
                        onClick={() =>
                          void patchRows(
                            { withdrawn_exception_row_ids: [row.id] },
                            'The decision could not be undone',
                          )
                        }
                      >
                        <Undo2 aria-hidden="true" className="size-3.5" />
                        Undo
                      </Button>
                    </li>
                  ))}
                  {excluded.map((row) => (
                    <li
                      key={`excluded-${row.id}`}
                      className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-[12px]"
                    >
                      <span className="font-medium tabular">Row {row.row_number}</span>
                      <span className="truncate text-muted-foreground">
                        Excluded ·{' '}
                        {[row.values.trainer_id, row.values.trainer_name, row.values.location, row.values.unit_code]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="ml-auto h-7 gap-1 text-[12px]"
                        disabled={busy}
                        onClick={() =>
                          void patchRows({ included_row_ids: [row.id] }, 'The row could not be included again')
                        }
                      >
                        <Undo2 aria-hidden="true" className="size-3.5" />
                        Undo
                      </Button>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {blocked && blocked.length === 0 && (
            <EmptyState
              title="Every row is ready"
              description="No row needs a decision. Confirm to write the data."
              icon={CheckCircle2}
            />
          )}

          {/* -- Confirm -------------------------------------------------- */}
          <Card>
            <CardHeader>
              <CardTitle>Confirm</CardTitle>
              <CardDescription>
                Merge adds and updates what the file contains. Replace clears this data type first —
                for the trainers named in the file only, so re-uploading a corrected BSB file does
                not touch a CHC trainer.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="max-w-xs">
                <SimpleSelect
                  value={applyMode}
                  onChange={(value) => setApplyMode(value as ApplyMode)}
                  placeholder="Re-import mode"
                  options={[
                    { value: 'MERGE', label: 'Merge — add and update' },
                    { value: 'REPLACE', label: 'Replace — clear these trainers first' },
                  ]}
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => void confirm()} disabled={busy || !review.can_apply}>
                  {busy ? (
                    <Loader2 className="animate-spin" aria-hidden="true" />
                  ) : (
                    <Upload aria-hidden="true" />
                  )}
                  Confirm import
                </Button>
                <Button variant="outline" onClick={() => void abandon()} disabled={busy}>
                  Abandon
                </Button>
              </div>
              {!review.can_apply && (
                <p className="text-[12px] text-muted-foreground">
                  Confirm becomes available once every row is ready or excluded.
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

/** The cells a row's issues name, editable in place. */
function RowEditor({
  row,
  drafts,
  busy,
  onDraft,
  onApply,
}: {
  row: ImportReview['rows'][number];
  drafts: Record<string, string>;
  busy: boolean;
  onDraft: (field: string, value: string) => void;
  onApply: () => void;
}) {
  const fields = Array.from(
    new Set(
      row.issues
        .map((issue) => (issue.column_name ? EDITABLE_FIELDS[issue.column_name] : undefined))
        .filter((field): field is string => Boolean(field)),
    ),
  );
  if (fields.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap items-end gap-2">
      {fields.map((field) => (
        <label key={field} className="min-w-40 flex-1 space-y-1">
          <span className="text-[11px] text-muted-foreground">{fieldLabel(field)}</span>
          <Input
            className="h-8 text-[13px]"
            value={drafts[`${row.id}:${field}`] ?? row.values[field] ?? ''}
            onChange={(event) => onDraft(field, event.target.value)}
          />
        </label>
      ))}
      <Button size="sm" variant="outline" className="h-8 text-[12px]" disabled={busy} onClick={onApply}>
        Apply edit
      </Button>
    </div>
  );
}
