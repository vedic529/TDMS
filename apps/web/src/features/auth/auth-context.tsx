'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';

import type { AuthFailure, AuthSession, TdmsUser } from '@/types/auth';
import { getAuthProvider } from '@/services/auth';
import { getPermissions, type PermissionSet } from '@/lib/permissions';

interface AuthContextValue {
  status: 'loading' | 'signed-in' | 'signed-out';
  session: AuthSession | null;
  user: TdmsUser | null;
  permissions: PermissionSet;
  lastFailure: AuthFailure | null;
  signIn: () => Promise<boolean>;
  signOut: () => Promise<void>;
  /** Re-reads the signed-in user so an access change applies (AUTH-12). */
  refreshSession: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function TdmsAuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [status, setStatus] = React.useState<AuthContextValue['status']>('loading');
  const [session, setSession] = React.useState<AuthSession | null>(null);
  const [lastFailure, setLastFailure] = React.useState<AuthFailure | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      const restored = await getAuthProvider().restoreSession();
      if (cancelled) return;
      setSession(restored);
      setStatus(restored ? 'signed-in' : 'signed-out');
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = React.useCallback(async () => {
    setLastFailure(null);
    const result = await getAuthProvider().signIn();
    if (result.ok) {
      setSession(result.session);
      setStatus('signed-in');
      return true;
    }
    setLastFailure(result.failure);
    setSession(null);
    setStatus('signed-out');
    return false;
  }, []);

  const signOut = React.useCallback(async () => {
    await getAuthProvider().signOut();
    setSession(null);
    setStatus('signed-out');
    router.replace('/login');
  }, [router]);

  const refreshSession = React.useCallback(async () => {
    const restored = await getAuthProvider().restoreSession();
    setSession(restored);
    setStatus(restored ? 'signed-in' : 'signed-out');
  }, []);

  const value = React.useMemo<AuthContextValue>(
    () => ({
      status,
      session,
      user: session?.user ?? null,
      permissions: getPermissions(session?.user ?? null),
      lastFailure,
      signIn,
      signOut,
      refreshSession,
    }),
    [status, session, lastFailure, signIn, signOut, refreshSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = React.useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside TdmsAuthProvider.');
  }
  return context;
}

/** Convenience hook: the signed-in user, or null while loading/signed out. */
export function useCurrentUser(): TdmsUser | null {
  return useAuth().user;
}

/** Convenience hook: the permission set for the signed-in user. */
export function usePermissions(): PermissionSet {
  return useAuth().permissions;
}
