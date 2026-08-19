'use client';

import * as React from 'react';
import { Trash2, Users } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { formatIntake } from '@/lib/student-rules';
import { FilterField } from '@/components/common/filter-bar';
import { EmptyState } from '@/components/common/states';
import { ExportMenu } from '@/components/common/export-menu';
import { RecycleAreaDialog } from '@/components/common/recycle-area-dialog';
import { useReferenceData } from '@/features/shared/reference-data-context';
import { useCascadingFilters } from '@/features/reference-data/use-cascading-filters';
import { MultiSelectFilter } from '@/components/common/multi-select-filter';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient } from '@/services';
import { SRS_PAGE_REFERENCE } from '@/lib/interface-names';
import { formatDate, today } from '@/lib/format';
import type { StudentFilters, StudentRecord } from '@/types/student';

/**
 * Student records list.
 *
 * Every approved user may view and download student information (SRS 3.4), so
 * this panel is available to all access levels. Opening a record for editing
 * still requires the Student Data Officer work assignment, Admin or Super Admin.
 */
export function StudentRecordsPanel({ onOpenStudent }: { onOpenStudent: (studentId: string) => void }) {
  const { user, permissions } = useAuth();
  const { collegeById, campusById } = useReferenceData();
  const cascade = useCascadingFilters();

  const [filters, setFilters] = React.useState<StudentFilters>({});
  const [rows, setRows] = React.useState<StudentRecord[]>([]);
  const [loading, setLoading] = React.useState(true);

  const [recycleOpen, setRecycleOpen] = React.useState(false);
  const [deletedRows, setDeletedRows] = React.useState<StudentRecord[]>([]);
  const [recycleLoading, setRecycleLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      // The cascade owns College/Campus/Qualification; `filters` keeps only the
      // free-text search. Passing both would let a stale id from the old state
      // silently narrow the list.
      const all = await getTdmsClient().listStudents({ search: filters.search });

      const colleges = new Set(cascade.filters.collegeIds);
      const campuses = new Set(cascade.filters.campusIds);
      const qualifications = new Set(
        cascade.qualificationOptions
          .filter((option) => cascade.filters.qualificationIds.includes(option.value))
          .map((option) => option.label.split(' — ')[0]),
      );

      // An empty set means "no restriction at that level" — the Select All
      // contract — not "match nothing".
      setRows(
        all.filter(
          (student) =>
            (colleges.size === 0 || colleges.has(student.collegeId)) &&
            (campuses.size === 0 || campuses.has(student.campusId)) &&
            (qualifications.size === 0 || qualifications.has(student.qualificationCode)),
        ),
      );
    } finally {
      setLoading(false);
    }
  }, [
    filters.search,
    cascade.filters.collegeIds,
    cascade.filters.campusIds,
    cascade.filters.qualificationIds,
    cascade.qualificationOptions,
  ]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const loadDeleted = React.useCallback(async () => {
    setRecycleLoading(true);
    try {
      setDeletedRows(await getTdmsClient().listDeletedStudents());
    } finally {
      setRecycleLoading(false);
    }
  }, []);


  const columns: DataTableColumn<StudentRecord>[] = [
    {
      id: 'studentId',
      header: 'Student ID',
      cell: (row) => <span className="font-medium text-foreground">{row.studentId}</span>,
      sortValue: (row) => row.studentId,
    },
    {
      id: 'name',
      header: 'Student',
      cell: (row) => `${row.firstName} ${row.lastName}`.trim(),
      sortValue: (row) => `${row.lastName} ${row.firstName}`,
    },
    {
      id: 'qualification',
      header: 'Qualification',
      cell: (row) => (
        <span className="block max-w-72">
          <span className="block font-medium text-foreground">{row.qualificationCode}</span>
          <span className="block truncate text-[12px] text-muted-foreground">{row.qualificationTitle}</span>
        </span>
      ),
      sortValue: (row) => row.qualificationCode,
    },
    { id: 'group', header: 'Group', cell: (row) => row.group || '—', sortValue: (row) => row.group },
    // Displayed as DD-MMM-YYYY, sorted on the underlying ISO date so
    // January 2027 does not sort before August 2026.
    {
      id: 'intake',
      header: 'Intake',
      // A CT student has no intake. `N/A` says that deliberately; an
      // em dash would read as missing data.
      cell: (row) => (row.intake ? formatIntake(row.intake) : 'N/A'),
      sortValue: (row) => row.intake ?? '',
    },
    {
      id: 'campus',
      header: 'Campus',
      cell: (row) => campusById(row.campusId)?.campusName ?? '—',
      sortValue: (row) => campusById(row.campusId)?.campusName ?? '',
    },
    {
      id: 'coe',
      header: 'CoE',
      cell: (row) => <Badge variant={row.coeStatus === 'CoE' ? 'neutral' : 'outline'}>{row.coeStatus}</Badge>,
      sortValue: (row) => row.coeStatus,
    },
    {
      id: 'dates',
      header: 'Proposed dates',
      cell: (row) => (
        <span className="whitespace-nowrap tabular">
          {formatDate(row.proposedStartDate)} – {formatDate(row.proposedEndDate)}
        </span>
      ),
      sortValue: (row) => row.proposedStartDate,
    },
  ];

  return (
    <>
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>Student records</CardTitle>
            <CardDescription>
              {rows.length} {rows.length === 1 ? 'record' : 'records'} match the current filters. Select a row to open
              the record.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <ExportMenu
              rows={rows}
              baseFileName={`tdms-students-${today()}`}
              pageReference={SRS_PAGE_REFERENCE.singleStudentEntry}
              columns={[
                { header: 'Group', value: (row) => row.group },
                { header: 'Intake', value: (row) => (row.intake ? formatIntake(row.intake) : 'N/A') },
                { header: 'College', value: (row) => collegeById(row.collegeId)?.collegeFullName ?? '' },
                { header: 'Campus', value: (row) => campusById(row.campusId)?.campusName ?? '' },
                { header: 'College Email', value: (row) => row.collegeEmail },
                { header: 'First Name', value: (row) => row.firstName },
                { header: 'Last Name', value: (row) => row.lastName },
                { header: 'Student ID', value: (row) => row.studentId },
                { header: 'CoE / Non-CoE', value: (row) => row.coeStatus },
                { header: 'Proposed Start Date', value: (row) => row.proposedStartDate },
                { header: 'Proposed End Date', value: (row) => row.proposedEndDate },
                { header: 'Actual Course Duration', value: (row) => row.actualCourseDuration },
                { header: 'Course Duration Option', value: (row) => row.courseDurationOption ?? '' },
                { header: 'Qualification Title', value: (row) => row.qualificationTitle },
                { header: 'Qualification Code', value: (row) => row.qualificationCode },
                { header: 'CT Student', value: (row) => row.ctStudent },
                { header: 'Personal Email', value: (row) => row.personalEmail },
                { header: 'Primary Phone', value: (row) => row.primaryPhone },
                { header: 'State', value: (row) => row.state },
                { header: 'Primary Country', value: (row) => row.primaryCountry },
                { header: 'Remarks', value: (row) => row.remarks },
              ]}
            />
            {permissions.maintainStudentData && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  void loadDeleted();
                  setRecycleOpen(true);
                }}
              >
                <Trash2 aria-hidden="true" />
                Deleted Records
              </Button>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <FilterField label="Search" htmlFor="student-list-search">
              <Input
                id="student-list-search"
                value={filters.search ?? ''}
                onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
                placeholder="Student ID, name or email"
              />
            </FilterField>
            {/*
              The same cascade Page 4 uses, from the same service. College
              narrows Campus; College and Campus together narrow Qualification to
              what is genuinely offered there — never the global list.
            */}
            <FilterField label="College" htmlFor="student-list-college">
              <MultiSelectFilter
                id="student-list-college"
                value={cascade.filters.collegeIds}
                onChange={cascade.setColleges}
                options={cascade.collegeOptions}
                allLabel="All Colleges"
                noun="College"
              />
            </FilterField>
            <FilterField label="Campus" htmlFor="student-list-campus">
              <MultiSelectFilter
                id="student-list-campus"
                value={cascade.filters.campusIds}
                onChange={cascade.setCampuses}
                options={cascade.campusOptions}
                allLabel="All Campuses"
                noun="Campus"
                loading={cascade.loadingCampuses}
              />
            </FilterField>
            <FilterField label="Qualification" htmlFor="student-list-qualification">
              <MultiSelectFilter
                id="student-list-qualification"
                value={cascade.filters.qualificationIds}
                onChange={cascade.setQualifications}
                options={cascade.qualificationOptions}
                allLabel="All Qualifications"
                noun="Qualification"
                loading={cascade.loadingQualifications}
                emptyMessage="No qualifications are offered for the selected College and Campus."
              />
            </FilterField>
          </div>

          <DataTable
            ariaLabel="Student records"
            columns={columns}
            rows={rows}
            rowKey={(row) => row.id}
            loading={loading}
            loadingLabel="Loading student records…"
            pageSize={10}
            initialSort={{ columnId: 'studentId', direction: 'asc' }}
            onRowClick={(row) => onOpenStudent(row.studentId)}
            empty={
              <EmptyState
                title="No student record matches the selected filters."
                description="Change or clear a filter to see more records."
                icon={Users}
              />
            }
          />
        </CardContent>
      </Card>

      <RecycleAreaDialog
        open={recycleOpen}
        onOpenChange={setRecycleOpen}
        title="Deleted student records"
        recordTypeLabel="Student Record"
        reasonContext="student"
        rows={deletedRows}
        loading={recycleLoading}
        rowKey={(row) => row.id}
        canRestore={permissions.maintainStudentData}
        columns={[
          {
            id: 'studentId',
            header: 'Student ID',
            cell: (row) => row.studentId,
            sortValue: (row) => row.studentId,
          },
          { id: 'name', header: 'Student', cell: (row) => `${row.firstName} ${row.lastName}`.trim() },
          { id: 'qualification', header: 'Qualification', cell: (row) => row.qualificationCode },
        ]}
        describe={(row) => ({
          primary: row.studentId,
          secondary: `${row.firstName} ${row.lastName}`.trim(),
          lines: [`${row.qualificationCode} — ${row.qualificationTitle}`],
        })}
        onRestore={async (row, reason, reasonDetail) => {
          if (!user) return;
          await getTdmsClient().restoreStudent(row.id, { reason, reasonDetail }, { actor: user });
          toast.success('Student record restored', {
            description: `${row.studentId} has been returned to active use.`,
          });
          await Promise.all([load(), loadDeleted()]);
        }}
      />
    </>
  );
}
