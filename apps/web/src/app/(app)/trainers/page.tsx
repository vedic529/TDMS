import type { Metadata } from 'next';

import { TrainerWorkArea } from '@/features/trainers/trainer-work-area';
import { INTERFACE_NAMES } from '@/lib/interface-names';

export const metadata: Metadata = {
  title: INTERFACE_NAMES.trainerData,
};

export default function TrainersPage() {
  return <TrainerWorkArea />;
}
