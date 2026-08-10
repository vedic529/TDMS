import type { ExportFormat, ExportResult } from '@/types/common';

/**
 * Client-side export used by every operational page.
 *
 * SRS 2.3 / COL-06 / TRN-05: an export must use the filters currently shown on
 * the page. Callers therefore pass the rows that are visible, never the whole
 * mock dataset.
 *
 * CSV is produced properly in the browser. XLSX is *not* implemented in the
 * frontend prototype: the action, interface and result are real, but the file
 * produced is CSV and the returned `notice` says so. Production XLSX generation
 * belongs to the TDMS API (BULK-10, COL-06).
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

function triggerDownload(fileName: string, content: string, mimeType: string) {
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

export interface ExportRequest<T> {
  format: ExportFormat;
  /** Without extension, e.g. `tdms-timetable-2026-08-10`. */
  baseFileName: string;
  columns: ExportColumn<T>[];
  rows: T[];
}

export function exportRows<T>({ format, baseFileName, columns, rows }: ExportRequest<T>): ExportResult {
  const csv = buildCsv(columns, rows);

  if (format === 'csv') {
    const fileName = `${baseFileName}.csv`;
    triggerDownload(fileName, csv, 'text/csv;charset=utf-8;');
    return { format, fileName, rowCount: rows.length, status: 'generated' };
  }

  const fileName = `${baseFileName}.csv`;
  triggerDownload(fileName, csv, 'text/csv;charset=utf-8;');
  return {
    format,
    fileName,
    rowCount: rows.length,
    status: 'demo-fallback',
    notice:
      'XLSX generation is not implemented in the frontend prototype. A CSV file containing the same filtered rows has been downloaded. Production XLSX files will be produced by the TDMS API.',
  };
}
