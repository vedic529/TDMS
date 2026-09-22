/**
 * The shared reference-suggestion queue.
 *
 * Every importer raises into this queue and every reference-data tab reads from
 * it, so it is not an allocation concern and no longer lives in
 * `allocation-api.ts`.
 */

import { env } from '@/lib/env';
import { getAuthProvider } from './auth';
import { ReferenceApiError } from './reference-api';

/**
 * What a suggestion can stand in for. ROLLING is a class the rolling timetable
 * does not account for; CITY is a city the City Dictionary does not hold.
 */
export type SuggestionEntityType =
  | 'COLLEGE'
  | 'CAMPUS'
  | 'QUALIFICATION'
  | 'UNIT'
  | 'FACILITY'
  | 'TRAINER'
  | 'ROLLING'
  | 'CITY';

/** PENDING awaits a decision; EXCEPTION was accepted and still stands. */
export type SuggestionStatus =
  | 'PENDING'
  | 'ADDED'
  | 'MAPPED'
  | 'DELETED'
  | 'REJECTED'
  | 'EXCEPTION'
  | 'WITHDRAWN';

export interface ReferenceSuggestion {
  id: number;
  entity_type: SuggestionEntityType;
  raw_value: string;
  context: Record<string, string>;
  /**
   * The raising row's other values, for pre-filling the form Add opens: a
   * unit's title, the campus a room was named at. Lists gather every row.
   */
  attributes: SuggestionAttributes;
  source: string;
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string | null;
  status: SuggestionStatus;
  resolved_entity_id: number | null;
  // Present on an accepted exception: who allowed the value, and when.
  accepted_by_user_id: number | null;
  accepted_at: string | null;
  exception_note: string | null;
}

export type SuggestionAttributeValue = string | number | null | Array<string | Record<string, string>>;
export type SuggestionAttributes = Record<string, SuggestionAttributeValue>;

export interface SuggestionList {
  items: ReferenceSuggestion[];
  total: number;
  limit: number;
  offset: number;
}

export interface SuggestionSummaryRow {
  entity_type: SuggestionEntityType;
  pending: number;
  exceptions: number;
}

/** One record a suggestion could be mapped to. */
export interface MapOption {
  id: number;
  label: string;
  /** Tells two similar records apart - for a room, the building. */
  detail: string | null;
  /** Inside the scope the entry was raised with. */
  in_scope: boolean;
}

/**
 * What a suggestion could be mapped to, narrowed by its context: a unit's
 * qualification, a room's campus, a location's college.
 */
export interface MapOptions {
  suggestion_id: number;
  entity_type: SuggestionEntityType;
  scope_label: string | null;
  /** The college, qualification or campus the scope resolved to. */
  scope_id: number | null;
  /** The list holds the scope and nothing else - rooms at one campus. */
  scope_only: boolean;
  items: MapOption[];
  total: number;
  truncated: boolean;
}

export interface AffectedRecords {
  suggestion_id: number;
  entity_type: SuggestionEntityType;
  raw_value: string;
  total: number;
  items: Array<Record<string, unknown>>;
  truncated: boolean;
}

export interface SuggestionResolveResult {
  suggestion: ReferenceSuggestion;
  /** How many stored records the decision repaired. Zero is a warning, not a success. */
  records_updated: number;
}

/** The four administrator actions. */
export type SuggestionAction = 'CREATE' | 'MAP' | 'REJECT' | 'WITHDRAW';

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

export const suggestionsApi = {
  /**
   * Per-entity counts for every tab indicator — one call, one grouped query.
   * Never call the list endpoint repeatedly merely to count.
   */
  summary: () => request<SuggestionSummaryRow[]>('/suggestions/summary'),

  list: (params: {
    entityTypes?: SuggestionEntityType[];
    status?: SuggestionStatus;
    limit?: number;
    offset?: number;
  }) => {
    const search = new URLSearchParams();
    (params.entityTypes ?? []).forEach((entity) => search.append('entity_types', entity));
    if (params.status) search.set('status', params.status);
    if (params.limit !== undefined) search.set('limit', String(params.limit));
    if (params.offset !== undefined) search.set('offset', String(params.offset));
    const query = search.toString();
    return request<SuggestionList>(`/suggestions${query ? `?${query}` : ''}`);
  },

  /** The records an entry affects. Fetched on demand, never for every entry. */
  affected: (suggestionId: number, limit = 50) =>
    request<AffectedRecords>(`/suggestions/${suggestionId}/affected?limit=${limit}`),

  mapOptions: (suggestionId: number, search = '', limit = 50) => {
    const term = search.trim();
    const query = term ? `&search=${encodeURIComponent(term)}` : '';
    return request<MapOptions>(
      `/suggestions/${suggestionId}/map-options?limit=${limit}${query}`,
    );
  },

  resolve: (
    suggestionId: number,
    action: SuggestionAction,
    resolvedEntityId?: number,
    /** Fields for a record CREATE must bring into existence, e.g. a unit title. */
    createValues?: Record<string, string>,
    /**
     * REJECT deletes what carries the value. A reason is required when unverified
     * students are among them: a student is deleted the approved way, with a
     * reason and a recovery window (DATA-04).
     */
    reason?: { code?: string; detail?: string },
  ) =>
    request<SuggestionResolveResult>(`/suggestions/${suggestionId}/resolve`, {
      method: 'POST',
      body: JSON.stringify({
        action,
        resolved_entity_id: resolvedEntityId ?? null,
        create_values: createValues ?? null,
        reason_code: reason?.code ?? null,
        reason_detail: reason?.detail ?? null,
      }),
    }),
};

/** Human labels for the entity types, used by the dialog headings. */
export const ENTITY_LABELS: Record<SuggestionEntityType, string> = {
  COLLEGE: 'College',
  CAMPUS: 'Campus',
  QUALIFICATION: 'Qualification',
  UNIT: 'Unit',
  FACILITY: 'Classroom',
  TRAINER: 'Trainer',
  ROLLING: 'Rolling timetable',
  CITY: 'City',
};
