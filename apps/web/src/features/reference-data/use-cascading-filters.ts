'use client';

import * as React from 'react';

import { referenceApi } from '@/services/reference-api';
import { qualificationCodeLabel } from './reference-adapters';
import type { SelectOption } from '@/types/common';

/**
 * College -> Campus -> Qualification, with every level derived from the one
 * above it.
 *
 * Three things this exists to guarantee, all of which were previously wrong:
 *
 * 1. **Options come from the server, scoped.** Campus options are the campuses
 *    approved for the chosen colleges; qualification options are the
 *    qualifications on real offerings within the chosen college/campus. Building
 *    them from the full tables is what offered HJ/Hobart a list of agriculture
 *    qualifications it does not deliver.
 *
 * 2. **Downstream selections are pruned when upstream changes.** Switching from
 *    AVTA to HJ must drop Bundaberg and AHC40422, not leave their ids in state
 *    where they would silently restrict the next query to nothing.
 *
 * 3. **Empty means All.** Holding every id instead would go stale the moment the
 *    scope changed. The empty array is the only representation of "no
 *    restriction", so a cascade change cannot leave a wrong filter behind.
 */
export interface CascadingFilters {
  collegeIds: string[];
  campusIds: string[];
  qualificationIds: string[];
}

export const EMPTY_FILTERS: CascadingFilters = {
  collegeIds: [],
  campusIds: [],
  qualificationIds: [],
};

const numbers = (ids: readonly string[]) => ids.map(Number).filter(Number.isFinite);

export function useCascadingFilters() {
  const [filters, setFilters] = React.useState<CascadingFilters>(EMPTY_FILTERS);

  const [collegeOptions, setCollegeOptions] = React.useState<SelectOption[]>([]);
  const [campusOptions, setCampusOptions] = React.useState<SelectOption[]>([]);
  const [qualificationOptions, setQualificationOptions] = React.useState<SelectOption[]>([]);
  const [loadingCampuses, setLoadingCampuses] = React.useState(false);
  const [loadingQualifications, setLoadingQualifications] = React.useState(false);

  // Colleges are the root of the cascade and depend on nothing.
  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const rows = await referenceApi.listColleges();
        if (!cancelled) {
          setCollegeOptions(
            rows.map((row) => ({ value: String(row.id), label: row.college_short_name })),
          );
        }
      } catch {
        if (!cancelled) setCollegeOptions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const collegeKey = filters.collegeIds.join(',');
  const campusKey = filters.campusIds.join(',');

  // Campuses follow the colleges.
  React.useEffect(() => {
    let cancelled = false;
    setLoadingCampuses(true);
    void (async () => {
      try {
        const rows = await referenceApi.listCampuses({
          collegeIds: numbers(collegeKey ? collegeKey.split(',') : []),
        });
        if (cancelled) return;
        const options = rows.map((row) => ({
          value: String(row.id),
          label: row.campus_name,
        }));
        setCampusOptions(options);

        // Drop any campus that the new college scope no longer offers.
        const allowed = new Set(options.map((option) => option.value));
        setFilters((current) => {
          const kept = current.campusIds.filter((id) => allowed.has(id));
          return kept.length === current.campusIds.length
            ? current
            : { ...current, campusIds: kept };
        });
      } catch {
        if (!cancelled) setCampusOptions([]);
      } finally {
        if (!cancelled) setLoadingCampuses(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [collegeKey]);

  // Qualifications follow both, and come from real offerings.
  React.useEffect(() => {
    let cancelled = false;
    setLoadingQualifications(true);
    void (async () => {
      try {
        const rows = await referenceApi.listQualifications({
          collegeIds: numbers(collegeKey ? collegeKey.split(',') : []),
          campusIds: numbers(campusKey ? campusKey.split(',') : []),
        });
        if (cancelled) return;
        const options = rows.map((row) => ({
          value: String(row.id),
          label: `${qualificationCodeLabel(row.qualification_code)} — ${row.qualification_title}`,
        }));
        setQualificationOptions(options);

        const allowed = new Set(options.map((option) => option.value));
        setFilters((current) => {
          const kept = current.qualificationIds.filter((id) => allowed.has(id));
          return kept.length === current.qualificationIds.length
            ? current
            : { ...current, qualificationIds: kept };
        });
      } catch {
        if (!cancelled) setQualificationOptions([]);
      } finally {
        if (!cancelled) setLoadingQualifications(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [collegeKey, campusKey]);

  const setColleges = React.useCallback((collegeIds: string[]) => {
    // Campus and qualification are recalculated by the effects above; clearing
    // them here means the stale ids never reach a request in the first place.
    setFilters({ collegeIds, campusIds: [], qualificationIds: [] });
  }, []);

  const setCampuses = React.useCallback((campusIds: string[]) => {
    setFilters((current) => ({ ...current, campusIds, qualificationIds: [] }));
  }, []);

  const setQualifications = React.useCallback((qualificationIds: string[]) => {
    setFilters((current) => ({ ...current, qualificationIds }));
  }, []);

  const clear = React.useCallback(() => setFilters(EMPTY_FILTERS), []);

  const qualificationKey = filters.qualificationIds.join(',');

  /**
   * Numeric ids for a request, memoised on the *contents* of the selection.
   *
   * This has to be stable between renders. Consumers put `scope.collegeIds` in
   * the dependency array of the callback that fetches their rows, and a fresh
   * array each render makes that callback fresh each render, which re-runs the
   * fetching effect, which sets state, which renders again — React stops it with
   * "Maximum update depth exceeded", but only after the loop has already started.
   *
   * The join keys are the dependencies rather than the arrays themselves because
   * the arrays are what is being rebuilt; their identity is exactly the thing
   * that cannot be trusted here.
   */
  const scope = React.useMemo(
    () => ({
      collegeIds: numbers(filters.collegeIds),
      campusIds: numbers(filters.campusIds),
      qualificationIds: numbers(filters.qualificationIds),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [collegeKey, campusKey, qualificationKey],
  );

  return {
    filters,
    collegeOptions,
    campusOptions,
    qualificationOptions,
    loadingCampuses,
    loadingQualifications,
    setColleges,
    setCampuses,
    setQualifications,
    clear,
    /** Ids for a request. Empty arrays are omitted by the API client. */
    scope,
  };
}
