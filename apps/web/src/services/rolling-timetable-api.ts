import { env } from '@/lib/env';
import { getAuthProvider } from './auth';
import { ReferenceApiError } from './reference-api';

export const TRAINING_PACKAGES = [
  'CHC',
  'BSB',
  'FNS',
  'SIT',
  'AUR',
  'CPC',
  'ICT',
  'RII',
  'TLI',
  'UEE',
  'AHC',
] as const;

export type TrainingPackage = (typeof TRAINING_PACKAGES)[number];

export interface RollingWeek {
  id: number;
  training_package: string;
  qualification_code: string;
  duration_weeks: number;
  intake_label: string;
  intake_group: string;
  intake_start_date: string;
  week_no: number;
  week_start_date: string;
  week_end_date: string;
  schedule_type: 'UNIT' | 'BREAK' | 'ASSESSMENT_WEEK';
  schedule_value: string;
  unit_code: string | null;
  unit_count: number;
  unit_delivery_span_weeks: number | null;
  unit_slot: number;
}

export interface RollingWeekList {
  items: RollingWeek[];
  total: number;
  limit: number;
  offset: number;
}

export interface RollingWeekPatchItem {
  id: number;
  schedule_type: RollingWeek['schedule_type'];
  schedule_value: string;
}

export interface RollingScope {
  training_package: string;
  qualification_code: string;
  duration_weeks: number;
  intake_count: number;
  row_count: number;
}

export interface RollingFacets {
  intake_labels: string[];
  unit_codes: string[];
}

export interface VisualizerGrid {
  training_package: string;
  qualification_code: string;
  duration_weeks: number;
  weeks: Array<{ week_no: number; week_start_date: string; week_end_date: string }>;
  intake_columns: Array<{ intake_label: string; unit_slot: number; heading: string }>;
  grid: string[][];
  counts: { unit: number; break_count: number; assessment_week: number };
}

export interface ImportDiscrepancy {
  kind: string;
  severity: string;
  row_number: number | null;
  column: string | null;
  value: string | null;
  message: string;
}

export interface QualificationImportSummary {
  qualification_code: string;
  duration_weeks: number;
  training_package: string;
  row_count: number;
  intake_count: number;
}

export interface ImportReview {
  status: string;
  training_package: string;
  file_name: string;
  rows_read: number;
  rows_that_would_be_written: number;
  qualifications: QualificationImportSummary[];
  matching_qualifications: QualificationImportSummary[];
  non_matching_qualifications: QualificationImportSummary[];
  counts: { unit: number; break_count: number; assessment_week: number };
  discrepancies: ImportDiscrepancy[];
  discrepancies_by_kind: Record<string, ImportDiscrepancy[]>;
  existing_qualifications_replaced: string[];
  refused: boolean;
  can_proceed_with_package: boolean;
}

export interface ImportApplyResult {
  rows_written: number;
  qualifications_replaced: string[];
  qualifications_skipped: string[];
  rows_read: number;
}

type QueryValue = string | number | boolean | undefined;

function query(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '' || value === false) continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has('Content-Type') && !(init?.body instanceof FormData)) {
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
      /* no JSON */
    }
    throw new ReferenceApiError(response.status, detail || 'The request could not be completed.');
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function packImport(trainingPackage: string, file: File, proceedWithMatching?: boolean): FormData {
  const data = new FormData();
  data.set('training_package', trainingPackage);
  data.set('file', file);
  if (proceedWithMatching !== undefined) data.set('proceed_with_matching', proceedWithMatching ? 'true' : 'false');
  return data;
}

export const rollingTimetableApi = {
  listScopes: () => request<RollingScope[]>('/rolling-timetable/scopes'),
  listFacets: (trainingPackage: string, qualificationCode: string, durationWeeks: number) =>
    request<RollingFacets>(
      `/rolling-timetable/facets${query({
        training_package: trainingPackage,
        qualification_code: qualificationCode,
        duration_weeks: durationWeeks,
      })}`,
    ),
  listWeeks: (
    params: {
      trainingPackage?: string;
      qualificationCode?: string;
      durationWeeks?: number;
      intakeLabel?: string;
      weekNo?: number;
      scheduleType?: string;
      unitCode?: string;
      weekStartFrom?: string;
      weekStartTo?: string;
      search?: string;
      limit?: number;
      offset?: number;
      sort?: string;
      direction?: string;
    } = {},
  ) =>
    request<RollingWeekList>(
      `/rolling-timetable/weeks${query({
        training_package: params.trainingPackage,
        qualification_code: params.qualificationCode,
        duration_weeks: params.durationWeeks,
        intake_label: params.intakeLabel,
        week_no: params.weekNo,
        schedule_type: params.scheduleType,
        unit_code: params.unitCode,
        week_start_from: params.weekStartFrom,
        week_start_to: params.weekStartTo,
        search: params.search,
        limit: params.limit,
        offset: params.offset,
        sort: params.sort,
        direction: params.direction,
      })}`,
    ),
  visualizer: (trainingPackage: string, qualificationCode: string, durationWeeks: number) =>
    request<VisualizerGrid>(
      `/rolling-timetable/visualizer${query({
        training_package: trainingPackage,
        qualification_code: qualificationCode,
        duration_weeks: durationWeeks,
      })}`,
    ),
  updateWeeks: (items: RollingWeekPatchItem[]) =>
    request<{ items: RollingWeek[] }>('/rolling-timetable/weeks', {
      method: 'PATCH',
      body: JSON.stringify({ items }),
    }),
  validateImport: (trainingPackage: string, file: File) =>
    request<ImportReview>('/rolling-timetable/import/validate', {
      method: 'POST',
      body: packImport(trainingPackage, file),
    }),
  applyImport: (trainingPackage: string, file: File, proceedWithMatching: boolean) =>
    request<ImportApplyResult>('/rolling-timetable/import/apply', {
      method: 'POST',
      body: packImport(trainingPackage, file, proceedWithMatching),
    }),
};

export const ROLLING_EMPTY_MESSAGE = 'No rolling timetable has been imported yet.';
export const ROLLING_EMPTY_DESCRIPTION =
  'Use Import Data to load the approved flat file. Nothing is shown here until that import is confirmed.';
