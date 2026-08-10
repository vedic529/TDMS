import type { StagedRowIssue, StagedStudentRow } from '@/types/import';
import type { TdmsDataset } from './dataset';

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

function matchCollege(dataset: TdmsDataset, value: string) {
  const needle = value.trim().toLowerCase();
  if (!needle) return undefined;
  return dataset.colleges.find(
    (college) =>
      college.collegeFullName.toLowerCase() === needle || college.collegeShortName.toLowerCase() === needle,
  );
}

function matchCampus(dataset: TdmsDataset, collegeId: string | undefined, value: string) {
  const needle = value.trim().toLowerCase();
  if (!needle) return undefined;
  return dataset.campuses.find(
    (campus) =>
      (!collegeId || campus.collegeId === collegeId) &&
      (campus.campusName.toLowerCase() === needle || campus.campusLocation.toLowerCase() === needle),
  );
}

function matchQualification(dataset: TdmsDataset, collegeId?: string, campusId?: string, value?: string) {
  const needle = (value ?? '').trim().toLowerCase();
  if (!needle) return undefined;
  return dataset.qualificationOfferings.find(
    (offering) =>
      (!collegeId || offering.collegeId === collegeId) &&
      (!campusId || offering.campusId === campusId) &&
      (offering.qualificationCode.toLowerCase() === needle ||
        offering.qualificationTitle.toLowerCase() === needle),
  );
}

export function validateStagedRows(rows: StagedStudentRow[], dataset: TdmsDataset): StagedStudentRow[] {
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
    if (row.personalEmail.trim() && !EMAIL.test(row.personalEmail.trim())) {
      issues.push({
        field: 'Personal Email',
        message: `Personal Email "${row.personalEmail}" is not a valid email address. Correct or clear the value.`,
      });
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
