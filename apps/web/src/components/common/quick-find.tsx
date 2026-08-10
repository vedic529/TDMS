'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { GraduationCap, Search, Users } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { EmptyState } from './states';
import { getTdmsClient } from '@/services';
import { INTERFACE_NAMES } from '@/lib/interface-names';

interface QuickFindResult {
  id: string;
  label: string;
  detail: string;
  area: string;
  href: string;
  icon: React.ElementType;
}

/**
 * Compact search in the top navigation.
 *
 * It finds a record and opens the operational page that owns it. It does not
 * bypass permissions: the destination page applies the same rules as any other
 * route (ACC-06).
 */
export function QuickFind() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [term, setTerm] = React.useState('');
  const [results, setResults] = React.useState<QuickFindResult[]>([]);
  const [searching, setSearching] = React.useState(false);

  React.useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen(true);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  React.useEffect(() => {
    if (!open) {
      setTerm('');
      setResults([]);
      return;
    }
  }, [open]);

  React.useEffect(() => {
    const value = term.trim();
    if (value.length < 2) {
      setResults([]);
      return;
    }
    let cancelled = false;
    setSearching(true);

    const timer = setTimeout(() => {
      void (async () => {
        const client = getTdmsClient();
        const [students, courses] = await Promise.all([
          client.listStudents({ search: value }),
          client.listCourses({ search: value }),
        ]);
        if (cancelled) return;

        const found: QuickFindResult[] = [
          ...students.slice(0, 5).map((student) => ({
            id: `student-${student.id}`,
            label: `${student.studentId} — ${student.firstName} ${student.lastName}`.trim(),
            detail: `${student.qualificationCode} · ${student.group || 'No group'}`,
            area: INTERFACE_NAMES.singleStudentEntry,
            href: `/students?tab=single-entry&studentId=${encodeURIComponent(student.studentId)}`,
            icon: Users,
          })),
          ...courses.slice(0, 4).map((course) => ({
            id: `course-${course.id}`,
            label: `${course.courseCode} — ${course.courseName}`,
            detail: `${course.courseLevel} · ${course.durationInWeeks} weeks`,
            area: INTERFACE_NAMES.courseData,
            href: `/reference-data?tab=course-data&search=${encodeURIComponent(course.courseCode)}`,
            icon: GraduationCap,
          })),
        ];
        setResults(found);
        setSearching(false);
      })();
    }, 200);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [term]);

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="hidden w-56 justify-start gap-2 text-muted-foreground lg:inline-flex"
        onClick={() => setOpen(true)}
      >
        <Search aria-hidden="true" />
        <span className="flex-1 text-left font-normal">Search TDMS records</span>
        <kbd className="rounded border border-border bg-muted px-1 text-[10px] font-medium">Ctrl K</kbd>
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        className="lg:hidden"
        onClick={() => setOpen(true)}
        aria-label="Search TDMS records"
      >
        <Search aria-hidden="true" />
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>Search TDMS records</DialogTitle>
            <DialogDescription>
              Find a student or course record and open the page that owns it.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <Input
              autoFocus
              value={term}
              onChange={(event) => setTerm(event.target.value)}
              placeholder="Student ID, student name, course code or course name"
              aria-label="Search term"
            />

            {term.trim().length < 2 ? (
              <p className="px-1 text-[13px] text-muted-foreground">Enter at least two characters to search.</p>
            ) : searching ? (
              <p className="px-1 text-[13px] text-muted-foreground">Searching…</p>
            ) : results.length === 0 ? (
              <EmptyState
                title="No record matched this search"
                description="Check the spelling, or use the filters on the relevant operational page."
                icon={Search}
              />
            ) : (
              <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
                {results.map((result) => {
                  const Icon = result.icon;
                  return (
                    <li key={result.id}>
                      <button
                        type="button"
                        className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-muted/60"
                        onClick={() => {
                          setOpen(false);
                          router.push(result.href);
                        }}
                      >
                        <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium text-foreground">
                            {result.label}
                          </span>
                          <span className="block truncate text-[12px] text-muted-foreground">{result.detail}</span>
                        </span>
                        <span className="hidden shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground sm:block">
                          {result.area}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </DialogBody>
        </DialogContent>
      </Dialog>
    </>
  );
}
