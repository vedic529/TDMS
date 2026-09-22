'use client';

import * as React from 'react';
import { Download } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
import { addDays, endOfWeek, localToday, startOfWeek } from '@/lib/format';
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
  // Start with the current week's Monday. An empty end means every later allocation.
  const [fromDate, setFromDate] = React.useState(() => startOfWeek(localToday()));
  const [toDate, setToDate] = React.useState('');
  const [grid, setGrid] = React.useState<CalendarPayload | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<AllocationCalendarSession | null>(null);
  // The calendar day whose classes are open. A class opened from it hides the
  // day while its panel is open, and the day comes back when the panel closes.
  const [openDate, setOpenDate] = React.useState<string | null>(null);
  const [resumeDate, setResumeDate] = React.useState<string | null>(null);
  const [reload, setReload] = React.useState(0);

  React.useEffect(() => {
    void allocationApi.listPackages().then(setPackages).catch(() => setPackages([]));
  }, []);

  React.useEffect(() => {
    if (view === 'spreadsheet') {
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        // The calendar is laid out in whole weeks, Monday to Sunday.
        // A calendar must stay finite. With no To date, show a four-week window;
        // the spreadsheet and download remain open-ended.
        const [start, end] = [
          startOfWeek(fromDate),
          endOfWeek(toDate || addDays(startOfWeek(fromDate), 27)),
        ];
        setGrid(await allocationApi.calendar(trainingPackage, start, end));
      } catch (caught) {
        setError(caught instanceof ReferenceApiError ? caught.message : 'Allocation records could not be loaded.');
        setGrid(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [trainingPackage, fromDate, toDate, reload, view]);

  /** The spreadsheet view, downloaded as it is shown. */
  async function download(fileFormat: 'xlsx' | 'csv') {
    try {
      const { blob, fileName } = await allocationApi.download(trainingPackage, fromDate, toDate, fileFormat);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      toast.error(caught instanceof ReferenceApiError ? caught.message : 'The file could not be downloaded.');
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
            <Input id="alloc-from" type="date" required value={fromDate} onChange={(event) => { if (event.target.value) setFromDate(event.target.value); }} />
          </FilterField>
          <FilterField label="To" htmlFor="alloc-to">
            <Input id="alloc-to" type="date" min={fromDate} value={toDate} onChange={(event) => setToDate(event.target.value)} />
          </FilterField>
        </FilterBar>
        <div className="flex gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" variant="outline">
                <Download aria-hidden="true" />
                Download
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Allocation records, as the spreadsheet shows them</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => void download('xlsx')}>Export XLSX</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void download('csv')}>Export CSV</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          {canChange && <AllocationImportDialog packages={packages} onImported={() => setReload((value) => value + 1)} />}
          {isSuperAdmin && (
            <ClearAllocationDialog onCleared={() => setReload((value) => value + 1)} />
          )}
        </div>
      </div>

      {view === 'spreadsheet' ? (
        <AllocationSpreadsheet
          trainingPackage={trainingPackage}
          fromDate={fromDate}
          toDate={toDate}
          onFromDateChange={setFromDate}
          onToDateChange={setToDate}
          reloadToken={reload}
          canChange={canChange}
        />
      ) : error ? (
        <ErrorState title="Allocation records could not be loaded" description={error} />
      ) : loading || !grid ? (
        <LoadingState label="Opening allocation records…" />
      ) : (
        <AllocationCalendar
            grid={grid}
            openDate={openDate}
            onOpenDate={setOpenDate}
            onSelect={(item) => {
              // Two modal layers side by side dismiss each other, so the day
              // steps aside while the class is edited.
              setResumeDate(openDate);
              setOpenDate(null);
              setSelected(item);
            }}
          />
      )}

      <AllocationSessionPanel
        session={selected}
        trainingPackage={trainingPackage}
        onOpenChange={(open) => {
          if (open) return;
          setSelected(null);
          if (resumeDate) {
            setOpenDate(resumeDate);
            setResumeDate(null);
          }
        }}
        onSaved={() => setReload((value) => value + 1)}
      />
    </div>
  );
}
