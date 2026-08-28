'use client';

import * as React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { CalendarDays, CalendarRange, Database, Grid3x3, LayoutGrid, Sheet } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { PageHeader } from '@/components/common/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/common/states';
import { INTERFACE_NAMES } from '@/lib/interface-names';
import {
  ROLLING_EMPTY_DESCRIPTION,
  ROLLING_EMPTY_MESSAGE,
  rollingTimetableApi,
  type RollingScope,
} from '@/services/rolling-timetable-api';
import { ReferenceApiError } from '@/services/reference-api';
import { AllocationRecordsPanel, type AllocationView } from './allocation-records-panel';
import { RollingDatabaseActions } from './rolling-database-actions';
import { RollingDatabaseView } from './rolling-database-view';
import { RollingScopeBar, selectionFromScopes, type RollingSelection } from './rolling-scope-bar';
import { RollingVisualizer } from './rolling-visualizer';

type TabValue = 'allocation' | 'rolling';
type RollingView = 'visualizer' | 'database';

function parseTab(value: string | null): TabValue {
  return value === 'rolling' ? 'rolling' : 'allocation';
}

function parseRollingView(value: string | null): RollingView {
  return value === 'database' ? 'database' : 'visualizer';
}

function parseAllocationView(value: string | null): AllocationView {
  return value === 'spreadsheet' ? 'spreadsheet' : 'calendar';
}

function selectionFromParams(params: URLSearchParams): RollingSelection | null {
  const trainingPackage = params.get('package');
  const qualificationCode = params.get('qualification');
  const duration = params.get('duration');
  if (!trainingPackage || !qualificationCode || !duration) return null;
  const durationWeeks = Number(duration);
  if (!Number.isFinite(durationWeeks) || durationWeeks <= 0) return null;
  return { trainingPackage, qualificationCode, durationWeeks };
}

