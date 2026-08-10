/**
 * Central TDMS permission configuration.
 *
 * Every role check in the application resolves through this file. Components
 * must never test `role === 'ADMIN'` directly - they call a capability helper
 * so that ACC-06 (page buttons, navigation items and direct web addresses
 * enforce the same rules) holds by construction.
 *
 * Source: SRS 3.2 Complete Responsibilities, 3.3 Data Editor Work Assignments
 * and 3.4 Permission Matrix.
 */

import type { DataEditorAssignment, TdmsRole, TdmsUser } from '@/types/auth';

export type Capability =
  | 'view'
  | 'export'
  | 'createStudent'
  | 'editStudent'
  | 'deleteStudent'
  | 'processBulkStudentImport'
  | 'createTimetable'
  | 'editTimetable'
  | 'deleteTimetable'
  | 'overrideTimetableClash'
  | 'maintainTrainerData'
  | 'maintainCourseData'
  | 'maintainQualificationUnitData'
  | 'manageMappings'
  | 'manageUsers'
  | 'viewActivityRecords'
  | 'restoreDeletedRecords';

const isDataEditor = (user: TdmsUser) => user.role === 'DATA_EDITOR';

const hasAssignment = (user: TdmsUser, assignment: DataEditorAssignment) =>
  isDataEditor(user) && user.assignment === assignment;

const isAdminOrAbove = (user: TdmsUser) => user.role === 'ADMIN' || user.role === 'SUPER_ADMIN';

/**
 * An inactive or disabled account never reaches an operational page (AUTH-05),
 * but the guard is repeated here so a stale session cannot act.
 */
const isUsable = (user: TdmsUser | null | undefined): user is TdmsUser =>
  !!user && user.accountStatus === 'ACTIVE';

// ---------------------------------------------------------------------------
// Capability helpers
// ---------------------------------------------------------------------------

/** ACC-05: every approved user may view all operational pages. */
export function canView(user: TdmsUser | null): boolean {
  return isUsable(user);
}

/** SRS 3.4: every approved user may download or export filtered operational data. */
export function canExport(user: TdmsUser | null): boolean {
  return isUsable(user);
}

export function canCreateStudent(user: TdmsUser | null): boolean {
  if (!isUsable(user)) return false;
  return isAdminOrAbove(user) || hasAssignment(user, 'STUDENT_DATA_OFFICER');
}

export const canEditStudent = canCreateStudent;
export const canDeleteStudent = canCreateStudent;
export const canProcessBulkStudentImport = canCreateStudent;

export function canCreateTimetable(user: TdmsUser | null): boolean {
  if (!isUsable(user)) return false;
  return isAdminOrAbove(user) || hasAssignment(user, 'TIMETABLE_OFFICER');
}

export const canEditTimetable = canCreateTimetable;
export const canDeleteTimetable = canCreateTimetable;

/**
 * TT-06 / OD-06: who may approve a clash override is an open decision. Until it
 * is approved, TDMS offers the override only to Admin and Super Admin and
 * records the reason, rather than inventing an approval rule.
 */
export function canOverrideTimetableClash(user: TdmsUser | null): boolean {
  return isUsable(user) && isAdminOrAbove(user);
}

/** TRN-06: only Admin and Super Admin may maintain trainer reference data. */
export function canMaintainTrainerData(user: TdmsUser | null): boolean {
  return isUsable(user) && isAdminOrAbove(user);
}

/** COL-07: only Admin and Super Admin may maintain course reference data. */
export function canMaintainCourseData(user: TdmsUser | null): boolean {
  return isUsable(user) && isAdminOrAbove(user);
}

export const canMaintainQualificationUnitData = canMaintainCourseData;

/**
 * SRS 3.4: managing college/campus/qualification mappings is Super Admin work.
 * An Admin may only do it when the delegation flag is explicitly set.
 */
export function canManageMappings(user: TdmsUser | null): boolean {
  if (!isUsable(user)) return false;
  if (user.role === 'SUPER_ADMIN') return true;
  return user.role === 'ADMIN' && user.delegatedMappingManagement;
}

/** SRS 3.4 / 3.2: Super Admin manages all users; Admin within delegated authority. */
export function canManageUsers(user: TdmsUser | null): boolean {
  if (!isUsable(user)) return false;
  return isAdminOrAbove(user);
}

/** LOG-04: only Super Admin and Admin may view user activity records. */
export function canViewActivityRecords(user: TdmsUser | null): boolean {
  return isUsable(user) && isAdminOrAbove(user);
}

/** Restoring a soft-deleted record uses the same authority as deleting it. */
export function canRestoreRecord(
  user: TdmsUser | null,
  recordType: 'student' | 'timetable' | 'trainer' | 'course' | 'qualificationUnit',
): boolean {
  switch (recordType) {
    case 'student':
      return canDeleteStudent(user);
    case 'timetable':
      return canDeleteTimetable(user);
    case 'trainer':
      return canMaintainTrainerData(user);
    case 'course':
      return canMaintainCourseData(user);
    case 'qualificationUnit':
      return canMaintainQualificationUnitData(user);
    default:
      return false;
  }
}

/**
 * OD-05 keeps the Admin role boundary open. Until it is approved:
 *  - a Super Admin may act on any account;
 *  - an Admin may act on a Data Editor;
 *  - an Admin may act on another Admin only with the delegation flag;
 *  - an Admin may never act on a Super Admin.
 * The reason is returned so the UI can explain a disabled action.
 */
