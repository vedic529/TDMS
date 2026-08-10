'use client';

import * as React from 'react';
import { Eye, Loader2, Save } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { FormField, FormGrid, FormSection } from '@/components/common/form-field';
import { DependentSelect, SimpleSelect } from '@/components/common/dependent-select';
import { PreviewPanel } from '@/components/common/preview-panel';
import { ValidationPanel } from '@/components/common/validation-panel';
import { ConfirmationDialog } from '@/components/common/confirmation-dialog';
import { ChangeSummaryDialog, buildChanges } from '@/components/common/change-summary-dialog';
import { useReferenceData } from '@/features/shared/reference-data-context';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient } from '@/services';
import { formatCurrency, nowIso } from '@/lib/format';
import {
  COURSE_LEVEL_OPTIONS,
  COURSE_SECTOR_OPTIONS,
  COURSE_STATUS_OPTIONS,
  FIELD_OF_EDUCATION_BROAD_OPTIONS,
  FIELD_OF_EDUCATION_NARROW_OPTIONS,
} from '@/mock-data';
import type { ValidationIssue, ValidationResult } from '@/types/common';
import type { CourseRecord, CourseStatus } from '@/types/reference';
import type { CourseInput } from '@/services/tdms-client';

const EMPTY: CourseInput = {
  collegeId: '',
  campusId: '',
  courseCode: '',
  vetCode: '',
  courseStatus: 'Active',
  courseName: '',
  courseLevel: '',
  fieldOfEducationBroad: '',
  fieldOfEducationNarrow: '',
  courseSector: 'VET',
  durationInWeeks: 0,
  totalCourseCost: 0,
  location: '',
};

interface CourseFormDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: CourseRecord | null;
  /** Current course records, used for the COL-04 duplicate-offering check. */
  existingCourses: CourseRecord[];
  onSaved: () => void;
}

