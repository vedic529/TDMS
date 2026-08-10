import type { TdmsUser } from '@/types/auth';
import type { ActivityFilters, UserActivityRecord } from '@/types/activity';
import type { ImportBatch, ImportResult, StagedStudentRow } from '@/types/import';
import type { CourseRecord, QualificationUnitSequence } from '@/types/reference';
import type { StudentFilters, StudentInput, StudentRecord } from '@/types/student';
import type { TimetableFilters, TimetableInput, TimetableSession } from '@/types/timetable';
import type { TrainerFilters, TrainerInput, TrainerRecord } from '@/types/trainer';
import type { SoftDeletable, SoftDeleteMetadata } from '@/types/common';

import { addDays, nowIso, rangesOverlap, today } from '@/lib/format';
import { PROPOSED_RECYCLE_PERIOD_DAYS } from '@/lib/reasons';
import { SRS_PAGE_REFERENCE } from '@/lib/interface-names';
import { createSeedDataset } from '@/mock-data';
import { qualificationByCode } from '@/mock-data/qualifications';

import type { ReferenceDataBundle, TdmsDataset } from './dataset';
import { PROTOTYPE_STORAGE_KEYS, readPrototypeValue, writePrototypeValue } from './prototype-storage';
import { countByStatus, validateStagedRows } from './import-validation';
import type {
  ActionContext,
  CourseFilters,
  CourseInput,
  QualificationUnitFilters,
  QualificationUnitInput,
  ReasonedRequest,
  StageImportRequest,
  TdmsClient,
  UserInput,
} from './tdms-client';

/**
 * In-browser TDMS data service used while the FastAPI backend and production
 * database are not connected.
 *
 * Behaviour intentionally mirrors the SRS: soft deletion with a recycle area,
 * a staging area for imports, and a user activity record for every action
 * required by LOG-01. Changes are kept in prototype browser storage so a demo
 * survives a page refresh; the storage is namespaced and is never production
 * data.
 */

/** A small delay makes loading states visible and mirrors a network round trip. */
const LATENCY_MS = 140;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS));
}

function nextNumber(existing: string[], prefix: string, width: number): string {
  let highest = 0;
  for (const value of existing) {
    if (!value?.startsWith(prefix)) continue;
    const numeric = Number.parseInt(value.slice(prefix.length), 10);
    if (Number.isFinite(numeric) && numeric > highest) highest = numeric;
  }
  return `${prefix}${String(highest + 1).padStart(width, '0')}`;
}

function buildDeletion(request: ReasonedRequest, actor: TdmsUser): SoftDeleteMetadata {
  return {
    deletedAt: nowIso(),
    deletedBy: actor.organisationEmail,
    deleteReason: request.reason,
    deleteReasonDetail: request.reasonDetail,
    recoveryDeadline: addDays(today(), PROPOSED_RECYCLE_PERIOD_DAYS),
  };
}

function activeOnly<T extends SoftDeletable>(records: T[]): T[] {
  return records.filter((record) => !record.isDeleted);
}

function deletedOnly<T extends SoftDeletable>(records: T[]): T[] {
  return records.filter((record) => record.isDeleted);
}

function includesText(haystack: Array<string | number | undefined>, needle: string): boolean {
  const value = needle.trim().toLowerCase();
  if (!value) return true;
  return haystack.some((entry) => String(entry ?? '').toLowerCase().includes(value));
}

export class MockTdmsClient implements TdmsClient {
  readonly mode = 'mock' as const;

  private dataset: TdmsDataset;

  constructor() {
    this.dataset = this.load();
  }

  // -- storage -------------------------------------------------------------

  private load(): TdmsDataset {
    const stored = readPrototypeValue<TdmsDataset>(PROTOTYPE_STORAGE_KEYS.dataset);
    if (stored && Array.isArray(stored.students) && Array.isArray(stored.timetableSessions)) {
      return stored;
    }
    return createSeedDataset();
  }

  private persist(): void {
    writePrototypeValue(PROTOTYPE_STORAGE_KEYS.dataset, this.dataset);
  }

  private logActivity(record: Omit<UserActivityRecord, 'activityRecordNumber' | 'dateTime'>): UserActivityRecord {
    const activityRecordNumber = nextNumber(
      this.dataset.activityRecords.map((entry) => entry.activityRecordNumber),
      'ACT-',
      6,
    );
    const created: UserActivityRecord = { ...record, activityRecordNumber, dateTime: nowIso() };
    this.dataset.activityRecords = [created, ...this.dataset.activityRecords];
    return created;
  }

