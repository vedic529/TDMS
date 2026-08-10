'use client';

import * as React from 'react';
import { Pencil, Trash2 } from 'lucide-react';

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
import { PreviewPanel } from '@/components/common/preview-panel';
import { useReferenceData } from '@/features/shared/reference-data-context';
import { formatDate, formatDateTime, formatSlots } from '@/lib/format';
import type { TimetableSession } from '@/types/timetable';

interface TimetableDetailDrawerProps {
  session: TimetableSession | null;
  onOpenChange: (open: boolean) => void;
  canEdit: boolean;
  onEdit: (session: TimetableSession) => void;
  onDelete: (session: TimetableSession) => void;
}

/**
 * Full record view opened from the table or calendar.
 * Wide SRS structures are shown here rather than squeezed into table columns.
 */
export function TimetableDetailDrawer({
  session,
  onOpenChange,
  canEdit,
  onEdit,
  onDelete,
}: TimetableDetailDrawerProps) {
  const { collegeById, campusById, data } = useReferenceData();

  if (!session) return null;

  const trainerName = (trainerId: string) =>
    trainerId ? (data?.trainers.find((t) => t.trainerId === trainerId)?.trainerName ?? trainerId) : '';

  const campus = campusById(session.campusId);

  return (
    <Sheet open onOpenChange={onOpenChange}>
      <SheetContent width="lg">
        <SheetHeader>
          <SheetTitle>{session.recordNumber}</SheetTitle>
          <SheetDescription>
            {session.group} · {session.qualificationCode} — {session.qualificationName}
          </SheetDescription>
        </SheetHeader>

        <SheetBody>
          <PreviewPanel
            groups={[
              {
                title: 'Timetable basic details',
                items: [
                  { label: 'College', value: collegeById(session.collegeId)?.collegeFullName ?? '' },
                  {
                    label: 'Campus Location',
                    value: campus ? `${campus.campusName} — ${campus.campusLocation}` : '',
                  },
                  { label: 'Qualification Code', value: session.qualificationCode },
                  { label: 'Qualification Name', value: session.qualificationName },
                  { label: 'Duration in Weeks', value: `${session.durationInWeeks} weeks` },
                  { label: 'Group', value: session.group },
                  { label: 'Classroom Size', value: session.classroomSize },
                ],
              },
              {
                title: 'Unit details',
                items: [
                  { label: 'UoC Code', value: session.uocCode },
                  { label: 'UoC Title', value: session.uocTitle },
                  { label: 'UoC Type', value: session.uocType },
                  { label: 'Mode of Delivery', value: session.modeOfDelivery },
                  { label: 'UoC Start Date', value: formatDate(session.uocStartDate) },
                  { label: 'UoC End Date', value: formatDate(session.uocEndDate) },
                ],
              },
              {
                title: 'Theory',
                items: [
                  { label: 'Theory Days and Times', value: formatSlots(session.theoryDaysAndTimes) },
                  { label: 'Theory Classroom Name', value: session.theoryClassroomName },
                  { label: 'Theory Classroom Capacity', value: session.theoryClassroomCapacity || '' },
                  { label: 'Theory Trainer', value: trainerName(session.theoryTrainerId) },
                ],
              },
              {
                title: 'Practical',
                items: [
                  { label: 'Practical Classroom Name', value: session.practicalClassroomName },
                  { label: 'Practical Classroom Capacity', value: session.practicalClassroomCapacity || '' },
                  { label: 'Practical Days and Times', value: formatSlots(session.practicalDaysAndTimes) },
                  { label: 'Practical Trainer', value: trainerName(session.practicalTrainerId) },
                ],
              },
              {
                title: 'MSCRIS and remarks',
                items: [
                  { label: 'MSCRIS Class Name', value: session.mscrisClassName },
                  { label: 'MSCRIS Days and Times', value: formatSlots(session.mscrisDaysAndTimes) },
                  { label: 'MSCRIS Trainer', value: trainerName(session.mscrisTrainerId) },
                  { label: 'Remarks', value: session.remarks },
                ],
              },
              {
                title: 'Record',
                items: [
                  { label: 'Timetable record number', value: session.recordNumber },
                  { label: 'Created', value: formatDateTime(session.createdAt) },
                  { label: 'Last updated', value: formatDateTime(session.updatedAt) },
                ],
              },
            ]}
          />
        </SheetBody>

        <SheetFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {canEdit && (
            <>
              <Button variant="destructive" onClick={() => onDelete(session)}>
                <Trash2 aria-hidden="true" />
                Delete
              </Button>
              <Button onClick={() => onEdit(session)}>
                <Pencil aria-hidden="true" />
                Edit
              </Button>
            </>
          )}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
