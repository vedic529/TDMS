import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const alertVariants = cva(
  'relative flex w-full gap-3 rounded-lg border px-4 py-3 text-[13px] leading-relaxed [&>svg]:size-4 [&>svg]:shrink-0 [&>svg]:translate-y-0.5',
  {
    variants: {
      variant: {
        default: 'border-border bg-muted/50 text-foreground [&>svg]:text-muted-foreground',
        info: 'border-info/25 bg-info-soft text-info [&>svg]:text-info',
        success: 'border-success/25 bg-success-soft text-success [&>svg]:text-success',
        warning: 'border-warning/30 bg-warning-soft text-warning [&>svg]:text-warning',
        destructive: 'border-destructive/25 bg-destructive-soft text-destructive [&>svg]:text-destructive',
      },
    },
    defaultVariants: { variant: 'default' },
  },
);

function Alert({
  className,
  variant,
  ...props
}: React.ComponentProps<'div'> & VariantProps<typeof alertVariants>) {
  return <div role="status" className={cn(alertVariants({ variant }), className)} {...props} />;
}

function AlertTitle({ className, ...props }: React.ComponentProps<'p'>) {
  return <p className={cn('font-semibold text-current', className)} {...props} />;
}

function AlertDescription({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('text-current/90', className)} {...props} />;
}

export { Alert, AlertTitle, AlertDescription };
