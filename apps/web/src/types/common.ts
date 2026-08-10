/**
 * Shared TDMS types.
 *
 * Field and status names follow the SRS (Version 1.1). Where the SRS records an
 * unresolved decision (Section 12), the type carries the placeholder only - no
 * business rule is implied here.
 */

/** ISO date, `YYYY-MM-DD`. */
export type IsoDate = string;

/** ISO date and time, `YYYY-MM-DDTHH:mm:ss.sssZ`. */
export type IsoDateTime = string;

/**
 * Approved delete/restore/override reasons.
 * SRS 4.6 lists these as *proposed* examples. OD-06 keeps the final list open,
 * so the values live in one place and are labelled as proposed in the UI.
 */
export type ReasonCode =
  | 'INCORRECT_OR_DUPLICATE_RECORD'
  | 'STUDENT_WITHDRAWAL_CANCELLATION_OR_CORRECTION'
  | 'TIMETABLE_CORRECTION'
  | 'APPROVED_CLASH_OR_SCHEDULING_OVERRIDE'
  | 'DATA_IMPORTED_IN_ERROR'
  | 'OTHER';

export interface ReasonOption {
  value: ReasonCode;
  label: string;
  /** Reasons are offered only where they make sense for the record type. */
  appliesTo: Array<'student' | 'timetable' | 'trainer' | 'course' | 'qualificationUnit' | 'restore' | 'override'>;
}

/** SRS 2.3 / DATA-04: soft deletion metadata retained on every deleted record. */
export interface SoftDeleteMetadata {
  deletedAt: IsoDateTime;
  deletedBy: string;
  deleteReason: ReasonCode;
  deleteReasonDetail?: string;
  /** SRS 2.3 proposes a 14-day recycle period. */
  recoveryDeadline: IsoDate;
}

export interface SoftDeletable {
  isDeleted: boolean;
  deletion?: SoftDeleteMetadata;
}

export type ValidationSeverity = 'blocking' | 'advisory' | 'pending-approval';

/**
 * One validation outcome shown in a ValidationPanel.
 * `pending-approval` marks a check whose rule is still an SRS open decision:
 * it is displayed but never invents a result.
 */
export interface ValidationIssue {
  id: string;
  severity: ValidationSeverity;
  /** Plain-language title, e.g. "Trainer clash". */
  title: string;
  /** Plain-language explanation of the problem and the required correction. */
  message: string;
  /** Affected field, row number or record reference (SRS 2.3). */
  reference?: string;
  /** Related SRS open decision, e.g. `OD-07`. */
  openDecisionId?: string;
}

export interface ValidationResult {
  issues: ValidationIssue[];
  /** True when no blocking issue remains, so Save may be offered. */
  canSave: boolean;
  checkedAt: IsoDateTime;
}

export interface FieldChange {
  field: string;
  label: string;
  oldValue: string;
  newValue: string;
}

export interface SelectOption {
  value: string;
  label: string;
  description?: string;
  disabled?: boolean;
}

export type ExportFormat = 'csv' | 'xlsx';

export interface ExportResult {
  format: ExportFormat;
  fileName: string;
  rowCount: number;
  /** `generated` = a real file was produced. `demo-fallback` = see `notice`. */
  status: 'generated' | 'demo-fallback';
  notice?: string;
}
