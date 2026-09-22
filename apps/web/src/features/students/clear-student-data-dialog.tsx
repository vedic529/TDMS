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
import { studentsApi, type ClearStudentCounts } from '@/services/students-api';

/** Typed to confirm. An irreversible bulk delete should not turn on one click. */
const CONFIRM_WORD = 'CLEAR';

/**
 * Clear the student records - Super Admin only (approved 21 September 2026).
 *
 * Irreversible and outside the recycle area: the recycle area belongs to the
 * per-student Delete button, and this removes those records too. The dialog
 * states the real counts fetched before anything is deleted, names what is left
 * alone, and requires the word to be typed.
 */
export function ClearStudentDataDialog({ onCleared }: { onCleared: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [counts, setCounts] = React.useState<ClearStudentCounts | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [typed, setTyped] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    setTyped('');
    setError(null);
    setLoading(true);
    void studentsApi
      .clearPreview()
      .then(setCounts)
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'The counts could not be loaded.'))
      .finally(() => setLoading(false));
  }, [open]);

  const confirmed = typed.trim().toUpperCase() === CONFIRM_WORD;
  const nothingStored =
    counts !== null &&
    counts.students + counts.deleted_students + counts.intakes + counts.import_batches === 0;

  async function clear() {
    setBusy(true);
    try {
      const removed = await studentsApi.clearRecords();
      toast.success('Student records cleared', {
        description:
          `${removed.students + removed.deleted_students} student record(s), ${removed.intakes} intake(s) and ` +
          `${removed.import_batches} import(s) were removed. The rolling timetable, trainer data and ` +
          'allocation records were not affected.',
      });
      setOpen(false);
      onCleared();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The student records could not be cleared.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button variant="destructive" size="sm" onClick={() => setOpen(true)}>
        <Trash2 aria-hidden="true" />
        Clear Database
      </Button>

      <Dialog open={open} onOpenChange={busy ? undefined : setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <TriangleAlert aria-hidden="true" className="size-4 text-destructive" />
              Clear the student records?
            </DialogTitle>
            <DialogDescription>
              Every student record is deleted outright. There is no recycle area for this: the records in the
              recycle area are deleted too, and nothing can be restored afterwards.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            {loading ? (
              <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                Counting what would be removed…
              </p>
            ) : counts ? (
              <>
                <dl className="divide-y divide-border rounded-md border border-border text-[13px]">
                  {[
                    { label: 'Student records', value: counts.students },
                    { label: 'In the recycle area', value: counts.deleted_students },
                    { label: 'Intakes held for them', value: counts.intakes },
                    { label: 'Student imports', value: counts.import_batches },
                    { label: 'Uploaded rows kept with those imports', value: counts.staged_rows },
                  ].map((line) => (
                    <div key={line.label} className="flex items-baseline justify-between gap-3 px-3 py-1.5">
                      <dt className="text-muted-foreground">{line.label}</dt>
                      <dd className="tabular font-medium">{line.value.toLocaleString()}</dd>
                    </div>
                  ))}
                </dl>
                <p className="text-[12px] text-muted-foreground">
                  Suggestions left with no record behind them are closed automatically. The rolling timetable,
                  trainer data, allocation records and reference data are not touched.
                </p>
              </>
            ) : null}
            {error && <p className="text-[13px] text-destructive">{error}</p>}
            {!nothingStored && (
              <div className="space-y-1">
                <label className="text-[12px] font-medium text-muted-foreground" htmlFor="clear-students-confirm">
                  Type {CONFIRM_WORD} to confirm
                </label>
                <Input
                  id="clear-students-confirm"
                  value={typed}
                  onChange={(event) => setTyped(event.target.value)}
                  autoComplete="off"
                  disabled={busy}
                />
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => void clear()}
              disabled={busy || loading || !confirmed || nothingStored}
            >
              {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
              Clear student records
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
