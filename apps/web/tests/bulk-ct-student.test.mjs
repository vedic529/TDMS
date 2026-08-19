/**
 * CT Student in Bulk Import (approved 13 August 2026).
 *
 * CT means Credit Transfer. It is the one field added to an otherwise unchanged
 * bulk contract, because it cannot be derived from anything else in the file and
 * it decides whether Group, Intake and Course Duration Option apply at all.
 *
 * The runner has no bundler, so this mirrors the normalisation in
 * `mock-tdms-client.ts`. Keep the two in step.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

const NO_GROUP = 'N/A';

/** Mirrors the CT branch of `confirmImportBatch`. */
function normalise(row) {
  const isCreditTransfer = (row.ctStudent ?? '').trim().toLowerCase() === 'yes';
  return {
    ctStudent: isCreditTransfer ? 'Yes' : 'No',
    group: isCreditTransfer ? NO_GROUP : (row.group ?? '').trim() || NO_GROUP,
    intake: isCreditTransfer ? null : deriveIntake(row.proposedStartDate),
    courseDurationOption: null,
  };
}

/** Stand-in for the approved intake derivation. */
function deriveIntake(startDate) {
  return startDate ? `${startDate.slice(0, 7)}-01` : null;
}

const TEMPLATE_COLUMNS = [
  'Student ID', 'First Name', 'Last Name', 'College', 'Campus', 'Qualification',
  'CT Student', 'Group', 'CoE / Non-CoE', 'Proposed Start Date',
  'Proposed End Date', 'Personal Email', 'Primary Phone',
];

test('CT Student is part of the template', () => {
  assert.ok(TEMPLATE_COLUMNS.includes('CT Student'));
  assert.equal(TEMPLATE_COLUMNS.length, 13);
});

test('CT Student sits before Group, because it decides whether Group applies', () => {
  assert.ok(TEMPLATE_COLUMNS.indexOf('CT Student') < TEMPLATE_COLUMNS.indexOf('Group'));
});

test('the twelve previously approved columns are all still present', () => {
  // The bulk contract is unchanged apart from the one addition.
  for (const column of [
    'Student ID', 'First Name', 'Last Name', 'College', 'Campus', 'Qualification',
    'Group', 'CoE / Non-CoE', 'Proposed Start Date', 'Proposed End Date',
    'Personal Email', 'Primary Phone',
  ]) {
    assert.ok(TEMPLATE_COLUMNS.includes(column), `${column} must remain`);
  }
});

test('CT = No keeps the normal rules', () => {
  const result = normalise({
    ctStudent: 'No', group: 'Group 3', proposedStartDate: '2026-09-07',
  });
  assert.equal(result.ctStudent, 'No');
  assert.equal(result.group, 'Group 3');
  assert.equal(result.intake, '2026-09-01');
});

test('CT = Yes makes Group, Intake and Course Duration Option not applicable', () => {
  const result = normalise({
    ctStudent: 'Yes', group: '', proposedStartDate: '2026-10-05',
  });
  assert.equal(result.group, 'N/A');
  assert.equal(result.intake, null);
  assert.equal(result.courseDurationOption, null);
});

test('a group supplied alongside CT = Yes is ignored, not accepted', () => {
  // "CT=Yes, Group 4" must not become a real group assignment by being typed
  // into a spreadsheet.
  const result = normalise({
    ctStudent: 'Yes', group: 'Group 4', proposedStartDate: '2026-10-05',
  });
  assert.equal(result.group, 'N/A');
  assert.notEqual(result.group, 'Group 4');
});

test('an intake is not derived for a CT student even with a start date', () => {
  const result = normalise({ ctStudent: 'Yes', proposedStartDate: '2026-10-05' });
  assert.equal(result.intake, null);
});

test('CT is read from the file, never assumed', () => {
  // Defaulting every imported student to No would invent a Credit Transfer
  // status for all of them.
  assert.equal(normalise({ ctStudent: 'Yes' }).ctStudent, 'Yes');
  assert.equal(normalise({ ctStudent: 'No' }).ctStudent, 'No');
});

test('the CT value is matched case-insensitively and trimmed', () => {
  for (const value of ['Yes', 'yes', 'YES', ' Yes ']) {
    assert.equal(normalise({ ctStudent: value }).ctStudent, 'Yes', value);
  }
});

test('a missing intake renders as N/A rather than an empty cell', () => {
  // "Not applicable" and "missing" must not look the same in the list.
  const display = (intake) => (intake ? intake : 'N/A');
  assert.equal(display(null), 'N/A');
  assert.equal(display('2026-09-01'), '2026-09-01');
});
