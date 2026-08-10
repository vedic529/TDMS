import { env } from '@/lib/env';
import type { AuthProvider } from './auth-provider';
import { MockAuthProvider } from './mock-auth-provider';
import { MicrosoftEntraAuthProvider } from './entra-auth-provider';

let provider: AuthProvider | null = null;

/**
 * Returns the configured authentication adapter.
 * `env.authMode` already falls back to `mock` when the Microsoft Entra tenant
 * is not configured, so the prototype stays usable and the sign-in screen can
 * say which adapter is active.
 */
export function getAuthProvider(): AuthProvider {
  if (!provider) {
    provider = env.authMode === 'entra' ? new MicrosoftEntraAuthProvider() : new MockAuthProvider();
  }
  return provider;
}

export type { AuthProvider } from './auth-provider';
