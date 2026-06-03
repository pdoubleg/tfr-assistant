"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { Activity, BarChart3, Gauge, LineChart, Pencil, SlidersHorizontal, TrendingUp } from "lucide-react";

import { PlotlyChart } from "@/components/a2ui/plotly-chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  evalRoleLabel,
  percent,
  trendCompareLabels,
  trendMetricLabels,
  type DashboardReviewRow,
  type TrendCompareBy,
  type TrendGranularity,
  type TrendMetric,
} from "@/lib/dashboard-data";
import { buildViridisColorway, hexToRgba, VIRIDIS_CONTROL_COLORS } from "@/lib/plotly-theme";
import { cn } from "@/lib/utils";

type ChartMode = "line" | "bar";
type PlotView = "trend" | "aggregate" | "questions" | "drivers";
type MetricFormat = "count" | "percent" | "currency";
type DashboardDimension =
  | "none"
  | "form_id"
  | "form_version"
  | "source"
  | "outcome"
  | "result_version"
  | "eval_result_role";
type AggregateMetric =
  | "review_volume"
  | "meets_count"
  | "does_not_meet_count"
  | "question_total"
  | "question_no_count"
  | "question_no_rate"
  | "driver_review_count"
  | "driver_count"
  | "overwrite_total"
  | "underwrite_total"
  | "net_exception";
type QuestionMetric =
  | "total_count"
  | "yes_count"
  | "no_count"
  | "no_percent"
  | "driver_count"
  | "overwrite_total"
  | "underwrite_total"
  | "net_exception";
type DriverMetric = "driver_count" | "driver_percent" | "appearance_count";

const chartSettingsKey = "tfr-dashboard-chart-settings";
const maxSegmentCount = 6;
const topLimitOptions = [8, 12, 20] as const;
const metricCardColors = [
  VIRIDIS_CONTROL_COLORS[4],
  VIRIDIS_CONTROL_COLORS[7],
  VIRIDIS_CONTROL_COLORS[2],
  VIRIDIS_CONTROL_COLORS[8],
] as const;

interface PersistedChartSettings {
  plotView?: PlotView;
  granularity?: TrendGranularity;
  metric?: TrendMetric;
  trendMetric?: TrendMetric;
  compareBy?: TrendCompareBy;
  trendCompareBy?: TrendCompareBy;
  mode?: ChartMode;
  aggregateMetric?: AggregateMetric;
  aggregateDimension?: DashboardDimension;
  aggregateSegmentBy?: DashboardDimension;
  questionMetric?: QuestionMetric;
  questionSegmentBy?: DashboardDimension;
  driverMetric?: DriverMetric;
  driverSegmentBy?: DashboardDimension;
  topLimit?: number;
}

interface DashboardFigure {
  data: Record<string, unknown>[];
  layout: Record<string, unknown>;
  emptyMessage: string;
}

interface ReviewStats {
  totalReviews: number;
  meetsCount: number;
  doesNotMeetCount: number;
  totalQuestions: number;
  noQuestions: number;
  driverReviews: number;
  driverCount: number;
  totalReviewed: number;
  overwriteTotal: number;
  underwriteTotal: number;
  netException: number;
}

interface TrendPoint extends ReviewStats {
  bucket: string;
  label: string;
  value: number;
}

interface TrendSeries {
  key: string;
  label: string;
  points: TrendPoint[];
}

interface AggregateBucket {
  key: string;
  label: string;
  total: ReviewStats;
  segments: Map<string, ReviewStats>;
}

interface QuestionStats {
  totalCount: number;
  yesCount: number;
  noCount: number;
  driverCount: number;
  totalOverwriteDollars: number;
  totalUnderwriteDollars: number;
}

interface DriverStats {
  driverCount: number;
  totalAppearances: number;
  questionNoCount: number;
}

interface LabelledStats<TStats> {
  key: string;
  context: string;
  text: string;
  fullLabel: string;
  total: TStats;
  segments: Map<string, TStats>;
}

const plotViewLabels: Record<PlotView, string> = {
  trend: "Trend",
  aggregate: "Aggregate",
  questions: "Questions",
  drivers: "Drivers",
};

const dimensionLabels: Record<DashboardDimension, string> = {
  none: "All reviews",
  form_id: "Form",
  form_version: "Form version",
  source: "Source",
  outcome: "Outcome",
  result_version: "Result version",
  eval_result_role: "Eval role",
};

const aggregateMetricLabels: Record<AggregateMetric, string> = {
  review_volume: "Review volume",
  meets_count: "Meets count",
  does_not_meet_count: "Does Not Meet count",
  question_total: "Question total",
  question_no_count: "Question No count",
  question_no_rate: "Question No %",
  driver_review_count: "Reviews with drivers",
  driver_count: "Driver count",
  overwrite_total: "Overwrite total",
  underwrite_total: "Underwrite total",
  net_exception: "Net exception",
};

const aggregateMetricFormats: Record<AggregateMetric, MetricFormat> = {
  review_volume: "count",
  meets_count: "count",
  does_not_meet_count: "count",
  question_total: "count",
  question_no_count: "count",
  question_no_rate: "percent",
  driver_review_count: "count",
  driver_count: "count",
  overwrite_total: "currency",
  underwrite_total: "currency",
  net_exception: "currency",
};

const questionMetricLabels: Record<QuestionMetric, string> = {
  total_count: "Total answers",
  yes_count: "Yes answers",
  no_count: "No answers",
  no_percent: "No %",
  driver_count: "Driver count",
  overwrite_total: "Overwrite total",
  underwrite_total: "Underwrite total",
  net_exception: "Net exception",
};

