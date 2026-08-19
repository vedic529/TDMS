import { env } from '@/lib/env';
import { getAuthProvider } from './auth';

/**
 * College and Course Reference Data — the real API client (Step 6).
 *
 * **This module always calls FastAPI.** It does not consult
 * `NEXT_PUBLIC_TDMS_DATA_MODE`, and it has no mock fallback: an empty real
 * database must produce an empty interface, never demo records dressed up as
 * real ones. A failure surfaces as an error the page shows, because quietly
 * substituting mock data would be worse than saying nothing loaded.
 *
 * It sits beside `TdmsClient` rather than inside it so one module can be real
 * while Student, Trainer and Timetable stay on the transitional mock service.
 * Those modules migrate in their own steps; nothing here breaks them.
 *
 * The bearer token is attached in one place, `request()`, from the same MSAL
 * session the rest of the application uses.
 */

// ---------------------------------------------------------------------------
// Wire types — snake_case, exactly as FastAPI returns them
// ---------------------------------------------------------------------------

export interface ApiCollege {
  id: number;
  college_short_name: string;
  college_full_name: string;
  email_domain: string | null;
  is_active: boolean;
}

export interface ApiCampus {
  id: number;
  campus_code: string;
  campus_name: string;
  campus_location: string;
  state: string;
  is_active: boolean;
  /** Every spelling of this campus's address found in a source system. */
  source_addresses?: string[];
}

export interface ApiCollegeCampus {
  college_id: number;
  campus_id: number;
  is_active: boolean;
}

export interface ApiQualification {
  id: number;
  /**
   * `null` where no VET Code has been issued (ELICOS). Displayed as `NA`
   * via `qualificationCodeLabel`; do not substitute a placeholder here,
   * or "no code" becomes indistinguishable from a code reading "NA".
   */
  qualification_code: string | null;
  /** Retired codes that resolve to this qualification. */
  qualification_superseded_codes?: string[];
  qualification_title: string;
  course_level: string | null;
  field_of_education_broad: string | null;
  field_of_education_narrow: string | null;
  course_sector: string | null;
  source_url: string | null;
  is_active: boolean;
}

export interface ApiUnit {
  id: number;
  unit_code: string;
  unit_title: string;
  uoc_type: string | null;
  is_active: boolean;
}

export interface ApiQualificationUnit {
  id: number;
  qualification_id: number;
  /**
   * `null` where no VET Code has been issued (ELICOS). Displayed as `NA`
   * via `qualificationCodeLabel`; do not substitute a placeholder here,
   * or "no code" becomes indistinguishable from a code reading "NA".
   */
  qualification_code: string | null;
  qualification_title: string;
  unit_id: number;
  unit_code: string;
  unit_title: string;
  uoc_type: string | null;
  /** C-1: the approved delivery sequence. Orders rows; not a displayed field. */
  delivery_order: number;
  is_deleted: boolean;
}

export interface ApiCourse {
  id: number;
  course_code: string;
  college_id: number;
  college_short_name: string;
  college_full_name: string;
  campus_id: number;
  campus_name: string;
  /** C-3: derived from the campus, never a second stored value. */
  location: string;
  state: string;
  qualification_id: number;
  /**
   * `null` where no VET Code has been issued (ELICOS). Displayed as `NA`
   * via `qualificationCodeLabel`; do not substitute a placeholder here,
   * or "no code" becomes indistinguishable from a code reading "NA".
   */
  qualification_code: string | null;
  /** Retired codes that resolve to this qualification. */
  qualification_superseded_codes?: string[];
  qualification_title: string;
  course_level: string | null;
  field_of_education_broad: string | null;
  field_of_education_narrow: string | null;
  course_sector: string | null;
  source_url: string | null;
  course_status_id: number;
  course_status_code: string;
  course_status_label: string;
  selectable_for_new_records: boolean;
  total_course_cost: string | number | null;
  duration_options: number[];
  is_deleted: boolean;
  deleted_at: string | null;
  recovery_deadline: string | null;
}

export interface ApiCourseStatus {
  id: number;
  code: string;
  label: string;
  selectable_for_new_records: boolean;
  is_active: boolean;
}

export interface DeletePayload {
  reason_code_id?: number | null;
  reason_detail?: string | null;
}

/** An error carrying the API's safe message, so pages can show it verbatim. */
export class ReferenceApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ReferenceApiError';
  }

  /** True when the message describes a business conflict worth showing inline. */
  get isConflict(): boolean {
    return this.status === 409 || this.status === 422;
  }
}

// ---------------------------------------------------------------------------
// Transport
// ---------------------------------------------------------------------------

type QueryValue = string | number | boolean | undefined | readonly (string | number)[];

