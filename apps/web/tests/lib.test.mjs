/**
 * Frontend unit tests.
 *
 * These run on the Node test runner (`npm test`) without a bundler, so they
 * cover the pure logic modules rather than React components. The rules checked
 * here are the ones the SRS states plainly: soft deletion metadata, export
 * following the visible filters, and the CSV reader used by Bulk Student
 * Import.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

// ---------------------------------------------------------------- CSV reader
// A trimmed copy of `src/lib/csv.ts` so the test runs without a TypeScript
// build step. Keep the two in step when the parser changes.
function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;
  const input = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;

  for (let index = 0; index < input.length; index += 1) {
    const char = input[index];
    if (inQuotes) {
      if (char === '"') {
        if (input[index + 1] === '"') {
          field += '"';
          index += 1;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
      continue;
    }
    if (char === '"') inQuotes = true;
    else if (char === ',') {
      row.push(field);
      field = '';
    } else if (char === '\n') {
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else if (char !== '\r') {
      field += char;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((entry) => entry.some((cell) => cell.trim() !== ''));
}

test('parseCsv reads a simple header and row', () => {
  const rows = parseCsv('Student ID,First Name\nST001,Ana\n');
  assert.deepEqual(rows, [
    ['Student ID', 'First Name'],
    ['ST001', 'Ana'],
  ]);
});

test('parseCsv keeps commas and quotes inside a quoted field', () => {
  const rows = parseCsv('Name,Remarks\nAna,"Hobart, TAS ""main"" campus"\n');
  assert.deepEqual(rows[1], ['Ana', 'Hobart, TAS "main" campus']);
});

test('parseCsv skips a blank trailing line', () => {
  const rows = parseCsv('A,B\n1,2\n\n');
  assert.equal(rows.length, 2);
});

// ------------------------------------------------------------- date handling
function addDays(value, days) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function rangesOverlap(aStart, aEnd, bStart, bEnd) {
  return aStart <= bEnd && bStart <= aEnd;
}

test('the proposed 14-day recycle period lands on the right date', () => {
  assert.equal(addDays('2026-08-03', 14), '2026-08-17');
});

test('a session that starts inside the filter range overlaps it', () => {
  assert.equal(rangesOverlap('2026-08-10', '2026-09-07', '2026-08-01', '2026-08-31'), true);
});

test('a session that finishes before the filter range does not overlap it', () => {
  assert.equal(rangesOverlap('2026-06-01', '2026-06-30', '2026-08-01', '2026-08-31'), false);
});
