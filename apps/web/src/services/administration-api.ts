import { env } from '@/lib/env';
import type {
  AccessRequest,
  AccountStatus,
  DashboardOverview,
  NotificationOutcome,
  RequestableRole,
  TdmsRole,
  TdmsUser,
} from '@/types/auth';
import type { ActivityAction, ActivityFilters, ActivityResult, UserActivityRecord } from '@/types/activity';

import { getAuthProvider } from './auth';

interface UserWire {
  id: number;
  display_name: string | null;
  organisation_email: string;
  access_level: TdmsRole;
  account_status: AccountStatus;
  last_sign_in_at: string | null;
  identity_linked: boolean;
}

interface AccessRequestWire {
  id: number;
  requester_user_id: number;
  requester_display_name: string | null;
  requester_email: string | null;
  role_at_request: TdmsRole;
  requested_role: RequestableRole;
  status: AccessRequest['status'];
  requested_at: string;
  decided_at: string | null;
  decided_by_user_id: number | null;
  decided_by_email: string | null;
}

interface OverviewWire {
  pending_access_requests: number;
  active_users: number;
  viewer_count: number;
  data_editor_count: number;
  admin_count: number;
  super_admin_count: number;
  inactive_or_disabled_users: number;
}

interface ActivityWire {
  id: string;
  occurredAt: string;
  userReference: string;
  accessLevel: TdmsRole | null;
  pageOrFunction: string;
  action: string;
  recordReference: string | null;
  result: string | null;
  microsoftSignInResult: UserActivityRecord['microsoftSignInResult'];
  tdmsAccessDecision: UserActivityRecord['tdmsAccessDecision'];
  detail: string;
}

const ACTION_LABELS: Record<string, ActivityAction> = {
  SIGN_IN: 'Sign in',
  SIGN_OUT: 'Sign out',
  CREATE: 'Create',
  UPDATE: 'Edit',
  DELETE: 'Delete',
  RESTORE: 'Restore',
  IMPORT: 'Import',
  EXPORT: 'Export',
  TIMETABLE_SAVE: 'Timetable save',
  TIMETABLE_GENERATION: 'Timetable generation',
  CANCELLATION_AFTER_UPDATE: 'Cancellation after update',
  OVERRIDE: 'Override',
  ACCESS_DENIED: 'Access denied',
  ACCESS_REQUEST_SUBMITTED: 'Access request submitted',
  ACCESS_REQUEST_APPROVED: 'Access request approved',
  ACCESS_REQUEST_DENIED: 'Access request denied',
  ACCESS_REQUEST_CANCELLED: 'Access request cancelled',
  ROLE_CHANGED: 'Role changed',
  ACCOUNT_STATUS_CHANGED: 'Account status changed',
  USER_PROVISIONED: 'User provisioned',
};

