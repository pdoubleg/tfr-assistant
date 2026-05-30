"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  FileSpreadsheet,
  Hash,
  Info,
  Loader2,
  Plus,
  Save,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type {
  BatchInputMode,
  BatchReviewInput,
  BatchTemplatePayload,
  BatchTemplateRecord,
  FormCatalogEntry,
} from "@/lib/types";
import { cn } from "@/lib/utils";

type ColumnMap = {
  claim_number?: string;
  effective_date?: string;
  instructions?: string;
};

interface BatchRunDialogProps {
  open: boolean;
  template?: BatchTemplateRecord | null;
  mode?: "create" | "edit" | "duplicate";
  forms: FormCatalogEntry[];
  locked?: boolean;
  saving?: boolean;
  onClose: () => void;
  onSave: (payload: BatchTemplatePayload) => Promise<void> | void;
}

interface DialogState {
  name: string;
  description: string;
  formKey: string;
  synthetic: boolean;
  synthetic_count: number;
  input_mode: BatchInputMode;
  generation_prompt: string;
  excel_column_map: ColumnMap;
  items: BatchReviewInput[];
}

const emptyItem = (): BatchReviewInput => ({
  claim_number: "",
  effective_date: "",
  instructions: "",
  prompt: "",
  source_file_ids: [],
});

const initialState = (forms: FormCatalogEntry[], template?: BatchTemplateRecord | null): DialogState => {
  const firstForm = forms[0];
  const formKey = template
    ? `${template.form_id}@${template.form_version}`
    : firstForm
      ? `${firstForm.id}@${firstForm.version}`
      : "tfr_default@v0.1";

  return {
    name: template?.name ?? "",
    description: template?.description ?? "",
    formKey,
    synthetic: template?.synthetic ?? false,
    synthetic_count: template?.synthetic_count || 3,
    input_mode: template?.input_mode ?? (template?.synthetic ? "synthetic" : "manual"),
    generation_prompt: template?.generation_prompt ?? "",
    excel_column_map: template?.excel_column_map ?? {},
    items: template?.items?.length ? template.items : [emptyItem()],
  };
};

function splitFormKey(formKey: string): { form_id: string; form_version: string } {
  const [form_id, form_version] = formKey.split("@");
  return {
    form_id: form_id || "tfr_default",
    form_version: form_version || "v0.1",
  };
}

function normalizeCell(value: unknown): string {
  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }
  return String(value ?? "").trim();
}

function parseDelimitedRows(text: string): string[][] {
  const rows: string[][] = [];
  let field = "";
  let row: string[] = [];
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];

    if (char === '"' && quoted && next === '"') {
      field += '"';
      index += 1;
      continue;
    }
    if (char === '"') {
      quoted = !quoted;
      continue;
    }
    if (char === "," && !quoted) {
      row.push(field);
      field = "";
      continue;
    }
    if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") {
        index += 1;
      }
      row.push(field);
      rows.push(row);
      field = "";
      row = [];
      continue;
    }
    field += char;
  }

  row.push(field);
  rows.push(row);
  return rows.filter((candidate) => candidate.some((cell) => cell.trim()));
}

function rowsToObjects(rows: string[][]): {
  headers: string[];
  records: Array<Record<string, string>>;
} {
  const [headerRow, ...bodyRows] = rows;
  const headers = (headerRow ?? []).map((value, index) => value.trim() || `Column ${index + 1}`);
  const records = bodyRows.map((row) =>
    headers.reduce<Record<string, string>>((record, header, index) => {
      record[header] = normalizeCell(row[index]);
      return record;
    }, {}),
  );
  return { headers, records };
}

function inferColumn(headers: string[], patterns: RegExp[]): string {
  return headers.find((header) => patterns.some((pattern) => pattern.test(header))) ?? "";
}

function buildItemsFromRows(
  rows: Array<Record<string, string>>,
  columnMap: ColumnMap,
): BatchReviewInput[] {
  return rows
    .map((row) => ({
      claim_number: normalizeCell(row[columnMap.claim_number ?? ""]),
      effective_date: normalizeCell(row[columnMap.effective_date ?? ""]),
      instructions: normalizeCell(row[columnMap.instructions ?? ""]),
      prompt: normalizeCell(row[columnMap.instructions ?? ""]),
      source_file_ids: [],
    }))
    .filter((item) => item.claim_number || item.effective_date || item.instructions);
}

