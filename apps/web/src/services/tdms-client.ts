import type { ReasonCode } from '@/types/common';
import type {
  AccessRequest,
  AccountStatus,
  DashboardOverview,
  NotificationOutcome,
  RequestableRole,
  TdmsRole,
  TdmsUser,
} from '@/types/auth';
import type { UserActivityRecord, ActivityFilters } from '@/types/activity';
import type { CourseRecord, QualificationUnitSequence } from '@/types/reference';
import type { ReferenceDataBundle } from './dataset';

/**
 * The single data contract used by every TDMS page.
 *
 *   UI components
 *         |
 *         v
 *   TdmsClient (this interface)
 *         |
 *         +---- MockTdmsClient  (current prototype)
 *         |
 *         +---- ApiTdmsClient   (future FastAPI service)
 *
 * Every method is asynchronous so that moving from the in-browser prototype to
 * HTTPS calls against FastAPI requires no change in the pages.
 */

/** Who is performing the action. Used for permission checks and activity records. */
export interface ActionContext {
  actor: TdmsUser;
}

/** SRS 2.3: a delete, restore or override action must carry an approved reason. */
export interface ReasonedRequest {
  reason: ReasonCode;
  reasonDetail?: string;
}

export interface CourseFilters {
  collegeId?: string;
  campusId?: string;
  search?: string;
  courseStatus?: string;
}

export interface QualificationUnitFilters {
  collegeId?: string;
  campusId?: string;
  qualificationCode?: string;
  search?: string;
}

export type CourseInput = Omit<CourseRecord, 'id' | 'isDeleted' | 'deletion'>;
// `deliveryOrder` is not an input. The teaching order comes from an approved
// rolling timetable, never from someone typing a number - and once groups run
// their own cycle of the same units, one number could only be right for one
// group. The row type still carries it, because the API still returns it.
// What a person actually decides when adding a unit to a qualification.
//
// A complete `qualification_units` row is two columns: the qualification and the
// unit. Everything else is generated or optional, so nothing else is asked for.
//
// `recordId` is not an input and never was - there is no `record_id` column. The
// list adapter renders it from the row's own primary key, and the form used to
// ask a person to invent one that the API then ignored.
//
// `collegeId` and `campusId` are not inputs either. Unit membership belongs to
// the qualification, not to a place - the model says so ("one sequence per
// qualification, not per campus") - so a unit added once applies everywhere that
// qualification is offered.
export type QualificationUnitInput = Omit<
  QualificationUnitSequence,
  'id' | 'isDeleted' | 'deletion' | 'deliveryOrder' | 'recordId' | 'collegeId' | 'campusId'
>;
export type UserInput = Omit<TdmsUser, 'id' | 'lastSignInAt'>;


export interface TdmsClient {
  /** Identifies which implementation is active, so the UI can label demo mode. */
  readonly mode: 'mock' | 'api';

  // -- Reference data ------------------------------------------------------
  getReferenceData(): Promise<ReferenceDataBundle>;

  // -- Student Data --------------------------------------------------------
  // Student records and the bulk import are **not** on this interface. They
  // live in PostgreSQL and are reached through `services/students-api.ts`,
  // which talks to the API directly (25 August 2026). There is no mock
  // implementation of them, and no student is held in browser storage.

  // -- Trainer Data --------------------------------------------------------
  // Trainer records, their locations and their units are **not** on this
  // interface, for the same reason students are not. They live in PostgreSQL
  // and are reached through `services/trainers-api.ts` (27 August 2026). There
  // is no mock implementation of them, and no trainer is held in browser
  // storage.

  // -- College and Course Reference Data -----------------------------------
  listCourses(filters: CourseFilters): Promise<CourseRecord[]>;
  createCourse(input: CourseInput, context: ActionContext): Promise<CourseRecord>;
  updateCourse(id: string, input: CourseInput, context: ActionContext): Promise<CourseRecord>;
  deleteCourse(id: string, request: ReasonedRequest, context: ActionContext): Promise<void>;
  listDeletedCourses(): Promise<CourseRecord[]>;
  restoreCourse(id: string, request: ReasonedRequest, context: ActionContext): Promise<CourseRecord>;

  listQualificationUnitSequences(filters: QualificationUnitFilters): Promise<QualificationUnitSequence[]>;
  createQualificationUnit(input: QualificationUnitInput, context: ActionContext): Promise<QualificationUnitSequence>;
  updateQualificationUnit(
    id: string,
    input: QualificationUnitInput,
    context: ActionContext,
  ): Promise<QualificationUnitSequence>;
  deleteQualificationUnit(id: string, request: ReasonedRequest, context: ActionContext): Promise<void>;
  listDeletedQualificationUnits(): Promise<QualificationUnitSequence[]>;
  restoreQualificationUnit(
    id: string,
    request: ReasonedRequest,
    context: ActionContext,
  ): Promise<QualificationUnitSequence>;

  // -- Administration ------------------------------------------------------
  listUsers(): Promise<TdmsUser[]>;
  createUser(input: UserInput, context: ActionContext): Promise<TdmsUser>;
  updateUser(id: string, input: UserInput, context: ActionContext): Promise<TdmsUser>;

  // -- Access requests (Access Model v1.1) ---------------------------------
  /** The caller's own pending request, or null. */
  getMyAccessRequest(userId: string): Promise<AccessRequest | null>;
  submitAccessRequest(
    requestedRole: RequestableRole,
    context: ActionContext,
  ): Promise<{ request: AccessRequest; notification: NotificationOutcome }>;
  cancelAccessRequest(id: string, context: ActionContext): Promise<AccessRequest>;

  /** Super Admin only. Every request, newest first. */
  listAccessRequests(): Promise<AccessRequest[]>;
  /**
   * Approving applies the new access level and closes the request together.
   * The first decision wins: a second attempt must be refused, not silently
   * overwrite the first.
   */
  approveAccessRequest(id: string, context: ActionContext): Promise<AccessRequest>;
  denyAccessRequest(id: string, context: ActionContext): Promise<AccessRequest>;

  /** Super Admin only. Direct role change, independent of the request system. */
  changeUserRole(id: string, role: TdmsRole, context: ActionContext): Promise<TdmsUser>;
  changeUserAccountStatus(
    id: string,
    status: AccountStatus,
    context: ActionContext,
  ): Promise<TdmsUser>;

  getDashboardOverview(): Promise<DashboardOverview>;

  listActivityRecords(filters: ActivityFilters): Promise<UserActivityRecord[]>;
  /** LOG-01: used for actions the pages perform directly, such as export. */
  recordActivity(
    record: Omit<UserActivityRecord, 'activityRecordNumber' | 'dateTime'>,
  ): Promise<UserActivityRecord>;

  // -- Prototype maintenance ----------------------------------------------
  /** Restores the seeded demo dataset. Development tools only. */
  resetPrototypeData(): Promise<void>;
}
