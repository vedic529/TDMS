'use client';

import * as React from 'react';
import { AlertTriangle, Upload } from 'lucide-react';
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
    for (const field of fieldsForItem(item)) {
      if (field.column) byColumn.set(field.column, field);
    }
  }
  return Array.from(byColumn.values());
}

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
  const [applyMode, setApplyMode] = React.useState<'REPLACE' | 'MERGE'>('REPLACE');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [raiseSuggestions, setRaiseSuggestions] = React.useState(false);
  const [corrections, setCorrections] = React.useState<Correction[]>([]);
  const [exceptIds, setExceptIds] = React.useState<string[]>([]);
  const [raiseIds, setRaiseIds] = React.useState<string[]>([]);
  const [noRaiseIds, setNoRaiseIds] = React.useState<string[]>([]);
  const [drafts, setDrafts] = React.useState<Record<string, string>>({});
  const reviewRequest = React.useRef(0);

  function fieldDraftKey(rowNumber: number, column: string) {
    return `${rowNumber}::${column}`;
  }

  function currentOverrides(
    next: Partial<AllocationImportOverrides> = {},
  ): AllocationImportOverrides {
    return {
      corrections: next.corrections ?? corrections,
      except_ids: next.except_ids ?? exceptIds,
      raise_ids: next.raise_ids ?? raiseIds,
      no_raise_ids: next.no_raise_ids ?? noRaiseIds,
    };
  }

  function clearFile() {
    reviewRequest.current += 1;
    setFile(null);
    setReview(null);
    setError(null);
    setCorrections([]);
    setExceptIds([]);
    setRaiseIds([]);
    setNoRaiseIds([]);
    setDrafts({});
    setRaiseSuggestions(false);
    setBusy(false);
  }

  function reset() {
    reviewRequest.current += 1;
    setTrainingPackage('');
    setFile(null);
    setReview(null);
    setApplyMode('REPLACE');
    setBusy(false);
    setError(null);
    setRaiseSuggestions(false);
    setCorrections([]);
    setExceptIds([]);
    setRaiseIds([]);
    setNoRaiseIds([]);
    setDrafts({});
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
      toast.success(
        `Imported ${result.deliveries_written} deliveries and ${result.sessions_written} class days.`,
      );
      setOpen(false);
      reset();
      onImported();
    } catch (caught) {
      setError(caught instanceof ReferenceApiError ? caught.message : 'The file could not be imported.');
    } finally {
      setBusy(false);
    }
  }

  function suggestionChecked(item: AllocationDiscrepancy) {
    if (exceptIds.includes(item.issue_id)) return false;
    if (noRaiseIds.includes(item.issue_id)) return false;
    if (raiseIds.includes(item.issue_id)) return true;
    return raiseSuggestions;
  }

  const raisable = review?.discrepancies.filter((item) => item.can_raise_suggestion) ?? [];
  const exceptable = review?.discrepancies.filter((item) => item.can_except) ?? [];
  // An import may raise some values and accept others in the same pass, so the
  // two bulk actions work on what is still open rather than on the whole set.
  // A value already accepted as an exception is decided, not outstanding.
  const raisableOpen = raisable.filter((item) => !exceptIds.includes(item.issue_id));
  const allSuggestionsRaised =
    raisableOpen.length > 0 && raisableOpen.every((item) => suggestionChecked(item));
  const allExcepted = exceptable.length > 0 && exceptable.every((item) => exceptIds.includes(item.issue_id));

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
              Review each issue. You can edit the cell, raise a suggestion, or accept it as an exception.
              Confirm stays available once nothing is still blocked.
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
                      variant={allSuggestionsRaised ? 'destructive' : 'outline'}
                      disabled={busy || !review || raisableOpen.length === 0}
                      onClick={() => {
                        if (!file || !review) return;
                        const ids = raisableOpen.map((item) => item.issue_id);
                        if (allSuggestionsRaised) {
                          setRaiseSuggestions(false);
                          setRaiseIds([]);
                          setNoRaiseIds(ids);
                          void validateSelected(
                            file,
                            false,
                            currentOverrides({ raise_ids: [], no_raise_ids: ids }),
                          );
                          return;
                        }
                        // The blanket flag already means "raise everything still
                        // unresolved", and the server gives an accepted exception
                        // precedence over it. So `raise_ids` stays reserved for
                        // values raised one by one, and the exceptions stand.
                        setRaiseSuggestions(true);
                        setRaiseIds([]);
                        setNoRaiseIds([]);
                        void validateSelected(
                          file,
                          true,
                          currentOverrides({ raise_ids: [], no_raise_ids: [] }),
                        );
                      }}
                    >
                      {allSuggestionsRaised ? <AlertTriangle aria-hidden="true" /> : null}
                      Raise all suggestions
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={busy || !review || exceptable.length === 0 || allExcepted}
                      onClick={() => {
                        if (!file || !review) return;
                        // Values raised on their own row are left alone: this
                        // accepts what is still undecided, it does not overrule
                        // a decision already made.
                        const ids = exceptable
                          .filter((item) => !raiseIds.includes(item.issue_id))
                          .map((item) => item.issue_id);
                        const nextExcept = Array.from(new Set([...exceptIds, ...ids]));
                        const nextNoRaise = noRaiseIds.filter((id) => !ids.includes(id));
                        setExceptIds(nextExcept);
                        setNoRaiseIds(nextNoRaise);
                        void validateSelected(
                          file,
                          raiseSuggestions,
                          currentOverrides({
                            except_ids: nextExcept,
                            no_raise_ids: nextNoRaise,
                          }),
                        );
                      }}
                    >
                      Accept all exceptions
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
                setCorrections([]);
                setExceptIds([]);
                setRaiseIds([]);
                setNoRaiseIds([]);
                setDrafts({});
                setRaiseSuggestions(false);
                void validateSelected(next, false, {
                  corrections: [],
                  except_ids: [],
                  raise_ids: [],
                  no_raise_ids: [],
                });
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
                    Confirm import is blocked until each red item is edited, given a suggestion, or accepted as an
                    exception.
                  </p>
                ) : (
                  <p className="font-medium text-foreground">
                    Review complete. Grey items can still be edited or excepted before you confirm.
                  </p>
                )}
                <p>
                  {review.rows_read} rows · {review.deliveries_that_would_be_written} deliveries ·{' '}
                  {review.sessions_that_would_be_written} sessions · {review.intakes_matched} intakes matched ·{' '}
                  {review.intakes_not_matched} not matched · {review.suggestions_that_would_be_raised} suggestions
                </p>
                {review.discrepancies.length > 0 && (
                  <ul className="max-h-80 space-y-2 overflow-auto">
                    {groupBySourceRow(review.discrepancies).map((group, groupIndex) => {
                      const rowNumber = group[0]?.row_number ?? null;
                      const excepted = group.every((item) => exceptIds.includes(item.issue_id));
                      const raising =
                        group.some((item) => item.can_raise_suggestion && suggestionChecked(item) && !exceptIds.includes(item.issue_id));
                      const blocked = group.some((item) => item.severity === 'refuse' && !(item.can_raise_suggestion && suggestionChecked(item)));
                      const fields = uniqueEditFields(group);
                      const canEditRow = Boolean(rowNumber && rowNumber >= 2 && file && fields.length > 0);
                      return (
                        <li
                          key={rowNumber != null ? `row-${rowNumber}` : `group-${groupIndex}`}
                          className={cn(
                            'space-y-2 rounded-md border p-2',
                            blocked && 'border-destructive/35 bg-destructive-soft',
                            raising && !blocked && 'border-success/35 bg-success-soft',
                          )}
                        >
                          <p
                            className={cn(
                              'font-medium',
                              blocked && 'text-destructive',
                              raising && !blocked && 'text-success',
                              !blocked && !raising && 'text-muted-foreground',
                            )}
                          >
                            {blocked ? 'Blocked' : excepted ? 'Exception' : raising ? 'Raised' : 'Note'}
                            {rowNumber ? ` · row ${rowNumber}` : ''}
                          </p>
                          <ul className="space-y-1">
                            {group.map((item, itemIndex) => {
                              const issueId = item.issue_id || `${item.kind}-${rowNumber ?? 'x'}-${item.column ?? 'x'}-${itemIndex}`;
                              const itemExcepted = exceptIds.includes(item.issue_id || issueId);
                              const itemRaising = item.can_raise_suggestion && suggestionChecked(item) && !itemExcepted;
                              return (
                                <li key={`${issueId}-${itemIndex}`} className="space-y-1">
                                  <p>
                                    {item.column ? `${item.column} · ` : ''}
                                    {item.message}
                                  </p>
                                  <div className="flex flex-wrap items-center gap-2">
                                    {item.can_raise_suggestion && file && (
                                      <Button
                                        type="button"
                                        size="sm"
                                        variant={itemRaising ? 'destructive' : 'outline'}
                                        disabled={busy || itemExcepted}
                                        onClick={() => {
                                          const on = !itemRaising;
                                          const nextRaise = on
                                            ? Array.from(new Set([...raiseIds, issueId]))
                                            : raiseIds.filter((id) => id !== issueId);
                                          const nextNoRaise = on
                                            ? noRaiseIds.filter((id) => id !== issueId)
                                            : Array.from(new Set([...noRaiseIds, issueId]));
                                          const nextExcept = exceptIds.filter((id) => id !== issueId);
                                          setRaiseIds(nextRaise);
                                          setNoRaiseIds(nextNoRaise);
                                          setExceptIds(nextExcept);
                                          void validateSelected(
                                            file,
                                            raiseSuggestions,
                                            currentOverrides({
                                              raise_ids: nextRaise,
                                              no_raise_ids: nextNoRaise,
                                              except_ids: nextExcept,
                                            }),
                                          );
                                        }}
                                      >
                                        {itemRaising ? <AlertTriangle aria-hidden="true" /> : null}
                                        Raise suggestion
                                      </Button>
                                    )}
                                    {item.can_except && file && (
                                      <Button
                                        type="button"
                                        size="sm"
                                        variant="outline"
                                        disabled={busy || itemExcepted}
                                        onClick={() => {
                                          const nextExcept = Array.from(new Set([...exceptIds, issueId]));
                                          const nextRaise = raiseIds.filter((id) => id !== issueId);
                                          const nextNoRaise = noRaiseIds.filter((id) => id !== issueId);
                                          setExceptIds(nextExcept);
                                          setRaiseIds(nextRaise);
                                          setNoRaiseIds(nextNoRaise);
                                          void validateSelected(
                                            file,
                                            raiseSuggestions,
                                            currentOverrides({
                                              except_ids: nextExcept,
                                              raise_ids: nextRaise,
                                              no_raise_ids: nextNoRaise,
                                            }),
                                          );
                                        }}
                                      >
                                        {itemExcepted ? 'Exception accepted' : 'Accept exception'}
                                      </Button>
                                    )}
                                  </div>
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
                                    field.value.includes('\n');
                                  const inputId = `alloc-edit-${groupIndex}-${fieldIndex}`;
                                  return (
                                    <div key={`${field.column}-${fieldIndex}`} className="min-w-40 flex-1 space-y-1">
                                      <Label htmlFor={inputId}>
                                        {fields.length === 1 ? 'Edit value' : field.column}
                                      </Label>
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
                                      nextCorrections = upsertCorrection(nextCorrections, {
                                        row_number: rowNumber as number,
                                        column: field.column,
                                        value: drafts[fieldDraftKey(rowNumber as number, field.column)] ?? field.value,
                                      });
                                    }
                                    setCorrections(nextCorrections);
                                    // `file` is nullable while no upload is
                                    // selected; there is nothing to re-validate
                                    // in that state.
                                    if (file) {
                                      void validateSelected(
                                        file,
                                        raiseSuggestions,
                                        currentOverrides({ corrections: nextCorrections }),
                                      );
                                    }
                                  }}
                                >
                                  Apply edit
                                </Button>
                              </>
                            )}
                            {group.every((item) => !item.can_edit && !item.can_except && !item.can_raise_suggestion) && (
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
                  <SimpleSelect
                    value={applyMode}
                    onChange={(value) => setApplyMode(value as 'REPLACE' | 'MERGE')}
                    placeholder="How to apply this file"
                    options={[
                      {
                        value: 'REPLACE',
                        label: 'Replace — delete this package’s stored allocations, then insert the file',
                      },
                      {
                        value: 'MERGE',
                        label: 'Merge — update matching deliveries, insert new ones, leave the rest',
                      },
                    ]}
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
