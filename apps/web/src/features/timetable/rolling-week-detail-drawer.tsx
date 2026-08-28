'use client';

import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { PreviewPanel } from '@/components/common/preview-panel';
import { formatDate } from '@/lib/format';
import type { RollingWeek } from '@/services/rolling-timetable-api';

export function scheduleTypeLabel(type: RollingWeek['schedule_type']): string {
  if (type === 'BREAK') return 'Break';
  if (type === 'ASSESSMENT_WEEK') return 'Assessment Week';
  return 'Unit';
}

export function RollingWeekDetailDrawer({
  week,
  onOpenChange,
}: {
  week: RollingWeek | null;
  onOpenChange: (open: boolean) => void;
}) {
  if (!week) return null;

  return (
    <Sheet open onOpenChange={onOpenChange}>
      <SheetContent width="lg">
        <SheetHeader>
          <SheetTitle>Week {week.week_no}</SheetTitle>
          <SheetDescription>
            {week.intake_label} · {week.qualification_code}
          </SheetDescription>
        </SheetHeader>
        <SheetBody>
          <PreviewPanel
            groups={[
              {
                title: 'Loop',
                items: [
                  { label: 'Training package', value: week.training_package },
                  { label: 'Qualification code', value: week.qualification_code },
                  { label: 'Duration in weeks', value: week.duration_weeks },
                ],
              },
              {
                title: 'Intake',
                items: [
                  { label: 'Intake label', value: week.intake_label },
                  { label: 'Intake group', value: week.intake_group },
                  { label: 'Intake start date', value: formatDate(week.intake_start_date) },
                ],
              },
              {
                title: 'Calendar week',
                items: [
                  { label: 'Week no.', value: week.week_no },
                  { label: 'Start date', value: formatDate(week.week_start_date) },
                  { label: 'End date', value: formatDate(week.week_end_date) },
                ],
              },
              {
                title: 'Requirement',
                items: [
                  { label: 'Type', value: scheduleTypeLabel(week.schedule_type) },
                  { label: 'Value', value: week.schedule_value },
                  { label: 'Unit code', value: week.unit_code },
                  { label: 'Unit count', value: week.unit_count },
                  { label: 'Delivery span (weeks)', value: week.unit_delivery_span_weeks },
                  { label: 'Unit slot', value: week.unit_slot },
                ],
              },
            ]}
          />
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}
