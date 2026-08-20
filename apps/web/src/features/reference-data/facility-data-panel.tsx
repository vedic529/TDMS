'use client';

import * as React from 'react';

import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { FilterBar, FilterField } from '@/components/common/filter-bar';
import { SimpleSelect } from '@/components/common/dependent-select';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState, ErrorState } from '@/components/common/states';
import { ExportMenu } from '@/components/common/export-menu';
import { MultiSelectFilter } from '@/components/common/multi-select-filter';
import { useCascadingFilters } from './use-cascading-filters';
import { toFacilityRecord } from './reference-adapters';
import { ReferenceApiError, referenceApi } from '@/services/reference-api';
import { INTERFACE_NAMES, SRS_PAGE_REFERENCE } from '@/lib/interface-names';
import { today } from '@/lib/format';
import type { FacilityRecord } from '@/types/reference';

const DAYS = [
  { key: 'monday', label: 'Mon', full: 'Monday' },
  { key: 'tuesday', label: 'Tue', full: 'Tuesday' },
  { key: 'wednesday', label: 'Wed', full: 'Wednesday' },
  { key: 'thursday', label: 'Thu', full: 'Thursday' },
  { key: 'friday', label: 'Fri', full: 'Friday' },
] as const;

/** A room admits a qualification when this faculty is `NA` (requirement §8). */
const UNRESTRICTED_FACULTY = 'NA';

/**
 * A room is available on a day when any faculty rule on it says so.
 *
 * Availability is recorded per faculty, because ten rooms carry more than one
 * faculty with different weekday patterns. The table shows the room, so it
 * shows whether the room is usable at all that day; the faculty column says by
 * whom.
 */
function availableOn(row: FacilityRecord, day: (typeof DAYS)[number]['key']): boolean {
  return row.faculties.some((rule) => rule[day]);
}

function matchesSearch(row: FacilityRecord, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [
    row.classroomName,
    row.campusName,
    row.state,
    row.sourceLocation,
    row.classroomType,
    row.collegeShortNames.join(' '),
    row.faculties.map((rule) => `${rule.faculty} ${rule.remarks ?? ''}`).join(' '),
  ]
    .join(' ')
    .toLowerCase()
    .includes(needle);
}

/**
 * Facility Data (SRS Page 4C).
 *
 * Read-only: the supplied file is the source, and no create or edit workflow
 * was requested. Filters reuse the shared College -> Campus cascade so this tab
 * narrows the same way the other two do.
 */
