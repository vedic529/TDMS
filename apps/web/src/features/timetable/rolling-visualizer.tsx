'use client';

import * as React from 'react';

import { EmptyState, ErrorState, LoadingState } from '@/components/common/states';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';
import { ReferenceApiError } from '@/services/reference-api';
import { rollingTimetableApi, type VisualizerGrid } from '@/services/rolling-timetable-api';
import type { RollingSelection } from './rolling-scope-bar';
import { RollingIntakePanel } from './rolling-intake-panel';

const MIN_COL_WIDTH = 64;
const DEFAULT_WEEK_WIDTH = 84;
const DEFAULT_DATE_WIDTH = 112;
const DEFAULT_INTAKE_WIDTH = 168;

function displayCell(value: string): string {
  return value.trim().toUpperCase() === 'NA' ? '' : value;
}

function cellClass(value: string): string {
  const upper = value.trim().toUpperCase();
  if (!upper || upper === 'NA') return '';
  if (upper === 'BREAK') return 'bg-amber-50 text-amber-950';
  if (upper === 'ASSESSMENT WEEK') return 'bg-sky-50 text-sky-950 font-medium';
  return 'font-medium';
}

function ColumnResizeHandle({ onResize }: { onResize: (deltaX: number) => void }) {
  const startX = React.useRef(0);

  function onPointerDown(event: React.PointerEvent<HTMLSpanElement>) {
    event.preventDefault();
    event.stopPropagation();
    startX.current = event.clientX;
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);

    function onPointerMove(move: PointerEvent) {
      onResize(move.clientX - startX.current);
      startX.current = move.clientX;
    }

    function onPointerUp(up: PointerEvent) {
      target.releasePointerCapture(up.pointerId);
      target.removeEventListener('pointermove', onPointerMove);
      target.removeEventListener('pointerup', onPointerUp);
    }

    target.addEventListener('pointermove', onPointerMove);
    target.addEventListener('pointerup', onPointerUp);
  }

  return (
    <span
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize column"
      onPointerDown={onPointerDown}
      className="absolute inset-y-0 right-0 z-40 w-2 cursor-col-resize touch-none hover:bg-primary/25"
    />
  );
}

