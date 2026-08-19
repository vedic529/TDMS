import { env } from '@/lib/env';
import type { AuthProvider } from './auth-provider';
import { MockAuthProvider } from './mock-auth-provider';
import { MicrosoftEntraAuthProvider } from './entra-auth-provider';

let provider: AuthProvider | null = null;

/**
 * Returns the configured authentication adapter.
 *
 * `env.authMode` is used exactly as configured - there is deliberately no
 * downgrade from `entra` to `mock`. If Microsoft sign-in is selected and the
 * tenant configuration is missing, the Entra adapter raises a clear error and
 * the sign-in screen explains it. Quietly admitting people through the
 * development adapter instead would be an application that looks like it is
 * working while letting anyone in.
 */
export function getAuthProvider(): AuthProvider {
  if (!provider) {
    provider = env.authMode === 'entra' ? new MicrosoftEntraAuthProvider() : new MockAuthProvider();
  }
  return provider;
}

export type { AuthProvider } from './auth-provider';
