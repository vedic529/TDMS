'use client';

import * as React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { BookOpen, GraduationCap, ListOrdered, Pencil, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PageHeader } from '@/components/common/page-header';
import { FilterBar, FilterField } from '@/components/common/filter-bar';
import { SimpleSelect } from '@/components/common/dependent-select';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState, ErrorState, PendingRuleNotice, ReadOnlyNotice } from '@/components/common/states';
import { CourseStatusBadge } from '@/components/common/status-badge';
import { ExportMenu } from '@/components/common/export-menu';
import { DeleteConfirmationDialog } from '@/components/common/delete-confirmation-dialog';
import { RecycleAreaDialog } from '@/components/common/recycle-area-dialog';
import { CourseFormDrawer } from './course-form-drawer';
import { QualificationUnitFormDialog } from './qualification-unit-form-dialog';
import { useReferenceLookups } from './use-reference-lookups';
import { useCascadingFilters } from './use-cascading-filters';
import { MultiSelectFilter } from '@/components/common/multi-select-filter';
import { useAuth } from '@/features/auth/auth-context';
import { ReferenceApiError, referenceApi } from '@/services/reference-api';
import type { SelectOption } from '@/types/common';
import { toCourseRecord, toQualificationUnit } from './reference-adapters';
import { INTERFACE_NAMES, SRS_PAGE_REFERENCE } from '@/lib/interface-names';
import { readOnlyReason } from '@/lib/permissions';
import { formatCurrency, today } from '@/lib/format';
import type { ReasonCode } from '@/types/common';
import type { CourseRecord, QualificationUnitSequence } from '@/types/reference';

type TabValue = 'course-data' | 'qualification-unit-sequence';

