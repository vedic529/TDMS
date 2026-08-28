'use client';

import * as React from 'react';
import { FilePlus2, Search, Trash2, Users } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { FilterField } from '@/components/common/filter-bar';
import { EmptyState, ErrorState } from '@/components/common/states';
import { ExportMenu } from '@/components/common/export-menu';
import { RecycleAreaDialog } from '@/components/common/recycle-area-dialog';
import { useReferenceData } from '@/features/shared/reference-data-context';
import { useCascadingFilters } from '@/features/reference-data/use-cascading-filters';
import { MultiSelectFilter } from '@/components/common/multi-select-filter';
import { useAuth } from '@/features/auth/auth-context';
import { StudentDetailPanel } from './student-detail-panel';
import { SingleStudentEntry } from './single-student-entry';
import { studentsApi, STUDENTS_EMPTY_DESCRIPTION, STUDENTS_EMPTY_TITLE, type StudentRecord } from '@/services/students-api';
import { SRS_PAGE_REFERENCE } from '@/lib/interface-names';
import { formatDate, today } from '@/lib/format';
import type { ReasonCode, SoftDeletable } from '@/types/common';

/** One page of records. Each page is fetched from the API as it is opened. */
const PAGE_SIZE = 10;

/**
 * A deleted student in the shape the shared recycle dialog expects.
 *
 * The dialog is written against `SoftDeletable`, so the API's flat deletion
 * columns are folded into the approved `deletion` block rather than the dialog
 * being loosened to accept two shapes (DATA-04).
 */
type DeletedStudent = StudentRecord & SoftDeletable;

function toDeletedStudent(row: StudentRecord): DeletedStudent {
  return {
    ...row,
    isDeleted: true,
    deletion: row.deleted_at
      ? {
          deletedAt: row.deleted_at,
          deletedBy: row.deleted_by ?? 'Unknown user',
          deleteReason: (row.delete_reason ?? 'OTHER') as ReasonCode,
          deleteReasonDetail: row.delete_reason_detail ?? undefined,
          recoveryDeadline: row.recovery_deadline ?? '',
        }
      : undefined,
  };
}

/**
 * The intake as it should read on screen.
 *
 * A Credit Transfer student genuinely has no intake, and a qualification whose
 * rolling timetable has not been supplied has none *yet* — those are different
 * facts, so they are shown differently rather than both as an em dash.
 */
function intakeLabel(row: StudentRecord): string {
  if (row.intake_match_status === 'NOT_APPLICABLE') return 'N/A';
  if (row.intake_label) return row.intake_label;
  return 'TBD';
}

/**
 * Student records list — read from the TDMS database.
 *
 * Every approved user may view and download student information (SRS 3.4), so
 * this panel is available to all access levels. Maintaining a record still
 * requires Data Editor access or above.
 */
