'use client';

import * as React from 'react';

import { referenceApi } from '@/services/reference-api';
import { qualificationCodeLabel } from '@/features/reference-data/reference-adapters';
import type { Campus, College, QualificationOffering } from '@/types/reference';
import type { SelectOption } from '@/types/common';

interface ReferenceDataBundle {
  colleges: College[];
  campuses: Campus[];
  qualificationOfferings: QualificationOffering[];
}

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
      // Colleges, campuses and the qualifications actually offered come from
      // PostgreSQL through the reference API — the same source Page 4 uses.
      //
      // Everything downstream of this provider uses the same database-backed
      // college, campus and qualification offering records.
      const [collegeRows, campusRows, courseRows] = await Promise.all([
        referenceApi.listColleges(),
        referenceApi.listCampuses(),
        referenceApi.listCourses(),
      ]);

      const colleges: College[] = collegeRows.map((row) => ({
        id: String(row.id),
        collegeShortName: row.college_short_name,
        collegeFullName: row.college_full_name,
        emailDomain: row.email_domain ?? '',
        isActive: row.is_active,
      }));

      // A campus is shared between colleges (DBQ-04), but the display type
      // carries one `collegeId`. The real college/campus pairs come from the
      // offerings below, so a campus is emitted once per college that operates
      // it — which is what makes the dependent dropdown correct.
      const campusById = new Map(campusRows.map((row) => [row.id, row]));
      const seenPairs = new Set<string>();
      const campuses: Campus[] = [];
      const qualificationOfferings: QualificationOffering[] = [];

      for (const course of courseRows) {
        const pair = `${course.college_id}:${course.campus_id}`;
        if (!seenPairs.has(pair)) {
          seenPairs.add(pair);
          const campus = campusById.get(course.campus_id);
          if (campus) {
            campuses.push({
              id: String(campus.id),
              collegeId: String(course.college_id),
              campusName: campus.campus_name,
              campusLocation: campus.campus_location,
              // Carried through so a student file resolves whichever spelling
              // of the address it uses.
              sourceAddresses: campus.source_addresses ?? [],
              state: campus.state,
              isActive: campus.is_active,
            });
          }
        }

        qualificationOfferings.push({
          id: String(course.id),
          collegeId: String(course.college_id),
          campusId: String(course.campus_id),
          qualificationCode: qualificationCodeLabel(course.qualification_code),
          supersededCodes: course.qualification_superseded_codes ?? [],
          qualificationTitle: course.qualification_title,
          durationOptions: course.duration_options,
          isActive: !course.is_deleted,
        });
      }

      setData({
        colleges,
        campuses,
        qualificationOfferings,
      });

      // Bulk Student Import no longer validates in the browser: the API reads
      // the file and resolves every reference against the database directly,
      // so there is nothing to hand the prototype client here.
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
