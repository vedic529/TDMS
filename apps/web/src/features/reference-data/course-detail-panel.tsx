'use client';

import * as React from 'react';
import { Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
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
import { CourseStatusBadge } from '@/components/common/status-badge';
import { ErrorState } from '@/components/common/states';
import { formatCurrency } from '@/lib/format';
import { referenceApi, ReferenceApiError, type ApiCourseDetail } from '@/services/reference-api';

/**
 * Everything the site knows about one course record (approved 21 September 2026).
 *
 * The table carries the six values that identify a record — college, campus,
 * location, VET code, qualification, duration — and this panel answers "what
 * else do we know", gathering what other work areas hold about it: the address
 * the Campus Address Dictionary keeps for this college at this campus, the
 * city, the students enrolled here and the classes the timetable holds.
 */
export function CourseDetailPanel({
  courseId,
  onOpenChange,
  onEdit,
}: {
  courseId: string | null;
  onOpenChange: (open: boolean) => void;
  onEdit?: () => void;
}) {
  const [detail, setDetail] = React.useState<ApiCourseDetail | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!courseId) return;
    setLoading(true);
    setError(null);
    setDetail(null);
    let cancelled = false;
    void referenceApi
      .getCourseDetail(Number(courseId))
      .then((row) => {
        if (!cancelled) setDetail(row);
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(caught instanceof ReferenceApiError ? caught.message : 'This record could not be loaded.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [courseId]);

  if (!courseId) return null;

  return (
    <Sheet open onOpenChange={onOpenChange}>
      <SheetContent width="lg">
        <SheetHeader>
          <SheetTitle className="flex flex-wrap items-center gap-2">
            {detail ? `${detail.college_short_name} · ${detail.campus_name}` : 'Course record'}
            {detail && <CourseStatusBadge status={detail.course_status_label} />}
          </SheetTitle>
          <SheetDescription>
            {detail
              ? `${detail.qualification_code ?? 'NA'} — ${detail.qualification_title}`
              : 'Loading the record…'}
          </SheetDescription>
        </SheetHeader>
        <SheetBody className="space-y-5">
          {loading && (
            <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Loading…
            </p>
          )}
          {error && <ErrorState title="Course record could not be loaded" description={error} />}
          {detail && (
            <>
              <Section title="Location">
                <Field label="College">{detail.college_full_name || detail.college_short_name}</Field>
                <Field label="Campus">{detail.campus_name}</Field>
                <Field label="Full address" wide>
                  {detail.address ?? 'Address not recorded'}
                  {detail.address_is_from_dictionary && (
                    <span className="ml-1 text-[11px] text-muted-foreground">(Address Dictionary)</span>
                  )}
                </Field>
                <Field label="City">{detail.city ?? 'City not recorded'}</Field>
                <Field label="State">{detail.state}</Field>
                {detail.campus_source_addresses.length > 0 && (
                  <Field label="Known as" wide>
                    <span className="flex flex-wrap gap-1">
                      {detail.campus_source_addresses.map((spelling) => (
                        <Badge key={spelling} variant="outline" className="text-[10px] font-normal">
                          {spelling}
                        </Badge>
                      ))}
                    </span>
                  </Field>
                )}
              </Section>

              <Section title="Course">
                <Field label="Course Code">{detail.course_code}</Field>
                <Field label="VET Code">{detail.qualification_code ?? 'NA'}</Field>
                <Field label="Course Name" wide>
                  {detail.qualification_title}
                </Field>
                <Field label="Course Level">{detail.course_level ?? '—'}</Field>
                <Field label="Course Sector">{detail.course_sector ?? '—'}</Field>
                <Field label="Field of Education — Broad" wide>
                  {detail.field_of_education_broad ?? '—'}
                </Field>
                <Field label="Field of Education — Narrow" wide>
                  {detail.field_of_education_narrow ?? '—'}
                </Field>
                <Field label="Duration options">
                  {detail.duration_options.length
                    ? detail.duration_options.map((weeks) => `${weeks} weeks`).join(', ')
                    : 'None approved'}
                </Field>
                <Field label="Total Course Cost">{formatCurrency(Number(detail.total_course_cost ?? 0))}</Field>
              </Section>

              <Section title="Enrolment here">
                <Field label="Active students">
                  <span className="text-[15px] font-semibold">{detail.students.total}</span>
                </Field>
                <Field label="CoE / Non-CoE">
                  {detail.students.coe} / {detail.students.non_coe}
                </Field>
                <Field label="Timetable classes">{detail.classes}</Field>
                <Field label="Approved rooms">{detail.rooms}</Field>
              </Section>

              {detail.intakes.length > 0 && (
                <Section title={`Intakes · ${detail.intakes.length}`} plain>
                  <div className="overflow-auto rounded-md border border-border">
                    <table className="w-full text-[12px]">
                      <thead className="bg-muted text-left text-muted-foreground">
                        <tr>
                          <th className="px-2 py-1.5 font-medium">Intake</th>
                          <th className="px-2 py-1.5 text-right font-medium">Students</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.intakes.map((intake) => (
                          <tr key={intake.intake_label || 'none'} className="border-t border-border">
                            <td className="px-2 py-1.5">{intake.intake_label || 'No intake (TBD)'}</td>
                            <td className="px-2 py-1.5 text-right tabular">{intake.students}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Section>
              )}
            </>
          )}
        </SheetBody>
        <SheetFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {onEdit && detail && (
            <Button
              onClick={() => {
                onOpenChange(false);
                onEdit();
              }}
            >
              Edit record
            </Button>
          )}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function Section({
  title,
  children,
  plain,
}: React.PropsWithChildren<{ title: string; plain?: boolean }>) {
  return (
    <section className="space-y-2">
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {plain ? children : <div className="grid grid-cols-2 gap-2">{children}</div>}
    </section>
  );
}

function Field({ label, children, wide }: React.PropsWithChildren<{ label: string; wide?: boolean }>) {
  return (
    <div className={`rounded-md border border-border px-3 py-2 ${wide ? 'col-span-2' : ''}`}>
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="text-[13px] text-foreground">{children}</div>
    </div>
  );
}
