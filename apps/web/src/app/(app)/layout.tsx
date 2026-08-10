'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';

import { TopNavigation } from '@/components/common/top-navigation';
import { DevAccessPreview } from '@/features/dev-tools/dev-access-preview';
import { ReferenceDataProvider } from '@/features/shared/reference-data-context';
import { useAuth } from '@/features/auth/auth-context';

/**
 * Shell for every operational page.
 *
 * AUTH-01 / AUTH-06 / ACC-06: an operational route cannot be opened without a
 * granted TDMS access decision, including when a direct web address is entered.
 */
export default function OperationalLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { status } = useAuth();

  React.useEffect(() => {
    if (status === 'signed-out') router.replace('/login');
  }, [status, router]);

  if (status !== 'signed-in') {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          Checking your TDMS access…
        </p>
      </main>
    );
  }

  return (
    <ReferenceDataProvider>
      <div className="flex min-h-screen flex-col bg-page">
        <TopNavigation />
        <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6">{children}</main>
        <footer className="border-t border-border bg-background">
          <div className="mx-auto flex max-w-[1600px] flex-col gap-1 px-4 py-4 text-[12px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <p>TDMS — Timetable Database Management System · Internal use only</p>
            <p>Frontend prototype. Demo data only; not production student, trainer or timetable information.</p>
          </div>
        </footer>
      </div>
      <DevAccessPreview />
    </ReferenceDataProvider>
  );
}
