/**
 * XLSX workbook writer.
 *
 * These import `src/lib/xlsx.ts` directly — Node strips the types — so they
 * exercise the shipped code rather than a copy of it. The archive is read back
 * with a ZIP reader written here on purpose: checking the bytes with the same
 * code that produced them would prove nothing.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import { buildXlsx, columnName, crc32, escapeXml, safeSheetName } from '../src/lib/xlsx.ts';

const LOCAL_HEADER = 0x04034b50;
const CENTRAL_HEADER = 0x02014b50;
const END_OF_CENTRAL_DIRECTORY = 0x06054b50;

/** Reads a stored-method ZIP via its central directory, verifying every CRC. */
function readZip(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const decoder = new TextDecoder();

  let eocd = -1;
  for (let index = bytes.length - 22; index >= 0; index -= 1) {
    if (view.getUint32(index, true) === END_OF_CENTRAL_DIRECTORY) {
      eocd = index;
      break;
    }
  }
  assert.notEqual(eocd, -1, 'no end-of-central-directory record');

  const count = view.getUint16(eocd + 10, true);
  let at = view.getUint32(eocd + 16, true);
  const entries = new Map();

  for (let n = 0; n < count; n += 1) {
    assert.equal(view.getUint32(at, true), CENTRAL_HEADER, 'central directory header');
    const declaredCrc = view.getUint32(at + 16, true);
    const size = view.getUint32(at + 24, true);
    const nameLength = view.getUint16(at + 28, true);
    const extraLength = view.getUint16(at + 30, true);
    const commentLength = view.getUint16(at + 32, true);
    const offset = view.getUint32(at + 42, true);
    const name = decoder.decode(bytes.subarray(at + 46, at + 46 + nameLength));

    assert.equal(view.getUint32(offset, true), LOCAL_HEADER, `local header for ${name}`);
    const localNameLength = view.getUint16(offset + 26, true);
    const localExtraLength = view.getUint16(offset + 28, true);
    const start = offset + 30 + localNameLength + localExtraLength;
    const data = bytes.subarray(start, start + size);

    assert.equal(crc32(data), declaredCrc, `CRC for ${name}`);
    entries.set(name, decoder.decode(data));
    at += 46 + nameLength + extraLength + commentLength;
  }
  return entries;
}

const sheetOf = (workbook) => readZip(workbook).get('xl/worksheets/sheet1.xml');

// ------------------------------------------------------------------- checksum

test('crc32 matches the published check value', () => {
  // The IEEE 802.3 check value for "123456789". A wrong CRC makes Excel report
  // the workbook as corrupt, so this is worth pinning exactly.
  assert.equal(crc32(new TextEncoder().encode('123456789')), 0xcbf43926);
});

test('crc32 of nothing is zero', () => {
  assert.equal(crc32(new Uint8Array(0)), 0);
});

// ------------------------------------------------------------ archive shape

test('the workbook contains every part Excel requires', () => {
  const entries = readZip(buildXlsx({ name: 'Sheet', header: ['A'], rows: [['1']] }));
  assert.deepEqual(
    [...entries.keys()].sort(),
    [
      '[Content_Types].xml',
      '_rels/.rels',
      'xl/_rels/workbook.xml.rels',
      'xl/styles.xml',
      'xl/workbook.xml',
      'xl/worksheets/sheet1.xml',
    ],
  );
});

test('every relationship target exists in the archive', () => {
  const entries = readZip(buildXlsx({ name: 'Sheet', header: ['A'], rows: [] }));
  assert.match(entries.get('_rels/.rels'), /Target="xl\/workbook\.xml"/);
  assert.match(entries.get('xl/_rels/workbook.xml.rels'), /Target="worksheets\/sheet1\.xml"/);
  assert.match(entries.get('xl/_rels/workbook.xml.rels'), /Target="styles\.xml"/);
});

test('the same rows always produce the same bytes', () => {
  // No timestamp leaks into the archive, so two exports can be compared.
  const sheet = { name: 'Errors identified', header: ['Student ID'], rows: [['000025']] };
  assert.deepEqual(buildXlsx(sheet), buildXlsx(sheet));
});

