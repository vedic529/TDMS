'use client';

import * as React from 'react';
import { Loader2, Trash2, Undo2 } from 'lucide-react';

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
import { Textarea } from '@/components/ui/textarea';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { FormField } from './form-field';
import { SimpleSelect } from './dependent-select';
import { RecordSummary } from './preview-panel';
import { PROPOSED_RECYCLE_PERIOD_DAYS, reasonsFor, type ReasonContext } from '@/lib/reasons';
import type { ReasonCode } from '@/types/common';

interface DeleteConfirmationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Identity of the record being removed, always displayed (SRS 2.3). */
  record: { primary: string; secondary?: string; lines?: string[] };
  reasonContext: ReasonContext;
  onConfirm: (reason: ReasonCode, reasonDetail?: string) => void | Promise<void>;
  busy?: boolean;
  /** Switches the dialog to restore wording. */
  mode?: 'delete' | 'restore';
  title?: string;
  recordTypeLabel: string;
}

/**
 * Delete and restore confirmation.
 *
 * SRS 2.3 / LOG-03: the selected record is shown, a reason must be chosen from
 * the approved list, and an "Other" reason requires a written explanation.
 * Normal deletion is soft deletion into the recycle area.
 */
export function DeleteConfirmationDialog({
  open,
  onOpenChange,
  record,
  reasonContext,
  onConfirm,
  busy,
  mode = 'delete',
  title,
  recordTypeLabel,
}: DeleteConfirmationDialogProps) {
  const [reason, setReason] = React.useState<string>('');
  const [detail, setDetail] = React.useState('');
  const [touched, setTouched] = React.useState(false);

  React.useEffect(() => {
    if (open) {
      setReason('');
      setDetail('');
      setTouched(false);
    }
  }, [open]);

  const options = React.useMemo(
    () => reasonsFor(mode === 'restore' ? 'restore' : reasonContext).map((entry) => ({ value: entry.value, label: entry.label })),
    [reasonContext, mode],
  );

  const requiresDetail = reason === 'OTHER';
  const detailMissing = requiresDetail && detail.trim().length === 0;
  const reasonMissing = reason === '';
  const canConfirm = !reasonMissing && !detailMissing;

  const isDelete = mode === 'delete';
  const heading = title ?? (isDelete ? `Delete ${recordTypeLabel}?` : `Restore ${recordTypeLabel}?`);

  return (
    <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle className={isDelete ? 'text-destructive' : undefined}>{heading}</DialogTitle>
          <DialogDescription>
            {isDelete
              ? 'Check the record below, then select an approved reason. The record is moved to the recycle area and removed from active use.'
              : 'Check the record below, then select an approved reason. The record is returned to active use.'}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <RecordSummary primary={record.primary} secondary={record.secondary} lines={record.lines} />

          <FormField
            label="Reason"
            htmlFor="delete-reason"
            required
            hint="The approved reason list is proposed in the SRS and is subject to approval (OD-06)."
            error={touched && reasonMissing ? 'Select a reason before continuing.' : undefined}
          >
            <SimpleSelect
              id="delete-reason"
              value={reason}
              onChange={setReason}
              options={options}
              placeholder="Select reason"
            />
          </FormField>

          {requiresDetail && (
            <FormField
              label="Additional explanation"
              htmlFor="delete-reason-detail"
              required
              hint='An "Other" reason requires a written explanation.'
              error={touched && detailMissing ? 'Enter a written explanation for the "Other" reason.' : undefined}
            >
              <Textarea
                id="delete-reason-detail"
                value={detail}
                onChange={(event) => setDetail(event.target.value)}
                placeholder="Explain why this action is required."
              />
            </FormField>
          )}

          <Alert variant={isDelete ? 'destructive' : 'info'}>
            {isDelete ? <Trash2 aria-hidden="true" /> : <Undo2 aria-hidden="true" />}
            <AlertDescription>
              {isDelete
                ? `This record will be moved to the recycle area and removed from active use. The proposed recovery period is ${PROPOSED_RECYCLE_PERIOD_DAYS} days and remains subject to approval. The record is not permanently deleted.`
                : 'This record will be returned to active use and will appear again in normal results.'}
            </AlertDescription>
          </Alert>
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant={isDelete ? 'destructive' : 'default'}
            onClick={() => {
              setTouched(true);
              if (!canConfirm) return;
              void onConfirm(reason as ReasonCode, requiresDetail ? detail.trim() : undefined);
            }}
            disabled={busy}
          >
            {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
            {isDelete ? 'Confirm Delete' : 'Confirm Restore'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
