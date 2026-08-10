import type { ValidationIssue, ValidationResult } from '@/types/common';
import type { DayTimeSlot, TimetableInput, TimetableSession } from '@/types/timetable';
import type { Facility, QualificationOffering, QualificationUnitSequence } from '@/types/reference';
import type { TrainerRecord, WeekdayAvailability } from '@/types/trainer';
import { nowIso, rangesOverlap, timesOverlap } from '@/lib/format';

/**
 * Timetable preview validation (TT-06 to TT-12).
 *
 * IMPORTANT — this module is deliberately split into two kinds of check:
 *
 *  1. Checks derived from approved reference data (trainer, facility and
 *     student-group clashes, facility capacity, approved duration options,
 *     approved unit sequence, inactive trainer). These produce real results.
 *
 *  2. Checks whose rules the SRS records as unresolved (break placement for
 *     26/52/78/104-week courses - OD-07; the trainer physical/virtual delivery
 *     rule - OD-10). These are displayed as "Awaiting approval" and never
 *     produce an invented pass or fail. TT-11 requires the break rules to be
 *     approved before automatic generation is released.
 *
 * The mock checks are isolated here so the real rules can replace them without
 * touching the pages.
 */

export interface TimetableValidationContext {
  /** Existing saved sessions, excluding the record being edited. */
  existingSessions: TimetableSession[];
  trainers: TrainerRecord[];
  facilities: Facility[];
  offerings: QualificationOffering[];
  unitSequences: QualificationUnitSequence[];
  /** Record id being edited, so it does not clash with itself. */
  editingId?: string;
}

type SlotKind = 'Theory' | 'Practical' | 'MSCRIS';

interface NamedSlot {
  kind: SlotKind;
  slot: DayTimeSlot;
}

function namedSlots(input: TimetableInput): NamedSlot[] {
  return [
    ...input.theoryDaysAndTimes.map((slot) => ({ kind: 'Theory' as const, slot })),
    ...input.practicalDaysAndTimes.map((slot) => ({ kind: 'Practical' as const, slot })),
    ...input.mscrisDaysAndTimes.map((slot) => ({ kind: 'MSCRIS' as const, slot })),
  ];
}

function sessionSlots(session: TimetableSession): Array<NamedSlot & { trainerId: string; facility: string }> {
  return [
    ...session.theoryDaysAndTimes.map((slot) => ({
      kind: 'Theory' as const,
      slot,
      trainerId: session.theoryTrainerId,
      facility: session.theoryClassroomName,
    })),
    ...session.practicalDaysAndTimes.map((slot) => ({
      kind: 'Practical' as const,
      slot,
      trainerId: session.practicalTrainerId,
      facility: session.practicalClassroomName,
    })),
    ...session.mscrisDaysAndTimes.map((slot) => ({
      kind: 'MSCRIS' as const,
      slot,
      trainerId: session.mscrisTrainerId,
      facility: session.mscrisClassName,
    })),
  ];
}

function trainerFor(input: TimetableInput, kind: SlotKind): string {
  if (kind === 'Theory') return input.theoryTrainerId;
  if (kind === 'Practical') return input.practicalTrainerId;
  return input.mscrisTrainerId;
}

function facilityFor(input: TimetableInput, kind: SlotKind): string {
  if (kind === 'Theory') return input.theoryClassroomName;
  if (kind === 'Practical') return input.practicalClassroomName;
  return input.mscrisClassName;
}

const WEEKDAY_KEY = {
  Monday: 'monday',
  Tuesday: 'tuesday',
  Wednesday: 'wednesday',
  Thursday: 'thursday',
  Friday: 'friday',
} as const;

