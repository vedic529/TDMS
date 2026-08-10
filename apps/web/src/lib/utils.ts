import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Initials used by the account avatar, e.g. "Ankit Kumar" -> "AK". */
export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Stable, non-random identifier suffix for prototype records. */
export function nextSequence(existing: string[], prefix: string): string {
  let highest = 0;
  for (const value of existing) {
    if (!value.startsWith(prefix)) continue;
    const numeric = Number.parseInt(value.slice(prefix.length), 10);
    if (Number.isFinite(numeric) && numeric > highest) highest = numeric;
  }
  return `${prefix}${String(highest + 1).padStart(4, '0')}`;
}

export function unique<T>(values: T[]): T[] {
  return Array.from(new Set(values));
}

export function sortByLabel<T extends { label: string }>(values: T[]): T[] {
  return [...values].sort((a, b) => a.label.localeCompare(b.label));
}
