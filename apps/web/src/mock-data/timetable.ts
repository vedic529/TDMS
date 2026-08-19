import type { DayTimeSlot, TimetableSession } from '@/types/timetable';
import { MOCK_CAMPUSES } from './colleges';
import { MOCK_FACILITIES, MSCRIS_CLASS_NAME } from './facilities';
import { MOCK_TRAINERS } from './trainers';
import { qualificationByCode } from './qualifications';
import { anchorDate, anchorDateTime } from './anchor';

interface GroupSeed {
  group: string;
  campusId: string;
  qualificationCode: string;
  durationInWeeks: number;
  classroomSize: number;
  /** Offset in days from the demo anchor for the first unit. */
  startOffsetDays: number;
  /** Number of consecutive units to schedule for this group. */
  unitCount: number;
  weeksPerUnit: number;
}

const GROUP_SEEDS: GroupSeed[] = [
  {
    group: 'BSB60420-HOB-AUG2026',
    campusId: 'cam-aibt-hobart',
    qualificationCode: 'BSB60420',
    durationInWeeks: 52,
    classroomSize: 22,
    startOffsetDays: -21,
    unitCount: 4,
    weeksPerUnit: 4,
  },
  {
    group: 'BSB50420-MEL-AUG2026',
    campusId: 'cam-aibt-melbourne',
    qualificationCode: 'BSB50420',
    durationInWeeks: 52,
    classroomSize: 28,
    startOffsetDays: -14,
    unitCount: 4,
    weeksPerUnit: 3,
  },
  {
    group: 'SIT30821-MEL-AUG2026',
    campusId: 'cam-aibt-melbourne',
    qualificationCode: 'SIT30821',
    durationInWeeks: 52,
    classroomSize: 16,
    startOffsetDays: -7,
    unitCount: 4,
    weeksPerUnit: 3,
  },
  {
    group: 'BSB50820-SYD-AUG2026',
    campusId: 'cam-aibti-sydney',
    qualificationCode: 'BSB50820',
    durationInWeeks: 26,
    classroomSize: 25,
    startOffsetDays: 0,
    unitCount: 3,
    weeksPerUnit: 3,
  },
  {
    group: 'SIT50422-ADL-AUG2026',
    campusId: 'cam-aibti-adelaide',
    qualificationCode: 'SIT50422',
    durationInWeeks: 78,
    classroomSize: 18,
    startOffsetDays: 7,
    unitCount: 3,
    weeksPerUnit: 4,
  },
  {
    group: 'AUR30620-PER-AUG2026',
    campusId: 'cam-avi-perth',
    qualificationCode: 'AUR30620',
    durationInWeeks: 104,
    classroomSize: 14,
    startOffsetDays: 14,
    unitCount: 2,
    weeksPerUnit: 5,
  },
];

const THEORY_SLOT_PATTERNS: DayTimeSlot[][] = [
  [
    { day: 'Monday', startTime: '09:00', endTime: '13:00' },
    { day: 'Tuesday', startTime: '09:00', endTime: '13:00' },
  ],
  [
    { day: 'Wednesday', startTime: '09:00', endTime: '13:00' },
    { day: 'Thursday', startTime: '09:00', endTime: '13:00' },
  ],
  [
    { day: 'Tuesday', startTime: '13:30', endTime: '17:30' },
    { day: 'Wednesday', startTime: '13:30', endTime: '17:30' },
  ],
];

const PRACTICAL_SLOT_PATTERNS: DayTimeSlot[][] = [
  [{ day: 'Thursday', startTime: '08:00', endTime: '14:00' }],
  [{ day: 'Friday', startTime: '08:00', endTime: '14:00' }],
  [{ day: 'Monday', startTime: '14:00', endTime: '18:00' }],
];

const MSCRIS_SLOT_PATTERNS: DayTimeSlot[][] = [
  [{ day: 'Friday', startTime: '18:00', endTime: '20:00' }],
  [{ day: 'Thursday', startTime: '18:00', endTime: '20:00' }],
];

function trainerForQualification(qualificationCode: string, campusId: string, offset: number): string {
  const eligible = MOCK_TRAINERS.filter(
    (trainer) => trainer.isActive && trainer.qualificationsCanTeach.includes(qualificationCode),
  );
  const onCampus = eligible.filter((trainer) => trainer.campusId === campusId);
  const pool = onCampus.length > 0 ? onCampus : eligible;
  if (pool.length === 0) return '';
  return pool[offset % pool.length].trainerId;
}

