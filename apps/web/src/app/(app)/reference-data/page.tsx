import { Suspense } from 'react';
import type { Metadata } from 'next';

import { ReferenceDataWorkArea } from '@/features/reference-data/reference-data-work-area';
import { LoadingState } from '@/components/common/states';
import { INTERFACE_NAMES } from '@/lib/interface-names';

export const metadata: Metadata = {
  title: INTERFACE_NAMES.referenceData,
};

export default function ReferenceDataPage() {
  return (
    <Suspense fallback={<LoadingState label="Opening College and Course Reference Data…" />}>
      <ReferenceDataWorkArea />
    </Suspense>
  );
}
