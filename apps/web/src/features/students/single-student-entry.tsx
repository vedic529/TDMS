'use client';

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { AlertCircle, CheckCircle2, Eye, FilePlus2, Loader2, Save, Search, Trash2, UserRoundSearch } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Alert, AlertDescription } from '@/components/ui/alert';
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
import { DeleteConfirmationDialog } from '@/components/common/delete-confirmation-dialog';
import { EmptyState, PendingRuleNotice, ReadOnlyNotice } from '@/components/common/states';
import { useReferenceData } from '@/features/shared/reference-data-context';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient } from '@/services';
import { INTERFACE_NAMES } from '@/lib/interface-names';
import { readOnlyReason } from '@/lib/permissions';
import { formatDate, nowIso } from '@/lib/format';
import {
  COURSE_DURATION_OPTION_RULE_PENDING,
  deriveActualCourseDuration,
  deriveCollegeEmail,
  deriveGroup,
  deriveIntake,
  deriveState,
  suggestCourseDurationOption,
} from '@/lib/student-rules';
import { COUNTRY_OPTIONS } from '@/mock-data';
import { COE_OPTIONS, YES_NO_OPTIONS, studentFormSchema, type StudentFormValues } from './student-fields';
import type { ValidationIssue, ValidationResult, ReasonCode } from '@/types/common';
import type { StudentInput, StudentRecord } from '@/types/student';

const EMPTY_FORM: StudentFormValues = {
  collegeId: '',
  campusId: '',
  collegeEmail: '',
  firstName: '',
  lastName: '',
  studentId: '',
  coeStatus: 'CoE',
  proposedStartDate: '',
  proposedEndDate: '',
  qualificationTitle: '',
  ctStudent: 'No',
  personalEmail: '',
  primaryPhone: '',
  primaryCountry: '',
  remarks: '',
};