  private actorFields(actor: TdmsUser) {
    return {
      userReference: actor.organisationEmail,
      accessLevel: actor.role,
      assignment: actor.assignment,
    };
  }

  // -- reference data ------------------------------------------------------

  async getReferenceData(): Promise<ReferenceDataBundle> {
    const groups = Array.from(
      new Set([
        ...activeOnly(this.dataset.timetableSessions).map((session) => session.group),
        ...activeOnly(this.dataset.students).map((student) => student.group),
      ]),
    )
      .filter(Boolean)
      .sort();

    return delay({
      colleges: this.dataset.colleges,
      campuses: this.dataset.campuses,
      qualificationOfferings: this.dataset.qualificationOfferings,
      qualificationUnitSequences: activeOnly(this.dataset.qualificationUnitSequences),
      facilities: this.dataset.facilities,
      trainers: activeOnly(this.dataset.trainers),
      groups,
    });
  }

  // -- Timetable View and Management ---------------------------------------

  async listTimetableSessions(filters: TimetableFilters): Promise<TimetableSession[]> {
    const rows = activeOnly(this.dataset.timetableSessions).filter((session) => {
      // TT-03: show every session that overlaps the selected date range.
      if (filters.fromDate && filters.toDate) {
        if (!rangesOverlap(session.uocStartDate, session.uocEndDate, filters.fromDate, filters.toDate)) {
          return false;
        }
      }
      if (filters.collegeId && session.collegeId !== filters.collegeId) return false;
      if (filters.campusId && session.campusId !== filters.campusId) return false;
      if (filters.qualificationCode && session.qualificationCode !== filters.qualificationCode) return false;
      if (filters.group && session.group !== filters.group) return false;
      return true;
    });

    return delay([...rows].sort((a, b) => a.uocStartDate.localeCompare(b.uocStartDate)));
  }

