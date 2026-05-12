"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  FileSpreadsheet,
  ListChecks,
  Search,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TablePagination } from "@/components/dashboard/table-pagination";
import {
  aggregateQuestions,
  compareDashboardValues,
  type AggregatedQuestionRow,
  type AggregatedSubQuestionRow,
  type CommentQuestionFilter,
  type DashboardReviewRow,
} from "@/lib/dashboard-data";
import { buildCsv, buildTsv, downloadText, downloadWorkbook, type ExportColumn } from "@/lib/table-export";
import { cn } from "@/lib/utils";

type SortDir = "asc" | "desc";
type QuestionSortKey =
  | "formKey"
  | "id"
  | "text"
  | "totalCount"
  | "yesCount"
  | "noCount"
  | "yesPercent"
  | "noPercent"
  | "driverCount"
  | "editCount";

interface ColumnDef {
  key: QuestionSortKey;
  label: string;
  className?: string;
  align?: "left" | "center";
}

const columns: ColumnDef[] = [
  { key: "formKey", label: "Form", className: "min-w-[170px]" },
  { key: "id", label: "ID", className: "w-16" },
  { key: "text", label: "Question", className: "min-w-[320px]" },
  { key: "totalCount", label: "Total", align: "center" },
  { key: "yesCount", label: "Yes", align: "center" },
  { key: "yesPercent", label: "% Yes", align: "center" },
  { key: "noCount", label: "No", align: "center" },
  { key: "noPercent", label: "% No", align: "center" },
  { key: "driverCount", label: "Drivers", align: "center" },
];

function FilterCheckbox({
  checked,
  disabled,
  indeterminate = false,
  onChange,
  label,
}: {
  checked: boolean;
  disabled?: boolean;
  indeterminate?: boolean;
  onChange: () => void;
  label: string;
}) {
  const ref = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <input
      ref={ref}
      type="checkbox"
      checked={checked}
      disabled={disabled}
      onChange={onChange}
      onClick={(event) => event.stopPropagation()}
      className="h-4 w-4 rounded border-input accent-primary disabled:cursor-not-allowed disabled:opacity-40"
      title={label}
      aria-label={label}
    />
  );
}

interface QuestionExportRow {
  exportRowId: string;
  questionKey: string;
  formId: string;
  formVersion: string;
  formKey: string;
  questionId: string;
  questionText: string;
  questionSubQuestion: string;
  totalCount: number;
  yesCount: number;
  yesPercent: number;
  noCount: number;
  noPercent: number;
  driverCount: number;
  subQuestionKey: string;
  subQuestionId: string;
  subQuestionText: string;
  subQuestionDriverCount: number;
  subQuestionAppearances: number;
  subQuestionDriverPercent: number;
}

interface QuestionDetailExportRow {
  exportRowId: string;
  detailRowId: string;
  reviewId: string;
  batchId: string;
  status: string;
  source: string;
  claimNumber: string;
  batchRun: string;
  batchDescription: string;
  batchTemplateId: string;
  effectiveDate: string;
  synthetic: string;
  sourceFileIds: string;
  createdAt: string;
  updatedAt: string;
  resultVersion: string;
  edited: string;
  formId: string;
  formVersion: string;
  formKey: string;
  reviewOutcome: string;
  reviewOutcomeJustification: string;
  reviewTitle: string;
  reviewDescription: string;
  questionId: string;
  questionText: string;
  questionAnswer: string;
  subQuestionId: string;
  subQuestionText: string;
  questionSubQuestion: string;
  subQuestionApplicable: string;
  subQuestionReasoning: string;
  subQuestionCitations: string;
  inputJson: string;
}

function stringifyJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {});
  } catch {
    return "";
  }
}

function detailExportRowId(formKey: string, questionId: string, subQuestionId: string, subQuestionText: string): string {
  return subQuestionId ? `${formKey}:${questionId}:${subQuestionId}:${subQuestionText}` : `${formKey}:${questionId}:question`;
}

