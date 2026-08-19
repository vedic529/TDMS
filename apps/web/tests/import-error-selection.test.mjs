/**
 * Errors identified — selection, filtering and what Delete acts on.
 *
 * These import `src/features/students/import-error-selection.ts` directly, so
 * they test the rules the screen actually runs. The rules matter more than they
 * look: they decide which staged rows a bulk Delete removes.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  BLOCKING_STATUSES,
  filterErrorRows,
  isBlockingStatus,
  matchesQuery,
  pruneSelection,
  selectionState,
  targetedRows,
  toggleAllVisible,
  toggleOne,
} from '../src/features/students/import-error-selection.ts';

function row(id, overrides = {}) {
  return {
    id,
    sourceRowNumber: Number(id.replace(/\D/g, '')) || 1,
    studentId: `00000${id.replace(/\D/g, '')}`,
    firstName: 'Nafiza',
    lastName: 'ALI',
    collegeValue: 'AIBT',
    campusValue: '132-146 Elizabeth Street, HOBART, Tasmania 7000',
    qualificationValue: 'CHC30125',
    ctStudent: 'No',
    group: '',
    coeStatus: 'CoE',
    proposedStartDate: '2026-03-09',
    proposedEndDate: '2027-03-07',
    personalEmail: '',
    primaryPhone: '',
    status: 'Needs correction',
    issues: [{ field: 'Campus', message: 'No campus matches this address.' }],
    corrected: false,
    ...overrides,
  };
}

const ids = (rows) => rows.map((entry) => entry.id);

// ------------------------------------------------------------ what is an error

test('only the three blocking statuses count as errors', () => {
  assert.deepEqual([...BLOCKING_STATUSES], ['Needs correction', 'Duplicate', 'Unmatched reference']);
  assert.equal(isBlockingStatus('Needs correction'), true);
  assert.equal(isBlockingStatus('Duplicate'), true);
  assert.equal(isBlockingStatus('Unmatched reference'), true);
});

test('a Ready row is never an error', () => {
  // This is what makes a bulk Delete safe: a corrected row leaves the section.
  assert.equal(isBlockingStatus('Ready'), false);
});

test('a row the user excluded is a decision, not an error', () => {
  assert.equal(isBlockingStatus('Excluded by user'), false);
});

// -------------------------------------------------------------------- filters

test('the status filter narrows to one kind of error', () => {
  const rows = [row('r1'), row('r2', { status: 'Duplicate' }), row('r3', { status: 'Duplicate' })];
  assert.deepEqual(ids(filterErrorRows(rows, 'all', '')), ['r1', 'r2', 'r3']);
  assert.deepEqual(ids(filterErrorRows(rows, 'Duplicate', '')), ['r2', 'r3']);
  assert.deepEqual(ids(filterErrorRows(rows, 'Unmatched reference', '')), []);
});

test('search covers the issue message, not only the student', () => {
  const target = row('r1', { issues: [{ field: 'Qualification', message: 'CHC52021 is superseded.' }] });
  assert.equal(matchesQuery(target, 'superseded'), true);
  assert.equal(matchesQuery(target, 'CHC52021'), true);
  assert.equal(matchesQuery(row('r2'), 'superseded'), false);
});

test('search ignores case and surrounding spaces', () => {
  assert.equal(matchesQuery(row('r1'), '  hobart '), true);
  assert.equal(matchesQuery(row('r1'), 'NAFIZA'), true);
});

test('an empty search matches everything', () => {
  const rows = [row('r1'), row('r2')];
  assert.deepEqual(ids(filterErrorRows(rows, 'all', '   ')), ['r1', 'r2']);
});

// ------------------------------------------------------------------ selection

test('the header checkbox reports none, some or all', () => {
  assert.equal(selectionState(['a', 'b'], new Set()), 'none');
  assert.equal(selectionState(['a', 'b'], new Set(['a'])), 'some');
  assert.equal(selectionState(['a', 'b'], new Set(['a', 'b'])), 'all');
});

test('with nothing shown the header checkbox is empty, not all', () => {
  // Every member of an empty list is selected, vacuously. Reporting "all" there
  // would offer a Delete with nothing to delete.
  assert.equal(selectionState([], new Set(['a'])), 'none');
});

test('select all takes every shown row', () => {
  const after = toggleAllVisible(new Set(), ['a', 'b', 'c']);
  assert.deepEqual([...after].sort(), ['a', 'b', 'c']);
});

test('select all again clears them', () => {
  const after = toggleAllVisible(new Set(['a', 'b']), ['a', 'b']);
  assert.equal(after.size, 0);
});

test('select all does not reach rows a filter is hiding', () => {
  // The user filtered to Duplicate and ticked the header. A row hidden behind
  // the filter must not join the selection — a later Delete would take it.
  const after = toggleAllVisible(new Set(), ['visible-1']);
  assert.equal(after.has('hidden-1'), false);
});

test('clearing the shown rows leaves a hidden selection alone', () => {
  const after = toggleAllVisible(new Set(['shown-1', 'hidden-1']), ['shown-1']);
  assert.deepEqual([...after], ['hidden-1']);
});

test('one row toggles on and off', () => {
  assert.deepEqual([...toggleOne(new Set(), 'a')], ['a']);
  assert.equal(toggleOne(new Set(['a']), 'a').size, 0);
});

// --------------------------------------------------------------------- safety

test('a row corrected while ticked drops out of the selection', () => {
  // The decisive one. The user ticks row r2, corrects it in the staging table,
  // it turns Ready and leaves this section. Without pruning it stays selected
  // and the next Delete removes a row that was just fixed.
  const stillErrors = ['r1', 'r3'];
  const after = pruneSelection(new Set(['r1', 'r2']), stillErrors);
  assert.deepEqual([...after], ['r1']);
});

test('pruning returns the same set when nothing changed', () => {
  // Identity is compared by React state, so a new set every render would loop.
  const current = new Set(['r1']);
  assert.equal(pruneSelection(current, ['r1', 'r2']), current);
});

test('pruning an empty selection does nothing', () => {
  const current = new Set();
  assert.equal(pruneSelection(current, ['r1']), current);
});

test('with nothing ticked the actions apply to every shown row', () => {
  const visible = [row('r1'), row('r2')];
  assert.deepEqual(ids(targetedRows(visible, [])), ['r1', 'r2']);
});

test('with rows ticked the actions apply to those only', () => {
  const visible = [row('r1'), row('r2')];
  assert.deepEqual(ids(targetedRows(visible, [visible[1]])), ['r2']);
});

test('a filter that shows nothing leaves nothing to act on', () => {
  // Guards the fallback: "no selection" must not silently mean "all errors"
  // when the filter has hidden them all.
  assert.deepEqual(targetedRows([], []), []);
});
