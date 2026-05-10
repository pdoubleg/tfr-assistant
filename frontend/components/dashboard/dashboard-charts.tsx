"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, BarChart3, Gauge, LineChart, Pencil, TrendingUp } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  aggregateQuestions,
  percent,
  trendCompareLabels,
  trendMetricLabels,
  type AggregatedQuestionRow,
  type AggregatedSubQuestionRow,
  type DashboardReviewRow,
  type TrendCompareBy,
  type TrendGranularity,
  type TrendMetric,
} from "@/lib/dashboard-data";
import { cn } from "@/lib/utils";

type ChartMode = "line" | "bar";
type SignalMode = "count" | "percent";

const chartSettingsKey = "tfr-dashboard-chart-settings";

interface PersistedChartSettings {
  granularity?: TrendGranularity;
  metric?: TrendMetric;
  compareBy?: TrendCompareBy;
  mode?: ChartMode;
  signalMode?: SignalMode;
}

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

interface TrendPoint {
  bucket: string;
  label: string;
  value: number;
  totalReviews: number;
  meetsCount: number;
  doesNotMeetCount: number;
  totalQuestions: number;
  noQuestions: number;
  driverReviews: number;
}

interface TrendSeries {
  key: string;
  label: string;
  color: string;
  points: TrendPoint[];
}

const seriesColors = ["#0891b2", "#db2777", "#16a34a", "#d97706", "#7c3aed", "#475569"];

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

function compareLabel(row: DashboardReviewRow, compareBy: TrendCompareBy): string {
  if (compareBy === "form_id") return row.formId || "Unknown form";
  if (compareBy === "form_version") return row.formKey || "Unknown version";
  if (compareBy === "source") return row.source || "Unknown source";
  if (compareBy === "result_version") return row.resultVersion === "original" ? "Original agent" : "Current user";
  return "All reviews";
}

function emptyPoint(bucket: string, label: string): TrendPoint {
  return {
    bucket,
    label,
    value: 0,
    totalReviews: 0,
    meetsCount: 0,
    doesNotMeetCount: 0,
    totalQuestions: 0,
    noQuestions: 0,
    driverReviews: 0,
  };
}

function metricValue(point: TrendPoint, metric: TrendMetric): number {
  if (metric === "review_volume") return point.totalReviews;
  if (metric === "meets_rate") return percent(point.meetsCount, point.totalReviews);
  if (metric === "does_not_meet_rate") return percent(point.doesNotMeetCount, point.totalReviews);
  if (metric === "question_no_rate") return percent(point.noQuestions, point.totalQuestions);
  return percent(point.driverReviews, point.totalReviews);
}

function trendTooltip(seriesLabel: string, point: TrendPoint): string {
  return [
    `${seriesLabel} - ${point.label}`,
    `Review volume: ${point.totalReviews}`,
    `Meets: ${point.meetsCount} (${percent(point.meetsCount, point.totalReviews)}%)`,
    `Does Not Meet: ${point.doesNotMeetCount} (${percent(point.doesNotMeetCount, point.totalReviews)}%)`,
    `Question No: ${point.noQuestions} of ${point.totalQuestions} (${percent(point.noQuestions, point.totalQuestions)}%)`,
    `Reviews with drivers: ${point.driverReviews} (${percent(point.driverReviews, point.totalReviews)}%)`,
  ].join("\n");
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
    const key = compareLabel(row, compareBy);
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
    point.totalReviews += 1;
    point.meetsCount += row.outcome === "Meets" ? 1 : 0;
    point.doesNotMeetCount += row.outcome === "Does Not Meet" ? 1 : 0;
    point.totalQuestions += row.questionCount;
    point.noQuestions += row.noCount;
    point.driverReviews += row.driverCount > 0 ? 1 : 0;
  }

  const sortedBuckets = Array.from(allBuckets.entries()).sort(([first], [second]) => first.localeCompare(second));
  const sortedSeries = Array.from(seriesMap.entries())
    .sort(([firstKey], [secondKey]) => (totalsBySeries.get(secondKey) ?? 0) - (totalsBySeries.get(firstKey) ?? 0))
    .slice(0, 6);

  return sortedSeries.map(([key, pointMap], index) => ({
    key,
    label: key,
    color: seriesColors[index % seriesColors.length],
    points: sortedBuckets.map(([bucketKey, label]) => {
      const point = pointMap.get(bucketKey) ?? emptyPoint(bucketKey, label);
      return {
        ...point,
        label,
        value: metricValue(point, metric),
      };
    }),
  }));
}