const questionMetricFormats: Record<QuestionMetric, MetricFormat> = {
  total_count: "count",
  yes_count: "count",
  no_count: "count",
  no_percent: "percent",
  driver_count: "count",
  overwrite_total: "currency",
  underwrite_total: "currency",
  net_exception: "currency",
};

const driverMetricLabels: Record<DriverMetric, string> = {
  driver_count: "Applicable drivers",
  driver_percent: "Applicable driver %",
  appearance_count: "Sub-question appearances",
};

const driverMetricFormats: Record<DriverMetric, MetricFormat> = {
  driver_count: "count",
  driver_percent: "percent",
  appearance_count: "count",
};

const trendMetricFormats: Record<TrendMetric, MetricFormat> = {
  review_volume: "count",
  meets_rate: "percent",
  does_not_meet_rate: "percent",
  question_no_rate: "percent",
  driver_review_rate: "percent",
  overwrite_percent: "percent",
  underwrite_percent: "percent",
  overwrite_total: "currency",
  underwrite_total: "currency",
  net_exception: "currency",
};

const dimensionOptions: DashboardDimension[] = [
  "none",
  "form_id",
  "form_version",
  "source",
  "outcome",
  "result_version",
  "eval_result_role",
];

function loadChartSettings(): PersistedChartSettings | null {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(window.localStorage.getItem(chartSettingsKey) ?? "null") as PersistedChartSettings | null;
  } catch {
    return null;
  }
}

function saveChartSettings(settings: PersistedChartSettings): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(chartSettingsKey, JSON.stringify(settings));
}

function startOfWeek(date: Date): Date {
  const next = new Date(date);
  const day = next.getDay();
  next.setDate(next.getDate() - day);
  next.setHours(0, 0, 0, 0);
  return next;
}

function bucketFor(value: string, granularity: TrendGranularity): { key: string; label: string } | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;

  if (granularity === "month") {
    const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
    return {
      key,
      label: new Intl.DateTimeFormat("en-US", { month: "short", year: "2-digit" }).format(date),
    };
  }

  if (granularity === "week") {
    const week = startOfWeek(date);
    const key = week.toISOString().slice(0, 10);
    return {
      key,
      label: `Wk ${new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(week)}`,
    };
  }

  return {
    key: date.toISOString().slice(0, 10),
    label: new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date),
  };
}

function emptyReviewStats(): ReviewStats {
  return {
    totalReviews: 0,
    meetsCount: 0,
    doesNotMeetCount: 0,
    totalQuestions: 0,
    noQuestions: 0,
    driverReviews: 0,
    driverCount: 0,
    totalReviewed: 0,
    overwriteTotal: 0,
    underwriteTotal: 0,
    netException: 0,
  };
}

function addRowToReviewStats(stats: ReviewStats, row: DashboardReviewRow): void {
  stats.totalReviews += 1;
  stats.meetsCount += row.outcome === "Meets" ? 1 : 0;
  stats.doesNotMeetCount += row.outcome === "Does Not Meet" ? 1 : 0;
  stats.totalQuestions += row.questionCount;
  stats.noQuestions += row.noCount;
  stats.driverReviews += row.driverCount > 0 ? 1 : 0;
  stats.driverCount += row.driverCount;
  stats.totalReviewed += row.totalAmountReviewedDollars ?? 0;
  stats.overwriteTotal += row.totalOverwriteDollars;
  stats.underwriteTotal += row.totalUnderwriteDollars;
  stats.netException += row.netExceptionDollars;
}

function mergeReviewStats(target: ReviewStats, source: ReviewStats): void {
  target.totalReviews += source.totalReviews;
  target.meetsCount += source.meetsCount;
  target.doesNotMeetCount += source.doesNotMeetCount;
  target.totalQuestions += source.totalQuestions;
  target.noQuestions += source.noQuestions;
  target.driverReviews += source.driverReviews;
  target.driverCount += source.driverCount;
  target.totalReviewed += source.totalReviewed;
  target.overwriteTotal += source.overwriteTotal;
  target.underwriteTotal += source.underwriteTotal;
  target.netException += source.netException;
}

function emptyPoint(bucket: string, label: string): TrendPoint {
  return {
    bucket,
    label,
    value: 0,
    ...emptyReviewStats(),
  };
}

function trendMetricValue(point: ReviewStats, metric: TrendMetric): number {
  if (metric === "review_volume") return point.totalReviews;
  if (metric === "meets_rate") return percent(point.meetsCount, point.totalReviews);
  if (metric === "does_not_meet_rate") return percent(point.doesNotMeetCount, point.totalReviews);
  if (metric === "question_no_rate") return percent(point.noQuestions, point.totalQuestions);
  if (metric === "overwrite_percent") return percent(point.overwriteTotal, point.totalReviewed, 2);
  if (metric === "underwrite_percent") return percent(point.underwriteTotal, point.totalReviewed, 2);
  if (metric === "overwrite_total") return point.overwriteTotal;
  if (metric === "underwrite_total") return point.underwriteTotal;
  if (metric === "net_exception") return point.netException;
  return percent(point.driverReviews, point.totalReviews);
}

function aggregateMetricValue(point: ReviewStats, metric: AggregateMetric): number {
  if (metric === "review_volume") return point.totalReviews;
  if (metric === "meets_count") return point.meetsCount;
  if (metric === "does_not_meet_count") return point.doesNotMeetCount;
  if (metric === "question_total") return point.totalQuestions;
  if (metric === "question_no_count") return point.noQuestions;
  if (metric === "question_no_rate") return percent(point.noQuestions, point.totalQuestions);
  if (metric === "driver_review_count") return point.driverReviews;
  if (metric === "driver_count") return point.driverCount;
  if (metric === "overwrite_total") return point.overwriteTotal;
  if (metric === "underwrite_total") return point.underwriteTotal;
  return point.netException;
}

