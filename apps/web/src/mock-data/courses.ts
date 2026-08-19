import type { CourseRecord } from '@/types/reference';
import { MOCK_CAMPUSES } from './colleges';
import { MOCK_QUALIFICATION_OFFERINGS, qualificationByCode } from './qualifications';

/**
 * SRS 9.3 - Page 4A Course Data.
 * One course record per approved college/campus qualification offering.
 */
export const MOCK_COURSES: CourseRecord[] = MOCK_QUALIFICATION_OFFERINGS.map((offering, index) => {
  const definition = qualificationByCode(offering.qualificationCode)!;
  const campus = MOCK_CAMPUSES.find((entry) => entry.id === offering.campusId)!;
  // A small number of records are marked Superseded/Inactive so COL-05
  // (historical values remain visible but are not selectable) can be reviewed.
  const courseStatus = index % 17 === 5 ? 'Superseded' : index % 13 === 7 ? 'Inactive' : 'Active';

  return {
    id: `crs-${offering.campusId}-${offering.qualificationCode}`,
    collegeId: offering.collegeId,
    campusId: offering.campusId,
    courseCode: `${offering.qualificationCode}-${campus.state}`,
    qualificationCode: offering.qualificationCode,
    courseStatus,
    qualificationTitle: definition.qualificationTitle,
    courseLevel: definition.courseLevel,
    fieldOfEducationBroad: definition.fieldOfEducationBroad,
    fieldOfEducationNarrow: definition.fieldOfEducationNarrow,
    courseSector: definition.courseSector,
    durationInWeeks: definition.durationOptions[definition.durationOptions.length - 1],
    totalCourseCost: definition.totalCourseCost,
    isDeleted: false,
  } satisfies CourseRecord;
});

export const COURSE_STATUS_OPTIONS = ['Active', 'Inactive', 'Superseded'] as const;

export const COURSE_LEVEL_OPTIONS = [
  'Certificate II',
  'Certificate III',
  'Certificate IV',
  'Diploma',
  'Advanced Diploma',
  'Graduate Diploma',
];

export const COURSE_SECTOR_OPTIONS = ['VET', 'Higher Education', 'ELICOS'];

export const FIELD_OF_EDUCATION_BROAD_OPTIONS = [
  'Management and Commerce',
  'Food, Hospitality and Personal Services',
  'Society and Culture',
  'Engineering and Related Technologies',
  'Information Technology',
  'Health',
];

export const FIELD_OF_EDUCATION_NARROW_OPTIONS = [
  'Business and Management',
  'Food and Hospitality',
  'Human Welfare Studies and Services',
  'Automotive Engineering and Technology',
  'Computer Science',
  'Nursing',
];
