'use client';

import * as React from 'react';
import { Loader2, Pencil, Plus } from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SimpleSelect } from '@/components/common/dependent-select';
import { EmptyState } from '@/components/common/states';
import { plain } from '@/features/shared/suggestion-prefill';
import { ReferenceApiError, referenceApi, type ApiCampus, type ApiCity } from '@/services/reference-api';

/**
 * Add or edit one city in the City Dictionary (approved 15 September 2026).
 *
 * A city is a name, its state, and the campuses located in it. Campuses are
 * chosen from the ones already recorded in that state - a campus in Victoria
 * cannot belong to Sydney - and a campus belongs to one city, so choosing it here
 * moves it from any other.
 */
export function CityFormDialog({
  open,
  onOpenChange,
  editing,
  prefill,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing?: ApiCity | null;
  /** From a suggestion: the city as a file spelled it, and the campuses it was named for. */
  prefill?: { name?: string; campusNames?: string[] } | null;
  /** The saved city, so a suggestion can be resolved onto it. */
  onSaved: (city: ApiCity) => void;
}) {
  const [campuses, setCampuses] = React.useState<ApiCampus[]>([]);
  const [name, setName] = React.useState('');
  const [state, setState] = React.useState('');
  const [campusIds, setCampusIds] = React.useState<number[]>([]);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setName(editing?.city_name ?? prefill?.name ?? '');
    setState(editing?.state ?? '');
    setCampusIds(editing?.campuses.map((campus) => campus.id) ?? []);
    let cancelled = false;
    void referenceApi
      .listCampuses({ activeOnly: true })
      .then((rows) => {
        if (cancelled) return;
        setCampuses(rows);
        // From a suggestion: the campuses the city was named for, chosen, and
        // their state when they share one.
        const wanted = new Set((prefill?.campusNames ?? []).map(plain));
        if (!editing && wanted.size > 0) {
          const named = rows.filter(
            (campus) =>
              wanted.has(plain(campus.campus_name)) ||
              wanted.has(plain(campus.campus_location)) ||
              (campus.source_addresses ?? []).some((spelling) => wanted.has(plain(spelling))),
          );
          const states = Array.from(new Set(named.map((campus) => campus.state)));
          if (states.length === 1) {
            setState(states[0]);
            setCampusIds(named.map((campus) => campus.id));
          }
        }
      })
      .catch(() => {
        if (!cancelled) toast.error('The campuses could not be loaded');
      });
    return () => {
      cancelled = true;
    };
  }, [open, editing, prefill]);

  const stateOptions = React.useMemo(
    () =>
      Array.from(new Set(campuses.map((campus) => campus.state)))
        .sort()
        .map((value) => ({ value, label: value })),
    [campuses],
  );
  const inState = React.useMemo(
    () =>
      campuses
        .filter((campus) => campus.state === state)
        .sort((a, b) => a.campus_name.localeCompare(b.campus_name)),
    [campuses, state],
  );

  async function save() {
    setBusy(true);
    try {
      const body = {
        city_name: name.trim(),
        state,
        campus_ids: campusIds.filter((id) => inState.some((campus) => campus.id === id)),
      };
      const city = editing
        ? await referenceApi.updateCity(editing.id, body)
        : await referenceApi.createCity(body);
      toast.success(editing ? `${city.city_name} updated` : `${city.city_name} added to the City Dictionary`);
      onSaved(city);
      onOpenChange(false);
    } catch (caught) {
      toast.error('The city could not be saved', {
        description: caught instanceof ReferenceApiError ? caught.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{editing ? `Edit ${editing.city_name}` : 'Add city'}</DialogTitle>
          <DialogDescription>
            A city and the campuses located in it. A campus belongs to one city, so choosing it here moves it
            from any other.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="city-name">
                City name<span className="ml-0.5 text-destructive">*</span>
              </Label>
              <Input id="city-name" value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="city-state">
                State<span className="ml-0.5 text-destructive">*</span>
              </Label>
              <SimpleSelect
                value={state}
                onChange={(value) => setState(value)}
                options={stateOptions}
                placeholder="Choose the state"
              />
            </div>
          </div>
          <div className="space-y-1">
            <p className="text-[12px] font-medium text-muted-foreground">Campuses in this city</p>
            {!state ? (
              <p className="text-[12px] text-muted-foreground">Choose the state to see its campuses.</p>
            ) : inState.length === 0 ? (
              <p className="text-[12px] text-muted-foreground">No campus is recorded in {state}.</p>
            ) : (
              <ul className="max-h-56 space-y-0.5 overflow-y-auto rounded border border-border bg-background p-1">
                {inState.map((campus) => (
                  <li key={campus.id}>
                    <label className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-[12px] hover:bg-accent/50">
                      <input
                        type="checkbox"
                        checked={campusIds.includes(campus.id)}
                        onChange={(event) =>
                          setCampusIds((current) =>
                            event.target.checked
                              ? [...current, campus.id]
                              : current.filter((id) => id !== campus.id),
                          )
                        }
                      />
                      <span>
                        <span className="font-medium">{campus.campus_name}</span>
                        <span className="text-muted-foreground"> — {campus.campus_location}</span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={busy || !name.trim() || !state}>
            {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
            {editing ? 'Save city' : 'Add city'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Every city in the dictionary and its campuses, with add and edit. */
export function CityDictionaryDialog({
  open,
  onOpenChange,
  canMaintain,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canMaintain: boolean;
}) {
  const [cities, setCities] = React.useState<ApiCity[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [formOpen, setFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<ApiCity | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setCities(await referenceApi.listCities());
    } catch {
      setCities([]);
      toast.error('The City Dictionary could not be loaded');
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (open) void load();
  }, [open, load]);

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>City Dictionary</DialogTitle>
            <DialogDescription>
              The approved cities and the campuses located in each. A trainer&apos;s city is checked against it.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            {canMaintain && (
              <div className="flex justify-end">
                <Button
                  size="sm"
                  onClick={() => {
                    setEditing(null);
                    setFormOpen(true);
                  }}
                >
                  <Plus aria-hidden="true" />
                  Add city
                </Button>
              </div>
            )}
            {loading ? (
              <p className="flex items-center gap-2 py-6 text-[13px] text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                Loading…
              </p>
            ) : cities.length === 0 ? (
              <EmptyState
                title="No cities recorded"
                description="Add a city and choose the campuses located in it."
              />
            ) : (
              <ul className="space-y-2">
                {cities.map((city) => (
                  <li key={city.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2">
                    <span className="text-[13px] font-medium">{city.city_name}</span>
                    <Badge variant="neutral" className="text-[10px]">
                      {city.state}
                    </Badge>
                    <span className="flex flex-wrap gap-1">
                      {city.campuses.length === 0 ? (
                        <span className="text-[12px] text-muted-foreground">No campus assigned</span>
                      ) : (
                        city.campuses.map((campus) => (
                          <Badge key={campus.id} variant="outline" className="text-[10px]">
                            {campus.campus_name}
                          </Badge>
                        ))
                      )}
                    </span>
                    {canMaintain && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="ml-auto h-7 text-[12px]"
                        onClick={() => {
                          setEditing(city);
                          setFormOpen(true);
                        }}
                      >
                        <Pencil aria-hidden="true" className="size-3.5" />
                        Edit
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CityFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        editing={editing}
        onSaved={() => void load()}
      />
    </>
  );
}
