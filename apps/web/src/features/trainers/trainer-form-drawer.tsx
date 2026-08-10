'use client';

import * as React from 'react';
import { Eye, Loader2, Save } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
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
import { useReferenceData } from '@/features/shared/reference-data-context';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient } from '@/services';
import { nowIso } from '@/lib/format';
import { QUALIFICATION_CATALOGUE, qualificationByCode } from '@/mock-data';
import {
  LOCATION_TYPE_OPTIONS,
  TRAINER_DELIVERY_TYPE_OPTIONS,
  WEEKDAY_AVAILABILITY_OPTIONS,
  WORKING_TIME_OPTIONS,
} from '@/mock-data';
import type { ValidationIssue, ValidationResult } from '@/types/common';
import type { TrainerInput, TrainerRecord, WeekdayAvailability } from '@/types/trainer';

const EMPTY: TrainerInput = {
  trainerId: '',
  trainerName: '',
  trainerCampus: '',
  campusId: '',
  location: '',
  locationType: 'Campus',
  workingTime: '09:00 - 17:00',
  deliveryType: 'Theory',
  monday: 'Not Available',
  tuesday: 'Not Available',
  wednesday: 'Not Available',
  thursday: 'Not Available',
  friday: 'Not Available',
  qualificationsCanTeach: [],
  unitsCanTeach: [],
  isActive: true,
};

const WEEKDAYS = [
  { key: 'monday', label: 'Monday' },
  { key: 'tuesday', label: 'Tuesday' },
  { key: 'wednesday', label: 'Wednesday' },
  { key: 'thursday', label: 'Thursday' },
  { key: 'friday', label: 'Friday' },
] as const;

interface TrainerFormDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: TrainerRecord | null;
  onSaved: () => void;
}

