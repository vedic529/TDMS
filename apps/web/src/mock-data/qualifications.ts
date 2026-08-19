import type { QualificationOffering, QualificationUnitSequence, UocType } from '@/types/reference';

/** Approved qualification catalogue used by the dependent dropdowns. */
export interface QualificationDefinition {
  qualificationCode: string;
  qualificationTitle: string;
  courseLevel: string;
  courseSector: string;
  fieldOfEducationBroad: string;
  fieldOfEducationNarrow: string;
  durationOptions: number[];
  totalCourseCost: number;
  units: Array<{ unitCode: string; unitTitle: string; uocType: UocType }>;
}

const theory: UocType = 'Theory';
const both: UocType = 'Theory and Practical';

export const QUALIFICATION_CATALOGUE: QualificationDefinition[] = [
  {
    qualificationCode: 'BSB50420',
    qualificationTitle: 'Diploma of Leadership and Management',
    courseLevel: 'Diploma',
    courseSector: 'VET',
    fieldOfEducationBroad: 'Management and Commerce',
    fieldOfEducationNarrow: 'Business and Management',
    durationOptions: [26, 52, 78],
    totalCourseCost: 12000,
    units: [
      { unitCode: 'BSBCMM511', unitTitle: 'Communicate with influence', uocType: theory },
      { unitCode: 'BSBCRT511', unitTitle: 'Develop critical thinking in others', uocType: theory },
      { unitCode: 'BSBLDR523', unitTitle: 'Lead and manage effective workplace relationships', uocType: theory },
      { unitCode: 'BSBOPS502', unitTitle: 'Manage business operational plans', uocType: theory },
      { unitCode: 'BSBPEF502', unitTitle: 'Develop and use emotional intelligence', uocType: theory },
      { unitCode: 'BSBTWK502', unitTitle: 'Manage team effectiveness', uocType: theory },
      { unitCode: 'BSBSTR502', unitTitle: 'Facilitate continuous improvement', uocType: theory },
      { unitCode: 'BSBXCM501', unitTitle: 'Lead communication in the workplace', uocType: theory },
    ],
  },
  {
    qualificationCode: 'BSB60420',
    qualificationTitle: 'Advanced Diploma of Leadership and Management',
    courseLevel: 'Advanced Diploma',
    courseSector: 'VET',
    fieldOfEducationBroad: 'Management and Commerce',
    fieldOfEducationNarrow: 'Business and Management',
    durationOptions: [52, 78, 104],
    totalCourseCost: 15500,
    units: [
      { unitCode: 'BSBCMM511', unitTitle: 'Communicate with influence', uocType: theory },
      { unitCode: 'BSBCRT511', unitTitle: 'Develop critical thinking in others', uocType: theory },
      { unitCode: 'BSBCRT611', unitTitle: 'Apply critical thinking for complex problem solving', uocType: theory },
      { unitCode: 'BSBLDR601', unitTitle: 'Lead and manage organisational change', uocType: theory },
      { unitCode: 'BSBLDR602', unitTitle: 'Provide leadership across the organisation', uocType: theory },
      { unitCode: 'BSBOPS601', unitTitle: 'Develop and implement business plans', uocType: theory },
      { unitCode: 'BSBPEF501', unitTitle: 'Manage personal and professional development', uocType: theory },
      { unitCode: 'BSBSTR601', unitTitle: 'Manage innovation and continuous improvement', uocType: theory },
    ],
  },
  {
    qualificationCode: 'BSB50820',
    qualificationTitle: 'Diploma of Project Management',
    courseLevel: 'Diploma',
    courseSector: 'VET',
    fieldOfEducationBroad: 'Management and Commerce',
    fieldOfEducationNarrow: 'Business and Management',
    durationOptions: [26, 52],
    totalCourseCost: 11500,
    units: [
      { unitCode: 'BSBPMG530', unitTitle: 'Manage project scope', uocType: theory },
      { unitCode: 'BSBPMG531', unitTitle: 'Manage project time', uocType: theory },
      { unitCode: 'BSBPMG532', unitTitle: 'Manage project quality', uocType: theory },
      { unitCode: 'BSBPMG533', unitTitle: 'Manage project cost', uocType: theory },
      { unitCode: 'BSBPMG534', unitTitle: 'Manage project human resources', uocType: theory },
      { unitCode: 'BSBPMG535', unitTitle: 'Manage project information and communication', uocType: theory },
      { unitCode: 'BSBPMG536', unitTitle: 'Manage project risk', uocType: theory },
      { unitCode: 'BSBPMG540', unitTitle: 'Manage project integration', uocType: theory },
    ],
  },
  {
    qualificationCode: 'BSB80120',
    qualificationTitle: 'Graduate Diploma of Management (Learning)',
    courseLevel: 'Graduate Diploma',
    courseSector: 'VET',
    fieldOfEducationBroad: 'Management and Commerce',
    fieldOfEducationNarrow: 'Business and Management',
    durationOptions: [52, 78],
    totalCourseCost: 17000,
    units: [
      { unitCode: 'BSBHRM611', unitTitle: 'Contribute to organisational performance development', uocType: theory },
      { unitCode: 'BSBHRM612', unitTitle: 'Contribute to the development of learning and development strategies', uocType: theory },
      { unitCode: 'BSBHRM613', unitTitle: 'Contribute to the development of learning and development strategy', uocType: theory },
      { unitCode: 'BSBLDR811', unitTitle: 'Lead strategic transformation', uocType: theory },
      { unitCode: 'BSBLDR812', unitTitle: 'Develop and cultivate collaborative partnerships and relationships', uocType: theory },
      { unitCode: 'BSBSTR801', unitTitle: 'Lead innovative thinking and practice', uocType: theory },
    ],
  },
  {
    qualificationCode: 'SIT50422',
    qualificationTitle: 'Diploma of Hospitality Management',
    courseLevel: 'Diploma',
    courseSector: 'VET',
    fieldOfEducationBroad: 'Food, Hospitality and Personal Services',
    fieldOfEducationNarrow: 'Food and Hospitality',
    durationOptions: [52, 78, 104],
    totalCourseCost: 16500,
    units: [
      { unitCode: 'SITXCCS015', unitTitle: 'Enhance customer service experiences', uocType: both },
      { unitCode: 'SITXCOM010', unitTitle: 'Manage conflict', uocType: theory },
      { unitCode: 'SITXFIN009', unitTitle: 'Manage finances within a budget', uocType: theory },
      { unitCode: 'SITXGLC002', unitTitle: 'Identify and manage legal risks and comply with law', uocType: theory },
      { unitCode: 'SITXHRM008', unitTitle: 'Roster staff', uocType: theory },
      { unitCode: 'SITXHRM009', unitTitle: 'Lead and manage people', uocType: theory },
      { unitCode: 'SITXMGT004', unitTitle: 'Monitor work operations', uocType: both },
      { unitCode: 'SITXWHS007', unitTitle: 'Implement and monitor work health and safety practices', uocType: theory },
    ],
  },
  {
    qualificationCode: 'SIT30821',
    qualificationTitle: 'Certificate III in Commercial Cookery',
    courseLevel: 'Certificate III',
    courseSector: 'VET',
    fieldOfEducationBroad: 'Food, Hospitality and Personal Services',
    fieldOfEducationNarrow: 'Food and Hospitality',
    durationOptions: [52, 78],
    totalCourseCost: 14000,
    units: [
      { unitCode: 'SITHCCC027', unitTitle: 'Prepare dishes using basic methods of cookery', uocType: both },
      { unitCode: 'SITHCCC028', unitTitle: 'Prepare appetisers and salads', uocType: both },
      { unitCode: 'SITHCCC029', unitTitle: 'Prepare stocks, sauces and soups', uocType: both },
      { unitCode: 'SITHCCC030', unitTitle: 'Prepare vegetable, fruit, eggs and farinaceous dishes', uocType: both },
      { unitCode: 'SITHCCC035', unitTitle: 'Prepare poultry dishes', uocType: both },
      { unitCode: 'SITHCCC036', unitTitle: 'Prepare meat dishes', uocType: both },
      { unitCode: 'SITHKOP009', unitTitle: 'Clean kitchen premises and equipment', uocType: both },
      { unitCode: 'SITXFSA005', unitTitle: 'Use hygienic practices for food safety', uocType: theory },
    ],
  },
  {
    qualificationCode: 'CHC50125',
    qualificationTitle: 'Diploma of Early Childhood Education and Care',
    courseLevel: 'Diploma',
    courseSector: 'VET',
    fieldOfEducationBroad: 'Society and Culture',
    fieldOfEducationNarrow: 'Human Welfare Studies and Services',
    durationOptions: [78, 104],
    totalCourseCost: 15000,
    units: [
      { unitCode: 'CHCECE041', unitTitle: 'Maintain a safe and healthy environment for children', uocType: theory },
      { unitCode: 'CHCECE042', unitTitle: 'Foster holistic early childhood learning and development', uocType: both },
      { unitCode: 'CHCECE043', unitTitle: 'Nurture creativity in children', uocType: both },
      { unitCode: 'CHCECE044', unitTitle: 'Facilitate compliance in a children education and care service', uocType: theory },
      { unitCode: 'CHCECE045', unitTitle: 'Foster positive and respectful interactions and behaviour', uocType: theory },
      { unitCode: 'CHCECE046', unitTitle: 'Implement strategies for the inclusion of all children', uocType: theory },
    ],
  },
  {
    qualificationCode: 'CHC33021',
    qualificationTitle: 'Certificate III in Individual Support',
    courseLevel: 'Certificate III',
    courseSector: 'VET',
    fieldOfEducationBroad: 'Society and Culture',
    fieldOfEducationNarrow: 'Human Welfare Studies and Services',
    durationOptions: [26, 52],
    totalCourseCost: 9500,
    units: [
      { unitCode: 'CHCCCS031', unitTitle: 'Provide individualised support', uocType: both },
      { unitCode: 'CHCCCS038', unitTitle: 'Facilitate the empowerment of people receiving support', uocType: theory },
      { unitCode: 'CHCCCS040', unitTitle: 'Support independence and wellbeing', uocType: both },
      { unitCode: 'CHCCOM005', unitTitle: 'Communicate and work in health or community services', uocType: theory },
      { unitCode: 'HLTWHS002', unitTitle: 'Follow safe work practices for direct client care', uocType: both },
    ],
  },
  {
    qualificationCode: 'FBP30321',
    qualificationTitle: 'Certificate III in Cake and Pastry',
    courseLevel: 'Certificate III',
    courseSector: 'VET',
    fieldOfEducationBroad: 'Food, Hospitality and Personal Services',
    fieldOfEducationNarrow: 'Food and Hospitality',
    durationOptions: [52],
    totalCourseCost: 13500,
    units: [
      { unitCode: 'FBPCAK3001', unitTitle: 'Produce basic cakes and cake decorations', uocType: both },
      { unitCode: 'FBPCAK3002', unitTitle: 'Produce pastry products', uocType: both },
      { unitCode: 'FBPCAK3003', unitTitle: 'Produce sweet yeast products', uocType: both },
      { unitCode: 'FBPCAK3004', unitTitle: 'Produce specialty cakes', uocType: both },
      { unitCode: 'FBPOPR3002', unitTitle: 'Apply quality systems and procedures', uocType: theory },
    ],
  },
  {
    qualificationCode: 'AUR30620',
    qualificationTitle: 'Certificate III in Light Vehicle Mechanical Technology',
    courseLevel: 'Certificate III',
    courseSector: 'VET',
    fieldOfEducationBroad: 'Engineering and Related Technologies',
    fieldOfEducationNarrow: 'Automotive Engineering and Technology',
    durationOptions: [78, 104],
    totalCourseCost: 16000,
    units: [
      { unitCode: 'AURETR112', unitTitle: 'Test and repair basic electrical circuits', uocType: both },
      { unitCode: 'AURLTB005', unitTitle: 'Diagnose and repair light vehicle braking systems', uocType: both },
      { unitCode: 'AURLTD005', unitTitle: 'Diagnose and repair light vehicle steering systems', uocType: both },
      { unitCode: 'AURLTE102', unitTitle: 'Diagnose and repair light vehicle engines', uocType: both },
      { unitCode: 'AURTTA104', unitTitle: 'Carry out servicing operations', uocType: both },
      { unitCode: 'AURAFA103', unitTitle: 'Communicate effectively in an automotive workplace', uocType: theory },
    ],
  },
];