function dimensionValue(row: DashboardReviewRow, dimension: DashboardDimension | TrendCompareBy): string {
  if (dimension === "form_id") return row.formId || "Unknown form";
  if (dimension === "form_version") return row.formKey || "Unknown version";
  if (dimension === "source") return row.source || "Unknown source";
  if (dimension === "outcome") return row.outcome || "Unknown outcome";
  if (dimension === "result_version") return row.resultVersion === "original" ? "Original agent" : "Current user";
  if (dimension === "eval_result_role") return evalRoleLabel(row.evalResultRole, row.evalReferenceKind);
  return "All filtered reviews";
}

function buildTrendSeries(
  rows: DashboardReviewRow[],
  granularity: TrendGranularity,
  metric: TrendMetric,
  compareBy: TrendCompareBy,
): TrendSeries[] {
  const allBuckets = new Map<string, string>();
  const seriesMap = new Map<string, Map<string, TrendPoint>>();
  const totalsBySeries = new Map<string, number>();

  for (const row of rows) {
    const bucket = bucketFor(row.createdAt || row.updatedAt, granularity);
    if (!bucket) continue;
    const key = dimensionValue(row, compareBy);
    allBuckets.set(bucket.key, bucket.label);
    totalsBySeries.set(key, (totalsBySeries.get(key) ?? 0) + 1);

    let pointMap = seriesMap.get(key);
    if (!pointMap) {
      pointMap = new Map();
      seriesMap.set(key, pointMap);
    }

    let point = pointMap.get(bucket.key);
    if (!point) {
      point = emptyPoint(bucket.key, bucket.label);
      pointMap.set(bucket.key, point);
    }
    addRowToReviewStats(point, row);
  }

  const sortedBuckets = Array.from(allBuckets.entries()).sort(([first], [second]) => first.localeCompare(second));
  const sortedSeries = Array.from(seriesMap.entries())
    .sort(([firstKey], [secondKey]) => (totalsBySeries.get(secondKey) ?? 0) - (totalsBySeries.get(firstKey) ?? 0))
    .slice(0, maxSegmentCount);

  return sortedSeries.map(([key, pointMap]) => ({
    key,
    label: key,
    points: sortedBuckets.map(([bucketKey, label]) => {
      const point = pointMap.get(bucketKey) ?? emptyPoint(bucketKey, label);
      return {
        ...point,
        label,
        value: trendMetricValue(point, metric),
      };
    }),
  }));
}

function metricToken(axis: "x" | "y", format: MetricFormat): string {
  const precision = format === "currency" ? ",.2f" : format === "percent" ? ",.1f" : ",.0f";
  const prefix = format === "currency" ? "$" : "";
  const suffix = format === "percent" ? "%" : "";
  return `${prefix}%{${axis}:${precision}}${suffix}`;
}

function valueAxisLayout(format: MetricFormat, title: string): Record<string, unknown> {
  const axis: Record<string, unknown> = {
    title: { text: title },
    automargin: true,
    rangemode: "tozero",
    tickformat: format === "currency" ? ",.0f" : ",.0f",
  };
  if (format === "currency") {
    axis.tickprefix = "$";
  }
  if (format === "percent") {
    axis.range = [0, 100];
    axis.ticksuffix = "%";
  }
  return axis;
}

function baseLayout(partial: Record<string, unknown>): Record<string, unknown> {
  return {
    autosize: true,
    margin: { l: 70, r: 28, t: 18, b: 64 },
    legend: {
      orientation: "h",
      yanchor: "bottom",
      y: 1.02,
      xanchor: "right",
      x: 1,
    },
    ...partial,
  };
}

function buildTrendFigure(
  rows: DashboardReviewRow[],
  granularity: TrendGranularity,
  metric: TrendMetric,
  compareBy: TrendCompareBy,
  mode: ChartMode,
): DashboardFigure {
  const series = buildTrendSeries(rows, granularity, metric, compareBy);
  const format = trendMetricFormats[metric];
  const labels = series[0]?.points.map((point) => point.label) ?? [];
  const data = series.map((item) => {
    const values = item.points.map((point) => point.value);
    const customdata = item.points.map((point) => [
      point.totalReviews,
      point.meetsCount,
      point.doesNotMeetCount,
      point.noQuestions,
      point.totalQuestions,
      point.driverReviews,
    ]);
    const hovertemplate = [
      `<b>${item.label}</b>`,
      "%{x}",
      `${trendMetricLabels[metric]}: ${metricToken("y", format)}`,
      "Reviews: %{customdata[0]:,.0f}",
      "Meets: %{customdata[1]:,.0f}",
      "Does Not Meet: %{customdata[2]:,.0f}",
      "Question No: %{customdata[3]:,.0f} of %{customdata[4]:,.0f}",
      "Reviews with drivers: %{customdata[5]:,.0f}",
      "<extra></extra>",
    ].join("<br>");

    if (mode === "line") {
      return {
        type: "scatter",
        mode: "lines+markers",
        name: item.label,
        x: labels,
        y: values,
        customdata,
        hovertemplate,
        line: { width: 3 },
        marker: { size: 7 },
      };
    }

    return {
      type: "bar",
      name: item.label,
      x: labels,
      y: values,
      customdata,
      hovertemplate,
    };
  });

  return {
    data,
    emptyMessage: "No trend data for the current filters.",
    layout: baseLayout({
      barmode: "group",
      hovermode: mode === "line" ? "x unified" : "closest",
      xaxis: {
        title: { text: "Time" },
        type: "category",
        automargin: true,
      },
      yaxis: valueAxisLayout(format, trendMetricLabels[metric]),
    }),
  };
}

