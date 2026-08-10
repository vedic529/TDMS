'use client';

import * as React from 'react';
import { FileSpreadsheet, UploadCloud } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const ACCEPTED_EXTENSIONS = ['.csv', '.xlsx'];

interface FileDropzoneProps {
  onFileSelected: (file: File) => void;
  /** Shown under the primary text, e.g. row limits. */
  hint?: string;
  disabled?: boolean;
  disabledMessage?: string;
}

/**
 * BULK-01: only the approved CSV and XLSX templates are accepted. An
 * unsupported file is rejected with a clear message and is never staged.
 */
export function FileDropzone({ onFileSelected, hint, disabled, disabledMessage }: FileDropzoneProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  function accept(file: File | undefined) {
    if (!file) return;
    const lower = file.name.toLowerCase();
    const supported = ACCEPTED_EXTENSIONS.some((extension) => lower.endsWith(extension));
    if (!supported) {
      setError(
        `"${file.name}" is not an approved template. Select a CSV or XLSX file that matches the approved bulk student import template.`,
      );
      return;
    }
    setError(null);
    onFileSelected(file);
  }

  return (
    <div className="space-y-2">
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        aria-label="Select a CSV or XLSX file to upload"
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(event) => {
          if (disabled) return;
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(event) => {
          if (disabled) return;
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          if (disabled) return;
          event.preventDefault();
          setDragging(false);
          accept(event.dataTransfer.files?.[0]);
        }}
        className={cn(
          'flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors',
          disabled
            ? 'cursor-not-allowed border-border bg-muted/40'
            : 'cursor-pointer border-border bg-card hover:border-primary/50 hover:bg-primary-soft/40',
          dragging && 'border-primary bg-primary-soft',
        )}
      >
        <span
          className={cn(
            'flex size-12 items-center justify-center rounded-full',
            dragging ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground',
          )}
        >
          <UploadCloud className="size-6" aria-hidden="true" />
        </span>
        <div className="space-y-1">
          <p className="text-sm font-medium text-foreground">Drag and drop the student file here</p>
          <p className="text-[13px] text-muted-foreground">or select a file from your computer</p>
        </div>
        <Button variant="default" size="sm" disabled={disabled} tabIndex={-1}>
          <FileSpreadsheet aria-hidden="true" />
          Select File
        </Button>
        <p className="text-[12px] text-muted-foreground">
          Approved templates: CSV, XLSX. {hint}
        </p>
        {disabled && disabledMessage && (
          <p className="text-[12px] font-medium text-muted-foreground">{disabledMessage}</p>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx"
          className="sr-only"
          onChange={(event) => {
            accept(event.target.files?.[0]);
            event.target.value = '';
          }}
        />
      </div>
      {error && (
        <p className="text-[13px] font-medium text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
