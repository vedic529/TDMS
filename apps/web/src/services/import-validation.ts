import type { StagedRowIssue, StagedStudentRow } from '@/types/import';
import type { StudentRecord } from '@/types/student';
import { validateGroup } from '@/lib/student-rules';
import type { Campus, College, QualificationOffering } from '@/types/reference';

/**
 * The approved reference values a staged row is checked against.
 *
 * Narrowed to the three lists this module actually reads so that **real**
 * reference data can be passed in. It used to take the whole prototype dataset,
 * which meant a student file carrying a genuine campus address —
 * `132-146 Elizabeth Street, HOBART, Tasmania 7000` — was compared against an
 * invented one and rejected as unmatched.
 */
export interface ReferenceLookups {
  colleges: College[];
  campuses: Campus[];
  qualificationOfferings: QualificationOffering[];
  /** Existing students, for the DATA-01 duplicate Student ID check. */
  students: Array<Pick<StudentRecord, 'studentId' | 'isDeleted'>>;
}

/**
 * Bulk Student Import staging validation (BULK-04).
 *
 * Checks required columns and values, data formats, duplicate Student IDs and
 * approved college, campus and qualification mappings. Every message names the
 * affected field, explains the problem in plain language and says what must be
 * corrected (BULK-05 / SRS 2.3).
 *
 * A row the user has excluded keeps the "Excluded by user" status and is not
 * re-checked (BULK-06).
 */

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Characters that look like a space but are not one.
 *
 * A student file carrying `Tasmania 7000` and a database holding
 * `Tasmania 7000` are identical on screen and different to a comparison. That
 * single non-breaking space rejected a campus that matches exactly. Zero-width
 * characters cause the same failure while being invisible even in an error
 * message.
 */
const INVISIBLE = /[ ​‌‍﻿]/g;

