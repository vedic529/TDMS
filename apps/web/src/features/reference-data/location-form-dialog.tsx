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
import { referenceApi, type ApiCollege, type ApiQualification } from '@/services/reference-api';


/**
 * One course taught at the location being added.
 *
 * The qualification is chosen, never typed. This form adds a *location*; a
 * course it does not have yet is a different job, and Add Qualification is where
 * that happens. Typing one here would create a qualification as a side effect of
 * registering a campus.
 */
interface CourseRow {
  qualificationId: string;
  courseCode: string;
  durationWeeks: string;
  cost: string;
}

const EMPTY_COURSE: CourseRow = {
  qualificationId: '',
  courseCode: '',
  durationWeeks: '',
  cost: '',
};

/** The states TDMS holds campuses in. */
const STATES = ['NSW', 'QLD', 'SA', 'TAS', 'VIC', 'WA', 'ACT', 'NT'];

/**
 * The stored code for a campus name.
 *
 * Derived, not asked for. Every campus in the database follows this exactly -
 * `Bundaberg Central` is `BUNDABERGCENTRAL`, `South Melbourne` is
 * `SOUTHMELBOURNE` - so asking a person to type it invites a value that differs
 * from the seven already stored, and the code is machinery rather than
 * information anyone holds.
 */
export function campusCodeFor(name: string): string {
  return name
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '')
    .slice(0, 50);
}

interface LocationFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
  /** Values carried in from a suggestion: the spelling seen, and its college. */
  prefill?: { name?: string; college?: string } | null;
  /** The new campus, so a suggestion can be resolved onto it. */
  onCreated?: (campusId: number) => void;
}

/**
 * Add a location to College Locations.
 *
 * A location is a campus, the link saying which college operates there, and what
 * that college teaches there. All three are written together.
 *
 * The courses are part of the record because a location without them is inert:
 * no student can enrol, no offering points at it, and the only thing left to do
 * with it is add a room. Every one of the eighteen college-campus links in the
 * database has at least one offering behind it - a location teaching nothing
 * would be the first.
 *
 * The link itself is not a later step either: a campus with no college appears in
 * no cascade and is what the integrity check reports as "campuses without a
 * college".
 */
