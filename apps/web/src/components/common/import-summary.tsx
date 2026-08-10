import * as React from 'react';

import { cn } from '@/lib/utils';
import type { ImportResult } from '@/types/import';

interface CountTileProps {
  label: string;
  value: number;
  tone?: 'default' | 'success' | 'warning' | 'destructive' | 'muted';
}

const TONE_CLASS: Record<NonNullable<CountTileProps['tone']>, string> = {
  default: 'border-border bg-card text-foreground',
  success: 'border-success/25 bg-success-soft text-success',
  warning: 'border-warning/30 bg-warning-soft text-warning',
  destructive: 'border-destructive/25 bg-destructive-soft text-destructive',
  muted: 'border-border bg-muted/50 text-muted-foreground',
};

export function CountTile({ label, value, tone = 'default' }: CountTileProps) {
  return (
    <div className={cn('rounded-lg border px-4 py-3', TONE_CLASS[tone])}>
      <p className="text-2xl font-semibold tabular leading-none">{value}</p>
      <p className="mt-1.5 text-[12px] font-medium">{label}</p>
    </div>
  );
}

/** BULK-09: the result must report inserted, excluded, duplicate, corrected, rejected and unmatched counts. */
export function ImportSummary({ result, className }: { result: ImportResult; className?: string }) {
  return (
    <div className={cn('grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6', className)}>
      <CountTile label="Inserted" value={result.inserted} tone="success" />
      <CountTile label="Excluded" value={result.excluded} tone="muted" />
      <CountTile label="Duplicate" value={result.duplicate} tone="destructive" />
      <CountTile label="Corrected" value={result.corrected} tone="default" />
      <CountTile label="Rejected" value={result.rejected} tone="warning" />
      <CountTile label="Unmatched" value={result.unmatched} tone="destructive" />
    </div>
  );
}
