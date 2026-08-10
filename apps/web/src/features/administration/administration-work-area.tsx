'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeft, ClipboardList, ListChecks, Pencil, Plus, ShieldAlert, Users } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PageHeader } from '@/components/common/page-header';
import { FilterField } from '@/components/common/filter-bar';
import { SimpleSelect } from '@/components/common/dependent-select';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState, ErrorState } from '@/components/common/states';
import { AccountStatusBadge } from '@/components/common/status-badge';
import { AssignmentBadge, RoleBadge } from '@/components/common/role-badge';
import { ExportMenu } from '@/components/common/export-menu';
import { UserFormDialog } from './user-form-dialog';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient } from '@/services';
import { INTERFACE_NAMES, SRS_PAGE_REFERENCE } from '@/lib/interface-names';
import { ASSIGNMENT_LABELS, ROLE_LABELS, canManageTargetUser } from '@/lib/permissions';
import { OPEN_DECISIONS } from '@/lib/open-decisions';
import { reasonLabel } from '@/lib/reasons';
import { formatDateTime, today } from '@/lib/format';
import type { ActivityFilters, UserActivityRecord } from '@/types/activity';
import type { TdmsUser } from '@/types/auth';

type TabValue = 'users' | 'activity' | 'open-decisions';

/**
 * Administration.
 *
 * Reached from the account menu, never from the primary navigation: TDMS has
 * exactly four primary operational work areas (SRS 2.2).
 */
export function AdministrationWorkArea() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { permissions } = useAuth();

  const requested = searchParams.get('tab');
  const tab: TabValue =
    requested === 'activity' ? 'activity' : requested === 'open-decisions' ? 'open-decisions' : 'users';

  if (!permissions.manageUsers && !permissions.viewActivityRecords) {
    return (
      <div className="space-y-5">
        <PageHeader title={INTERFACE_NAMES.administration} />
        <ErrorState
          title="You do not have access to Administration"
          description="Managing TDMS users and viewing user activity records requires Admin or Super Admin access. Return to an operational page to continue your work."
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
        description="Manage TDMS users and access levels, review user activity records and track the SRS open decisions."
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
          {permissions.manageUsers && (
            <TabsTrigger value="users">
              <Users aria-hidden="true" />
              User management
            </TabsTrigger>
          )}
          {permissions.viewActivityRecords && (
            <TabsTrigger value="activity">
              <ClipboardList aria-hidden="true" />
              {INTERFACE_NAMES.userActivityRecords}
            </TabsTrigger>
          )}
          <TabsTrigger value="open-decisions">
            <ListChecks aria-hidden="true" />
            Open decisions
          </TabsTrigger>
        </TabsList>

        {permissions.manageUsers && (
          <TabsContent value="users">
            <UserManagementPanel />
          </TabsContent>
        )}
        {permissions.viewActivityRecords && (
          <TabsContent value="activity">
            <ActivityRecordsPanel />
          </TabsContent>
        )}
        <TabsContent value="open-decisions">
          <OpenDecisionsPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// -------------------------------------------------------------- user management

function UserManagementPanel() {
  const { user: actor } = useAuth();
  const [users, setUsers] = React.useState<TdmsUser[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [formOpen, setFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<TdmsUser | null>(null);

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
      id: 'status',
      header: 'Account status',
      cell: (row) => <AccountStatusBadge status={row.accountStatus} />,
      sortValue: (row) => row.accountStatus,
    },
    {
      id: 'role',
      header: 'Access level',
      cell: (row) => <RoleBadge role={row.role} />,
      sortValue: (row) => row.role,
    },
    {
      id: 'assignment',
      header: 'Data Editor assignment',
      cell: (row) =>
        row.assignment ? (
          <AssignmentBadge assignment={row.assignment} />
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
      sortValue: (row) => row.assignment ?? '',
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
              A change takes effect no later than the user&apos;s next sign-in or approved session refresh (ACC-07).
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <ExportMenu
              rows={users}
              baseFileName={`tdms-users-${today()}`}
              pageReference={SRS_PAGE_REFERENCE.administration}
              columns={[
                { header: 'Name', value: (row) => row.displayName },
                { header: 'Organisation email', value: (row) => row.organisationEmail },
                { header: 'Access level', value: (row) => ROLE_LABELS[row.role] },
                {
                  header: 'Data Editor assignment',
                  value: (row) => (row.assignment ? ASSIGNMENT_LABELS[row.assignment] : ''),
                },
                { header: 'Account status', value: (row) => row.accountStatus },
                { header: 'Last sign-in', value: (row) => row.lastSignInAt ?? '' },
              ]}
            />
            <Button
              size="sm"
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
            >
              <Plus aria-hidden="true" />
              Add user
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <DataTable
            ariaLabel="TDMS users"
            columns={columns}
            rows={users}
            rowKey={(row) => row.id}
            loading={loading}
            loadingLabel="Loading TDMS users…"
            initialSort={{ columnId: 'name', direction: 'asc' }}
            empty={<EmptyState title="No TDMS user account is recorded" icon={Users} />}
            rowActions={(row) => {
              const decision = canManageTargetUser(actor, row);
              return (
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!decision.allowed}
                  title={decision.allowed ? undefined : decision.reason}
                  onClick={() => {
                    setEditing(row);
                    setFormOpen(true);
                  }}
                >
                  <Pencil aria-hidden="true" />
                  Edit
                </Button>
              );
            }}
          />
        </CardContent>
      </Card>

      <UserFormDialog
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditing(null);
        }}
        editing={editing}
        existingUsers={users}
        onSaved={() => void load()}
      />
    </div>
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
        <span className="flex flex-col gap-1">
          <span>{row.accessLevel === 'Unknown' ? 'Unknown' : ROLE_LABELS[row.accessLevel]}</span>
          {row.assignment && (
            <span className="text-[11px] text-muted-foreground">{ASSIGNMENT_LABELS[row.assignment]}</span>
          )}
        </span>
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
              { header: 'Assignment', value: (row) => (row.assignment ? ASSIGNMENT_LABELS[row.assignment] : '') },
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
                  label="Access level and assignment"
                  value={`${selected.accessLevel === 'Unknown' ? 'Unknown' : ROLE_LABELS[selected.accessLevel]}${
                    selected.assignment ? ` · ${ASSIGNMENT_LABELS[selected.assignment]}` : ''
                  }`}
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
  return (
    <Card>
      <CardHeader>
        <CardTitle>SRS open decisions</CardTitle>
        <CardDescription>
          Matters the SRS records as unresolved. TDMS displays where each one affects the interface and never applies an
          invented rule in its place.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
          {OPEN_DECISIONS.map((decision) => (
            <li key={decision.id} className="grid gap-2 px-4 py-3 sm:grid-cols-[6rem_1fr]">
              <div className="flex items-start">
                <Badge variant="warning">
                  <ShieldAlert aria-hidden="true" />
                  {decision.id}
                </Badge>
              </div>
              <div className="space-y-1">
                <p className="text-[13px] font-semibold text-foreground">{decision.area}</p>
                <p className="text-[13px] leading-relaxed text-muted-foreground">{decision.requiredDecision}</p>
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
