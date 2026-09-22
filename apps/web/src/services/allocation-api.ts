import { env } from '@/lib/env';
import { getAuthProvider } from './auth';
import { ReferenceApiError } from './reference-api';

export interface AllocationPackage {
  training_package: string;
  enabled: boolean;
  has_profile: boolean;
}

export interface AllocationDiscrepancy {
  kind: string;
  severity: string;
  row_number: number | null;
  column: string | null;
  value: string | null;
  message: string;
  issue_id: string;
  /**
   * What the issue offers, decided by its kind: SUGGESTION is raised, EXCEPTION
   * is accepted for this import, UNSTORABLE is edited or its row excluded, and
   * EXCLUDED is a row the reviewer took out.
   */
  category: 'SUGGESTION' | 'EXCEPTION' | 'UNSTORABLE' | 'EXCLUDED';
  can_edit: boolean;
  can_raise_suggestion: boolean;
  can_except: boolean;
  can_exclude: boolean;
  edit_fields?: Array<{ column: string; value: string }>;
}

export interface AllocationImportOverrides {
  corrections: Array<{ row_number: number; column: string; value: string }>;
  except_ids: string[];
  raise_ids: string[];
  no_raise_ids: string[];
  /** Source rows taken out of the import. */
  exclude_rows: number[];
}

export interface AllocationImportReview {
  status: string;
  training_package: string;
  file_name: string;
  rows_read: number;
  deliveries_that_would_be_written: number;
  sessions_that_would_be_written: number;
  qualifications: string[];
  units: string[];
  intakes_matched: number;
  intakes_not_matched: number;
  suggestions_that_would_be_raised: number;
  discrepancies: AllocationDiscrepancy[];
  discrepancies_by_kind: Record<string, AllocationDiscrepancy[]>;
  refused: boolean;
  can_apply: boolean;
  raise_suggestions?: boolean;
  existing_deliveries?: number;
  exceptions_accepted?: number;
  rows_excluded?: number;
}

/** One unit's class day inside a merged MSCRIS entry. */
export interface AllocationCoveredClass {
  session_id: number;
  delivery_id: number;
  unit_code: string;
  unit_title: string;
  qualification_code: string;
  college: string;
  campus: string;
  intakes: string[];
  student_count: number;
}

export interface AllocationCalendarSession {
  session_id: number;
  delivery_id: number;
  stream: string;
  weekday: string;
  start_time: string;
  end_time: string;
  unit_code: string;
  unit_title: string;
  qualification_code: string;
  college: string;
  campus: string;
  duration_weeks: number | null;
  /** The delivery's dates: one stored row is one unit's delivery. */
  unit_start_date: string;
  unit_end_date: string;
  classroom: string;
  trainer: string;
  delivery_mode: string;
  virtual_kind: string | null;
  intakes: string[];
  intake_match_status: string;
  needs_allocation: boolean;
  not_found: boolean;
  /** Active students whose college, campus, qualification and intake are this class's. */
  student_count: number;
  /** Every stored class day this entry stands for. One, or each class day of a merged MSCRIS entry. */
  session_ids: number[];
  /**
   * The units a merged MSCRIS entry covers (approved 17 September 2026): MSCRIS
   * class days with the same time, classroom and trainer are one class. Empty for
   * any other entry.
   */
  covered: AllocationCoveredClass[];
}

export interface AllocationCalendarDay {
  date: string;
  weekday: string;
  sessions: AllocationCalendarSession[];
  /** Unique units with a Theory or Practical class this day. MSCRIS is not counted. */
  allocated_unit_count: number;
  /** Units the rolling timetable schedules this week that no class teaches yet. The same on every day of the week. */
  expected_unit_count: number;
  expected_units: Array<{ unit_code: string; qualification_codes: string[]; intake_labels: string[] }>;
}

export interface AllocationCalendar {
  training_package: string;
  start_date: string;
  end_date: string;
  days: AllocationCalendarDay[];
  query_cost: number;
  empty: boolean;
}

export interface AllocationSpreadsheetSession {
  session_id: number;
  stream: 'THEORY' | 'PRACTICAL';
  weekday: string;
  start_time: string;
  end_time: string;
  delivery_mode: 'PHYSICAL' | 'VIRTUAL';
  facility_id: number | null;
  classroom: string;
  classroom_capacity: number | null;
  trainer: string;
  trainer_id: number | null;
}

export interface AllocationSpreadsheetRow {
  sl_no: number;
  delivery_id: number;
  college: string;
  campus: string;
  qualification_code: string;
  qualification_title: string;
  duration_weeks: number;
  group: string;
  intakes: string[];
  total_students: number;
  coe_students: number;
  non_coe_students: number;
  unit_code: string;
  unit_title: string;
  unit_start_date: string;
  unit_end_date: string;
  uoc_type: string;
  mode_of_delivery: string;
  sessions: AllocationSpreadsheetSession[];
}

