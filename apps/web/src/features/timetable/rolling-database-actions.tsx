'use client';

import * as React from 'react';
import { Download, Upload } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SimpleSelect } from '@/components/common/dependent-select';
import { FileDropzone } from '@/components/common/file-dropzone';
import { exportRows } from '@/lib/export';
import { ReferenceApiError } from '@/services/reference-api';
import {
  rollingTimetableApi,
  TRAINING_PACKAGES,
  type ImportReview,
} from '@/services/rolling-timetable-api';

const TEMPLATE_COLUMNS = [
  'qualification_code',
  'duration_weeks',
  'intake_label',
  'intake_group',
  'intake_start_date',
  'week_no',
  'week_start_date',
  'week_end_date',
  'schedule_type',
  'schedule_value',
  'unit_code',
  'unit_count',
  'unit_delivery_span_weeks',
] as const;

export function RollingDatabaseActions({ onImported }: { onImported?: () => void }) {
  const [importOpen, setImportOpen] = React.useState(false);
  const [trainingPackage, setTrainingPackage] = React.useState('');
  const [file, setFile] = React.useState<File | null>(null);
  const [review, setReview] = React.useState<ImportReview | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  function reset() {
    setTrainingPackage('');
    setFile(null);
    setReview(null);
    setBusy(false);
    setError(null);
  }

  function downloadTemplate() {
    exportRows({
      format: 'xlsx',
      baseFileName: 'Rolling TT Data Schema',
      sheetName: 'Rolling TT Data Schema',
      rows: [] as Array<Record<string, string>>,
      columns: TEMPLATE_COLUMNS.map((header) => ({ header, value: () => '' })),
    });
    toast.success('Template downloaded', {
      description: 'Rolling TT Data Schema.xlsx contains the 13 field names used for bulk import.',
    });
  }

  async function validateSelected(nextFile: File) {
    if (!trainingPackage) return;
    setBusy(true);
    setError(null);
    try {
      setReview(await rollingTimetableApi.validateImport(trainingPackage, nextFile));
    } catch (caught) {
      setReview(null);
      setError(caught instanceof ReferenceApiError ? caught.message : 'The file could not be reviewed.');
    } finally {
      setBusy(false);
    }
  }

  async function apply(proceedWithMatching: boolean) {
    if (!file || !trainingPackage) return;
    setBusy(true);
    setError(null);
    try {
      const result = await rollingTimetableApi.applyImport(trainingPackage, file, proceedWithMatching);
      toast.success('Import complete', {
        description: `${result.rows_written} rows written for ${trainingPackage}.`,
      });
      setImportOpen(false);
      reset();
      onImported?.();
    } catch (caught) {
      setError(caught instanceof ReferenceApiError ? caught.message : 'The import could not be written.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={downloadTemplate}>
        <Download aria-hidden="true" />
        Export template
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => {
          reset();
          setImportOpen(true);
        }}
      >
        <Upload aria-hidden="true" />
        Import Data
      </Button>

      <Dialog
        open={importOpen}
        onOpenChange={(open) => {
          setImportOpen(open);
          if (!open) reset();
        }}
      >
        <DialogContent size="xl">
          <DialogHeader>
            <DialogTitle>Import rolling timetable</DialogTitle>
            <DialogDescription>
              Choose one training package, then upload the 13-column flat file. Nothing is written until you
              confirm.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="max-w-xs space-y-1">
              <p className="text-[12px] font-medium text-foreground">Training package</p>
              <SimpleSelect
                value={trainingPackage}
                onChange={(value) => {
                  setTrainingPackage(value);
                  setReview(null);
                  setFile(null);
                }}
                options={TRAINING_PACKAGES.map((item) => ({ value: item, label: item }))}
                placeholder="Select a training package"
              />
            </div>

            <FileDropzone
              disabled={!trainingPackage || busy}
              disabledMessage={trainingPackage ? undefined : 'Select a training package before uploading a file.'}
              title="Drag and drop the rolling timetable file here"
              hint="CSV or XLSX. One training package per import."
              onFileSelected={(next) => {
                setFile(next);
                void validateSelected(next);
              }}
            />

            {error && <p className="text-[13px] text-destructive">{error}</p>}
            {busy && !review && <p className="text-[13px] text-muted-foreground">Reviewing the file…</p>}

            {review && (
              <div className="space-y-3 text-[13px]">
                <p>
                  {review.rows_read} rows read · {review.rows_that_would_be_written} would be written · UNIT{' '}
                  {review.counts.unit} · Break {review.counts.break_count} · Assessment Week{' '}
                  {review.counts.assessment_week}
                </p>
                {review.matching_qualifications.length > 0 && (
                  <div>
                    <p className="font-medium">{review.training_package} qualifications</p>
                    <ul className="mt-1 list-disc pl-5 text-muted-foreground">
                      {review.matching_qualifications.map((item) => (
                        <li key={item.qualification_code}>
                          {item.qualification_code} · {item.row_count} rows · {item.intake_count} intakes
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {review.non_matching_qualifications.length > 0 && (
                  <div>
                    <p className="font-medium">Not in {review.training_package}</p>
                    <ul className="mt-1 list-disc pl-5 text-muted-foreground">
                      {review.non_matching_qualifications.map((item) => (
                        <li key={item.qualification_code}>
                          {item.qualification_code} ({item.training_package}) · {item.row_count} rows
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {review.existing_qualifications_replaced.length > 0 && (
                  <p>Will replace: {review.existing_qualifications_replaced.join(', ')}</p>
                )}
                {Object.entries(review.discrepancies_by_kind).map(([kind, items]) => (
                  <div key={kind}>
                    <p className="font-medium">
                      {kind.replaceAll('_', ' ')} ({items.length})
                    </p>
                    <ul className="mt-1 max-h-40 list-disc overflow-auto pl-5 text-muted-foreground">
                      {items.slice(0, 20).map((item, index) => (
                        <li key={`${kind}-${index}`}>
                          {item.row_number ? `Row ${item.row_number}: ` : ''}
                          {item.message}
                          {item.value ? ` (${item.value})` : ''}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            {review?.can_proceed_with_package ? (
              <>
                <Button type="button" variant="destructive" disabled={busy} onClick={() => { setImportOpen(false); reset(); }}>
                  Discard
                </Button>
                <Button type="button" disabled={busy} onClick={() => void apply(true)}>
                  Proceed with {review.training_package} qualifications
                </Button>
              </>
            ) : (
              <>
                <Button type="button" variant="outline" onClick={() => { setImportOpen(false); reset(); }}>
                  Close
                </Button>
                <Button
                  type="button"
                  disabled={busy || !review || review.refused}
                  onClick={() => void apply(false)}
                >
                  Import
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