  async createTimetableSession(input: TimetableInput, context: ActionContext): Promise<TimetableSession> {
    const recordNumber = nextNumber(
      this.dataset.timetableSessions.map((session) => session.recordNumber),
      'TT-',
      5,
    );
    const session: TimetableSession = {
      ...input,
      id: `tt-${recordNumber.toLowerCase()}`,
      recordNumber,
      createdAt: nowIso(),
      updatedAt: nowIso(),
      isDeleted: false,
    };
    this.dataset.timetableSessions = [session, ...this.dataset.timetableSessions];
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.timetable,
      action: 'Timetable save',
      recordOrBatchReference: recordNumber,
      reasonDetail: input.overrideReasonDetail,
      result: 'Completed',
      plainLanguageDetail: `Timetable record created for ${input.group}, unit ${input.uocCode}.`,
    });
    this.persist();
    return delay(session);
  }

  async updateTimetableSession(
    id: string,
    input: TimetableInput,
    context: ActionContext,
  ): Promise<TimetableSession> {
    const existing = this.dataset.timetableSessions.find((session) => session.id === id);
    if (!existing) throw new Error('Timetable record not found.');
    const updated: TimetableSession = { ...existing, ...input, updatedAt: nowIso() };
    this.dataset.timetableSessions = this.dataset.timetableSessions.map((session) =>
      session.id === id ? updated : session,
    );
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.timetable,
      action: 'Edit',
      recordOrBatchReference: existing.recordNumber,
      result: 'Completed',
      plainLanguageDetail: `Timetable record ${existing.recordNumber} updated after the change summary was confirmed.`,
    });
    this.persist();
    return delay(updated);
  }

  async deleteTimetableSession(id: string, request: ReasonedRequest, context: ActionContext): Promise<void> {
    const existing = this.dataset.timetableSessions.find((session) => session.id === id);
    if (!existing) throw new Error('Timetable record not found.');
    const deletion = buildDeletion(request, context.actor);
    this.dataset.timetableSessions = this.dataset.timetableSessions.map((session) =>
      session.id === id ? { ...session, isDeleted: true, deletion } : session,
    );
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.timetable,
      action: 'Delete',
      recordOrBatchReference: existing.recordNumber,
      reason: request.reason,
      reasonDetail: request.reasonDetail,
      result: 'Completed',
      plainLanguageDetail: `Timetable record moved to the recycle area. Recovery deadline ${deletion.recoveryDeadline}.`,
    });
    this.persist();
    await delay(null);
  }

  async listDeletedTimetableSessions(): Promise<TimetableSession[]> {
    return delay(deletedOnly(this.dataset.timetableSessions));
  }

  async restoreTimetableSession(
    id: string,
    request: ReasonedRequest,
    context: ActionContext,
  ): Promise<TimetableSession> {
    const existing = this.dataset.timetableSessions.find((session) => session.id === id);
    if (!existing) throw new Error('Timetable record not found.');
    const restored: TimetableSession = { ...existing, isDeleted: false, deletion: undefined, updatedAt: nowIso() };
    this.dataset.timetableSessions = this.dataset.timetableSessions.map((session) =>
      session.id === id ? restored : session,
    );
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.timetable,
      action: 'Restore',
      recordOrBatchReference: existing.recordNumber,
      reason: request.reason,
      reasonDetail: request.reasonDetail,
      result: 'Completed',
      plainLanguageDetail: `Timetable record ${existing.recordNumber} restored from the recycle area.`,
    });
    this.persist();
    return delay(restored);
  }

  // -- Single Student Entry ------------------------------------------------

  async listStudents(filters: StudentFilters): Promise<StudentRecord[]> {
    const rows = activeOnly(this.dataset.students).filter((student) => {
      if (filters.collegeId && student.collegeId !== filters.collegeId) return false;
      if (filters.campusId && student.campusId !== filters.campusId) return false;
      if (filters.qualificationCode && student.qualificationCode !== filters.qualificationCode) return false;
      if (filters.coeStatus && student.coeStatus !== filters.coeStatus) return false;
      if (filters.intake && student.intake !== filters.intake) return false;
      if (
        filters.search &&
        !includesText(
          [
            student.studentId,
            student.firstName,
            student.lastName,
            student.collegeEmail,
            student.group,
            student.qualificationCode,
            student.qualificationTitle,
          ],
          filters.search,
        )
      ) {
        return false;
      }
      return true;
    });
    return delay([...rows].sort((a, b) => a.studentId.localeCompare(b.studentId)));
  }

  async findStudentByStudentId(studentId: string): Promise<StudentRecord | null> {
    const needle = studentId.trim().toUpperCase();
    const found = activeOnly(this.dataset.students).find(
      (student) => student.studentId.toUpperCase() === needle,
    );
    return delay(found ?? null);
  }

  async isStudentIdAvailable(studentId: string, excludeRecordId?: string): Promise<boolean> {
    const needle = studentId.trim().toUpperCase();
    if (!needle) return delay(false);
    const clash = activeOnly(this.dataset.students).some(
      (student) => student.studentId.toUpperCase() === needle && student.id !== excludeRecordId,
    );
    return delay(!clash);
  }

  async createStudent(input: StudentInput, context: ActionContext): Promise<StudentRecord> {
    const student: StudentRecord = {
      ...input,
      id: `stu-${input.studentId.toLowerCase()}-${this.dataset.students.length + 1}`,
      createdAt: nowIso(),
      updatedAt: nowIso(),
      isDeleted: false,
    };
    this.dataset.students = [student, ...this.dataset.students];
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.singleStudentEntry,
      action: 'Create',
      recordOrBatchReference: student.studentId,
      result: 'Completed',
      plainLanguageDetail: `Student record created for ${student.firstName} ${student.lastName} (${student.qualificationCode}).`,
    });
    this.persist();
    return delay(student);
  }

  async updateStudent(id: string, input: StudentInput, context: ActionContext): Promise<StudentRecord> {
    const existing = this.dataset.students.find((student) => student.id === id);
    if (!existing) throw new Error('Student record not found.');
    const updated: StudentRecord = { ...existing, ...input, updatedAt: nowIso() };
    this.dataset.students = this.dataset.students.map((student) => (student.id === id ? updated : student));
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.singleStudentEntry,
      action: 'Edit',
      recordOrBatchReference: updated.studentId,
      result: 'Completed',
      plainLanguageDetail: `Student record ${updated.studentId} updated after the change summary was confirmed.`,
    });
    this.persist();
    return delay(updated);
  }

  async deleteStudent(id: string, request: ReasonedRequest, context: ActionContext): Promise<void> {
    const existing = this.dataset.students.find((student) => student.id === id);
    if (!existing) throw new Error('Student record not found.');
    const deletion = buildDeletion(request, context.actor);
    this.dataset.students = this.dataset.students.map((student) =>
      student.id === id ? { ...student, isDeleted: true, deletion } : student,
    );
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.singleStudentEntry,
      action: 'Delete',
      recordOrBatchReference: existing.studentId,
      reason: request.reason,
      reasonDetail: request.reasonDetail,
      result: 'Completed',
      plainLanguageDetail: `Student record moved to the recycle area. Recovery deadline ${deletion.recoveryDeadline}.`,
    });
    this.persist();
    await delay(null);
  }

  async listDeletedStudents(): Promise<StudentRecord[]> {
    return delay(deletedOnly(this.dataset.students));
  }

  async restoreStudent(id: string, request: ReasonedRequest, context: ActionContext): Promise<StudentRecord> {
    const existing = this.dataset.students.find((student) => student.id === id);
    if (!existing) throw new Error('Student record not found.');
    const restored: StudentRecord = { ...existing, isDeleted: false, deletion: undefined, updatedAt: nowIso() };
    this.dataset.students = this.dataset.students.map((student) => (student.id === id ? restored : student));
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.singleStudentEntry,
      action: 'Restore',
      recordOrBatchReference: existing.studentId,
      reason: request.reason,
      reasonDetail: request.reasonDetail,
      result: 'Completed',
      plainLanguageDetail: `Student record ${existing.studentId} restored from the recycle area.`,
    });
    this.persist();
    return delay(restored);
  }

  // -- Bulk Student Import -------------------------------------------------

  async stageImport(request: StageImportRequest, context: ActionContext): Promise<ImportBatch> {
    const batchReference = nextNumber(
      this.dataset.importBatches.map((batch) => batch.batchReference),
      'BATCH-',
      6,
    );

    const rows: StagedStudentRow[] = request.rows.map((raw, index) => ({
      id: `${batchReference}-row-${index + 1}`,
      // Row 1 is the header, so the first data row is source row 2.
      sourceRowNumber: index + 2,
      studentId: raw['Student ID'] ?? '',
      firstName: raw['First Name'] ?? '',
      lastName: raw['Last Name'] ?? '',
      collegeValue: raw['College'] ?? '',
      campusValue: raw['Campus'] ?? '',
      qualificationValue: raw['Qualification'] ?? '',
      coeStatus: raw['CoE / Non-CoE'] ?? '',
      proposedStartDate: raw['Proposed Start Date'] ?? '',
      proposedEndDate: raw['Proposed End Date'] ?? '',
      personalEmail: raw['Personal Email'] ?? '',
      primaryPhone: raw['Primary Phone'] ?? '',
      status: 'Needs correction',
      issues: [],
      corrected: false,
    }));

    const batch: ImportBatch = {
      id: `imp-${batchReference.toLowerCase()}`,
      batchReference,
      fileName: request.fileName,
      fileSizeBytes: request.fileSizeBytes,
      uploadedAt: nowIso(),
      uploadedByUserId: context.actor.id,
      uploadedByDisplayName: context.actor.displayName,
      rowCount: rows.length,
      rows: validateStagedRows(rows, this.dataset),
    };

    this.dataset.importBatches = [batch, ...this.dataset.importBatches].slice(0, 10);
    this.persist();
    return delay(batch);
  }

  async revalidateImport(batch: ImportBatch): Promise<ImportBatch> {
    const revalidated: ImportBatch = { ...batch, rows: validateStagedRows(batch.rows, this.dataset) };
    this.dataset.importBatches = this.dataset.importBatches.map((entry) =>
      entry.id === batch.id ? revalidated : entry,
    );
    this.persist();
    return delay(revalidated);
  }

  async saveImport(batch: ImportBatch, context: ActionContext): Promise<ImportResult> {
    const counts = countByStatus(batch.rows);
    const readyRows = batch.rows.filter((row) => row.status === 'Ready');

    // BULK-08: the confirmed set is written together or not at all.
    const created: StudentRecord[] = readyRows.map((row) => {
      const campus = this.dataset.campuses.find((entry) => entry.id === row.resolvedCampusId);
      const college = this.dataset.colleges.find((entry) => entry.id === row.resolvedCollegeId);
      const definition = qualificationByCode(row.resolvedQualificationCode ?? '');
      const durationDays =
        row.proposedStartDate && row.proposedEndDate
          ? Math.round(
              (new Date(`${row.proposedEndDate}T00:00:00Z`).getTime() -
                new Date(`${row.proposedStartDate}T00:00:00Z`).getTime()) /
                86_400_000,
            )
          : 0;

      return {
        id: `stu-${row.studentId.toLowerCase()}-${batch.batchReference}`,
        group: '',
        intake: '',
        collegeId: row.resolvedCollegeId ?? '',
        campusId: row.resolvedCampusId ?? '',
        collegeEmail: college ? `${row.studentId.toLowerCase()}@${college.emailDomain}` : '',
        firstName: row.firstName,
        lastName: row.lastName,
        studentId: row.studentId,
        coeStatus: row.coeStatus === 'Non-CoE' ? 'Non-CoE' : 'CoE',
        proposedStartDate: row.proposedStartDate,
        proposedEndDate: row.proposedEndDate,
        actualCourseDuration: Math.max(0, Math.round(durationDays / 7)),
        courseDurationOption: definition?.durationOptions[0] ?? null,
        qualificationTitle: definition?.qualificationTitle ?? '',
        qualificationCode: row.resolvedQualificationCode ?? '',
        ctStudent: 'No',
        personalEmail: row.personalEmail,
        primaryPhone: row.primaryPhone,
        state: campus?.state ?? '',
        primaryCountry: '',
        remarks: `Imported from ${batch.fileName} (${batch.batchReference}).`,
        createdAt: nowIso(),
        updatedAt: nowIso(),
        isDeleted: false,
      } satisfies StudentRecord;
    });

    this.dataset.students = [...created, ...this.dataset.students];

    const result: ImportResult = {
      inserted: created.length,
      excluded: counts.excluded,
      duplicate: counts.duplicate,
      corrected: counts.corrected,
      rejected: counts.needsCorrection,
      unmatched: counts.unmatched,
      completedAt: nowIso(),
    };

    this.dataset.importBatches = this.dataset.importBatches.map((entry) =>
      entry.id === batch.id ? { ...batch, result } : entry,
    );

    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.bulkStudentImport,
      action: 'Import',
      recordOrBatchReference: batch.batchReference,
      result: 'Completed',
      plainLanguageDetail: `Bulk student import saved from ${batch.fileName}. Inserted ${result.inserted}, excluded ${result.excluded}, duplicate ${result.duplicate}, unmatched ${result.unmatched}.`,
    });

    this.persist();
    return delay(result);
  }

  // -- Trainer Data --------------------------------------------------------

  async listTrainers(filters: TrainerFilters): Promise<TrainerRecord[]> {
    // TRN-01: no results until a qualification is selected.
    if (!filters.qualificationCode) return delay([]);

    const rows = activeOnly(this.dataset.trainers).filter((trainer) => {
      if (!trainer.qualificationsCanTeach.includes(filters.qualificationCode!)) return false;
      if (filters.campusId && trainer.campusId !== filters.campusId) return false;
      if (filters.location && trainer.location !== filters.location) return false;
      if (filters.deliveryType && trainer.deliveryType !== filters.deliveryType) return false;
      if (filters.status === 'active' && !trainer.isActive) return false;
      if (filters.status === 'inactive' && trainer.isActive) return false;
      if (filters.search && !includesText([trainer.trainerId, trainer.trainerName, trainer.location], filters.search)) {
        return false;
      }
      return true;
    });

    return delay([...rows].sort((a, b) => a.serialNumber - b.serialNumber));
  }

  async createTrainer(input: TrainerInput, context: ActionContext): Promise<TrainerRecord> {
    const serialNumber = this.dataset.trainers.reduce((max, trainer) => Math.max(max, trainer.serialNumber), 0) + 1;
    const trainer: TrainerRecord = {
      ...input,
      id: `trn-${input.trainerId.toLowerCase()}`,
      serialNumber,
      isDeleted: false,
    };
    this.dataset.trainers = [...this.dataset.trainers, trainer];
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.trainerData,
      action: 'Create',
      recordOrBatchReference: trainer.trainerId,
      result: 'Completed',
      plainLanguageDetail: `Trainer ${trainer.trainerName} added to trainer reference data.`,
    });
    this.persist();
    return delay(trainer);
  }

  async updateTrainer(id: string, input: TrainerInput, context: ActionContext): Promise<TrainerRecord> {
    const existing = this.dataset.trainers.find((trainer) => trainer.id === id);
    if (!existing) throw new Error('Trainer record not found.');
    const updated: TrainerRecord = { ...existing, ...input };
    this.dataset.trainers = this.dataset.trainers.map((trainer) => (trainer.id === id ? updated : trainer));
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.trainerData,
      action: 'Edit',
      recordOrBatchReference: updated.trainerId,
      result: 'Completed',
      plainLanguageDetail: `Trainer ${updated.trainerName} updated after the change summary was confirmed.`,
    });
    this.persist();
    return delay(updated);
  }

  async deleteTrainer(id: string, request: ReasonedRequest, context: ActionContext): Promise<void> {
    const existing = this.dataset.trainers.find((trainer) => trainer.id === id);
    if (!existing) throw new Error('Trainer record not found.');
    const deletion = buildDeletion(request, context.actor);
    this.dataset.trainers = this.dataset.trainers.map((trainer) =>
      trainer.id === id ? { ...trainer, isDeleted: true, isActive: false, deletion } : trainer,
    );
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.trainerData,
      action: 'Delete',
      recordOrBatchReference: existing.trainerId,
      reason: request.reason,
      reasonDetail: request.reasonDetail,
      result: 'Completed',
      plainLanguageDetail: `Trainer record moved to the recycle area. Recovery deadline ${deletion.recoveryDeadline}.`,
    });
    this.persist();
    await delay(null);
  }

  async listDeletedTrainers(): Promise<TrainerRecord[]> {
    return delay(deletedOnly(this.dataset.trainers));
  }

  async restoreTrainer(id: string, request: ReasonedRequest, context: ActionContext): Promise<TrainerRecord> {
    const existing = this.dataset.trainers.find((trainer) => trainer.id === id);
    if (!existing) throw new Error('Trainer record not found.');
    const restored: TrainerRecord = { ...existing, isDeleted: false, deletion: undefined };
    this.dataset.trainers = this.dataset.trainers.map((trainer) => (trainer.id === id ? restored : trainer));
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.trainerData,
      action: 'Restore',
      recordOrBatchReference: existing.trainerId,
      reason: request.reason,
      reasonDetail: request.reasonDetail,
      result: 'Completed',
      plainLanguageDetail: `Trainer record ${existing.trainerId} restored from the recycle area.`,
    });
    this.persist();
    return delay(restored);
  }

  // -- Course Data ---------------------------------------------------------

  async listCourses(filters: CourseFilters): Promise<CourseRecord[]> {
    const rows = activeOnly(this.dataset.courses).filter((course) => {
      if (filters.collegeId && course.collegeId !== filters.collegeId) return false;
      if (filters.campusId && course.campusId !== filters.campusId) return false;
      if (filters.courseStatus && course.courseStatus !== filters.courseStatus) return false;
      if (
        filters.search &&
        !includesText([course.courseCode, course.vetCode, course.courseName, course.courseLevel], filters.search)
      ) {
        return false;
      }
      return true;
    });
    return delay([...rows].sort((a, b) => a.courseCode.localeCompare(b.courseCode)));
  }

  async createCourse(input: CourseInput, context: ActionContext): Promise<CourseRecord> {
    const course: CourseRecord = {
      ...input,
      id: `crs-${input.courseCode.toLowerCase()}-${this.dataset.courses.length + 1}`,
      isDeleted: false,
    };
    this.dataset.courses = [course, ...this.dataset.courses];
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.courseData,
      action: 'Create',
      recordOrBatchReference: course.courseCode,
      result: 'Completed',
      plainLanguageDetail: `Course ${course.courseCode} - ${course.courseName} added to reference data.`,
    });
    this.persist();
    return delay(course);
  }

  async updateCourse(id: string, input: CourseInput, context: ActionContext): Promise<CourseRecord> {
    const existing = this.dataset.courses.find((course) => course.id === id);
    if (!existing) throw new Error('Course record not found.');
    const updated: CourseRecord = { ...existing, ...input };
    this.dataset.courses = this.dataset.courses.map((course) => (course.id === id ? updated : course));
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.courseData,
      action: 'Edit',
      recordOrBatchReference: updated.courseCode,
      result: 'Completed',
      plainLanguageDetail: `Course ${updated.courseCode} updated after the change summary was confirmed.`,
    });
    this.persist();
    return delay(updated);
  }

  async deleteCourse(id: string, request: ReasonedRequest, context: ActionContext): Promise<void> {
    const existing = this.dataset.courses.find((course) => course.id === id);
    if (!existing) throw new Error('Course record not found.');
    const deletion = buildDeletion(request, context.actor);
    this.dataset.courses = this.dataset.courses.map((course) =>
      course.id === id ? { ...course, isDeleted: true, deletion } : course,
    );
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.courseData,
      action: 'Delete',
      recordOrBatchReference: existing.courseCode,
      reason: request.reason,
      reasonDetail: request.reasonDetail,
      result: 'Completed',
      plainLanguageDetail: `Course record moved to the recycle area. Recovery deadline ${deletion.recoveryDeadline}.`,
    });
    this.persist();
    await delay(null);
  }

  async listDeletedCourses(): Promise<CourseRecord[]> {
    return delay(deletedOnly(this.dataset.courses));
  }

  async restoreCourse(id: string, request: ReasonedRequest, context: ActionContext): Promise<CourseRecord> {
    const existing = this.dataset.courses.find((course) => course.id === id);
    if (!existing) throw new Error('Course record not found.');
    const restored: CourseRecord = { ...existing, isDeleted: false, deletion: undefined };
    this.dataset.courses = this.dataset.courses.map((course) => (course.id === id ? restored : course));
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.courseData,
      action: 'Restore',
      recordOrBatchReference: existing.courseCode,
      reason: request.reason,
      reasonDetail: request.reasonDetail,
      result: 'Completed',
      plainLanguageDetail: `Course record ${existing.courseCode} restored from the recycle area.`,
    });
    this.persist();
    return delay(restored);
  }

  // -- Qualification and Unit Sequence Data --------------------------------

  async listQualificationUnitSequences(
    filters: QualificationUnitFilters,
  ): Promise<QualificationUnitSequence[]> {
    const rows = activeOnly(this.dataset.qualificationUnitSequences).filter((record) => {
      if (filters.collegeId && record.collegeId !== filters.collegeId) return false;
      if (filters.campusId && record.campusId !== filters.campusId) return false;
      if (filters.qualificationCode && record.qualificationCode !== filters.qualificationCode) return false;
      if (
        filters.search &&
        !includesText(
          [record.recordId, record.qualificationCode, record.qualificationTitle, record.unitCode, record.unitTitle],
          filters.search,
        )
      ) {
        return false;
      }
      return true;
    });
    return delay(
      [...rows].sort(
        (a, b) => a.qualificationCode.localeCompare(b.qualificationCode) || a.sequenceId - b.sequenceId,
      ),
    );
  }

  async createQualificationUnit(
    input: QualificationUnitInput,
    context: ActionContext,
  ): Promise<QualificationUnitSequence> {
    const record: QualificationUnitSequence = {
      ...input,
      id: `qus-${input.qualificationCode}-${input.unitCode}-${this.dataset.qualificationUnitSequences.length + 1}`,
      isDeleted: false,
    };
    this.dataset.qualificationUnitSequences = [record, ...this.dataset.qualificationUnitSequences];
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.qualificationUnitSequence,
      action: 'Create',
      recordOrBatchReference: record.recordId,
      result: 'Completed',
      plainLanguageDetail: `Unit ${record.unitCode} added to ${record.qualificationCode} at sequence ${record.sequenceId}.`,
    });
    this.persist();
    return delay(record);
  }

  async updateQualificationUnit(
    id: string,
    input: QualificationUnitInput,
    context: ActionContext,
  ): Promise<QualificationUnitSequence> {
    const existing = this.dataset.qualificationUnitSequences.find((record) => record.id === id);
    if (!existing) throw new Error('Qualification and unit sequence record not found.');
    const updated: QualificationUnitSequence = { ...existing, ...input };
    this.dataset.qualificationUnitSequences = this.dataset.qualificationUnitSequences.map((record) =>
      record.id === id ? updated : record,
    );
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.qualificationUnitSequence,
      action: 'Edit',
      recordOrBatchReference: updated.recordId,
      result: 'Completed',
      plainLanguageDetail: `Qualification and unit sequence record ${updated.recordId} updated.`,
    });
    this.persist();
    return delay(updated);
  }

  async deleteQualificationUnit(
    id: string,
    request: ReasonedRequest,
    context: ActionContext,
  ): Promise<void> {
    const existing = this.dataset.qualificationUnitSequences.find((record) => record.id === id);
    if (!existing) throw new Error('Qualification and unit sequence record not found.');
    const deletion = buildDeletion(request, context.actor);
    this.dataset.qualificationUnitSequences = this.dataset.qualificationUnitSequences.map((record) =>
      record.id === id ? { ...record, isDeleted: true, deletion } : record,
    );
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.qualificationUnitSequence,
      action: 'Delete',
      recordOrBatchReference: existing.recordId,
      reason: request.reason,
      reasonDetail: request.reasonDetail,
      result: 'Completed',
      plainLanguageDetail: `Qualification and unit sequence record moved to the recycle area. Recovery deadline ${deletion.recoveryDeadline}.`,
    });
    this.persist();
    await delay(null);
  }

  async listDeletedQualificationUnits(): Promise<QualificationUnitSequence[]> {
    return delay(deletedOnly(this.dataset.qualificationUnitSequences));
  }

  async restoreQualificationUnit(
    id: string,
    request: ReasonedRequest,
    context: ActionContext,
  ): Promise<QualificationUnitSequence> {
    const existing = this.dataset.qualificationUnitSequences.find((record) => record.id === id);
    if (!existing) throw new Error('Qualification and unit sequence record not found.');
    const restored: QualificationUnitSequence = { ...existing, isDeleted: false, deletion: undefined };
    this.dataset.qualificationUnitSequences = this.dataset.qualificationUnitSequences.map((record) =>
      record.id === id ? restored : record,
    );
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.qualificationUnitSequence,
      action: 'Restore',
      recordOrBatchReference: existing.recordId,
      reason: request.reason,
      reasonDetail: request.reasonDetail,
      result: 'Completed',
      plainLanguageDetail: `Qualification and unit sequence record ${existing.recordId} restored.`,
    });
    this.persist();
    return delay(restored);
  }

  // -- Administration ------------------------------------------------------

  async listUsers(): Promise<TdmsUser[]> {
    return delay([...this.dataset.users].sort((a, b) => a.displayName.localeCompare(b.displayName)));
  }

  async createUser(input: UserInput, context: ActionContext): Promise<TdmsUser> {
    const id = nextNumber(this.dataset.users.map((user) => user.id), 'usr-', 4);
    const user: TdmsUser = { ...input, id, lastSignInAt: null };
    this.dataset.users = [...this.dataset.users, user];
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.administration,
      action: 'Create',
      recordOrBatchReference: user.organisationEmail,
      result: 'Completed',
      plainLanguageDetail: `TDMS user account created with access level ${user.role}.`,
    });
    this.persist();
    return delay(user);
  }

  async updateUser(id: string, input: UserInput, context: ActionContext): Promise<TdmsUser> {
    const existing = this.dataset.users.find((user) => user.id === id);
    if (!existing) throw new Error('User account not found.');
    const updated: TdmsUser = { ...existing, ...input };
    this.dataset.users = this.dataset.users.map((user) => (user.id === id ? updated : user));
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.administration,
      action: 'Edit',
      recordOrBatchReference: updated.organisationEmail,
      result: 'Completed',
      plainLanguageDetail: `TDMS user account updated. Access level ${updated.role}, account status ${updated.accountStatus}.`,
    });
    this.persist();
    return delay(updated);
  }

  async listActivityRecords(filters: ActivityFilters): Promise<UserActivityRecord[]> {
    const rows = this.dataset.activityRecords.filter((record) => {
      if (filters.action && record.action !== filters.action) return false;
      if (filters.result && record.result !== filters.result) return false;
      if (filters.pageOrFunction && record.pageOrFunction !== filters.pageOrFunction) return false;
      if (
        filters.search &&
        !includesText(
          [
            record.activityRecordNumber,
            record.userReference,
            record.recordOrBatchReference,
            record.plainLanguageDetail,
            record.pageOrFunction,
          ],
          filters.search,
        )
      ) {
        return false;
      }
      return true;
    });
    return delay(rows);
  }

  async recordActivity(
    record: Omit<UserActivityRecord, 'activityRecordNumber' | 'dateTime'>,
  ): Promise<UserActivityRecord> {
    const created = this.logActivity(record);
    this.persist();
    return delay(created);
  }

  // -- Prototype maintenance ----------------------------------------------

  async resetPrototypeData(): Promise<void> {
    this.dataset = createSeedDataset();
    this.persist();
    await delay(null);
  }
}
