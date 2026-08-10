/**
 * SRS 2.2 - the approved interface names.
 *
 * The same names must be used in the navigation bar, page headings,
 * requirements, testing and development tasks. Page numbers (Page 2A, Page 4B)
 * are internal SRS references only and are never shown to the user, so they are
 * kept here as `srsReference` for traceability.
 */

export const INTERFACE_NAMES = {
  login: 'Login and Authentication',
  timetable: 'Timetable View and Management',
  singleStudentEntry: 'Single Student Entry',
  bulkStudentImport: 'Bulk Student Import',
  studentData: 'Student Data',
  trainerData: 'Trainer Data',
  referenceData: 'College and Course Reference Data',
  courseData: 'Course Data',
  qualificationUnitSequence: 'Qualification and Unit Sequence Data',
  administration: 'Administration',
  userActivityRecords: 'User Activity Records',
} as const;

/**
 * SRS page references used inside stored user activity records so an
 * administrator can trace an action back to the requirement.
 */
export const SRS_PAGE_REFERENCE = {
  timetable: 'Page 1 - Timetable View and Management',
  singleStudentEntry: 'Page 2A - Single Student Entry',
  bulkStudentImport: 'Page 2B - Bulk Student Import',
  trainerData: 'Page 3 - Trainer Data',
  courseData: 'Page 4A - Course Data',
  qualificationUnitSequence: 'Page 4B - Qualification and Unit Sequence Data',
  login: 'Login and Authentication',
  administration: 'Administration',
} as const;

export type InterfaceKey = keyof typeof INTERFACE_NAMES;

/** The four primary operational work areas shown in the top navigation. */
export const PRIMARY_NAVIGATION = [
  { href: '/timetable', label: INTERFACE_NAMES.timetable, shortLabel: 'Timetable' },
  { href: '/students', label: INTERFACE_NAMES.studentData, shortLabel: 'Students' },
  { href: '/trainers', label: INTERFACE_NAMES.trainerData, shortLabel: 'Trainers' },
  { href: '/reference-data', label: INTERFACE_NAMES.referenceData, shortLabel: 'Reference Data' },
] as const;
