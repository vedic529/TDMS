'use client';

import * as React from 'react';
import { Info, Lock } from 'lucide-react';

import { Label } from '@/components/ui/label';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

interface FormFieldProps {
  /** SRS field name, used verbatim. */
  label: string;
  htmlFor?: string;
  required?: boolean;
  /** True for SRS "Generated" fields. Marks the value as produced by TDMS. */
  generated?: boolean;
  /** Shown when the SRS marks a field Conditional. */
  conditional?: boolean;
  hint?: string;
  /** Explains an unresolved SRS rule, e.g. "OD-08". */
  pendingRule?: string;
  error?: string;
  className?: string;
  children: React.ReactNode;
}

/**
 * One labelled form control.
 *
 * SRS 6.3 replaces the asterisk method with an explicit Required column, so the
 * interface distinguishes required, optional and generated fields with words,
 * not with punctuation or colour alone.
 */
export function FormField({
  label,
  htmlFor,
  required,
  generated,
  conditional,
  hint,
  pendingRule,
  error,
  className,
  children,
}: FormFieldProps) {
  const describedBy = [hint || pendingRule ? `${htmlFor}-hint` : null, error ? `${htmlFor}-error` : null]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Label htmlFor={htmlFor}>{label}</Label>
        {required && <span className="text-[11px] font-medium uppercase tracking-wide text-destructive">Required</span>}
        {!required && !generated && (
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Optional</span>
        )}
        {conditional && (
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Conditional</span>
        )}
        {generated && (
          <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            <Lock className="size-3" aria-hidden="true" />
            Generated
          </span>
        )}
        {pendingRule && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                tabIndex={0}
                className="inline-flex items-center gap-1 rounded bg-warning-soft px-1.5 py-0.5 text-[11px] font-medium text-warning"
              >
                <Info className="size-3" aria-hidden="true" />
                Awaiting approval
              </span>
            </TooltipTrigger>
            <TooltipContent>{pendingRule}</TooltipContent>
          </Tooltip>
        )}
      </div>

      {React.isValidElement(children)
        ? React.cloneElement(children as React.ReactElement<Record<string, unknown>>, {
            'aria-describedby': describedBy || undefined,
            'aria-invalid': error ? true : undefined,
          })
        : children}

      {(hint || pendingRule) && !error && (
        <p id={`${htmlFor}-hint`} className="text-[12px] leading-relaxed text-muted-foreground">
          {hint ?? pendingRule}
        </p>
      )}
      {error && (
        <p id={`${htmlFor}-error`} className="text-[12px] font-medium text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

/** Groups related fields into one titled block inside a form or drawer. */
export function FormSection({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('space-y-4', className)}>
      <div className="border-b border-border pb-2">
        <h3 className="text-[13px] font-semibold uppercase tracking-wide text-foreground">{title}</h3>
        {description && <p className="mt-1 text-[12px] text-muted-foreground">{description}</p>}
      </div>
      {children}
    </section>
  );
}

export function FormGrid({ children, columns = 2 }: { children: React.ReactNode; columns?: 1 | 2 | 3 }) {
  return (
    <div
      className={cn(
        'grid gap-4',
        columns === 1 && 'grid-cols-1',
        columns === 2 && 'grid-cols-1 sm:grid-cols-2',
        columns === 3 && 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
      )}
    >
      {children}
    </div>
  );
}
