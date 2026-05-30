"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  Eye,
  FileSpreadsheet,
  MessageSquareText,
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
  buildCommentRows,
  compareDashboardValues,
  evalRoleLabel,
  formatDateTime,
  questionCommentKey,
  resultVersionLabels,
  subQuestionCommentKey,
  type CommentQuestionFilter,
  type CommentReportRow,
  type DashboardReviewRow,
} from "@/lib/dashboard-data";
import { buildCsv, buildTsv, downloadText, downloadWorkbook, type ExportColumn } from "@/lib/table-export";
import { cn } from "@/lib/utils";

type SortDir = "asc" | "desc";
type CommentSortKey =
  | "createdAt"
  | "claimNumber"
  | "formId"
  | "formVersion"
  | "outcome"
  | "evalRole"
  | "commentType"
  | "questionId"
  | "subQuestionId";

interface ColumnDef {
  key: CommentSortKey;
  label: string;
  className?: string;
}

const columns: ColumnDef[] = [
  { key: "createdAt", label: "Created" },
  { key: "claimNumber", label: "Claim", className: "min-w-[110px]" },
  { key: "formId", label: "Form" },
  { key: "formVersion", label: "Version" },
  { key: "outcome", label: "Outcome" },
  { key: "evalRole", label: "Eval Role" },
  { key: "commentType", label: "Comment Type" },
  { key: "questionId", label: "Question" },
  { key: "subQuestionId", label: "Sub-question" },
];

