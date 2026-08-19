'use client';

import * as React from 'react';
import { GraduationCap, Pencil, Plus, Trash2, Users } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { PageHeader } from '@/components/common/page-header';
import { FilterBar, FilterField } from '@/components/common/filter-bar';
import { DependentSelect, SimpleSelect } from '@/components/common/dependent-select';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState, PendingRuleNotice, ReadOnlyNotice } from '@/components/common/states';
import { ActiveBadge } from '@/components/common/status-badge';
import { ExportMenu } from '@/components/common/export-menu';
import { PreviewPanel } from '@/components/common/preview-panel';
import { DeleteConfirmationDialog } from '@/components/common/delete-confirmation-dialog';
import { RecycleAreaDialog } from '@/components/common/recycle-area-dialog';
import { AVAILABILITY_LEGEND, WeekdayAvailabilityStrip } from './weekday-availability';
import { TrainerFormDrawer } from './trainer-form-drawer';
import { useReferenceData } from '@/features/shared/reference-data-context';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient } from '@/services';
import { INTERFACE_NAMES, SRS_PAGE_REFERENCE } from '@/lib/interface-names';
import { readOnlyReason } from '@/lib/permissions';
import { today } from '@/lib/format';
import { TRAINER_DELIVERY_TYPE_OPTIONS } from '@/mock-data';
import type { ReasonCode } from '@/types/common';
import type { TrainerFilters, TrainerRecord } from '@/types/trainer';

