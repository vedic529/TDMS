'use client';

import * as React from 'react';
import { Loader2, Plus, Trash2 } from 'lucide-react';
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
import { FormField, FormGrid } from '@/components/common/form-field';
import { DependentSelect, SimpleSelect } from '@/components/common/dependent-select';
import { referenceApi, type ApiCampus, type ApiCollege } from '@/services/reference-api';

/** Weekday keys in the order `facility_faculties` stores them. */
const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'] as const;

/**
 * A room admits any qualification when its faculty is `NA` (requirement §8), so
 * it is offered as a first-class choice rather than left as something to type.
 */
const UNRESTRICTED_FACULTY = 'NA';

interface FacultyRule {
  faculty: string;
  monday: boolean;
  tuesday: boolean;
  wednesday: boolean;
  thursday: boolean;
  friday: boolean;
}

const EMPTY_RULE: FacultyRule = {
  faculty: '',
  monday: false,
  tuesday: false,
  wednesday: false,
  thursday: false,
  friday: false,
};

interface FacilityFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
  /**
   * From a suggestion: the room name seen, and the campus the server resolved
   * its address spelling to.
   */
  prefill?: {
    reference?: string;
    campusId?: number;
    /** The colleges whose classes were timetabled in the room, as the file named them. */
    collegeNames?: string[];
  } | null;
  /** The new room, so a suggestion can be resolved onto it. */
  onCreated?: (facilityId: number) => void;
}

/**
 * Add a room to College Facility.
 *
 * A facility is three tables - the room, the colleges that may use it and the
 * faculty rules - so this asks for all three and writes them in one call. A room
 * saved without its links exists but is usable by nobody and shows in no
 * filtered list, which is why the API refuses a room with no college and no
 * faculty rather than accepting a half-record.
 *
 * Every dependent value is chosen, never typed: campus and colleges come from
 * the database, and the faculty list comes from the faculties already in use, so
 * a typo cannot invent a seventh faculty. Only the room's own facts - its
 * reference, seats and classification - are typed, because only they are new.
 */
