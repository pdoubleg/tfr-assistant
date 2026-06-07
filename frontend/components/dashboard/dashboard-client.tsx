"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCheck, Database, Filter, Loader2, RefreshCw, Search, X } from "lucide-react";

import { CommentsReportTable } from "@/components/dashboard/comments-report-table";
import { DashboardCharts } from "@/components/dashboard/dashboard-charts";
import { FormViewerSheet } from "@/components/dashboard/form-viewer-sheet";
import { FormsDataTable } from "@/components/dashboard/forms-data-table";
import { QuestionsAggregationTable } from "@/components/dashboard/questions-aggregation-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  listEvalRunItems,
  listEvalRuns,
  listPublishedDatasetRows,
  listPublishedDatasets,
  listReviews,
  getReview,
} from "@/lib/api";
import {
  defaultDashboardFilters,
  derivePublishedDatasetRows,
  deriveReviewRows,
  deriveVersionComparisonRows,
  filterDashboardRows,
  getFilterOptions,
  resultVersionLabels,
  type DashboardFilters,
  type DashboardReviewRow,
  type CommentQuestionFilter,
  type ResultVersionKind,
} from "@/lib/dashboard-data";
import type {
  EvalDatasetRecord,
  EvalRunItemRecord,
  EvalRunRecord,
  PublishedDatasetRow,
  ReviewRecord,
} from "@/lib/types";

const dashboardSettingsKey = "tfr-dashboard-settings";

interface PersistedDashboardSettings {
  filters?: DashboardFilters;
  commentQuestionFilter?: {
    questionKeys?: string[];
    subQuestionKeys?: string[];
  };
}

function loadDashboardSettings(): PersistedDashboardSettings | null {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(window.localStorage.getItem(dashboardSettingsKey) ?? "null") as PersistedDashboardSettings | null;
  } catch {
    return null;
  }
}

function saveDashboardSettings(settings: PersistedDashboardSettings): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(dashboardSettingsKey, JSON.stringify(settings));
}

function SelectControl({
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
    <label className="space-y-1">
      <span className="block text-[11px] font-semibold uppercase text-muted-foreground">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {children}
      </select>
    </label>
  );
}

function DateControl({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="space-y-1">
      <span className="block text-[11px] font-semibold uppercase text-muted-foreground">{label}</span>
      <Input type="date" value={value} onChange={(event) => onChange(event.target.value)} className="h-9 text-sm" />
    </label>
  );
}

function buildEvalGroundTruthReviews(
  runs: EvalRunRecord[],
  itemsByRun: Record<string, EvalRunItemRecord[]>,
): ReviewRecord[] {
  return runs.flatMap((run) =>
    (itemsByRun[run.id] ?? []).flatMap((item) =>
      item.ground_truths.map((truth) => ({
        id: `eval-ground-truth:${run.id}:${truth.id}`,
        form_id: truth.result.form_id,
        form_version: truth.result.form_version,
        status: "completed",
        source: "eval",
        input_json: {
          claim_number: item.claim_number,
          effective_date: item.effective_date ?? "",
          batch_run_name: run.name,
          eval_run_id: run.id,
          eval_run_name: run.name,
          eval_dataset_id: run.dataset_id,
          eval_result_role: "ground_truth",
          eval_reference_kind: truth.reference_kind,
          eval_config_version: run.config_version,
          synthetic: false,
        },
        original: truth.result,
        user_version: truth.result,
        created_at: truth.created_at ?? item.created_at,
        updated_at: item.updated_at ?? truth.created_at,
      }) satisfies ReviewRecord),
    ),
  );
}

