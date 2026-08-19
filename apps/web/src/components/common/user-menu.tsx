'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDown, Clock, LogOut, Settings2, ShieldQuestion, UserRound } from 'lucide-react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { RoleBadge } from './role-badge';
import { PreviewPanel } from './preview-panel';
import { PendingRuleNotice } from './states';
import { AccessRequestDialog } from '@/features/auth/access-request-dialog';
import { useAuth } from '@/features/auth/auth-context';
import { ROLE_LABELS } from '@/lib/permissions';
import { INTERFACE_NAMES } from '@/lib/interface-names';
import { INACTIVITY_TIMEOUT_MINUTES } from '@/lib/session';
import { formatDateTime } from '@/lib/format';
import { initialsOf } from '@/lib/utils';
import { env } from '@/lib/env';

/**
 * Top-right account area.
 *
 * SRS 22: the access level is shown for visibility only. A user can never
 * change their own role from here.
 */
export function UserMenu() {
  const router = useRouter();
  const { user, session, signOut, permissions } = useAuth();
  const [accountOpen, setAccountOpen] = React.useState(false);
  const [accessOpen, setAccessOpen] = React.useState(false);

  if (!user) return null;

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="flex items-center gap-2.5 rounded-lg border border-transparent px-2 py-1.5 text-left transition-colors hover:border-border hover:bg-muted/60"
            aria-label={`Account menu for ${user.displayName}`}
          >
            <span
              aria-hidden="true"
              className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-[12px] font-semibold text-primary"
            >
              {initialsOf(user.displayName)}
            </span>
            <span className="hidden min-w-0 flex-col leading-tight sm:flex">
              <span className="truncate text-[13px] font-medium text-foreground">{user.displayName}</span>
              <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                <span>{ROLE_LABELS[user.role]}</span>
              </span>
            </span>
            <ChevronDown className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          </button>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="end" className="min-w-64">
          <DropdownMenuLabel className="space-y-2 py-2.5">
            <div>
              <p className="text-[13px] font-semibold text-foreground">{user.displayName}</p>
              <p className="truncate text-[12px] font-normal text-muted-foreground">{user.organisationEmail}</p>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <RoleBadge role={user.role} />
            </div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />

          <DropdownMenuItem onSelect={() => setAccountOpen(true)}>
            <UserRound aria-hidden="true" />
            Account information
          </DropdownMenuItem>

          <DropdownMenuItem onSelect={() => setAccessOpen(true)}>
            <ShieldQuestion aria-hidden="true" />
            Your access &amp; requests
          </DropdownMenuItem>

          {/* The administration dashboard is Super Admin only. Hiding it is a
              courtesy; the route and every API endpoint refuse anyone else. */}
          {permissions.accessAdministration && (
            <DropdownMenuItem onSelect={() => router.push('/administration')}>
              <Settings2 aria-hidden="true" />
              {INTERFACE_NAMES.administration}
            </DropdownMenuItem>
          )}

          <DropdownMenuSeparator />
          <DropdownMenuItem destructive onSelect={() => void signOut()}>
            <LogOut aria-hidden="true" />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <AccessRequestDialog open={accessOpen} onOpenChange={setAccessOpen} />

      <Dialog open={accountOpen} onOpenChange={setAccountOpen}>
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>Account information</DialogTitle>
            <DialogDescription>
              Your TDMS access is set by a Super Admin. It cannot be changed from this screen.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <PreviewPanel
              groups={[
                {
                  title: 'TDMS account',
                  items: [
                    { label: 'Name', value: user.displayName },
                    { label: 'Organisation email', value: user.organisationEmail },
                    { label: 'Access level', value: <RoleBadge role={user.role} /> },
                    { label: 'Account status', value: user.accountStatus },
                    { label: 'Last sign-in', value: formatDateTime(user.lastSignInAt) },
                  ],
                },
                {
                  title: 'Current session',
                  items: [
                    { label: 'Signed in at', value: formatDateTime(session?.signedInAt) },
                    { label: 'Microsoft sign-in result', value: session?.microsoftSignInResult ?? '—' },
                    { label: 'TDMS access decision', value: session?.accessDecision ?? '—' },
                    { label: 'Correlation ID', value: session?.correlationId ?? '—' },
                    {
                      label: 'Authentication adapter',
                      value: session?.provider === 'entra' ? 'Microsoft Entra ID' : 'Development (mock) adapter',
                    },
                    { label: 'Environment', value: env.appEnvironment },
                  ],
                },
              ]}
            />
            <Alert variant="info">
              <Clock aria-hidden="true" />
              <div className="space-y-1">
                <AlertTitle>Session timeout</AlertTitle>
                <AlertDescription>
                  TDMS signs you out after {INACTIVITY_TIMEOUT_MINUTES} minutes without activity. This inactivity
                  period is approved.
                </AlertDescription>
              </div>
            </Alert>
            <PendingRuleNotice
              decisionId="OD-03"
              message="Whether a maximum session duration applies in addition to the inactivity timeout has not been approved, so TDMS does not enforce one."
            />
          </DialogBody>
        </DialogContent>
      </Dialog>
    </>
  );
}