function ensureAggregateBucket(map: Map<string, AggregateBucket>, key: string, label: string): AggregateBucket {
  let bucket = map.get(key);
  if (!bucket) {
    bucket = {
      key,
      label,
      total: emptyReviewStats(),
      segments: new Map(),
    };
    map.set(key, bucket);
  }
  return bucket;
}

function ensureReviewStats(map: Map<string, ReviewStats>, key: string): ReviewStats {
  let stats = map.get(key);
  if (!stats) {
    stats = emptyReviewStats();
    map.set(key, stats);
  }
  return stats;
}

function topAggregateSegments(buckets: AggregateBucket[], metric: AggregateMetric): string[] {
  const totals = new Map<string, ReviewStats>();
  for (const bucket of buckets) {
    for (const [segment, stats] of bucket.segments) {
      mergeReviewStats(ensureReviewStats(totals, segment), stats);
    }
  }
  return Array.from(totals.entries())
    .sort(([firstKey, first], [secondKey, second]) => {
      const valueCompare = aggregateMetricValue(second, metric) - aggregateMetricValue(first, metric);
      return valueCompare || firstKey.localeCompare(secondKey, undefined, { numeric: true });
    })
    .slice(0, maxSegmentCount)
    .map(([segment]) => segment);
}

function buildAggregateFigure(
  rows: DashboardReviewRow[],
  metric: AggregateMetric,
  dimension: DashboardDimension,
  segmentBy: DashboardDimension,
  topLimit: number,
): DashboardFigure {
  const effectiveSegmentBy = segmentBy === dimension ? "none" : segmentBy;
  const buckets = new Map<string, AggregateBucket>();

  for (const row of rows) {
    const bucketLabel = dimensionValue(row, dimension);
    const bucket = ensureAggregateBucket(buckets, bucketLabel, bucketLabel);
    const segmentLabel = effectiveSegmentBy === "none" ? "Total" : dimensionValue(row, effectiveSegmentBy);
    addRowToReviewStats(bucket.total, row);
    addRowToReviewStats(ensureReviewStats(bucket.segments, segmentLabel), row);
  }

  const sortedBuckets = Array.from(buckets.values())
    .sort((first, second) => {
      const valueCompare = aggregateMetricValue(second.total, metric) - aggregateMetricValue(first.total, metric);
      return valueCompare || first.label.localeCompare(second.label, undefined, { numeric: true });
    })
    .slice(0, topLimit);
  const segments = effectiveSegmentBy === "none" ? ["Total"] : topAggregateSegments(sortedBuckets, metric);
  const labels = sortedBuckets.map((bucket) => bucket.label);
  const format = aggregateMetricFormats[metric];
  const metricLabel = aggregateMetricLabels[metric];

  const data =
    effectiveSegmentBy === "none"
      ? [
          {
            type: "bar",
            name: metricLabel,
            x: labels,
            y: sortedBuckets.map((bucket) => aggregateMetricValue(bucket.total, metric)),
            marker: { color: buildViridisColorway(Math.max(labels.length, 1)).slice(0, labels.length) },
            hovertemplate: `<b>%{x}</b><br>${metricLabel}: ${metricToken("y", format)}<extra></extra>`,
          },
        ]
      : segments.map((segment) => ({
          type: "bar",
          name: segment,
          x: labels,
          y: sortedBuckets.map((bucket) => aggregateMetricValue(bucket.segments.get(segment) ?? emptyReviewStats(), metric)),
          hovertemplate: `<b>%{x}</b><br>${metricLabel}: ${metricToken("y", format)}<extra>${segment}</extra>`,
        }));

  return {
    data: labels.length ? data : [],
    emptyMessage: "No aggregate data for the current filters.",
    layout: baseLayout({
      barmode: "group",
      xaxis: {
        title: { text: dimensionLabels[dimension] },
        type: "category",
        automargin: true,
        tickangle: labels.length > 6 ? -25 : 0,
      },
      yaxis: valueAxisLayout(format, metricLabel),
    }),
  };
}

function emptyQuestionStats(): QuestionStats {
  return {
    totalCount: 0,
    yesCount: 0,
    noCount: 0,
    driverCount: 0,
    totalOverwriteDollars: 0,
    totalUnderwriteDollars: 0,
  };
}

function addQuestionToStats(stats: QuestionStats, question: DashboardReviewRow["form"]["questions"][number]): void {
  stats.totalCount += 1;
  stats.yesCount += question.answer === "Yes" ? 1 : 0;
  stats.noCount += question.answer === "No" ? 1 : 0;
  stats.driverCount += (question.sub_questions ?? []).filter((subQuestion) => Boolean(subQuestion.answer)).length;
  stats.totalOverwriteDollars += Number(question.overwrite_dollars) || 0;
  stats.totalUnderwriteDollars += Number(question.underwrite_dollars) || 0;
}

function mergeQuestionStats(target: QuestionStats, source: QuestionStats): void {
  target.totalCount += source.totalCount;
  target.yesCount += source.yesCount;
  target.noCount += source.noCount;
  target.driverCount += source.driverCount;
  target.totalOverwriteDollars += source.totalOverwriteDollars;
  target.totalUnderwriteDollars += source.totalUnderwriteDollars;
}

function ensureQuestionStats(map: Map<string, QuestionStats>, key: string): QuestionStats {
  let stats = map.get(key);
  if (!stats) {
    stats = emptyQuestionStats();
    map.set(key, stats);
  }
  return stats;
}

function questionMetricValue(stats: QuestionStats, metric: QuestionMetric): number {
  if (metric === "total_count") return stats.totalCount;
  if (metric === "yes_count") return stats.yesCount;
  if (metric === "no_count") return stats.noCount;
  if (metric === "no_percent") return percent(stats.noCount, stats.totalCount);
  if (metric === "driver_count") return stats.driverCount;
  if (metric === "overwrite_total") return stats.totalOverwriteDollars;
  if (metric === "underwrite_total") return stats.totalUnderwriteDollars;
  return stats.totalOverwriteDollars - stats.totalUnderwriteDollars;
}

