'use client';

import * as React from 'react';
import { ChevronDown, GraduationCap, MapPin, Plus, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { SimpleSelect } from '@/components/common/dependent-select';
import { EmptyState, ErrorState } from '@/components/common/states';
import {
  AVAILABILITY_LEGEND,
  WeekdayAvailabilityList,
  WeekdayAvailabilityStrip,
} from './weekday-availability';
import { trainersApi, type TrainerDetail, type TrainerLocation } from '@/services/trainers-api';
import { referenceApi } from '@/services/reference-api';
import { cn } from '@/lib/utils';

const WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'] as const;

const WEEKDAY_OPTIONS = [
  { value: 'NOT_AVAILABLE', label: 'Not available' },
  { value: 'PHYSICAL', label: 'Physical' },
  { value: 'VIRTUAL', label: 'Virtual' },
];

const CLASS_TYPE_OPTIONS = [
  { value: 'THEORY', label: 'Theory' },
  { value: 'PRACTICAL', label: 'Practical' },
  // Approved 26 August 2026: eligible for both, and now a real stored value.
  { value: 'THEORY_AND_PRACTICAL', label: 'Theory and Practical' },
];

const LOCATION_TYPE_OPTIONS = ['Campus', 'Kitchen', 'Workshop', 'Virtual', 'Offshore'].map(
  (value) => ({ value, label: value }),
);

/** `09:00:00` → `9:00 am`, matching the convention used elsewhere. */
function formatTime(value: string): string {
  const [rawHour, minute] = value.split(':');
  const hour = Number.parseInt(rawHour ?? '', 10);
  if (Number.isNaN(hour)) return value;
  const meridian = hour < 12 ? 'am' : 'pm';
  const display = hour % 12 === 0 ? 12 : hour % 12;
  return `${display}:${minute} ${meridian}`;
}

/** What a location is called: the campus, Offshore, or the raw unresolved text. */
function placeOf(row: TrainerLocation): { label: string; unresolved: boolean } {
  if (row.is_offshore) return { label: 'Offshore', unresolved: false };
  if (row.campus_name) return { label: row.campus_name, unresolved: false };
  return { label: row.location_text ?? 'Location not recorded', unresolved: true };
}

/**
 * One trainer, shown in a side panel.
 *
 * **Location first, then Qualification** (2.10). Every tray expands from data
 * already in the single `GET /trainers/{id}` response, so opening one costs no
 * request — browsing a trainer's units must not become a fetch per click.
 */
export function TrainerDetailPanel({
  trainerPk,
  open,
  onOpenChange,
  canMaintain,
  onChanged,
}: {
  trainerPk: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canMaintain: boolean;
  onChanged?: () => void;
}) {
  const [detail, setDetail] = React.useState<TrainerDetail | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [addingLocation, setAddingLocation] = React.useState(false);
  const [addingUnits, setAddingUnits] = React.useState(false);

  const load = React.useCallback(async () => {
    if (trainerPk === null) return;
    setLoading(true);
    setError(null);
    try {
      setDetail(await trainersApi.get(trainerPk));
    } catch (caught) {
      setDetail(null);
      setError(caught instanceof Error ? caught.message : 'The trainer could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [trainerPk]);

  React.useEffect(() => {
    if (open) void load();
  }, [open, load]);

  function applyDetail(next: TrainerDetail) {
    setDetail(next);
    setAddingLocation(false);
    setAddingUnits(false);
    onChanged?.();
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle className="flex flex-wrap items-center gap-2">
            {detail?.trainer_id ?? 'Trainer'}
            {detail && (
              <Badge variant={detail.is_active ? 'success' : 'neutral'}>
                {detail.is_active ? 'Active' : 'Inactive'}
              </Badge>
            )}
            {/* Derived from the qualifications they teach — never stored (1.7). */}
            {detail?.training_packages.map((code) => (
              <Badge key={code} variant="info">
                {code}
              </Badge>
            ))}
          </SheetTitle>
          <SheetDescription>
            {detail ? `${detail.trainer_name} · ${detail.city ?? 'City not recorded'}` : 'Loading…'}
          </SheetDescription>
        </SheetHeader>

        <SheetBody className="space-y-6">
          {loading ? (
            <p className="flex items-center gap-2 text-[13px] text-muted-foreground" aria-busy="true">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Loading the trainer…
            </p>
          ) : error ? (
            <div className="space-y-3">
              <ErrorState title="The trainer could not be loaded" description={error} />
              <Button variant="outline" size="sm" onClick={() => void load()}>
                Retry
              </Button>
            </div>
          ) : detail ? (
            <>
              {/* ---- Location ------------------------------------------- */}
              <section className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="flex items-center gap-1.5 text-[14px] font-semibold">
                    <MapPin aria-hidden="true" className="size-4" />
                    Location
                  </h3>
                  <span className="text-[12px] text-muted-foreground">
                    {detail.locations.length}{' '}
                    {detail.locations.length === 1 ? 'location' : 'locations'}
                  </span>
                  {canMaintain && !addingLocation && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="ml-auto h-7 text-[12px]"
                      onClick={() => setAddingLocation(true)}
                    >
                      <Plus aria-hidden="true" className="size-3.5" />
                      Add Location
                    </Button>
                  )}
                </div>

                {addingLocation && (
                  <AddLocationForm
                    trainerPk={detail.id}
                    onCancel={() => setAddingLocation(false)}
                    onSaved={applyDetail}
                  />
                )}

                {detail.locations.length === 0 && !addingLocation ? (
                  <EmptyState
                    title="No location recorded"
                    description="This trainer has no campus or offshore location on record yet."
                    icon={MapPin}
                  />
                ) : (
                  <ul className="space-y-1.5">
                    {detail.locations.map((row) => (
                      <LocationRow key={row.id} row={row} />
                    ))}
                  </ul>
                )}
                {detail.locations.length > 0 && (
                  <p className="text-[11px] text-muted-foreground">{AVAILABILITY_LEGEND}</p>
                )}
              </section>

              {/* ---- Qualification -------------------------------------- */}
              <section className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="flex items-center gap-1.5 text-[14px] font-semibold">
                    <GraduationCap aria-hidden="true" className="size-4" />
                    Qualification
                  </h3>
                  <span className="text-[12px] text-muted-foreground">
                    {detail.qualifications.length}{' '}
                    {detail.qualifications.length === 1 ? 'qualification' : 'qualifications'}
                  </span>
                  {canMaintain && !addingUnits && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="ml-auto h-7 text-[12px]"
                      onClick={() => setAddingUnits(true)}
                    >
                      <Plus aria-hidden="true" className="size-3.5" />
                      Add Units
                    </Button>
                  )}
                </div>

                {addingUnits && (
                  <AddUnitsForm
                    trainerPk={detail.id}
                    onCancel={() => setAddingUnits(false)}
                    onSaved={applyDetail}
                  />
                )}

                {detail.qualifications.length === 0 && !addingUnits ? (
                  <EmptyState
                    title="No qualification recorded"
                    description="This trainer is not yet approved to teach any qualification."
                    icon={GraduationCap}
                  />
                ) : (
                  <ul className="space-y-1.5">
                    {detail.qualifications.map((group) => (
                      <QualificationRow key={group.qualification_id} group={group} />
                    ))}
                  </ul>
                )}
              </section>
            </>
          ) : null}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}

/** A location row: a real button, so the tray is reachable by keyboard. */
function LocationRow({ row }: { row: TrainerLocation }) {
  const [expanded, setExpanded] = React.useState(false);
  const panelId = `trainer-location-${row.id}`;
  const place = placeOf(row);

  return (
    <li className="rounded-md border border-border">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        aria-controls={panelId}
        className="flex w-full flex-wrap items-center gap-2 px-3 py-2 text-left hover:bg-accent/50"
      >
        <ChevronDown
          aria-hidden="true"
          className={cn('size-4 shrink-0 transition-transform', expanded && 'rotate-180')}
        />
        <span className="text-[13px] font-medium">{place.label}</span>
        {place.unresolved && (
          <span className="text-[11px] text-warning">(unresolved)</span>
        )}
        {row.location_type && (
          <span className="text-[12px] text-muted-foreground">{row.location_type}</span>
        )}
        <Badge variant="neutral" className="text-[10px]">
          {CLASS_TYPE_OPTIONS.find((o) => o.value === row.class_type)?.label ?? row.class_type}
        </Badge>
        <span className="ml-auto text-[12px] text-muted-foreground tabular">
          {row.working_time_text ??
            `${formatTime(row.working_time_start)} to ${formatTime(row.working_time_end)}`}
        </span>
        <WeekdayAvailabilityStrip days={row} />
      </button>

      {expanded && (
        <div id={panelId} className="border-t border-border px-3 py-2 pl-9">
          <WeekdayAvailabilityList days={row} />
        </div>
      )}
    </li>
  );
}

function QualificationRow({
  group,
}: {
  group: TrainerDetail['qualifications'][number];
}) {
  const [expanded, setExpanded] = React.useState(false);
  const panelId = `trainer-qualification-${group.qualification_id}`;

  return (
    <li className="rounded-md border border-border">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        aria-controls={panelId}
        className="flex w-full flex-wrap items-center gap-2 px-3 py-2 text-left hover:bg-accent/50"
      >
        <ChevronDown
          aria-hidden="true"
          className={cn('size-4 shrink-0 transition-transform', expanded && 'rotate-180')}
        />
        <span className="text-[13px] font-medium">{group.qualification_code ?? 'NA'}</span>
        <span className="truncate text-[12px] text-muted-foreground">
          {group.qualification_title}
        </span>
        {group.qualification_unresolved && (
          <span className="text-[11px] text-warning">(not in the reference data yet)</span>
        )}
        <span className="ml-auto text-[12px] text-muted-foreground tabular">
          {group.units.length} {group.units.length === 1 ? 'unit' : 'units'}
        </span>
      </button>

      {expanded && (
        <div id={panelId} className="border-t border-border px-3 py-2 pl-9">
          <ul className="space-y-0.5">
            {group.units.map((unit) => (
              <li key={unit.id} className="text-[12px]">
                <span className="font-medium">{unit.unit_code}</span>
                <span className="mx-1.5 text-muted-foreground">·</span>
                <span className="text-muted-foreground">{unit.unit_title}</span>
                {/* Marked, never hidden: the row is real, its unit is not
                    approved yet. Resolving the suggestion repairs it. */}
                {unit.unresolved && (
                  <span className="ml-1.5 text-[11px] text-warning">(suggestion raised)</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Add Location (1.6)
// ---------------------------------------------------------------------------

function AddLocationForm({
  trainerPk,
  onCancel,
  onSaved,
}: {
  trainerPk: number;
  onCancel: () => void;
  onSaved: (detail: TrainerDetail) => void;
}) {
  const [campuses, setCampuses] = React.useState<{ value: string; label: string }[]>([]);
  const [campus, setCampus] = React.useState('');
  const [locationType, setLocationType] = React.useState('Campus');
  const [classType, setClassType] = React.useState('THEORY');
  const [start, setStart] = React.useState('09:00');
  const [end, setEnd] = React.useState('17:00');
  const [days, setDays] = React.useState<Record<string, string>>({
    monday: 'NOT_AVAILABLE',
    tuesday: 'NOT_AVAILABLE',
    wednesday: 'NOT_AVAILABLE',
    thursday: 'NOT_AVAILABLE',
    friday: 'NOT_AVAILABLE',
  });
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    void referenceApi
      .listCampuses({ activeOnly: true })
      .then((rows) =>
        setCampuses([
          // Offshore is a place a trainer can work, not a campus that failed
          // to resolve, so it is offered as a first-class choice.
          { value: 'OFFSHORE', label: 'Offshore — not at a campus' },
          ...rows.map((row) => ({
            value: String(row.id),
            label: `${row.campus_name} — ${row.campus_location}`,
          })),
        ]),
      )
      .catch(() => setCampuses([{ value: 'OFFSHORE', label: 'Offshore — not at a campus' }]));
  }, []);

  async function save() {
    if (!campus) {
      toast.error('Choose a campus, or Offshore.');
      return;
    }
    setBusy(true);
    try {
      const offshore = campus === 'OFFSHORE';
      const detail = await trainersApi.addLocation(trainerPk, {
        campus_id: offshore ? null : Number(campus),
        is_offshore: offshore,
        location_type: locationType,
        class_type: classType,
        working_time_start: `${start}:00`,
        working_time_end: `${end}:00`,
        ...days,
      });
      toast.success('Location added');
      onSaved(detail);
    } catch (caught) {
      toast.error('The location could not be added', {
        description: caught instanceof Error ? caught.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-md border border-border bg-muted/30 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Campus">
          <SimpleSelect
            value={campus}
            onChange={setCampus}
            options={campuses}
            placeholder="Search approved campuses"
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
        <p className="mb-1.5 text-[12px] font-medium">Weekdays</p>
        <div className="grid gap-2 sm:grid-cols-5">
          {WEEKDAYS.map((day) => (
            <Field key={day} label={day.charAt(0).toUpperCase() + day.slice(1)}>
              <SimpleSelect
                value={days[day]}
                onChange={(value) => setDays((prev) => ({ ...prev, [day]: value }))}
                options={WEEKDAY_OPTIONS}
                placeholder="Not available"
              />
            </Field>
          ))}
        </div>
      </div>

      <div className="flex gap-2">
        <Button size="sm" onClick={() => void save()} disabled={busy}>
          {busy && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
          Save location
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add Units (1.6) — one qualification, many units, one call
// ---------------------------------------------------------------------------

function AddUnitsForm({
  trainerPk,
  onCancel,
  onSaved,
}: {
  trainerPk: number;
  onCancel: () => void;
  onSaved: (detail: TrainerDetail) => void;
}) {
  const [qualifications, setQualifications] = React.useState<{ value: string; label: string }[]>([]);
  const [qualification, setQualification] = React.useState('');
  const [units, setUnits] = React.useState<{ id: number; label: string }[]>([]);
  const [chosen, setChosen] = React.useState<number[]>([]);
  const [search, setSearch] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
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
  }, []);

  // The units of the chosen qualification, so the picker offers what belongs.
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

  async function save() {
    if (!qualification || chosen.length === 0) {
      toast.error('Choose a qualification and at least one unit.');
      return;
    }
    setBusy(true);
    try {
      // One call, however many units — never one request per unit.
      const detail = await trainersApi.addUnits(trainerPk, Number(qualification), chosen);
      toast.success(`${chosen.length} unit(s) added`);
      onSaved(detail);
    } catch (caught) {
      toast.error('The units could not be added', {
        description: caught instanceof Error ? caught.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-md border border-border bg-muted/30 p-3">
      <Field label="Qualification">
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
          <ul className="max-h-48 space-y-0.5 overflow-y-auto rounded border border-border bg-background p-1">
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
          <p className="text-[12px] text-muted-foreground tabular">{chosen.length} selected</p>
        </>
      )}

      <div className="flex gap-2">
        <Button size="sm" onClick={() => void save()} disabled={busy || chosen.length === 0}>
          {busy && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
          Save units
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-[12px] font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}
