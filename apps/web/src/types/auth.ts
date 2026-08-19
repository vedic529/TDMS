import type { IsoDateTime } from './common';

/**
 * Access Model v1.1: TDMS has exactly four hierarchy levels, in ascending
 * privilege. The order matters — it is the same order as the PostgreSQL
 * `access_level` enum, so "at least this level" means the same thing on both
 * sides, and "may only request a higher role" is a comparison rather than a
 * hand-maintained table.
 *
 * The Data Editor work assignment (Student Data Officer / Timetable Officer)
 * was removed: a Data Editor now maintains both Student Data and Timetable, so
 * the distinction no longer decided anything.
 */
export type TdmsRole = 'VIEWER' | 'DATA_EDITOR' | 'ADMIN' | 'SUPER_ADMIN';

/** SRS 4.4 account status definitions. */
export type AccountStatus = 'ACTIVE' | 'INACTIVE' | 'DISABLED';

export interface TdmsUser {
  id: string;
  /** Supplied by Microsoft at sign-in, never derived from the mailbox. */
  displayName: string;
  /** Organisation Microsoft account. TDMS never stores a password (AUTH-03). */
  organisationEmail: string;
  role: TdmsRole;
  accountStatus: AccountStatus;
  lastSignInAt: IsoDateTime | null;
  /** Whether a verified Microsoft identity has been bound to this account. */
  identityLinked?: boolean;
}

// ---------------------------------------------------------------------------
// Access requests
// ---------------------------------------------------------------------------

export type AccessRequestStatus = 'PENDING' | 'APPROVED' | 'DENIED' | 'CANCELLED';

/** VIEWER is the default access level and is never requested. */
export type RequestableRole = Exclude<TdmsRole, 'VIEWER'>;

export interface AccessRequest {
  id: string;
  requesterUserId: string;
  requesterDisplayName: string | null;
  requesterEmail: string | null;
  roleAtRequest: TdmsRole;
  requestedRole: RequestableRole;
  status: AccessRequestStatus;
  requestedAt: IsoDateTime;
  decidedAt: IsoDateTime | null;
  decidedByUserId: string | null;
  decidedByEmail: string | null;
}

/** What actually happened to the approval notification. Never optimistic. */
export interface NotificationOutcome {
  delivered: boolean;
  provider: string;
  detail: string;
}

export interface DashboardOverview {
  pendingAccessRequests: number;
  activeUsers: number;
  viewerCount: number;
  dataEditorCount: number;
  adminCount: number;
  superAdminCount: number;
  inactiveOrDisabledUsers: number;
}

// ---------------------------------------------------------------------------
// Sign-in
// ---------------------------------------------------------------------------

/** SRS 4.2: Microsoft sign-in result and TDMS access decision are separate. */
export type MicrosoftSignInResult = 'SUCCESS' | 'FAILURE';
export type TdmsAccessDecision = 'GRANTED' | 'DENIED';

export type AccessDenialReason =
  | 'MICROSOFT_SIGN_IN_FAILED'
  | 'SIGN_IN_NOT_COMPLETED'
  | 'ACCOUNT_INACTIVE'
  | 'ACCOUNT_DISABLED'
  | 'BLOCKED_BY_SECURITY_RULE'
  | 'ORGANISATION_NOT_APPROVED'
  | 'NO_TDMS_ROLE'
  | 'UNMATCHED_USER'
  /**
   * The TDMS API could not be reached at all.
   *
   * Not a denial — nothing decided anything. It is in this list because the
   * sign-in still failed and the user still needs telling, but the interface
   * must not label it "Access denied": that sends someone to request access
   * when the actual fix is to start the backend.
   */
  | 'SERVICE_UNAVAILABLE';

export interface AuthSession {
  user: TdmsUser;
  microsoftSignInResult: MicrosoftSignInResult;
  accessDecision: Extract<TdmsAccessDecision, 'GRANTED'>;
  signedInAt: IsoDateTime;
  /** AUTH-11: safe technical reference retained for authorised investigation. */
  correlationId: string;
  /** Which adapter produced the session. Displayed so mock is never mistaken for production. */
  provider: 'mock' | 'entra';
}

export interface AuthFailure {
  microsoftSignInResult: MicrosoftSignInResult;
  accessDecision: Extract<TdmsAccessDecision, 'DENIED'>;
  reason: AccessDenialReason;
  /** AUTH-10: safe, non-disclosing message for the user. */
  userMessage: string;
  correlationId: string;
}

export type AuthResult = { ok: true; session: AuthSession } | { ok: false; failure: AuthFailure };
