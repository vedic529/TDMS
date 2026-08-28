'use client';

import * as React from 'react';
import { CalendarDays, Pencil, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { PreviewPanel } from '@/components/common/preview-panel';
import { StudentTimetableDialog } from './student-timetable-dialog';
import { formatDate } from '@/lib/format';
import type { StudentRecord } from '@/services/students-api';

/**
 * One student record, shown in a side panel.
 *
 * Selecting a row opens this rather than filling a section of the page, so the
 * list stays where it is and the reader keeps their place.
 */
export function StudentDetailPanel({
  student,
  open,
  onOpenChange,
  canMaintain,
  onEdit,
  onDelete,
}: {
  student: StudentRecord | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canMaintain: boolean;
  onEdit: (student: StudentRecord) => void;
  onDelete: (student: StudentRecord) => void;
}) {
  const [timetableOpen, setTimetableOpen] = React.useState(false);

  if (!student) return null;

  const name = `${student.first_name} ${student.last_name ?? ''}`.trim();

  // A Credit Transfer student has no intake by the approved rule; a
  // qualification with no rolling timetable has none *yet*. Different facts,
  // shown differently.
  const intake =
    student.intake_match_status === 'NOT_APPLICABLE'
      ? 'N/A — Credit Transfer'
      : student.intake_label ?? 'TBD — no rolling timetable for this qualification and duration';

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex flex-wrap items-center gap-2">
            {student.student_id}
            <Badge variant={student.status === 'ACTIVE' ? 'success' : 'neutral'}>
              {student.status.replace(/_/g, ' ')}
            </Badge>
            {student.ct_student && <Badge variant="info">Credit Transfer</Badge>}
          </SheetTitle>
          <SheetDescription>
            {name} · {student.qualification_code} — {student.qualification_title}
          </SheetDescription>
        </SheetHeader>

        <SheetBody>
          <PreviewPanel
            groups={[
              {
                title: 'Identification',
                items: [
                  { label: 'Student ID', value: student.student_id },
                  { label: 'First Name', value: student.first_name },
                  { label: 'Last Name', value: student.last_name ?? '—' },
                  { label: 'College Email', value: student.college_email, generated: true },
                  { label: 'Personal Email', value: student.personal_email ?? '—' },
                  { label: 'Primary Phone', value: student.primary_phone ?? '—' },
                ],
              },
              {
                title: 'College and course',
                items: [
                  { label: 'College', value: student.college },
                  { label: 'Campus', value: student.campus },
                  { label: 'State', value: student.state ?? '—', generated: true },
                  { label: 'Qualification Code', value: student.qualification_code },
                  { label: 'Qualification Title', value: student.qualification_title },
                  { label: 'CoE / Non-CoE', value: student.coe_status === 'COE' ? 'CoE' : 'Non-CoE' },
                  { label: 'CT Student', value: student.ct_student ? 'Yes' : 'No' },
                  { label: 'Status', value: student.status.replace(/_/g, ' ') },
                ],
              },
              {
                title: 'Intake and group',
                items: [
                  { label: 'Intake', value: intake, generated: true },
                  { label: 'Group', value: student.group_code ?? '—', generated: true },
                ],
              },
              {
                title: 'Dates and duration',
                items: [
                  { label: 'Proposed Start Date', value: formatDate(student.proposed_start_date) },
                  { label: 'Proposed End Date', value: formatDate(student.proposed_end_date) },
                  {
                    label: 'Actual Course Duration',
                    value: `${student.actual_course_duration_weeks} weeks`,
                    generated: true,
                  },
                  {
                    label: 'Course Duration Option',
                    value: student.course_duration_option_weeks
                      ? `${student.course_duration_option_weeks} weeks`
                      : '—',
                  },
                ],
              },
              {
                title: 'Other',
                items: [{ label: 'Remarks', value: student.remarks ?? '—' }],
              },
            ]}
          />
        </SheetBody>

        <SheetFooter>
          {/* Reading a timetable is not maintenance, so this sits outside the
              canMaintain branch and is available to a Viewer. */}
          <Button variant="outline" onClick={() => setTimetableOpen(true)}>
            <CalendarDays aria-hidden="true" />
            Show Timetable
          </Button>
          {canMaintain ? (
            <>
              <Button variant="outline" onClick={() => onDelete(student)}>
                <Trash2 aria-hidden="true" />
                Delete
              </Button>
              <Button onClick={() => onEdit(student)}>
                <Pencil aria-hidden="true" />
                Edit record
              </Button>
            </>
          ) : (
            <p className="text-[13px] text-muted-foreground">
              You may view and download student records. Maintaining them requires Data Editor access or above.
            </p>
          )}
        </SheetFooter>
      </SheetContent>

      <StudentTimetableDialog
        student={student}
        open={timetableOpen}
        onOpenChange={setTimetableOpen}
      />
    </Sheet>
  );
}
