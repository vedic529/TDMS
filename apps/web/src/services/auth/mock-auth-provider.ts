import type { AuthResult, AuthSession, TdmsUser } from '@/types/auth';
import { SRS_PAGE_REFERENCE } from '@/lib/interface-names';
import { MOCK_USERS, DEFAULT_MOCK_USER_ID } from '@/mock-data/users';
import { getTdmsClient } from '@/services';
import {
  PROTOTYPE_STORAGE_KEYS,
  readPrototypeValue,
  removePrototypeValue,
  writePrototypeValue,
} from '@/services/prototype-storage';
import type { AuthProvider } from './auth-provider';

/**
 * Development authentication used while Microsoft Entra ID is not configured.
 *
 * It creates a demo session for an existing TDMS user record. It never asks for
 * a password, never contacts Microsoft and never presents itself as production
 * authentication. The sign-in screen shows only the Microsoft button; this
 * provider is what that button uses until OD-01 is approved.
 */
export class MockAuthProvider implements AuthProvider {
  readonly kind = 'mock' as const;

  private correlationCounter = 0;

  private nextCorrelationId(): string {
    this.correlationCounter += 1;
    return `mock-corr-${String(this.correlationCounter).padStart(4, '0')}`;
  }

  /**
   * The identity the development access preview has selected, if any.
   * Stored under a prototype key so it is obviously not a production concept.
   */
  private selectedUserId(): string {
    return readPrototypeValue<string>(PROTOTYPE_STORAGE_KEYS.devIdentity) ?? DEFAULT_MOCK_USER_ID;
  }

  async signIn(): Promise<AuthResult> {
    const correlationId = this.nextCorrelationId();
    const client = getTdmsClient();
    const users = await client.listUsers().catch(() => MOCK_USERS);
    const user = users.find((entry) => entry.id === this.selectedUserId()) ?? users[0];

    if (!user) {
      return {
        ok: false,
        failure: {
          microsoftSignInResult: 'SUCCESS',
          accessDecision: 'DENIED',
          reason: 'UNMATCHED_USER',
          userMessage: 'Sign-in could not be completed. Contact the TDMS administrator if this continues.',
          correlationId,
        },
      };
    }

    const denial = accessDecisionFor(user);
    if (denial) {
      await client.recordActivity({
        userReference: user.organisationEmail,
        accessLevel: user.role,
        pageOrFunction: SRS_PAGE_REFERENCE.login,
        action: 'Access denied',
        recordOrBatchReference: user.id,
        result: 'Access denied',
        technicalReference: correlationId,
        plainLanguageDetail: denial.detail,
      });
      return {
        ok: false,
        failure: {
          microsoftSignInResult: 'SUCCESS',
          accessDecision: 'DENIED',
          reason: denial.reason,
          userMessage: denial.userMessage,
          correlationId,
        },
      };
    }

    const session: AuthSession = {
      user,
      microsoftSignInResult: 'SUCCESS',
      accessDecision: 'GRANTED',
      signedInAt: new Date().toISOString(),
      correlationId,
      provider: 'mock',
    };

    writePrototypeValue(PROTOTYPE_STORAGE_KEYS.session, session);

    await client.recordActivity({
      userReference: user.organisationEmail,
      accessLevel: user.role,
      pageOrFunction: SRS_PAGE_REFERENCE.login,
      action: 'Sign in',
      recordOrBatchReference: user.id,
      result: 'Access granted',
      technicalReference: correlationId,
      plainLanguageDetail:
        'Development sign-in completed. The TDMS account is active and has an approved access level.',
    });

    return { ok: true, session };
  }

  /**
   * The development adapter contacts no Microsoft endpoint, so there is no
   * bearer token. `ApiTdmsClient` sends the development identity header
   * instead, which the API only honours outside production.
   */
  async getApiAccessToken(): Promise<string | null> {
    return null;
  }

  async signOut(): Promise<void> {
    const session = readPrototypeValue<AuthSession>(PROTOTYPE_STORAGE_KEYS.session);
    removePrototypeValue(PROTOTYPE_STORAGE_KEYS.session);
    if (session) {
      await getTdmsClient().recordActivity({
        userReference: session.user.organisationEmail,
        accessLevel: session.user.role,
        pageOrFunction: SRS_PAGE_REFERENCE.login,
        action: 'Sign out',
        recordOrBatchReference: session.user.id,
        result: 'Completed',
        technicalReference: session.correlationId,
        plainLanguageDetail: 'User signed out of TDMS.',
      });
    }
  }

  async restoreSession(): Promise<AuthSession | null> {
    const session = readPrototypeValue<AuthSession>(PROTOTYPE_STORAGE_KEYS.session);
    if (!session?.user) return null;

    // AUTH-12: a role or account-status change takes effect at the next
    // sign-in or session refresh, so the stored user is re-read here.
    const users = await getTdmsClient().listUsers().catch(() => MOCK_USERS);
    const current = users.find((entry) => entry.id === session.user.id);
    if (!current) return null;
    if (accessDecisionFor(current)) {
      removePrototypeValue(PROTOTYPE_STORAGE_KEYS.session);
      return null;
    }
    return { ...session, user: current };
  }
}

/** SRS 4.4: an inactive, disabled or roleless account is denied (AUTH-05). */
function accessDecisionFor(user: TdmsUser) {
  if (user.accountStatus === 'DISABLED') {
    return {
      reason: 'ACCOUNT_DISABLED' as const,
      userMessage: 'TDMS access is not available for this account. Contact the TDMS administrator.',
      detail: 'TDMS access denied because the account status is Disabled.',
    };
  }
  if (user.accountStatus === 'INACTIVE') {
    return {
      reason: 'ACCOUNT_INACTIVE' as const,
      userMessage: 'TDMS access is not available for this account. Contact the TDMS administrator.',
      detail: 'TDMS access denied because the account status is Inactive.',
    };
  }
  return null;
}
