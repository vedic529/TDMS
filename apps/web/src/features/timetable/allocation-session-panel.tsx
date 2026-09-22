'use client';

import * as React from 'react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { SimpleSelect } from '@/components/common/dependent-select';
import { ReadOnlyNotice } from '@/components/common/states';
import { useAuth } from '@/features/auth/auth-context';
import { INTERFACE_NAMES } from '@/lib/interface-names';
import { formatDate } from '@/lib/format';
import { readOnlyReason } from '@/lib/permissions';
import { ReferenceApiError } from '@/services/reference-api';
import { allocationApi, type AllocationCalendarSession } from '@/services/allocation-api';

const WEEKDAYS = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY'];

export function AllocationSessionPanel({
  session,
  trainingPackage,
  onOpenChange,
  onSaved,
}: {
  session: AllocationCalendarSession | null;
  trainingPackage: string;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const { user, permissions } = useAuth();
  const canEdit = permissions.maintainTimetable;
  const [weekday, setWeekday] = React.useState('MONDAY');
  const [start, setStart] = React.useState('09:00');
  const [end, setEnd] = React.useState('17:00');
  const [classroom, setClassroom] = React.useState('');
  const [trainer, setTrainer] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!session) return;
    setWeekday(session.weekday);
    setStart(session.start_time);
    setEnd(session.end_time);
    setClassroom(session.classroom);
    setTrainer(session.trainer);
  }, [session]);

  if (!session) return null;
  const current = session;
  // A merged MSCRIS entry is one class covering several units (17 September 2026).
  const isMscris = current.stream === 'MSCRIS';
  const classDays = current.session_ids.length > 0 ? current.session_ids : [current.session_id];

  async function save() {
    setBusy(true);
    try {
      if (isMscris) {
        // MSCRIS is always Saturday, so the day is not offered; the rest applies
        // to every class day the entry covers.
        const result = await allocationApi.updateMscrisGroup(trainingPackage, {
          session_ids: classDays,
          start_time: start,
          end_time: end,
          classroom,
          trainer,
        });
        toast.success(`MSCRIS class updated for ${result.updated} class day${result.updated === 1 ? '' : 's'}.`);
        onSaved();
        onOpenChange(false);
        return;
      }
      await allocationApi.updateSession(current.session_id, trainingPackage, {
        weekday,
        start_time: start,
        end_time: end,
        classroom,
        trainer,
      });
      toast.success('Class day updated.');
      onSaved();
      onOpenChange(false);
    } catch (caught) {
      toast.error(caught instanceof ReferenceApiError ? caught.message : 'The class day could not be saved.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open onOpenChange={onOpenChange}>
      <SheetContent width="lg">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {isMscris ? (
              <>
                <Badge variant="info">MSCRIS</Badge>
                <span>{session.unit_title}</span>
              </>
            ) : (
              <>
                {session.unit_code} · {session.stream}
              </>
            )}
          </SheetTitle>
          <SheetDescription>
            {isMscris
              ? `${session.start_time}–${session.end_time} · ${session.classroom || 'No classroom'} · ${session.trainer || 'No trainer'}`
              : session.unit_title || 'Unit name not available'}
          </SheetDescription>
        </SheetHeader>
        <SheetBody className="space-y-6">
          {!canEdit && <ReadOnlyNotice message={readOnlyReason(user, INTERFACE_NAMES.timetable)} />}
          {!isMscris && (
            <PanelSection title="Class details">
              <dl className="grid gap-x-5 gap-y-4 rounded-lg border border-border bg-muted/20 p-4 text-[13px] sm:grid-cols-2">
                <Detail label="Unit">
                  <span className="font-semibold">{session.unit_code}</span>
                  <span className="block text-muted-foreground">{session.unit_title || 'Name not available'}</span>
                </Detail>
                <Detail label="Qualification and duration">
                  <span className="font-semibold">{session.qualification_code}</span>
                  <span className="block text-muted-foreground">
                    {session.duration_weeks ? `${session.duration_weeks} weeks` : 'Duration not available'}
                  </span>
                </Detail>
                <Detail label="College">{session.college || 'Not available'}</Detail>
                <Detail label="Campus">{session.campus || 'Not available'}</Detail>
                <Detail label="Training package">{trainingPackage}</Detail>
                <Detail label="Class stream">{titleCase(session.stream)}</Detail>
                <Detail label="Unit start date">{formatDate(session.unit_start_date)}</Detail>
                <Detail label="Unit end date">{formatDate(session.unit_end_date)}</Detail>
              </dl>
            </PanelSection>
          )}

          <PanelSection title="Attendance and intakes">
            <div className="rounded-lg border border-border p-4">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
                <div>
                  <p className="text-2xl font-semibold tabular text-foreground">{session.student_count}</p>
                  <p className="text-[12px] text-muted-foreground">
                    Active student{session.student_count === 1 ? '' : 's'} across {session.intakes.length}{' '}
                    matched intake{session.intakes.length === 1 ? '' : 's'}
                  </p>
                </div>
                <Badge variant={session.not_found ? 'warning' : 'success'}>
                  {session.not_found ? 'Intake not matched' : 'Intakes matched'}
                </Badge>
              </div>
              {session.intakes.length > 0 ? (
                <ul className="mt-3 space-y-1.5 text-[12px]">
                  {session.intakes.map((intake) => (
                    <li key={intake} className="rounded bg-muted/50 px-2.5 py-1.5 break-all">
                      {intake}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-[12px] text-muted-foreground">No rolling-timetable intake is linked.</p>
              )}
            </div>
          </PanelSection>

          {isMscris && (
            <p className="text-[12px] text-muted-foreground">
              One MSCRIS class. A change to its time, classroom or trainer applies to all{' '}
              {classDays.length} class day{classDays.length === 1 ? '' : 's'} below.
            </p>
          )}

          <PanelSection title="Schedule and delivery" description={canEdit ? 'These fields can be changed.' : undefined}>
            <div className="grid gap-4 sm:grid-cols-2">
              {!isMscris && (
                <LabeledControl label="Weekday" htmlFor="allocation-weekday">
                  <SimpleSelect
                    id="allocation-weekday"
                    value={weekday}
                    onChange={setWeekday}
                    disabled={!canEdit}
                    placeholder="Weekday"
                    options={WEEKDAYS.map((item) => ({ value: item, label: titleCase(item) }))}
                  />
                </LabeledControl>
              )}
              <LabeledControl label="Start time" htmlFor="allocation-start-time">
                <Input id="allocation-start-time" type="time" value={start} disabled={!canEdit} onChange={(event) => setStart(event.target.value)} />
              </LabeledControl>
              <LabeledControl label="End time" htmlFor="allocation-end-time">
                <Input id="allocation-end-time" type="time" value={end} disabled={!canEdit} onChange={(event) => setEnd(event.target.value)} />
              </LabeledControl>
              <DetailCard label="Delivery mode" value={titleCase(session.delivery_mode)} />
              <LabeledControl
                label={session.delivery_mode === 'VIRTUAL' ? 'Virtual classroom' : 'Classroom'}
                htmlFor="allocation-classroom"
              >
                <Input id="allocation-classroom" value={classroom} disabled={!canEdit} onChange={(event) => setClassroom(event.target.value)} placeholder="No classroom assigned" />
              </LabeledControl>
              <LabeledControl label="Trainer" htmlFor="allocation-trainer">
                <Input id="allocation-trainer" value={trainer} disabled={!canEdit} onChange={(event) => setTrainer(event.target.value)} placeholder="No trainer assigned" />
              </LabeledControl>
            </div>
          </PanelSection>

          <PanelSection title="Allocation status">
            <div className="flex flex-wrap gap-2 rounded-lg border border-border p-3">
              <Badge variant={session.needs_allocation ? 'warning' : 'success'}>
                {session.needs_allocation ? 'Needs classroom or trainer' : 'Allocation complete'}
              </Badge>
              <Badge variant={session.not_found ? 'warning' : 'outline'}>
                {session.not_found ? 'Rolling intake not found' : 'Rolling intake linked'}
              </Badge>
              <Badge variant="outline">{titleCase(session.stream)}</Badge>
            </div>
          </PanelSection>
          {isMscris && session.covered.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[12px] font-medium text-muted-foreground">Units covered</p>
              <div className="max-h-[50vh] overflow-auto rounded-md border border-border">
                <table className="w-full text-[12px]">
                  <thead className="sticky top-0 bg-muted text-left text-muted-foreground">
                    <tr>
                      <th className="px-2 py-1.5 font-medium">Unit</th>
                      <th className="px-2 py-1.5 font-medium">Qualification</th>
                      <th className="px-2 py-1.5 font-medium">College</th>
                      <th className="px-2 py-1.5 font-medium">Campus</th>
                      <th className="px-2 py-1.5 font-medium">Intakes</th>
                      <th className="px-2 py-1.5 text-right font-medium">Students</th>
                    </tr>
                  </thead>
                  <tbody>
                    {session.covered.map((item) => (
                      <tr key={item.session_id} className="border-t border-border align-top">
                        <td className="px-2 py-1.5">
                          <span className="font-medium">{item.unit_code}</span>
                          {item.unit_title && <span className="block text-muted-foreground">{item.unit_title}</span>}
                        </td>
                        <td className="px-2 py-1.5">{item.qualification_code}</td>
                        <td className="px-2 py-1.5">{item.college}</td>
                        <td className="px-2 py-1.5">{item.campus}</td>
                        <td className="px-2 py-1.5 text-muted-foreground">
                          {item.intakes.length > 0 ? item.intakes.join(', ') : '—'}
                        </td>
                        <td className="px-2 py-1.5 text-right tabular">{item.student_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </SheetBody>
        <SheetFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {canEdit && (
            <Button onClick={() => void save()} disabled={busy}>
              {busy ? 'Saving…' : 'Save'}
            </Button>
          )}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function titleCase(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(' ');
}

function PanelSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2.5">
      <div>
        <h3 className="text-[12px] font-semibold uppercase tracking-wide text-foreground">{title}</h3>
        {description && <p className="mt-0.5 text-[11px] text-muted-foreground">{description}</p>}
      </div>
      {children}
    </section>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-1 leading-relaxed text-foreground">{children}</dd>
    </div>
  );
}

function DetailCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-muted/20 px-3 py-2.5">
      <p className="text-[11px] font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 text-[13px] font-medium text-foreground">{value || 'Not available'}</p>
    </div>
  );
}

function LabeledControl({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="text-[11px] font-medium text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}
