import type { AuthResult, AuthSession } from '@/types/auth';
import { env } from '@/lib/env';
import type { AuthProvider } from './auth-provider';

/**
 * Microsoft Entra ID single sign-on adapter.
 *
 * This is the seam where MSAL connects once OD-01 (tenant, app registration,
 * redirect addresses, permitted users, role mapping and support owner) is
 * approved. The intended flow follows SRS 4.1:
 *
 *   1. `signIn()` redirects the browser to the approved Microsoft sign-in page
 *      using `@azure/msal-browser` configured from `env.entra`.
 *   2. Microsoft verifies the account and returns to the redirect address.
 *   3. The verified account is matched to one internal TDMS user record
 *      through `TdmsClient.listUsers()` / the FastAPI `/auth/me` endpoint.
 *   4. The TDMS access decision is applied separately from the Microsoft
 *      sign-in result (SRS 4.2), and the correlation ID is retained (AUTH-11).
 *
 * TDMS never receives, stores or logs the user password (AUTH-03), and no
 * client secret belongs in the frontend.
 */
export class MicrosoftEntraAuthProvider implements AuthProvider {
  readonly kind = 'entra' as const;

  private unavailable(): never {
    throw new Error(
      'Microsoft Entra ID sign-in is not configured. Supply NEXT_PUBLIC_ENTRA_CLIENT_ID and NEXT_PUBLIC_ENTRA_TENANT_ID, then set NEXT_PUBLIC_TDMS_AUTH_MODE=entra.',
    );
  }

  async signIn(): Promise<AuthResult> {
    if (!env.isEntraConfigured) this.unavailable();
    // MSAL `loginRedirect` / `acquireTokenSilent` are wired here.
    this.unavailable();
  }

  async signOut(): Promise<void> {
    if (!env.isEntraConfigured) this.unavailable();
    // MSAL `logoutRedirect` is wired here.
    this.unavailable();
  }

  async restoreSession(): Promise<AuthSession | null> {
    if (!env.isEntraConfigured) return null;
    // MSAL account lookup plus the TDMS access decision is wired here.
    return null;
  }
}
