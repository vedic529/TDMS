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
  trainerLocationDetails: 'Trainer Location and Details',
  trainerUnitCoverage: 'Unit Coverage',
  bulkTrainerImport: 'Bulk Import',
  referenceData: 'College and Course Reference Data',
  // Renamed 9 September 2026. The keys keep their original names so the SRS
  // page references below still line up: `courseData` is Page 4A whatever it is
  // called on screen.
  courseData: 'College Locations',
  qualificationUnitSequence: 'College Qualifications',
  facilityData: 'College Facility',
  administration: 'Administration',
  userActivityRecords: 'User Activity Records',
} as const;

/**
 * SRS page references used inside stored user activity records so an
 * administrator can trace an action back to the requirement.
 *
 * These keep the SRS wording even after the on-screen names changed. They are
 * written into stored activity records, and thousands of existing rows already
 * carry these exact strings - rewording them here would split one page's history
 * across two labels and break the trace back to the approved requirement.
 */
export const SRS_PAGE_REFERENCE = {
  timetable: 'Page 1 - Timetable View and Management',
  singleStudentEntry: 'Page 2A - Single Student Entry',
  bulkStudentImport: 'Page 2B - Bulk Student Import',
  trainerData: 'Page 3 - Trainer Data',
  courseData: 'Page 4A - Course Data',
  qualificationUnitSequence: 'Page 4B - Qualification and Unit Sequence Data',
  facilityData: 'Page 4C - Facility Data',
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
