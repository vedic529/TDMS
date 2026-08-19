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
  /**
   * Other spellings of this campus's address that appear in source systems.
   *
   * One site is written several ways — Haymarket as both `841 George St` and
   * `Level 2, 8 Quay St`. Incoming data must resolve whichever form it uses.
   */
  sourceAddresses?: string[];
  /** Student "State" is generated from the selected campus (SRS 6.3). */
  state: string;
  isActive: boolean;
}

/**
 * SRS 9.3 - Page 4A Course Data fields.
 *
 * C-2: the SRS names are Qualification Code (the VET Code) and Qualification
 * Title (the Course Name).
 * C-3: "Location represents the Campus value", so there is no separate free-text
 * location column - it is derived from `campusId`.
 */
export interface CourseRecord extends SoftDeletable {
  id: string;
  collegeId: string;
  campusId: string;
  courseCode: string;
  qualificationCode: string;
  courseStatus: CourseStatus;
  qualificationTitle: string;
  courseLevel: string;
  fieldOfEducationBroad: string;
  fieldOfEducationNarrow: string;
  courseSector: string;
  durationInWeeks: number;
  totalCourseCost: number;
}

/**
 * COL-05 course status, as an open string.
 *
 * Not a union. The SRS says a course may be "active, inactive, superseded **or
 * in another approved status**", so the approved set lives in `course_statuses`
 * in the database and can grow without a frontend release. A closed union here
 * forced every unrecognised value into a fallback, which is how a perfectly
 * active course came to be labelled Inactive.
 *
 * The three names below are the ones the interface styles differently; any other
 * approved value renders neutrally with its own label.
 */
export type CourseStatus = string;

export const STYLED_COURSE_STATUSES = ['Active', 'Inactive', 'Superseded'] as const;

/** SRS 9.4 - Page 4B Qualification and Unit Sequence Data fields. */
export interface QualificationUnitSequence extends SoftDeletable {
  id: string;
  recordId: string;
  qualificationCode: string;
  qualificationTitle: string;
  unitCode: string;
  unitTitle: string;
  /**
   * C-1: the approved delivery sequence. SRS 8.3 states a separate "Sequence
   * ID" is not a Page 4B field - a relational table has no inherent row order,
   * so the ordinal is persisted and used for ordering, but not displayed as a
   * column. TT-08 depends on it.
   */
  deliveryOrder: number;
  /** C-4: SRS 8.3 Source URL, held on the qualification. */
  sourceUrl?: string;
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
  /** Retired codes this qualification replaced, e.g. CHC30121 for CHC30125. */
  supersededCodes?: string[];
  qualificationTitle: string;
  /** Approved Duration in Weeks options for this offering (SRS 5.3). */
  durationOptions: number[];
  isActive: boolean;
}
