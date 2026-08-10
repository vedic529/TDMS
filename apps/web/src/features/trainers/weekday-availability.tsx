import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { TrainerRecord, WeekdayAvailability } from '@/types/trainer';

const CODE: Record<WeekdayAvailability, string> = {
  'Not Available': '–',
  Physical: 'P',
  Virtual: 'V',
};

const STYLE: Record<WeekdayAvailability, string> = {
  'Not Available': 'border-border bg-muted text-muted-foreground',
  Physical: 'border-primary/25 bg-primary-soft text-primary',
  Virtual: 'border-info/25 bg-info-soft text-info',
};

const DAYS: Array<{ key: keyof Pick<TrainerRecord, 'monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday'>; short: string; label: string }> = [
  { key: 'monday', short: 'M', label: 'Monday' },
  { key: 'tuesday', short: 'T', label: 'Tuesday' },
  { key: 'wednesday', short: 'W', label: 'Wednesday' },
  { key: 'thursday', short: 'T', label: 'Thursday' },
  { key: 'friday', short: 'F', label: 'Friday' },
];

/**
 * Compact Monday-to-Friday availability (SRS 8.3).
 * Each day shows a letter code as well as a colour so status is never conveyed
 * by colour alone, and the full value is available on hover and focus.
 */
export function WeekdayAvailabilityStrip({ trainer }: { trainer: TrainerRecord }) {
  return (
    <span className="flex items-center gap-1">
      {DAYS.map((day) => {
        const value = trainer[day.key];
        return (
          <Tooltip key={day.key}>
            <TooltipTrigger asChild>
              <span
                tabIndex={0}
                className={cn(
                  'flex size-6 items-center justify-center rounded border text-[11px] font-semibold',
                  STYLE[value],
                )}
                aria-label={`${day.label}: ${value}`}
              >
                {CODE[value]}
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {day.label}: {value}
            </TooltipContent>
          </Tooltip>
        );
      })}
    </span>
  );
}

export const AVAILABILITY_LEGEND = 'P = Physical, V = Virtual, – = Not Available';
