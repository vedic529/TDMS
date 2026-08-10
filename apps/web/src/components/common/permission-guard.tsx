'use client';

import * as React from 'react';

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { hasCapability, type Capability } from '@/lib/permissions';
import { useCurrentUser } from '@/features/auth/auth-context';

interface PermissionGuardProps {
  capability: Capability;
  children: React.ReactNode;
  /**
   * `hide` removes an action that is irrelevant to the user.
   * `disable` keeps it visible with an explanation, which is useful where the
   * user needs to understand that the action exists but is outside their work
   * area (SRS 3.4 / ACC-05).
   */
  behaviour?: 'hide' | 'disable';
  /** Explanation shown for the disabled behaviour. */
  reason?: string;
  fallback?: React.ReactNode;
}

/**
 * Wraps an action so that the same central permission rules apply to buttons,
 * navigation items and routes (ACC-06). A visible button never implies the
 * action is allowed: the service layer receives the acting user and the page
 * re-checks the capability before calling it.
 */
export function PermissionGuard({
  capability,
  children,
  behaviour = 'hide',
  reason,
  fallback = null,
}: PermissionGuardProps) {
  const user = useCurrentUser();
  const allowed = hasCapability(user, capability);

  if (allowed) return <>{children}</>;
  if (behaviour === 'hide') return <>{fallback}</>;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-not-allowed opacity-60" tabIndex={0} aria-disabled="true">
          <span className="pointer-events-none">{children}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent>{reason ?? 'This action is outside your assigned work area.'}</TooltipContent>
    </Tooltip>
  );
}

/** Hook form of the guard for conditional logic inside a component. */
export function useCapability(capability: Capability): boolean {
  const user = useCurrentUser();
  return hasCapability(user, capability);
}
