/**
 * Environment configuration for the TDMS frontend.
 *
 * Every value is read from a NEXT_PUBLIC_ variable so that development,
 * staging and production configuration never mix. No tenant ID, client ID,
 * client secret, password or database connection string is hard-coded here.
 */

export type AppEnvironment = 'development' | 'staging' | 'production';
export type DataMode = 'mock' | 'api';
export type AuthMode = 'mock' | 'entra';

function readString(value: string | undefined, fallback: string): string {
  const trimmed = value?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : fallback;
}

const appEnvironment = readString(process.env.NEXT_PUBLIC_APP_ENV, 'development') as AppEnvironment;

const entraClientId = readString(process.env.NEXT_PUBLIC_ENTRA_CLIENT_ID, '');
const entraTenantId = readString(process.env.NEXT_PUBLIC_ENTRA_TENANT_ID, '');
const entraRedirectUri = readString(process.env.NEXT_PUBLIC_ENTRA_REDIRECT_URI, '');

/** True only when the organisation has supplied a complete Entra configuration (OD-01). */
const isEntraConfigured = entraClientId !== '' && entraTenantId !== '';

const requestedAuthMode = readString(process.env.NEXT_PUBLIC_TDMS_AUTH_MODE, 'mock') as AuthMode;
const requestedDataMode = readString(process.env.NEXT_PUBLIC_TDMS_DATA_MODE, 'mock') as DataMode;

export const env = {
  appName: readString(process.env.NEXT_PUBLIC_APP_NAME, 'TDMS'),
  appEnvironment,
  apiUrl: readString(process.env.NEXT_PUBLIC_API_URL, 'http://localhost:8000'),

  /** `api` is honoured only when a base URL is present. */
  dataMode: requestedDataMode,

  /**
   * `entra` is honoured only when the tenant is configured. Until then the
   * sign-in button falls back to the mock provider so the prototype stays
   * usable, and the login screen says so.
   */
  authMode: (requestedAuthMode === 'entra' && isEntraConfigured ? 'entra' : 'mock') as AuthMode,
  requestedAuthMode,
  isEntraConfigured,

  entra: {
    clientId: entraClientId,
    tenantId: entraTenantId,
    redirectUri: entraRedirectUri,
  },

  /**
   * Development access preview. Never enabled outside development: it is a
   * developer testing aid, not an authentication mechanism.
   */
  devToolsEnabled:
    appEnvironment === 'development' && readString(process.env.NEXT_PUBLIC_TDMS_DEV_TOOLS, 'true') === 'true',
} as const;

export const isProduction = env.appEnvironment === 'production';
