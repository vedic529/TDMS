'use client';

import * as React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { FileSpreadsheet, MapPin, Plus, Search, Users } from 'lucide-react';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageHeader } from '@/components/common/page-header';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { ActiveBadge } from '@/components/common/status-badge';
import { ExportMenu } from '@/components/common/export-menu';
import { EmptyState, ErrorState } from '@/components/common/states';
import { SuggestionIndicator } from '@/features/shared/suggestion-indicator';
import { TrainerDetailPanel } from './trainer-detail-panel';
import { TrainerUnitCoverage } from './trainer-unit-coverage';
import { BulkTrainerImport } from './bulk-trainer-import';
import { AddTrainerDialog } from './add-trainer-dialog';
import { ClearTrainersDialog } from './clear-trainers-dialog';
import { useAuth } from '@/features/auth/auth-context';
import { trainersApi, type TrainerRow } from '@/services/trainers-api';
import { INTERFACE_NAMES, SRS_PAGE_REFERENCE } from '@/lib/interface-names';

type TabValue = 'location-details' | 'unit-coverage' | 'bulk-import';

const PAGE_SIZE = 25;

function parseTab(value: string | null): TabValue {
  if (value === 'unit-coverage' || value === 'bulk-import') return value;
  return 'location-details';
}

/**
 * Trainer Data work area.
 *
 * Three subtabs, following the `?tab=` pattern the Student Data work area uses.
 * The tab names come from `INTERFACE_NAMES`; the SRS page reference (Page 3) is
 * never shown to the user.
 */
