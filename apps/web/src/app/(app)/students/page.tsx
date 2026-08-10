import { Suspense } from 'react';
import type { Metadata } from 'next';

import { StudentWorkArea } from '@/features/students/student-work-area';
import { LoadingState } from '@/components/common/states';
import { INTERFACE_NAMES } from '@/lib/interface-names';

export const metadata: Metadata = {
  title: INTERFACE_NAMES.studentData,
};

export default function StudentsPage() {
  return (
    <Suspense fallback={<LoadingState label="Opening Student Data…" />}>
      <StudentWorkArea />
    </Suspense>
  );
}
