'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { AlertCircle, Loader2, ShieldCheck } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { MicrosoftLogo, TdmsLogo } from '@/components/common/tdms-logo';
import { useAuth } from './auth-context';
import { env } from '@/lib/env';

/**
 * Login and Authentication (SRS 2.2 entry point).
 *
 * TDMS offers exactly one authentication action: sign in with Microsoft. There
 * is no email or password field, no "forgot password", and no social sign-in.
 * The application never asks the user for a Microsoft password (AUTH-03).
 *
 * Until the Microsoft Entra tenant is approved (OD-01), the same button uses
 * the development authentication adapter and the screen says so.
 */
export function LoginScreen() {
  const router = useRouter();
  const { status, signIn, lastFailure } = useAuth();
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (status === 'signed-in') router.replace('/timetable');
  }, [status, router]);

  async function handleSignIn() {
    setBusy(true);
    try {
      const ok = await signIn();
      // AUTH-07: a granted user enters Timetable View and Management.
      if (ok) router.replace('/timetable');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="tdms-auth-backdrop flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-[26rem]">
        <div className="rounded-2xl border border-border/70 bg-background/85 p-8 shadow-[0_18px_50px_-24px_rgba(15,23,42,0.35)] backdrop-blur-sm">
          <div className="flex flex-col items-center text-center">
            <TdmsLogo />
            <h1 className="mt-6 text-lg font-semibold tracking-tight text-foreground">
              Timetable Database Management System
            </h1>
            <p className="mt-4 text-[15px] font-medium text-foreground">Sign in to TDMS</p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">
              Use your organisation Microsoft account to continue.
            </p>
          </div>

          {lastFailure && (
            <Alert variant="destructive" className="mt-6">
              <AlertCircle aria-hidden="true" />
              <div className="space-y-1">
                <AlertTitle>
                  {/*
                    An unreachable API is not a denial. Calling it "Access
                    denied" sends the user to request access when what is
                    actually needed is to start the backend.
                  */}
                  {lastFailure.reason === 'SERVICE_UNAVAILABLE'
                    ? 'TDMS is unavailable'
                    : 'Access denied'}
                </AlertTitle>
                <AlertDescription>
                  {lastFailure.userMessage}
                  <span className="mt-1 block text-[12px] opacity-80">
                    Reference: {lastFailure.correlationId}
                  </span>
                </AlertDescription>
              </div>
            </Alert>
          )}

          {env.authConfigurationError && (
            <Alert variant="destructive" className="mt-6">
              <AlertCircle aria-hidden="true" />
              <div className="space-y-1">
                <AlertTitle>Sign-in is not available</AlertTitle>
                <AlertDescription>
                  {env.authConfigurationError} Contact the TDMS administrator - this is a server
                  configuration problem, not a problem with your account.
                </AlertDescription>
              </div>
            </Alert>
          )}

          <Button
            size="lg"
            className="mt-7 w-full gap-3"
            onClick={() => void handleSignIn()}
            disabled={busy || status === 'loading' || !env.canSignIn}
          >
            {busy ? (
              <Loader2 className="animate-spin" aria-hidden="true" />
            ) : (
              <MicrosoftLogo className="size-[18px]" />
            )}
            Sign in with Microsoft
          </Button>

          <p className="mt-5 flex items-start gap-2 text-[12px] leading-relaxed text-muted-foreground">
            <ShieldCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            Secure organisational access through Microsoft Entra ID. TDMS never asks for, receives or stores your
            Microsoft password.
          </p>
        </div>

        {env.authMode === 'mock' && env.canSignIn && (
          <p className="mx-auto mt-5 max-w-[24rem] text-center text-[12px] leading-relaxed text-muted-foreground">
            The Microsoft Entra ID application registration has not been supplied for this
            environment, so the button above uses the development authentication adapter and creates
            a demo session. No Microsoft account is contacted. This adapter is refused in production.
          </p>
        )}
      </div>

      <footer className="mt-10 text-center text-[12px] text-muted-foreground">
        <p>TDMS · Internal application · {env.appEnvironment}</p>
      </footer>
    </main>
  );
}
