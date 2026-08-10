import type { Campus, College } from '@/types/reference';

/**
 * Demo reference data only.
 *
 * The college names, campus addresses and qualification codes mirror the values
 * visible in the current TDMS prototype so the interface can be reviewed
 * against familiar data. No live student, trainer or enrolment information is
 * included anywhere in this repository (DATA-06).
 */

export const MOCK_COLLEGES: College[] = [
  {
    id: 'col-aibt',
    collegeShortName: 'AIBT',
    collegeFullName: 'AIBT Global',
    isActive: true,
    emailDomain: 'aibtglobal.edu.au',
  },
  {
    id: 'col-aibti',
    collegeShortName: 'AIBTI',
    collegeFullName: 'AIBT International',
    isActive: true,
    emailDomain: 'aibtinternational.edu.au',
  },
  {
    id: 'col-avi',
    collegeShortName: 'AVI',
    collegeFullName: 'Australian Vocational Institute',
    isActive: true,
    emailDomain: 'avi.edu.au',
  },
];

export const MOCK_CAMPUSES: Campus[] = [
  {
    id: 'cam-aibt-hobart',
    collegeId: 'col-aibt',
    campusName: 'Hobart',
    campusLocation: 'Ground Floor, 132-146 Elizabeth Street, Hobart TAS 7000',
    state: 'TAS',
    isActive: true,
  },
  {
    id: 'cam-aibt-melbourne',
    collegeId: 'col-aibt',
    campusName: 'Melbourne',
    campusLocation: 'Level 5, 123 Lonsdale Street, Melbourne VIC 3000',
    state: 'VIC',
    isActive: true,
  },
  {
    id: 'cam-aibt-brisbane',
    collegeId: 'col-aibt',
    campusName: 'Brisbane',
    campusLocation: 'Level 2, 348 Edward Street, Brisbane QLD 4000',
    state: 'QLD',
    isActive: true,
  },
  {
    id: 'cam-aibti-sydney',
    collegeId: 'col-aibti',
    campusName: 'Sydney',
    campusLocation: 'Level 8, 233 Castlereagh Street, Sydney NSW 2000',
    state: 'NSW',
    isActive: true,
  },
  {
    id: 'cam-aibti-adelaide',
    collegeId: 'col-aibti',
    campusName: 'Adelaide',
    campusLocation: 'Level 3, 81 Flinders Street, Adelaide SA 5000',
    state: 'SA',
    isActive: true,
  },
  {
    id: 'cam-avi-perth',
    collegeId: 'col-avi',
    campusName: 'Perth',
    campusLocation: 'Level 1, 190 St Georges Terrace, Perth WA 6000',
    state: 'WA',
    isActive: true,
  },
  {
    id: 'cam-avi-melbourne',
    collegeId: 'col-avi',
    campusName: 'Melbourne CBD',
    campusLocation: 'Level 9, 250 Collins Street, Melbourne VIC 3000',
    state: 'VIC',
    isActive: true,
  },
];

/** SRS 6.3: Primary Country is a controlled selection with free text allowed. */
export const COUNTRY_OPTIONS = [
  'Australia',
  'Bangladesh',
  'Brazil',
  'China',
  'Colombia',
  'India',
  'Indonesia',
  'Nepal',
  'Pakistan',
  'Philippines',
  'Sri Lanka',
  'Thailand',
  'Vietnam',
];
