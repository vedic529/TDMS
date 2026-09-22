'use client';

import * as React from 'react';
import { Monitor, Users } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { SimpleSelect } from '@/components/common/dependent-select';
import { EmptyState } from '@/components/common/states';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';
import type {
  AllocationCalendar,
  AllocationCalendarDay,
  AllocationCalendarSession,
} from '@/services/allocation-api';
import { ALLOCATION_EMPTY_DESCRIPTION, ALLOCATION_EMPTY_TITLE } from '@/services/allocation-api';

const STREAM_STYLE = {
  THEORY: 'border-l-primary bg-primary-soft/60',
  PRACTICAL: 'border-l-success bg-success-soft/60',
  MSCRIS: 'border-l-info bg-info-soft/60',
} as const;

const ALL = '__all__';

/**
 * The allocation calendar (approved 17 September 2026).
 *
 * A day shows two numbers, not every class: the unique units with a class that
 * day, and the units the rolling timetable expects this week that no class
 * teaches yet. Clicking the day opens its classes. An MSCRIS class stays on the
 * day itself - it is one class for every college, so it is not clutter and has
 * nothing to filter.
 */
export function AllocationCalendar({
  grid,
  onSelect,
  openDate,
  onOpenDate,
}: {
  grid: AllocationCalendar;
  onSelect: (session: AllocationCalendarSession) => void;
  /** The day whose classes are open, kept by the caller so it can reopen after an edit. */
  openDate: string | null;
  onOpenDate: (date: string | null) => void;
}) {
  if (grid.empty) {
    return <EmptyState title={ALLOCATION_EMPTY_TITLE} description={ALLOCATION_EMPTY_DESCRIPTION} />;
  }

  const weeks: AllocationCalendar['days'][] = [];
  for (let index = 0; index < grid.days.length; index += 7) {
    weeks.push(grid.days.slice(index, index + 7));
  }
  const openDay = grid.days.find((day) => day.date === openDate) ?? null;

  return (
    <div className="space-y-3">
      {weeks.map((week) => (
        <div key={week[0]?.date} className="grid grid-cols-1 gap-2 md:grid-cols-7">
          {week.map((day) => (
            <DayCard key={day.date} day={day} onOpen={() => onOpenDate(day.date)} onSelect={onSelect} />
          ))}
        </div>
      ))}

      <DayClassesDialog
        day={openDay}
        onOpenChange={(open) => {
          if (!open) onOpenDate(null);
        }}
        onSelect={onSelect}
      />
    </div>
  );
}

function DayCard({
  day,
  onOpen,
  onSelect,
}: {
  day: AllocationCalendarDay;
  onOpen: () => void;
  onSelect: (session: AllocationCalendarSession) => void;
}) {
  const mscris = day.sessions.filter((item) => item.stream === 'MSCRIS');
  return (
    <section className="flex min-h-28 flex-col rounded-lg border border-border bg-card">
      <button
        type="button"
        onClick={onOpen}
        className="flex flex-1 flex-col rounded-t-lg p-2 text-left transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={`Open the classes on ${formatDate(day.date)}`}
      >
        <header className="flex w-full items-start justify-between gap-2">
          <p className="text-[11px] font-bold uppercase tracking-wide text-foreground">{day.weekday.slice(0, 3)}</p>
          <p className="text-[12px] font-bold tabular text-foreground">{formatDate(day.date)}</p>
        </header>
        <dl className="mt-auto w-full space-y-1 pt-4 text-[12px]">
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-muted-foreground">Allocated Units</dt>
            <dd className="tabular font-medium text-foreground">{day.allocated_unit_count}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-muted-foreground">Expected Allocation Units</dt>
            <dd className={cn('tabular font-medium', day.expected_unit_count > 0 ? 'text-warning' : 'text-foreground')}>
              {day.expected_unit_count}
            </dd>
          </div>
        </dl>
      </button>
      {mscris.length > 0 && (
        <div className="space-y-1.5 border-t border-border p-2">
          {mscris.map((item) => (
            <ClassBlock key={item.session_id} item={item} onSelect={onSelect} />
          ))}
        </div>
      )}
    </section>
  );
}

