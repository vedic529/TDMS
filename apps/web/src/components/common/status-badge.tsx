import { AlertTriangle, Ban, CheckCircle2, CircleSlash, Copy, HelpCircle, PauseCircle } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import type { StagedRowStatus } from '@/types/import';
import type { AccountStatus } from '@/types/auth';
import type { CourseStatus } from '@/types/reference';

/**
 * Status is always shown as text plus an icon, never colour alone
 * (NFR-09 / accessibility).
 */

const IMPORT_STATUS_STYLE: Record<
  StagedRowStatus,
  { variant: 'success' | 'warning' | 'destructive' | 'neutral' | 'info'; Icon: typeof CheckCircle2 }
> = {
  Ready: { variant: 'success', Icon: CheckCircle2 },
  'Needs correction': { variant: 'warning', Icon: AlertTriangle },
  Duplicate: { variant: 'destructive', Icon: Copy },
  'Unmatched reference': { variant: 'destructive', Icon: HelpCircle },
  'Excluded by user': { variant: 'neutral', Icon: CircleSlash },
};

export function ImportStatusBadge({ status }: { status: StagedRowStatus }) {
  const { variant, Icon } = IMPORT_STATUS_STYLE[status];
  return (
    <Badge variant={variant}>
      <Icon aria-hidden="true" />
      {status}
    </Badge>
  );
}

const ACCOUNT_STATUS_STYLE: Record<
  AccountStatus,
  { variant: 'success' | 'warning' | 'destructive'; Icon: typeof CheckCircle2; label: string }
> = {
  ACTIVE: { variant: 'success', Icon: CheckCircle2, label: 'Active' },
  INACTIVE: { variant: 'warning', Icon: PauseCircle, label: 'Inactive' },
  DISABLED: { variant: 'destructive', Icon: Ban, label: 'Disabled' },
};

export function AccountStatusBadge({ status }: { status: AccountStatus }) {
  const { variant, Icon, label } = ACCOUNT_STATUS_STYLE[status];
  return (
    <Badge variant={variant}>
      <Icon aria-hidden="true" />
      {label}
    </Badge>
  );
}

const COURSE_STATUS_STYLE: Record<CourseStatus, { variant: 'success' | 'neutral' | 'warning' }> = {
  Active: { variant: 'success' },
  Inactive: { variant: 'neutral' },
  Superseded: { variant: 'warning' },
};

export function CourseStatusBadge({ status }: { status: CourseStatus }) {
  return <Badge variant={COURSE_STATUS_STYLE[status].variant}>{status}</Badge>;
}

export function ActiveBadge({ isActive }: { isActive: boolean }) {
  return isActive ? (
    <Badge variant="success">
      <CheckCircle2 aria-hidden="true" />
      Active
    </Badge>
  ) : (
    <Badge variant="warning">
      <PauseCircle aria-hidden="true" />
      Inactive
    </Badge>
  );
}
