'use client';

import * as React from 'react';
import { GraduationCap, Loader2, MapPin, Plus, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
import { SimpleSelect } from '@/components/common/dependent-select';
import { referenceApi } from '@/services/reference-api';
import { trainersApi, type LocationWrite } from '@/services/trainers-api';

/**
 * The cities a trainer can be based in.
 *
 * A fixed list rather than the Location Dictionary, because no campus carries a
 * city yet — the column is new and every existing row is null, so deriving the
 * options would offer an empty dropdown. Once campuses record their city this
 * can read from `GET /reference/locations` instead.
 */
const CITY_OPTIONS = ['Sydney', 'Brisbane', 'Melbourne', 'Hobart'].map((value) => ({
  value,
  label: value,
}));

const WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'] as const;

const WEEKDAY_OPTIONS = [
  { value: 'NOT_AVAILABLE', label: 'Not available' },
  { value: 'PHYSICAL', label: 'Physical' },
  { value: 'VIRTUAL', label: 'Virtual' },
];

const CLASS_TYPE_OPTIONS = [
  { value: 'THEORY', label: 'Theory' },
  { value: 'PRACTICAL', label: 'Practical' },
  { value: 'THEORY_AND_PRACTICAL', label: 'Theory and Practical' },
];

const LOCATION_TYPE_OPTIONS = ['Campus', 'Kitchen', 'Workshop', 'Virtual', 'Offshore'].map(
  (value) => ({ value, label: value }),
);

interface DraftLocation extends LocationWrite {
  /** For the list beneath the tile — the campus is an id on the wire. */
  campus_label: string;
}

interface DraftUnits {
  qualification_id: number;
  qualification_label: string;
  unit_ids: number[];
  unit_labels: string[];
}

/** `09:00:00` → `9:00 am`. */
function shortTime(value: string): string {
  const [rawHour, minute] = value.split(':');
  const hour = Number.parseInt(rawHour ?? '', 10);
  if (Number.isNaN(hour)) return value;
  const meridian = hour < 12 ? 'am' : 'pm';
  const display = hour % 12 === 0 ? 12 : hour % 12;
  return `${display}:${minute} ${meridian}`;
}

/**
 * Add one trainer.
 *
 * **The Trainer ID is generated, never typed.** `TI_010_AY` — the tag, the next
 * number in the sequence, and the initials of the name. It updates as the name
 * is typed so the value is visible before saving, but nothing is reserved: the
 * id is generated again on save, so two people filling this form at once cannot
 * both take TI_010.
 *
 * The city is required. Locations and qualifications are added through their own
 * popups and listed as they are added, so a trainer with three campuses is
 * entered in one pass — or saved with none and completed later from the side
 * panel.
 */
export function AddTrainerDialog({
  open,
  onOpenChange,
  onCreated,
  prefill,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The new trainer, so a suggestion can be resolved onto it. */
  onCreated: (trainerId: number) => void;
  /** From a suggestion: the trainer name as it was seen. */
  prefill?: { name?: string } | null;
}) {
  const [name, setName] = React.useState('');
  const [city, setCity] = React.useState('');
  const [preview, setPreview] = React.useState('TI_001_XX');
  const [busy, setBusy] = React.useState(false);

  const [locations, setLocations] = React.useState<DraftLocation[]>([]);
  const [units, setUnits] = React.useState<DraftUnits[]>([]);
  const [locationOpen, setLocationOpen] = React.useState(false);
  const [unitsOpen, setUnitsOpen] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setName(prefill?.name ?? '');
    setCity('');
    setLocations([]);
    setUnits([]);
  }, [open, prefill]);

  // Debounced: the id follows the name without a request per keystroke.
  React.useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      void trainersApi
        .nextId(name)
        .then((result) => {
          if (!cancelled) setPreview(result.trainer_id);
        })
        .catch(() => undefined);
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [name, open]);

  async function save() {
    setBusy(true);
    try {
      const detail = await trainersApi.create({
        trainer_name: name.trim(),
        city: city.trim(),
        locations: locations.map(({ campus_label: _label, ...rest }) => rest),
        units: units.map((entry) => ({
          qualification_id: entry.qualification_id,
          unit_ids: entry.unit_ids,
        })),
      });
      toast.success(`Trainer ${detail.trainer_id} created`, {
        description:
          detail.locations.length || detail.qualifications.length
            ? `${detail.locations.length} location(s) and ${detail.qualifications.length} qualification(s) recorded.`
            : 'Add their locations and units from the side panel whenever you are ready.',
      });
      onCreated(detail.id);
      onOpenChange(false);
    } catch (caught) {
      toast.error('The trainer could not be created', {
        description: caught instanceof Error ? caught.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>Add a trainer</DialogTitle>
            <DialogDescription>
              The Trainer ID is generated from the sequence and the name. Locations and
              qualifications are optional — add as many as you need, or none.
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Trainer name" required>
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="John Smith"
                  autoComplete="off"
                  autoFocus
                />
              </Field>
              <Field label="Trainer ID">
                {/* Read-only but a real value, so it reads as one: full-strength
                    text on the normal field background, never placeholder grey. */}
                <Input
                  value={preview}
                  readOnly
                  aria-readonly="true"
                  className="font-mono text-[13px] font-medium text-foreground"
                  aria-describedby="trainer-id-hint"
                />
                <p id="trainer-id-hint" className="text-[11px] text-muted-foreground">
                  Generated. Confirmed when you save.
                </p>
              </Field>
              <Field label="Trainer campus (city)" required>
                <SimpleSelect
                  value={city}
                  onChange={setCity}
                  options={CITY_OPTIONS}
                  placeholder="Choose City"
                />
              </Field>
            </div>

            {/* -- Locations ------------------------------------------------ */}
            <div className="space-y-2">
              <AddTile
                icon={MapPin}
                label="Add location"
                onClick={() => setLocationOpen(true)}
              />
              {locations.length > 0 && (
                <ul className="space-y-1.5">
                  {locations.map((entry, index) => (
                    <AddedRow
                      key={`${entry.campus_label}-${index}`}
                      onRemove={() =>
                        setLocations((prev) => prev.filter((_, at) => at !== index))
                      }
                    >
                      <span className="text-[13px] font-medium">{entry.campus_label}</span>
                      <Badge variant="neutral" className="text-[10px]">
                        {CLASS_TYPE_OPTIONS.find((o) => o.value === entry.class_type)?.label}
                      </Badge>
                      <span className="text-[12px] text-muted-foreground tabular">
                        {shortTime(entry.working_time_start)} to {shortTime(entry.working_time_end)}
                      </span>
                      <span className="text-[11px] text-muted-foreground">
                        {WEEKDAYS.filter((day) => entry[day] !== 'NOT_AVAILABLE')
                          .map((day) => day.slice(0, 3))
                          .join(', ') || 'no days set'}
                      </span>
                    </AddedRow>
                  ))}
                </ul>
              )}
            </div>

            {/* -- Qualifications and units --------------------------------- */}
            <div className="space-y-2">
              <AddTile
                icon={GraduationCap}
                label="Add qualification and units"
                onClick={() => setUnitsOpen(true)}
              />
              {units.length > 0 && (
                <ul className="space-y-1.5">
                  {units.map((entry, index) => (
                    <AddedRow
                      key={`${entry.qualification_id}-${index}`}
                      onRemove={() => setUnits((prev) => prev.filter((_, at) => at !== index))}
                    >
                      <span className="text-[13px] font-medium">{entry.qualification_label}</span>
                      <span className="text-[12px] text-muted-foreground tabular">
                        {entry.unit_ids.length} unit{entry.unit_ids.length === 1 ? '' : 's'}
                      </span>
                      <span className="truncate text-[11px] text-muted-foreground">
                        {entry.unit_labels.slice(0, 3).join(', ')}
                        {entry.unit_labels.length > 3 && ` +${entry.unit_labels.length - 3} more`}
                      </span>
                    </AddedRow>
                  ))}
                </ul>
              )}
            </div>
          </DialogBody>

          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={() => void save()} disabled={busy || !name.trim() || !city.trim()}>
              {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
              Create trainer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <LocationDialog
        open={locationOpen}
        onOpenChange={setLocationOpen}
        onAdd={(entry) => setLocations((prev) => [...prev, entry])}
      />
      <UnitsDialog
        open={unitsOpen}
        onOpenChange={setUnitsOpen}
        onAdd={(entry) => setUnits((prev) => [...prev, entry])}
      />
    </>
  );
}

/** The small box with a plus sign that opens one of the popups. */
function AddTile({
  icon: Icon,
  label,
  onClick,
}: {
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' }>;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-2 rounded-md border border-dashed border-border px-3 py-2.5 text-left transition-colors hover:border-primary/40 hover:bg-accent/40"
    >
      <span className="flex size-6 shrink-0 items-center justify-center rounded border border-border bg-muted">
        <Plus aria-hidden="true" className="size-3.5" />
      </span>
      <Icon aria-hidden="true" className="size-4 text-muted-foreground" />
      <span className="text-[13px] font-medium">{label}</span>
    </button>
  );
}

/** One entry already added, listed under its tile. */
function AddedRow({
  children,
  onRemove,
}: {
  children: React.ReactNode;
  onRemove: () => void;
}) {
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2">
      {children}
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="ml-auto size-7 shrink-0 p-0"
        onClick={onRemove}
        aria-label="Remove"
      >
        <X aria-hidden="true" className="size-3.5" />
      </Button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// The location popup
// ---------------------------------------------------------------------------

function LocationDialog({
  open,
  onOpenChange,
  onAdd,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdd: (entry: DraftLocation) => void;
}) {
  const [campuses, setCampuses] = React.useState<{ value: string; label: string }[]>([]);
  const [campus, setCampus] = React.useState('');
  const [locationType, setLocationType] = React.useState('Campus');
  const [classType, setClassType] = React.useState('THEORY');
  const [start, setStart] = React.useState('09:00');
  const [end, setEnd] = React.useState('17:00');
  const [days, setDays] = React.useState<Record<string, string>>({});

  React.useEffect(() => {
    if (!open) return;
    setCampus('');
    setLocationType('Campus');
    setClassType('THEORY');
    setStart('09:00');
    setEnd('17:00');
    setDays(Object.fromEntries(WEEKDAYS.map((day) => [day, 'NOT_AVAILABLE'])));
    if (campuses.length) return;
    void referenceApi
      .listCampuses({ activeOnly: true })
      .then((rows) =>
        setCampuses([
          // Offshore is a place a trainer can work, not a campus that failed to
          // resolve, so it is offered as a first-class choice.
          { value: 'OFFSHORE', label: 'Offshore — not at a campus' },
          ...rows.map((row) => ({
            value: String(row.id),
            label: `${row.campus_name} — ${row.campus_location}`,
          })),
        ]),
      )
      .catch(() => setCampuses([{ value: 'OFFSHORE', label: 'Offshore — not at a campus' }]));
  }, [open, campuses.length]);

  function add() {
    const chosen = campuses.find((option) => option.value === campus);
    if (!chosen) {
      toast.error('Choose a campus, or Offshore.');
      return;
    }
    if (end <= start) {
      toast.error('The working time must end after it starts.');
      return;
    }
    onAdd({
      campus_id: campus === 'OFFSHORE' ? null : Number(campus),
      is_offshore: campus === 'OFFSHORE',
      campus_label: campus === 'OFFSHORE' ? 'Offshore' : chosen.label.split(' — ')[0],
      location_type: locationType,
      class_type: classType,
      working_time_start: `${start}:00`,
      working_time_end: `${end}:00`,
      ...days,
    });
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Add location</DialogTitle>
          <DialogDescription>
            Where this trainer works, and which days they are available there.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Campus" required>
              <SimpleSelect
                value={campus}
                onChange={setCampus}
                options={campuses}
                placeholder="Choose a campus, or Offshore"
              />
            </Field>
            <Field label="Location type">
              <SimpleSelect
                value={locationType}
                onChange={setLocationType}
                options={LOCATION_TYPE_OPTIONS}
                placeholder="Location type"
              />
            </Field>
            <Field label="Class type">
              <SimpleSelect
                value={classType}
                onChange={setClassType}
                options={CLASS_TYPE_OPTIONS}
                placeholder="Class type"
              />
            </Field>
            <Field label="Working time">
              <div className="flex items-center gap-2">
                <Input type="time" value={start} onChange={(e) => setStart(e.target.value)} />
                <span className="text-[12px] text-muted-foreground">to</span>
                <Input type="time" value={end} onChange={(e) => setEnd(e.target.value)} />
              </div>
            </Field>
          </div>
          <div>
            <p className="mb-1.5 text-[12px] font-medium text-muted-foreground">Weekdays</p>
            <div className="grid gap-2 sm:grid-cols-5">
              {WEEKDAYS.map((day) => (
                <Field key={day} label={day.charAt(0).toUpperCase() + day.slice(1)}>
                  <SimpleSelect
                    value={days[day] ?? 'NOT_AVAILABLE'}
                    onChange={(value) => setDays((prev) => ({ ...prev, [day]: value }))}
                    options={WEEKDAY_OPTIONS}
                    placeholder="Not available"
                  />
                </Field>
              ))}
            </div>
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={add} disabled={!campus}>
            <Plus aria-hidden="true" />
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// The qualification and units popup
// ---------------------------------------------------------------------------

function UnitsDialog({
  open,
  onOpenChange,
  onAdd,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdd: (entry: DraftUnits) => void;
}) {
  const [qualifications, setQualifications] = React.useState<{ value: string; label: string }[]>([]);
  const [qualification, setQualification] = React.useState('');
  const [units, setUnits] = React.useState<{ id: number; label: string }[]>([]);
  const [chosen, setChosen] = React.useState<number[]>([]);
  const [search, setSearch] = React.useState('');

  React.useEffect(() => {
    if (!open) return;
    setQualification('');
    setChosen([]);
    setSearch('');
    if (qualifications.length) return;
    void referenceApi
      .listQualifications({ activeOnly: true })
      .then((rows) =>
        setQualifications(
          rows.map((row) => ({
            value: String(row.id),
            label: `${row.qualification_code ?? 'NA'} — ${row.qualification_title}`,
          })),
        ),
      )
      .catch(() => setQualifications([]));
  }, [open, qualifications.length]);

  React.useEffect(() => {
    setChosen([]);
    if (!qualification) {
      setUnits([]);
      return;
    }
    void referenceApi
      .listUnits({ qualificationId: Number(qualification) })
      .then((rows) =>
        setUnits(rows.map((row) => ({ id: row.id, label: `${row.unit_code} — ${row.unit_title}` }))),
      )
      .catch(() => setUnits([]));
  }, [qualification]);

  const visible = units.filter(
    (unit) => !search || unit.label.toLowerCase().includes(search.trim().toLowerCase()),
  );

  function add() {
    const chosenQualification = qualifications.find((option) => option.value === qualification);
    if (!chosenQualification || chosen.length === 0) {
      toast.error('Choose a qualification and at least one unit.');
      return;
    }
    onAdd({
      qualification_id: Number(qualification),
      qualification_label: chosenQualification.label.split(' — ')[0],
      unit_ids: chosen,
      unit_labels: chosen.map(
        (id) => units.find((unit) => unit.id === id)?.label.split(' — ')[0] ?? '',
      ),
    });
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add qualification and units</DialogTitle>
          <DialogDescription>
            One qualification and the units this trainer can teach in it. Add the block again for a
            second qualification.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <Field label="Qualification" required>
            <SimpleSelect
              value={qualification}
              onChange={setQualification}
              options={qualifications}
              placeholder="Choose one qualification"
            />
          </Field>

          {qualification && (
            <>
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Filter units"
                className="h-8 text-[13px]"
              />
              <div className="flex items-center justify-between text-[12px] text-muted-foreground">
                <span className="tabular">{chosen.length} selected</span>
                <button
                  type="button"
                  className="underline-offset-2 hover:underline"
                  onClick={() =>
                    setChosen(
                      chosen.length === visible.length ? [] : visible.map((unit) => unit.id),
                    )
                  }
                >
                  {chosen.length === visible.length ? 'Clear all' : 'Select all shown'}
                </button>
              </div>
              <ul className="max-h-56 space-y-0.5 overflow-y-auto rounded border border-border bg-background p-1">
                {visible.map((unit) => (
                  <li key={unit.id}>
                    <label className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-[12px] hover:bg-accent/50">
                      <input
                        type="checkbox"
                        checked={chosen.includes(unit.id)}
                        onChange={(event) =>
                          setChosen((prev) =>
                            event.target.checked
                              ? [...prev, unit.id]
                              : prev.filter((id) => id !== unit.id),
                          )
                        }
                      />
                      {unit.label}
                    </label>
                  </li>
                ))}
                {visible.length === 0 && (
                  <li className="px-1.5 py-1 text-[12px] text-muted-foreground">
                    No unit matches.
                  </li>
                )}
              </ul>
            </>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={add} disabled={!qualification || chosen.length === 0}>
            <Plus aria-hidden="true" />
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-[12px] font-medium text-muted-foreground">
        {label}
        {required && <span className="ml-0.5 text-destructive">*</span>}
      </span>
      {children}
    </label>
  );
}
