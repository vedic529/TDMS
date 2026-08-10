import { cn } from '@/lib/utils';

/** TDMS wordmark used in the top navigation and on the sign-in screen. */
export function TdmsLogo({ className, showSubtitle }: { className?: string; showSubtitle?: boolean }) {
  return (
    <span className={cn('flex items-center gap-2.5', className)}>
      <span
        aria-hidden="true"
        className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-[13px] font-bold tracking-tight text-primary-foreground shadow-sm"
      >
        TD
      </span>
      <span className="flex flex-col leading-tight">
        <span className="text-[15px] font-semibold tracking-tight text-foreground">TDMS</span>
        {showSubtitle && (
          <span className="text-[11px] text-muted-foreground">Timetable Database Management System</span>
        )}
      </span>
    </span>
  );
}

/** Microsoft logo used only on the sign-in button. */
export function MicrosoftLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 23 23" className={cn('size-4', className)} aria-hidden="true" focusable="false">
      <rect x="1" y="1" width="10" height="10" fill="#F25022" />
      <rect x="12" y="1" width="10" height="10" fill="#7FBA00" />
      <rect x="1" y="12" width="10" height="10" fill="#00A4EF" />
      <rect x="12" y="12" width="10" height="10" fill="#FFB900" />
    </svg>
  );
}
