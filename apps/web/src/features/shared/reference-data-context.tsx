'use client';

import * as React from 'react';

import type { ReferenceDataBundle } from '@/services/dataset';
import { getTdmsClient } from '@/services';
import type { Campus, College, QualificationOffering } from '@/types/reference';
import type { SelectOption } from '@/types/common';

interface ReferenceDataContextValue {
  data: ReferenceDataBundle | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
  /** Campuses approved for one college (COL-01 / SRS 6.3 dependent dropdown). */
  campusesForCollege: (collegeId: string | undefined) => Campus[];
  /** Qualifications offered by the selected college and campus (COL-02). */
  offeringsFor: (collegeId: string | undefined, campusId: string | undefined) => QualificationOffering[];
  collegeById: (id: string | undefined) => College | undefined;
  campusById: (id: string | undefined) => Campus | undefined;
  collegeOptions: SelectOption[];
}

const ReferenceDataContext = React.createContext<ReferenceDataContextValue | null>(null);

export function ReferenceDataProvider({ children }: { children: React.ReactNode }) {
  const [data, setData] = React.useState<ReferenceDataBundle | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getTdmsClient().getReferenceData());
    } catch {
      setError('Reference data could not be loaded. Refresh the page or contact the TDMS administrator.');
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const value = React.useMemo<ReferenceDataContextValue>(() => {
    const campuses = data?.campuses ?? [];
    const colleges = data?.colleges ?? [];
    const offerings = data?.qualificationOfferings ?? [];

    return {
      data,
      loading,
      error,
      reload: load,
      campusesForCollege: (collegeId) =>
        collegeId ? campuses.filter((campus) => campus.collegeId === collegeId && campus.isActive) : [],
      offeringsFor: (collegeId, campusId) =>
        offerings.filter(
          (offering) =>
            offering.isActive &&
            (!collegeId || offering.collegeId === collegeId) &&
            (!campusId || offering.campusId === campusId),
        ),
      collegeById: (id) => colleges.find((college) => college.id === id),
      campusById: (id) => campuses.find((campus) => campus.id === id),
      collegeOptions: colleges
        .filter((college) => college.isActive)
        .map((college) => ({ value: college.id, label: college.collegeFullName })),
    };
  }, [data, loading, error, load]);

  return <ReferenceDataContext.Provider value={value}>{children}</ReferenceDataContext.Provider>;
}

export function useReferenceData(): ReferenceDataContextValue {
  const context = React.useContext(ReferenceDataContext);
  if (!context) {
    throw new Error('useReferenceData must be used inside ReferenceDataProvider.');
  }
  return context;
}
