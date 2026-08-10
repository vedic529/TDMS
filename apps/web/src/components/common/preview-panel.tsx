import * as React from 'react';

import { cn } from '@/lib/utils';

export interface PreviewItem {
  label: string;
  value: React.ReactNode;
  /** Marks a value TDMS generated rather than one the user typed. */
  generated?: boolean;
}

export interface PreviewGroup {
  title: string;
  items: PreviewItem[];
}

/**
 * Displays the complete proposed record before anything is written
 * (SRS 2.3 "Preview must display the proposed result ... without writing data
 * to the production database", SST-04, BULK-02, TT-12).
 */
export function PreviewPanel({ groups, className }: { groups: PreviewGroup[]; className?: string }) {
  return (
    <div className={cn('space-y-5', className)}>
      {groups.map((group) => (
        <section key={group.title}>
          <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
            {group.title}
          </h3>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-2.5 rounded-lg border border-border bg-muted/30 p-4 sm:grid-cols-2">
            {group.items.map((item) => (
              <div key={item.label} className="min-w-0">
                <dt className="text-[12px] text-muted-foreground">
                  {item.label}
                  {item.generated && <span className="ml-1.5 text-[11px] uppercase tracking-wide">generated</span>}
                </dt>
                <dd className="truncate text-[13px] font-medium text-foreground" title={typeof item.value === 'string' ? item.value : undefined}>
                  {item.value === '' || item.value === null || item.value === undefined ? '—' : item.value}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}

/** A compact record identity block used at the top of confirmation dialogs. */
export function RecordSummary({
  primary,
  secondary,
  lines,
  className,
}: {
  primary: string;
  secondary?: string;
  lines?: string[];
  className?: string;
}) {
  return (
    <div className={cn('rounded-lg border border-border bg-muted/40 px-4 py-3', className)}>
      <p className="text-sm font-semibold text-foreground">{primary}</p>
      {secondary && <p className="text-[13px] text-muted-foreground">{secondary}</p>}
      {lines && lines.length > 0 && (
        <ul className="mt-1.5 space-y-0.5">
          {lines.map((line) => (
            <li key={line} className="text-[13px] text-muted-foreground">
              {line}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
