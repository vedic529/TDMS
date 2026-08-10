import type { StudentRecord } from '@/types/student';
import { MOCK_CAMPUSES, MOCK_COLLEGES } from './colleges';
import { qualificationByCode } from './qualifications';
import { anchorDate, anchorDateTime } from './anchor';
import {
  deriveActualCourseDuration,
  deriveCollegeEmail,
  deriveGroup,
  deriveIntake,
  deriveState,
  suggestCourseDurationOption,
} from '@/lib/student-rules';

interface StudentSeed {
  studentId: string;
  firstName: string;
  lastName: string;
  campusId: string;
  qualificationCode: string;
  coeStatus: StudentRecord['coeStatus'];
  ctStudent: StudentRecord['ctStudent'];
  startOffsetDays: number;
  durationWeeks: number;
  primaryCountry: string;
  primaryPhone: string;
  remarks?: string;
}

const SEEDS: StudentSeed[] = [
  { studentId: 'ST20261001', firstName: 'Anas', lastName: 'Abbas', campusId: 'cam-aibt-hobart', qualificationCode: 'BSB80120', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: -28, durationWeeks: 52, primaryCountry: 'Pakistan', primaryPhone: '0412 445 001' },
  { studentId: 'ST20261002', firstName: 'Azeezat', lastName: 'Abdulazeez', campusId: 'cam-aibt-hobart', qualificationCode: 'BSB50420', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: -28, durationWeeks: 52, primaryCountry: 'Nigeria', primaryPhone: '0412 445 002' },
  { studentId: 'ST20261003', firstName: 'Edward', lastName: 'Abellanosa', campusId: 'cam-aibt-melbourne', qualificationCode: 'BSB50820', coeStatus: 'CoE', ctStudent: 'Yes', startOffsetDays: -28, durationWeeks: 26, primaryCountry: 'Philippines', primaryPhone: '0412 445 003', remarks: 'Credit transfer assessment recorded on enrolment.' },
  { studentId: 'ST20261004', firstName: 'Diana', lastName: 'Acuna Martinez', campusId: 'cam-aibt-melbourne', qualificationCode: 'BSB50420', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: -21, durationWeeks: 52, primaryCountry: 'Colombia', primaryPhone: '0412 445 004' },
  { studentId: 'ST20261005', firstName: 'Waqas', lastName: 'Afzal', campusId: 'cam-aibt-melbourne', qualificationCode: 'SIT50422', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: -21, durationWeeks: 78, primaryCountry: 'Pakistan', primaryPhone: '0412 445 005' },
  { studentId: 'ST20261006', firstName: 'Amy', lastName: 'Agmata', campusId: 'cam-aibt-melbourne', qualificationCode: 'SIT30821', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: -21, durationWeeks: 52, primaryCountry: 'Philippines', primaryPhone: '0412 445 006' },
  { studentId: 'ST20261007', firstName: "O'Shannie", lastName: 'Akim', campusId: 'cam-aibt-brisbane', qualificationCode: 'BSB50420', coeStatus: 'Non-CoE', ctStudent: 'No', startOffsetDays: -14, durationWeeks: 26, primaryCountry: 'Australia', primaryPhone: '0412 445 007' },
  { studentId: 'ST20261008', firstName: 'Afnan', lastName: 'Akram', campusId: 'cam-aibt-brisbane', qualificationCode: 'BSB80120', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: -14, durationWeeks: 52, primaryCountry: 'Bangladesh', primaryPhone: '0412 445 008' },
  { studentId: 'ST20261009', firstName: 'Regina', lastName: 'Ali', campusId: 'cam-aibti-sydney', qualificationCode: 'BSB60420', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: -14, durationWeeks: 78, primaryCountry: 'Indonesia', primaryPhone: '0412 445 009' },
  { studentId: 'ST20261010', firstName: 'Sufyan', lastName: 'Ali', campusId: 'cam-aibti-sydney', qualificationCode: 'BSB50820', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: -7, durationWeeks: 52, primaryCountry: 'Pakistan', primaryPhone: '0412 445 010' },
  { studentId: 'ST20261011', firstName: 'Inoke', lastName: 'Iftikar', campusId: 'cam-aibti-sydney', qualificationCode: 'CHC50125', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: -7, durationWeeks: 78, primaryCountry: 'Nepal', primaryPhone: '0412 445 011' },
  { studentId: 'ST20261012', firstName: 'Niroshan', lastName: 'Amalathas', campusId: 'cam-aibti-adelaide', qualificationCode: 'SIT50422', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: -7, durationWeeks: 52, primaryCountry: 'Sri Lanka', primaryPhone: '0412 445 012' },
  { studentId: 'ST20261013', firstName: 'Amit', lastName: 'Kumar', campusId: 'cam-aibti-adelaide', qualificationCode: 'SIT30821', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: 0, durationWeeks: 52, primaryCountry: 'India', primaryPhone: '0412 445 013' },
  { studentId: 'ST20261014', firstName: 'Javeria', lastName: 'Anar', campusId: 'cam-avi-perth', qualificationCode: 'AUR30620', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: 0, durationWeeks: 104, primaryCountry: 'Pakistan', primaryPhone: '0412 445 014' },
  { studentId: 'ST20261015', firstName: 'Anas', lastName: 'Murtuza Khan', campusId: 'cam-avi-perth', qualificationCode: 'BSB50820', coeStatus: 'Non-CoE', ctStudent: 'Yes', startOffsetDays: 0, durationWeeks: 26, primaryCountry: 'Australia', primaryPhone: '0412 445 015', remarks: 'Domestic student, part-time attendance approved.' },
  { studentId: 'ST20261016', firstName: 'Anchal', lastName: 'Sharma', campusId: 'cam-avi-melbourne', qualificationCode: 'BSB50420', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: 7, durationWeeks: 52, primaryCountry: 'India', primaryPhone: '0412 445 016' },
  { studentId: 'ST20261017', firstName: 'Anjali', lastName: 'Verma', campusId: 'cam-avi-melbourne', qualificationCode: 'BSB60420', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: 7, durationWeeks: 78, primaryCountry: 'India', primaryPhone: '0412 445 017' },
  { studentId: 'ST20261018', firstName: 'Shamlesh', lastName: 'Appiah', campusId: 'cam-aibt-hobart', qualificationCode: 'BSB60420', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: 7, durationWeeks: 52, primaryCountry: 'Ghana', primaryPhone: '0412 445 018' },
  { studentId: 'ST20261019', firstName: 'Thi Minh', lastName: 'Nguyen', campusId: 'cam-aibt-hobart', qualificationCode: 'SIT30821', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: 14, durationWeeks: 52, primaryCountry: 'Vietnam', primaryPhone: '0412 445 019' },
  { studentId: 'ST20261020', firstName: 'Carlos', lastName: 'Mendes', campusId: 'cam-aibt-hobart', qualificationCode: 'FBP30321', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: 14, durationWeeks: 52, primaryCountry: 'Brazil', primaryPhone: '0412 445 020' },
  { studentId: 'ST20261021', firstName: 'Sunita', lastName: 'Gurung', campusId: 'cam-aibt-melbourne', qualificationCode: 'CHC50125', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: 14, durationWeeks: 104, primaryCountry: 'Nepal', primaryPhone: '0412 445 021' },
  { studentId: 'ST20261022', firstName: 'Lucas', lastName: 'Fernandes', campusId: 'cam-aibt-melbourne', qualificationCode: 'BSB50420', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: 21, durationWeeks: 26, primaryCountry: 'Brazil', primaryPhone: '0412 445 022' },
  { studentId: 'ST20261023', firstName: 'Chen', lastName: 'Wei', campusId: 'cam-aibt-brisbane', qualificationCode: 'CHC33021', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: 21, durationWeeks: 52, primaryCountry: 'China', primaryPhone: '0412 445 023' },
  { studentId: 'ST20261024', firstName: 'Maria', lastName: 'Santos', campusId: 'cam-aibti-sydney', qualificationCode: 'CHC33021', coeStatus: 'Non-CoE', ctStudent: 'No', startOffsetDays: 21, durationWeeks: 26, primaryCountry: 'Australia', primaryPhone: '0412 445 024' },
  { studentId: 'ST20261025', firstName: 'Kwame', lastName: 'Boateng', campusId: 'cam-aibti-adelaide', qualificationCode: 'BSB50420', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: 28, durationWeeks: 52, primaryCountry: 'Ghana', primaryPhone: '0412 445 025' },
  { studentId: 'ST20261026', firstName: 'Somsak', lastName: 'Chaiyaporn', campusId: 'cam-avi-perth', qualificationCode: 'BSB50420', coeStatus: 'CoE', ctStudent: 'No', startOffsetDays: 28, durationWeeks: 26, primaryCountry: 'Thailand', primaryPhone: '0412 445 026' },
];

