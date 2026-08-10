import type { SoftDeletable } from './common';

/** Approved college reference value (SRS 10.1 "College and campus"). */
export interface College {
  id: string;
  collegeShortName: string;
  collegeFullName: string;
  isActive: boolean;
  /** Domain used to generate the proposed College Email (SRS 6.3). */
  emailDomain: string;
}

export interface Campus {
  id: string;
  collegeId: string;
  campusName: string;
  campusLocation: string;
  /** Student "State" is generated from the selected campus (SRS 6.3). */
  state: string;
  isActive: boolean;
}

/** SRS 9.3 - Page 4A Course Data fields. */
export interface CourseRecord extends SoftDeletable {
  id: string;
  collegeId: string;
  campusId: string;
  courseCode: string;
  vetCode: string;
  courseStatus: CourseStatus;
  courseName: string;
  courseLevel: string;
  fieldOfEducationBroad: string;
  fieldOfEducationNarrow: string;
  courseSector: string;
  durationInWeeks: number;
  totalCourseCost: number;
  location: string;
}

/** COL-05: inactive and superseded values stay visible but are not selectable for new records. */
export type CourseStatus = 'Active' | 'Inactive' | 'Superseded';

/** SRS 9.4 - Page 4B Qualification and Unit Sequence Data fields. */
export interface QualificationUnitSequence extends SoftDeletable {
  id: string;
  recordId: string;
  qualificationCode: string;
  qualificationTitle: string;
  unitCode: string;
  unitTitle: string;
  sequenceId: number;
  /** Used only to filter Page 4B by college/campus. */
  collegeId: string;
  campusId: string;
  /** SRS 5.3 "UoC Type": theory only, or theory and practical. */
  uocType: UocType;
}

export type UocType = 'Theory' | 'Theory and Practical';

/**
 * TT-15 / COL-09 / OD-09: facility data is required for clash and capacity
 * checking, but the facility fields, source data and whether a separate
 * facility maintenance page is needed remain open decisions. TDMS therefore
 * stores the minimum set named in TT-15 and does not add a fifth main page.
 */
export interface Facility {
  id: string;
  facilityReference: string;
  campusId: string;
  facilityType: FacilityType;
  capacity: number;
  isActive: boolean;
}

export type FacilityType = 'Classroom' | 'Commercial Kitchen' | 'Workshop' | 'Computer Lab' | 'Virtual Classroom';

/** Approved college + campus + qualification offering used by dependent dropdowns. */
export interface QualificationOffering {
  id: string;
  collegeId: string;
  campusId: string;
  qualificationCode: string;
  qualificationTitle: string;
  /** Approved Duration in Weeks options for this offering (SRS 5.3). */
  durationOptions: number[];
  isActive: boolean;
}
