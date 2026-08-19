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
import type { StudentRecord, StudentInput, StudentFilters } from '@/types/student';
import type { TimetableSession, TimetableInput, TimetableFilters } from '@/types/timetable';
import type { TrainerRecord, TrainerInput, TrainerFilters } from '@/types/trainer';
import type { CourseRecord, QualificationUnitSequence } from '@/types/reference';
import type { ImportBatch, ImportResult, StagedStudentRow } from '@/types/import';
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
export type QualificationUnitInput = Omit<QualificationUnitSequence, 'id' | 'isDeleted' | 'deletion'>;
export type UserInput = Omit<TdmsUser, 'id' | 'lastSignInAt'>;

export interface StageImportRequest {
  fileName: string;
  fileSizeBytes: number;
  rows: Array<Record<string, string>>;
}

export interface TdmsClient {
  /** Identifies which implementation is active, so the UI can label demo mode. */
  readonly mode: 'mock' | 'api';

  // -- Reference data ------------------------------------------------------
  getReferenceData(): Promise<ReferenceDataBundle>;

  // -- Timetable View and Management ---------------------------------------
  listTimetableSessions(filters: TimetableFilters): Promise<TimetableSession[]>;
  createTimetableSession(input: TimetableInput, context: ActionContext): Promise<TimetableSession>;
  updateTimetableSession(id: string, input: TimetableInput, context: ActionContext): Promise<TimetableSession>;
  deleteTimetableSession(id: string, request: ReasonedRequest, context: ActionContext): Promise<void>;
  listDeletedTimetableSessions(): Promise<TimetableSession[]>;
  restoreTimetableSession(id: string, request: ReasonedRequest, context: ActionContext): Promise<TimetableSession>;

  // -- Single Student Entry ------------------------------------------------
  listStudents(filters: StudentFilters): Promise<StudentRecord[]>;
  findStudentByStudentId(studentId: string): Promise<StudentRecord | null>;
  isStudentIdAvailable(studentId: string, excludeRecordId?: string): Promise<boolean>;
  createStudent(input: StudentInput, context: ActionContext): Promise<StudentRecord>;
  updateStudent(id: string, input: StudentInput, context: ActionContext): Promise<StudentRecord>;
  deleteStudent(id: string, request: ReasonedRequest, context: ActionContext): Promise<void>;
  listDeletedStudents(): Promise<StudentRecord[]>;
  restoreStudent(id: string, request: ReasonedRequest, context: ActionContext): Promise<StudentRecord>;

  // -- Bulk Student Import -------------------------------------------------
  /** Loads rows into the staging area. Nothing is written to the database (BULK-02). */
  stageImport(request: StageImportRequest, context: ActionContext): Promise<ImportBatch>;
  /** Re-runs validation over corrected or excluded staged rows (BULK-06). */
  revalidateImport(batch: ImportBatch): Promise<ImportBatch>;
  /** Writes the confirmed staged set in one transaction (BULK-08). */
  saveImport(batch: ImportBatch, context: ActionContext): Promise<ImportResult>;

  // -- Trainer Data --------------------------------------------------------
  listTrainers(filters: TrainerFilters): Promise<TrainerRecord[]>;
  createTrainer(input: TrainerInput, context: ActionContext): Promise<TrainerRecord>;
  updateTrainer(id: string, input: TrainerInput, context: ActionContext): Promise<TrainerRecord>;
  deleteTrainer(id: string, request: ReasonedRequest, context: ActionContext): Promise<void>;
  listDeletedTrainers(): Promise<TrainerRecord[]>;
  restoreTrainer(id: string, request: ReasonedRequest, context: ActionContext): Promise<TrainerRecord>;

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

export type { StagedStudentRow };
