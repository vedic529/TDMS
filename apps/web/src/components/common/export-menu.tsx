'use client';

import * as React from 'react';
import { Download, FileSpreadsheet, FileText } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { exportRows, type ExportColumn } from '@/lib/export';
import { getTdmsClient } from '@/services';
import { useAuth } from '@/features/auth/auth-context';
import type { ExportFormat } from '@/types/common';

interface ExportMenuProps<T> {
  /** Rows currently shown by the page filters (SRS 2.3 - export follows filters). */
  rows: T[];
  columns: ExportColumn<T>[];
  baseFileName: string;
  /** Approved SRS page reference recorded in the user activity record. */
  pageReference: string;
  disabled?: boolean;
  label?: string;
}

/**
 * Export action shared by every operational page.
 *
 * SRS 2.3: an export uses the filters currently shown on the page and records
 * the number of exported rows in the user activity record (LOG-01).
 */
export function ExportMenu<T>({
  rows,
  columns,
  baseFileName,
  pageReference,
  disabled,
  label = 'Export',
}: ExportMenuProps<T>) {
  const { user } = useAuth();

  async function handleExport(format: ExportFormat) {
    if (!user) return;
    if (rows.length === 0) {
      toast.warning('There is nothing to export', {
        description: 'Adjust the filters so at least one row is shown, then export again.',
      });
      return;
    }

    const result = exportRows({ format, baseFileName, columns, rows });

    await getTdmsClient().recordActivity({
      userReference: user.organisationEmail,
      accessLevel: user.role,
      assignment: user.assignment,
      pageOrFunction: pageReference,
      action: 'Export',
      recordOrBatchReference: `${result.rowCount} rows`,
      result: 'Completed',
      plainLanguageDetail: `Filtered result exported as ${result.fileName} (${result.rowCount} rows).`,
    });

    if (result.status === 'demo-fallback') {
      toast.info('XLSX export is not implemented yet', { description: result.notice, duration: 8000 });
    } else {
      toast.success('Export complete', {
        description: `${result.rowCount} filtered ${result.rowCount === 1 ? 'row' : 'rows'} downloaded as ${result.fileName}.`,
      });
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled}>
          <Download aria-hidden="true" />
          {label}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Export current filtered result</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void handleExport('csv')}>
          <FileText aria-hidden="true" />
          Export CSV
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void handleExport('xlsx')}>
          <FileSpreadsheet aria-hidden="true" />
          Export XLSX
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
