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
import {
  referenceApi,
  type ApiCampus,
  type ApiCollege,
  type ApiCollegeCampus,
  type ApiQualification,
} from '@/services/reference-api';

/**
 * AQF levels, as stored. Not derived from the title: only 55 of 79 stored
 * qualifications begin with their level, and `Vocational Short Course` and
 * `Non AQF Award` appear nowhere in a title.
 */
const COURSE_LEVELS = [
  'Certificate II',
  'Certificate III',
  'Certificate IV',
  'Diploma',
  'Advanced Diploma',
  'Graduate Diploma',
  'Non AQF Award',
  'Vocational Short Course',
];

const COURSE_SECTORS = ['VET', 'ELICOS'];

/**
 * One place the qualification is taught, and what it costs there.
 *
 * A list, because a qualification runs at up to eleven locations and each has
 * its own CRICOS registration and price - ten qualifications hold a different
 * CRICOS code at different campuses of the *same* college. Adding them together
 * is how a new qualification arrives complete instead of one offering at a time.
 */
interface LocationRow {
  collegeId: string;
  campusId: string;
  courseCode: string;
  durationWeeks: string;
  cost: string;
}

const EMPTY_LOCATION: LocationRow = {
  collegeId: '',
  campusId: '',
  courseCode: '',
  durationWeeks: '',
  cost: '',
};

interface CourseFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
  /** From a suggestion: the value seen, as a VET code or as a title. */
  prefill?: { vetCode?: string; title?: string } | null;
  /** The qualification, so a suggestion can be resolved onto it. */
  onCreated?: (qualificationId: number) => void;
}

/**
 * Add a qualification at a location.
 *
 * The record is a `course_offerings` row: which college teaches which
 * qualification, where. Almost everything the old form asked for was a property
 * of the qualification - its title, VET code, level, sector and both Fields of
 * Education - and retyping those made a second, slightly different qualification
 * every time someone spelled one differently. They come with the qualification
 * now.
 *
 * What is genuinely typed is what belongs to *this* offering and nothing else:
 * the CRICOS code, the price, the duration. Those differ by college and even by
 * campus - ten qualifications hold a different CRICOS code at different campuses
 * of the same college - which is exactly why the offering is its own row.
 *
 * `course_status_id` is not asked for. `course_statuses` holds one row, `ACTIVE`,
 * so a dropdown of one is a question with no answer to give.
 */
