'use client';

import * as React from 'react';
import { CheckCircle2, Clock, Info, ShieldQuestion } from 'lucide-react';
import { toast } from 'sonner';

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { RoleBadge } from '@/components/common/role-badge';
import { useAuth } from '@/features/auth/auth-context';
import { ROLE_DESCRIPTIONS, ROLE_LABELS, requestableRolesFor } from '@/lib/permissions';
import { formatDateTime } from '@/lib/format';
import { getTdmsClient } from '@/services';
import type { AccessRequest, RequestableRole } from '@/types/auth';

/**
 * "Current access, and how to ask for more."
 *
 * Only strictly higher roles are offered - a user cannot request their current
 * role or a lower one, and a reduction is an administrative action a Super
 * Admin performs. No reason field: Access Model v1.1 states a request needs no
 * justification, and inventing one would be inventing a business rule.
 */
export function AccessRequestDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { user, refreshSession } = useAuth();
  const [pending, setPending] = React.useState<AccessRequest | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [confirming, setConfirming] = React.useState<RequestableRole | null>(null);

  const load = React.useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      setPending(await getTdmsClient().getMyAccessRequest(user.id));
    } finally {
      setLoading(false);
    }
  }, [user]);

  React.useEffect(() => {
    if (open) void load();
  }, [open, load]);

  if (!user) return null;

  const options = requestableRolesFor(user.role);

  async function submit(role: RequestableRole) {
    if (!user) return;
    setBusy(true);
    try {
      const { notification } = await getTdmsClient().submitAccessRequest(role, { actor: user });
      await load();
      setConfirming(null);
      toast.success(`${ROLE_LABELS[role]} access requested`, {
        description: notification.delivered
          ? 'The Super Admin approval group has been notified by email.'
          : 'A Super Admin will see it in the administration dashboard. ' + notification.detail,
      });
    } catch (error) {
      toast.error('Request not submitted', {
        description: error instanceof Error ? error.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!user || !pending) return;
    setBusy(true);
    try {
      await getTdmsClient().cancelAccessRequest(pending.id, { actor: user });
      await load();
      await refreshSession();
      toast.success('Access request cancelled');
    } catch (error) {
      toast.error('Request not cancelled', {
        description: error instanceof Error ? error.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Your TDMS access</DialogTitle>
          <DialogDescription>
            Ask a Super Admin for a higher access level. Your current access does not change until a
            Super Admin approves the request.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <div className="rounded-lg border border-border bg-muted/40 p-4">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Current access
            </p>
            <div className="mt-1.5 flex items-center gap-2">
              <RoleBadge role={user.role} />
            </div>
            <p className="mt-2 text-[13px] text-muted-foreground">{ROLE_DESCRIPTIONS[user.role]}</p>
          </div>

          {loading ? (
            <p className="text-[13px] text-muted-foreground">Checking for an existing request…</p>
          ) : pending ? (
            <Alert variant="info">
              <Clock aria-hidden="true" />
              <div className="space-y-1">
                <AlertTitle>Pending request: {ROLE_LABELS[pending.requestedRole]}</AlertTitle>
                <AlertDescription>
                  Submitted {formatDateTime(pending.requestedAt)}. You can have one pending request
                  at a time — cancel this one if you need to ask for a different level.
                </AlertDescription>
              </div>
            </Alert>
          ) : options.length === 0 ? (
            <Alert variant="success">
              <CheckCircle2 aria-hidden="true" />
              <div className="space-y-1">
                <AlertTitle>You already hold the highest access level</AlertTitle>
                <AlertDescription>There is no higher role to request.</AlertDescription>
              </div>
            </Alert>
          ) : (
            <div className="space-y-2">
              <p className="text-[13px] font-medium text-foreground">Request additional access</p>
              {options.map((role) => (
                <button
                  key={role}
                  type="button"
                  disabled={busy}
                  onClick={() => setConfirming(role)}
                  className="flex w-full items-start gap-3 rounded-lg border border-border p-3 text-left transition-colors hover:border-primary/50 hover:bg-primary-soft/40 disabled:opacity-60"
                >
                  <ShieldQuestion
                    className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <span className="min-w-0">
                    <span className="block text-[13px] font-medium text-foreground">
                      {ROLE_LABELS[role]}
                    </span>
                    <span className="block text-[12px] text-muted-foreground">
                      {ROLE_DESCRIPTIONS[role]}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}

          <Alert variant="info">
            <Info aria-hidden="true" />
            <div className="space-y-1">
              <AlertTitle>No reason is needed</AlertTitle>
              <AlertDescription>
                A request carries only who you are, your current access and the level you are asking
                for. Only a Super Admin can approve or deny it.
              </AlertDescription>
            </div>
          </Alert>
        </DialogBody>

        <DialogFooter>
          {pending && (
            <Button variant="outline" onClick={() => void cancel()} disabled={busy}>
              Cancel request
            </Button>
          )}
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>

      {/* Preview then confirm - never submitted straight from the list. */}
      <Dialog open={confirming !== null} onOpenChange={(next) => !next && setConfirming(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Request {confirming ? ROLE_LABELS[confirming] : ''} access?</DialogTitle>
            <DialogDescription>
              This asks a Super Admin to change your TDMS access. Nothing changes until they approve
              it.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3 text-[13px]">
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
              <dt className="text-muted-foreground">User</dt>
              <dd className="text-foreground">{user.displayName}</dd>
              <dt className="text-muted-foreground">Current access</dt>
              <dd className="text-foreground">{ROLE_LABELS[user.role]}</dd>
              <dt className="text-muted-foreground">Requested access</dt>
              <dd className="font-medium text-foreground">
                {confirming ? ROLE_LABELS[confirming] : ''}
              </dd>
            </dl>
          </DialogBody>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setConfirming(null)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={() => confirming && void submit(confirming)} disabled={busy}>
              Submit request
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
}