function validateUploadedRows({
  headers,
  rows,
  columnMap,
}: {
  headers: string[];
  rows: Array<Record<string, string>>;
  columnMap: ColumnMap;
}): string {
  if (!rows.length) {
    return "Upload a spreadsheet with at least one review row, or switch to Direct Entry.";
  }

  const claimColumn = columnMap.claim_number?.trim();
  if (!claimColumn) {
    return "Choose the Claim Number Column Name before creating the run.";
  }

  if (!headers.includes(claimColumn)) {
    return `The Claim Number Column Name "${claimColumn}" was not found in the uploaded spreadsheet.`;
  }

  const blankClaimRows = rows.filter((row) => !normalizeCell(row[claimColumn]));
  if (blankClaimRows.length) {
    return `${blankClaimRows.length} spreadsheet row${blankClaimRows.length === 1 ? "" : "s"} missing a claim number. Fill those cells or remove the rows.`;
  }

  const optionalColumns = [
    ["Effective Date Column Name", columnMap.effective_date],
    ["Additional Instructions Column Name", columnMap.instructions],
  ] as const;
  for (const [label, column] of optionalColumns) {
    const trimmed = column?.trim();
    if (trimmed && !headers.includes(trimmed)) {
      return `The ${label} "${trimmed}" was not found in the uploaded spreadsheet.`;
    }
  }

  return "";
}

function useBodyScrollLock(open: boolean) {
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);
}

