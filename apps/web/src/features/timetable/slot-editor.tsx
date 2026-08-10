'use client';

import * as React from 'react';
import { Plus, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { SimpleSelect } from '@/components/common/dependent-select';
import { WEEKDAYS, type DayTimeSlot, type Weekday } from '@/types/timetable';
import { TIME_OPTIONS } from '@/mock-data';

const DAY_OPTIONS = WEEKDAYS.map((day) => ({ value: day, label: day }));
const TIME_SELECT_OPTIONS = TIME_OPTIONS.map((time) => ({ value: time, label: time }));

interface SlotEditorProps {
  id: string;
  label: string;
  slots: DayTimeSlot[];
  onChange: (slots: DayTimeSlot[]) => void;
  readOnly?: boolean;
  disabled?: boolean;
}

/**
 * Editor for an SRS "Days and Times" field. A unit can be delivered on more
 * than one day, so the value is a list of day and time slots.
 */
export function SlotEditor({ id, label, slots, onChange, readOnly, disabled }: SlotEditorProps) {
  if (readOnly) {
    return (
      <div className="rounded-md border border-input bg-muted/60 px-3 py-2 text-[13px] text-muted-foreground">
        {slots.length === 0
          ? 'No day and time has been generated.'
          : slots.map((slot) => `${slot.day} ${slot.startTime}-${slot.endTime}`).join(', ')}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {slots.length === 0 && (
        <p className="text-[12px] text-muted-foreground">No day and time added yet.</p>
      )}
      <ul className="space-y-2">
        {slots.map((slot, index) => (
          <li key={`${id}-${index}`} className="flex flex-wrap items-center gap-2">
            <div className="min-w-32 flex-1">
              <SimpleSelect
                id={`${id}-day-${index}`}
                value={slot.day}
                onChange={(value) =>
                  onChange(slots.map((entry, i) => (i === index ? { ...entry, day: value as Weekday } : entry)))
                }
                options={DAY_OPTIONS}
                placeholder="Day"
                disabled={disabled}
              />
            </div>
            <div className="w-28">
              <SimpleSelect
                id={`${id}-start-${index}`}
                value={slot.startTime}
                onChange={(value) =>
                  onChange(slots.map((entry, i) => (i === index ? { ...entry, startTime: value } : entry)))
                }
                options={TIME_SELECT_OPTIONS}
                placeholder="From"
                disabled={disabled}
              />
            </div>
            <span className="text-[13px] text-muted-foreground">to</span>
            <div className="w-28">
              <SimpleSelect
                id={`${id}-end-${index}`}
                value={slot.endTime}
                onChange={(value) =>
                  onChange(slots.map((entry, i) => (i === index ? { ...entry, endTime: value } : entry)))
                }
                options={TIME_SELECT_OPTIONS}
                placeholder="To"
                disabled={disabled}
              />
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => onChange(slots.filter((_, i) => i !== index))}
              aria-label={`Remove ${label} slot ${index + 1}`}
              disabled={disabled}
            >
              <X aria-hidden="true" />
            </Button>
          </li>
        ))}
      </ul>
      <Button
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={() => onChange([...slots, { day: 'Monday', startTime: '09:00', endTime: '13:00' }])}
      >
        <Plus aria-hidden="true" />
        Add day and time
      </Button>
    </div>
  );
}