/** Create and edit for Course Data (COL-07). */
export function CourseFormDrawer({ open, onOpenChange, editing, existingCourses, onSaved }: CourseFormDrawerProps) {
  const { data, campusesForCollege, campusById, collegeById } = useReferenceData();
  const { user } = useAuth();

  const [input, setInput] = React.useState<CourseInput>(EMPTY);
  const [step, setStep] = React.useState<'form' | 'preview'>('form');
  const [validation, setValidation] = React.useState<ValidationResult | null>(null);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setStep('form');
    setValidation(null);
    if (editing) {
      const { id: _id, isDeleted: _d, deletion: _del, ...rest } = editing;
      setInput(rest);
    } else {
      setInput(EMPTY);
    }
  }, [open, editing]);

  function update<K extends keyof CourseInput>(key: K, value: CourseInput[K]) {
    setInput((current) => ({ ...current, [key]: value }));
    setValidation(null);
    setStep('form');
  }

  function selectCampus(campusId: string) {
    const campus = campusById(campusId);
    setInput((current) => ({ ...current, campusId, location: campus?.campusLocation ?? current.location }));
    setValidation(null);
    setStep('form');
  }

  function runPreview() {
    const issues: ValidationIssue[] = [];
    const required: Array<[string, unknown, string]> = [
      ['College', input.collegeId, 'Select the college that offers the course.'],
      ['Campus', input.campusId, 'Select an approved campus for the selected college.'],
      ['Course Code', input.courseCode, 'Enter the approved internal or source-system code for the course.'],
      ['VET Code', input.vetCode, 'Enter the code supplied in the approved VET course source.'],
      ['Course Name', input.courseName, 'Enter the approved course title.'],
      ['Course Level', input.courseLevel, 'Select the approved level or award type.'],
      ['Duration in Weeks', input.durationInWeeks, 'Enter the approved course duration in weeks.'],
    ];
    for (const [label, value, message] of required) {
      if (!value) {
        issues.push({
          id: `course-${label}`,
          severity: 'blocking',
          title: `${label} is required`,
          message,
          reference: label,
        });
      }
    }

    // COL-04: the same approved college, campus and qualification offering must
    // not be stored more than once.
    const duplicate = existingCourses.find(
      (course) =>
        course.id !== editing?.id &&
        course.collegeId === input.collegeId &&
        course.campusId === input.campusId &&
        course.vetCode.trim().toUpperCase() === input.vetCode.trim().toUpperCase(),
    );
    if (duplicate) {
      issues.push({
        id: 'course-duplicate',
        severity: 'blocking',
        title: 'Duplicate offering',
        message: `${duplicate.courseCode} already stores VET Code ${duplicate.vetCode} for this college and campus. The same approved offering must not be stored more than once.`,
        reference: 'VET Code',
      });
    }

    setValidation({
      issues,
      canSave: issues.filter((issue) => issue.severity === 'blocking').length === 0,
      checkedAt: nowIso(),
    });
    setStep('preview');
  }

  async function save() {
    if (!user || !validation?.canSave) return;
    setBusy(true);
    try {
      const client = getTdmsClient();
      if (editing) {
        await client.updateCourse(editing.id, input, { actor: user });
        toast.success('Course updated', { description: `${input.courseCode} was updated.` });
      } else {
        await client.createCourse(input, { actor: user });
        toast.success('Course added', { description: `${input.courseCode} was added to Course Data.` });
      }
      setConfirmOpen(false);
      onOpenChange(false);
      onSaved();
    } catch (error) {
      toast.error('The course record could not be saved', {
        description: error instanceof Error ? error.message : 'Try again, or contact the TDMS administrator.',
      });
    } finally {
      setBusy(false);
    }
  }

  const changes = editing
    ? buildChanges(editing as unknown as Record<string, unknown>, input as unknown as Record<string, unknown>, [
        { key: 'courseCode', label: 'Course Code' },
        { key: 'vetCode', label: 'VET Code' },
        { key: 'courseStatus', label: 'Course Status' },
        { key: 'courseName', label: 'Course Name' },
        { key: 'courseLevel', label: 'Course Level' },
        { key: 'fieldOfEducationBroad', label: 'Field of Education - Broad' },
        { key: 'fieldOfEducationNarrow', label: 'Field of Education - Narrow' },
        { key: 'courseSector', label: 'Course Sector' },
        { key: 'durationInWeeks', label: 'Duration in Weeks' },
        { key: 'totalCourseCost', label: 'Total Course Cost' },
        { key: 'location', label: 'Location' },
      ])
    : [];

  const groups = [
    {
      title: 'Course identification',
      items: [
        { label: 'College', value: collegeById(input.collegeId)?.collegeFullName ?? '' },
        { label: 'Campus', value: campusById(input.campusId)?.campusName ?? '' },
        { label: 'Course Code', value: input.courseCode },
        { label: 'VET Code', value: input.vetCode },
        { label: 'Course Status', value: input.courseStatus },
        { label: 'Course Name', value: input.courseName },
      ],
    },
    {
      title: 'Classification, duration, cost and location',
      items: [
        { label: 'Course Level', value: input.courseLevel },
        { label: 'Field of Education - Broad', value: input.fieldOfEducationBroad },
        { label: 'Field of Education - Narrow', value: input.fieldOfEducationNarrow },
        { label: 'Course Sector', value: input.courseSector },
        { label: 'Duration in Weeks', value: input.durationInWeeks ? `${input.durationInWeeks} weeks` : '' },
        { label: 'Total Course Cost', value: formatCurrency(input.totalCourseCost) },
        { label: 'Location', value: input.location },
      ],
    },
  ];

  return (
    <>
      <Sheet open={open} onOpenChange={busy ? undefined : onOpenChange}>
        <SheetContent width="lg">
          <SheetHeader>
            <SheetTitle>{editing ? 'Edit Course' : 'Create Course'}</SheetTitle>
            <SheetDescription>
              {step === 'form'
                ? 'Complete the course reference data, then preview before confirming.'
                : 'This is the proposed course record. It has not been saved.'}
            </SheetDescription>
          </SheetHeader>

          <SheetBody className="space-y-7">
            {step === 'form' ? (
              <>
                <FormSection title="Course identification">
                  <FormGrid>
                    <FormField label="College" htmlFor="course-college" required>
                      <DependentSelect
                        id="course-college"
                        value={input.collegeId}
                        onChange={(value) => {
                          setInput((current) => ({ ...current, collegeId: value, campusId: '' }));
                          setValidation(null);
                          setStep('form');
                        }}
                        options={(data?.colleges ?? []).map((college) => ({
                          value: college.id,
                          label: college.collegeFullName,
                        }))}
                        placeholder="Select college"
                      />
                    </FormField>
                    <FormField label="Campus" htmlFor="course-campus" required>
                      <DependentSelect
                        id="course-campus"
                        value={input.campusId}
                        onChange={selectCampus}
                        options={campusesForCollege(input.collegeId).map((campus) => ({
                          value: campus.id,
                          label: campus.campusName,
                        }))}
                        placeholder="Select campus"
                        requires={input.collegeId ? undefined : 'a college'}
                      />
                    </FormField>
                    <FormField label="Course Code" htmlFor="course-code" required>
                      <Input
                        id="course-code"
                        value={input.courseCode}
                        onChange={(event) => update('courseCode', event.target.value)}
                      />
                    </FormField>
                    <FormField label="VET Code" htmlFor="course-vet-code" required>
                      <Input
                        id="course-vet-code"
                        value={input.vetCode}
                        onChange={(event) => update('vetCode', event.target.value)}
                      />
                    </FormField>
                    <FormField label="Course Status" htmlFor="course-status" required>
                      <SimpleSelect
                        id="course-status"
                        value={input.courseStatus}
                        onChange={(value) => update('courseStatus', value as CourseStatus)}
                        options={COURSE_STATUS_OPTIONS.map((status) => ({ value: status, label: status }))}
                        placeholder="Select status"
                      />
                    </FormField>
                    <FormField label="Course Name" htmlFor="course-name" required>
                      <Input
                        id="course-name"
                        value={input.courseName}
                        onChange={(event) => update('courseName', event.target.value)}
                      />
                    </FormField>
                  </FormGrid>
                </FormSection>

                <FormSection title="Classification, duration, cost and location">
                  <FormGrid>
                    <FormField label="Course Level" htmlFor="course-level" required>
                      <SimpleSelect
                        id="course-level"
                        value={input.courseLevel}
                        onChange={(value) => update('courseLevel', value)}
                        options={COURSE_LEVEL_OPTIONS.map((level) => ({ value: level, label: level }))}
                        placeholder="Select level"
                      />
                    </FormField>
                    <FormField label="Course Sector" htmlFor="course-sector">
                      <SimpleSelect
                        id="course-sector"
                        value={input.courseSector}
                        onChange={(value) => update('courseSector', value)}
                        options={COURSE_SECTOR_OPTIONS.map((sector) => ({ value: sector, label: sector }))}
                        placeholder="Select sector"
                      />
                    </FormField>
                    <FormField label="Field of Education - Broad" htmlFor="course-foe-broad">
                      <SimpleSelect
                        id="course-foe-broad"
                        value={input.fieldOfEducationBroad}
                        onChange={(value) => update('fieldOfEducationBroad', value)}
                        options={FIELD_OF_EDUCATION_BROAD_OPTIONS.map((option) => ({ value: option, label: option }))}
                        placeholder="Select classification"
                      />
                    </FormField>
                    <FormField label="Field of Education - Narrow" htmlFor="course-foe-narrow">
                      <SimpleSelect
                        id="course-foe-narrow"
                        value={input.fieldOfEducationNarrow}
                        onChange={(value) => update('fieldOfEducationNarrow', value)}
                        options={FIELD_OF_EDUCATION_NARROW_OPTIONS.map((option) => ({ value: option, label: option }))}
                        placeholder="Select classification"
                      />
                    </FormField>
                    <FormField label="Duration in Weeks" htmlFor="course-duration" required>
                      <Input
                        id="course-duration"
                        type="number"
                        min={0}
                        value={input.durationInWeeks || ''}
                        onChange={(event) => update('durationInWeeks', Number(event.target.value))}
                      />
                    </FormField>
                    <FormField label="Total Course Cost" htmlFor="course-cost">
                      <Input
                        id="course-cost"
                        type="number"
                        min={0}
                        value={input.totalCourseCost || ''}
                        onChange={(event) => update('totalCourseCost', Number(event.target.value))}
                      />
                    </FormField>
                    <FormField label="Location" htmlFor="course-location">
                      <Input
                        id="course-location"
                        value={input.location}
                        onChange={(event) => update('location', event.target.value)}
                      />
                    </FormField>
                  </FormGrid>
                </FormSection>
              </>
            ) : (
              <div className="space-y-6">
                <PreviewPanel groups={groups} />
                <div>
                  <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
                    Validation results
                  </h3>
                  <ValidationPanel result={validation} />
                </div>
              </div>
            )}
          </SheetBody>

          <SheetFooter>
            {step === 'preview' && (
              <Button variant="ghost" onClick={() => setStep('form')} disabled={busy}>
                Back to form
              </Button>
            )}
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
            {step === 'form' ? (
              <Button onClick={runPreview}>
                <Eye aria-hidden="true" />
                Preview
              </Button>
            ) : (
              <Button onClick={() => setConfirmOpen(true)} disabled={!validation?.canSave || busy}>
                {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
                {editing ? 'Confirm Update' : 'Confirm Add'}
              </Button>
            )}
          </SheetFooter>
        </SheetContent>
      </Sheet>

      {editing ? (
        <ChangeSummaryDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Update Course Record?"
          description="Check the record and the fields that will change, then confirm the update."
          record={{ primary: editing.courseCode, secondary: editing.courseName, lines: [editing.location] }}
          changes={changes}
          busy={busy}
          onConfirm={save}
        />
      ) : (
        <ConfirmationDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Add Course Record?"
          description="Please confirm that you want to add this course to the approved reference data."
          confirmLabel="Confirm Add"
          busy={busy}
          onConfirm={save}
          size="lg"
        >
          <PreviewPanel groups={groups} />
        </ConfirmationDialog>
      )}
    </>
  );
}