function ClassBlock({
  item,
  onSelect,
  detailed = false,
}: {
  item: AllocationCalendarSession;
  onSelect: (session: AllocationCalendarSession) => void;
  /** Inside the day's popup: every allocation detail, not the compact card. */
  detailed?: boolean;
}) {
  const isVirtual =
    item.delivery_mode === 'VIRTUAL' || /virtual|\bvc\b/i.test(item.classroom ?? '');

  return (
    <button
      type="button"
      onClick={() => onSelect(item)}
      className={cn(
        'w-full rounded border border-transparent border-l-2 px-2.5 py-2 text-left leading-tight',
        detailed ? 'text-[12px]' : 'text-[11px]',
        STREAM_STYLE[item.stream as keyof typeof STREAM_STYLE] ?? 'bg-muted',
        item.needs_allocation && 'ring-1 ring-destructive/40',
        item.not_found && 'ring-1 ring-warning/40',
      )}
    >
      {item.stream === 'MSCRIS' ? (
        <span className="flex items-center gap-1">
          <Badge variant="info" className="px-1 py-0 text-[10px]">
            MSCRIS
          </Badge>
          <span className="truncate text-muted-foreground">{item.unit_title}</span>
        </span>
      ) : (
        <span className="flex items-start justify-between gap-3">
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="truncate text-[13px] font-semibold">{item.unit_code}</span>
            {detailed && item.qualification_code && (
              <span
                className="shrink-0 rounded border border-border/70 bg-background/70 px-1 py-0.5 text-[9px] font-medium leading-none text-muted-foreground"
                title={`Qualification: ${item.qualification_code}`}
              >
                {item.qualification_code}
              </span>
            )}
          </span>
          {detailed && (
            <span className="min-w-0 max-w-[55%] shrink-0 text-right leading-snug">
              <span className="block truncate font-semibold" title={item.college}>{item.college}</span>
              <span className="block truncate text-[11px] text-muted-foreground" title={item.campus}>{item.campus}</span>
            </span>
          )}
        </span>
      )}
      <span className="block text-muted-foreground">
        {item.start_time}–{item.end_time}
        {detailed && item.stream !== 'MSCRIS' ? ` · ${item.stream.slice(0, 1)}${item.stream.slice(1).toLowerCase()}` : ''}
      </span>
      {isVirtual ? (
        <span className="flex h-4 items-center" title="Virtual class" aria-label="Virtual class">
          <Monitor aria-hidden="true" className="size-3.5 text-muted-foreground" />
        </span>
      ) : (
        <span className="block truncate">{item.classroom || 'Needs classroom'}</span>
      )}
      {(detailed || item.stream === 'MSCRIS') && item.trainer && <span className="block truncate">{item.trainer}</span>}
      {detailed && item.stream !== 'MSCRIS' && (
        <>
          <span className="block truncate text-muted-foreground">
            {formatDate(item.unit_start_date)} – {formatDate(item.unit_end_date)}
          </span>
        </>
      )}
      <span className="mt-1 flex items-center gap-1 text-[10px] text-muted-foreground">
        <Users aria-hidden="true" className="size-3" />
        {item.student_count}
      </span>
    </button>
  );
}

type FilterKey = 'college' | 'campus' | 'qualification' | 'duration' | 'unit' | 'start' | 'end';

const FILTERS: Array<{ key: FilterKey; label: string; value: (item: AllocationCalendarSession) => string; show?: (value: string) => string }> = [
  { key: 'college', label: 'College', value: (item) => item.college },
  { key: 'campus', label: 'Campus', value: (item) => item.campus },
  { key: 'qualification', label: 'Qualification', value: (item) => item.qualification_code },
  {
    key: 'duration',
    label: 'Duration',
    value: (item) => (item.duration_weeks ? String(item.duration_weeks) : ''),
    show: (value) => `${value} weeks`,
  },
  { key: 'unit', label: 'Unit', value: (item) => item.unit_code },
  { key: 'start', label: 'Unit start date', value: (item) => item.unit_start_date, show: (value) => formatDate(value) },
  { key: 'end', label: 'Unit end date', value: (item) => item.unit_end_date, show: (value) => formatDate(value) },
];

const NO_FILTERS: Record<FilterKey, string> = {
  college: ALL,
  campus: ALL,
  qualification: ALL,
  duration: ALL,
  unit: ALL,
  start: ALL,
  end: ALL,
};

