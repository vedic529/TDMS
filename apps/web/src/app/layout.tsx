import type { Metadata, Viewport } from 'next';
import { Toaster } from 'sonner';

import { TooltipProvider } from '@/components/ui/tooltip';
import { TdmsAuthProvider } from '@/features/auth/auth-context';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'TDMS — Timetable Database Management System',
    template: '%s · TDMS',
  },
  description:
    'Internal web application for viewing and managing timetable information and the approved student, trainer, college, course and unit data used to create reliable timetables.',
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-AU">
      <body>
        <TdmsAuthProvider>
          <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
        </TdmsAuthProvider>
        <Toaster
          position="bottom-center"
          richColors
          closeButton
          toastOptions={{ classNames: { toast: 'text-[13px]' } }}
        />
      </body>
    </html>
  );
}
