import type {
  ApiCampus,
  ApiCollege,
  ApiCourse,
  ApiQualification,
  ApiQualificationUnit,
  ApiFacility,
} from '@/services/reference-api';
import type {
  Campus,
  College,
  CourseRecord,
  FacilityRecord,
  QualificationUnitSequence,
  UocType,
} from '@/types/reference';

/**
 * Map the real API's wire shapes onto the display types the reference-data
 * screens already use.
 *
 * A translation layer rather than a rename of the display types: the API speaks
 * snake_case with integer keys, the components were written against camelCase
 * with string ids, and changing every component to match would be a large,
 * risky edit for no user-visible gain. Keeping the seam explicit also means the
 * next module can adopt the same API without inheriting this module's view
 * shapes.
 *
 * Nothing here invents a value. Where the API has no data, the field is empty.
 */

/**
 * How a Qualification Code reads when none has been issued.
 *
 * ELICOS courses have no VET Code. The database stores NULL and the API reports
 * it as `null`, so "no code" stays distinguishable from a code that happens to
 * read "NA"; the substitution happens here, at the display edge, and only here.
 */
export const NO_QUALIFICATION_CODE = 'NA';

export function qualificationCodeLabel(code: string | null | undefined): string {
  return code ?? NO_QUALIFICATION_CODE;
}

export function toCollege(row: ApiCollege): College {
  return {
    id: String(row.id),
    collegeShortName: row.college_short_name,
    collegeFullName: row.college_full_name,
    isActive: row.is_active,
    emailDomain: row.email_domain ?? '',
  };
}

export function toCampus(row: ApiCampus, collegeId: string): Campus {
  return {
    id: String(row.id),
    // The approved model is many-to-many (DBQ-04), so a campus has no single
    // owning college. The caller supplies the college it was listed under.
    collegeId,
    campusName: row.campus_name,
    campusLocation: row.campus_location,
    state: row.state,
    isActive: row.is_active,
  };
}

/**
 * The course status is whatever FastAPI says it is.
 *
 * This used to derive the status from the code — `ACT*` meant Active, `SUP*`
 * meant Superseded, and **anything else fell through to Inactive**. That is why
 * 104262B displayed as Inactive: its stored code did not begin with those
 * letters, so the browser overrode the backend and invented a status the API had
 * never sent.
 *
 * COL-05 is explicitly open-ended — a course may be "active, inactive,
 * superseded or in another approved status" — so a closed set of strings in the
 * browser can only ever be wrong about the next approved value. The status is
 * decided once, in the database, and passed through here unchanged.
 */
function toCourseStatus(code: string, label: string): string {
  return label || code;
}

export function toCourseRecord(row: ApiCourse): CourseRecord {
  return {
    id: String(row.id),
    collegeId: String(row.college_id),
    campusId: String(row.campus_id),
    courseCode: row.course_code,
    qualificationCode: qualificationCodeLabel(row.qualification_code),
    qualificationTitle: row.qualification_title,
    courseStatus: toCourseStatus(row.course_status_code, row.course_status_label),
    courseLevel: row.course_level ?? '',
    fieldOfEducationBroad: row.field_of_education_broad ?? '',
    fieldOfEducationNarrow: row.field_of_education_narrow ?? '',
    courseSector: row.course_sector ?? '',
    // DBQ-03: durations are approved options. The list shows the longest, which
    // is the full-length course; the form edits the whole set.
    durationInWeeks: row.duration_options.length
      ? Math.max(...row.duration_options)
      : 0,
    totalCourseCost: row.total_course_cost === null ? 0 : Number(row.total_course_cost),
    isDeleted: row.is_deleted,
  };
}

/** SRS §5.3 UoC Type. The API uses the enum spelling; the interface uses prose. */
function toUocType(value: string | null): UocType {
  return value === 'THEORY_AND_PRACTICAL' ? 'Theory and Practical' : 'Theory';
}

export function toQualificationUnit(
  row: ApiQualificationUnit,
  collegeId = '',
  campusId = '',
): QualificationUnitSequence {
  return {
    id: String(row.id),
    recordId: String(row.id),
    qualificationCode: qualificationCodeLabel(row.qualification_code),
    qualificationTitle: row.qualification_title,
    unitCode: row.unit_code,
    unitTitle: row.unit_title,
    // C-1: orders the rows; the SRS states it is not a displayed Page 4B field.
    deliveryOrder: row.delivery_order,
    // Page 4B filters by college/campus, which the sequence itself does not
    // carry — a qualification's unit order is the same wherever it is taught.
    collegeId,
    campusId,
    uocType: toUocType(row.uoc_type),
    isDeleted: row.is_deleted,
  };
}

export function toQualificationOption(row: ApiQualification) {
  return {
    value: String(row.id),
    label: `${qualificationCodeLabel(row.qualification_code)} — ${row.qualification_title}`,
  };
}

/**
 * Facility Data as the table shows it.
 *
 * `state` and `campusName` arrive already resolved through the campus, so this
 * only renames fields to the frontend's casing. Nothing is derived here — a
 * value the API did not send is a value the table does not show.
 */
export function toFacilityRecord(row: ApiFacility): FacilityRecord {
  return {
    id: String(row.id),
    classroomName: row.facility_reference,
    campusId: String(row.campus_id),
    campusName: row.campus_name,
    state: row.state,
    sourceLocation: row.source_location,
    classroomType: row.facility_type,
    capacity: row.capacity,
    isActive: row.is_active,
    collegeShortNames: row.college_short_names,
    faculties: row.faculties.map((rule) => ({
      faculty: rule.faculty,
      monday: rule.monday,
      tuesday: rule.tuesday,
      wednesday: rule.wednesday,
      thursday: rule.thursday,
      friday: rule.friday,
      remarks: rule.remarks,
    })),
  };
}
