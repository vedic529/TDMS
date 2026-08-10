'use client';

import * as React from 'react';
import { Eye, Loader2, Save } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { FormField, FormGrid } from '@/components/common/form-field';
import { SimpleSelect } from '@/components/common/dependent-select';
import { PreviewPanel } from '@/components/common/preview-panel';
import { ValidationPanel } from '@/components/common/validation-panel';
import { ConfirmationDialog } from '@/components/common/confirmation-dialog';
import { ChangeSummaryDialog, buildChanges } from '@/components/common/change-summary-dialog';
import { PendingRuleNotice } from '@/components/common/states';
import { useAuth } from '@/features/auth/auth-context';
import { getTdmsClient } from '@/services';
import { nowIso } from '@/lib/format';
import {
  ASSIGNMENT_LABELS,
  ASSIGNMENT_OPTIONS,
  ROLE_LABELS,
  ROLE_OPTIONS,
  canManageTargetUser,
} from '@/lib/permissions';
import type { ValidationIssue, ValidationResult } from '@/types/common';
import type { AccountStatus, DataEditorAssignment, TdmsRole, TdmsUser } from '@/types/auth';
import type { UserInput } from '@/services/tdms-client';

const EMPTY: UserInput = {
  displayName: '',
  organisationEmail: '',
  role: 'DATA_EDITOR',
  assignment: null,
  accountStatus: 'ACTIVE',
  delegatedUserManagement: false,
  delegatedMappingManagement: false,
};

const STATUS_OPTIONS: Array<{ value: AccountStatus; label: string }> = [
  { value: 'ACTIVE', label: 'Active' },
  { value: 'INACTIVE', label: 'Inactive' },
  { value: 'DISABLED', label: 'Disabled' },
];

interface UserFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: TdmsUser | null;
  existingUsers: TdmsUser[];
  onSaved: () => void;
}

/**
 * TDMS user and access management.
 *
 * ACC-01 / ACC-02: the role control offers exactly the three hierarchy levels.
 * Student Data Officer and Timetable Officer appear only as Data Editor work
 * assignments, and only when Data Editor is the selected role.
 */
