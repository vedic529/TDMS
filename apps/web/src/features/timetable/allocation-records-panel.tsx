'use client';

import * as React from 'react';
import { Download } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FilterBar, FilterField } from '@/components/common/filter-bar';
import { SimpleSelect } from '@/components/common/dependent-select';
import { ErrorState, LoadingState, ReadOnlyNotice } from '@/components/common/states';
import { useAuth } from '@/features/auth/auth-context';
import { AllocationCalendar } from './allocation-calendar-view';
import { AllocationImportDialog } from './allocation-import-dialog';
import { ClearAllocationDialog } from './clear-allocation-dialog';
import { AllocationSessionPanel } from './allocation-session-panel';
import { AllocationSpreadsheet } from './allocation-spreadsheet-view';

export type AllocationView = 'spreadsheet' | 'calendar';
import { INTERFACE_NAMES } from '@/lib/interface-names';
import { addDays, today } from '@/lib/format';
import { readOnlyReason } from '@/lib/permissions';
import { ReferenceApiError } from '@/services/reference-api';
import {
  allocationApi,
  type AllocationCalendar as CalendarPayload,
  type AllocationCalendarSession,
  type AllocationPackage,
} from '@/services/allocation-api';

export function AllocationRecordsPanel({ view }: { view: AllocationView }) {
  const { user, permissions } = useAuth();
  const canChange = permissions.maintainTimetable;
  // Clearing the records is a Super Admin action, not ordinary timetable
  // maintenance: it destroys every allocation row in one step.
  const isSuperAdmin = permissions.accessAdministration;
  const [packages, setPackages] = React.useState<AllocationPackage[]>([]);
  const [trainingPackage, setTrainingPackage] = React.useState('BSB');
  const [fromDate, setFromDate] = React.useState(() => today());
  const [toDate, setToDate] = React.useState(() => addDays(today(), 27));
  const [grid, setGrid] = React.useState<CalendarPayload | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<AllocationCalendarSession | null>(null);
  const [reload, setReload] = React.useState(0);

  React.useEffect(() => {
    void allocationApi.listPackages().then(setPackages).catch(() => setPackages([]));
  }, []);

  React.useEffect(() => {
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        setGrid(await allocationApi.calendar(trainingPackage, fromDate, toDate));
      } catch (caught) {
        setError(caught instanceof ReferenceApiError ? caught.message : 'Allocation records could not be loaded.');
        setGrid(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [trainingPackage, fromDate, toDate, reload]);

  async function download() {
    try {
      const blob = await allocationApi.download(trainingPackage, fromDate, toDate);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `allocation-${trainingPackage}.xlsx`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      toast.error(caught instanceof ReferenceApiError ? caught.message : 'The workbook could not be downloaded.');
    }
  }

  return (
    <div className="space-y-4">
      {!canChange && <ReadOnlyNotice message={readOnlyReason(user, INTERFACE_NAMES.timetable)} />}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <FilterBar>
          <FilterField label="Training package" htmlFor="alloc-package">
            <SimpleSelect
              id="alloc-package"
              value={trainingPackage}
              onChange={setTrainingPackage}
              placeholder="Package"
              options={packages.map((item) => ({
                value: item.training_package,
                label: item.training_package,
                disabled: !item.enabled,
              }))}
            />
          </FilterField>
          <FilterField label="From" htmlFor="alloc-from">
            <Input id="alloc-from" type="date" value={fromDate} onChange={(event) => setFromDate(event.target.value)} />
          </FilterField>
          <FilterField label="To" htmlFor="alloc-to">
            <Input id="alloc-to" type="date" value={toDate} onChange={(event) => setToDate(event.target.value)} />
          </FilterField>
        </FilterBar>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={() => void download()}>
            <Download aria-hidden="true" />
            Download
          </Button>
          {canChange && <AllocationImportDialog packages={packages} onImported={() => setReload((value) => value + 1)} />}
          {isSuperAdmin && (
            <ClearAllocationDialog onCleared={() => setReload((value) => value + 1)} />
          )}
        </div>
      </div>

      {error ? (
        <ErrorState title="Allocation records could not be loaded" description={error} />
      ) : loading || !grid ? (
        <LoadingState label="Opening allocation records…" />
      ) : (
        view === 'spreadsheet' ? (
          <AllocationSpreadsheet grid={grid} onSelect={setSelected} />
        ) : (
          <AllocationCalendar grid={grid} onSelect={setSelected} />
        )
      )}

      <AllocationSessionPanel
        session={selected}
        trainingPackage={trainingPackage}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        onSaved={() => setReload((value) => value + 1)}
      />
    </div>
  );
}
