import type { DayTimeSlot, IsoDate, IsoDateTime } from '@/types';

/**
 * SRS 2.3: dates, counts and calculated values must be derived by one approved
 * rule and shown consistently on screen, in exports and in stored records.
 * Every formatter used by TDMS lives here.
 */

const DISPLAY_DATE = new Intl.DateTimeFormat('en-AU', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
});

const DISPLAY_DATE_TIME = new Intl.DateTimeFormat('en-AU', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'UTC',
});

/** Formats an ISO date as `05 Aug 2026`. Returns an em dash when empty. */
export function formatDate(value: IsoDate | undefined | null): string {
  if (!value) return '—';
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return DISPLAY_DATE.format(date);
}

/** Formats an ISO date and time as `05 Aug 2026, 14:32` (UTC). */
export function formatDateTime(value: IsoDateTime | undefined | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${DISPLAY_DATE_TIME.format(date)} UTC`;
}

export function formatCurrency(value: number | undefined | null): string {
  if (value === undefined || value === null) return '—';
  return new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD', maximumFractionDigits: 0 }).format(
    value,
  );
}

export function formatWeeks(value: number | undefined | null): string {
  if (value === undefined || value === null) return '—';
  return `${value} ${value === 1 ? 'week' : 'weeks'}`;
}

export function formatSlots(slots: DayTimeSlot[] | undefined): string {
  if (!slots || slots.length === 0) return '—';
  return slots.map((slot) => `${slot.day} ${slot.startTime}-${slot.endTime}`).join(', ');
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Adds whole days to an ISO date without touching the local time zone. */
export function addDays(value: IsoDate, days: number): IsoDate {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function daysBetween(from: IsoDate, to: IsoDate): number {
  const start = new Date(`${from}T00:00:00Z`).getTime();
  const end = new Date(`${to}T00:00:00Z`).getTime();
  return Math.round((end - start) / 86_400_000);
}

/** Today as an ISO date, evaluated on demand so it is never captured at build time. */
export function today(): IsoDate {
  return new Date().toISOString().slice(0, 10);
}

export function nowIso(): IsoDateTime {
  return new Date().toISOString();
}

/** True when two date ranges overlap. Used by TT-03 and the clash checks. */
export function rangesOverlap(aStart: IsoDate, aEnd: IsoDate, bStart: IsoDate, bEnd: IsoDate): boolean {
  return aStart <= bEnd && bStart <= aEnd;
}

/** True when two `HH:mm` time windows on the same day overlap. */
export function timesOverlap(aStart: string, aEnd: string, bStart: string, bEnd: string): boolean {
  return aStart < bEnd && bStart < aEnd;
}
