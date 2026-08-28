'use client';

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { AlertCircle, CheckCircle2, Eye, Save } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
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
import { ReadOnlyNotice } from '@/components/common/states';
import { useReferenceData } from '@/features/shared/reference-data-context';
import { useAuth } from '@/features/auth/auth-context';
import { studentsApi, type StudentInput, type StudentRecord } from '@/services/students-api';
import { INTERFACE_NAMES } from '@/lib/interface-names';
import { readOnlyReason } from '@/lib/permissions';
import { formatDate, nowIso } from '@/lib/format';
import { deriveActualCourseDuration, deriveCollegeEmail, deriveState } from '@/lib/student-rules';
import { COUNTRY_OPTIONS } from '@/mock-data';
import { COE_OPTIONS, YES_NO_OPTIONS, studentFormSchema, type StudentFormValues } from './student-fields';
import type { ValidationIssue, ValidationResult, ReasonCode } from '@/types/common';

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
  courseDurationOption: '',
  ctStudent: 'No',
  personalEmail: '',
  primaryPhone: '',
  primaryCountry: '',
  remarks: '',
};

/**
 * Single Student Entry — create or edit one record, in a popup.
 *
 * The form is a dialog rather than a section of the page, so the records list
 * behind it keeps its place and its scroll position. `student` decides the
 * mode: a record edits it, `null` starts a new one.
 */