export function TrainerWorkArea() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = parseTab(searchParams.get('tab'));

  function setTab(next: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set('tab', next);
    // Row parameters belong to the tab that set them.
    params.delete('trainerId');
    router.replace(`/trainers?${params.toString()}`, { scroll: false });
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title={INTERFACE_NAMES.trainerData}
        description="Trainers, the locations they work at and the units they are approved to teach. One row per trainer, however many locations they hold."
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="location-details">
            <MapPin aria-hidden="true" />
            {INTERFACE_NAMES.trainerLocationDetails}
          </TabsTrigger>
          <TabsTrigger value="unit-coverage">
            <Users aria-hidden="true" />
            {INTERFACE_NAMES.trainerUnitCoverage}
          </TabsTrigger>
          <TabsTrigger value="bulk-import">
            <FileSpreadsheet aria-hidden="true" />
            {INTERFACE_NAMES.bulkTrainerImport}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="location-details">
          <TrainerRecordsPanel />
        </TabsContent>

        <TabsContent value="unit-coverage">
          <TrainerUnitCoverage />
        </TabsContent>

        <TabsContent value="bulk-import">
          <BulkTrainerImport />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/** One row per trainer. Clicking a row opens the side panel. */
function TrainerRecordsPanel() {
  const { permissions } = useAuth();
  const canMaintain = permissions.maintainTrainerData;
  // Clearing the whole database is a Super Admin action, not a maintainer's.
  const isSuperAdmin = permissions.accessAdministration;

  const [rows, setRows] = React.useState<TrainerRow[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [search, setSearch] = React.useState('');
  const [applied, setApplied] = React.useState('');
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const [selected, setSelected] = React.useState<number | null>(null);
  const [panelOpen, setPanelOpen] = React.useState(false);
  const [creating, setCreating] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await trainersApi.list({
        search: applied || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setRows(result.items);
      setTotal(result.total);
    } catch (caught) {
      setRows([]);
      setError(caught instanceof Error ? caught.message : 'Trainers could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [applied, page]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const columns: DataTableColumn<TrainerRow>[] = [
    {
      id: 'trainer_id',
      header: 'Trainer ID',
      sortValue: (row) => row.trainer_id,
      cell: (row) => <span className="font-medium">{row.trainer_id}</span>,
    },
    {
      id: 'trainer_name',
      header: 'Trainer Name',
      sortValue: (row) => row.trainer_name,
      cell: (row) => row.trainer_name,
    },
    {
      id: 'city',
      header: 'City',
      sortValue: (row) => row.city ?? '',
      cell: (row) =>
        row.city ?? <span className="text-muted-foreground">City not recorded</span>,
    },
    {
      id: 'locations',
      header: 'Locations',
      cell: (row) => (
        <span className="flex items-center gap-1.5">
          <span className="tabular text-muted-foreground">{row.location_count}</span>
          <span className="truncate">{row.location_summary || '—'}</span>
        </span>
      ),
    },
    {
      id: 'qualifications',
      header: 'Qualifications',
      sortValue: (row) => row.qualification_count,
      align: 'right',
      cell: (row) => <span className="tabular">{row.qualification_count}</span>,
    },
    {
      id: 'units',
      header: 'Units',
      sortValue: (row) => row.unit_count,
      align: 'right',
      cell: (row) => <span className="tabular">{row.unit_count}</span>,
    },
    {
      id: 'packages',
      header: 'Training Packages',
      cell: (row) => (
        // Derived from the qualifications they teach — never stored (1.7).
        <span className="flex flex-wrap gap-1">
          {row.training_packages.length === 0 ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            row.training_packages.map((code) => (
              <Badge key={code} variant="info">
                {code}
              </Badge>
            ))
          )}
        </span>
      ),
    },
    {
      id: 'active',
      header: 'Active',
      cell: (row) => <ActiveBadge isActive={row.is_active} />,
    },
  ];

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle>{INTERFACE_NAMES.trainerLocationDetails}</CardTitle>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search
                  aria-hidden="true"
                  className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      setPage(0);
                      setApplied(search);
                    }
                  }}
                  placeholder="Search trainer id or name"
                  className="w-64 pl-8"
                  aria-label="Search trainers"
                />
              </div>
              {/* The trainer suggestions raised by an import, plus the reference
                  values a trainer file can leave unmatched. Kept from the
                  previous tab (2.8). */}
              <SuggestionIndicator
                entityTypes={['TRAINER', 'CAMPUS', 'QUALIFICATION', 'UNIT']}
                onResolved={() => void load()}
              />
              <ExportMenu
                baseFileName="trainers"
                pageReference={SRS_PAGE_REFERENCE.trainerData}
                rows={rows}
                disabled={rows.length === 0}
                columns={[
                  { header: 'Trainer ID', value: (row) => row.trainer_id },
                  { header: 'Trainer Name', value: (row) => row.trainer_name },
                  { header: 'City', value: (row) => row.city ?? '' },
                  { header: 'Locations', value: (row) => row.location_summary },
                  { header: 'Qualifications', value: (row) => row.qualification_count },
                  { header: 'Units', value: (row) => row.unit_count },
                  { header: 'Training Packages', value: (row) => row.training_packages.join('; ') },
                  { header: 'Active', value: (row) => (row.is_active ? 'Yes' : 'No') },
                ]}
              />
              {canMaintain && (
                <Button onClick={() => setCreating(true)}>
                  <Plus aria-hidden="true" />
                  Add trainer
                </Button>
              )}
              {isSuperAdmin && <ClearTrainersDialog onCleared={() => void load()} />}
            </div>
          </div>
        </CardHeader>

        <CardContent>
          {error ? (
            <div className="space-y-3">
              <ErrorState title="Trainers could not be loaded" description={error} />
              <Button variant="outline" size="sm" onClick={() => void load()}>
                Retry
              </Button>
            </div>
          ) : !loading && total === 0 ? (
            <EmptyState
              title="No trainer records"
              description={
                applied
                  ? 'No trainer matches that search.'
                  : 'Import the Trainer Location and Details file, or add a trainer by hand.'
              }
              icon={Users}
            />
          ) : (
            <DataTable
              columns={columns}
              rows={rows}
              rowKey={(row) => String(row.id)}
              loading={loading}
              loadingLabel="Loading trainers…"
              ariaLabel="Trainer records"
              activeRowKey={selected !== null ? String(selected) : undefined}
              onRowClick={(row) => {
                setSelected(row.id);
                setPanelOpen(true);
              }}
              serverPagination={{
                page,
                pageSize: PAGE_SIZE,
                total,
                onPageChange: setPage,
              }}
            />
          )}
        </CardContent>
      </Card>

      <TrainerDetailPanel
        trainerPk={selected}
        open={panelOpen}
        onOpenChange={setPanelOpen}
        canMaintain={canMaintain}
        onChanged={() => void load()}
      />

      <AddTrainerDialog open={creating} onOpenChange={setCreating} onCreated={() => void load()} />
    </>
  );
}
