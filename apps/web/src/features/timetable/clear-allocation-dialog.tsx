'use client';

import * as React from 'react';
import { Loader2, Trash2, TriangleAlert } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { allocationApi, type ClearAllocationCounts } from '@/services/allocation-api';

/** Typed to confirm. An irreversible bulk delete should not turn on one click. */
const CONFIRM_WORD = 'CLEAR';

/**
 * Clear the allocation records — Super Admin only.
 *
 * Irreversible, so the dialog states the real counts fetched before anything is
 * deleted, names what is deliberately left alone, and requires the word to be
 * typed. There is no recycle area: these rows are the product of a re-runnable
 * import, and the remedy is to import the file again.
 */
export function ClearAllocationDialog({ onCleared }: { onCleared: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [counts, setCounts] = React.useState<ClearAllocationCounts | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [typed, setTyped] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);

  // The counts are fetched when the dialog opens, so the decision is made
  // against what is actually there rather than a vague warning.
  React.useEffect(() => {
    if (!open) return;
    setTyped('');
    setError(null);
    setLoading(true);
    void allocationApi
      .clearPreview()
      .then(setCounts)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : 'The counts could not be loaded.'),
      )
      .finally(() => setLoading(false));
  }, [open]);

  const total = counts
    ? counts.deliveries + counts.sessions + counts.intake_links + counts.import_batches
    : 0;
  const confirmed = typed.trim().toUpperCase() === CONFIRM_WORD;

  async function clear() {
    setBusy(true);
    try {
      const removed = await allocationApi.clearRecords();
      toast.success('Allocation records cleared', {
        description: `${removed.deliveries} deliveries, ${removed.sessions} sessions and ${
          removed.suggestions + removed.exceptions + removed.resolved_suggestions
        } allocation suggestions were removed. The rolling timetable and student records were not affected.`,
      });
      setOpen(false);
      onCleared();
    } catch (caught) {
      toast.error('The allocation records could not be cleared', {
        description: caught instanceof Error ? caught.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button type="button" variant="outline" onClick={() => setOpen(true)}>
        <Trash2 aria-hidden="true" />
        Clear Database
      </Button>

      <Dialog open={open} onOpenChange={busy ? undefined : setOpen}>
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>Clear the allocation records?</DialogTitle>
            <DialogDescription>
              This removes every allocation record and starts the Allocation Records tab from empty.
              It cannot be undone.
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-4">
            {loading ? (
              <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                Counting what would be removed…
              </p>
            ) : error ? (
              <p className="text-[13px] text-destructive">{error}</p>
            ) : counts ? (
              <>
                <div className="rounded-md border border-destructive/30 bg-destructive-soft p-3">
                  <p className="mb-2 flex items-center gap-1.5 text-[13px] font-medium text-destructive">
                    <TriangleAlert aria-hidden="true" className="size-4" />
                    This will permanently delete
                  </p>
                  <dl className="space-y-1 text-[13px]">
                    {[
                      ['Deliveries', counts.deliveries],
                      ['Class sessions', counts.sessions],
                      ['Intake links', counts.intake_links],
                      ['Import batches', counts.import_batches],
                      ['Source rows', counts.source_rows],
                      ['Pending suggestions', counts.suggestions],
                      ['Accepted exceptions', counts.exceptions],
                      ['Resolved suggestions', counts.resolved_suggestions],
                    ].map(([label, value]) => (
                      <div key={String(label)} className="flex gap-2">
                        <dt className="w-44 text-muted-foreground">{label}:</dt>
                        <dd className="font-medium tabular">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>

                {/* Naming what survives is as important as naming what goes. */}
                <div className="rounded-md border border-border bg-muted/40 p-3 text-[13px]">
                  <p className="mb-1 font-medium">This will not be touched</p>
                  <ul className="list-inside list-disc space-y-0.5 text-muted-foreground">
                    <li>The rolling timetable — every student&apos;s intake still resolves.</li>
                    <li>Student records and their groups.</li>
                    <li>Suggestions raised by the rolling timetable or student imports.</li>
                    <li>College, campus, qualification, unit, facility and trainer reference data.</li>
                  </ul>
                </div>

                <div className="space-y-1.5">
                  <label htmlFor="clear-confirm" className="text-[13px] font-medium">
                    Type <span className="font-mono">{CONFIRM_WORD}</span> to confirm
                  </label>
                  <Input
                    id="clear-confirm"
                    value={typed}
                    onChange={(event) => setTyped(event.target.value)}
                    placeholder={CONFIRM_WORD}
                    autoComplete="off"
                    aria-describedby="clear-confirm-hint"
                  />
                  <p id="clear-confirm-hint" className="text-[12px] text-muted-foreground">
                    {total === 0
                      ? 'There is nothing to clear.'
                      : 'There is no recycle area for these rows. Re-import the allocation file to restore them.'}
                  </p>
                </div>
              </>
            ) : null}
          </DialogBody>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => void clear()}
              disabled={!confirmed || busy || loading || total === 0}
            >
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Trash2 aria-hidden="true" />}
              Clear the allocation records
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
