import Link from 'next/link';
import { FileQuestion } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { TdmsLogo } from '@/components/common/tdms-logo';
import { INTERFACE_NAMES } from '@/lib/interface-names';

/**
 * Shown for an address that does not exist.
 *
 * Deliberately says nothing about whether a record exists but is not visible to
 * this user: "not found" and "not permitted" must look identical from outside,
 * or the page becomes a way to enumerate records (AUTH-10).
 */
export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-[30rem] rounded-2xl border border-border/70 bg-background/85 p-8 text-center shadow-[0_18px_50px_-24px_rgba(15,23,42,0.35)]">
        <div className="flex flex-col items-center">
          <TdmsLogo />
          <span
            aria-hidden="true"
            className="mt-6 flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground"
          >
            <FileQuestion className="size-5" />
          </span>
          <h1 className="mt-4 text-lg font-semibold tracking-tight text-foreground">
            Page not found
          </h1>
          <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
            That address is not part of TDMS. Use the navigation to reach an operational work area.
          </p>
        </div>

        <div className="mt-7">
          <Button asChild>
            <Link href="/timetable">Back to {INTERFACE_NAMES.timetable}</Link>
          </Button>
        </div>
      </div>
    </main>
  );
}
