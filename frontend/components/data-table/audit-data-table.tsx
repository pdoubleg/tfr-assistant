"use client";

import {
  getCoreRowModel,
  getFacetedRowModel,
  getFacetedUniqueValues,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnFiltersState,
  type OnChangeFn,
  type PaginationState,
  type RowSelectionState,
  type SortingState,
  type VisibilityState,
} from "@tanstack/react-table";
import {
  Check,
  ClipboardCheck,
  Copy,
  Download,
  Eye,
  FileSpreadsheet,
  Loader2,
  Pencil,
  RefreshCw,
  Search,
  Shrink,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type InputHTMLAttributes, type ReactNode } from "react";

import { DataTable } from "@/components/data-table/data-table";
import { DataTableColumnHeader } from "@/components/data-table/data-table-column-header";
import { DataTableViewOptions } from "@/components/data-table/data-table-view-options";
import { AuditResultEditSheet } from "@/components/data-table/audit-result-edit-sheet";
import { EvalRoleBadge } from "@/components/dashboard/eval-role-badge";
import { FormViewerSheet } from "@/components/dashboard/form-viewer-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  evalRoleLabel,
  formatDateTime,
  resultVersionLabels,
  type DashboardReviewRow,
} from "@/lib/dashboard-data";
import { buildCsv, buildTsv, downloadText, downloadWorkbook, type ExportColumn } from "@/lib/table-export";
import type { AuditFormResult, HomeTableContext, SelectedHomeRowContext } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTfrAgent } from "@/hooks/use-tfr-agent";

type AuditTableDensity = "compact" | "normal";

interface AuditDataTableSettings {
  columnVisibility?: VisibilityState;
  columnFilters?: ColumnFiltersState;
  density?: AuditTableDensity;
  globalFilter?: string;
  pagination?: PaginationState;
  rowSelection?: RowSelectionState;
  sorting?: SortingState;
  pageSize?: number;
}

const settingsKey = "tfr-audit-data-table-settings";
const defaultSorting: SortingState = [{ id: "createdAt", desc: true }];

const defaultColumnVisibility: VisibilityState = {
  reviewId: false,
  batchId: false,
  updatedAt: false,
  evalRole: false,
};

const defaultColumnSize = 112;
const idColumnSize = 260;

const exportColumns: ExportColumn<DashboardReviewRow>[] = [
  { header: "Review ID", value: (row) => row.reviewId },
  { header: "Created", value: (row) => formatDateTime(row.createdAt) },
  { header: "Updated", value: (row) => formatDateTime(row.updatedAt) },
  { header: "Claim Number", value: (row) => row.claimNumber },
  { header: "Batch Run", value: (row) => row.runName },
  { header: "Batch ID", value: (row) => row.batchId },
  { header: "Source", value: (row) => row.source },
  { header: "Eval Role", value: (row) => evalRoleLabel(row.evalResultRole, row.evalReferenceKind) },
  { header: "Form", value: (row) => row.formKey },
  { header: "Result Version", value: (row) => resultVersionLabels[row.resultVersion] },
  { header: "Title", value: (row) => row.title },
  { header: "Description", value: (row) => row.description },
  { header: "Outcome", value: (row) => row.outcome },
  { header: "Outcome Justification", value: (row) => row.outcomeJustification },
  { header: "Questions", value: (row) => row.questionCount },
  { header: "Yes Count", value: (row) => row.yesCount },
  { header: "No Count", value: (row) => row.noCount },
  { header: "Driver Count", value: (row) => row.driverCount },
  { header: "Edited", value: (row) => (row.edited ? "Yes" : "No") },
];

function loadSettings(): AuditDataTableSettings {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(settingsKey) ?? "{}") as AuditDataTableSettings;
  } catch {
    return {};
  }
}

function outcomeLabel(outcome: string): string {
  return outcome === "Does Not Meet" ? "DNM" : outcome;
}

function SelectFilter({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <label className="min-w-[132px] space-y-1">
      <span className="block text-[10px] font-semibold uppercase text-muted-foreground">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {children}
      </select>
    </label>
  );
}

