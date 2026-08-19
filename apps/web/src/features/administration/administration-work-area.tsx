'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  Gauge,
  ListChecks,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  Users,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { PageHeader } from '@/components/common/page-header';
import { FilterField } from '@/components/common/filter-bar';
import { SimpleSelect } from '@/components/common/dependent-select';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState, ErrorState } from '@/components/common/states';
import { AccountStatusBadge } from '@/components/common/status-badge';
import { RoleBadge } from '@/components/common/role-badge';
import { ExportMenu } from '@/components/common/export-menu';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient } from '@/services';
import { INTERFACE_NAMES, SRS_PAGE_REFERENCE } from '@/lib/interface-names';
import { ROLE_LABELS, ROLE_OPTIONS, canManageTargetUser } from '@/lib/permissions';
import { OPEN_DECISIONS, OPEN_DECISION_STATUS_LABEL } from '@/lib/open-decisions';
import { reasonLabel } from '@/lib/reasons';
import { formatDateTime, today } from '@/lib/format';
import type { ActivityFilters, UserActivityRecord } from '@/types/activity';
import type {
  AccessRequest,
  AccountStatus,
  DashboardOverview,
  TdmsRole,
  TdmsUser,
} from '@/types/auth';

type TabValue = 'overview' | 'requests' | 'users' | 'activity' | 'open-decisions';

const TAB_VALUES: TabValue[] = ['overview', 'requests', 'users', 'activity', 'open-decisions'];

/**
 * Super Admin Dashboard.
 *
 * Reached from the account menu, never from the primary navigation: TDMS has
 * exactly four primary operational work areas (SRS 2.2), and this is not a
 * fifth one.
 *
 * Access Model v1.1 §69: only a Super Admin may open it. Typing the address
 * directly as a Viewer, Data Editor or Admin is refused here, and every
 * underlying API endpoint refuses it again — this guard is for explanation, not
 * for security.
 */
