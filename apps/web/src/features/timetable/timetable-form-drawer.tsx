'use client';

import * as React from 'react';
import { AlertTriangle, ArrowLeft, Eye, Loader2, Save, Wand2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { FormField, FormGrid, FormSection } from '@/components/common/form-field';
import { DependentSelect, SimpleSelect } from '@/components/common/dependent-select';
import { PreviewPanel } from '@/components/common/preview-panel';
import { ValidationPanel } from '@/components/common/validation-panel';
import { ConfirmationDialog } from '@/components/common/confirmation-dialog';
import { ChangeSummaryDialog, buildChanges } from '@/components/common/change-summary-dialog';
import { PendingRuleNotice } from '@/components/common/states';
import { SlotEditor } from './slot-editor';
import { validateTimetableInput } from './validation';
import { useReferenceData } from '@/features/shared/reference-data-context';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient } from '@/services';
import { addDays, formatDate, formatSlots } from '@/lib/format';
import { MSCRIS_CLASS_NAME } from '@/mock-data';
import type { ValidationResult } from '@/types/common';
import type { TimetableInput, TimetableSession } from '@/types/timetable';
import type { UocType } from '@/types/reference';

type Mode = 'create' | 'generate' | 'edit';

interface TimetableFormDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: Mode;
  existingSessions: TimetableSession[];
  editing?: TimetableSession | null;
  onSaved: () => void;
}

const EMPTY_INPUT: TimetableInput = {
  collegeId: '',
  campusId: '',
  qualificationCode: '',
  qualificationName: '',
  durationInWeeks: 0,
  group: '',
  classroomSize: 0,
  uocCode: '',
  uocTitle: '',
  uocType: 'Theory',
  modeOfDelivery: 'Physical',
  uocStartDate: '',
  uocEndDate: '',
  theoryDaysAndTimes: [],
  theoryClassroomName: '',
  theoryClassroomCapacity: 0,
  theoryTrainerId: '',
  practicalClassroomName: '',
  practicalClassroomCapacity: 0,
  practicalDaysAndTimes: [],
  practicalTrainerId: '',
  mscrisClassName: '',
  mscrisDaysAndTimes: [],
  mscrisTrainerId: '',
  remarks: '',
};

const CHANGE_FIELDS: Array<{ key: keyof TimetableInput & string; label: string; format?: (value: unknown) => string }> = [
  { key: 'group', label: 'Group' },
  { key: 'qualificationCode', label: 'Qualification Code' },
  { key: 'durationInWeeks', label: 'Duration in Weeks' },
  { key: 'classroomSize', label: 'Classroom Size' },
  { key: 'uocCode', label: 'UoC Code' },
  { key: 'uocType', label: 'UoC Type' },
  { key: 'modeOfDelivery', label: 'Mode of Delivery' },
  { key: 'uocStartDate', label: 'UoC Start Date' },
  { key: 'uocEndDate', label: 'UoC End Date' },
  {
    key: 'theoryDaysAndTimes',
    label: 'Theory Days and Times',
    format: (value) => formatSlots(value as TimetableInput['theoryDaysAndTimes']),
  },
  { key: 'theoryClassroomName', label: 'Theory Classroom Name' },
  { key: 'theoryTrainerId', label: 'Theory Trainer' },
  { key: 'practicalClassroomName', label: 'Practical Classroom Name' },
  {
    key: 'practicalDaysAndTimes',
    label: 'Practical Days and Times',
    format: (value) => formatSlots(value as TimetableInput['practicalDaysAndTimes']),
  },
  { key: 'practicalTrainerId', label: 'Practical Trainer' },
  { key: 'mscrisClassName', label: 'MSCRIS Class Name' },
  {
    key: 'mscrisDaysAndTimes',
    label: 'MSCRIS Days and Times',
    format: (value) => formatSlots(value as TimetableInput['mscrisDaysAndTimes']),
  },
  { key: 'mscrisTrainerId', label: 'MSCRIS Trainer' },
  { key: 'remarks', label: 'Remarks' },
];

