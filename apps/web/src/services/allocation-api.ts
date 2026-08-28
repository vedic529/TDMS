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
  can_edit: boolean;
  can_raise_suggestion: boolean;
  can_except: boolean;
  edit_fields?: Array<{ column: string; value: string }>;
}

export interface AllocationImportOverrides {
  corrections: Array<{ row_number: number; column: string; value: string }>;
  except_ids: string[];
  raise_ids: string[];
  no_raise_ids: string[];
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
  classroom: string;
  trainer: string;
  delivery_mode: string;
  virtual_kind: string | null;
  intakes: string[];
  intake_match_status: string;
  needs_allocation: boolean;
  not_found: boolean;
}

export interface AllocationCalendarDay {
  date: string;
  weekday: string;
  sessions: AllocationCalendarSession[];
  expected_units: Array<{ unit_code: string; intake_label: string; scheduled: boolean }>;
  student_count: number | null;
}

export interface AllocationCalendar {
  training_package: string;
  start_date: string;
  end_date: string;
  days: AllocationCalendarDay[];
  query_cost: number;
  empty: boolean;
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
    data.set('overrides', JSON.stringify(overrides ?? { corrections: [], except_ids: [], raise_ids: [], no_raise_ids: [] }));
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
    data.set('overrides', JSON.stringify(overrides ?? { corrections: [], except_ids: [], raise_ids: [], no_raise_ids: [] }));
    return request<{ deliveries_written: number; sessions_written: number }>('/allocation/import/apply', {
      method: 'POST',
      body: data,
    });
  },
  updateSession: (
    sessionId: number,
    trainingPackage: string,
    payload: { weekday: string; start_time: string; end_time: string; classroom?: string; trainer?: string },
  ) =>
    request(`/allocation/sessions/${sessionId}?training_package=${encodeURIComponent(trainingPackage)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  download: async (trainingPackage: string, startDate: string, endDate: string) => {
    const token = await getAuthProvider().getApiAccessToken();
    const headers = new Headers();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const response = await fetch(
      `${env.apiUrl}/allocation/export?training_package=${encodeURIComponent(trainingPackage)}&start_date=${startDate}&end_date=${endDate}`,
      { headers },
    );
    if (!response.ok) throw new ReferenceApiError(response.status, 'The workbook could not be downloaded.');
    return response.blob();
  },
};

export const ALLOCATION_EMPTY_TITLE = 'No allocation records have been imported yet.';
export const ALLOCATION_EMPTY_DESCRIPTION =
  'Choose a training package and import the approved workbook. The calendar stays empty until that import is confirmed.';
