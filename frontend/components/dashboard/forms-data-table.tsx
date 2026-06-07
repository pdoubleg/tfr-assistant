"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  Copy,
  Download,
  Eye,
  FileSpreadsheet,
  Search,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EvalRoleBadge } from "@/components/dashboard/eval-role-badge";
import { TablePagination } from "@/components/dashboard/table-pagination";
import {
  compareDashboardValues,
  evalRoleLabel,
  formStatusLabels,
  formStatusVariant,
  formatDateTime,
  resultVersionLabels,
  type DashboardReviewRow,
} from "@/lib/dashboard-data";
import { buildCsv, buildTsv, downloadText, downloadWorkbook, type ExportColumn } from "@/lib/table-export";
import { cn } from "@/lib/utils";

type SortDir = "asc" | "desc";
type FormSortKey =
  | "createdAt"
  | "claimNumber"
  | "title"
  | "formId"
  | "formVersion"
  | "formKind"
  | "source"
  | "evalRole"
  | "outcome"
  | "questionCount"
  | "yesCount"
  | "noCount"
  | "driverCount"
  | "totalOverwriteDollars"
  | "totalUnderwriteDollars"
  | "formStatus"
  | "updatedAt";

interface ColumnDef {
  key: FormSortKey;
  label: string;
  className?: string;
  align?: "left" | "center" | "right";
}

const columns: ColumnDef[] = [
  { key: "createdAt", label: "Created" },
  { key: "claimNumber", label: "Claim", className: "min-w-[120px]" },
  { key: "title", label: "Review", className: "min-w-[250px]" },
  { key: "formId", label: "Form" },
  { key: "formVersion", label: "Version" },
  { key: "formKind", label: "Kind" },
  { key: "source", label: "Source" },
  { key: "evalRole", label: "Eval Role" },
  { key: "outcome", label: "Outcome" },
  { key: "questionCount", label: "Questions", align: "center" },
  { key: "yesCount", label: "Yes", align: "center" },
  { key: "noCount", label: "No", align: "center" },
  { key: "driverCount", label: "Drivers", align: "center" },
  { key: "totalOverwriteDollars", label: "OW", align: "right" },
  { key: "totalUnderwriteDollars", label: "UW", align: "right" },
  { key: "formStatus", label: "Status", align: "center" },
  { key: "updatedAt", label: "Updated" },
];

function exportRowId(row: DashboardReviewRow): string {
  return `${row.reviewId}:${row.resultVersion}`;
}

function stringifyJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {});
  } catch {
    return "";
  }
}

function outcomeLabel(outcome: string): string {
  return outcome === "Does Not Meet" ? "DNM" : outcome;
}

const viewColumns: ExportColumn<DashboardReviewRow>[] = [
  { header: "Export Row ID", value: exportRowId },
  { header: "Review ID", value: (row) => row.reviewId },
  { header: "Created", value: (row) => formatDateTime(row.createdAt) },
  { header: "Claim Number", value: (row) => row.claimNumber },
  { header: "Review Title", value: (row) => row.title },
  { header: "Form ID", value: (row) => row.formId },
  { header: "Form Version", value: (row) => row.formVersion },
  { header: "Form Kind", value: (row) => row.formKind },
  { header: "Source", value: (row) => row.source },
  { header: "Eval Role", value: (row) => evalRoleLabel(row.evalResultRole, row.evalReferenceKind) },
  { header: "Outcome", value: (row) => row.outcome },
  { header: "Questions", value: (row) => row.questionCount },
  { header: "Yes Count", value: (row) => row.yesCount },
  { header: "No Count", value: (row) => row.noCount },
  { header: "Driver Count", value: (row) => row.driverCount },
  { header: "Total Amount Reviewed", value: (row) => row.totalAmountReviewedDollars ?? "" },
  { header: "Total Overwrite Dollars", value: (row) => row.totalOverwriteDollars },
  { header: "Total Underwrite Dollars", value: (row) => row.totalUnderwriteDollars },
  { header: "Overwrite Percent", value: (row) => row.overwritePercent ?? "" },
  { header: "Underwrite Percent", value: (row) => row.underwritePercent ?? "" },
  { header: "Net Exception Dollars", value: (row) => row.netExceptionDollars },
  { header: "Status", value: (row) => formStatusLabels[row.formStatus] },
  { header: "First Finalized", value: (row) => formatDateTime(row.firstFinalizedAt) },
  { header: "Last Finalized", value: (row) => formatDateTime(row.lastFinalizedAt) },
  { header: "Updated", value: (row) => formatDateTime(row.updatedAt) },
];