export function qualificationByCode(code: string): QualificationDefinition | undefined {
  return QUALIFICATION_CATALOGUE.find((entry) => entry.qualificationCode === code);
}

/**
 * Approved college + campus + qualification offerings.
 * COL-04: the same offering must not be stored more than once.
 */
const OFFERING_MAP: Array<{ campusId: string; collegeId: string; qualificationCodes: string[] }> = [
  {
    collegeId: 'col-aibt',
    campusId: 'cam-aibt-hobart',
    qualificationCodes: ['BSB50420', 'BSB60420', 'BSB80120', 'SIT50422', 'SIT30821', 'FBP30321', 'AUR30620'],
  },
  {
    collegeId: 'col-aibt',
    campusId: 'cam-aibt-melbourne',
    qualificationCodes: ['BSB50420', 'BSB60420', 'BSB50820', 'SIT50422', 'SIT30821', 'CHC50125'],
  },
  {
    collegeId: 'col-aibt',
    campusId: 'cam-aibt-brisbane',
    qualificationCodes: ['BSB50420', 'BSB80120', 'SIT50422', 'CHC33021'],
  },
  {
    collegeId: 'col-aibti',
    campusId: 'cam-aibti-sydney',
    qualificationCodes: ['BSB50420', 'BSB60420', 'BSB50820', 'CHC50125', 'CHC33021'],
  },
  {
    collegeId: 'col-aibti',
    campusId: 'cam-aibti-adelaide',
    qualificationCodes: ['BSB50420', 'SIT50422', 'SIT30821'],
  },
  {
    collegeId: 'col-avi',
    campusId: 'cam-avi-perth',
    qualificationCodes: ['BSB50420', 'BSB50820', 'AUR30620'],
  },
  {
    collegeId: 'col-avi',
    campusId: 'cam-avi-melbourne',
    qualificationCodes: ['BSB50420', 'BSB60420', 'CHC33021'],
  },
];