export function StudentRecordsPanel({ initialStudentId }: { initialStudentId?: string } = {}) {
  const { permissions } = useAuth();
  const { collegeById, campusById } = useReferenceData();
  const cascade = useCascadingFilters();

  const [search, setSearch] = React.useState('');
  const [rows, setRows] = React.useState<StudentRecord[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  // The record open in the side panel, and the record open in the form popup.
  const [selected, setSelected] = React.useState<StudentRecord | null>(null);
  const [detailOpen, setDetailOpen] = React.useState(false);
  const [formOpen, setFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<StudentRecord | null>(null);

  const [recycleOpen, setRecycleOpen] = React.useState(false);
  const [deletedRows, setDeletedRows] = React.useState<DeletedStudent[]>([]);
  const [recycleLoading, setRecycleLoading] = React.useState(false);

  // The cascade selects ids; the API returns approved names. Resolving the ids
  // to names once here keeps the comparison honest without a second request.
  const selectedColleges = React.useMemo(
    () => new Set(cascade.filters.collegeIds.map((id) => collegeById(id)?.collegeShortName).filter(Boolean) as string[]),
    [cascade.filters.collegeIds, collegeById],
  );
  const selectedCampuses = React.useMemo(
    () => new Set(cascade.filters.campusIds.map((id) => campusById(id)?.campusName).filter(Boolean) as string[]),
    [cascade.filters.campusIds, campusById],
  );
  const selectedQualifications = React.useMemo(
    () =>
      new Set(
        cascade.qualificationOptions
          .filter((option) => cascade.filters.qualificationIds.includes(option.value))
          .map((option) => option.label.split(' — ')[0]),
      ),
    [cascade.qualificationOptions, cascade.filters.qualificationIds],
  );

  /**
   * Fetch exactly one page.
   *
   * The API orders newest first and applies the search, so only ten records
   * cross the wire however many the database holds. The College, Campus and
   * Qualification filters are passed as single ids when exactly one is chosen —
   * a multi-select cannot be expressed as one id, so a wider selection is
   * narrowed in the page that came back.
   */
  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await studentsApi.list({
        search: search || undefined,
        college_id: cascade.filters.collegeIds.length === 1 ? Number(cascade.filters.collegeIds[0]) : undefined,
        campus_id: cascade.filters.campusIds.length === 1 ? Number(cascade.filters.campusIds[0]) : undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setTotal(result.total);
      // An empty set means "no restriction at that level" — the Select All
      // contract — not "match nothing".
      setRows(
        result.items.filter(
          (student) =>
            (selectedColleges.size === 0 || selectedColleges.has(student.college)) &&
            (selectedCampuses.size === 0 || selectedCampuses.has(student.campus)) &&
            (selectedQualifications.size === 0 || selectedQualifications.has(student.qualification_code)),
        ),
      );
    } catch (caught) {
      setRows([]);
      setTotal(0);
      setError(caught instanceof Error ? caught.message : 'Student records could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [
    search,
    page,
    cascade.filters.collegeIds,
    cascade.filters.campusIds,
    selectedColleges,
    selectedCampuses,
    selectedQualifications,
  ]);

  React.useEffect(() => {
    const timer = setTimeout(() => void load(), 200);
    return () => clearTimeout(timer);
  }, [load]);

  // A changed search or filter invalidates the page number: page 4 of the old
  // result set is not page 4 of the new one.
  React.useEffect(() => {
    setPage(0);
  }, [search, cascade.filters.collegeIds, cascade.filters.campusIds, cascade.filters.qualificationIds]);

  function openDetail(student: StudentRecord) {
    setSelected(student);
    setDetailOpen(true);
  }

  // Arriving from Quick Find with a Student ID: search for it, and open the
  // record in the side panel once it is on screen.
  const deepLinked = React.useRef(false);
  React.useEffect(() => {
    if (initialStudentId && !deepLinked.current) {
      deepLinked.current = true;
      setSearch(initialStudentId);
    }
  }, [initialStudentId]);

  React.useEffect(() => {
    if (!initialStudentId || detailOpen || selected) return;
    const match = rows.find((row) => row.student_id.toUpperCase() === initialStudentId.toUpperCase());
    if (match) openDetail(match);
    // `rows` is the trigger: the record can only be opened once it has loaded.
  }, [rows, initialStudentId, detailOpen, selected]);

  function startCreate() {
    setEditing(null);
    setFormOpen(true);
  }

  function startEdit(student: StudentRecord) {
    setDetailOpen(false);
    setEditing(student);
    setFormOpen(true);
  }

  const loadDeleted = React.useCallback(async () => {
    setRecycleLoading(true);
    try {
      setDeletedRows((await studentsApi.listDeleted()).items.map(toDeletedStudent));
    } finally {
      setRecycleLoading(false);
    }
  }, []);

  const columns: DataTableColumn<StudentRecord>[] = [
    {
      id: 'studentId',
      header: 'Student ID',
      cell: (row) => <span className="font-medium text-foreground">{row.student_id}</span>,
      sortValue: (row) => row.student_id,
    },
    {
      id: 'name',
      header: 'Student',
      cell: (row) => `${row.first_name} ${row.last_name ?? ''}`.trim(),
      sortValue: (row) => `${row.last_name ?? ''} ${row.first_name}`,
    },
    {
      id: 'qualification',
      header: 'Qualification',
      cell: (row) => (
        <span className="block max-w-72">
          <span className="block font-medium text-foreground">{row.qualification_code}</span>
          <span className="block truncate text-[12px] text-muted-foreground">{row.qualification_title}</span>
        </span>
      ),
      sortValue: (row) => row.qualification_code,
    },
    { id: 'group', header: 'Group', cell: (row) => row.group_code || '—', sortValue: (row) => row.group_code ?? '' },
    {
      id: 'intake',
      header: 'Intake',
      cell: (row) => {
        const label = intakeLabel(row);
        if (label === 'TBD') return <Badge variant="warning">TBD</Badge>;
        return <span className="text-[12px]">{label}</span>;
      },
      sortValue: (row) => row.intake_label ?? '',
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <Badge variant={row.status === 'ACTIVE' ? 'success' : 'neutral'}>{row.status.replace(/_/g, ' ')}</Badge>
      ),
      sortValue: (row) => row.status,
    },
    { id: 'campus', header: 'Campus', cell: (row) => row.campus, sortValue: (row) => row.campus },
    {
      id: 'coe',
      header: 'CoE',
      cell: (row) => (
        <Badge variant={row.coe_status === 'COE' ? 'neutral' : 'outline'}>
          {row.coe_status === 'COE' ? 'CoE' : 'Non-CoE'}
        </Badge>
      ),
      sortValue: (row) => row.coe_status,
    },
    {
      id: 'dates',
      header: 'Proposed dates',
      cell: (row) => (
        <span className="whitespace-nowrap tabular">
          {formatDate(row.proposed_start_date)} – {formatDate(row.proposed_end_date)}
        </span>
      ),
      sortValue: (row) => row.proposed_start_date,
    },
  ];

  return (
    <>
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            {/* One compact search, and one action. */}
            <div className="relative w-full max-w-sm">
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                id="student-list-search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search Student ID, name or email"
                aria-label="Search student records"
                className="h-9 pl-9"
              />
            </div>
            <span className="whitespace-nowrap text-[12px] text-muted-foreground tabular">
              {total} {total === 1 ? 'record' : 'records'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {permissions.maintainStudentData && (
              <Button size="sm" onClick={startCreate}>
                <FilePlus2 aria-hidden="true" />
                Create New Student
              </Button>
            )}
            <ExportMenu
              rows={rows}
              baseFileName={`tdms-students-${today()}`}
              pageReference={SRS_PAGE_REFERENCE.singleStudentEntry}
              columns={[
                { header: 'Group', value: (row) => row.group_code ?? '' },
                { header: 'Intake', value: (row) => intakeLabel(row) },
                { header: 'College', value: (row) => row.college },
                { header: 'Campus', value: (row) => row.campus },
                { header: 'College Email', value: (row) => row.college_email },
                { header: 'First Name', value: (row) => row.first_name },
                { header: 'Last Name', value: (row) => row.last_name ?? '' },
                { header: 'Student ID', value: (row) => row.student_id },
                { header: 'Status', value: (row) => row.status },
                { header: 'CoE / Non-CoE', value: (row) => (row.coe_status === 'COE' ? 'CoE' : 'Non-CoE') },
                { header: 'Proposed Start Date', value: (row) => row.proposed_start_date },
                { header: 'Proposed End Date', value: (row) => row.proposed_end_date },
                { header: 'Actual Course Duration', value: (row) => row.actual_course_duration_weeks },
                { header: 'Qualification Title', value: (row) => row.qualification_title },
                { header: 'Qualification Code', value: (row) => row.qualification_code },
                { header: 'CT Student', value: (row) => (row.ct_student ? 'Yes' : 'No') },
                { header: 'Personal Email', value: (row) => row.personal_email ?? '' },
                { header: 'Primary Phone', value: (row) => row.primary_phone ?? '' },
                { header: 'State', value: (row) => row.state ?? '' },
                { header: 'Remarks', value: (row) => row.remarks ?? '' },
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
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
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

          {error ? (
            <ErrorState title="Student records could not be loaded" description={error} />
          ) : (
            <DataTable
              ariaLabel="Student records"
              columns={columns}
              rows={rows}
              rowKey={(row) => String(row.id)}
              loading={loading}
              loadingLabel="Loading student records…"
              // Ten at a time, fetched from the API as each page is opened, so
              // the newest record is always first (list order is id descending).
              serverPagination={{ page, pageSize: PAGE_SIZE, total, onPageChange: setPage }}
              activeRowKey={selected ? String(selected.id) : undefined}
              onRowClick={openDetail}
              empty={
                <EmptyState
                  title={total === 0 ? STUDENTS_EMPTY_TITLE : 'No student record matches the selected filters.'}
                  description={
                    total === 0 ? STUDENTS_EMPTY_DESCRIPTION : 'Change or clear a filter to see more records.'
                  }
                  icon={Users}
                />
              }
            />
          )}
        </CardContent>
      </Card>

      {/* The record opens beside the list, not in place of it. */}
      <StudentDetailPanel
        student={selected}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        canMaintain={permissions.maintainStudentData}
        onEdit={startEdit}
        onDelete={startEdit}
      />

      {/* Create and edit both happen in the popup form. */}
      <SingleStudentEntry
        open={formOpen}
        onOpenChange={setFormOpen}
        student={editing}
        onSaved={() => {
          setSelected(null);
          void load();
        }}
      />

      <RecycleAreaDialog
        open={recycleOpen}
        onOpenChange={setRecycleOpen}
        title="Deleted student records"
        recordTypeLabel="Student Record"
        reasonContext="student"
        rows={deletedRows}
        loading={recycleLoading}
        rowKey={(row) => String(row.id)}
        canRestore={permissions.maintainStudentData}
        columns={[
          {
            id: 'studentId',
            header: 'Student ID',
            cell: (row) => row.student_id,
            sortValue: (row) => row.student_id,
          },
          { id: 'name', header: 'Student', cell: (row) => `${row.first_name} ${row.last_name ?? ''}`.trim() },
          { id: 'qualification', header: 'Qualification', cell: (row) => row.qualification_code },
        ]}
        describe={(row) => ({
          primary: row.student_id,
          secondary: `${row.first_name} ${row.last_name ?? ''}`.trim(),
          lines: [`${row.qualification_code} — ${row.qualification_title}`],
        })}
        onRestore={async (row) => {
          await studentsApi.restore(row.id);
          toast.success('Student record restored', {
            description: `${row.student_id} has been returned to active use.`,
          });
          await Promise.all([load(), loadDeleted()]);
        }}
      />
    </>
  );
}
