'use client';

import * as React from 'react';
import { ChevronDown, ChevronRight, FilterX, Info, ListFilter, Loader2, Maximize2, Minimize2, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { EmptyState, ErrorState, LoadingState } from '@/components/common/states';
import { formatDate } from '@/lib/format';
import { ReferenceApiError } from '@/services/reference-api';
import {
  ALLOCATION_EMPTY_DESCRIPTION,
  ALLOCATION_EMPTY_TITLE,
  allocationApi,
  type AllocationSpreadsheetChoices,
  type AllocationSpreadsheetRow,
  type AllocationSpreadsheetSession,
} from '@/services/allocation-api';

const ALL_ROWS_LIMIT = 5000;
const WEEKDAYS = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY'];
const MONTH_FORMATTER = new Intl.DateTimeFormat('en-AU', { month: 'long', timeZone: 'UTC' });
const selectClass = 'h-8 min-w-32 rounded-md border border-input bg-background px-2 text-[12px] outline-none focus:border-ring focus:ring-2 focus:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-60';
type ChoiceCache = Record<string, AllocationSpreadsheetChoices>;
type SessionChange = Partial<AllocationSpreadsheetSession> & { facility_id?: number; trainer_id?: number };
type FilterKey =
  | 'sl_no' | 'college' | 'campus' | 'qualification_code' | 'qualification_title'
  | 'duration_weeks' | 'group' | 'intakes' | 'total_students' | 'coe_students'
  | 'non_coe_students' | 'unit_code' | 'unit_title' | 'unit_start_date' | 'unit_end_date'
  | 'uoc_type' | 'mode_of_delivery' | 'theory_schedule' | 'theory_classroom'
  | 'theory_capacity' | 'theory_trainer' | 'practical_classroom' | 'practical_capacity'
  | 'practical_schedule' | 'practical_trainer';
type Filters = Partial<Record<FilterKey, string[]>>;
type FilterOptions = Record<FilterKey, string[]>;

export function AllocationSpreadsheet({ trainingPackage, fromDate, toDate, onFromDateChange, onToDateChange, reloadToken, canChange }: {
  trainingPackage: string; fromDate: string; toDate: string;
  onFromDateChange: (value: string) => void; onToDateChange: (value: string) => void;
  reloadToken: number; canChange: boolean;
}) {
  const [rows, setRows] = React.useState<AllocationSpreadsheetRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState<string | null>(null);
  const [choices, setChoices] = React.useState<ChoiceCache>({});
  const [version, setVersion] = React.useState(0);
  const [maximized, setMaximized] = React.useState(false);
  const [filters, setFilters] = React.useState<Filters>({});

  React.useEffect(() => {
    if (!maximized) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, [maximized]);

  React.useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && maximized) setMaximized(false);
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [maximized]);

  React.useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    void allocationApi.spreadsheet(trainingPackage, fromDate, toDate, ALL_ROWS_LIMIT, 0)
      .then((result) => { if (alive) { setRows(result.items); setChoices({}); } })
      .catch((caught) => { if (alive) setError(caught instanceof ReferenceApiError ? caught.message : 'The spreadsheet could not be loaded.'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [trainingPackage, fromDate, toDate, reloadToken, version]);

  React.useEffect(() => {
    setFilters({});
  }, [trainingPackage, fromDate, toDate]);

  async function loadChoices(row: AllocationSpreadsheetRow, item: AllocationSpreadsheetSession) {
    const key = choiceKey(item);
    if (choices[key]) return choices[key];
    try {
      const result = await allocationApi.spreadsheetChoices(row.delivery_id, trainingPackage, {
        stream: item.stream, weekday: item.weekday, start_time: item.start_time, end_time: item.end_time, delivery_mode: item.delivery_mode,
      });
      setChoices((current) => ({ ...current, [key]: result }));
      return result;
    } catch (caught) {
      const empty = { classrooms: [], trainers: [] };
      setChoices((current) => ({ ...current, [key]: empty }));
      toast.error(caught instanceof ReferenceApiError ? caught.message : 'Available classrooms could not be loaded.');
      return empty;
    }
  }
  async function saveSession(row: AllocationSpreadsheetRow, item: AllocationSpreadsheetSession, change: SessionChange) {
    setSaving(String(item.session_id));
    try {
      await allocationApi.updateSession(item.session_id, trainingPackage, {
        weekday: change.weekday ?? item.weekday,
        start_time: change.start_time ?? item.start_time,
        end_time: change.end_time ?? item.end_time,
        classroom: change.classroom ?? item.classroom,
        trainer: change.trainer ?? item.trainer,
        facility_id: change.facility_id,
        trainer_id: change.trainer_id,
      });
      setVersion((value) => value + 1);
    } catch (caught) {
      toast.error(caught instanceof ReferenceApiError ? caught.message : 'The class could not be updated.');
    } finally { setSaving(null); }
  }
  async function addDay(row: AllocationSpreadsheetRow, stream: 'THEORY' | 'PRACTICAL', weekday: string) {
    setSaving(`add-${row.delivery_id}-${stream}`);
    try {
      await allocationApi.addSession(trainingPackage, {
        delivery_id: row.delivery_id, stream, weekday, start_time: '09:00', end_time: '17:00',
        classroom: stream === 'THEORY' && row.mode_of_delivery === 'F2FV' ? 'Face to Face VC' : undefined,
      });
      toast.success(`${friendly(stream)} class added at 09:00–17:00.`);
      setVersion((value) => value + 1);
    } catch (caught) {
      toast.error(caught instanceof ReferenceApiError ? caught.message : 'The class day could not be added.');
    } finally { setSaving(null); }
  }

  async function deleteDay(item: AllocationSpreadsheetSession) {
    setSaving(String(item.session_id));
    try {
      await allocationApi.deleteSession(item.session_id, trainingPackage);
      toast.success(`${friendly(item.weekday)} class day deleted.`);
      setVersion((value) => value + 1);
    } catch (caught) {
      toast.error(caught instanceof ReferenceApiError ? caught.message : 'The class day could not be deleted.');
    } finally { setSaving(null); }
  }

  if (loading) return <LoadingState label="Opening allocation spreadsheet…" />;
  if (error) return <ErrorState title="Allocation spreadsheet could not be loaded" description={error} />;
  if (!rows.length) return <EmptyState title={ALLOCATION_EMPTY_TITLE} description={ALLOCATION_EMPTY_DESCRIPTION} />;

  const shownRows = rows.filter((row) => rowMatchesFilters(row, filters));
  const filterOptions = buildFilterOptions(rows, filters);
  const hasFilters = Object.keys(filters).length > 0;
  const setFilter = (key: FilterKey, values: string[]) => {
    setFilters((current) => {
      const next = { ...current };
      if (values.length === filterOptions[key].length) delete next[key];
      else next[key] = values;
      return next;
    });
  };

  return <div className={maximized ? 'fixed inset-0 z-[100] flex min-h-0 flex-col gap-3 bg-background p-3' : 'space-y-3'}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-end gap-4">
        {maximized && <div className="flex items-center gap-1.5 self-center">
          <p className="text-sm font-semibold text-foreground">Allocation spreadsheet</p>
          <Tooltip>
            <TooltipTrigger asChild>
              <button type="button" className="rounded-full text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="About the allocation spreadsheet">
                <Info className="size-4" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent>
              Imported and rolling-timetable fields are locked. Use the blue columns to schedule classes, and filter from any column heading.
            </TooltipContent>
          </Tooltip>
        </div>}
        {maximized && <DateControl id="spreadsheet-from" label="Start date" value={fromDate} onChange={onFromDateChange} />}
        {maximized && <DateControl id="spreadsheet-to" label="End date" value={toDate} min={fromDate} onChange={onToDateChange} />}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {hasFilters && <Tooltip>
          <TooltipTrigger asChild>
            <Button type="button" variant="outline" size="icon-sm" onClick={() => setFilters({})} aria-label="Clear filters">
              <FilterX aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Clear filters</TooltipContent>
        </Tooltip>}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button type="button" variant="outline" size="icon-sm" onClick={() => setMaximized((value) => !value)} aria-label={maximized ? 'Minimize spreadsheet' : 'Maximize spreadsheet'}>
              {maximized ? <Minimize2 aria-hidden="true" /> : <Maximize2 aria-hidden="true" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{maximized ? 'Minimize spreadsheet' : 'Maximize spreadsheet'}</TooltipContent>
        </Tooltip>
      </div>
    </div>
    <TableContainer className={maximized ? 'min-h-0 flex-1 rounded-md' : 'max-h-[calc(100vh-20rem)] rounded-md'}>
      <Table className="min-w-[4050px] table-fixed text-[12px]">
        <TableHeader><TableRow className="hover:bg-transparent [&>th]:whitespace-normal [&>th]:border-r [&>th]:px-2 [&>th]:py-2 [&>th]:align-bottom [&>th]:leading-tight">
          <TableHead className="sticky left-0 z-30 w-[72px] min-w-[72px] bg-muted font-medium">Sl No.</TableHead>
          <Head filterKey="college" options={filterOptions.college} filters={filters} onFilter={setFilter} className="w-[110px] min-w-[110px]">College</Head>
          <Head filterKey="campus" options={filterOptions.campus} filters={filters} onFilter={setFilter} className="w-[125px] min-w-[125px]">Campus</Head>
          <Head filterKey="qualification_code" options={filterOptions.qualification_code} filters={filters} onFilter={setFilter} className="w-[140px] min-w-[140px]">Qualification Code</Head>
          <Head filterKey="qualification_title" options={filterOptions.qualification_title} filters={filters} onFilter={setFilter} className="w-[240px] min-w-[240px]">Qualification Title</Head>
          <Head filterKey="duration_weeks" options={filterOptions.duration_weeks} filters={filters} onFilter={setFilter} className="w-[115px] min-w-[115px]">Duration in weeks</Head>
          <Head filterKey="group" options={filterOptions.group} filters={filters} onFilter={setFilter} className="w-[90px] min-w-[90px]">Group</Head>
          <Head filterKey="intakes" options={filterOptions.intakes} filters={filters} onFilter={setFilter} className="w-[260px] min-w-[260px]">Linked Intakes</Head>
          <Head filterKey="total_students" options={filterOptions.total_students} filters={filters} onFilter={setFilter} className="w-[135px] min-w-[135px]">Total students attending</Head>
          <Head filterKey="coe_students" options={filterOptions.coe_students} filters={filters} onFilter={setFilter} className="w-[110px] min-w-[110px]">COE students</Head>
          <Head filterKey="non_coe_students" options={filterOptions.non_coe_students} filters={filters} onFilter={setFilter} className="w-[120px] min-w-[120px]">Non-COE students</Head>
          <Head filterKey="unit_code" options={filterOptions.unit_code} filters={filters} onFilter={setFilter} className="w-[155px] min-w-[155px]">Units of Competency ID</Head>
          <Head filterKey="unit_title" options={filterOptions.unit_title} filters={filters} onFilter={setFilter} className="w-[240px] min-w-[240px]">Units of Competency Title</Head>
          <Head filterKey="unit_start_date" options={filterOptions.unit_start_date} filters={filters} onFilter={setFilter} className="w-[145px] min-w-[145px]">Unit of Competency Start Date</Head>
          <Head filterKey="unit_end_date" options={filterOptions.unit_end_date} filters={filters} onFilter={setFilter} className="w-[145px] min-w-[145px]">Unit of Competency End Date</Head>
          <Head filterKey="uoc_type" options={filterOptions.uoc_type} filters={filters} onFilter={setFilter} className="w-[105px] min-w-[105px]">UoC Type</Head>
          <Head filterKey="mode_of_delivery" options={filterOptions.mode_of_delivery} filters={filters} onFilter={setFilter} className="w-[125px] min-w-[125px]">Mode of Delivery</Head>
          <EditHead filterKey="theory_schedule" options={filterOptions.theory_schedule} filters={filters} onFilter={setFilter} className="w-[270px] min-w-[270px]">Theory Class Days and Times</EditHead>
          <EditHead filterKey="theory_classroom" options={filterOptions.theory_classroom} filters={filters} onFilter={setFilter} className="w-[220px] min-w-[220px]">Theory Classroom Name</EditHead>
          <EditHead filterKey="theory_capacity" options={filterOptions.theory_capacity} filters={filters} onFilter={setFilter} className="w-[155px] min-w-[155px]">Theory Classroom Capacity</EditHead>
          <EditHead filterKey="theory_trainer" options={filterOptions.theory_trainer} filters={filters} onFilter={setFilter} className="w-[205px] min-w-[205px]">Theory Trainer</EditHead>
          <EditHead filterKey="practical_classroom" options={filterOptions.practical_classroom} filters={filters} onFilter={setFilter} className="w-[220px] min-w-[220px]">Practical Classroom Name</EditHead>
          <EditHead filterKey="practical_capacity" options={filterOptions.practical_capacity} filters={filters} onFilter={setFilter} className="w-[155px] min-w-[155px]">Practical Class Capacity</EditHead>
          <EditHead filterKey="practical_schedule" options={filterOptions.practical_schedule} filters={filters} onFilter={setFilter} className="w-[270px] min-w-[270px]">Practical Class Days and Times</EditHead>
          <EditHead filterKey="practical_trainer" options={filterOptions.practical_trainer} filters={filters} onFilter={setFilter} className="w-[205px] min-w-[205px]">Practical Trainers</EditHead>
        </TableRow></TableHeader>
        <TableBody>{shownRows.map((row) => {
          const theory = row.sessions.filter((item) => item.stream === 'THEORY');
          const practical = row.sessions.filter((item) => item.stream === 'PRACTICAL');
          return <TableRow key={row.delivery_id} className="[&>td]:border-r [&>td]:px-2 [&>td]:py-2 [&>td]:align-top">
            <Cell className="sticky left-0 z-20 bg-card font-medium tabular-nums">{row.sl_no}</Cell>
            <Cell>{row.college}</Cell><Cell>{row.campus}</Cell><Cell strong>{row.qualification_code}</Cell><Cell>{row.qualification_title}</Cell>
            <Cell>{row.duration_weeks}</Cell><Cell>{row.group}</Cell><Cell><div className="min-w-56 space-y-1 whitespace-normal" title={row.intakes.join(', ')}>{row.intakes.length ? row.intakes.map((intake) => <div key={intake}>{intake}</div>) : '—'}</div></Cell>
            <Cell>{row.total_students}</Cell><Cell>{row.coe_students}</Cell><Cell>{row.non_coe_students}</Cell>
            <Cell strong>{row.unit_code}</Cell><Cell>{row.unit_title}</Cell><Cell>{formatDate(row.unit_start_date)}</Cell><Cell>{formatDate(row.unit_end_date)}</Cell>
            <Cell>{friendly(row.uoc_type)}</Cell><Cell>{row.mode_of_delivery}</Cell>
            <EditCell><ScheduleEditor row={row} items={theory} stream="THEORY" canChange={canChange} saving={saving} onSave={saveSession} onAdd={addDay} onDelete={deleteDay} /></EditCell>
            <EditCell><ClassroomEditor row={row} items={theory} canChange={canChange} saving={saving} choices={choices} loadChoices={loadChoices} onSave={saveSession} /></EditCell>
            <EditCell><CapacityList items={theory} /></EditCell>
            <EditCell><TrainerEditor row={row} items={theory} canChange={canChange} saving={saving} choices={choices} loadChoices={loadChoices} onSave={saveSession} /></EditCell>
            <EditCell><ClassroomEditor row={row} items={practical} canChange={canChange} saving={saving} choices={choices} loadChoices={loadChoices} onSave={saveSession} /></EditCell>
            <EditCell><CapacityList items={practical} /></EditCell>
            <EditCell><ScheduleEditor row={row} items={practical} stream="PRACTICAL" canChange={canChange} saving={saving} onSave={saveSession} onAdd={addDay} onDelete={deleteDay} /></EditCell>
            <EditCell><TrainerEditor row={row} items={practical} canChange={canChange} saving={saving} choices={choices} loadChoices={loadChoices} onSave={saveSession} /></EditCell>
          </TableRow>;
        })}{shownRows.length === 0 && (
          <TableRow>
            <TableCell colSpan={25} className="h-28 text-center text-[13px] text-muted-foreground">
              No allocations match the current column filters.
            </TableCell>
          </TableRow>
        )}</TableBody>
      </Table>
    </TableContainer>
  </div>;
}

function ScheduleEditor({ row, items, stream, canChange, saving, onSave, onAdd, onDelete }: {
  row: AllocationSpreadsheetRow; items: AllocationSpreadsheetSession[]; stream: 'THEORY' | 'PRACTICAL'; canChange: boolean; saving: string | null;
  onSave: (row: AllocationSpreadsheetRow, item: AllocationSpreadsheetSession, change: SessionChange) => Promise<void>;
  onAdd: (row: AllocationSpreadsheetRow, stream: 'THEORY' | 'PRACTICAL', weekday: string) => Promise<void>;
  onDelete: (item: AllocationSpreadsheetSession) => Promise<void>;
}) {
  if (stream === 'PRACTICAL' && row.uoc_type === 'THEORY_ONLY') return <Muted>Not required</Muted>;
  const used = new Set(items.map((item) => item.weekday));
  return <Stack>{items.map((item) => <div key={item.session_id} className="relative space-y-1 rounded border border-primary/15 bg-background p-1.5 pr-8">
    {canChange && <button type="button" className="absolute right-1 top-1 rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={`Delete ${friendly(item.weekday)} class day`} title="Delete class day" disabled={saving === String(item.session_id)} onClick={() => void onDelete(item)}>{saving === String(item.session_id) ? <Loader2 className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}</button>}
    <select className={selectClass} value={item.weekday} disabled={!canChange || saving === String(item.session_id)} onChange={(event) => void onSave(row, item, { weekday: event.target.value })}>{WEEKDAYS.map((day) => <option key={day} value={day}>{friendly(day)}</option>)}</select>
    <div className="flex gap-1"><TimeInput value={item.start_time} disabled={!canChange} onCommit={(value) => onSave(row, item, { start_time: value })} /><TimeInput value={item.end_time} disabled={!canChange} onCommit={(value) => onSave(row, item, { end_time: value })} /></div>
  </div>)}{canChange && <select aria-label={`Add ${stream.toLowerCase()} class day`} className={`${selectClass} w-full`} value="" disabled={saving === `add-${row.delivery_id}-${stream}`} onChange={(event) => { if (event.target.value) void onAdd(row, stream, event.target.value); }}><option value="">＋ Add a class day · 09:00–17:00</option>{WEEKDAYS.filter((day) => !used.has(day)).map((day) => <option key={day} value={day}>{friendly(day)}</option>)}</select>}{saving === `add-${row.delivery_id}-${stream}` && <Loader2 className="size-4 animate-spin" />}</Stack>;
}

interface EditorProps { row: AllocationSpreadsheetRow; items: AllocationSpreadsheetSession[]; canChange: boolean; saving: string | null; choices: ChoiceCache; loadChoices: (row: AllocationSpreadsheetRow, item: AllocationSpreadsheetSession) => Promise<AllocationSpreadsheetChoices>; onSave: (row: AllocationSpreadsheetRow, item: AllocationSpreadsheetSession, change: SessionChange) => Promise<void>; }
function ClassroomEditor({ row, items, canChange, saving, choices, loadChoices, onSave }: EditorProps) {
  if (!items.length) return <Muted>—</Muted>;
  return <Stack>{items.map((item) => {
    const loadedChoices = choices[choiceKey(item)];
    const options = loadedChoices?.classrooms ?? [];
    const current = item.facility_id ? `id:${item.facility_id}` : item.classroom;
    return <Select
      key={item.session_id}
      value={current || undefined}
      disabled={!canChange || saving === String(item.session_id)}
      onOpenChange={(open) => { if (open) void loadChoices(row, item); }}
      onValueChange={(value) => {
        const selected = options.find((entry) => (entry.id ? `id:${entry.id}` : entry.name) === value);
        void onSave(row, item, { classroom: selected?.name ?? '', facility_id: selected?.id ?? undefined });
      }}
    >
      <SelectTrigger className="h-8 min-w-44 px-2 text-[12px]">
        <span className={item.classroom ? 'truncate' : 'truncate text-muted-foreground'}>{item.classroom || 'Select classroom'}</span>
      </SelectTrigger>
      <SelectContent className="z-[120] min-w-[18rem]">
        {!loadedChoices ? <div className="px-2 py-2 text-[12px] text-muted-foreground">Loading available classrooms…</div> : !options.length ? <div className="px-2 py-2 text-[12px] text-muted-foreground">No classrooms are available for this selection.</div> : options.map((entry) => {
          const value = entry.id ? `id:${entry.id}` : entry.name;
          const enough = entry.capacity !== null && entry.capacity >= row.coe_students;
          return <SelectItem key={`${entry.id ?? 'virtual'}-${entry.name}`} value={value}>
            <span className="flex w-full min-w-56 items-center justify-between gap-6">
              <span className="truncate">{entry.name}</span>
              {entry.capacity === null ? (
                <span className="ml-auto shrink-0 text-[12px] text-muted-foreground">Virtual</span>
              ) : (
                <span className={`ml-auto shrink-0 text-right text-[12px] font-semibold tabular-nums ${enough ? 'text-success' : 'text-destructive'}`}>
                  {entry.capacity}
                </span>
              )}
            </span>
          </SelectItem>;
        })}
      </SelectContent>
    </Select>;
  })}</Stack>;
}
function TrainerEditor({ row, items, canChange, saving, choices, loadChoices, onSave }: EditorProps) {
  if (!items.length) return <Muted>—</Muted>;
  return <Stack>{items.map((item) => { const options = choices[choiceKey(item)]?.trainers ?? []; const current = item.trainer_id ? String(item.trainer_id) : item.trainer; return <select key={item.session_id} className={selectClass} value={current} disabled={!canChange || saving === String(item.session_id)} onFocus={() => void loadChoices(row, item)} onChange={(event) => { const selected = options.find((entry) => String(entry.id) === event.target.value); void onSave(row, item, { trainer: selected?.name ?? '', trainer_id: selected?.id }); }}><option value="">Select trainer</option>{current && !options.some((entry) => String(entry.id) === current) && <option value={current}>{item.trainer}</option>}{options.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}</select>; })}</Stack>;
}
function CapacityList({ items }: { items: AllocationSpreadsheetSession[] }) { return items.length ? <Stack>{items.map((item) => <div key={item.session_id} className="h-8 rounded border bg-muted/40 px-2 py-1.5 tabular-nums">{item.classroom_capacity ?? (item.delivery_mode === 'VIRTUAL' ? 'Virtual' : '—')}</div>)}</Stack> : <Muted>—</Muted>; }
function TimeInput({ value, disabled, onCommit }: { value: string; disabled: boolean; onCommit: (value: string) => Promise<void> }) { const [draft, setDraft] = React.useState(value); React.useEffect(() => setDraft(value), [value]); return <Input type="time" className="h-8 w-28 px-1.5 text-[12px]" value={draft} disabled={disabled} onChange={(event) => setDraft(event.target.value)} onBlur={() => { if (draft && draft !== value) void onCommit(draft); }} />; }
function choiceKey(item: AllocationSpreadsheetSession) { return `${item.session_id}-${item.weekday}-${item.start_time}-${item.end_time}-${item.delivery_mode}`; }
function friendly(value: string) { return value.toLowerCase().split('_').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' '); }
interface HeadingProps {
  className?: string;
  filterKey: FilterKey;
  options: string[];
  filters: Filters;
  onFilter: (key: FilterKey, values: string[]) => void;
}
function Head({ className, children, filterKey, options, filters, onFilter }: React.PropsWithChildren<HeadingProps>) {
  return <TableHead className={className}><ColumnHeading filterKey={filterKey} options={options} filters={filters} onFilter={onFilter}>{children}</ColumnHeading></TableHead>;
}
function EditHead({ className, children, filterKey, options, filters, onFilter }: React.PropsWithChildren<HeadingProps>) {
  return <TableHead className={`bg-primary-soft/80 text-primary ${className ?? ''}`}><ColumnHeading filterKey={filterKey} options={options} filters={filters} onFilter={onFilter}>{children}</ColumnHeading></TableHead>;
}
function ColumnHeading({ children, filterKey, options, filters, onFilter }: React.PropsWithChildren<Omit<HeadingProps, 'className'>>) {
  const selected = filters[filterKey];
  const active = selected !== undefined;
  const [search, setSearch] = React.useState('');
  const [open, setOpen] = React.useState(false);
  const [draft, setDraft] = React.useState<Set<string>>(() => new Set(options));
  const visibleOptions = options.filter((option) => option.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const toggle = (value: string) => {
    setDraft((current) => {
      const next = new Set(current);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  };
  const selectAll = () => setDraft((current) => current.size === options.length ? new Set() : new Set(options));
  const apply = () => {
    onFilter(filterKey, options.filter((option) => draft.has(option)));
    setOpen(false);
  };
  return <div className="flex min-h-[68px] h-full flex-col gap-2">
    <div className="flex min-h-7 flex-1 items-start font-medium">{children}</div>
    {(filterKey === 'unit_start_date' || filterKey === 'unit_end_date') && (
      <DateFilterMenu label={String(children)} filterKey={filterKey} options={options} selected={selected} active={active} onFilter={onFilter} />
    )}
    {filterKey !== 'unit_start_date' && filterKey !== 'unit_end_date' && (
    <DropdownMenu open={open} onOpenChange={(nextOpen) => {
      setOpen(nextOpen);
      if (nextOpen) {
        setSearch('');
        setDraft(new Set(selected ?? options));
      }
    }}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`Filter ${String(children)}`}
          className={`flex size-7 items-center justify-center rounded border outline-none focus:ring-1 focus:ring-ring/30 ${active ? 'border-primary bg-primary-soft text-primary' : 'border-input bg-background text-muted-foreground hover:bg-accent'}`}
        >
          <ListFilter className="size-3.5" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="z-[130] flex h-[22rem] min-h-[14rem] w-72 max-h-[calc(100vh-7rem)] resize-y flex-col overflow-hidden p-0">
        <DropdownMenuLabel className="shrink-0 px-2 pt-2 flex items-center justify-between gap-3">
          <span className="truncate">Keep these values</span>
          <span className="shrink-0 text-[11px] font-normal text-muted-foreground">{options.length} values</span>
        </DropdownMenuLabel>
        <div className="shrink-0 px-1 pb-1">
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search values…"
            aria-label={`Search ${String(children)} values`}
            className="h-8 text-[12px]"
          />
        </div>
        <DropdownMenuCheckboxItem className="shrink-0" checked={draft.size === options.length} onCheckedChange={selectAll} onSelect={(event) => event.preventDefault()}>
          Select all
        </DropdownMenuCheckboxItem>
        <DropdownMenuSeparator className="shrink-0" />
        <div className="min-h-0 flex-1 overflow-y-auto py-1">
          {visibleOptions.map((option) => (
            <DropdownMenuCheckboxItem
              key={option}
              checked={draft.has(option)}
              onCheckedChange={() => toggle(option)}
              onSelect={(event) => event.preventDefault()}
            >
              <span className="min-w-0 whitespace-normal break-words" title={option}>{option}</span>
            </DropdownMenuCheckboxItem>
          ))}
          {visibleOptions.length === 0 && (
            <p className="px-2 py-3 text-[12px] text-muted-foreground">No values match.</p>
          )}
        </div>
        <DropdownMenuSeparator className="shrink-0" />
        <div className="shrink-0 p-1">
          <Button type="button" size="sm" className="w-full" onClick={apply}>Apply filter</Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
    )}
  </div>;
}

function DateFilterMenu({ label, filterKey, options, selected, active, onFilter }: {
  label: string;
  filterKey: FilterKey;
  options: string[];
  selected?: string[];
  active: boolean;
  onFilter: (key: FilterKey, values: string[]) => void;
}) {
  const [search, setSearch] = React.useState('');
  const [open, setOpen] = React.useState(false);
  const [draft, setDraft] = React.useState<Set<string>>(() => new Set(options));
  const [openYears, setOpenYears] = React.useState<Set<string>>(() => new Set());
  const [openMonths, setOpenMonths] = React.useState<Set<string>>(() => new Set());
  const groups = React.useMemo(() => groupDateOptions(options), [options]);
  const searchText = search.trim().toLocaleLowerCase();
  const filteredDates = searchText
    ? options.filter((value) => `${value} ${formatDate(value)} ${dateMonthLabel(value)}`.toLocaleLowerCase().includes(searchText))
    : [];
  const selectedSet = draft;
  const toggleValues = (values: string[]) => {
    setDraft((current) => {
      const next = new Set(current);
      const everySelected = values.every((value) => next.has(value));
      values.forEach((value) => {
        if (everySelected) next.delete(value);
        else next.add(value);
      });
      return next;
    });
  };
  const selectAll = () => setDraft((current) => current.size === options.length ? new Set() : new Set(options));
  const apply = () => {
    onFilter(filterKey, options.filter((option) => draft.has(option)));
    setOpen(false);
  };
  const toggleYearOpen = (year: string) => {
    setOpenYears((current) => {
      const next = new Set(current);
      if (next.has(year)) next.delete(year);
      else next.add(year);
      return next;
    });
  };
  const toggleMonthOpen = (key: string) => {
    setOpenMonths((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  return <DropdownMenu open={open} onOpenChange={(nextOpen) => {
    setOpen(nextOpen);
    if (nextOpen) {
      setSearch('');
      setDraft(new Set(selected ?? options));
    }
  }}>
    <DropdownMenuTrigger asChild>
      <button
        type="button"
        aria-label={`Filter ${label}`}
        className={`flex size-7 items-center justify-center rounded border outline-none focus:ring-1 focus:ring-ring/30 ${active ? 'border-primary bg-primary-soft text-primary' : 'border-input bg-background text-muted-foreground hover:bg-accent'}`}
      >
        <ListFilter className="size-3.5" aria-hidden="true" />
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" className="z-[130] flex h-[24rem] min-h-[16rem] w-80 max-h-[calc(100vh-7rem)] resize-y flex-col overflow-hidden p-0">
      <DropdownMenuLabel className="shrink-0 px-2 pt-2 flex items-center justify-between gap-3">
        <span className="truncate">Date filters</span>
        <span className="shrink-0 text-[11px] font-normal text-muted-foreground">{options.length} dates</span>
      </DropdownMenuLabel>
      <div className="shrink-0 px-1 pb-1">
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          onKeyDown={(event) => event.stopPropagation()}
          placeholder="Search dates..."
          aria-label={`Search ${label} dates`}
          className="h-8 text-[12px]"
        />
      </div>
      <DropdownMenuCheckboxItem className="shrink-0" checked={draft.size === options.length} onCheckedChange={selectAll} onSelect={(event) => event.preventDefault()}>
        Select all
      </DropdownMenuCheckboxItem>
      <DropdownMenuSeparator className="shrink-0" />
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {searchText ? (
          <div>
          {filteredDates.map((date) => (
            <DateLeaf key={date} date={date} checked={selectedSet.has(date)} onToggle={() => toggleValues([date])} />
          ))}
          {filteredDates.length === 0 && (
            <p className="px-2 py-3 text-[12px] text-muted-foreground">No dates match.</p>
          )}
        </div>
      ) : (
        <div>
          {groups.map((group) => {
            const yearOpen = openYears.has(group.year);
            const yearDates = group.months.flatMap((month) => month.dates);
            const selectedYearDates = yearDates.filter((date) => selectedSet.has(date)).length;
            return <div key={group.year}>
              <DateGroupRow
                label={group.year}
                open={yearOpen}
                checked={selectedYearDates === yearDates.length}
                partial={selectedYearDates > 0 && selectedYearDates < yearDates.length}
                onToggleOpen={() => toggleYearOpen(group.year)}
                onToggleChecked={() => toggleValues(yearDates)}
              />
              {yearOpen && group.months.map((month) => {
                const monthKey = `${group.year}-${month.month}`;
                const monthOpen = openMonths.has(monthKey);
                const selectedMonthDates = month.dates.filter((date) => selectedSet.has(date)).length;
                return <div key={monthKey}>
                  <DateGroupRow
                    label={month.label}
                    open={monthOpen}
                    checked={selectedMonthDates === month.dates.length}
                    partial={selectedMonthDates > 0 && selectedMonthDates < month.dates.length}
                    onToggleOpen={() => toggleMonthOpen(monthKey)}
                    onToggleChecked={() => toggleValues(month.dates)}
                    indent
                  />
                  {monthOpen && month.dates.map((date) => (
                    <DateLeaf key={date} date={date} checked={selectedSet.has(date)} onToggle={() => toggleValues([date])} indent />
                  ))}
                </div>;
              })}
            </div>;
          })}
          {groups.length === 0 && (
            <p className="px-2 py-3 text-[12px] text-muted-foreground">No dates available.</p>
          )}
        </div>
        )}
      </div>
      <DropdownMenuSeparator className="shrink-0" />
      <div className="shrink-0 p-1">
        <Button type="button" size="sm" className="w-full" onClick={apply}>Apply filter</Button>
      </div>
    </DropdownMenuContent>
  </DropdownMenu>;
}

function DateGroupRow({ label, open, checked, partial, indent, onToggleOpen, onToggleChecked }: {
  label: string;
  open: boolean;
  checked: boolean;
  partial: boolean;
  indent?: boolean;
  onToggleOpen: () => void;
  onToggleChecked: () => void;
}) {
  const checkboxRef = React.useRef<HTMLInputElement>(null);
  React.useEffect(() => {
    if (checkboxRef.current) checkboxRef.current.indeterminate = partial;
  }, [partial]);
  return <div className={`flex h-8 items-center gap-1.5 px-2 text-[12px] hover:bg-accent ${indent ? 'pl-7' : ''}`}>
    <button type="button" className="rounded p-0.5 text-muted-foreground hover:text-foreground" onClick={(event) => { event.preventDefault(); event.stopPropagation(); onToggleOpen(); }} aria-label={open ? `Collapse ${label}` : `Expand ${label}`}>
      {open ? <ChevronDown className="size-3.5" aria-hidden="true" /> : <ChevronRight className="size-3.5" aria-hidden="true" />}
    </button>
    <input
      ref={checkboxRef}
      type="checkbox"
      checked={checked}
      className="size-3.5 rounded border-input"
      onClick={(event) => event.stopPropagation()}
      onChange={() => onToggleChecked()}
      aria-label={`Keep ${label}`}
    />
    <span className="truncate">{label}</span>
  </div>;
}

function DateLeaf({ date, checked, indent, onToggle }: { date: string; checked: boolean; indent?: boolean; onToggle: () => void }) {
  return <label className={`flex h-8 cursor-pointer items-center gap-2 px-2 text-[12px] hover:bg-accent ${indent ? 'pl-14' : ''}`} onClick={(event) => event.stopPropagation()}>
    <input type="checkbox" checked={checked} className="size-3.5 rounded border-input" onChange={onToggle} />
    <span className="truncate">{formatDate(date)}</span>
  </label>;
}
function Cell({ children, className, strong }: React.PropsWithChildren<{ className?: string; strong?: boolean }>) { return <TableCell className={`${className ?? ''} ${strong ? 'font-semibold' : ''}`}>{children}</TableCell>; }
function EditCell({ children }: React.PropsWithChildren) { return <TableCell className="bg-primary-soft/20">{children}</TableCell>; }
function Stack({ children }: React.PropsWithChildren) { return <div className="flex min-w-44 flex-col gap-1.5">{children}</div>; }
function Muted({ children }: React.PropsWithChildren) { return <span className="text-muted-foreground">{children}</span>; }

function DateControl({ id, label, value, min, onChange }: { id: string; label: string; value: string; min?: string; onChange: (value: string) => void }) {
  return <label htmlFor={id} className="flex flex-col gap-1 text-left">
    <span className="text-[11px] font-medium text-muted-foreground">{label}</span>
    <Input id={id} type="date" value={value} min={min} required={label === 'Start date'} className="h-8 w-40 text-[12px]" onChange={(event) => {
      if (label !== 'Start date' || event.target.value) onChange(event.target.value);
    }} />
  </label>;
}

function rowFilterValues(row: AllocationSpreadsheetRow): Record<FilterKey, string[]> {
  const theory = row.sessions.filter((item) => item.stream === 'THEORY');
  const practical = row.sessions.filter((item) => item.stream === 'PRACTICAL');
  const sessionValues = (items: AllocationSpreadsheetSession[], field: 'schedule' | 'classroom' | 'capacity' | 'trainer', empty = '—') => {
    const values = items.map((item) => {
      if (field === 'schedule') return `${friendly(item.weekday)} · ${item.start_time}–${item.end_time}`;
      if (field === 'classroom') return item.classroom || '—';
      if (field === 'capacity') return String(item.classroom_capacity ?? (item.delivery_mode === 'VIRTUAL' ? 'Virtual' : '—'));
      return item.trainer || '—';
    });
    return values.length ? [...new Set(values)] : [empty];
  };
  return {
    sl_no: [String(row.sl_no)],
    college: [row.college || '—'],
    campus: [row.campus || '—'],
    qualification_code: [row.qualification_code || '—'],
    qualification_title: [row.qualification_title || '—'],
    duration_weeks: [String(row.duration_weeks)],
    group: [row.group || '—'],
    intakes: row.intakes.length ? row.intakes : ['—'],
    total_students: [String(row.total_students)],
    coe_students: [String(row.coe_students)],
    non_coe_students: [String(row.non_coe_students)],
    unit_code: [row.unit_code || '—'],
    unit_title: [row.unit_title || '—'],
    unit_start_date: [row.unit_start_date],
    unit_end_date: [row.unit_end_date],
    uoc_type: [friendly(row.uoc_type)],
    mode_of_delivery: [row.mode_of_delivery || '—'],
    theory_schedule: sessionValues(theory, 'schedule'),
    theory_classroom: sessionValues(theory, 'classroom'),
    theory_capacity: sessionValues(theory, 'capacity'),
    theory_trainer: sessionValues(theory, 'trainer'),
    practical_classroom: sessionValues(practical, 'classroom'),
    practical_capacity: sessionValues(practical, 'capacity'),
    practical_schedule: sessionValues(practical, 'schedule', row.uoc_type === 'THEORY_ONLY' ? 'Not required' : '—'),
    practical_trainer: sessionValues(practical, 'trainer'),
  };
}

type DateFilterGroup = {
  year: string;
  months: { month: string; label: string; dates: string[] }[];
};

function groupDateOptions(options: string[]): DateFilterGroup[] {
  const byYear = new Map<string, Map<string, string[]>>();
  const dates = [...new Set(options.filter((value) => /^\d{4}-\d{2}-\d{2}$/.test(value)))].sort();
  for (const date of dates) {
    const [year, month] = date.split('-');
    if (!byYear.has(year)) byYear.set(year, new Map());
    const months = byYear.get(year)!;
    if (!months.has(month)) months.set(month, []);
    months.get(month)!.push(date);
  }
  return [...byYear.entries()].map(([year, months]) => ({
    year,
    months: [...months.entries()].map(([month, monthDates]) => ({
      month,
      label: dateMonthLabel(`${year}-${month}-01`),
      dates: monthDates,
    })),
  }));
}

function dateMonthLabel(value: string) {
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? value : MONTH_FORMATTER.format(date);
}

function rowMatchesFilters(row: AllocationSpreadsheetRow, filters: Filters): boolean {
  return rowMatchesFiltersExcept(row, filters);
}

function rowMatchesFiltersExcept(row: AllocationSpreadsheetRow, filters: Filters, except?: FilterKey): boolean {
  const values = rowFilterValues(row);
  return (Object.entries(filters) as [FilterKey, string[]][]).every(([key, selected]) => {
    return key === except || selected.some((value) => values[key].includes(value));
  });
}

function buildFilterOptions(rows: AllocationSpreadsheetRow[], filters: Filters): FilterOptions {
  const keys: FilterKey[] = [
    'sl_no', 'college', 'campus', 'qualification_code', 'qualification_title', 'duration_weeks', 'group',
    'intakes', 'total_students', 'coe_students', 'non_coe_students', 'unit_code', 'unit_title',
    'unit_start_date', 'unit_end_date', 'uoc_type', 'mode_of_delivery', 'theory_schedule',
    'theory_classroom', 'theory_capacity', 'theory_trainer', 'practical_classroom',
    'practical_capacity', 'practical_schedule', 'practical_trainer',
  ];
  const output = {} as FilterOptions;
  for (const key of keys) {
    const values = new Set<string>();
    for (const row of rows) {
      // This field itself stays open for editing. Every other active filter
      // narrows its choices to values that can still produce a visible row.
      if (!rowMatchesFiltersExcept(row, filters, key)) continue;
      rowFilterValues(row)[key].forEach((value) => values.add(value));
    }
    output[key] = [...values].sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
  }
  return output;
}
