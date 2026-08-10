'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';

import { useAuth } from '@/features/auth/auth-context';

/**
 * AUTH-07: a granted user enters Timetable View and Management as the first
 * operational page. Anyone without a session goes to the sign-in screen.
 */
export default function RootPage() {
  const router = useRouter();
  const { status } = useAuth();

  React.useEffect(() => {
    if (status === 'loading') return;
    router.replace(status === 'signed-in' ? '/timetable' : '/login');
  }, [status, router]);

  return (
    <main className="flex min-h-screen items-center justify-center">
      <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        Opening TDMS…
      </p>
    </main>
  );
}