function exportRowId(row: CommentReportRow): string {
  return row.id;
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

function commentTypeLabel(type: string): string {
  if (type === "Outcome justification") return "Outcome";
  if (type === "Question comments") return "Question";
  if (type === "Financial exception") return "Financial";
  return "Sub-question";
}

const viewColumns: ExportColumn<CommentReportRow>[] = [
  { header: "Export Row ID", value: exportRowId },
  { header: "Review ID", value: (row) => row.reviewId },
  { header: "Created", value: (row) => formatDateTime(row.createdAt) },
  { header: "Claim Number", value: (row) => row.claimNumber },
  { header: "Form ID", value: (row) => row.formId },
  { header: "Form Version", value: (row) => row.formVersion },
  { header: "Outcome", value: (row) => row.outcome },
  { header: "Eval Role", value: (row) => evalRoleLabel(row.row.evalResultRole, row.row.evalReferenceKind) },
  { header: "Comment Type", value: (row) => row.commentType },
  { header: "Question ID", value: (row) => row.questionId },
  { header: "Sub-question ID", value: (row) => row.subQuestionId },
  { header: "Comment", value: (row) => row.comment },
];

const dataColumns: ExportColumn<CommentReportRow>[] = [
  { header: "Export Row ID", value: exportRowId },
  { header: "Review ID", value: (row) => row.reviewId },
  { header: "Batch ID", value: (row) => row.row.batchId },
  { header: "Status", value: (row) => row.row.status },
  { header: "Created", value: (row) => formatDateTime(row.createdAt) },
  { header: "Updated", value: (row) => formatDateTime(row.updatedAt) },
  { header: "Claim Number", value: (row) => row.claimNumber },
  { header: "Batch Run", value: (row) => row.runName },
  { header: "Batch Description", value: (row) => row.row.batchDescription },
  { header: "Batch Template ID", value: (row) => row.row.batchTemplateId },
  { header: "Effective Date", value: (row) => row.row.effectiveDate },
  { header: "Synthetic", value: (row) => (row.row.synthetic ? "Yes" : "No") },
  { header: "Source File IDs", value: (row) => row.row.sourceFileIds },
  { header: "Source", value: (row) => row.source },
  { header: "Eval Role", value: (row) => evalRoleLabel(row.row.evalResultRole, row.row.evalReferenceKind) },
  { header: "Form ID", value: (row) => row.formId },
  { header: "Form Version", value: (row) => row.formVersion },
  { header: "Form Key", value: (row) => row.row.formKey },
  { header: "Result Version", value: (row) => resultVersionLabels[row.resultVersion] },
  { header: "Outcome", value: (row) => row.outcome },
  { header: "Review Title", value: (row) => row.title },
  { header: "Review Description", value: (row) => row.row.description },
  { header: "Edited", value: (row) => (row.row.edited ? "Yes" : "No") },
  { header: "Comment Type", value: (row) => row.commentType },
  { header: "Question ID", value: (row) => row.questionId },
  { header: "Question", value: (row) => row.questionText },
  { header: "Answer", value: (row) => row.answer },
  { header: "Sub-question ID", value: (row) => row.subQuestionId },
  { header: "Sub-question", value: (row) => row.subQuestionText },
  { header: "Comment", value: (row) => row.comment },
  { header: "Citations", value: (row) => row.citations },
  { header: "Input JSON", value: (row) => stringifyJson(row.row.inputJson) },
  { header: "Form Payload JSON", value: (row) => stringifyJson(row.row.form) },
];

function SortIcon({ active, direction }: { active: boolean; direction: SortDir }) {
  if (!active) return <ArrowUpDown className="h-3 w-3 opacity-35" />;
  return direction === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />;
}

function getSortValue(row: CommentReportRow, key: CommentSortKey): string | boolean | null {
  if (key === "evalRole") return evalRoleLabel(row.row.evalResultRole, row.row.evalReferenceKind);
  return row[key];
}

export function CommentsReportTable({
  rows,
  questionFilter,
  onClearQuestionFilter,
  onViewReview,
}: {
  rows: DashboardReviewRow[];
  questionFilter: CommentQuestionFilter;
  onClearQuestionFilter: () => void;
  onViewReview: (row: DashboardReviewRow) => void;
}) {
  const commentRows = useMemo(() => buildCommentRows(rows), [rows]);
  const activeQuestionFilterCount = questionFilter.questionKeys.size + questionFilter.subQuestionKeys.size;
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sortKey, setSortKey] = useState<CommentSortKey>("createdAt");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [copyStatus, setCopyStatus] = useState<"idle" | "success">("idle");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);

  const visibleRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    const filtered = commentRows.filter((row) => {
      if (activeQuestionFilterCount > 0) {
        if (row.commentType === "Outcome justification") return false;
        const questionKey = questionCommentKey(row.row.formKey, row.questionId);
        const subQuestionKey =
          row.subQuestionId && row.subQuestionText
            ? subQuestionCommentKey(row.row.formKey, row.questionId, row.subQuestionId, row.subQuestionText)
            : "";
        if (!questionFilter.questionKeys.has(questionKey) && !questionFilter.subQuestionKeys.has(subQuestionKey)) {
          return false;
        }
      }
      if (typeFilter !== "all" && row.commentType !== typeFilter) return false;
      if (!query) return true;
      return [
        row.reviewId,
        row.claimNumber,
        row.runName,
        row.title,
        row.formId,
        row.formVersion,
        row.outcome,
        evalRoleLabel(row.row.evalResultRole, row.row.evalReferenceKind),
        row.commentType,
        row.questionId,
        row.questionText,
        row.subQuestionId,
        row.subQuestionText,
        row.comment,
        row.citations,
      ]
        .join(" ")
        .toLowerCase()
        .includes(query);
    });

    return [...filtered].sort((first, second) =>
      compareDashboardValues(getSortValue(first, sortKey), getSortValue(second, sortKey), sortDir),
    );
  }, [
    activeQuestionFilterCount,
    commentRows,
    questionFilter.questionKeys,
    questionFilter.subQuestionKeys,
    search,
    sortDir,
    sortKey,
    typeFilter,
  ]);
  const totalPages = Math.max(1, Math.ceil(visibleRows.length / pageSize));
  const paginatedRows = useMemo(
    () => visibleRows.slice((Math.min(page, totalPages) - 1) * pageSize, Math.min(page, totalPages) * pageSize),
    [page, pageSize, totalPages, visibleRows],
  );

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const handleSort = useCallback(
    (key: CommentSortKey) => {
      if (sortKey === key) {
        setSortDir((current) => (current === "asc" ? "desc" : "asc"));
      } else {
        setSortKey(key);
        setSortDir("asc");
      }
    },
    [sortKey],
  );

  const toggleExpanded = (rowId: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  };

  const copyRows = useCallback(async () => {
    await navigator.clipboard.writeText(buildTsv(visibleRows, dataColumns));
    setCopyStatus("success");
    window.setTimeout(() => setCopyStatus("idle"), 1400);
  }, [visibleRows]);

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="flex flex-wrap items-center gap-3 border-b bg-secondary/40 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <MessageSquareText className="h-4 w-4 text-primary" />
            <div>
              <h2 className="text-sm font-semibold">Comments Report</h2>
              <p className="text-xs text-muted-foreground">
                {visibleRows.length} comments out of {commentRows.length} shown
              </p>
            </div>
          </div>
          {activeQuestionFilterCount ? (
            <Badge variant="warning" className="whitespace-nowrap">
              Question filter: {activeQuestionFilterCount}
            </Badge>
          ) : null}
          <div className="relative min-w-[220px] flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="h-8 pl-9 text-xs"
              placeholder="Search comments..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <select
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            className="h-8 rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="all">All comments</option>
            <option value="Outcome justification">Outcome justification</option>
            <option value="Question comments">Question comments</option>
            <option value="Sub-question reasoning">Sub-question reasoning</option>
          </select>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setSearch("");
              setTypeFilter("all");
            }}
            disabled={!search && typeFilter === "all"}
          >
            <X className="h-3.5 w-3.5" />
            Clear
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClearQuestionFilter}
            disabled={activeQuestionFilterCount === 0}
          >
            Clear Question Filter
          </Button>
          <div className="ml-auto flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => downloadText(buildCsv(visibleRows, dataColumns), "comments_report.csv", "text/csv")}
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
                  fileName: "comments_report.xlsx",
                  viewSheetName: "comments_view",
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
              <TableHead className="w-20">View</TableHead>
              {columns.map((column) => (
                <TableHead
                  key={column.key}
                  className={cn("cursor-pointer select-none whitespace-nowrap", column.className)}
                  onClick={() => handleSort(column.key)}
                >
                  <span className="inline-flex items-center gap-1">
                    {column.label}
                    <SortIcon active={sortKey === column.key} direction={sortDir} />
                  </span>
                </TableHead>
              ))}
              <TableHead className="min-w-[320px]">Comment</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length + 2} className="h-24 text-center text-muted-foreground">
                  No comments match the current filters.
                </TableCell>
              </TableRow>
            ) : (
              paginatedRows.map((row) => {
                const isExpanded = expanded.has(row.id);
                return (
                  <Fragment key={row.id}>
                    <TableRow className={isExpanded ? "bg-secondary/30" : undefined}>
                      <TableCell>
                        <div className="flex items-center gap-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => toggleExpanded(row.id)}
                            title={isExpanded ? "Collapse comment" : "Expand comment"}
                            aria-label={isExpanded ? "Collapse comment" : "Expand comment"}
                          >
                            {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => onViewReview(row.row)}
                            title="Open read-only form"
                            aria-label="Open read-only form"
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatDateTime(row.createdAt)}
                      </TableCell>
                      <TableCell className="font-medium">{row.claimNumber || row.reviewId.slice(0, 8)}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{row.formId}</Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">{row.formVersion}</TableCell>
                      <TableCell>
                        <Badge
                          variant={row.outcome === "Meets" ? "success" : "danger"}
                          className="whitespace-nowrap text-[11px]"
                          title={row.outcome}
                        >
                          {outcomeLabel(row.outcome)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <EvalRoleBadge role={row.row.evalResultRole} referenceKind={row.row.evalReferenceKind} />
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={row.commentType === "Outcome justification" ? "secondary" : "outline"}
                          className="whitespace-nowrap text-[11px]"
                          title={row.commentType}
                        >
                          {commentTypeLabel(row.commentType)}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">{row.questionId}</TableCell>
                      <TableCell className="font-mono text-xs">{row.subQuestionId || "n/a"}</TableCell>
                      <TableCell className="max-w-[420px]">
                        <span className={cn("block text-sm leading-relaxed", !isExpanded && "line-clamp-2")}>{row.comment}</span>
                      </TableCell>
                    </TableRow>
                    {isExpanded ? (
                      <TableRow className="bg-secondary/15">
                        <TableCell />
                        <TableCell colSpan={columns.length + 1}>
                          <div className="grid gap-3 py-2 lg:grid-cols-2">
                            <div>
                              <p className="text-[11px] font-semibold uppercase text-muted-foreground">Context</p>
                              <div className="mt-1 space-y-2 rounded-md border bg-background p-3 text-sm leading-relaxed">
                                <p>
                                  <span className="font-medium">Question:</span> {row.questionText}
                                </p>
                                {row.subQuestionText ? (
                                  <p>
                                    <span className="font-medium">Sub-question:</span> {row.subQuestionText}
                                  </p>
                                ) : null}
                                {row.citations ? (
                                  <p>
                                    <span className="font-medium">Citations:</span> {row.citations}
                                  </p>
                                ) : null}
                              </div>
                            </div>
                            <div>
                              <p className="text-[11px] font-semibold uppercase text-muted-foreground">Comment</p>
                              <p className="mt-1 whitespace-pre-wrap rounded-md border bg-background p-3 text-sm leading-relaxed">
                                {row.comment || "No comment text."}
                              </p>
                            </div>
                          </div>
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </Fragment>
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
      </CardContent>
    </Card>
  );
}