export function AdministrationWorkArea() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { permissions } = useAuth();

  const requested = searchParams.get('tab') as TabValue | null;
  const tab: TabValue = requested && TAB_VALUES.includes(requested) ? requested : 'overview';

  if (!permissions.accessAdministration) {
    return (
      <div className="space-y-5">
        <PageHeader title={INTERFACE_NAMES.administration} />
        <ErrorState
          title="You do not have access to Administration"
          description="The administration dashboard — access requests, user roles and activity records — requires Super Admin access. Return to an operational page to continue your work, or request additional access from your account menu."
        />
        <Button asChild variant="outline">
          <Link href="/timetable">
            <ArrowLeft aria-hidden="true" />
            Back to {INTERFACE_NAMES.timetable}
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title={INTERFACE_NAMES.administration}
        description="Approve access requests, manage TDMS access levels, review user activity records and track the SRS open decisions."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/timetable">
              <ArrowLeft aria-hidden="true" />
              Back to operational pages
            </Link>
          </Button>
        }
      />

      <Tabs
        value={tab}
        onValueChange={(next) => router.replace(`/administration?tab=${next}`, { scroll: false })}
      >
        <TabsList>
          <TabsTrigger value="overview">
            <Gauge aria-hidden="true" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="requests">
            <ShieldQuestion aria-hidden="true" />
            Access requests
          </TabsTrigger>
          <TabsTrigger value="users">
            <Users aria-hidden="true" />
            User &amp; role management
          </TabsTrigger>
          <TabsTrigger value="activity">
            <ClipboardList aria-hidden="true" />
            {INTERFACE_NAMES.userActivityRecords}
          </TabsTrigger>
          <TabsTrigger value="open-decisions">
            <ListChecks aria-hidden="true" />
            Open decisions
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewPanel onOpenTab={(next) => router.replace(`/administration?tab=${next}`)} />
        </TabsContent>
        <TabsContent value="requests">
          <AccessRequestsPanel />
        </TabsContent>
        <TabsContent value="users">
          <UserManagementPanel />
        </TabsContent>
        <TabsContent value="activity">
          <ActivityRecordsPanel />
        </TabsContent>
        <TabsContent value="open-decisions">
          <OpenDecisionsPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ------------------------------------------------------------------- overview

function OverviewPanel({ onOpenTab }: { onOpenTab: (tab: TabValue) => void }) {
  const [overview, setOverview] = React.useState<DashboardOverview | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await getTdmsClient().getDashboardOverview();
        if (!cancelled) setOverview(result);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Counts come from the service layer, never recomputed in the component:
  // two places counting the same thing eventually disagree.
  const tiles = overview
    ? [
        { label: 'Pending access requests', value: overview.pendingAccessRequests, tab: 'requests' as const, highlight: overview.pendingAccessRequests > 0 },
        { label: 'Active users', value: overview.activeUsers, tab: 'users' as const },
        { label: 'Viewer', value: overview.viewerCount, tab: 'users' as const },
        { label: 'Data Editor', value: overview.dataEditorCount, tab: 'users' as const },
        { label: 'Admin', value: overview.adminCount, tab: 'users' as const },
        { label: 'Super Admin', value: overview.superAdminCount, tab: 'users' as const },
        { label: 'Inactive or disabled', value: overview.inactiveOrDisabledUsers, tab: 'users' as const },
      ]
    : [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Overview</CardTitle>
          <CardDescription>
            TDMS access at a glance. Every authenticated user from an approved organisation starts as
            a Viewer; anything higher is granted by approving a request or by a direct role change.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-[13px] text-muted-foreground">Loading dashboard…</p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {tiles.map((tile) => (
                <button
                  key={tile.label}
                  type="button"
                  onClick={() => onOpenTab(tile.tab)}
                  className={`rounded-lg border p-4 text-left transition-colors hover:bg-muted/60 ${
                    tile.highlight ? 'border-primary/50 bg-primary-soft/40' : 'border-border'
                  }`}
                >
                  <span className="block text-2xl font-semibold tabular-nums text-foreground">
                    {tile.value}
                  </span>
                  <span className="mt-0.5 block text-[12px] text-muted-foreground">{tile.label}</span>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------ access requests

type Decision = 'approve' | 'deny';

function AccessRequestsPanel() {
  const { user: actor } = useAuth();
  const [requests, setRequests] = React.useState<AccessRequest[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [confirming, setConfirming] = React.useState<{ request: AccessRequest; decision: Decision } | null>(null);
  const [busy, setBusy] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setRequests(await getTdmsClient().listAccessRequests());
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const pending = requests.filter((request) => request.status === 'PENDING');
  const history = requests.filter((request) => request.status !== 'PENDING');

  async function decide() {
    if (!actor || !confirming) return;
    const { request, decision } = confirming;
    setBusy(true);
    try {
      const client = getTdmsClient();
      const updated =
        decision === 'approve'
          ? await client.approveAccessRequest(request.id, { actor })
          : await client.denyAccessRequest(request.id, { actor });
      setConfirming(null);
      await load();
      toast.success(
        decision === 'approve'
          ? `${request.requesterEmail} now has ${ROLE_LABELS[updated.requestedRole]} access`
          : `Request denied. ${request.requesterEmail} keeps ${ROLE_LABELS[request.roleAtRequest]} access.`,
      );
    } catch (error) {
      // "Already decided" arrives here when another Super Admin got there
      // first. Reloading shows the decision that actually stands.
      await load();
      toast.error('Decision not applied', {
        description: error instanceof Error ? error.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  const columns: DataTableColumn<AccessRequest>[] = [
    {
      id: 'user',
      header: 'User',
      cell: (row) => (
        <span className="block">
          <span className="block font-medium text-foreground">{row.requesterDisplayName ?? '—'}</span>
          <span className="block text-[12px] text-muted-foreground">{row.requesterEmail ?? '—'}</span>
        </span>
      ),
      sortValue: (row) => row.requesterDisplayName ?? '',
    },
    {
      id: 'current',
      header: 'Current role',
      cell: (row) => <RoleBadge role={row.roleAtRequest} />,
      sortValue: (row) => row.roleAtRequest,
    },
    {
      id: 'requested',
      header: 'Requested role',
      cell: (row) => <RoleBadge role={row.requestedRole} />,
      sortValue: (row) => row.requestedRole,
    },
    {
      id: 'requestedAt',
      header: 'Requested',
      cell: (row) => formatDateTime(row.requestedAt),
      sortValue: (row) => row.requestedAt,
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => <AccessRequestStatusBadge status={row.status} />,
      sortValue: (row) => row.status,
    },
  ];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Pending requests</CardTitle>
          <CardDescription>
            Approving a request changes the user&apos;s access level immediately. The first decision
            closes the request — if another Super Admin has already decided it, your action is
            refused rather than overwriting theirs.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DataTable
            ariaLabel="Pending access requests"
            columns={columns.filter((column) => column.id !== 'status')}
            rows={pending}
            rowKey={(row) => row.id}
            loading={loading}
            loadingLabel="Loading access requests…"
            initialSort={{ columnId: 'requestedAt', direction: 'asc' }}
            empty={<EmptyState title="No pending access request" icon={CheckCircle2} />}
            rowActions={(row) => {
              // Nobody decides their own request. The API refuses it too.
              const ownRequest = row.requesterUserId === actor?.id;
              return (
                <span className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={ownRequest}
                    title={ownRequest ? 'You cannot decide your own access request.' : undefined}
                    onClick={() => setConfirming({ request: row, decision: 'approve' })}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={ownRequest}
                    title={ownRequest ? 'You cannot decide your own access request.' : undefined}
                    onClick={() => setConfirming({ request: row, decision: 'deny' })}
                  >
                    Deny
                  </Button>
                </span>
              );
            }}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Request history</CardTitle>
          <CardDescription>
            Decided and cancelled requests are kept, never deleted, so the access record stays
            complete.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DataTable
            ariaLabel="Access request history"
            columns={columns}
            rows={history}
            rowKey={(row) => row.id}
            loading={loading}
            loadingLabel="Loading request history…"
            initialSort={{ columnId: 'requestedAt', direction: 'desc' }}
            empty={<EmptyState title="No decided access request yet" icon={ClipboardList} />}
          />
        </CardContent>
      </Card>

      {/* Confirmation, never straight from the table button. */}
      <Dialog open={confirming !== null} onOpenChange={(open) => !open && setConfirming(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {confirming?.decision === 'approve' ? 'Approve access request?' : 'Deny access request?'}
            </DialogTitle>
            <DialogDescription>
              {confirming?.decision === 'approve'
                ? "This changes the user's TDMS access immediately."
                : "The user's current access will not change."}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3 text-[13px]">
            {confirming && (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
                <dt className="text-muted-foreground">User</dt>
                <dd className="text-foreground">{confirming.request.requesterDisplayName ?? '—'}</dd>
                <dt className="text-muted-foreground">Email</dt>
                <dd className="text-foreground">{confirming.request.requesterEmail ?? '—'}</dd>
                <dt className="text-muted-foreground">Current access</dt>
                <dd className="text-foreground">{ROLE_LABELS[confirming.request.roleAtRequest]}</dd>
                <dt className="text-muted-foreground">Requested access</dt>
                <dd className="font-medium text-foreground">
                  {ROLE_LABELS[confirming.request.requestedRole]}
                </dd>
              </dl>
            )}
            <p className="text-muted-foreground">
              {confirming?.decision === 'approve'
                ? `This will change the user's TDMS access to ${
                    confirming ? ROLE_LABELS[confirming.request.requestedRole] : ''
                  }.`
                : `The user's current access will remain ${
                    confirming ? ROLE_LABELS[confirming.request.roleAtRequest] : ''
                  }.`}
            </p>
          </DialogBody>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setConfirming(null)} disabled={busy}>
              Cancel
            </Button>
            <Button
              variant={confirming?.decision === 'deny' ? 'destructive' : 'default'}
              onClick={() => void decide()}
              disabled={busy}
            >
              {confirming?.decision === 'approve' ? 'Approve request' : 'Deny request'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AccessRequestStatusBadge({ status }: { status: AccessRequest['status'] }) {
  const variant =
    status === 'APPROVED'
      ? 'success'
      : status === 'DENIED'
        ? 'destructive'
        : status === 'CANCELLED'
          ? 'neutral'
          : 'info';
  const label =
    status === 'APPROVED'
      ? 'Approved'
      : status === 'DENIED'
        ? 'Denied'
        : status === 'CANCELLED'
          ? 'Cancelled'
          : 'Pending';
  return <Badge variant={variant}>{label}</Badge>;
}

// -------------------------------------------------------------- user management

function UserManagementPanel() {
  const { user: actor, refreshSession } = useAuth();
  const [users, setUsers] = React.useState<TdmsUser[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [search, setSearch] = React.useState('');
  const [roleFilter, setRoleFilter] = React.useState('');
  const [statusFilter, setStatusFilter] = React.useState('');
  const [changing, setChanging] = React.useState<TdmsUser | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setUsers(await getTdmsClient().listUsers());
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const activeSuperAdminCount = users.filter(
    (user) => user.role === 'SUPER_ADMIN' && user.accountStatus === 'ACTIVE',
  ).length;

  const rows = users.filter((user) => {
    if (roleFilter && user.role !== roleFilter) return false;
    if (statusFilter && user.accountStatus !== statusFilter) return false;
    if (search) {
      const needle = search.trim().toLowerCase();
      if (
        !user.displayName.toLowerCase().includes(needle) &&
        !user.organisationEmail.toLowerCase().includes(needle)
      ) {
        return false;
      }
    }
    return true;
  });

  const columns: DataTableColumn<TdmsUser>[] = [
    {
      id: 'name',
      header: 'Name',
      cell: (row) => (
        <span className="block">
          <span className="block font-medium text-foreground">{row.displayName}</span>
          <span className="block text-[12px] text-muted-foreground">{row.organisationEmail}</span>
        </span>
      ),
      sortValue: (row) => row.displayName,
    },
    {
      id: 'role',
      header: 'Access level',
      cell: (row) => <RoleBadge role={row.role} />,
      sortValue: (row) => row.role,
    },
    {
      id: 'status',
      header: 'Account status',
      cell: (row) => <AccountStatusBadge status={row.accountStatus} />,
      sortValue: (row) => row.accountStatus,
    },
    {
      id: 'identity',
      header: 'Microsoft identity',
      cell: (row) =>
        row.identityLinked ? (
          <span className="inline-flex items-center gap-1 text-[12px] text-muted-foreground">
            <ShieldCheck className="size-3.5" aria-hidden="true" />
            Linked
          </span>
        ) : (
          <span className="text-[12px] text-muted-foreground">Awaiting first sign-in</span>
        ),
      sortValue: (row) => (row.identityLinked ? '1' : '0'),
    },
    {
      id: 'lastSignIn',
      header: 'Last sign-in',
      cell: (row) => formatDateTime(row.lastSignInAt),
      sortValue: (row) => row.lastSignInAt ?? '',
    },
  ];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>TDMS users and access levels</CardTitle>
            <CardDescription>
              A change takes effect no later than the user&apos;s next sign-in or approved session
              refresh (ACC-07). You cannot change your own access level, and TDMS will not let the
              last active Super Admin be removed.
            </CardDescription>
          </div>
          <ExportMenu
            rows={rows}
            baseFileName={`tdms-users-${today()}`}
            pageReference={SRS_PAGE_REFERENCE.administration}
            columns={[
              { header: 'Name', value: (row) => row.displayName },
              { header: 'Organisation email', value: (row) => row.organisationEmail },
              { header: 'Access level', value: (row) => ROLE_LABELS[row.role] },
              { header: 'Account status', value: (row) => row.accountStatus },
              { header: 'Microsoft identity', value: (row) => (row.identityLinked ? 'Linked' : 'Not linked') },
              { header: 'Last sign-in', value: (row) => row.lastSignInAt ?? '' },
            ]}
          />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <FilterField label="Search" htmlFor="user-search">
              <Input
                id="user-search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Name or organisation email"
              />
            </FilterField>
            <FilterField label="Access level" htmlFor="user-role-filter">
              <SimpleSelect
                id="user-role-filter"
                value={roleFilter}
                onChange={setRoleFilter}
                placeholder="All access levels"
                options={ROLE_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
              />
            </FilterField>
            <FilterField label="Account status" htmlFor="user-status-filter">
              <SimpleSelect
                id="user-status-filter"
                value={statusFilter}
                onChange={setStatusFilter}
                placeholder="All statuses"
                options={[
                  { value: 'ACTIVE', label: 'Active' },
                  { value: 'INACTIVE', label: 'Inactive' },
                  { value: 'DISABLED', label: 'Disabled' },
                ]}
              />
            </FilterField>
          </div>

          <DataTable
            ariaLabel="TDMS users"
            columns={columns}
            rows={rows}
            rowKey={(row) => row.id}
            loading={loading}
            loadingLabel="Loading TDMS users…"
            initialSort={{ columnId: 'name', direction: 'asc' }}
            empty={<EmptyState title="No TDMS user account matches these filters" icon={Users} />}
            rowActions={(row) => {
              const decision = canManageTargetUser(actor, row, { activeSuperAdminCount });
              return (
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!decision.allowed}
                  title={decision.allowed ? undefined : decision.reason}
                  onClick={() => setChanging(row)}
                >
                  Change role
                </Button>
              );
            }}
          />
        </CardContent>
      </Card>

      <RoleChangeDialog
        target={changing}
        activeSuperAdminCount={activeSuperAdminCount}
        onOpenChange={(open) => !open && setChanging(null)}
        onSaved={async () => {
          await load();
          await refreshSession();
        }}
      />
    </div>
  );
}

/**
 * Preview then confirm, per SRS: a role is never mutated straight from a
 * dropdown. Both current and new access are shown before anything is saved.
 */
function RoleChangeDialog({
  target,
  activeSuperAdminCount,
  onOpenChange,
  onSaved,
}: {
  target: TdmsUser | null;
  activeSuperAdminCount: number;
  onOpenChange: (open: boolean) => void;
  onSaved: () => Promise<void>;
}) {
  const { user: actor } = useAuth();
  const [role, setRole] = React.useState<TdmsRole | ''>('');
  const [status, setStatus] = React.useState<AccountStatus | ''>('');
  const [confirming, setConfirming] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    setRole('');
    setStatus('');
    setConfirming(false);
  }, [target]);

  if (!target) return null;

  const roleChanged = role !== '' && role !== target.role;
  const statusChanged = status !== '' && status !== target.accountStatus;
  const wouldRemoveLastSuperAdmin =
    target.role === 'SUPER_ADMIN' &&
    target.accountStatus === 'ACTIVE' &&
    activeSuperAdminCount <= 1 &&
    ((roleChanged && role !== 'SUPER_ADMIN') || (statusChanged && status !== 'ACTIVE'));

  async function save() {
    if (!actor || !target) return;
    setBusy(true);
    try {
      const client = getTdmsClient();
      if (roleChanged) await client.changeUserRole(target.id, role as TdmsRole, { actor });
      if (statusChanged) {
        await client.changeUserAccountStatus(target.id, status as AccountStatus, { actor });
      }
      await onSaved();
      setConfirming(false);
      onOpenChange(false);
      toast.success(`${target.organisationEmail} updated`);
    } catch (error) {
      toast.error('Change not saved', {
        description: error instanceof Error ? error.message : 'Try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Dialog open={target !== null && !confirming} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Change TDMS role</DialogTitle>
            <DialogDescription>
              {target.displayName} · {target.organisationEmail}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
              <dt className="text-muted-foreground">Current access</dt>
              <dd className="text-foreground">{ROLE_LABELS[target.role]}</dd>
              <dt className="text-muted-foreground">Current status</dt>
              <dd className="text-foreground">{target.accountStatus}</dd>
            </dl>

            <FilterField label="New access level" htmlFor="role-change-select">
              <SimpleSelect
                id="role-change-select"
                value={role}
                onChange={(next) => setRole(next as TdmsRole)}
                placeholder="Leave unchanged"
                options={ROLE_OPTIONS.filter((option) => option.value !== target.role).map(
                  (option) => ({ value: option.value, label: option.label }),
                )}
              />
            </FilterField>

            <FilterField label="Account status" htmlFor="status-change-select">
              <SimpleSelect
                id="status-change-select"
                value={status}
                onChange={(next) => setStatus(next as AccountStatus)}
                placeholder="Leave unchanged"
                options={(['ACTIVE', 'INACTIVE', 'DISABLED'] as AccountStatus[])
                  .filter((option) => option !== target.accountStatus)
                  .map((option) => ({ value: option, label: option }))}
              />
            </FilterField>

            {wouldRemoveLastSuperAdmin && (
              <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[13px] text-destructive">
                This is the last active Super Admin. Grant Super Admin to another account before
                making this change.
              </p>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => setConfirming(true)}
              disabled={(!roleChanged && !statusChanged) || wouldRemoveLastSuperAdmin}
            >
              Review change
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirming} onOpenChange={(open) => !open && setConfirming(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Change TDMS role?</DialogTitle>
            <DialogDescription>{target.displayName}</DialogDescription>
          </DialogHeader>
          <DialogBody>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
              <dt className="text-muted-foreground">User</dt>
              <dd className="text-foreground">{target.displayName}</dd>
              <dt className="text-muted-foreground">Organisation email</dt>
              <dd className="text-foreground">{target.organisationEmail}</dd>
              {roleChanged && (
                <>
                  <dt className="text-muted-foreground">Current</dt>
                  <dd className="text-foreground">{ROLE_LABELS[target.role]}</dd>
                  <dt className="text-muted-foreground">New</dt>
                  <dd className="font-medium text-foreground">{ROLE_LABELS[role as TdmsRole]}</dd>
                </>
              )}
              {statusChanged && (
                <>
                  <dt className="text-muted-foreground">Current status</dt>
                  <dd className="text-foreground">{target.accountStatus}</dd>
                  <dt className="text-muted-foreground">New status</dt>
                  <dd className="font-medium text-foreground">{status}</dd>
                </>
              )}
            </dl>
          </DialogBody>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setConfirming(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={() => void save()} disabled={busy}>
              Confirm role change
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ------------------------------------------------------- user activity records

const ACTION_OPTIONS = [
  'Sign in',
  'Sign out',
  'Create',
  'Edit',
  'Delete',
  'Restore',
  'Import',
  'Export',
  'Timetable save',
  'Override',
  'Access denied',
];

function ActivityRecordsPanel() {
  const [filters, setFilters] = React.useState<ActivityFilters>({});
  const [rows, setRows] = React.useState<UserActivityRecord[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [selected, setSelected] = React.useState<UserActivityRecord | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setRows(await getTdmsClient().listActivityRecords(filters));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const columns: DataTableColumn<UserActivityRecord>[] = [
    {
      id: 'number',
      header: 'Record number',
      cell: (row) => <span className="font-medium text-foreground">{row.activityRecordNumber}</span>,
      sortValue: (row) => row.activityRecordNumber,
    },
    {
      id: 'dateTime',
      header: 'Date and time',
      cell: (row) => <span className="whitespace-nowrap">{formatDateTime(row.dateTime)}</span>,
      sortValue: (row) => row.dateTime,
    },
    {
      id: 'user',
      header: 'User',
      cell: (row) => (
        <span className="block max-w-56 truncate" title={row.userReference}>
          {row.userReference}
        </span>
      ),
      sortValue: (row) => row.userReference,
    },
    {
      id: 'access',
      header: 'Access level',
      cell: (row) => (
        <span>{row.accessLevel === 'Unknown' ? 'Unknown' : ROLE_LABELS[row.accessLevel]}</span>
      ),
      sortValue: (row) => row.accessLevel,
    },
    {
      id: 'page',
      header: 'Page or function',
      cell: (row) => (
        <span className="block max-w-64 truncate" title={row.pageOrFunction}>
          {row.pageOrFunction}
        </span>
      ),
      sortValue: (row) => row.pageOrFunction,
    },
    { id: 'action', header: 'Action', cell: (row) => <Badge variant="neutral">{row.action}</Badge>, sortValue: (row) => row.action },
    { id: 'reference', header: 'Record or batch', cell: (row) => row.recordOrBatchReference },
    {
      id: 'result',
      header: 'Result',
      cell: (row) => (
        <Badge
          variant={
            row.result === 'Completed' || row.result === 'Access granted'
              ? 'success'
              : row.result === 'Access denied' || row.result === 'Failed because of a system error'
                ? 'destructive'
                : 'warning'
          }
        >
          {row.result}
        </Badge>
      ),
      sortValue: (row) => row.result,
    },
  ];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>{INTERFACE_NAMES.userActivityRecords}</CardTitle>
            <CardDescription>
              Only Super Admin and Admin users may view these records. They cannot be changed or deleted from TDMS
              (LOG-04, LOG-05).
            </CardDescription>
          </div>
          <ExportMenu
            rows={rows}
            baseFileName={`tdms-user-activity-${today()}`}
            pageReference={SRS_PAGE_REFERENCE.administration}
            columns={[
              { header: 'Activity record number', value: (row) => row.activityRecordNumber },
              { header: 'Date and time', value: (row) => row.dateTime },
              { header: 'User reference', value: (row) => row.userReference },
              { header: 'Access level', value: (row) => row.accessLevel },
              { header: 'Page or function', value: (row) => row.pageOrFunction },
              { header: 'Action', value: (row) => row.action },
              { header: 'Record or batch reference', value: (row) => row.recordOrBatchReference },
              { header: 'Reason', value: (row) => reasonLabel(row.reason) },
              { header: 'Reason detail', value: (row) => row.reasonDetail ?? '' },
              { header: 'Result', value: (row) => row.result },
              { header: 'Technical reference', value: (row) => row.technicalReference ?? '' },
              { header: 'Plain-language detail', value: (row) => row.plainLanguageDetail },
            ]}
          />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <FilterField label="Search" htmlFor="activity-search">
              <Input
                id="activity-search"
                value={filters.search ?? ''}
                onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
                placeholder="User, record reference or detail"
              />
            </FilterField>
            <FilterField label="Action" htmlFor="activity-action">
              <SimpleSelect
                id="activity-action"
                value={filters.action ?? ''}
                onChange={(value) => setFilters((current) => ({ ...current, action: value as ActivityFilters['action'] }))}
                options={ACTION_OPTIONS.map((action) => ({ value: action, label: action }))}
                placeholder="All actions"
              />
            </FilterField>
            <FilterField label="Page or function" htmlFor="activity-page">
              <SimpleSelect
                id="activity-page"
                value={filters.pageOrFunction ?? ''}
                onChange={(value) => setFilters((current) => ({ ...current, pageOrFunction: value }))}
                options={Object.values(SRS_PAGE_REFERENCE).map((page) => ({ value: page, label: page }))}
                placeholder="All pages"
              />
            </FilterField>
          </div>

          <DataTable
            ariaLabel="User activity records"
            columns={columns}
            rows={rows}
            rowKey={(row) => row.activityRecordNumber}
            loading={loading}
            loadingLabel="Loading user activity records…"
            pageSize={12}
            initialSort={{ columnId: 'dateTime', direction: 'desc' }}
            onRowClick={(row) => setSelected(row)}
            empty={
              <EmptyState
                title="No user activity record matches the selected filters."
                description="Clear a filter to see more records."
                icon={ClipboardList}
              />
            }
          />

          {selected && (
            <Card className="border-primary/30 bg-primary-soft/30">
              <CardHeader>
                <CardTitle>{selected.activityRecordNumber}</CardTitle>
                <CardDescription>{formatDateTime(selected.dateTime)}</CardDescription>
              </CardHeader>
              <CardContent className="grid grid-cols-1 gap-3 text-[13px] sm:grid-cols-2">
                <Detail label="User reference" value={selected.userReference} />
                <Detail
                  label="Access level"
                  value={selected.accessLevel === 'Unknown' ? 'Unknown' : ROLE_LABELS[selected.accessLevel]}
                />
                <Detail label="Page or function" value={selected.pageOrFunction} />
                <Detail label="Action" value={selected.action} />
                <Detail label="Record or batch reference" value={selected.recordOrBatchReference} />
                <Detail label="Reason" value={reasonLabel(selected.reason) || '—'} />
                <Detail label="Reason detail" value={selected.reasonDetail ?? '—'} />
                <Detail label="Result" value={selected.result} />
                <Detail label="Technical reference" value={selected.technicalReference ?? '—'} />
                <Detail label="Plain-language detail" value={selected.plainLanguageDetail} className="sm:col-span-2" />
              </CardContent>
            </Card>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Detail({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className={className}>
      <p className="text-[12px] text-muted-foreground">{label}</p>
      <p className="font-medium text-foreground">{value}</p>
    </div>
  );
}

// --------------------------------------------------------------- open decisions

function OpenDecisionsPanel() {
  const partiallyResolved = OPEN_DECISIONS.filter((decision) => decision.status === 'partially-resolved').length;

  return (
    <Card>
      <CardHeader>
        <CardTitle>SRS open decisions</CardTitle>
        <CardDescription>
          Matters the SRS records as unresolved. TDMS displays where each one affects the interface and never applies an
          invented rule in its place. A decision is only marked approved when every outstanding point is resolved —{' '}
          {partiallyResolved} {partiallyResolved === 1 ? 'decision is' : 'decisions are'} partially resolved.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
          {OPEN_DECISIONS.map((decision) => (
            <li key={decision.id} className="grid gap-2 px-4 py-3.5 sm:grid-cols-[7rem_1fr]">
              <div className="flex items-start">
                <Badge variant={decision.status === 'approved' ? 'success' : 'warning'}>
                  <ShieldAlert aria-hidden="true" />
                  {decision.id}
                </Badge>
              </div>
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-[13px] font-semibold text-foreground">{decision.area}</p>
                  <Badge
                    variant={
                      decision.status === 'approved'
                        ? 'success'
                        : decision.status === 'partially-resolved'
                          ? 'info'
                          : 'neutral'
                    }
                  >
                    {OPEN_DECISION_STATUS_LABEL[decision.status]}
                  </Badge>
                </div>
                <p className="text-[13px] leading-relaxed text-muted-foreground">{decision.requiredDecision}</p>

                {decision.confirmed.length > 0 && (
                  <div className="rounded-md border border-success/25 bg-success-soft px-3 py-2">
                    <p className="flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-wide text-success">
                      <CheckCircle2 className="size-3.5" aria-hidden="true" />
                      Confirmed
                    </p>
                    <ul className="mt-1 space-y-1">
                      {decision.confirmed.map((item) => (
                        <li key={item} className="text-[13px] leading-relaxed text-success">
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {decision.outstanding.length > 0 && (
                  <div className="rounded-md border border-warning/30 bg-warning-soft px-3 py-2">
                    <p className="flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-wide text-warning">
                      <ShieldAlert className="size-3.5" aria-hidden="true" />
                      Awaiting approval
                    </p>
                    <ul className="mt-1 space-y-1">
                      {decision.outstanding.map((item) => (
                        <li key={item} className="text-[13px] leading-relaxed text-warning">
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {decision.note && (
                  <p className="rounded-md border border-border bg-muted/50 px-3 py-2 text-[12px] leading-relaxed text-muted-foreground">
                    <span className="font-medium text-foreground">Note:</span> {decision.note}
                  </p>
                )}

                <p className="text-[12px] text-muted-foreground">
                  <span className="font-medium">Affects:</span> {decision.affects.join(' · ')}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
