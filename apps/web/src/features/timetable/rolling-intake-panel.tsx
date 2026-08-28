'use client';

import * as React from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
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
import { SimpleSelect } from '@/components/common/dependent-select';
import { LoadingState, ReadOnlyNotice } from '@/components/common/states';
import { useAuth } from '@/features/auth/auth-context';
import { formatDate } from '@/lib/format';
import { INTERFACE_NAMES } from '@/lib/interface-names';
import { readOnlyReason } from '@/lib/permissions';
import { ReferenceApiError } from '@/services/reference-api';
import {
  rollingTimetableApi,
  type RollingWeek,
  type RollingWeekPatchItem,
} from '@/services/rolling-timetable-api';
import { scheduleTypeLabel } from './rolling-week-detail-drawer';
import type { RollingSelection } from './rolling-scope-bar';

const TYPE_OPTIONS = [
  { value: 'UNIT', label: 'Unit' },
  { value: 'BREAK', label: 'Break' },
  { value: 'ASSESSMENT_WEEK', label: 'Assessment Week' },
];

interface DraftRow {
  id: number;
  week_no: number;
  week_start_date: string;
  week_end_date: string;
  unit_slot: number;
  schedule_type: RollingWeek['schedule_type'];
  schedule_value: string;
}

function toDraft(row: RollingWeek): DraftRow {
  return {
    id: row.id,
    week_no: row.week_no,
    week_start_date: row.week_start_date,
    week_end_date: row.week_end_date,
    unit_slot: row.unit_slot,
    schedule_type: row.schedule_type,
    schedule_value: row.schedule_value,
  };
}

function defaultValueFor(type: RollingWeek['schedule_type'], current: string): string {
  if (type === 'BREAK') return 'BREAK';
  if (type === 'ASSESSMENT_WEEK') return 'ASSESSMENT WEEK';
  if (current.toUpperCase() === 'BREAK' || current.toUpperCase() === 'ASSESSMENT WEEK') return '';
  return current;
}

export function RollingIntakePanel({
  selection,
  intakeLabel,
  onOpenChange,
  onSaved,
}: {
  selection: RollingSelection;
  intakeLabel: string | null;
  onOpenChange: (open: boolean) => void;
  onSaved?: () => void;
}) {
  const { user, permissions } = useAuth();
  const canEdit = permissions.maintainTimetable;
  const [rows, setRows] = React.useState<DraftRow[]>([]);
  const [original, setOriginal] = React.useState<DraftRow[]>([]);
  const [meta, setMeta] = React.useState<Pick<RollingWeek, 'qualification_code' | 'duration_weeks' | 'intake_group'> | null>(
    null,
  );
  const [loading, setLoading] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!intakeLabel) {
      setRows([]);
      setOriginal([]);
      setMeta(null);
      return;
    }
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const result = await rollingTimetableApi.listWeeks({
          trainingPackage: selection.trainingPackage,
          qualificationCode: selection.qualificationCode,
          durationWeeks: selection.durationWeeks,
          intakeLabel,
          limit: 2000,
          offset: 0,
          sort: 'week_no',
          direction: 'asc',
        });
        const draft = result.items.map(toDraft);
        setRows(draft);
        setOriginal(draft);
        const first = result.items[0];
        setMeta(
          first
            ? {
                qualification_code: first.qualification_code,
                duration_weeks: first.duration_weeks,
                intake_group: first.intake_group,
              }
            : null,
        );
      } catch (caught) {
        setError(caught instanceof ReferenceApiError ? caught.message : 'This intake could not be loaded.');
        setRows([]);
        setOriginal([]);
      } finally {
        setLoading(false);
      }
    })();
  }, [intakeLabel, selection.trainingPackage, selection.qualificationCode, selection.durationWeeks]);

  if (!intakeLabel) return null;

  const dirty = rows.some((row, index) => {
    const before = original[index];
    return !before || row.schedule_type !== before.schedule_type || row.schedule_value !== before.schedule_value;
  });

  async function save() {
    const items: RollingWeekPatchItem[] = rows.map((row) => ({
      id: row.id,
      schedule_type: row.schedule_type,
      schedule_value: row.schedule_value,
    }));
    setSaving(true);
    try {
      const result = await rollingTimetableApi.updateWeeks(items);
      const draft = result.items.map(toDraft);
      setRows(draft);
      setOriginal(draft);
      toast.success('Intake weeks were updated.');
      onSaved?.();
    } catch (caught) {
      toast.error(caught instanceof ReferenceApiError ? caught.message : 'The intake could not be saved.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet open onOpenChange={onOpenChange}>
      <SheetContent width="xl">
        <SheetHeader>
          <SheetTitle>{intakeLabel}</SheetTitle>
          <SheetDescription>
            {meta
              ? `${meta.qualification_code} · ${meta.duration_weeks} weeks · ${meta.intake_group}`
              : `${selection.qualificationCode} · ${selection.durationWeeks} weeks`}
          </SheetDescription>
        </SheetHeader>
        <SheetBody className="space-y-4">
          {!canEdit && <ReadOnlyNotice message={readOnlyReason(user, INTERFACE_NAMES.timetable)} />}
          {loading ? (
            <LoadingState label="Loading this intake…" />
          ) : error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">This intake has no stored weeks.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full border-collapse text-[13px]">
                <thead className="bg-muted/70">
                  <tr>
                    <th className="border-b border-border px-3 py-2 text-left font-medium">Week</th>
                    <th className="border-b border-border px-3 py-2 text-left font-medium">Dates</th>
                    <th className="border-b border-border px-3 py-2 text-left font-medium">Slot</th>
                    <th className="border-b border-border px-3 py-2 text-left font-medium">Type</th>
                    <th className="border-b border-border px-3 py-2 text-left font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={row.id} className="border-b border-border">
                      <td className="px-3 py-2 align-middle tabular">{row.week_no}</td>
                      <td className="px-3 py-2 align-middle text-muted-foreground">
                        {formatDate(row.week_start_date)} – {formatDate(row.week_end_date)}
                      </td>
                      <td className="px-3 py-2 align-middle">{row.unit_slot}</td>
                      <td className="px-3 py-2 align-middle">
                        {canEdit ? (
                          <SimpleSelect
                            value={row.schedule_type}
                            onChange={(value) => {
                              const type = value as RollingWeek['schedule_type'];
                              setRows((current) =>
                                current.map((item, i) =>
                                  i === index
                                    ? {
                                        ...item,
                                        schedule_type: type,
                                        schedule_value: defaultValueFor(type, item.schedule_value),
                                      }
                                    : item,
                                ),
                              );
                            }}
                            options={TYPE_OPTIONS}
                            placeholder="Type"
                          />
                        ) : (
                          scheduleTypeLabel(row.schedule_type)
                        )}
                      </td>
                      <td className="px-3 py-2 align-middle">
                        {canEdit ? (
                          <Input
                            value={row.schedule_value}
                            onChange={(event) => {
                              const next = event.target.value;
                              setRows((current) =>
                                current.map((item, i) => (i === index ? { ...item, schedule_value: next } : item)),
                              );
                            }}
                            aria-label={`Value for week ${row.week_no}`}
                          />
                        ) : (
                          row.schedule_value
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SheetBody>
        <SheetFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {canEdit && (
            <Button onClick={() => void save()} disabled={!dirty || saving || loading || rows.length === 0}>
              {saving ? 'Saving…' : 'Save intake'}
            </Button>
          )}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
