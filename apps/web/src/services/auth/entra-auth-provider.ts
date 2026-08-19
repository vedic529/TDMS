import {
  BrowserAuthError,
  InteractionRequiredAuthError,
  PublicClientApplication,
  type AccountInfo,
  type AuthenticationResult,
  type Configuration,
} from '@azure/msal-browser';

import type { AuthResult, AuthSession, TdmsUser } from '@/types/auth';
import { env } from '@/lib/env';
import type { AuthProvider } from './auth-provider';

/**
 * Microsoft Entra ID single sign-on adapter.
 *
 *   1. `signIn()` sends the browser to Microsoft via MSAL. If the person already
 *      has an organisational session, Microsoft may complete it without a
 *      prompt - that is normal single sign-on, and TDMS never sees the password
 *      (AUTH-03).
 *   2. MSAL returns an **access token whose audience is the TDMS API**, obtained
 *      with the configured `api://.../access_as_user` scope. An ID token would
 *      not do: it authenticates the browser application, not the caller of the
 *      API, and the API refuses it.
 *   3. The token goes to `GET /me`. FastAPI verifies the signature against the
 *      tenant's published keys and checks audience, issuer, expiry, tenant
 *      allow-list and `oid` before answering.
 *   4. On first sign-in the API provisions a Viewer, or the approved elevated
 *      role if the address is on the bootstrap list.
 *
 * The API decides access. This adapter obtains a token and asks; the browser is
 * never trusted to say who the user is.
 *
 * No client secret appears here. A browser is a public client, and a secret in a
 * bundle is a published secret.
 */
/** The TDMS API could not be reached. Distinct from any access decision. */
export class ServiceUnavailableError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = 'ServiceUnavailableError';
  }
}

export class MicrosoftEntraAuthProvider implements AuthProvider {
  readonly kind = 'entra' as const;

  private client: PublicClientApplication | null = null;
  private initialised = false;
  /**
   * The result Microsoft handed back on a redirect return, kept until it is
   * consumed. Discarding it and re-acquiring silently would work most of the
   * time and fail exactly when the silent path cannot run - which is the moment
   * the redirect existed to solve.
   */
  private redirectResult: AuthenticationResult | null = null;

  private unavailable(): never {
    throw new Error(
      env.authConfigurationError ??
        'Microsoft Entra ID sign-in is not configured. Supply NEXT_PUBLIC_ENTRA_CLIENT_ID, NEXT_PUBLIC_ENTRA_ALLOWED_TENANT_IDS and NEXT_PUBLIC_ENTRA_API_SCOPE.',
    );
  }

  private configuration(): Configuration {
    return {
      auth: {
        clientId: env.entra.clientId,
        authority: env.entra.authority,
        redirectUri: env.entra.redirectUri,
        // Sign-out returns to the sign-in screen rather than a Microsoft page.
        postLogoutRedirectUri: env.entra.redirectUri,
        // Only the configured tenant may issue tokens MSAL will accept. The API
        // checks `tid` again, which is the check that actually matters.
        knownAuthorities: [],
        navigateToLoginRequestUrl: false,
      },
      cache: {
        // sessionStorage, not localStorage: the cached token dies with the
        // browser tab instead of persisting on a shared machine.
        cacheLocation: 'sessionStorage',
        storeAuthStateInCookie: false,
      },
    };
  }

  /** MSAL v3+ must be initialised before any other call. */
  private async instance(): Promise<PublicClientApplication> {
    if (!env.isEntraConfigured) this.unavailable();
    if (!this.client) {
      this.client = new PublicClientApplication(this.configuration());
    }
    if (!this.initialised) {
      await this.client.initialize();
      // Completes a redirect sign-in when the browser lands back on the
      // registered redirect address. Must run before any other MSAL call, and
      // exactly once.
      this.redirectResult = await this.client.handleRedirectPromise().catch(() => null);
      if (this.redirectResult?.account) {
        this.client.setActiveAccount(this.redirectResult.account);
      }
      this.initialised = true;
    }
    return this.client;
  }

  /**
   * An access token for the TDMS API.
   *
   * Uses the redirect result when the browser has just come back from
   * Microsoft, then the silent cache, and only falls back to an interactive
   * redirect when Microsoft genuinely requires one (consent, MFA, expired
   * session).
   */
  private async acquireToken(
    client: PublicClientApplication,
    account: AccountInfo,
  ): Promise<AuthenticationResult | null> {
    const pending = this.redirectResult;
    if (pending?.accessToken) {
      this.redirectResult = null;
      return pending;
    }

    const request = { scopes: [env.entra.apiScope], account };
    try {
      return await client.acquireTokenSilent(request);
    } catch (error) {
      if (error instanceof InteractionRequiredAuthError) {
        await client.acquireTokenRedirect(request);
        // The browser navigates away; nothing after this runs.
        return null;
      }
      throw error;
    }
  }

