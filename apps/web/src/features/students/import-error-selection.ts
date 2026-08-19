/**
 * Selection and filtering rules for the Errors identified section.
 *
 * Kept apart from the component so the behaviour that decides what a Delete
 * acts on is plain, testable logic rather than something only reachable through
 * a rendered checkbox.
 */

import type { StagedRowStatus, StagedStudentRow } from '@/types/import';

/**
 * The three statuses that stop a save.
 *
 * `Excluded by user` is a decision, not a problem, so it is never an error.
 * `Ready` is not one either — which is what makes deleting from this section
 * safe: a row a user has already corrected can no longer be caught by it.
 */
export const BLOCKING_STATUSES: readonly StagedRowStatus[] = [
  'Needs correction',
  'Duplicate',
  'Unmatched reference',
];

export function isBlockingStatus(status: StagedRowStatus): boolean {
  return BLOCKING_STATUSES.includes(status);
}

/** Everything a search covers, flattened once per row. */
export function searchableText(row: StagedStudentRow): string {
  return [
    row.sourceRowNumber,
    row.studentId,
    row.firstName,
    row.lastName,
    row.collegeValue,
    row.campusValue,
    row.qualificationValue,
    row.status,
    ...row.issues.map((issue) => `${issue.field} ${issue.message}`),
  ]
    .join(' ')
    .toLowerCase();
}

export function matchesQuery(row: StagedStudentRow, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return searchableText(row).includes(needle);
}

export type StatusFilter = 'all' | StagedRowStatus;

export function filterErrorRows(
  rows: StagedStudentRow[],
  statusFilter: StatusFilter,
  query: string,
): StagedStudentRow[] {
  return rows.filter(
    (row) => (statusFilter === 'all' || row.status === statusFilter) && matchesQuery(row, query),
  );
}

export type SelectionState = 'none' | 'some' | 'all';

/** Drives the header checkbox: `some` shows the indeterminate dash. */
export function selectionState(visibleIds: string[], selected: ReadonlySet<string>): SelectionState {
  if (visibleIds.length === 0) return 'none';
  const chosen = visibleIds.filter((id) => selected.has(id)).length;
  if (chosen === 0) return 'none';
  return chosen === visibleIds.length ? 'all' : 'some';
}

/**
 * Select all applies to what is shown, not to the whole error set.
 *
 * A row hidden by the current filter keeps whatever state it already had, so
 * narrowing the filter can never silently drop a row from a pending delete —
 * nor silently add one the user cannot see.
 */
export function toggleAllVisible(
  current: ReadonlySet<string>,
  visibleIds: string[],
): ReadonlySet<string> {
  const next = new Set(current);
  if (selectionState(visibleIds, current) === 'all') {
    visibleIds.forEach((id) => next.delete(id));
  } else {
    visibleIds.forEach((id) => next.add(id));
  }
  return next;
}

export function toggleOne(current: ReadonlySet<string>, id: string): ReadonlySet<string> {
  const next = new Set(current);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/**
 * Drops selected ids that no longer exist.
 *
 * A correction can move a row to Ready and out of this section while it is
 * ticked. Without this, that row stays in the selection and a later Delete
 * removes a row the user has just fixed. Returns the same set when nothing
 * changed, so React state is not replaced needlessly.
 */
export function pruneSelection(
  current: ReadonlySet<string>,
  aliveIds: string[],
): ReadonlySet<string> {
  if (current.size === 0) return current;
  const alive = new Set(aliveIds);
  const next = new Set<string>();
  current.forEach((id) => {
    if (alive.has(id)) next.add(id);
  });
  return next.size === current.size ? current : next;
}

/**
 * What Download and Delete act on: the ticked rows, or every row currently
 * shown when nothing is ticked. Never the rows a filter is hiding.
 */
export function targetedRows(
  visible: StagedStudentRow[],
  selected: StagedStudentRow[],
): StagedStudentRow[] {
  return selected.length > 0 ? selected : visible;
}