/** Compare a source value with approved reference data. */
function normalise(value: string): string {
  return value.replace(INVISIBLE, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
}

/**
 * Personal Email may hold several addresses separated by commas.
 *
 * Students supply more than one — a personal address and an agent's, or two of
 * their own. Approved 14 August 2026: they are stored comma-separated, and each
 * address is validated on its own so one malformed entry is reported rather than
 * the whole field being called invalid.
 */
export function splitEmails(value: string): string[] {
  return value
    .split(',')
    .map((entry) => entry.replace(INVISIBLE, ' ').trim())
    .filter(Boolean);
}

function invalidEmails(value: string): string[] {
  return splitEmails(value).filter((entry) => !EMAIL.test(entry));
}

function matchCollege(dataset: ReferenceLookups, value: string) {
  const needle = normalise(value);
  if (!needle) return undefined;
  return dataset.colleges.find(
    (college) =>
      normalise(college.collegeFullName) === needle ||
      normalise(college.collegeShortName) === needle,
  );
}

function matchCampus(dataset: ReferenceLookups, collegeId: string | undefined, value: string) {
  const needle = normalise(value);
  if (!needle) return undefined;
  return dataset.campuses.find(
    (campus) =>
      (!collegeId || campus.collegeId === collegeId) &&
      (normalise(campus.campusName) === needle ||
        normalise(campus.campusLocation) === needle ||
        // One site, several spellings across source systems.
        (campus.sourceAddresses ?? []).some((address) => normalise(address) === needle)),
  );
}

function matchQualification(
  dataset: ReferenceLookups,
  collegeId?: string,
  campusId?: string,
  value?: string,
) {
  const needle = normalise(value ?? '');
  if (!needle) return undefined;
  return dataset.qualificationOfferings.find(
    (offering) =>
      (!collegeId || offering.collegeId === collegeId) &&
      (!campusId || offering.campusId === campusId) &&
      (normalise(offering.qualificationCode) === needle ||
        normalise(offering.qualificationTitle) === needle ||
        // A student enrolled under a retired code is in the current
        // qualification — CHC30121 resolves to CHC30125.
        (offering.supersededCodes ?? []).some((code) => normalise(code) === needle)),
  );
}

export function validateStagedRows(
  rows: StagedStudentRow[],
  dataset: ReferenceLookups,
): StagedStudentRow[] {
  const idCounts = new Map<string, number>();
  rows.forEach((row) => {
    if (row.status === 'Excluded by user') return;
    const key = row.studentId.trim().toUpperCase();
    if (!key) return;
    idCounts.set(key, (idCounts.get(key) ?? 0) + 1);
  });

  const existingIds = new Set(
    dataset.students.filter((student) => !student.isDeleted).map((student) => student.studentId.toUpperCase()),
  );

  return rows.map((row) => {
    if (row.status === 'Excluded by user') {
      return { ...row, issues: [] };
    }

    const issues: StagedRowIssue[] = [];
    let unmatchedReference = false;
    let duplicate = false;

    // Required values
    if (!row.studentId.trim()) {
      issues.push({
        field: 'Student ID',
        message: 'Student ID is blank. Enter the Student ID before saving, or exclude this row.',
      });
    }
    if (!row.firstName.trim()) {
      issues.push({ field: 'First Name', message: 'First Name is blank. Enter the student first name.' });
    }

    // Duplicate Student ID (DATA-01)
    const key = row.studentId.trim().toUpperCase();
    if (key) {
      if (existingIds.has(key)) {
        duplicate = true;
        issues.push({
          field: 'Student ID',
          message: `Student ID ${row.studentId} already exists in the database. Follow the approved duplicate rule: correct the Student ID or exclude the row.`,
        });
      } else if ((idCounts.get(key) ?? 0) > 1) {
        duplicate = true;
        issues.push({
          field: 'Student ID',
          message: `Student ID ${row.studentId} appears more than once in this file. Keep one row and exclude the others.`,
        });
      }
    }

    // Approved reference mappings
    const college = matchCollege(dataset, row.collegeValue);
    if (!college) {
      unmatchedReference = true;
      issues.push({
        field: 'College',
        message: `College "${row.collegeValue || '(blank)'}" cannot be matched to approved reference data. Select an approved college name.`,
      });
    }

    const campus = matchCampus(dataset, college?.id, row.campusValue);
    if (!campus) {
      unmatchedReference = true;
      issues.push({
        field: 'Campus',
        message: `Campus "${row.campusValue || '(blank)'}" is not an approved campus for the selected college. Select an approved campus.`,
      });
    }

    const offering = matchQualification(dataset, college?.id, campus?.id, row.qualificationValue);
    if (!offering) {
      unmatchedReference = true;
      issues.push({
        field: 'Qualification',
        message: `Qualification "${row.qualificationValue || '(blank)'}" is not offered by the selected college and campus. Select an approved qualification.`,
      });
    }

    // Formats
    if (row.proposedStartDate && !ISO_DATE.test(row.proposedStartDate.trim())) {
      issues.push({
        field: 'Proposed Start Date',
        message: `Proposed Start Date "${row.proposedStartDate}" is not in the YYYY-MM-DD format. Correct the date.`,
      });
    }
    if (row.proposedEndDate && !ISO_DATE.test(row.proposedEndDate.trim())) {
      issues.push({
        field: 'Proposed End Date',
        message: `Proposed End Date "${row.proposedEndDate}" is not in the YYYY-MM-DD format. Correct the date.`,
      });
    }
    if (
      ISO_DATE.test(row.proposedStartDate.trim()) &&
      ISO_DATE.test(row.proposedEndDate.trim()) &&
      row.proposedEndDate.trim() <= row.proposedStartDate.trim()
    ) {
      issues.push({
        field: 'Proposed End Date',
        message: 'Proposed End Date must be after Proposed Start Date.',
      });
    }
    const badEmails = invalidEmails(row.personalEmail);
    if (badEmails.length > 0) {
      issues.push({
        field: 'Personal Email',
        message:
          badEmails.length === 1
            ? `Personal Email "${badEmails[0]}" is not a valid email address. Correct or clear the value.`
            : `Personal Email contains ${badEmails.length} invalid addresses: ${badEmails
                .map((entry) => `"${entry}"`)
                .join(', ')}. Separate several addresses with commas.`,
      });
    }
    // Group must match the qualification, using the same rule as Single
    // Student Entry. Only checked once the qualification resolves - reporting
    // "Group 5 is invalid" for a row whose qualification is unrecognised would
    // send the user to correct the wrong field.
    if (offering) {
      const groupProblem = validateGroup(offering.qualificationCode, row.group);
      if (groupProblem) {
        issues.push({ field: 'Group', message: groupProblem });
      }
    }

    if (row.coeStatus.trim() && !['CoE', 'Non-CoE'].includes(row.coeStatus.trim())) {
      issues.push({
        field: 'CoE / Non-CoE',
        message: `CoE / Non-CoE must be "CoE" or "Non-CoE". "${row.coeStatus}" is not an approved value.`,
      });
    }

    const status: StagedStudentRow['status'] = duplicate
      ? 'Duplicate'
      : unmatchedReference
        ? 'Unmatched reference'
        : issues.length > 0
          ? 'Needs correction'
          : 'Ready';

    return {
      ...row,
      resolvedCollegeId: college?.id,
      resolvedCampusId: campus?.id,
      resolvedQualificationCode: offering?.qualificationCode,
      issues,
      status,
    };
  });
}

/** A staged row blocks the save unless it is Ready or deliberately excluded. */
export function isBlockingRow(row: StagedStudentRow): boolean {
  return row.status !== 'Ready' && row.status !== 'Excluded by user';
}

export function countByStatus(rows: StagedStudentRow[]) {
  return {
    ready: rows.filter((row) => row.status === 'Ready').length,
    needsCorrection: rows.filter((row) => row.status === 'Needs correction').length,
    duplicate: rows.filter((row) => row.status === 'Duplicate').length,
    unmatched: rows.filter((row) => row.status === 'Unmatched reference').length,
    excluded: rows.filter((row) => row.status === 'Excluded by user').length,
    corrected: rows.filter((row) => row.corrected).length,
  };
}