export function ReferenceDataWorkArea() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get('tab');
  const tab: TabValue = tabParam === 'qualification-unit-sequence' ? 'qualification-unit-sequence' : 'course-data';

  return (
    <div className="space-y-5">
      <PageHeader
        title={INTERFACE_NAMES.referenceData}
        description="Approved college, campus, course, qualification and unit information used by student and timetable records."
      />

      <Tabs
        value={tab}
        onValueChange={(next) => {
          const params = new URLSearchParams(searchParams.toString());
          params.set('tab', next);
          params.delete('search');
          router.replace(`/reference-data?${params.toString()}`, { scroll: false });
        }}
      >
        <TabsList>
          <TabsTrigger value="course-data">
            <BookOpen aria-hidden="true" />
            {INTERFACE_NAMES.courseData}
          </TabsTrigger>
          <TabsTrigger value="qualification-unit-sequence">
            <ListOrdered aria-hidden="true" />
            {INTERFACE_NAMES.qualificationUnitSequence}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="course-data">
          <CourseDataPanel initialSearch={searchParams.get('search') ?? ''} />
        </TabsContent>

        <TabsContent value="qualification-unit-sequence">
          <QualificationUnitPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ---------------------------------------------------------------- Course Data

function CourseDataPanel({ initialSearch }: { initialSearch: string }) {
  const { user, permissions } = useAuth();
  const { collegeById, campusById } = useReferenceLookups();
  const cascade = useCascadingFilters();

  const [search, setSearch] = React.useState(initialSearch);
  const [courseStatus, setCourseStatus] = React.useState('');
  const [rows, setRows] = React.useState<CourseRecord[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [formOpen, setFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<CourseRecord | null>(null);
  const [deleting, setDeleting] = React.useState<CourseRecord | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [recycleOpen, setRecycleOpen] = React.useState(false);
  const [deletedRows, setDeletedRows] = React.useState<CourseRecord[]>([]);
  const [recycleLoading, setRecycleLoading] = React.useState(false);

  const [loadError, setLoadError] = React.useState<string | null>(null);

  /**
   * Filter options come from `course_statuses`, not a constant.
   *
   * COL-05 is an open vocabulary, so a hard-coded list would go stale the moment
   * an approved status is added — and would offer the user a filter that matches
   * nothing. The value sent back is the status *code*; the label is what shows.
   */
  const [courseStatusOptions, setCourseStatusOptions] = React.useState<SelectOption[]>([]);
  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const statuses = await referenceApi.listCourseStatuses();
        if (!cancelled) {
          setCourseStatusOptions(
            statuses.map((status) => ({ value: status.code, label: status.label })),
          );
        }
      } catch {
        if (!cancelled) setCourseStatusOptions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * Real data only. There is deliberately no mock fallback: an empty database
   * must render an empty table, and a failure must say so rather than quietly
   * showing demo records that look real.
   */
  const load = React.useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    // Never leave rows from the previous scope on screen while the new ones load.
    setRows([]);
    try {
      const courses = await referenceApi.listCourses({
        search: search || undefined,
        // Scope is enforced in SQL over real offerings, so the table can never
        // show a row outside the current College/Campus/Qualification selection.
        collegeIds: cascade.scope.collegeIds,
        campusIds: cascade.scope.campusIds,
        qualificationIds: cascade.scope.qualificationIds,
        // Filtered against the stored status, so the filter and the badge can
        // never disagree about what a record's status is.
        courseStatusCode: courseStatus || undefined,
      });
      setRows(courses.map(toCourseRecord));
    } catch (error) {
      setRows([]);
      setLoadError(
        error instanceof ReferenceApiError
          ? error.message
          : 'Course records could not be loaded. Refresh the page or contact the TDMS administrator.',
      );
    } finally {
      setLoading(false);
    }
  }, [
    cascade.scope.collegeIds,
    cascade.scope.campusIds,
    cascade.scope.qualificationIds,
    courseStatus,
    search,
  ]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const loadDeleted = React.useCallback(async () => {
    setRecycleLoading(true);
    try {
      const deleted = await referenceApi.listCourses({ includeDeleted: true });
      setDeletedRows(deleted.map(toCourseRecord));
    } catch {
      setDeletedRows([]);
    } finally {
      setRecycleLoading(false);
    }
  }, []);

  const canMaintain = permissions.maintainReferenceData;
  const hasCourseFilters = Boolean(
    search ||
      courseStatus ||
      cascade.filters.collegeIds.length ||
      cascade.filters.campusIds.length ||
      cascade.filters.qualificationIds.length,
  );

  const columns: DataTableColumn<CourseRecord>[] = [
    {
      id: 'courseCode',
      header: 'Course Code',
      cell: (row) => <span className="font-medium text-foreground">{row.courseCode}</span>,
      sortValue: (row) => row.courseCode,
    },
    { id: 'qualificationCode', header: 'VET Code', cell: (row) => row.qualificationCode, sortValue: (row) => row.qualificationCode },
    {
      id: 'courseStatus',
      header: 'Course Status',
      cell: (row) => <CourseStatusBadge status={row.courseStatus} />,
      sortValue: (row) => row.courseStatus,
    },
    {
      id: 'qualificationTitle',
      header: 'Course Name',
      cell: (row) => (
        <span className="block max-w-80 truncate" title={row.qualificationTitle}>
          {row.qualificationTitle}
        </span>
      ),
      sortValue: (row) => row.qualificationTitle,
    },
    { id: 'courseLevel', header: 'Course Level', cell: (row) => row.courseLevel, sortValue: (row) => row.courseLevel },
    {
      id: 'foeBroad',
      header: 'Field of Education - Broad',
      cell: (row) => (
        <span className="block max-w-56 truncate" title={row.fieldOfEducationBroad}>
          {row.fieldOfEducationBroad}
        </span>
      ),
    },
    {
      id: 'foeNarrow',
      header: 'Field of Education - Narrow',
      cell: (row) => (
        <span className="block max-w-56 truncate" title={row.fieldOfEducationNarrow}>
          {row.fieldOfEducationNarrow}
        </span>
      ),
    },
    { id: 'courseSector', header: 'Course Sector', cell: (row) => row.courseSector },
    {
      id: 'duration',
      header: 'Duration in Weeks',
      cell: (row) => row.durationInWeeks,
      sortValue: (row) => row.durationInWeeks,
      align: 'right',
    },
    {
      id: 'cost',
      header: 'Total Course Cost',
      cell: (row) => formatCurrency(row.totalCourseCost),
      sortValue: (row) => row.totalCourseCost,
      align: 'right',
    },
    {
      id: 'location',
      header: 'Location',
      // C-3: SRS 8.2 - Location represents the Campus value, so it is derived
      // from the approved campus rather than stored as free text.
      cell: (row) => {
        const location = campusById(row.campusId)?.campusLocation ?? '';
        return (
          <span className="block max-w-72 truncate" title={location}>
            {location}
          </span>
        );
      },
    },
  ];

  async function confirmDelete(reason: ReasonCode, reasonDetail?: string) {
    if (!deleting || !user) return;
    setBusy(true);
    try {
      await referenceApi.deleteCourse(Number(deleting.id), { reason_detail: reasonDetail ?? reason });
      toast.success('Course moved to the recycle area', { description: `${deleting.courseCode} was removed from active use.` });
      setDeleting(null);
      await load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      {!canMaintain && <ReadOnlyNotice message={readOnlyReason(user, INTERFACE_NAMES.courseData)} />}

      <FilterBar
        onClear={() => {
          cascade.clear();
          setSearch('');
          setCourseStatus('');
        }}
        trailing={
          <>
            <ExportMenu
              rows={rows}
              baseFileName={`tdms-course-data-${today()}`}
              pageReference={SRS_PAGE_REFERENCE.courseData}
              columns={[
                { header: 'Course Code', value: (row) => row.courseCode },
                { header: 'VET Code', value: (row) => row.qualificationCode },
                { header: 'Course Status', value: (row) => row.courseStatus },
                { header: 'Course Name', value: (row) => row.qualificationTitle },
                { header: 'Course Level', value: (row) => row.courseLevel },
                { header: 'Field of Education - Broad', value: (row) => row.fieldOfEducationBroad },
                { header: 'Field of Education - Narrow', value: (row) => row.fieldOfEducationNarrow },
                { header: 'Course Sector', value: (row) => row.courseSector },
                { header: 'Duration in Weeks', value: (row) => row.durationInWeeks },
                { header: 'Total Course Cost', value: (row) => row.totalCourseCost },
                { header: 'Location', value: (row) => campusById(row.campusId)?.campusLocation ?? '' },
                { header: 'College', value: (row) => collegeById(row.collegeId)?.collegeFullName ?? '' },
                { header: 'Campus', value: (row) => campusById(row.campusId)?.campusName ?? '' },
              ]}
            />
            {canMaintain && (
              <>
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
                <Button
                  size="sm"
                  onClick={() => {
                    setEditing(null);
                    setFormOpen(true);
                  }}
                >
                  <Plus aria-hidden="true" />
                  Create Course
                </Button>
              </>
            )}
          </>
        }
      >
        <FilterField label="College" htmlFor="course-filter-college">
          <MultiSelectFilter
            id="course-filter-college"
            value={cascade.filters.collegeIds}
            onChange={cascade.setColleges}
            options={cascade.collegeOptions}
            allLabel="All Colleges"
            noun="College"
          />
        </FilterField>
        <FilterField label="Campus" htmlFor="course-filter-campus">
          <MultiSelectFilter
            id="course-filter-campus"
            value={cascade.filters.campusIds}
            onChange={cascade.setCampuses}
            options={cascade.campusOptions}
            allLabel="All Campuses"
            noun="Campus"
            loading={cascade.loadingCampuses}
          />
        </FilterField>
        <FilterField label="Qualification" htmlFor="course-filter-qualification">
          <MultiSelectFilter
            id="course-filter-qualification"
            value={cascade.filters.qualificationIds}
            onChange={cascade.setQualifications}
            options={cascade.qualificationOptions}
            allLabel="All Qualifications"
            noun="Qualification"
            loading={cascade.loadingQualifications}
            emptyMessage="No qualifications are offered for the selected College and Campus."
          />
        </FilterField>
        <FilterField label="Course Status" htmlFor="course-filter-status">
          <SimpleSelect
            id="course-filter-status"
            value={courseStatus}
            onChange={setCourseStatus}
            options={courseStatusOptions}
            placeholder="All statuses"
          />
        </FilterField>
        <FilterField label="Search" htmlFor="course-filter-search">
          <Input
            id="course-filter-search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Course code or name"
          />
        </FilterField>
      </FilterBar>

      <DataTable
        ariaLabel="Course data"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        loading={loading}
        loadingLabel="Loading course data…"
        initialSort={{ columnId: 'courseCode', direction: 'asc' }}
        empty={
          loadError ? (
            <ErrorState title="Course records could not be loaded" description={loadError} />
          ) : hasCourseFilters ? (
            <EmptyState
              title="No course matches the selected filters."
              description="Change the college, campus or search filter to see more records."
              icon={BookOpen}
            />
          ) : (
            <EmptyState
              title="No course records have been added yet."
              description={
                canMaintain
                  ? 'Select Add Course Record to enter the first approved course.'
                  : 'No approved course records are currently available.'
              }
              icon={BookOpen}
            />
          )
        }
        rowActions={
          canMaintain
            ? (row) => (
                <div className="flex justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Edit ${row.courseCode}`}
                    onClick={() => {
                      setEditing(row);
                      setFormOpen(true);
                    }}
                  >
                    <Pencil aria-hidden="true" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Delete ${row.courseCode}`}
                    onClick={() => setDeleting(row)}
                  >
                    <Trash2 aria-hidden="true" />
                  </Button>
                </div>
              )
            : undefined
        }
      />

      <CourseFormDrawer
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditing(null);
        }}
        editing={editing}
        existingCourses={rows}
        onSaved={() => void load()}
      />

      {deleting && (
        <DeleteConfirmationDialog
          open
          onOpenChange={(open) => !open && setDeleting(null)}
          recordTypeLabel="Course Record"
          reasonContext="course"
          busy={busy}
          record={{
            primary: deleting.courseCode,
            secondary: deleting.qualificationTitle,
            lines: [
              `Current status: ${deleting.courseStatus}`,
              campusById(deleting.campusId)?.campusLocation ?? '',
            ],
          }}
          onConfirm={confirmDelete}
        />
      )}

      <RecycleAreaDialog
        open={recycleOpen}
        onOpenChange={setRecycleOpen}
        title="Deleted course records"
        recordTypeLabel="Course Record"
        reasonContext="course"
        rows={deletedRows}
        loading={recycleLoading}
        rowKey={(row) => row.id}
        canRestore={canMaintain}
        columns={[
          { id: 'courseCode', header: 'Course Code', cell: (row) => row.courseCode, sortValue: (row) => row.courseCode },
          { id: 'qualificationTitle', header: 'Course Name', cell: (row) => row.qualificationTitle },
        ]}
        describe={(row) => ({
          primary: row.courseCode,
          secondary: row.qualificationTitle,
          lines: [campusById(row.campusId)?.campusLocation ?? ''],
        })}
        onRestore={async (row, reason, reasonDetail) => {
          if (!user) return;
          await referenceApi.restoreCourse(Number(row.id), { reason_detail: reasonDetail ?? reason });
          toast.success('Course restored', { description: `${row.courseCode} has been returned to active use.` });
          await Promise.all([load(), loadDeleted()]);
        }}
      />
    </div>
  );
}

// ------------------------------------------- Qualification and Unit Sequence

function QualificationUnitPanel() {
  const { user, permissions } = useAuth();
  const cascade = useCascadingFilters();

  const [search, setSearch] = React.useState('');
  const [rows, setRows] = React.useState<QualificationUnitSequence[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [formOpen, setFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<QualificationUnitSequence | null>(null);
  const [deleting, setDeleting] = React.useState<QualificationUnitSequence | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [recycleOpen, setRecycleOpen] = React.useState(false);
  const [deletedRows, setDeletedRows] = React.useState<QualificationUnitSequence[]>([]);
  const [recycleLoading, setRecycleLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    // Clear first: a table still showing AIBT's BSB50420 under a heading that
    // now says HJ is worse than an empty table, because it looks like an answer.
    setRows([]);
    try {
      const sequence = await referenceApi.listQualificationUnits({
        // Sent to the API rather than filtered here: the scope is a relational
        // question about which qualifications are offered where, and the browser
        // does not hold the offerings to answer it.
        collegeIds: cascade.scope.collegeIds,
        campusIds: cascade.scope.campusIds,
        qualificationIds: cascade.scope.qualificationIds,
        search: search || undefined,
      });
      setRows(sequence.map((row) => toQualificationUnit(row)));
    } finally {
      setLoading(false);
    }
  }, [cascade.scope.collegeIds, cascade.scope.campusIds, cascade.scope.qualificationIds, search]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const loadDeleted = React.useCallback(async () => {
    setRecycleLoading(true);
    try {
      const deleted = await referenceApi.listQualificationUnits({ includeDeleted: true });
      setDeletedRows(deleted.map((row) => toQualificationUnit(row)));
    } finally {
      setRecycleLoading(false);
    }
  }, []);

  const canMaintain = permissions.maintainReferenceData;


  /**
   * Which OD-07 message applies to what the user is currently looking at.
   *
   * Membership and order are different things: Qualification Data establishes
   * which units belong to a qualification; an approved rolling timetable
   * establishes the order they run in. Only the second can be pending, and only
   * for some qualifications — so a page-wide banner was wrong in both
   * directions, claiming BSB50420's sequence was unapproved while saying
   * nothing specific about the ones that genuinely are.
   */
  const selectedQualification = React.useMemo(() => {
    if (cascade.filters.qualificationIds.length !== 1) return '';
    const option = cascade.qualificationOptions.find(
      (o) => o.value === cascade.filters.qualificationIds[0],
    );
    return option ? option.label.split(' — ')[0] : '';
  }, [cascade.filters.qualificationIds, cascade.qualificationOptions]);
  const sequenceState: 'unfiltered' | 'approved' | 'pending' = !selectedQualification
    ? 'unfiltered'
    : !loading && rows.length === 0
      ? 'pending'
      : 'approved';


  const columns: DataTableColumn<QualificationUnitSequence>[] = [
    { id: 'recordId', header: 'Record ID', cell: (row) => row.recordId, sortValue: (row) => row.recordId },
    {
      id: 'qualificationCode',
      header: 'Qualification Code',
      cell: (row) => <span className="font-medium text-foreground">{row.qualificationCode}</span>,
      sortValue: (row) => row.qualificationCode,
    },
    {
      id: 'qualificationTitle',
      header: 'Qualification Title',
      cell: (row) => (
        <span className="block max-w-72 truncate" title={row.qualificationTitle}>
          {row.qualificationTitle}
        </span>
      ),
    },
    { id: 'unitCode', header: 'Unit Code', cell: (row) => row.unitCode, sortValue: (row) => row.unitCode },
    {
      id: 'unitTitle',
      header: 'Unit Title',
      cell: (row) => (
        <span className="block max-w-80 truncate" title={row.unitTitle}>
          {row.unitTitle}
        </span>
      ),
    },
    {
      id: 'deliveryOrder',
      header: 'Sequence ID',
      cell: (row) => row.deliveryOrder,
      sortValue: (row) => row.deliveryOrder,
      align: 'right',
    },
  ];

  async function confirmDelete(reason: ReasonCode, reasonDetail?: string) {
    if (!deleting || !user) return;
    setBusy(true);
    try {
      await referenceApi.deleteQualificationUnit(Number(deleting.id), { reason_detail: reasonDetail ?? reason });
      toast.success('Record moved to the recycle area', { description: `${deleting.recordId} was removed from active use.` });
      setDeleting(null);
      await load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      {!canMaintain && <ReadOnlyNotice message={readOnlyReason(user, INTERFACE_NAMES.qualificationUnitSequence)} />}

      {/*
        OD-07 is shown for the qualification actually being looked at, not
        across the whole page.

        A blanket banner said "sequence is pending" even for a qualification
        whose delivery order comes from an approved rolling timetable, and said
        nothing more specific for one where it genuinely is missing. Both
        readings were wrong. The notice now names the situation in front of the
        user; TT-11 break placement remains unapproved either way and is stated
        separately.
      */}
      {sequenceState === 'pending' ? (
        <PendingRuleNotice
          decisionId="OD-07"
          message={`No approved delivery sequence has been supplied for ${selectedQualification}. Its unit membership comes from Qualification Data; the teaching order comes from an approved rolling timetable, which this qualification does not yet have. Break placement for 26, 52, 78 and 104-week courses is also still awaiting approval (TT-11).`}
        />
      ) : sequenceState === 'approved' ? (
        <PendingRuleNotice
          decisionId="TT-11"
          message={`The delivery sequence shown for ${selectedQualification} comes from its approved rolling timetable. Break placement rules for 26, 52, 78 and 104-week courses are still awaiting approval before automatic generation is released.`}
        />
      ) : (
        <PendingRuleNotice
          decisionId="OD-07"
          message="A delivery sequence is stored only for qualifications with an approved rolling timetable; select a qualification to see whether its order has been supplied. Break placement for 26, 52, 78 and 104-week courses is still awaiting approval before automatic generation is released (TT-11)."
        />
      )}

      <FilterBar
        onClear={() => {
          cascade.clear();
          setSearch('');
        }}
        trailing={
          <>
            <ExportMenu
              rows={rows}
              baseFileName={`tdms-qualification-unit-sequence-${today()}`}
              pageReference={SRS_PAGE_REFERENCE.qualificationUnitSequence}
              columns={[
                { header: 'Record ID', value: (row) => row.recordId },
                { header: 'Qualification Code', value: (row) => row.qualificationCode },
                { header: 'Qualification Title', value: (row) => row.qualificationTitle },
                { header: 'Unit Code', value: (row) => row.unitCode },
                { header: 'Unit Title', value: (row) => row.unitTitle },
                { header: 'Sequence ID', value: (row) => row.deliveryOrder },
                { header: 'UoC Type', value: (row) => row.uocType },
              ]}
            />
            {canMaintain && (
              <>
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
                <Button
                  size="sm"
                  onClick={() => {
                    setEditing(null);
                    setFormOpen(true);
                  }}
                >
                  <Plus aria-hidden="true" />
                  Create Record
                </Button>
              </>
            )}
          </>
        }
      >
        <FilterField label="College" htmlFor="qus-filter-college">
          <MultiSelectFilter
            id="qus-filter-college"
            value={cascade.filters.collegeIds}
            onChange={cascade.setColleges}
            options={cascade.collegeOptions}
            allLabel="All Colleges"
            noun="College"
          />
        </FilterField>
        <FilterField label="Campus" htmlFor="qus-filter-campus">
          <MultiSelectFilter
            id="qus-filter-campus"
            value={cascade.filters.campusIds}
            onChange={cascade.setCampuses}
            options={cascade.campusOptions}
            allLabel="All Campuses"
            noun="Campus"
            loading={cascade.loadingCampuses}
          />
        </FilterField>
        <FilterField label="Qualification" htmlFor="qus-filter-qualification">
          <MultiSelectFilter
            id="qus-filter-qualification"
            value={cascade.filters.qualificationIds}
            onChange={cascade.setQualifications}
            options={cascade.qualificationOptions}
            allLabel="All Qualifications"
            noun="Qualification"
            loading={cascade.loadingQualifications}
            emptyMessage="No qualifications are offered for the selected College and Campus."
          />
        </FilterField>
        <FilterField label="Search" htmlFor="qus-filter-search">
          <Input
            id="qus-filter-search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Unit code or title"
          />
        </FilterField>
      </FilterBar>

      <DataTable
        ariaLabel="Qualification and unit sequence data"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        loading={loading}
        loadingLabel="Loading qualification and unit sequence data…"
        pageSize={20}
        empty={
          cascade.qualificationOptions.length === 0 ? (
            <EmptyState
              title="No qualifications are offered for the selected College and Campus."
              description="Choose a different College or Campus to see the qualifications delivered there."
              icon={GraduationCap}
            />
          ) : selectedQualification ? (
            // The qualification is genuinely offered; its unit data has simply
            // not been supplied yet. Saying "nothing has been added" would read
            // as though the qualification did not exist.
            <EmptyState
              title={`No Qualification Unit data has been supplied for ${selectedQualification}.`}
              description="The qualification is offered at the selected College and Campus. Its unit membership has not been supplied yet."
              icon={GraduationCap}
            />
          ) : search ? (
            <EmptyState
              title="No records match the current filters."
              description="Change the search term to see more records."
              icon={GraduationCap}
            />
          ) : (
            <EmptyState
              title="No qualification and unit sequence has been added yet."
              description={
                canMaintain
                  ? 'Select Add Unit to Sequence to record the first approved unit.'
                  : 'No approved qualification and unit sequence records are currently available.'
              }
              icon={GraduationCap}
            />
          )
        }
        rowActions={
          canMaintain
            ? (row) => (
                <div className="flex justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Edit ${row.recordId}`}
                    onClick={() => {
                      setEditing(row);
                      setFormOpen(true);
                    }}
                  >
                    <Pencil aria-hidden="true" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Delete ${row.recordId}`}
                    onClick={() => setDeleting(row)}
                  >
                    <Trash2 aria-hidden="true" />
                  </Button>
                </div>
              )
            : undefined
        }
      />

      <QualificationUnitFormDialog
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditing(null);
        }}
        editing={editing}
        existingRecords={rows}
        onSaved={() => void load()}
      />

      {deleting && (
        <DeleteConfirmationDialog
          open
          onOpenChange={(open) => !open && setDeleting(null)}
          recordTypeLabel="Qualification and Unit Sequence Record"
          reasonContext="qualificationUnit"
          busy={busy}
          record={{
            primary: deleting.recordId,
            secondary: `${deleting.qualificationCode} · ${deleting.unitCode}`,
            lines: [deleting.unitTitle, `Sequence ID: ${deleting.deliveryOrder}`],
          }}
          onConfirm={confirmDelete}
        />
      )}

      <RecycleAreaDialog
        open={recycleOpen}
        onOpenChange={setRecycleOpen}
        title="Deleted qualification and unit sequence records"
        recordTypeLabel="Qualification and Unit Sequence Record"
        reasonContext="qualificationUnit"
        rows={deletedRows}
        loading={recycleLoading}
        rowKey={(row) => row.id}
        canRestore={canMaintain}
        columns={[
          { id: 'recordId', header: 'Record ID', cell: (row) => row.recordId, sortValue: (row) => row.recordId },
          { id: 'qualification', header: 'Qualification', cell: (row) => row.qualificationCode },
          { id: 'unit', header: 'Unit', cell: (row) => row.unitCode },
        ]}
        describe={(row) => ({
          primary: row.recordId,
          secondary: `${row.qualificationCode} · ${row.unitCode}`,
          lines: [row.unitTitle],
        })}
        onRestore={async (row, reason, reasonDetail) => {
          if (!user) return;
          await referenceApi.restoreQualificationUnit(Number(row.id), { reason_detail: reasonDetail ?? reason });
          toast.success('Record restored', { description: `${row.recordId} has been returned to active use.` });
          await Promise.all([load(), loadDeleted()]);
        }}
      />
    </div>
  );
}
