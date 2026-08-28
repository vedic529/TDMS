'use client';

import * as React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { FileSpreadsheet, UserRoundPen } from 'lucide-react';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PageHeader } from '@/components/common/page-header';
import { StudentRecordsPanel } from './student-records-panel';
import { BulkStudentImport } from './bulk-student-import';
import { INTERFACE_NAMES } from '@/lib/interface-names';

type TabValue = 'single-entry' | 'bulk-import';

/**
 * Student Data work area.
 *
 * One top-level work area with the two approved interface names as tabs. The
 * SRS page references (Page 2A / Page 2B) are never shown to the user.
 */
export function StudentWorkArea() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const tabParam = searchParams.get('tab');
  const tab: TabValue = tabParam === 'bulk-import' ? 'bulk-import' : 'single-entry';
  const studentIdParam = searchParams.get('studentId') ?? undefined;

  function setTab(next: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set('tab', next);
    params.delete('studentId');
    router.replace(`/students?${params.toString()}`, { scroll: false });
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title={INTERFACE_NAMES.studentData}
        description="Create, find, edit and delete one student record at a time, or process an approved bulk student file."
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="single-entry">
            <UserRoundPen aria-hidden="true" />
            {INTERFACE_NAMES.singleStudentEntry}
          </TabsTrigger>
          <TabsTrigger value="bulk-import">
            <FileSpreadsheet aria-hidden="true" />
            {INTERFACE_NAMES.bulkStudentImport}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="single-entry" className="space-y-5">
          {/*
            One panel. The records list carries its own search and Create
            control; a record opens in a side panel and the form opens in a
            popup, so nothing takes over the page.
          */}
          <StudentRecordsPanel initialStudentId={studentIdParam} />
        </TabsContent>

        <TabsContent value="bulk-import">
          <BulkStudentImport />
        </TabsContent>
      </Tabs>
    </div>
  );
}