const dataColumns: ExportColumn<DashboardReviewRow>[] = [
  { header: "Export Row ID", value: exportRowId },
  { header: "Review ID", value: (row) => row.reviewId },
  { header: "Batch ID", value: (row) => row.batchId },
  { header: "Review Lifecycle", value: (row) => row.status },
  { header: "Source", value: (row) => row.source },
  { header: "Eval Run ID", value: (row) => row.evalRunId },
  { header: "Eval Run", value: (row) => row.evalRunName },
  { header: "Eval Result Role", value: (row) => evalRoleLabel(row.evalResultRole, row.evalReferenceKind) },
  { header: "Eval Config Version", value: (row) => row.evalConfigVersion ?? "" },
  { header: "Created", value: (row) => formatDateTime(row.createdAt) },
  { header: "Updated", value: (row) => formatDateTime(row.updatedAt) },
  { header: "Claim Number", value: (row) => row.claimNumber },
  { header: "Batch Run", value: (row) => row.runName },
  { header: "Batch Description", value: (row) => row.batchDescription },
  { header: "Batch Template ID", value: (row) => row.batchTemplateId },
  { header: "Effective Date", value: (row) => row.effectiveDate },
  { header: "Synthetic", value: (row) => (row.synthetic ? "Yes" : "No") },
  { header: "Source File IDs", value: (row) => row.sourceFileIds },
  { header: "Form ID", value: (row) => row.formId },
  { header: "Form Version", value: (row) => row.formVersion },
  { header: "Form Key", value: (row) => row.formKey },
  { header: "Result Version", value: (row) => resultVersionLabels[row.resultVersion] },
  { header: "Outcome", value: (row) => row.outcome },
  { header: "Original Outcome", value: (row) => row.originalForm?.overall_outcome ?? "" },
  { header: "Current Outcome", value: (row) => row.currentForm?.overall_outcome ?? "" },
  { header: "Questions", value: (row) => row.questionCount },
  { header: "Yes Count", value: (row) => row.yesCount },
  { header: "No Count", value: (row) => row.noCount },
  { header: "Sub-question Count", value: (row) => row.subQuestionCount },
  { header: "Driver Count", value: (row) => row.driverCount },
  { header: "Status", value: (row) => formStatusLabels[row.formStatus] },
  { header: "First Finalized", value: (row) => formatDateTime(row.firstFinalizedAt) },
  { header: "Last Finalized", value: (row) => formatDateTime(row.lastFinalizedAt) },
  { header: "Title", value: (row) => row.title },
  { header: "Description", value: (row) => row.description },
  { header: "Outcome Justification", value: (row) => row.outcomeJustification },
  { header: "Input JSON", value: (row) => stringifyJson(row.inputJson) },
  { header: "Form Payload JSON", value: (row) => stringifyJson(row.form) },
];

function getSortValue(row: DashboardReviewRow, key: FormSortKey): string | number | boolean {
  if (key === "evalRole") return evalRoleLabel(row.evalResultRole, row.evalReferenceKind);
  return row[key];
}

function SortIcon({
  active,
  direction,
}: {
  active: boolean;
  direction: SortDir;
}) {
  if (!active) return <ArrowUpDown className="h-3 w-3 opacity-35" />;
  return direction === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />;
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
    <label className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {children}
      </select>
    </label>
  );
}

