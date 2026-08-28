'use client';

import * as React from 'react';

import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { FilterBar, FilterField } from '@/components/common/filter-bar';
import { SimpleSelect } from '@/components/common/dependent-select';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState, ErrorState } from '@/components/common/states';
import { formatDate } from '@/lib/format';
import { ReferenceApiError } from '@/services/reference-api';
import { rollingTimetableApi, type RollingFacets, type RollingWeek } from '@/services/rolling-timetable-api';
import type { RollingSelection } from './rolling-scope-bar';
import { RollingWeekDetailDrawer, scheduleTypeLabel } from './rolling-week-detail-drawer';

const TYPE_OPTIONS = [
  { value: 'ALL', label: 'All types' },
  { value: 'UNIT', label: 'Unit' },
  { value: 'BREAK', label: 'Break' },
  { value: 'ASSESSMENT_WEEK', label: 'Assessment Week' },
];

function typeLabel(type: RollingWeek['schedule_type']): string {
  return scheduleTypeLabel(type);
}

export function RollingDatabaseView({ selection }: { selection: RollingSelection }) {
  const [facets, setFacets] = React.useState<RollingFacets>({ intake_labels: [], unit_codes: [] });
  const [intakeLabel, setIntakeLabel] = React.useState('ALL');
  const [scheduleType, setScheduleType] = React.useState('ALL');
  const [unitCode, setUnitCode] = React.useState('ALL');
  const [weekNo, setWeekNo] = React.useState('');
  const [fromDate, setFromDate] = React.useState('');
  const [toDate, setToDate] = React.useState('');
  const [rows, setRows] = React.useState<RollingWeek[]>([]);
  const [total, setTotal] = React.useState(0);
  const [offset, setOffset] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<RollingWeek | null>(null);
  const limit = 100;

  React.useEffect(() => {
    setIntakeLabel('ALL');
    setScheduleType('ALL');
    setUnitCode('ALL');
    setWeekNo('');
    setFromDate('');
    setToDate('');
    setOffset(0);
  }, [selection.trainingPackage, selection.qualificationCode, selection.durationWeeks]);

  React.useEffect(() => {
    void (async () => {
      try {
        setFacets(
          await rollingTimetableApi.listFacets(
            selection.trainingPackage,
            selection.qualificationCode,
            selection.durationWeeks,
          ),
        );
      } catch {
        setFacets({ intake_labels: [], unit_codes: [] });
      }
    })();
  }, [selection.trainingPackage, selection.qualificationCode, selection.durationWeeks]);

  React.useEffect(() => {
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const result = await rollingTimetableApi.listWeeks({
          trainingPackage: selection.trainingPackage,
          qualificationCode: selection.qualificationCode,
          durationWeeks: selection.durationWeeks,
          intakeLabel: intakeLabel === 'ALL' ? undefined : intakeLabel,
          scheduleType: scheduleType === 'ALL' ? undefined : scheduleType,
          unitCode: unitCode === 'ALL' ? undefined : unitCode,
          weekNo: weekNo ? Number(weekNo) : undefined,
          weekStartFrom: fromDate || undefined,
          weekStartTo: toDate || undefined,
          limit,
          offset,
          sort: 'week_no',
          direction: 'asc',
        });
        setRows(result.items);
        setTotal(result.total);
      } catch (caught) {
        setError(caught instanceof ReferenceApiError ? caught.message : 'Rolling timetable rows could not be loaded.');
      } finally {
        setLoading(false);
      }
    })();
  }, [selection, intakeLabel, scheduleType, unitCode, weekNo, fromDate, toDate, offset]);

  const columns = React.useMemo<DataTableColumn<RollingWeek>[]>(
    () => [
      { id: 'week', header: 'Week', cell: (row) => row.week_no, sortValue: (row) => row.week_no },
      { id: 'start', header: 'Start', cell: (row) => formatDate(row.week_start_date) },
      { id: 'end', header: 'End', cell: (row) => formatDate(row.week_end_date) },
      { id: 'intake', header: 'Intake', cell: (row) => row.intake_label, className: 'max-w-[280px] truncate' },
      {
        id: 'type',
        header: 'Type',
        cell: (row) => <Badge variant="outline">{typeLabel(row.schedule_type)}</Badge>,
      },
      { id: 'value', header: 'Value', cell: (row) => row.schedule_value },
      { id: 'unit', header: 'Unit', cell: (row) => row.unit_code ?? '' },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      <FilterBar
        onClear={() => {
          setIntakeLabel('ALL');
          setScheduleType('ALL');
          setUnitCode('ALL');
          setWeekNo('');
          setFromDate('');
          setToDate('');
          setOffset(0);
        }}
      >
        <FilterField label="Intake" htmlFor="rt-intake">
          <SimpleSelect
            id="rt-intake"
            value={intakeLabel}
            onChange={(value) => {
              setIntakeLabel(value);
              setOffset(0);
            }}
            options={[{ value: 'ALL', label: 'All intakes' }, ...facets.intake_labels.map((item) => ({ value: item, label: item }))]}
            placeholder="All intakes"
          />
        </FilterField>
        <FilterField label="Type" htmlFor="rt-type">
          <SimpleSelect
            id="rt-type"
            placeholder="Type"
            value={scheduleType}
            onChange={(value) => {
              setScheduleType(value);
              setOffset(0);
            }}
            options={TYPE_OPTIONS}
          />
        </FilterField>
        <FilterField label="Unit" htmlFor="rt-unit">
          <SimpleSelect
            id="rt-unit"
            value={unitCode}
            onChange={(value) => {
              setUnitCode(value);
              setOffset(0);
            }}
            options={[{ value: 'ALL', label: 'All units' }, ...facets.unit_codes.map((item) => ({ value: item, label: item }))]}
            placeholder="All units"
          />
        </FilterField>
        <FilterField label="Week no." htmlFor="rt-week">
          <Input
            id="rt-week"
            inputMode="numeric"
            value={weekNo}
            onChange={(event) => {
              setWeekNo(event.target.value);
              setOffset(0);
            }}
            placeholder="Any"
          />
        </FilterField>
        <FilterField label="From date" htmlFor="rt-from">
          <Input
            id="rt-from"
            type="date"
            value={fromDate}
            onChange={(event) => {
              setFromDate(event.target.value);
              setOffset(0);
            }}
          />
        </FilterField>
        <FilterField label="To date" htmlFor="rt-to">
          <Input
            id="rt-to"
            type="date"
            value={toDate}
            onChange={(event) => {
              setToDate(event.target.value);
              setOffset(0);
            }}
          />
        </FilterField>
      </FilterBar>

      {error ? (
        <ErrorState title="Rolling timetable could not be loaded" description={error} />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => String(row.id)}
          loading={loading}
          pageSize={100}
          activeRowKey={selected ? String(selected.id) : undefined}
          onRowClick={setSelected}
          ariaLabel="Rolling timetable database view"
          empty={<EmptyState title="No stored weeks" description="Nothing matches these filters." />}
        />
      )}

      <RollingWeekDetailDrawer week={selected} onOpenChange={(open) => !open && setSelected(null)} />

      <div className="flex items-center justify-between text-[12px] text-muted-foreground">
        <p>
          Showing {rows.length} of {total} stored requirement rows
        </p>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
            Previous
          </Button>
          <Button variant="outline" size="sm" disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}>
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