// ------------------------------------------------------------------ cells

test('a Student ID keeps its leading zeros', () => {
  // The whole reason this writer exists: as CSV text, Excel reads 000025 as the
  // number 25. As an inline string it survives intact.
  const xml = sheetOf(buildXlsx({ name: 'S', header: ['Student ID'], rows: [['000025']] }));
  assert.match(xml, /<c r="A2" t="inlineStr"><is><t>000025<\/t><\/is><\/c>/);
  assert.doesNotMatch(xml, /<v>000025<\/v>/);
});

test('a real number is written as a number', () => {
  const xml = sheetOf(buildXlsx({ name: 'S', header: ['Row'], rows: [[42]] }));
  assert.match(xml, /<c r="A2"><v>42<\/v><\/c>/);
});

test('an empty, null or undefined value writes an empty cell', () => {
  const xml = sheetOf(buildXlsx({ name: 'S', header: ['A', 'B', 'C'], rows: [['', null, undefined]] }));
  assert.match(xml, /<c r="A2"\/><c r="B2"\/><c r="C2"\/>/);
});

test('XML markup in a value is escaped, not injected', () => {
  const xml = sheetOf(buildXlsx({ name: 'S', header: ['Name'], rows: [['Smith & Sons <test>']] }));
  assert.match(xml, /<t>Smith &amp; Sons &lt;test&gt;<\/t>/);
});

test('characters XML cannot represent are dropped', () => {
  // A control byte from a legacy system cannot be escaped; left in, the
  // workbook will not open at all.
  assert.equal(escapeXml('AI' + String.fromCharCode(0) + 'BT' + String.fromCharCode(31)), 'AIBT');
  assert.equal(escapeXml('form' + String.fromCharCode(12) + 'feed'), 'formfeed');
  assert.equal(escapeXml('keeps\ttabs\nand newlines'), 'keeps\ttabs\nand newlines');
});

test('surrounding spaces are preserved rather than trimmed by Excel', () => {
  const xml = sheetOf(buildXlsx({ name: 'S', header: ['A'], rows: [[' padded ']] }));
  assert.match(xml, /<t xml:space="preserve"> padded <\/t>/);
});

test('the header row is bold and the data rows are not', () => {
  const xml = sheetOf(buildXlsx({ name: 'S', header: ['Student ID'], rows: [['x']] }));
  assert.match(xml, /<c r="A1" s="1" t="inlineStr">/);
  assert.match(xml, /<c r="A2" t="inlineStr">/);
});

test('the sheet declares the range it actually covers', () => {
  const xml = sheetOf(
    buildXlsx({ name: 'S', header: ['A', 'B', 'C'], rows: [['1', '2', '3'], ['4', '5', '6']] }),
  );
  assert.match(xml, /<dimension ref="A1:C3"\/>/);
  assert.match(xml, /<autoFilter ref="A1:C3"\/>/);
});

// ------------------------------------------------------------ naming rules

test('column references continue past Z', () => {
  assert.equal(columnName(0), 'A');
  assert.equal(columnName(25), 'Z');
  assert.equal(columnName(26), 'AA');
  assert.equal(columnName(51), 'AZ');
  assert.equal(columnName(701), 'ZZ');
  assert.equal(columnName(702), 'AAA');
});

test('a sheet name is made legal for Excel', () => {
  assert.equal(safeSheetName('Errors identified'), 'Errors identified');
  assert.equal(safeSheetName('Errors / issues [2026]'), 'Errors issues 2026');
  assert.equal(safeSheetName(''), 'Sheet1');
  assert.equal(safeSheetName('x'.repeat(40)).length, 31);
});

test('a sheet name is escaped inside the workbook part', () => {
  const entries = readZip(buildXlsx({ name: 'R&D', header: ['A'], rows: [] }));
  assert.match(entries.get('xl/workbook.xml'), /name="R&amp;D"/);
});
