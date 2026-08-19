'use client';

import * as React from 'react';
import { Check, ChevronDown } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import type { SelectOption } from '@/types/common';

export interface MultiSelectFilterProps {
  id?: string;
  /** Selected ids. **Empty means "All"** — see the note below. */
  value: string[];
  onChange: (value: string[]) => void;
  options: SelectOption[];
  /** Shown when nothing is selected, e.g. "All Colleges". */
  allLabel: string;
  /** Singular noun for the summary, e.g. "College". */
  noun: string;
  /** When set the control is disabled and this says what to choose first. */
  requires?: string;
  loading?: boolean;
  emptyMessage?: string;
}

/**
 * A multi-select filter with Select All.
 *
 * **Empty means All.** The alternative — holding every id when "All" is chosen —
 * looks equivalent and is not: the set would go stale the moment the upstream
 * scope changed, and "all of yesterday's campuses" is not the same filter as
 * "no campus restriction". Keeping the empty array as the All state means a
 * cascade change cannot leave a wrong selection behind, and the request simply
 * omits the parameter.
 *
 * The three rules follow from that:
 *
 * - choosing All clears the individual selections;
 * - choosing an item while All is active leaves All and selects just that item;
 * - clearing the last item returns to All.
 *
 * Built on the menu primitive rather than a bare `<div>`: it arrives with roving
 * focus, type-ahead, Escape-to-close and the right ARIA roles, so the control is
 * usable from the keyboard instead of mouse-only.
 */
export function MultiSelectFilter({
  id,
  value,
  onChange,
  options,
  allLabel,
  noun,
  requires,
  loading = false,
  emptyMessage = 'No approved values are available for this selection.',
}: MultiSelectFilterProps) {
  const isDisabled = Boolean(requires) || loading;
  const selected = React.useMemo(() => new Set(value), [value]);

  // A selection that is no longer offered must not linger in the summary; the
  // parent prunes state, and this keeps the display honest in the meantime.
  const visible = React.useMemo(
    () => options.filter((option) => selected.has(option.value)),
    [options, selected],
  );

  const summary = React.useMemo(() => {
    if (loading) return 'Loading…';
    if (visible.length === 0) return `${allLabel} (${options.length})`;
    if (visible.length <= 2) return visible.map((option) => option.label).join(' + ');
    return `${visible.length} ${noun}s selected`;
  }, [loading, visible, allLabel, options.length, noun]);

  function toggle(optionValue: string) {
    const next = new Set(selected);
    if (next.has(optionValue)) {
      next.delete(optionValue);
    } else {
      next.add(optionValue);
    }
    // Selecting every option is the same filter as no restriction, so it
    // collapses back to All rather than sending a list of every id.
    onChange(next.size === options.length ? [] : Array.from(next));
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          disabled={isDisabled}
          aria-label={requires ? `${allLabel} — select ${requires} first` : allLabel}
          className={cn(
            'h-9 w-full justify-between gap-2 font-normal',
            visible.length === 0 && 'text-muted-foreground',
          )}
        >
          <span className="truncate">{requires ? `Select ${requires} first` : summary}</span>
          <ChevronDown aria-hidden="true" className="size-4 shrink-0 opacity-60" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" className="max-h-80 w-64 overflow-y-auto">
        {options.length === 0 ? (
          <p className="px-2 py-3 text-[13px] text-muted-foreground">{emptyMessage}</p>
        ) : (
          <>
            <DropdownMenuItem
              onSelect={(event) => {
                event.preventDefault();
                onChange([]);
              }}
              className="gap-2"
            >
              <Check
                aria-hidden="true"
                className={cn('size-4', visible.length > 0 && 'invisible')}
              />
              <span className="font-medium">{allLabel}</span>
              <span className="ml-auto text-[12px] text-muted-foreground">{options.length}</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {options.map((option) => (
              <DropdownMenuItem
                key={option.value}
                onSelect={(event) => {
                  // Keep the menu open: choosing several values is the point.
                  event.preventDefault();
                  toggle(option.value);
                }}
                className="gap-2"
              >
                <Check
                  aria-hidden="true"
                  className={cn('size-4', !selected.has(option.value) && 'invisible')}
                />
                <span className="truncate">{option.label}</span>
              </DropdownMenuItem>
            ))}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
