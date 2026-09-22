'use client';

import * as React from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
import { attributeRecords } from '@/features/shared/suggestion-prefill';
import { cn } from '@/lib/utils';
import { ReferenceApiError } from '@/services/reference-api';
import { rollingTimetableApi, type RollingScope, type RollingWeek } from '@/services/rolling-timetable-api';
import type { ReferenceSuggestion } from '@/services/suggestions-api';

const DAY_MS = 86_400_000;

function dayNumber(value: string): number {
  return Date.parse(`${value}T00:00:00Z`);
}

function shortDate(value: string): string {
  if (!value) return '';
  return new Date(`${value}T00:00:00Z`).toLocaleDateString('en-AU', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

function scopeKeyOf(scope: Pick<RollingScope, 'qualification_code' | 'duration_weeks'>): string {
  return `${scope.qualification_code.toUpperCase()}|${scope.duration_weeks}`;
}

/**
 * Place a class the rolling timetable does not account for (approved 15 September 2026).
 *
 * Opened from a ROLLING suggestion. The qualification, intake and starting week
 * are chosen - each arrives pre-selected from the class where the timetable can
 * say - and the weeks the unit occupies follow from the class's own dates.
 *
 * If those weeks already hold a different unit, adding would replace it. That
 * is warned about, and Map is offered instead: the class is attached to the
 * intake and the rolling timetable is left exactly as it is.
 */
export function RollingPlacementDialog({
  open,
  onOpenChange,
  suggestion,
  onPlaced,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  suggestion: ReferenceSuggestion | null;
  /** A week of the chosen intake, and whether the timetable was written (CREATE) or only linked (MAP). */
  onPlaced: (weekId: number, action: 'CREATE' | 'MAP') => void;
}) {
  const unitCode = suggestion?.raw_value.trim() ?? '';
  const context = suggestion?.context ?? {};
  const classStart = String(context.start_date ?? '');
  const classEnd = String(context.end_date ?? '');
  const classWeeks =
    classStart && classEnd
      ? Math.max(1, Math.ceil((dayNumber(classEnd) - dayNumber(classStart) + DAY_MS) / (7 * DAY_MS)))
      : 1;
  const placedAt = attributeRecords(suggestion, 'classes')[0];

  const [scopes, setScopes] = React.useState<RollingScope[]>([]);
  const [scopeKey, setScopeKey] = React.useState('');
  const [intakes, setIntakes] = React.useState<string[]>([]);
  const [intake, setIntake] = React.useState('');
  const [weeks, setWeeks] = React.useState<RollingWeek[]>([]);
  const [startWeek, setStartWeek] = React.useState('');
  const [weekCount, setWeekCount] = React.useState('1');
  const [loading, setLoading] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  const scope = React.useMemo(
    () => scopes.find((row) => scopeKeyOf(row) === scopeKey) ?? null,
    [scopes, scopeKey],
  );

  // Opening: every rolling scope, with the class's own qualification and duration chosen.
  React.useEffect(() => {
    if (!open || !suggestion) return;
    setWeekCount(String(classWeeks));
    setIntakes([]);
    setIntake('');
    setWeeks([]);
    setStartWeek('');
    let cancelled = false;
    void rollingTimetableApi
      .listScopes()
      .then((rows) => {
        if (cancelled) return;
        setScopes(rows);
        const wanted = scopeKeyOf({
          qualification_code: String(context.qualification ?? ''),
          duration_weeks: Number(context.duration_weeks ?? 0),
        });
        setScopeKey(rows.some((row) => scopeKeyOf(row) === wanted) ? wanted : '');
      })
      .catch(() => {
        if (!cancelled) setScopes([]);
      });
    return () => {
      cancelled = true;
    };
    // The entry is what the dialog opens for; its fields are read from it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, suggestion?.id]);

  // The intakes of the chosen scope, with the one running in the class's first week chosen.
  React.useEffect(() => {
    if (!open || !scope) {
      setIntakes([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const facets = await rollingTimetableApi.listFacets(
          scope.training_package,
          scope.qualification_code,
          scope.duration_weeks,
        );
        if (cancelled) return;
        setIntakes(facets.intake_labels);
        let chosen = '';
        if (classStart) {
          const running = await rollingTimetableApi.listWeeks({
            trainingPackage: scope.training_package,
            qualificationCode: scope.qualification_code,
            durationWeeks: scope.duration_weeks,
            weekStartFrom: new Date(dayNumber(classStart) - 6 * DAY_MS).toISOString().slice(0, 10),
            weekStartTo: classStart,
            limit: 100,
          });
          chosen = running.items.find((row) => facets.intake_labels.includes(row.intake_label))?.intake_label ?? '';
        }
        if (!cancelled) setIntake(chosen);
      } catch {
        if (!cancelled) setIntakes([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, scope, classStart]);

  // The chosen intake's weeks, with the week holding the class's first day chosen.
  React.useEffect(() => {
    if (!open || !scope || !intake) {
      setWeeks([]);
      return;
    }
    let cancelled = false;
    void rollingTimetableApi
      .listWeeks({
        trainingPackage: scope.training_package,
        qualificationCode: scope.qualification_code,
        durationWeeks: scope.duration_weeks,
        intakeLabel: intake,
        limit: 200,
        sort: 'week_no',
        direction: 'asc',
      })
      .then((result) => {
        if (cancelled) return;
        // Slot 1: a week teaching two units at once has a second slot, and the
        // placement writes the first.
        const slotOne = result.items
          .filter((row) => row.unit_slot === 1)
          .sort((a, b) => a.week_no - b.week_no);
        setWeeks(slotOne);
        const holding = classStart
          ? slotOne.find((row) => row.week_start_date <= classStart && classStart <= row.week_end_date)
          : undefined;
        setStartWeek(String((holding ?? slotOne[0])?.week_no ?? ''));
      })
      .catch(() => {
        if (!cancelled) setWeeks([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open, scope, intake, classStart]);

  const count = Math.max(1, Number.parseInt(weekCount, 10) || 1);
  const first = Number.parseInt(startWeek, 10);
  const target = Number.isFinite(first)
    ? weeks.filter((row) => row.week_no >= first && row.week_no < first + count)
    : [];
  const complete = target.length === count;
  const sameUnit = (row: RollingWeek) => (row.unit_code ?? '').trim().toUpperCase() === unitCode.toUpperCase();
  const conflicts = target.filter((row) => row.schedule_type === 'UNIT' && !sameUnit(row));

  async function add() {
    if (!complete || target.length === 0) return;
    setBusy(true);
    try {
      await rollingTimetableApi.updateWeeks(
        target.map((row) => ({ id: row.id, schedule_type: 'UNIT' as const, schedule_value: unitCode })),
      );
      toast.success(`${unitCode} added to ${intake}`, {
        description: `Weeks ${target[0].week_no}–${target[target.length - 1].week_no}.`,
      });
      onPlaced(target[0].id, 'CREATE');
      onOpenChange(false);
    } catch (caught) {
      toast.error('The rolling timetable could not be updated', {
        description: caught instanceof ReferenceApiError ? caught.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  function mapInstead() {
    const week = target[0] ?? weeks[0];
    if (!week) return;
    onPlaced(week.id, 'MAP');
    onOpenChange(false);
  }

  const wantedLabel = `${String(context.qualification ?? '')} (${String(context.duration_weeks ?? '')} weeks)`;

  return (
    <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Add to the rolling timetable</DialogTitle>
          <DialogDescription>
            {unitCode} ran {shortDate(classStart)} to {shortDate(classEnd)}
            {placedAt ? ` (${[placedAt.college, placedAt.campus, placedAt.group].filter(Boolean).join(' · ')})` : ''}, and
            no intake accounts for it. Choose where it belongs.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label>Qualification</Label>
              <SimpleSelect
                value={scopeKey}
                onChange={(value) => {
                  setScopeKey(value);
                  setIntake('');
                }}
                options={scopes.map((row) => ({
                  value: scopeKeyOf(row),
                  label: `${row.qualification_code} · ${row.duration_weeks} weeks`,
                }))}
                placeholder="Choose the qualification"
              />
            </div>
            <div className="space-y-1">
              <Label>Intake</Label>
              <SimpleSelect
                value={intake}
                onChange={setIntake}
                options={intakes.map((label) => ({ value: label, label }))}
                placeholder={loading ? 'Loading intakes…' : 'Choose the intake'}
              />
            </div>
            <div className="space-y-1">
              <Label>Starting week</Label>
              <SimpleSelect
                value={startWeek}
                onChange={setStartWeek}
                options={weeks.map((row) => ({
                  value: String(row.week_no),
                  label: `Week ${row.week_no} · ${shortDate(row.week_start_date)} · ${row.schedule_value}`,
                }))}
                placeholder="Choose the week"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="rolling-weeks">Weeks occupied</Label>
              <Input
                id="rolling-weeks"
                type="number"
                min={1}
                value={weekCount}
                onChange={(event) => setWeekCount(event.target.value)}
              />
              <p className="text-[11px] text-muted-foreground">
                From the class dates: {classWeeks} week{classWeeks === 1 ? '' : 's'}.
              </p>
            </div>
          </div>

          {scopes.length > 0 && !scopeKey && (
            <p className="text-[12px] text-muted-foreground">
              No rolling timetable holds {wantedLabel}. Import it first, or choose another qualification.
            </p>
          )}

          {target.length > 0 && (
            <div className="space-y-1">
              <p className="text-[12px] font-medium text-muted-foreground">What changes</p>
              <ul className="space-y-1">
                {target.map((row) => {
                  const clash = row.schedule_type === 'UNIT' && !sameUnit(row);
                  return (
                    <li
                      key={row.id}
                      className={cn(
                        'flex flex-wrap items-center gap-2 rounded-md border px-2 py-1 text-[12px]',
                        clash ? 'border-destructive/35 bg-destructive-soft text-destructive' : 'border-border',
                      )}
                    >
                      <span className="font-medium tabular">Week {row.week_no}</span>
                      <span className="text-muted-foreground">
                        {shortDate(row.week_start_date)} – {shortDate(row.week_end_date)}
                      </span>
                      <span>
                        {sameUnit(row) ? `${row.schedule_value} (already)` : `${row.schedule_value} → ${unitCode}`}
                      </span>
                    </li>
                  );
                })}
              </ul>
              {!complete && (
                <p className="text-[12px] text-destructive">
                  The intake ends at week {weeks[weeks.length - 1]?.week_no}. Choose fewer weeks or an earlier start.
                </p>
              )}
            </div>
          )}

          {conflicts.length > 0 && (
            <div
              role="alert"
              className="flex gap-2 rounded-md border border-warning/30 bg-warning-soft p-2 text-[12px] text-warning"
            >
              <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
              <p>
                {conflicts.length === 1 ? `Week ${conflicts[0].week_no} holds` : `${conflicts.length} of these weeks hold`}{' '}
                {Array.from(new Set(conflicts.map((row) => row.schedule_value))).join(', ')}. Adding replaces{' '}
                {conflicts.length === 1 ? 'it' : 'them'}. To leave the rolling timetable as it is, map the class to
                this intake instead.
              </p>
            </div>
          )}
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          {conflicts.length > 0 && (
            <Button variant="outline" onClick={mapInstead} disabled={busy || target.length === 0}>
              Map to this intake instead
            </Button>
          )}
          <Button
            variant={conflicts.length > 0 ? 'destructive' : 'default'}
            onClick={() => void add()}
            disabled={busy || !complete || target.length === 0}
          >
            {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
            {conflicts.length > 0 ? 'Replace and add' : 'Add to rolling timetable'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