function IndeterminateCheckbox({
  indeterminate,
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { indeterminate?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.indeterminate = Boolean(indeterminate) && !props.checked;
    }
  }, [indeterminate, props.checked]);

  return (
    <input
      ref={ref}
      type="checkbox"
      className={cn("h-4 w-4 rounded border-input accent-primary", className)}
      {...props}
    />
  );
}

function uniqueSorted(values: Iterable<string>) {
  return Array.from(values)
    .filter(Boolean)
    .sort((first, second) => first.localeCompare(second, undefined, { numeric: true }));
}

function rowSearchText(row: DashboardReviewRow): string {
  return [
    row.reviewId,
    row.batchId,
    row.claimNumber,
    row.runName,
    row.formKey,
    row.title,
    row.description,
    row.outcome,
    row.source,
    evalRoleLabel(row.evalResultRole, row.evalReferenceKind),
    row.outcomeJustification,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function auditRowId(row: DashboardReviewRow): string {
  return `${row.reviewId}:${row.resultVersion}`;
}

function selectedHomeRowFromDashboardRow(row: DashboardReviewRow): SelectedHomeRowContext {
  return {
    row_id: auditRowId(row),
    review_id: row.rowKind === "dataset_case" ? "" : row.reviewId,
    result_version: row.resultVersion,
    form_id: row.formId,
    form_version: row.formVersion,
    form_kind: row.formKind,
    form_key: row.formKey,
    claim_number: row.claimNumber,
    batch_id: row.batchId,
    run_name: row.runName,
    source: row.source,
    outcome: row.outcome,
    title: row.title,
    created_at: row.createdAt,
    updated_at: row.updatedAt,
    question_count: row.questionCount,
    no_count: row.noCount,
    driver_count: row.driverCount,
    edited: row.edited,
    row_kind: row.rowKind ?? "review",
    dataset_id: row.datasetId ?? "",
    dataset_case_id: row.datasetCaseId ?? "",
    ground_truth_id: row.groundTruthId ?? "",
    reference_kind: row.referenceKind ?? row.evalReferenceKind ?? "",
  };
}

export function AuditDataTable({
  rows,
  totalCount,
  loading,
  onRefresh,
  onSaveForm,
  onFeedbackSubmitted,
}: {
  rows: DashboardReviewRow[];
  totalCount: number;
  loading?: boolean;
  onRefresh: () => void;
  onSaveForm: (reviewId: string, form: AuditFormResult) => Promise<void>;
  onFeedbackSubmitted?: (reviewId: string) => void | Promise<void>;
}) {
  const { setHomeTableContext, setState: setAgentState } = useTfrAgent();
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [sorting, setSorting] = useState<SortingState>(defaultSorting);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(defaultColumnVisibility);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [globalFilter, setGlobalFilter] = useState("");
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [density, setDensity] = useState<AuditTableDensity>("normal");
  const [copyStatus, setCopyStatus] = useState<"idle" | "success">("idle");
  const [viewRow, setViewRow] = useState<DashboardReviewRow | null>(null);
  const [editRow, setEditRow] = useState<DashboardReviewRow | null>(null);

  useEffect(() => {
    const settings = loadSettings();
    setSorting(settings.sorting ?? defaultSorting);
    setColumnFilters(settings.columnFilters ?? []);
    setColumnVisibility({
      ...defaultColumnVisibility,
      ...(settings.columnVisibility ?? {}),
    });
    setGlobalFilter(settings.globalFilter ?? "");
    setPagination({
      pageIndex: settings.pagination?.pageIndex ?? 0,
      pageSize: settings.pagination?.pageSize ?? settings.pageSize ?? 25,
    });
    setRowSelection(settings.rowSelection ?? {});
    setDensity(settings.density ?? "normal");
    setSettingsLoaded(true);
  }, []);

  useEffect(() => {
    if (!settingsLoaded) return;
    window.localStorage.setItem(
      settingsKey,
      JSON.stringify({
        columnVisibility,
        columnFilters,
        density,
        globalFilter,
        pagination,
        rowSelection,
        sorting,
      } satisfies AuditDataTableSettings),
    );
  }, [columnFilters, columnVisibility, density, globalFilter, pagination, rowSelection, settingsLoaded, sorting]);

  const syncAgentContext = useCallback(
    (row: DashboardReviewRow) => {
      setAgentState((current) => ({
        ...current,
        active_route: "/",
        active_review_id: row.rowKind === "dataset_case" ? null : row.reviewId,
        selected_form_ids: [row.formKey],
      }));
    },
    [setAgentState],
  );

  const openView = useCallback(
    (row: DashboardReviewRow) => {
      syncAgentContext(row);
      setViewRow(row);
    },
    [syncAgentContext],
  );

  const openEdit = useCallback(
    (row: DashboardReviewRow) => {
      syncAgentContext(row);
      setEditRow(row);
    },
    [syncAgentContext],
  );

  const sourceOptions = useMemo(() => uniqueSorted(new Set(rows.map((row) => row.source))), [rows]);
  const formOptions = useMemo(() => uniqueSorted(new Set(rows.map((row) => row.formKey))), [rows]);
  const evalRoleOptions = useMemo(
    () => uniqueSorted(new Set(rows.map((row) => evalRoleLabel(row.evalResultRole, row.evalReferenceKind)))),
    [rows],
  );

  const columns = useMemo<ColumnDef<DashboardReviewRow>[]>(
    () => [
      {
        id: "select",
        size: 44,
        enableSorting: false,
        enableHiding: false,
        header: ({ table }) => (
          <IndeterminateCheckbox
            checked={table.getIsAllPageRowsSelected()}
            indeterminate={table.getIsSomePageRowsSelected()}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
            aria-label="Select visible rows"
          />
        ),
        cell: ({ row }) => (
          <IndeterminateCheckbox
            checked={row.getIsSelected()}
            disabled={!row.getCanSelect()}
            onChange={row.getToggleSelectedHandler()}
            aria-label={`Select ${row.original.title}`}
          />
        ),
        meta: {
          label: "Select",
          align: "center",
          headerClassName: "w-11",
          cellClassName: "w-11",
        },
      },
      {
        id: "actions",
        size: 92,
        enableSorting: false,
        enableHiding: false,
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className={cn("h-8 w-8", density === "compact" && "h-7 w-7")}
              onClick={() => openView(row.original)}
              title="Open form"
              aria-label="Open form"
            >
              <Eye className="h-4 w-4" />
            </Button>
            {row.original.rowKind !== "dataset_case" ? (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className={cn("h-8 w-8", density === "compact" && "h-7 w-7")}
                onClick={() => openEdit(row.original)}
                title="Edit form"
                aria-label="Edit form"
              >
                <Pencil className="h-4 w-4" />
              </Button>
            ) : null}
          </div>
        ),
        meta: {
          label: "Actions",
          cellClassName: "w-[92px] bg-card/90",
          headerClassName: "w-[92px]",
        },
      },
      {
        accessorKey: "createdAt",
        size: 132,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
        cell: ({ row }) => <span className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTime(row.original.createdAt)}</span>,
        meta: { label: "Created" },
      },
      {
        id: "claimNumber",
        accessorFn: (row) => row.claimNumber || row.reviewId.slice(0, 8),
        size: 160,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Claim" />,
        cell: ({ row }) => {
          const claim = row.original.claimNumber || row.original.reviewId.slice(0, 8);
          if (density === "compact") {
            return (
              <span className="block w-full min-w-0 max-w-full truncate font-medium" title={claim}>
                {claim}
              </span>
            );
          }

          return (
            <div className="w-full min-w-0 max-w-full">
              <div className="truncate font-medium">{claim}</div>
              {row.original.runName ? (
                <div className="mt-0.5 truncate text-xs text-muted-foreground">{row.original.runName}</div>
              ) : null}
            </div>
          );
        },
        meta: { label: "Claim", cellClassName: "min-w-[150px] max-w-[180px]" },
      },
      {
        accessorKey: "title",
        size: density === "compact" ? 440 : 360,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Review" />,
        cell: ({ row }) => {
          if (density === "compact") {
            return (
              <button
                type="button"
                className="block w-full min-w-0 max-w-full truncate text-left font-medium text-foreground hover:text-primary"
                onClick={() => openView(row.original)}
                title={`${row.original.title}${row.original.description ? ` - ${row.original.description}` : ""}`}
              >
                {row.original.title}
              </button>
            );
          }

          return (
            <button
              type="button"
              className="block w-full min-w-0 max-w-full text-left"
              onClick={() => openView(row.original)}
              title="Open form"
            >
              <div className="truncate font-medium text-foreground hover:text-primary">{row.original.title}</div>
              <div className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{row.original.description}</div>
            </button>
          );
        },
        meta: { label: "Review", cellClassName: "min-w-[300px] max-w-[440px]" },
      },
      {
        id: "formKey",
        accessorFn: (row) => row.formKey,
        filterFn: "equalsString",
        size: density === "compact" ? 136 : 152,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Form" />,
        cell: ({ row }) => (
          <div className="mx-auto flex min-w-0 max-w-full justify-center overflow-hidden">
            <Badge
              variant="outline"
              className="max-w-full whitespace-nowrap font-mono text-[10px]"
              title={row.original.formKey}
            >
              <span className="min-w-0 truncate">{row.original.formKey}</span>
            </Badge>
          </div>
        ),
        meta: { label: "Form", align: "center", cellClassName: "min-w-0 max-w-[180px] overflow-hidden" },
      },
      {
        accessorKey: "outcome",
        filterFn: "equalsString",
        size: 96,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Outcome" />,
        cell: ({ row }) => (
          <Badge
            variant={row.original.outcome === "Meets" ? "success" : "danger"}
            className="whitespace-nowrap"
            title={row.original.outcome}
          >
            {outcomeLabel(row.original.outcome)}
          </Badge>
        ),
        meta: { label: "Outcome", align: "center" },
      },
      {
        accessorKey: "source",
        filterFn: "equalsString",
        size: 92,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Source" />,
        cell: ({ row }) => (
          <div className="mx-auto flex min-w-0 max-w-full justify-center overflow-hidden">
            <Badge variant="secondary" className="max-w-full whitespace-nowrap" title={row.original.source || "api"}>
              <span className="min-w-0 truncate">{row.original.source || "api"}</span>
            </Badge>
          </div>
        ),
        meta: { label: "Source", align: "center", cellClassName: "min-w-0 max-w-[120px] overflow-hidden" },
      },
      {
        id: "evalRole",
        accessorFn: (row) => evalRoleLabel(row.evalResultRole, row.evalReferenceKind),
        filterFn: "equalsString",
        size: 112,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Eval Role" />,
        cell: ({ row }) =>
          row.original.source === "eval" || row.original.evalResultRole ? (
            <EvalRoleBadge role={row.original.evalResultRole} referenceKind={row.original.evalReferenceKind} />
          ) : (
            <span className="text-xs text-muted-foreground">Non-eval</span>
          ),
        meta: { label: "Eval Role", align: "center" },
      },
      {
        accessorKey: "questionCount",
        size: 104,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Questions" />,
        cell: ({ row }) => <span className="tabular-nums">{row.original.questionCount}</span>,
        meta: { label: "Questions", align: "center", fitContent: true },
      },
      {
        accessorKey: "noCount",
        size: 64,
        header: ({ column }) => <DataTableColumnHeader column={column} title="No" />,
        cell: ({ row }) => (
          <span className="tabular-nums text-rose-700 dark:text-rose-300">{row.original.noCount}</span>
        ),
        meta: { label: "No", align: "center", fitContent: true },
      },
      {
        accessorKey: "driverCount",
        size: 88,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Drivers" />,
        cell: ({ row }) => (
          <span className="tabular-nums text-amber-700 dark:text-amber-300">{row.original.driverCount}</span>
        ),
        meta: { label: "Drivers", align: "center", fitContent: true },
      },
      {
        id: "edited",
        accessorFn: (row) => (row.edited ? "edited" : "unedited"),
        filterFn: "equalsString",
        size: 88,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Edited" />,
        cell: ({ row }) => (
          <Badge variant={row.original.edited ? "warning" : "outline"}>
            {row.original.edited ? "Yes" : "No"}
          </Badge>
        ),
        meta: { label: "Edited", align: "center", fitContent: true },
      },
      {
        accessorKey: "updatedAt",
        size: 132,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Updated" />,
        cell: ({ row }) => <span className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTime(row.original.updatedAt)}</span>,
        meta: { label: "Updated" },
      },
      {
        accessorKey: "reviewId",
        size: idColumnSize,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Review ID" />,
        cell: ({ row }) => <span className="font-mono text-xs">{row.original.reviewId}</span>,
        meta: { label: "Review ID", cellClassName: "min-w-[260px]" },
      },
      {
        accessorKey: "batchId",
        size: 240,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Batch ID" />,
        cell: ({ row }) => <span className="font-mono text-xs">{row.original.batchId || "-"}</span>,
        meta: { label: "Batch ID", cellClassName: "min-w-[240px]" },
      },
    ],
    [density, openEdit, openView],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      rowSelection,
      globalFilter,
      pagination,
    },
    enableRowSelection: true,
    getRowId: auditRowId,
    defaultColumn: {
      size: defaultColumnSize,
      minSize: 72,
      maxSize: idColumnSize,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: setRowSelection,
    onGlobalFilterChange: setGlobalFilter,
    onPaginationChange: setPagination as OnChangeFn<PaginationState>,
    globalFilterFn: (row, _columnId, filterValue) =>
      rowSearchText(row.original).includes(String(filterValue).trim().toLowerCase()),
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getFacetedRowModel: getFacetedRowModel(),
    getFacetedUniqueValues: getFacetedUniqueValues(),
  });

  useEffect(() => {
    const editKey = editRow ? auditRowId(editRow) : "";
    const viewKey = viewRow ? auditRowId(viewRow) : "";
    if (editKey) {
      const nextEditRow = rows.find((row) => auditRowId(row) === editKey);
      if (nextEditRow && nextEditRow !== editRow) setEditRow(nextEditRow);
    }
    if (viewKey) {
      const nextViewRow = rows.find((row) => auditRowId(row) === viewKey);
      if (nextViewRow && nextViewRow !== viewRow) setViewRow(nextViewRow);
    }
  }, [editRow, rows, viewRow]);

  useEffect(() => {
    if (loading) return;
    const rowIds = new Set(rows.map(auditRowId));
    setRowSelection((current) => {
      let changed = false;
      const next: RowSelectionState = {};

      for (const [rowId, selected] of Object.entries(current)) {
        if (!selected || !rowIds.has(rowId)) {
          changed = true;
          continue;
        }
        next[rowId] = selected;
      }

      return changed ? next : current;
    });
  }, [loading, rows]);

  const tableRows = table.getSortedRowModel().rows.map((row) => row.original);
  const selectedRows = useMemo(() => {
    const rowsById = new Map(rows.map((row) => [auditRowId(row), row]));
    return Object.entries(rowSelection)
      .filter(([, selected]) => selected)
      .map(([rowId]) => rowsById.get(rowId))
      .filter((row): row is DashboardReviewRow => Boolean(row));
  }, [rowSelection, rows]);
  const filtersActive = Boolean(globalFilter.trim()) || columnFilters.length > 0;
  const dnmCount = tableRows.filter((row) => row.outcome === "Does Not Meet").length;
  const editedCount = tableRows.filter((row) => row.edited).length;
  const driverCount = tableRows.reduce((sum, row) => sum + row.driverCount, 0);

  useEffect(() => {
    const columnFilterEntries = columnFilters.map((filter) => [
      filter.id,
      String(filter.value ?? ""),
    ]);
    setHomeTableContext({
      selected_rows: selectedRows.map(selectedHomeRowFromDashboardRow),
      visible_row_count: tableRows.length,
      total_row_count: totalCount,
      filters: {
        search: globalFilter,
        column_filters: Object.fromEntries(columnFilterEntries),
        sorting: sorting.map((sort) => ({ id: sort.id, desc: sort.desc })),
        page_index: pagination.pageIndex,
        page_size: pagination.pageSize,
        density,
      },
    } satisfies HomeTableContext);
  }, [
    columnFilters,
    density,
    globalFilter,
    pagination.pageIndex,
    pagination.pageSize,
    selectedRows,
    setHomeTableContext,
    sorting,
    tableRows.length,
    totalCount,
  ]);

  useEffect(() => {
    const pageCount = table.getPageCount();
    if (pageCount > 0 && pagination.pageIndex >= pageCount) {
      setPagination((current) => ({ ...current, pageIndex: pageCount - 1 }));
    }
  }, [pagination.pageIndex, table, tableRows.length]);

  const setColumnFilter = (id: string, value: string) => {
    setColumnFilters((current) => {
      const withoutCurrent = current.filter((filter) => filter.id !== id);
      return value === "all" ? withoutCurrent : [...withoutCurrent, { id, value }];
    });
    setPagination((current) => ({ ...current, pageIndex: 0 }));
  };

  const getColumnFilter = (id: string) =>
    String(columnFilters.find((filter) => filter.id === id)?.value ?? "all");

  const clearFilters = () => {
    setGlobalFilter("");
    setColumnFilters([]);
    setPagination((current) => ({ ...current, pageIndex: 0 }));
  };

  const copyRows = useCallback(async (rowsToCopy: DashboardReviewRow[]) => {
    await navigator.clipboard.writeText(buildTsv(rowsToCopy, exportColumns));
    setCopyStatus("success");
    window.setTimeout(() => setCopyStatus("idle"), 1400);
  }, []);

  const submitEditForm = async (form: AuditFormResult) => {
    if (!editRow) return;
    await onSaveForm(editRow.reviewId, form);
  };

  const handleFeedbackSubmitted = async (reviewId: string) => {
    await onFeedbackSubmitted?.(reviewId);
  };

  const toolbar = (
    <div className="space-y-3 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold">Audit Data</h2>
            {loading ? (
              <Badge variant="outline" className="gap-1">
                <Loader2 className="h-3 w-3 animate-spin" />
                Loading
              </Badge>
            ) : null}
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
            <span>{tableRows.length} visible</span>
            <span>of {totalCount} completed</span>
            <span>{dnmCount} DNM</span>
            <span>{editedCount} edited</span>
            <span>{driverCount} drivers</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Refresh
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setDensity((current) => (current === "normal" ? "compact" : "normal"))}
          >
            <Shrink className="h-3.5 w-3.5" />
            {density === "normal" ? "Compact" : "Comfort"}
          </Button>
          <DataTableViewOptions table={table} />
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-[240px] flex-1 space-y-1">
          <span className="block text-[10px] font-semibold uppercase text-muted-foreground">Search</span>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={globalFilter}
              onChange={(event) => {
                setGlobalFilter(event.target.value);
                setPagination((current) => ({ ...current, pageIndex: 0 }));
              }}
              className="h-8 pl-8 text-xs"
              placeholder="Claim, review, run, form..."
            />
          </div>
        </label>

        <SelectFilter label="Outcome" value={getColumnFilter("outcome")} onChange={(value) => setColumnFilter("outcome", value)}>
          <option value="all">All outcomes</option>
          <option value="Meets">Meets</option>
          <option value="Does Not Meet">Does Not Meet</option>
        </SelectFilter>

        <SelectFilter label="Source" value={getColumnFilter("source")} onChange={(value) => setColumnFilter("source", value)}>
          <option value="all">All sources</option>
          {sourceOptions.map((source) => (
            <option key={source} value={source}>
              {source}
            </option>
          ))}
        </SelectFilter>

        <SelectFilter label="Form" value={getColumnFilter("formKey")} onChange={(value) => setColumnFilter("formKey", value)}>
          <option value="all">All forms</option>
          {formOptions.map((form) => (
            <option key={form} value={form}>
              {form}
            </option>
          ))}
        </SelectFilter>

        <SelectFilter label="Edited" value={getColumnFilter("edited")} onChange={(value) => setColumnFilter("edited", value)}>
          <option value="all">All edits</option>
          <option value="edited">Edited</option>
          <option value="unedited">Unedited</option>
        </SelectFilter>

        <SelectFilter label="Eval Role" value={getColumnFilter("evalRole")} onChange={(value) => setColumnFilter("evalRole", value)}>
          <option value="all">All roles</option>
          {evalRoleOptions.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </SelectFilter>

        <div className="ml-auto flex items-end gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={clearFilters}
            disabled={!filtersActive}
          >
            <X className="h-3.5 w-3.5" />
            Clear
          </Button>
          <details className="relative">
            <summary className="inline-flex h-8 cursor-pointer list-none items-center justify-center gap-1.5 rounded-md border border-input bg-background px-3 text-xs font-medium transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
              <SlidersHorizontal className="h-3.5 w-3.5" />
              Export
            </summary>
            <div className="absolute right-0 z-50 mt-2 w-48 rounded-md border bg-card p-1 shadow-lg">
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-secondary"
                onClick={() => void copyRows(tableRows)}
              >
                {copyStatus === "success" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {copyStatus === "success" ? "Copied" : "Copy TSV"}
              </button>
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-secondary"
                onClick={() => downloadText(buildCsv(tableRows, exportColumns), "audit_data.csv", "text/csv")}
              >
                <Download className="h-4 w-4" />
                CSV
              </button>
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-secondary"
                onClick={() =>
                  downloadWorkbook({
                    fileName: "audit_data.xlsx",
                    viewSheetName: "audit_data",
                    dataSheetName: "data",
                    viewRows: tableRows,
                    viewColumns: exportColumns,
                    dataRows: tableRows,
                    dataColumns: exportColumns,
                  })
                }
              >
                <FileSpreadsheet className="h-4 w-4" />
                Excel
              </button>
            </div>
          </details>
        </div>
      </div>
    </div>
  );

  const actionBar = selectedRows.length > 0 ? (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-primary/10 px-4 py-3 text-sm">
      <div className="flex items-center gap-2">
        <ClipboardCheck className="h-4 w-4 text-primary" />
        <span className="font-medium">{selectedRows.length} selected</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => void copyRows(selectedRows)}>
          {copyStatus === "success" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copyStatus === "success" ? "Copied" : "Copy"}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => downloadText(buildCsv(selectedRows, exportColumns), "selected_audit_data.csv", "text/csv")}
        >
          <Download className="h-3.5 w-3.5" />
          CSV
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            downloadWorkbook({
              fileName: "selected_audit_data.xlsx",
              viewSheetName: "selected_audit_data",
              dataSheetName: "data",
              viewRows: selectedRows,
              viewColumns: exportColumns,
              dataRows: selectedRows,
              dataColumns: exportColumns,
            })
          }
        >
          <FileSpreadsheet className="h-3.5 w-3.5" />
          Excel
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => table.resetRowSelection()}>
          <X className="h-3.5 w-3.5" />
          Unselect all
        </Button>
      </div>
    </div>
  ) : null;

  return (
    <>
      <DataTable
        table={table}
        toolbar={toolbar}
        actionBar={actionBar}
        density={density}
        className="h-full"
        emptyState={
          <div className="flex flex-col items-center gap-2">
            <Search className="h-8 w-8 text-muted-foreground/45" />
            <div>
              <p className="font-medium text-foreground">No audits found</p>
              <p className="mt-1 text-xs text-muted-foreground">Adjust filters or refresh the audit data.</p>
            </div>
          </div>
        }
      />
      <FormViewerSheet
        row={viewRow}
        open={Boolean(viewRow)}
        onOpenChange={(open) => !open && setViewRow(null)}
        onFeedbackSubmitted={handleFeedbackSubmitted}
      />
      <AuditResultEditSheet
        row={
          editRow
            ? {
                reviewId: editRow.reviewId,
                title: editRow.title,
                formKey: editRow.formKey,
                edited: editRow.edited,
                claimNumber: editRow.claimNumber,
                form: editRow.form,
                feedbackCount: editRow.feedbackCount,
                feedbackEnabled: editRow.rowKind !== "dataset_case" && !editRow.reviewId.startsWith("eval-ground-truth:"),
                createdAt: editRow.createdAt,
                updatedAt: editRow.updatedAt,
                source: editRow.source,
              }
            : null
        }
        onClose={() => setEditRow(null)}
        onSubmit={submitEditForm}
        onFeedbackSubmitted={handleFeedbackSubmitted}
      />
    </>
  );
}
