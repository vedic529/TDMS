/**
 * XLSX workbook writer.
 *
 * An `.xlsx` file is a ZIP archive of XML parts, so it can be produced in the
 * browser without a library. This module writes the five parts Excel needs and
 * packs them with the ZIP *stored* method — no compression, so no deflate
 * implementation is required and the output is byte-for-byte reproducible.
 *
 * Why this exists rather than a CSV renamed `.xlsx`: a spreadsheet cell has a
 * type, and a CSV cell does not. Excel reads the CSV text `000025` as the number
 * 25 and silently drops the leading zeros — which is exactly what a TDMS Student
 * ID looks like. Written as an inline string here, it survives.
 *
 * Values are written as text unless the caller passes a real JavaScript number.
 * Numeric-looking *strings* are never converted, for the reason above.
 */

/** Cell value as supplied by a caller. `null`/`undefined`/`''` write an empty cell. */
export type XlsxValue = string | number | null | undefined;

export interface XlsxSheet {
  /** Worksheet tab name. Sanitised against Excel's naming rules. */
  name: string;
  header: string[];
  rows: XlsxValue[][];
}

// --------------------------------------------------------------------- CRC-32

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) {
      c = (c & 1) === 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  return table;
})();

/** ZIP entry checksum. An archive with a wrong CRC opens as "corrupt". */
export function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (let index = 0; index < bytes.length; index += 1) {
    crc = CRC_TABLE[(crc ^ bytes[index]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

// ------------------------------------------------------------------ ZIP writer

interface ZipEntry {
  name: string;
  data: Uint8Array;
}

/**
 * 1 January 1980 in MS-DOS format — the earliest a ZIP can express.
 *
 * A fixed timestamp is deliberate: the same rows must always produce the same
 * bytes, so an export can be compared or checksummed. The file's real date is
 * the one the operating system records when it is saved.
 */
const DOS_DATE = (1 << 5) | 1;
const DOS_TIME = 0;

const LOCAL_HEADER = 0x04034b50;
const CENTRAL_HEADER = 0x02014b50;
const END_OF_CENTRAL_DIRECTORY = 0x06054b50;
/** Bit 11: file names are UTF-8. */
const UTF8_NAMES = 0x0800;
/** Stored, i.e. not compressed. */
const METHOD_STORED = 0;

function concat(parts: Uint8Array[]): Uint8Array<ArrayBuffer> {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const output = new Uint8Array(total);
  let at = 0;
  for (const part of parts) {
    output.set(part, at);
    at += part.length;
  }
  return output;
}

function zip(entries: ZipEntry[]): Uint8Array<ArrayBuffer> {
  const encoder = new TextEncoder();
  const locals: Uint8Array[] = [];
  const centrals: Uint8Array[] = [];
  let offset = 0;

  for (const entry of entries) {
    const name = encoder.encode(entry.name);
    const checksum = crc32(entry.data);
    const size = entry.data.length;

    const local = new Uint8Array(30 + name.length + size);
    const localView = new DataView(local.buffer);
    localView.setUint32(0, LOCAL_HEADER, true);
    localView.setUint16(4, 20, true); // version needed to extract
    localView.setUint16(6, UTF8_NAMES, true);
    localView.setUint16(8, METHOD_STORED, true);
    localView.setUint16(10, DOS_TIME, true);
    localView.setUint16(12, DOS_DATE, true);
    localView.setUint32(14, checksum, true);
    localView.setUint32(18, size, true); // compressed size == uncompressed
    localView.setUint32(22, size, true);
    localView.setUint16(26, name.length, true);
    localView.setUint16(28, 0, true); // extra field length
    local.set(name, 30);
    local.set(entry.data, 30 + name.length);
    locals.push(local);

    const central = new Uint8Array(46 + name.length);
    const centralView = new DataView(central.buffer);
    centralView.setUint32(0, CENTRAL_HEADER, true);
    centralView.setUint16(4, 20, true); // version made by
    centralView.setUint16(6, 20, true); // version needed
    centralView.setUint16(8, UTF8_NAMES, true);
    centralView.setUint16(10, METHOD_STORED, true);
    centralView.setUint16(12, DOS_TIME, true);
    centralView.setUint16(14, DOS_DATE, true);
    centralView.setUint32(16, checksum, true);
    centralView.setUint32(20, size, true);
    centralView.setUint32(24, size, true);
    centralView.setUint16(28, name.length, true);
    // Extra, comment, disk number, and both attribute fields stay zero.
    centralView.setUint32(42, offset, true); // offset of the local header
    central.set(name, 46);
    centrals.push(central);

    offset += local.length;
  }

  const centralSize = centrals.reduce((sum, part) => sum + part.length, 0);
  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  endView.setUint32(0, END_OF_CENTRAL_DIRECTORY, true);
  endView.setUint16(8, entries.length, true);
  endView.setUint16(10, entries.length, true);
  endView.setUint32(12, centralSize, true);
  endView.setUint32(16, offset, true);

  return concat([...locals, ...centrals, end]);
}

// ------------------------------------------------------------- SpreadsheetML

/**
 * Characters XML 1.0 cannot represent at all, not even escaped.
 *
 * Imported student files do carry them — a stray form feed or a control byte
 * from a legacy system. Escaping is not an option, so they are dropped; leaving
 * one in produces a workbook Excel refuses to open.
 */
 
const UNREPRESENTABLE = /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g;

export function escapeXml(value: string): string {
  return value
    .replace(UNREPRESENTABLE, '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/** 0 -> `A`, 25 -> `Z`, 26 -> `AA`. */
export function columnName(index: number): string {
  let name = '';
  let remaining = index;
  while (remaining >= 0) {
    name = String.fromCharCode(65 + (remaining % 26)) + name;
    remaining = Math.floor(remaining / 26) - 1;
  }
  return name;
}

/** Excel rejects `: \ / ? * [ ]`, an empty name, and anything over 31 characters. */
export function safeSheetName(name: string): string {
  const cleaned = name.replace(/[:\\/?*[\]]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 31);
  return cleaned || 'Sheet1';
}

/** Style 1 in the stylesheet below: bold, used for the header row. */
const HEADER_STYLE = 1;

function cell(reference: string, value: XlsxValue, style: number): string {
  const styleAttribute = style > 0 ? ` s="${style}"` : '';
  if (value === null || value === undefined || value === '') {
    return `<c r="${reference}"${styleAttribute}/>`;
  }
  if (typeof value === 'number') {
    // A non-finite number has no cell representation; write it as its text.
    if (Number.isFinite(value)) return `<c r="${reference}"${styleAttribute}><v>${value}</v></c>`;
  }
  const text = String(value);
  // Without this, Excel trims leading and trailing spaces out of the value.
  const preserve = /^\s|\s$/.test(text) ? ' xml:space="preserve"' : '';
  return `<c r="${reference}"${styleAttribute} t="inlineStr"><is><t${preserve}>${escapeXml(text)}</t></is></c>`;
}

const DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
const MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
const RELS_NS = 'http://schemas.openxmlformats.org/package/2006/relationships';
const DOC_RELS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';

function worksheetXml({ header, rows }: XlsxSheet): string {
  const width = Math.max(header.length, ...rows.map((row) => row.length), 1);
  const lastColumn = columnName(width - 1);
  const lastRow = rows.length + 1;

  const body: string[] = [
    `<row r="1">${header.map((value, index) => cell(`${columnName(index)}1`, value, HEADER_STYLE)).join('')}</row>`,
  ];
  rows.forEach((row, index) => {
    const number = index + 2;
    body.push(
      `<row r="${number}">${row
        .map((value, column) => cell(`${columnName(column)}${number}`, value, 0))
        .join('')}</row>`,
    );
  });

  // Element order follows the schema sequence: dimension, sheetViews, cols,
  // sheetData, autoFilter. Excel rejects the file if they are out of order.
  return (
    `${DECLARATION}<worksheet xmlns="${MAIN_NS}">` +
    `<dimension ref="A1:${lastColumn}${lastRow}"/>` +
    // The header stays visible while scrolling a long issue report.
    '<sheetViews><sheetView workbookViewId="0">' +
    '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>' +
    '</sheetView></sheetViews>' +
    '<sheetFormatPr defaultRowHeight="15"/>' +
    `<cols><col min="1" max="${width}" width="22" customWidth="1"/></cols>` +
    `<sheetData>${body.join('')}</sheetData>` +
    `<autoFilter ref="A1:${lastColumn}${lastRow}"/>` +
    '</worksheet>'
  );
}

/**
 * The smallest stylesheet Excel accepts.
 *
 * Both fills are required and must be in this order — Excel assumes index 0 is
 * `none` and index 1 is `gray125`, and reports the workbook as damaged without
 * them, even though neither is used here.
 */
const STYLES_XML =
  `${DECLARATION}<styleSheet xmlns="${MAIN_NS}">` +
  '<fonts count="2">' +
  '<font><sz val="11"/><name val="Calibri"/></font>' +
  '<font><b/><sz val="11"/><name val="Calibri"/></font>' +
  '</fonts>' +
  '<fills count="2">' +
  '<fill><patternFill patternType="none"/></fill>' +
  '<fill><patternFill patternType="gray125"/></fill>' +
  '</fills>' +
  '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>' +
  '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
  '<cellXfs count="2">' +
  '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
  '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>' +
  '</cellXfs>' +
  '</styleSheet>';

/** Builds a single-worksheet `.xlsx` file. */
export function buildXlsx(sheet: XlsxSheet): Uint8Array<ArrayBuffer> {
  const encoder = new TextEncoder();
  const tab = escapeXml(safeSheetName(sheet.name));

  const parts: ZipEntry[] = [
    {
      name: '[Content_Types].xml',
      data: encoder.encode(
        `${DECLARATION}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
          '<Default Extension="xml" ContentType="application/xml"/>' +
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
          '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
          '</Types>',
      ),
    },
    {
      name: '_rels/.rels',
      data: encoder.encode(
        `${DECLARATION}<Relationships xmlns="${RELS_NS}">` +
          `<Relationship Id="rId1" Type="${DOC_RELS}/officeDocument" Target="xl/workbook.xml"/>` +
          '</Relationships>',
      ),
    },
    {
      name: 'xl/workbook.xml',
      data: encoder.encode(
        `${DECLARATION}<workbook xmlns="${MAIN_NS}" xmlns:r="${DOC_RELS}">` +
          `<sheets><sheet name="${tab}" sheetId="1" r:id="rId1"/></sheets>` +
          '</workbook>',
      ),
    },
    {
      name: 'xl/_rels/workbook.xml.rels',
      data: encoder.encode(
        `${DECLARATION}<Relationships xmlns="${RELS_NS}">` +
          `<Relationship Id="rId1" Type="${DOC_RELS}/worksheet" Target="worksheets/sheet1.xml"/>` +
          `<Relationship Id="rId2" Type="${DOC_RELS}/styles" Target="styles.xml"/>` +
          '</Relationships>',
      ),
    },
    { name: 'xl/styles.xml', data: encoder.encode(STYLES_XML) },
    { name: 'xl/worksheets/sheet1.xml', data: encoder.encode(worksheetXml(sheet)) },
  ];

  return zip(parts);
}
