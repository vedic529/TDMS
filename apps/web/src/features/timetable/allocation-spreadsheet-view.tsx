'use client';

import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState } from '@/components/common/states';
import { formatDate } from '@/lib/format';
import {
  ALLOCATION_EMPTY_DESCRIPTION,
  ALLOCATION_EMPTY_TITLE,
  type AllocationCalendar,
  type AllocationCalendarSession,
} from '@/services/allocation-api';

interface SpreadsheetRow extends AllocationCalendarSession {
  date: string;
  weekday: string;
}

export function AllocationSpreadsheet({
  grid,
  onSelect,
}: {
  grid: AllocationCalendar;
  onSelect: (session: AllocationCalendarSession) => void;
}) {
  const rows = React.useMemo<SpreadsheetRow[]>(
    () =>
      grid.days.flatMap((day) =>
        day.sessions.map((session) => ({
          ...session,
          date: day.date,
          weekday: day.weekday,
        })),
      ),
    [grid],
  );

  const columns: DataTableColumn<SpreadsheetRow>[] = [
    {
      id: 'date',
      header: 'Date',
      cell: (row) => formatDate(row.date),
      sortValue: (row) => row.date,
    },
    {
      id: 'weekday',
      header: 'Day',
      cell: (row) => row.weekday.slice(0, 3),
      sortValue: (row) => row.weekday,
    },
    {
      id: 'unit',
      header: 'Unit',
      cell: (row) => (
        <span className="font-medium text-foreground">
          {row.unit_code}
          {row.unit_title ? ` · ${row.unit_title}` : ''}
        </span>
      ),
      sortValue: (row) => row.unit_code,
    },
    { id: 'qualification', header: 'Qualification', cell: (row) => row.qualification_code, sortValue: (row) => row.qualification_code },
    { id: 'stream', header: 'Stream', cell: (row) => row.stream, sortValue: (row) => row.stream },
    {
      id: 'time',
      header: 'Time',
      cell: (row) => `${row.start_time}–${row.end_time}`,
      sortValue: (row) => row.start_time,
    },
    { id: 'classroom', header: 'Classroom', cell: (row) => row.classroom || '—', sortValue: (row) => row.classroom },
    { id: 'trainer', header: 'Trainer', cell: (row) => row.trainer || '—', sortValue: (row) => row.trainer },
    { id: 'mode', header: 'Mode', cell: (row) => row.delivery_mode, sortValue: (row) => row.delivery_mode },
    {
      id: 'intakes',
      header: 'Intake',
      cell: (row) => (row.intakes.length ? row.intakes.join(', ') : '—'),
      sortValue: (row) => row.intakes.join(', '),
    },
  ];

  if (grid.empty || rows.length === 0) {
    return <EmptyState title={ALLOCATION_EMPTY_TITLE} description={ALLOCATION_EMPTY_DESCRIPTION} />;
  }

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(row) => String(row.session_id)}
      ariaLabel="Allocation spreadsheet"
      onRowClick={onSelect}
    />
  );
}