export function SingleStudentEntry({ initialStudentId }: { initialStudentId?: string }) {
  const { user, permissions } = useAuth();
  const { data, campusesForCollege, offeringsFor, collegeById, campusById } = useReferenceData();

  const [mode, setMode] = React.useState<'idle' | 'create' | 'edit'>('idle');
  const [record, setRecord] = React.useState<StudentRecord | null>(null);
  const [searchTerm, setSearchTerm] = React.useState(initialStudentId ?? '');
  const [searching, setSearching] = React.useState(false);
  const [searchMessage, setSearchMessage] = React.useState<string | null>(null);

  const [previewOpen, setPreviewOpen] = React.useState(false);
  const [validation, setValidation] = React.useState<ValidationResult | null>(null);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [duplicateState, setDuplicateState] = React.useState<'unknown' | 'available' | 'duplicate'>('unknown');

  const form = useForm<StudentFormValues>({
    resolver: zodResolver(studentFormSchema),
    defaultValues: EMPTY_FORM,
    mode: 'onBlur',
  });

  const values = form.watch();
  const canChange = permissions.createStudent;

  // ------------------------------------------------------- derived selections
  const campuses = campusesForCollege(values.collegeId);
  const offerings = offeringsFor(values.collegeId, values.campusId);
  const offering = offerings.find((entry) => entry.qualificationTitle === values.qualificationTitle);
  const college = collegeById(values.collegeId);
  const campus = campusById(values.campusId);

  // SRS 6.3 generated values (SST-03).
  const generated = React.useMemo(() => {
    const actualCourseDuration = deriveActualCourseDuration(values.proposedStartDate, values.proposedEndDate);
    return {
      intake: deriveIntake(values.proposedStartDate),
      group: deriveGroup({
        qualificationCode: offering?.qualificationCode ?? '',
        campus,
        proposedStartDate: values.proposedStartDate,
      }),
      qualificationCode: offering?.qualificationCode ?? '',
      state: deriveState(campus),
      actualCourseDuration,
      courseDurationOption: suggestCourseDurationOption(actualCourseDuration, offering?.durationOptions ?? []),
    };
  }, [values.proposedStartDate, values.proposedEndDate, offering, campus]);

  // College Email is generated but editable; it regenerates while untouched.
  React.useEffect(() => {
    if (mode !== 'create') return;
    if (form.getFieldState('collegeEmail').isDirty) return;
    const proposed = deriveCollegeEmail(values.studentId, college);
    if (proposed && proposed !== values.collegeEmail) {
      form.setValue('collegeEmail', proposed, { shouldDirty: false });
    }
  }, [values.studentId, values.collegeEmail, college, mode, form]);

  // Mock duplicate Student ID check (SST-05 / DATA-01).
  React.useEffect(() => {
    const studentId = values.studentId.trim();
    if (!studentId) {
      setDuplicateState('unknown');
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      void getTdmsClient()
        .isStudentIdAvailable(studentId, record?.id)
        .then((available) => {
          if (!cancelled) setDuplicateState(available ? 'available' : 'duplicate');
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [values.studentId, record?.id]);

  const search = React.useCallback(
    async (term: string) => {
      const studentId = term.trim();
      if (!studentId) return;
      setSearching(true);
      setSearchMessage(null);
      try {
        const found = await getTdmsClient().findStudentByStudentId(studentId);
        if (!found) {
          setSearchMessage(`No student was found with Student ID "${studentId}".`);
          return;
        }
        setRecord(found);
        setMode('edit');
        form.reset({
          collegeId: found.collegeId,
          campusId: found.campusId,
          collegeEmail: found.collegeEmail,
          firstName: found.firstName,
          lastName: found.lastName,
          studentId: found.studentId,
          coeStatus: found.coeStatus,
          proposedStartDate: found.proposedStartDate,
          proposedEndDate: found.proposedEndDate,
          qualificationTitle: found.qualificationTitle,
          ctStudent: found.ctStudent,
          personalEmail: found.personalEmail,
          primaryPhone: found.primaryPhone,
          primaryCountry: found.primaryCountry,
          remarks: found.remarks,
        });
      } finally {
        setSearching(false);
      }
    },
    [form],
  );

  React.useEffect(() => {
    if (initialStudentId) void search(initialStudentId);
  }, [initialStudentId, search]);

  function startCreate() {
    setRecord(null);
    setMode('create');
    setSearchMessage(null);
    form.reset(EMPTY_FORM);
  }

  function buildInput(): StudentInput {
    return {
      group: generated.group,
      intake: generated.intake,
      collegeId: values.collegeId,
      campusId: values.campusId,
      collegeEmail: values.collegeEmail,
      firstName: values.firstName,
      lastName: values.lastName,
      studentId: values.studentId.trim(),
      coeStatus: values.coeStatus,
      proposedStartDate: values.proposedStartDate,
      proposedEndDate: values.proposedEndDate,
      actualCourseDuration: generated.actualCourseDuration,
      courseDurationOption: generated.courseDurationOption,
      qualificationTitle: values.qualificationTitle,
      qualificationCode: generated.qualificationCode,
      ctStudent: values.ctStudent,
      personalEmail: values.personalEmail,
      primaryPhone: values.primaryPhone,
      state: generated.state,
      primaryCountry: values.primaryCountry,
      remarks: values.remarks,
    };
  }

  async function runPreview() {
    const valid = await form.trigger();
    const issues: ValidationIssue[] = [];

    if (!valid) {
      for (const [field, error] of Object.entries(form.formState.errors)) {
        issues.push({
          id: `field-${field}`,
          severity: 'blocking',
          title: 'Required information is missing or invalid',
          message: (error as { message?: string })?.message ?? `Correct the ${field} field.`,
          reference: field,
        });
      }
    }

    if (duplicateState === 'duplicate') {
      issues.push({
        id: 'duplicate-student-id',
        severity: 'blocking',
        title: 'Duplicate Student ID',
        message: `Student ID ${values.studentId} already exists in the database. Student ID must uniquely identify a student record.`,
        reference: 'Student ID',
      });
    }

    issues.push({
      id: 'week-calculation',
      severity: 'pending-approval',
      title: 'Actual Course Duration calculation',
      message:
        'Whether course weeks are counted using inclusive or exclusive dates has not been approved. The calculated value is shown for review and is not final.',
      openDecisionId: 'OD-08',
    });

    if (COURSE_DURATION_OPTION_RULE_PENDING) {
      issues.push({
        id: 'ct-rule',
        severity: 'pending-approval',
        title: 'CT definition and Course Duration Option display rule',
        message:
          'The exact CT definition and the rule that hides Course Duration Option have not been approved, so the field is always shown and no CT business rule is applied.',
        openDecisionId: 'OD-08',
      });
    }

    setValidation({
      issues,
      canSave: issues.filter((issue) => issue.severity === 'blocking').length === 0,
      checkedAt: nowIso(),
    });
    setPreviewOpen(true);
  }

  async function save() {
    if (!user || !validation?.canSave) return;
    setBusy(true);
    try {
      const client = getTdmsClient();
      const input = buildInput();
      if (mode === 'edit' && record) {
        const updated = await client.updateStudent(record.id, input, { actor: user });
        setRecord(updated);
        toast.success('Student record updated', {
          description: `${updated.studentId} was updated and a user activity record was created.`,
        });
      } else {
        const created = await client.createStudent(input, { actor: user });
        setRecord(created);
        setMode('edit');
        toast.success('Student record created', {
          description: `${created.studentId} was created and a user activity record was created.`,
        });
      }
      setConfirmOpen(false);
      setPreviewOpen(false);
    } catch (error) {
      toast.error('The student record could not be saved', {
        description: error instanceof Error ? error.message : 'Try again, or contact the TDMS administrator.',
      });
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete(reason: ReasonCode, reasonDetail?: string) {
    if (!record || !user) return;
    setBusy(true);
    try {
      await getTdmsClient().deleteStudent(record.id, { reason, reasonDetail }, { actor: user });
      toast.success('Student record moved to the recycle area', {
        description: `${record.studentId} was removed from active use. A user activity record was created.`,
      });
      setDeleteOpen(false);
      setRecord(null);
      setMode('idle');
      form.reset(EMPTY_FORM);
    } finally {
      setBusy(false);
    }
  }

  const changes = record
    ? buildChanges(
        record as unknown as Record<string, unknown>,
        buildInput() as unknown as Record<string, unknown>,
        [
          { key: 'collegeId', label: 'College', format: (v) => collegeById(String(v ?? ''))?.collegeFullName ?? '' },
          { key: 'campusId', label: 'Campus', format: (v) => campusById(String(v ?? ''))?.campusName ?? '' },
          { key: 'collegeEmail', label: 'College Email' },
          { key: 'firstName', label: 'First Name' },
          { key: 'lastName', label: 'Last Name' },
          { key: 'studentId', label: 'Student ID' },
          { key: 'coeStatus', label: 'CoE / Non-CoE' },
          { key: 'proposedStartDate', label: 'Proposed Start Date' },
          { key: 'proposedEndDate', label: 'Proposed End Date' },
          { key: 'actualCourseDuration', label: 'Actual Course Duration' },
          { key: 'courseDurationOption', label: 'Course Duration Option' },
          { key: 'qualificationTitle', label: 'Qualification Title' },
          { key: 'qualificationCode', label: 'Qualification Code' },
          { key: 'group', label: 'Group' },
          { key: 'intake', label: 'Intake' },
          { key: 'ctStudent', label: 'CT Student' },
          { key: 'personalEmail', label: 'Personal Email' },
          { key: 'primaryPhone', label: 'Primary Phone' },
          { key: 'state', label: 'State' },
          { key: 'primaryCountry', label: 'Primary Country' },
          { key: 'remarks', label: 'Remarks' },
        ],
      )
    : [];

  const errors = form.formState.errors;

  return (
    <div className="space-y-5">
      {!canChange && <ReadOnlyNotice message={readOnlyReason(user, INTERFACE_NAMES.singleStudentEntry)} />}

      <Card>
        <CardHeader>
          <CardTitle>Find or create a student record</CardTitle>
          <CardDescription>
            Search an existing Student ID to view or edit it, or start a new record.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1.5">
            <label htmlFor="student-search" className="text-[13px] font-medium">
              Search Student ID
            </label>
            <div className="flex gap-2">
              <Input
                id="student-search"
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void search(searchTerm);
                }}
                placeholder="e.g. ST20261001"
              />
              <Button variant="outline" onClick={() => void search(searchTerm)} disabled={searching}>
                {searching ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Search aria-hidden="true" />}
                Search
              </Button>
            </div>
          </div>
          {canChange && (
            <Button onClick={startCreate}>
              <FilePlus2 aria-hidden="true" />
              Create New Student
            </Button>
          )}
        </CardContent>
      </Card>

      {searchMessage && (
        <Alert variant="warning">
          <AlertCircle aria-hidden="true" />
          <AlertDescription>{searchMessage}</AlertDescription>
        </Alert>
      )}

      {mode === 'idle' ? (
        <EmptyState
          title="No student record is open"
          description="Search for a Student ID, or select Create New Student to enter a new record."
          icon={UserRoundSearch}
        />
      ) : (
        <Card>
          <CardHeader className="flex-row items-start justify-between gap-4">
            <div>
              <CardTitle>{mode === 'edit' ? `Student record ${record?.studentId}` : 'New student record'}</CardTitle>
              <CardDescription>
                {mode === 'edit'
                  ? 'Change the values you need, then preview the changes before confirming the update.'
                  : 'Complete the form, then preview the record before confirming the save.'}
              </CardDescription>
            </div>
            {mode === 'edit' && record && permissions.deleteStudent && (
              <Button variant="outline" size="sm" onClick={() => setDeleteOpen(true)}>
                <Trash2 aria-hidden="true" />
                Delete
              </Button>
            )}
          </CardHeader>

          <CardContent className="space-y-8">
            <fieldset disabled={!canChange} className="space-y-8">
              <FormSection title="Identification and college">
                <FormGrid columns={3}>
                  <FormField
                    label="Group"
                    htmlFor="student-group"
                    required
                    generated
                    hint="Generated from the qualification, campus and proposed start date."
                  >
                    <Input id="student-group" value={generated.group} readOnly placeholder="Generated after selection" />
                  </FormField>

                  <FormField
                    label="Intake"
                    htmlFor="student-intake"
                    required
                    generated
                    hint="Generated from the proposed start date."
                  >
                    <Input id="student-intake" value={generated.intake} readOnly placeholder="Generated after selection" />
                  </FormField>

                  <FormField label="College" htmlFor="student-college" required error={errors.collegeId?.message}>
                    <DependentSelect
                      id="student-college"
                      value={values.collegeId}
                      onChange={(value) => {
                        form.setValue('collegeId', value, { shouldValidate: true });
                        form.setValue('campusId', '');
                        form.setValue('qualificationTitle', '');
                      }}
                      options={(data?.colleges ?? [])
                        .filter((entry) => entry.isActive)
                        .map((entry) => ({ value: entry.id, label: entry.collegeFullName }))}
                      placeholder="Select college"
                    />
                  </FormField>

                  <FormField label="Campus" htmlFor="student-campus" required error={errors.campusId?.message}>
                    <DependentSelect
                      id="student-campus"
                      value={values.campusId}
                      onChange={(value) => {
                        form.setValue('campusId', value, { shouldValidate: true });
                        form.setValue('qualificationTitle', '');
                      }}
                      options={campuses.map((entry) => ({
                        value: entry.id,
                        label: `${entry.campusName} — ${entry.campusLocation}`,
                      }))}
                      placeholder="Select campus"
                      requires={values.collegeId ? undefined : 'a college'}
                    />
                  </FormField>

                  <FormField
                    label="College Email"
                    htmlFor="student-college-email"
                    required
                    hint="Generated from the Student ID and the approved college domain. You can edit it."
                    error={errors.collegeEmail?.message}
                  >
                    <Input id="student-college-email" {...form.register('collegeEmail')} placeholder="Generated" />
                  </FormField>

                  <FormField label="First Name" htmlFor="student-first-name" required error={errors.firstName?.message}>
                    <Input id="student-first-name" {...form.register('firstName')} />
                  </FormField>

                  <FormField label="Last Name" htmlFor="student-last-name">
                    <Input id="student-last-name" {...form.register('lastName')} />
                  </FormField>

                  <FormField
                    label="Student ID"
                    htmlFor="student-id"
                    required
                    error={errors.studentId?.message}
                    hint={
                      duplicateState === 'duplicate'
                        ? undefined
                        : duplicateState === 'available' && values.studentId
                          ? 'This Student ID is available.'
                          : 'The main student record key. It must be unique.'
                    }
                  >
                    <Input id="student-id" {...form.register('studentId')} placeholder="e.g. ST20261234" />
                  </FormField>

                  <FormField label="CoE / Non-CoE" htmlFor="student-coe" required>
                    <SimpleSelect
                      id="student-coe"
                      value={values.coeStatus}
                      onChange={(value) => form.setValue('coeStatus', value as StudentFormValues['coeStatus'])}
                      options={COE_OPTIONS}
                      placeholder="Select CoE status"
                    />
                  </FormField>
                </FormGrid>

                {duplicateState === 'duplicate' && values.studentId && (
                  <Alert variant="destructive">
                    <AlertCircle aria-hidden="true" />
                    <AlertDescription>
                      Student ID {values.studentId} already exists in the database. Enter a different Student ID.
                    </AlertDescription>
                  </Alert>
                )}
                {duplicateState === 'available' && values.studentId && mode === 'create' && (
                  <Alert variant="success">
                    <CheckCircle2 aria-hidden="true" />
                    <AlertDescription>Student ID {values.studentId} is available.</AlertDescription>
                  </Alert>
                )}
              </FormSection>

              <FormSection title="Dates, duration and course">
                <FormGrid columns={3}>
                  <FormField
                    label="Proposed Start Date"
                    htmlFor="student-start"
                    required
                    error={errors.proposedStartDate?.message}
                  >
                    <Input id="student-start" type="date" {...form.register('proposedStartDate')} />
                  </FormField>

                  <FormField
                    label="Proposed End Date"
                    htmlFor="student-end"
                    required
                    error={errors.proposedEndDate?.message}
                  >
                    <Input id="student-end" type="date" {...form.register('proposedEndDate')} />
                  </FormField>

                  <FormField
                    label="Actual Course Duration"
                    htmlFor="student-duration"
                    required
                    generated
                    pendingRule="OD-08: whether course weeks are counted using inclusive or exclusive dates has not been approved."
                  >
                    <Input
                      id="student-duration"
                      value={generated.actualCourseDuration ? `${generated.actualCourseDuration} weeks` : ''}
                      readOnly
                      placeholder="Calculated from the dates"
                    />
                  </FormField>

                  <FormField
                    label="Course Duration Option"
                    htmlFor="student-duration-option"
                    conditional
                    pendingRule="OD-08: the rule that hides this field when CT applies has not been approved, so it is always shown."
                  >
                    <SimpleSelect
                      id="student-duration-option"
                      value={generated.courseDurationOption ? String(generated.courseDurationOption) : ''}
                      onChange={() => undefined}
                      options={(offering?.durationOptions ?? []).map((weeks) => ({
                        value: String(weeks),
                        label: `${weeks} weeks`,
                      }))}
                      placeholder="Selected from the calculated duration"
                      disabled
                    />
                  </FormField>

                  <FormField
                    label="Qualification Title"
                    htmlFor="student-qualification"
                    required
                    error={errors.qualificationTitle?.message}
                  >
                    <DependentSelect
                      id="student-qualification"
                      value={values.qualificationTitle}
                      onChange={(value) => form.setValue('qualificationTitle', value, { shouldValidate: true })}
                      options={offerings.map((entry) => ({
                        value: entry.qualificationTitle,
                        label: `${entry.qualificationCode} — ${entry.qualificationTitle}`,
                      }))}
                      placeholder="Select qualification"
                      requires={values.campusId ? undefined : 'a campus'}
                    />
                  </FormField>

                  <FormField
                    label="Qualification Code"
                    htmlFor="student-qualification-code"
                    required
                    generated
                    hint="Returned automatically for the selected qualification."
                  >
                    <Input id="student-qualification-code" value={generated.qualificationCode} readOnly />
                  </FormField>
                </FormGrid>
              </FormSection>

              <FormSection title="Qualification and contact">
                <FormGrid columns={3}>
                  <FormField
                    label="CT Student"
                    htmlFor="student-ct"
                    required
                    pendingRule="OD-08: the exact CT definition has not been confirmed. The value is stored but no CT rule is applied."
                  >
                    <SimpleSelect
                      id="student-ct"
                      value={values.ctStudent}
                      onChange={(value) => form.setValue('ctStudent', value as StudentFormValues['ctStudent'])}
                      options={YES_NO_OPTIONS}
                      placeholder="Select"
                    />
                  </FormField>

                  <FormField label="Personal Email" htmlFor="student-personal-email" error={errors.personalEmail?.message}>
                    <Input id="student-personal-email" {...form.register('personalEmail')} />
                  </FormField>

                  <FormField label="Primary Phone" htmlFor="student-phone">
                    <Input id="student-phone" {...form.register('primaryPhone')} />
                  </FormField>

                  <FormField
                    label="State"
                    htmlFor="student-state"
                    required
                    generated
                    hint="Generated from the selected campus."
                  >
                    <Input id="student-state" value={generated.state} readOnly />
                  </FormField>

                  <FormField label="Primary Country" htmlFor="student-country">
                    <SimpleSelect
                      id="student-country"
                      value={values.primaryCountry}
                      onChange={(value) => form.setValue('primaryCountry', value)}
                      options={COUNTRY_OPTIONS.map((country) => ({ value: country, label: country }))}
                      placeholder="Select country"
                    />
                  </FormField>
                </FormGrid>

                <FormField label="Remarks" htmlFor="student-remarks">
                  <Textarea id="student-remarks" {...form.register('remarks')} />
                </FormField>
              </FormSection>
            </fieldset>

            {canChange && (
              <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
                <Button
                  variant="outline"
                  onClick={() => {
                    setMode('idle');
                    setRecord(null);
                    form.reset(EMPTY_FORM);
                  }}
                >
                  Cancel
                </Button>
                <Button onClick={() => void runPreview()}>
                  <Eye aria-hidden="true" />
                  {mode === 'edit' ? 'Preview Changes' : 'Preview Student'}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Preview: shows the complete proposed record and every validation message
          without saving (SST-04). */}
      <Sheet open={previewOpen} onOpenChange={busy ? undefined : setPreviewOpen}>
        <SheetContent width="lg">
          <SheetHeader>
            <SheetTitle>{mode === 'edit' ? 'Preview changes' : 'Preview student record'}</SheetTitle>
            <SheetDescription>
              Preview does not save. Nothing is written to the database until you confirm.
            </SheetDescription>
          </SheetHeader>
          <SheetBody className="space-y-6">
            <PendingRuleNotice
              decisionId="OD-08"
              message="Generated values use provisional prototype rules. The approved intake, group and week-calculation rules have not been supplied yet."
            />
            <PreviewPanel
              groups={[
                {
                  title: 'Identification and college',
                  items: [
                    { label: 'Group', value: generated.group, generated: true },
                    { label: 'Intake', value: generated.intake, generated: true },
                    { label: 'College', value: college?.collegeFullName ?? '' },
                    { label: 'Campus', value: campus ? `${campus.campusName} — ${campus.campusLocation}` : '' },
                    { label: 'College Email', value: values.collegeEmail },
                    { label: 'First Name', value: values.firstName },
                    { label: 'Last Name', value: values.lastName },
                    { label: 'Student ID', value: values.studentId },
                    { label: 'CoE / Non-CoE', value: values.coeStatus },
                  ],
                },
                {
                  title: 'Dates, duration and course',
                  items: [
                    { label: 'Proposed Start Date', value: formatDate(values.proposedStartDate) },
                    { label: 'Proposed End Date', value: formatDate(values.proposedEndDate) },
                    {
                      label: 'Actual Course Duration',
                      value: generated.actualCourseDuration ? `${generated.actualCourseDuration} weeks` : '',
                      generated: true,
                    },
                    {
                      label: 'Course Duration Option',
                      value: generated.courseDurationOption ? `${generated.courseDurationOption} weeks` : '',
                    },
                    { label: 'Qualification Title', value: values.qualificationTitle },
                    { label: 'Qualification Code', value: generated.qualificationCode, generated: true },
                  ],
                },
                {
                  title: 'Qualification and contact',
                  items: [
                    { label: 'CT Student', value: values.ctStudent },
                    { label: 'Personal Email', value: values.personalEmail },
                    { label: 'Primary Phone', value: values.primaryPhone },
                    { label: 'State', value: generated.state, generated: true },
                    { label: 'Primary Country', value: values.primaryCountry },
                    { label: 'Remarks', value: values.remarks },
                  ],
                },
              ]}
            />
            <div>
              <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
                Validation results
              </h3>
              <ValidationPanel result={validation} />
            </div>
          </SheetBody>
          <SheetFooter>
            <Button variant="outline" onClick={() => setPreviewOpen(false)} disabled={busy}>
              Back to form
            </Button>
            <Button onClick={() => setConfirmOpen(true)} disabled={!validation?.canSave || busy}>
              <Save aria-hidden="true" />
              {mode === 'edit' ? 'Update Student Record' : 'Save Student Record'}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      {mode === 'edit' && record ? (
        <ChangeSummaryDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Update Student Record?"
          description="Check the record and the fields that will change, then confirm the update."
          record={{
            primary: record.studentId,
            secondary: `${record.firstName} ${record.lastName}`.trim(),
            lines: [`${record.qualificationCode} — ${record.qualificationTitle}`],
          }}
          changes={changes}
          busy={busy}
          onConfirm={save}
        />
      ) : (
        <ConfirmationDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Save Student Record?"
          description="Please confirm that you want to create this student record."
          confirmLabel="Confirm and Save"
          busy={busy}
          onConfirm={save}
        >
          <dl className="space-y-1.5 rounded-lg border border-border bg-muted/40 px-4 py-3 text-[13px]">
            <div className="flex gap-2">
              <dt className="w-32 text-muted-foreground">Student ID:</dt>
              <dd className="font-medium">{values.studentId}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-32 text-muted-foreground">Student:</dt>
              <dd className="font-medium">{`${values.firstName} ${values.lastName}`.trim()}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-32 text-muted-foreground">Qualification:</dt>
              <dd className="font-medium">{generated.qualificationCode}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-32 text-muted-foreground">Group:</dt>
              <dd className="font-medium">{generated.group || '—'}</dd>
            </div>
          </dl>
        </ConfirmationDialog>
      )}

      {record && (
        <DeleteConfirmationDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          recordTypeLabel="Student Record"
          reasonContext="student"
          busy={busy}
          record={{
            primary: record.studentId,
            secondary: `${record.firstName} ${record.lastName}`.trim(),
            lines: [
              `${record.qualificationCode} — ${record.qualificationTitle}`,
              `Current status: Active · ${record.group || 'No group'}`,
            ],
          }}
          onConfirm={confirmDelete}
        />
      )}
    </div>
  );
}
