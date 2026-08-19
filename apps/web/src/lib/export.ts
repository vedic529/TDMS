import type { ExportFormat, ExportResult } from '@/types/common';
import { buildXlsx } from '@/lib/xlsx';

/**
 * Client-side export used by every operational page.
 *
 * SRS 2.3 / COL-06 / TRN-05: an export must use the filters currently shown on
 * the page. Callers therefore pass the rows that are visible, never the whole
 * dataset.
 *
 * Both formats produce a real file. CSV is written here; XLSX is written by
 * `lib/xlsx.ts`, which packs the OOXML parts itself rather than renaming a CSV.
 * The difference matters for identifiers: Excel reads the CSV text `000025` as
 * the number 25 and drops the leading zeros, while the XLSX cell keeps it.
 */

export interface ExportColumn<T> {
  header: string;
  value: (row: T) => string | number | null | undefined;
}

function escapeCsvCell(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '';
  const text = String(value);
  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

export function buildCsv<T>(columns: ExportColumn<T>[], rows: T[]): string {
  const header = columns.map((column) => escapeCsvCell(column.header)).join(',');
  const body = rows.map((row) => columns.map((column) => escapeCsvCell(column.value(row))).join(','));
  // A BOM keeps Excel from mangling non-ASCII characters.
  return `﻿${[header, ...body].join('\r\n')}`;
}

function triggerDownload(fileName: string, content: BlobPart, mimeType: string) {
  if (typeof window === 'undefined') return;
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

export interface ExportRequest<T> {
  format: ExportFormat;
  /** Without extension, e.g. `tdms-timetable-2026-08-10`. */
  baseFileName: string;
  columns: ExportColumn<T>[];
  rows: T[];
  /** Worksheet tab name for XLSX. Ignored by CSV, which has no sheets. */
  sheetName?: string;
}

export function exportRows<T>({
  format,
  baseFileName,
  columns,
  rows,
  sheetName,
}: ExportRequest<T>): ExportResult {
  if (format === 'xlsx') {
    const workbook = buildXlsx({
      name: sheetName ?? 'TDMS Export',
      header: columns.map((column) => column.header),
      rows: rows.map((row) => columns.map((column) => column.value(row))),
    });
    const fileName = `${baseFileName}.xlsx`;
    triggerDownload(fileName, workbook, XLSX_MIME);
    return { format, fileName, rowCount: rows.length, status: 'generated' };
  }

  const fileName = `${baseFileName}.csv`;
  triggerDownload(fileName, buildCsv(columns, rows), 'text/csv;charset=utf-8;');
  return { format, fileName, rowCount: rows.length, status: 'generated' };
}
