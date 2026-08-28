import type {
  AccessRequest,
  AccountStatus,
  DashboardOverview,
  NotificationOutcome,
  RequestableRole,
  TdmsRole,
  TdmsUser,
} from '@/types/auth';
import type { ActivityFilters, UserActivityRecord } from '@/types/activity';
import type { CourseRecord, QualificationUnitSequence } from '@/types/reference';
import type { TrainerFilters, TrainerInput, TrainerRecord } from '@/types/trainer';

import { getAuthProvider } from './auth';
import type { ReferenceDataBundle } from './dataset';
import type {
  ActionContext,
  CourseFilters,
  CourseInput,
  QualificationUnitFilters,
  QualificationUnitInput,
  ReasonedRequest,
  TdmsClient,
  UserInput,
} from './tdms-client';

/**
 * FastAPI-backed TDMS data service.
 *
 * This is the seam where the real backend connects. Every method already has
 * its route mapped out below; the bodies call `request()` once the matching
 * FastAPI endpoint exists. Page components are written against `TdmsClient`,
 * so switching `NEXT_PUBLIC_TDMS_DATA_MODE` from `mock` to `api` is the only
 * change the frontend needs.
 *
 * Nothing here reads browser storage: persistence belongs to the API and the
 * production database.
 */
export class ApiTdmsClient implements TdmsClient {
  readonly mode = 'api' as const;

  constructor(private readonly baseUrl: string) {}

