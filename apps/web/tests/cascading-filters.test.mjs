/**
 * Cascading filter state: College -> Campus -> Qualification.
 *
 * The runner has no bundler, so this mirrors the pure state rules from
 * `use-cascading-filters.ts` and `multi-select-filter.tsx` rather than mounting
 * React. Keep the three functions below in step with those files.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

const EMPTY = { collegeIds: [], campusIds: [], qualificationIds: [] };

/** Mirrors setColleges / setCampuses / setQualifications. */
function setColleges(state, collegeIds) {
  return { collegeIds, campusIds: [], qualificationIds: [] };
}
function setCampuses(state, campusIds) {
  return { ...state, campusIds, qualificationIds: [] };
}
function setQualifications(state, qualificationIds) {
  return { ...state, qualificationIds };
}

/** Mirrors the pruning the option effects perform when a scope narrows. */
function prune(state, allowedCampusIds, allowedQualificationIds) {
  return {
    collegeIds: state.collegeIds,
    campusIds: state.campusIds.filter((id) => allowedCampusIds.includes(id)),
    qualificationIds: state.qualificationIds.filter((id) =>
      allowedQualificationIds.includes(id),
    ),
  };
}

/** Mirrors MultiSelectFilter.toggle. */
function toggle(selected, value, optionCount) {
  const next = new Set(selected);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next.size === optionCount ? [] : Array.from(next);
}

test('empty means All, not "match nothing"', () => {
  assert.deepEqual(EMPTY.collegeIds, []);
  // A request built from an empty scope omits the parameter entirely.
  const params = new URLSearchParams();
  for (const id of EMPTY.collegeIds) params.append('college_ids', id);
  assert.equal(params.toString(), '');
});

test('choosing an item while All is active leaves All', () => {
  assert.deepEqual(toggle([], 'c1', 3), ['c1']);
});

test('clearing the last item returns to All', () => {
  assert.deepEqual(toggle(['c1'], 'c1', 3), []);
});

test('selecting every option collapses back to All', () => {
  // Sending every id is the same filter as no restriction, and goes stale the
  // moment the upstream scope changes.
  assert.deepEqual(toggle(['c1', 'c2'], 'c3', 3), []);
});

test('multiple values are kept', () => {
  assert.deepEqual(toggle(['c1'], 'c2', 4).sort(), ['c1', 'c2']);
});

test('changing College prunes Campus and Qualification', () => {
  let state = { collegeIds: ['avta'], campusIds: ['bundaberg'], qualificationIds: ['ahc40422'] };
  state = setColleges(state, ['hj']);
  assert.deepEqual(state.campusIds, []);
  assert.deepEqual(state.qualificationIds, []);
  assert.deepEqual(state.collegeIds, ['hj']);
});

test('changing Campus prunes Qualification but keeps College', () => {
  let state = { collegeIds: ['avta'], campusIds: ['bundaberg'], qualificationIds: ['ahc40422'] };
  state = setCampuses(state, ['melbourne']);
  assert.deepEqual(state.collegeIds, ['avta']);
  assert.deepEqual(state.campusIds, ['melbourne']);
  assert.deepEqual(state.qualificationIds, []);
});

test('a selection no longer offered is pruned, valid ones survive', () => {
  const state = {
    collegeIds: ['avta'],
    campusIds: ['bundaberg', 'melbourne'],
    qualificationIds: ['ahc40422', 'cpc30220'],
  };
  const pruned = prune(state, ['melbourne'], ['cpc30220']);
  assert.deepEqual(pruned.campusIds, ['melbourne']);
  assert.deepEqual(pruned.qualificationIds, ['cpc30220']);
});

test('stale ids never survive a college change', () => {
  // The specific bug: switching AVTA -> HJ left Bundaberg and AHC40422 in state,
  // so the next request asked for a combination that does not exist.
  const state = { collegeIds: ['avta'], campusIds: ['bundaberg'], qualificationIds: ['ahc40422'] };
  const next = setColleges(state, ['hj']);
  assert.equal(next.campusIds.includes('bundaberg'), false);
  assert.equal(next.qualificationIds.includes('ahc40422'), false);
});

test('Clear filters restores All at every level', () => {
  let state = { collegeIds: ['hj'], campusIds: ['hobart'], qualificationIds: ['bsb50120'] };
  state = EMPTY;
  assert.deepEqual(state, { collegeIds: [], campusIds: [], qualificationIds: [] });
});

test('setting Qualification does not disturb College or Campus', () => {
  const state = { collegeIds: ['hj'], campusIds: ['hobart'], qualificationIds: [] };
  const next = setQualifications(state, ['bsb50120']);
  assert.deepEqual(next.collegeIds, ['hj']);
  assert.deepEqual(next.campusIds, ['hobart']);
  assert.deepEqual(next.qualificationIds, ['bsb50120']);
});

// --------------------------------------------------------- render stability
//
// The `scope` object handed to consumers goes into the dependency array of the
// callback that fetches rows. If its arrays are rebuilt on every render, that
// callback is new on every render, the fetching effect re-runs, it sets state,
// and React aborts with "Maximum update depth exceeded". The hook memoises
// `scope` on the *contents* of the selection; these tests pin why that is
// needed and that the key is a sound stand-in for the arrays.

/** Mirrors `numbers()` in the hook — new array every call, by construction. */
const numbers = (ids) => ids.map(Number).filter(Number.isFinite);

/** Mirrors the memo key. */
const key = (ids) => ids.join(',');

test('deriving ids returns a new array every call', () => {
  const selection = ['1', '2'];
  const first = numbers(selection);
  const second = numbers(selection);

  assert.deepEqual(first, second);
  // Equal contents, different identity — this is the render loop's cause.
  assert.notEqual(first, second);
});

test('the memo key is stable while the selection is unchanged', () => {
  const selection = ['1', '2'];
  assert.equal(key(selection), key([...selection]));
  assert.equal(key([]), key([]));
});

test('the memo key changes when the selection genuinely changes', () => {
  assert.notEqual(key(['1']), key(['1', '2']));
  assert.notEqual(key(['1', '2']), key(['2', '1']));
  assert.notEqual(key([]), key(['1']));
});

test('a memo keyed on contents keeps one identity across renders', () => {
  // Stand-in for React.useMemo: recompute only when the key changes.
  let cachedKey;
  let cached;
  const scopeFor = (ids) => {
    const next = key(ids);
    if (next !== cachedKey) {
      cachedKey = next;
      cached = numbers(ids);
    }
    return cached;
  };

  const selection = ['1', '2'];
  const a = scopeFor(selection);
  const b = scopeFor([...selection]); // a re-render, same selection
  assert.equal(a, b, 'unchanged selection must keep the same array identity');

  const c = scopeFor(['1']);
  assert.notEqual(b, c, 'a real change must produce a new array');
});

test('a repeated query parameter is built per value', () => {
  const params = new URLSearchParams();
  for (const id of ['1', '2', '3']) params.append('college_ids', id);
  assert.equal(params.toString(), 'college_ids=1&college_ids=2&college_ids=3');
});
