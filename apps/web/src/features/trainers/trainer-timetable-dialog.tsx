'use client';

import * as React from 'react';
import {
  BookOpen,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  ExternalLink,
  Loader2,
  MapPin,
  Monitor,
  Users,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ErrorState } from '@/components/common/states';
import {
  trainersApi,
  type TrainerDetail,
  type TrainerTimetable,
  type TrainerTimetableClass,
  type TrainerTimetableStudent,
} from '@/services/trainers-api';
import { cn } from '@/lib/utils';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function moveMonth(value: string, amount: number) {
  const [year, month] = value.split('-').map(Number);
  const next = new Date(year, month - 1 + amount, 1);
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`;
}

function monthLabel(value: string) {
  const [year, month] = value.split('-').map(Number);
  return new Intl.DateTimeFormat('en-AU', { month: 'long', year: 'numeric' }).format(
    new Date(year, month - 1, 1),
  );
}

function displayDate(value: string) {
  return new Intl.DateTimeFormat('en-AU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(new Date(`${value}T00:00:00`));
}

export function TrainerTimetableDialog({
  trainer,
  open,
  onOpenChange,
}: {
  trainer: TrainerDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [month, setMonth] = React.useState(currentMonth);
  const [calendar, setCalendar] = React.useState<TrainerTimetable | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<{
    date: string;
    item: TrainerTimetableClass;
  } | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCalendar(await trainersApi.timetable(trainer.id, month));
    } catch (caught) {
      setCalendar(null);
      setError(caught instanceof Error ? caught.message : 'The timetable could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [month, trainer.id]);

  React.useEffect(() => {
    if (open) void load();
  }, [open, load]);

  React.useEffect(() => {
    if (!open) setSelected(null);
  }, [open]);

  const firstDayOffset = calendar?.days.length
    ? (new Date(`${calendar.days[0].date}T00:00:00`).getDay() + 6) % 7
    : 0;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent size="full" className="h-[calc(100vh-3rem)]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CalendarDays className="size-4" aria-hidden="true" />
              {trainer.trainer_name}&apos;s timetable
            </DialogTitle>
            <DialogDescription>
              Each unit and classroom combination appears once per day.
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="flex min-h-0 flex-col gap-4 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Previous month"
                  onClick={() => setMonth((value) => moveMonth(value, -1))}
                >
                  <ChevronLeft className="size-4" />
                </Button>
                <Button variant="outline" size="sm" onClick={() => setMonth(currentMonth())}>
                  Today
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Next month"
                  onClick={() => setMonth((value) => moveMonth(value, 1))}
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
              <h3 className="text-[16px] font-semibold">{monthLabel(month)}</h3>
              <input
                type="month"
                value={month}
                onChange={(event) => event.target.value && setMonth(event.target.value)}
                className="h-9 rounded-md border border-input bg-background px-3 text-[13px]"
                aria-label="Selected month"
              />
            </div>

            {loading ? (
              <div className="flex flex-1 items-center justify-center gap-2 text-[13px] text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading timetable…
              </div>
            ) : error ? (
              <div className="m-auto w-full max-w-lg">
                <ErrorState title="The timetable could not be loaded" description={error} />
                <Button className="mt-3" variant="outline" size="sm" onClick={() => void load()}>
                  Retry
                </Button>
              </div>
            ) : calendar ? (
              <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-border">
                <div className="grid min-w-[900px] grid-cols-7 bg-muted/60">
                  {WEEKDAYS.map((day) => (
                    <div key={day} className="border-r border-border px-2 py-2 text-[12px] font-semibold last:border-r-0">
                      {day}
                    </div>
                  ))}
                </div>
                <div className="grid min-w-[900px] grid-cols-7 auto-rows-[minmax(145px,1fr)]">
                  {Array.from({ length: firstDayOffset }).map((_, index) => (
                    <div key={`blank-${index}`} className="border-r border-t border-border bg-muted/20" />
                  ))}
                  {calendar.days.map((day, index) => {
                    const date = new Date(`${day.date}T00:00:00`);
                    const today = new Date();
                    const isToday =
                      date.getFullYear() === today.getFullYear() &&
                      date.getMonth() === today.getMonth() &&
                      date.getDate() === today.getDate();
                    return (
                      <div
                        key={day.date}
                        className={cn(
                          'min-w-0 border-r border-t border-border p-1.5',
                          (firstDayOffset + index + 1) % 7 === 0 && 'border-r-0',
                        )}
                      >
                        <div
                          className={cn(
                            'mb-1 flex size-6 items-center justify-center rounded-full text-[12px] font-medium',
                            isToday && 'bg-primary text-primary-foreground',
                          )}
                        >
                          {date.getDate()}
                        </div>
                        <div className="space-y-1">
                          {day.classes.map((item) => (
                            <button
                              type="button"
                              key={item.class_key}
                              onClick={() => setSelected({ date: day.date, item })}
                              className="w-full rounded-md border border-blue-200 bg-blue-50 px-2 py-1.5 text-left transition-colors hover:border-blue-400 hover:bg-blue-100"
                            >
                              <span className="block truncate text-[11px] font-semibold text-blue-950">
                                {item.unit_code}
                              </span>
                              <span className="block truncate text-[10px] text-blue-900">
                                {item.classroom}
                              </span>
                              <span className="mt-1 flex flex-wrap gap-1">
                                {item.delivery_modes.map((mode) => (
                                  <span key={mode} className="rounded bg-white/80 px-1 text-[9px] text-blue-900">
                                    {mode}
                                  </span>
                                ))}
                                {item.uoc_types.map((type) => (
                                  <span key={type} className="rounded bg-white/80 px-1 text-[9px] text-blue-900">
                                    {type}
                                  </span>
                                ))}
                              </span>
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </DialogBody>
        </DialogContent>
      </Dialog>

      <ClassDetailsDialog
        trainerId={trainer.id}
        selected={selected}
        open={selected !== null}
        onOpenChange={(next) => !next && setSelected(null)}
      />
    </>
  );
}

function ClassDetailsDialog({
  trainerId,
  selected,
  open,
  onOpenChange,
}: {
  trainerId: number;
  selected: { date: string; item: TrainerTimetableClass } | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [showStudents, setShowStudents] = React.useState(false);
  const [students, setStudents] = React.useState<TrainerTimetableStudent[]>([]);
  const [studentTotal, setStudentTotal] = React.useState(0);
  const [studentLoading, setStudentLoading] = React.useState(false);
  const [studentError, setStudentError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setShowStudents(false);
    setStudents([]);
    setStudentTotal(0);
    setStudentError(null);
  }, [selected?.item.class_key]);

  async function loadStudents() {
    if (!selected) return;
    setShowStudents(true);
    setStudentLoading(true);
    setStudentError(null);
    try {
      const result = await trainersApi.timetableStudents(
        trainerId,
        selected.date,
        selected.item.session_ids,
      );
      setStudents(result.items);
      setStudentTotal(result.total);
    } catch (caught) {
      setStudentError(caught instanceof Error ? caught.message : 'Students could not be loaded.');
    } finally {
      setStudentLoading(false);
    }
  }

  if (!selected) return null;
  const item = selected.item;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>{item.unit_code} · {item.unit_title}</DialogTitle>
          <DialogDescription>{displayDate(selected.date)}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-5">
          <div className="grid gap-3 rounded-lg border border-border p-4 sm:grid-cols-2">
            <Detail icon={BookOpen} label="Unit ID" value={item.unit_code} />
            <Detail icon={BookOpen} label="Unit name" value={item.unit_title} />
            <Detail icon={MapPin} label="College" value={item.colleges.join(', ')} />
            <Detail icon={MapPin} label="Campus" value={item.campuses.join(', ')} />
            <Detail icon={MapPin} label="Classroom" value={item.classroom} />
            <Detail icon={Clock3} label="Time" value={item.times.join(', ')} />
            <Detail icon={Monitor} label="Mode of delivery" value={item.delivery_modes.join(', ')} />
            <Detail icon={BookOpen} label="Unit type" value={item.uoc_types.join(', ')} />
            <Detail icon={Users} label="Co-Trainer" value={item.co_trainers.length ? item.co_trainers.join(', ') : 'No Co-Trainer'} />
            <div className="sm:col-span-2">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Moodle link</p>
              {item.moodle_link ? (
                <a className="mt-1 inline-flex items-center gap-1 text-[13px] text-primary underline" href={item.moodle_link} target="_blank" rel="noreferrer">
                  Open Moodle <ExternalLink className="size-3.5" />
                </a>
              ) : (
                <p className="mt-1 text-[13px] text-muted-foreground">Not recorded</p>
              )}
            </div>
          </div>

          {showStudents && (
            <section className="space-y-2">
              <h3 className="flex items-center gap-2 text-[13px] font-semibold">
                <Users className="size-4" /> Students attending
                {!studentLoading && <Badge variant="neutral">{studentTotal}</Badge>}
              </h3>
              {studentLoading ? (
                <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" /> Loading students…
                </p>
              ) : studentError ? (
                <p className="text-[13px] text-destructive">{studentError}</p>
              ) : students.length === 0 ? (
                <p className="rounded-md border border-dashed p-3 text-[13px] text-muted-foreground">
                  No active students are linked to this class.
                </p>
              ) : (
                <div className="max-h-60 overflow-y-auto rounded-md border border-border">
                  <table className="w-full text-left text-[12px]">
                    <thead className="sticky top-0 bg-muted">
                      <tr><th className="px-3 py-2">Student ID</th><th className="px-3 py-2">Name</th><th className="px-3 py-2">Status</th></tr>
                    </thead>
                    <tbody>
                      {students.map((student) => (
                        <tr key={student.id} className="border-t border-border">
                          <td className="px-3 py-2 font-medium">{student.student_id}</td>
                          <td className="px-3 py-2">{[student.first_name, student.last_name].filter(Boolean).join(' ')}</td>
                          <td className="px-3 py-2">{student.coe_status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          {!showStudents && (
            <Button onClick={() => void loadStudents()}>
              <Users className="size-4" /> Show attending students
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Detail({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div>
      <p className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        <Icon className="size-3.5" /> {label}
      </p>
      <p className="mt-1 text-[13px]">{value || 'Not recorded'}</p>
    </div>
  );
}
