'use client';

import { FilterBar, FilterField } from '@/components/common/filter-bar';
import { SimpleSelect } from '@/components/common/dependent-select';
import { TRAINING_PACKAGES, type RollingScope } from '@/services/rolling-timetable-api';

export interface RollingSelection {
  trainingPackage: string;
  qualificationCode: string;
  durationWeeks: number;
}

export function defaultSelection(scopes: RollingScope[]): RollingSelection | null {
  if (scopes.length === 0) return null;
  const rank = new Map<string, number>(TRAINING_PACKAGES.map((item, index) => [item, index]));
  const ordered = [...scopes].sort((a, b) => {
    const packageDelta = (rank.get(a.training_package) ?? 99) - (rank.get(b.training_package) ?? 99);
    if (packageDelta !== 0) return packageDelta;
    if (a.qualification_code !== b.qualification_code) {
      return a.qualification_code < b.qualification_code ? -1 : 1;
    }
    return a.duration_weeks - b.duration_weeks;
  });
  const first = ordered[0];
  return {
    trainingPackage: first.training_package,
    qualificationCode: first.qualification_code,
    durationWeeks: first.duration_weeks,
  };
}

export function selectionFromScopes(
  scopes: RollingScope[],
  candidate: RollingSelection | null,
): RollingSelection | null {
  const fallback = defaultSelection(scopes);
  if (!candidate || !fallback) return fallback;
  const exact = scopes.find(
    (scope) =>
      scope.training_package === candidate.trainingPackage &&
      scope.qualification_code === candidate.qualificationCode &&
      scope.duration_weeks === candidate.durationWeeks,
  );
  if (exact) return candidate;
  const sameQual = scopes.find(
    (scope) =>
      scope.training_package === candidate.trainingPackage &&
      scope.qualification_code === candidate.qualificationCode,
  );
  if (sameQual) {
    return {
      trainingPackage: sameQual.training_package,
      qualificationCode: sameQual.qualification_code,
      durationWeeks: sameQual.duration_weeks,
    };
  }
  const samePackage = scopes.find((scope) => scope.training_package === candidate.trainingPackage);
  if (samePackage) {
    return {
      trainingPackage: samePackage.training_package,
      qualificationCode: samePackage.qualification_code,
      durationWeeks: samePackage.duration_weeks,
    };
  }
  return fallback;
}

export function RollingScopeBar({
  scopes,
  selection,
  onChange,
}: {
  scopes: RollingScope[];
  selection: RollingSelection;
  onChange: (next: RollingSelection) => void;
}) {
  const packages = TRAINING_PACKAGES.filter((item) =>
    scopes.some((scope) => scope.training_package === item),
  );
  const qualifications = [
    ...new Set(
      scopes
        .filter((scope) => scope.training_package === selection.trainingPackage)
        .map((scope) => scope.qualification_code),
    ),
  ].sort();
  const durations = [
    ...new Set(
      scopes
        .filter(
          (scope) =>
            scope.training_package === selection.trainingPackage &&
            scope.qualification_code === selection.qualificationCode,
        )
        .map((scope) => scope.duration_weeks),
    ),
  ].sort((a, b) => a - b);

  return (
    <FilterBar>
      <FilterField label="Training package" htmlFor="rt-package">
        <SimpleSelect
          id="rt-package"
          value={selection.trainingPackage}
          onChange={(value) => {
            const next = selectionFromScopes(scopes, {
              trainingPackage: value,
              qualificationCode: selection.qualificationCode,
              durationWeeks: selection.durationWeeks,
            });
            if (next) onChange(next);
          }}
          options={packages.map((item) => ({ value: item, label: item }))}
          placeholder="Training package"
        />
      </FilterField>
      <FilterField label="Qualification" htmlFor="rt-qualification">
        <SimpleSelect
          id="rt-qualification"
          value={selection.qualificationCode}
          onChange={(value) => {
            const next = selectionFromScopes(scopes, {
              trainingPackage: selection.trainingPackage,
              qualificationCode: value,
              durationWeeks: selection.durationWeeks,
            });
            if (next) onChange(next);
          }}
          options={qualifications.map((item) => ({ value: item, label: item }))}
          placeholder="Qualification"
        />
      </FilterField>
      <FilterField label="Duration in weeks" htmlFor="rt-duration">
        <SimpleSelect
          id="rt-duration"
          value={String(selection.durationWeeks)}
          onChange={(value) =>
            onChange({
              trainingPackage: selection.trainingPackage,
              qualificationCode: selection.qualificationCode,
              durationWeeks: Number(value),
            })
          }
          options={durations.map((item) => ({ value: String(item), label: `${item} weeks` }))}
          placeholder="Duration"
        />
      </FilterField>
    </FilterBar>
  );
}