function buildQuestionExportRows(rows: AggregatedQuestionRow[]): QuestionExportRow[] {
  return rows.flatMap((row) => {
    const base = {
      questionKey: row.key,
      formId: row.formId,
      formVersion: row.formVersion,
      formKey: row.formKey,
      questionId: row.id,
      questionText: row.text,
      totalCount: row.totalCount,
      yesCount: row.yesCount,
      yesPercent: row.yesPercent,
      noCount: row.noCount,
      noPercent: row.noPercent,
      driverCount: row.driverCount,
    };

    if (row.subQuestions.length === 0) {
      return [
        {
          ...base,
          exportRowId: `${row.key}:question`,
          questionSubQuestion: row.text,
          subQuestionKey: "",
          subQuestionId: "",
          subQuestionText: "",
          subQuestionDriverCount: 0,
          subQuestionAppearances: 0,
          subQuestionDriverPercent: 0,
        },
      ];
    }

    return row.subQuestions.map((subQuestion) => ({
      ...base,
      exportRowId: subQuestion.key,
      questionSubQuestion: `${row.text} / ${subQuestion.text}`,
      subQuestionKey: subQuestion.key,
      subQuestionId: subQuestion.id,
      subQuestionText: subQuestion.text,
      subQuestionDriverCount: subQuestion.driverCount,
      subQuestionAppearances: subQuestion.totalAppearances,
      subQuestionDriverPercent: subQuestion.driverPercent,
    }));
  });
}

function buildQuestionDetailRows(rows: DashboardReviewRow[]): QuestionDetailExportRow[] {
  return rows.flatMap((row) =>
    (row.form.questions ?? []).flatMap((question) => {
      const base = {
        reviewId: row.reviewId,
        batchId: row.batchId,
        status: row.status,
        source: row.source,
        claimNumber: row.claimNumber,
        batchRun: row.runName,
        batchDescription: row.batchDescription,
        batchTemplateId: row.batchTemplateId,
        effectiveDate: row.effectiveDate,
        synthetic: row.synthetic ? "Yes" : "No",
        sourceFileIds: row.sourceFileIds,
        createdAt: row.createdAt,
        updatedAt: row.updatedAt,
        resultVersion: row.resultVersion,
        edited: row.edited ? "Yes" : "No",
        formId: row.formId,
        formVersion: row.formVersion,
        formKey: row.formKey,
        reviewOutcome: row.outcome,
        reviewOutcomeJustification: row.outcomeJustification,
        reviewTitle: row.title,
        reviewDescription: row.description,
        questionId: question.id,
        questionText: question.text,
        questionAnswer: question.answer,
        inputJson: stringifyJson(row.inputJson),
      };

      const subQuestions = question.sub_questions ?? [];

      if (subQuestions.length === 0) {
        return [
          {
            ...base,
            exportRowId: detailExportRowId(row.formKey, question.id, "", ""),
            detailRowId: `${row.reviewId}:${question.id}:question`,
            subQuestionId: "",
            subQuestionText: "",
            questionSubQuestion: question.text,
            subQuestionApplicable: "",
            subQuestionReasoning: "",
            subQuestionCitations: "",
          },
        ];
      }

      return subQuestions.map((subQuestion) => ({
        ...base,
        exportRowId: detailExportRowId(row.formKey, question.id, subQuestion.id, subQuestion.text),
        detailRowId: `${row.reviewId}:${question.id}:${subQuestion.id}`,
        subQuestionId: subQuestion.id,
        subQuestionText: subQuestion.text,
        questionSubQuestion: `${question.text} / ${subQuestion.text}`,
        subQuestionApplicable: subQuestion.answer ? "Yes" : "No",
        subQuestionReasoning: subQuestion.reasoning,
        subQuestionCitations: subQuestion.citations,
      }));
    }),
  );
}