function facilityForCampus(campusId: string, type: 'classroom' | 'practical', offset: number) {
  const pool = MOCK_FACILITIES.filter(
    (facility) =>
      facility.campusId === campusId &&
      facility.isActive &&
      (type === 'classroom'
        ? facility.facilityType === 'Classroom' || facility.facilityType === 'Computer Lab'
        : facility.facilityType === 'Commercial Kitchen' || facility.facilityType === 'Workshop'),
  );
  if (pool.length === 0) return undefined;
  return pool[offset % pool.length];
}

let sequence = 0;

function buildSession(seed: GroupSeed, unitIndex: number): TimetableSession | null {
  const definition = qualificationByCode(seed.qualificationCode);
  const campus = MOCK_CAMPUSES.find((entry) => entry.id === seed.campusId);
  if (!definition || !campus) return null;

  const unit = definition.units[unitIndex];
  if (!unit) return null;

  const startOffset = seed.startOffsetDays + unitIndex * seed.weeksPerUnit * 7;
  const uocStartDate = anchorDate(startOffset);
  const uocEndDate = anchorDate(startOffset + seed.weeksPerUnit * 7 - 3);

  const theoryFacility = facilityForCampus(seed.campusId, 'classroom', unitIndex);
  const practicalFacility = facilityForCampus(seed.campusId, 'practical', unitIndex);
  const requiresPractical = unit.uocType === 'Theory and Practical';

  sequence += 1;

  return {
    id: `tt-${seed.group.toLowerCase()}-${unit.unitCode.toLowerCase()}`,
    recordNumber: `TT-${String(sequence).padStart(5, '0')}`,
    collegeId: campus.collegeId,
    campusId: campus.id,
    qualificationCode: seed.qualificationCode,
    qualificationName: definition.qualificationTitle,
    durationInWeeks: seed.durationInWeeks,
    group: seed.group,
    classroomSize: seed.classroomSize,

    uocCode: unit.unitCode,
    uocTitle: unit.unitTitle,
    uocType: unit.uocType,
    modeOfDelivery: unitIndex % 4 === 3 ? 'Virtual' : 'Physical',
    uocStartDate,
    uocEndDate,

    theoryDaysAndTimes: THEORY_SLOT_PATTERNS[unitIndex % THEORY_SLOT_PATTERNS.length],
    theoryClassroomName: theoryFacility?.facilityReference ?? '',
    theoryClassroomCapacity: theoryFacility?.capacity ?? 0,
    theoryTrainerId: trainerForQualification(seed.qualificationCode, seed.campusId, unitIndex),

    practicalClassroomName: requiresPractical ? (practicalFacility?.facilityReference ?? '') : '',
    practicalClassroomCapacity: requiresPractical ? (practicalFacility?.capacity ?? 0) : 0,
    practicalDaysAndTimes: requiresPractical
      ? PRACTICAL_SLOT_PATTERNS[unitIndex % PRACTICAL_SLOT_PATTERNS.length]
      : [],
    practicalTrainerId: requiresPractical
      ? trainerForQualification(seed.qualificationCode, seed.campusId, unitIndex + 1)
      : '',

    mscrisClassName: unitIndex % 2 === 0 ? MSCRIS_CLASS_NAME : '',
    mscrisDaysAndTimes: unitIndex % 2 === 0 ? MSCRIS_SLOT_PATTERNS[unitIndex % MSCRIS_SLOT_PATTERNS.length] : [],
    mscrisTrainerId:
      unitIndex % 2 === 0 ? trainerForQualification(seed.qualificationCode, seed.campusId, unitIndex + 2) : '',

    remarks: unitIndex === 0 ? 'First unit of the group schedule.' : '',

    createdAt: anchorDateTime(-35, 10, 0),
    updatedAt: anchorDateTime(-35, 10, 0),
    isDeleted: false,
  } satisfies TimetableSession;
}

export const MOCK_TIMETABLE_SESSIONS: TimetableSession[] = GROUP_SEEDS.flatMap((seed) =>
  Array.from({ length: seed.unitCount }, (_, unitIndex) => buildSession(seed, unitIndex)).filter(
    (session): session is TimetableSession => session !== null,
  ),
);

/** Distinct group values used by the timetable filter bar. */
export const MOCK_GROUPS = GROUP_SEEDS.map((seed) => seed.group);

export const TIME_OPTIONS = [
  '07:00',
  '08:00',
  '08:30',
  '09:00',
  '10:00',
  '11:00',
  '12:00',
  '13:00',
  '13:30',
  '14:00',
  '15:00',
  '16:00',
  '17:00',
  '17:30',
  '18:00',
  '19:00',
  '20:00',
  '21:00',
];
