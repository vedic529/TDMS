'use client';

import * as React from 'react';
import { Loader2, TriangleAlert } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { FilterBar, FilterField } from '@/components/common/filter-bar';
import { SimpleSelect } from '@/components/common/dependent-select';
import { ExportMenu } from '@/components/common/export-menu';
import { ErrorState } from '@/components/common/states';
import { referenceApi } from '@/services/reference-api';
import { trainersApi, type UnitCoverageRow } from '@/services/trainers-api';
import { SRS_PAGE_REFERENCE } from '@/lib/interface-names';

/**
 * Unit Coverage — every unit, and how many trainers can teach it.
 *
 * Sorted by trainer count ascending, so the **gaps come first**: a unit nobody
 * is approved for is the reason this view exists, and burying it under the
 * covered units would defeat the point. A zero-trainer unit carries a badge
 * reading "No trainer" as well as its count, so the state is never signalled by
 * colour alone.
 */
export function TrainerUnitCoverage() {
  const [rows, setRows] = React.useState<UnitCoverageRow[]>([]);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const [qualifications, setQualifications] = React.useState<{ value: string; label: string }[]>([]);
  const [qualification, setQualification] = React.useState('');
  const [onlyUncovered, setOnlyUncovered] = React.useState(false);

  React.useEffect(() => {
    void referenceApi
      .listQualifications({ activeOnly: true })
      .then((found) =>
        setQualifications([
          { value: '', label: 'All qualifications' },
          ...found.map((row) => ({
            value: String(row.id),
            label: `${row.qualification_code ?? 'NA'} — ${row.qualification_title}`,
          })),
        ]),
      )
      .catch(() => setQualifications([{ value: '', label: 'All qualifications' }]));
  }, []);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await trainersApi.unitCoverage({
        qualification_id: qualification ? Number(qualification) : undefined,
        only_uncovered: onlyUncovered || undefined,
        limit: 1000,
      });
      setRows(result.items);
      setTotal(result.total);
    } catch (caught) {
      setRows([]);
      setError(caught instanceof Error ? caught.message : 'Unit coverage could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [qualification, onlyUncovered]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const uncovered = rows.filter((row) => row.trainer_count === 0).length;

  const columns: DataTableColumn<UnitCoverageRow>[] = [
    { id: 'unit_code', header: 'Unit Code', cell: (row) => <span className="font-medium">{row.unit_code}</span> },
    { id: 'unit_title', header: 'Unit Title', cell: (row) => row.unit_title },
    {
      id: 'qualification',
      header: 'Qualification',
      cell: (row) =>
        row.qualification_code ? (
          <span title={row.qualification_title ?? undefined}>{row.qualification_code}</span>
        ) : (
          <span className="text-muted-foreground">Not in a qualification</span>
        ),
    },
    {
      id: 'trainer_count',
      header: 'Trainer Count',
      sortValue: (row) => row.trainer_count,
      cell: (row) =>
        row.trainer_count === 0 ? (
          // The count and the badge text both say it; colour is never the only
          // signal that a unit has nobody approved to teach it.
          <span className="flex items-center gap-1.5">
            <span className="tabular">0</span>
            <Badge variant="destructive" className="gap-1">
              <TriangleAlert aria-hidden="true" className="size-3" />
              No trainer
            </Badge>
          </span>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span tabIndex={0} className="tabular underline-offset-2 hover:underline">
                {row.trainer_count}
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {row.trainer_names.join(', ')}
              {row.has_more_trainers && ' and more'}
            </TooltipContent>
          </Tooltip>
        ),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Unit Coverage</CardTitle>
            <CardDescription>
              Every unit in the reference data, and how many active trainers are approved to teach
              it. Units with no trainer are listed first.
            </CardDescription>
          </div>
          <ExportMenu
            baseFileName="unit-coverage"
            pageReference={SRS_PAGE_REFERENCE.trainerData}
            rows={rows}
            disabled={rows.length === 0}
            columns={[
              { header: 'Unit Code', value: (row) => row.unit_code },
              { header: 'Unit Title', value: (row) => row.unit_title },
              { header: 'Qualification', value: (row) => row.qualification_code ?? '' },
              { header: 'Trainer Count', value: (row) => row.trainer_count },
              {
                header: 'Trainers',
                value: (row) =>
                  row.trainer_names.join('; ') + (row.has_more_trainers ? ' and more' : ''),
              },
            ]}
          />
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <FilterBar>
          <FilterField label="Qualification" htmlFor="coverage-qualification">
            <SimpleSelect
              value={qualification}
              onChange={setQualification}
              options={qualifications}
              placeholder="All qualifications"
            />
          </FilterField>
          <FilterField label="Coverage" htmlFor="coverage-only">
            <Button
              id="coverage-only"
              type="button"
              variant={onlyUncovered ? 'default' : 'outline'}
              onClick={() => setOnlyUncovered((value) => !value)}
              aria-pressed={onlyUncovered}
            >
              Units with no trainer
            </Button>
          </FilterField>
        </FilterBar>

        <p className="text-[13px] text-muted-foreground tabular">
          {total} unit{total === 1 ? '' : 's'}
          {uncovered > 0 && ` · ${uncovered} with no trainer`}
        </p>

        {loading ? (
          <p className="flex items-center gap-2 py-6 text-[13px] text-muted-foreground" aria-busy="true">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            Loading unit coverage…
          </p>
        ) : error ? (
          <div className="space-y-3">
            <ErrorState title="Unit coverage could not be loaded" description={error} />
            <Button variant="outline" size="sm" onClick={() => void load()}>
              Retry
            </Button>
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(row) => `${row.unit_id}-${row.qualification_id ?? 'none'}`}
            ariaLabel="Unit coverage"
            empty="No unit matches these filters."
          />
        )}
      </CardContent>
    </Card>
  );
}
