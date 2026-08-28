'use client';

import * as React from 'react';
import { toast } from 'sonner';

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

  async function save() {
    setBusy(true);
    try {
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
          <SheetTitle>
            {session.unit_code} · {session.stream}
          </SheetTitle>
          <SheetDescription>{session.qualification_code}</SheetDescription>
        </SheetHeader>
        <SheetBody className="space-y-4">
          {!canEdit && <ReadOnlyNotice message={readOnlyReason(user, INTERFACE_NAMES.timetable)} />}
          <p className="text-[13px] text-muted-foreground">
            {session.intakes.length > 0 ? session.intakes.join(', ') : 'No matching rolling-timetable intake'}
          </p>
          {session.needs_allocation && <p className="text-sm text-destructive">This class day still needs a classroom or trainer.</p>}
          <div className="grid gap-3 sm:grid-cols-2">
            <SimpleSelect
              value={weekday}
              onChange={setWeekday}
              disabled={!canEdit}
              placeholder="Weekday"
              options={WEEKDAYS.map((item) => ({ value: item, label: item.slice(0, 1) + item.slice(1).toLowerCase() }))}
            />
            <Input type="time" value={start} disabled={!canEdit} onChange={(event) => setStart(event.target.value)} />
            <Input type="time" value={end} disabled={!canEdit} onChange={(event) => setEnd(event.target.value)} />
            <Input value={classroom} disabled={!canEdit} onChange={(event) => setClassroom(event.target.value)} placeholder="Classroom" />
            <Input value={trainer} disabled={!canEdit} onChange={(event) => setTrainer(event.target.value)} placeholder="Trainer" />
          </div>
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
