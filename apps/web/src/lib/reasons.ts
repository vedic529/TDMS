import type { ReasonCode, ReasonOption } from '@/types/common';

/**
 * SRS 4.6 - Reason Selection.
 *
 * "The program does not guess a reason." The list below is the SRS *proposed*
 * list; OD-06 keeps the final list open, so the UI labels it as proposed and
 * does not add invented values.
 */
export const REASON_OPTIONS: ReasonOption[] = [
  {
    value: 'INCORRECT_OR_DUPLICATE_RECORD',
    label: 'Incorrect or duplicate record',
    appliesTo: ['student', 'timetable', 'trainer', 'course', 'qualificationUnit', 'restore'],
  },
  {
    value: 'STUDENT_WITHDRAWAL_CANCELLATION_OR_CORRECTION',
    label: 'Student withdrawal, cancellation or record correction',
    appliesTo: ['student', 'restore'],
  },
  {
    value: 'TIMETABLE_CORRECTION',
    label: 'Timetable correction',
    appliesTo: ['timetable', 'restore'],
  },
  {
    value: 'APPROVED_CLASH_OR_SCHEDULING_OVERRIDE',
    label: 'Approved clash or scheduling override',
    appliesTo: ['timetable', 'override'],
  },
  {
    value: 'DATA_IMPORTED_IN_ERROR',
    label: 'Data imported in error',
    appliesTo: ['student', 'timetable', 'trainer', 'course', 'qualificationUnit', 'restore'],
  },
  {
    value: 'OTHER',
    label: 'Other - written explanation required',
    appliesTo: ['student', 'timetable', 'trainer', 'course', 'qualificationUnit', 'restore', 'override'],
  },
];

export type ReasonContext = ReasonOption['appliesTo'][number];

export function reasonsFor(context: ReasonContext): ReasonOption[] {
  return REASON_OPTIONS.filter((option) => option.appliesTo.includes(context));
}

export function reasonLabel(code: ReasonCode | undefined): string {
  if (!code) return '';
  return REASON_OPTIONS.find((option) => option.value === code)?.label ?? code;
}

/** SRS 2.3: normal deletion keeps the record for 14 days unless a different period is approved. */
export const PROPOSED_RECYCLE_PERIOD_DAYS = 14;