export function RollingVisualizer({ selection }: { selection: RollingSelection }) {
  const [grid, setGrid] = React.useState<VisualizerGrid | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [weekWidth, setWeekWidth] = React.useState(DEFAULT_WEEK_WIDTH);
  const [startWidth, setStartWidth] = React.useState(DEFAULT_DATE_WIDTH);
  const [endWidth, setEndWidth] = React.useState(DEFAULT_DATE_WIDTH);
  const [intakeWidths, setIntakeWidths] = React.useState<number[]>([]);
  const [selectedIntake, setSelectedIntake] = React.useState<string | null>(null);
  const [reloadToken, setReloadToken] = React.useState(0);

  React.useEffect(() => {
    setSelectedIntake(null);
    setGrid(null);
    setWeekWidth(DEFAULT_WEEK_WIDTH);
    setStartWidth(DEFAULT_DATE_WIDTH);
    setEndWidth(DEFAULT_DATE_WIDTH);
  }, [selection.trainingPackage, selection.qualificationCode, selection.durationWeeks]);

  React.useEffect(() => {
    const initial = grid === null;
    if (initial) {
      setError(null);
    }
    let cancelled = false;
    void (async () => {
      try {
        const next = await rollingTimetableApi.visualizer(
          selection.trainingPackage,
          selection.qualificationCode,
          selection.durationWeeks,
        );
        if (cancelled) return;
        setGrid(next);
        setIntakeWidths((current) => {
          if (current.length === next.intake_columns.length) return current;
          return next.intake_columns.map(() => DEFAULT_INTAKE_WIDTH);
        });
        setError(null);
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof ReferenceApiError ? caught.message : 'Visualizer could not be loaded.');
        if (initial) setGrid(null);
      }
    })();
    return () => {
      cancelled = true;
    };
    // grid is intentionally omitted so a refetch does not retrigger itself
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection.trainingPackage, selection.qualificationCode, selection.durationWeeks, reloadToken]);

  const clamp = (width: number) => Math.max(MIN_COL_WIDTH, Math.round(width));
  const startLeft = weekWidth;
  const endLeft = weekWidth + startWidth;
  const tableWidth = weekWidth + startWidth + endWidth + intakeWidths.reduce((sum, width) => sum + width, 0);

  function resizeIntake(index: number, deltaX: number) {
    setIntakeWidths((current) => current.map((width, i) => (i === index ? clamp(width + deltaX) : width)));
  }

  if (!grid) {
    if (error) return <ErrorState title="Visualizer could not be loaded" description={error} />;
    return <LoadingState label="Building the rolling grid from stored rows…" />;
  }
  if (grid.weeks.length === 0) {
    return (
      <EmptyState
        title="No stored weeks for this selection"
        description="The qualification has no rolling timetable rows."
      />
    );
  }

  const intakeCount = new Set(grid.intake_columns.map((column) => column.intake_label)).size;

  return (
    <div className="space-y-4">
      <p className="text-[12px] text-muted-foreground">
        {grid.weeks.length} weeks · {intakeCount} intakes · Unit {grid.counts.unit} · Break {grid.counts.break_count} ·
        Assessment Week {grid.counts.assessment_week}. Click an intake heading to open the full stack.
      </p>
      <div className="tdms-scrollbar max-h-[70vh] overflow-auto rounded-lg border border-border bg-card">
        <table className="border-collapse text-[11px]" style={{ tableLayout: 'fixed', width: tableWidth }}>
          <colgroup>
            <col style={{ width: weekWidth }} />
            <col style={{ width: startWidth }} />
            <col style={{ width: endWidth }} />
            {intakeWidths.map((width, index) => (
              <col key={grid.intake_columns[index]?.heading ?? index} style={{ width }} />
            ))}
          </colgroup>
          <thead className="sticky top-0 z-20 bg-muted">
            <tr>
              <th
                className="sticky z-30 relative border-b border-r border-border bg-muted px-2 py-1.5 text-left font-medium"
                style={{ left: 0, width: weekWidth, minWidth: weekWidth, maxWidth: weekWidth }}
              >
                <span className="block pr-1 leading-tight break-words">Week No.</span>
                <ColumnResizeHandle onResize={(delta) => setWeekWidth((width) => clamp(width + delta))} />
              </th>
              <th
                className="sticky z-30 relative border-b border-r border-border bg-muted px-2 py-1.5 text-left font-medium"
                style={{ left: startLeft, width: startWidth, minWidth: startWidth, maxWidth: startWidth }}
              >
                <span className="block pr-1 leading-tight break-words">Start Date</span>
                <ColumnResizeHandle onResize={(delta) => setStartWidth((width) => clamp(width + delta))} />
              </th>
              <th
                className="sticky z-30 relative border-b border-r border-border bg-muted px-2 py-1.5 text-left font-medium shadow-[2px_0_4px_-2px_rgba(15,23,42,0.18)]"
                style={{ left: endLeft, width: endWidth, minWidth: endWidth, maxWidth: endWidth }}
              >
                <span className="block pr-1 leading-tight break-words">End Date</span>
                <ColumnResizeHandle onResize={(delta) => setEndWidth((width) => clamp(width + delta))} />
              </th>
              {grid.intake_columns.map((column, index) => {
                const selected = selectedIntake === column.intake_label;
                return (
                  <th
                    key={`${column.intake_label}-${column.unit_slot}`}
                    className={cn(
                      'relative border-b border-r border-border px-2 py-1.5 text-left font-medium align-bottom',
                      selected && 'bg-primary-soft',
                    )}
                    style={{
                      width: intakeWidths[index],
                      minWidth: intakeWidths[index],
                      maxWidth: intakeWidths[index],
                    }}
                    title={column.heading}
                    aria-selected={selected}
                  >
                    <button
                      type="button"
                      className="block w-full pr-1 text-left leading-tight break-words [overflow-wrap:anywhere] hover:underline"
                      onClick={() => setSelectedIntake(column.intake_label)}
                    >
                      {column.heading}
                    </button>
                    <ColumnResizeHandle onResize={(delta) => resizeIntake(index, delta)} />
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {grid.weeks.map((week, weekIndex) => (
              <tr key={week.week_no}>
                <td
                  className="sticky z-10 border-b border-r border-border bg-card px-2 py-1 align-top"
                  style={{ left: 0, width: weekWidth, minWidth: weekWidth, maxWidth: weekWidth }}
                >
                  <span className="block leading-tight break-words">{week.week_no}</span>
                </td>
                <td
                  className="sticky z-10 border-b border-r border-border bg-card px-2 py-1 align-top"
                  style={{ left: startLeft, width: startWidth, minWidth: startWidth, maxWidth: startWidth }}
                >
                  <span className="block leading-tight break-words">{formatDate(week.week_start_date)}</span>
                </td>
                <td
                  className="sticky z-10 border-b border-r border-border bg-card px-2 py-1 align-top shadow-[2px_0_4px_-2px_rgba(15,23,42,0.18)]"
                  style={{ left: endLeft, width: endWidth, minWidth: endWidth, maxWidth: endWidth }}
                >
                  <span className="block leading-tight break-words">{formatDate(week.week_end_date)}</span>
                </td>
                {grid.grid[weekIndex]?.map((value, intakeIndex) => {
                  const column = grid.intake_columns[intakeIndex];
                  const selected = Boolean(column && selectedIntake === column.intake_label);
                  return (
                    <td
                      key={`${week.week_no}-${column?.heading ?? intakeIndex}`}
                      className={cn(
                        'border-b border-r border-border px-2 py-1 align-top leading-tight break-words [overflow-wrap:anywhere]',
                        cellClass(value),
                        selected && 'bg-primary-soft/70',
                        column && 'cursor-pointer',
                      )}
                      style={{
                        width: intakeWidths[intakeIndex],
                        minWidth: intakeWidths[intakeIndex],
                        maxWidth: intakeWidths[intakeIndex],
                      }}
                      onClick={() => column && setSelectedIntake(column.intake_label)}
                    >
                      {displayCell(value)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <RollingIntakePanel
        selection={selection}
        intakeLabel={selectedIntake}
        onOpenChange={(open) => {
          if (!open) setSelectedIntake(null);
        }}
        onSaved={() => setReloadToken((value) => value + 1)}
      />
    </div>
  );
}
