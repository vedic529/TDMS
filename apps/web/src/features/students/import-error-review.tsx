'use client';

import * as React from 'react';
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, FileText, Search, Trash2, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ImportStatusBadge } from '@/components/common/status-badge';
import { ConfirmationDialog } from '@/components/common/confirmation-dialog';
import {
  BLOCKING_STATUSES,
  filterErrorRows,
  pruneSelection,
  selectionState,
  targetedRows,
  toggleAllVisible,
  toggleOne,
  type StatusFilter,
} from '@/features/students/import-error-selection';
import type { ExportFormat } from '@/types/common';
import type { StagedRowStatus, StagedStudentRow } from '@/types/import';

interface ImportErrorReviewProps {
  /** Blocking rows only, in source order. */
  rows: StagedStudentRow[];
  canEdit: boolean;
  busy?: boolean;
  /** Exports the given rows. The parent owns file naming and the activity record. */
  onDownload: (format: ExportFormat, rows: StagedStudentRow[]) => void;
  /** Removes the given rows from the staging area. */
  onDelete: (rows: StagedStudentRow[]) => void;
}

/**
 * Errors identified — review, download and delete the rows that block a save.
 *
 * The staging table above is where a value is corrected one row at a time. This
 * section answers the other question: which rows are wrong, and can they go?
 * Deleting removes a row from the staging area only. Nothing has been written to
 * the database at this point, and the uploaded file is not touched, so a deleted
 * row comes back by uploading the file again.
 */