export function FormsDataTable({
  rows,
  totalCount,
  selectedReviewId,
  onViewReview,
}: {
  rows: DashboardReviewRow[];
  totalCount: number;
  selectedReviewId?: string | null;
  onViewReview: (row: DashboardReviewRow) => void;
}) {
  const [search, setSearch] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortKey, setSortKey] = useState<FormSortKey>("createdAt");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [copyStatus, setCopyStatus] = useState<"idle" | "success">("idle");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);

  const sourceOptions = useMemo(
    () => Array.from(new Set(rows.map((row) => row.source).filter(Boolean))).sort(),
    [rows],
  );

  const visibleRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    const filtered = rows.filter((row) => {
      if (outcomeFilter !== "all" && row.outcome !== outcomeFilter) return false;
      if (sourceFilter !== "all" && row.source !== sourceFilter) return false;
      if (statusFilter !== "all" && row.formStatus !== statusFilter) return false;
      if (!query) return true;
      return [
        row.reviewId,
        row.claimNumber,
        row.runName,
        row.title,
        row.description,
        row.formId,
        row.formVersion,
        row.outcome,
        row.source,
        formStatusLabels[row.formStatus],
        evalRoleLabel(row.evalResultRole, row.evalReferenceKind),
        row.evalRunName,
      ]
        .join(" ")
        .toLowerCase()
        .includes(query);
    });

    return [...filtered].sort((first, second) =>
      compareDashboardValues(getSortValue(first, sortKey), getSortValue(second, sortKey), sortDir),
    );
  }, [outcomeFilter, rows, search, sortDir, sortKey, sourceFilter, statusFilter]);
  const totalPages = Math.max(1, Math.ceil(visibleRows.length / pageSize));
  const paginatedRows = useMemo(
    () => visibleRows.slice((Math.min(page, totalPages) - 1) * pageSize, Math.min(page, totalPages) * pageSize),
    [page, pageSize, totalPages, visibleRows],
  );

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const handleSort = useCallback(
    (key: FormSortKey) => {
      if (sortKey === key) {
        setSortDir((current) => (current === "asc" ? "desc" : "asc"));
      } else {
        setSortKey(key);
        setSortDir("asc");
      }
    },
    [sortKey],
  );

  const copyRows = useCallback(async () => {
    await navigator.clipboard.writeText(buildTsv(visibleRows, dataColumns));
    setCopyStatus("success");
    window.setTimeout(() => setCopyStatus("idle"), 1400);
  }, [visibleRows]);

  const resetTableFilters = () => {
    setSearch("");
    setOutcomeFilter("all");
    setSourceFilter("all");
    setStatusFilter("all");
  };

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="flex flex-wrap items-center gap-3 border-b bg-secondary/40 px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold">Audit Forms</h2>
            <p className="text-xs text-muted-foreground">One row per completed review.</p>
          </div>
          <div className="relative min-w-[220px] flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="h-8 pl-9 text-xs"
              placeholder="Search reviews..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <SelectFilter label="Outcome" value={outcomeFilter} onChange={setOutcomeFilter}>
            <option value="all">All outcomes</option>
            <option value="Meets">Meets</option>
            <option value="Does Not Meet">Does Not Meet</option>
          </SelectFilter>
          <SelectFilter label="Source" value={sourceFilter} onChange={setSourceFilter}>
            <option value="all">All sources</option>
            {sourceOptions.map((source) => (
              <option key={source} value={source}>
                {source}
              </option>
            ))}
          </SelectFilter>
          <SelectFilter label="Status" value={statusFilter} onChange={setStatusFilter}>
            <option value="all">All statuses</option>
            <option value="finalized">Finalized</option>
            <option value="edited">Edited</option>
            <option value="unedited">Unedited</option>
          </SelectFilter>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={resetTableFilters}
            disabled={!search && outcomeFilter === "all" && sourceFilter === "all" && statusFilter === "all"}
          >
            <X className="h-3.5 w-3.5" />
            Clear
          </Button>
          <div className="ml-auto flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => downloadText(buildCsv(visibleRows, dataColumns), "audit_forms.csv", "text/csv")}
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
                  fileName: "audit_forms.xlsx",
                  viewSheetName: "audit_forms_view",
                  dataSheetName: "data",
                  viewRows: visibleRows,
                  viewColumns,
                  dataRows: visibleRows,
                  dataColumns,
                })
              }
            >
              <FileSpreadsheet className="h-3.5 w-3.5" />
              Excel
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => void copyRows()}>
              {copyStatus === "success" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              {copyStatus === "success" ? "Copied" : "Copy"}
            </Button>
          </div>
        </div>

        <Table>
          <TableHeader>
            <TableRow className="bg-secondary/60">
              <TableHead className="w-12">View</TableHead>
              {columns.map((column) => (
                <TableHead
                  key={column.key}
                  className={cn(
                    "cursor-pointer select-none whitespace-nowrap",
                    column.className,
                    column.align === "center" && "text-center",
                    column.align === "right" && "text-right",
                  )}
                  onClick={() => handleSort(column.key)}
                >
                  <span className={cn("inline-flex items-center gap-1", column.align === "center" && "justify-center")}>
                    {column.label}
                    <SortIcon active={sortKey === column.key} direction={sortDir} />
                  </span>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length + 1} className="h-24 text-center text-muted-foreground">
                  No reviews match the current filters.
                </TableCell>
              </TableRow>
            ) : (
              paginatedRows.map((row) => {
                const selected = selectedReviewId === row.reviewId;
                return (
                  <TableRow key={`${row.reviewId}-${row.resultVersion}`} data-state={selected ? "selected" : undefined}>
                    <TableCell>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => onViewReview(row)}
                        title="Open read-only form"
                        aria-label="Open read-only form"
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatDateTime(row.createdAt)}
                    </TableCell>
                    <TableCell className="font-medium">{row.claimNumber || row.reviewId.slice(0, 8)}</TableCell>
                    <TableCell className="max-w-[300px]">
                      <div className="truncate font-medium">{row.title}</div>
                      <div className="truncate text-xs text-muted-foreground">{row.runName || row.description}</div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{row.formId}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{row.formVersion}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{row.source}</Badge>
                    </TableCell>
                    <TableCell>
                      {row.source === "eval" || row.evalResultRole ? (
                        <EvalRoleBadge role={row.evalResultRole} referenceKind={row.evalReferenceKind} />
                      ) : (
                        <span className="text-xs text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={row.outcome === "Meets" ? "success" : "danger"}
                        className="whitespace-nowrap text-[11px]"
                        title={row.outcome}
                      >
                        {outcomeLabel(row.outcome)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-center tabular-nums">{row.questionCount}</TableCell>
                    <TableCell className="text-center tabular-nums text-emerald-700 dark:text-emerald-300">
                      {row.yesCount}
                    </TableCell>
                    <TableCell className="text-center tabular-nums text-rose-700 dark:text-rose-300">{row.noCount}</TableCell>
                    <TableCell className="text-center tabular-nums text-amber-700 dark:text-amber-300">
                      {row.driverCount}
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge variant={formStatusVariant(row.formStatus)}>
                        {formStatusLabels[row.formStatus]}
                      </Badge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatDateTime(row.updatedAt)}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>

        <TablePagination
          totalRows={visibleRows.length}
          page={page}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(nextPageSize);
            setPage(1);
          }}
        />
        <div className="border-t bg-secondary/20 px-4 py-2 text-xs text-muted-foreground">
          {rows.length} reviews match the dashboard filters, {totalCount} completed reviews loaded.
        </div>
      </CardContent>
    </Card>
  );
}
