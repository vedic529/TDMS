import { Suspense } from 'react';
import type { Metadata } from 'next';

import { TimetableWorkArea } from '@/features/timetable/timetable-work-area';
import { LoadingState } from '@/components/common/states';
import { INTERFACE_NAMES } from '@/lib/interface-names';

export const metadata: Metadata = {
  title: INTERFACE_NAMES.timetable,
};

export default function TimetablePage() {
  return (
    <Suspense fallback={<LoadingState label="Opening Timetable View and Management…" />}>
      <TimetableWorkArea />
    </Suspense>
  );
}