export const MOCK_QUALIFICATION_OFFERINGS: QualificationOffering[] = OFFERING_MAP.flatMap((entry) =>
  entry.qualificationCodes.map((code) => {
    const definition = qualificationByCode(code)!;
    return {
      id: `off-${entry.campusId}-${code}`,
      collegeId: entry.collegeId,
      campusId: entry.campusId,
      qualificationCode: code,
      qualificationTitle: definition.qualificationTitle,
      durationOptions: definition.durationOptions,
      isActive: true,
    } satisfies QualificationOffering;
  }),
);

/**
 * SRS 9.4 - Page 4B Qualification and Unit Sequence Data.
 * One record per college/campus offering and unit, carrying the approved
 * teaching-order Sequence ID used by timetable generation (TT-08).
 */
export const MOCK_QUALIFICATION_UNIT_SEQUENCES: QualificationUnitSequence[] = MOCK_QUALIFICATION_OFFERINGS.flatMap(
  (offering) => {
    const definition = qualificationByCode(offering.qualificationCode)!;
    return definition.units.map((unit, index) => ({
      id: `qus-${offering.campusId}-${offering.qualificationCode}-${unit.unitCode}`,
      recordId: `QUS-${offering.qualificationCode}-${String(index + 1).padStart(2, '0')}`,
      qualificationCode: offering.qualificationCode,
      qualificationTitle: offering.qualificationTitle,
      unitCode: unit.unitCode,
      unitTitle: unit.unitTitle,
      deliveryOrder: index + 1,
      collegeId: offering.collegeId,
      campusId: offering.campusId,
      uocType: unit.uocType,
      isDeleted: false,
    }));
  },
);
