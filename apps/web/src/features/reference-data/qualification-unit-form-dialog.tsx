'use client';

import * as React from 'react';
import { Eye, Loader2, Save } from 'lucide-react';
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
import { PreviewPanel } from '@/components/common/preview-panel';
import { ValidationPanel } from '@/components/common/validation-panel';
import { ConfirmationDialog } from '@/components/common/confirmation-dialog';
import { ChangeSummaryDialog, buildChanges } from '@/components/common/change-summary-dialog';
import { useReferenceData } from '@/features/shared/reference-data-context';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient } from '@/services';
import { nowIso } from '@/lib/format';
import type { ValidationIssue, ValidationResult } from '@/types/common';
import type { QualificationUnitSequence, UocType } from '@/types/reference';
import type { QualificationUnitInput } from '@/services/tdms-client';

const EMPTY: QualificationUnitInput = {
  recordId: '',
  qualificationCode: '',
  qualificationTitle: '',
  unitCode: '',
  unitTitle: '',
  sequenceId: 1,
  collegeId: '',
  campusId: '',
  uocType: 'Theory',
};

interface QualificationUnitFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: QualificationUnitSequence | null;
  existingRecords: QualificationUnitSequence[];
  onSaved: () => void;
}

/** Create and edit for Qualification and Unit Sequence Data (COL-07). */
export function QualificationUnitFormDialog({
  open,
  onOpenChange,
  editing,
  existingRecords,
  onSaved,
}: QualificationUnitFormDialogProps) {
  const { data, campusesForCollege, offeringsFor } = useReferenceData();
  const { user } = useAuth();

  const [input, setInput] = React.useState<QualificationUnitInput>(EMPTY);
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

  function update<K extends keyof QualificationUnitInput>(key: K, value: QualificationUnitInput[K]) {
    setInput((current) => ({ ...current, [key]: value }));
    setValidation(null);
    setStep('form');
  }

  const offerings = offeringsFor(input.collegeId, input.campusId);

  function runPreview() {
    const issues: ValidationIssue[] = [];
    const required: Array<[string, unknown, string]> = [
      ['College', input.collegeId, 'Select the college that offers the qualification.'],
      ['Campus', input.campusId, 'Select an approved campus for the selected college.'],
      ['Qualification Code', input.qualificationCode, 'Select the approved qualification.'],
      ['Unit Code', input.unitCode, 'Enter the approved Unit of Competency code.'],
      ['Unit Title', input.unitTitle, 'Enter the approved Unit of Competency title.'],
      ['Record ID', input.recordId, 'Enter the system or source reference for this relationship.'],
    ];
    for (const [label, value, message] of required) {
      if (!value) {
        issues.push({
          id: `qus-${label}`,
          severity: 'blocking',
          title: `${label} is required`,
          message,
          reference: label,
        });
      }
    }

    if (!input.sequenceId || input.sequenceId < 1) {
      issues.push({
        id: 'qus-sequence',
        severity: 'blocking',
        title: 'Sequence ID must be 1 or higher',
        message: 'Enter the approved teaching-order number used when a timetable is generated or checked.',
        reference: 'Sequence ID',
      });
    }

    const duplicateUnit = existingRecords.find(
      (record) =>
        record.id !== editing?.id &&
        record.campusId === input.campusId &&
        record.qualificationCode === input.qualificationCode &&
        record.unitCode.trim().toUpperCase() === input.unitCode.trim().toUpperCase(),
    );
    if (duplicateUnit) {
      issues.push({
        id: 'qus-duplicate-unit',
        severity: 'blocking',
        title: 'Unit already exists for this qualification',
        message: `${duplicateUnit.unitCode} is already recorded for ${duplicateUnit.qualificationCode} at this campus (${duplicateUnit.recordId}).`,
        reference: 'Unit Code',
      });
    }

    const duplicateSequence = existingRecords.find(
      (record) =>
        record.id !== editing?.id &&
        record.campusId === input.campusId &&
        record.qualificationCode === input.qualificationCode &&
        record.sequenceId === input.sequenceId,
    );
    if (duplicateSequence) {
      issues.push({
        id: 'qus-duplicate-sequence',
        severity: 'advisory',
        title: 'Sequence ID is already used',
        message: `Sequence ${input.sequenceId} is already used by ${duplicateSequence.unitCode}. Confirm this is intended before saving.`,
        reference: 'Sequence ID',
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
        await client.updateQualificationUnit(editing.id, input, { actor: user });
        toast.success('Record updated', { description: `${input.recordId} was updated.` });
      } else {
        await client.createQualificationUnit(input, { actor: user });
        toast.success('Record added', {
          description: `${input.unitCode} was added to ${input.qualificationCode} at sequence ${input.sequenceId}.`,
        });
      }
      setConfirmOpen(false);
      onOpenChange(false);
      onSaved();
    } catch (error) {
      toast.error('The record could not be saved', {
        description: error instanceof Error ? error.message : 'Try again, or contact the TDMS administrator.',
      });
    } finally {
      setBusy(false);
    }
  }

  const changes = editing
    ? buildChanges(editing as unknown as Record<string, unknown>, input as unknown as Record<string, unknown>, [
        { key: 'recordId', label: 'Record ID' },
        { key: 'qualificationCode', label: 'Qualification Code' },
        { key: 'qualificationTitle', label: 'Qualification Title' },
        { key: 'unitCode', label: 'Unit Code' },
        { key: 'unitTitle', label: 'Unit Title' },
        { key: 'sequenceId', label: 'Sequence ID' },
        { key: 'uocType', label: 'UoC Type' },
      ])
    : [];

  const groups = [
    {
      title: 'Qualification and unit sequence',
      items: [
        { label: 'Record ID', value: input.recordId },
        { label: 'Qualification Code', value: input.qualificationCode },
        { label: 'Qualification Title', value: input.qualificationTitle },
        { label: 'Unit Code', value: input.unitCode },
        { label: 'Unit Title', value: input.unitTitle },
        { label: 'Sequence ID', value: input.sequenceId },
        { label: 'UoC Type', value: input.uocType },
      ],
    },
  ];

  return (
    <>
      <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>
              {editing ? 'Edit Qualification and Unit Sequence Record' : 'Create Qualification and Unit Sequence Record'}
            </DialogTitle>
            <DialogDescription>
              {step === 'form'
                ? 'Complete the record, then preview before confirming. Nothing is saved until you confirm.'
                : 'This is the proposed record. It has not been saved.'}
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-5">
            {step === 'form' ? (
              <>
                <FormGrid>
                  <FormField label="College" htmlFor="qus-college" required>
                    <DependentSelect
                      id="qus-college"
                      value={input.collegeId}
                      onChange={(value) => {
                        setInput((current) => ({ ...current, collegeId: value, campusId: '', qualificationCode: '' }));
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
                  <FormField label="Campus" htmlFor="qus-campus" required>
                    <DependentSelect
                      id="qus-campus"
                      value={input.campusId}
                      onChange={(value) => {
                        setInput((current) => ({ ...current, campusId: value, qualificationCode: '' }));
                        setValidation(null);
                        setStep('form');
                      }}
                      options={campusesForCollege(input.collegeId).map((campus) => ({
                        value: campus.id,
                        label: campus.campusName,
                      }))}
                      placeholder="Select campus"
                      requires={input.collegeId ? undefined : 'a college'}
                    />
                  </FormField>
                  <FormField label="Qualification Code" htmlFor="qus-qualification" required>
                    <DependentSelect
                      id="qus-qualification"
                      value={input.qualificationCode}
                      onChange={(value) => {
                        const offering = offerings.find((entry) => entry.qualificationCode === value);
                        setInput((current) => ({
                          ...current,
                          qualificationCode: value,
                          qualificationTitle: offering?.qualificationTitle ?? '',
                        }));
                        setValidation(null);
                        setStep('form');
                      }}
                      options={Array.from(
                        new Map(
                          offerings.map((entry) => [
                            entry.qualificationCode,
                            {
                              value: entry.qualificationCode,
                              label: `${entry.qualificationCode} — ${entry.qualificationTitle}`,
                            },
                          ]),
                        ).values(),
                      )}
                      placeholder="Select qualification"
                      requires={input.campusId ? undefined : 'a campus'}
                    />
                  </FormField>
                  <FormField
                    label="Qualification Title"
                    htmlFor="qus-qualification-title"
                    generated
                    hint="Derived from the selected qualification."
                  >
                    <Input id="qus-qualification-title" value={input.qualificationTitle} readOnly />
                  </FormField>
                  <FormField label="Record ID" htmlFor="qus-record-id" required>
                    <Input
                      id="qus-record-id"
                      value={input.recordId}
                      onChange={(event) => update('recordId', event.target.value)}
                      placeholder="e.g. QUS-BSB50420-09"
                    />
                  </FormField>
                  <FormField label="Sequence ID" htmlFor="qus-sequence" required>
                    <Input
                      id="qus-sequence"
                      type="number"
                      min={1}
                      value={input.sequenceId || ''}
                      onChange={(event) => update('sequenceId', Number(event.target.value))}
                    />
                  </FormField>
                  <FormField label="Unit Code" htmlFor="qus-unit-code" required>
                    <Input
                      id="qus-unit-code"
                      value={input.unitCode}
                      onChange={(event) => update('unitCode', event.target.value)}
                    />
                  </FormField>
                  <FormField label="Unit Title" htmlFor="qus-unit-title" required>
                    <Input
                      id="qus-unit-title"
                      value={input.unitTitle}
                      onChange={(event) => update('unitTitle', event.target.value)}
                    />
                  </FormField>
                  <FormField label="UoC Type" htmlFor="qus-uoc-type">
                    <SimpleSelect
                      id="qus-uoc-type"
                      value={input.uocType}
                      onChange={(value) => update('uocType', value as UocType)}
                      options={[
                        { value: 'Theory', label: 'Theory' },
                        { value: 'Theory and Practical', label: 'Theory and Practical' },
                      ]}
                      placeholder="Select unit type"
                    />
                  </FormField>
                </FormGrid>
              </>
            ) : (
              <div className="space-y-5">
                <PreviewPanel groups={groups} />
                <div>
                  <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
                    Validation results
                  </h3>
                  <ValidationPanel result={validation} />
                </div>
              </div>
            )}
          </DialogBody>

          <DialogFooter>
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
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {editing ? (
        <ChangeSummaryDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Update Qualification and Unit Sequence Record?"
          description="Check the record and the fields that will change, then confirm the update."
          record={{
            primary: editing.recordId,
            secondary: `${editing.qualificationCode} · ${editing.unitCode}`,
            lines: [editing.unitTitle],
          }}
          changes={changes}
          busy={busy}
          onConfirm={save}
        />
      ) : (
        <ConfirmationDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Add Qualification and Unit Sequence Record?"
          description="Please confirm that you want to add this record to the approved reference data."
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