export function CourseFormDialog({
  open,
  onOpenChange,
  onSaved,
  prefill,
  onCreated,
}: CourseFormDialogProps) {
  const [colleges, setColleges] = React.useState<ApiCollege[]>([]);
  const [links, setLinks] = React.useState<ApiCollegeCampus[]>([]);
  const [campuses, setCampuses] = React.useState<ApiCampus[]>([]);
  const [qualifications, setQualifications] = React.useState<ApiQualification[]>([]);
  const [statusId, setStatusId] = React.useState<number | null>(null);

  const [places, setPlaces] = React.useState<LocationRow[]>([EMPTY_LOCATION]);
  const [vetCode, setVetCode] = React.useState('');
  const [title, setTitle] = React.useState('');
  const [newLevel, setNewLevel] = React.useState('');
  const [newSector, setNewSector] = React.useState('');

  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setPlaces([EMPTY_LOCATION]);
    setVetCode(prefill?.vetCode ?? '');
    setTitle(prefill?.title ?? '');
    setNewLevel('');
    setNewSector('');

    let cancelled = false;
    void (async () => {
      try {
        const [collegeRows, linkRows, campusRows, qualificationRows, statuses] = await Promise.all([
          referenceApi.listColleges({ activeOnly: true }),
          referenceApi.listCollegeCampuses(),
          referenceApi.listCampuses({ activeOnly: true }),
          referenceApi.listQualifications({ activeOnly: true }),
          referenceApi.listCourseStatuses(),
        ]);
        if (cancelled) return;
        setColleges(collegeRows);
        setLinks(linkRows);
        setCampuses(campusRows);
        setQualifications(qualificationRows);
        setStatusId(statuses[0]?.id ?? null);
      } catch {
        if (!cancelled) toast.error('The reference lists could not be loaded');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, prefill]);

  /**
   * Only campuses this college already operates.
   *
   * A qualification is added at a place the college is already at; setting up a
   * new place is what Add location is for. Reading it from `college_campuses`
   * means the form cannot offer a combination `course_offerings` would reject -
   * its college and campus columns point at that link, not at the two tables.
   */
  const campusOptionsFor = React.useCallback(
    (collegeId: string) =>
      links
        .filter((link) => String(link.college_id) === collegeId)
        .map((link) => {
          const campus = campuses.find((row) => row.id === link.campus_id);
          return {
            value: String(link.campus_id),
            // The full address, not just the name. A campus is a place, and the
            // name alone hides which one: `Haymarket` covers both 841 George St
            // and 8 Quay St, two buildings recorded as one campus.
            label: campus ? `${campus.campus_name} — ${campus.campus_location}` : String(link.campus_id),
          };
        }),
    [links, campuses],
  );

  function setPlace(index: number, patch: Partial<LocationRow>) {
    setPlaces((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  const placeComplete = (row: LocationRow) =>
    Boolean(row.collegeId) &&
    Boolean(row.campusId) &&
    Boolean(row.courseCode.trim()) &&
    Number(row.durationWeeks) > 0;

  /**
   * The stored qualification the typed values name, if there is one.
   *
   * By code when a code is typed; by title when there is none, because every
   * ELICOS course is code-less and four of them are told apart by title alone.
   */
  const knownQualification = React.useMemo(() => {
    const code = vetCode.trim().toUpperCase();
    if (code) {
      return (
        qualifications.find((row) => (row.qualification_code ?? '').toUpperCase() === code) ?? null
      );
    }
    const name = title.trim().toUpperCase();
    if (!name) return null;
    return (
      qualifications.find((row) => row.qualification_title.trim().toUpperCase() === name) ?? null
    );
  }, [qualifications, vetCode, title]);

  const canSave =
    places.length > 0 &&
    places.every(placeComplete) &&
    statusId !== null &&
    // A new qualification needs its title, level and sector. An existing one
    // brings all three with it.
    (knownQualification !== null ||
      (Boolean(title.trim()) && Boolean(newLevel) && Boolean(newSector)));

  async function save() {
    if (!canSave || statusId === null) return;
    setBusy(true);
    try {
      // Reused, never duplicated: the same national course offered at another
      // location is a new offering, not a second qualification.
      const id =
        knownQualification?.id ??
        (
          await referenceApi.createQualification({
            qualification_title: title.trim(),
            // A code-less qualification is normal: every ELICOS course has none.
            qualification_code: vetCode.trim().toUpperCase() || null,
            course_level: newLevel || null,
            course_sector: newSector || null,
          })
        ).id;

      for (const row of places) {
        await referenceApi.createCourse({
          college_id: Number(row.collegeId),
          campus_id: Number(row.campusId),
          qualification_id: id,
          course_code: row.courseCode.trim().toUpperCase(),
          course_status_id: statusId,
          total_course_cost: row.cost.trim() ? Number(row.cost) : null,
          duration_options: [Number(row.durationWeeks)],
        });
      }

      toast.success(
        knownQualification ? 'Qualification offered at this location' : 'Qualification created',
        {
          description: `${knownQualification?.qualification_title ?? title.trim()} — taught at ${
            places.length
          } location(s).`,
        },
      );
      onCreated?.(id);
      onOpenChange(false);
      onSaved();
    } catch (error) {
      toast.error('The record could not be saved', {
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
          <DialogTitle>Add a qualification at a location</DialogTitle>
          <DialogDescription>
            Name the qualification, then say where it is taught. A VET code that already exists
            brings its title and level with it.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-5">
          <FormGrid>
            <FormField
              label="VET code"
              htmlFor="course-vet-code"
              hint="Leave empty for an ELICOS course, which has none."
            >
              <Input
                id="course-vet-code"
                value={vetCode}
                onChange={(event) => setVetCode(event.target.value)}
                placeholder="e.g. BSB50820"
              />
            </FormField>
            <FormField
              label="Qualification title"
              htmlFor="course-title"
              required
              hint={
                knownQualification
                  ? 'This qualification already exists. It will be offered here, not created again.'
                  : 'A new qualification.'
              }
            >
              <Input
                id="course-title"
                value={knownQualification?.qualification_title ?? title}
                onChange={(event) => setTitle(event.target.value)}
                readOnly={Boolean(knownQualification)}
                placeholder="e.g. Diploma of Project Management"
              />
            </FormField>
            <FormField label="Course level" htmlFor="course-level" required={!knownQualification}>
              {knownQualification ? (
                <Input id="course-level" value={knownQualification.course_level ?? ''} readOnly />
              ) : (
                <SimpleSelect
                  id="course-level"
                  value={newLevel}
                  onChange={setNewLevel}
                  options={COURSE_LEVELS.map((value) => ({ value, label: value }))}
                  placeholder="Select level"
                />
              )}
            </FormField>
            <FormField label="Course sector" htmlFor="course-sector" required={!knownQualification}>
              {knownQualification ? (
                <Input id="course-sector" value={knownQualification.course_sector ?? ''} readOnly />
              ) : (
                <SimpleSelect
                  id="course-sector"
                  value={newSector}
                  onChange={setNewSector}
                  options={COURSE_SECTORS.map((value) => ({ value, label: value }))}
                  placeholder="Select sector"
                />
              )}
            </FormField>
          </FormGrid>


          {/* -- Where it is taught --------------------------------------- */}
          <div className="space-y-2">
            <p className="text-[13px] font-medium">
              Taught at <span className="text-destructive text-[11px]">REQUIRED</span>
            </p>
            <p className="text-[12px] text-muted-foreground">
              Only locations the chosen college already operates. Each has its own CRICOS
              registration and price, which is why they are entered per location.
            </p>

            <ul className="space-y-2">
              {places.map((row, index) => (
                <li key={index} className="space-y-2 rounded-md border border-border p-2.5">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-medium text-muted-foreground">
                      Location {index + 1}
                    </span>
                    {places.length > 1 && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="ml-auto h-7"
                        onClick={() => setPlaces((current) => current.filter((_, i) => i !== index))}
                      >
                        <Trash2 aria-hidden="true" className="size-3.5" />
                      </Button>
                    )}
                  </div>
                  <FormGrid>
                    <FormField label="College" htmlFor={`course-college-${index}`} required>
                      <DependentSelect
                        id={`course-college-${index}`}
                        value={row.collegeId}
                        onChange={(value) => setPlace(index, { collegeId: value, campusId: '' })}
                        options={colleges.map((college) => ({
                          value: String(college.id),
                          label: `${college.college_short_name} — ${college.college_full_name}`,
                        }))}
                        placeholder="Select college"
                      />
                    </FormField>
                    <FormField label="Location" htmlFor={`course-campus-${index}`} required>
                      <DependentSelect
                        id={`course-campus-${index}`}
                        value={row.campusId}
                        onChange={(value) => setPlace(index, { campusId: value })}
                        options={campusOptionsFor(row.collegeId)}
                        placeholder="Select location"
                        requires={row.collegeId ? undefined : 'a college'}
                      />
                    </FormField>
                    <FormField label="CRICOS code" htmlFor={`course-code-${index}`} required>
                      <Input
                        id={`course-code-${index}`}
                        value={row.courseCode}
                        onChange={(event) => setPlace(index, { courseCode: event.target.value })}
                        placeholder="e.g. 104262B"
                      />
                    </FormField>
                    <FormField label="Duration in weeks" htmlFor={`course-weeks-${index}`} required>
                      <Input
                        id={`course-weeks-${index}`}
                        type="number"
                        min={1}
                        value={row.durationWeeks}
                        onChange={(event) => setPlace(index, { durationWeeks: event.target.value })}
                      />
                    </FormField>
                    <FormField label="Total course cost" htmlFor={`course-cost-${index}`}>
                      <Input
                        id={`course-cost-${index}`}
                        type="number"
                        min={0}
                        value={row.cost}
                        onChange={(event) => setPlace(index, { cost: event.target.value })}
                        placeholder="e.g. 14600"
                      />
                    </FormField>
                  </FormGrid>
                </li>
              ))}
            </ul>

            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 text-[12px]"
              onClick={() => setPlaces((current) => [...current, EMPTY_LOCATION])}
            >
              <Plus aria-hidden="true" className="size-3.5" />
              Add another location
            </Button>
          </div>
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={!canSave || busy}>
            {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
            Add qualification
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