export function BatchRunDialog({
  open,
  template,
  mode,
  forms,
  locked = false,
  saving = false,
  onClose,
  onSave,
}: BatchRunDialogProps) {
  const [state, setState] = useState<DialogState>(() => initialState(forms, template));
  const [uploadedHeaders, setUploadedHeaders] = useState<string[]>([]);
  const [uploadedRows, setUploadedRows] = useState<Array<Record<string, string>>>([]);
  const [uploadName, setUploadName] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [formError, setFormError] = useState("");
  const dialogMode = mode ?? (template ? "edit" : "create");
  const isEditing = dialogMode === "edit";
  const isDuplicate = dialogMode === "duplicate";
  const disabled = locked || saving;
  const selectedForm = forms.find((form) => `${form.id}@${form.version}` === state.formKey);

  useBodyScrollLock(open);

  useEffect(() => {
    if (!open) return;
    setState(initialState(forms, template));
    setUploadedHeaders([]);
    setUploadedRows([]);
    setUploadName("");
    setUploadError("");
    setFormError("");
  }, [forms, open, template]);

  const uploadItems = useMemo(
    () =>
      uploadedRows.length
        ? buildItemsFromRows(uploadedRows, state.excel_column_map)
        : state.items,
    [state.excel_column_map, state.items, uploadedRows],
  );

  if (!open) {
    return null;
  }

  const setItem = (index: number, patch: Partial<BatchReviewInput>) => {
    setState((current) => ({
      ...current,
      items: current.items.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item,
      ),
    }));
  };

  const addItem = () => {
    setState((current) => ({ ...current, items: [...current.items, emptyItem()] }));
  };

  const removeItem = (index: number) => {
    setState((current) => ({
      ...current,
      items: current.items.length === 1
        ? [emptyItem()]
        : current.items.filter((_, itemIndex) => itemIndex !== index),
    }));
  };

  const setInputMode = (mode: BatchInputMode) => {
    setState((current) => ({
      ...current,
      input_mode: mode,
      synthetic: mode === "synthetic",
    }));
  };

  const parseUpload = async (file: File) => {
    setUploadError("");
    setUploadName(file.name);

    try {
      let rows: string[][];
      if (file.name.toLowerCase().endsWith(".csv")) {
        rows = parseDelimitedRows(await file.text());
      } else {
        const XLSX = await import("xlsx");
        const workbook = XLSX.read(await file.arrayBuffer(), {
          type: "array",
          cellDates: true,
        });
        const sheet = workbook.Sheets[workbook.SheetNames[0]];
        rows = XLSX.utils.sheet_to_json(sheet, {
          header: 1,
          blankrows: false,
          defval: "",
        }) as string[][];
      }

      const parsed = rowsToObjects(rows);
      if (!parsed.headers.length || !parsed.records.length) {
        throw new Error("The file did not include a header row and at least one review row.");
      }

      setUploadedHeaders(parsed.headers);
      setUploadedRows(parsed.records);
      setState((current) => ({
        ...current,
        input_mode: "upload",
        synthetic: false,
        excel_column_map: {
          claim_number:
            current.excel_column_map.claim_number ||
            inferColumn(parsed.headers, [/claim/i, /claim.*number/i]),
          effective_date:
            current.excel_column_map.effective_date ||
            inferColumn(parsed.headers, [/effective/i, /date/i]),
          instructions:
            current.excel_column_map.instructions ||
            inferColumn(parsed.headers, [/instruction/i, /note/i, /comment/i]),
        },
      }));
    } catch (error) {
      setUploadedHeaders([]);
      setUploadedRows([]);
      setUploadError(error instanceof Error ? error.message : "Unable to read that file.");
    }
  };

  const handleSave = async () => {
    const name = state.name.trim();
    const description = state.description.trim();
    const { form_id, form_version } = splitFormKey(state.formKey);
    const inputMode = state.synthetic ? "synthetic" : state.input_mode;
    if (inputMode === "upload") {
      const hasPersistedUploadItems =
        !uploadedRows.length &&
        state.items.some((item) => item.claim_number || item.effective_date || item.instructions);
      const spreadsheetError = hasPersistedUploadItems
        ? ""
        : validateUploadedRows({
            headers: uploadedHeaders,
            rows: uploadedRows,
            columnMap: state.excel_column_map,
          });
      if (spreadsheetError) {
        setFormError(spreadsheetError);
        return;
      }
    }

    const items = inputMode === "upload" ? uploadItems : state.items;
    const usableItems = items
      .map((item) => ({
        ...item,
        claim_number: item.claim_number.trim(),
        effective_date: item.effective_date?.trim() ?? "",
        instructions: item.instructions?.trim() ?? "",
        prompt: item.prompt?.trim() || item.instructions?.trim() || "",
      }))
      .filter((item) => item.claim_number || item.effective_date || item.instructions);

    if (!name) {
      setFormError("Run name is required.");
      return;
    }
    if (!state.synthetic && !usableItems.length) {
      setFormError("Add at least one review.");
      return;
    }
    if (!state.synthetic && usableItems.some((item) => !item.claim_number)) {
      setFormError("Each review needs a claim number unless synthetic mode is enabled.");
      return;
    }
    if (state.synthetic && state.synthetic_count <= 0) {
      setFormError("Synthetic mode needs a review count.");
      return;
    }

    setFormError("");
    await onSave({
      name,
      description,
      form_id,
      form_version,
      synthetic: state.synthetic,
      synthetic_count: state.synthetic ? state.synthetic_count : 0,
      input_mode: inputMode,
      generation_prompt: state.synthetic ? state.generation_prompt.trim() : "",
      prompt_ref: null,
      excel_column_map: inputMode === "upload" ? state.excel_column_map : {},
      items: state.synthetic ? [] : usableItems,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 p-4 backdrop-blur-sm">
      <div
        aria-modal="true"
        role="dialog"
        className="flex max-h-[94vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border bg-card shadow-2xl"
      >
        <div className="flex shrink-0 items-start gap-4 border-b bg-secondary/35 px-6 py-5">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border bg-background text-primary">
            {state.synthetic ? <Sparkles className="h-6 w-6" /> : <FileSpreadsheet className="h-6 w-6" />}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold">
                {isEditing ? "Edit Batch Audit Run" : isDuplicate ? "Configure Production Batch" : "Create Batch Audit Run"}
              </h2>
              {locked ? <Badge variant="warning">Locked</Badge> : null}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {selectedForm ? `${selectedForm.title} · ${selectedForm.questionCount} questions` : "Batch audit setup"}
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="ml-auto h-9 w-9"
            onClick={onClose}
            aria-label="Close batch dialog"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto px-6 py-6">
          {locked ? (
            <div className="mb-4 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              <Info className="mt-0.5 h-4 w-4 shrink-0" />
              <span>This configuration can be inspected, but edits are locked while the run is active.</span>
            </div>
          ) : null}

          <div className="grid gap-5 md:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
            <div className="grid min-w-0 gap-2">
              <label htmlFor="batch-name" className="text-sm font-medium">
                Run Name
              </label>
              <Input
                id="batch-name"
                value={state.name}
                onChange={(event) => setState((current) => ({ ...current, name: event.target.value }))}
                disabled={disabled || isEditing}
                placeholder="May file review pilot"
                className="h-12 text-base"
                autoFocus
              />
            </div>
            <div className="grid min-w-0 gap-2">
              <label htmlFor="batch-form" className="text-sm font-medium">
                Registered Form
              </label>
              <select
                id="batch-form"
                value={state.formKey}
                onChange={(event) => setState((current) => ({ ...current, formKey: event.target.value }))}
                disabled={disabled}
                className="h-12 w-full min-w-0 rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              >
                {forms.map((form) => (
                  <option key={`${form.id}@${form.version}`} value={`${form.id}@${form.version}`}>
                    {form.title} - {form.id}@{form.version}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">
                Runs use the active prompt configured on this form version.
              </p>
            </div>
            <div className="grid gap-2 md:col-span-2">
              <label htmlFor="batch-description" className="text-sm font-medium">
                Description
              </label>
              <Textarea
                id="batch-description"
                value={state.description}
                onChange={(event) =>
                  setState((current) => ({ ...current, description: event.target.value }))
                }
                disabled={disabled}
                className="min-h-[104px] text-base"
                placeholder="Scope, audience, or notes for this run"
              />
            </div>
          </div>

          <div className="mt-5 grid gap-3">
            <div className="flex flex-wrap gap-2">
              {(["manual", "upload", "synthetic"] as BatchInputMode[]).map((mode) => {
                const active = state.synthetic ? mode === "synthetic" : state.input_mode === mode;
                const Icon = mode === "synthetic" ? Sparkles : mode === "upload" ? Upload : Hash;
                return (
                  <button
                    key={mode}
                    type="button"
                    disabled={disabled}
                    onClick={() => setInputMode(mode)}
                    className={cn(
                      "inline-flex h-9 items-center gap-2 rounded-md border px-3 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                      active
                        ? "border-primary bg-primary text-primary-foreground"
                        : "bg-background hover:bg-secondary",
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {mode === "manual" ? "Direct Entry" : mode === "upload" ? "Spreadsheet" : "Synthetic"}
                  </button>
                );
              })}
            </div>

            {state.synthetic ? (
              <div className="rounded-lg border bg-background p-4">
                <div className="grid gap-4 md:grid-cols-[240px_minmax(0,1fr)]">
                  <div className="grid gap-2">
                  <label htmlFor="synthetic-count" className="text-sm font-medium">
                    Number of Reviews
                  </label>
                  <Input
                    id="synthetic-count"
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    value={state.synthetic_count ? String(state.synthetic_count) : ""}
                    onChange={(event) => {
                      const digits = event.target.value.replace(/\D/g, "");
                      setState((current) => ({
                        ...current,
                        synthetic_count: digits ? Number(digits) : 0,
                      }));
                    }}
                    disabled={disabled}
                    placeholder="10"
                  />
                  </div>
                  <div className="grid gap-2">
                    <label htmlFor="synthetic-prompt" className="text-sm font-medium">
                      Generation Instructions
                    </label>
                    <Textarea
                      id="synthetic-prompt"
                      value={state.generation_prompt}
                      onChange={(event) =>
                        setState((current) => ({ ...current, generation_prompt: event.target.value }))
                      }
                      disabled={disabled}
                      className="min-h-24"
                      placeholder="Make this a Meets rating with all Yes"
                    />
                  </div>
                </div>
              </div>
            ) : state.input_mode === "upload" ? (
              <div className="rounded-lg border bg-background p-4">
                <div className="grid gap-4">
                  <div className="grid gap-2">
                    <label htmlFor="batch-upload" className="text-sm font-medium">
                      Excel or CSV File
                    </label>
                    <Input
                      id="batch-upload"
                      type="file"
                      accept=".xlsx,.xls,.csv"
                      disabled={disabled}
                      onChange={(event) => {
                        const file = event.currentTarget.files?.[0];
                        if (file) void parseUpload(file);
                      }}
                    />
                    {uploadName ? (
                      <p className="text-xs text-muted-foreground">
                        {uploadName} · {uploadedRows.length} rows
                      </p>
                    ) : null}
                    {uploadError ? <p className="text-xs text-destructive">{uploadError}</p> : null}
                  </div>

                  <div className="grid gap-3 md:grid-cols-3">
                    <ColumnNameInput
                      id="claim-column"
                      label="Claim Number Column Name"
                      value={state.excel_column_map.claim_number ?? ""}
                      headers={uploadedHeaders}
                      disabled={disabled}
                      placeholder="Claim Number"
                      onChange={(value) =>
                        setState((current) => ({
                          ...current,
                          excel_column_map: { ...current.excel_column_map, claim_number: value },
                        }))
                      }
                    />
                    <ColumnNameInput
                      id="effective-column"
                      label="Effective Date Column Name"
                      value={state.excel_column_map.effective_date ?? ""}
                      headers={uploadedHeaders}
                      disabled={disabled}
                      optional
                      placeholder="Effective Date"
                      onChange={(value) =>
                        setState((current) => ({
                          ...current,
                          excel_column_map: { ...current.excel_column_map, effective_date: value },
                        }))
                      }
                    />
                    <ColumnNameInput
                      id="instructions-column"
                      label="Additional Instructions Column Name"
                      value={state.excel_column_map.instructions ?? ""}
                      headers={uploadedHeaders}
                      disabled={disabled}
                      optional
                      placeholder="Instructions"
                      onChange={(value) =>
                        setState((current) => ({
                          ...current,
                          excel_column_map: { ...current.excel_column_map, instructions: value },
                        }))
                      }
                    />
                  </div>

                  {uploadItems.length ? (
                    <div className="max-h-44 overflow-y-auto rounded-md border">
                      {uploadItems.slice(0, 8).map((item, index) => (
                        <div
                          key={`${item.claim_number}-${index}`}
                          className="grid gap-2 border-b px-3 py-2 text-sm last:border-b-0 md:grid-cols-[1fr_120px_1fr]"
                        >
                          <span className="truncate font-medium">{item.claim_number || "Missing claim"}</span>
                          <span className="text-muted-foreground">{item.effective_date || "No date"}</span>
                          <span className="truncate text-muted-foreground">{item.instructions || "No instructions"}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            ) : (
              <div className="rounded-lg border bg-background">
                <div className="grid gap-3 border-b bg-secondary/35 px-4 py-3 text-xs font-medium text-muted-foreground md:grid-cols-[minmax(150px,1fr)_210px_minmax(180px,0.9fr)_40px]">
                  <span>Claim Number</span>
                  <span>Effective Date</span>
                  <span>Additional Instructions</span>
                  <span />
                </div>
                <div className="divide-y">
                  {state.items.map((item, index) => (
                    <div
                      key={index}
                      className="grid gap-3 px-4 py-3 md:grid-cols-[minmax(150px,1fr)_210px_minmax(180px,0.9fr)_40px]"
                    >
                      <label className="relative">
                        <Hash className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                        <Input
                          value={item.claim_number}
                          onChange={(event) => setItem(index, { claim_number: event.target.value })}
                          disabled={disabled}
                          className="pl-8"
                          placeholder="012345678"
                        />
                      </label>
                      <label className="relative">
                        <CalendarDays className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-primary" />
                        <Input
                          type="date"
                          value={item.effective_date ?? ""}
                          onChange={(event) => setItem(index, { effective_date: event.target.value })}
                          disabled={disabled}
                          className="date-input pl-8 dark:scheme-dark"
                        />
                      </label>
                      <Input
                        value={item.instructions ?? ""}
                        onChange={(event) =>
                          setItem(index, {
                            instructions: event.target.value,
                            prompt: event.target.value,
                          })
                        }
                        disabled={disabled}
                        placeholder="Optional"
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-9 w-9"
                        disabled={disabled}
                        onClick={() => removeItem(index)}
                        aria-label="Remove review"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
                <div className="border-t px-4 py-3">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    disabled={disabled}
                    onClick={addItem}
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add Review
                  </Button>
                </div>
              </div>
            )}
          </div>

          {formError ? <p className="mt-4 text-sm text-destructive">{formError}</p> : null}
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t bg-secondary/35 px-6 py-5">
          <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
            {locked ? "Close" : "Cancel"}
          </Button>
          {!locked ? (
            <Button type="button" className="min-w-32 gap-2" onClick={() => void handleSave()} disabled={saving}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {isEditing ? "Save Changes" : isDuplicate ? "Save Configuration" : "Create Run"}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ColumnNameInput({
  id,
  label,
  value,
  headers,
  placeholder,
  optional = false,
  disabled = false,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  headers: string[];
  placeholder?: string;
  optional?: boolean;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const dataListId = `${id}-options`;

  return (
    <div className="grid min-w-0 gap-2">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
        {optional ? <span className="ml-1 text-xs font-normal text-muted-foreground">optional</span> : null}
      </label>
      <Input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        list={headers.length ? dataListId : undefined}
        placeholder={placeholder}
        className="h-10"
      />
      {headers.length ? (
        <datalist id={dataListId}>
          {headers.map((header) => (
            <option key={header} value={header} />
          ))}
        </datalist>
      ) : null}
      {headers.length ? (
        <p className="text-xs text-muted-foreground">
          Type a column name or choose one from the uploaded headers.
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">
          Enter the exact header from the spreadsheet.
        </p>
      )}
    </div>
  );
}