function topQuestionSegments(entries: LabelledStats<QuestionStats>[], metric: QuestionMetric): string[] {
  const totals = new Map<string, QuestionStats>();
  for (const entry of entries) {
    for (const [segment, stats] of entry.segments) {
      mergeQuestionStats(ensureQuestionStats(totals, segment), stats);
    }
  }
  return Array.from(totals.entries())
    .sort(([firstKey, first], [secondKey, second]) => {
      const valueCompare = questionMetricValue(second, metric) - questionMetricValue(first, metric);
      return valueCompare || firstKey.localeCompare(secondKey, undefined, { numeric: true });
    })
    .slice(0, maxSegmentCount)
    .map(([segment]) => segment);
}

function truncateText(value: string, maxLength: number): string {
  return value.length <= maxLength ? value : `${value.slice(0, maxLength - 3)}...`;
}

function compactFormKey(formKey: string): string {
  const [formId, version] = formKey.split("@");
  const compactId =
    formId
      .split(/[\s_-]+/)
      .filter(Boolean)
      .map((part) => part[0])
      .join("")
      .slice(0, 6) || truncateText(formId, 8);
  return version ? `${compactId}@${version}` : compactId;
}

function buildQuestionEntries(
  rows: DashboardReviewRow[],
  segmentBy: DashboardDimension,
): LabelledStats<QuestionStats>[] {
  const entries = new Map<string, LabelledStats<QuestionStats>>();

  for (const row of rows) {
    const segmentLabel = segmentBy === "none" ? "Total" : dimensionValue(row, segmentBy);
    for (const question of row.form.questions ?? []) {
      const key = `${row.formKey || row.formId}:${question.id}`;
      const context = `${compactFormKey(row.formKey || row.formId)} ${question.id}`;
      let entry = entries.get(key);
      if (!entry) {
        entry = {
          key,
          context,
          text: question.text,
          fullLabel: `${row.formKey || row.formId} ${question.id}: ${question.text}`,
          total: emptyQuestionStats(),
          segments: new Map(),
        };
        entries.set(key, entry);
      }
      addQuestionToStats(entry.total, question);
      addQuestionToStats(ensureQuestionStats(entry.segments, segmentLabel), question);
    }
  }

  return Array.from(entries.values());
}

function buildHorizontalBarFigure<TStats>({
  entries,
  segments,
  metricLabel,
  format,
  valueFor,
  emptyMessage,
}: {
  entries: LabelledStats<TStats>[];
  segments: string[];
  metricLabel: string;
  format: MetricFormat;
  valueFor: (stats: TStats) => number;
  emptyMessage: string;
}): DashboardFigure {
  const labels = entries.map((entry) => `${entry.context}: ${truncateText(entry.text, 50)}`);
  const customdata = entries.map((entry) => [entry.fullLabel]);
  const data =
    segments.length === 1 && segments[0] === "Total"
      ? [
          {
            type: "bar",
            orientation: "h",
            name: metricLabel,
            x: entries.map((entry) => valueFor(entry.total)),
            y: labels,
            customdata,
            marker: { color: buildViridisColorway(Math.max(entries.length, 1)).slice(0, entries.length) },
            hovertemplate: `<b>%{customdata[0]}</b><br>${metricLabel}: ${metricToken("x", format)}<extra></extra>`,
          },
        ]
      : segments.map((segment) => ({
          type: "bar",
          orientation: "h",
          name: segment,
          x: entries.map((entry) => valueFor(entry.segments.get(segment) ?? entry.total)),
          y: labels,
          customdata,
          hovertemplate: `<b>%{customdata[0]}</b><br>${metricLabel}: ${metricToken("x", format)}<extra>${segment}</extra>`,
        }));

  return {
    data: entries.length ? data : [],
    emptyMessage,
    layout: baseLayout({
      barmode: "group",
      margin: { l: 270, r: 28, t: 18, b: 56 },
      xaxis: valueAxisLayout(format, metricLabel),
      yaxis: {
        type: "category",
        automargin: true,
        categoryorder: "array",
        categoryarray: labels,
        autorange: "reversed",
        tickfont: { size: 11 },
      },
    }),
  };
}

function buildQuestionFigure(
  rows: DashboardReviewRow[],
  metric: QuestionMetric,
  segmentBy: DashboardDimension,
  topLimit: number,
): DashboardFigure {
  const entries = buildQuestionEntries(rows, segmentBy)
    .sort((first, second) => {
      const valueCompare = questionMetricValue(second.total, metric) - questionMetricValue(first.total, metric);
      return valueCompare || first.context.localeCompare(second.context, undefined, { numeric: true });
    })
    .slice(0, topLimit);
  const segments = segmentBy === "none" ? ["Total"] : topQuestionSegments(entries, metric);

  return buildHorizontalBarFigure({
    entries,
    segments,
    metricLabel: questionMetricLabels[metric],
    format: questionMetricFormats[metric],
    valueFor: (stats) => questionMetricValue(stats, metric),
    emptyMessage: "No question data for the current filters.",
  });
}

function emptyDriverStats(): DriverStats {
  return {
    driverCount: 0,
    totalAppearances: 0,
    questionNoCount: 0,
  };
}

function addDriverToStats(
  stats: DriverStats,
  question: DashboardReviewRow["form"]["questions"][number],
  subQuestion: NonNullable<DashboardReviewRow["form"]["questions"][number]["sub_questions"]>[number],
): void {
  stats.totalAppearances += 1;
  stats.questionNoCount += question.answer === "No" ? 1 : 0;
  stats.driverCount += subQuestion.answer ? 1 : 0;
}

