import * as React from 'react';
import { AlertTriangle, CheckCircle2, Info, LockKeyhole } from 'lucide-react';

import type { ValidationIssue, ValidationResult } from '@/types/common';
import { cn } from '@/lib/utils';

const SEVERITY_STYLE = {
  blocking: {
    Icon: AlertTriangle,
    label: 'Blocking',
    container: 'border-destructive/25 bg-destructive-soft',
    text: 'text-destructive',
  },
  advisory: {
    Icon: Info,
    label: 'Advisory',
    container: 'border-info/25 bg-info-soft',
    text: 'text-info',
  },
  'pending-approval': {
    Icon: LockKeyhole,
    label: 'Awaiting approval',
    container: 'border-warning/30 bg-warning-soft',
    text: 'text-warning',
  },
} as const;

/**
 * Shows every validation outcome before a save is offered.
 *
 * A `pending-approval` entry represents a check whose rule is still an SRS open
 * decision (Section 12). TDMS displays the check and says it cannot be applied
 * yet; it never produces an invented pass or fail result.
 */
export function ValidationPanel({
  result,
  className,
  emptyMessage = 'Run the preview to see the validation result.',
}: {
  result: ValidationResult | null;
  className?: string;
  emptyMessage?: string;
}) {
  if (!result) {
    return (
      <p className={cn('rounded-lg border border-dashed border-border px-4 py-6 text-center text-[13px] text-muted-foreground', className)}>
        {emptyMessage}
      </p>
    );
  }

  const blocking = result.issues.filter((issue) => issue.severity === 'blocking');
  const others = result.issues.filter((issue) => issue.severity !== 'blocking');

  return (
    <div className={cn('space-y-3', className)} role="region" aria-label="Validation results">
      {blocking.length === 0 ? (
        <div className="flex items-start gap-3 rounded-lg border border-success/25 bg-success-soft px-4 py-3">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
          <div className="text-[13px] leading-relaxed text-success">
            <p className="font-semibold">No blocking problem was found.</p>
            <p>Save is available. Confirm the action to write the record.</p>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-3 rounded-lg border border-destructive/25 bg-destructive-soft px-4 py-3">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
          <div className="text-[13px] leading-relaxed text-destructive">
            <p className="font-semibold">
              {blocking.length} blocking {blocking.length === 1 ? 'problem' : 'problems'} must be corrected.
            </p>
            <p>Save stays unavailable until every blocking problem is resolved.</p>
          </div>
        </div>
      )}

      <ul className="space-y-2">
        {[...blocking, ...others].map((issue) => (
          <ValidationIssueRow key={issue.id} issue={issue} />
        ))}
      </ul>
    </div>
  );
}

function ValidationIssueRow({ issue }: { issue: ValidationIssue }) {
  const style = SEVERITY_STYLE[issue.severity];
  const { Icon } = style;
  return (
    <li className={cn('flex items-start gap-3 rounded-lg border px-4 py-3', style.container)}>
      <Icon className={cn('mt-0.5 size-4 shrink-0', style.text)} aria-hidden="true" />
      <div className="min-w-0 space-y-0.5">
        <p className={cn('text-[13px] font-semibold', style.text)}>
          {issue.title}
          <span className="ml-2 text-[11px] font-medium uppercase tracking-wide opacity-80">{style.label}</span>
          {issue.openDecisionId && (
            <span className="ml-2 text-[11px] font-medium uppercase tracking-wide opacity-80">
              {issue.openDecisionId}
            </span>
          )}
        </p>
        <p className="text-[13px] leading-relaxed text-foreground/80">{issue.message}</p>
        {issue.reference && <p className="text-[12px] text-muted-foreground">Reference: {issue.reference}</p>}
      </div>
    </li>
  );
}
