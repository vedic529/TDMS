/**
 * Fixed anchor used by every seeded demo record.
 *
 * Seed data must be deterministic: a value derived from `Date.now()` at module
 * load would differ between the server render and the browser render and would
 * also change every time the prototype is reloaded. `2026-08-03` is a Monday,
 * which keeps generated weekly timetable dates readable.
 */
export const DEMO_ANCHOR_DATE = '2026-08-03';

/** Demo timestamps are derived from the anchor so exports stay reproducible. */
export function anchorDateTime(dayOffset: number, hour = 9, minute = 0): string {
  const date = new Date(`${DEMO_ANCHOR_DATE}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + dayOffset);
  date.setUTCHours(hour, minute, 0, 0);
  return date.toISOString();
}

export function anchorDate(dayOffset: number): string {
  const date = new Date(`${DEMO_ANCHOR_DATE}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + dayOffset);
  return date.toISOString().slice(0, 10);
}
