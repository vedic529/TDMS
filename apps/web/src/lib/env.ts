/**
 * Environment configuration for the TDMS frontend.
 *
 * Every value is read from a NEXT_PUBLIC_ variable so that development,
 * staging and production configuration never mix. No tenant ID, client ID,
 * client secret, password or database connection string is hard-coded here.
 *
 * A client ID and authority are public identifiers - they appear in every
 * authorisation URL. A client **secret** is confidential and must never be a
 * NEXT_PUBLIC_ value: every one of those is embedded in the browser bundle.
 */

export type AppEnvironment = 'development' | 'staging' | 'production';

function readString(value: string | undefined, fallback: string): string {
  const trimmed = value?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : fallback;
}

function readList(value: string | undefined): string[] {
  return readString(value, '')
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
}

const appEnvironment = readString(process.env.NEXT_PUBLIC_APP_ENV, 'development') as AppEnvironment;
const isProductionEnvironment = appEnvironment === 'production';

const entraClientId = readString(process.env.NEXT_PUBLIC_ENTRA_CLIENT_ID, '');
const entraAuthority = readString(process.env.NEXT_PUBLIC_ENTRA_AUTHORITY, '');
const entraRedirectUri = readString(process.env.NEXT_PUBLIC_ENTRA_REDIRECT_URI, '');
/**
 * The delegated scope the browser must request so the token it receives is
 * intended for the TDMS API - e.g. `api://<api-client-id>/access_as_user`.
 * Requesting only `openid profile` would yield an ID token for the SPA, which
 * the API correctly refuses: it authenticates the client, not the caller.
 */
const entraApiScope = readString(process.env.NEXT_PUBLIC_ENTRA_API_SCOPE, '');
/**
 * Every tenant permitted to reach TDMS. The browser uses this only to choose an
 * authority; the API re-validates the `tid` claim against its own allow-list,
 * which is what actually decides admission.
 */
const entraAllowedTenantIds = readList(process.env.NEXT_PUBLIC_ENTRA_ALLOWED_TENANT_IDS);

/** True only when the organisation has supplied a complete Entra configuration. */
const isEntraConfigured =
  entraClientId !== '' && entraAllowedTenantIds.length > 0 && entraApiScope !== '';

/**
 * Why authentication cannot run, or null when it can.
 *
 * Production never falls back to mock. A deployment missing its Entra
 * configuration must fail visibly: the quiet alternative is an application that
 * lets anybody in while looking like it is working correctly.
 */
function authConfigurationError(): string | null {
  if (isEntraConfigured) return null;
  const missing = [
    entraClientId === '' ? 'NEXT_PUBLIC_ENTRA_CLIENT_ID' : null,
    entraAllowedTenantIds.length === 0 ? 'NEXT_PUBLIC_ENTRA_ALLOWED_TENANT_IDS' : null,
    entraApiScope === '' ? 'NEXT_PUBLIC_ENTRA_API_SCOPE' : null,
  ].filter(Boolean);
  return `Microsoft sign-in is not configured. Missing: ${missing.join(', ')}.`;
}

const configurationError = authConfigurationError();

export const env = {
  appName: readString(process.env.NEXT_PUBLIC_APP_NAME, 'TDMS'),
  appEnvironment,
  apiUrl: readString(process.env.NEXT_PUBLIC_API_URL, 'http://localhost:8000'),

  authMode: 'entra' as const,
  isEntraConfigured,
  authConfigurationError: configurationError,
  /** Whether sign-in can work at all right now. */
  canSignIn: configurationError === null,

  entra: {
    clientId: entraClientId,
    allowedTenantIds: entraAllowedTenantIds,
    /** Defaults to the first allowed tenant when no explicit authority is set. */
    authority:
      entraAuthority ||
      (entraAllowedTenantIds[0]
        ? `https://login.microsoftonline.com/${entraAllowedTenantIds[0]}`
        : ''),
    redirectUri: entraRedirectUri,
    apiScope: entraApiScope,
  },

} as const;

export const isProduction = isProductionEnvironment;
