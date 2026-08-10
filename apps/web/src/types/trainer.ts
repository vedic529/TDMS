import type { SoftDeletable } from './common';

/** SRS 8.3 - weekday availability values. */
export type WeekdayAvailability = 'Not Available' | 'Physical' | 'Virtual';

/** SRS 8.3 - Delivery Type applies to theory or practical delivery. */
export type TrainerDeliveryType = 'Theory' | 'Practical' | 'Theory and Practical';

export type TrainerLocationType = 'Campus' | 'Kitchen' | 'Workshop' | 'Virtual';

/** SRS 8.3 Trainer Location fields + SRS 8.4 trainer qualification/unit fields. */
export interface TrainerRecord extends SoftDeletable {
  id: string;
  serialNumber: number;
  trainerId: string;
  trainerName: string;
  trainerCampus: string;
  campusId: string;
  location: string;
  locationType: TrainerLocationType;
  workingTime: string;
  deliveryType: TrainerDeliveryType;
  monday: WeekdayAvailability;
  tuesday: WeekdayAvailability;
  wednesday: WeekdayAvailability;
  thursday: WeekdayAvailability;
  friday: WeekdayAvailability;

  /** SRS 8.4 - Qualifications They Can Teach. */
  qualificationsCanTeach: string[];
  /** SRS 8.4 - Units They Can Teach. */
  unitsCanTeach: string[];

  /** TRN-04: an inactive trainer stays visible for history but is not selectable. */
  isActive: boolean;
}

export type TrainerInput = Omit<TrainerRecord, 'id' | 'serialNumber' | 'isDeleted' | 'deletion'>;

export interface TrainerFilters {
  /** TRN-01: a qualification must be selected before results are displayed. */
  qualificationCode?: string;
  campusId?: string;
  location?: string;
  deliveryType?: TrainerDeliveryType;
  status?: 'active' | 'inactive' | 'all';
  search?: string;
}