/**
 * Create, Generate and Edit for a timetable record.
 *
 * SRS 5.1 / TT-04 / TT-12: nothing is written when the drawer opens or when
 * Preview runs. The order is always
 * enter selections -> Preview -> validation results -> confirmation -> Save.
 */
export function TimetableFormDrawer({
  open,
  onOpenChange,
  mode,
  existingSessions,
  editing,
  onSaved,
}: TimetableFormDrawerProps) {
  const { data, campusesForCollege, offeringsFor } = useReferenceData();
  const { user } = useAuth();

  const [step, setStep] = React.useState<'form' | 'preview'>('form');
  const [input, setInput] = React.useState<TimetableInput>(EMPTY_INPUT);
  const [validation, setValidation] = React.useState<ValidationResult | null>(null);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [generated, setGenerated] = React.useState(false);

  const isGenerate = mode === 'generate';
  const isEdit = mode === 'edit';

  React.useEffect(() => {
    if (!open) return;
    setStep('form');
    setValidation(null);
    setGenerated(false);
    if (editing) {
      const { id: _id, recordNumber: _n, createdAt: _c, updatedAt: _u, isDeleted: _d, deletion: _del, ...rest } = editing;
      setInput(rest);
    } else {
      setInput(EMPTY_INPUT);
    }
  }, [open, editing]);

  function update<K extends keyof TimetableInput>(key: K, value: TimetableInput[K]) {
    setInput((current) => ({ ...current, [key]: value }));
    setValidation(null);
    setStep('form');
  }

  /**
   * OD-11 approved: MSCRIS Class Name always holds the single fixed value, so
   * it is set as soon as any MSCRIS detail is entered and cleared when the
   * section is emptied again.
   */
  React.useEffect(() => {
    const hasDetail = input.mscrisDaysAndTimes.length > 0 || input.mscrisTrainerId.trim() !== '';
    const expected = hasDetail ? MSCRIS_CLASS_NAME : '';
    if (input.mscrisClassName !== expected) {
      setInput((current) => ({ ...current, mscrisClassName: expected }));
    }
  }, [input.mscrisDaysAndTimes, input.mscrisTrainerId, input.mscrisClassName]);

  // ------------------------------------------------------------- selections
  const campuses = campusesForCollege(input.collegeId);
  const offerings = offeringsFor(input.collegeId, input.campusId);
  const offering = offerings.find((entry) => entry.qualificationCode === input.qualificationCode);
  const facilities = (data?.facilities ?? []).filter(
    (facility) => facility.campusId === input.campusId && facility.isActive,
  );
  const unitSequence = (data?.qualificationUnitSequences ?? [])
    .filter(
      (entry) =>
        entry.qualificationCode === input.qualificationCode &&
        (!input.campusId || entry.campusId === input.campusId),
    )
    .sort((a, b) => a.deliveryOrder - b.deliveryOrder);

  const eligibleTrainers = (data?.trainers ?? []).filter(
    (trainer) => trainer.isActive && trainer.qualificationsCanTeach.includes(input.qualificationCode),
  );
  const trainerOptions = eligibleTrainers.map((trainer) => ({
    value: trainer.trainerId,
    label: `${trainer.trainerName} (${trainer.trainerId})`,
  }));

  const classroomOptions = facilities
    .filter((facility) => facility.facilityType === 'Classroom' || facility.facilityType === 'Computer Lab')
    .map((facility) => ({
      value: facility.facilityReference,
      label: `${facility.facilityReference} · ${facility.facilityType} · capacity ${facility.capacity}`,
    }));

  const practicalOptions = facilities
    .filter((facility) => facility.facilityType === 'Commercial Kitchen' || facility.facilityType === 'Workshop')
    .map((facility) => ({
      value: facility.facilityReference,
      label: `${facility.facilityReference} · ${facility.facilityType} · capacity ${facility.capacity}`,
    }));

  const groupOptions = (data?.groups ?? []).map((group) => ({ value: group, label: group }));

  function selectCollege(collegeId: string) {
    setInput((current) => ({
      ...current,
      collegeId,
      campusId: '',
      qualificationCode: '',
      qualificationName: '',
      durationInWeeks: 0,
      theoryClassroomName: '',
      theoryClassroomCapacity: 0,
      practicalClassroomName: '',
      practicalClassroomCapacity: 0,
    }));
    setValidation(null);
    setStep('form');
  }

  function selectCampus(campusId: string) {
    setInput((current) => ({
      ...current,
      campusId,
      qualificationCode: '',
      qualificationName: '',
      theoryClassroomName: '',
      theoryClassroomCapacity: 0,
      practicalClassroomName: '',
      practicalClassroomCapacity: 0,
    }));
    setValidation(null);
    setStep('form');
  }

  function selectQualification(code: string) {
    const selected = offerings.find((entry) => entry.qualificationCode === code);
    setInput((current) => ({
      ...current,
      qualificationCode: code,
      qualificationName: selected?.qualificationTitle ?? '',
      durationInWeeks: selected?.durationOptions[0] ?? 0,
      uocCode: '',
      uocTitle: '',
      theoryTrainerId: '',
      practicalTrainerId: '',
      mscrisTrainerId: '',
    }));
    setValidation(null);
    setStep('form');
  }

  function selectUnit(unitCode: string) {
    const unit = unitSequence.find((entry) => entry.unitCode === unitCode);
    setInput((current) => ({
      ...current,
      uocCode: unitCode,
      uocTitle: unit?.unitTitle ?? '',
      uocType: (unit?.uocType ?? 'Theory') as UocType,
    }));
    setValidation(null);
    setStep('form');
  }

  function selectFacility(kind: 'theory' | 'practical', reference: string) {
    const facility = facilities.find((entry) => entry.facilityReference === reference);
    setInput((current) =>
      kind === 'theory'
        ? { ...current, theoryClassroomName: reference, theoryClassroomCapacity: facility?.capacity ?? 0 }
        : { ...current, practicalClassroomName: reference, practicalClassroomCapacity: facility?.capacity ?? 0 },
    );
    setValidation(null);
    setStep('form');
  }

  // -------------------------------------------------------------- generation
  /**
   * Proposes the next unit and its dates from the approved qualification-unit
   * sequence and the approved offering. It does not apply any break rule:
   * TT-11 / OD-07 keep break placement unapproved, so the proposal only fills
   * fields that are derived from approved reference data.
   */
  function generateProposal() {
    if (!input.qualificationCode || !input.group || !input.uocStartDate) {
      toast.warning('More information is needed', {
        description: 'Select the qualification, the group and a start date before generating a proposal.',
      });
      return;
    }

    const scheduled = new Set(
      existingSessions.filter((session) => session.group === input.group).map((session) => session.uocCode),
    );
    const nextUnit = unitSequence.find((entry) => !scheduled.has(entry.unitCode)) ?? unitSequence[0];
    if (!nextUnit) {
      toast.warning('No approved unit is available', {
        description: 'This qualification has no approved unit sequence records for the selected campus.',
      });
      return;
    }

    const weeksPerUnit = Math.max(1, Math.round((input.durationInWeeks || 52) / Math.max(1, unitSequence.length)));
    const endDate = addDays(input.uocStartDate, weeksPerUnit * 7 - 3);
    const requiresPractical = nextUnit.uocType === 'Theory and Practical';

    setInput((current) => ({
      ...current,
      uocCode: nextUnit.unitCode,
      uocTitle: nextUnit.unitTitle,
      uocType: nextUnit.uocType,
      uocEndDate: endDate,
      theoryDaysAndTimes: [
        { day: 'Monday', startTime: '09:00', endTime: '13:00' },
        { day: 'Tuesday', startTime: '09:00', endTime: '13:00' },
      ],
      practicalDaysAndTimes: requiresPractical ? [{ day: 'Thursday', startTime: '08:00', endTime: '14:00' }] : [],
      theoryClassroomName: current.theoryClassroomName || (classroomOptions[0]?.value ?? ''),
      theoryClassroomCapacity:
        current.theoryClassroomCapacity ||
        (facilities.find((f) => f.facilityReference === classroomOptions[0]?.value)?.capacity ?? 0),
      practicalClassroomName: requiresPractical
        ? current.practicalClassroomName || (practicalOptions[0]?.value ?? '')
        : '',
      practicalClassroomCapacity: requiresPractical
        ? current.practicalClassroomCapacity ||
          (facilities.find((f) => f.facilityReference === practicalOptions[0]?.value)?.capacity ?? 0)
        : 0,
      theoryTrainerId: current.theoryTrainerId || (trainerOptions[0]?.value ?? ''),
    }));
    setGenerated(true);
    setValidation(null);
    setStep('form');
    toast.success('Proposal generated', {
      description: 'Nothing has been saved. Check the proposal, then run Preview.',
    });
  }

  // ---------------------------------------------------------------- preview
  function runPreview() {
    const result = validateTimetableInput(input, {
      existingSessions,
      trainers: data?.trainers ?? [],
      facilities: data?.facilities ?? [],
      offerings: data?.qualificationOfferings ?? [],
      unitSequences: data?.qualificationUnitSequences ?? [],
      editingId: editing?.id,
    });
    setValidation(result);
    setStep('preview');
  }

  async function save() {
    if (!user || !validation?.canSave) return;
    setBusy(true);
    try {
      const client = getTdmsClient();
      if (isEdit && editing) {
        await client.updateTimetableSession(editing.id, input, { actor: user });
        toast.success('Timetable record updated', {
          description: `${editing.recordNumber} was updated and a user activity record was created.`,
        });
      } else {
        const created = await client.createTimetableSession(input, { actor: user });
        toast.success('Timetable record saved', {
          description: `${created.recordNumber} was created and a user activity record was created.`,
        });
      }
      setConfirmOpen(false);
      onOpenChange(false);
      onSaved();
    } catch (error) {
      toast.error('The timetable record could not be saved', {
        description: error instanceof Error ? error.message : 'Try again, or contact the TDMS administrator.',
      });
    } finally {
      setBusy(false);
    }
  }

  const changes = editing
    ? buildChanges(
        {
          ...editing,
        } as unknown as Record<string, unknown>,
        input as unknown as Record<string, unknown>,
        CHANGE_FIELDS as unknown as Array<{
          key: string;
          label: string;
          format?: (value: unknown) => string;
        }>,
      )
    : [];

  const title = isEdit ? 'Edit Timetable Record' : isGenerate ? 'Generate Timetable' : 'Create Timetable';

  return (
    <>
      <Sheet open={open} onOpenChange={busy ? undefined : onOpenChange}>
        <SheetContent width="xl">
          <SheetHeader>
            <SheetTitle>{title}</SheetTitle>
            <SheetDescription>
              {step === 'form'
                ? 'Select approved reference values, then run Preview. Nothing is saved until validation passes and you confirm.'
                : 'This is the proposed timetable record. It has not been saved.'}
            </SheetDescription>
          </SheetHeader>

          <SheetBody className="space-y-7">
            {step === 'form' ? (
              <>
                {isGenerate && (
                  <Alert variant="info">
                    <Wand2 aria-hidden="true" />
                    <AlertDescription>
                      Generate proposes the next unit and its dates from the approved qualification and unit sequence.
                      Generated values are shown as read-only until you preview and confirm.
                    </AlertDescription>
                  </Alert>
                )}

                <FormSection title="Timetable Basic Details">
                  <FormGrid>
                    <FormField label="College" htmlFor="tt-college" required>
                      <DependentSelect
                        id="tt-college"
                        value={input.collegeId}
                        onChange={selectCollege}
                        options={(data?.colleges ?? [])
                          .filter((college) => college.isActive)
                          .map((college) => ({ value: college.id, label: college.collegeFullName }))}
                        placeholder="Select college"
                      />
                    </FormField>

                    <FormField label="Campus Location" htmlFor="tt-campus" required>
                      <DependentSelect
                        id="tt-campus"
                        value={input.campusId}
                        onChange={selectCampus}
                        options={campuses.map((campus) => ({
                          value: campus.id,
                          label: `${campus.campusName} — ${campus.campusLocation}`,
                        }))}
                        placeholder="Select campus location"
                        requires={input.collegeId ? undefined : 'a college'}
                      />
                    </FormField>

                    <FormField label="Qualification Code" htmlFor="tt-qualification" required>
                      <DependentSelect
                        id="tt-qualification"
                        value={input.qualificationCode}
                        onChange={selectQualification}
                        options={offerings.map((entry) => ({
                          value: entry.qualificationCode,
                          label: `${entry.qualificationCode} — ${entry.qualificationTitle}`,
                        }))}
                        placeholder="Select qualification"
                        requires={input.campusId ? undefined : 'a campus'}
                      />
                    </FormField>

                    <FormField
                      label="Qualification Name"
                      htmlFor="tt-qualification-name"
                      generated
                      hint="Derived from the selected qualification."
                    >
                      <Input id="tt-qualification-name" value={input.qualificationName} readOnly />
                    </FormField>

                    <FormField
                      label="Duration in Weeks"
                      htmlFor="tt-duration"
                      required
                      hint="Approved duration options come from the qualification offering."
                    >
                      <SimpleSelect
                        id="tt-duration"
                        value={input.durationInWeeks ? String(input.durationInWeeks) : ''}
                        onChange={(value) => update('durationInWeeks', Number(value))}
                        options={(offering?.durationOptions ?? []).map((weeks) => ({
                          value: String(weeks),
                          label: `${weeks} weeks`,
                        }))}
                        placeholder="Select duration"
                        disabled={!offering}
                      />
                    </FormField>

                    <FormField label="Group" htmlFor="tt-group" required>
                      <Input
                        id="tt-group"
                        value={input.group}
                        list="tt-group-options"
                        onChange={(event) => update('group', event.target.value)}
                        placeholder="e.g. BSB50420-MEL-AUG2026"
                      />
                    </FormField>
                    <datalist id="tt-group-options">
                      {groupOptions.map((option) => (
                        <option key={option.value} value={option.value} />
                      ))}
                    </datalist>

                    <FormField label="Classroom Size" htmlFor="tt-classroom-size" required>
                      <Input
                        id="tt-classroom-size"
                        type="number"
                        min={0}
                        value={input.classroomSize || ''}
                        onChange={(event) => update('classroomSize', Number(event.target.value))}
                        placeholder="Expected number of students"
                      />
                    </FormField>
                  </FormGrid>
                </FormSection>

                {isGenerate && (
                  <div className="rounded-lg border border-border bg-muted/40 p-4">
                    <p className="text-[13px] font-medium text-foreground">Generate the unit proposal</p>
                    <p className="mt-1 text-[12px] text-muted-foreground">
                      TDMS proposes the next unit in the approved sequence and its dates. Break placement is not
                      applied because the rules are not approved yet (OD-07).
                    </p>
                    <div className="mt-3 flex flex-wrap items-end gap-3">
                      <FormField label="UoC Start Date" htmlFor="tt-generate-start" required className="w-52">
                        <Input
                          id="tt-generate-start"
                          type="date"
                          value={input.uocStartDate}
                          onChange={(event) => update('uocStartDate', event.target.value)}
                        />
                      </FormField>
                      <Button variant="outline" onClick={generateProposal}>
                        <Wand2 aria-hidden="true" />
                        Generate proposal
                      </Button>
                    </div>
                  </div>
                )}

                <FormSection title="Unit Details">
                  <FormGrid>
                    <FormField label="UoC Code" htmlFor="tt-uoc" required>
                      {isGenerate && generated ? (
                        <Input id="tt-uoc" value={input.uocCode} readOnly />
                      ) : (
                        <DependentSelect
                          id="tt-uoc"
                          value={input.uocCode}
                          onChange={selectUnit}
                          options={unitSequence.map((entry) => ({
                            value: entry.unitCode,
                            label: `${entry.deliveryOrder}. ${entry.unitCode} — ${entry.unitTitle}`,
                          }))}
                          placeholder="Select unit of competency"
                          requires={input.qualificationCode ? undefined : 'a qualification'}
                        />
                      )}
                    </FormField>

                    <FormField label="UoC Title" htmlFor="tt-uoc-title" generated hint="Derived from UoC Code.">
                      <Input id="tt-uoc-title" value={input.uocTitle} readOnly />
                    </FormField>

                    <FormField label="UoC Type" htmlFor="tt-uoc-type" generated hint="Derived from approved unit data.">
                      <Input id="tt-uoc-type" value={input.uocType} readOnly />
                    </FormField>

                    <FormField label="Mode of Delivery" htmlFor="tt-mode" required>
                      <SimpleSelect
                        id="tt-mode"
                        value={input.modeOfDelivery}
                        onChange={(value) => update('modeOfDelivery', value as TimetableInput['modeOfDelivery'])}
                        options={[
                          { value: 'Physical', label: 'Physical' },
                          { value: 'Virtual', label: 'Virtual' },
                        ]}
                        placeholder="Select mode of delivery"
                      />
                    </FormField>

                    <FormField label="UoC Start Date" htmlFor="tt-start" required>
                      <Input
                        id="tt-start"
                        type="date"
                        value={input.uocStartDate}
                        onChange={(event) => update('uocStartDate', event.target.value)}
                      />
                    </FormField>

                    <FormField
                      label="UoC End Date"
                      htmlFor="tt-end"
                      required
                      generated={isGenerate && generated}
                      hint={isGenerate && generated ? 'Calculated from the approved duration.' : undefined}
                    >
                      <Input
                        id="tt-end"
                        type="date"
                        value={input.uocEndDate}
                        readOnly={isGenerate && generated}
                        onChange={(event) => update('uocEndDate', event.target.value)}
                      />
                    </FormField>
                  </FormGrid>
                </FormSection>

                <FormSection title="Theory">
                  <FormGrid>
                    <FormField label="Theory Classroom Name" htmlFor="tt-theory-room">
                      <DependentSelect
                        id="tt-theory-room"
                        value={input.theoryClassroomName}
                        onChange={(value) => selectFacility('theory', value)}
                        options={classroomOptions}
                        placeholder="Select approved room"
                        requires={input.campusId ? undefined : 'a campus'}
                      />
                    </FormField>
                    <FormField
                      label="Theory Classroom Capacity"
                      htmlFor="tt-theory-capacity"
                      generated
                      hint="Derived from approved facility data."
                    >
                      <Input id="tt-theory-capacity" value={input.theoryClassroomCapacity || ''} readOnly />
                    </FormField>
                    <FormField label="Theory Trainer" htmlFor="tt-theory-trainer">
                      <DependentSelect
                        id="tt-theory-trainer"
                        value={input.theoryTrainerId}
                        onChange={(value) => update('theoryTrainerId', value)}
                        options={trainerOptions}
                        placeholder="Select approved trainer"
                        requires={input.qualificationCode ? undefined : 'a qualification'}
                        emptyMessage="No active trainer is approved for this qualification."
                      />
                    </FormField>
                  </FormGrid>
                  <FormField label="Theory Days and Times" htmlFor="tt-theory-slots">
                    <SlotEditor
                      id="tt-theory-slots"
                      label="theory"
                      slots={input.theoryDaysAndTimes}
                      onChange={(slots) => update('theoryDaysAndTimes', slots)}
                    />
                  </FormField>
                </FormSection>

                <FormSection
                  title="Practical"
                  description={
                    input.uocType === 'Theory'
                      ? 'This unit is recorded as theory only, so practical values are optional.'
                      : undefined
                  }
                >
                  <FormGrid>
                    <FormField label="Practical Classroom Name" htmlFor="tt-practical-room">
                      <DependentSelect
                        id="tt-practical-room"
                        value={input.practicalClassroomName}
                        onChange={(value) => selectFacility('practical', value)}
                        options={practicalOptions}
                        placeholder="Select approved facility"
                        requires={input.campusId ? undefined : 'a campus'}
                        emptyMessage="No approved practical facility is recorded for this campus."
                      />
                    </FormField>
                    <FormField
                      label="Practical Classroom Capacity"
                      htmlFor="tt-practical-capacity"
                      generated
                      hint="Derived from approved facility data."
                    >
                      <Input id="tt-practical-capacity" value={input.practicalClassroomCapacity || ''} readOnly />
                    </FormField>
                    <FormField label="Practical Trainer" htmlFor="tt-practical-trainer">
                      <DependentSelect
                        id="tt-practical-trainer"
                        value={input.practicalTrainerId}
                        onChange={(value) => update('practicalTrainerId', value)}
                        options={trainerOptions}
                        placeholder="Select approved trainer"
                        requires={input.qualificationCode ? undefined : 'a qualification'}
                      />
                    </FormField>
                  </FormGrid>
                  <FormField label="Practical Days and Times" htmlFor="tt-practical-slots">
                    <SlotEditor
                      id="tt-practical-slots"
                      label="practical"
                      slots={input.practicalDaysAndTimes}
                      onChange={(slots) => update('practicalDaysAndTimes', slots)}
                    />
                  </FormField>
                </FormSection>

                <FormSection
                  title="MSCRIS"
                  description="Additional classes, particularly additional classes arranged for specific topics. Delivered virtually and completed only when an additional class is required."
                >
                  <Alert variant="warning">
                    <AlertTriangle aria-hidden="true" />
                    <AlertDescription>
                      MSCRIS classes are excluded from trainer, student-group and facility clash checking, and the
                      MSCRIS Trainer is free text. Check the day, time and trainer manually before saving.
                    </AlertDescription>
                  </Alert>
                  <PendingRuleNotice
                    decisionId="OD-11"
                    message="MSCRIS is required only in certain cases, but the exact condition has not been supplied. TDMS treats the section as optional and never blocks a save because it is empty."
                  />
                  <FormGrid>
                    <FormField
                      label="MSCRIS Class Name"
                      htmlFor="tt-mscris-name"
                      generated
                      hint={`Fixed approved value. An MSCRIS class is always delivered virtually, so the name is always "${MSCRIS_CLASS_NAME}".`}
                    >
                      <Input id="tt-mscris-name" value={input.mscrisClassName} readOnly placeholder="Set automatically" />
                    </FormField>
                    <FormField
                      label="MSCRIS Trainer"
                      htmlFor="tt-mscris-trainer"
                      hint="Free text. Approved trainers are suggested, but any name may be entered."
                    >
                      <Input
                        id="tt-mscris-trainer"
                        list="tt-mscris-trainer-options"
                        value={input.mscrisTrainerId}
                        onChange={(event) => update('mscrisTrainerId', event.target.value)}
                        placeholder="Enter the trainer taking the additional class"
                      />
                    </FormField>
                  </FormGrid>
                  <datalist id="tt-mscris-trainer-options">
                    {trainerOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </datalist>
                  <FormField label="MSCRIS Days and Times" htmlFor="tt-mscris-slots">
                    <SlotEditor
                      id="tt-mscris-slots"
                      label="MSCRIS"
                      slots={input.mscrisDaysAndTimes}
                      onChange={(slots) => update('mscrisDaysAndTimes', slots)}
                    />
                  </FormField>
                </FormSection>

                <FormSection title="Other">
                  <FormField label="Remarks" htmlFor="tt-remarks">
                    <Textarea
                      id="tt-remarks"
                      value={input.remarks}
                      onChange={(event) => update('remarks', event.target.value)}
                      placeholder="Optional information needed to explain the timetable allocation."
                    />
                  </FormField>
                </FormSection>
              </>
            ) : (
              <div className="space-y-6">
                <Alert variant="info">
                  <Eye aria-hidden="true" />
                  <AlertDescription>
                    Preview does not save. Nothing is written to the database until you confirm.
                  </AlertDescription>
                </Alert>

                <PreviewPanel groups={previewGroups(input, data?.campuses, data?.colleges)} />

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
                <ArrowLeft aria-hidden="true" />
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
                {isEdit ? 'Update Timetable Record' : 'Save Timetable Record'}
              </Button>
            )}
          </SheetFooter>
        </SheetContent>
      </Sheet>

      {isEdit && editing ? (
        <ChangeSummaryDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Update Timetable Record?"
          description="Check the record and the fields that will change, then confirm the update."
          record={{
            primary: editing.recordNumber,
            secondary: `${editing.group} · ${editing.qualificationCode}`,
            lines: [`${editing.uocCode} — ${editing.uocTitle}`],
          }}
          changes={changes}
          busy={busy}
          onConfirm={save}
        />
      ) : (
        <ConfirmationDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Save Timetable Record?"
          description="Please confirm that you want to create this timetable record."
          confirmLabel="Confirm and Save"
          busy={busy}
          onConfirm={save}
          size="lg"
        >
          <PreviewPanel groups={previewGroups(input, data?.campuses, data?.colleges).slice(0, 2)} />
        </ConfirmationDialog>
      )}
    </>
  );
}

function previewGroups(
  input: TimetableInput,
  campuses: Array<{ id: string; campusName: string; campusLocation: string }> | undefined,
  colleges: Array<{ id: string; collegeFullName: string }> | undefined,
) {
  const campus = campuses?.find((entry) => entry.id === input.campusId);
  const college = colleges?.find((entry) => entry.id === input.collegeId);

  return [
    {
      title: 'Timetable basic details',
      items: [
        { label: 'College', value: college?.collegeFullName ?? '' },
        { label: 'Campus Location', value: campus ? `${campus.campusName} — ${campus.campusLocation}` : '' },
        { label: 'Qualification Code', value: input.qualificationCode },
        { label: 'Qualification Name', value: input.qualificationName, generated: true },
        { label: 'Duration in Weeks', value: input.durationInWeeks ? `${input.durationInWeeks} weeks` : '' },
        { label: 'Group', value: input.group },
        { label: 'Classroom Size', value: input.classroomSize || '' },
      ],
    },
    {
      title: 'Unit details',
      items: [
        { label: 'UoC Code', value: input.uocCode },
        { label: 'UoC Title', value: input.uocTitle, generated: true },
        { label: 'UoC Type', value: input.uocType, generated: true },
        { label: 'Mode of Delivery', value: input.modeOfDelivery },
        { label: 'UoC Start Date', value: formatDate(input.uocStartDate) },
        { label: 'UoC End Date', value: formatDate(input.uocEndDate) },
      ],
    },
    {
      title: 'Theory',
      items: [
        { label: 'Theory Days and Times', value: formatSlots(input.theoryDaysAndTimes) },
        { label: 'Theory Classroom Name', value: input.theoryClassroomName },
        { label: 'Theory Classroom Capacity', value: input.theoryClassroomCapacity || '', generated: true },
        { label: 'Theory Trainer', value: input.theoryTrainerId },
      ],
    },
    {
      title: 'Practical',
      items: [
        { label: 'Practical Classroom Name', value: input.practicalClassroomName },
        { label: 'Practical Classroom Capacity', value: input.practicalClassroomCapacity || '', generated: true },
        { label: 'Practical Days and Times', value: formatSlots(input.practicalDaysAndTimes) },
        { label: 'Practical Trainer', value: input.practicalTrainerId },
      ],
    },
    {
      title: 'MSCRIS and remarks',
      items: [
        { label: 'MSCRIS Class Name', value: input.mscrisClassName },
        { label: 'MSCRIS Days and Times', value: formatSlots(input.mscrisDaysAndTimes) },
        { label: 'MSCRIS Trainer', value: input.mscrisTrainerId },
        { label: 'Remarks', value: input.remarks },
      ],
    },
  ];
}
