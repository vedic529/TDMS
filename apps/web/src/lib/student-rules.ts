import type { Campus, College } from '@/types/reference';
import { daysBetween } from './format';

/**
 * Approved student business rules (SRS 6.3 / SST-03).
 *
 * **This module is the single source of truth for the frontend.** No component
 * hard-codes a qualification code, a group name or an intake format. Raising
 * the maximum group number is one constant here, not an edit across components.
 *
 * It mirrors `apps/api/app/core/student_rules.py`. The API is authoritative -
 * it validates every value regardless of what the browser sent - so the two
 * files must always change together.
 */

// ---------------------------------------------------------------------------
// Group
// ---------------------------------------------------------------------------

/**
 * Qualifications that use numbered Groups. Every other qualification uses N/A.
 * Approved 11 August 2026.
 */
export const GROUP_ENABLED_QUALIFICATIONS: readonly string[] = [
  'SIT40721',
  'SIT40521',
  'SIT30821',
  'SIT31021',
  'SIT50422',
  'SIT60322',
  'SIT50122',
  'SIT60122',
  'RII50520',
  'RII60520',
];

/**
 * The highest numbered Group currently approved.
 *
 * **Raising the limit is a one-line change here.** Options, validation and the
 * tests all derive from this value.
 */
export const MAX_NUMBERED_GROUP = 15;

/** The value used when a qualification does not use numbered Groups. */
export const NO_GROUP = 'N/A';

/**
 * Accepts exactly `Group <n>` with no leading zeros and no extra spacing, so
 * `G1`, `group 1`, `Group 01` and ` Group 1 ` are rejected rather than quietly
 * turned into something the user did not type.
 */
const GROUP_PATTERN = /^Group ([1-9][0-9]*)$/;

/** `['Group 1', …, 'Group N']` - generated, never a literal array. */
export function numberedGroups(maximum: number = MAX_NUMBERED_GROUP): string[] {
  return Array.from({ length: maximum }, (_, index) => `Group ${index + 1}`);
}

export function usesNumberedGroups(qualificationCode: string | null | undefined): boolean {
  return GROUP_ENABLED_QUALIFICATIONS.includes((qualificationCode ?? '').trim().toUpperCase());
}

/**
 * The Group values a user may choose for this qualification. A group-enabled
 * qualification offers the numbered range; everything else offers only `N/A`,
 * which the interface shows as read-only.
 */
export function groupOptionsFor(qualificationCode: string | null | undefined): string[] {
  return usesNumberedGroups(qualificationCode) ? numberedGroups() : [NO_GROUP];
}

/** The numeric part of a well-formed group name, or null. */
export function groupNumber(group: string | null | undefined): number | null {
  const match = GROUP_PATTERN.exec((group ?? '').trim());
  return match ? Number.parseInt(match[1], 10) : null;
}

/** Null when valid; otherwise the message to show the user. */
export function validateGroup(
  qualificationCode: string | null | undefined,
  group: string | null | undefined,
): string | null {
  const value = (group ?? '').trim();
  const range = `Group 1–Group ${MAX_NUMBERED_GROUP}`;

  if (!usesNumberedGroups(qualificationCode)) {
    if (value === '' || value === NO_GROUP) return null;
    return `${qualificationCode} does not use numbered groups. The Group must be ${NO_GROUP}.`;
  }

  if (value === '' || value === NO_GROUP) {
    return `${qualificationCode} requires a group. Choose one of ${range}.`;
  }

  const number = groupNumber(value);
  if (number === null || number < 1 || number > MAX_NUMBERED_GROUP) {
    return `"${value}" is not a valid group. Choose one of ${range}.`;
  }
  return null;
}

/**
 * The Group value to hold after the qualification changes.
 *
 * Switching away from a group-enabled qualification must not leave `Group 5`
 * behind on a qualification that has no groups, and switching *into* one must
 * not leave `N/A` in a field that now needs a real choice. An empty string
 * means "the user must now choose".
 */
export function groupAfterQualificationChange(
  newQualificationCode: string | null | undefined,
  currentGroup: string | null | undefined,
): string {
  if (!usesNumberedGroups(newQualificationCode)) return NO_GROUP;

  const number = groupNumber(currentGroup);
  if (number !== null && number >= 1 && number <= MAX_NUMBERED_GROUP) {
    // A still-valid numbered group carries over between two group-enabled
    // qualifications rather than being cleared for no reason.
    return currentGroup as string;
  }
  return '';
}

// ---------------------------------------------------------------------------
// Intake
// ---------------------------------------------------------------------------

/**
 * English three-letter month labels used by the approved `DD-MMM-YYYY` format.
 * Written out rather than taken from `toLocaleString`, which follows the
 * browser locale and would render `août` for a French-locale user.
 */
export const MONTH_LABELS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
] as const;

export const INTAKE_DISPLAY_FORMAT = 'DD-MMM-YYYY';

