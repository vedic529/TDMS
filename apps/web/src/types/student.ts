import type { IsoDate, IsoDateTime, SoftDeletable } from './common';

/** SRS 6.3 - CoE / Non-CoE. */
export type CoeStatus = 'CoE' | 'Non-CoE';

/** SRS 6.3 - CT Student is a Yes/No selection. OD-08 keeps the CT definition open. */
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
  group: string;
  intake: string;
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