export function canManageTargetUser(
  actor: TdmsUser | null,
  target: TdmsUser,
): { allowed: boolean; reason?: string } {
  if (!isUsable(actor)) return { allowed: false, reason: 'Your account is not active.' };
  if (!canManageUsers(actor)) {
    return { allowed: false, reason: 'Managing TDMS users requires Admin or Super Admin access.' };
  }
  if (actor.role === 'SUPER_ADMIN') return { allowed: true };

  if (target.role === 'SUPER_ADMIN') {
    return {
      allowed: false,
      reason: 'An Admin cannot change a Super Admin account. Super Admin account changes remain restricted (OD-05).',
    };
  }
  if (target.role === 'ADMIN' && !actor.delegatedUserManagement) {
    return {
      allowed: false,
      reason:
        'Changing another Admin account requires delegated user management authority. The Admin role boundary is an open decision (OD-05).',
    };
  }
  return { allowed: true };
}

// ---------------------------------------------------------------------------
// Aggregate view used by pages and guards
// ---------------------------------------------------------------------------

export interface PermissionSet {
  view: boolean;
  export: boolean;
  createStudent: boolean;
  editStudent: boolean;
  deleteStudent: boolean;
  processBulkStudentImport: boolean;
  createTimetable: boolean;
  editTimetable: boolean;
  deleteTimetable: boolean;
  overrideTimetableClash: boolean;
  maintainTrainerData: boolean;
  maintainCourseData: boolean;
  maintainQualificationUnitData: boolean;
  manageMappings: boolean;
  manageUsers: boolean;
  viewActivityRecords: boolean;
}

export function getPermissions(user: TdmsUser | null): PermissionSet {
  return {
    view: canView(user),
    export: canExport(user),
    createStudent: canCreateStudent(user),
    editStudent: canEditStudent(user),
    deleteStudent: canDeleteStudent(user),
    processBulkStudentImport: canProcessBulkStudentImport(user),
    createTimetable: canCreateTimetable(user),
    editTimetable: canEditTimetable(user),
    deleteTimetable: canDeleteTimetable(user),
    overrideTimetableClash: canOverrideTimetableClash(user),
    maintainTrainerData: canMaintainTrainerData(user),
    maintainCourseData: canMaintainCourseData(user),
    maintainQualificationUnitData: canMaintainQualificationUnitData(user),
    manageMappings: canManageMappings(user),
    manageUsers: canManageUsers(user),
    viewActivityRecords: canViewActivityRecords(user),
  };
}

export function hasCapability(user: TdmsUser | null, capability: Capability): boolean {
  switch (capability) {
    case 'view':
      return canView(user);
    case 'export':
      return canExport(user);
    case 'createStudent':
      return canCreateStudent(user);
    case 'editStudent':
      return canEditStudent(user);
    case 'deleteStudent':
      return canDeleteStudent(user);
    case 'processBulkStudentImport':
      return canProcessBulkStudentImport(user);
    case 'createTimetable':
      return canCreateTimetable(user);
    case 'editTimetable':
      return canEditTimetable(user);
    case 'deleteTimetable':
      return canDeleteTimetable(user);
    case 'overrideTimetableClash':
      return canOverrideTimetableClash(user);
    case 'maintainTrainerData':
      return canMaintainTrainerData(user);
    case 'maintainCourseData':
      return canMaintainCourseData(user);
    case 'maintainQualificationUnitData':
      return canMaintainQualificationUnitData(user);
    case 'manageMappings':
      return canManageMappings(user);
    case 'manageUsers':
      return canManageUsers(user);
    case 'viewActivityRecords':
      return canViewActivityRecords(user);
    case 'restoreDeletedRecords':
      return canDeleteStudent(user) || canDeleteTimetable(user) || canMaintainCourseData(user);
    default:
      return false;
  }
}

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

export const ROLE_LABELS: Record<TdmsRole, string> = {
  SUPER_ADMIN: 'Super Admin',
  ADMIN: 'Admin',
  DATA_EDITOR: 'Data Editor',
};

export const ASSIGNMENT_LABELS: Record<DataEditorAssignment, string> = {
  STUDENT_DATA_OFFICER: 'Student Data Officer',
  TIMETABLE_OFFICER: 'Timetable Officer',
};

/**
 * Only these three values may ever populate a role selection control.
 * Work assignments are deliberately excluded (ACC-02).
 */
export const ROLE_OPTIONS: Array<{ value: TdmsRole; label: string; description: string }> = [
  {
    value: 'SUPER_ADMIN',
    label: ROLE_LABELS.SUPER_ADMIN,
    description: 'Full TDMS access, including user management and approved mappings.',
  },
  {
    value: 'ADMIN',
    label: ROLE_LABELS.ADMIN,
    description: 'All operational work, user management within delegated authority.',
  },
  {
    value: 'DATA_EDITOR',
    label: ROLE_LABELS.DATA_EDITOR,
    description: 'Create, edit and delete within one assigned work area only.',
  },
];

export const ASSIGNMENT_OPTIONS: Array<{ value: DataEditorAssignment; label: string; description: string }> = [
  {
    value: 'STUDENT_DATA_OFFICER',
    label: ASSIGNMENT_LABELS.STUDENT_DATA_OFFICER,
    description: 'Single Student Entry and Bulk Student Import.',
  },
  {
    value: 'TIMETABLE_OFFICER',
    label: ASSIGNMENT_LABELS.TIMETABLE_OFFICER,
    description: 'Timetable View and Management.',
  },
];

/** Short explanation shown on a read-only page for a Data Editor. */
export function readOnlyReason(user: TdmsUser | null, area: string): string {
  if (!user) return 'Sign in to view this information.';
  if (user.role === 'DATA_EDITOR') {
    const assignment = user.assignment ? ASSIGNMENT_LABELS[user.assignment] : 'Data Editor';
    return `You have view-only access to ${area}. Your ${assignment} work assignment does not include changing this information. You can still view, filter and download it.`;
  }
  return `You have view-only access to ${area}.`;
}
