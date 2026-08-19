/**
 * SRS Section 12 - Open Decisions and Assumptions: working record.
 *
 * These are matters the SRS records as unresolved. TDMS must not invent a final
 * rule for any of them. The frontend therefore:
 *   - keeps the register in one place;
 *   - shows a `PendingRuleNotice` wherever an unresolved rule would apply;
 *   - displays validation checks whose rules are not yet approved as
 *     "Awaiting approval" instead of producing a pass or fail result.
 *
 * A supplied fact may resolve PART of a decision without resolving the whole
 * decision, so each entry carries what has been confirmed and what is still
 * outstanding. A decision only becomes `approved` when every outstanding item
 * has been resolved.
 */

export type OpenDecisionStatus = 'open' | 'partially-resolved' | 'approved';

export interface OpenDecision {
  id: string;
  area: string;
  requiredDecision: string;
  status: OpenDecisionStatus;
  /** Points that have been confirmed by the project owner. */
  confirmed: string[];
  /** Points still awaiting approval. Must be empty before `approved`. */
  outstanding: string[];
  /** Where the unresolved rule affects the interface. */
  affects: string[];
  /** A consequence or conflict worth recording alongside an approved answer. */
  note?: string;
}

export const OPEN_DECISIONS: OpenDecision[] = [
  {
    id: 'OD-01',
    area: 'Microsoft Entra configuration and TDMS access',
    requiredDecision:
      'Confirm the tenant, app registration, redirect addresses, permitted users, role mapping and production support owner.',
    status: 'partially-resolved',
    confirmed: [
      'Access Model v1.1 (approved 11 August 2026): four access levels - Viewer, Data Editor, Admin, Super Admin. Viewer is the default for any authenticated user from an approved organisation.',
      'Super Admin users (4): a.chattopadhyay@chelsongordon.com, w.rajjak@chelsongordon.com, v.yadav@chelsongordon.com, d.panda@chelsongordon.com.',
      'Admin users (2): c.dejsakultorn@chelsongordon.com and n.verma@chelsongordon.com. N. Verma is no longer a Super Admin.',
      'Organisation domains supplied: @chelsongordon.com and @vconsultancy.com.au.',
      'Access model: the security boundary is the verified Microsoft tenant identifier, not the email domain. A domain suffix is never treated as authorisation and grants nothing beyond Viewer.',
      'The Data Editor work assignment (Student Data Officer / Timetable Officer) is removed. A Data Editor maintains both Student Data and Timetables.',
      'Higher access is granted by a Super Admin approving an access request, or by a direct Super Admin role change. Admin does neither.',
      'Chelson Gordon tenant ID supplied 11 August 2026 and held in the git-ignored environment configuration.',
    ],
    outstanding: [
      'Application (Client) ID, whether V Consultancy is a separate tenant, staging and production redirect addresses, and the production support owner.',
    ],
    affects: ['Login and Authentication', 'Administration - access requests and roles'],
  },
  {
    id: 'OD-02',
    area: 'Microsoft sign-in record integration',
    requiredDecision:
      'Decide whether TDMS will only link administrators to Microsoft Entra records or will retrieve them using Microsoft Graph, including permission, licensing and authorised roles.',
    status: 'open',
    confirmed: [],
    outstanding: ['The whole decision.'],
    affects: ['User Activity Records'],
  },
  {
    id: 'OD-03',
    area: 'Session timeout',
    requiredDecision: 'Approve the inactivity period and any maximum session duration.',
    status: 'partially-resolved',
    confirmed: ['TDMS inactivity timeout is 30 minutes. This is applied by the application.'],
    outstanding: [
      'Whether a maximum session duration applies in addition to the inactivity timeout. No maximum is applied until one is approved.',
    ],
    affects: ['Login and Authentication', 'Account information'],
  },
  {
    id: 'OD-04',
    area: 'Retention',
    requiredDecision:
      'Approve the TDMS user activity retention period and how Microsoft sign-in records will be retained if required.',
    status: 'open',
    confirmed: [],
    outstanding: ['The whole decision.'],
    affects: ['User Activity Records'],
  },
  {
    id: 'OD-05',
    area: 'Admin role boundary',
    requiredDecision:
      'Confirm whether an Admin may create or change other Admin accounts and confirm that Super Admin account changes remain restricted.',
    status: 'open',
    confirmed: [],
    outstanding: ['The whole decision.'],
    affects: ['Administration - user management'],
  },
  {
    id: 'OD-06',
    area: 'Delete and override reasons',
    requiredDecision: 'Approve the controlled reason lists and who may approve a timetable clash override.',
    status: 'open',
    confirmed: [],
    outstanding: ['The whole decision.'],
    affects: ['All delete dialogs', 'Timetable override', 'Restore from recycle area'],
  },
  {
    id: 'OD-07',
    area: 'Break rules',
    requiredDecision:
      'Approve the exact break dates or calculation rules for 26, 52, 78 and 104-week courses before automatic timetable generation is released.',
    status: 'open',
    confirmed: [],
    outstanding: ['The whole decision.'],
    affects: ['Timetable View and Management - generate and validate'],
  },
  {
    id: 'OD-08',
    area: 'Student calculations',
    requiredDecision:
      'Confirm the exact CT definition, the Course Duration Option display rule and whether course weeks are calculated using inclusive or exclusive dates.',
    status: 'approved',
    confirmed: [
      'CT means Credit Transfer. The terminology is settled and is used throughout the interface.',
      'CT Student is a flag only: Yes means the student has at least one approved Credit Transfer. TDMS does not store transferred units, a unit count or a Credit Transfer reference.',
      'Course duration when CT Student = Yes: staff select an approved Course Duration Option. TDMS does not derive any reduction from the Credit Transfer.',
      'Course Duration Option is always shown. It is not hidden by any Credit Transfer condition, and staff select the value.',
      'Actual Course Duration uses an inclusive date calculation: (end date - start date + 1 day) / 7, rounded to whole weeks.',
    ],
    outstanding: [],
    affects: ['Single Student Entry', 'Bulk Student Import'],
  },
  {
    id: 'OD-09',
    area: 'Facility data',
    requiredDecision:
      'Approve the facility fields, source data, maintenance owner and whether a separate facility page is required.',
    status: 'open',
    confirmed: [],
    outstanding: ['The whole decision.'],
    affects: ['Timetable View and Management - facility selection and clash checking'],
  },
  {
    id: 'OD-10',
    area: 'Trainer delivery rule',
    requiredDecision:
      'Confirm that physical trainer availability permits virtual delivery and that virtual-only availability cannot be used for physical delivery.',
    status: 'open',
    confirmed: [],
    outstanding: ['The whole decision.'],
    affects: ['Trainer Data', 'Timetable validation'],
  },
  {
    id: 'OD-11',
    area: 'MSCRIS',
    requiredDecision: 'Confirm the full term, business purpose and final field rules.',
    status: 'partially-resolved',
    confirmed: [
      'Business purpose: MSCRIS refers to additional classes, particularly additional classes arranged for specific topics.',
      'Spelling: MSCRIS, as used in the SRS. MISCRIS was a slip and nothing is renamed.',
      'Delivery mode: an MSCRIS class is virtual only. No facility is selected for it.',
      'MSCRIS Class Name always holds the fixed value "Virtual Classroom".',
      'MSCRIS Trainer is free text. It does not have to come from approved TDMS trainer data.',
      'MSCRIS sessions are excluded from trainer, student-group and facility clash checking.',
    ],
    outstanding: [
      'MSCRIS is required only in certain cases, but the exact condition has not been supplied. Until it is, TDMS treats the section as optional and never blocks a save because it is empty.',
    ],
    affects: ['Timetable View and Management - MSCRIS section'],
    note:
      'Flagged consequence: a free-text MSCRIS Trainer that is excluded from clash checking means TDMS cannot detect a trainer booked for both an MSCRIS class and a normal class. This also sits against DATA-02, which requires timetable assignments to reference approved trainer data rather than uncontrolled text. Implemented as approved; the preview panel warns the user to check MSCRIS manually.',
  },
  {
    id: 'OD-12',
    area: 'Performance target',
    requiredDecision: 'Approve measurable response-time and expected concurrent-user targets.',
    status: 'open',
    confirmed: [],
    outstanding: ['The whole decision.'],
    affects: ['All pages'],
  },
  {
    id: 'OD-13',
    area: 'Production hosting',
    requiredDecision:
      'Approve the final PostgreSQL schema, Supabase configuration or alternative hosting service before production connection.',
    status: 'open',
    confirmed: [],
    outstanding: ['The whole decision.'],
    affects: ['Data service layer'],
  },
];

export const OPEN_DECISION_STATUS_LABEL: Record<OpenDecisionStatus, string> = {
  open: 'Awaiting approval',
  'partially-resolved': 'Partially resolved · awaiting remaining approval',
  approved: 'Approved',
};

export function openDecision(id: string): OpenDecision | undefined {
  return OPEN_DECISIONS.find((decision) => decision.id === id);
}