export function TimetableWorkArea() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const tab = parseTab(searchParams.get('tab'));
  const rollingView = parseRollingView(searchParams.get('view'));
  const allocationView = parseAllocationView(searchParams.get('view'));
  const urlSelection = selectionFromParams(searchParams);

  const [scopes, setScopes] = React.useState<RollingScope[]>([]);
  const [scopesLoading, setScopesLoading] = React.useState(tab === 'rolling');
  const [scopesError, setScopesError] = React.useState<string | null>(null);

  const loadScopes = React.useCallback(async () => {
    setScopesLoading(true);
    setScopesError(null);
    try {
      setScopes(await rollingTimetableApi.listScopes());
    } catch (caught) {
      setScopesError(caught instanceof ReferenceApiError ? caught.message : 'Rolling timetable could not be loaded.');
      setScopes([]);
    } finally {
      setScopesLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (tab === 'rolling') void loadScopes();
  }, [tab, loadScopes]);

  const selection = selectionFromScopes(scopes, urlSelection);

  function replaceParams(next: {
    tab?: TabValue;
    rollingView?: RollingView;
    allocationView?: AllocationView;
    selection?: RollingSelection | null;
  }) {
    const params = new URLSearchParams(searchParams.toString());
    const nextTab = next.tab ?? tab;
    params.set('tab', nextTab);
    if (nextTab === 'allocation') {
      params.set('view', next.allocationView ?? (next.tab && next.tab !== tab ? 'calendar' : allocationView));
    } else {
      params.set('view', next.rollingView ?? (next.tab && next.tab !== tab ? 'visualizer' : rollingView));
    }
    const chosen = next.selection === undefined ? selection : next.selection;
    if (chosen) {
      params.set('package', chosen.trainingPackage);
      params.set('qualification', chosen.qualificationCode);
      params.set('duration', String(chosen.durationWeeks));
    } else {
      params.delete('package');
      params.delete('qualification');
      params.delete('duration');
    }
    router.replace(`/timetable?${params.toString()}`, { scroll: false });
  }

  React.useEffect(() => {
    if (tab !== 'rolling' || scopesLoading || !selection) return;
    const current = selectionFromParams(searchParams);
    if (
      current &&
      current.trainingPackage === selection.trainingPackage &&
      current.qualificationCode === selection.qualificationCode &&
      current.durationWeeks === selection.durationWeeks
    ) {
      return;
    }
    replaceParams({ selection });
    // URL write after scopes resolve; searchParams is the source of the check above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, scopesLoading, selection?.trainingPackage, selection?.qualificationCode, selection?.durationWeeks]);

  return (
    <div className="space-y-5">
      <PageHeader
        title={INTERFACE_NAMES.timetable}
        description="View allocated sessions, or inspect the approved rolling timetable as a week grid or as stored records."
      />

      <Tabs value={tab} onValueChange={(next) => replaceParams({ tab: parseTab(next) })}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList>
            <TabsTrigger value="allocation">
              <CalendarRange aria-hidden="true" />
              Allocation Records
            </TabsTrigger>
            <TabsTrigger value="rolling">
              <LayoutGrid aria-hidden="true" />
              Rolling Timetable
            </TabsTrigger>
          </TabsList>

          {tab === 'allocation' && (
            <div
              className="flex items-center gap-1 rounded-lg border border-border bg-background p-1"
              role="group"
              aria-label="Allocation records view"
            >
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    size="icon-sm"
                    variant={allocationView === 'spreadsheet' ? 'secondary' : 'ghost'}
                    aria-pressed={allocationView === 'spreadsheet'}
                    aria-label="Spreadsheet View"
                    onClick={() => replaceParams({ allocationView: 'spreadsheet' })}
                  >
                    <Sheet aria-hidden="true" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Spreadsheet View</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    size="icon-sm"
                    variant={allocationView === 'calendar' ? 'secondary' : 'ghost'}
                    aria-pressed={allocationView === 'calendar'}
                    aria-label="Calendar View"
                    onClick={() => replaceParams({ allocationView: 'calendar' })}
                  >
                    <CalendarDays aria-hidden="true" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Calendar View</TooltipContent>
              </Tooltip>
            </div>
          )}
          {tab === 'rolling' && (
            <div className="flex flex-wrap items-center justify-end gap-2">
              <RollingDatabaseActions onImported={() => void loadScopes()} />
              <div
                className="flex items-center gap-1 rounded-lg border border-border bg-background p-1"
                role="group"
                aria-label="Rolling timetable view"
              >
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      size="icon-sm"
                      variant={rollingView === 'visualizer' ? 'secondary' : 'ghost'}
                      aria-pressed={rollingView === 'visualizer'}
                      aria-label="Visualizer"
                      onClick={() => replaceParams({ rollingView: 'visualizer' })}
                    >
                      <Grid3x3 aria-hidden="true" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Visualizer</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      size="icon-sm"
                      variant={rollingView === 'database' ? 'secondary' : 'ghost'}
                      aria-pressed={rollingView === 'database'}
                      aria-label="Database View"
                      onClick={() => replaceParams({ rollingView: 'database' })}
                    >
                      <Database aria-hidden="true" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Database View</TooltipContent>
                </Tooltip>
              </div>
            </div>
          )}
        </div>

        <TabsContent value="allocation">
          <AllocationRecordsPanel view={allocationView} />
        </TabsContent>
        <TabsContent value="rolling" className="space-y-4">
          {scopesError ? (
            <ErrorState title="Rolling timetable could not be loaded" description={scopesError} />
          ) : scopesLoading ? (
            <LoadingState label="Opening the rolling timetable…" />
          ) : !selection ? (
            <EmptyState title={ROLLING_EMPTY_MESSAGE} description={ROLLING_EMPTY_DESCRIPTION} />
          ) : (
            <>
              <RollingScopeBar scopes={scopes} selection={selection} onChange={(next) => replaceParams({ selection: next })} />
              {rollingView === 'database' ? (
                <RollingDatabaseView selection={selection} />
              ) : (
                <RollingVisualizer selection={selection} />
              )}
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
