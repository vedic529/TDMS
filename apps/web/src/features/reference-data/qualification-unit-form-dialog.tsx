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
import {
  referenceApi,
  type ApiQualification,
  type ApiUnit,
} from '@/services/reference-api';
import { fromUocType, qualificationCodeLabel } from './reference-adapters';
import { useAuth } from '@/features/auth/auth-context';
import { nowIso } from '@/lib/format';
import type { ValidationIssue, ValidationResult } from '@/types/common';
import type { QualificationUnitSequence, UocType } from '@/types/reference';
import type { QualificationUnitInput } from '@/services/tdms-client';

const EMPTY: QualificationUnitInput = {
  qualificationCode: '',
  qualificationTitle: '',
  unitCode: '',
  unitTitle: '',
  uocType: 'Theory',
};

interface QualificationUnitFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: QualificationUnitSequence | null;
  existingRecords: QualificationUnitSequence[];
  onSaved: () => void;
  /** From a suggestion: the unit code seen, and the qualification it was under. */
  prefill?: {
    unitCode?: string;
    qualificationCode?: string;
    /** The title an allocation file gave the unit, used when TDMS has none. */
    unitTitle?: string;
    uocType?: UocType;
  } | null;
  /** The unit, so a suggestion can be resolved onto it. */
  onCreated?: (unitId: number) => void;
}

/** Create and edit for College Qualifications, the tab formerly called
 *  Qualification and Unit Sequence Data (COL-07). */