export function FacilityFormDialog({
  open,
  onOpenChange,
  onSaved,
  prefill,
  onCreated,
}: FacilityFormDialogProps) {
  const [colleges, setColleges] = React.useState<ApiCollege[]>([]);
  const [campuses, setCampuses] = React.useState<ApiCampus[]>([]);
  const [knownFaculties, setKnownFaculties] = React.useState<string[]>([]);
  const [knownTypes, setKnownTypes] = React.useState<string[]>([]);
  const [knownClassifications, setKnownClassifications] = React.useState<string[]>([]);

  const [reference, setReference] = React.useState('');
  const [campusId, setCampusId] = React.useState('');
  const [facilityType, setFacilityType] = React.useState('');
  const [capacity, setCapacity] = React.useState('');
  const [classification, setClassification] = React.useState('');
  const [collegeIds, setCollegeIds] = React.useState<number[]>([]);
  const [rules, setRules] = React.useState<FacultyRule[]>([EMPTY_RULE]);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setReference(prefill?.reference ?? '');
    setCampusId(prefill?.campusId ? String(prefill.campusId) : '');
    setFacilityType('');
    setCapacity('');
    setClassification('');
    setCollegeIds([]);
    setRules([EMPTY_RULE]);

    let cancelled = false;
    void (async () => {
      try {
        const [collegeRows, campusRows, facilityRows] = await Promise.all([
          referenceApi.listColleges({ activeOnly: true }),
          referenceApi.listCampuses({ activeOnly: true }),
          referenceApi.listFacilities({}),
        ]);
        if (cancelled) return;
        setColleges(collegeRows);
        const wantedColleges = new Set((prefill?.collegeNames ?? []).map((value) => value.trim().toUpperCase()));
        if (wantedColleges.size > 0) {
          setCollegeIds(
            collegeRows
              .filter(
                (row) =>
                  wantedColleges.has(row.college_short_name.trim().toUpperCase()) ||
                  wantedColleges.has(row.college_full_name.trim().toUpperCase()),
              )
              .map((row) => row.id),
          );
        }
        setCampuses(campusRows);
        // The choosable values are whatever the stored rooms already use. This
        // keeps the lists true without a reference table for either, and stops a
        // typo creating a faculty or a room type that exists once.
        setKnownFaculties(
          Array.from(
            new Set(facilityRows.flatMap((row) => row.faculties.map((rule) => rule.faculty))),
          ).sort(),
        );
        setKnownTypes(Array.from(new Set(facilityRows.map((row) => row.facility_type))).sort());
        setKnownClassifications(
          Array.from(
            new Set(
              facilityRows
                .map((row) => row.room_classification)
                .filter((value): value is string => Boolean(value)),
            ),
          ).sort(),
        );
      } catch {
        if (!cancelled) toast.error('The reference lists could not be loaded');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, prefill]);

  const seats = Number(capacity);
  const rulesComplete = rules.every((rule) => rule.faculty && DAYS.some((day) => rule[day]));

  // Mirrors what the API requires, so Save is only offered for a record that
  // will be accepted.
  const canSave =
    Boolean(reference.trim()) &&
    Boolean(campusId) &&
    Boolean(facilityType) &&
    Number.isFinite(seats) &&
    seats > 0 &&
    collegeIds.length > 0 &&
    rules.length > 0 &&
    rulesComplete;

  function setRule(index: number, patch: Partial<FacultyRule>) {
    setRules((current) =>
      current.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)),
    );
  }

  async function save() {
    if (!canSave) return;
    setBusy(true);
    try {
      const facility = await referenceApi.createFacility({
        facility_reference: reference.trim(),
        campus_id: Number(campusId),
        facility_type: facilityType,
        capacity: seats,
        room_classification: classification || null,
        college_ids: collegeIds,
        faculties: rules.map((rule) => ({
          faculty: rule.faculty,
          monday: rule.monday,
          tuesday: rule.tuesday,
          wednesday: rule.wednesday,
          thursday: rule.thursday,
          friday: rule.friday,
        })),
      });
      toast.success('Room added', {
        description: `${reference.trim()} is available to ${collegeIds.length} college(s).`,
      });
      onCreated?.(facility.id);
      onOpenChange(false);
      onSaved();
    } catch (error) {
      toast.error('The room could not be added', {
        description:
          error instanceof Error ? error.message : 'Try again, or contact the TDMS administrator.',
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Add a room</DialogTitle>
          <DialogDescription>
            A room needs a location, the colleges that may use it, and at least one faculty rule
            saying which days it is available.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-5">
          <FormGrid>
            <FormField label="Classroom name" htmlFor="fac-reference" required>
              <Input
                id="fac-reference"
                value={reference}
                onChange={(event) => setReference(event.target.value)}
                placeholder="e.g. Level 4 - Room 403"
              />
            </FormField>
            <FormField
              label="Location"
              htmlFor="fac-campus"
              required
              hint="The state comes with the campus."
            >
              <DependentSelect
                id="fac-campus"
                value={campusId}
                onChange={setCampusId}
                options={campuses.map((campus) => ({
                  value: String(campus.id),
                  // The full address: `Haymarket` covers two buildings.
                  label: `${campus.campus_name} — ${campus.campus_location}`,
                }))}
                placeholder="Select location"
              />
            </FormField>
            <FormField label="Classroom type" htmlFor="fac-type" required>
              <SimpleSelect
                id="fac-type"
                value={facilityType}
                onChange={setFacilityType}
                options={knownTypes.map((value) => ({ value, label: value }))}
                placeholder="Select type"
              />
            </FormField>
            <FormField label="Exact seats" htmlFor="fac-capacity" required>
              <Input
                id="fac-capacity"
                type="number"
                min={1}
                value={capacity}
                onChange={(event) => setCapacity(event.target.value)}
              />
            </FormField>
            <FormField
              label="Room classification"
              htmlFor="fac-classification"
              hint="Only for a specialised room. A plain classroom has none."
            >
              <SimpleSelect
                id="fac-classification"
                value={classification}
                onChange={setClassification}
                options={knownClassifications.map((value) => ({ value, label: value }))}
                placeholder="None"
              />
            </FormField>
          </FormGrid>

          {/* -- Which colleges may use it -------------------------------- */}
          <div className="space-y-2">
            <p className="text-[13px] font-medium">
              Colleges <span className="text-destructive text-[11px]">REQUIRED</span>
            </p>
            <p className="text-[12px] text-muted-foreground">
              A room usable by nobody would not appear on any college&apos;s timetable.
            </p>
            <div className="flex flex-wrap gap-2">
              {colleges.map((college) => {
                const chosen = collegeIds.includes(college.id);
                return (
                  <Button
                    key={college.id}
                    type="button"
                    size="sm"
                    variant={chosen ? 'default' : 'outline'}
                    className="h-8 text-[12px]"
                    onClick={() =>
                      setCollegeIds((current) =>
                        chosen
                          ? current.filter((id) => id !== college.id)
                          : [...current, college.id],
                      )
                    }
                  >
                    {college.college_short_name}
                  </Button>
                );
              })}
            </div>
          </div>

          {/* -- Faculty rules and the days they may use it --------------- */}
          <div className="space-y-2">
            <p className="text-[13px] font-medium">
              Faculty and available days <span className="text-destructive text-[11px]">REQUIRED</span>
            </p>
            <p className="text-[12px] text-muted-foreground">
              Availability is recorded per faculty, because a room can be open to one faculty on
              Monday and another on Friday. Choose <span className="font-mono">NA</span> for a room
              open to every faculty.
            </p>
            <ul className="space-y-2">
              {rules.map((rule, index) => (
                <li key={index} className="rounded-md border border-border p-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <SimpleSelect
                      id={`fac-faculty-${index}`}
                      value={rule.faculty}
                      onChange={(value) => setRule(index, { faculty: value })}
                      options={knownFaculties.map((value) => ({
                        value,
                        label: value === UNRESTRICTED_FACULTY ? 'NA — any faculty' : value,
                      }))}
                      placeholder="Select faculty"
                    />
                    {DAYS.map((day) => (
                      <Button
                        key={day}
                        type="button"
                        size="sm"
                        variant={rule[day] ? 'default' : 'outline'}
                        className="h-8 w-12 text-[12px] capitalize"
                        onClick={() => setRule(index, { [day]: !rule[day] } as Partial<FacultyRule>)}
                      >
                        {day.slice(0, 3)}
                      </Button>
                    ))}
                    {rules.length > 1 && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="ml-auto h-8"
                        onClick={() => setRules((current) => current.filter((_, i) => i !== index))}
                      >
                        <Trash2 aria-hidden="true" className="size-3.5" />
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 text-[12px]"
              onClick={() => setRules((current) => [...current, EMPTY_RULE])}
            >
              <Plus aria-hidden="true" className="size-3.5" />
              Add another faculty
            </Button>
          </div>
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={!canSave || busy}>
            {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
            Add room
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