const viewColumns: ExportColumn<QuestionExportRow>[] = [
  { header: "Export Row ID", value: (row) => row.exportRowId },
  { header: "Form", value: (row) => row.formKey },
  { header: "Question ID", value: (row) => row.questionId },
  { header: "Question", value: (row) => row.questionText },
  { header: "Sub-question ID", value: (row) => row.subQuestionId },
  { header: "Sub-question", value: (row) => row.subQuestionText },
  { header: "Total", value: (row) => row.totalCount },
  { header: "Yes", value: (row) => row.yesCount },
  { header: "% Yes", value: (row) => `${row.yesPercent}%` },
  { header: "No", value: (row) => row.noCount },
  { header: "% No", value: (row) => `${row.noPercent}%` },
  { header: "Flagged", value: (row) => (row.subQuestionId ? row.subQuestionDriverCount : row.driverCount) },
];

const dataColumns: ExportColumn<QuestionDetailExportRow>[] = [
  { header: "Export Row ID", value: (row) => row.exportRowId },
  { header: "Detail Row ID", value: (row) => row.detailRowId },
  { header: "Review ID", value: (row) => row.reviewId },
  { header: "Batch ID", value: (row) => row.batchId },
  { header: "Status", value: (row) => row.status },
  { header: "Source", value: (row) => row.source },
  { header: "Claim Number", value: (row) => row.claimNumber },
  { header: "Batch Run", value: (row) => row.batchRun },
  { header: "Batch Description", value: (row) => row.batchDescription },
  { header: "Batch Template ID", value: (row) => row.batchTemplateId },
  { header: "Effective Date", value: (row) => row.effectiveDate },
  { header: "Synthetic", value: (row) => row.synthetic },
  { header: "Source File IDs", value: (row) => row.sourceFileIds },
  { header: "Created", value: (row) => row.createdAt },
  { header: "Updated", value: (row) => row.updatedAt },
  { header: "Result Version", value: (row) => row.resultVersion },
  { header: "Edited", value: (row) => row.edited },
  { header: "Form ID", value: (row) => row.formId },
  { header: "Form Version", value: (row) => row.formVersion },
  { header: "Form Key", value: (row) => row.formKey },
  { header: "Review Outcome", value: (row) => row.reviewOutcome },
  { header: "Review Outcome Justification", value: (row) => row.reviewOutcomeJustification },
  { header: "Review Title", value: (row) => row.reviewTitle },
  { header: "Review Description", value: (row) => row.reviewDescription },
  { header: "Question ID", value: (row) => row.questionId },
  { header: "Question", value: (row) => row.questionText },
  { header: "Question Answer", value: (row) => row.questionAnswer },
  { header: "Sub-question ID", value: (row) => row.subQuestionId },
  { header: "Sub-question", value: (row) => row.subQuestionText },
  { header: "Question and Sub-question", value: (row) => row.questionSubQuestion },
  { header: "Sub-question Applicable", value: (row) => row.subQuestionApplicable },
  { header: "Sub-question Reasoning", value: (row) => row.subQuestionReasoning },
  { header: "Sub-question Citations", value: (row) => row.subQuestionCitations },
  { header: "Input JSON", value: (row) => row.inputJson },
];

function SortIcon({ active, direction }: { active: boolean; direction: SortDir }) {
  if (!active) return <ArrowUpDown className="h-3 w-3 opacity-35" />;
  return direction === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />;
}

function getSortValue(row: AggregatedQuestionRow, key: QuestionSortKey): string | number {
  return row[key];
}