export interface AllocationSpreadsheetList {
  items: AllocationSpreadsheetRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface AllocationSpreadsheetChoices {
  classrooms: Array<{ id: number | null; name: string; capacity: number | null }>;
  trainers: Array<{ id: number; name: string }>;
}


/** What clearing the allocation records removed, or would remove. */
export interface ClearAllocationCounts {
  deliveries: number;
  sessions: number;
  intake_links: number;
  import_batches: number;
  source_rows: number;
  suggestions: number;
  exceptions: number;
  resolved_suggestions: number;
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
      /* ignore */
    }
    throw new ReferenceApiError(response.status, detail || 'The request could not be completed.');
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// The reference-suggestion queue lives in `suggestions-api.ts`: it is shared by
// every importer and every reference-data tab, not an allocation concern.
export const allocationApi = {
  listPackages: () => request<AllocationPackage[]>('/allocation/packages'),

  /** Super Admin only. Counts what a clear would remove, deleting nothing. */
  clearPreview: () => request<ClearAllocationCounts>('/allocation/records/clear-preview'),

  /**
   * Super Admin only. Deletes every allocation record and the suggestions the
   * allocation import raised. The rolling timetable and student records are
   * deliberately untouched.
   */
  clearRecords: () => request<ClearAllocationCounts>('/allocation/records', { method: 'DELETE' }),
  calendar: (trainingPackage: string, startDate: string, endDate: string) =>
    request<AllocationCalendar>(
      `/allocation/calendar?training_package=${encodeURIComponent(trainingPackage)}&start_date=${startDate}&end_date=${endDate}`,
    ),
  spreadsheet: (trainingPackage: string, startDate: string, endDate: string, limit: number, offset: number) =>
    request<AllocationSpreadsheetList>(
      `/allocation/spreadsheet?${new URLSearchParams({
        training_package: trainingPackage,
        start_date: startDate,
        ...(endDate ? { end_date: endDate } : {}),
        limit: String(limit),
        offset: String(offset),
      }).toString()}`,
    ),
  spreadsheetChoices: (
    deliveryId: number,
    trainingPackage: string,
    values: { stream: string; weekday: string; start_time: string; end_time: string; delivery_mode: string },
  ) => {
    const params = new URLSearchParams({ training_package: trainingPackage, ...values });
    return request<AllocationSpreadsheetChoices>(`/allocation/spreadsheet/${deliveryId}/choices?${params}`);
  },
  validateImport: (
    trainingPackage: string,
    file: File,
    raiseSuggestions: boolean,
    overrides?: AllocationImportOverrides,
  ) => {
    const data = new FormData();
    data.set('training_package', trainingPackage);
    data.set('file', file);
    data.set('raise_suggestions', raiseSuggestions ? 'true' : 'false');
    data.set('overrides', JSON.stringify(overrides ?? { corrections: [], except_ids: [], raise_ids: [], no_raise_ids: [], exclude_rows: [] }));
    return request<AllocationImportReview>('/allocation/import/validate', { method: 'POST', body: data });
  },
  applyImport: (
    trainingPackage: string,
    file: File,
    applyMode: 'REPLACE' | 'MERGE',
    raiseSuggestions: boolean,
    overrides?: AllocationImportOverrides,
  ) => {
    const data = new FormData();
    data.set('training_package', trainingPackage);
    data.set('file', file);
    data.set('apply_mode', applyMode);
    data.set('raise_suggestions', raiseSuggestions ? 'true' : 'false');
    data.set('overrides', JSON.stringify(overrides ?? { corrections: [], except_ids: [], raise_ids: [], no_raise_ids: [], exclude_rows: [] }));
    return request<{ deliveries_written: number; sessions_written: number }>('/allocation/import/apply', {
      method: 'POST',
      body: data,
    });
  },
  updateSession: (
    sessionId: number,
    trainingPackage: string,
    payload: { weekday: string; start_time: string; end_time: string; classroom?: string; trainer?: string; facility_id?: number; trainer_id?: number },
  ) =>
    request(`/allocation/sessions/${sessionId}?training_package=${encodeURIComponent(trainingPackage)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  addSession: (
    trainingPackage: string,
    payload: {
      delivery_id: number;
      stream: string;
      weekday: string;
      start_time: string;
      end_time: string;
      classroom?: string;
      trainer?: string;
    },
  ) =>
    request(`/allocation/sessions?training_package=${encodeURIComponent(trainingPackage)}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteSession: (sessionId: number, trainingPackage: string) =>
    request<void>(`/allocation/sessions/${sessionId}?training_package=${encodeURIComponent(trainingPackage)}`, {
      method: 'DELETE',
    }),
  /** Edit a merged MSCRIS entry: every class day it covers changes together. */
  updateMscrisGroup: (
    trainingPackage: string,
    payload: { session_ids: number[]; start_time: string; end_time: string; classroom?: string; trainer?: string },
  ) =>
    request<{ updated: number }>(
      `/allocation/mscris-groups?training_package=${encodeURIComponent(trainingPackage)}`,
      { method: 'PATCH', body: JSON.stringify(payload) },
    ),
  /**
   * The allocation records as the spreadsheet view shows them: same columns,
   * same order, same wording (21 September 2026). Returns the file and the name
   * the API chose, so the download is named the same way everywhere.
   */
  download: async (
    trainingPackage: string,
    startDate: string,
    endDate: string,
    fileFormat: 'xlsx' | 'csv' = 'xlsx',
  ): Promise<{ blob: Blob; fileName: string }> => {
    const token = await getAuthProvider().getApiAccessToken();
    const headers = new Headers();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const params = new URLSearchParams({
      training_package: trainingPackage,
      start_date: startDate,
      format: fileFormat,
    });
    if (endDate) params.set('end_date', endDate);
    const response = await fetch(`${env.apiUrl}/allocation/export?${params.toString()}`, { headers });
    if (!response.ok) throw new ReferenceApiError(response.status, 'The file could not be downloaded.');
    const disposition = response.headers.get('Content-Disposition') ?? '';
    const named = /filename="?([^";]+)"?/.exec(disposition);
    return {
      blob: await response.blob(),
      fileName: named?.[1] ?? `allocation-records-${trainingPackage}.${fileFormat}`,
    };
  },
};

export const ALLOCATION_EMPTY_TITLE = 'No allocation records have been imported yet.';
export const ALLOCATION_EMPTY_DESCRIPTION =
  'Choose a training package and import the approved workbook. The calendar stays empty until that import is confirmed.';
