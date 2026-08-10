'use client';

import * as React from 'react';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { SelectOption } from '@/types/common';

interface DependentSelectProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder: string;
  /** When set, the control is disabled and this explains what to choose first. */
  requires?: string;
  disabled?: boolean;
  emptyMessage?: string;
  'aria-describedby'?: string;
  'aria-invalid'?: boolean;
}

/**
 * A controlled dropdown that depends on an earlier selection
 * (SRS 6.3 College -> Campus -> Qualification, COL-01/COL-02).
 *
 * It stays visible but disabled until the parent value is chosen so the user
 * can see the required order rather than discovering a missing control.
 */
/**
 * The same approved value can be offered by more than one campus, so an option
 * list built from reference data may repeat a value. A dropdown must show each
 * approved value once, so options are collapsed by value here rather than at
 * every call site.
 */
function distinct(options: SelectOption[]): SelectOption[] {
  const seen = new Map<string, SelectOption>();
  for (const option of options) {
    if (!seen.has(option.value)) seen.set(option.value, option);
  }
  return Array.from(seen.values());
}

export function DependentSelect({
  id,
  value,
  onChange,
  options,
  placeholder,
  requires,
  disabled,
  emptyMessage = 'No approved values are available for this selection.',
  ...aria
}: DependentSelectProps) {
  const isDisabled = disabled || Boolean(requires);
  const items = distinct(options);
  const hasOptions = items.length > 0;

  return (
    <div className="space-y-1">
      <Select value={value} onValueChange={onChange} disabled={isDisabled || !hasOptions}>
        <SelectTrigger id={id} {...aria}>
          <SelectValue placeholder={requires ? `Select ${requires} first` : placeholder} />
        </SelectTrigger>
        <SelectContent>
          {items.map((option) => (
            <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {!requires && !hasOptions && !disabled && (
        <p className="text-[12px] text-muted-foreground">{emptyMessage}</p>
      )}
    </div>
  );
}

/** Convenience wrapper for a plain, non-dependent controlled dropdown. */
export function SimpleSelect({
  id,
  value,
  onChange,
  options,
  placeholder,
  disabled,
  ...aria
}: Omit<DependentSelectProps, 'requires' | 'emptyMessage'>) {
  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger id={id} {...aria}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {distinct(options).map((option) => (
          <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function toOptions<T>(
  items: T[],
  toValue: (item: T) => string,
  toLabel: (item: T) => string,
): SelectOption[] {
  return items.map((item) => ({ value: toValue(item), label: toLabel(item) }));
}
