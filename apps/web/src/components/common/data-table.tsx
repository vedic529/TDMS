'use client';

import * as React from 'react';
import { ChevronDown, ChevronLeft, ChevronRight, ChevronsUpDown, ChevronUp } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { LoadingState } from './states';
import { cn } from '@/lib/utils';

export interface DataTableColumn<T> {
  id: string;
  header: string;
  cell: (row: T) => React.ReactNode;
  /** Supplying this makes the column sortable. */
  sortValue?: (row: T) => string | number;
  className?: string;
  headerClassName?: string;
  align?: 'left' | 'right';
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  loadingLabel?: string;
  /** Rendered when there are no rows. */
  empty?: React.ReactNode;
  pageSize?: number;
  initialSort?: { columnId: string; direction: 'asc' | 'desc' };
  onRowClick?: (row: T) => void;
  selection?: {
    selectedIds: string[];
    onChange: (ids: string[]) => void;
  };
  /** Optional per-row action cell rendered in a sticky right column. */
  rowActions?: (row: T) => React.ReactNode;
  className?: string;
  /** Accessible description of the table contents. */
  ariaLabel: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  loadingLabel,
  empty,
  pageSize = 15,
  initialSort,
  onRowClick,
  selection,
  rowActions,
  className,
  ariaLabel,
}: DataTableProps<T>) {
  const [sort, setSort] = React.useState(initialSort ?? null);
  const [page, setPage] = React.useState(0);

  React.useEffect(() => {
    setPage(0);
  }, [rows.length]);

  const sortedRows = React.useMemo(() => {
    if (!sort) return rows;
    const column = columns.find((entry) => entry.id === sort.columnId);
    if (!column?.sortValue) return rows;
    const factor = sort.direction === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      const left = column.sortValue!(a);
      const right = column.sortValue!(b);
      if (typeof left === 'number' && typeof right === 'number') return (left - right) * factor;
      return String(left).localeCompare(String(right)) * factor;
    });
  }, [rows, sort, columns]);

  const pageCount = Math.max(1, Math.ceil(sortedRows.length / pageSize));
  const currentPage = Math.min(page, pageCount - 1);
  const visibleRows = sortedRows.slice(currentPage * pageSize, currentPage * pageSize + pageSize);

  const allVisibleSelected =
    !!selection && visibleRows.length > 0 && visibleRows.every((row) => selection.selectedIds.includes(rowKey(row)));

  function toggleSort(columnId: string) {
    setSort((current) => {
      if (current?.columnId !== columnId) return { columnId, direction: 'asc' };
      if (current.direction === 'asc') return { columnId, direction: 'desc' };
      return null;
    });
  }

  if (loading) {
    return <LoadingState label={loadingLabel} />;
  }

  if (rows.length === 0) {
    return <>{empty}</>;
  }

  return (
    <div className={cn('space-y-3', className)}>
      <TableContainer className="max-h-[calc(100vh-22rem)]">
        <Table aria-label={ariaLabel}>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {selection && (
                <TableHead className="w-10">
                  <Checkbox
                    checked={allVisibleSelected}
                    onCheckedChange={(checked) => {
                      const visibleIds = visibleRows.map(rowKey);
                      selection.onChange(
                        checked === true
                          ? Array.from(new Set([...selection.selectedIds, ...visibleIds]))
                          : selection.selectedIds.filter((id) => !visibleIds.includes(id)),
                      );
                    }}
                    aria-label="Select all rows on this page"
                  />
                </TableHead>
              )}
              {columns.map((column) => {
                const sortable = Boolean(column.sortValue);
                const active = sort?.columnId === column.id;
                return (
                  <TableHead
                    key={column.id}
                    className={cn(column.headerClassName, column.align === 'right' && 'text-right')}
                    aria-sort={active ? (sort!.direction === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    {sortable ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(column.id)}
                        className="inline-flex items-center gap-1 rounded-sm uppercase tracking-wide hover:text-foreground"
                      >
                        {column.header}
                        {active ? (
                          sort!.direction === 'asc' ? (
                            <ChevronUp className="size-3.5" aria-hidden="true" />
                          ) : (
                            <ChevronDown className="size-3.5" aria-hidden="true" />
                          )
                        ) : (
                          <ChevronsUpDown className="size-3.5 opacity-40" aria-hidden="true" />
                        )}
                      </button>
                    ) : (
                      column.header
                    )}
                  </TableHead>
                );
              })}
              {rowActions && <TableHead className="w-16 text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleRows.map((row) => {
              const key = rowKey(row);
              const selected = selection?.selectedIds.includes(key) ?? false;
              return (
                <TableRow
                  key={key}
                  data-selected={selected}
                  className={onRowClick ? 'cursor-pointer' : undefined}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                >
                  {selection && (
                    <TableCell onClick={(event) => event.stopPropagation()}>
                      <Checkbox
                        checked={selected}
                        onCheckedChange={(checked) =>
                          selection.onChange(
                            checked === true
                              ? [...selection.selectedIds, key]
                              : selection.selectedIds.filter((id) => id !== key),
                          )
                        }
                        aria-label={`Select row ${key}`}
                      />
                    </TableCell>
                  )}
                  {columns.map((column) => (
                    <TableCell
                      key={column.id}
                      className={cn(column.className, column.align === 'right' && 'text-right tabular')}
                    >
                      {column.cell(row)}
                    </TableCell>
                  ))}
                  {rowActions && (
                    <TableCell className="text-right" onClick={(event) => event.stopPropagation()}>
                      {rowActions(row)}
                    </TableCell>
                  )}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      {pageCount > 1 && (
        <nav className="flex items-center justify-between gap-3" aria-label="Table pagination">
          <p className="text-[13px] text-muted-foreground">
            Showing {currentPage * pageSize + 1}–{Math.min((currentPage + 1) * pageSize, sortedRows.length)} of{' '}
            {sortedRows.length}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((value) => Math.max(0, value - 1))}
              disabled={currentPage === 0}
            >
              <ChevronLeft aria-hidden="true" />
              Previous
            </Button>
            <span className="text-[13px] text-muted-foreground tabular">
              Page {currentPage + 1} of {pageCount}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}
              disabled={currentPage >= pageCount - 1}
            >
              Next
              <ChevronRight aria-hidden="true" />
            </Button>
          </div>
        </nav>
      )}
    </div>
  );
}
