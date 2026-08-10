import { Shield, ShieldCheck, UserCog } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { ASSIGNMENT_LABELS, ROLE_LABELS } from '@/lib/permissions';
import type { DataEditorAssignment, TdmsRole } from '@/types/auth';
import { cn } from '@/lib/utils';

const ROLE_ICON = {
  SUPER_ADMIN: ShieldCheck,
  ADMIN: Shield,
  DATA_EDITOR: UserCog,
} as const;

const ROLE_VARIANT = {
  SUPER_ADMIN: 'primary',
  ADMIN: 'info',
  DATA_EDITOR: 'neutral',
} as const;

/**
 * Displays the signed-in access level. Visibility only - a user can never
 * change their own role by interacting with this badge.
 */
export function RoleBadge({ role, className }: { role: TdmsRole; className?: string }) {
  const Icon = ROLE_ICON[role];
  return (
    <Badge variant={ROLE_VARIANT[role]} className={cn('font-medium', className)}>
      <Icon aria-hidden="true" />
      {ROLE_LABELS[role]}
    </Badge>
  );
}

/**
 * Displays the Data Editor work assignment. SRS 3.3 / ACC-02: an assignment is
 * not a hierarchy level, so it is always shown beside the role, never instead
 * of it.
 */
export function AssignmentBadge({
  assignment,
  className,
}: {
  assignment: DataEditorAssignment | null;
  className?: string;
}) {
  if (!assignment) return null;
  return (
    <Badge variant="outline" className={cn('font-medium', className)}>
      {ASSIGNMENT_LABELS[assignment]}
    </Badge>
  );
}