/** Create and edit for trainer reference data (TRN-06). */
export function TrainerFormDrawer({ open, onOpenChange, editing, onSaved }: TrainerFormDrawerProps) {
  const { data, campusById } = useReferenceData();
  const { user } = useAuth();

  const [input, setInput] = React.useState<TrainerInput>(EMPTY);
  const [step, setStep] = React.useState<'form' | 'preview'>('form');
  const [validation, setValidation] = React.useState<ValidationResult | null>(null);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setStep('form');
    setValidation(null);
    if (editing) {
      const { id: _id, serialNumber: _s, isDeleted: _d, deletion: _del, ...rest } = editing;
      setInput(rest);
    } else {
      setInput(EMPTY);
    }
  }, [open, editing]);

  function update<K extends keyof TrainerInput>(key: K, value: TrainerInput[K]) {
    setInput((current) => ({ ...current, [key]: value }));
    setValidation(null);
    setStep('form');
  }

  function toggleQualification(code: string, checked: boolean) {
    const qualifications = checked
      ? [...input.qualificationsCanTeach, code]
      : input.qualificationsCanTeach.filter((entry) => entry !== code);

    // Units follow the approved qualification-unit sequence, so they are
    // derived rather than typed.
    const units = Array.from(
      new Set(qualifications.flatMap((entry) => qualificationByCode(entry)?.units.map((unit) => unit.unitCode) ?? [])),
    );

    setInput((current) => ({ ...current, qualificationsCanTeach: qualifications, unitsCanTeach: units }));
    setValidation(null);
    setStep('form');
  }

  function selectCampus(campusId: string) {
    const campus = campusById(campusId);
    const college = data?.colleges.find((entry) => entry.id === campus?.collegeId);
    setInput((current) => ({
      ...current,
      campusId,
      trainerCampus: campus && college ? `${college.collegeFullName} - ${campus.campusName}` : '',
      location: campus?.campusName ?? '',
    }));
    setValidation(null);
    setStep('form');
  }

  function runPreview() {
    const issues: ValidationIssue[] = [];
    if (!input.trainerId.trim()) {
      issues.push({
        id: 'trainer-id',
        severity: 'blocking',
        title: 'Trainer ID is required',
        message: 'Enter the reference that distinguishes this trainer from every other trainer.',
        reference: 'Trainer ID',
      });
    }
    if (!input.trainerName.trim()) {
      issues.push({
        id: 'trainer-name',
        severity: 'blocking',
        title: 'Trainer Name is required',
        message: 'Enter the approved trainer name displayed in TDMS.',
        reference: 'Trainer Name',
      });
    }
    if (!input.campusId) {
      issues.push({
        id: 'trainer-campus',
        severity: 'blocking',
        title: 'Trainer Campus is required',
        message: 'Select the approved college and campus relationship for the trainer.',
        reference: 'Trainer Campus',
      });
    }
    if (input.qualificationsCanTeach.length === 0) {
      issues.push({
        id: 'trainer-qualifications',
        severity: 'blocking',
        title: 'No qualification is selected',
        message: 'Select at least one qualification the trainer is approved to teach.',
        reference: 'Qualifications They Can Teach',
      });
    }
    if (WEEKDAYS.every((day) => input[day.key] === 'Not Available')) {
      issues.push({
        id: 'trainer-availability',
        severity: 'advisory',
        title: 'No weekday availability recorded',
        message: 'The trainer is Not Available on every weekday and will not appear as available for scheduling.',
        reference: 'Monday to Friday',
      });
    }

    issues.push({
      id: 'delivery-rule',
      severity: 'pending-approval',
      title: 'Physical and virtual delivery rule',
      message:
        'TRN-07 requires the physical-to-virtual availability rule to be approved before it is applied. The recorded values are stored, but TDMS does not derive virtual availability from physical availability yet.',
      openDecisionId: 'OD-10',
    });

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
        await client.updateTrainer(editing.id, input, { actor: user });
        toast.success('Trainer updated', {
          description: `${input.trainerName} was updated and a user activity record was created.`,
        });
      } else {
        await client.createTrainer(input, { actor: user });
        toast.success('Trainer added', {
          description: `${input.trainerName} was added to trainer reference data.`,
        });
      }
      setConfirmOpen(false);
      onOpenChange(false);
      onSaved();
    } catch (error) {
      toast.error('The trainer record could not be saved', {
        description: error instanceof Error ? error.message : 'Try again, or contact the TDMS administrator.',
      });
    } finally {
      setBusy(false);
    }
  }

  const changes = editing
    ? buildChanges(editing as unknown as Record<string, unknown>, input as unknown as Record<string, unknown>, [
        { key: 'trainerId', label: 'Trainer ID' },
        { key: 'trainerName', label: 'Trainer Name' },
        { key: 'trainerCampus', label: 'Trainer Campus' },
        { key: 'location', label: 'Location' },
        { key: 'locationType', label: 'Location Type' },
        { key: 'workingTime', label: 'Working Time' },
        { key: 'deliveryType', label: 'Delivery Type' },
        { key: 'monday', label: 'Monday' },
        { key: 'tuesday', label: 'Tuesday' },
        { key: 'wednesday', label: 'Wednesday' },
        { key: 'thursday', label: 'Thursday' },
        { key: 'friday', label: 'Friday' },
        {
          key: 'qualificationsCanTeach',
          label: 'Qualifications They Can Teach',
          format: (value) => (value as string[]).join(', '),
        },
        { key: 'unitsCanTeach', label: 'Units They Can Teach', format: (value) => (value as string[]).join(', ') },
        { key: 'isActive', label: 'Status', format: (value) => (value ? 'Active' : 'Inactive') },
      ])
    : [];

  return (
    <>
      <Sheet open={open} onOpenChange={busy ? undefined : onOpenChange}>
        <SheetContent width="lg">
          <SheetHeader>
            <SheetTitle>{editing ? 'Edit Trainer' : 'Create Trainer'}</SheetTitle>
            <SheetDescription>
              {step === 'form'
                ? 'Complete the trainer reference data, then preview before confirming.'
                : 'This is the proposed trainer record. It has not been saved.'}
            </SheetDescription>
          </SheetHeader>

          <SheetBody className="space-y-7">
            {step === 'form' ? (
              <>
                <FormSection title="Identity and location">
                  <FormGrid>
                    <FormField label="Trainer ID" htmlFor="trainer-id" required>
                      <Input
                        id="trainer-id"
                        value={input.trainerId}
                        onChange={(event) => update('trainerId', event.target.value)}
                        placeholder="e.g. TRN-0013"
                      />
                    </FormField>
                    <FormField label="Trainer Name" htmlFor="trainer-name" required>
                      <Input
                        id="trainer-name"
                        value={input.trainerName}
                        onChange={(event) => update('trainerName', event.target.value)}
                      />
                    </FormField>
                    <FormField label="Trainer Campus" htmlFor="trainer-campus" required>
                      <DependentSelect
                        id="trainer-campus"
                        value={input.campusId}
                        onChange={selectCampus}
                        options={(data?.campuses ?? []).map((campus) => ({
                          value: campus.id,
                          label: `${campus.campusName} — ${campus.campusLocation}`,
                        }))}
                        placeholder="Select approved campus"
                      />
                    </FormField>
                    <FormField label="Location" htmlFor="trainer-location">
                      <Input
                        id="trainer-location"
                        value={input.location}
                        onChange={(event) => update('location', event.target.value)}
                      />
                    </FormField>
                    <FormField label="Location Type" htmlFor="trainer-location-type">
                      <SimpleSelect
                        id="trainer-location-type"
                        value={input.locationType}
                        onChange={(value) => update('locationType', value as TrainerInput['locationType'])}
                        options={LOCATION_TYPE_OPTIONS.map((option) => ({ value: option, label: option }))}
                        placeholder="Select location type"
                      />
                    </FormField>
                    <FormField label="Working Time" htmlFor="trainer-working-time">
                      <SimpleSelect
                        id="trainer-working-time"
                        value={input.workingTime}
                        onChange={(value) => update('workingTime', value)}
                        options={WORKING_TIME_OPTIONS.map((option) => ({ value: option, label: option }))}
                        placeholder="Select working time"
                      />
                    </FormField>
                    <FormField label="Delivery Type" htmlFor="trainer-delivery-type">
                      <SimpleSelect
                        id="trainer-delivery-type"
                        value={input.deliveryType}
                        onChange={(value) => update('deliveryType', value as TrainerInput['deliveryType'])}
                        options={TRAINER_DELIVERY_TYPE_OPTIONS.map((option) => ({ value: option, label: option }))}
                        placeholder="Select delivery type"
                      />
                    </FormField>
                  </FormGrid>

                  <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/40 px-4 py-3">
                    <Switch
                      id="trainer-active"
                      checked={input.isActive}
                      onCheckedChange={(checked) => update('isActive', checked)}
                    />
                    <div>
                      <Label htmlFor="trainer-active">Active trainer</Label>
                      <p className="text-[12px] text-muted-foreground">
                        An inactive trainer stays visible for historical records but cannot be selected for a new
                        timetable assignment (TRN-04).
                      </p>
                    </div>
                  </div>
                </FormSection>

                <FormSection title="Weekday availability">
                  <PendingRuleNotice
                    decisionId="OD-10"
                    message="The rule allowing a physically-available trainer to deliver virtually is not approved yet, so each weekday value is recorded exactly as entered."
                  />
                  <FormGrid columns={3}>
                    {WEEKDAYS.map((day) => (
                      <FormField key={day.key} label={day.label} htmlFor={`trainer-${day.key}`}>
                        <SimpleSelect
                          id={`trainer-${day.key}`}
                          value={input[day.key]}
                          onChange={(value) => update(day.key, value as WeekdayAvailability)}
                          options={WEEKDAY_AVAILABILITY_OPTIONS.map((option) => ({ value: option, label: option }))}
                          placeholder="Select availability"
                        />
                      </FormField>
                    ))}
                  </FormGrid>
                </FormSection>

                <FormSection
                  title="Qualifications They Can Teach"
                  description="Units They Can Teach follow the approved qualification and unit sequence for each selected qualification."
                >
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {QUALIFICATION_CATALOGUE.map((qualification) => {
                      const checked = input.qualificationsCanTeach.includes(qualification.qualificationCode);
                      return (
                        <label
                          key={qualification.qualificationCode}
                          className="flex items-start gap-2.5 rounded-lg border border-border px-3 py-2.5 hover:bg-muted/50"
                        >
                          <Checkbox
                            checked={checked}
                            onCheckedChange={(value) =>
                              toggleQualification(qualification.qualificationCode, value === true)
                            }
                            aria-label={qualification.qualificationTitle}
                          />
                          <span className="min-w-0">
                            <span className="block text-[13px] font-medium text-foreground">
                              {qualification.qualificationCode}
                            </span>
                            <span className="block truncate text-[12px] text-muted-foreground">
                              {qualification.qualificationTitle}
                            </span>
                          </span>
                        </label>
                      );
                    })}
                  </div>

                  {input.unitsCanTeach.length > 0 && (
                    <Alert>
                      <AlertDescription>
                        <span className="font-medium">Units They Can Teach ({input.unitsCanTeach.length}):</span>{' '}
                        {input.unitsCanTeach.join(', ')}
                      </AlertDescription>
                    </Alert>
                  )}
                </FormSection>
              </>
            ) : (
              <div className="space-y-6">
                <PreviewPanel groups={previewGroups(input)} />
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
          title="Update Trainer?"
          description="Check the record and the fields that will change, then confirm the update."
          record={{ primary: editing.trainerId, secondary: editing.trainerName, lines: [editing.trainerCampus] }}
          changes={changes}
          busy={busy}
          onConfirm={save}
        />
      ) : (
        <ConfirmationDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Add Trainer?"
          description="Please confirm that you want to add this trainer to the approved reference data."
          confirmLabel="Confirm Add"
          busy={busy}
          onConfirm={save}
          size="lg"
        >
          <PreviewPanel groups={previewGroups(input)} />
        </ConfirmationDialog>
      )}
    </>
  );
}

function previewGroups(input: TrainerInput) {
  return [
    {
      title: 'Trainer location data',
      items: [
        { label: 'Trainer ID', value: input.trainerId },
        { label: 'Trainer Name', value: input.trainerName },
        { label: 'Trainer Campus', value: input.trainerCampus },
        { label: 'Location', value: input.location },
        { label: 'Location Type', value: input.locationType },
        { label: 'Working Time', value: input.workingTime },
        { label: 'Delivery Type', value: input.deliveryType },
        { label: 'Status', value: input.isActive ? 'Active' : 'Inactive' },
      ],
    },
    {
      title: 'Weekday availability',
      items: [
        { label: 'Monday', value: input.monday },
        { label: 'Tuesday', value: input.tuesday },
        { label: 'Wednesday', value: input.wednesday },
        { label: 'Thursday', value: input.thursday },
        { label: 'Friday', value: input.friday },
      ],
    },
    {
      title: 'Trainer qualification and unit data',
      items: [
        { label: 'Qualifications They Can Teach', value: input.qualificationsCanTeach.join(', ') },
        { label: 'Units They Can Teach', value: input.unitsCanTeach.join(', ') },
      ],
    },
  ];
}
