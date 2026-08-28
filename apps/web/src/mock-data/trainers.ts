/**
 * Trainer option lists.
 *
 * **No trainer records live here any more (27 August 2026).** Trainer Data is
 * served by the database through `services/trainers-api.ts`, exactly as student
 * records were moved on 25 August. What remains is the four option lists the
 * forms offer, which are presentation choices rather than records.
 */

import type { TrainerRecord } from '@/types/trainer';

export const WORKING_TIME_OPTIONS = [
  '07:00 - 15:00',
  '07:30 - 15:30',
  '08:00 - 16:00',
  '08:30 - 16:30',
  '09:00 - 17:00',
  '10:00 - 18:00',
  '13:00 - 21:00',
];

export const LOCATION_TYPE_OPTIONS: TrainerRecord['locationType'][] = [
  'Campus',
  'Kitchen',
  'Workshop',
  'Virtual',
];

/**
 * "Theory and Practical" is no longer a workaround: `class_type` holds it as a
 * real value since the trainer backend migration.
 */
export const TRAINER_DELIVERY_TYPE_OPTIONS: TrainerRecord['classType'][] = [
  'Theory',
  'Practical',
  'Theory and Practical',
];

export const WEEKDAY_AVAILABILITY_OPTIONS: TrainerRecord['monday'][] = [
  'Not Available',
  'Physical',
  'Virtual',
];
