import type { IsoDate, IsoDateTime, SoftDeletable } from './common';

/** SRS 6.3 - CoE / Non-CoE. */
export type CoeStatus = 'CoE' | 'Non-CoE';

/**
 * SRS 6.3 - CT Student is a Yes/No selection.
 * CT means Credit Transfer (confirmed under OD-08). What the flag records and
 * how it affects course duration are still awaiting approval.
 */
export type YesNo = 'Yes' | 'No';

/**
 * SRS 6.3 Student fields, in the SRS order.
 *
 * Generated fields (Group, Intake, Qualification Code, State, Actual Course
 * Duration) are stored on the record but are produced by TDMS, not typed by the
 * user. College Email is generated and remains editable with validation.
 */
export interface StudentRecord extends SoftDeletable {
  id: string;

  // Identification and college
  /**
   * Approved 11 August 2026: staff select `Group 1`...`Group N` for the ten
   * group-enabled qualifications, and `N/A` for every other one.
   */
  group: string;
  /**
   * ISO date (`YYYY-MM-01`) - the first day of the proposed start month.
   *
   * Stored as a date so sorting and filtering stay correct; the approved
   * `DD-MMM-YYYY` form is applied at the display and export boundary only.
   */
  /**
   * `null` for a Credit Transfer student, for whom an intake does not apply
   * (approved 13 August 2026). Rendered as `N/A`, which distinguishes "does not
   * apply" from an empty cell meaning "missing".
   */
  intake: string | null;
  collegeId: string;
  campusId: string;
  collegeEmail: string;
  firstName: string;
  lastName: string;
  studentId: string;
  coeStatus: CoeStatus;

  // Dates, duration and course
  proposedStartDate: IsoDate;
  proposedEndDate: IsoDate;
  actualCourseDuration: number;
  courseDurationOption: number | null;

  // Qualification and contact
  qualificationTitle: string;
  qualificationCode: string;
  ctStudent: YesNo;
  personalEmail: string;
  primaryPhone: string;
  state: string;
  primaryCountry: string;
  remarks: string;

  createdAt: IsoDateTime;
  updatedAt: IsoDateTime;
}

/** Values a user actually enters or selects. Generated values are derived. */
export type StudentInput = Omit<
  StudentRecord,
  'id' | 'createdAt' | 'updatedAt' | 'isDeleted' | 'deletion'
>;

export interface StudentFilters {
  search?: string;
  collegeId?: string;
  campusId?: string;
  qualificationCode?: string;
  coeStatus?: CoeStatus;
  intake?: string;
}
