import * as React from 'react';
import { AlertCircle, Eye, Inbox, Loader2, LockKeyhole } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

/** Shown while a result set is being loaded. */
export function LoadingState({ label = 'Loading…', rows = 5 }: { label?: string; rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        {label}
      </p>
      <div className="space-y-2">
        {Array.from({ length: rows }).map((_, index) => (
          <Skeleton key={index} className="h-10 w-full" />
        ))}
      </div>
    </div>
  );
}

/** Shown when a filter combination returns nothing. Message must be plain language. */
export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action,
  className,
}: {
  title: string;
  description?: string;
  icon?: React.ElementType;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-card px-6 py-14 text-center',
        className,
      )}
    >
      <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <div className="space-y-1">
        <p className="text-sm font-medium text-foreground">{title}</p>
        {description && <p className="mx-auto max-w-md text-[13px] text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

/** Shown when an operation fails for a system reason. */
export function ErrorState({ title = 'Something went wrong', description }: { title?: string; description?: string }) {
  return (
    <Alert variant="destructive">
      <AlertCircle aria-hidden="true" />
      <div className="space-y-1">
        <AlertTitle>{title}</AlertTitle>
        {description && <AlertDescription>{description}</AlertDescription>}
      </div>
    </Alert>
  );
}

/**
 * SRS 3.4 / ACC-05: a Data Editor keeps view and download access on pages
 * outside the assigned work area. The page is never hidden; the reason for
 * read-only access is explained instead.
 */
export function ReadOnlyNotice({ message, className }: { message: string; className?: string }) {
  return (
    <Alert variant="info" className={className}>
      <Eye aria-hidden="true" />
      <div className="space-y-1">
        <AlertTitle>View and download only</AlertTitle>
        <AlertDescription>{message}</AlertDescription>
      </div>
    </Alert>
  );
}

/**
 * Shown where an SRS open decision (Section 12) prevents TDMS from applying a
 * final rule. It states what is unresolved instead of inventing a rule.
 */
export function PendingRuleNotice({
  decisionId,
  message,
  className,
}: {
  decisionId: string;
  message: string;
  className?: string;
}) {
  return (
    <Alert variant="warning" className={className}>
      <LockKeyhole aria-hidden="true" />
      <div className="space-y-1">
        <AlertTitle>Awaiting approval &middot; {decisionId}</AlertTitle>
        <AlertDescription>{message}</AlertDescription>
      </div>
    </Alert>
  );
}
