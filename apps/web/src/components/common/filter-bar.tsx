'use client';

import * as React from 'react';
import { FilterX } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

interface FilterBarProps {
  children: React.ReactNode;
  onClear?: () => void;
  /** Rendered on the right, e.g. Export or a result count. */
  trailing?: React.ReactNode;
  className?: string;
}

/** Consistent filter surface used by every operational page. */
export function FilterBar({ children, onClear, trailing, className }: FilterBarProps) {
  return (
    <Card className={cn('p-4', className)}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">{children}</div>
        {(onClear || trailing) && (
          <div className="flex shrink-0 items-center gap-2">
            {trailing}
            {onClear && (
              <Button variant="ghost" size="sm" onClick={onClear}>
                <FilterX aria-hidden="true" />
                Clear filters
              </Button>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

export function FilterField({
  label,
  htmlFor,
  children,
  className,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <Label htmlFor={htmlFor} className="text-[12px] font-medium text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  );
}
