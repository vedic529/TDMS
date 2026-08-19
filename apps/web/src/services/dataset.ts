import type {
  Campus,
  College,
  CourseRecord,
  Facility,
  QualificationOffering,
  QualificationUnitSequence,
} from '@/types/reference';
import type { StudentRecord } from '@/types/student';
import type { TimetableSession } from '@/types/timetable';
import type { TrainerRecord } from '@/types/trainer';
import type { AccessRequest, TdmsUser } from '@/types/auth';
import type { UserActivityRecord } from '@/types/activity';
import type { ImportBatch } from '@/types/import';

/**
 * The complete shape held by the prototype data store.
 * The future FastAPI service returns the same record shapes, so page code does
 * not change when `ApiTdmsClient` replaces `MockTdmsClient`.
 */
export interface TdmsDataset {
  colleges: College[];
  campuses: Campus[];
  qualificationOfferings: QualificationOffering[];
  qualificationUnitSequences: QualificationUnitSequence[];
  courses: CourseRecord[];
  facilities: Facility[];
  trainers: TrainerRecord[];
  students: StudentRecord[];
  timetableSessions: TimetableSession[];
  users: TdmsUser[];
  /** Access Model v1.1 role requests, newest last. */
  accessRequests: AccessRequest[];
  activityRecords: UserActivityRecord[];
  importBatches: ImportBatch[];
}

/** Reference data bundle requested once per page load. */
export interface ReferenceDataBundle {
  colleges: College[];
  campuses: Campus[];
  qualificationOfferings: QualificationOffering[];
  qualificationUnitSequences: QualificationUnitSequence[];
  facilities: Facility[];
  trainers: TrainerRecord[];
  groups: string[];
}
