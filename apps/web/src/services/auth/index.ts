import type { AuthProvider } from './auth-provider';
import { MicrosoftEntraAuthProvider } from './entra-auth-provider';

let provider: AuthProvider | null = null;

/**
 * Returns the configured authentication adapter.
 *
 * Authentication always uses Microsoft Entra ID. Missing configuration is
 * reported explicitly by the adapter; there is no browser-only identity path.
 */
export function getAuthProvider(): AuthProvider {
  if (!provider) {
    provider = new MicrosoftEntraAuthProvider();
  }
  return provider;
}

export type { AuthProvider } from './auth-provider';
