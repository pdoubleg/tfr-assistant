"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Filter, Loader2, RefreshCw, Search, X } from "lucide-react";

import { CommentsReportTable } from "@/components/dashboard/comments-report-table";
import { DashboardCharts } from "@/components/dashboard/dashboard-charts";
import { FormViewerSheet } from "@/components/dashboard/form-viewer-sheet";
import { FormsDataTable } from "@/components/dashboard/forms-data-table";
import { QuestionsAggregationTable } from "@/components/dashboard/questions-aggregation-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { listReviews } from "@/lib/api";
import {
  defaultDashboardFilters,
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
import type { ReviewRecord } from "@/lib/types";

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

export function DashboardClient() {
  const [reviews, setReviews] = useState<ReviewRecord[]>([]);
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
      const nextReviews = await listReviews();
      setReviews(nextReviews);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }, []);

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

  const allRows = useMemo(() => deriveReviewRows(reviews, filters.resultVersion), [filters.resultVersion, reviews]);
  const filteredRows = useMemo(() => filterDashboardRows(allRows, filters), [allRows, filters]);
  const versionComparisonRows = useMemo(
    () => filterDashboardRows(deriveVersionComparisonRows(reviews), filters),
    [filters, reviews],
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
        <Button type="button" variant="outline" size="sm" onClick={refreshDataAndFilters} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Refresh
        </Button>
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
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(220px,1.4fr)_repeat(7,minmax(130px,1fr))_auto]">
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

            <DateControl label="From" value={filters.dateFrom} onChange={(value) => setFilter("dateFrom", value)} />
            <DateControl label="To" value={filters.dateTo} onChange={(value) => setFilter("dateTo", value)} />

            <div className="flex items-end">
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

      <FormViewerSheet row={selectedRow} open={viewerOpen} onOpenChange={setViewerOpen} />
    </div>
  );
}
