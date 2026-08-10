'use client';

import * as React from 'react';
import { ChevronLeft, ChevronRight, MapPin, User } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/common/states';
import { addDays, formatDate, rangesOverlap } from '@/lib/format';
import { WEEKDAYS, type TimetableSession, type Weekday } from '@/types/timetable';
import { cn } from '@/lib/utils';

interface CalendarEntry {
  session: TimetableSession;
  kind: 'Theory' | 'Practical' | 'MSCRIS';
  day: Weekday;
  startTime: string;
  endTime: string;
  facility: string;
  trainerId: string;
}

const KIND_STYLE = {
  Theory: 'border-l-primary bg-primary-soft/60',
  Practical: 'border-l-success bg-success-soft/60',
  MSCRIS: 'border-l-info bg-info-soft/60',
} as const;

/** Monday of the week that contains `date`. */
function weekStart(date: string): string {
  const value = new Date(`${date}T00:00:00Z`);
  const day = value.getUTCDay();
  const offset = day === 0 ? -6 : 1 - day;
  value.setUTCDate(value.getUTCDate() + offset);
  return value.toISOString().slice(0, 10);
}

/**
 * Weekly calendar presentation of the filtered timetable result.
 * Sessions repeat weekly inside their unit date range, so a session appears in
 * every week its range covers.
 */
export function TimetableCalendar({
  sessions,
  anchorDate,
  onSelect,
}: {
  sessions: TimetableSession[];
  anchorDate: string;
  onSelect: (session: TimetableSession) => void;
}) {
  const [start, setStart] = React.useState(() => weekStart(anchorDate));

  React.useEffect(() => {
    setStart(weekStart(anchorDate));
  }, [anchorDate]);

  const weekEnd = addDays(start, 6);

  const byDay = React.useMemo(() => {
    const map = new Map<Weekday, CalendarEntry[]>();
    WEEKDAYS.forEach((day) => map.set(day, []));

    for (const session of sessions) {
      if (!rangesOverlap(session.uocStartDate, session.uocEndDate, start, weekEnd)) continue;

      const entries: CalendarEntry[] = [
        ...session.theoryDaysAndTimes.map((slot) => ({
          session,
          kind: 'Theory' as const,
          startTime: slot.startTime,
          endTime: slot.endTime,
          facility: session.theoryClassroomName,
          trainerId: session.theoryTrainerId,
          day: slot.day,
        })),
        ...session.practicalDaysAndTimes.map((slot) => ({
          session,
          kind: 'Practical' as const,
          startTime: slot.startTime,
          endTime: slot.endTime,
          facility: session.practicalClassroomName,
          trainerId: session.practicalTrainerId,
          day: slot.day,
        })),
        ...session.mscrisDaysAndTimes.map((slot) => ({
          session,
          kind: 'MSCRIS' as const,
          startTime: slot.startTime,
          endTime: slot.endTime,
          facility: session.mscrisClassName,
          trainerId: session.mscrisTrainerId,
          day: slot.day,
        })),
      ];

      for (const entry of entries) {
        const bucket = map.get(entry.day);
        if (bucket) bucket.push(entry);
      }
    }

    map.forEach((entries) => entries.sort((a, b) => a.startTime.localeCompare(b.startTime)));
    return map;
  }, [sessions, start, weekEnd]);

  const total = Array.from(byDay.values()).reduce((sum, entries) => sum + entries.length, 0);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setStart(addDays(start, -7))}>
            <ChevronLeft aria-hidden="true" />
            Previous week
          </Button>
          <Button variant="outline" size="sm" onClick={() => setStart(addDays(start, 7))}>
            Next week
            <ChevronRight aria-hidden="true" />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setStart(weekStart(anchorDate))}>
            Reset
          </Button>
        </div>
        <p className="text-[13px] font-medium text-foreground">
          {formatDate(start)} – {formatDate(addDays(start, 4))}
          <span className="ml-2 font-normal text-muted-foreground">
            {total} scheduled {total === 1 ? 'class' : 'classes'}
          </span>
        </p>
      </div>

      {total === 0 ? (
        <EmptyState
          title="No timetable sessions fall in this week"
          description="Use the previous and next week controls, or adjust the date filters above."
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-5">
          {WEEKDAYS.map((day, index) => {
            const entries = byDay.get(day) ?? [];
            return (
              <section key={day} className="rounded-lg border border-border bg-card">
                <header className="border-b border-border px-3 py-2">
                  <p className="text-[13px] font-semibold text-foreground">{day}</p>
                  <p className="text-[12px] text-muted-foreground">{formatDate(addDays(start, index))}</p>
                </header>
                <div className="space-y-2 p-2">
                  {entries.length === 0 ? (
                    <p className="px-1 py-3 text-[12px] text-muted-foreground">No class scheduled.</p>
                  ) : (
                    entries.map((entry, entryIndex) => (
                      <button
                        key={`${entry.session.id}-${entry.kind}-${entryIndex}`}
                        type="button"
                        onClick={() => onSelect(entry.session)}
                        className={cn(
                          'w-full rounded-md border border-border border-l-4 px-2.5 py-2 text-left transition-shadow hover:shadow-sm',
                          KIND_STYLE[entry.kind],
                        )}
                      >
                        <span className="flex items-center justify-between gap-2">
                          <span className="text-[12px] font-semibold tabular text-foreground">
                            {entry.startTime}–{entry.endTime}
                          </span>
                          <Badge variant="outline" className="text-[10px]">
                            {entry.kind}
                          </Badge>
                        </span>
                        <span className="mt-1 block truncate text-[13px] font-medium text-foreground">
                          {entry.session.uocCode}
                        </span>
                        <span className="block truncate text-[12px] text-muted-foreground">
                          {entry.session.group}
                        </span>
                        <span className="mt-1 flex flex-col gap-0.5 text-[11px] text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <User className="size-3" aria-hidden="true" />
                            {entry.trainerId || 'No trainer assigned'}
                          </span>
                          <span className="flex items-center gap-1">
                            <MapPin className="size-3" aria-hidden="true" />
                            {entry.facility || 'No facility assigned'}
                          </span>
                        </span>
                      </button>
                    ))
                  )}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
