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
import { trainersApi, type ClearTrainersCounts } from '@/services/trainers-api';

/** Typed to confirm. An irreversible bulk delete should not turn on one click. */
const CONFIRM_WORD = 'CLEAR';

/**
 * Clear the trainer database — Super Admin only.
 *
 * Irreversible, so the dialog states the real counts fetched before anything is
 * deleted and names what happens to the rest of the system. The two facts that
 * matter and are easy to get wrong:
 *
 * * The timetable **keeps every trainer's name**. Allocation sessions hold it as
 *   text beside the link, so clearing releases the link and the session reads as
 *   an unresolved trainer — a suggestion is raised for each name so it is not
 *   quietly forgotten, and resolving it re-links the sessions.
 * * Numbering **restarts at TI_001**, because the sequence is read from the
 *   table and the table is now empty.
 */
export function ClearTrainersDialog({ onCleared }: { onCleared: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [counts, setCounts] = React.useState<ClearTrainersCounts | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [typed, setTyped] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);

  // Fetched when the dialog opens, so the decision is made against what is
  // actually there rather than a vague warning.
  React.useEffect(() => {
    if (!open) return;
    setTyped('');
    setError(null);
    setLoading(true);
    void trainersApi
      .clearPreview()
      .then(setCounts)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : 'The counts could not be loaded.'),
      )
      .finally(() => setLoading(false));
  }, [open]);

  const total = counts ? counts.trainers : 0;
  const confirmed = typed.trim().toUpperCase() === CONFIRM_WORD;

  async function clear() {
    setBusy(true);
    try {
      const removed = await trainersApi.clearRecords();
      toast.success('Trainer database cleared', {
        description:
          `${removed.trainers} trainer(s), ${removed.locations} location(s) and ` +
          `${removed.unit_links} unit link(s) removed. ` +
          `${removed.allocation_sessions_unlinked} allocation session(s) kept their trainer name ` +
          `as ${removed.trainer_suggestions_raised} suggestion(s). Numbering restarts at TI_001.`,
      });
      setOpen(false);
      onCleared();
    } catch (caught) {
      toast.error('The trainer database could not be cleared', {
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
            <DialogTitle>Clear the trainer database?</DialogTitle>
            <DialogDescription>
              This removes every trainer record and starts the tab from empty. It cannot be undone.
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
                      ['Trainers', counts.trainers],
                      ['Locations', counts.locations],
                      ['Unit links', counts.unit_links],
                      ['Qualification links', counts.qualification_links],
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
                  <p className="mb-1 font-medium">What happens to the rest</p>
                  <ul className="list-inside list-disc space-y-0.5 text-muted-foreground">
                    <li>
                      <span className="font-medium text-foreground">
                        {counts.allocation_sessions_unlinked} allocation session
                        {counts.allocation_sessions_unlinked === 1 ? '' : 's'}
                      </span>{' '}
                      keep the trainer&apos;s name and read as unresolved.{' '}
                      {counts.trainer_suggestions_raised} suggestion
                      {counts.trainer_suggestions_raised === 1 ? '' : 's'} will be raised so the
                      names are not forgotten — resolving one re-links its sessions.
                    </li>
                    <li>The rolling timetable and allocation records are otherwise untouched.</li>
                    <li>Students, campuses, qualifications and units are untouched.</li>
                    <li>
                      Trainer numbering <span className="font-medium text-foreground">restarts
                      at TI_001</span>.
                    </li>
                  </ul>
                </div>

                <div className="space-y-1.5">
                  <label htmlFor="clear-trainers-confirm" className="text-[13px] font-medium">
                    Type <span className="font-mono">{CONFIRM_WORD}</span> to confirm
                  </label>
                  <Input
                    id="clear-trainers-confirm"
                    value={typed}
                    onChange={(event) => setTyped(event.target.value)}
                    placeholder={CONFIRM_WORD}
                    autoComplete="off"
                    aria-describedby="clear-trainers-hint"
                  />
                  <p id="clear-trainers-hint" className="text-[12px] text-muted-foreground">
                    {total === 0
                      ? 'There is nothing to clear.'
                      : 'There is no recycle area for these rows. Re-import the trainer files to restore them.'}
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
              {busy ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : (
                <Trash2 aria-hidden="true" />
              )}
              Clear the trainer database
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