export const MOCK_STUDENTS: StudentRecord[] = SEEDS.map((seed, index) => {
  const campus = MOCK_CAMPUSES.find((entry) => entry.id === seed.campusId)!;
  const college = MOCK_COLLEGES.find((entry) => entry.id === campus.collegeId)!;
  const definition = qualificationByCode(seed.qualificationCode)!;

  const proposedStartDate = anchorDate(seed.startOffsetDays);
  const proposedEndDate = anchorDate(seed.startOffsetDays + seed.durationWeeks * 7);
  const actualCourseDuration = deriveActualCourseDuration(proposedStartDate, proposedEndDate);

  return {
    id: `stu-${seed.studentId.toLowerCase()}`,
    group: deriveGroup({ qualificationCode: seed.qualificationCode, campus, proposedStartDate }),
    intake: deriveIntake(proposedStartDate),
    collegeId: college.id,
    campusId: campus.id,
    collegeEmail: deriveCollegeEmail(seed.studentId, college),
    firstName: seed.firstName,
    lastName: seed.lastName,
    studentId: seed.studentId,
    coeStatus: seed.coeStatus,
    proposedStartDate,
    proposedEndDate,
    actualCourseDuration,
    courseDurationOption: suggestCourseDurationOption(actualCourseDuration, definition.durationOptions),
    qualificationTitle: definition.qualificationTitle,
    qualificationCode: seed.qualificationCode,
    ctStudent: seed.ctStudent,
    personalEmail: `${seed.firstName.toLowerCase().replace(/[^a-z]/g, '')}.${seed.lastName
      .toLowerCase()
      .replace(/[^a-z]/g, '')}@example.com`,
    primaryPhone: seed.primaryPhone,
    state: deriveState(campus),
    primaryCountry: seed.primaryCountry,
    remarks: seed.remarks ?? '',
    createdAt: anchorDateTime(-40 + index, 9, 15),
    updatedAt: anchorDateTime(-40 + index, 9, 15),
    isDeleted: false,
  } satisfies StudentRecord;
});
