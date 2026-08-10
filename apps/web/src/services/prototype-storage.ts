/**
 * Prototype browser storage.
 *
 * Everything written here belongs to the FRONTEND PROTOTYPE ONLY. Keys are
 * namespaced with `tdms.prototype.v1.` so demo data can never be confused with,
 * or migrated into, production data (DATA-06).
 *
 * Only the service layer touches this module. Page and feature components go
 * through `TdmsClient`, so swapping in the real FastAPI client removes browser
 * persistence with no change to the UI.
 */

export const PROTOTYPE_STORAGE_PREFIX = 'tdms.prototype.v1';

export const PROTOTYPE_STORAGE_KEYS = {
  dataset: `${PROTOTYPE_STORAGE_PREFIX}.dataset`,
  session: `${PROTOTYPE_STORAGE_PREFIX}.session`,
  devIdentity: `${PROTOTYPE_STORAGE_PREFIX}.dev-identity`,
} as const;

function storage(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    // Storage can be blocked by browser policy; the prototype still works,
    // it simply stops remembering changes between reloads.
    return null;
  }
}

export function readPrototypeValue<T>(key: string): T | null {
  const store = storage();
  if (!store) return null;
  try {
    const raw = store.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function writePrototypeValue<T>(key: string, value: T): void {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(key, JSON.stringify(value));
  } catch {
    // Quota or policy failure: the prototype continues with in-memory data.
  }
}

export function removePrototypeValue(key: string): void {
  const store = storage();
  if (!store) return;
  try {
    store.removeItem(key);
  } catch {
    /* ignore */
  }
}

/** Clears every prototype key. Used by the development tools "Reset demo data". */
export function clearPrototypeStorage(): void {
  const store = storage();
  if (!store) return;
  try {
    Object.values(PROTOTYPE_STORAGE_KEYS).forEach((key) => store.removeItem(key));
  } catch {
    /* ignore */
  }
}
