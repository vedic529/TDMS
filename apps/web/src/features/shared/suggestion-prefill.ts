/**
 * Reading the pre-fill values a suggestion carries.
 *
 * An import stores the raising row's other values beside each entry (approved
 * 15 September 2026) - a unit's title, the campus a room was named at, the
 * units a trainer was teaching - so Add opens its form already filled with
 * what the file said. These helpers read them defensively: the column is JSON,
 * and an entry raised before it existed has none.
 */

import type { ReferenceSuggestion } from '@/services/suggestions-api';
import type { UocType } from '@/types/reference';

export function attributeText(row: ReferenceSuggestion | null | undefined, key: string): string {
  const value = row?.attributes?.[key];
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number') return String(value);
  return '';
}

export function attributeList(row: ReferenceSuggestion | null | undefined, key: string): string[] {
  const value = row?.attributes?.[key];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string' && item.trim() !== '');
}

export function attributeRecords(
  row: ReferenceSuggestion | null | undefined,
  key: string,
): Record<string, string>[] {
  const value = row?.attributes?.[key];
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is Record<string, string> => typeof item === 'object' && item !== null,
  );
}

/** How an allocation file's UoC Type reads as a unit's. */
const UOC_TYPES: Record<string, UocType> = {
  THEORY_ONLY: 'Theory',
  PRACTICAL_ONLY: 'Practical',
  THEORY_AND_PRACTICAL: 'Theory and Practical',
};

export function uocTypeFromAllocation(value: string): UocType | undefined {
  return UOC_TYPES[value.trim().toUpperCase()];
}

/** Upper case with collapsed spacing - how the server compares two spellings. */
export function plain(value: string | null | undefined): string {
  return (value ?? '').split(/\s+/).filter(Boolean).join(' ').toUpperCase();
}
