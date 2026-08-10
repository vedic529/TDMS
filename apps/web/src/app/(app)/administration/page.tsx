import { Suspense } from 'react';
import type { Metadata } from 'next';

import { AdministrationWorkArea } from '@/features/administration/administration-work-area';
import { LoadingState } from '@/components/common/states';
import { INTERFACE_NAMES } from '@/lib/interface-names';

export const metadata: Metadata = {
  title: INTERFACE_NAMES.administration,
};

/**
 * Secondary administrative route.
 * It is reached from the account menu and is deliberately not one of the four
 * primary operational navigation items (SRS 2.2).
 */
export default function AdministrationPage() {
  return (
    <Suspense fallback={<LoadingState label="Opening Administration…" />}>
      <AdministrationWorkArea />
    </Suspense>
  );
}
