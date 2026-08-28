'use client';

import * as React from 'react';
import { CalendarDays, ChevronDown, Loader2, TriangleAlert } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { EmptyState, ErrorState } from '@/components/common/states';
import {
  studentsApi,
  type StudentRecord,
  type StudentTimetable,
  type TimetableClass,
  type TimetableRow,
} from '@/services/students-api';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';

/** `09:00` → `9:00 am`, matching the approved `9 am to 5 pm` convention. */
function formatTime(value: string): string {
  const [rawHour, minute] = value.split(':');
  const hour = Number.parseInt(rawHour ?? '', 10);
  if (Number.isNaN(hour)) return value;
  const meridian = hour < 12 ? 'am' : 'pm';
  const display = hour % 12 === 0 ? 12 : hour % 12;
  return `${display}:${minute} ${meridian}`;
}

/** The full sentence for each empty state — never "no timetable found". */
function emptyMessage(data: StudentTimetable): { title: string; description: string } {
  switch (data.empty_reason) {
    case 'CREDIT_TRANSFER':
      return {
        title: 'Credit Transfer student',
        description:
          'This is a Credit Transfer student, who has no intake and therefore no rolling timetable.',
      };
    case 'NO_ROLLING_TIMETABLE':
      return {
        title: 'No rolling timetable',
        description: `No rolling timetable has been imported for ${data.qualification.code} at ${
          data.qualification.duration_weeks ?? '—'
        } weeks, so this student's intake cannot be determined yet.`,
      };
    case 'NO_ROLLING_ROWS':
      return {
        title: 'No weeks stored for this intake',
        description: `This student is assigned to intake ${
          data.intake.label ?? '—'
        }, but no rolling-timetable weeks are stored for it.`,
      };
    default:
      return { title: '', description: '' };
  }
}

const TIMING_LABEL: Record<string, string> = {
  BEFORE_JOINING: 'Before this student joined',
  AFTER_END: "After this student's course ends",
};

/**
 * One student's own timetable.
 *
 * A dialog rather than a second side panel: a stacked sheet is too narrow for a
 * class table and awkward to dismiss. The detail panel stays open beneath.
 *
 * The request fires when this opens, not when the detail panel does — browsing
 * records must not cost a timetable fetch per row. Expanding a unit costs no
 * further request; every class is already in the response.
 */
