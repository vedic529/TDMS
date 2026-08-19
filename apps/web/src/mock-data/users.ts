import type { TdmsUser } from '@/types/auth';
import { anchorDateTime } from './anchor';

/**
 * TDMS user accounts used by the prototype (Access Model v1.1).
 *
 * The Super Admin and Admin accounts below are the confirmed elevated roster:
 * four Super Admins and two Admins. Everyone else is a Viewer, which is what an
 * authenticated user from an approved organisation receives by default.
 *
 * IMPORTANT: a domain suffix is not authorisation. Production admits a user
 * because their verified Microsoft **tenant** is approved, and then grants the
 * access level held by their TDMS account. No part of this application checks
 * an email suffix to decide access.
 *
 * These are prototype records for reviewing the access model. They are not
 * Microsoft Entra accounts and contain no credential of any kind (AUTH-03).
 * Display names here are prototype placeholders; with real Entra sign-in the
 * name comes from the Microsoft profile.
 */

/** Confirmed Super Admin accounts (Access Model v1.1 §6) - exactly four. */
const CONFIRMED_SUPER_ADMINS = [
  { id: 'usr-0001', displayName: 'A. Chattopadhyay', organisationEmail: 'a.chattopadhyay@chelsongordon.com' },
  { id: 'usr-0002', displayName: 'W. Rajjak', organisationEmail: 'w.rajjak@chelsongordon.com' },
  { id: 'usr-0003', displayName: 'V. Yadav', organisationEmail: 'v.yadav@chelsongordon.com' },
  { id: 'usr-0004', displayName: 'D. Panda', organisationEmail: 'd.panda@chelsongordon.com' },
];

/** Confirmed Admin accounts (Access Model v1.1 §5) - N. Verma moved down here. */
const CONFIRMED_ADMINS = [
  { id: 'usr-0005', displayName: 'C. Dejsakultorn', organisationEmail: 'c.dejsakultorn@chelsongordon.com' },
  { id: 'usr-0006', displayName: 'N. Verma', organisationEmail: 'n.verma@chelsongordon.com' },
];

export const MOCK_USERS: TdmsUser[] = [
  ...CONFIRMED_SUPER_ADMINS.map((entry, index) => ({
    ...entry,
    role: 'SUPER_ADMIN' as const,
    accountStatus: 'ACTIVE' as const,
    lastSignInAt: anchorDateTime(-1 - index, 8, 42),
    identityLinked: true,
  })),

  ...CONFIRMED_ADMINS.map((entry, index) => ({
    ...entry,
    role: 'ADMIN' as const,
    accountStatus: 'ACTIVE' as const,
    lastSignInAt: anchorDateTime(-1 - index, 9, 5),
    identityLinked: true,
  })),

  // ---------------------------------------------------------------------
  // PLACEHOLDER accounts, so the four levels and the Inactive/Disabled
  // account states can be reviewed. No individual Data Editor account has
  // been approved: Data Editor is granted by approving an access request or
  // by a Super Admin role change.
  // ---------------------------------------------------------------------
  {
    id: 'usr-0007',
    displayName: 'Data Editor (placeholder)',
    organisationEmail: 'placeholder.editor@vconsultancy.com.au',
    role: 'DATA_EDITOR',
    accountStatus: 'ACTIVE',
    lastSignInAt: anchorDateTime(-1, 11, 12),
    identityLinked: true,
  },
  {
    id: 'usr-0008',
    displayName: 'Viewer (placeholder)',
    organisationEmail: 'placeholder.viewer@vconsultancy.com.au',
    role: 'VIEWER',
    accountStatus: 'ACTIVE',
    lastSignInAt: anchorDateTime(-2, 14, 20),
    identityLinked: true,
  },
  {
    id: 'usr-0009',
    displayName: 'Inactive account (placeholder)',
    organisationEmail: 'placeholder.inactive@vconsultancy.com.au',
    role: 'DATA_EDITOR',
    accountStatus: 'INACTIVE',
    lastSignInAt: anchorDateTime(-40, 15, 55),
    identityLinked: true,
  },
  {
    id: 'usr-0010',
    displayName: 'Disabled account (placeholder)',
    organisationEmail: 'placeholder.disabled@vconsultancy.com.au',
    role: 'VIEWER',
    accountStatus: 'DISABLED',
    lastSignInAt: anchorDateTime(-90, 9, 1),
    identityLinked: true,
  },
  {
    id: 'usr-0011',
    displayName: 'Newly provisioned (placeholder)',
    organisationEmail: 'placeholder.new@chelsongordon.com',
    role: 'VIEWER',
    accountStatus: 'ACTIVE',
    lastSignInAt: null,
    identityLinked: false,
  },
];

/**
 * Identities offered by the development access preview: one per access level,
 * so all four can be reviewed.
 */
export const DEV_PREVIEW_USER_IDS = ['usr-0008', 'usr-0007', 'usr-0005', 'usr-0001'] as const;

/** Identity used by the mock sign-in when no preview identity has been chosen. */
export const DEFAULT_MOCK_USER_ID = 'usr-0001';

/**
 * Supplied for reference only. TDMS does **not** use these to decide access:
 * the security boundary is the verified Microsoft tenant identifier, and a
 * domain suffix grants nothing on its own.
 */
export const SUPPLIED_ORGANISATION_DOMAINS = ['@chelsongordon.com', '@vconsultancy.com.au'];
