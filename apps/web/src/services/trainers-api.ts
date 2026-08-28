/**
 * Trainer Data — the real API client.
 *
 * Follows `students-api.ts`: a direct fetch client carrying the bearer token,
 * deliberately **not** routed through `TdmsClient`. Trainer records live in
 * PostgreSQL, so there is no mock implementation and no browser storage.
 *
 * The file upload is sent as multipart form data and parsed by the API. That is
 * what makes XLSX work — the browser cannot open a workbook — and it is also
 * what lets the API pick the right **sheet** for the chosen data type, since the
 * supplied workbook holds Trainer Location and Trainer Units side by side.
 */

import { env } from '@/lib/env';
import { getAuthProvider } from './auth';
import { ReferenceApiError } from './reference-api';

// ---------------------------------------------------------------------------
// Wire types (snake_case, matching app/schemas/trainer.py)
// ---------------------------------------------------------------------------

/** One row of the list — one row per trainer, however many locations they hold. */
export interface TrainerRow {
  id: number;
  trainer_id: string;
  trainer_name: string;
  /** The city the trainer is based in — the file's `Trainer Campus`. */
  city: string | null;
  is_active: boolean;
  location_count: number;
  location_summary: string;
  qualification_count: number;
  unit_count: number;
  /** Derived from the qualification codes the trainer teaches. Never stored. */
  training_packages: string[];
}

