/**
 * Central TDMS permission configuration (Access Model v1.1).
 *
 * Every role check in the interface resolves through this file. Components must
 * never test `role === 'ADMIN'` directly - they call a capability helper, so
 * that ACC-06 (page buttons, navigation items and direct web addresses enforce
 * the same rules) holds by construction.
 *
 * This mirrors the API policy in `apps/api/app/core/rbac.py`. The API is
 * authoritative: hiding a control is a courtesy to the user, and the only thing
 * that actually stops an action is the server refusing it. Both files must be
 * changed together.
 */

import type { RequestableRole, TdmsRole, TdmsUser } from '@/types/auth';

export type Capability =
  | 'view'
  | 'export'
  | 'maintainStudentData'
  | 'maintainTimetable'
  | 'maintainTrainerData'
  | 'maintainReferenceData'
  | 'overrideTimetableClash'
  | 'viewActivityRecords'
  | 'accessAdministration'
  | 'manageUserRoles'
  | 'decideAccessRequests';

/** Ascending privilege. Matches the PostgreSQL `access_level` enum order. */
const ROLE_RANK: Record<TdmsRole, number> = {
  VIEWER: 0,
  DATA_EDITOR: 1,
  ADMIN: 2,
  SUPER_ADMIN: 3,
};

/**
 * The minimum level each capability requires.
 *
 * Two entries carry the Access Model v1.1 changes that are easiest to get
 * wrong: a Data Editor maintains BOTH Student Data and Timetable, and deciding
 * access requests is Super Admin work - an Admin does not approve access
 * requests or assign roles.
 */
const MINIMUM_LEVEL: Record<Capability, TdmsRole> = {
  view: 'VIEWER',
  export: 'VIEWER',
  maintainStudentData: 'DATA_EDITOR',
  maintainTimetable: 'DATA_EDITOR',
  // Reference data stays read-and-download-only for a Data Editor.
  maintainTrainerData: 'ADMIN',
  maintainReferenceData: 'ADMIN',
  overrideTimetableClash: 'ADMIN',
  viewActivityRecords: 'SUPER_ADMIN',
  accessAdministration: 'SUPER_ADMIN',
  manageUserRoles: 'SUPER_ADMIN',
  decideAccessRequests: 'SUPER_ADMIN',
};

/**
 * An inactive or disabled account never reaches an operational page (AUTH-05),
 * but the guard is repeated here so a stale session cannot act.
 */
const isUsable = (user: TdmsUser | null | undefined): user is TdmsUser =>
  !!user && user.accountStatus === 'ACTIVE';

export function rankOf(role: TdmsRole): number {
  return ROLE_RANK[role];
}

export function atLeast(role: TdmsRole, minimum: TdmsRole): boolean {
  return ROLE_RANK[role] >= ROLE_RANK[minimum];
}

export function hasCapability(user: TdmsUser | null, capability: Capability): boolean {
  if (!isUsable(user)) return false;
  return atLeast(user.role, MINIMUM_LEVEL[capability]);
}

// ---------------------------------------------------------------------------
// Capability helpers
// ---------------------------------------------------------------------------

/** Every approved user may view all four operational work areas (ACC-05). */
export const canView = (user: TdmsUser | null) => hasCapability(user, 'view');

/** Every approved user may download or export filtered operational data. */
export const canExport = (user: TdmsUser | null) => hasCapability(user, 'export');

/** Single Student Entry and Bulk Student Import. */
export const canMaintainStudentData = (user: TdmsUser | null) =>
  hasCapability(user, 'maintainStudentData');

/** Create, edit, delete, generate, preview and save timetables. */
export const canMaintainTimetable = (user: TdmsUser | null) =>
  hasCapability(user, 'maintainTimetable');

/** TRN-06: Admin and Super Admin only. Read-and-download for everyone else. */
export const canMaintainTrainerData = (user: TdmsUser | null) =>
  hasCapability(user, 'maintainTrainerData');

/** COL-07: Admin and Super Admin only. Read-and-download for everyone else. */
export const canMaintainReferenceData = (user: TdmsUser | null) =>
  hasCapability(user, 'maintainReferenceData');

export const canOverrideTimetableClash = (user: TdmsUser | null) =>
  hasCapability(user, 'overrideTimetableClash');

/** LOG-04: activity records are part of the Super Admin dashboard. */
export const canViewActivityRecords = (user: TdmsUser | null) =>
  hasCapability(user, 'viewActivityRecords');

/** The Super Admin Dashboard as a whole. */
export const canAccessAdministration = (user: TdmsUser | null) =>
  hasCapability(user, 'accessAdministration');

export const canManageUserRoles = (user: TdmsUser | null) =>
  hasCapability(user, 'manageUserRoles');