export function LocationFormDialog({
  open,
  onOpenChange,
  onSaved,
  prefill,
  onCreated,
}: LocationFormDialogProps) {
  const [colleges, setColleges] = React.useState<ApiCollege[]>([]);
  const [collegeId, setCollegeId] = React.useState('');
  const [name, setName] = React.useState('');
  const [address, setAddress] = React.useState('');
  const [state, setState] = React.useState('');
  const [courses, setCourses] = React.useState<CourseRow[]>([]);
  const [qualifications, setQualifications] = React.useState<ApiQualification[]>([]);
  const [statusId, setStatusId] = React.useState<number | null>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setCollegeId('');
    setName(prefill?.name ?? '');
    setAddress('');
    setState('');
    setCourses([]);
    let cancelled = false;
    void (async () => {
      try {
        const [collegeRows, qualificationRows, statuses] = await Promise.all([
          referenceApi.listColleges({ activeOnly: true }),
          referenceApi.listQualifications({ activeOnly: true }),
          referenceApi.listCourseStatuses(),
        ]);
        if (cancelled) return;
        setColleges(collegeRows);
        const collegeKey = prefill?.college?.trim().toUpperCase();
        if (collegeKey) {
          const match = collegeRows.find(
            (row) =>
              row.college_short_name.toUpperCase() === collegeKey ||
              row.college_full_name.toUpperCase() === collegeKey,
          );
          if (match) setCollegeId(String(match.id));
        }
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

  const code = campusCodeFor(name);

  function courseComplete(row: CourseRow): boolean {
    return (
      Boolean(row.qualificationId) && Boolean(row.courseCode.trim()) && Number(row.durationWeeks) > 0
    );
  }

  // Courses are optional. A location can be registered before anything is
  // approved to run there, and a course TDMS does not have yet is added through
  // Add Qualification - which then asks where it is taught.
  const canSave =
    Boolean(collegeId && name.trim() && address.trim() && state && code) &&
    (courses.length === 0 || (statusId !== null && courses.every(courseComplete)));

  function setCourse(index: number, patch: Partial<CourseRow>) {
    setCourses((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  async function save() {
    if (!canSave) return;
    setBusy(true);
    try {
      const campus = await referenceApi.createCampus({
        campus_code: code,
        campus_name: name.trim(),
        campus_location: address.trim(),
        state,
      });
      // The campus and its college are one decision, so the link is written
      // here rather than left for someone to remember.
      await referenceApi.approveCollegeCampus({
        college_id: Number(collegeId),
        campus_id: campus.id,
        is_active: true,
      });
      // The courses the location teaches. Written after the link, because an
      // offering points at the college-campus pair rather than at the two
      // tables separately.
      for (const row of courses) {
        await referenceApi.createCourse({
          college_id: Number(collegeId),
          campus_id: campus.id,
          qualification_id: Number(row.qualificationId),
          course_code: row.courseCode.trim().toUpperCase(),
          course_status_id: statusId as number,
          total_course_cost: row.cost.trim() ? Number(row.cost) : null,
          duration_options: [Number(row.durationWeeks)],
        });
      }

      toast.success('Location added', {
        description: courses.length
          ? `${name.trim()} — ${courses.length} course(s) taught here.`
          : `${name.trim()} added. Use Add Qualification to record what is taught here.`,
      });
      onCreated?.(campus.id);
      onOpenChange(false);
      onSaved();
    } catch (error) {
      toast.error('The location could not be added', {
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
          <DialogTitle>Add a location</DialogTitle>
          <DialogDescription>
            A location is a campus and the college that operates there. Both are saved together.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-5">
          <FormGrid>
            <FormField label="College" htmlFor="loc-college" required>
              <DependentSelect
                id="loc-college"
                value={collegeId}
                onChange={setCollegeId}
                options={colleges.map((college) => ({
                  value: String(college.id),
                  label: `${college.college_short_name} — ${college.college_full_name}`,
                }))}
                placeholder="Select college"
              />
            </FormField>
            <FormField label="Location name" htmlFor="loc-name" required>
              <Input
                id="loc-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Parramatta"
              />
            </FormField>
            <FormField label="Address" htmlFor="loc-address" required>
              <Input
                id="loc-address"
                value={address}
                onChange={(event) => setAddress(event.target.value)}
                placeholder="e.g. 12 Smith St, Parramatta NSW 2150"
              />
            </FormField>
            <FormField label="State" htmlFor="loc-state" required>
              <SimpleSelect
                id="loc-state"
                value={state}
                onChange={setState}
                options={STATES.map((value) => ({ value, label: value }))}
                placeholder="Select state"
              />
            </FormField>
            <FormField
              label="Location code"
              htmlFor="loc-code"
              generated
              hint="Derived from the name."
            >
              <Input
                id="loc-code"
                value={code}
                readOnly
                className="font-mono text-[13px] font-medium text-foreground"
              />
            </FormField>
          </FormGrid>

          {/* -- What is taught here ------------------------------------- */}
          <div className="space-y-2">
            <p className="text-[13px] font-medium">
              Courses taught here <span className="text-[11px] text-muted-foreground">OPTIONAL</span>
            </p>
            <p className="text-[12px] text-muted-foreground">
              Chosen from the approved qualifications. A course TDMS does not have yet is added
              through Add Qualification, which asks where it is taught. The CRICOS code and
              duration belong to this college at this location, so they are entered per course.
            </p>

            {courses.length > 0 && (
              <ul className="space-y-2">
                {courses.map((row, index) => (
                  <li key={index} className="space-y-2 rounded-md border border-border p-2.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[12px] font-medium text-muted-foreground">
                        Course {index + 1}
                      </span>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="ml-auto h-7"
                        onClick={() =>
                          setCourses((current) => current.filter((_, i) => i !== index))
                        }
                      >
                        <Trash2 aria-hidden="true" className="size-3.5" />
                      </Button>
                    </div>
                    <FormGrid>
                      <FormField
                        label="Qualification"
                        htmlFor={`loc-course-qual-${index}`}
                        required
                      >
                        <DependentSelect
                          id={`loc-course-qual-${index}`}
                          value={row.qualificationId}
                          onChange={(value) => setCourse(index, { qualificationId: value })}
                          options={qualifications.map((q) => ({
                            value: String(q.id),
                            label: `${q.qualification_code ?? 'NA'} — ${q.qualification_title}`,
                          }))}
                          placeholder="Select qualification"
                        />
                      </FormField>
                      <FormField label="CRICOS code" htmlFor={`loc-course-code-${index}`} required>
                        <Input
                          id={`loc-course-code-${index}`}
                          value={row.courseCode}
                          onChange={(event) => setCourse(index, { courseCode: event.target.value })}
                          placeholder="e.g. 104262B"
                        />
                      </FormField>
                      <FormField
                        label="Duration in weeks"
                        htmlFor={`loc-course-weeks-${index}`}
                        required
                      >
                        <Input
                          id={`loc-course-weeks-${index}`}
                          type="number"
                          min={1}
                          value={row.durationWeeks}
                          onChange={(event) =>
                            setCourse(index, { durationWeeks: event.target.value })
                          }
                        />
                      </FormField>
                      <FormField label="Total course cost" htmlFor={`loc-course-cost-${index}`}>
                        <Input
                          id={`loc-course-cost-${index}`}
                          type="number"
                          min={0}
                          value={row.cost}
                          onChange={(event) => setCourse(index, { cost: event.target.value })}
                          placeholder="e.g. 14600"
                        />
                      </FormField>
                    </FormGrid>
                  </li>
                ))}
              </ul>
            )}

            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 text-[12px]"
              onClick={() => setCourses((current) => [...current, EMPTY_COURSE])}
            >
              <Plus aria-hidden="true" className="size-3.5" />
              Add another course
            </Button>
          </div>
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={!canSave || busy}>
            {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
            Add location
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