function TrendChart({
  series,
  metric,
  mode,
}: {
  series: TrendSeries[];
  metric: TrendMetric;
  mode: ChartMode;
}) {
  const width = 920;
  const height = 420;
  const padding = { top: 24, right: 24, bottom: 46, left: 48 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const bucketCount = series[0]?.points.length ?? 0;
  const maxValue =
    metric === "review_volume"
      ? Math.max(1, ...series.flatMap((item) => item.points.map((point) => point.value)))
      : 100;
  const y = (value: number) => padding.top + plotHeight - (value / maxValue) * plotHeight;
  const x = (index: number) =>
    bucketCount <= 1 ? padding.left + plotWidth / 2 : padding.left + (index / (bucketCount - 1)) * plotWidth;

  if (series.length === 0 || bucketCount === 0) {
    return (
      <div className="flex min-h-[420px] flex-1 items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground">
        No trend data for the current filters.
      </div>
    );
  }

  const tickLabels = series[0].points.filter((_, index) => {
    if (bucketCount <= 6) return true;
    const stride = Math.ceil(bucketCount / 6);
    return index % stride === 0 || index === bucketCount - 1;
  });

  return (
    <div className="min-h-[420px] flex-1 overflow-x-auto">
      <svg className="h-full min-h-[420px] w-full min-w-[720px]" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Review trend chart">
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const value = maxValue * ratio;
          return (
            <g key={ratio}>
              <line
                x1={padding.left}
                x2={width - padding.right}
                y1={y(value)}
                y2={y(value)}
                stroke="currentColor"
                className="text-border"
                strokeDasharray="4 4"
              />
              <text x={padding.left - 8} y={y(value) + 4} textAnchor="end" className="fill-muted-foreground text-[11px]">
                {Math.round(value)}
                {metric === "review_volume" ? "" : "%"}
              </text>
            </g>
          );
        })}

        {mode === "line"
          ? series.map((item) => (
              <g key={item.key}>
                <polyline
                  points={item.points.map((point, index) => `${x(index)},${y(point.value)}`).join(" ")}
                  fill="none"
                  stroke={item.color}
                  strokeWidth="3"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                {item.points.map((point, index) => (
                  <circle key={`${item.key}-${point.bucket}`} cx={x(index)} cy={y(point.value)} r="3.5" fill={item.color}>
                    <title>{trendTooltip(item.label, point)}</title>
                  </circle>
                ))}
              </g>
            ))
          : series.map((item, seriesIndex) => {
              const groupWidth = plotWidth / Math.max(1, bucketCount);
              const barWidth = Math.max(4, Math.min(18, (groupWidth / Math.max(1, series.length)) * 0.68));
              return (
                <g key={item.key}>
                  {item.points.map((point, index) => {
                    const groupStart = padding.left + index * groupWidth + groupWidth / 2;
                    const xOffset = (seriesIndex - (series.length - 1) / 2) * (barWidth + 2);
                    const barHeight = plotHeight - (y(point.value) - padding.top);
                    return (
                      <rect
                        key={`${item.key}-${point.bucket}`}
                        x={groupStart + xOffset - barWidth / 2}
                        y={y(point.value)}
                        width={barWidth}
                        height={Math.max(1, barHeight)}
                        rx="2"
                        fill={item.color}
                      >
                        <title>{trendTooltip(item.label, point)}</title>
                      </rect>
                    );
                  })}
                </g>
              );
            })}

        {tickLabels.map((point) => {
          const index = series[0].points.findIndex((candidate) => candidate.bucket === point.bucket);
          return (
            <text key={point.bucket} x={x(index)} y={height - 16} textAnchor="middle" className="fill-muted-foreground text-[11px]">
              {point.label}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

function MetricCard({
  label,
  value,
  helper,
  icon: Icon,
  tone,
}: {
  label: string;
  value: string;
  helper: string;
  icon: typeof BarChart3;
  tone: keyof typeof toneClasses;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <div className={cn("flex h-10 w-10 items-center justify-center rounded-md border", toneClasses[tone])}>
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

interface DriverSignalItem {
  key: string;
  context: string;
  label: string;
  count: number;
  denominator: number;
  percentValue: number;
}

function topQuestionSignals(questions: AggregatedQuestionRow[], mode: SignalMode): DriverSignalItem[] {
  return questions
    .map((question) => ({
      key: question.key,
      context: `${question.formKey} ${question.id}`,
      label: question.text,
      count: question.noCount,
      denominator: question.totalCount,
      percentValue: question.noPercent,
    }))
    .filter((item) => item.count > 0)
    .sort((first, second) =>
      mode === "count"
        ? second.count - first.count || second.percentValue - first.percentValue
        : second.percentValue - first.percentValue || second.count - first.count,
    )
    .slice(0, 3);
}

function topSubQuestionSignals(questions: AggregatedQuestionRow[], mode: SignalMode): DriverSignalItem[] {
  return questions
    .flatMap((question) =>
      question.subQuestions.map((subQuestion: AggregatedSubQuestionRow) => ({
        key: subQuestion.key,
        context: `${question.formKey} ${subQuestion.id}`,
        label: subQuestion.text,
        count: subQuestion.driverCount,
        denominator: subQuestion.questionNoCount,
        percentValue: percent(subQuestion.driverCount, subQuestion.questionNoCount),
      })),
    )
    .filter((item) => item.count > 0)
    .sort((first, second) =>
      mode === "count"
        ? second.count - first.count || second.percentValue - first.percentValue
        : second.percentValue - first.percentValue || second.count - first.count,
    )
    .slice(0, 3);
}

function SignalList({
  title,
  items,
  mode,
}: {
  title: string;
  items: DriverSignalItem[];
  mode: SignalMode;
}) {
  const maxCount = Math.max(1, ...items.map((item) => item.count));

  return (
    <div>
      <p className="text-sm font-semibold text-foreground">{title}</p>
      <div className="mt-2 space-y-2">
        {items.length === 0 ? (
          <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">No driver signal in this slice.</p>
        ) : (
          items.map((item) => {
            const value = mode === "count" ? item.count : item.percentValue;
            const barWidth = mode === "count" ? percent(item.count, maxCount) : item.percentValue;
            return (
              <div key={item.key} title={`${item.context}: ${item.label}`} className="space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium leading-snug">{item.label}</p>
                    <p className="truncate text-[11px] text-muted-foreground">{item.context}</p>
                  </div>
                  <span className="shrink-0 text-xs font-semibold tabular-nums">
                    {mode === "count" ? value : `${value}%`}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-secondary">
                  <div className="h-full rounded-full bg-amber-500" style={{ width: `${barWidth}%` }} />
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {mode === "count" ? `${item.count} of ${item.denominator}` : `${item.count} flagged of ${item.denominator}`}
                </p>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export function DashboardCharts({
  rows,
  versionComparisonRows,
}: {
  rows: DashboardReviewRow[];
  versionComparisonRows: DashboardReviewRow[];
}) {
  const [granularity, setGranularity] = useState<TrendGranularity>("day");
  const [metric, setMetric] = useState<TrendMetric>("does_not_meet_rate");
  const [compareBy, setCompareBy] = useState<TrendCompareBy>("form_id");
  const [mode, setMode] = useState<ChartMode>("bar");
  const [signalMode, setSignalMode] = useState<SignalMode>("count");
  const [settingsLoaded, setSettingsLoaded] = useState(false);

  useEffect(() => {
    const saved = loadChartSettings();
    if (saved?.granularity) setGranularity(saved.granularity);
    if (saved?.metric) setMetric(saved.metric);
    if (saved?.compareBy) setCompareBy(saved.compareBy);
    if (saved?.mode) setMode(saved.mode);
    if (saved?.signalMode) setSignalMode(saved.signalMode);
    setSettingsLoaded(true);
  }, []);

  useEffect(() => {
    if (!settingsLoaded) return;
    saveChartSettings({ granularity, metric, compareBy, mode, signalMode });
  }, [compareBy, granularity, metric, mode, settingsLoaded, signalMode]);

  const totalReviews = rows.length;
  const doesNotMeetCount = rows.filter((row) => row.outcome === "Does Not Meet").length;
  const editedCount = rows.filter((row) => row.edited).length;
  const totalQuestions = rows.reduce((sum, row) => sum + row.questionCount, 0);
  const totalNoQuestions = rows.reduce((sum, row) => sum + row.noCount, 0);

  const trendRows = compareBy === "result_version" ? versionComparisonRows : rows;
  const trendSeries = useMemo(
    () => buildTrendSeries(trendRows, granularity, metric, compareBy),
    [compareBy, granularity, metric, trendRows],
  );
  const aggregatedQuestions = useMemo(() => aggregateQuestions(rows), [rows]);
  const questionSignals = useMemo(
    () => topQuestionSignals(aggregatedQuestions, signalMode),
    [aggregatedQuestions, signalMode],
  );
  const subQuestionSignals = useMemo(
    () => topSubQuestionSignals(aggregatedQuestions, signalMode),
    [aggregatedQuestions, signalMode],
  );

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Completed reviews"
          value={String(totalReviews)}
          helper="After current filters"
          icon={BarChart3}
          tone="cyan"
        />
        <MetricCard
          label="Does Not Meet"
          value={`${percent(doesNotMeetCount, totalReviews)}%`}
          helper={`${doesNotMeetCount} of ${totalReviews} reviews`}
          icon={Gauge}
          tone="rose"
        />
        <MetricCard
          label="Question No rate"
          value={`${percent(totalNoQuestions, totalQuestions)}%`}
          helper={`${totalNoQuestions} No answers across ${totalQuestions} questions`}
          icon={Activity}
          tone="amber"
        />
        <MetricCard
          label="Edited reviews"
          value={`${percent(editedCount, totalReviews)}%`}
          helper={`${editedCount} current versions differ from original`}
          icon={Pencil}
          tone="violet"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-4">
        <Card className="flex h-full flex-col overflow-hidden xl:col-span-3">
          <CardHeader className="border-b">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <TrendingUp className="h-4 w-4 text-primary" />
                <CardTitle>Trend Explorer</CardTitle>
              </div>
              <div className="ml-auto flex flex-wrap items-center gap-2">
                <select
                  value={metric}
                  onChange={(event) => setMetric(event.target.value as TrendMetric)}
                  className="h-8 rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {Object.entries(trendMetricLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <select
                  value={granularity}
                  onChange={(event) => setGranularity(event.target.value as TrendGranularity)}
                  className="h-8 rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="day">Daily</option>
                  <option value="week">Weekly</option>
                  <option value="month">Monthly</option>
                </select>
                <select
                  value={compareBy}
                  onChange={(event) => setCompareBy(event.target.value as TrendCompareBy)}
                  className="h-8 rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {Object.entries(trendCompareLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <div className="inline-flex rounded-md border bg-background p-0.5">
                  <button
                    type="button"
                    onClick={() => setMode("line")}
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
                    onClick={() => setMode("bar")}
                    className={cn(
                      "inline-flex h-7 items-center gap-1 rounded px-2 text-xs",
                      mode === "bar" ? "bg-secondary text-foreground" : "text-muted-foreground",
                    )}
                  >
                    <BarChart3 className="h-3.5 w-3.5" />
                    Bar
                  </button>
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col p-4">
            <TrendChart series={trendSeries} metric={metric} mode={mode} />
            <div className="mt-3 flex flex-wrap gap-3">
              {trendSeries.map((item) => (
                <div key={item.key} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                  {item.label}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="h-full xl:col-span-1">
          <CardHeader className="border-b">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              <CardTitle>Driver Signal</CardTitle>
              <button
                type="button"
                onClick={() => setSignalMode((current) => (current === "count" ? "percent" : "count"))}
                className="ml-auto inline-flex h-7 items-center rounded-md border bg-background px-2 text-xs font-medium hover:bg-secondary"
                title="Toggle count or percentage ranking"
              >
                {signalMode === "count" ? "Count" : "%"}
              </button>
            </div>
          </CardHeader>
          <CardContent className="space-y-5 pt-5">
            <SignalList title="Top questions" items={questionSignals} mode={signalMode} />
            <SignalList title="Top sub-questions" items={subQuestionSignals} mode={signalMode} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

const toneClasses = {
  cyan: "border-cyan-500/30 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300",
  amber: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  rose: "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300",
  violet: "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300",
};
