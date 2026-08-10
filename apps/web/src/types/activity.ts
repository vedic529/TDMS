import type { IsoDateTime, ReasonCode } from './common';
import type { DataEditorAssignment, TdmsRole } from './auth';

/** SRS 4.5 / LOG-01 - actions that must create a user activity record. */
export type ActivityAction =
  | 'Sign in'
  | 'Sign out'
  | 'Create'
  | 'Edit'
  | 'Delete'
  | 'Restore'
  | 'Import'
  | 'Export'
  | 'Timetable save'
  | 'Override'
  | 'Access denied';

/** SRS 4.5 - Result values. */
export type ActivityResult =
  | 'Completed'
  | 'Rejected by validation'
  | 'Cancelled by the user'
  | 'Failed because of a system error'
  | 'Access granted'
  | 'Access denied';

/**
 * SRS 4.5 - stored user activity record fields.
 * The plain-language name is "user activity record"; "log" appears only in the
 * LOG-NN requirement identifier.
 */
export interface UserActivityRecord {
  /** System-generated record number. */
  activityRecordNumber: string;
  dateTime: IsoDateTime;
  /** Verified TDMS user, or "Unmatched user" for a failed sign-in. */
  userReference: string;
  accessLevel: TdmsRole | 'Unknown';
  assignment: DataEditorAssignment | null;
  /** Approved interface name, e.g. "Page 2B - Bulk Student Import". */
  pageOrFunction: string;
  action: ActivityAction;
  recordOrBatchReference: string;
  reason?: ReasonCode;
  reasonDetail?: string;
  result: ActivityResult;
  /** Correlation ID, Microsoft error code or internal error reference. */
  technicalReference?: string;
  plainLanguageDetail: string;
}

export interface ActivityFilters {
  search?: string;
  action?: ActivityAction;
  result?: ActivityResult;
  pageOrFunction?: string;
}
