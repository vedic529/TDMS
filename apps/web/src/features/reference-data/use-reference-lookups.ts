'use client';

import * as React from 'react';

import { referenceApi } from '@/services/reference-api';
import { toCampus, toCollege } from './reference-adapters';
import type { Campus, College } from '@/types/reference';

/**
 * College and campus lookups for the reference-data screens, from PostgreSQL.
 *
 * The application-wide `ReferenceDataProvider` is still backed by the
 * transitional mock service that Student, Trainer and Timetable use. Reading
 * dropdown options from it here would leave this module half real — the course
 * list from the database, the college filter from a mock array — which is
 * exactly the mixing Step 6 set out to remove.
 *
 * `campusesForCollege` asks the server rather than filtering a cached list.
 * COL-01 approval lives in `college_campuses` and the API applies it in SQL;
 * deciding it in the browser would put an approval rule in the one place a user
 * can edit.
 */
export function useReferenceLookups() {
  const [colleges, setColleges] = React.useState<College[]>([]);
  const [campuses, setCampuses] = React.useState<Campus[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  /** Campuses approved for one college, keyed by college id. */
  const [byCollege, setByCollege] = React.useState<Record<string, Campus[]>>({});

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [collegeRows, campusRows] = await Promise.all([
        referenceApi.listColleges(),
        referenceApi.listCampuses(),
      ]);
      setColleges(collegeRows.map(toCollege));
      setCampuses(campusRows.map((row) => toCampus(row, '')));
    } catch {
      setColleges([]);
      setCampuses([]);
      setError('Reference lookups could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const loadCampusesFor = React.useCallback(async (collegeId: string | undefined) => {
    if (!collegeId) return;
    try {
      const rows = await referenceApi.listCampuses({
        collegeId: Number(collegeId),
        activeOnly: true,
      });
      setByCollege((current) => ({
        ...current,
        [collegeId]: rows.map((row) => toCampus(row, collegeId)),
      }));
    } catch {
      setByCollege((current) => ({ ...current, [collegeId]: [] }));
    }
  }, []);

  const campusesForCollege = React.useCallback(
    (collegeId: string | undefined): Campus[] => (collegeId ? byCollege[collegeId] ?? [] : []),
    [byCollege],
  );

  const collegeById = React.useCallback(
    (id: string | undefined) => colleges.find((college) => college.id === id),
    [colleges],
  );

  const campusById = React.useCallback(
    (id: string | undefined) => campuses.find((campus) => campus.id === id),
    [campuses],
  );

  return {
    colleges,
    campuses,
    loading,
    error,
    reload: load,
    loadCampusesFor,
    campusesForCollege,
    collegeById,
    campusById,
    collegeOptions: colleges.map((college) => ({
      value: college.id,
      label: college.collegeFullName,
    })),
  };
}
