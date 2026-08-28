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

/** The six entity types a suggestion can stand in for. */
export type SuggestionEntityType =
  | 'COLLEGE'
  | 'CAMPUS'
  | 'QUALIFICATION'
  | 'UNIT'
  | 'FACILITY'
  | 'TRAINER';

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

  resolve: (suggestionId: number, action: SuggestionAction, resolvedEntityId?: number) =>
    request<SuggestionResolveResult>(`/suggestions/${suggestionId}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ action, resolved_entity_id: resolvedEntityId ?? null }),
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
};