export function SingleStudentEntry({
  open,
  onOpenChange,
  student = null,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  student?: StudentRecord | null;
  onSaved?: () => void;
}) {
  const { user, permissions } = useAuth();
  const { data, campusesForCollege, offeringsFor, collegeById, campusById } = useReferenceData();

  const [mode, setMode] = React.useState<'idle' | 'create' | 'edit'>('idle');
  const [record, setRecord] = React.useState<StudentRecord | null>(null);

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
  const canChange = permissions.maintainStudentData;

  // ------------------------------------------------------- derived selections
  const campuses = campusesForCollege(values.collegeId);
  const offerings = offeringsFor(values.collegeId, values.campusId);
  const offering = offerings.find((entry) => entry.qualificationTitle === values.qualificationTitle);
  const college = collegeById(values.collegeId);
  const campus = campusById(values.campusId);

  // SRS 6.3 generated values (SST-03).
  //
  // Intake and Group are **not** here: they are worked out by the API from the
  // rolling timetable when the record is saved (rule 1.3), so the form shows
  // what was assigned rather than guessing at it locally.
  const generated = React.useMemo(
    () => ({
      qualificationCode: offering?.qualificationCode ?? '',
      state: deriveState(campus),
      // OD-08 approved: inclusive date calculation.
      actualCourseDuration: deriveActualCourseDuration(values.proposedStartDate, values.proposedEndDate),
    }),
    [values.proposedStartDate, values.proposedEndDate, offering, campus],
  );

  /**
   * The Intake and Group the system assigned, as text for the read-only fields.
   *
   * Before a save there is nothing to show — the assignment happens against the
   * rolling timetable on the server — so the field says so instead of inventing
   * a value.
   */
  const assigned = React.useMemo(() => {
    if (!record) {
      return {
        intake: 'Assigned on save from the rolling timetable',
        group: 'Read from the assigned intake',
        note: null as string | null,
      };
    }
    if (record.intake_match_status === 'NOT_APPLICABLE') {
      return { intake: 'N/A', group: 'N/A', note: 'A Credit Transfer student has no intake or group.' };
    }
    if (record.intake_match_status === 'TBD' || !record.intake_label) {
      return {
        intake: 'TBD',
        group: '—',
        note: 'No rolling timetable has been supplied for this qualification and duration, so no intake could be assigned.',
      };
    }
    return { intake: record.intake_label, group: record.group_code ?? 'NA', note: null };
  }, [record]);

  // College Email is generated but editable; it regenerates while untouched.
  React.useEffect(() => {
    if (mode !== 'create') return;
    if (form.getFieldState('collegeEmail').isDirty) return;
    const proposed = deriveCollegeEmail(values.studentId, college);
    if (proposed && proposed !== values.collegeEmail) {
      form.setValue('collegeEmail', proposed, { shouldDirty: false });
    }
  }, [values.studentId, values.collegeEmail, college, mode, form]);

  /**
   * Live duplicate Student ID check (SST-05 / DATA-01).
   *
   * A Student ID may legitimately appear more than once now — one person can
   * hold two enrolments — so this warns only about a clash with an **active**
   * record other than the one being edited. The database has the final say.
   */
  React.useEffect(() => {
    const studentId = values.studentId.trim();
    if (!studentId) {
      setDuplicateState('unknown');
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      void studentsApi
        .list({ search: studentId, limit: 20 })
        .then((page) => {
          if (cancelled) return;
          const clash = page.items.some(
            (item) =>
              item.student_id.toUpperCase() === studentId.toUpperCase() &&
              item.status === 'ACTIVE' &&
              item.id !== record?.id,
          );
          setDuplicateState(clash ? 'duplicate' : 'available');
        })
        .catch(() => {
          if (!cancelled) setDuplicateState('unknown');
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [values.studentId, record?.id]);

  /**
   * Fill the form from a stored record.
   *
   * The record carries approved *names*; the form works in reference ids, so
   * the ids are resolved back from the reference data.
   */
  const resetFromRecord = React.useCallback(
    (found: StudentRecord) => {
      const foundCollege = (data?.colleges ?? []).find(
        (item) => item.collegeShortName === found.college || item.collegeFullName === found.college,
      );
      const foundCampus = (data?.campuses ?? []).find((item) => item.campusName === found.campus);
      form.reset({
          collegeId: foundCollege?.id ?? '',
          campusId: foundCampus?.id ?? '',
          collegeEmail: found.college_email,
          firstName: found.first_name,
          lastName: found.last_name ?? '',
          studentId: found.student_id,
          coeStatus: found.coe_status === 'COE' ? 'CoE' : 'Non-CoE',
          proposedStartDate: found.proposed_start_date,
          proposedEndDate: found.proposed_end_date,
          qualificationTitle: found.qualification_title,
          courseDurationOption: found.course_duration_option_weeks
            ? String(found.course_duration_option_weeks)
            : '',
          ctStudent: found.ct_student ? 'Yes' : 'No',
          personalEmail: found.personal_email ?? '',
          primaryPhone: found.primary_phone ?? '',
        primaryCountry: '',
        remarks: found.remarks ?? '',
      });
    },
    [form, data],
  );

  /** Open in the right mode: a supplied record edits it, nothing creates one. */
  React.useEffect(() => {
    if (!open) return;
    if (student) {
      setRecord(student);
      setMode('edit');
      resetFromRecord(student);
    } else {
      setRecord(null);
      setMode('create');
      form.reset(EMPTY_FORM);
    }
  }, [open, student, resetFromRecord, form]);

  /**
   * The payload for the API.
   *
   * Intake, Group, Qualification Code, State and Actual Course Duration are
   * absent by design: the API derives every one of them, so sending a local
   * guess could only ever disagree with it.
   */
  function buildInput(): StudentInput {
    return {
      student_id: values.studentId.trim(),
      first_name: values.firstName,
      last_name: values.lastName || null,
      college_id: Number(values.collegeId),
      campus_id: Number(values.campusId),
      qualification_code: generated.qualificationCode || null,
      coe_status: values.coeStatus === 'CoE' ? 'COE' : 'NON_COE',
      ct_student: values.ctStudent === 'Yes',
      proposed_start_date: values.proposedStartDate,
      proposed_end_date: values.proposedEndDate,
      personal_email: values.personalEmail || null,
      primary_phone: values.primaryPhone || null,
      status: record?.status ?? 'ACTIVE',
      college_email: values.collegeEmail || null,
      remarks: values.remarks || null,
      // OD-08 approved: staff select the approved option; TDMS derives nothing.
      course_duration_option_weeks: values.courseDurationOption
        ? Number(values.courseDurationOption)
        : null,
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

    // OD-08 approved: the Course Duration Option must be one of the approved
    // options for the selected offering when a value is chosen.
    const approvedOptions = offering?.durationOptions ?? [];
    if (values.courseDurationOption && !approvedOptions.includes(Number(values.courseDurationOption))) {
      issues.push({
        id: 'duration-option',
        severity: 'blocking',
        title: 'Course Duration Option is not approved for this qualification',
        message: `Approved options for ${offering?.qualificationCode ?? 'this qualification'} are ${approvedOptions.join(', ')} weeks. Select an approved option.`,
        reference: 'Course Duration Option',
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
      const input = buildInput();
      if (mode === 'edit' && record) {
        const updated = await studentsApi.update(record.id, input);
        setRecord(updated);
        toast.success('Student record updated', {
          description: `${updated.student_id} was updated and a user activity record was created.`,
        });
      } else {
        const created = await studentsApi.create(input);
        setRecord(created);
        setMode('edit');
        toast.success('Student record created', {
          description: `${created.student_id} was created and a user activity record was created.`,
        });
      }
      setConfirmOpen(false);
      setPreviewOpen(false);
      onSaved?.();
      onOpenChange(false);
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
      await studentsApi.remove(record.id, reason, reasonDetail);
      toast.success('Student record moved to the recycle area', {
        description: `${record.student_id} was removed from active use. A user activity record was created.`,
      });
      setDeleteOpen(false);
      setRecord(null);
      form.reset(EMPTY_FORM);
      onSaved?.();
      onOpenChange(false);
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
    <>
      {/*
        `DialogContent` lays itself out as header / scrolling body / footer, so
        the title stays put and the actions stay reachable however long the form
        is. Only the body scrolls.
      */}
      <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
        <DialogContent size="full">
          <DialogHeader>
            <DialogTitle>{mode === 'edit' ? `Student record ${record?.student_id}` : 'New student record'}</DialogTitle>
            <DialogDescription>
              {mode === 'edit'
                ? 'Change the values you need, then preview the changes before confirming the update.'
                : 'Complete the form, then preview the record before confirming the save.'}
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-6">
            {!canChange && <ReadOnlyNotice message={readOnlyReason(user, INTERFACE_NAMES.singleStudentEntry)} />}
            <fieldset disabled={!canChange} className="space-y-8">
              <FormSection title="Identification and college">
                <FormGrid columns={3}>
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
                    hint="Calculated inclusively from the proposed start and end dates."
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
                    hint="Select the approved duration option for this student. TDMS does not derive it from a Credit Transfer."
                    error={errors.courseDurationOption?.message}
                  >
                    <SimpleSelect
                      id="student-duration-option"
                      value={values.courseDurationOption}
                      onChange={(value) => form.setValue('courseDurationOption', value, { shouldValidate: true })}
                      options={(offering?.durationOptions ?? []).map((weeks) => ({
                        value: String(weeks),
                        label: `${weeks} weeks`,
                      }))}
                      placeholder="Select approved duration option"
                      disabled={!offering}
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
                    hint="CT means Credit Transfer. Yes records that the student has at least one approved Credit Transfer."
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

              {/*
                Assigned by the system, not entered. Kept at the end and clearly
                separated: putting read-only values among the inputs invites the
                user to try to type in them (rule 1.3).
              */}
              <FormSection title="Assigned by the system">
                <FormGrid columns={2}>
                  <FormField
                    label="Intake"
                    htmlFor="student-intake"
                    generated
                    hint={assigned.note ?? 'Assigned from the rolling timetable using the proposed start date.'}
                  >
                    <Input id="student-intake" value={assigned.intake} readOnly className="bg-muted/50" />
                  </FormField>

                  <FormField
                    label="Group"
                    htmlFor="student-group"
                    generated
                    hint="Read from the assigned intake. It is never chosen separately."
                  >
                    <Input id="student-group" value={assigned.group} readOnly className="bg-muted/50" />
                  </FormField>
                </FormGrid>
              </FormSection>
            </fieldset>
          </DialogBody>

          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {canChange ? 'Cancel' : 'Close'}
            </Button>
            {canChange && (
              <Button onClick={() => void runPreview()}>
                <Eye aria-hidden="true" />
                {mode === 'edit' ? 'Preview Changes' : 'Preview Student'}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
            <PreviewPanel
              groups={[
                {
                  title: 'Identification and college',
                  items: [
                    { label: 'Intake', value: assigned.intake, generated: true },
                    { label: 'Group', value: assigned.group, generated: true },
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
                      value: values.courseDurationOption ? `${values.courseDurationOption} weeks` : '',
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
            primary: record.student_id,
            secondary: `${record.first_name} ${record.last_name ?? ''}`.trim(),
            lines: [`${record.qualification_code} — ${record.qualification_title}`],
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
              <dt className="w-32 text-muted-foreground">Intake:</dt>
              <dd className="font-medium">Assigned on save from the rolling timetable</dd>
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
            primary: record.student_id,
            secondary: `${record.first_name} ${record.last_name ?? ''}`.trim(),
            lines: [
              `${record.qualification_code} — ${record.qualification_title}`,
              `Current status: ${record.status.replace(/_/g, ' ')} · ${record.group_code || 'No group'}`,
            ],
          }}
          onConfirm={confirmDelete}
        />
      )}
    </>
  );
}