/** One day's classes as a grid of blocks, with its seven filters and the week's expected units. */
function DayClassesDialog({
  day,
  onOpenChange,
  onSelect,
}: {
  day: AllocationCalendarDay | null;
  onOpenChange: (open: boolean) => void;
  onSelect: (session: AllocationCalendarSession) => void;
}) {
  const [filters, setFilters] = React.useState(NO_FILTERS);
  const [tab, setTab] = React.useState('classes');
  const date = day?.date ?? null;

  // A different day starts unfiltered; reopening the same day after an edit keeps them.
  const lastDate = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (date && date !== lastDate.current) {
      setFilters(NO_FILTERS);
      setTab('classes');
      lastDate.current = date;
    }
  }, [date]);

  const classes = React.useMemo(() => (day?.sessions ?? []).filter((item) => item.stream !== 'MSCRIS'), [day]);
  const shown = React.useMemo(
    () =>
      classes.filter((item) =>
        FILTERS.every((filter) => filters[filter.key] === ALL || filter.value(item) === filters[filter.key]),
      ),
    [classes, filters],
  );

  return (
    <Dialog open={day !== null} onOpenChange={onOpenChange}>
      <DialogContent size="full">
        {day && (
          <>
            <DialogHeader>
              <DialogTitle>
                {day.weekday.slice(0, 1)}
                {day.weekday.slice(1).toLowerCase()} {formatDate(day.date)}
              </DialogTitle>
              <DialogDescription>
                {day.allocated_unit_count} allocated unit{day.allocated_unit_count === 1 ? '' : 's'} ·{' '}
                {day.expected_unit_count} unit{day.expected_unit_count === 1 ? '' : 's'} expected this week and not yet
                allocated
              </DialogDescription>
            </DialogHeader>
            <DialogBody>
              <Tabs value={tab} onValueChange={setTab}>
                <TabsList>
                  <TabsTrigger value="classes">Allocated classes ({classes.length})</TabsTrigger>
                  <TabsTrigger value="expected">Expected units ({day.expected_unit_count})</TabsTrigger>
                </TabsList>

                <TabsContent value="classes" className="space-y-3">
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
                    {FILTERS.map((filter, filterIndex) => {
                      // Each option list is constrained by the selections to
                      // its left. A campus shown after choosing a college must
                      // therefore belong to an allocation for that college,
                      // rather than merely appearing elsewhere on this day.
                      const eligible = classes.filter((item) =>
                        FILTERS.slice(0, filterIndex).every(
                          (parent) =>
                            filters[parent.key] === ALL || parent.value(item) === filters[parent.key],
                        ),
                      );
                      const values = Array.from(new Set(eligible.map(filter.value).filter(Boolean))).sort();
                      return (
                        <div key={filter.key} className="space-y-1">
                          <p className="text-[11px] font-medium text-muted-foreground">{filter.label}</p>
                          <SimpleSelect
                            value={filters[filter.key]}
                            onChange={(value) =>
                              setFilters((current) => {
                                const next = { ...current, [filter.key]: value };
                                // A changed parent may make every later choice
                                // invalid, so return those filters to All.
                                for (const child of FILTERS.slice(filterIndex + 1)) {
                                  next[child.key] = ALL;
                                }
                                return next;
                              })
                            }
                            aria-label={filter.label}
                            placeholder="All"
                            options={[
                              { value: ALL, label: 'All' },
                              ...values.map((value) => ({ value, label: filter.show ? filter.show(value) : value })),
                            ]}
                          />
                        </div>
                      );
                    })}
                  </div>
                  <p className="text-[12px] text-muted-foreground">
                    Showing {shown.length} of {classes.length} class{classes.length === 1 ? '' : 'es'}
                  </p>
                  {classes.length === 0 ? (
                    <EmptyState title="No classes allocated" description="No Theory or Practical class runs on this day." />
                  ) : shown.length === 0 ? (
                    <EmptyState title="Nothing matches" description="Change or clear a filter." />
                  ) : (
                    <div className="grid max-h-[60vh] grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                      {shown.map((item) => (
                        <ClassBlock key={item.session_id} item={item} onSelect={onSelect} detailed />
                      ))}
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="expected">
                  {day.expected_units.length === 0 ? (
                    <EmptyState
                      title="Nothing outstanding"
                      description="Every unit the rolling timetable schedules this week has a class."
                    />
                  ) : (
                    <div className="max-h-[60vh] overflow-auto rounded-md border border-border">
                      <table className="w-full text-[12px]">
                        <thead className="sticky top-0 bg-muted text-left text-muted-foreground">
                          <tr>
                            <th className="px-2 py-1.5 font-medium">Unit</th>
                            <th className="px-2 py-1.5 font-medium">Qualifications</th>
                            <th className="px-2 py-1.5 font-medium">Intakes</th>
                          </tr>
                        </thead>
                        <tbody>
                          {day.expected_units.map((item) => (
                            <tr key={item.unit_code} className="border-t border-border align-top">
                              <td className="px-2 py-1.5 font-medium">{item.unit_code}</td>
                              <td className="px-2 py-1.5">{(item.qualification_codes ?? []).join(', ')}</td>
                              <td className="px-2 py-1.5 text-muted-foreground">{(item.intake_labels ?? []).join(', ')}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </TabsContent>
              </Tabs>
            </DialogBody>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
