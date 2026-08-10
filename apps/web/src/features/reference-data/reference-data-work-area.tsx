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
import { DependentSelect, SimpleSelect } from '@/components/common/dependent-select';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState, PendingRuleNotice, ReadOnlyNotice } from '@/components/common/states';
import { CourseStatusBadge } from '@/components/common/status-badge';
import { ExportMenu } from '@/components/common/export-menu';
import { DeleteConfirmationDialog } from '@/components/common/delete-confirmation-dialog';
import { RecycleAreaDialog } from '@/components/common/recycle-area-dialog';
import { CourseFormDrawer } from './course-form-drawer';
import { QualificationUnitFormDialog } from './qualification-unit-form-dialog';
import { useReferenceData } from '@/features/shared/reference-data-context';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient } from '@/services';
import { INTERFACE_NAMES, SRS_PAGE_REFERENCE } from '@/lib/interface-names';
import { readOnlyReason } from '@/lib/permissions';
import { formatCurrency, today } from '@/lib/format';
import { COURSE_STATUS_OPTIONS } from '@/mock-data';
import type { ReasonCode } from '@/types/common';
import type { CourseRecord, QualificationUnitSequence } from '@/types/reference';
import type { CourseFilters, QualificationUnitFilters } from '@/services/tdms-client';

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
  const { data, campusesForCollege, collegeById, campusById } = useReferenceData();

  const [filters, setFilters] = React.useState<CourseFilters>({ search: initialSearch });
  const [rows, setRows] = React.useState<CourseRecord[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [formOpen, setFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<CourseRecord | null>(null);
  const [deleting, setDeleting] = React.useState<CourseRecord | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [recycleOpen, setRecycleOpen] = React.useState(false);
  const [deletedRows, setDeletedRows] = React.useState<CourseRecord[]>([]);
  const [recycleLoading, setRecycleLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setRows(await getTdmsClient().listCourses(filters));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const loadDeleted = React.useCallback(async () => {
    setRecycleLoading(true);
    try {
      setDeletedRows(await getTdmsClient().listDeletedCourses());
    } finally {
      setRecycleLoading(false);
    }
  }, []);

  const canMaintain = permissions.maintainCourseData;

  const columns: DataTableColumn<CourseRecord>[] = [
    {
      id: 'courseCode',
      header: 'Course Code',
      cell: (row) => <span className="font-medium text-foreground">{row.courseCode}</span>,
      sortValue: (row) => row.courseCode,
    },
    { id: 'vetCode', header: 'VET Code', cell: (row) => row.vetCode, sortValue: (row) => row.vetCode },
    {
      id: 'courseStatus',
      header: 'Course Status',
      cell: (row) => <CourseStatusBadge status={row.courseStatus} />,
      sortValue: (row) => row.courseStatus,
    },
    {
      id: 'courseName',
      header: 'Course Name',
      cell: (row) => (
        <span className="block max-w-80 truncate" title={row.courseName}>
          {row.courseName}
        </span>
      ),
      sortValue: (row) => row.courseName,
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
      cell: (row) => (
        <span className="block max-w-72 truncate" title={row.location}>
          {row.location}
        </span>
      ),
    },
  ];

  async function confirmDelete(reason: ReasonCode, reasonDetail?: string) {
    if (!deleting || !user) return;
    setBusy(true);
    try {
      await getTdmsClient().deleteCourse(deleting.id, { reason, reasonDetail }, { actor: user });
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
        onClear={() => setFilters({})}
        trailing={
          <>
            <ExportMenu
              rows={rows}
              baseFileName={`tdms-course-data-${today()}`}
              pageReference={SRS_PAGE_REFERENCE.courseData}
              columns={[
                { header: 'Course Code', value: (row) => row.courseCode },
                { header: 'VET Code', value: (row) => row.vetCode },
                { header: 'Course Status', value: (row) => row.courseStatus },
                { header: 'Course Name', value: (row) => row.courseName },
                { header: 'Course Level', value: (row) => row.courseLevel },
                { header: 'Field of Education - Broad', value: (row) => row.fieldOfEducationBroad },
                { header: 'Field of Education - Narrow', value: (row) => row.fieldOfEducationNarrow },
                { header: 'Course Sector', value: (row) => row.courseSector },
                { header: 'Duration in Weeks', value: (row) => row.durationInWeeks },
                { header: 'Total Course Cost', value: (row) => row.totalCourseCost },
                { header: 'Location', value: (row) => row.location },
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
          <DependentSelect
            id="course-filter-college"
            value={filters.collegeId ?? ''}
            onChange={(value) => setFilters((current) => ({ ...current, collegeId: value, campusId: '' }))}
            options={(data?.colleges ?? []).map((college) => ({ value: college.id, label: college.collegeFullName }))}
            placeholder="All colleges"
          />
        </FilterField>
        <FilterField label="Campus" htmlFor="course-filter-campus">
          <DependentSelect
            id="course-filter-campus"
            value={filters.campusId ?? ''}
            onChange={(value) => setFilters((current) => ({ ...current, campusId: value }))}
            options={campusesForCollege(filters.collegeId).map((campus) => ({
              value: campus.id,
              label: campus.campusName,
            }))}
            placeholder="All campuses"
            requires={filters.collegeId ? undefined : 'a college'}
          />
        </FilterField>
        <FilterField label="Course Status" htmlFor="course-filter-status">
          <SimpleSelect
            id="course-filter-status"
            value={filters.courseStatus ?? ''}
            onChange={(value) => setFilters((current) => ({ ...current, courseStatus: value }))}
            options={COURSE_STATUS_OPTIONS.map((status) => ({ value: status, label: status }))}
            placeholder="All statuses"
          />
        </FilterField>
        <FilterField label="Search" htmlFor="course-filter-search">
          <Input
            id="course-filter-search"
            value={filters.search ?? ''}
            onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
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
          <EmptyState
            title="No course matches the selected filters."
            description="Change the college, campus or status filter to see more records."
            icon={BookOpen}
          />
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
            secondary: deleting.courseName,
            lines: [`Current status: ${deleting.courseStatus}`, deleting.location],
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
          { id: 'courseName', header: 'Course Name', cell: (row) => row.courseName },
        ]}
        describe={(row) => ({ primary: row.courseCode, secondary: row.courseName, lines: [row.location] })}
        onRestore={async (row, reason, reasonDetail) => {
          if (!user) return;
          await getTdmsClient().restoreCourse(row.id, { reason, reasonDetail }, { actor: user });
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
  const { data, campusesForCollege, offeringsFor } = useReferenceData();

  const [filters, setFilters] = React.useState<QualificationUnitFilters>({});
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
    try {
      setRows(await getTdmsClient().listQualificationUnitSequences(filters));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const loadDeleted = React.useCallback(async () => {
    setRecycleLoading(true);
    try {
      setDeletedRows(await getTdmsClient().listDeletedQualificationUnits());
    } finally {
      setRecycleLoading(false);
    }
  }, []);

  const canMaintain = permissions.maintainQualificationUnitData;
  const offerings = offeringsFor(filters.collegeId, filters.campusId);

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
      id: 'sequenceId',
      header: 'Sequence ID',
      cell: (row) => row.sequenceId,
      sortValue: (row) => row.sequenceId,
      align: 'right',
    },
  ];

  async function confirmDelete(reason: ReasonCode, reasonDetail?: string) {
    if (!deleting || !user) return;
    setBusy(true);
    try {
      await getTdmsClient().deleteQualificationUnit(deleting.id, { reason, reasonDetail }, { actor: user });
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

      <PendingRuleNotice
        decisionId="OD-07"
        message="Sequence IDs are used by timetable generation to place units in the approved teaching order. The break placement rules for 26, 52, 78 and 104-week courses must be approved before automatic generation is released (TT-11)."
      />

      <FilterBar
        onClear={() => setFilters({})}
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
                { header: 'Sequence ID', value: (row) => row.sequenceId },
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
          <DependentSelect
            id="qus-filter-college"
            value={filters.collegeId ?? ''}
            onChange={(value) =>
              setFilters((current) => ({ ...current, collegeId: value, campusId: '', qualificationCode: '' }))
            }
            options={(data?.colleges ?? []).map((college) => ({ value: college.id, label: college.collegeFullName }))}
            placeholder="All colleges"
          />
        </FilterField>
        <FilterField label="Campus" htmlFor="qus-filter-campus">
          <DependentSelect
            id="qus-filter-campus"
            value={filters.campusId ?? ''}
            onChange={(value) => setFilters((current) => ({ ...current, campusId: value, qualificationCode: '' }))}
            options={campusesForCollege(filters.collegeId).map((campus) => ({
              value: campus.id,
              label: campus.campusName,
            }))}
            placeholder="All campuses"
            requires={filters.collegeId ? undefined : 'a college'}
          />
        </FilterField>
        <FilterField label="Qualification" htmlFor="qus-filter-qualification">
          <SimpleSelect
            id="qus-filter-qualification"
            value={filters.qualificationCode ?? ''}
            onChange={(value) => setFilters((current) => ({ ...current, qualificationCode: value }))}
            options={Array.from(
              new Map(
                (offerings.length > 0 ? offerings : (data?.qualificationOfferings ?? [])).map((entry) => [
                  entry.qualificationCode,
                  { value: entry.qualificationCode, label: `${entry.qualificationCode} — ${entry.qualificationTitle}` },
                ]),
              ).values(),
            )}
            placeholder="All qualifications"
          />
        </FilterField>
        <FilterField label="Search" htmlFor="qus-filter-search">
          <Input
            id="qus-filter-search"
            value={filters.search ?? ''}
            onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
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
          <EmptyState
            title="No qualification and unit sequence record matches the selected filters."
            description="Change the college, campus or qualification filter to see more records."
            icon={GraduationCap}
          />
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
            lines: [deleting.unitTitle, `Sequence ID: ${deleting.sequenceId}`],
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
          await getTdmsClient().restoreQualificationUnit(row.id, { reason, reasonDetail }, { actor: user });
          toast.success('Record restored', { description: `${row.recordId} has been returned to active use.` });
          await Promise.all([load(), loadDeleted()]);
        }}
      />
    </div>
  );
}
