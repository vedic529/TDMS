import type {
  Campus,
  College,
  CourseRecord,
  Facility,
  QualificationOffering,
  QualificationUnitSequence,
} from '@/types/reference';
import type { TrainerRecord } from '@/types/trainer';
import type { AccessRequest, TdmsUser } from '@/types/auth';
import type { UserActivityRecord } from '@/types/activity';

/**
 * The shape held by the prototype data store.
 *
 * **Students are not here (25 August 2026).** Student records and their bulk
 * import live in PostgreSQL and are reached through `services/students-api.ts`,
 * so neither a seeded student nor an import batch is held in browser storage.
 */
export interface TdmsDataset {
  colleges: College[];
  campuses: Campus[];
  qualificationOfferings: QualificationOffering[];
  qualificationUnitSequences: QualificationUnitSequence[];
  courses: CourseRecord[];
  facilities: Facility[];
  trainers: TrainerRecord[];
  users: TdmsUser[];
  /** Access Model v1.1 role requests, newest last. */
  accessRequests: AccessRequest[];
  activityRecords: UserActivityRecord[];
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
