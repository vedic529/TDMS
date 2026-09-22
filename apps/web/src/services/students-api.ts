/**
 * Student Data — the real API client.
 *
 * Follows `allocation-api.ts` and `rolling-timetable-api.ts`: a direct fetch
 * client carrying the bearer token, deliberately **not** routed through
 * `TdmsClient`. Student records live in PostgreSQL, so there is no mock
 * implementation and no browser storage.
 *
 * The file upload is sent to the API as multipart form data and parsed there.
 * That is what makes XLSX work: the browser cannot open a workbook, and the API
 * reads both CSV and XLSX with the same code path.
 */

import { env } from '@/lib/env';
import { getAuthProvider } from './auth';
import { ReferenceApiError } from './reference-api';

// ---------------------------------------------------------------------------
// Wire types (snake_case, matching app/schemas/student.py)
// ---------------------------------------------------------------------------

export interface StudentRecord {
  id: number;
  student_id: string;
  first_name: string;
  last_name: string | null;
  college_email: string;
  coe_status: string;
  ct_student: boolean;
  status: string;
  intake_match_status: string;
  proposed_start_date: string;
  proposed_end_date: string;
  actual_course_duration_weeks: number;
  personal_email: string | null;
  primary_phone: string | null;
  remarks: string | null;
  /** Null while the student is unverified: a reference was raised as a suggestion. */
  course_offering_id: number | null;
  student_group_id: number | null;
  college: string;
  campus: string;
  state: string | null;
  qualification_code: string;
  qualification_title: string;
  intake_label: string | null;
  group_code: string | null;
  /** The approved Course Duration Option in weeks, when one is set (OD-08). */
  course_duration_option_weeks: number | null;
  /** Stored with a value that matches no approved record (approved 15 September 2026). */
  is_unverified: boolean;
  /** Which of the values that is - shown in red in the side panel. */
  unverified_fields: Array<'college' | 'campus' | 'qualification'>;
  // DATA-04 soft-delete metadata, present on a deleted record.
  is_deleted: boolean;
  deleted_at?: string | null;
  deleted_by?: string | null;
  delete_reason?: string | null;
  delete_reason_detail?: string | null;
  recovery_deadline?: string | null;
}

