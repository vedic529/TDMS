'use client';

import * as React from 'react';
import { FlaskConical, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { AssignmentBadge, RoleBadge } from '@/components/common/role-badge';
import { AccountStatusBadge } from '@/components/common/status-badge';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient, resetTdmsClient } from '@/services';
import {
  PROTOTYPE_STORAGE_KEYS,
  clearPrototypeStorage,
  readPrototypeValue,
  writePrototypeValue,
} from '@/services/prototype-storage';
import { env } from '@/lib/env';
import { cn } from '@/lib/utils';
import type { TdmsUser } from '@/types/auth';

/**
 * DEVELOPMENT ONLY.
 *
 * While Microsoft Entra ID and the backend are not connected, this discreet
 * panel lets the team preview how TDMS behaves for each access state. It is not
 * an authentication mechanism, it never appears in the normal interface, and it
 * is compiled out unless `NEXT_PUBLIC_APP_ENV=development` and
 * `NEXT_PUBLIC_TDMS_DEV_TOOLS=true`.
 *
 * Selecting an identity only changes which demo account the *next* sign-in
 * uses; the current session is then refreshed, exactly as AUTH-12 describes for
 * a role change taking effect at the next sign-in or session refresh.
 */
export function DevAccessPreview() {
  const { user, signIn, refreshSession } = useAuth();
  const [open, setOpen] = React.useState(false);
  const [users, setUsers] = React.useState<TdmsUser[]>([]);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    void getTdmsClient().listUsers().then(setUsers);
  }, [open]);

  if (!env.devToolsEnabled) return null;

  async function applyIdentity(target: TdmsUser) {
    setBusy(true);
    try {
      writePrototypeValue(PROTOTYPE_STORAGE_KEYS.devIdentity, target.id);
      const ok = await signIn();
      if (ok) {
        toast.success('Access preview applied', {
          description: `Signed in as ${target.displayName}. Permissions now follow this access level.`,
        });
        setOpen(false);
      } else {
        toast.error('TDMS access was denied for this account', {
          description:
            'The account status is Inactive or Disabled, so no session was created. This is the expected behaviour for AUTH-05.',
          duration: 7000,
        });
      }
    } finally {
      setBusy(false);
    }
  }

  async function resetDemoData() {
    setBusy(true);
    try {
      await getTdmsClient().resetPrototypeData();
      clearPrototypeStorage();
      resetTdmsClient();
      await refreshSession();
      toast.success('Demo data reset', { description: 'The seeded prototype dataset has been restored.' });
      setOpen(false);
      window.location.reload();
    } finally {
      setBusy(false);
    }
  }

  const selectedId = readPrototypeValue<string>(PROTOTYPE_STORAGE_KEYS.devIdentity);

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-30 gap-2 border-dashed bg-background/95 text-muted-foreground shadow-sm backdrop-blur"
        title="Development access preview (not available in staging or production)"
      >
        <FlaskConical aria-hidden="true" />
        Dev tools
      </Button>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent width="md">
          <SheetHeader>
            <SheetTitle>Development access preview</SheetTitle>
            <SheetDescription>
              A development testing aid, not a TDMS sign-in method. It never appears in staging or production.
            </SheetDescription>
          </SheetHeader>

          <SheetBody className="space-y-5">
            <Alert variant="warning">
              <FlaskConical aria-hidden="true" />
              <div className="space-y-1">
                <AlertTitle>Not a production authentication mechanism</AlertTitle>
                <AlertDescription>
                  TDMS users cannot choose their own access level. This panel exists only because Microsoft Entra ID
                  (OD-01) is not configured yet, so the team can check how each access level behaves.
                </AlertDescription>
              </div>
            </Alert>

            <div className="space-y-2">
              <p className="text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
                Preview an access state
              </p>
              <ul className="space-y-2">
                {users.map((entry) => {
                  const active = user?.id === entry.id;
                  const selected = selectedId === entry.id;
                  return (
                    <li key={entry.id}>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void applyIdentity(entry)}
                        className={cn(
                          'flex w-full items-start justify-between gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors',
                          active
                            ? 'border-primary/40 bg-primary-soft'
                            : 'border-border bg-card hover:border-primary/30 hover:bg-muted/60',
                          busy && 'opacity-60',
                        )}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-[13px] font-medium text-foreground">
                            {entry.displayName}
                          </span>
                          <span className="block truncate text-[12px] text-muted-foreground">
                            {entry.organisationEmail}
                          </span>
                          <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                            <RoleBadge role={entry.role} />
                            <AssignmentBadge assignment={entry.assignment} />
                            <AccountStatusBadge status={entry.accountStatus} />
                          </span>
                        </span>
                        <span className="shrink-0 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                          {active ? 'Signed in' : selected ? 'Selected' : ''}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className="space-y-2 rounded-lg border border-border bg-muted/40 p-4">
              <p className="text-[13px] font-medium text-foreground">Prototype data</p>
              <p className="text-[12px] text-muted-foreground">
                Demo changes are stored under the <code className="rounded bg-background px-1">tdms.prototype.v1</code>{' '}
                browser keys. Resetting restores the seeded dataset and clears the demo session.
              </p>
              <Button variant="outline" size="sm" disabled={busy} onClick={() => void resetDemoData()}>
                <RotateCcw aria-hidden="true" />
                Reset demo data
              </Button>
            </div>
          </SheetBody>

          <SheetFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Close
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </>
  );
}
