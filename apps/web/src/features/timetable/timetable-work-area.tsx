'use client';

import * as React from 'react';
import { CalendarDays, CalendarRange, Plus, Rows3, Trash2, Wand2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { PageHeader } from '@/components/common/page-header';
import { FilterBar, FilterField } from '@/components/common/filter-bar';
import { DependentSelect, SimpleSelect } from '@/components/common/dependent-select';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState, ErrorState, ReadOnlyNotice } from '@/components/common/states';
import { ExportMenu } from '@/components/common/export-menu';
import { DeleteConfirmationDialog } from '@/components/common/delete-confirmation-dialog';
import { RecycleAreaDialog } from '@/components/common/recycle-area-dialog';
import { TimetableCalendar } from './timetable-calendar';
import { TimetableDetailDrawer } from './timetable-detail-drawer';
import { TimetableFormDrawer } from './timetable-form-drawer';
import { useReferenceData } from '@/features/shared/reference-data-context';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient } from '@/services';
import { INTERFACE_NAMES, SRS_PAGE_REFERENCE } from '@/lib/interface-names';
import { readOnlyReason } from '@/lib/permissions';
import { addDays, formatDate, formatSlots, today } from '@/lib/format';
import type { ReasonCode } from '@/types/common';
import type { TimetableFilters, TimetableSession } from '@/types/timetable';

type ViewMode = 'table' | 'calendar';

function defaultFilters(): TimetableFilters {
  const from = addDays(today(), -14);
  return { fromDate: from, toDate: addDays(from, 70) };
}