export function UserFormDialog({ open, onOpenChange, editing, existingUsers, onSaved }: UserFormDialogProps) {
  const { user: actor } = useAuth();
  const [input, setInput] = React.useState<UserInput>(EMPTY);
  const [step, setStep] = React.useState<'form' | 'preview'>('form');
  const [validation, setValidation] = React.useState<ValidationResult | null>(null);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setStep('form');
    setValidation(null);
    if (editing) {
      const { id: _id, lastSignInAt: _l, ...rest } = editing;
      setInput(rest);
    } else {
      setInput(EMPTY);
    }
  }, [open, editing]);

  function update<K extends keyof UserInput>(key: K, value: UserInput[K]) {
    setInput((current) => ({ ...current, [key]: value }));
    setValidation(null);
    setStep('form');
  }

  function selectRole(role: TdmsRole) {
    setInput((current) => ({
      ...current,
      role,
      // A work assignment only applies to a Data Editor.
      assignment: role === 'DATA_EDITOR' ? current.assignment : null,
      delegatedUserManagement: role === 'DATA_EDITOR' ? false : current.delegatedUserManagement,
      delegatedMappingManagement: role === 'DATA_EDITOR' ? false : current.delegatedMappingManagement,
    }));
    setValidation(null);
    setStep('form');
  }

  function runPreview() {
    const issues: ValidationIssue[] = [];

    if (!input.displayName.trim()) {
      issues.push({
        id: 'user-name',
        severity: 'blocking',
        title: 'Name is required',
        message: 'Enter the name shown for this TDMS user.',
        reference: 'Name',
      });
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(input.organisationEmail.trim())) {
      issues.push({
        id: 'user-email',
        severity: 'blocking',
        title: 'Organisation email is not valid',
        message: 'Enter the organisation Microsoft account used to sign in.',
        reference: 'Organisation email',
      });
    }
    const duplicate = existingUsers.find(
      (entry) =>
        entry.id !== editing?.id &&
        entry.organisationEmail.trim().toLowerCase() === input.organisationEmail.trim().toLowerCase(),
    );
    if (duplicate) {
      issues.push({
        id: 'user-duplicate',
        severity: 'blocking',
        title: 'This organisation email is already used',
        message: `${duplicate.displayName} already uses ${duplicate.organisationEmail}. One Microsoft account must match one internal TDMS user record (AUTH-04).`,
        reference: 'Organisation email',
      });
    }

    if (input.role === 'DATA_EDITOR' && !input.assignment) {
      issues.push({
        id: 'user-assignment',
        severity: 'advisory',
        title: 'No work assignment selected',
        message:
          'A Data Editor without a work assignment can view and download every operational page but cannot create, edit or delete any record.',
        reference: 'Assignment',
      });
    }

    if (editing) {
      const decision = canManageTargetUser(actor, editing);
      if (!decision.allowed) {
        issues.push({
          id: 'user-authority',
          severity: 'blocking',
          title: 'You cannot change this account',
          message: decision.reason ?? 'This change is outside your delegated authority.',
          openDecisionId: 'OD-05',
        });
      }
    } else if (actor?.role === 'ADMIN' && input.role !== 'DATA_EDITOR') {
      issues.push({
        id: 'user-create-authority',
        severity: 'blocking',
        title: 'You cannot create this access level',
        message:
          'An Admin may create a Data Editor account. Creating an Admin or Super Admin account remains restricted until the Admin role boundary is approved.',
        openDecisionId: 'OD-05',
      });
    }

    issues.push({
      id: 'role-change-timing',
      severity: 'pending-approval',
      title: 'When the change takes effect',
      message:
        'A role or account-status change is applied no later than the next sign-in or approved session refresh (ACC-07, AUTH-12). The approved session refresh behaviour depends on the session timeout decision.',
      openDecisionId: 'OD-03',
    });

    setValidation({
      issues,
      canSave: issues.filter((issue) => issue.severity === 'blocking').length === 0,
      checkedAt: nowIso(),
    });
    setStep('preview');
  }

  async function save() {
    if (!actor || !validation?.canSave) return;
    setBusy(true);
    try {
      const client = getTdmsClient();
      if (editing) {
        await client.updateUser(editing.id, input, { actor });
        toast.success('TDMS user updated', {
          description: `${input.displayName} now has ${ROLE_LABELS[input.role]} access. The change applies at the next sign-in.`,
        });
      } else {
        await client.createUser(input, { actor });
        toast.success('TDMS user created', {
          description: `${input.displayName} was added with ${ROLE_LABELS[input.role]} access.`,
        });
      }
      setConfirmOpen(false);
      onOpenChange(false);
      onSaved();
    } catch (error) {
      toast.error('The user account could not be saved', {
        description: error instanceof Error ? error.message : 'Try again, or contact the TDMS administrator.',
      });
    } finally {
      setBusy(false);
    }
  }

  const changes = editing
    ? buildChanges(editing as unknown as Record<string, unknown>, input as unknown as Record<string, unknown>, [
        { key: 'displayName', label: 'Name' },
        { key: 'organisationEmail', label: 'Organisation email' },
        { key: 'role', label: 'Access level', format: (value) => ROLE_LABELS[value as TdmsRole] },
        {
          key: 'assignment',
          label: 'Data Editor work assignment',
          format: (value) => (value ? ASSIGNMENT_LABELS[value as DataEditorAssignment] : 'None'),
        },
        { key: 'accountStatus', label: 'Account status' },
        {
          key: 'delegatedUserManagement',
          label: 'Delegated user management',
          format: (value) => (value ? 'Yes' : 'No'),
        },
        {
          key: 'delegatedMappingManagement',
          label: 'Delegated mapping management',
          format: (value) => (value ? 'Yes' : 'No'),
        },
      ])
    : [];

  const groups = [
    {
      title: 'TDMS user account',
      items: [
        { label: 'Name', value: input.displayName },
        { label: 'Organisation email', value: input.organisationEmail },
        { label: 'Access level', value: ROLE_LABELS[input.role] },
        {
          label: 'Data Editor work assignment',
          value: input.assignment ? ASSIGNMENT_LABELS[input.assignment] : 'Not applicable',
        },
        { label: 'Account status', value: input.accountStatus },
        { label: 'Delegated user management', value: input.delegatedUserManagement ? 'Yes' : 'No' },
        { label: 'Delegated mapping management', value: input.delegatedMappingManagement ? 'Yes' : 'No' },
      ],
    },
  ];

  return (
    <>
      <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit TDMS user' : 'Add TDMS user'}</DialogTitle>
            <DialogDescription>
              {step === 'form'
                ? 'Set the access level and, for a Data Editor, the work assignment. Preview the change before confirming.'
                : 'This is the proposed access change. It has not been applied.'}
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-5">
            {step === 'form' ? (
              <>
                <FormGrid>
                  <FormField label="Name" htmlFor="user-name" required>
                    <Input
                      id="user-name"
                      value={input.displayName}
                      onChange={(event) => update('displayName', event.target.value)}
                    />
                  </FormField>
                  <FormField
                    label="Organisation email"
                    htmlFor="user-email"
                    required
                    hint="The Microsoft account used to sign in. TDMS never stores a password."
                  >
                    <Input
                      id="user-email"
                      type="email"
                      value={input.organisationEmail}
                      onChange={(event) => update('organisationEmail', event.target.value)}
                    />
                  </FormField>
                  <FormField
                    label="Access level"
                    htmlFor="user-role"
                    required
                    hint="TDMS has exactly three hierarchy levels."
                  >
                    <SimpleSelect
                      id="user-role"
                      value={input.role}
                      onChange={(value) => selectRole(value as TdmsRole)}
                      options={ROLE_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
                      placeholder="Select access level"
                    />
                  </FormField>
                  <FormField label="Account status" htmlFor="user-status" required>
                    <SimpleSelect
                      id="user-status"
                      value={input.accountStatus}
                      onChange={(value) => update('accountStatus', value as AccountStatus)}
                      options={STATUS_OPTIONS}
                      placeholder="Select status"
                    />
                  </FormField>
                </FormGrid>

                {input.role === 'DATA_EDITOR' && (
                  <FormField
                    label="Assignment"
                    htmlFor="user-assignment"
                    hint="A work assignment decides where the Data Editor may create, edit and delete. It is not a hierarchy level."
                  >
                    <SimpleSelect
                      id="user-assignment"
                      value={input.assignment ?? ''}
                      onChange={(value) => update('assignment', (value || null) as DataEditorAssignment | null)}
                      options={ASSIGNMENT_OPTIONS.map((option) => ({
                        value: option.value,
                        label: `${option.label} — ${option.description}`,
                      }))}
                      placeholder="Select work assignment"
                    />
                  </FormField>
                )}

                {input.role !== 'DATA_EDITOR' && (
                  <div className="space-y-3 rounded-lg border border-border bg-muted/40 p-4">
                    <PendingRuleNotice
                      decisionId="OD-05"
                      message="Whether an Admin may create or change other Admin accounts is an open decision. Until it is approved, these delegation flags control what an Admin may do."
                    />
                    <div className="flex items-center gap-3">
                      <Switch
                        id="user-delegated-users"
                        checked={input.delegatedUserManagement}
                        onCheckedChange={(checked) => update('delegatedUserManagement', checked)}
                        disabled={actor?.role !== 'SUPER_ADMIN'}
                      />
                      <Label htmlFor="user-delegated-users">
                        Delegated user management (may change another Admin account)
                      </Label>
                    </div>
                    <div className="flex items-center gap-3">
                      <Switch
                        id="user-delegated-mappings"
                        checked={input.delegatedMappingManagement}
                        onCheckedChange={(checked) => update('delegatedMappingManagement', checked)}
                        disabled={actor?.role !== 'SUPER_ADMIN'}
                      />
                      <Label htmlFor="user-delegated-mappings">
                        Delegated mapping management (college, campus and qualification mappings)
                      </Label>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="space-y-5">
                <PreviewPanel groups={groups} />
                <div>
                  <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
                    Validation results
                  </h3>
                  <ValidationPanel result={validation} />
                </div>
              </div>
            )}
          </DialogBody>

          <DialogFooter>
            {step === 'preview' && (
              <Button variant="ghost" onClick={() => setStep('form')} disabled={busy}>
                Back to form
              </Button>
            )}
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
            {step === 'form' ? (
              <Button onClick={runPreview}>
                <Eye aria-hidden="true" />
                Preview
              </Button>
            ) : (
              <Button onClick={() => setConfirmOpen(true)} disabled={!validation?.canSave || busy}>
                {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
                {editing ? 'Confirm Update' : 'Confirm Add'}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {editing ? (
        <ChangeSummaryDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Apply access change?"
          description="Check the account and the fields that will change, then confirm."
          record={{
            primary: editing.displayName,
            secondary: editing.organisationEmail,
            lines: [`Current access level: ${ROLE_LABELS[editing.role]}`],
          }}
          changes={changes}
          busy={busy}
          onConfirm={save}
          confirmLabel="Confirm and Apply"
        />
      ) : (
        <ConfirmationDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Add TDMS user?"
          description="Please confirm that you want to create this TDMS user account."
          confirmLabel="Confirm and Add"
          busy={busy}
          onConfirm={save}
          size="lg"
        >
          <PreviewPanel groups={groups} />
        </ConfirmationDialog>
      )}
    </>
  );
}
