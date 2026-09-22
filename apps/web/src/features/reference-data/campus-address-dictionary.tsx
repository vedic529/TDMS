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
import {
  ReferenceApiError,
  referenceApi,
  type ApiCampus,
  type ApiCampusAddress,
  type ApiCollege,
} from '@/services/reference-api';

/**
 * Add or edit one entry in the Campus Address Dictionary (approved 16 September 2026).
 *
 * The address belongs to a college at a campus, not to the campus: Haymarket is
 * 8 Quay St for REACH and NPA but 841 George St for AIBT and BIC. Editing keeps
 * the college and campus fixed; a different pair is a different entry.
 */
function CampusAddressFormDialog({
  open,
  onOpenChange,
  editing,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: ApiCampusAddress | null;
  onSaved: () => void;
}) {
  const [colleges, setColleges] = React.useState<ApiCollege[]>([]);
  const [campuses, setCampuses] = React.useState<ApiCampus[]>([]);
  const [collegeId, setCollegeId] = React.useState('');
  const [campusId, setCampusId] = React.useState('');
  const [address, setAddress] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setCollegeId(editing ? String(editing.college_id) : '');
    setCampusId(editing ? String(editing.campus_id) : '');
    setAddress(editing?.address ?? '');
    if (editing) return;
    let cancelled = false;
    void Promise.all([
      referenceApi.listColleges({ activeOnly: true }),
      referenceApi.listCampuses({ activeOnly: true }),
    ])
      .then(([collegeRows, campusRows]) => {
        if (cancelled) return;
        setColleges(collegeRows);
        setCampuses(campusRows);
      })
      .catch(() => {
        if (!cancelled) toast.error('The colleges and campuses could not be loaded');
      });
    return () => {
      cancelled = true;
    };
  }, [open, editing]);

  async function save() {
    setBusy(true);
    try {
      const body = { college_id: Number(collegeId), campus_id: Number(campusId), address: address.trim() };
      const saved = editing
        ? await referenceApi.updateCampusAddress(body)
        : await referenceApi.createCampusAddress(body);
      toast.success(
        `${saved.college_short_name} / ${saved.campus_name} ${editing ? 'updated' : 'added to the Address Dictionary'}`,
      );
      onSaved();
      onOpenChange(false);
    } catch (caught) {
      toast.error('The address could not be saved', {
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
          <DialogTitle>
            {editing ? `Edit ${editing.college_short_name} / ${editing.campus_name}` : 'Add campus address'}
          </DialogTitle>
          <DialogDescription>
            A full address is identified by the college and the campus together. Several colleges can share one
            building; an address already recorded for a different campus is refused.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3">
          {!editing && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label>
                  College<span className="ml-0.5 text-destructive">*</span>
                </Label>
                <SimpleSelect
                  value={collegeId}
                  onChange={setCollegeId}
                  options={colleges.map((college) => ({
                    value: String(college.id),
                    label: college.college_short_name,
                  }))}
                  placeholder="Choose the college"
                />
              </div>
              <div className="space-y-1">
                <Label>
                  Campus<span className="ml-0.5 text-destructive">*</span>
                </Label>
                <SimpleSelect
                  value={campusId}
                  onChange={setCampusId}
                  options={campuses.map((campus) => ({
                    value: String(campus.id),
                    label: `${campus.campus_name} (${campus.state})`,
                  }))}
                  placeholder="Choose the campus"
                />
              </div>
            </div>
          )}
          <div className="space-y-1">
            <Label htmlFor="campus-address">
              Full address<span className="ml-0.5 text-destructive">*</span>
            </Label>
            <Input
              id="campus-address"
              value={address}
              onChange={(event) => setAddress(event.target.value)}
              placeholder="e.g. Level 2, 8 Quay St, HAYMARKET, New South Wales 2000"
              autoComplete="off"
            />
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={busy || !collegeId || !campusId || !address.trim()}>
            {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
            {editing ? 'Save address' : 'Add address'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Every college/campus combination and its full address, with add and edit. */
export function CampusAddressDictionaryDialog({
  open,
  onOpenChange,
  canMaintain,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canMaintain: boolean;
}) {
  const [entries, setEntries] = React.useState<ApiCampusAddress[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [search, setSearch] = React.useState('');
  const [formOpen, setFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<ApiCampusAddress | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setEntries(await referenceApi.listCampusAddresses());
    } catch {
      setEntries([]);
      toast.error('The Address Dictionary could not be loaded');
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const shown = React.useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return entries;
    return entries.filter((entry) =>
      [entry.state, entry.campus_name, entry.college_short_name, entry.address ?? '']
        .join(' ')
        .toLowerCase()
        .includes(term),
    );
  }, [entries, search]);

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent size="xl">
          <DialogHeader>
            <DialogTitle>Address Dictionary</DialogTitle>
            <DialogDescription>
              The full address of each college at each campus. The college and campus together identify the
              address, so one campus name can be a different building for each college.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search state, campus, college or address"
                className="h-8 max-w-xs text-[13px]"
              />
              {canMaintain && (
                <Button
                  size="sm"
                  className="ml-auto"
                  onClick={() => {
                    setEditing(null);
                    setFormOpen(true);
                  }}
                >
                  <Plus aria-hidden="true" />
                  Add address
                </Button>
              )}
            </div>
            {loading ? (
              <p className="flex items-center gap-2 py-6 text-[13px] text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                Loading…
              </p>
            ) : shown.length === 0 ? (
              <EmptyState
                title={entries.length === 0 ? 'No addresses recorded' : 'Nothing matches'}
                description={
                  entries.length === 0
                    ? 'Add a college, a campus and the full address they name.'
                    : 'Try a different search.'
                }
              />
            ) : (
              <div className="overflow-x-auto rounded-md border border-border">
                <table className="w-full text-[12px]">
                  <thead className="bg-muted/50 text-left text-muted-foreground">
                    <tr>
                      <th className="px-2 py-1.5 font-medium">State</th>
                      <th className="px-2 py-1.5 font-medium">Campus</th>
                      <th className="px-2 py-1.5 font-medium">College</th>
                      <th className="px-2 py-1.5 font-medium">Full address</th>
                      {canMaintain && <th className="px-2 py-1.5" aria-label="Actions" />}
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((entry) => (
                      <tr key={`${entry.college_id}-${entry.campus_id}`} className="border-t border-border">
                        <td className="px-2 py-1.5">{entry.state}</td>
                        <td className="px-2 py-1.5 font-medium">{entry.campus_name}</td>
                        <td className="px-2 py-1.5">
                          {entry.college_short_name}
                          {!entry.is_active && (
                            <Badge variant="neutral" className="ml-1 text-[10px]">
                              Retired
                            </Badge>
                          )}
                        </td>
                        <td className="px-2 py-1.5">
                          {entry.address ?? <span className="text-muted-foreground">Address not recorded</span>}
                        </td>
                        {canMaintain && (
                          <td className="px-2 py-1 text-right">
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 text-[12px]"
                              onClick={() => {
                                setEditing(entry);
                                setFormOpen(true);
                              }}
                            >
                              <Pencil aria-hidden="true" className="size-3.5" />
                              Edit
                            </Button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CampusAddressFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        editing={editing}
        onSaved={() => void load()}
      />
    </>
  );
}