export interface StudentList {
  items: StudentRecord[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * A single-entry create or edit.
 *
 * Intake and Group are **not** here: both are derived from the rolling
 * timetable by the API (rule 2.5) and are never supplied by the interface.
 */
export interface StudentInput {
  student_id: string;
  first_name: string;
  last_name?: string | null;
  college_id: number;
  campus_id: number;
  /** Either id or code; the interface holds the code on the approved offering. */
  qualification_id?: number | null;
  qualification_code?: string | null;
  coe_status: 'COE' | 'NON_COE';
  ct_student: boolean;
  proposed_start_date: string;
  proposed_end_date: string;
  personal_email?: string | null;
  primary_phone?: string | null;
  status: string;
  college_email?: string | null;
  remarks?: string | null;
  /** Staff-selected approved Course Duration Option, in weeks (OD-08). */
  course_duration_option_weeks?: number | null;
}

export interface RowIssue {
  field_name: string;
  message: string;
  /** REFUSE_ROW | BLOCK | BLOCK_DUP | EXCEPTION | ACCEPTED | NOTE */
  issue_status: string;
}

export interface StagedRow {
  id: number;
  source_row_number: number;
  status: string;

  student_id_value: string | null;
  first_name_value: string | null;
  last_name_value: string | null;
  college_value: string | null;
  campus_value: string | null;
  qualification_value: string | null;
  coe_status_value: string | null;
  ct_student_value: string | null;
  status_value: string | null;
  proposed_start_date_value: string | null;
  proposed_end_date_value: string | null;
  personal_email_value: string | null;
  primary_phone_value: string | null;

  resolved_college_id: number | null;
  resolved_campus_id: number | null;
  resolved_qualification_id: number | null;
  resolved_offering_id: number | null;

  /** Derived by the system from the rolling timetable — never typed by a user. */
  derived_intake_label: string | null;
  derived_group_code: string | null;
  intake_match_status: string | null;
  /** An approved Course Duration Option chosen to resolve a TBD intake (OD-08). */
  duration_override_weeks: number | null;

  duplicate_scope: string | null;
  existing_student_id: number | null;
  duplicate_decision: string | null;
  existing_status_value: string | null;

  college_choice: string | null;
  campus_choice: string | null;
  qualification_choice: string | null;

  issues: RowIssue[];
}

export interface DuplicateComparisonField {
  field: string;
  stored: string | null;
  incoming: string | null;
  differs: boolean;
}

export interface DuplicateContext {
  staged_row_id: number;
  /** SAME_QUALIFICATION | DIFFERENT_QUALIFICATION */
  scope: string;
  existing_student_id: number;
  existing_status: string;
  existing_qualification_code: string;
  incoming_qualification_code: string;
  fields: DuplicateComparisonField[];
}

export interface ImportReview {
  batch_id: number;
  batch_reference: string;
  file_name: string;
  status: string;
  rows_read: number;
  counts: Record<string, number>;
  can_apply: boolean;
  blocking_reasons: string[];
  rows: StagedRow[];
  duplicates: DuplicateContext[];
  /** Qualification code -> the rolling-timetable durations it actually offers. */
  duration_options: Record<string, number[]>;
}

/** What clearing the student records removed, or would remove. Super Admin only. */
export interface ClearStudentCounts {
  students: number;
  /** Records in the recycle area. They go too: "no deleted record left". */
  deleted_students: number;
  intakes: number;
  import_batches: number;
  staged_rows: number;
  /** Open suggestions left with nothing behind them, closed by the clear. */
  suggestions: number;
}

export interface ImportApplyResult {
  batch_id: number;
  rows_read: number;
  inserted: number;
  updated: number;
  excluded: number;
  duplicates: number;
  unmatched: number;
  suggestions_raised: number;
  /** Saved with a raised reference, completed when its suggestion resolves. */
  unverified?: number;
  intakes_matched: number;
  intakes_tbd: number;
  intakes_not_applicable: number;
  groups_created: number;
}

/** One change to a staged row: a correction, an exclusion, or a decision. */
export interface RowPatch {
  row_id: number;
  corrections?: Array<{ column: string; value: string }>;
  exclude?: boolean;
  /** Accept the row's broken rule for this import (true), or undo that (false). */
  accept_exception?: boolean;
  /** Resolve a TBD intake by choosing an approved duration. 0 clears the choice. */
  duration_weeks?: number;
  duplicate_decision?: 'KEEP_STORED' | 'KEEP_INCOMING';
  status_value?: string;
  existing_status_value?: string;
  reference_entity?: 'college' | 'campus' | 'qualification';
  /** NONE undoes a decision: the row returns to blocking until it is settled again. */
  reference_choice?: 'RAISE' | 'RESOLVE' | 'NONE';
  reference_resolved_id?: number;
}

// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// Show Timetable — derived on every call, never stored
// ---------------------------------------------------------------------------

export interface TimetableClass {
  date: string;
  weekday: string;
  /** "HH:MM". */
  start_time: string;
  end_time: string;
  stream: 'THEORY' | 'PRACTICAL' | 'MSCRIS';
  delivery_mode: 'PHYSICAL' | 'VIRTUAL';
  mode_label: string;
  classroom: string;
  /** True when the value is the file's text rather than an approved record. */
  classroom_unresolved: boolean;
  campus: string;
  campus_unresolved: boolean;
}

export interface TimetableRow {
  row_type: 'UNIT' | 'BREAK' | 'ASSESSMENT_WEEK';
  week_from: string;
  week_to: string;
  /** Where the row sits against the student's own enrolment dates. */
  timing: 'BEFORE_JOINING' | 'DURING' | 'AFTER_END';
  unit_code: string | null;
  unit_title: string | null;
  allocation_status: 'ALLOCATED' | 'UNALLOCATED' | null;
  mode_of_delivery: string | null;
  uoc_type: string | null;
  span_note: string | null;
  expansion_refused: boolean;
  classes: TimetableClass[];
}

export interface StudentTimetable {
  student: { id: number; student_id: string; name: string; status: string; ct_student: boolean };
  qualification: { code: string; title: string | null; duration_weeks: number | null };
  intake: {
    label: string | null;
    group_code: string | null;
    match_status: string;
    start_date: string | null;
  };
  scope: { college: string; campus: string };
  course_dates: { proposed_start_date: string; proposed_end_date: string };
  /** null when the student has a timetable; otherwise which state applies. */
  empty_reason: null | 'UNVERIFIED' | 'CREDIT_TRANSFER' | 'NO_ROLLING_TIMETABLE' | 'NO_ROLLING_ROWS';
  summary: {
    units_total: number;
    units_allocated: number;
    units_unallocated: number;
    classes_total: number;
  };
  rows: TimetableRow[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has('Content-Type') && !(init?.body instanceof FormData) && init?.body) {
    headers.set('Content-Type', 'application/json');
  }
  const token = await getAuthProvider().getApiAccessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${env.apiUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = '';
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* ignore a non-JSON error body */
    }
    throw new ReferenceApiError(response.status, detail || 'The request could not be completed.');
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

export const studentsApi = {
  list: (params: {
    search?: string;
    college_id?: number;
    campus_id?: number;
    qualification_id?: number;
    status?: string;
    coe_status?: string;
    /** Only students with unverified data. */
    unverified?: boolean;
    limit?: number;
    offset?: number;
  } = {}) =>
    request<StudentList>(
      // The query string carries text, so the flag is sent only when it is set.
      `/students${query({ ...params, unverified: params.unverified ? 'true' : undefined })}`,
    ),

  listDeleted: (limit = 50, offset = 0) =>
    request<StudentList>(`/students/deleted${query({ limit, offset })}`),

  get: (id: number) => request<StudentRecord>(`/students/${id}`),

  /**
   * This student's own timetable, drawn from their intake.
   *
   * Fired when the dialog opens, not when the detail panel does: browsing
   * records must not cost a timetable fetch per row.
   */
  getTimetable: (id: number) => request<StudentTimetable>(`/students/${id}/timetable`),

  create: (payload: StudentInput) =>
    request<StudentRecord>('/students', { method: 'POST', body: JSON.stringify(payload) }),

  update: (id: number, payload: StudentInput) =>
    request<StudentRecord>(`/students/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

  /** Soft delete (DATA-04): a reason is required and recorded. */
  remove: (id: number, reasonCode: string, reasonDetail?: string) =>
    request<void>(`/students/${id}`, {
      method: 'DELETE',
      body: JSON.stringify({ reason_code: reasonCode, reason_detail: reasonDetail ?? null }),
    }),

  restore: (id: number) => request<StudentRecord>(`/students/${id}/restore`, { method: 'POST' }),

  /**
   * Upload a CSV or XLSX file into the staging area.
   *
   * Nothing reaches `students` here — the API parses the workbook, resolves the
   * references, derives the Intake and Group, and returns the review to confirm.
   */
  stageImport: (file: File) => {
    const data = new FormData();
    data.set('file', file);
    return request<ImportReview>('/students/import/stage', { method: 'POST', body: data });
  },

  readImport: (batchId: number) => request<ImportReview>(`/students/import/${batchId}`),

  // ------------------------------------------------ clear the student records
  /** What clearing would remove. Super Admin only. */
  clearPreview: () => request<ClearStudentCounts>('/students/records/clear-preview'),
  /** Delete every student record and the import copies. Irreversible. */
  clearRecords: () => request<ClearStudentCounts>('/students/records', { method: 'DELETE' }),

  patchImportRows: (batchId: number, items: RowPatch[]) =>
    request<ImportReview>(`/students/import/${batchId}/rows`, {
      method: 'PATCH',
      body: JSON.stringify({ items }),
    }),

  applyImport: (batchId: number) =>
    request<ImportApplyResult>(`/students/import/${batchId}/apply`, { method: 'POST' }),

  abandonImport: (batchId: number) =>
    request<void>(`/students/import/${batchId}`, { method: 'DELETE' }),
};

/** The staged-row statuses the preview groups by, in the approved order. */
export const STAGED_STATUS_LABELS: Record<string, string> = {
  READY: 'Ready',
  NEEDS_CORRECTION: 'Needs correction',
  DUPLICATE: 'Duplicate',
  UNMATCHED_REFERENCE: 'Unmatched reference',
  EXCLUDED_BY_USER: 'Excluded by user',
};

export function isBlockingStagedStatus(status: string): boolean {
  return status === 'NEEDS_CORRECTION' || status === 'DUPLICATE' || status === 'UNMATCHED_REFERENCE';
}

export const STUDENTS_EMPTY_TITLE = 'No students imported yet.';
export const STUDENTS_EMPTY_DESCRIPTION =
  'Student records live in the TDMS database. Use Bulk Student Import to upload the approved CSV or XLSX file.';
