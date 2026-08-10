'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { TdmsLogo } from './tdms-logo';
import { UserMenu } from './user-menu';
import { QuickFind } from './quick-find';
import { PRIMARY_NAVIGATION } from '@/lib/interface-names';
import { env } from '@/lib/env';
import { cn } from '@/lib/utils';

/**
 * Sticky top navigation used by the whole operational application.
 *
 * SRS 2.2 approved interface names are used verbatim. TDMS has exactly four
 * primary operational work areas; Administration is reached from the account
 * menu and is deliberately not a fifth navigation item.
 */
export function TopNavigation() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = React.useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/85">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-3 px-4 sm:px-6">
        <Link href="/timetable" className="shrink-0 rounded-md" aria-label="TDMS home">
          <TdmsLogo />
        </Link>

        <nav className="ml-2 hidden flex-1 items-center gap-1 xl:flex" aria-label="Primary">
          {PRIMARY_NAVIGATION.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors',
                  active
                    ? 'bg-primary-soft text-primary'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Between mobile and xl the full interface names do not fit, so the
            approved short labels are used and the full name stays in the title. */}
        <nav className="ml-2 hidden flex-1 items-center gap-1 md:flex xl:hidden" aria-label="Primary">
          {PRIMARY_NAVIGATION.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors',
                  active
                    ? 'bg-primary-soft text-primary'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                )}
              >
                {item.shortLabel}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          {env.appEnvironment !== 'production' && (
            <Badge variant="warning" className="hidden sm:inline-flex" title="Demo data. Not production information.">
              {env.appEnvironment === 'development' ? 'Development · demo data' : 'Staging'}
            </Badge>
          )}
          <QuickFind />
          <UserMenu />
          <Button
            variant="ghost"
            size="icon-sm"
            className="md:hidden"
            aria-label="Open navigation"
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen((value) => !value)}
          >
            <Menu aria-hidden="true" />
          </Button>
        </div>
      </div>

      {mobileOpen && (
        <nav className="border-t border-border bg-background px-4 py-2 md:hidden" aria-label="Primary (compact)">
          <ul className="space-y-1">
            {PRIMARY_NAVIGATION.map((item) => {
              const active = pathname.startsWith(item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={() => setMobileOpen(false)}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'block rounded-md px-3 py-2 text-[13px] font-medium',
                      active ? 'bg-primary-soft text-primary' : 'text-muted-foreground hover:bg-muted',
                    )}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      )}
    </header>
  );
}