export function StudentTimetableDialog({
  student,
  open,
  onOpenChange,
}: {
  student: StudentRecord | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [data, setData] = React.useState<StudentTimetable | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const studentPk = student?.id ?? null;

  const load = React.useCallback(async () => {
    if (studentPk === null) return;
    setLoading(true);
    setError(null);
    try {
      setData(await studentsApi.getTimetable(studentPk));
    } catch (caught) {
      setData(null);
      setError(caught instanceof Error ? caught.message : 'The timetable could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [studentPk]);

  React.useEffect(() => {
    if (open) void load();
  }, [open, load]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="xl">
        <DialogHeader>
          <DialogTitle>
            {student ? `${student.student_id} — ${student.first_name} ${student.last_name ?? ''}`.trim() : 'Timetable'}
          </DialogTitle>
          <DialogDescription>
            {data
              ? `${data.qualification.code} ${data.qualification.title ?? ''} · Intake ${
                  data.intake.label ?? '—'
                } · Group ${data.intake.group_code ?? '—'} · ${data.scope.campus}`
              : 'The units this student studies, drawn from their intake.'}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          {data && !data.empty_reason && (
            <p className="text-[13px] text-muted-foreground tabular">
              {data.summary.units_total} units · {data.summary.units_allocated} allocated ·{' '}
              {data.summary.units_unallocated} unallocated · {data.summary.classes_total} classes
            </p>
          )}

          {loading ? (
            <div className="space-y-2" aria-busy="true" aria-live="polite">
              <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                Loading the timetable…
              </p>
              {[0, 1, 2, 3].map((n) => (
                <div key={n} className="h-12 animate-pulse rounded-md bg-muted/60" />
              ))}
            </div>
          ) : error ? (
            <div className="space-y-3">
              <ErrorState title="The timetable could not be loaded" description={error} />
              <Button variant="outline" size="sm" onClick={() => void load()}>
                Retry
              </Button>
            </div>
          ) : data?.empty_reason ? (
            <EmptyState {...emptyMessage(data)} icon={CalendarDays} />
          ) : data ? (
            <ul className="space-y-2">
              {data.rows.map((row, index) => (
                <TimetableRowItem key={`${row.row_type}-${row.week_from}-${index}`} row={row} index={index} />
              ))}
            </ul>
          ) : null}
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

function TimetableRowItem({ row, index }: { row: TimetableRow; index: number }) {
  const [expanded, setExpanded] = React.useState(false);
  const panelId = `timetable-row-${index}`;

  const dates = `${formatDate(row.week_from)} to ${formatDate(row.week_to)}`;
  const dimmed = row.timing !== 'DURING';

  // A break and an assessment week are not buttons: there is nothing to expand.
  if (row.row_type !== 'UNIT') {
    const isBreak = row.row_type === 'BREAK';
    return (
      <li
        className={cn(
          'rounded-md border px-3 py-2 text-[13px]',
          isBreak
            ? 'border-destructive/30 bg-destructive-soft text-destructive'
            : 'border-warning/30 bg-warning-soft text-warning',
          dimmed && 'opacity-60',
        )}
      >
        <span className="font-medium">{isBreak ? 'Break' : 'Assessment Week'}</span>
        <span className="mx-1.5">·</span>
        <span className="tabular">{dates}</span>
        {dimmed && <span className="ml-2 text-[11px]">({TIMING_LABEL[row.timing]})</span>}
      </li>
    );
  }

  const allocated = row.allocation_status === 'ALLOCATED';
  const canExpand = allocated && !row.expansion_refused && row.classes.length > 0;

  return (
    <li className={cn('rounded-md border border-border', dimmed && 'opacity-60')}>
      {canExpand ? (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          aria-controls={panelId}
          className="flex w-full flex-wrap items-center gap-2 px-3 py-2 text-left hover:bg-accent/50"
        >
          <ChevronDown
            aria-hidden="true"
            className={cn('size-4 shrink-0 transition-transform', expanded && 'rotate-180')}
          />
          <UnitHeading row={row} dates={dates} />
        </button>
      ) : (
        <div className="flex flex-wrap items-center gap-2 px-3 py-2">
          {/* No chevron: an unallocated unit has nothing to expand. */}
          <span className="size-4 shrink-0" aria-hidden="true" />
          <UnitHeading row={row} dates={dates} />
        </div>
      )}

      {!allocated && (
        <p className="px-3 pb-2 pl-9 text-[12px] text-muted-foreground">
          No allocation records for this unit yet.
        </p>
      )}

      {row.span_note && (
        <p className="flex items-start gap-1.5 px-3 pb-2 pl-9 text-[12px] text-warning">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
          {row.span_note}
        </p>
      )}

      {row.expansion_refused && (
        <p className="px-3 pb-2 pl-9 text-[12px] text-muted-foreground">
          The stored dates span too long a period to list class by class. Check the allocation record.
        </p>
      )}

      {expanded && canExpand && (
        <div id={panelId} className="border-t border-border px-3 py-2">
          <ClassTable classes={row.classes} />
        </div>
      )}
    </li>
  );
}

function UnitHeading({ row, dates }: { row: TimetableRow; dates: string }) {
  return (
    <>
      <span className="text-[13px] font-medium">{row.unit_code}</span>
      {row.unit_title && (
        <span className="truncate text-[12px] text-muted-foreground">{row.unit_title}</span>
      )}
      <span className="text-[12px] text-muted-foreground tabular">{dates}</span>
      {/* The badge carries the word, so colour is never the only signal. */}
      <Badge
        variant={row.allocation_status === 'ALLOCATED' ? 'success' : 'neutral'}
        className="ml-auto"
      >
        {row.allocation_status === 'ALLOCATED' ? 'Allocated' : 'Unallocated'}
      </Badge>
      {row.timing !== 'DURING' && (
        <span className="text-[11px] text-muted-foreground">{TIMING_LABEL[row.timing]}</span>
      )}
    </>
  );
}

function ClassTable({ classes }: { classes: TimetableClass[] }) {
  // A subheading only earns its place when the unit has more than one stream.
  const streams = [...new Set(classes.map((item) => item.stream))];
  const groups = streams.map((stream) => ({
    stream,
    rows: classes.filter((item) => item.stream === stream),
  }));

  return (
    <div className="space-y-3">
      {groups.map((group) => (
        <div key={group.stream}>
          {streams.length > 1 && (
            <p className="mb-1 text-[12px] font-medium text-muted-foreground">
              {group.stream.charAt(0) + group.stream.slice(1).toLowerCase()}
            </p>
          )}
          {/* The table scrolls inside its own container; the dialog body never
              scrolls horizontally. */}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-[12px]">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-1 pr-3 font-medium">Date</th>
                  <th className="py-1 pr-3 font-medium">Day</th>
                  <th className="py-1 pr-3 font-medium">Start</th>
                  <th className="py-1 pr-3 font-medium">End</th>
                  <th className="py-1 pr-3 font-medium">Mode</th>
                  <th className="py-1 pr-3 font-medium">Classroom</th>
                  <th className="py-1 font-medium">Campus</th>
                </tr>
              </thead>
              <tbody>
                {group.rows.map((item, index) => (
                  <tr key={`${item.date}-${item.start_time}-${index}`} className="border-b border-border/50">
                    <td className="py-1 pr-3 tabular">{formatDate(item.date)}</td>
                    <td className="py-1 pr-3">
                      {item.weekday.charAt(0) + item.weekday.slice(1).toLowerCase()}
                    </td>
                    <td className="py-1 pr-3 tabular">{formatTime(item.start_time)}</td>
                    <td className="py-1 pr-3 tabular">{formatTime(item.end_time)}</td>
                    <td className="py-1 pr-3">{item.mode_label}</td>
                    <td className="py-1 pr-3">
                      {item.classroom}
                      {item.classroom_unresolved && <Unresolved />}
                    </td>
                    <td className="py-1">
                      {item.campus}
                      {item.campus_unresolved && <Unresolved />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

/** An unresolved value is marked, never hidden and never blank. */
function Unresolved() {
  return <span className="ml-1 text-[10px] text-muted-foreground">(unresolved)</span>;
}
