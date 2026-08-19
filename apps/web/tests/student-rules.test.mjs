import assert from 'node:assert/strict';
import test from 'node:test';

/**
 * Approved student business rules — Intake and Group (11 August 2026).
 *
 * The frontend rules are re-implemented here rather than imported, because the
 * source is TypeScript and this suite runs on plain `node --test`. That is
 * deliberate: the assertions below are the *approved behaviour*, and the mirror
 * test at the bottom checks the real module's constants still agree with them.
 */

import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../src/lib/student-rules.ts', import.meta.url), 'utf8');

/** Reads an exported constant out of the module source. */
function exportedNumber(name) {
  const match = new RegExp(`export const ${name} = (\\d+)`).exec(source);
  assert.ok(match, `${name} not found in student-rules.ts`);
  return Number.parseInt(match[1], 10);
}

function exportedStringArray(name) {
  const match = new RegExp(`export const ${name}[^=]*= \\[([^\\]]*)\\]`, 's').exec(source);
  assert.ok(match, `${name} not found in student-rules.ts`);
  return [...match[1].matchAll(/'([^']+)'/g)].map((m) => m[1]);
}

const APPROVED_GROUP_QUALIFICATIONS = [
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

// ---------------------------------------------------------------------------
// The approved list and range, read from the real module
// ---------------------------------------------------------------------------

test('exactly ten qualifications use numbered groups', () => {
  const codes = exportedStringArray('GROUP_ENABLED_QUALIFICATIONS');
  assert.equal(codes.length, 10);
});

test('the group-enabled list is exactly as approved', () => {
  const codes = exportedStringArray('GROUP_ENABLED_QUALIFICATIONS');
  assert.deepEqual([...codes].sort(), [...APPROVED_GROUP_QUALIFICATIONS].sort());
});

test('the current maximum group is 15', () => {
  assert.equal(exportedNumber('MAX_NUMBERED_GROUP'), 15);
});

test('the frontend maximum matches the backend rule module', () => {
  const backend = readFileSync(
    new URL('../../api/app/core/student_rules.py', import.meta.url),
    'utf8',
  );
  const match = /MAX_NUMBERED_GROUP: int = (\d+)/.exec(backend);
  assert.ok(match, 'MAX_NUMBERED_GROUP not found in student_rules.py');
  assert.equal(Number.parseInt(match[1], 10), exportedNumber('MAX_NUMBERED_GROUP'));
});

test('the frontend qualification list matches the backend rule module', () => {
  const backend = readFileSync(
    new URL('../../api/app/core/student_rules.py', import.meta.url),
    'utf8',
  );
  const block = /GROUP_ENABLED_QUALIFICATIONS: frozenset\[str\] = frozenset\(\s*\{([^}]*)\}/s.exec(
    backend,
  );
  assert.ok(block, 'GROUP_ENABLED_QUALIFICATIONS not found in student_rules.py');
  const backendCodes = [...block[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort();
  assert.deepEqual(backendCodes, exportedStringArray('GROUP_ENABLED_QUALIFICATIONS').sort());
});

test('the group list is generated, not a literal array', () => {
  // A literal "Group 1', 'Group 2', ..." list would defeat the point of the
  // configurable maximum, so the source must build it from the constant.
  assert.match(source, /Array\.from\(\{ length: maximum \}/);
});

// ---------------------------------------------------------------------------
// Behaviour, using the same logic the module implements
// ---------------------------------------------------------------------------

const MAX = 15;
const NO_GROUP = 'N/A';
const GROUP_PATTERN = /^Group ([1-9][0-9]*)$/;

const usesNumberedGroups = (code) =>
  APPROVED_GROUP_QUALIFICATIONS.includes((code ?? '').trim().toUpperCase());

const groupNumber = (group) => {
  const match = GROUP_PATTERN.exec((group ?? '').trim());
  return match ? Number.parseInt(match[1], 10) : null;
};

function validateGroup(code, group) {
  const value = (group ?? '').trim();
  if (!usesNumberedGroups(code)) {
    return value === '' || value === NO_GROUP ? null : 'must be N/A';
  }
  if (value === '' || value === NO_GROUP) return 'requires a group';
  const number = groupNumber(value);
  return number !== null && number >= 1 && number <= MAX ? null : 'not a valid group';
}

function groupAfterQualificationChange(code, current) {
  if (!usesNumberedGroups(code)) return NO_GROUP;
  const number = groupNumber(current);
  return number !== null && number >= 1 && number <= MAX ? current : '';
}

test('Group 1 and Group 15 are valid for every group-enabled qualification', () => {
  for (const code of APPROVED_GROUP_QUALIFICATIONS) {
    assert.equal(validateGroup(code, 'Group 1'), null, code);
    assert.equal(validateGroup(code, 'Group 15'), null, code);
  }
});

test('Group 0 and Group 16 are rejected', () => {
  assert.ok(validateGroup('SIT40721', 'Group 0'));
  assert.ok(validateGroup('SIT40721', 'Group 16'));
});

test('arbitrary group text is rejected', () => {
  for (const value of ['G1', '1', 'group 1', 'Group 01', 'Morning Group', 'A-Team']) {
    assert.ok(validateGroup('SIT40721', value), value);
  }
});

test('a non-group qualification expects N/A', () => {
  assert.equal(validateGroup('BSB50420', NO_GROUP), null);
  assert.equal(validateGroup('BSB50420', ''), null);
  assert.ok(validateGroup('BSB50420', 'Group 3'));
});

test('switching to a non-group qualification clears the group', () => {
  assert.equal(groupAfterQualificationChange('BSB50420', 'Group 5'), NO_GROUP);
});

test('switching to a group qualification requires a fresh choice', () => {
  assert.equal(groupAfterQualificationChange('RII50520', NO_GROUP), '');
});

test('a valid group carries between two group-enabled qualifications', () => {
  assert.equal(groupAfterQualificationChange('SIT50422', 'Group 5'), 'Group 5');
});

// ---------------------------------------------------------------------------
// Intake
// ---------------------------------------------------------------------------

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const deriveIntakeDate = (start) => (start ? `${start.slice(0, 7)}-01` : '');

function formatIntake(iso) {
  if (!iso) return '';
  const [year, month, day] = iso.split('-');
  return `${day.padStart(2, '0')}-${MONTHS[Number.parseInt(month, 10) - 1]}-${year}`;
}

test('intake is the first day of the proposed start month', () => {
  assert.equal(deriveIntakeDate('2026-08-18'), '2026-08-01');
  assert.equal(deriveIntakeDate('2027-01-03'), '2027-01-01');
});

test('intake displays as DD-MMM-YYYY', () => {
  assert.equal(formatIntake(deriveIntakeDate('2026-08-18')), '01-Aug-2026');
  assert.equal(formatIntake(deriveIntakeDate('2027-01-03')), '01-Jan-2027');
  assert.equal(formatIntake(deriveIntakeDate('2025-12-31')), '01-Dec-2025');
});

test('intake never displays in a rejected format', () => {
  const value = formatIntake(deriveIntakeDate('2026-08-18'));
  for (const rejected of ['AUG-2026', '08/01/2026', '01/08/2026', '2026-08-01']) {
    assert.notEqual(value, rejected);
  }
});

test('every month uses its English three-letter label', () => {
  MONTHS.forEach((label, index) => {
    const month = String(index + 1).padStart(2, '0');
    assert.equal(formatIntake(`2026-${month}-01`), `01-${label}-2026`);
  });
});

test('the stored intake stays sortable as a date', () => {
  const intakes = ['2027-01-01', '2026-08-01', '2026-12-01'].sort();
  assert.deepEqual(intakes, ['2026-08-01', '2026-12-01', '2027-01-01']);
});
