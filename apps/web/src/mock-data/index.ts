import type { TdmsDataset } from '@/services/dataset';
import { MOCK_ACTIVITY_RECORDS } from './activity';
import { MOCK_CAMPUSES, MOCK_COLLEGES } from './colleges';
import { MOCK_COURSES } from './courses';
import { MOCK_FACILITIES } from './facilities';
import { MOCK_QUALIFICATION_OFFERINGS, MOCK_QUALIFICATION_UNIT_SEQUENCES } from './qualifications';
import { MOCK_STUDENTS } from './students';
import { MOCK_TIMETABLE_SESSIONS } from './timetable';
import { MOCK_TRAINERS } from './trainers';
import { MOCK_USERS } from './users';

/**
 * The complete seeded demo dataset.
 *
 * Mock data is never imported by a UI component. Pages read through
 * `TdmsClient`, so replacing `MockTdmsClient` with `ApiTdmsClient` requires no
 * change to any page.
 */
export function createSeedDataset(): TdmsDataset {
  return structuredClone({
    colleges: MOCK_COLLEGES,
    campuses: MOCK_CAMPUSES,
    qualificationOfferings: MOCK_QUALIFICATION_OFFERINGS,
    qualificationUnitSequences: MOCK_QUALIFICATION_UNIT_SEQUENCES,
    courses: MOCK_COURSES,
    facilities: MOCK_FACILITIES,
    trainers: MOCK_TRAINERS,
    students: MOCK_STUDENTS,
    timetableSessions: MOCK_TIMETABLE_SESSIONS,
    users: MOCK_USERS,
    // No seeded access requests: a request is something a real user makes.
    accessRequests: [],
    activityRecords: MOCK_ACTIVITY_RECORDS,
    importBatches: [],
  });
}

export { MOCK_COLLEGES, MOCK_CAMPUSES } from './colleges';
export { QUALIFICATION_CATALOGUE, qualificationByCode } from './qualifications';
export {
  COURSE_STATUS_OPTIONS,
  COURSE_LEVEL_OPTIONS,
  COURSE_SECTOR_OPTIONS,
  FIELD_OF_EDUCATION_BROAD_OPTIONS,
  FIELD_OF_EDUCATION_NARROW_OPTIONS,
} from './courses';
export { MSCRIS_CLASS_NAME } from './facilities';
export {
  WORKING_TIME_OPTIONS,
  LOCATION_TYPE_OPTIONS,
  TRAINER_DELIVERY_TYPE_OPTIONS,
  WEEKDAY_AVAILABILITY_OPTIONS,
} from './trainers';
export { TIME_OPTIONS } from './timetable';
export { COUNTRY_OPTIONS } from './colleges';
export { DEV_PREVIEW_USER_IDS, DEFAULT_MOCK_USER_ID } from './users';
export { IMPORT_TEMPLATE_COLUMNS, DEMO_IMPORT_CSV, DEMO_IMPORT_FILE_NAME } from './import-sample';
