'use client';

import * as React from 'react';
import { AlertTriangle, Undo2, Upload } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SimpleSelect } from '@/components/common/dependent-select';
import { FileDropzone } from '@/components/common/file-dropzone';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { ReferenceApiError } from '@/services/reference-api';
import {
  allocationApi,
  type AllocationDiscrepancy,
  type AllocationImportOverrides,
  type AllocationImportReview,
  type AllocationPackage,
} from '@/services/allocation-api';

type Correction = AllocationImportOverrides['corrections'][number];
type EditField = { column: string; value: string };

const NO_DECISIONS: AllocationImportOverrides = {
  corrections: [],
  except_ids: [],
  raise_ids: [],
  no_raise_ids: [],
  exclude_rows: [],
};

function unique<T>(values: T[]): T[] {
  return Array.from(new Set(values));
}

function asEditField(field: { column?: string | null; value?: string | null }, fallbackColumn = ''): EditField {
  return {
    column: field.column ?? fallbackColumn,
    value: field.value ?? '',
  };
}

function upsertCorrection(list: Correction[], next: Correction): Correction[] {
  return [...list.filter((item) => !(item.row_number === next.row_number && item.column === next.column)), next];
}

function groupBySourceRow(items: AllocationDiscrepancy[]): AllocationDiscrepancy[][] {
  const groups: AllocationDiscrepancy[][] = [];
  const indexFor = new Map<string, number>();
  for (const item of items) {
    const key = item.row_number != null ? `row-${item.row_number}` : `one-${item.issue_id}`;
    const existing = indexFor.get(key);
    if (existing === undefined) {
      indexFor.set(key, groups.length);
      groups.push([item]);
    } else {
      groups[existing].push(item);
    }
  }
  return groups;
}

function fieldsForItem(item: AllocationDiscrepancy): EditField[] {
  if (item.edit_fields?.length) {
    return item.edit_fields.map((field) => asEditField(field, item.column ?? ''));
  }
  if (item.can_edit && item.column) return [{ column: item.column, value: item.value ?? '' }];
  return [];
}

function uniqueEditFields(items: AllocationDiscrepancy[]): EditField[] {
  const byColumn = new Map<string, EditField>();
  for (const item of items) {
    if (!item.can_edit) continue;
    for (const field of fieldsForItem(item)) {
      if (field.column) byColumn.set(field.column, field);
    }
  }
  return Array.from(byColumn.values());
}

/** A decision already taken on this review, with the way back. */
function DecisionTag({ label, onUndo, disabled }: { label: string; onUndo: () => void; disabled?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-success/35 bg-success-soft py-0.5 pl-2 pr-0.5 text-[12px] text-success">
      {label}
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="h-6 gap-1 px-1.5 text-[12px]"
        disabled={disabled}
        onClick={onUndo}
      >
        <Undo2 aria-hidden="true" className="size-3.5" />
        Undo
      </Button>
    </span>
  );
}

/**
 * The allocation import review.
 *
 * What each issue offers is decided by its kind, not chosen (approved
 * 15 September 2026):
 *
 * - a value that matches no approved record, or a class no rolling-timetable
 *   intake accounts for, is **raised as a suggestion** - or edited;
 * - any predefined rule the row breaks is **accepted as an exception** for this
 *   import only, **edited**, or the row **excluded** - the same for every rule;
 * - a value that cannot be read is **edited**, or the row is **excluded**.
 *
 * Every decision re-runs the checks on the whole file, and every decision - an
 * edit included - can be undone.
 */