  /**
   * Every API call goes through here, which is the only place the Authorization
   * header is set. Repeating it per call site is how one endpoint eventually
   * ships without it.
   *
   * The token is the **TDMS API access token** obtained by MSAL for the
   * configured `api://…/access_as_user` scope — never the Microsoft ID token,
   * which identifies the browser application rather than the caller and which
   * the API refuses.
   *
   * It is held only in memory for the duration of the call. It is never logged
   * and never written to localStorage.
   */
  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((init?.headers as Record<string, string> | undefined) ?? {}),
    };

    const accessToken = await getAuthProvider().getApiAccessToken();
    if (accessToken) {
      headers.Authorization = `Bearer ${accessToken}`;
    }

    const response = await fetch(`${this.baseUrl}${path}`, { ...init, headers });

    if (!response.ok) {
      // The status is enough to act on; the body may carry user detail that
      // does not belong in a thrown message.
      throw new Error(`TDMS API request failed: ${response.status} ${response.statusText}`);
    }
    return (await response.json()) as T;
  }

  private notConnected(operation: string): never {
    throw new Error(
      `The TDMS API is not connected yet, so "${operation}" is unavailable. Set NEXT_PUBLIC_TDMS_DATA_MODE=mock to use the prototype dataset.`,
    );
  }

  // -- Reference data ------------------------------------------------------
  getReferenceData(): Promise<ReferenceDataBundle> {
    return this.request<ReferenceDataBundle>('/reference-data');
  }

  // -- Student Data --------------------------------------------------------
  // Students and the bulk import are served by `students-api.ts`, which
  // talks to the API directly rather than through this client.

  // -- Trainer Data --------------------------------------------------------
  // Removed 27 August 2026: trainers are served by `trainers-api.ts`, which
  // talks to the API directly. The old `GET /trainers` call here pointed at an
  // endpoint that did not exist and returned an empty array.

  // -- College and Course Reference Data -----------------------------------
  listCourses(filters: CourseFilters): Promise<CourseRecord[]> {
    const query = new URLSearchParams(
      Object.entries(filters).filter(([, value]) => Boolean(value)) as [string, string][],
    );
    return this.request<CourseRecord[]>(`/courses?${query.toString()}`);
  }

  createCourse(input: CourseInput, _context: ActionContext): Promise<CourseRecord> {
    return this.request<CourseRecord>('/courses', { method: 'POST', body: JSON.stringify(input) });
  }

  updateCourse(id: string, input: CourseInput, _context: ActionContext): Promise<CourseRecord> {
    return this.request<CourseRecord>(`/courses/${id}`, { method: 'PUT', body: JSON.stringify(input) });
  }

  async deleteCourse(id: string, request: ReasonedRequest, _context: ActionContext): Promise<void> {
    await this.request<void>(`/courses/${id}`, { method: 'DELETE', body: JSON.stringify(request) });
  }

  listDeletedCourses(): Promise<CourseRecord[]> {
    return this.request<CourseRecord[]>('/courses/deleted');
  }

  restoreCourse(id: string, request: ReasonedRequest, _context: ActionContext): Promise<CourseRecord> {
    return this.request<CourseRecord>(`/courses/${id}/restore`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  listQualificationUnitSequences(filters: QualificationUnitFilters): Promise<QualificationUnitSequence[]> {
    const query = new URLSearchParams(
      Object.entries(filters).filter(([, value]) => Boolean(value)) as [string, string][],
    );
    return this.request<QualificationUnitSequence[]>(`/qualification-units?${query.toString()}`);
  }

  createQualificationUnit(
    input: QualificationUnitInput,
    _context: ActionContext,
  ): Promise<QualificationUnitSequence> {
    return this.request<QualificationUnitSequence>('/qualification-units', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  }

  updateQualificationUnit(
    id: string,
    input: QualificationUnitInput,
    _context: ActionContext,
  ): Promise<QualificationUnitSequence> {
    return this.request<QualificationUnitSequence>(`/qualification-units/${id}`, {
      method: 'PUT',
      body: JSON.stringify(input),
    });
  }

  async deleteQualificationUnit(
    id: string,
    request: ReasonedRequest,
    _context: ActionContext,
  ): Promise<void> {
    await this.request<void>(`/qualification-units/${id}`, { method: 'DELETE', body: JSON.stringify(request) });
  }

  listDeletedQualificationUnits(): Promise<QualificationUnitSequence[]> {
    return this.request<QualificationUnitSequence[]>('/qualification-units/deleted');
  }

  restoreQualificationUnit(
    id: string,
    request: ReasonedRequest,
    _context: ActionContext,
  ): Promise<QualificationUnitSequence> {
    return this.request<QualificationUnitSequence>(`/qualification-units/${id}/restore`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  // -- Administration ------------------------------------------------------
  listUsers(): Promise<TdmsUser[]> {
    return this.request<TdmsUser[]>('/users');
  }

  createUser(input: UserInput, _context: ActionContext): Promise<TdmsUser> {
    return this.request<TdmsUser>('/users', { method: 'POST', body: JSON.stringify(input) });
  }

  updateUser(id: string, input: UserInput, _context: ActionContext): Promise<TdmsUser> {
    return this.request<TdmsUser>(`/users/${id}`, { method: 'PUT', body: JSON.stringify(input) });
  }

  listActivityRecords(filters: ActivityFilters): Promise<UserActivityRecord[]> {
    const query = new URLSearchParams(
      Object.entries(filters).filter(([, value]) => Boolean(value)) as [string, string][],
    );
    return this.request<UserActivityRecord[]>(`/admin/activity-records?${query.toString()}`);
  }

  // -- Access requests (Access Model v1.1) ---------------------------------
  //
  // These routes exist in the API today. The `_context` parameters are unused
  // on purpose: the API identifies the actor from the verified Microsoft token,
  // never from a value the browser supplies.

  getMyAccessRequest(_userId: string): Promise<AccessRequest | null> {
    return this.request<AccessRequest | null>('/me/access-request');
  }

  submitAccessRequest(
    requestedRole: RequestableRole,
    _context: ActionContext,
  ): Promise<{ request: AccessRequest; notification: NotificationOutcome }> {
    return this.request('/me/access-requests', {
      method: 'POST',
      body: JSON.stringify({ requested_role: requestedRole }),
    });
  }

  cancelAccessRequest(id: string, _context: ActionContext): Promise<AccessRequest> {
    return this.request<AccessRequest>(`/me/access-requests/${id}`, { method: 'DELETE' });
  }

  listAccessRequests(): Promise<AccessRequest[]> {
    return this.request<AccessRequest[]>('/admin/access-requests');
  }

  approveAccessRequest(id: string, _context: ActionContext): Promise<AccessRequest> {
    return this.request<AccessRequest>(`/admin/access-requests/${id}/approve`, { method: 'POST' });
  }

  denyAccessRequest(id: string, _context: ActionContext): Promise<AccessRequest> {
    return this.request<AccessRequest>(`/admin/access-requests/${id}/deny`, { method: 'POST' });
  }

  /**
   * Grant a person TDMS access directly. Super Admin only, enforced by the API.
   *
   * Two fields, because that is all a Super Admin is asked for. No display name
   * is sent: Microsoft supplies it at first sign-in, and deriving one from the
   * mailbox would store a guess as though someone had confirmed it.
   */
  provisionUser(organisationEmail: string, role: TdmsRole): Promise<TdmsUser> {
    return this.request<TdmsUser>('/admin/users', {
      method: 'POST',
      body: JSON.stringify({ organisation_email: organisationEmail, access_level: role }),
    });
  }

  changeUserRole(id: string, role: TdmsRole, _context: ActionContext): Promise<TdmsUser> {
    return this.request<TdmsUser>(`/admin/users/${id}/role`, {
      method: 'POST',
      body: JSON.stringify({ access_level: role }),
    });
  }

  changeUserAccountStatus(
    id: string,
    status: AccountStatus,
    _context: ActionContext,
  ): Promise<TdmsUser> {
    return this.request<TdmsUser>(`/admin/users/${id}/status`, {
      method: 'POST',
      body: JSON.stringify({ account_status: status }),
    });
  }

  getDashboardOverview(): Promise<DashboardOverview> {
    return this.request<DashboardOverview>('/admin/overview');
  }

  recordActivity(
    record: Omit<UserActivityRecord, 'activityRecordNumber' | 'dateTime'>,
  ): Promise<UserActivityRecord> {
    return this.request<UserActivityRecord>('/activity-records', {
      method: 'POST',
      body: JSON.stringify(record),
    });
  }

  // -- Prototype maintenance ----------------------------------------------
  async resetPrototypeData(): Promise<void> {
    // Resetting demo data is a prototype-only operation.
    this.notConnected('reset prototype data');
  }
}
