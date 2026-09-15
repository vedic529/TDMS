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
import { usePermissions } from '@/features/auth/auth-context';
import {
  ENTITY_LABELS,
  suggestionsApi,
  type MapOptions,
  type AffectedRecords,
  type ReferenceSuggestion,
  type SuggestionEntityType,
} from '@/services/suggestions-api';
import { formatDateTime } from '@/lib/format';
import { cn } from '@/lib/utils';

/** One page of entries inside the dialog. The true total is always stated. */
const PAGE_SIZE = 10;

/**
 * The outstanding reference values for one tab.
 *
 * Replaces the inline red banner, which capped silently at eight entries and
 * asked an administrator to type a database id into a text box.
 *
 * Grey and inert when there is nothing to review — rendered rather than hidden,
 * so its place in the action row is stable. Red, counted and clickable when
 * there is. Colour is never the only signal: the count badge and the accessible
 * label carry the same information, and the glow is suppressed for anyone who
 * has asked for reduced motion.
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
  const [exceptions, setExceptions] = React.useState(0);

  const key = entityTypes.join(',');

  /** One call to the summary endpoint, never one list call per entity. */
  const loadSummary = React.useCallback(async () => {
    try {
      const rows = await suggestionsApi.summary();
      const mine = rows.filter((row) => entityTypes.includes(row.entity_type));
      setPending(mine.reduce((total, row) => total + row.pending, 0));
      setExceptions(mine.reduce((total, row) => total + row.exceptions, 0));
    } catch {
      // A tab must still render if the queue cannot be read.
      setPending(0);
      setExceptions(0);
    }
    // `key` stands for the entity list; the array itself is a new object each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // Fetched when the tab mounts and after any resolution. Never on a timer.
  React.useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  const total = pending + exceptions;
  // Clickable whenever there is anything to look at. Exceptions are not an
  // outstanding *task* — they never turn the icon red — but they are a recorded
  // state that must stay reachable, or an accepted value becomes invisible with
  // no way to promote or withdraw it.
  const hasAnything = total > 0;
  const label =
    pending > 0
      ? `${pending} unmatched ${pending === 1 ? 'value needs' : 'values need'} review.`
      : exceptions > 0
        ? `${exceptions} accepted exception${exceptions === 1 ? '' : 's'} on record. Nothing needs review.`
        : 'No suggestions raised for this page.';

  const button = (
    <Button
      type="button"
      variant="outline"
      size="sm"
      aria-label={label}
      aria-disabled={hasAnything ? undefined : 'true'}
      disabled={!hasAnything}
      onClick={() => setOpen(true)}
      className={cn(
        'relative size-9 shrink-0 p-0',
        pending > 0
          ? 'border-destructive/40 bg-destructive-soft text-destructive hover:bg-destructive-soft motion-safe:animate-pulse'
          : 'text-muted-foreground',
      )}
    >
      <ShieldAlert aria-hidden="true" className="size-4" />
      {/* Red and counted for a pending decision; a quiet count for exceptions,
          which are on record rather than outstanding. */}
      {pending > 0 ? (
        <span className="absolute -right-1.5 -top-1.5 min-w-4 rounded-full bg-destructive px-1 text-[10px] font-semibold leading-4 text-destructive-foreground tabular">
          {pending}
        </span>
      ) : exceptions > 0 ? (
        <span className="absolute -right-1.5 -top-1.5 min-w-4 rounded-full bg-muted px-1 text-[10px] font-semibold leading-4 text-muted-foreground tabular ring-1 ring-border">
          {exceptions}
        </span>
      ) : null}
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
        <TooltipContent>
          {pending > 0
            ? label
            : exceptions > 0
              ? `Nothing to review. ${exceptions} accepted exception${exceptions === 1 ? '' : 's'} on record.`
              : 'No suggestions raised for this page.'}
        </TooltipContent>
      </Tooltip>

      {open && (
        <SuggestionDialog
          entityTypes={entityTypes}
          open={open}
          onOpenChange={setOpen}
          canMaintain={canMaintain}
          exceptionCount={exceptions}
          totalCount={total}
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
  exceptionCount,
  totalCount,
  onChanged,
  onAdd,
}: {
  entityTypes: SuggestionEntityType[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canMaintain: boolean;
  exceptionCount: number;
  totalCount: number;
  onChanged: () => void;
  onAdd?: (row: ReferenceSuggestion) => void;
}) {
  // Open on the section that has something in it. Landing on an empty
  // "Suggestions" list while exceptions sit one click away reads as "nothing is
  // here", which is the very confusion this indicator exists to prevent.
  const [section, setSection] = React.useState<'PENDING' | 'EXCEPTION'>(() =>
    totalCount - exceptionCount > 0 ? 'PENDING' : 'EXCEPTION',
  );
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
        status: section,
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
  }, [key, section, page]);

  React.useEffect(() => {
    void load();
  }, [load]);

  React.useEffect(() => {
    setPage(0);
  }, [section]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="full">
        <DialogHeader>
          <DialogTitle>Unmatched reference values</DialogTitle>
          <DialogDescription>
            Values from an import that do not match an approved record. Resolving one repairs every
            stored record that used it.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant={section === 'PENDING' ? 'default' : 'outline'}
              onClick={() => setSection('PENDING')}
            >
              Suggestions
            </Button>
            <Button
              size="sm"
              variant={section === 'EXCEPTION' ? 'default' : 'outline'}
              onClick={() => setSection('EXCEPTION')}
            >
              Exceptions
              {exceptionCount > 0 && (
                <Badge variant="warning" className="ml-1.5 tabular">
                  {exceptionCount}
                </Badge>
              )}
            </Button>
            <span className="ml-auto text-[12px] text-muted-foreground tabular">
              {total} {total === 1 ? 'entry' : 'entries'}
            </span>
          </div>

          {section === 'EXCEPTION' && (
            <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-[12px] text-muted-foreground">
              An exception is a value allowed to stand without an approved match. It is recorded, not
              approved — promote it with Create or Map, or withdraw it to decide again.
            </p>
          )}

          {loading ? (
            <p className="flex items-center gap-2 py-6 text-[13px] text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Loading…
            </p>
          ) : rows.length === 0 ? (
            <EmptyState
              title={section === 'PENDING' ? 'Nothing to review' : 'No exceptions on record'}
              description={
                section === 'PENDING'
                  ? 'Every reference value on this page matches an approved record.'
                  : 'No value on this page has been accepted without an approved match.'
              }
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

          {!canMaintain && totalCount > 0 && (
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

  const contextText = Object.entries(row.context ?? {})
    .filter(([, value]) => value)
    .map(([field, value]) => `${field}: ${value}`)
    .join(' · ');

  React.useEffect(() => {
    if (!picking) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      // Scoped on the server by the entry's own context - the qualification a
      // unit was raised under, the campus a room was named at - because that
      // context is stored as text and resolving it is matching the API
      // already does for everything else.
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

  async function act(
    action: 'CREATE' | 'MAP' | 'REJECT' | 'WITHDRAW',
    entityId?: number,
    createValues?: Record<string, string>,
  ) {
    setBusy(true);
    try {
      const result = await suggestionsApi.resolve(row.id, action, entityId, createValues);
      // A resolution that repaired nothing is a warning, never a plain success:
      // it is exactly the condition that hid the original relink fault.
      if (action !== 'WITHDRAW' && result.records_updated === 0) {
        toast.warning('Resolved, but no stored records matched this value.', {
          description: `${ENTITY_LABELS[row.entity_type]} “${row.raw_value}” — check the spelling stored on the affected rows.`,
        });
      } else {
        toast.success(
          action === 'WITHDRAW'
            ? 'Returned to the suggestions queue.'
            : `${action === 'REJECT' ? 'Rejected' : 'Resolved'}. ${result.records_updated} record(s) updated.`,
        );
      }
      setPicking(false);
      onChanged();
    } catch (error) {
      toast.error('The decision could not be applied', {
        description: error instanceof Error ? error.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
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
          Seen {row.occurrence_count} time{row.occurrence_count === 1 ? '' : 's'} on import
          <ChevronDown aria-hidden="true" className={cn('size-3 transition-transform', showAffected && 'rotate-180')} />
        </button>
      </div>

      {row.status === 'EXCEPTION' && row.accepted_at && (
        <p className="mt-1 text-[11px] text-muted-foreground">
          Accepted {formatDateTime(row.accepted_at)}
          {row.accepted_by_user_id ? ` by user #${row.accepted_by_user_id}` : ''}.
        </p>
      )}

      {showAffected && (
        <div className="mt-2 rounded-md border border-border bg-muted/40 p-2">
          {affected === null ? (
            <p className="text-[12px] text-muted-foreground">Loading…</p>
          ) : (
            <>
              <p className="mb-1 text-[12px] font-medium">
                {affected.total} affected record{affected.total === 1 ? '' : 's'}
                {affected.truncated &&
                  (affected.items.length > 0
                    ? ` — showing ${affected.items.length}`
                    : ' — none can be listed here')}
              </p>
              <ul className="max-h-40 space-y-0.5 overflow-y-auto">
                {affected.items.map((item, index) => (
                  <li key={index} className="text-[11px] text-muted-foreground">
                    {/* A membership entry's rows are rolling-timetable weeks,
                        summarised one line per intake: 192 week rows are eight
                        intakes teaching the unit, and eight lines say that
                        where 192 do not. */}
                    {item.kind === 'rolling_intake'
                      ? `${item.intake_label} · weeks ${item.first_week}-${item.last_week} (${item.week_rows} row${item.week_rows === 1 ? '' : 's'})`
                      : [
                      item.qualification_code,
                      item.unit_code,
                      item.campus,
                      item.college,
                      item.classroom,
                      item.trainer,
                          item.start_date,
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                  </li>
                ))}
              </ul>
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
                  placeholder={`Search approved ${ENTITY_LABELS[row.entity_type].toLowerCase()} records`}
                  className="h-8 pl-8 text-[13px]"
                />
              </div>
              {options && (
                <p className="text-[11px] text-muted-foreground">
                  {options.scope_label
                    ? options.scope_only
                      ? `${options.scope_label} only, closest spelling first.`
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
                  <li className="text-[12px] text-muted-foreground">No approved record matches.</li>
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
                Map to approved record
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
                onClick={() => void act('REJECT')}
              >
                <AlertTriangle aria-hidden="true" className="size-3.5" />
                Reject
              </Button>
              {row.status === 'EXCEPTION' && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-[12px]"
                  disabled={busy}
                  onClick={() => void act('WITHDRAW')}
                >
                  Withdraw
                </Button>
              )}
            </>
          )}
        </div>
      )}

    </li>
  );
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
 * calls it and closes itself in.
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

  const finish = React.useCallback(async (entityId: number) => {
    const entry = current.current;
    current.current = null;
    setSuggestion(null);
    if (!entry) return;
    try {
      const result = await suggestionsApi.resolve(entry.id, 'CREATE', entityId);
      toast.success('Suggestion resolved', {
        description: `${ENTITY_LABELS[entry.entity_type]} “${entry.raw_value}” — ${result.records_updated} record(s) updated.`,
      });
    } catch (error) {
      toast.error('The record was added, but the suggestion could not be resolved', {
        description: error instanceof Error ? error.message : 'Map it from the queue instead.',
      });
    } finally {
      // Remounts the indicator so its count reflects the resolution.
      setEpoch((value) => value + 1);
    }
  }, []);

  return { suggestion, epoch, start, cancel, finish };
}
