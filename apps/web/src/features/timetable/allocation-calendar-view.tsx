'use client';

import * as React from 'react';

import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/common/states';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { AllocationCalendar, AllocationCalendarSession } from '@/services/allocation-api';
import { ALLOCATION_EMPTY_DESCRIPTION, ALLOCATION_EMPTY_TITLE } from '@/services/allocation-api';

const STREAM_STYLE = {
  THEORY: 'border-l-primary bg-primary-soft/60',
  PRACTICAL: 'border-l-success bg-success-soft/60',
  MSCRIS: 'border-l-info bg-info-soft/60',
} as const;

export function AllocationCalendar({
  grid,
  onSelect,
}: {
  grid: AllocationCalendar;
  onSelect: (session: AllocationCalendarSession) => void;
}) {
  if (grid.empty) {
    return <EmptyState title={ALLOCATION_EMPTY_TITLE} description={ALLOCATION_EMPTY_DESCRIPTION} />;
  }

  const weeks: AllocationCalendar['days'][] = [];
  for (let index = 0; index < grid.days.length; index += 7) {
    weeks.push(grid.days.slice(index, index + 7));
  }

  return (
    <div className="space-y-3">
      {weeks.map((week) => (
        <div key={week[0]?.date} className="grid grid-cols-1 gap-2 md:grid-cols-7">
          {week.map((day) => (
            <section key={day.date} className="min-h-36 rounded-lg border border-border bg-card p-2">
              <header className="mb-2 flex items-baseline justify-between gap-2">
                <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{day.weekday.slice(0, 3)}</p>
                <p className="text-[12px] tabular text-foreground">{formatDate(day.date)}</p>
              </header>
              <div className="space-y-1.5">
                {day.sessions.map((item) => (
                  <button
                    key={item.session_id}
                    type="button"
                    onClick={() => onSelect(item)}
                    className={cn(
                      'w-full rounded border border-transparent px-2 py-1.5 text-left text-[11px] leading-tight',
                      STREAM_STYLE[item.stream as keyof typeof STREAM_STYLE] ?? 'bg-muted',
                      item.needs_allocation && 'ring-1 ring-destructive/40',
                      item.not_found && 'ring-1 ring-warning/40',
                    )}
                  >
                    <span className="block font-medium">{item.unit_code}</span>
                    <span className="block text-muted-foreground">
                      {item.start_time}–{item.end_time}
                    </span>
                    <span className="block truncate">{item.classroom || 'Needs classroom'}</span>
                    {item.intakes.length > 0 && (
                      <span className="mt-1 block truncate text-[10px] text-muted-foreground">
                        {item.intakes.join(', ')}
                      </span>
                    )}
                  </button>
                ))}
                {day.expected_units
                  .filter((item) => !item.scheduled)
                  .slice(0, 3)
                  .map((item) => (
                    <p key={`${item.intake_label}-${item.unit_code}`} className="px-1 text-[10px] text-muted-foreground">
                      Expected {item.unit_code}
                    </p>
                  ))}
                <p className="px-1 text-[10px] text-muted-foreground">Students {day.student_count ?? 0}</p>
              </div>
            </section>
          ))}
        </div>
      ))}
    </div>
  );
}
