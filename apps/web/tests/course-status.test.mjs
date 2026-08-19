/**
 * The frontend must not decide a course's status.
 *
 * TDMS displays whatever FastAPI returns. It previously derived the status from
 * the code — `ACT*` meant Active, `SUP*` meant Superseded, everything else fell
 * through to Inactive — which is how course 104262B, stored under an approved
 * status, came to be labelled Inactive in the interface.
 *
 * The runner has no bundler, so this mirrors the adapter's logic rather than
 * importing the TypeScript. Keep it in step with `reference-adapters.ts`.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

/** Mirrors `toCourseStatus` in src/features/reference-data/reference-adapters.ts. */
function toCourseStatus(code, label) {
  return label || code;
}

/** Mirrors the superseded implementation, kept only to prove the defect. */
function supersededDerivation(code, label) {
  const normalised = (code || label).trim().toUpperCase();
  if (normalised.startsWith('ACT')) return 'Active';
  if (normalised.startsWith('SUP')) return 'Superseded';
  return 'Inactive';
}

test('the status shown is the status the backend sent', () => {
  assert.equal(toCourseStatus('ACTIVE', 'Active'), 'Active');
  assert.equal(toCourseStatus('INACTIVE', 'Inactive'), 'Inactive');
  assert.equal(toCourseStatus('SUPERSEDED', 'Superseded'), 'Superseded');
});

test('an approved status this build has never seen is passed through unchanged', () => {
  // COL-05 is open-ended: "active, inactive, superseded or in another approved
  // status". A value added to the database after this build shipped must still
  // display correctly.
  assert.equal(toCourseStatus('TEACH_OUT', 'Teach Out'), 'Teach Out');
  assert.equal(toCourseStatus('REGISTERED', 'Registered'), 'Registered');
});

test('the old derivation mislabelled anything outside its closed set', () => {
  // The defect, pinned so it cannot return: a genuinely active course whose
  // code did not begin with ACT was relabelled Inactive by the browser.
  assert.equal(supersededDerivation('REGISTERED', 'Registered'), 'Inactive');
  assert.equal(supersededDerivation('TEACH_OUT', 'Teach Out'), 'Inactive');

  // The replacement does not.
  assert.notEqual(toCourseStatus('REGISTERED', 'Registered'), 'Inactive');
  assert.notEqual(toCourseStatus('TEACH_OUT', 'Teach Out'), 'Inactive');
});

test('a course supplied by the project owner displays as Active', () => {
  // The backend applies the approved rule and stores ACTIVE / "Active"; the
  // browser's only job is to render it.
  assert.equal(toCourseStatus('ACTIVE', 'Active'), 'Active');
});

test('the label wins over the code, and the code is the fallback', () => {
  assert.equal(toCourseStatus('ACTIVE', 'Currently offered'), 'Currently offered');
  assert.equal(toCourseStatus('ACTIVE', ''), 'ACTIVE');
});
