import type { Metadata } from 'next';

import { TimetableWorkArea } from '@/features/timetable/timetable-work-area';
import { INTERFACE_NAMES } from '@/lib/interface-names';

export const metadata: Metadata = {
  title: INTERFACE_NAMES.timetable,
};

export default function TimetablePage() {
  return <TimetableWorkArea />;
}