export function validateTimetableInput(
  input: TimetableInput,
  context: TimetableValidationContext,
): ValidationResult {
  const issues: ValidationIssue[] = [];
  const others = context.existingSessions.filter((session) => session.id !== context.editingId);
  const slots = namedSlots(input);

  // ---------------------------------------------------------------- required
  const required: Array<[string, unknown, string]> = [
    ['College', input.collegeId, 'Select the college responsible for the student group.'],
    ['Campus Location', input.campusId, 'Select the campus for the selected college.'],
    ['Qualification Code', input.qualificationCode, 'Select the qualification offered by the college and campus.'],
    ['Group', input.group, 'Enter or select the student group receiving the delivery.'],
    ['UoC Code', input.uocCode, 'Select the Unit of Competency from the approved qualification-unit sequence.'],
    ['UoC Start Date', input.uocStartDate, 'Select the first scheduled date for the unit.'],
    ['UoC End Date', input.uocEndDate, 'Select the final scheduled date for the unit.'],
  ];
  for (const [label, value, message] of required) {
    if (!value) {
      issues.push({
        id: `required-${label}`,
        severity: 'blocking',
        title: `${label} is required`,
        message,
        reference: label,
      });
    }
  }

  if (input.uocStartDate && input.uocEndDate && input.uocEndDate < input.uocStartDate) {
    issues.push({
      id: 'date-order',
      severity: 'blocking',
      title: 'Unit dates are in the wrong order',
      message: 'UoC End Date must be on or after UoC Start Date. Correct one of the dates.',
      reference: 'UoC End Date',
    });
  }

  if (slots.length === 0) {
    issues.push({
      id: 'no-slots',
      severity: 'blocking',
      title: 'No delivery time has been scheduled',
      message:
        'Add at least one theory, practical or MSCRIS day and time so the session can be checked for clashes.',
      reference: 'Theory Days and Times',
    });
  }

  // -------------------------------------------------------- trainer clashes
  for (const { kind, slot } of slots) {
    const trainerId = trainerFor(input, kind);
    if (!trainerId) continue;

    for (const session of others) {
      if (!rangesOverlap(input.uocStartDate, input.uocEndDate, session.uocStartDate, session.uocEndDate)) continue;
      for (const existing of sessionSlots(session)) {
        if (existing.trainerId !== trainerId) continue;
        if (existing.slot.day !== slot.day) continue;
        if (!timesOverlap(slot.startTime, slot.endTime, existing.slot.startTime, existing.slot.endTime)) continue;

        const trainer = context.trainers.find((entry) => entry.trainerId === trainerId);
        issues.push({
          id: `trainer-clash-${session.id}-${kind}-${slot.day}-${slot.startTime}`,
          severity: 'blocking',
          title: 'Trainer clash',
          message: `${trainer?.trainerName ?? trainerId} is already scheduled on ${slot.day} ${existing.slot.startTime}-${existing.slot.endTime} for ${session.group} (${session.uocCode}) between ${session.uocStartDate} and ${session.uocEndDate}. Choose a different trainer or time, or record an approved override.`,
          reference: `${session.recordNumber} · ${kind} ${slot.day} ${slot.startTime}-${slot.endTime}`,
        });
      }
    }
  }

  // ------------------------------------------------------- facility clashes
  for (const { kind, slot } of slots) {
    const facility = facilityFor(input, kind);
    if (!facility) continue;

    for (const session of others) {
      if (!rangesOverlap(input.uocStartDate, input.uocEndDate, session.uocStartDate, session.uocEndDate)) continue;
      if (session.campusId !== input.campusId) continue;
      for (const existing of sessionSlots(session)) {
        if (existing.facility !== facility) continue;
        if (existing.slot.day !== slot.day) continue;
        if (!timesOverlap(slot.startTime, slot.endTime, existing.slot.startTime, existing.slot.endTime)) continue;

        issues.push({
          id: `facility-clash-${session.id}-${kind}-${slot.day}-${slot.startTime}`,
          severity: 'blocking',
          title: 'Facility clash',
          message: `${facility} is already in use on ${slot.day} ${existing.slot.startTime}-${existing.slot.endTime} by ${session.group} (${session.uocCode}). Choose a different room or time, or record an approved override.`,
          reference: `${session.recordNumber} · ${kind} ${slot.day} ${slot.startTime}-${slot.endTime}`,
        });
      }
    }
  }

  // -------------------------------------------------- student-group clashes
  if (input.group) {
    for (const { kind, slot } of slots) {
      for (const session of others) {
        if (session.group !== input.group) continue;
        if (!rangesOverlap(input.uocStartDate, input.uocEndDate, session.uocStartDate, session.uocEndDate)) continue;
        for (const existing of sessionSlots(session)) {
          if (existing.slot.day !== slot.day) continue;
          if (!timesOverlap(slot.startTime, slot.endTime, existing.slot.startTime, existing.slot.endTime)) continue;

          issues.push({
            id: `group-clash-${session.id}-${kind}-${slot.day}-${slot.startTime}`,
            severity: 'blocking',
            title: 'Student-group clash',
            message: `${input.group} is already scheduled on ${slot.day} ${existing.slot.startTime}-${existing.slot.endTime} for ${session.uocCode}. A group cannot attend two sessions at the same time.`,
            reference: `${session.recordNumber} · ${kind} ${slot.day} ${slot.startTime}-${slot.endTime}`,
          });
        }
      }
    }
  }

  // ------------------------------------------------------- facility capacity
  const capacityChecks: Array<[string, string, number]> = [
    ['Theory Classroom', input.theoryClassroomName, input.theoryClassroomCapacity],
    ['Practical Classroom', input.practicalClassroomName, input.practicalClassroomCapacity],
  ];
  for (const [label, name, capacity] of capacityChecks) {
    if (!name || !capacity) continue;
    if (input.classroomSize > capacity) {
      issues.push({
        id: `capacity-${label}`,
        severity: 'blocking',
        title: 'Facility capacity exceeded',
        message: `Classroom Size is ${input.classroomSize} but ${name} has an approved capacity of ${capacity}. Choose a larger facility or reduce the class size.`,
        reference: label,
      });
    }
  }

  // -------------------------------------------------------- inactive trainer
  for (const kind of ['Theory', 'Practical', 'MSCRIS'] as const) {
    const trainerId = trainerFor(input, kind);
    if (!trainerId) continue;
    const trainer = context.trainers.find((entry) => entry.trainerId === trainerId);
    if (trainer && !trainer.isActive) {
      issues.push({
        id: `inactive-trainer-${kind}`,
        severity: 'blocking',
        title: 'Inactive trainer selected',
        message: `${trainer.trainerName} is marked INACTIVE. An inactive trainer remains visible for historical records but cannot be assigned to a new timetable record (TRN-04).`,
        reference: `${kind} Trainer`,
      });
    }
  }

  // ---------------------------------------------------- qualification duration
  if (input.qualificationCode && input.durationInWeeks) {
    const offering = context.offerings.find(
      (entry) =>
        entry.qualificationCode === input.qualificationCode &&
        (!input.campusId || entry.campusId === input.campusId),
    );
    if (offering && !offering.durationOptions.includes(input.durationInWeeks)) {
      issues.push({
        id: 'duration-option',
        severity: 'blocking',
        title: 'Duration is not an approved option',
        message: `${input.durationInWeeks} weeks is not an approved duration for ${input.qualificationCode} at this campus. Approved options: ${offering.durationOptions.join(', ')} weeks.`,
        reference: 'Duration in Weeks',
      });
    }
  }

  // ------------------------------------------------------------ unit sequence
  if (input.qualificationCode && input.uocCode) {
    const sequence = context.unitSequences
      .filter((entry) => entry.qualificationCode === input.qualificationCode)
      .sort((a, b) => a.sequenceId - b.sequenceId);
    const current = sequence.find((entry) => entry.unitCode === input.uocCode);

    if (sequence.length > 0 && !current) {
      issues.push({
        id: 'unit-not-in-sequence',
        severity: 'blocking',
        title: 'Unit is not in the approved sequence',
        message: `${input.uocCode} is not part of the approved qualification and unit sequence for ${input.qualificationCode}. Select an approved unit.`,
        reference: 'UoC Code',
      });
    }

    if (current && input.group) {
      const scheduledForGroup = new Set(
        others.filter((session) => session.group === input.group).map((session) => session.uocCode),
      );
      const missingEarlier = sequence
        .filter((entry) => entry.sequenceId < current.sequenceId && !scheduledForGroup.has(entry.unitCode))
        .map((entry) => entry.unitCode);

      if (missingEarlier.length > 0) {
        issues.push({
          id: 'unit-sequence-order',
          severity: 'advisory',
          title: 'Earlier units are not scheduled',
          message: `${input.uocCode} has sequence ${current.sequenceId}. These earlier units are not yet scheduled for ${input.group}: ${missingEarlier.join(', ')}. Confirm this is intended before saving.`,
          reference: 'Unit sequence',
        });
      }
    }
  }

  // -------------------------------------------- trainer weekday availability
  for (const { kind, slot } of slots) {
    const trainerId = trainerFor(input, kind);
    if (!trainerId) continue;
    const trainer = context.trainers.find((entry) => entry.trainerId === trainerId);
    if (!trainer) continue;

    const availability: WeekdayAvailability = trainer[WEEKDAY_KEY[slot.day]];
    if (availability === 'Not Available') {
      issues.push({
        id: `availability-${kind}-${slot.day}`,
        severity: 'advisory',
        title: 'Trainer availability',
        message: `${trainer.trainerName} is recorded as Not Available on ${slot.day}. Confirm the availability record before saving.`,
        reference: `${kind} Trainer · ${slot.day}`,
      });
    }
  }

  // ------------------------------------------------------ unresolved SRS rules
  issues.push({
    id: 'break-rules',
    severity: 'pending-approval',
    title: 'Break placement and course-end rule',
    message:
      'TT-09, TT-10 and TT-11 require approved break placement for 26, 52, 78 and 104-week courses, and a course must not finish on a break. The exact break dates or calculation rules have not been approved, so TDMS cannot check them yet. This check is displayed but produces no pass or fail result.',
    openDecisionId: 'OD-07',
  });

  const usesVirtual =
    input.modeOfDelivery === 'Virtual' ||
    ['Theory', 'Practical', 'MSCRIS'].some((kind) => Boolean(trainerFor(input, kind as SlotKind)));
  if (usesVirtual) {
    issues.push({
      id: 'trainer-delivery-rule',
      severity: 'pending-approval',
      title: 'Trainer physical and virtual delivery rule',
      message:
        'The supplied rule states that a trainer approved for physical delivery may also deliver virtually, and that a virtual-only trainer may not be assigned to a physical class. TRN-07 requires this rule to be approved before it is applied, so TDMS does not enforce it yet.',
      openDecisionId: 'OD-10',
    });
  }

  if (input.mscrisClassName || input.mscrisDaysAndTimes.length > 0 || input.mscrisTrainerId) {
    issues.push({
      id: 'mscris-definition',
      severity: 'pending-approval',
      title: 'MSCRIS field rules',
      message:
        'The full MSCRIS term, business purpose and final field rules are not confirmed. The values entered are stored and displayed, but no MSCRIS business rule is applied.',
      openDecisionId: 'OD-11',
    });
  }

  const blocking = issues.filter((issue) => issue.severity === 'blocking');

  return {
    issues,
    // TT-12 / SRS 2.3: Save stays unavailable until every blocking rule passes.
    canSave: blocking.length === 0,
    checkedAt: nowIso(),
  };
}