export const ImportErrorReview = React.forwardRef<HTMLDivElement, ImportErrorReviewProps>(
  function ImportErrorReview({ rows, canEdit, busy, onDownload, onDelete }, ref) {
    const [selectedIds, setSelectedIds] = React.useState<ReadonlySet<string>>(new Set());
    const [statusFilter, setStatusFilter] = React.useState<StatusFilter>('all');
    const [query, setQuery] = React.useState('');
    const [confirmOpen, setConfirmOpen] = React.useState(false);

    // A correction or a deletion changes the row set. Drop any selected id that
    // no longer exists, without touching the rest of the selection.
    React.useEffect(() => {
      setSelectedIds((current) => pruneSelection(current, rows.map((row) => row.id)));
    }, [rows]);

    const countsByStatus = React.useMemo(() => {
      const counts = new Map<StagedRowStatus, number>();
      for (const row of rows) counts.set(row.status, (counts.get(row.status) ?? 0) + 1);
      return counts;
    }, [rows]);

    const visible = React.useMemo(
      () => filterErrorRows(rows, statusFilter, query),
      [rows, statusFilter, query],
    );

    const selected = React.useMemo(
      () => rows.filter((row) => selectedIds.has(row.id)),
      [rows, selectedIds],
    );

    const visibleIds = React.useMemo(() => visible.map((row) => row.id), [visible]);
    const headerState = selectionState(visibleIds, selectedIds);

    function handleToggleAll() {
      setSelectedIds((current) => toggleAllVisible(current, visibleIds));
    }

    function toggleRow(id: string) {
      setSelectedIds((current) => toggleOne(current, id));
    }

    /** With nothing ticked, the actions apply to every error row shown. */
    const targeted = targetedRows(visible, selected);
    const usingSelection = selected.length > 0;

    function handleDelete() {
      onDelete(targeted);
      setConfirmOpen(false);
      setSelectedIds(new Set());
    }

    const filters: Array<{ value: StatusFilter; label: string; count: number }> = [
      { value: 'all', label: 'All errors', count: rows.length },
      ...BLOCKING_STATUSES.map((status) => ({
        value: status as StatusFilter,
        label: status,
        count: countsByStatus.get(status) ?? 0,
      })).filter((entry) => entry.count > 0),
    ];

    return (
      <Card
        ref={ref}
        id="import-errors-identified"
        tabIndex={-1}
        className="scroll-mt-4 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/25"
      >
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              {rows.length === 0 ? (
                <CheckCircle2 className="size-4 text-success" aria-hidden="true" />
              ) : (
                <AlertTriangle className="size-4 text-warning" aria-hidden="true" />
              )}
              Errors identified
            </CardTitle>
            <CardDescription>
              {rows.length === 0
                ? 'Every staged row is Ready or excluded. There is nothing to review here.'
                : 'Download these rows to correct them outside TDMS, or delete them from the staging area. Correcting a single value is still done in the staging table above.'}
            </CardDescription>
          </div>

          {rows.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" disabled={targeted.length === 0}>
                    <Download aria-hidden="true" />
                    Download {usingSelection ? `${selected.length} selected` : 'all errors'}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuLabel>
                    {targeted.length} error {targeted.length === 1 ? 'row' : 'rows'} with their issues
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={() => onDownload('xlsx', targeted)}>
                    <FileSpreadsheet aria-hidden="true" />
                    Download XLSX
                  </DropdownMenuItem>
                  <DropdownMenuItem onSelect={() => onDownload('csv', targeted)}>
                    <FileText aria-hidden="true" />
                    Download CSV
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>

              <Button
                variant="destructive"
                size="sm"
                onClick={() => setConfirmOpen(true)}
                disabled={!canEdit || busy || targeted.length === 0}
              >
                <Trash2 aria-hidden="true" />
                Delete {usingSelection ? `${selected.length} selected` : 'all errors'}
              </Button>
            </div>
          )}
        </CardHeader>

        {rows.length > 0 && (
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              {filters.map((filter) => (
                <Button
                  key={filter.value}
                  variant={statusFilter === filter.value ? 'secondary' : 'outline'}
                  size="sm"
                  onClick={() => setStatusFilter(filter.value)}
                  aria-pressed={statusFilter === filter.value}
                >
                  {filter.label}
                  <Badge variant="neutral" className="ml-1 tabular text-[10px]">
                    {filter.count}
                  </Badge>
                </Button>
              ))}

              <div className="relative ml-auto w-full sm:w-64">
                <Search
                  className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
                  aria-hidden="true"
                />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search name, ID or issue"
                  aria-label="Search the identified errors"
                  className="h-8 pl-8 text-[13px]"
                />
              </div>
            </div>

            <p className="text-[12px] text-muted-foreground" aria-live="polite">
              Showing {visible.length} of {rows.length} error {rows.length === 1 ? 'row' : 'rows'}
              {selected.length > 0 && ` · ${selected.length} selected`}
              {selected.length > 0 && (
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto p-0 pl-2 text-[12px]"
                  onClick={() => setSelectedIds(new Set())}
                >
                  <X aria-hidden="true" />
                  Clear selection
                </Button>
              )}
            </p>

            <TableContainer className="max-h-[28rem]">
              <Table aria-label="Errors identified in the staged rows">
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="w-10">
                      <Checkbox
                        checked={
                          headerState === 'all' ? true : headerState === 'some' ? 'indeterminate' : false
                        }
                        onCheckedChange={handleToggleAll}
                        disabled={visible.length === 0}
                        aria-label={
                          headerState === 'all'
                            ? `Clear the selection of ${visible.length} shown error rows`
                            : `Select all ${visible.length} shown error rows`
                        }
                      />
                    </TableHead>
                    <TableHead className="w-16">Source row</TableHead>
                    <TableHead className="w-32">Student ID</TableHead>
                    <TableHead className="w-44">Name</TableHead>
                    <TableHead className="w-28">College</TableHead>
                    <TableHead className="w-32">Campus</TableHead>
                    <TableHead className="w-32">Qualification</TableHead>
                    <TableHead className="w-40">Status</TableHead>
                    <TableHead className="min-w-80">Issue</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visible.length === 0 ? (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={9} className="py-8 text-center text-[13px] text-muted-foreground">
                        No error row matches this filter.
                      </TableCell>
                    </TableRow>
                  ) : (
                    visible.map((row) => {
                      const checked = selectedIds.has(row.id);
                      return (
                        <TableRow key={row.id} data-selected={checked ? 'true' : undefined}>
                          <TableCell>
                            <Checkbox
                              checked={checked}
                              onCheckedChange={() => toggleRow(row.id)}
                              aria-label={`Select source row ${row.sourceRowNumber}`}
                            />
                          </TableCell>
                          <TableCell className="tabular">{row.sourceRowNumber}</TableCell>
                          <TableCell className="tabular text-[13px]">{row.studentId || '—'}</TableCell>
                          <TableCell className="text-[13px]">
                            {[row.firstName, row.lastName].filter(Boolean).join(' ') || '—'}
                          </TableCell>
                          <TableCell className="text-[13px]">{row.collegeValue || '—'}</TableCell>
                          <TableCell className="truncate text-[13px]" title={row.campusValue}>
                            {row.campusValue || '—'}
                          </TableCell>
                          <TableCell className="text-[13px]">{row.qualificationValue || '—'}</TableCell>
                          <TableCell>
                            <ImportStatusBadge status={row.status} />
                          </TableCell>
                          <TableCell>
                            <ul className="space-y-1">
                              {row.issues.map((issue, index) => (
                                <li key={index} className="text-[12px] leading-relaxed text-destructive">
                                  <span className="font-medium">{issue.field}:</span> {issue.message}
                                </li>
                              ))}
                            </ul>
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        )}

        <ConfirmationDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title={`Delete ${targeted.length} error ${targeted.length === 1 ? 'row' : 'rows'} from the staging area?`}
          description="The rows are removed from this staging area only. Nothing has been written to the database, and your uploaded file is not changed."
          confirmLabel={`Delete ${targeted.length} ${targeted.length === 1 ? 'row' : 'rows'}`}
          variant="destructive"
          busy={busy}
          onConfirm={handleDelete}
        >
          <div className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-[13px]">
            <p className="text-muted-foreground">
              {usingSelection
                ? `${selected.length} selected of ${rows.length} error rows.`
                : `Every error row currently shown (${visible.length} of ${rows.length}).`}
            </p>
            <p className="mt-2 text-foreground">
              To get them back you would upload the file again. Download them first if you intend to correct
              them outside TDMS.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => onDownload('xlsx', targeted)}>
                <FileSpreadsheet aria-hidden="true" />
                Download XLSX first
              </Button>
              <Button variant="outline" size="sm" onClick={() => onDownload('csv', targeted)}>
                <FileText aria-hidden="true" />
                Download CSV first
              </Button>
            </div>
          </div>
        </ConfirmationDialog>
      </Card>
    );
  },
);