const RESULT_LABELS: Record<string, ActivityResult> = {
  COMPLETED: 'Completed',
  REJECTED_BY_VALIDATION: 'Rejected by validation',
  CANCELLED_BY_USER: 'Cancelled by the user',
  FAILED_SYSTEM_ERROR: 'Failed because of a system error',
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init?.headers as Record<string, string> | undefined) ?? {}),
  };
  const token = await getAuthProvider().getApiAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${env.apiUrl}${path}`, { ...init, headers });
  if (!response.ok) throw new Error(`TDMS API request failed: ${response.status} ${response.statusText}`);
  return (await response.json()) as T;
}

function toUser(row: UserWire): TdmsUser {
  return {
    id: String(row.id),
    displayName: row.display_name ?? row.organisation_email,
    organisationEmail: row.organisation_email,
    role: row.access_level,
    accountStatus: row.account_status,
    lastSignInAt: row.last_sign_in_at,
    identityLinked: row.identity_linked,
  };
}

function toAccessRequest(row: AccessRequestWire): AccessRequest {
  return {
    id: String(row.id),
    requesterUserId: String(row.requester_user_id),
    requesterDisplayName: row.requester_display_name,
    requesterEmail: row.requester_email,
    roleAtRequest: row.role_at_request,
    requestedRole: row.requested_role,
    status: row.status,
    requestedAt: row.requested_at,
    decidedAt: row.decided_at,
    decidedByUserId: row.decided_by_user_id === null ? null : String(row.decided_by_user_id),
    decidedByEmail: row.decided_by_email,
  };
}

function toActivity(row: ActivityWire): UserActivityRecord {
  return {
    activityRecordNumber: row.id,
    dateTime: row.occurredAt,
    userReference: row.userReference,
    accessLevel: row.accessLevel ?? 'Unknown',
    pageOrFunction: row.pageOrFunction,
    action: ACTION_LABELS[row.action] ?? 'Edit',
    recordOrBatchReference: row.recordReference ?? '',
    result: RESULT_LABELS[row.result ?? ''] ?? (row.tdmsAccessDecision === 'DENIED' ? 'Access denied' : 'Access granted'),
    microsoftSignInResult: row.microsoftSignInResult ?? undefined,
    tdmsAccessDecision: row.tdmsAccessDecision ?? undefined,
    plainLanguageDetail: row.detail,
  };
}

export const administrationApi = {
  async getDashboardOverview(): Promise<DashboardOverview> {
    const row = await request<OverviewWire>('/admin/overview');
    return {
      pendingAccessRequests: row.pending_access_requests,
      activeUsers: row.active_users,
      viewerCount: row.viewer_count,
      dataEditorCount: row.data_editor_count,
      adminCount: row.admin_count,
      superAdminCount: row.super_admin_count,
      inactiveOrDisabledUsers: row.inactive_or_disabled_users,
    };
  },

  async getMyAccessRequest(): Promise<AccessRequest | null> {
    const row = await request<AccessRequestWire | null>('/me/access-request');
    return row ? toAccessRequest(row) : null;
  },

  async submitAccessRequest(requestedRole: RequestableRole): Promise<{ request: AccessRequest; notification: NotificationOutcome }> {
    const body = await request<{ request: AccessRequestWire; notification: NotificationOutcome }>('/me/access-requests', {
      method: 'POST',
      body: JSON.stringify({ requested_role: requestedRole }),
    });
    return { request: toAccessRequest(body.request), notification: body.notification };
  },

  async cancelAccessRequest(id: string): Promise<AccessRequest> {
    return toAccessRequest(await request<AccessRequestWire>(`/me/access-requests/${id}`, { method: 'DELETE' }));
  },

  async listAccessRequests(): Promise<AccessRequest[]> {
    return (await request<AccessRequestWire[]>('/admin/access-requests')).map(toAccessRequest);
  },

  async approveAccessRequest(id: string): Promise<AccessRequest> {
    return toAccessRequest(await request<AccessRequestWire>(`/admin/access-requests/${id}/approve`, { method: 'POST' }));
  },

  async denyAccessRequest(id: string): Promise<AccessRequest> {
    return toAccessRequest(await request<AccessRequestWire>(`/admin/access-requests/${id}/deny`, { method: 'POST' }));
  },

  async listUsers(): Promise<TdmsUser[]> {
    return (await request<UserWire[]>('/admin/users')).map(toUser);
  },

  async changeUserRole(id: string, role: TdmsRole): Promise<TdmsUser> {
    return toUser(await request<UserWire>(`/admin/users/${id}/role`, {
      method: 'POST', body: JSON.stringify({ access_level: role }),
    }));
  },

  async changeUserAccountStatus(id: string, status: AccountStatus): Promise<TdmsUser> {
    return toUser(await request<UserWire>(`/admin/users/${id}/status`, {
      method: 'POST', body: JSON.stringify({ account_status: status }),
    }));
  },

  async listActivityRecords(filters: ActivityFilters): Promise<UserActivityRecord[]> {
    const rows = (await request<ActivityWire[]>('/admin/activity-records')).map(toActivity);
    const search = filters.search?.trim().toLowerCase();
    return rows.filter((row) =>
      (!search || Object.values(row).some((value) => String(value ?? '').toLowerCase().includes(search))) &&
      (!filters.action || row.action === filters.action) &&
      (!filters.result || row.result === filters.result) &&
      (!filters.pageOrFunction || row.pageOrFunction === filters.pageOrFunction));
  },

  async recordExport(record: Omit<UserActivityRecord, 'activityRecordNumber' | 'dateTime'>): Promise<void> {
    await request('/me/activity-records', {
      method: 'POST',
      body: JSON.stringify({
        action: 'EXPORT',
        page_or_function: record.pageOrFunction,
        record_reference: record.recordOrBatchReference,
        detail: record.plainLanguageDetail,
      }),
    });
  },
};