  /** Reads the TDMS account for an acquired Microsoft access token. */
  private async loadTdmsUser(accessToken: string): Promise<TdmsUser> {
    let response: Response;
    try {
      response = await fetch(`${env.apiUrl}/me`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
    } catch (error) {
      // `fetch` rejects rather than returning a status when the host is not
      // listening, and the browser's own wording is "Failed to fetch" — which,
      // shown under an "Access denied" heading, describes neither what happened
      // nor what to do about it.
      throw new ServiceUnavailableError(
        `TDMS could not reach its API at ${env.apiUrl}. The TDMS API may not be running. ` +
          'Start it, then sign in again.',
        { cause: error },
      );
    }

    if (response.status === 401) {
      throw new Error('Microsoft sign-in could not be verified. Please sign in again.');
    }
    if (response.status === 403) {
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      throw new Error(body.detail ?? 'TDMS access is not available for this account.');
    }
    if (!response.ok) {
      throw new Error('TDMS could not confirm your access. Try again shortly.');
    }

    const body = (await response.json()) as {
      user: {
        id: number;
        display_name: string;
        organisation_email: string;
        access_level: TdmsUser['role'];
        account_status: TdmsUser['accountStatus'];
        last_sign_in_at: string | null;
        identity_linked: boolean;
      };
    };

    return {
      id: String(body.user.id),
      displayName: body.user.display_name,
      organisationEmail: body.user.organisation_email,
      role: body.user.access_level,
      accountStatus: body.user.account_status,
      lastSignInAt: body.user.last_sign_in_at,
      identityLinked: body.user.identity_linked,
    };
  }

  private sessionFrom(result: AuthenticationResult, user: TdmsUser): AuthSession {
    return {
      user,
      microsoftSignInResult: 'SUCCESS',
      accessDecision: 'GRANTED',
      signedInAt: new Date().toISOString(),
      // AUTH-11: a safe correlation reference. Never the token itself.
      correlationId: result.correlationId ?? result.uniqueId,
      provider: 'entra',
    };
  }

  async signIn(): Promise<AuthResult> {
    if (!env.isEntraConfigured) this.unavailable();
    const client = await this.instance();

    const correlationId = `entra-${Date.now().toString(36)}`;
    try {
      const account = client.getActiveAccount() ?? client.getAllAccounts()[0] ?? null;

      if (!account) {
        // Organisation accounts only. `prompt` is deliberately unset so an
        // existing Microsoft session completes without a second sign-in.
        await client.loginRedirect({ scopes: [env.entra.apiScope] });
        // The browser navigates away; nothing after this runs.
        return {
          ok: false,
          failure: {
            microsoftSignInResult: 'SUCCESS',
            accessDecision: 'DENIED',
            reason: 'SIGN_IN_NOT_COMPLETED',
            userMessage: 'Completing sign-in with Microsoft…',
            correlationId,
          },
        };
      }

      client.setActiveAccount(account);
      const result = await this.acquireToken(client, account);
      if (!result) {
        return {
          ok: false,
          failure: {
            microsoftSignInResult: 'SUCCESS',
            accessDecision: 'DENIED',
            reason: 'SIGN_IN_NOT_COMPLETED',
            userMessage: 'Completing sign-in with Microsoft…',
            correlationId,
          },
        };
      }

      const user = await this.loadTdmsUser(result.accessToken);
      return { ok: true, session: this.sessionFrom(result, user) };
    } catch (error) {
      // A denial from the API carries a safe message (AUTH-10); anything else
      // is reported without disclosing internals.
      const message =
        error instanceof BrowserAuthError
          ? 'Microsoft sign-in could not be completed. Please try again.'
          : error instanceof Error
            ? error.message
            : 'Sign-in could not be completed.';

      return {
        ok: false,
        failure: {
          microsoftSignInResult: error instanceof BrowserAuthError ? 'FAILURE' : 'SUCCESS',
          accessDecision: 'DENIED',
          reason:
            error instanceof ServiceUnavailableError
              ? 'SERVICE_UNAVAILABLE'
              : error instanceof BrowserAuthError
                ? 'MICROSOFT_SIGN_IN_FAILED'
                : 'BLOCKED_BY_SECURITY_RULE',
          userMessage: message,
          correlationId,
        },
      };
    }
  }

  /**
   * A TDMS API access token for the signed-in account.
   *
   * Returns null rather than throwing when nobody is signed in, so an
   * unauthenticated call fails as a clean 401 from the API instead of an
   * exception in the data layer.
   */
  async getApiAccessToken(): Promise<string | null> {
    if (!env.isEntraConfigured) return null;
    try {
      const client = await this.instance();
      const account = client.getActiveAccount() ?? client.getAllAccounts()[0] ?? null;
      if (!account) return null;
      const result = await this.acquireToken(client, account);
      return result?.accessToken ?? null;
    } catch {
      return null;
    }
  }

  async signOut(): Promise<void> {
    if (!env.isEntraConfigured) this.unavailable();
    const client = await this.instance();
    const account = client.getActiveAccount() ?? client.getAllAccounts()[0] ?? undefined;
    // Ends the Microsoft session as well as the TDMS one, so signing out does
    // not leave a signed-in browser behind on a shared machine.
    await client.logoutRedirect({ account });
  }

  async restoreSession(): Promise<AuthSession | null> {
    // No configuration means no session - never a quiet fall back to the
    // development adapter.
    if (!env.isEntraConfigured) return null;

    try {
      const client = await this.instance();
      const account = client.getActiveAccount() ?? client.getAllAccounts()[0] ?? null;
      if (!account) return null;

      client.setActiveAccount(account);
      const result = await this.acquireToken(client, account);
      if (!result) return null;

      const user = await this.loadTdmsUser(result.accessToken);
      return this.sessionFrom(result, user);
    } catch {
      // A failed restore must never leave the application stuck: treat it as no
      // session so the user reaches the sign-in screen (AUTH-01).
      return null;
    }
  }
}
