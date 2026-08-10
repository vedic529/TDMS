import type { TdmsUser } from '@/types/auth';
import { anchorDateTime } from './anchor';

/**
 * Demo TDMS user accounts.
 *
 * These are prototype records used to review the access model. They are not
 * Microsoft Entra accounts and contain no credential of any kind (AUTH-03).
 */
export const MOCK_USERS: TdmsUser[] = [
  {
    id: 'usr-0001',
    displayName: 'Wasim Ahmed',
    organisationEmail: 'wasim.ahmed@aibtglobal.edu.au',
    role: 'SUPER_ADMIN',
    assignment: null,
    accountStatus: 'ACTIVE',
    lastSignInAt: anchorDateTime(-1, 8, 42),
    delegatedUserManagement: true,
    delegatedMappingManagement: true,
  },
  {
    id: 'usr-0002',
    displayName: 'Ankit Kumar',
    organisationEmail: 'ankit.kumar@aibtglobal.edu.au',
    role: 'DATA_EDITOR',
    assignment: 'TIMETABLE_OFFICER',
    accountStatus: 'ACTIVE',
    lastSignInAt: anchorDateTime(-1, 9, 5),
    delegatedUserManagement: false,
    delegatedMappingManagement: false,
  },
  {
    id: 'usr-0003',
    displayName: 'Rebecca Lawson',
    organisationEmail: 'rebecca.lawson@aibtglobal.edu.au',
    role: 'ADMIN',
    assignment: null,
    accountStatus: 'ACTIVE',
    lastSignInAt: anchorDateTime(-2, 14, 20),
    delegatedUserManagement: false,
    delegatedMappingManagement: false,
  },
  {
    id: 'usr-0004',
    displayName: 'Sophia Nguyen',
    organisationEmail: 'sophia.nguyen@aibtglobal.edu.au',
    role: 'DATA_EDITOR',
    assignment: 'STUDENT_DATA_OFFICER',
    accountStatus: 'ACTIVE',
    lastSignInAt: anchorDateTime(-1, 11, 12),
    delegatedUserManagement: false,
    delegatedMappingManagement: false,
  },
  {
    id: 'usr-0005',
    displayName: 'Marcus Bell',
    organisationEmail: 'marcus.bell@aibtinternational.edu.au',
    role: 'ADMIN',
    assignment: null,
    accountStatus: 'ACTIVE',
    lastSignInAt: anchorDateTime(-5, 10, 3),
    delegatedUserManagement: true,
    delegatedMappingManagement: false,
  },
  {
    id: 'usr-0006',
    displayName: 'Hina Patel',
    organisationEmail: 'hina.patel@aibtinternational.edu.au',
    role: 'DATA_EDITOR',
    assignment: 'STUDENT_DATA_OFFICER',
    accountStatus: 'INACTIVE',
    lastSignInAt: anchorDateTime(-40, 15, 55),
    delegatedUserManagement: false,
    delegatedMappingManagement: false,
  },
  {
    id: 'usr-0007',
    displayName: 'Tom Ferguson',
    organisationEmail: 'tom.ferguson@avi.edu.au',
    role: 'DATA_EDITOR',
    assignment: 'TIMETABLE_OFFICER',
    accountStatus: 'DISABLED',
    lastSignInAt: anchorDateTime(-90, 9, 1),
    delegatedUserManagement: false,
    delegatedMappingManagement: false,
  },
  {
    id: 'usr-0008',
    displayName: 'Grace Okonkwo',
    organisationEmail: 'grace.okonkwo@avi.edu.au',
    role: 'DATA_EDITOR',
    assignment: null,
    accountStatus: 'ACTIVE',
    lastSignInAt: null,
    delegatedUserManagement: false,
    delegatedMappingManagement: false,
  },
];

/**
 * Identities offered by the development access preview.
 * Each entry maps to one of the access states that must be testable while
 * Microsoft Entra ID is not connected.
 */
export const DEV_PREVIEW_USER_IDS = ['usr-0001', 'usr-0003', 'usr-0004', 'usr-0002'] as const;

/** Identity used by the mock sign-in when no preview identity has been chosen. */
export const DEFAULT_MOCK_USER_ID = 'usr-0001';
