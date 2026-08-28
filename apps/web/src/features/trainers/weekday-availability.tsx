import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

/** The stored per-day mode, as the API sends it. */
export type WeekdayMode = 'NOT_AVAILABLE' | 'PHYSICAL' | 'VIRTUAL';

export interface WeekdayModes {
  monday: string;
  tuesday: string;
  wednesday: string;
  thursday: string;
  friday: string;
}

const LABEL: Record<WeekdayMode, string> = {
  NOT_AVAILABLE: 'Not Available',
  PHYSICAL: 'Physical',
  VIRTUAL: 'Virtual',
};

const CODE: Record<WeekdayMode, string> = {
  NOT_AVAILABLE: '–',
  PHYSICAL: 'P',
  VIRTUAL: 'V',
};

const STYLE: Record<WeekdayMode, string> = {
  NOT_AVAILABLE: 'border-border bg-muted text-muted-foreground',
  PHYSICAL: 'border-primary/25 bg-primary-soft text-primary',
  VIRTUAL: 'border-info/25 bg-info-soft text-info',
};

const DAYS: Array<{ key: keyof WeekdayModes; label: string }> = [
  { key: 'monday', label: 'Monday' },
  { key: 'tuesday', label: 'Tuesday' },
  { key: 'wednesday', label: 'Wednesday' },
  { key: 'thursday', label: 'Thursday' },
  { key: 'friday', label: 'Friday' },
];

function mode(value: string): WeekdayMode {
  return value === 'PHYSICAL' || value === 'VIRTUAL' ? value : 'NOT_AVAILABLE';
}

/**
 * Compact Monday-to-Friday availability (SRS 8.3).
 *
 * Each day shows a letter code as well as a colour, so status is never conveyed
 * by colour alone, and the full value is available on hover and focus.
 *
 * Takes the five stored modes directly, so one component serves the list row
 * and the side panel's expanded tray.
 */
export function WeekdayAvailabilityStrip({ days }: { days: WeekdayModes }) {
  return (
    <span className="flex items-center gap-1">
      {DAYS.map((day) => {
        const value = mode(days[day.key]);
        return (
          <Tooltip key={day.key}>
            <TooltipTrigger asChild>
              <span
                tabIndex={0}
                className={cn(
                  'flex size-6 items-center justify-center rounded border text-[11px] font-semibold',
                  STYLE[value],
                )}
                aria-label={`${day.label}: ${LABEL[value]}`}
              >
                {CODE[value]}
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {day.label}: {LABEL[value]}
            </TooltipContent>
          </Tooltip>
        );
      })}
    </span>
  );
}

/** Monday to Friday with each day named — for the side panel's tray. */
export function WeekdayAvailabilityList({ days }: { days: WeekdayModes }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[12px]">
      {DAYS.map((day) => {
        const value = mode(days[day.key]);
        return (
          <div key={day.key} className="contents">
            <dt className="text-muted-foreground">{day.label}</dt>
            <dd
              className={cn(
                'w-fit rounded border px-1.5 text-[11px] font-medium',
                STYLE[value],
              )}
            >
              {LABEL[value]}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

export const AVAILABILITY_LEGEND = 'P = Physical, V = Virtual, – = Not Available';
