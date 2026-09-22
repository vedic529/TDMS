'use client';

import * as React from 'react';
import { AlertTriangle, ChevronDown, Loader2, Plus, Search, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { EmptyState } from '@/components/common/states';
import { ConfirmationDialog } from '@/components/common/confirmation-dialog';
import { SimpleSelect } from '@/components/common/dependent-select';
import { reasonsFor } from '@/lib/reasons';
import { usePermissions } from '@/features/auth/auth-context';
import {
  ENTITY_LABELS,
  suggestionsApi,
  type MapOptions,
  type AffectedRecords,
  type ReferenceSuggestion,
  type SuggestionEntityType,
} from '@/services/suggestions-api';
import { cn } from '@/lib/utils';

/** One page of entries inside the dialog. The true total is always stated. */
const PAGE_SIZE = 10;

/**
 * The outstanding suggestions for one tab.
 *
 * Replaces the inline red banner, which capped silently at eight entries and
 * asked an administrator to type a database id into a text box.
 *
 * Grey and inert when there is nothing to review — rendered rather than hidden,
 * so its place in the action row is stable. Red, counted and clickable when
 * there is. Colour is never the only signal: the count badge and the accessible
 * label carry the same information, and the glow is suppressed for anyone who
 * has asked for reduced motion.
 *
 * Suggestions only (15 September 2026). An exception is a broken rule accepted
 * for one import and is never recorded here, so this has no exceptions section.
 */
export function SuggestionIndicator({
  entityTypes,
  onResolved,
  onAdd,
}: {
  entityTypes: SuggestionEntityType[];
  onResolved?: () => void;
  /**
   * Opens the tab's own add form for this entry. A tab that can create the
   * record passes it; without it the entry offers Map and Reject only.
   */
  onAdd?: (row: ReferenceSuggestion) => void;
}) {
  const permissions = usePermissions();
  const canMaintain = permissions.maintainReferenceData;

  const [open, setOpen] = React.useState(false);
  const [pending, setPending] = React.useState(0);

  const key = entityTypes.join(',');

  /** One call to the summary endpoint, never one list call per entity. */
  const loadSummary = React.useCallback(async () => {
    try {
      const rows = await suggestionsApi.summary();
      const mine = rows.filter((row) => entityTypes.includes(row.entity_type));
      setPending(mine.reduce((total, row) => total + row.pending, 0));
    } catch {
      // A tab must still render if the queue cannot be read.
      setPending(0);
    }
    // `key` stands for the entity list; the array itself is a new object each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // Fetched when the tab mounts and after any resolution. Never on a timer.
  React.useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  const label =
    pending > 0
      ? `${pending} unmatched ${pending === 1 ? 'value needs' : 'values need'} review.`
      : 'No suggestions raised for this page.';

  const button = (
    <Button
      type="button"
      variant="outline"
      size="sm"
      aria-label={label}
      aria-disabled={pending > 0 ? undefined : 'true'}
      disabled={pending === 0}
      onClick={() => setOpen(true)}
      className={cn(
        'relative size-9 shrink-0 p-0',
        pending > 0
          ? 'border-destructive/40 bg-destructive-soft text-destructive hover:bg-destructive-soft motion-safe:animate-pulse'
          : 'text-muted-foreground',
      )}
    >
      <ShieldAlert aria-hidden="true" className="size-4" />
      {pending > 0 && (
        <span className="absolute -right-1.5 -top-1.5 min-w-4 rounded-full bg-destructive px-1 text-[10px] font-semibold leading-4 text-destructive-foreground tabular">
          {pending}
        </span>
      )}
    </Button>
  );

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          {/* A disabled button emits no pointer events, so the tooltip needs a
              wrapper to remain reachable when there is nothing to review. */}
          <span className="inline-flex">{button}</span>
        </TooltipTrigger>
        <TooltipContent>{label}</TooltipContent>
      </Tooltip>

      {open && (
        <SuggestionDialog
          entityTypes={entityTypes}
          open={open}
          onOpenChange={setOpen}
          canMaintain={canMaintain}
          onChanged={() => {
            void loadSummary();
            onResolved?.();
          }}
          onAdd={onAdd}
        />
      )}
    </>
  );
}

function SuggestionDialog({
  entityTypes,
  open,
  onOpenChange,
  canMaintain,
  onChanged,
  onAdd,
}: {
  entityTypes: SuggestionEntityType[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canMaintain: boolean;
  onChanged: () => void;
  onAdd?: (row: ReferenceSuggestion) => void;
}) {
  const [rows, setRows] = React.useState<ReferenceSuggestion[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [loading, setLoading] = React.useState(true);

  const key = entityTypes.join(',');

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const result = await suggestionsApi.list({
        entityTypes,
        status: 'PENDING',
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setRows(result.items);
      setTotal(result.total);
    } catch {
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, page]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="full">
        <DialogHeader>
          <DialogTitle>Suggestions</DialogTitle>
          <DialogDescription>
            Values from an import that match no approved record. Add each one, or map it to the record it
            means - resolving it repairs every stored record that used it.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <p className="text-right text-[12px] text-muted-foreground tabular">
            {total} {total === 1 ? 'entry' : 'entries'}
          </p>

          {loading ? (
            <p className="flex items-center gap-2 py-6 text-[13px] text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Loading…
            </p>
          ) : rows.length === 0 ? (
            <EmptyState
              title="Nothing to review"
              description="Every value on this page matches an approved record."
              icon={ShieldAlert}
            />
          ) : (
            <ul className="space-y-3">
              {rows.map((row) => (
                <SuggestionRow
                  key={row.id}
                  row={row}
                  canMaintain={canMaintain}
                  onChanged={() => {
                    void load();
                    onChanged();
                  }}
                  onAdd={
                    onAdd
                      ? (entry) => {
                          // The form opens over the page, not over this list.
                          onOpenChange(false);
                          onAdd(entry);
                        }
                      : undefined
                  }
                />
              ))}
            </ul>
          )}

          {pageCount > 1 && (
            <nav className="flex items-center justify-between gap-3" aria-label="Suggestion pages">
              <p className="text-[12px] text-muted-foreground">
                Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total}
              </p>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                  Previous
                </Button>
                <span className="text-[12px] text-muted-foreground tabular">
                  Page {page + 1} of {pageCount}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page >= pageCount - 1}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </nav>
          )}

          {!canMaintain && total > 0 && (
            <p className="text-[12px] text-muted-foreground">
              You can see what is outstanding. Resolving a value requires Admin access or above.
            </p>
          )}
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** `duration_weeks` → `duration weeks`, for the context shown beside an entry. */
function contextLabel(field: string): string {
  return field.replace(/_/g, ' ');
}

function SuggestionRow({
  row,
  canMaintain,
  onChanged,
  onAdd,
}: {
  row: ReferenceSuggestion;
  canMaintain: boolean;
  onChanged: () => void;
  onAdd?: (row: ReferenceSuggestion) => void;
}) {
  const [busy, setBusy] = React.useState(false);
  const [picking, setPicking] = React.useState(false);
  const [search, setSearch] = React.useState('');
  const [options, setOptions] = React.useState<MapOptions | null>(null);
  const [affected, setAffected] = React.useState<AffectedRecords | null>(null);

  const [showAffected, setShowAffected] = React.useState(false);
  const [rejecting, setRejecting] = React.useState(false);
  const [reasonCode, setReasonCode] = React.useState('');
  const [reasonDetail, setReasonDetail] = React.useState('');

  const contextText = Object.entries(row.context ?? {})
    .filter(([, value]) => value)
    .map(([field, value]) => `${contextLabel(field)}: ${value}`)
    .join(' · ');

  React.useEffect(() => {
    if (!picking) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      // Scoped on the server by the entry's own context - the qualification a
      // unit was raised under, the campus a room was named at, the intakes of a
      // class's qualification - because resolving that context is matching the
      // API already does for everything else.
      void suggestionsApi
        .mapOptions(row.id, search)
        .then((result) => {
          if (!cancelled) setOptions(result);
        })
        .catch(() => {
          if (!cancelled)
            setOptions({
              suggestion_id: row.id,
              entity_type: row.entity_type,
              scope_label: null,
              scope_id: null,
              scope_only: false,
              items: [],
              total: 0,
              truncated: false,
            });
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [picking, search, row.id, row.entity_type]);

  async function act(action: 'MAP' | 'REJECT', entityId?: number) {
    setBusy(true);
    try {
      const result = await suggestionsApi.resolve(row.id, action, entityId, undefined, {
        code: reasonCode || undefined,
        detail: reasonDetail || undefined,
      });
      // A resolution that repaired nothing is a warning, never a plain success:
      // it is exactly the condition that hid the original relink fault.
      if (result.records_updated === 0) {
        toast.warning('Resolved, but no stored records matched this value.', {
          description: `${ENTITY_LABELS[row.entity_type]} “${row.raw_value}” — check the spelling stored on the affected rows.`,
        });
      } else {
        toast.success(
          `${action === 'REJECT' ? 'Rejected' : 'Resolved'}. ${result.records_updated} record(s) updated.`,
        );
      }
      setPicking(false);
      setRejecting(false);
      onChanged();
    } catch (error) {
      toast.error('The decision could not be applied', {
        description: error instanceof Error ? error.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  /** Reject is destructive, so the records it removes are counted first. */
  async function startReject() {
    if (affected === null) {
      try {
        setAffected(await suggestionsApi.affected(row.id));
      } catch {
        setAffected({
          suggestion_id: row.id,
          entity_type: row.entity_type,
          raw_value: row.raw_value,
          total: 0,
          items: [],
          truncated: false,
        });
      }
    }
    setRejecting(true);
  }

  async function toggleAffected() {
    if (showAffected) {
      setShowAffected(false);
      return;
    }
    setShowAffected(true);
    if (affected === null) {
      try {
        setAffected(await suggestionsApi.affected(row.id));
      } catch {
        setAffected({
          suggestion_id: row.id,
          entity_type: row.entity_type,
          raw_value: row.raw_value,
          total: 0,
          items: [],
          truncated: false,
        });
      }
    }
  }

  const mapLabel = MAP_LABELS[row.entity_type] ?? 'Map to approved record';
  const studentsAffected = Boolean(affected?.items.some((item) => item.kind === 'student'));

  return (
    <li className="rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="neutral">{ENTITY_LABELS[row.entity_type]}</Badge>
        <span className="text-[13px] font-medium">“{row.raw_value}”</span>
        {contextText && <span className="text-[11px] text-muted-foreground">({contextText})</span>}
        <button
          type="button"
          onClick={() => void toggleAffected()}
          className="ml-auto inline-flex items-center gap-1 text-[12px] text-muted-foreground underline-offset-2 hover:underline"
        >
          {/* `occurrence_count` is how many times an import has met this value,
              not how many records it affects. It was labelled "Affects N
              records", which promised live impact and delivered a tally - so an
              entry read "Affects 1 record" while 192 rolling-timetable rows sat
              behind it, and the expansion said something different again.
              The tally is named for what it is; the live count is one click
              away and is the number that decides anything. */}
          <span title="How many times an import has met this value - not how many stored records carry it. Open to see the records.">
            Seen {row.occurrence_count} time{row.occurrence_count === 1 ? '' : 's'} on import
          </span>
          <ChevronDown aria-hidden="true" className={cn('size-3 transition-transform', showAffected && 'rotate-180')} />
        </button>
      </div>

      {showAffected && (
        <div className="mt-2 rounded-md border border-border bg-muted/40 p-2">
          {affected === null ? (
            <p className="text-[12px] text-muted-foreground">Loading…</p>
          ) : (
            <>
              <p className="mb-1 text-[12px] font-medium">
                {affected.total} stored record{affected.total === 1 ? '' : 's'} carry this value
                {affected.truncated &&
                  (affected.items.length > 0
                    ? ` — showing ${affected.items.length}`
                    : ' — none can be listed here')}
              </p>
              <AffectedTable items={affected.items} />
            </>
          )}
        </div>
      )}

      {canMaintain && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {picking ? (
            <div className="w-full space-y-2">
              <div className="relative">
                <Search
                  aria-hidden="true"
                  className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
                />
                <Input
                  autoFocus
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={
                    row.entity_type === 'ROLLING'
                      ? 'Search intakes'
                      : `Search approved ${ENTITY_LABELS[row.entity_type].toLowerCase()} records`
                  }
                  className="h-8 pl-8 text-[13px]"
                />
              </div>
              {options && (
                <p className="text-[11px] text-muted-foreground">
                  {options.scope_label
                    ? options.scope_only
                      ? `${options.scope_label} only${row.entity_type === 'ROLLING' ? ', in date order' : ', closest spelling first'}.`
                      : `Closest spelling first, then ${options.scope_label.toLowerCase()} (marked ●).`
                    : 'Closest spelling first.'}
                </p>
              )}
              <ul className="max-h-56 space-y-1 overflow-y-auto">
                {(options?.items ?? []).map((option) => (
                  <li key={option.id}>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-auto min-h-7 w-full justify-start py-1 text-left text-[12px]"
                      disabled={busy}
                      onClick={() => void act('MAP', option.id)}
                    >
                      <span className="flex flex-col items-start">
                        <span>
                          {option.in_scope && !options?.scope_only && (
                            <span aria-label="In scope" className="mr-1.5 text-primary">
                              ●
                            </span>
                          )}
                          {option.label}
                        </span>
                        {option.detail && (
                          <span className="text-[11px] text-muted-foreground">{option.detail}</span>
                        )}
                      </span>
                    </Button>
                  </li>
                ))}
                {options !== null && options.items.length === 0 && (
                  <li className="text-[12px] text-muted-foreground">
                    {row.entity_type === 'ROLLING'
                      ? 'No rolling timetable holds this qualification and duration.'
                      : 'No approved record matches.'}
                  </li>
                )}
                {options?.truncated && (
                  <li className="text-[11px] text-muted-foreground">
                    Showing {options.items.length} of {options.total}. Type to narrow the list.
                  </li>
                )}
              </ul>
              <Button variant="ghost" size="sm" className="h-7 text-[12px]" onClick={() => setPicking(false)}>
                Cancel
              </Button>
            </div>
          ) : (
            <>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-[12px]"
                disabled={busy}
                onClick={() => setPicking(true)}
              >
                {mapLabel}
              </Button>
              {onAdd && ADD_LABELS[row.entity_type] && (
                <Button
                  size="sm"
                  className="h-7 text-[12px]"
                  disabled={busy}
                  onClick={() => onAdd(row)}
                >
                  <Plus aria-hidden="true" className="size-3.5" />
                  {ADD_LABELS[row.entity_type]}
                </Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-[12px]"
                disabled={busy}
                onClick={() => void startReject()}
              >
                <AlertTriangle aria-hidden="true" className="size-3.5" />
                Reject
              </Button>
            </>
          )}
        </div>
      )}

      <ConfirmationDialog
        open={rejecting}
        onOpenChange={(next) => {
          setRejecting(next);
          if (!next) {
            setReasonCode('');
            setReasonDetail('');
          }
        }}
        title={`Reject “${row.raw_value}”?`}
        description={rejectDescription(row.entity_type, affected?.total ?? 0)}
        confirmLabel="Reject"
        variant="destructive"
        size="lg"
        busy={busy}
        confirmDisabled={studentsAffected && !reasonCode}
        onConfirm={() => void act('REJECT')}
      >
        {affected && affected.items.length > 0 && <AffectedTable items={affected.items} />}
        {studentsAffected && (
          <div className="space-y-2">
            <p className="text-[12px] text-muted-foreground">
              A student record is deleted the approved way: recoverable for the recycle period, with the
              reason recorded (DATA-04).
            </p>
            <div className="space-y-1">
              <label className="text-[12px] font-medium text-muted-foreground" htmlFor={`reject-reason-${row.id}`}>
                Deletion reason<span className="ml-0.5 text-destructive">*</span>
              </label>
              <SimpleSelect
                value={reasonCode}
                onChange={setReasonCode}
                options={reasonsFor('student').map((option) => ({ value: option.value, label: option.label }))}
                placeholder="Choose a reason"
              />
            </div>
            <Input
              value={reasonDetail}
              onChange={(event) => setReasonDetail(event.target.value)}
              placeholder="More detail (optional)"
              className="h-8 text-[13px]"
            />
          </div>
        )}
      </ConfirmationDialog>
    </li>
  );
}

/** What Reject will do to the stored records, said plainly before it is done. */
function rejectDescription(entity: SuggestionEntityType, total: number): string {
  const records = `${total} stored record${total === 1 ? '' : 's'}`;
  if (entity === 'TRAINER' || entity === 'FACILITY') {
    return `The name is cleared from ${records}. The classes themselves stay, reading as awaiting a ${
      entity === 'TRAINER' ? 'trainer' : 'room'
    }.`;
  }
  if (entity === 'CITY') {
    return `${records} keep their trainer, with no city recorded.`;
  }
  if (entity === 'UNIT') {
    return 'The rolling timetable is never changed by a rejection. The entry is recorded as rejected and closes.';
  }
  return `${records} carrying this value will be deleted, along with their class days. This cannot be undone - only re-importing the file brings them back.`;
}

/**
 * What Add says for each kind of entry, matching the tab's own button.
 *
 * COLLEGE has none: a college cannot be created, so its entries are mapped or
 * rejected.
 */
const ADD_LABELS: Partial<Record<SuggestionEntityType, string>> = {
  CAMPUS: 'Add location',
  QUALIFICATION: 'Add qualification',
  UNIT: 'Add unit',
  FACILITY: 'Add room',
  TRAINER: 'Add trainer',
  ROLLING: 'Add to rolling timetable',
  CITY: 'Add city',
};

/** Where Map means something other than "another spelling of a record". */
const MAP_LABELS: Partial<Record<SuggestionEntityType, string>> = {
  ROLLING: 'Map to an intake',
};

/**
 * Adding a record from a suggestion, for any tab.
 *
 * Add opens the tab's own form rather than a second copy of it in the queue, so
 * there is one form per record type. When the form has created the record, the
 * entry is resolved onto it - which relinks the rows that raised it and corrects
 * their spelling, exactly as Map does.
 *
 * `finish` reads the entry through a ref so it works whichever order a form
 * calls it and closes itself in. A form that ends up linking to an existing
 * record instead - placing a class in an intake without changing the rolling
 * timetable - finishes with MAP.
 */
export function useAddFromSuggestion() {
  const [suggestion, setSuggestion] = React.useState<ReferenceSuggestion | null>(null);
  const [epoch, setEpoch] = React.useState(0);
  const current = React.useRef<ReferenceSuggestion | null>(null);

  React.useEffect(() => {
    current.current = suggestion;
  }, [suggestion]);

  const start = React.useCallback((row: ReferenceSuggestion) => {
    current.current = row;
    setSuggestion(row);
  }, []);

  const cancel = React.useCallback(() => setSuggestion(null), []);

  const finish = React.useCallback(async (entityId: number, action: 'CREATE' | 'MAP' = 'CREATE') => {
    const entry = current.current;
    current.current = null;
    setSuggestion(null);
    if (!entry) return;
    try {
      const result = await suggestionsApi.resolve(entry.id, action, entityId);
      toast.success('Suggestion resolved', {
        description: `${ENTITY_LABELS[entry.entity_type]} “${entry.raw_value}” — ${result.records_updated} record(s) updated.`,
      });
    } catch (error) {
      toast.error(
        action === 'MAP'
          ? 'The suggestion could not be resolved'
          : 'The record was added, but the suggestion could not be resolved',
        {
          description: error instanceof Error ? error.message : 'Map it from the queue instead.',
        },
      );
    } finally {
      // Remounts the indicator so its count reflects the resolution.
      setEpoch((value) => value + 1);
    }
  }, []);

  return { suggestion, epoch, start, cancel, finish };
}

type AffectedItem = Record<string, unknown>;

function cell(value: unknown): string {
  return value === null || value === undefined ? '' : String(value);
}

function titleCase(value: unknown): string {
  const text = cell(value).toLowerCase();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : '';
}

const RECORD_KINDS: Record<string, string> = {
  delivery: 'Timetable class',
  session: 'Class day',
  student: 'Student',
  trainer: 'Trainer',
  trainer_location: 'Trainer location',
  rolling_intake: 'Rolling intake',
};

/**
 * The columns an affected record can fill. Only those some record fills are
 * shown, so a trainer's list reads as classes and a campus's as locations.
 */
const AFFECTED_COLUMNS: Array<{ key: string; label: string; value: (item: AffectedItem) => string }> = [
  { key: 'record', label: 'Record', value: (item) => RECORD_KINDS[cell(item.kind)] ?? cell(item.kind) },
  { key: 'student', label: 'Student', value: (item) => cell(item.student) },
  { key: 'qualification', label: 'Qualification', value: (item) => cell(item.qualification_code) },
  { key: 'unit', label: 'Unit', value: (item) => cell(item.unit_code) },
  { key: 'college', label: 'College', value: (item) => cell(item.college) },
  { key: 'campus', label: 'Campus', value: (item) => cell(item.campus) },
  { key: 'group', label: 'Group', value: (item) => (cell(item.group_code) === 'NA' ? '' : cell(item.group_code)) },
  {
    key: 'dates',
    label: 'Dates',
    value: (item) => (item.start_date ? `${cell(item.start_date)} to ${cell(item.end_date)}` : ''),
  },
  {
    key: 'class',
    label: 'Class',
    value: (item) =>
      item.weekday
        ? [titleCase(item.stream), titleCase(item.weekday), item.start_time ? `${cell(item.start_time)}–${cell(item.end_time)}` : '']
            .filter(Boolean)
            .join(' · ')
        : '',
  },
  { key: 'classroom', label: 'Classroom', value: (item) => cell(item.classroom) },
  { key: 'trainer', label: 'Trainer', value: (item) => cell(item.trainer) },
  {
    key: 'intake',
    label: 'Intake',
    value: (item) =>
      item.kind === 'rolling_intake'
        ? `${cell(item.intake_label)} · weeks ${cell(item.first_week)}–${cell(item.last_week)} (${cell(item.week_rows)} rows)`
        : '',
  },
];

/** The stored records an entry stands for, one row each, in a table. */
function AffectedTable({ items }: { items: AffectedItem[] }) {
  if (items.length === 0) {
    return (
      <p className="text-[11px] text-muted-foreground">
        No stored record carries this value any more, so there is nothing for it to repair.
      </p>
    );
  }
  const columns = AFFECTED_COLUMNS.filter((column) => items.some((item) => column.value(item)));
  return (
    <div className="max-h-64 overflow-auto rounded border border-border bg-background">
      <table className="w-full text-left text-[11px]">
        <thead className="sticky top-0 bg-muted text-muted-foreground">
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className="whitespace-nowrap px-2 py-1 font-medium">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => (
            <tr key={`${cell(item.kind)}-${cell(item.id)}-${index}`} className="border-t border-border/60">
              {columns.map((column) => (
                <td key={column.key} className="whitespace-nowrap px-2 py-1">
                  {column.value(item) || '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
