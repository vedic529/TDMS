/**
 * SRS Section 12 - Open Decisions and Assumptions.
 *
 * These are matters the SRS records as unresolved. TDMS must not invent a final
 * rule for any of them. The frontend therefore:
 *   - keeps the register in one place;
 *   - shows a `PendingRuleNotice` wherever an unresolved rule would apply;
 *   - displays validation checks whose rules are not yet approved as
 *     "Awaiting approval" instead of producing a pass or fail result.
 */

export interface OpenDecision {
  id: string;
  area: string;
  requiredDecision: string;
  /** Where the unresolved rule affects the interface. */
  affects: string[];
}

export const OPEN_DECISIONS: OpenDecision[] = [
  {
    id: 'OD-01',
    area: 'Microsoft Entra configuration',
    requiredDecision:
      'Confirm the tenant, app registration, redirect addresses, permitted users, role mapping and production support owner.',
    affects: ['Login and Authentication'],
  },
  {
    id: 'OD-02',
    area: 'Microsoft sign-in record integration',
    requiredDecision:
      'Decide whether TDMS will only link administrators to Microsoft Entra records or will retrieve them using Microsoft Graph, including permission, licensing and authorised roles.',
    affects: ['User Activity Records'],
  },
  {
    id: 'OD-03',
    area: 'Session timeout',
    requiredDecision: 'Approve the inactivity period and any maximum session duration.',
    affects: ['Login and Authentication', 'Account information'],
  },
  {
    id: 'OD-04',
    area: 'Retention',
    requiredDecision:
      'Approve the TDMS user activity retention period and how Microsoft sign-in records will be retained if required.',
    affects: ['User Activity Records'],
  },
  {
    id: 'OD-05',
    area: 'Admin role boundary',
    requiredDecision:
      'Confirm whether an Admin may create or change other Admin accounts and confirm that Super Admin account changes remain restricted.',
    affects: ['Administration - user management'],
  },
  {
    id: 'OD-06',
    area: 'Delete and override reasons',
    requiredDecision: 'Approve the controlled reason lists and who may approve a timetable clash override.',
    affects: ['All delete dialogs', 'Timetable override', 'Restore from recycle area'],
  },
  {
    id: 'OD-07',
    area: 'Break rules',
    requiredDecision:
      'Approve the exact break dates or calculation rules for 26, 52, 78 and 104-week courses before automatic timetable generation is released.',
    affects: ['Timetable View and Management - generate and validate'],
  },
  {
    id: 'OD-08',
    area: 'Student calculations',
    requiredDecision:
      'Confirm the exact CT definition, the Course Duration Option display rule and whether course weeks are calculated using inclusive or exclusive dates.',
    affects: ['Single Student Entry', 'Bulk Student Import'],
  },
  {
    id: 'OD-09',
    area: 'Facility data',
    requiredDecision:
      'Approve the facility fields, source data, maintenance owner and whether a separate facility page is required.',
    affects: ['Timetable View and Management - facility selection and clash checking'],
  },
  {
    id: 'OD-10',
    area: 'Trainer delivery rule',
    requiredDecision:
      'Confirm that physical trainer availability permits virtual delivery and that virtual-only availability cannot be used for physical delivery.',
    affects: ['Trainer Data', 'Timetable validation'],
  },
  {
    id: 'OD-11',
    area: 'MSCRIS',
    requiredDecision: 'Confirm the full term, business purpose and final field rules.',
    affects: ['Timetable View and Management - MSCRIS section'],
  },
  {
    id: 'OD-12',
    area: 'Performance target',
    requiredDecision: 'Approve measurable response-time and expected concurrent-user targets.',
    affects: ['All pages'],
  },
  {
    id: 'OD-13',
    area: 'Production hosting',
    requiredDecision:
      'Approve the final PostgreSQL schema, Supabase configuration or alternative hosting service before production connection.',
    affects: ['Data service layer'],
  },
];

export function openDecision(id: string): OpenDecision | undefined {
  return OPEN_DECISIONS.find((decision) => decision.id === id);
}
