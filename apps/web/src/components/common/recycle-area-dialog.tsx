'use client';

import * as React from 'react';
import { RotateCcw, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { DataTable, type DataTableColumn } from './data-table';
import { DeleteConfirmationDialog } from './delete-confirmation-dialog';
import { EmptyState } from './states';
import { PROPOSED_RECYCLE_PERIOD_DAYS, reasonLabel } from '@/lib/reasons';
import { formatDate, formatDateTime } from '@/lib/format';
import type { ReasonCode, SoftDeletable } from '@/types/common';
import type { ReasonContext } from '@/lib/reasons';

interface RecycleAreaDialogProps<T extends SoftDeletable> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  recordTypeLabel: string;
  reasonContext: ReasonContext;
  rows: T[];
  loading: boolean;
  rowKey: (row: T) => string;
  /** Columns identifying the record; deletion columns are appended. */
  columns: DataTableColumn<T>[];
  describe: (row: T) => { primary: string; secondary?: string; lines?: string[] };
  canRestore: boolean;
  onRestore: (row: T, reason: ReasonCode, reasonDetail?: string) => Promise<void>;
}

/**
 * SRS 2.3 / DATA-04: soft-deleted records are held in a recycle area with the
 * deletion date, deleting user, reason and recovery deadline. Restoring also
 * requires confirmation and a reason (LOG-03).
 */
export function RecycleAreaDialog<T extends SoftDeletable>({
  open,
  onOpenChange,
  title,
  recordTypeLabel,
  reasonContext,
  rows,
  loading,
  rowKey,
  columns,
  describe,
  canRestore,
  onRestore,
}: RecycleAreaDialogProps<T>) {
  const [selected, setSelected] = React.useState<T | null>(null);
  const [busy, setBusy] = React.useState(false);

  const allColumns: DataTableColumn<T>[] = [
    ...columns,
    {
      id: 'deletedAt',
      header: 'Deleted',
      cell: (row) => formatDateTime(row.deletion?.deletedAt),
      sortValue: (row) => row.deletion?.deletedAt ?? '',
    },
    {
      id: 'deletedBy',
      header: 'Deleted by',
      cell: (row) => row.deletion?.deletedBy ?? '—',
    },
    {
      id: 'reason',
      header: 'Reason',
      cell: (row) => (
        <span className="block max-w-64 truncate" title={row.deletion?.deleteReasonDetail}>
          {reasonLabel(row.deletion?.deleteReason)}
          {row.deletion?.deleteReasonDetail ? ` — ${row.deletion.deleteReasonDetail}` : ''}
        </span>
      ),
    },
    {
      id: 'recoveryDeadline',
      header: 'Recovery deadline',
      cell: (row) => formatDate(row.deletion?.recoveryDeadline),
      sortValue: (row) => row.deletion?.recoveryDeadline ?? '',
    },
  ];

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent size="full">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>
              Records removed from active use. Nothing is permanently deleted by TDMS.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <Alert variant="info">
              <Trash2 aria-hidden="true" />
              <AlertDescription>
                The proposed recovery period is {PROPOSED_RECYCLE_PERIOD_DAYS} days from the deletion date and remains
                subject to approval (SRS 2.3). Restoring a record requires an approved reason and confirmation.
              </AlertDescription>
            </Alert>

            <DataTable
              ariaLabel={title}
              columns={allColumns}
              rows={rows}
              rowKey={rowKey}
              loading={loading}
              loadingLabel="Loading deleted records…"
              pageSize={8}
              empty={
                <EmptyState
                  title="The recycle area is empty"
                  description={`No ${recordTypeLabel.toLowerCase()} has been deleted.`}
                  icon={Trash2}
                />
              }
              rowActions={
                canRestore
                  ? (row) => (
                      <Button variant="outline" size="sm" onClick={() => setSelected(row)}>
                        <RotateCcw aria-hidden="true" />
                        Restore
                      </Button>
                    )
                  : undefined
              }
            />

            {!canRestore && rows.length > 0 && (
              <p className="text-[13px] text-muted-foreground">
                You can view deleted records. Restoring a record is outside your assigned work area.
              </p>
            )}
          </DialogBody>
        </DialogContent>
      </Dialog>

      {selected && (
        <DeleteConfirmationDialog
          open
          mode="restore"
          recordTypeLabel={recordTypeLabel}
          reasonContext={reasonContext}
          record={describe(selected)}
          busy={busy}
          onOpenChange={(next) => {
            if (!next) setSelected(null);
          }}
          onConfirm={async (reason, detail) => {
            setBusy(true);
            try {
              await onRestore(selected, reason, detail);
              setSelected(null);
            } finally {
              setBusy(false);
            }
          }}
        />
      )}
    </>
  );
}
