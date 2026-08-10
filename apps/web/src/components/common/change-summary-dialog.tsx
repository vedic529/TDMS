'use client';

import * as React from 'react';
import { ArrowRight, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { EmptyState } from './states';
import { RecordSummary } from './preview-panel';
import type { FieldChange } from '@/types/common';

interface ChangeSummaryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  record: { primary: string; secondary?: string; lines?: string[] };
  changes: FieldChange[];
  onConfirm: () => void | Promise<void>;
  busy?: boolean;
  confirmLabel?: string;
}

/**
 * SST-07 / SRS 2.3: when an existing record is edited, the confirmation must
 * identify the record and the fields that will change.
 */
export function ChangeSummaryDialog({
  open,
  onOpenChange,
  title,
  description,
  record,
  changes,
  onConfirm,
  busy,
  confirmLabel = 'Confirm Update',
}: ChangeSummaryDialogProps) {
  return (
    <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <RecordSummary primary={record.primary} secondary={record.secondary} lines={record.lines} />

          {changes.length === 0 ? (
            <EmptyState
              title="No field has changed"
              description="Close this dialog and edit a value before confirming an update."
            />
          ) : (
            <div className="space-y-2">
              <p className="text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
                {changes.length} {changes.length === 1 ? 'field will change' : 'fields will change'}
              </p>
              <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
                {changes.map((change) => (
                  <li key={change.field} className="grid gap-1 px-4 py-3 sm:grid-cols-[minmax(0,14rem)_1fr]">
                    <p className="text-[13px] font-medium text-foreground">{change.label}</p>
                    <div className="flex flex-wrap items-center gap-2 text-[13px]">
                      <span className="rounded bg-muted px-2 py-0.5 text-muted-foreground line-through decoration-muted-foreground/50">
                        {change.oldValue || '—'}
                      </span>
                      <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden="true" />
                      <span className="rounded bg-primary-soft px-2 py-0.5 font-medium text-primary">
                        {change.newValue || '—'}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => void onConfirm()} disabled={busy || changes.length === 0}>
            {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Builds a change list from two records using a labelled field map. */
export function buildChanges<T extends Record<string, unknown>>(
  before: T,
  after: T,
  fields: Array<{ key: keyof T & string; label: string; format?: (value: unknown) => string }>,
): FieldChange[] {
  const changes: FieldChange[] = [];
  for (const field of fields) {
    const format = field.format ?? ((value: unknown) => (value === null || value === undefined ? '' : String(value)));
    const oldValue = format(before[field.key]);
    const newValue = format(after[field.key]);
    if (oldValue !== newValue) {
      changes.push({ field: field.key, label: field.label, oldValue, newValue });
    }
  }
  return changes;
}
