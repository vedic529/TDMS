import type { IsoDateTime } from './common';

/** SRS 7.3 validation statuses - these exact names are shown to the user. */
export type StagedRowStatus =
  | 'Ready'
  | 'Needs correction'
  | 'Duplicate'
  | 'Unmatched reference'
  | 'Excluded by user';

export interface StagedRowIssue {
  /** Column the problem belongs to, so the row action can focus it. */
  field: string;
  /** BULK-05: plain-language explanation and the required correction. */
  message: string;
}

/**
 * One uploaded row held in the staging area (SRS 7.1).
 * Values are kept as strings because they come from a CSV/XLSX cell and may be
 * invalid until corrected.
 */
export interface StagedStudentRow {
  id: string;
  /** BULK-03/BULK-05: the row number in the uploaded file. */
  sourceRowNumber: number;
  studentId: string;
  firstName: string;
  lastName: string;
  collegeValue: string;
  campusValue: string;
  qualificationValue: string;
  coeStatus: string;
  proposedStartDate: string;
  proposedEndDate: string;
  personalEmail: string;
  primaryPhone: string;

  /** Mapped reference values resolved during validation, when they match. */
  resolvedCollegeId?: string;
  resolvedCampusId?: string;
  resolvedQualificationCode?: string;

  status: StagedRowStatus;
  issues: StagedRowIssue[];
  /** True once a user has edited the staged values. */
  corrected: boolean;
}

/** SRS 7.1 - the uploaded file and its staging area. */
export interface ImportBatch {
  id: string;
  batchReference: string;
  fileName: string;
  fileSizeBytes: number;
  uploadedAt: IsoDateTime;
  uploadedByUserId: string;
  uploadedByDisplayName: string;
  rowCount: number;
  rows: StagedStudentRow[];
  /** Set once the confirmed set has been written. */
  result?: ImportResult;
}

/** BULK-09 - the counts that must be reported. */
export interface ImportResult {
  inserted: number;
  excluded: number;
  duplicate: number;
  corrected: number;
  rejected: number;
  unmatched: number;
  completedAt: IsoDateTime;
}
