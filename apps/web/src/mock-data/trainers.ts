import type { TrainerRecord } from '@/types/trainer';
import { qualificationByCode } from './qualifications';

interface TrainerSeed {
  trainerId: string;
  trainerName: string;
  campusId: string;
  trainerCampus: string;
  location: string;
  locationType: TrainerRecord['locationType'];
  workingTime: string;
  deliveryType: TrainerRecord['deliveryType'];
  weekdays: [
    TrainerRecord['monday'],
    TrainerRecord['tuesday'],
    TrainerRecord['wednesday'],
    TrainerRecord['thursday'],
    TrainerRecord['friday'],
  ];
  qualifications: string[];
  isActive?: boolean;
}

const P = 'Physical' as const;
const V = 'Virtual' as const;
const N = 'Not Available' as const;

const TRAINER_SEEDS: TrainerSeed[] = [
  {
    trainerId: 'TRN-0001',
    trainerName: 'Azmal Hossen Khokan',
    campusId: 'cam-aibt-hobart',
    trainerCampus: 'AIBT Global - Hobart',
    location: 'Hobart',
    locationType: 'Campus',
    workingTime: '09:00 - 17:00',
    deliveryType: 'Theory',
    weekdays: [P, P, P, V, N],
    qualifications: ['BSB60420', 'BSB50420'],
  },
  {
    trainerId: 'TRN-0002',
    trainerName: 'Ertajul Noorani',
    campusId: 'cam-aibt-hobart',
    trainerCampus: 'AIBT Global - Hobart',
    location: 'Hobart',
    locationType: 'Campus',
    workingTime: '09:00 - 17:00',
    deliveryType: 'Theory',
    weekdays: [V, P, P, P, P],
    qualifications: ['BSB60420', 'BSB80120'],
  },
  {
    trainerId: 'TRN-0003',
    trainerName: 'Priya Raghavan',
    campusId: 'cam-aibt-melbourne',
    trainerCampus: 'AIBT Global - Melbourne',
    location: 'Melbourne',
    locationType: 'Campus',
    workingTime: '08:30 - 16:30',
    deliveryType: 'Theory',
    weekdays: [P, P, N, P, P],
    qualifications: ['BSB50420', 'BSB50820'],
  },
  {
    trainerId: 'TRN-0004',
    trainerName: 'Daniel Okafor',
    campusId: 'cam-aibt-melbourne',
    trainerCampus: 'AIBT Global - Melbourne',
    location: 'Melbourne',
    locationType: 'Kitchen',
    workingTime: '07:00 - 15:00',
    deliveryType: 'Practical',
    weekdays: [P, P, P, N, N],
    qualifications: ['SIT30821', 'SIT50422'],
  },
  {
    trainerId: 'TRN-0005',
    trainerName: 'Mei Ling Chan',
    campusId: 'cam-aibt-melbourne',
    trainerCampus: 'AIBT Global - Melbourne',
    location: 'Melbourne',
    locationType: 'Campus',
    workingTime: '10:00 - 18:00',
    deliveryType: 'Theory and Practical',
    weekdays: [N, P, P, P, P],
    qualifications: ['SIT50422', 'CHC50125'],
  },
  {
    trainerId: 'TRN-0006',
    trainerName: 'Rajesh Kumar Menon',
    campusId: 'cam-aibt-brisbane',
    trainerCampus: 'AIBT Global - Brisbane',
    location: 'Brisbane',
    locationType: 'Campus',
    workingTime: '09:00 - 17:00',
    deliveryType: 'Theory',
    weekdays: [P, P, P, P, N],
    qualifications: ['BSB50420', 'BSB80120', 'CHC33021'],
  },
  {
    trainerId: 'TRN-0007',
    trainerName: 'Sarah Whitfield',
    campusId: 'cam-aibti-sydney',
    trainerCampus: 'AIBT International - Sydney',
    location: 'Sydney',
    locationType: 'Campus',
    workingTime: '09:00 - 17:00',
    deliveryType: 'Theory',
    weekdays: [P, V, P, P, V],
    qualifications: ['BSB50420', 'BSB60420', 'BSB50820'],
  },
  {
    trainerId: 'TRN-0008',
    trainerName: 'Nguyen Van Hai',
    campusId: 'cam-aibti-sydney',
    trainerCampus: 'AIBT International - Sydney',
    location: 'Sydney',
    locationType: 'Virtual',
    workingTime: '13:00 - 21:00',
    deliveryType: 'Theory',
    weekdays: [V, V, V, V, N],
    qualifications: ['CHC50125', 'CHC33021'],
  },
  {
    trainerId: 'TRN-0009',
    trainerName: 'Amara Diallo',
    campusId: 'cam-aibti-adelaide',
    trainerCampus: 'AIBT International - Adelaide',
    location: 'Adelaide',
    locationType: 'Kitchen',
    workingTime: '07:30 - 15:30',
    deliveryType: 'Practical',
    weekdays: [P, P, N, P, P],
    qualifications: ['SIT30821', 'SIT50422'],
  },
  {
    trainerId: 'TRN-0010',
    trainerName: 'James Patterson',
    campusId: 'cam-avi-perth',
    trainerCampus: 'Australian Vocational Institute - Perth',
    location: 'Perth',
    locationType: 'Workshop',
    workingTime: '08:00 - 16:00',
    deliveryType: 'Theory and Practical',
    weekdays: [P, P, P, P, P],
    qualifications: ['AUR30620', 'BSB50820'],
  },
  {
    trainerId: 'TRN-0011',
    trainerName: 'Fatima Al-Rashid',
    campusId: 'cam-avi-melbourne',
    trainerCampus: 'Australian Vocational Institute - Melbourne CBD',
    location: 'Melbourne',
    locationType: 'Campus',
    workingTime: '09:00 - 17:00',
    deliveryType: 'Theory',
    weekdays: [P, P, V, N, P],
    qualifications: ['BSB50420', 'BSB60420', 'CHC33021'],
  },
  {
    trainerId: 'TRN-0012',
    trainerName: 'Gregory Hale',
    campusId: 'cam-aibt-hobart',
    trainerCampus: 'AIBT Global - Hobart',
    location: 'Hobart',
    locationType: 'Kitchen',
    workingTime: '07:00 - 15:00',
    deliveryType: 'Practical',
    weekdays: [P, P, P, N, N],
    qualifications: ['FBP30321', 'SIT30821'],
    // TRN-04: an inactive trainer stays visible for historical records but must
    // not be selectable for a new timetable assignment.
    isActive: false,
  },
];