/** Approving or denying an access request. Super Admin only - never Admin. */
export const canDecideAccessRequests = (user: TdmsUser | null) =>
  hasCapability(user, 'decideAccessRequests');

/** Restoring a soft-deleted record uses the same authority as deleting it. */
export function canRestoreRecord(
  user: TdmsUser | null,
  recordType: 'student' | 'timetable' | 'trainer' | 'course' | 'qualificationUnit',
): boolean {
  switch (recordType) {
    case 'student':
      return canMaintainStudentData(user);
    case 'timetable':
      return canMaintainTimetable(user);
    case 'trainer':
      return canMaintainTrainerData(user);
    case 'course':
    case 'qualificationUnit':
      return canMaintainReferenceData(user);
    default:
      return false;
  }
}

/**
 * Whether the acting user may change this account.
 *
 * Two administrative lockout protections, both also enforced server-side:
 * nobody changes their own access level, and the last active Super Admin
 * cannot be removed. The reason is returned so the interface can explain a
 * disabled action rather than leaving the user guessing.
 */
export function canManageTargetUser(
  actor: TdmsUser | null,
  target: TdmsUser,
  context?: { activeSuperAdminCount: number },
): { allowed: boolean; reason?: string } {
  if (!isUsable(actor)) return { allowed: false, reason: 'Your account is not active.' };
  if (!canManageUserRoles(actor)) {
    return { allowed: false, reason: 'Managing TDMS access levels requires Super Admin access.' };
  }
  if (actor.id === target.id) {
    return {
      allowed: false,
      reason: 'You cannot change your own access level. Ask another Super Admin to make this change.',
    };
  }
  if (
    target.role === 'SUPER_ADMIN' &&
    context &&
    context.activeSuperAdminCount <= 1 &&
    target.accountStatus === 'ACTIVE'
  ) {
    return {
      allowed: false,
      reason: 'This is the last active Super Admin. Grant Super Admin to another account first.',
    };
  }
  return { allowed: true };
}

// ---------------------------------------------------------------------------
// Aggregate view used by pages and guards
// ---------------------------------------------------------------------------

export type PermissionSet = Record<Capability, boolean>;

export function getPermissions(user: TdmsUser | null): PermissionSet {
  return (Object.keys(MINIMUM_LEVEL) as Capability[]).reduce((set, capability) => {
    set[capability] = hasCapability(user, capability);
    return set;
  }, {} as PermissionSet);
}

// ---------------------------------------------------------------------------
// Access requests
// ---------------------------------------------------------------------------

/** VIEWER is the default level, so it is never something to request. */
export const REQUESTABLE_ROLES: RequestableRole[] = ['DATA_EDITOR', 'ADMIN', 'SUPER_ADMIN'];

/**
 * Which roles this user may request: strictly higher ones only.
 *
 * A user cannot request their current role or a lower one. A reduction is an
 * administrative action a Super Admin performs, not something a user asks for.
 */
export function requestableRolesFor(role: TdmsRole): RequestableRole[] {
  return REQUESTABLE_ROLES.filter((candidate) => ROLE_RANK[candidate] > ROLE_RANK[role]);
}

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

export const ROLE_LABELS: Record<TdmsRole, string> = {
  VIEWER: 'Viewer',
  DATA_EDITOR: 'Data Editor',
  ADMIN: 'Admin',
  SUPER_ADMIN: 'Super Admin',
};

export const ROLE_DESCRIPTIONS: Record<TdmsRole, string> = {
  VIEWER: 'View, search, filter and download every work area. No changes.',
  DATA_EDITOR:
    'Everything a Viewer can do, plus maintaining Student Data and Timetables. Trainer and reference data stay view-only.',
  ADMIN: 'All operational work, including trainer and course reference data.',
  SUPER_ADMIN: 'Full TDMS access, including the administration dashboard, roles and access requests.',
};

/** Ascending privilege - the order a role selector should offer. */
export const ROLE_OPTIONS: Array<{ value: TdmsRole; label: string; description: string }> = (
  ['VIEWER', 'DATA_EDITOR', 'ADMIN', 'SUPER_ADMIN'] as TdmsRole[]
).map((value) => ({ value, label: ROLE_LABELS[value], description: ROLE_DESCRIPTIONS[value] }));

/** Short explanation shown on a page the user can see but not change. */
export function readOnlyReason(user: TdmsUser | null, area: string): string {
  if (!user) return 'Sign in to view this information.';
  if (user.role === 'VIEWER') {
    return `You have view-only access to ${area}. Viewer access covers searching, filtering and downloading. Request Data Editor access from your account menu if you need to make changes.`;
  }
  if (user.role === 'DATA_EDITOR') {
    return `You have view-only access to ${area}. Data Editor access covers Student Data and Timetables; maintaining this information requires Admin access. You can still view, filter and download it.`;
  }
  return `You have view-only access to ${area}.`;
}
