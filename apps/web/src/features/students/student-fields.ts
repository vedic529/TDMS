import { z } from 'zod';

import type { StudentInput } from '@/types/student';
import { isValidEmail } from '@/lib/student-rules';

/**
 * Frontend validation for Single Student Entry.
 *
 * SST-05: a blank or duplicate Student ID is rejected and every invalid
 * required field is identified in plain language. Duplicate checking needs the
 * data service, so it is applied separately by the form.
 */
export const studentFormSchema = z
  .object({
    collegeId: z.string().min(1, 'Select the college in which the student is enrolled.'),
    campusId: z.string().min(1, 'Select the approved campus for the selected college.'),
    collegeEmail: z
      .string()
      .min(1, 'College Email is required.')
      .refine(isValidEmail, 'Enter a valid college email address.'),
    firstName: z.string().min(1, "Enter the student's first name."),
    lastName: z.string(),
    studentId: z
      .string()
      .min(1, 'Student ID is required and must not be blank.')
      .max(30, 'Student ID must be 30 characters or fewer.'),
    coeStatus: z.enum(['CoE', 'Non-CoE']),
    proposedStartDate: z.string().min(1, 'Select the proposed first date of the course.'),
    proposedEndDate: z.string().min(1, 'Select the proposed final date of the course.'),
    qualificationTitle: z.string().min(1, 'Select the qualification offered by the college and campus.'),
    ctStudent: z.enum(['Yes', 'No']),
    personalEmail: z.string(),
    primaryPhone: z.string(),
    primaryCountry: z.string(),
    remarks: z.string(),
  })
  .refine((values) => !values.personalEmail || isValidEmail(values.personalEmail), {
    path: ['personalEmail'],
    message: 'Enter a valid personal email address, or leave the field empty.',
  })
  .refine((values) => values.proposedEndDate > values.proposedStartDate, {
    path: ['proposedEndDate'],
    message: 'Proposed End Date must be after Proposed Start Date.',
  });

export type StudentFormValues = z.infer<typeof studentFormSchema>;

/** SRS 6.3 field labels, used by the preview, change summary and exports. */
export const STUDENT_FIELD_LABELS: Array<{ key: keyof StudentInput & string; label: string }> = [
  { key: 'group', label: 'Group' },
  { key: 'intake', label: 'Intake' },
  { key: 'collegeId', label: 'College' },
  { key: 'campusId', label: 'Campus' },
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
  { key: 'ctStudent', label: 'CT Student' },
  { key: 'personalEmail', label: 'Personal Email' },
  { key: 'primaryPhone', label: 'Primary Phone' },
  { key: 'state', label: 'State' },
  { key: 'primaryCountry', label: 'Primary Country' },
  { key: 'remarks', label: 'Remarks' },
];

export const COE_OPTIONS = [
  { value: 'CoE', label: 'CoE' },
  { value: 'Non-CoE', label: 'Non-CoE' },
];

export const YES_NO_OPTIONS = [
  { value: 'Yes', label: 'Yes' },
  { value: 'No', label: 'No' },
];
