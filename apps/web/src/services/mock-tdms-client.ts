import type {
  AccessRequest,
  AccountStatus,
  DashboardOverview,
  NotificationOutcome,
  RequestableRole,
  TdmsRole,
  TdmsUser,
} from '@/types/auth';
import type { ActivityFilters, UserActivityRecord } from '@/types/activity';
import type { CourseRecord, QualificationUnitSequence } from '@/types/reference';
import type { SoftDeletable, SoftDeleteMetadata } from '@/types/common';

import { addDays, nowIso, today } from '@/lib/format';
import { PROPOSED_RECYCLE_PERIOD_DAYS } from '@/lib/reasons';
import { SRS_PAGE_REFERENCE } from '@/lib/interface-names';
import {
  ROLE_LABELS,
  canDecideAccessRequests,
  canManageUserRoles,
  requestableRolesFor,
} from '@/lib/permissions';
import { createSeedDataset } from '@/mock-data';

import type { ReferenceDataBundle, TdmsDataset } from './dataset';
import { PROTOTYPE_STORAGE_KEYS, readPrototypeValue, writePrototypeValue } from './prototype-storage';
import type {
  ActionContext,
  CourseFilters,
  CourseInput,
  QualificationUnitFilters,
  QualificationUnitInput,
  ReasonedRequest,
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
    // A dataset stored before students moved to the database still carries a
    // `students` array. Reseeding on that shape drops it rather than keeping a
    // stale copy of records that now live in PostgreSQL.
    if (stored && Array.isArray(stored.trainers) && !('students' in stored)) {
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
    };
  }

  // -- reference data ------------------------------------------------------

  async getReferenceData(): Promise<ReferenceDataBundle> {
    // Groups come from the student records, which now live in the database —
    // this bundle no longer supplies them, and no caller reads them.
    const groups: string[] = [];

    return delay({
      colleges: this.dataset.colleges,
      campuses: this.dataset.campuses,
      qualificationOfferings: this.dataset.qualificationOfferings,
      qualificationUnitSequences: activeOnly(this.dataset.qualificationUnitSequences),
      facilities: this.dataset.facilities,
      // Always empty: trainer records live in the database (27 August 2026).
      trainers: activeOnly(this.dataset.trainers),
      groups,
    });
  }

  // -- Trainer Data --------------------------------------------------------
  // Removed 27 August 2026: trainer records live in PostgreSQL and are reached
  // through `services/trainers-api.ts`. No trainer is held in browser storage.

  // -- Course Data ---------------------------------------------------------

  async listCourses(filters: CourseFilters): Promise<CourseRecord[]> {
    const rows = activeOnly(this.dataset.courses).filter((course) => {
      if (filters.collegeId && course.collegeId !== filters.collegeId) return false;
      if (filters.campusId && course.campusId !== filters.campusId) return false;
      if (filters.courseStatus && course.courseStatus !== filters.courseStatus) return false;
      if (
        filters.search &&
        !includesText([course.courseCode, course.qualificationCode, course.qualificationTitle, course.courseLevel], filters.search)
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
      plainLanguageDetail: `Course ${course.courseCode} - ${course.qualificationTitle} added to reference data.`,
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
        (a, b) => a.qualificationCode.localeCompare(b.qualificationCode) || (a.deliveryOrder ?? Number.MAX_SAFE_INTEGER) - (b.deliveryOrder ?? Number.MAX_SAFE_INTEGER),
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
      plainLanguageDetail: `Unit ${record.unitCode} added to ${record.qualificationCode} at sequence ${record.deliveryOrder}.`,
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

  // -- Access requests (Access Model v1.1) ---------------------------------
  //
  // The prototype mirrors the API rules so the interface behaves the same in
  // demo mode. The API remains authoritative: these checks shape the UI, they
  // do not secure anything.

  async getMyAccessRequest(userId: string): Promise<AccessRequest | null> {
    const pending = this.dataset.accessRequests.find(
      (request) => request.requesterUserId === userId && request.status === 'PENDING',
    );
    return delay(pending ?? null);
  }

  async listAccessRequests(): Promise<AccessRequest[]> {
    return delay(
      [...this.dataset.accessRequests].sort((a, b) => b.requestedAt.localeCompare(a.requestedAt)),
    );
  }

  async submitAccessRequest(
    requestedRole: RequestableRole,
    context: ActionContext,
  ): Promise<{ request: AccessRequest; notification: NotificationOutcome }> {
    const actor = context.actor;

    if (!requestableRolesFor(actor.role).includes(requestedRole)) {
      throw new Error(
        `${ROLE_LABELS[requestedRole]} is not a role you can request from ${ROLE_LABELS[actor.role]}.`,
      );
    }
    // One pending request at a time. The database enforces this with a partial
    // unique index; here it stops the interface offering an impossible action.
    if (this.dataset.accessRequests.some((r) => r.requesterUserId === actor.id && r.status === 'PENDING')) {
      throw new Error(
        'You already have a pending request. Wait for a decision, or cancel it before requesting a different role.',
      );
    }

    const request: AccessRequest = {
      id: nextNumber(this.dataset.accessRequests.map((r) => r.id), 'req-', 4),
      requesterUserId: actor.id,
      requesterDisplayName: actor.displayName,
      requesterEmail: actor.organisationEmail,
      roleAtRequest: actor.role,
      requestedRole,
      status: 'PENDING',
      requestedAt: nowIso(),
      decidedAt: null,
      decidedByUserId: null,
      decidedByEmail: null,
    };
    this.dataset.accessRequests = [...this.dataset.accessRequests, request];

    this.logActivity({
      ...this.actorFields(actor),
      pageOrFunction: SRS_PAGE_REFERENCE.administration,
      action: 'Create',
      recordOrBatchReference: request.id,
      result: 'Completed',
      plainLanguageDetail: `Requested ${ROLE_LABELS[requestedRole]} access from ${ROLE_LABELS[actor.role]}.`,
    });
    this.persist();

    return delay({
      request,
      // The prototype sends no email and must not claim otherwise.
      notification: {
        delivered: false,
        provider: 'development',
        detail:
          'Recorded locally. No email was sent: Microsoft Graph Mail.Send is not configured for the approved sender.',
      },
    });
  }

  async cancelAccessRequest(id: string, context: ActionContext): Promise<AccessRequest> {
    const request = this.dataset.accessRequests.find((entry) => entry.id === id);
    if (!request) throw new Error('Access request not found.');
    if (request.requesterUserId !== context.actor.id) {
      throw new Error('You can only cancel your own access request.');
    }
    if (request.status !== 'PENDING') throw new Error('This access request has already been decided.');

    // Cancelled, never deleted: request history stays available.
    const updated: AccessRequest = {
      ...request,
      status: 'CANCELLED',
      decidedAt: nowIso(),
      decidedByUserId: context.actor.id,
      decidedByEmail: context.actor.organisationEmail,
    };
    this.dataset.accessRequests = this.dataset.accessRequests.map((entry) =>
      entry.id === id ? updated : entry,
    );
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.administration,
      action: 'Edit',
      recordOrBatchReference: id,
      result: 'Cancelled by the user',
      plainLanguageDetail: `Cancelled their own request for ${ROLE_LABELS[request.requestedRole]}.`,
    });
    this.persist();
    return delay(updated);
  }

  private decideAccessRequest(
    id: string,
    decision: 'APPROVED' | 'DENIED',
    context: ActionContext,
  ): AccessRequest {
    const request = this.dataset.accessRequests.find((entry) => entry.id === id);
    if (!request) throw new Error('Access request not found.');
    // The first decision closes the request; a second must not overwrite it.
    if (request.status !== 'PENDING') throw new Error('This access request has already been decided.');
    if (request.requesterUserId === context.actor.id) {
      throw new Error('You cannot decide your own access request.');
    }
    if (!canDecideAccessRequests(context.actor)) {
      throw new Error('Deciding an access request requires Super Admin access.');
    }

    const updated: AccessRequest = {
      ...request,
      status: decision,
      decidedAt: nowIso(),
      decidedByUserId: context.actor.id,
      decidedByEmail: context.actor.organisationEmail,
    };
    this.dataset.accessRequests = this.dataset.accessRequests.map((entry) =>
      entry.id === id ? updated : entry,
    );

    if (decision === 'APPROVED') {
      // The role change and the closed request move together.
      this.dataset.users = this.dataset.users.map((user) =>
        user.id === request.requesterUserId ? { ...user, role: request.requestedRole } : user,
      );
    }

    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.administration,
      action: decision === 'APPROVED' ? 'Edit' : 'Edit',
      recordOrBatchReference: id,
      result: 'Completed',
      plainLanguageDetail:
        decision === 'APPROVED'
          ? `Approved ${request.requesterEmail}: ${ROLE_LABELS[request.roleAtRequest]} to ${ROLE_LABELS[request.requestedRole]}.`
          : `Denied ${request.requesterEmail}: request for ${ROLE_LABELS[request.requestedRole]}. Their access level is unchanged.`,
    });
    this.persist();
    return updated;
  }

  async approveAccessRequest(id: string, context: ActionContext): Promise<AccessRequest> {
    return delay(this.decideAccessRequest(id, 'APPROVED', context));
  }

  async denyAccessRequest(id: string, context: ActionContext): Promise<AccessRequest> {
    return delay(this.decideAccessRequest(id, 'DENIED', context));
  }

  async changeUserRole(id: string, role: TdmsRole, context: ActionContext): Promise<TdmsUser> {
    const target = this.dataset.users.find((user) => user.id === id);
    if (!target) throw new Error('User account not found.');
    if (!canManageUserRoles(context.actor)) {
      throw new Error('Changing a TDMS access level requires Super Admin access.');
    }
    // Two administrative lockout protections, both also enforced by the API.
    if (target.id === context.actor.id) {
      throw new Error('You cannot change your own access level. Ask another Super Admin to make this change.');
    }
    if (target.role === role) {
      throw new Error(`${target.organisationEmail} already has ${ROLE_LABELS[role]} access.`);
    }
    if (target.role === 'SUPER_ADMIN' && role !== 'SUPER_ADMIN' && this.activeSuperAdminCount(target.id) === 0) {
      throw new Error(
        'This change would leave TDMS with no active Super Admin. Grant Super Admin to another account first.',
      );
    }

    const updated: TdmsUser = { ...target, role };
    this.dataset.users = this.dataset.users.map((user) => (user.id === id ? updated : user));
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.administration,
      action: 'Edit',
      recordOrBatchReference: target.organisationEmail,
      result: 'Completed',
      plainLanguageDetail: `Changed ${target.organisationEmail}: ${ROLE_LABELS[target.role]} to ${ROLE_LABELS[role]}.`,
    });
    this.persist();
    return delay(updated);
  }

  async changeUserAccountStatus(
    id: string,
    status: AccountStatus,
    context: ActionContext,
  ): Promise<TdmsUser> {
    const target = this.dataset.users.find((user) => user.id === id);
    if (!target) throw new Error('User account not found.');
    if (!canManageUserRoles(context.actor)) {
      throw new Error('Changing an account status requires Super Admin access.');
    }
    if (target.id === context.actor.id) {
      throw new Error('You cannot change your own account status.');
    }
    if (target.role === 'SUPER_ADMIN' && status !== 'ACTIVE' && this.activeSuperAdminCount(target.id) === 0) {
      throw new Error(
        'This change would leave TDMS with no active Super Admin. Grant Super Admin to another account first.',
      );
    }

    const updated: TdmsUser = { ...target, accountStatus: status };
    this.dataset.users = this.dataset.users.map((user) => (user.id === id ? updated : user));
    this.logActivity({
      ...this.actorFields(context.actor),
      pageOrFunction: SRS_PAGE_REFERENCE.administration,
      action: 'Edit',
      recordOrBatchReference: target.organisationEmail,
      result: 'Completed',
      plainLanguageDetail: `Changed ${target.organisationEmail}: ${target.accountStatus} to ${status}.`,
    });
    this.persist();
    return delay(updated);
  }

  /** Active Super Admins, optionally ignoring one account being changed. */
  private activeSuperAdminCount(excludingUserId?: string): number {
    return this.dataset.users.filter(
      (user) =>
        user.role === 'SUPER_ADMIN' && user.accountStatus === 'ACTIVE' && user.id !== excludingUserId,
    ).length;
  }

  async getDashboardOverview(): Promise<DashboardOverview> {
    const users = this.dataset.users;
    const count = (role: TdmsRole) => users.filter((user) => user.role === role).length;
    return delay({
      pendingAccessRequests: this.dataset.accessRequests.filter((r) => r.status === 'PENDING').length,
      activeUsers: users.filter((user) => user.accountStatus === 'ACTIVE').length,
      viewerCount: count('VIEWER'),
      dataEditorCount: count('DATA_EDITOR'),
      adminCount: count('ADMIN'),
      superAdminCount: count('SUPER_ADMIN'),
      inactiveOrDisabledUsers: users.filter((user) => user.accountStatus !== 'ACTIVE').length,
    });
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