export function TrainerWorkArea() {
  const { user, permissions } = useAuth();
  const { data } = useReferenceData();

  const [filters, setFilters] = React.useState<TrainerFilters>({ status: 'all' });
  const [rows, setRows] = React.useState<TrainerRecord[]>([]);
  const [loading, setLoading] = React.useState(false);

  const [selected, setSelected] = React.useState<TrainerRecord | null>(null);
  const [formOpen, setFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<TrainerRecord | null>(null);
  const [deleting, setDeleting] = React.useState<TrainerRecord | null>(null);
  const [busy, setBusy] = React.useState(false);

  const [recycleOpen, setRecycleOpen] = React.useState(false);
  const [deletedRows, setDeletedRows] = React.useState<TrainerRecord[]>([]);
  const [recycleLoading, setRecycleLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    if (!filters.qualificationCode) {
      setRows([]);
      return;
    }
    setLoading(true);
    try {
      setRows(await getTdmsClient().listTrainers(filters));
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
      setDeletedRows(await getTdmsClient().listDeletedTrainers());
    } finally {
      setRecycleLoading(false);
    }
  }, []);

  const qualificationOptions = React.useMemo(
    () =>
      Array.from(
        new Map(
          (data?.qualificationOfferings ?? []).map((offering) => [
            offering.qualificationCode,
            {
              value: offering.qualificationCode,
              label: `${offering.qualificationCode} — ${offering.qualificationTitle}`,
            },
          ]),
        ).values(),
      ).sort((a, b) => a.value.localeCompare(b.value)),
    [data],
  );

  const locationOptions = React.useMemo(
    () =>
      Array.from(new Set((data?.trainers ?? []).map((trainer) => trainer.location)))
        .filter(Boolean)
        .sort()
        .map((location) => ({ value: location, label: location })),
    [data],
  );

  const canMaintain = permissions.maintainTrainerData;

  const columns: DataTableColumn<TrainerRecord>[] = [
    {
      id: 'serialNumber',
      header: 'Serial Number',
      cell: (row) => <span className="tabular">{row.serialNumber}</span>,
      sortValue: (row) => row.serialNumber,
    },
    {
      id: 'trainerId',
      header: 'Trainer ID',
      cell: (row) => <span className="font-medium text-foreground">{row.trainerId}</span>,
      sortValue: (row) => row.trainerId,
    },
    {
      id: 'trainerName',
      header: 'Trainer Name',
      cell: (row) => (
        <span className="flex items-center gap-2">
          {row.trainerName}
          {!row.isActive && (
            <Badge variant="warning" className="text-[10px]">
              INACTIVE
            </Badge>
          )}
        </span>
      ),
      sortValue: (row) => row.trainerName,
    },
    {
      id: 'trainerCampus',
      header: 'Trainer Campus',
      cell: (row) => row.trainerCampus,
      sortValue: (row) => row.trainerCampus,
    },
    { id: 'location', header: 'Location', cell: (row) => row.location, sortValue: (row) => row.location },
    {
      id: 'classType',
      header: 'Delivery Type',
      cell: (row) => <Badge variant="neutral">{row.classType}</Badge>,
      sortValue: (row) => row.classType,
    },
    {
      id: 'workingTime',
      header: 'Working Time',
      cell: (row) => <span className="whitespace-nowrap tabular">{row.workingTime}</span>,
      sortValue: (row) => row.workingTime,
    },
    {
      id: 'availability',
      header: 'Mon – Fri',
      cell: (row) => <WeekdayAvailabilityStrip trainer={row} />,
    },
  ];

  async function confirmDelete(reason: ReasonCode, reasonDetail?: string) {
    if (!deleting || !user) return;
    setBusy(true);
    try {
      await getTdmsClient().deleteTrainer(deleting.id, { reason, reasonDetail }, { actor: user });
      toast.success('Trainer moved to the recycle area', {
        description: `${deleting.trainerName} was removed from active use and marked inactive.`,
      });
      setDeleting(null);
      setSelected(null);
      await load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title={INTERFACE_NAMES.trainerData}
        description="Select a qualification to view approved trainers, the units they can teach and their availability."
        meta={
          filters.qualificationCode ? (
            <Badge variant="primary">Number of Trainers Available: {rows.length}</Badge>
          ) : (
            <Badge variant="outline">Select a qualification to see trainers</Badge>
          )
        }
        actions={
          <>
            <ExportMenu
              rows={rows}
              baseFileName={`tdms-trainers-${today()}`}
              pageReference={SRS_PAGE_REFERENCE.trainerData}
              disabled={!filters.qualificationCode}
              columns={[
                { header: 'Serial Number', value: (row) => row.serialNumber },
                { header: 'Trainer ID', value: (row) => row.trainerId },
                { header: 'Trainer Name', value: (row) => row.trainerName },
                { header: 'Trainer Campus', value: (row) => row.trainerCampus },
                { header: 'Location', value: (row) => row.location },
                { header: 'Location Type', value: (row) => row.locationType },
                { header: 'Working Time', value: (row) => row.workingTime },
                { header: 'Delivery Type', value: (row) => row.classType },
                { header: 'Monday', value: (row) => row.monday },
                { header: 'Tuesday', value: (row) => row.tuesday },
                { header: 'Wednesday', value: (row) => row.wednesday },
                { header: 'Thursday', value: (row) => row.thursday },
                { header: 'Friday', value: (row) => row.friday },
                { header: 'Qualifications They Can Teach', value: (row) => row.qualificationsCanTeach.join('; ') },
                { header: 'Units They Can Teach', value: (row) => row.unitsCanTeach.join('; ') },
                { header: 'Status', value: (row) => (row.isActive ? 'Active' : 'Inactive') },
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
                  Create Trainer
                </Button>
              </>
            )}
          </>
        }
      />

      {!canMaintain && <ReadOnlyNotice message={readOnlyReason(user, INTERFACE_NAMES.trainerData)} />}

      <PendingRuleNotice
        decisionId="OD-10"
        message="The rule stating that a physically-available trainer may also deliver virtually, and that virtual-only availability cannot be used for a physical class, must be confirmed before TDMS applies it to trainer search and timetable validation (TRN-07)."
      />

      <FilterBar onClear={() => setFilters({ status: 'all' })}>
        <FilterField label="Qualification (required)" htmlFor="trainer-qualification">
          <SimpleSelect
            id="trainer-qualification"
            value={filters.qualificationCode ?? ''}
            onChange={(value) => setFilters((current) => ({ ...current, qualificationCode: value }))}
            options={qualificationOptions}
            placeholder="Select qualification"
          />
        </FilterField>
        <FilterField label="Campus" htmlFor="trainer-filter-campus">
          <DependentSelect
            id="trainer-filter-campus"
            value={filters.campusId ?? ''}
            onChange={(value) => setFilters((current) => ({ ...current, campusId: value }))}
            options={(data?.campuses ?? []).map((campus) => ({ value: campus.id, label: campus.campusName }))}
            placeholder="All campuses"
          />
        </FilterField>
        <FilterField label="Location" htmlFor="trainer-filter-location">
          <SimpleSelect
            id="trainer-filter-location"
            value={filters.location ?? ''}
            onChange={(value) => setFilters((current) => ({ ...current, location: value }))}
            options={locationOptions}
            placeholder="All locations"
          />
        </FilterField>
        <FilterField label="Delivery Type" htmlFor="trainer-filter-delivery">
          <SimpleSelect
            id="trainer-filter-delivery"
            value={filters.classType ?? ''}
            onChange={(value) => setFilters((current) => ({ ...current, classType: value as TrainerFilters['classType'] }))}
            options={TRAINER_DELIVERY_TYPE_OPTIONS.map((option) => ({ value: option, label: option }))}
            placeholder="All delivery types"
          />
        </FilterField>
        <FilterField label="Status" htmlFor="trainer-filter-status">
          <SimpleSelect
            id="trainer-filter-status"
            value={filters.status ?? 'all'}
            onChange={(value) => setFilters((current) => ({ ...current, status: value as TrainerFilters['status'] }))}
            options={[
              { value: 'all', label: 'All trainers' },
              { value: 'active', label: 'Active only' },
              { value: 'inactive', label: 'Inactive only' },
            ]}
            placeholder="All trainers"
          />
        </FilterField>
        <FilterField label="Search" htmlFor="trainer-filter-search">
          <Input
            id="trainer-filter-search"
            value={filters.search ?? ''}
            onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
            placeholder="Trainer ID or name"
          />
        </FilterField>
      </FilterBar>

      {!filters.qualificationCode ? (
        <EmptyState
          title="Select a qualification to see trainers"
          description="Trainer results are shown once a qualification is selected."
          icon={GraduationCap}
        />
      ) : (
        <>
          <DataTable
            ariaLabel="Trainers approved for the selected qualification"
            columns={columns}
            rows={rows}
            rowKey={(row) => row.id}
            loading={loading}
            loadingLabel="Loading trainers…"
            initialSort={{ columnId: 'serialNumber', direction: 'asc' }}
            onRowClick={(row) => setSelected(row)}
            empty={
              <EmptyState
                title="No trainers are available for this qualification."
                description="Change the campus, location, delivery type or status filter to widen the search."
                icon={Users}
              />
            }
            rowActions={
              canMaintain
                ? (row) => (
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Edit ${row.trainerName}`}
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
                        aria-label={`Delete ${row.trainerName}`}
                        onClick={() => setDeleting(row)}
                      >
                        <Trash2 aria-hidden="true" />
                      </Button>
                    </div>
                  )
                : undefined
            }
          />
          <p className="text-[12px] text-muted-foreground">Weekday availability: {AVAILABILITY_LEGEND}</p>
        </>
      )}

      {selected && (
        <Sheet open onOpenChange={(open) => !open && setSelected(null)}>
          <SheetContent width="lg">
            <SheetHeader>
              <SheetTitle>{selected.trainerName}</SheetTitle>
              <SheetDescription>
                {selected.trainerId} · {selected.trainerCampus}
              </SheetDescription>
            </SheetHeader>
            <SheetBody className="space-y-4">
              <div className="flex items-center gap-2">
                <ActiveBadge isActive={selected.isActive} />
                {!selected.isActive && (
                  <span className="text-[12px] text-muted-foreground">
                    Visible for historical records. Not selectable for a new timetable assignment.
                  </span>
                )}
              </div>
              <PreviewPanel
                groups={[
                  {
                    title: 'Trainer location data',
                    items: [
                      { label: 'Serial Number', value: selected.serialNumber },
                      { label: 'Trainer ID', value: selected.trainerId },
                      { label: 'Trainer Name', value: selected.trainerName },
                      { label: 'Trainer Campus', value: selected.trainerCampus },
                      { label: 'Location', value: selected.location },
                      { label: 'Location Type', value: selected.locationType },
                      { label: 'Working Time', value: selected.workingTime },
                      { label: 'Delivery Type', value: selected.classType },
                    ],
                  },
                  {
                    title: 'Weekday availability',
                    items: [
                      { label: 'Monday', value: selected.monday },
                      { label: 'Tuesday', value: selected.tuesday },
                      { label: 'Wednesday', value: selected.wednesday },
                      { label: 'Thursday', value: selected.thursday },
                      { label: 'Friday', value: selected.friday },
                    ],
                  },
                ]}
              />
              <section>
                <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Qualifications They Can Teach
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {selected.qualificationsCanTeach.map((code) => (
                    <Badge key={code} variant="primary">
                      {code}
                    </Badge>
                  ))}
                </div>
              </section>
              <section>
                <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Units They Can Teach ({selected.unitsCanTeach.length})
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {selected.unitsCanTeach.map((code) => (
                    <Badge key={code} variant="outline">
                      {code}
                    </Badge>
                  ))}
                </div>
              </section>
            </SheetBody>
            <SheetFooter>
              <Button variant="outline" onClick={() => setSelected(null)}>
                Close
              </Button>
              {canMaintain && (
                <Button
                  onClick={() => {
                    setEditing(selected);
                    setSelected(null);
                    setFormOpen(true);
                  }}
                >
                  <Pencil aria-hidden="true" />
                  Edit Trainer
                </Button>
              )}
            </SheetFooter>
          </SheetContent>
        </Sheet>
      )}

      <TrainerFormDrawer
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditing(null);
        }}
        editing={editing}
        onSaved={() => void load()}
      />

      {deleting && (
        <DeleteConfirmationDialog
          open
          onOpenChange={(open) => !open && setDeleting(null)}
          recordTypeLabel="Trainer Record"
          reasonContext="trainer"
          busy={busy}
          record={{
            primary: deleting.trainerId,
            secondary: deleting.trainerName,
            lines: [
              deleting.trainerCampus,
              `Current status: ${deleting.isActive ? 'Active' : 'Inactive'}`,
              `Qualifications: ${deleting.qualificationsCanTeach.join(', ')}`,
            ],
          }}
          onConfirm={confirmDelete}
        />
      )}

      <RecycleAreaDialog
        open={recycleOpen}
        onOpenChange={setRecycleOpen}
        title="Deleted trainer records"
        recordTypeLabel="Trainer Record"
        reasonContext="trainer"
        rows={deletedRows}
        loading={recycleLoading}
        rowKey={(row) => row.id}
        canRestore={canMaintain}
        columns={[
          { id: 'trainerId', header: 'Trainer ID', cell: (row) => row.trainerId, sortValue: (row) => row.trainerId },
          { id: 'trainerName', header: 'Trainer Name', cell: (row) => row.trainerName },
          { id: 'campus', header: 'Trainer Campus', cell: (row) => row.trainerCampus },
        ]}
        describe={(row) => ({ primary: row.trainerId, secondary: row.trainerName, lines: [row.trainerCampus] })}
        onRestore={async (row, reason, reasonDetail) => {
          if (!user) return;
          await getTdmsClient().restoreTrainer(row.id, { reason, reasonDetail }, { actor: user });
          toast.success('Trainer restored', { description: `${row.trainerName} has been returned to active use.` });
          await Promise.all([load(), loadDeleted()]);
        }}
      />
    </div>
  );
}
