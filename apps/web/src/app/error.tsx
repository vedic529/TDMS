'use client';

import * as React from 'react';
import Link from 'next/link';
import { AlertCircle, RotateCcw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { TdmsLogo } from '@/components/common/tdms-logo';
import { INTERFACE_NAMES } from '@/lib/interface-names';

/**
 * Error boundary for the App Router.
 *
 * Next.js requires this component to exist — without it the router has nothing
 * to render when a page throws, and the dev server reports "missing required
 * error components".
 *
 * It shows the user what to do next and a safe technical reference for support
 * (AUTH-11). It never shows the error message itself: a thrown message can
 * carry an internal path, a query or a record the user is not entitled to see.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  React.useEffect(() => {
    // The full error goes to the console for a developer; the interface does not
    // repeat it back to the user.
    console.error('TDMS page error:', error);
  }, [error]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-[30rem] rounded-2xl border border-border/70 bg-background/85 p-8 text-center shadow-[0_18px_50px_-24px_rgba(15,23,42,0.35)]">
        <div className="flex flex-col items-center">
          <TdmsLogo />
          <span
            aria-hidden="true"
            className="mt-6 flex size-11 items-center justify-center rounded-full bg-destructive/10 text-destructive"
          >
            <AlertCircle className="size-5" />
          </span>
          <h1 className="mt-4 text-lg font-semibold tracking-tight text-foreground">
            Something went wrong
          </h1>
          <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
            TDMS could not display this page. Your data has not been changed. Try again, and if the
            problem continues contact the TDMS administrator with the reference below.
          </p>
          {error.digest && (
            <p className="mt-3 rounded-md bg-muted px-3 py-1.5 font-mono text-[12px] text-muted-foreground">
              Reference: {error.digest}
            </p>
          )}
        </div>

        <div className="mt-7 flex flex-col gap-2 sm:flex-row sm:justify-center">
          <Button onClick={reset}>
            <RotateCcw aria-hidden="true" />
            Try again
          </Button>
          <Button asChild variant="outline">
            <Link href="/timetable">Back to {INTERFACE_NAMES.timetable}</Link>
          </Button>
        </div>
      </div>
    </main>
  );
}