export function TimetableWorkArea() {
  const { user, permissions } = useAuth();
  const { data, campusesForCollege, offeringsFor, collegeById, campusById } = useReferenceData();

  const [filters, setFilters] = React.useState<TimetableFilters>(defaultFilters);
  const [sessions, setSessions] = React.useState<TimetableSession[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [view, setView] = React.useState<ViewMode>('table');

  const [formMode, setFormMode] = React.useState<'create' | 'generate' | 'edit' | null>(null);
  const [editing, setEditing] = React.useState<TimetableSession | null>(null);
  const [selected, setSelected] = React.useState<TimetableSession | null>(null);
  const [deleting, setDeleting] = React.useState<TimetableSession | null>(null);
  const [deleteBusy, setDeleteBusy] = React.useState(false);

  const [recycleOpen, setRecycleOpen] = React.useState(false);
  const [deletedRows, setDeletedRows] = React.useState<TimetableSession[]>([]);
  const [recycleLoading, setRecycleLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSessions(await getTdmsClient().listTimetableSessions(filters));
    } catch {
      setError('Timetable records could not be loaded. Refresh the page or contact the TDMS administrator.');
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
      setDeletedRows(await getTdmsClient().listDeletedTimetableSessions());
    } finally {
      setRecycleLoading(false);
    }
  }, []);

  const campuses = campusesForCollege(filters.collegeId);
  const offerings = offeringsFor(filters.collegeId, filters.campusId);

  const trainerName = React.useCallback(
    (trainerId: string) =>
      trainerId ? (data?.trainers.find((entry) => entry.trainerId === trainerId)?.trainerName ?? trainerId) : '—',
    [data],
  );

  const columns: DataTableColumn<TimetableSession>[] = [
    {
      id: 'recordNumber',
      header: 'Record',
      cell: (row) => <span className="font-medium text-foreground">{row.recordNumber}</span>,
      sortValue: (row) => row.recordNumber,
    },
    {
      id: 'qualification',
      header: 'Qualification',
      cell: (row) => (
        <span className="block max-w-64">
          <span className="block font-medium text-foreground">{row.qualificationCode}</span>
          <span className="block truncate text-[12px] text-muted-foreground">{row.qualificationName}</span>
        </span>
      ),
      sortValue: (row) => row.qualificationCode,
    },
    {
      id: 'unit',
      header: 'Unit',
      cell: (row) => (
        <span className="block max-w-64">
          <span className="block font-medium text-foreground">{row.uocCode}</span>
          <span className="block truncate text-[12px] text-muted-foreground">{row.uocTitle}</span>
        </span>
      ),
      sortValue: (row) => row.uocCode,
    },
    { id: 'group', header: 'Group', cell: (row) => row.group, sortValue: (row) => row.group },
    {
      id: 'trainer',
      header: 'Trainer',
      cell: (row) => (
        <span className="block max-w-48 truncate" title={trainerName(row.theoryTrainerId)}>
          {trainerName(row.theoryTrainerId)}
        </span>
      ),
      sortValue: (row) => row.theoryTrainerId,
    },
    {
      id: 'facility',
      header: 'Facility',
      cell: (row) => (
        <span>
          {row.theoryClassroomName || '—'}
          {row.practicalClassroomName ? ` / ${row.practicalClassroomName}` : ''}
        </span>
      ),
      sortValue: (row) => row.theoryClassroomName,
    },
    {
      id: 'dates',
      header: 'Start / End',
      cell: (row) => (
        <span className="whitespace-nowrap tabular">
          {formatDate(row.uocStartDate)} – {formatDate(row.uocEndDate)}
        </span>
      ),
      sortValue: (row) => row.uocStartDate,
    },
    {
      id: 'mode',
      header: 'Delivery',
      cell: (row) => (
        <Badge variant={row.modeOfDelivery === 'Virtual' ? 'info' : 'neutral'}>{row.modeOfDelivery}</Badge>
      ),
      sortValue: (row) => row.modeOfDelivery,
    },
  ];

  async function confirmDelete(reason: ReasonCode, reasonDetail?: string) {
    if (!deleting || !user) return;
    setDeleteBusy(true);
    try {
      await getTdmsClient().deleteTimetableSession(deleting.id, { reason, reasonDetail }, { actor: user });
      toast.success('Timetable record moved to the recycle area', {
        description: `${deleting.recordNumber} was removed from active use. A user activity record was created.`,
      });
      setDeleting(null);
      setSelected(null);
      await load();
    } catch (caught) {
      toast.error('The timetable record could not be deleted', {
        description: caught instanceof Error ? caught.message : 'Try again, or contact the TDMS administrator.',
      });
    } finally {
      setDeleteBusy(false);
    }
  }

  const canChange = permissions.createTimetable;

  return (
    <div className="space-y-5">
      <PageHeader
        title={INTERFACE_NAMES.timetable}
        description="View, filter, generate and manage timetable records."
        meta={
          <>
            <Badge variant="outline">
              {sessions.length} {sessions.length === 1 ? 'session' : 'sessions'} in the selected range
            </Badge>
            {filters.fromDate && filters.toDate && (
              <span className="text-[12px] text-muted-foreground">
                {formatDate(filters.fromDate)} – {formatDate(filters.toDate)}
              </span>
            )}
          </>
        }
        actions={
          <>
            <div className="flex items-center gap-1 rounded-lg border border-border bg-background p-1">
              <Button
                variant={view === 'table' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setView('table')}
                aria-pressed={view === 'table'}
              >
                <Rows3 aria-hidden="true" />
                Table
              </Button>
              <Button
                variant={view === 'calendar' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setView('calendar')}
                aria-pressed={view === 'calendar'}
              >
                <CalendarDays aria-hidden="true" />
                Calendar
              </Button>
            </div>

            <ExportMenu
              rows={sessions}
              baseFileName={`tdms-timetable-${today()}`}
              pageReference={SRS_PAGE_REFERENCE.timetable}
              columns={[
                { header: 'Timetable Record Number', value: (row) => row.recordNumber },
                { header: 'College', value: (row) => collegeById(row.collegeId)?.collegeFullName ?? '' },
                { header: 'Campus Location', value: (row) => campusById(row.campusId)?.campusLocation ?? '' },
                { header: 'Qualification Code', value: (row) => row.qualificationCode },
                { header: 'Qualification Name', value: (row) => row.qualificationName },
                { header: 'Duration in Weeks', value: (row) => row.durationInWeeks },
                { header: 'Group', value: (row) => row.group },
                { header: 'Classroom Size', value: (row) => row.classroomSize },
                { header: 'UoC Code', value: (row) => row.uocCode },
                { header: 'UoC Title', value: (row) => row.uocTitle },
                { header: 'UoC Type', value: (row) => row.uocType },
                { header: 'Mode of Delivery', value: (row) => row.modeOfDelivery },
                { header: 'UoC Start Date', value: (row) => row.uocStartDate },
                { header: 'UoC End Date', value: (row) => row.uocEndDate },
                { header: 'Theory Days and Times', value: (row) => formatSlots(row.theoryDaysAndTimes) },
                { header: 'Theory Classroom Name', value: (row) => row.theoryClassroomName },
                { header: 'Theory Classroom Capacity', value: (row) => row.theoryClassroomCapacity },
                { header: 'Theory Trainer', value: (row) => trainerName(row.theoryTrainerId) },
                { header: 'Practical Classroom Name', value: (row) => row.practicalClassroomName },
                { header: 'Practical Classroom Capacity', value: (row) => row.practicalClassroomCapacity },
                { header: 'Practical Days and Times', value: (row) => formatSlots(row.practicalDaysAndTimes) },
                { header: 'Practical Trainer', value: (row) => trainerName(row.practicalTrainerId) },
                { header: 'MSCRIS Class Name', value: (row) => row.mscrisClassName },
                { header: 'MSCRIS Days and Times', value: (row) => formatSlots(row.mscrisDaysAndTimes) },
                { header: 'MSCRIS Trainer', value: (row) => trainerName(row.mscrisTrainerId) },
                { header: 'Remarks', value: (row) => row.remarks },
              ]}
            />

            {canChange && (
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
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setEditing(null);
                    setFormMode('generate');
                  }}
                >
                  <Wand2 aria-hidden="true" />
                  Generate Timetable
                </Button>
                <Button
                  size="sm"
                  onClick={() => {
                    setEditing(null);
                    setFormMode('create');
                  }}
                >
                  <Plus aria-hidden="true" />
                  Create Timetable
                </Button>
              </>
            )}
          </>
        }
      />

      {!canChange && <ReadOnlyNotice message={readOnlyReason(user, INTERFACE_NAMES.timetable)} />}

      <FilterBar onClear={() => setFilters(defaultFilters())}>
        <FilterField label="From Date" htmlFor="tt-from">
          <Input
            id="tt-from"
            type="date"
            value={filters.fromDate ?? ''}
            onChange={(event) => setFilters((current) => ({ ...current, fromDate: event.target.value }))}
          />
        </FilterField>
        <FilterField label="To Date" htmlFor="tt-to">
          <Input
            id="tt-to"
            type="date"
            value={filters.toDate ?? ''}
            onChange={(event) => setFilters((current) => ({ ...current, toDate: event.target.value }))}
          />
        </FilterField>
        <FilterField label="College" htmlFor="tt-filter-college">
          <DependentSelect
            id="tt-filter-college"
            value={filters.collegeId ?? ''}
            onChange={(value) =>
              setFilters((current) => ({ ...current, collegeId: value, campusId: '', qualificationCode: '' }))
            }
            options={(data?.colleges ?? []).map((college) => ({
              value: college.id,
              label: college.collegeFullName,
            }))}
            placeholder="All colleges"
          />
        </FilterField>
        <FilterField label="Campus" htmlFor="tt-filter-campus">
          <DependentSelect
            id="tt-filter-campus"
            value={filters.campusId ?? ''}
            onChange={(value) => setFilters((current) => ({ ...current, campusId: value, qualificationCode: '' }))}
            options={campuses.map((campus) => ({ value: campus.id, label: campus.campusName }))}
            placeholder="All campuses"
            requires={filters.collegeId ? undefined : 'a college'}
          />
        </FilterField>
        <FilterField label="Qualification" htmlFor="tt-filter-qualification">
          <DependentSelect
            id="tt-filter-qualification"
            value={filters.qualificationCode ?? ''}
            onChange={(value) => setFilters((current) => ({ ...current, qualificationCode: value }))}
            options={Array.from(
              new Map(
                offerings.map((entry) => [
                  entry.qualificationCode,
                  { value: entry.qualificationCode, label: `${entry.qualificationCode} — ${entry.qualificationTitle}` },
                ]),
              ).values(),
            )}
            placeholder="All qualifications"
            requires={filters.collegeId ? undefined : 'a college'}
          />
        </FilterField>
        <FilterField label="Group" htmlFor="tt-filter-group">
          <SimpleSelect
            id="tt-filter-group"
            value={filters.group ?? ''}
            onChange={(value) => setFilters((current) => ({ ...current, group: value }))}
            options={(data?.groups ?? []).map((group) => ({ value: group, label: group }))}
            placeholder="All groups"
          />
        </FilterField>
      </FilterBar>

      {error ? (
        <ErrorState description={error} />
      ) : view === 'table' ? (
        <DataTable
          ariaLabel="Timetable sessions"
          columns={columns}
          rows={sessions}
          rowKey={(row) => row.id}
          loading={loading}
          loadingLabel="Loading timetable records…"
          initialSort={{ columnId: 'dates', direction: 'asc' }}
          onRowClick={(row) => setSelected(row)}
          empty={
            <EmptyState
              title="No timetable sessions match the selected filters."
              description="Change the date range or clear a filter to see more records."
              icon={CalendarRange}
            />
          }
        />
      ) : loading ? (
        <EmptyState title="Loading timetable records…" description="Please wait." icon={CalendarRange} />
      ) : (
        <TimetableCalendar
          sessions={sessions}
          anchorDate={filters.fromDate ?? today()}
          onSelect={(session) => setSelected(session)}
        />
      )}

      <TimetableDetailDrawer
        session={selected}
        onOpenChange={(open) => !open && setSelected(null)}
        canEdit={canChange}
        onEdit={(session) => {
          setEditing(session);
          setFormMode('edit');
          setSelected(null);
        }}
        onDelete={(session) => setDeleting(session)}
      />

      {formMode && (
        <TimetableFormDrawer
          open
          mode={formMode}
          editing={editing}
          existingSessions={sessions}
          onOpenChange={(open) => {
            if (!open) {
              setFormMode(null);
              setEditing(null);
            }
          }}
          onSaved={() => void load()}
        />
      )}

      {deleting && (
        <DeleteConfirmationDialog
          open
          onOpenChange={(open) => !open && setDeleting(null)}
          recordTypeLabel="Timetable Record"
          reasonContext="timetable"
          busy={deleteBusy}
          record={{
            primary: deleting.recordNumber,
            secondary: `${deleting.group} · ${deleting.qualificationCode}`,
            lines: [
              `${deleting.uocCode} — ${deleting.uocTitle}`,
              `${formatDate(deleting.uocStartDate)} – ${formatDate(deleting.uocEndDate)}`,
            ],
          }}
          onConfirm={confirmDelete}
        />
      )}

      <RecycleAreaDialog
        open={recycleOpen}
        onOpenChange={setRecycleOpen}
        title="Deleted timetable records"
        recordTypeLabel="Timetable Record"
        reasonContext="timetable"
        rows={deletedRows}
        loading={recycleLoading}
        rowKey={(row) => row.id}
        canRestore={permissions.deleteTimetable}
        columns={[
          { id: 'record', header: 'Record', cell: (row) => row.recordNumber, sortValue: (row) => row.recordNumber },
          { id: 'group', header: 'Group', cell: (row) => row.group },
          { id: 'unit', header: 'Unit', cell: (row) => row.uocCode },
        ]}
        describe={(row) => ({
          primary: row.recordNumber,
          secondary: `${row.group} · ${row.qualificationCode}`,
          lines: [`${row.uocCode} — ${row.uocTitle}`],
        })}
        onRestore={async (row, reason, reasonDetail) => {
          if (!user) return;
          await getTdmsClient().restoreTimetableSession(row.id, { reason, reasonDetail }, { actor: user });
          toast.success('Timetable record restored', {
            description: `${row.recordNumber} has been returned to active use.`,
          });
          await Promise.all([load(), loadDeleted()]);
        }}
      />
    </div>
  );
}