export function DashboardClient() {
  const [sourceMode, setSourceMode] = useState<"reviews" | "dataset">("reviews");
  const [reviews, setReviews] = useState<ReviewRecord[]>([]);
  const [datasets, setDatasets] = useState<EvalDatasetRecord[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [datasetRows, setDatasetRows] = useState<PublishedDatasetRow[]>([]);
  const [filters, setFilters] = useState<DashboardFilters>(defaultDashboardFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedRow, setSelectedRow] = useState<DashboardReviewRow | null>(null);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [commentQuestionFilter, setCommentQuestionFilter] = useState<CommentQuestionFilter>({
    questionKeys: new Set(),
    subQuestionKeys: new Set(),
  });
  const [settingsLoaded, setSettingsLoaded] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const nextDatasets = await listPublishedDatasets();
      setDatasets(nextDatasets);
      if (sourceMode === "dataset") {
        const datasetId = selectedDatasetId || nextDatasets[0]?.id || "";
        if (datasetId && datasetId !== selectedDatasetId) setSelectedDatasetId(datasetId);
        setDatasetRows(datasetId ? await listPublishedDatasetRows(datasetId) : []);
      } else {
        const [nextReviews, evalRuns] = await Promise.all([listReviews(), listEvalRuns()]);
        const evalItemsEntries = await Promise.all(
          evalRuns.map(async (run) => [run.id, await listEvalRunItems(run.id)] as const),
        );
        const evalGroundTruthReviews = buildEvalGroundTruthReviews(
          evalRuns,
          Object.fromEntries(evalItemsEntries),
        );
        setReviews([...nextReviews, ...evalGroundTruthReviews]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }, [selectedDatasetId, sourceMode]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const saved = loadDashboardSettings();
    if (saved?.filters) {
      setFilters({ ...defaultDashboardFilters, ...saved.filters });
    }
    if (saved?.commentQuestionFilter) {
      setCommentQuestionFilter({
        questionKeys: new Set(saved.commentQuestionFilter.questionKeys ?? []),
        subQuestionKeys: new Set(saved.commentQuestionFilter.subQuestionKeys ?? []),
      });
    }
    setSettingsLoaded(true);
  }, []);

  useEffect(() => {
    if (!settingsLoaded) return;
    saveDashboardSettings({
      filters,
      commentQuestionFilter: {
        questionKeys: Array.from(commentQuestionFilter.questionKeys),
        subQuestionKeys: Array.from(commentQuestionFilter.subQuestionKeys),
      },
    });
  }, [commentQuestionFilter.questionKeys, commentQuestionFilter.subQuestionKeys, filters, settingsLoaded]);

  const allRows = useMemo(
    () =>
      sourceMode === "dataset"
        ? derivePublishedDatasetRows(datasetRows)
        : deriveReviewRows(reviews, filters.resultVersion),
    [datasetRows, filters.resultVersion, reviews, sourceMode],
  );
  const filteredRows = useMemo(() => filterDashboardRows(allRows, filters), [allRows, filters]);
  const versionComparisonRows = useMemo(
    () =>
      sourceMode === "dataset"
        ? filteredRows
        : filterDashboardRows(deriveVersionComparisonRows(reviews), filters),
    [filteredRows, filters, reviews, sourceMode],
  );
  const filterOptions = useMemo(() => getFilterOptions(allRows), [allRows]);
  const completedReviewCount = allRows.length;

  const setFilter = <K extends keyof DashboardFilters>(key: K, value: DashboardFilters[K]) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const openRow = (row: DashboardReviewRow) => {
    setSelectedRow(row);
    setViewerOpen(true);
  };

  const refreshReview = useCallback(
    async (reviewId: string) => {
      if (sourceMode === "dataset" || reviewId.startsWith("eval-ground-truth:")) return;
      const updatedReview = await getReview(reviewId);
      setReviews((current) =>
        current.map((review) => (review.id === reviewId ? updatedReview : review)),
      );
      const nextRow = deriveReviewRows([updatedReview], filters.resultVersion)[0];
      if (nextRow) {
        setSelectedRow((current) => (current?.reviewId === reviewId ? nextRow : current));
      }
    },
    [filters.resultVersion, sourceMode],
  );

  const clearCommentQuestionFilter = () =>
    setCommentQuestionFilter({
      questionKeys: new Set(),
      subQuestionKeys: new Set(),
    });

  const clearFilters = () => {
    setFilters(defaultDashboardFilters);
    clearCommentQuestionFilter();
  };

  const refreshDataAndFilters = () => {
    clearFilters();
    void refresh();
  };

  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-4 p-4 lg:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Review volume, audit outcomes, question results, and stored comments.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-md border bg-card p-1">
            {(["reviews", "dataset"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setSourceMode(mode)}
                className={[
                  "rounded px-3 py-1.5 text-xs font-medium",
                  sourceMode === mode
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                ].join(" ")}
              >
                {mode === "reviews" ? "Reviews" : "Dataset"}
              </button>
            ))}
          </div>
          {sourceMode === "dataset" ? (
            <label className="flex items-center gap-2 rounded-md border bg-card px-2 py-1.5 text-xs text-muted-foreground">
              <Database className="h-3.5 w-3.5 text-primary" />
              <select
                value={selectedDatasetId}
                onChange={(event) => setSelectedDatasetId(event.target.value)}
                className="max-w-[260px] bg-transparent text-foreground outline-none"
              >
                {datasets.length === 0 ? <option value="">No datasets</option> : null}
                {datasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <Button type="button" variant="outline" size="sm" onClick={refreshDataAndFilters} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Refresh
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="mb-3 flex items-center gap-2">
            <Filter className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold">Filters</h2>
            <span className="text-xs text-muted-foreground">
              {filteredRows.length} of {completedReviewCount} completed reviews
            </span>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(220px,1.4fr)_repeat(8,minmax(130px,1fr))_auto]">
            <label className="space-y-1">
              <span className="block text-[11px] font-semibold uppercase text-muted-foreground">Search</span>
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={filters.search}
                  onChange={(event) => setFilter("search", event.target.value)}
                  className="h-9 pl-9 text-sm"
                  placeholder="Claim, run, form, outcome..."
                />
              </div>
            </label>

            <SelectControl
              label="Result"
              value={filters.resultVersion}
              onChange={(value) => setFilter("resultVersion", value as ResultVersionKind)}
            >
              {Object.entries(resultVersionLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </SelectControl>

            <SelectControl label="Form" value={filters.formId} onChange={(value) => setFilter("formId", value)}>
              <option value="all">All forms</option>
              {filterOptions.formIds.map((formId) => (
                <option key={formId} value={formId}>
                  {formId}
                </option>
              ))}
            </SelectControl>

            <SelectControl
              label="Version"
              value={filters.formVersion}
              onChange={(value) => setFilter("formVersion", value)}
            >
              <option value="all">All versions</option>
              {filterOptions.formVersions.map((version) => (
                <option key={version} value={version}>
                  {version}
                </option>
              ))}
            </SelectControl>

            <SelectControl label="Source" value={filters.source} onChange={(value) => setFilter("source", value)}>
              <option value="all">All sources</option>
              {filterOptions.sources.map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
            </SelectControl>

            <SelectControl label="Outcome" value={filters.outcome} onChange={(value) => setFilter("outcome", value)}>
              <option value="all">All outcomes</option>
              <option value="Meets">Meets</option>
              <option value="Does Not Meet">Does Not Meet</option>
            </SelectControl>

            <SelectControl label="Eval Role" value={filters.evalRole} onChange={(value) => setFilter("evalRole", value)}>
              <option value="all">All eval roles</option>
              {filterOptions.evalRoles.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </SelectControl>

            <DateControl label="From" value={filters.dateFrom} onChange={(value) => setFilter("dateFrom", value)} />
            <DateControl label="To" value={filters.dateTo} onChange={(value) => setFilter("dateTo", value)} />

            <div className="flex items-end gap-2">
              <Button
                type="button"
                variant={filters.finalizedOnly ? "default" : "outline"}
                size="sm"
                onClick={() => setFilter("finalizedOnly", !filters.finalizedOnly)}
                aria-pressed={filters.finalizedOnly}
                className={
                  filters.finalizedOnly
                    ? "border border-primary shadow-sm ring-2 ring-primary/25"
                    : undefined
                }
              >
                <CheckCheck className="h-3.5 w-3.5" />
                Finalized
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={clearFilters}>
                <X className="h-3.5 w-3.5" />
                Clear
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {error ? (
        <Card className="border-destructive/40">
          <CardContent className="p-4 text-sm text-destructive">{error}</CardContent>
        </Card>
      ) : null}

      {loading && reviews.length === 0 ? (
        <Card>
          <CardContent className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading dashboard data
          </CardContent>
        </Card>
      ) : null}

      <DashboardCharts rows={filteredRows} versionComparisonRows={versionComparisonRows} />

      <FormsDataTable
        rows={filteredRows}
        totalCount={completedReviewCount}
        selectedReviewId={selectedRow?.reviewId}
        onViewReview={openRow}
      />
      <QuestionsAggregationTable
        rows={filteredRows}
        commentQuestionFilter={commentQuestionFilter}
        onCommentQuestionFilterChange={setCommentQuestionFilter}
        onClearCommentQuestionFilter={clearCommentQuestionFilter}
      />
      <CommentsReportTable
        rows={filteredRows}
        questionFilter={commentQuestionFilter}
        onClearQuestionFilter={clearCommentQuestionFilter}
        onViewReview={openRow}
      />

      <FormViewerSheet
        row={selectedRow}
        open={viewerOpen}
        onOpenChange={setViewerOpen}
        onFeedbackSubmitted={refreshReview}
      />
    </div>
  );
}
