import type { AuthResult, AuthSession } from '@/types/auth';

/**
 * TDMS authentication abstraction.
 *
 *   AuthProvider
 *        |
 *        +---- MockAuthProvider                (development, no Microsoft call)
 *        |
 *        +---- MicrosoftEntraAuthProvider      (production, Microsoft Entra ID SSO)
 *
 * The application never asks the user for a Microsoft password and never stores
 * one (AUTH-03). The provider only reports the Microsoft sign-in result; the
 * TDMS access decision is made separately against the internal user record
 * (SRS 4.2).
 */
export interface AuthProvider {
  readonly kind: 'mock' | 'entra';
  /** Starts the sign-in flow and returns the resulting access decision. */
  signIn(): Promise<AuthResult>;
  /** Ends the TDMS session (AUTH-09). */
  signOut(): Promise<void>;
  /** Restores a session on page load, or null when there is none. */
  restoreSession(): Promise<AuthSession | null>;
  /**
   * A bearer token for the TDMS API, or null when this adapter does not issue
   * one. `ApiTdmsClient` calls this so the Authorization header is attached in
   * exactly one place instead of being repeated by every caller.
   */
  getApiAccessToken(): Promise<string | null>;
}
