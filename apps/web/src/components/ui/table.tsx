import * as React from 'react';

import { cn } from '@/lib/utils';

function TableContainer({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn('tdms-scrollbar relative w-full overflow-auto rounded-lg border border-border bg-card', className)}
      {...props}
    />
  );
}

function Table({ className, ...props }: React.ComponentProps<'table'>) {
  return <table className={cn('w-full caption-bottom border-collapse text-[13px]', className)} {...props} />;
}

function TableHeader({ className, ...props }: React.ComponentProps<'thead'>) {
  return <thead className={cn('sticky top-0 z-10 bg-muted/70 backdrop-blur-sm', className)} {...props} />;
}

function TableBody({ className, ...props }: React.ComponentProps<'tbody'>) {
  return <tbody className={cn('[&_tr:last-child]:border-0', className)} {...props} />;
}

function TableRow({ className, ...props }: React.ComponentProps<'tr'>) {
  return (
    <tr
      className={cn(
        'border-b border-border transition-colors hover:bg-muted/40 data-[selected=true]:bg-primary-soft',
        className,
      )}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: React.ComponentProps<'th'>) {
  return (
    <th
      scope="col"
      className={cn(
        'h-10 whitespace-nowrap border-b border-border px-3 text-left align-middle text-[12px] font-semibold uppercase tracking-wide text-muted-foreground',
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: React.ComponentProps<'td'>) {
  return <td className={cn('px-3 py-2.5 align-middle text-foreground', className)} {...props} />;
}

function TableCaption({ className, ...props }: React.ComponentProps<'caption'>) {
  return <caption className={cn('mt-3 text-[13px] text-muted-foreground', className)} {...props} />;
}

export { TableContainer, Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption };
