'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';

import type { AuthFailure, AuthSession, TdmsUser } from '@/types/auth';
import { getAuthProvider } from '@/services/auth';
import { getPermissions, type PermissionSet } from '@/lib/permissions';
import { ACTIVITY_EVENTS, INACTIVITY_TIMEOUT_MINUTES, INACTIVITY_TIMEOUT_MS } from '@/lib/session';

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

/**
 * How long to wait for a session to be restored before giving up and showing
 * the sign-in screen. Long enough for a slow network, short enough that a
 * stalled silent renewal does not look like a broken application.
 */
const RESTORE_TIMEOUT_MS = 12_000;

export function TdmsAuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [status, setStatus] = React.useState<AuthContextValue['status']>('loading');
  const [session, setSession] = React.useState<AuthSession | null>(null);
  const [lastFailure, setLastFailure] = React.useState<AuthFailure | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      let restored: AuthSession | null = null;
      try {
        // Bounded on purpose. A rejection is not the only way a restore can
        // fail: MSAL renews tokens through a hidden iframe, and if the
        // Microsoft session has ended that request can hang rather than throw,
        // leaving the user on "Checking your TDMS access…" indefinitely. A
        // timeout guarantees the application always reaches a decision — a
        // session, or the sign-in screen (AUTH-01).
        restored = await Promise.race([
          getAuthProvider().restoreSession(),
          new Promise<null>((resolve) => setTimeout(() => resolve(null), RESTORE_TIMEOUT_MS)),
        ]);
      } catch {
        restored = null;
      }
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
    try {
      const result = await getAuthProvider().signIn();
      if (result.ok) {
        setSession(result.session);
        setStatus('signed-in');
        return true;
      }
      setLastFailure(result.failure);
    } catch {
      setLastFailure({
        microsoftSignInResult: 'FAILURE',
        accessDecision: 'DENIED',
        reason: 'SIGN_IN_NOT_COMPLETED',
        userMessage: 'Sign-in could not be completed. Try again, or contact the TDMS administrator.',
        correlationId: 'unavailable',
      });
    }
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
    const restored = await getAuthProvider().restoreSession().catch(() => null);
    setSession(restored);
    setStatus(restored ? 'signed-in' : 'signed-out');
  }, []);

  /**
   * AUTH-09 with the approved OD-03 inactivity period: the session ends after
   * 30 minutes without activity. No maximum session duration is applied,
   * because that part of OD-03 is not approved.
   */
  React.useEffect(() => {
    if (status !== 'signed-in') return;

    let timer: ReturnType<typeof setTimeout>;

    const expire = () => {
      toast.info('You have been signed out', {
        description: `TDMS ends a session after ${INACTIVITY_TIMEOUT_MINUTES} minutes without activity. Sign in again to continue.`,
        duration: 10000,
      });
      void signOut();
    };

    const restart = () => {
      clearTimeout(timer);
      timer = setTimeout(expire, INACTIVITY_TIMEOUT_MS);
    };

    restart();
    ACTIVITY_EVENTS.forEach((event) => window.addEventListener(event, restart, { passive: true }));

    return () => {
      clearTimeout(timer);
      ACTIVITY_EVENTS.forEach((event) => window.removeEventListener(event, restart));
    };
  }, [status, signOut]);

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
