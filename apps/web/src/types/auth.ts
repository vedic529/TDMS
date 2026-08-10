import type { IsoDateTime } from './common';

/**
 * SRS 3.1 / ACC-01: TDMS has exactly three hierarchy levels.
 * No other value may be added to this union.
 */
export type TdmsRole = 'SUPER_ADMIN' | 'ADMIN' | 'DATA_EDITOR';

/**
 * SRS 3.3 / ACC-02: Student Data Officer and Timetable Officer are Data Editor
 * *work assignments*. They are not hierarchy levels and must never appear in a
 * role selection control.
 */
export type DataEditorAssignment = 'STUDENT_DATA_OFFICER' | 'TIMETABLE_OFFICER';

/** SRS 4.4 account status definitions. */
export type AccountStatus = 'ACTIVE' | 'INACTIVE' | 'DISABLED';

export interface TdmsUser {
  id: string;
  displayName: string;
  /** Organisation Microsoft account. TDMS never stores a password (AUTH-03). */
  organisationEmail: string;
  role: TdmsRole;
  /** Null for Super Admin and Admin, and for an unassigned Data Editor. */
  assignment: DataEditorAssignment | null;
  accountStatus: AccountStatus;
  lastSignInAt: IsoDateTime | null;
  /**
   * OD-05 keeps the Admin role boundary open. Until it is approved, an Admin
   * may only act on another Admin or Super Admin when this delegation flag is
   * explicitly set on the acting user's record.
   */
  delegatedUserManagement: boolean;
  /** SRS 3.4: managing college/campus/qualification mappings for an Admin. */
  delegatedMappingManagement: boolean;
}

/** SRS 4.2: Microsoft sign-in result and TDMS access decision are separate. */
export type MicrosoftSignInResult = 'SUCCESS' | 'FAILURE';
export type TdmsAccessDecision = 'GRANTED' | 'DENIED';

export type AccessDenialReason =
  | 'MICROSOFT_SIGN_IN_FAILED'
  | 'SIGN_IN_NOT_COMPLETED'
  | 'ACCOUNT_INACTIVE'
  | 'ACCOUNT_DISABLED'
  | 'BLOCKED_BY_SECURITY_RULE'
  | 'NO_TDMS_ROLE'
  | 'UNMATCHED_USER';

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