export function QualificationUnitFormDialog({
  open,
  onOpenChange,
  editing,
  existingRecords,
  onSaved,
  prefill,
  onCreated,
}: QualificationUnitFormDialogProps) {
  const [qualifications, setQualifications] = React.useState<ApiQualification[]>([]);
  const [units, setUnits] = React.useState<ApiUnit[]>([]);

  // Real qualifications and units for the dependent dropdowns.
  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [q, u] = await Promise.all([
          referenceApi.listQualifications({ activeOnly: true }),
          referenceApi.listUnits({ activeOnly: true }),
        ]);
        if (!cancelled) {
          setQualifications(q);
          setUnits(u);
        }
      } catch {
        if (!cancelled) {
          setQualifications([]);
          setUnits([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const { user } = useAuth();

  const [input, setInput] = React.useState<QualificationUnitInput>(EMPTY);

  /**
   * The chosen qualification's database id, held beside the display input.
   *
   * The form shows a Qualification Code, but that is not an identity any more:
   * every code-less ELICOS qualification displays as NA. The id is what the
   * selection and the save actually resolve against.
   */
  const [qualificationId, setQualificationId] = React.useState('');

  /** The register entry for the typed code, when there is one. */
  const knownUnit = React.useMemo(
    () =>
      units.find(
        (row) => row.unit_code.trim().toUpperCase() === input.unitCode.trim().toUpperCase(),
      ) ?? null,
    [units, input.unitCode],
  );

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
      // Recover the id from the row being edited, matching on the same label
      // the list renders.
      setQualificationId(
        String(
          qualifications.find(
            (row) => qualificationCodeLabel(row.qualification_code) === editing.qualificationCode,
          )?.id ?? '',
        ),
      );
    } else {
      // From a suggestion the unit code and its qualification come with the
      // entry. A code that already exists brings its title too.
      const code = prefill?.unitCode?.trim() ?? '';
      const known = code
        ? units.find((row) => row.unit_code.trim().toUpperCase() === code.toUpperCase())
        : undefined;
      const presetCode = prefill?.qualificationCode?.trim().toUpperCase();
      const preset = presetCode
        ? qualifications.find((row) => (row.qualification_code ?? '').toUpperCase() === presetCode)
        : undefined;
      setInput({
        ...EMPTY,
        unitCode: code,
        unitTitle: known?.unit_title ?? prefill?.unitTitle ?? '',
        uocType: prefill?.uocType ?? EMPTY.uocType,
        qualificationCode: preset ? qualificationCodeLabel(preset.qualification_code) : '',
        qualificationTitle: preset?.qualification_title ?? '',
      });
      setQualificationId(preset ? String(preset.id) : '');
    }
  }, [open, editing, qualifications, units, prefill]);

  function update<K extends keyof QualificationUnitInput>(key: K, value: QualificationUnitInput[K]) {
    setInput((current) => ({ ...current, [key]: value }));
    setValidation(null);
    setStep('form');
  }

  // Real qualifications. A qualification's unit sequence is a property of the
  // qualification itself, so the list is not narrowed by college or campus.
  //
  // Keyed on the id, not the code: ELICOS qualifications have no VET Code and
  // all display as NA, so a code-keyed option list would make two different
  // qualifications indistinguishable — and silently select the wrong one.
  const qualificationOptions = qualifications.map((row) => ({
    value: String(row.id),
    label: `${qualificationCodeLabel(row.qualification_code)} — ${row.qualification_title}`,
  }));


  function runPreview() {
    const issues: ValidationIssue[] = [];
    // A complete `qualification_units` row is the qualification and the unit.
    // Nothing else is asked for, because nothing else is part of the record.
    const required: Array<[string, unknown, string]> = [
      ['Qualification', qualificationId, 'Select the qualification this unit belongs to.'],
      ['Unit Code', input.unitCode, 'Enter the unit of competency code.'],
      ['Unit Title', input.unitTitle, 'A unit needs a title.'],
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

    // Per qualification, matching `uq_qualification_units_qualification_id_unit_id`.
    // Campus is not part of it: a unit belongs to the qualification everywhere it
    // is offered.
    const duplicateUnit = existingRecords.find(
      (record) =>
        record.id !== editing?.id &&
        record.qualificationCode === input.qualificationCode &&
        record.unitCode.trim().toUpperCase() === input.unitCode.trim().toUpperCase(),
    );
    if (duplicateUnit) {
      issues.push({
        id: 'qus-duplicate-unit',
        severity: 'blocking',
        title: 'Unit already exists for this qualification',
        message: `${duplicateUnit.unitCode} is already a unit of ${duplicateUnit.qualificationCode}.`,
        reference: 'Unit Code',
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
      const qualification = qualifications.find((row) => String(row.id) === qualificationId);
      const unit = knownUnit;

      if (editing) {
        await referenceApi.updateQualificationUnit(Number(editing.id), {
          unit_id: unit?.id,
          // Omitted rather than sent as null: a membership may legitimately
          // have no approved sequence, and the update contract treats an
          // absent value as "leave it alone".
          // The teaching order is never typed in. It comes from an approved
          // rolling timetable, and once groups arrive each group runs its own
          // cycle of the same units - so a single number entered by hand could
          // only ever be right for one of them.
          delivery_order: undefined,
        });
        toast.success('Record updated', { description: `${input.unitCode} was updated.` });
      } else {
        if (!qualification) throw new Error('Select an approved qualification.');

        // A unit TDMS does not have is created, not refused. Refusing was the
        // whole problem: adding a unit means adding one that is not there, and
        // the form used to insist it already existed.
        //
        // An existing code is reused. `units.unit_code` is globally unique, so
        // a second row is impossible anyway, and a unit that belongs to another
        // qualification is the ordinary case for this form - it needs the
        // membership, not another unit.
        const unitId =
          unit?.id ??
          (
            await referenceApi.createUnit({
              unit_code: input.unitCode.trim(),
              unit_title: input.unitTitle.trim(),
              uoc_type: fromUocType(input.uocType),
            })
          ).id;

        // No position is sent. Membership is what this form decides; the
        // teaching order arrives from an approved rolling timetable.
        await referenceApi.createQualificationUnit({
          qualification_id: qualification.id,
          unit_id: unitId,
        });
        onCreated?.(unitId);
        toast.success(unit ? 'Unit added to the qualification' : 'Unit created and added', {
          description: unit
            ? `${input.unitCode} already existed and is now a unit of ${input.qualificationCode}.`
            : `${input.unitCode} was created and added to ${input.qualificationCode}.`,
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
        { key: 'qualificationCode', label: 'Qualification Code' },
        { key: 'qualificationTitle', label: 'Qualification Title' },
        { key: 'unitCode', label: 'Unit Code' },
        { key: 'unitTitle', label: 'Unit Title' },
        { key: 'uocType', label: 'UoC Type' },
      ])
    : [];

  const groups = [
    {
      title: 'Qualification and unit sequence',
      items: [
        { label: 'Qualification Code', value: input.qualificationCode },
        { label: 'Qualification Title', value: input.qualificationTitle },
        { label: 'Unit Code', value: input.unitCode },
        { label: 'Unit Title', value: input.unitTitle },
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
              {editing ? 'Edit College Qualification Record' : 'Create College Qualification Record'}
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
                  {/* Two fields, because a `qualification_units` record is two
                      columns. College and campus are not asked for: unit
                      membership belongs to the qualification, so a unit added
                      here applies everywhere that qualification is offered.
                      Record ID is not asked for either - there is no such
                      column, and the list renders it from the row's own key. */}
                  <FormField label="Qualification" htmlFor="qus-qualification" required>
                    <DependentSelect
                      id="qus-qualification"
                      value={qualificationId}
                      onChange={(value) => {
                        const chosen = qualifications.find((row) => String(row.id) === value);
                        setQualificationId(value);
                        setInput((current) => ({
                          ...current,
                          qualificationCode: qualificationCodeLabel(chosen?.qualification_code),
                          qualificationTitle: chosen?.qualification_title ?? '',
                        }));
                        setValidation(null);
                        setStep('form');
                      }}
                      options={qualificationOptions}
                      placeholder="Select qualification"
                    />
                  </FormField>
                  <FormField
                    label="Qualification Title"
                    htmlFor="qus-qualification-title"
                    generated
                    hint="Comes with the qualification."
                  >
                    <Input id="qus-qualification-title" value={input.qualificationTitle} readOnly />
                  </FormField>
                  {/* Typed, not chosen.
                      Adding a unit means adding one TDMS does not have, so a
                      dropdown of every existing unit answered the wrong
                      question - and with 675 of them, listing units from
                      unrelated qualifications, it was unusable besides.

                      A code that already exists is reused, never duplicated:
                      `units.unit_code` is globally unique, and a unit belonging
                      to another qualification is exactly the case where this
                      form links rather than creates. The title fills itself in
                      then, so the person typing does not have to know which
                      case they are in. */}
                  <FormField label="Unit Code" htmlFor="qus-unit-code" required>
                    <Input
                      id="qus-unit-code"
                      value={input.unitCode}
                      onChange={(event) => {
                        const code = event.target.value;
                        const known = units.find(
                          (row) => row.unit_code.trim().toUpperCase() === code.trim().toUpperCase(),
                        );
                        setInput((current) => ({
                          ...current,
                          unitCode: code,
                          // Only overwrite the title from the register, never a
                          // title the person is part-way through typing.
                          unitTitle: known ? known.unit_title : current.unitTitle,
                          uocType: (known?.uoc_type as UocType) ?? current.uocType,
                        }));
                        setValidation(null);
                        setStep('form');
                      }}
                      placeholder="e.g. BSBOPS501"
                    />
                  </FormField>
                  <FormField
                    label="Unit Title"
                    htmlFor="qus-unit-title"
                    required
                    hint={
                      knownUnit
                        ? 'This unit already exists. It will be added to the qualification, not created again.'
                        : 'A new unit. Enter its title.'
                    }
                  >
                    <Input
                      id="qus-unit-title"
                      value={input.unitTitle}
                      onChange={(event) => update('unitTitle', event.target.value)}
                      readOnly={Boolean(knownUnit)}
                      placeholder="e.g. Manage business resources"
                    />
                  </FormField>
                  <FormField label="UoC Type" htmlFor="qus-uoc-type">
                    <SimpleSelect
                      id="qus-uoc-type"
                      value={input.uocType}
                      onChange={(value) => update('uocType', value as UocType)}
                      options={[
                        { value: 'Theory', label: 'Theory' },
                        { value: 'Practical', label: 'Practical' },
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
          title="Update College Qualification Record?"
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
          title="Add College Qualification Record?"
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