function mergeDriverStats(target: DriverStats, source: DriverStats): void {
  target.driverCount += source.driverCount;
  target.totalAppearances += source.totalAppearances;
  target.questionNoCount += source.questionNoCount;
}

function ensureDriverStats(map: Map<string, DriverStats>, key: string): DriverStats {
  let stats = map.get(key);
  if (!stats) {
    stats = emptyDriverStats();
    map.set(key, stats);
  }
  return stats;
}

function driverMetricValue(stats: DriverStats, metric: DriverMetric): number {
  if (metric === "driver_count") return stats.driverCount;
  if (metric === "driver_percent") return percent(stats.driverCount, stats.questionNoCount || stats.totalAppearances);
  return stats.totalAppearances;
}

function topDriverSegments(entries: LabelledStats<DriverStats>[], metric: DriverMetric): string[] {
  const totals = new Map<string, DriverStats>();
  for (const entry of entries) {
    for (const [segment, stats] of entry.segments) {
      mergeDriverStats(ensureDriverStats(totals, segment), stats);
    }
  }
  return Array.from(totals.entries())
    .sort(([firstKey, first], [secondKey, second]) => {
      const valueCompare = driverMetricValue(second, metric) - driverMetricValue(first, metric);
      return valueCompare || firstKey.localeCompare(secondKey, undefined, { numeric: true });
    })
    .slice(0, maxSegmentCount)
    .map(([segment]) => segment);
}

function buildDriverEntries(
  rows: DashboardReviewRow[],
  segmentBy: DashboardDimension,
): LabelledStats<DriverStats>[] {
  const entries = new Map<string, LabelledStats<DriverStats>>();

  for (const row of rows) {
    const segmentLabel = segmentBy === "none" ? "Total" : dimensionValue(row, segmentBy);
    for (const question of row.form.questions ?? []) {
      for (const subQuestion of question.sub_questions ?? []) {
        const key = `${row.formKey || row.formId}:${question.id}:${subQuestion.id}:${subQuestion.text}`;
        const context = `${compactFormKey(row.formKey || row.formId)} ${subQuestion.id}`;
        let entry = entries.get(key);
        if (!entry) {
          entry = {
            key,
            context,
            text: subQuestion.text,
            fullLabel: `${row.formKey || row.formId} ${question.id} > ${subQuestion.id}: ${subQuestion.text}`,
            total: emptyDriverStats(),
            segments: new Map(),
          };
          entries.set(key, entry);
        }
        addDriverToStats(entry.total, question, subQuestion);
        addDriverToStats(ensureDriverStats(entry.segments, segmentLabel), question, subQuestion);
      }
    }
  }

  return Array.from(entries.values());
}

function buildDriverFigure(
  rows: DashboardReviewRow[],
  metric: DriverMetric,
  segmentBy: DashboardDimension,
  topLimit: number,
): DashboardFigure {
  const entries = buildDriverEntries(rows, segmentBy)
    .filter((entry) => driverMetricValue(entry.total, metric) > 0)
    .sort((first, second) => {
      const valueCompare = driverMetricValue(second.total, metric) - driverMetricValue(first.total, metric);
      return valueCompare || first.context.localeCompare(second.context, undefined, { numeric: true });
    })
    .slice(0, topLimit);
  const segments = segmentBy === "none" ? ["Total"] : topDriverSegments(entries, metric);

  return buildHorizontalBarFigure({
    entries,
    segments,
    metricLabel: driverMetricLabels[metric],
    format: driverMetricFormats[metric],
    valueFor: (stats) => driverMetricValue(stats, metric),
    emptyMessage: "No driver data for the current filters.",
  });
}

function usesResultVersionRows(...dimensions: DashboardDimension[]): boolean {
  return dimensions.some((dimension) => dimension === "result_version");
}

function ChartSelect({
  label,
  value,
  onChange,
  children,
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("min-w-[140px] space-y-1", className)}>
      <span className="block text-[11px] font-semibold uppercase text-muted-foreground">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {children}
      </select>
    </label>
  );
}

function StyleToggle({ mode, onChange }: { mode: ChartMode; onChange: (mode: ChartMode) => void }) {
  return (
    <label className="space-y-1">
      <span className="block text-[11px] font-semibold uppercase text-muted-foreground">Style</span>
      <div className="inline-flex rounded-md border bg-background p-0.5">
        <button
          type="button"
          onClick={() => onChange("line")}
          className={cn(
            "inline-flex h-7 items-center gap-1 rounded px-2 text-xs",
            mode === "line" ? "bg-secondary text-foreground" : "text-muted-foreground",
          )}
        >
          <LineChart className="h-3.5 w-3.5" />
          Line
        </button>
        <button
          type="button"
          onClick={() => onChange("bar")}
          className={cn(
            "inline-flex h-7 items-center gap-1 rounded px-2 text-xs",
            mode === "bar" ? "bg-secondary text-foreground" : "text-muted-foreground",
          )}
        >
          <BarChart3 className="h-3.5 w-3.5" />
          Bar
        </button>
      </div>
    </label>
  );
}