export interface TrainerList {
  items: TrainerRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface TrainerLocation {
  id: number;
  campus_id: number | null;
  campus_name: string | null;
  /** Set only when the campus could not be resolved, so it can be marked. */
  location_text: string | null;
  is_offshore: boolean;
  location: string | null;
  location_type: string | null;
  class_type: string;
  working_time_start: string;
  working_time_end: string;
  working_time_text: string | null;
  monday: string;
  tuesday: string;
  wednesday: string;
  thursday: string;
  friday: string;
}

export interface TrainerUnitLink {
  id: number;
  /** None until the unit exists in the reference data. */
  unit_id: number | null;
  unit_code: string;
  unit_title: string;
  unresolved: boolean;
}

export interface TrainerQualificationGroup {
  qualification_id: number | null;
  qualification_unresolved: boolean;
  qualification_code: string | null;
  qualification_title: string;
  units: TrainerUnitLink[];
}

/** The whole side panel, in one response. Expanding a tray costs no request. */
export interface TrainerDetail {
  id: number;
  trainer_id: string;
  trainer_name: string;
  city: string | null;
  is_active: boolean;
  training_packages: string[];
  locations: TrainerLocation[];
  qualifications: TrainerQualificationGroup[];
}

export interface UnitCoverageRow {
  unit_id: number;
  unit_code: string;
  unit_title: string;
  qualification_id: number | null;
  qualification_code: string | null;
  qualification_title: string | null;
  trainer_count: number;
  trainer_names: string[];
  has_more_trainers: boolean;
}

export interface UnitCoverageList {
  items: UnitCoverageRow[];
  total: number;
}

export interface LocationWrite {
  campus_id?: number | null;
  is_offshore?: boolean;
  location?: string | null;
  location_type?: string | null;
  class_type: string;
  working_time_start: string;
  working_time_end: string;
  working_time_text?: string | null;
  monday?: string;
  tuesday?: string;
  wednesday?: string;
  thursday?: string;
  friday?: string;
}

// -- Bulk import ------------------------------------------------------------

/** Which kind of data is being uploaded. Never a training package (1.7). */
export type TrainerImportDataType = 'LOCATION' | 'UNITS';

export const IMPORT_DATA_TYPES: { value: TrainerImportDataType; label: string }[] = [
  { value: 'LOCATION', label: 'Trainer Location and Details' },
  { value: 'UNITS', label: 'Trainer Units' },
];

export interface ImportRowIssue {
  severity: string;
  code: string;
  column_name: string | null;
  message: string;
}

export interface ImportStagedRow {
  id: number;
  row_number: number;
  status: string;
  values: Record<string, string>;
  issues: ImportRowIssue[];
}

/** A trainer id in the file that is not in the trainer database (1.9). */
export interface MissingTrainerGroup {
  trainer_id: string;
  row_count: number;
}

/**
 * A value in the file that matches no approved record.
 *
 * Detected at staging but **not** raised: whether it becomes a suggestion is
 * the user's decision. There is no exception path — a qualification or a unit
 * either exists in the reference data or it does not, so the only resolutions
 * offered afterwards are Create Record and Map Record.
 */
export interface UnresolvedValue {
  key: string;
  entity_type: 'CAMPUS' | 'QUALIFICATION' | 'UNIT';
  raw_value: string;
  context: Record<string, string>;
  row_count: number;
  /** True once a queue entry exists, whichever import first raised it. */
  in_queue: boolean;
  queue_status: string | null;
  /** True once this batch was told to raise it — what lets its rows import. */
  raised_here: boolean;
}

/** One field a re-import would change on a location already stored. */
export interface OverrideChange {
  field: string;
  label: string;
  stored_value: string;
  incoming_value: string;
}

/**
 * A row that would overwrite something, waiting for a decision.
 *
 * Adding is silent; overwriting is not. Confirm stays shut until every one
 * says whether to keep the stored value or take the file's.
 */
export interface OverrideRow {
  row_id: number;
  row_number: number;
  trainer_id: string;
  location: string;
  decision: 'KEEP_STORED' | 'TAKE_FROM_FILE' | null;
  changes: OverrideChange[];
}

export interface ImportReview {
  batch_id: number;
  data_type: TrainerImportDataType;
  file_name: string;
  rows_read: number;
  rows_valid: number;
  rows_with_errors: number;
  rows_excluded: number;
  can_apply: boolean;
  rows: ImportStagedRow[];
  missing_trainers: MissingTrainerGroup[];
  /** Every unmatched value, offered for a decision rather than raised silently. */
  unresolved_values: UnresolvedValue[];
  /** Rows that would change something already stored. */
  overrides: OverrideRow[];
  suggestions_raised: number;
  blocking_message: string | null;
}

export interface ImportApplyResult {
  batch_id: number;
  data_type: TrainerImportDataType;
  apply_mode: string;
  trainers_written: number;
  locations_written: number;
  unit_links_written: number;
  qualification_links_written: number;
  /** Links stored against a value the reference data does not hold yet. */
  unit_links_unresolved: number;
  /** Stored locations replaced with the file's version, on request. */
  locations_overwritten: number;
  rows_excluded: number;
}

/** What clearing the trainer database removes, or removed. */
export interface ClearTrainersCounts {
  trainers: number;
  locations: number;
  unit_links: number;
  qualification_links: number;
  /** Sessions that keep their trainer's name and read as unresolved after. */
  allocation_sessions_unlinked: number;
  /** Suggestions raised so those names are not quietly forgotten. */
  trainer_suggestions_raised: number;
}

// -- The Location Dictionary (2.4) ------------------------------------------

export interface LocationCampus {
  id: number;
  campus_code: string;
  campus_name: string;
  campus_location: string;
  approved_address: string | null;
  is_active: boolean;
  source_addresses: string[];
}

export interface LocationCity {
  /** `null` when no city is recorded — rendered "City not recorded", never guessed. */
  city: string | null;
  campuses: LocationCampus[];
}

export interface LocationState {
  state: string;
  cities: LocationCity[];
}

// ---------------------------------------------------------------------------

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

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

export const trainersApi = {
  list: (
    params: {
      search?: string;
      campus_id?: number;
      qualification_id?: number;
      unit_id?: number;
      is_active?: boolean;
      limit?: number;
      offset?: number;
    } = {},
  ) => request<TrainerList>(`/trainers${query(params)}`),

  /** Everything the side panel shows, in one round trip. */
  get: (id: number) => request<TrainerDetail>(`/trainers/${id}`),

  /**
   * The id this trainer would be given, previewed while the name is typed.
   * Nothing is reserved — it is generated again when the record is created.
   */
  nextId: (name: string) =>
    request<{ trainer_id: string; sequence: number; initials: string }>(
      `/trainers/next-id${query({ name })}`,
    ),

  /** No `trainer_id`: it is generated. The city is required. */
  create: (payload: {
    trainer_name: string;
    city: string;
    is_active?: boolean;
    /** Both optional and both repeatable. */
    locations?: LocationWrite[];
    units?: { qualification_id: number; unit_ids: number[] }[];
  }) =>
    request<TrainerDetail>('/trainers', { method: 'POST', body: JSON.stringify(payload) }),

  update: (id: number, payload: { trainer_name?: string; city?: string; is_active?: boolean }) =>
    request<TrainerDetail>(`/trainers/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

  /** Soft delete (DATA-04): a reason is required and recorded. */
  remove: (id: number, reasonCodeId: number, reasonNote?: string) =>
    request<void>(`/trainers/${id}`, {
      method: 'DELETE',
      body: JSON.stringify({ reason_code_id: reasonCodeId, reason_note: reasonNote ?? null }),
    }),

  restore: (id: number) => request<TrainerDetail>(`/trainers/${id}/restore`, { method: 'POST' }),

  addLocation: (id: number, payload: LocationWrite) =>
    request<TrainerDetail>(`/trainers/${id}/locations`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateLocation: (id: number, availabilityId: number, payload: Partial<LocationWrite>) =>
    request<TrainerDetail>(`/trainers/${id}/locations/${availabilityId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  removeLocation: (id: number, availabilityId: number) =>
    request<TrainerDetail>(`/trainers/${id}/locations/${availabilityId}`, { method: 'DELETE' }),

  /** One qualification and many units, in one call (1.6). */
  addUnits: (id: number, qualificationId: number, unitIds: number[]) =>
    request<TrainerDetail>(`/trainers/${id}/units`, {
      method: 'POST',
      body: JSON.stringify({ qualification_id: qualificationId, unit_ids: unitIds }),
    }),

  removeUnitLink: (id: number, linkId: number) =>
    request<TrainerDetail>(`/trainers/${id}/units/${linkId}`, { method: 'DELETE' }),

  unitCoverage: (
    params: { qualification_id?: number; only_uncovered?: boolean; limit?: number; offset?: number } = {},
  ) => request<UnitCoverageList>(`/trainers/unit-coverage${query(params)}`),

  /**
   * Upload a CSV or XLSX file into the staging area.
   *
   * `data_type` selects the column map **and** the worksheet, which is why the
   * two-sheet supplied workbook can be uploaded as-is for either shape.
   */
  stageImport: (dataType: TrainerImportDataType, file: File) => {
    const body = new FormData();
    body.set('data_type', dataType);
    body.set('file', file);
    return request<ImportReview>('/trainers/import/stage', { method: 'POST', body });
  },

  readImport: (batchId: number) => request<ImportReview>(`/trainers/import/${batchId}`),

  patchImportRows: (
    batchId: number,
    payload: {
      corrections?: Record<number, Record<string, string>>;
      excluded_row_ids?: number[];
      exclude_missing_trainers?: boolean;
      override_decisions?: Record<number, 'KEEP_STORED' | 'TAKE_FROM_FILE'>;
    },
  ) =>
    request<ImportReview>(`/trainers/import/${batchId}/rows`, {
      method: 'PATCH',
      body: JSON.stringify({
        corrections: payload.corrections ?? {},
        excluded_row_ids: payload.excluded_row_ids ?? [],
        exclude_missing_trainers: payload.exclude_missing_trainers ?? false,
        override_decisions: payload.override_decisions ?? {},
      }),
    }),

  /** Raise a suggestion for the chosen unmatched values, or for all of them. */
  raiseSuggestions: (batchId: number, payload: { keys?: string[]; all?: boolean }) =>
    request<ImportReview>(`/trainers/import/${batchId}/suggestions`, {
      method: 'POST',
      body: JSON.stringify({ keys: payload.keys ?? [], all: payload.all ?? false }),
    }),

  applyImport: (batchId: number, applyMode: 'MERGE' | 'REPLACE') =>
    request<ImportApplyResult>(
      `/trainers/import/${batchId}/apply${query({ apply_mode: applyMode })}`,
      { method: 'POST' },
    ),

  abandonImport: (batchId: number) =>
    request<void>(`/trainers/import/${batchId}`, { method: 'DELETE' }),

  /** What clearing the trainer database would remove. Super Admin only. */
  clearPreview: () => request<ClearTrainersCounts>('/trainers/records/clear-preview'),

  /** Delete every trainer record. Irreversible. */
  clearRecords: () =>
    request<ClearTrainersCounts>('/trainers/records', { method: 'DELETE' }),

  /** State -> City -> Campus -> Address. Lives on the reference router. */
  locationDictionary: () => request<LocationState[]>('/reference/locations'),
};
