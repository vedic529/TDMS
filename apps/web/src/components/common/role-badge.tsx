import { Eye, Shield, ShieldCheck, UserCog } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { ROLE_LABELS } from '@/lib/permissions';
import type { TdmsRole } from '@/types/auth';
import { cn } from '@/lib/utils';

const ROLE_ICON = {
  SUPER_ADMIN: ShieldCheck,
  ADMIN: Shield,
  DATA_EDITOR: UserCog,
  VIEWER: Eye,
} as const;

const ROLE_VARIANT = {
  SUPER_ADMIN: 'primary',
  ADMIN: 'info',
  DATA_EDITOR: 'neutral',
  VIEWER: 'outline',
} as const;

/**
 * Displays the signed-in access level. Visibility only - a user can never
 * change their own role by interacting with this badge.
 *
 * Access Model v1.1 removed the Data Editor work assignment, so there is no
 * longer a second badge beside this one.
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