/**
 * Intake = the first day of the proposed start month, as an ISO date.
 *
 * `2026-08-18` -> `2026-08-01`. Kept as a date rather than a formatted string
 * so that sorting and comparison stay correct; formatting happens at the
 * display and export boundary only.
 */
export function deriveIntakeDate(proposedStartDate: string): string {
  if (!proposedStartDate) return '';
  const [year, month] = proposedStartDate.split('-');
  const monthIndex = Number.parseInt(month ?? '', 10);
  if (!year || Number.isNaN(monthIndex) || monthIndex < 1 || monthIndex > 12) return '';
  return `${year}-${String(monthIndex).padStart(2, '0')}-01`;
}

/** Render an intake as the approved `DD-MMM-YYYY`, e.g. `01-Aug-2026`. */
export function formatIntake(isoDate: string): string {
  if (!isoDate) return '';
  const [year, month, day] = isoDate.split('-');
  const monthIndex = Number.parseInt(month ?? '', 10) - 1;
  if (!year || !day || Number.isNaN(monthIndex) || !MONTH_LABELS[monthIndex]) return '';
  return `${day.padStart(2, '0')}-${MONTH_LABELS[monthIndex]}-${year}`;
}

/** Read `DD-MMM-YYYY` (or an ISO date) back into an ISO date. */
export function parseIntake(value: string): string {
  const text = (value ?? '').trim();
  if (!text) return '';

  const match = /^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/.exec(text);
  if (match) {
    const [, day, label, year] = match;
    const index = MONTH_LABELS.findIndex((m) => m.toLowerCase() === label.toLowerCase());
    if (index === -1) return '';
    return `${year}-${String(index + 1).padStart(2, '0')}-${day.padStart(2, '0')}`;
  }

  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : '';
}

/** Proposed start date straight to the displayed intake, e.g. `01-Aug-2026`. */
export function deriveIntake(proposedStartDate: string): string {
  return formatIntake(deriveIntakeDate(proposedStartDate));
}

// ---------------------------------------------------------------------------
// Other generated values
// ---------------------------------------------------------------------------

/**
 * APPROVED (OD-08): course weeks are counted using inclusive dates, so both the
 * proposed start date and the proposed end date count as course days.
 */
export const WEEK_CALCULATION_METHOD: 'inclusive' | 'exclusive' = 'inclusive';

/**
 * SRS 6.3: the proposed college email is created from the Student ID and the
 * approved college domain. The value is generated but remains editable.
 */
export function deriveCollegeEmail(studentId: string, college: College | undefined): string {
  if (!studentId || !college) return '';
  return `${studentId.toLowerCase()}@${college.emailDomain}`;
}

/** SRS 6.3: State is generated from the selected campus. */
export function deriveState(campus: Campus | undefined): string {
  return campus?.state ?? '';
}

/**
 * APPROVED (OD-08): Actual Course Duration in whole weeks, counted inclusively:
 * (end date - start date + 1 day) / 7, rounded to whole weeks.
 * Returns 0 when either date is missing or the range is invalid.
 */
export function deriveActualCourseDuration(proposedStartDate: string, proposedEndDate: string): number {
  if (!proposedStartDate || !proposedEndDate) return 0;
  const days = daysBetween(proposedStartDate, proposedEndDate);
  if (days <= 0) return 0;
  const countedDays = WEEK_CALCULATION_METHOD === 'inclusive' ? days + 1 : days;
  return Math.round(countedDays / 7);
}

/**
 * CT means Credit Transfer (APPROVED, OD-08).
 *
 * CT Student is a flag only: Yes means the student has at least one approved
 * Credit Transfer. TDMS stores no transferred units, unit count or Credit
 * Transfer reference, and derives no duration reduction from it. Staff select
 * the approved Course Duration Option instead, and that field is always shown.
 */
export const CT_TERM = 'Credit Transfer';

/**
 * Chooses the approved duration option closest to the calculated duration.
 *
 * 62 weeks against options of 52 and 78 gives 52: |62-52| = 10 beats
 * |62-78| = 16. This does **not** change Actual Course Duration, which stays
 * 62 — the two are separate fields answering separate questions.
 *
 * **On an exact tie the shorter option wins** (approved 13 August 2026). 65
 * weeks sits midway between 52 and 78; without a stated rule the answer would
 * depend on the order the options happened to arrive in, which is not a
 * business rule at all.
 */
export function suggestCourseDurationOption(
  actualCourseDuration: number,
  durationOptions: number[],
): number | null {
  if (!actualCourseDuration || durationOptions.length === 0) return null;
  return durationOptions.reduce((closest, option) => {
    const distance = Math.abs(option - actualCourseDuration);
    const closestDistance = Math.abs(closest - actualCourseDuration);
    if (distance !== closestDistance) return distance < closestDistance ? option : closest;
    return option < closest ? option : closest;
  });
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(value: string): boolean {
  return EMAIL_PATTERN.test(value.trim());
}
