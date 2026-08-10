import type { IsoDate, IsoDateTime, SoftDeletable } from './common';
import type { UocType } from './reference';

/** SRS 5.3 - Mode of Delivery is a controlled selection. */
export type ModeOfDelivery = 'Physical' | 'Virtual';

/**
 * A day-and-time slot, e.g. Monday 09:00-13:00.
 * `Days and Times` fields in the SRS are stored as a list of these slots so a
 * unit can be delivered on more than one day.
 */
export interface DayTimeSlot {
  day: Weekday;
  startTime: string;
  endTime: string;
}

export type Weekday = 'Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday';

export const WEEKDAYS: Weekday[] = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];

/**
 * SRS 5.3 Timetable fields, grouped exactly as Figures 3A-3E:
 * basic class identification, unit identification, theory, practical, MSCRIS
 * and remarks.
 */
export interface TimetableSession extends SoftDeletable {
  id: string;
  /** Human-readable timetable record number used in confirmations and activity records. */
  recordNumber: string;

  // Basic details
  collegeId: string;
  campusId: string;
  qualificationCode: string;
  qualificationName: string;
  durationInWeeks: number;
  group: string;
  classroomSize: number;

  // Unit details
  uocCode: string;
  uocTitle: string;
  uocType: UocType;
  modeOfDelivery: ModeOfDelivery;
  uocStartDate: IsoDate;
  uocEndDate: IsoDate;

  // Theory
  theoryDaysAndTimes: DayTimeSlot[];
  theoryClassroomName: string;
  theoryClassroomCapacity: number;
  theoryTrainerId: string;

  // Practical
  practicalClassroomName: string;
  practicalClassroomCapacity: number;
  practicalDaysAndTimes: DayTimeSlot[];
  practicalTrainerId: string;

  // MSCRIS - OD-11 keeps the full term and business purpose open.
  mscrisClassName: string;
  mscrisDaysAndTimes: DayTimeSlot[];
  mscrisTrainerId: string;

  // Other
  remarks: string;

  createdAt: IsoDateTime;
  updatedAt: IsoDateTime;
  /** Set when a clash was saved under an approved override (TT-06). */
  overrideReasonDetail?: string;
}

export type TimetableInput = Omit<
  TimetableSession,
  'id' | 'recordNumber' | 'createdAt' | 'updatedAt' | 'isDeleted' | 'deletion'
>;

export interface TimetableFilters {
  fromDate?: IsoDate;
  toDate?: IsoDate;
  collegeId?: string;
  campusId?: string;
  qualificationCode?: string;
  group?: string;
}

/** Named check displayed by the timetable ValidationPanel. */
export type TimetableCheckId =
  | 'TRAINER_CLASH'
  | 'FACILITY_CLASH'
  | 'STUDENT_GROUP_CLASH'
  | 'QUALIFICATION_DURATION'
  | 'UNIT_SEQUENCE'
  | 'BREAK_RULES';