/**
 * Build a query string, repeating a key once per value for array parameters —
 * `?college_ids=1&college_ids=2`, which is what FastAPI's `list[int]` reads.
 *
 * An **empty array is omitted entirely**. That is the Select All contract: no
 * restriction at that level. Sending `college_ids=` would ask the server to
 * match a college whose id is the empty string, and it would correctly return
 * nothing.
 */
function query(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '' || value === false) continue;
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, String(item));
      continue;
    }
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init?.headers as Record<string, string> | undefined) ?? {}),
  };

  // The TDMS API access token, obtained by MSAL for the configured scope. Held
  // in memory for this call only: never logged, never written to localStorage.
  const token = await getAuthProvider().getApiAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${env.apiUrl}${path}`, { ...init, headers });

  if (!response.ok) {
    // FastAPI puts the safe, user-facing sentence in `detail`. Anything else
    // gets a generic message rather than exposing a response body.
    let detail = '';
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* no JSON body */
    }
    throw new ReferenceApiError(
      response.status,
      detail || defaultMessage(response.status),
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function defaultMessage(status: number): string {
  switch (status) {
    case 401:
      return 'Your sign-in has expired. Sign in again to continue.';
    case 403:
      return 'You do not have permission to perform this action.';
    case 404:
      return 'That record no longer exists.';
    case 409:
      return 'That change conflicts with an existing approved record.';
    default:
      return 'The request could not be completed. Try again shortly.';
  }
}

// ---------------------------------------------------------------------------
// Reference data API
// ---------------------------------------------------------------------------

export const referenceApi = {
  // -- College -------------------------------------------------------------
  listColleges: (params: { search?: string; activeOnly?: boolean } = {}) =>
    request<ApiCollege[]>(
      `/reference/colleges${query({ search: params.search, active_only: params.activeOnly })}`,
    ),
  getCollege: (id: number) => request<ApiCollege>(`/reference/colleges/${id}`),
  createCollege: (body: Partial<ApiCollege>) =>
    request<ApiCollege>('/reference/colleges', { method: 'POST', body: JSON.stringify(body) }),
  updateCollege: (id: number, body: Partial<ApiCollege>) =>
    request<ApiCollege>(`/reference/colleges/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

  // -- Campus --------------------------------------------------------------
  listCampuses: (
    params: {
      search?: string;
      activeOnly?: boolean;
      collegeId?: number;
      /** Union of campuses approved for these colleges (COL-01), deduplicated. */
      collegeIds?: readonly number[];
    } = {},
  ) =>
    request<ApiCampus[]>(
      `/reference/campuses${query({
        search: params.search,
        active_only: params.activeOnly,
        college_id: params.collegeId,
        college_ids: params.collegeIds,
      })}`,
    ),
  getCampus: (id: number) => request<ApiCampus>(`/reference/campuses/${id}`),
  createCampus: (body: Partial<ApiCampus>) =>
    request<ApiCampus>('/reference/campuses', { method: 'POST', body: JSON.stringify(body) }),
  updateCampus: (id: number, body: Partial<ApiCampus>) =>
    request<ApiCampus>(`/reference/campuses/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

  listCollegeCampuses: (collegeId?: number) =>
    request<ApiCollegeCampus[]>(`/reference/college-campuses${query({ college_id: collegeId })}`),
  approveCollegeCampus: (body: ApiCollegeCampus) =>
    request<ApiCollegeCampus>('/reference/college-campuses', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // -- Qualification -------------------------------------------------------
  /**
   * With a college or campus supplied this returns only qualifications actually
   * **offered** in that scope, from `course_offerings`. Without one it returns
   * the whole table, which is what a maintenance form needs.
   */
  listQualifications: (
    params: {
      search?: string;
      activeOnly?: boolean;
      collegeIds?: readonly number[];
      campusIds?: readonly number[];
    } = {},
  ) =>
    request<ApiQualification[]>(
      `/reference/qualifications${query({
        search: params.search,
        active_only: params.activeOnly,
        college_ids: params.collegeIds,
        campus_ids: params.campusIds,
      })}`,
    ),
  createQualification: (body: Partial<ApiQualification>) =>
    request<ApiQualification>('/reference/qualifications', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateQualification: (id: number, body: Partial<ApiQualification>) =>
    request<ApiQualification>(`/reference/qualifications/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  // -- Unit ----------------------------------------------------------------
  listUnits: (params: { search?: string; activeOnly?: boolean; qualificationId?: number } = {}) =>
    request<ApiUnit[]>(
      `/reference/units${query({
        search: params.search,
        active_only: params.activeOnly,
        qualification_id: params.qualificationId,
      })}`,
    ),
  createUnit: (body: Partial<ApiUnit>) =>
    request<ApiUnit>('/reference/units', { method: 'POST', body: JSON.stringify(body) }),
  updateUnit: (id: number, body: Partial<ApiUnit>) =>
    request<ApiUnit>(`/reference/units/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

  // -- Qualification / Unit sequence (Page 4B) -----------------------------
  listQualificationUnits: (
    params: {
      qualificationId?: number;
      collegeIds?: readonly number[];
      campusIds?: readonly number[];
      qualificationIds?: readonly number[];
      search?: string;
      includeDeleted?: boolean;
    } = {},
  ) =>
    request<ApiQualificationUnit[]>(
      `/reference/qualification-units${query({
        qualification_id: params.qualificationId,
        college_ids: params.collegeIds,
        campus_ids: params.campusIds,
        qualification_ids: params.qualificationIds,
        search: params.search,
        include_deleted: params.includeDeleted,
      })}`,
    ),
  createQualificationUnit: (body: {
    qualification_id: number;
    unit_id: number;
    delivery_order: number;
  }) =>
    request<ApiQualificationUnit>('/reference/qualification-units', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateQualificationUnit: (
    id: number,
    body: { unit_id?: number; delivery_order?: number },
  ) =>
    request<ApiQualificationUnit>(`/reference/qualification-units/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteQualificationUnit: (id: number, body: DeletePayload) =>
    request<ApiQualificationUnit>(`/reference/qualification-units/${id}`, {
      method: 'DELETE',
      body: JSON.stringify(body),
    }),
  restoreQualificationUnit: (id: number, body: DeletePayload = {}) =>
    request<ApiQualificationUnit>(`/reference/qualification-units/${id}/restore`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // -- Course (Page 4A) ----------------------------------------------------
  listCourses: (
    params: {
      search?: string;
      collegeId?: number;
      campusId?: number;
      qualificationId?: number;
      /** Multi-select scope. Empty or omitted means no restriction. */
      collegeIds?: readonly number[];
      campusIds?: readonly number[];
      qualificationIds?: readonly number[];
      /** Approved status code, e.g. ACTIVE. Filtering happens in SQL. */
      courseStatusCode?: string;
      includeDeleted?: boolean;
    } = {},
  ) =>
    request<ApiCourse[]>(
      `/reference/courses${query({
        search: params.search,
        college_id: params.collegeId,
        campus_id: params.campusId,
        qualification_id: params.qualificationId,
        college_ids: params.collegeIds,
        campus_ids: params.campusIds,
        qualification_ids: params.qualificationIds,
        course_status_code: params.courseStatusCode,
        include_deleted: params.includeDeleted,
      })}`,
    ),
  getCourse: (id: number) => request<ApiCourse>(`/reference/courses/${id}`),
  createCourse: (body: {
    college_id: number;
    campus_id: number;
    qualification_id: number;
    course_code: string;
    course_status_id: number;
    total_course_cost?: number | null;
    duration_options?: number[];
  }) => request<ApiCourse>('/reference/courses', { method: 'POST', body: JSON.stringify(body) }),
  updateCourse: (
    id: number,
    body: {
      course_code?: string;
      course_status_id?: number;
      total_course_cost?: number | null;
      duration_options?: number[];
    },
  ) => request<ApiCourse>(`/reference/courses/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteCourse: (id: number, body: DeletePayload) =>
    request<ApiCourse>(`/reference/courses/${id}`, { method: 'DELETE', body: JSON.stringify(body) }),
  restoreCourse: (id: number, body: DeletePayload = {}) =>
    request<ApiCourse>(`/reference/courses/${id}/restore`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  listCourseStatuses: (activeOnly = false) =>
    request<ApiCourseStatus[]>(`/reference/course-statuses${query({ active_only: activeOnly })}`),
};

// ---------------------------------------------------------------------------
// Reusable lookups for later modules
// ---------------------------------------------------------------------------

/**
 * The lookup layer Student, Trainer and Timetable will consume when they
 * migrate, so that dependent-dropdown logic is written once rather than
 * reimplemented per module.
 *
 * `getCampusesForCollege` deliberately asks the server rather than filtering a
 * cached list: COL-01 approval lives in `college_campuses`, and the API applies
 * it in SQL. Filtering client-side would mean the browser deciding which
 * combinations are approved.
 */
export const referenceLookups = {
  getActiveColleges: () => referenceApi.listColleges({ activeOnly: true }),
  getCampusesForCollege: (collegeId: number) =>
    referenceApi.listCampuses({ collegeId, activeOnly: true }),
  getActiveQualifications: () => referenceApi.listQualifications({ activeOnly: true }),
  /** Units in the qualification's approved delivery sequence, already ordered. */
  getUnitsForQualification: (qualificationId: number) =>
    referenceApi.listUnits({ qualificationId, activeOnly: true }),
  getCoursesForCollegeCampus: (collegeId: number, campusId: number) =>
    referenceApi.listCourses({ collegeId, campusId }),
  getSelectableCourseStatuses: () => referenceApi.listCourseStatuses(true),
};
