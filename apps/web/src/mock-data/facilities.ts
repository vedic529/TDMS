import type { Facility } from '@/types/reference';

/**
 * TT-15: facility data used for clash and capacity checking must include at
 * least a facility reference, campus, facility type, capacity and active
 * status. OD-09 keeps the wider facility structure and any separate maintenance
 * page open, so TDMS stores only the minimum named in TT-15 and does not create
 * a fifth main navigation page.
 */
export const MOCK_FACILITIES: Facility[] = [
  { id: 'fac-hob-c1', facilityReference: 'HOB-C1', campusId: 'cam-aibt-hobart', facilityType: 'Classroom', capacity: 30, isActive: true },
  { id: 'fac-hob-c2', facilityReference: 'HOB-C2', campusId: 'cam-aibt-hobart', facilityType: 'Classroom', capacity: 24, isActive: true },
  { id: 'fac-hob-k1', facilityReference: 'HOB-K1', campusId: 'cam-aibt-hobart', facilityType: 'Commercial Kitchen', capacity: 16, isActive: true },
  { id: 'fac-hob-w1', facilityReference: 'HOB-W1', campusId: 'cam-aibt-hobart', facilityType: 'Workshop', capacity: 18, isActive: true },
  { id: 'fac-mel-c1', facilityReference: 'MEL-C1', campusId: 'cam-aibt-melbourne', facilityType: 'Classroom', capacity: 35, isActive: true },
  { id: 'fac-mel-c2', facilityReference: 'MEL-C2', campusId: 'cam-aibt-melbourne', facilityType: 'Classroom', capacity: 28, isActive: true },
  { id: 'fac-mel-k1', facilityReference: 'MEL-K1', campusId: 'cam-aibt-melbourne', facilityType: 'Commercial Kitchen', capacity: 18, isActive: true },
  { id: 'fac-mel-l1', facilityReference: 'MEL-L1', campusId: 'cam-aibt-melbourne', facilityType: 'Computer Lab', capacity: 22, isActive: true },
  { id: 'fac-bne-c1', facilityReference: 'BNE-C1', campusId: 'cam-aibt-brisbane', facilityType: 'Classroom', capacity: 30, isActive: true },
  { id: 'fac-bne-c2', facilityReference: 'BNE-C2', campusId: 'cam-aibt-brisbane', facilityType: 'Classroom', capacity: 20, isActive: false },
  { id: 'fac-syd-c1', facilityReference: 'SYD-C1', campusId: 'cam-aibti-sydney', facilityType: 'Classroom', capacity: 32, isActive: true },
  { id: 'fac-syd-c2', facilityReference: 'SYD-C2', campusId: 'cam-aibti-sydney', facilityType: 'Classroom', capacity: 26, isActive: true },
  { id: 'fac-adl-c1', facilityReference: 'ADL-C1', campusId: 'cam-aibti-adelaide', facilityType: 'Classroom', capacity: 24, isActive: true },
  { id: 'fac-adl-k1', facilityReference: 'ADL-K1', campusId: 'cam-aibti-adelaide', facilityType: 'Commercial Kitchen', capacity: 14, isActive: true },
  { id: 'fac-per-c1', facilityReference: 'PER-C1', campusId: 'cam-avi-perth', facilityType: 'Classroom', capacity: 28, isActive: true },
  { id: 'fac-per-w1', facilityReference: 'PER-W1', campusId: 'cam-avi-perth', facilityType: 'Workshop', capacity: 16, isActive: true },
  { id: 'fac-mcb-c1', facilityReference: 'MCB-C1', campusId: 'cam-avi-melbourne', facilityType: 'Classroom', capacity: 30, isActive: true },
];

/**
 * OD-11: the MSCRIS class name is expected to be "Virtual Classroom", but the
 * full term and business purpose are not yet confirmed.
 */
export const MSCRIS_CLASS_NAME_OPTIONS = ['Virtual Classroom'];