export const MOCK_TRAINERS: TrainerRecord[] = TRAINER_SEEDS.map((seed, index) => ({
  id: `trn-${seed.trainerId.toLowerCase()}`,
  serialNumber: index + 1,
  trainerId: seed.trainerId,
  trainerName: seed.trainerName,
  trainerCampus: seed.trainerCampus,
  campusId: seed.campusId,
  location: seed.location,
  locationType: seed.locationType,
  workingTime: seed.workingTime,
  deliveryType: seed.deliveryType,
  monday: seed.weekdays[0],
  tuesday: seed.weekdays[1],
  wednesday: seed.weekdays[2],
  thursday: seed.weekdays[3],
  friday: seed.weekdays[4],
  qualificationsCanTeach: seed.qualifications,
  unitsCanTeach: seed.qualifications.flatMap(
    (code) => qualificationByCode(code)?.units.map((unit) => unit.unitCode) ?? [],
  ),
  isActive: seed.isActive ?? true,
  isDeleted: false,
}));

export const WORKING_TIME_OPTIONS = [
  '07:00 - 15:00',
  '07:30 - 15:30',
  '08:00 - 16:00',
  '08:30 - 16:30',
  '09:00 - 17:00',
  '10:00 - 18:00',
  '13:00 - 21:00',
];

export const LOCATION_TYPE_OPTIONS: TrainerRecord['locationType'][] = ['Campus', 'Kitchen', 'Workshop', 'Virtual'];

export const TRAINER_DELIVERY_TYPE_OPTIONS: TrainerRecord['deliveryType'][] = [
  'Theory',
  'Practical',
  'Theory and Practical',
];

export const WEEKDAY_AVAILABILITY_OPTIONS: TrainerRecord['monday'][] = ['Not Available', 'Physical', 'Virtual'];