export function FacilityDataPanel() {
  const cascade = useCascadingFilters();

  const [search, setSearch] = React.useState('');
  const [faculty, setFaculty] = React.useState('');
  const [rows, setRows] = React.useState<FacilityRecord[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    // Cleared first for the same reason the other tabs clear: a stale table
    // under a changed heading reads as an answer.
    setRows([]);
    try {
      const facilities = await referenceApi.listFacilities({
        collegeIds: cascade.scope.collegeIds,
        campusIds: cascade.scope.campusIds,
      });
      setRows(facilities.map(toFacilityRecord));
    } catch (caught) {
      setError(
        caught instanceof ReferenceApiError
          ? caught.message
          : 'Facility Data could not be loaded. Try again, or contact the TDMS administrator.',
      );
    } finally {
      setLoading(false);
    }
  }, [cascade.scope.collegeIds, cascade.scope.campusIds]);

  React.useEffect(() => {
    void load();
  }, [load]);

  /** Every faculty actually present, so the filter never offers an empty result. */
  const facultyOptions = React.useMemo(() => {
    const present = new Set<string>();
    for (const row of rows) for (const rule of row.faculties) present.add(rule.faculty);
    return [...present].sort().map((value) => ({ value, label: value }));
  }, [rows]);

  const visible = React.useMemo(
    () =>
      rows.filter(
        (row) =>
          matchesSearch(row, search) &&
          (!faculty || row.faculties.some((rule) => rule.faculty === faculty)),
      ),
    [rows, search, faculty],
  );

  const columns: DataTableColumn<FacilityRecord>[] = [
    { id: 'state', header: 'State', cell: (row) => row.state, sortValue: (row) => row.state },
    {
      id: 'location',
      header: 'Location',
      cell: (row) => (
        <span className="block max-w-80 truncate" title={row.sourceLocation}>
          {row.sourceLocation}
        </span>
      ),
      sortValue: (row) => row.sourceLocation,
    },
    {
      id: 'college',
      header: 'College',
      cell: (row) => (
        <span className="flex flex-wrap gap-1">
          {row.collegeShortNames.map((name) => (
            <Badge key={name} variant="neutral" className="text-[10px]">
              {name}
            </Badge>
          ))}
        </span>
      ),
      sortValue: (row) => row.collegeShortNames.join(', '),
    },
    {
      id: 'faculty',
      header: 'Faculty',
      cell: (row) => (
        <span className="flex flex-wrap gap-1">
          {row.faculties.map((rule) => (
            <Badge
              key={rule.faculty}
              variant={rule.faculty === UNRESTRICTED_FACULTY ? 'info' : 'outline'}
              className="text-[10px]"
              title={
                rule.faculty === UNRESTRICTED_FACULTY
                  ? 'Not restricted to a faculty — available to every qualification'
                  : `Qualifications in ${rule.faculty}`
              }
            >
              {rule.faculty === UNRESTRICTED_FACULTY ? 'NA — all faculties' : rule.faculty}
            </Badge>
          ))}
        </span>
      ),
      sortValue: (row) => row.faculties.map((rule) => rule.faculty).join(', '),
    },
    {
      id: 'classroomName',
      header: 'Classroom Name',
      cell: (row) => <span className="font-medium text-foreground">{row.classroomName}</span>,
      sortValue: (row) => row.classroomName,
    },
    {
      id: 'capacity',
      header: 'Capacity',
      cell: (row) => row.capacity,
      sortValue: (row) => row.capacity,
      align: 'right',
    },
    {
      id: 'classroomType',
      header: 'Classroom Type',
      cell: (row) => row.classroomType,
      sortValue: (row) => row.classroomType,
    },
    ...DAYS.map<DataTableColumn<FacilityRecord>>((day) => ({
      id: day.key,
      header: day.label,
      cell: (row) => {
        const open = availableOn(row, day.key);
        return (
          <Badge variant={open ? 'success' : 'neutral'} className="text-[10px]">
            <span className="sr-only">{`${day.full}: `}</span>
            {open ? 'Yes' : 'No'}
          </Badge>
        );
      },
      sortValue: (row) => (availableOn(row, day.key) ? 1 : 0),
    })),
    {
      id: 'remarks',
      header: 'Remarks',
      cell: (row) => {
        const notes = row.faculties.map((rule) => rule.remarks).filter(Boolean) as string[];
        if (notes.length === 0) return <span className="text-muted-foreground">—</span>;
        const joined = notes.join(' · ');
        return (
          <span className="block max-w-96 truncate" title={joined}>
            {joined}
          </span>
        );
      },
    },
  ];

  return (
    <div className="space-y-5">
      <FilterBar
        onClear={() => {
          cascade.clear();
          setSearch('');
          setFaculty('');
        }}
        trailing={
          <ExportMenu
            rows={visible}
            baseFileName={`tdms-facility-data-${today()}`}
            pageReference={SRS_PAGE_REFERENCE.facilityData}
            columns={[
              { header: 'State', value: (row) => row.state },
              { header: 'Location', value: (row) => row.sourceLocation },
              { header: 'College', value: (row) => row.collegeShortNames.join(', ') },
              { header: 'Faculty', value: (row) => row.faculties.map((r) => r.faculty).join(', ') },
              { header: 'Classroom Name', value: (row) => row.classroomName },
              { header: 'Capacity', value: (row) => row.capacity },
              { header: 'Classroom Type', value: (row) => row.classroomType },
              ...DAYS.map((day) => ({
                header: day.full,
                value: (row: FacilityRecord) => (availableOn(row, day.key) ? 'Yes' : 'No'),
              })),
              {
                header: 'Remarks',
                value: (row) =>
                  row.faculties
                    .map((rule) => rule.remarks)
                    .filter(Boolean)
                    .join(' | '),
              },
            ]}
          />
        }
      >
        <FilterField label="College" htmlFor="facility-college">
          <MultiSelectFilter
            id="facility-college"
            options={cascade.collegeOptions}
            value={cascade.filters.collegeIds}
            onChange={cascade.setColleges}
            allLabel="All Colleges"
            noun="College"
          />
        </FilterField>
        <FilterField label="Campus" htmlFor="facility-campus">
          <MultiSelectFilter
            id="facility-campus"
            options={cascade.campusOptions}
            value={cascade.filters.campusIds}
            onChange={cascade.setCampuses}
            allLabel="All Campuses"
            noun="Campus"
            loading={cascade.loadingCampuses}
          />
        </FilterField>
        <FilterField label="Faculty" htmlFor="facility-faculty">
          <SimpleSelect
            id="facility-faculty"
            value={faculty}
            onChange={setFaculty}
            options={facultyOptions}
            placeholder="All faculties"
          />
        </FilterField>
        <FilterField label="Search" htmlFor="facility-search">
          <Input
            id="facility-search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Classroom, location or remark"
            aria-label="Search Facility Data"
          />
        </FilterField>
      </FilterBar>

      {error ? (
        <ErrorState title="Facility Data could not be loaded" description={error} />
      ) : (
        <DataTable
          rows={visible}
          columns={columns}
          rowKey={(row) => row.id}
          ariaLabel={INTERFACE_NAMES.facilityData}
          loading={loading}
          loadingLabel={`Loading ${INTERFACE_NAMES.facilityData}`}
          empty={
            <EmptyState
              title="No facility matches these filters"
              description="Widen the college, campus or faculty filter, or clear the search."
            />
          }
        />
      )}
    </div>
  );
}