export function QuestionsAggregationTable({
  rows,
  commentQuestionFilter,
  onCommentQuestionFilterChange,
  onClearCommentQuestionFilter,
}: {
  rows: DashboardReviewRow[];
  commentQuestionFilter: CommentQuestionFilter;
  onCommentQuestionFilterChange: (filter: CommentQuestionFilter) => void;
  onClearCommentQuestionFilter: () => void;
}) {
  const aggregated = useMemo(() => aggregateQuestions(rows), [rows]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [answerFilter, setAnswerFilter] = useState("all");
  const [sortKey, setSortKey] = useState<QuestionSortKey>("formKey");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [copyStatus, setCopyStatus] = useState<"idle" | "success">("idle");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);
  const activeCommentFilterCount = commentQuestionFilter.questionKeys.size + commentQuestionFilter.subQuestionKeys.size;

  const visibleRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    const filtered = aggregated.filter((row) => {
      if (answerFilter === "has_no" && row.noCount === 0) return false;
      if (answerFilter === "has_drivers" && row.driverCount === 0) return false;
      if (answerFilter === "edited" && row.editCount === 0) return false;
      if (!query) return true;
      const subSearch = row.subQuestions.map((subQuestion) => `${subQuestion.id} ${subQuestion.text}`).join(" ");
      return `${row.formKey} ${row.id} ${row.text} ${subSearch}`.toLowerCase().includes(query);
    });

    return [...filtered].sort((first, second) =>
      compareDashboardValues(getSortValue(first, sortKey), getSortValue(second, sortKey), sortDir),
    );
  }, [aggregated, answerFilter, search, sortDir, sortKey]);
  const exportRows = useMemo(() => buildQuestionExportRows(visibleRows), [visibleRows]);
  const visibleExportIds = useMemo(() => new Set(exportRows.map((row) => row.exportRowId)), [exportRows]);
  const dataExportRows = useMemo(
    () => buildQuestionDetailRows(rows).filter((row) => visibleExportIds.has(row.exportRowId)),
    [rows, visibleExportIds],
  );
  const totalPages = Math.max(1, Math.ceil(visibleRows.length / pageSize));
  const paginatedRows = useMemo(
    () => visibleRows.slice((Math.min(page, totalPages) - 1) * pageSize, Math.min(page, totalPages) * pageSize),
    [page, pageSize, totalPages, visibleRows],
  );

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const handleSort = useCallback(
    (key: QuestionSortKey) => {
      if (sortKey === key) {
        setSortDir((current) => (current === "asc" ? "desc" : "asc"));
      } else {
        setSortKey(key);
        setSortDir("asc");
      }
    },
    [sortKey],
  );

  const toggleExpand = (questionKey: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(questionKey)) next.delete(questionKey);
      else next.add(questionKey);
      return next;
    });
  };

  const expandAll = () => setExpanded(new Set(visibleRows.map((row) => row.key)));
  const collapseAll = () => setExpanded(new Set());

  const questionCheckedState = (row: AggregatedQuestionRow) => {
    const subKeys = row.subQuestions.map((subQuestion) => subQuestion.key);
    const selectedByQuestion = commentQuestionFilter.questionKeys.has(row.key);
    const selectedSubCount = subKeys.filter((key) => commentQuestionFilter.subQuestionKeys.has(key)).length;
    const checked = selectedByQuestion || (subKeys.length > 0 && selectedSubCount === subKeys.length);
    const indeterminate = !checked && selectedSubCount > 0;
    return { checked, indeterminate, selectedSubCount, subKeys };
  };

  const toggleQuestionCommentFilter = (row: AggregatedQuestionRow) => {
    const nextQuestionKeys = new Set(commentQuestionFilter.questionKeys);
    const nextSubQuestionKeys = new Set(commentQuestionFilter.subQuestionKeys);
    const { checked, subKeys } = questionCheckedState(row);

    if (checked) {
      nextQuestionKeys.delete(row.key);
      subKeys.forEach((key) => nextSubQuestionKeys.delete(key));
    } else {
      nextQuestionKeys.add(row.key);
      subKeys.forEach((key) => nextSubQuestionKeys.delete(key));
    }

    onCommentQuestionFilterChange({
      questionKeys: nextQuestionKeys,
      subQuestionKeys: nextSubQuestionKeys,
    });
  };

  const toggleSubQuestionCommentFilter = (row: AggregatedQuestionRow, subQuestion: AggregatedSubQuestionRow) => {
    const nextQuestionKeys = new Set(commentQuestionFilter.questionKeys);
    const nextSubQuestionKeys = new Set(commentQuestionFilter.subQuestionKeys);
    const siblingKeys = row.subQuestions.map((candidate) => candidate.key);

    if (nextQuestionKeys.has(row.key)) {
      nextQuestionKeys.delete(row.key);
      siblingKeys.forEach((key) => {
        if (key !== subQuestion.key) nextSubQuestionKeys.add(key);
      });
    } else if (nextSubQuestionKeys.has(subQuestion.key)) {
      nextSubQuestionKeys.delete(subQuestion.key);
    } else {
      nextSubQuestionKeys.add(subQuestion.key);
    }

    const allSiblingsSelected = siblingKeys.length > 0 && siblingKeys.every((key) => nextSubQuestionKeys.has(key));
    if (allSiblingsSelected) {
      nextQuestionKeys.add(row.key);
      siblingKeys.forEach((key) => nextSubQuestionKeys.delete(key));
    }

    onCommentQuestionFilterChange({
      questionKeys: nextQuestionKeys,
      subQuestionKeys: nextSubQuestionKeys,
    });
  };

  const copyRows = useCallback(async () => {
    await navigator.clipboard.writeText(buildTsv(dataExportRows, dataColumns));
    setCopyStatus("success");
    window.setTimeout(() => setCopyStatus("idle"), 1400);
  }, [dataExportRows]);

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="flex flex-wrap items-center gap-3 border-b bg-secondary/40 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <ListChecks className="h-4 w-4 text-primary" />
            <div>
              <h2 className="text-sm font-semibold">Question Level</h2>
              <p className="text-xs text-muted-foreground">
                {aggregated.length} form-question rows across {rows.length} reviews.
              </p>
            </div>
          </div>
          {activeCommentFilterCount ? (
            <Badge variant="warning" className="whitespace-nowrap">
              Comments filtered: {activeCommentFilterCount}
            </Badge>
          ) : null}
          <div className="relative min-w-[220px] flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="h-8 pl-9 text-xs"
              placeholder="Search questions..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <select
            value={answerFilter}
            onChange={(event) => setAnswerFilter(event.target.value)}
            className="h-8 rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="all">All questions</option>
            <option value="has_no">Has No answers</option>
            <option value="has_drivers">Has drivers</option>
            <option value="edited">Edited questions</option>
          </select>
          <Button type="button" variant="ghost" size="sm" onClick={expandAll} disabled={visibleRows.length === 0}>
            Expand
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={collapseAll} disabled={expanded.size === 0}>
            Collapse
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setSearch("");
              setAnswerFilter("all");
            }}
            disabled={!search && answerFilter === "all"}
          >
            <X className="h-3.5 w-3.5" />
            Clear
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClearCommentQuestionFilter}
            disabled={activeCommentFilterCount === 0}
          >
            Clear Comment Filter
          </Button>
          <div className="ml-auto flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => downloadText(buildCsv(dataExportRows, dataColumns), "question_level.csv", "text/csv")}
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
                  fileName: "question_level.xlsx",
                  viewSheetName: "question_view",
                  dataSheetName: "data",
                  viewRows: exportRows,
                  viewColumns,
                  dataRows: dataExportRows,
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
              <TableHead className="w-9 text-center">Filter</TableHead>
              <TableHead className="w-9" />
              {columns.map((column) => (
                <TableHead
                  key={column.key}
                  className={cn(
                    "cursor-pointer select-none whitespace-nowrap",
                    column.className,
                    column.align === "center" && "text-center",
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
                <TableCell colSpan={columns.length + 2} className="h-24 text-center text-muted-foreground">
                  No question results match the current filters.
                </TableCell>
              </TableRow>
            ) : (
              paginatedRows.map((row) => {
                const isExpanded = expanded.has(row.key);
                const hasSubQuestions = row.subQuestions.length > 0;
                const checkedState = questionCheckedState(row);
                return (
                  <Fragment key={row.key}>
                    <TableRow className={cn(hasSubQuestions && "cursor-pointer", isExpanded && "bg-secondary/30")}>
                      <TableCell className="text-center">
                        <FilterCheckbox
                          checked={checkedState.checked}
                          indeterminate={checkedState.indeterminate}
                          disabled={!hasSubQuestions}
                          onChange={() => toggleQuestionCommentFilter(row)}
                          label={
                            hasSubQuestions
                              ? `Filter comments to ${row.formKey} ${row.id}`
                              : "No sub-question comments available"
                          }
                        />
                      </TableCell>
                      <TableCell className="text-center">
                        {hasSubQuestions ? (
                          <button
                            type="button"
                            onClick={() => toggleExpand(row.key)}
                            className="inline-flex h-7 w-7 items-center justify-center rounded-md hover:bg-secondary"
                            title={isExpanded ? "Collapse sub-questions" : "Expand sub-questions"}
                            aria-label={isExpanded ? "Collapse sub-questions" : "Expand sub-questions"}
                          >
                            {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                          </button>
                        ) : null}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="whitespace-nowrap font-mono text-[10px]">
                          {row.formKey}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs font-semibold text-primary">{row.id}</TableCell>
                      <TableCell className="max-w-[440px]">
                        <span className="line-clamp-2">{row.text}</span>
                      </TableCell>
                      <TableCell className="text-center tabular-nums">{row.totalCount}</TableCell>
                      <TableCell className="text-center">
                        <Badge variant="success">{row.yesCount}</Badge>
                      </TableCell>
                      <TableCell className="text-center tabular-nums text-emerald-700 dark:text-emerald-300">
                        {row.yesPercent}%
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge variant="danger">{row.noCount}</Badge>
                      </TableCell>
                      <TableCell className="text-center tabular-nums text-rose-700 dark:text-rose-300">{row.noPercent}%</TableCell>
                      <TableCell className="text-center">
                        <Badge variant={row.driverCount ? "warning" : "outline"}>{row.driverCount}</Badge>
                      </TableCell>
                    </TableRow>
                    {isExpanded
                      ? row.subQuestions.map((subQuestion) => (
                          <TableRow key={subQuestion.key} className="bg-secondary/15">
                            <TableCell className="text-center">
                              <FilterCheckbox
                                checked={
                                  commentQuestionFilter.questionKeys.has(row.key) ||
                                  commentQuestionFilter.subQuestionKeys.has(subQuestion.key)
                                }
                                onChange={() => toggleSubQuestionCommentFilter(row, subQuestion)}
                                label={`Filter comments to ${row.formKey} ${subQuestion.id}`}
                              />
                            </TableCell>
                            <TableCell />
                            <TableCell />
                            <TableCell className="pl-6 font-mono text-xs text-muted-foreground">{subQuestion.id}</TableCell>
                            <TableCell className="max-w-[520px] text-sm text-muted-foreground" colSpan={4}>
                              <span className="line-clamp-2">{subQuestion.text}</span>
                            </TableCell>
                            <TableCell className="text-center" colSpan={2}>
                              <Badge variant={subQuestion.driverCount ? "warning" : "outline"}>
                                Flagged {subQuestion.driverCount} of {subQuestion.questionNoCount} No answers
                              </Badge>
                            </TableCell>
                            <TableCell className="text-center tabular-nums text-amber-700 dark:text-amber-300">
                              {subQuestion.driverPercent}% flagged
                            </TableCell>
                          </TableRow>
                        ))
                      : null}
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