export function AllocationImportDialog({
  packages,
  onImported,
}: {
  packages: AllocationPackage[];
  onImported: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [trainingPackage, setTrainingPackage] = React.useState('');
  const [file, setFile] = React.useState<File | null>(null);
  const [review, setReview] = React.useState<AllocationImportReview | null>(null);
  const [applyMode, setApplyMode] = React.useState<'REPLACE' | 'MERGE'>('MERGE');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [raiseSuggestions, setRaiseSuggestions] = React.useState(false);
  const [corrections, setCorrections] = React.useState<Correction[]>([]);
  const [exceptIds, setExceptIds] = React.useState<string[]>([]);
  const [raiseIds, setRaiseIds] = React.useState<string[]>([]);
  const [noRaiseIds, setNoRaiseIds] = React.useState<string[]>([]);
  const [excludeRows, setExcludeRows] = React.useState<number[]>([]);
  const [drafts, setDrafts] = React.useState<Record<string, string>>({});
  const reviewRequest = React.useRef(0);

  function fieldDraftKey(rowNumber: number, column: string) {
    return `${rowNumber}::${column}`;
  }

  function currentOverrides(next: Partial<AllocationImportOverrides> = {}): AllocationImportOverrides {
    return {
      corrections: next.corrections ?? corrections,
      except_ids: next.except_ids ?? exceptIds,
      raise_ids: next.raise_ids ?? raiseIds,
      no_raise_ids: next.no_raise_ids ?? noRaiseIds,
      exclude_rows: next.exclude_rows ?? excludeRows,
    };
  }

  function clearDecisions() {
    setCorrections([]);
    setExceptIds([]);
    setRaiseIds([]);
    setNoRaiseIds([]);
    setExcludeRows([]);
    setDrafts({});
    setRaiseSuggestions(false);
  }

  function clearFile() {
    reviewRequest.current += 1;
    setFile(null);
    setReview(null);
    setError(null);
    clearDecisions();
    setBusy(false);
  }

  function reset() {
    reviewRequest.current += 1;
    setTrainingPackage('');
    setFile(null);
    setReview(null);
    setApplyMode('MERGE');
    setBusy(false);
    setError(null);
    clearDecisions();
  }

  async function validateSelected(
    nextFile: File,
    nextRaise = raiseSuggestions,
    nextOverrides?: AllocationImportOverrides,
  ) {
    if (!trainingPackage) return;
    const overrides = nextOverrides ?? currentOverrides();
    const requestId = ++reviewRequest.current;
    setBusy(true);
    setError(null);
    try {
      const nextReview = await allocationApi.validateImport(trainingPackage, nextFile, nextRaise, overrides);
      if (requestId !== reviewRequest.current) return;
      setReview(nextReview);
      setDrafts({});
    } catch (caught) {
      if (requestId !== reviewRequest.current) return;
      setReview(null);
      setError(caught instanceof ReferenceApiError ? caught.message : 'The file could not be reviewed.');
    } finally {
      if (requestId === reviewRequest.current) setBusy(false);
    }
  }

  /** Record changed decisions and review the file again with them. */
  function revise(next: Partial<AllocationImportOverrides>, nextRaise = raiseSuggestions) {
    if (next.corrections) setCorrections(next.corrections);
    if (next.except_ids) setExceptIds(next.except_ids);
    if (next.raise_ids) setRaiseIds(next.raise_ids);
    if (next.no_raise_ids) setNoRaiseIds(next.no_raise_ids);
    if (next.exclude_rows) setExcludeRows(next.exclude_rows);
    if (nextRaise !== raiseSuggestions) setRaiseSuggestions(nextRaise);
    if (file) void validateSelected(file, nextRaise, currentOverrides(next));
  }

  async function apply() {
    if (!file || !review?.can_apply) return;
    setBusy(true);
    try {
      const result = await allocationApi.applyImport(
        trainingPackage,
        file,
        review.existing_deliveries ? applyMode : 'MERGE',
        raiseSuggestions,
        currentOverrides(),
      );
      toast.success(`Imported ${result.deliveries_written} deliveries and ${result.sessions_written} class days.`);
      setOpen(false);
      reset();
      onImported();
    } catch (caught) {
      setError(caught instanceof ReferenceApiError ? caught.message : 'The file could not be imported.');
    } finally {
      setBusy(false);
    }
  }

  function suggestionRaised(item: AllocationDiscrepancy) {
    if (noRaiseIds.includes(item.issue_id)) return false;
    if (raiseIds.includes(item.issue_id)) return true;
    return raiseSuggestions;
  }

  function toggleRaise(item: AllocationDiscrepancy) {
    const on = !suggestionRaised(item);
    revise({
      raise_ids: on ? unique([...raiseIds, item.issue_id]) : raiseIds.filter((id) => id !== item.issue_id),
      no_raise_ids: on ? noRaiseIds.filter((id) => id !== item.issue_id) : unique([...noRaiseIds, item.issue_id]),
    });
  }

  function toggleException(item: AllocationDiscrepancy) {
    const on = !exceptIds.includes(item.issue_id);
    revise({
      except_ids: on ? unique([...exceptIds, item.issue_id]) : exceptIds.filter((id) => id !== item.issue_id),
    });
  }

  function toggleExclude(rowNumber: number) {
    const on = !excludeRows.includes(rowNumber);
    revise({
      exclude_rows: on ? unique([...excludeRows, rowNumber]) : excludeRows.filter((row) => row !== rowNumber),
    });
  }

  function undoCorrection(entry: Correction) {
    revise({
      corrections: corrections.filter(
        (item) => !(item.row_number === entry.row_number && item.column === entry.column),
      ),
    });
  }

  const discrepancies = review?.discrepancies ?? [];
  const suggestionItems = discrepancies.filter((item) => item.category === 'SUGGESTION');
  const exceptionItems = discrepancies.filter((item) => item.category === 'EXCEPTION' && item.can_except);
  const allRaised = suggestionItems.length > 0 && suggestionItems.every((item) => suggestionRaised(item));
  const allAccepted =
    exceptionItems.length > 0 && exceptionItems.every((item) => exceptIds.includes(item.issue_id));

  return (
    <>
      <Button type="button" onClick={() => setOpen(true)}>
        <Upload aria-hidden="true" />
        Import Data
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) reset();
        }}
      >
        <DialogContent size="xl">
          <DialogHeader>
            <DialogTitle>Import allocation records</DialogTitle>
            <DialogDescription>
              A value that matches no approved record is raised as a suggestion. A broken rule is accepted as an
              exception for this import, edited, or its row excluded. A value that cannot be read is edited, or its row
              excluded.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <SimpleSelect
              value={trainingPackage}
              onChange={(value) => {
                setTrainingPackage(value);
                setReview(null);
                setFile(null);
              }}
              placeholder="Training package"
              options={packages.map((item) => ({
                value: item.training_package,
                label: item.has_profile ? item.training_package : `${item.training_package} (profile not ready)`,
                disabled: !item.enabled,
              }))}
            />
            <FileDropzone
              file={file}
              onClear={clearFile}
              actions={
                file ? (
                  <>
                    <Button
                      type="button"
                      size="sm"
                      variant={allRaised ? 'destructive' : 'outline'}
                      disabled={busy || !review || suggestionItems.length === 0}
                      onClick={() => {
                        if (allRaised) {
                          revise(
                            { raise_ids: [], no_raise_ids: suggestionItems.map((item) => item.issue_id) },
                            false,
                          );
                          return;
                        }
                        // The blanket flag means "raise every unmatched value", so the
                        // one-by-one lists are cleared rather than filled.
                        revise({ raise_ids: [], no_raise_ids: [] }, true);
                      }}
                    >
                      {allRaised ? <AlertTriangle aria-hidden="true" /> : null}
                      {allRaised ? 'Undo raise all' : 'Raise all suggestions'}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={busy || !review || exceptionItems.length === 0}
                      onClick={() =>
                        allAccepted
                          ? revise({
                              except_ids: exceptIds.filter(
                                (id) => !exceptionItems.some((item) => item.issue_id === id),
                              ),
                            })
                          : revise({ except_ids: unique([...exceptIds, ...exceptionItems.map((item) => item.issue_id)]) })
                      }
                    >
                      {allAccepted ? 'Undo accept all' : 'Accept all exceptions'}
                    </Button>
                  </>
                ) : null
              }
              disabled={!trainingPackage || busy}
              disabledMessage={
                !trainingPackage
                  ? 'Select a training package before uploading a file.'
                  : busy
                    ? 'Reviewing the workbook…'
                    : undefined
              }
              title="Drag and drop the allocation workbook here"
              hint="CSV or XLSX. Columns are matched by header name."
              onFileSelected={(next) => {
                setFile(next);
                setReview(null);
                clearDecisions();
                void validateSelected(next, false, NO_DECISIONS);
              }}
            />
            {busy && !review && (
              <p className="text-sm text-muted-foreground" role="status">
                Reviewing the workbook. Confirm stays unavailable until the review finishes and the file is accepted.
              </p>
            )}
            {error && <p className="text-sm text-destructive">{error}</p>}
            {review && (
              <div className="space-y-3 rounded-lg border border-border p-3 text-[13px]">
                {review.refused ? (
                  <p className="font-medium text-destructive">
                    Confirm import is blocked until each red item is raised, accepted, edited or excluded.
                  </p>
                ) : (
                  <p className="font-medium text-foreground">
                    Review complete. Accepted exceptions apply to this import only.
                  </p>
                )}
                <p>
                  {review.rows_read} rows · {review.deliveries_that_would_be_written} deliveries ·{' '}
                  {review.sessions_that_would_be_written} sessions · {review.intakes_matched} intakes matched ·{' '}
                  {review.suggestions_that_would_be_raised} suggestions · {review.exceptions_accepted ?? 0} exceptions
                  accepted · {review.rows_excluded ?? 0} rows excluded
                </p>

                {corrections.length > 0 && (
                  <div className="space-y-1 rounded-md border border-border bg-muted/40 p-2">
                    <p className="text-[12px] font-medium">Edits in this review</p>
                    <ul className="space-y-1">
                      {corrections.map((entry) => (
                        <li
                          key={`${entry.row_number}-${entry.column}`}
                          className="flex flex-wrap items-center gap-2 text-[12px]"
                        >
                          <span className="min-w-0 break-words">
                            Row {entry.row_number} · {entry.column} → “{entry.value}”
                          </span>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="h-6 gap-1 px-1.5 text-[12px]"
                            disabled={busy}
                            onClick={() => undoCorrection(entry)}
                          >
                            <Undo2 aria-hidden="true" className="size-3.5" />
                            Undo
                          </Button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {discrepancies.length > 0 && (
                  <ul className="max-h-80 space-y-2 overflow-auto">
                    {groupBySourceRow(discrepancies).map((group, groupIndex) => {
                      const rowNumber = group[0]?.row_number ?? null;
                      const excluded = group.some((item) => item.category === 'EXCLUDED');
                      const blocked = group.some((item) => item.severity === 'refuse');
                      const settled =
                        !blocked &&
                        !excluded &&
                        group.some(
                          (item) =>
                            (item.category === 'SUGGESTION' && suggestionRaised(item)) ||
                            (item.category === 'EXCEPTION' && exceptIds.includes(item.issue_id)),
                        );
                      const fields = excluded ? [] : uniqueEditFields(group);
                      const canEditRow = Boolean(rowNumber && rowNumber >= 2 && file && fields.length > 0);
                      const nothingOffered =
                        !canEditRow &&
                        group.every(
                          (item) => !item.can_except && !item.can_raise_suggestion && !item.can_exclude && !excluded,
                        );
                      return (
                        <li
                          key={rowNumber != null ? `row-${rowNumber}` : `group-${groupIndex}`}
                          className={cn(
                            'space-y-2 rounded-md border p-2',
                            blocked && 'border-destructive/35 bg-destructive-soft',
                            settled && 'border-success/35 bg-success-soft',
                            excluded && 'border-border bg-muted/40',
                          )}
                        >
                          <p
                            className={cn(
                              'font-medium',
                              blocked && 'text-destructive',
                              settled && 'text-success',
                              !blocked && !settled && 'text-muted-foreground',
                            )}
                          >
                            {excluded ? 'Excluded' : blocked ? 'Blocked' : settled ? 'Decided for this import' : 'Note'}
                            {rowNumber ? ` · row ${rowNumber}` : ''}
                          </p>
                          <ul className="space-y-1">
                            {group.map((item, itemIndex) => {
                              const raised = item.category === 'SUGGESTION' && suggestionRaised(item);
                              const accepted = item.category === 'EXCEPTION' && exceptIds.includes(item.issue_id);
                              return (
                                <li key={`${item.issue_id}-${itemIndex}`} className="space-y-1">
                                  <p>
                                    {item.column ? `${item.column} · ` : ''}
                                    {item.message}
                                  </p>
                                  {file && (
                                    <div className="flex flex-wrap items-center gap-2">
                                      {item.category === 'SUGGESTION' &&
                                        (raised ? (
                                          <DecisionTag
                                            label="Suggestion raised"
                                            disabled={busy}
                                            onUndo={() => toggleRaise(item)}
                                          />
                                        ) : (
                                          <Button
                                            type="button"
                                            size="sm"
                                            variant="outline"
                                            disabled={busy}
                                            onClick={() => toggleRaise(item)}
                                          >
                                            Raise suggestion
                                          </Button>
                                        ))}
                                      {item.category === 'EXCEPTION' &&
                                        item.can_except &&
                                        (accepted ? (
                                          <DecisionTag
                                            label="Exception accepted"
                                            disabled={busy}
                                            onUndo={() => toggleException(item)}
                                          />
                                        ) : (
                                          <Button
                                            type="button"
                                            size="sm"
                                            variant="outline"
                                            disabled={busy}
                                            onClick={() => toggleException(item)}
                                          >
                                            Accept exception
                                          </Button>
                                        ))}
                                      {item.can_exclude && rowNumber && (
                                        <Button
                                          type="button"
                                          size="sm"
                                          variant="outline"
                                          disabled={busy}
                                          onClick={() => toggleExclude(rowNumber)}
                                        >
                                          Exclude row
                                        </Button>
                                      )}
                                      {item.category === 'EXCLUDED' && rowNumber && (
                                        <DecisionTag
                                          label="Row excluded"
                                          disabled={busy}
                                          onUndo={() => toggleExclude(rowNumber)}
                                        />
                                      )}
                                    </div>
                                  )}
                                </li>
                              );
                            })}
                          </ul>
                          <div className="flex flex-wrap items-end gap-2">
                            {canEditRow && (
                              <>
                                {fields.map((field, fieldIndex) => {
                                  const draftKey = fieldDraftKey(rowNumber as number, field.column);
                                  const multiline =
                                    field.column.toLowerCase().includes('classroom name') ||
                                    field.column.toLowerCase().includes('days and times') ||
                                    field.value.includes('\n');
                                  const inputId = `alloc-edit-${groupIndex}-${fieldIndex}`;
                                  return (
                                    <div key={`${field.column}-${fieldIndex}`} className="min-w-40 flex-1 space-y-1">
                                      <Label htmlFor={inputId}>{fields.length === 1 ? 'Edit value' : field.column}</Label>
                                      {multiline ? (
                                        <Textarea
                                          id={inputId}
                                          rows={3}
                                          value={drafts[draftKey] ?? field.value}
                                          onChange={(event) =>
                                            setDrafts((current) => ({ ...current, [draftKey]: event.target.value }))
                                          }
                                        />
                                      ) : (
                                        <Input
                                          id={inputId}
                                          value={drafts[draftKey] ?? field.value}
                                          onChange={(event) =>
                                            setDrafts((current) => ({ ...current, [draftKey]: event.target.value }))
                                          }
                                        />
                                      )}
                                    </div>
                                  );
                                })}
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  disabled={busy}
                                  onClick={() => {
                                    let nextCorrections = corrections;
                                    for (const field of fields) {
                                      const value = drafts[fieldDraftKey(rowNumber as number, field.column)];
                                      // Only a field the reviewer actually changed becomes an
                                      // edit, so Undo lists what they did and nothing else.
                                      if (value === undefined || value === field.value) continue;
                                      nextCorrections = upsertCorrection(nextCorrections, {
                                        row_number: rowNumber as number,
                                        column: field.column,
                                        value,
                                      });
                                    }
                                    if (nextCorrections !== corrections) revise({ corrections: nextCorrections });
                                  }}
                                >
                                  Apply edit
                                </Button>
                              </>
                            )}
                            {nothingOffered && (
                              <p className="text-[12px] text-muted-foreground">
                                This must be fixed in the workbook (for example a missing required column).
                              </p>
                            )}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
                {review.existing_deliveries ? (
                  <ApplyModeChoice
                    value={applyMode}
                    onChange={setApplyMode}
                    existingDeliveries={review.existing_deliveries}
                  />
                ) : (
                  <p className="text-muted-foreground">
                    This package has no stored allocations yet. Confirm will insert the file.
                  </p>
                )}
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Discard
            </Button>
            <Button onClick={() => void apply()} disabled={!review?.can_apply || busy}>
              {busy && !review ? 'Reviewing…' : busy ? 'Importing…' : 'Confirm import'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}


/** Merge keeps what is stored; Replace removes it. Each choice says so in its own words. */
const APPLY_MODES = [
  {
    value: 'MERGE' as const,
    title: 'Merge',
    summary: 'Update matching classes and add new ones',
    detail: 'Classes already stored for this package are updated from the file, new rows are added, and anything the file does not mention is left as it is.',
  },
  {
    value: 'REPLACE' as const,
    title: 'Replace',
    summary: 'Delete stored classes, then load the file',
    detail: 'Every class stored for this package is deleted first, so the package ends up holding exactly what this file contains.',
  },
];

function ApplyModeChoice({
  value,
  onChange,
  existingDeliveries,
}: {
  value: 'REPLACE' | 'MERGE';
  onChange: (value: 'REPLACE' | 'MERGE') => void;
  existingDeliveries: number;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-[13px] font-medium text-foreground">How should this file be applied?</legend>
      <p className="text-[12px] text-muted-foreground">
        This package already holds {existingDeliveries.toLocaleString()} stored class
        {existingDeliveries === 1 ? '' : 'es'}.
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        {APPLY_MODES.map((mode) => {
          const selected = value === mode.value;
          return (
            <label
              key={mode.value}
              className={cn(
                'flex cursor-pointer gap-2.5 rounded-md border p-3 transition-colors',
                selected ? 'border-primary bg-primary-soft/40 ring-1 ring-primary/30' : 'border-border hover:bg-accent/40',
              )}
            >
              <input
                type="radio"
                name="allocation-apply-mode"
                className="mt-1 size-3.5 shrink-0 accent-[color:var(--primary)]"
                checked={selected}
                onChange={() => onChange(mode.value)}
              />
              <span className="min-w-0 space-y-1">
                <span className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[13px] font-semibold text-foreground">{mode.title}</span>
                  {mode.value === 'REPLACE' && (
                    <span className="rounded border border-destructive/30 bg-destructive-soft px-1 py-0.5 text-[10px] font-medium leading-none text-destructive">
                      Deletes stored classes
                    </span>
                  )}
                </span>
                <span className="block text-[12px] font-medium text-foreground">{mode.summary}</span>
                <span className="block text-[12px] leading-snug text-muted-foreground">{mode.detail}</span>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