function TopLimitSelect({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return (
    <ChartSelect label="Top" value={String(value)} onChange={(nextValue) => onChange(Number(nextValue))} className="min-w-[92px]">
      {topLimitOptions.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </ChartSelect>
  );
}

function SegmentOptions({ disabledValue }: { disabledValue?: DashboardDimension }) {
  return (
    <>
      {dimensionOptions.map((dimension) => (
        <option key={dimension} value={dimension} disabled={dimension !== "none" && dimension === disabledValue}>
          {dimensionLabels[dimension]}
        </option>
      ))}
    </>
  );
}

function DashboardPlot({ figure }: { figure: DashboardFigure }) {
  if (figure.data.length === 0) {
    return (
      <div className="flex min-h-[440px] items-center justify-center rounded-md border border-dashed px-4 text-center text-sm text-muted-foreground">
        {figure.emptyMessage}
      </div>
    );
  }

  return (
    <PlotlyChart
      data={figure.data}
      layout={figure.layout}
      config={{ toImageButtonOptions: { filename: "tfr-dashboard-plot" } }}
      collapsible={false}
      showHeader={false}
      surfaceClassName="h-[560px] min-h-[440px]"
    />
  );
}

function MetricCard({
  label,
  value,
  helper,
  icon: Icon,
  color,
}: {
  label: string;
  value: string;
  helper: string;
  icon: typeof BarChart3;
  color: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <div
          className="flex h-10 w-10 items-center justify-center rounded-md border"
          style={{
            borderColor: hexToRgba(color, 0.34),
            backgroundColor: hexToRgba(color, 0.12),
            color,
          }}
        >
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{helper}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export function DashboardCharts({
  rows,
  versionComparisonRows,
}: {
  rows: DashboardReviewRow[];
  versionComparisonRows: DashboardReviewRow[];
}) {
  const [plotView, setPlotView] = useState<PlotView>("trend");
  const [granularity, setGranularity] = useState<TrendGranularity>("day");
  const [trendMetric, setTrendMetric] = useState<TrendMetric>("does_not_meet_rate");
  const [trendCompareBy, setTrendCompareBy] = useState<TrendCompareBy>("form_id");
  const [mode, setMode] = useState<ChartMode>("bar");
  const [aggregateMetric, setAggregateMetric] = useState<AggregateMetric>("review_volume");
  const [aggregateDimension, setAggregateDimension] = useState<DashboardDimension>("source");
  const [aggregateSegmentBy, setAggregateSegmentBy] = useState<DashboardDimension>("outcome");
  const [questionMetric, setQuestionMetric] = useState<QuestionMetric>("no_count");
  const [questionSegmentBy, setQuestionSegmentBy] = useState<DashboardDimension>("source");
  const [driverMetric, setDriverMetric] = useState<DriverMetric>("driver_count");
  const [driverSegmentBy, setDriverSegmentBy] = useState<DashboardDimension>("source");
  const [topLimit, setTopLimit] = useState<number>(12);
  const [settingsLoaded, setSettingsLoaded] = useState(false);

  useEffect(() => {
    const saved = loadChartSettings();
    if (saved?.plotView) setPlotView(saved.plotView);
    if (saved?.granularity) setGranularity(saved.granularity);
    if (saved?.trendMetric ?? saved?.metric) setTrendMetric((saved.trendMetric ?? saved.metric) as TrendMetric);
    if (saved?.trendCompareBy ?? saved?.compareBy) {
      setTrendCompareBy((saved.trendCompareBy ?? saved.compareBy) as TrendCompareBy);
    }
    if (saved?.mode) setMode(saved.mode);
    if (saved?.aggregateMetric) setAggregateMetric(saved.aggregateMetric);
    if (saved?.aggregateDimension) setAggregateDimension(saved.aggregateDimension);
    if (saved?.aggregateSegmentBy) setAggregateSegmentBy(saved.aggregateSegmentBy);
    if (saved?.questionMetric) setQuestionMetric(saved.questionMetric);
    if (saved?.questionSegmentBy) setQuestionSegmentBy(saved.questionSegmentBy);
    if (saved?.driverMetric) setDriverMetric(saved.driverMetric);
    if (saved?.driverSegmentBy) setDriverSegmentBy(saved.driverSegmentBy);
    if (saved?.topLimit && topLimitOptions.includes(saved.topLimit as (typeof topLimitOptions)[number])) {
      setTopLimit(saved.topLimit);
    }
    setSettingsLoaded(true);
  }, []);

  useEffect(() => {
    if (aggregateDimension === aggregateSegmentBy) setAggregateSegmentBy("none");
  }, [aggregateDimension, aggregateSegmentBy]);

  useEffect(() => {
    if (!settingsLoaded) return;
    saveChartSettings({
      plotView,
      granularity,
      metric: trendMetric,
      trendMetric,
      compareBy: trendCompareBy,
      trendCompareBy,
      mode,
      aggregateMetric,
      aggregateDimension,
      aggregateSegmentBy,
      questionMetric,
      questionSegmentBy,
      driverMetric,
      driverSegmentBy,
      topLimit,
    });
  }, [
    aggregateDimension,
    aggregateMetric,
    aggregateSegmentBy,
    driverMetric,
    driverSegmentBy,
    granularity,
    mode,
    plotView,
    questionMetric,
    questionSegmentBy,
    settingsLoaded,
    topLimit,
    trendCompareBy,
    trendMetric,
  ]);

  const totalReviews = rows.length;
  const doesNotMeetCount = rows.filter((row) => row.outcome === "Does Not Meet").length;
  const editedCount = rows.filter((row) => row.edited).length;
  const totalQuestions = rows.reduce((sum, row) => sum + row.questionCount, 0);
  const totalNoQuestions = rows.reduce((sum, row) => sum + row.noCount, 0);

  const trendRows = trendCompareBy === "result_version" ? versionComparisonRows : rows;
  const aggregateRows = usesResultVersionRows(aggregateDimension, aggregateSegmentBy) ? versionComparisonRows : rows;
  const questionRows = usesResultVersionRows(questionSegmentBy) ? versionComparisonRows : rows;
  const driverRows = usesResultVersionRows(driverSegmentBy) ? versionComparisonRows : rows;
  const figure = useMemo(() => {
    if (plotView === "aggregate") {
      return buildAggregateFigure(aggregateRows, aggregateMetric, aggregateDimension, aggregateSegmentBy, topLimit);
    }
    if (plotView === "questions") {
      return buildQuestionFigure(questionRows, questionMetric, questionSegmentBy, topLimit);
    }
    if (plotView === "drivers") {
      return buildDriverFigure(driverRows, driverMetric, driverSegmentBy, topLimit);
    }
    return buildTrendFigure(trendRows, granularity, trendMetric, trendCompareBy, mode);
  }, [
    aggregateDimension,
    aggregateMetric,
    aggregateRows,
    aggregateSegmentBy,
    driverMetric,
    driverRows,
    driverSegmentBy,
    granularity,
    mode,
    plotView,
    questionMetric,
    questionRows,
    questionSegmentBy,
    topLimit,
    trendCompareBy,
    trendMetric,
    trendRows,
  ]);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Completed reviews"
          value={String(totalReviews)}
          helper="After current filters"
          icon={BarChart3}
          color={metricCardColors[0]}
        />
        <MetricCard
          label="Does Not Meet"
          value={`${percent(doesNotMeetCount, totalReviews)}%`}
          helper={`${doesNotMeetCount} of ${totalReviews} reviews`}
          icon={Gauge}
          color={metricCardColors[1]}
        />
        <MetricCard
          label="Question No rate"
          value={`${percent(totalNoQuestions, totalQuestions)}%`}
          helper={`${totalNoQuestions} No answers across ${totalQuestions} questions`}
          icon={Activity}
          color={metricCardColors[2]}
        />
        <MetricCard
          label="Edited reviews"
          value={`${percent(editedCount, totalReviews)}%`}
          helper={`${editedCount} current versions differ from original`}
          icon={Pencil}
          color={metricCardColors[3]}
        />
      </div>

      <Card className="overflow-hidden">
        <CardHeader className="border-b">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
            <div className="flex min-w-0 items-center gap-2">
              {plotView === "trend" ? (
                <TrendingUp className="h-4 w-4 shrink-0 text-primary" />
              ) : (
                <SlidersHorizontal className="h-4 w-4 shrink-0 text-primary" />
              )}
              <CardTitle>Visualization Explorer</CardTitle>
            </div>
            <div className="grid w-full gap-2 sm:grid-cols-2 md:grid-cols-3 xl:w-auto xl:grid-cols-none xl:flex xl:flex-wrap xl:justify-end">
              <ChartSelect label="View" value={plotView} onChange={(value) => setPlotView(value as PlotView)}>
                {Object.entries(plotViewLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </ChartSelect>

              {plotView === "trend" ? (
                <>
                  <ChartSelect label="Metric" value={trendMetric} onChange={(value) => setTrendMetric(value as TrendMetric)} className="min-w-[168px]">
                    {Object.entries(trendMetricLabels).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </ChartSelect>
                  <ChartSelect label="Time" value={granularity} onChange={(value) => setGranularity(value as TrendGranularity)} className="min-w-[116px]">
                    <option value="day">Daily</option>
                    <option value="week">Weekly</option>
                    <option value="month">Monthly</option>
                  </ChartSelect>
                  <ChartSelect label="Split" value={trendCompareBy} onChange={(value) => setTrendCompareBy(value as TrendCompareBy)} className="min-w-[164px]">
                    {Object.entries(trendCompareLabels).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </ChartSelect>
                  <StyleToggle mode={mode} onChange={setMode} />
                </>
              ) : null}

              {plotView === "aggregate" ? (
                <>
                  <ChartSelect label="Metric" value={aggregateMetric} onChange={(value) => setAggregateMetric(value as AggregateMetric)} className="min-w-[170px]">
                    {Object.entries(aggregateMetricLabels).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </ChartSelect>
                  <ChartSelect label="Axis" value={aggregateDimension} onChange={(value) => setAggregateDimension(value as DashboardDimension)} className="min-w-[150px]">
                    <SegmentOptions />
                  </ChartSelect>
                  <ChartSelect label="Bars" value={aggregateSegmentBy} onChange={(value) => setAggregateSegmentBy(value as DashboardDimension)} className="min-w-[150px]">
                    <SegmentOptions disabledValue={aggregateDimension} />
                  </ChartSelect>
                  <TopLimitSelect value={topLimit} onChange={setTopLimit} />
                </>
              ) : null}

              {plotView === "questions" ? (
                <>
                  <ChartSelect label="Metric" value={questionMetric} onChange={(value) => setQuestionMetric(value as QuestionMetric)} className="min-w-[170px]">
                    {Object.entries(questionMetricLabels).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </ChartSelect>
                  <ChartSelect label="Bars" value={questionSegmentBy} onChange={(value) => setQuestionSegmentBy(value as DashboardDimension)} className="min-w-[150px]">
                    <SegmentOptions />
                  </ChartSelect>
                  <TopLimitSelect value={topLimit} onChange={setTopLimit} />
                </>
              ) : null}

              {plotView === "drivers" ? (
                <>
                  <ChartSelect label="Metric" value={driverMetric} onChange={(value) => setDriverMetric(value as DriverMetric)} className="min-w-[170px]">
                    {Object.entries(driverMetricLabels).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </ChartSelect>
                  <ChartSelect label="Bars" value={driverSegmentBy} onChange={(value) => setDriverSegmentBy(value as DashboardDimension)} className="min-w-[150px]">
                    <SegmentOptions />
                  </ChartSelect>
                  <TopLimitSelect value={topLimit} onChange={setTopLimit} />
                </>
              ) : null}
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-4">
          <DashboardPlot figure={figure} />
        </CardContent>
      </Card>
    </div>
  );
}
