"use client";

import { Fragment, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  ChevronDown,
  ChevronRight,
  Eye,
  FileText,
  FlaskConical,
  FolderArchive,
  Layers3,
  Loader2,
  Pause,
  Play,
  PlayCircle,
  Plus,
  RefreshCw,
  Search,
  Square,
  SquarePen,
  Trash2,
  X,
} from "lucide-react";

import { TablePagination } from "@/components/dashboard/table-pagination";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  cancelEvalRun,
  createEvalRun,
  listEvalDatasets,
  listEvalRunItems,
  listEvalRuns,
  pauseEvalRun,
  resumeEvalRun,
} from "@/lib/api";
import type {
  AuditFormResult,
  EvalComparisonRecord,
  EvalDatasetRecord,
  EvalGroundTruthRecord,
  EvalReferenceKind,
  EvalReferencePolicy,
  EvalRunItemRecord,
  EvalRunPayload,
  EvalRunRecord,
  EvalRunStatus,
  FormQuestion,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const pollMs = 3000;
const evalQueueStorageKey = "tfr.eval.executionQueue.v1";

type RunAction = "start" | "pause" | "resume" | "cancel";
type HierarchyLevel = "form" | "question" | "subquestion";
type MetricColumnKey =
  | "score"
  | "score_percent"
  | "outcome_match"
  | "outcome_score"
  | "question_total"
  | "question_matches"
  | "question_agreement"
  | "question_agreement_percent"
  | "question_no_precision"
  | "question_no_recall"
  | "question_no_f1"
  | "question_no_f1_percent"
  | "subquestion_eligible_question_count"
  | "subquestion_total"
  | "subquestion_matches"
  | "subquestion_agreement"
  | "subquestion_agreement_percent"
  | "subquestion_precision"
  | "subquestion_recall"
  | "subquestion_f1"
  | "subquestion_f1_percent"
  | "path_exact_matches"
  | "path_exact_rate"
  | "path_exact_percent"
  | "form_exact_match";
type MetricFormat = "count" | "number" | "percent" | "ratio";
type MetricAggregate = "mean" | "sum";
type VisualizationMode = "results" | "agreement";
type ReferenceView = EvalReferenceKind | "both";

interface EvalRunDialogState {
  dataset_id: string;
  name: string;
  model_name: string;
  reference_policy: EvalReferencePolicy;
  retry_limit: number;
  enable_mlflow: boolean;
}

interface HierarchyMetricRow {
  id: string;
  level: HierarchyLevel;
  referenceKind: EvalReferenceKind;
  path: string;
  parentPath: string;
  label: string;
  total: number;
  matches: number;
  agreement: number;
  averageScore: number | null;
  outcomeMatches: number;
  metrics: Partial<Record<MetricColumnKey, number>>;
}

interface PairResultRow {
  id: string;
  item: EvalRunItemRecord;
  comparison: EvalComparisonRecord;
  referenceKind: EvalReferenceKind;
  referenceTruth: EvalGroundTruthRecord;
  claimNumber: string;
  status: string;
  score: number | null;
  outcomeMatch: boolean;
  questionAgreement: number | null;
  subquestionF1: number | null;
  generatedOutcome: string;
  referenceOutcome: string;
}

interface MetricColumnDefinition {
  key: MetricColumnKey;
  label: string;
  format: MetricFormat;
  aggregate: MetricAggregate;
  levels: HierarchyLevel[];
}

interface DetectionStats {
  truePositive: number;
  falsePositive: number;
  falseNegative: number;
}

interface MatchStats {
  total: number;
  matches: number;
}

interface HierarchyMetricAccumulator extends HierarchyMetricRow {
  scoreSum: number;
  scoreCount: number;
  metricSums: Partial<Record<MetricColumnKey, number>>;
  metricCounts: Partial<Record<MetricColumnKey, number>>;
  questionStats: MatchStats;
  questionNoStats: DetectionStats;
  subquestionStats: MatchStats;
  subquestionStatsByParent: Map<string, MatchStats>;
  subquestionDetectionStats: DetectionStats;
  subquestionEligibleQuestionCount: number;
}

interface EvalVisualizationBar {
  key: string;
  label: string;
  value: number;
  displayValue: string;
  color: string;
  muted?: boolean;
}

interface EvalVisualizationRow {
  id: string;
  label: string;
  context: string;
  bars: EvalVisualizationBar[];
}

interface EvalVisualizationSection {
  id: "overall" | "question" | "subquestion";
  title: string;
  rows: EvalVisualizationRow[];
}

const metricColumnDefinitions: MetricColumnDefinition[] = [
  { key: "score", label: "Score", format: "ratio", aggregate: "mean", levels: ["form"] },
  { key: "score_percent", label: "Score %", format: "percent", aggregate: "mean", levels: ["form"] },
  { key: "outcome_match", label: "Outcome Match", format: "ratio", aggregate: "mean", levels: ["form"] },
  { key: "outcome_score", label: "Outcome Score", format: "ratio", aggregate: "mean", levels: ["form"] },
  { key: "question_total", label: "Question Total", format: "count", aggregate: "sum", levels: ["form", "question"] },
  { key: "question_matches", label: "Question Matches", format: "count", aggregate: "sum", levels: ["form", "question"] },
  { key: "question_agreement", label: "Question Agreement", format: "ratio", aggregate: "mean", levels: ["form", "question"] },
  {
    key: "question_agreement_percent",
    label: "Question Agreement %",
    format: "percent",
    aggregate: "mean",
    levels: ["form", "question"],
  },
  {
    key: "question_no_precision",
    label: "Question No Precision",
    format: "ratio",
    aggregate: "mean",
    levels: ["form", "question"],
  },
  {
    key: "question_no_recall",
    label: "Question No Recall",
    format: "ratio",
    aggregate: "mean",
    levels: ["form", "question"],
  },
  {
    key: "question_no_f1",
    label: "Question No F1",
    format: "ratio",
    aggregate: "mean",
    levels: ["form", "question"],
  },
  {
    key: "question_no_f1_percent",
    label: "Question No F1 %",
    format: "percent",
    aggregate: "mean",
    levels: ["form", "question"],
  },
  {
    key: "subquestion_eligible_question_count",
    label: "Sub-question Eligible Questions",
    format: "count",
    aggregate: "sum",
    levels: ["form", "question"],
  },
  {
    key: "subquestion_total",
    label: "Sub-question Total",
    format: "count",
    aggregate: "sum",
    levels: ["form", "question", "subquestion"],
  },
  {
    key: "subquestion_matches",
    label: "Sub-question Matches",
    format: "count",
    aggregate: "sum",
    levels: ["form", "question", "subquestion"],
  },
  {
    key: "subquestion_agreement",
    label: "Sub-question Agreement",
    format: "ratio",
    aggregate: "mean",
    levels: ["form", "question", "subquestion"],
  },
  {
    key: "subquestion_agreement_percent",
    label: "Sub-question Agreement %",
    format: "percent",
    aggregate: "mean",
    levels: ["form", "question", "subquestion"],
  },
  {
    key: "subquestion_precision",
    label: "Sub-question Precision",
    format: "ratio",
    aggregate: "mean",
    levels: ["form", "question", "subquestion"],
  },
  {
    key: "subquestion_recall",
    label: "Sub-question Recall",
    format: "ratio",
    aggregate: "mean",
    levels: ["form", "question", "subquestion"],
  },
  {
    key: "subquestion_f1",
    label: "Sub-question F1",
    format: "ratio",
    aggregate: "mean",
    levels: ["form", "question", "subquestion"],
  },
  {
    key: "subquestion_f1_percent",
    label: "Sub-question F1 %",
    format: "percent",
    aggregate: "mean",
    levels: ["form", "question", "subquestion"],
  },
  { key: "path_exact_matches", label: "Path Exact Matches", format: "count", aggregate: "sum", levels: ["form"] },
  { key: "path_exact_rate", label: "Path Exact Rate", format: "ratio", aggregate: "mean", levels: ["form"] },
  { key: "path_exact_percent", label: "Path Exact %", format: "percent", aggregate: "mean", levels: ["form"] },
  { key: "form_exact_match", label: "Form Exact Match", format: "ratio", aggregate: "mean", levels: ["form"] },
];

const metricColumnDefinitionByKey = new Map(metricColumnDefinitions.map((definition) => [definition.key, definition]));
const resultSeriesColors = {
  generated: "#0891b2",
  R1: "#d97706",
  R2: "#16a34a",
};

function statusVariant(status: EvalRunStatus | string): "secondary" | "outline" | "success" | "danger" | "warning" {
  if (status === "completed") return "success";
  if (status === "failed" || status === "canceled") return "danger";
  if (status === "running" || status === "paused") return "warning";
  return "secondary";
}

function scorePercent(score?: number | null): string {
  if (score === null || score === undefined) return "-";
  return `${Math.round(score * 100)}%`;
}

function agreementPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function metricNumber(metrics: Record<string, unknown>, key: string): number | null {
  const value = metrics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function metricNumberFallback(metrics: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = metricNumber(metrics, key);
    if (value !== null) return value;
  }
  return null;
}

function metricBool(metrics: Record<string, unknown>, key: string): boolean {
  return Boolean(metrics[key]);
}

function metricScalar(metrics: Record<string, unknown>, key: string): number | null {
  const value = metrics[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "boolean") return value ? 1 : 0;
  return null;
}

function emptyDetectionStats(): DetectionStats {
  return { truePositive: 0, falsePositive: 0, falseNegative: 0 };
}

function emptyMatchStats(): MatchStats {
  return { total: 0, matches: 0 };
}

function addMatch(stats: MatchStats, matched: boolean) {
  stats.total += 1;
  if (matched) stats.matches += 1;
}

function normalizedAnswer(value?: string | null): string {
  return (value ?? "").trim().toLowerCase();
}

function boolAnswer(value?: string | null): boolean {
  return ["true", "yes", "1"].includes(normalizedAnswer(value));
}

function noAnswer(value?: string | null): boolean {
  return normalizedAnswer(value) === "no";
}

function addDetection(stats: DetectionStats, generated: boolean, reference: boolean) {
  if (generated && reference) stats.truePositive += 1;
  else if (generated && !reference) stats.falsePositive += 1;
  else if (!generated && reference) stats.falseNegative += 1;
}

function precision(stats: DetectionStats): number {
  const denominator = stats.truePositive + stats.falsePositive;
  return denominator ? stats.truePositive / denominator : 0;
}

function recall(stats: DetectionStats): number {
  const denominator = stats.truePositive + stats.falseNegative;
  return denominator ? stats.truePositive / denominator : 0;
}

function f1Score(stats: DetectionStats): number {
  const p = precision(stats);
  const r = recall(stats);
  return p + r ? (2 * p * r) / (p + r) : 0;
}

function ratioFromStats(stats: MatchStats): number {
  return stats.total ? stats.matches / stats.total : 0;
}

function addMetricSample(row: HierarchyMetricAccumulator, key: MetricColumnKey, value: number) {
  row.metricSums[key] = (row.metricSums[key] ?? 0) + value;
  row.metricCounts[key] = (row.metricCounts[key] ?? 0) + 1;
}

function formatNumber(value: number): string {
  if (Number.isInteger(value)) return new Intl.NumberFormat("en-US").format(value);
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

function formatMetricValue(row: HierarchyMetricRow, definition: MetricColumnDefinition): string {
  if (!definition.levels.includes(row.level)) return "-";
  const value = row.metrics[definition.key];
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  if (definition.format === "count") return formatNumber(value);
  if (definition.format === "percent") return `${Math.round(value)}%`;
  if (definition.format === "ratio") return agreementPercent(value);
  return formatNumber(value);
}

function formatRuntime(seconds?: number | null): string {
  if (!seconds) return "";
  const rounded = Math.max(1, Math.round(seconds));
  const minutes = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

function formatDate(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function isActiveRun(run: EvalRunRecord): boolean {
  return run.status === "running";
}

function comparisonFor(item: EvalRunItemRecord, kind: EvalReferenceKind): EvalComparisonRecord | undefined {
  return item.comparisons.find((comparison) => comparison.reference_kind === kind);
}

function primaryComparison(item: EvalRunItemRecord, policy: EvalReferencePolicy): EvalComparisonRecord | undefined {
  if (policy === "r1") return comparisonFor(item, "R1");
  if (policy === "r2") return comparisonFor(item, "R2");
  return comparisonFor(item, "R2") ?? comparisonFor(item, "R1");
}

function visibleVersion(run: EvalRunRecord): string {
  return `v${run.config_version || 1}`;
}

function initialDialogState(datasets: EvalDatasetRecord[], run?: EvalRunRecord | null): EvalRunDialogState {
  return {
    dataset_id: run?.dataset_id ?? datasets[0]?.id ?? "",
    name: run?.name ?? "Ground truth eval",
    model_name: run?.model_name ?? "",
    reference_policy: run?.reference_policy ?? "prefer_r2",
    retry_limit: run?.retry_limit ?? 0,
    enable_mlflow: run?.enable_mlflow ?? false,
  };
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

function buildHierarchyRows(items: EvalRunItemRecord[]): HierarchyMetricRow[] {
  const rows = new Map<HierarchyMetricRow["id"], HierarchyMetricAccumulator>();

  const ensure = (
    level: HierarchyLevel,
    referenceKind: EvalReferenceKind,
    path: string,
    parentPath: string,
    label: string,
  ) => {
    const id = `${referenceKind}:${level}:${path}`;
    let row = rows.get(id);
    if (!row) {
      row = {
        id,
        level,
        referenceKind,
        path,
        parentPath,
        label,
        total: 0,
        matches: 0,
        agreement: 0,
        averageScore: null,
        outcomeMatches: 0,
        metrics: {},
        scoreSum: 0,
        scoreCount: 0,
        metricSums: {},
        metricCounts: {},
        questionStats: emptyMatchStats(),
        questionNoStats: emptyDetectionStats(),
        subquestionStats: emptyMatchStats(),
        subquestionStatsByParent: new Map<string, MatchStats>(),
        subquestionDetectionStats: emptyDetectionStats(),
        subquestionEligibleQuestionCount: 0,
      };
      rows.set(id, row);
    }
    return row;
  };

  for (const item of items) {
    for (const comparison of item.comparisons) {
      const formRow = ensure("form", comparison.reference_kind, "Overall", "", "Overall outcome and form path");
      formRow.total += 1;
      if (metricBool(comparison.metrics, "form_exact_match")) formRow.matches += 1;
      if (metricBool(comparison.metrics, "outcome_match")) formRow.outcomeMatches += 1;
      if (typeof comparison.score === "number") {
        formRow.scoreSum += comparison.score;
        formRow.scoreCount += 1;
      }
      for (const definition of metricColumnDefinitions) {
        const value = metricScalar(comparison.metrics, definition.key);
        if (value !== null) addMetricSample(formRow, definition.key, value);
      }

      for (const agreementItem of comparison.agreement_items ?? []) {
        if (agreementItem.level === "overall") {
          continue;
        }

        if (agreementItem.level === "question") {
          const questionId = agreementItem.question_id ?? "Question";
          const questionText = agreementItem.question_text ?? questionId;
          const questionRow = ensure("question", comparison.reference_kind, questionId, "", questionText);
          questionRow.total += 1;
          if (agreementItem.matched) questionRow.matches += 1;
          addMatch(questionRow.questionStats, agreementItem.matched);
          addDetection(questionRow.questionNoStats, noAnswer(agreementItem.generated_answer), noAnswer(agreementItem.reference_answer));
          if (noAnswer(agreementItem.generated_answer) && noAnswer(agreementItem.reference_answer)) {
            questionRow.subquestionEligibleQuestionCount += 1;
          }
          continue;
        }

        const questionId = agreementItem.question_id ?? "Question";
        const subquestionId = agreementItem.subquestion_id ?? "Sub-question";
        const subquestionText = agreementItem.subquestion_text ?? subquestionId;
        const subquestionRow = ensure(
          "subquestion",
          comparison.reference_kind,
          subquestionId,
          questionId,
          subquestionText,
        );
        subquestionRow.total += 1;
        if (agreementItem.matched) subquestionRow.matches += 1;
        addMatch(subquestionRow.subquestionStats, agreementItem.matched);
        addDetection(subquestionRow.subquestionDetectionStats, boolAnswer(agreementItem.generated_answer), boolAnswer(agreementItem.reference_answer));

        const questionRow = ensure("question", comparison.reference_kind, questionId, "", agreementItem.question_text ?? questionId);
        const parentStats = questionRow.subquestionStatsByParent.get(subquestionId) ?? emptyMatchStats();
        addMatch(parentStats, agreementItem.matched);
        questionRow.subquestionStatsByParent.set(subquestionId, parentStats);
        addMatch(questionRow.subquestionStats, agreementItem.matched);
        addDetection(questionRow.subquestionDetectionStats, boolAnswer(agreementItem.generated_answer), boolAnswer(agreementItem.reference_answer));
      }

      if ((comparison.agreement_items ?? []).length > 0) {
        continue;
      }

      const legacyQuestionMetrics = comparison.metrics.questions;
      if (!Array.isArray(legacyQuestionMetrics)) continue;
      for (const question of legacyQuestionMetrics) {
        const questionRecord = question as Record<string, unknown>;
        const questionId = typeof questionRecord.id === "string" ? questionRecord.id : "Question";
        const questionText = typeof questionRecord.text === "string" ? questionRecord.text : questionId;
        const questionRow = ensure("question", comparison.reference_kind, questionId, "", questionText);
        questionRow.total += 1;
        if (questionRecord.answer_match === true) questionRow.matches += 1;
        addMatch(questionRow.questionStats, questionRecord.answer_match === true);

        const legacyDrivers = questionRecord.drivers;
        if (!Array.isArray(legacyDrivers)) continue;
        for (const driver of legacyDrivers) {
          const driverRecord = driver as Record<string, unknown>;
          const driverId = typeof driverRecord.id === "string" ? driverRecord.id : "Driver";
          const driverText = typeof driverRecord.text === "string" ? driverRecord.text : driverId;
          const driverRow = ensure(
            "subquestion",
            comparison.reference_kind,
            driverId,
            questionId,
            driverText,
          );
          driverRow.total += 1;
          if (driverRecord.match === true) driverRow.matches += 1;
          addMatch(driverRow.subquestionStats, driverRecord.match === true);
          addMatch(questionRow.subquestionStats, driverRecord.match === true);
        }
      }
    }
  }

  return Array.from(rows.values())
    .map((row) => finalizeHierarchyRow(row))
    .sort((first, second) => {
      const refCompare = first.referenceKind.localeCompare(second.referenceKind);
      if (refCompare) return refCompare;
      const order = { form: 0, question: 1, subquestion: 2 };
      return order[first.level] - order[second.level] || first.path.localeCompare(second.path, undefined, { numeric: true });
    });
}

function finalizeHierarchyRow(row: HierarchyMetricAccumulator): HierarchyMetricRow {
  const metrics: Partial<Record<MetricColumnKey, number>> = {};

  for (const definition of metricColumnDefinitions) {
    const sum = row.metricSums[definition.key];
    const count = row.metricCounts[definition.key] ?? 0;
    if (sum === undefined || !count) continue;
    metrics[definition.key] = definition.aggregate === "sum" ? sum : sum / count;
  }

  if (row.level === "form") {
    const questionTotal = metrics.question_total ?? 0;
    const questionMatches = metrics.question_matches ?? 0;
    const subquestionTotal = metrics.subquestion_total ?? 0;
    const subquestionMatches = metrics.subquestion_matches ?? 0;
    const pathExactMatches = metrics.path_exact_matches ?? 0;

    metrics.question_agreement = questionTotal ? questionMatches / questionTotal : 0;
    metrics.question_agreement_percent = metrics.question_agreement * 100;
    metrics.subquestion_agreement = subquestionTotal ? subquestionMatches / subquestionTotal : 0;
    metrics.subquestion_agreement_percent = metrics.subquestion_agreement * 100;
    metrics.path_exact_rate = questionTotal ? pathExactMatches / questionTotal : 0;
    metrics.path_exact_percent = metrics.path_exact_rate * 100;
  }

  if (row.level === "question") {
    metrics.question_total = row.questionStats.total;
    metrics.question_matches = row.questionStats.matches;
    metrics.question_agreement = ratioFromStats(row.questionStats);
    metrics.question_agreement_percent = metrics.question_agreement * 100;
    metrics.question_no_precision = precision(row.questionNoStats);
    metrics.question_no_recall = recall(row.questionNoStats);
    metrics.question_no_f1 = f1Score(row.questionNoStats);
    metrics.question_no_f1_percent = metrics.question_no_f1 * 100;
    metrics.subquestion_eligible_question_count = row.subquestionEligibleQuestionCount;
  }

  if (row.level === "question" || row.level === "subquestion") {
    metrics.subquestion_total = row.subquestionStats.total;
    metrics.subquestion_matches = row.subquestionStats.matches;
    metrics.subquestion_agreement = ratioFromStats(row.subquestionStats);
    metrics.subquestion_agreement_percent = metrics.subquestion_agreement * 100;
    metrics.subquestion_precision = precision(row.subquestionDetectionStats);
    metrics.subquestion_recall = recall(row.subquestionDetectionStats);
    metrics.subquestion_f1 = f1Score(row.subquestionDetectionStats);
    metrics.subquestion_f1_percent = metrics.subquestion_f1 * 100;
  }

  return {
    id: row.id,
    level: row.level,
    referenceKind: row.referenceKind,
    path: row.path,
    parentPath: row.parentPath,
    label: row.label,
    total: row.total,
    matches: row.matches,
    agreement: row.total ? row.matches / row.total : 0,
    averageScore: row.scoreCount ? row.scoreSum / row.scoreCount : null,
    outcomeMatches: row.outcomeMatches,
    metrics,
  };
}

function aggregateRunMetrics(run: EvalRunRecord | null, items: EvalRunItemRecord[]) {
  const completedItems = items.filter((item) => item.status === "completed");
  const primaryComparisons = completedItems
    .map((item) => (run ? primaryComparison(item, run.reference_policy) : undefined))
    .filter((comparison): comparison is EvalComparisonRecord => Boolean(comparison));
  const outcomeMatches = primaryComparisons.filter((comparison) => metricBool(comparison.metrics, "outcome_match")).length;
  const questionAgreement = primaryComparisons
    .map((comparison) => metricNumber(comparison.metrics, "question_agreement"))
    .filter((value): value is number => value !== null);
  const subquestionF1 = primaryComparisons
    .map((comparison) => metricNumberFallback(comparison.metrics, ["subquestion_f1", "driver_f1"]))
    .filter((value): value is number => value !== null);
  const average = (values: number[]) => (values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null);
  return {
    completedItems: completedItems.length,
    outcomeAgreement: primaryComparisons.length ? outcomeMatches / primaryComparisons.length : null,
    questionAgreement: average(questionAgreement),
    subquestionF1: average(subquestionF1),
  };
}

function buildPairRows(items: EvalRunItemRecord[]): PairResultRow[] {
  return items.flatMap((item) =>
    item.comparisons.flatMap((comparison) => {
      const referenceTruth = item.ground_truths.find((truth) => truth.reference_kind === comparison.reference_kind);
      if (!referenceTruth) return [];
      return [
        {
          id: `${item.id}:${comparison.reference_kind}`,
          item,
          comparison,
          referenceKind: comparison.reference_kind,
          referenceTruth,
          claimNumber: item.claim_number,
          status: item.status,
          score: typeof comparison.score === "number" ? comparison.score : null,
          outcomeMatch: metricBool(comparison.metrics, "outcome_match"),
          questionAgreement: metricNumber(comparison.metrics, "question_agreement"),
          subquestionF1: metricNumberFallback(comparison.metrics, ["subquestion_f1", "driver_f1"]),
          generatedOutcome: item.generated_result?.overall_outcome ?? "",
          referenceOutcome: referenceTruth.result.overall_outcome,
        },
      ];
    }),
  );
}

function availableReferenceKinds(items: EvalRunItemRecord[]): EvalReferenceKind[] {
  const kinds = new Set<EvalReferenceKind>();
  for (const item of items) {
    for (const truth of item.ground_truths) kinds.add(truth.reference_kind);
    for (const comparison of item.comparisons) kinds.add(comparison.reference_kind);
  }
  return (["R1", "R2"] as EvalReferenceKind[]).filter((kind) => kinds.has(kind));
}

function selectedReferenceKinds(view: ReferenceView, availableKinds: EvalReferenceKind[]): EvalReferenceKind[] {
  if (view === "both") return availableKinds;
  return availableKinds.includes(view) ? [view] : availableKinds.slice(0, 1);
}

function preferredReferenceView(run: EvalRunRecord | null, availableKinds: EvalReferenceKind[]): ReferenceView {
  if (run?.reference_policy === "r1" && availableKinds.includes("R1")) return "R1";
  if (run?.reference_policy === "r2" && availableKinds.includes("R2")) return "R2";
  return availableKinds.includes("R2") ? "R2" : availableKinds[0] ?? "R1";
}

function comparePath(first: string, second: string): number {
  return first.localeCompare(second, undefined, { numeric: true });
}

function formQuestionLabel(question: FormQuestion): string {
  return question.text || question.id;
}

function questionMap(form: AuditFormResult): Map<string, FormQuestion> {
  return new Map(form.questions.map((question) => [question.id, question]));
}

function subQuestionMap(question?: FormQuestion): Map<string, NonNullable<FormQuestion["sub_questions"]>[number]> {
  return new Map((question?.sub_questions ?? []).map((subQuestion) => [subQuestion.id, subQuestion]));
}

function orderedQuestionIdsForForms(generated: AuditFormResult, reference: AuditFormResult): string[] {
  const generatedQuestions = questionMap(generated);
  const referenceQuestions = questionMap(reference);
  const questionIds = reference.questions.map((question) => question.id);
  for (const questionId of generatedQuestions.keys()) {
    if (!referenceQuestions.has(questionId)) questionIds.push(questionId);
  }
  return questionIds;
}

function countDisplay(count: number, total: number): string {
  return `${formatNumber(count)} of ${formatNumber(total)}`;
}

function percentDisplay(value: number, matches: number, total: number): string {
  return `${Math.round(value)}% (${formatNumber(matches)}/${formatNumber(total)})`;
}

function buildResultSections(items: EvalRunItemRecord[], referenceView: ReferenceView): EvalVisualizationSection[] {
  const availableKinds = availableReferenceKinds(items);
  const references = selectedReferenceKinds(referenceView, availableKinds);
  const generatedKey = "generated";
  type CountBucket = { count: number; total: number };
  type ResultAccumulator = {
    id: string;
    label: string;
    context: string;
    generated: CountBucket;
    references: Partial<Record<EvalReferenceKind, CountBucket>>;
  };
  const newBucket = (): CountBucket => ({ count: 0, total: 0 });
  const overall: ResultAccumulator = {
    id: "overall:rating",
    label: "Overall rating: Does Not Meet",
    context: "Form result",
    generated: newBucket(),
    references: {},
  };
  const questionRows = new Map<string, ResultAccumulator>();
  const subquestionRows = new Map<string, ResultAccumulator>();

  const ensureResultRow = (map: Map<string, ResultAccumulator>, id: string, label: string, context: string) => {
    let row = map.get(id);
    if (!row) {
      row = { id, label, context, generated: newBucket(), references: {} };
      map.set(id, row);
    } else {
      row.label = row.label || label;
      row.context = row.context || context;
    }
    return row;
  };
  const referenceBucket = (row: ResultAccumulator, kind: EvalReferenceKind) => {
    row.references[kind] = row.references[kind] ?? newBucket();
    return row.references[kind] as CountBucket;
  };
  const addQuestionCounts = (form: AuditFormResult, target: "generated" | EvalReferenceKind) => {
    for (const question of form.questions) {
      const questionRow = ensureResultRow(questionRows, question.id, formQuestionLabel(question), question.id);
      const questionBucket = target === generatedKey ? questionRow.generated : referenceBucket(questionRow, target);
      questionBucket.total += 1;
      if (question.answer === "No") questionBucket.count += 1;

      for (const subQuestion of question.sub_questions ?? []) {
        const subquestionId = `${question.id}:${subQuestion.id}`;
        const subquestionRow = ensureResultRow(
          subquestionRows,
          subquestionId,
          subQuestion.text || subQuestion.id,
          `${question.id} / ${subQuestion.id}`,
        );
        const subquestionBucket = target === generatedKey ? subquestionRow.generated : referenceBucket(subquestionRow, target);
        subquestionBucket.total += 1;
        if (subQuestion.answer) subquestionBucket.count += 1;
      }
    }
  };

  for (const item of items) {
    if (item.generated_result) {
      overall.generated.total += 1;
      if (item.generated_result.overall_outcome === "Does Not Meet") overall.generated.count += 1;
      addQuestionCounts(item.generated_result, generatedKey);
    }

    for (const referenceKind of references) {
      const truth = item.ground_truths.find((candidate) => candidate.reference_kind === referenceKind);
      if (!truth) continue;
      const bucket = referenceBucket(overall, referenceKind);
      bucket.total += 1;
      if (truth.result.overall_outcome === "Does Not Meet") bucket.count += 1;
      addQuestionCounts(truth.result, referenceKind);
    }
  }

  const toBars = (row: ResultAccumulator): EvalVisualizationBar[] => {
    const bars: EvalVisualizationBar[] = [];
    if (row.generated.total > 0) {
      bars.push({
        key: "generated",
        label: "Generated",
        value: row.generated.count,
        displayValue: countDisplay(row.generated.count, row.generated.total),
        color: resultSeriesColors.generated,
      });
    }
    for (const referenceKind of references) {
      const bucket = row.references[referenceKind];
      if (!bucket || bucket.total === 0) continue;
      bars.push({
        key: referenceKind,
        label: `Ground Truth ${referenceKind}`,
        value: bucket.count,
        displayValue: countDisplay(bucket.count, bucket.total),
        color: resultSeriesColors[referenceKind],
      });
    }
    return bars;
  };
  const toRows = (rows: ResultAccumulator[]) =>
    rows
      .map((row) => ({ id: row.id, label: row.label, context: row.context, bars: toBars(row) }))
      .filter((row) => row.bars.length > 0);

  return [
    { id: "overall", title: "Overall Rating", rows: toRows([overall]) },
    { id: "question", title: "Question No Answers", rows: toRows(Array.from(questionRows.values()).sort((a, b) => comparePath(a.id, b.id))) },
    {
      id: "subquestion",
      title: "Ticked Drivers",
      rows: toRows(Array.from(subquestionRows.values()).sort((a, b) => comparePath(a.id, b.id))),
    },
  ];
}

function buildAgreementSections(items: EvalRunItemRecord[], referenceView: ReferenceView): EvalVisualizationSection[] {
  const availableKinds = availableReferenceKinds(items);
  const references = selectedReferenceKinds(referenceView, availableKinds);
  type AgreementAccumulator = {
    id: string;
    label: string;
    context: string;
    references: Partial<Record<EvalReferenceKind, MatchStats>>;
  };
  const overall: AgreementAccumulator = {
    id: "overall:agreement",
    label: "Overall rating agreement",
    context: "Generated vs ground truth",
    references: {},
  };
  const questionRows = new Map<string, AgreementAccumulator>();
  const subquestionRows = new Map<string, AgreementAccumulator>();

  const ensureAgreementRow = (map: Map<string, AgreementAccumulator>, id: string, label: string, context: string) => {
    let row = map.get(id);
    if (!row) {
      row = { id, label, context, references: {} };
      map.set(id, row);
    } else {
      row.label = row.label || label;
      row.context = row.context || context;
    }
    return row;
  };
  const referenceStats = (row: AgreementAccumulator, kind: EvalReferenceKind) => {
    row.references[kind] = row.references[kind] ?? emptyMatchStats();
    return row.references[kind] as MatchStats;
  };
  const addFormAgreementRows = (
    generated: AuditFormResult,
    reference: AuditFormResult,
    referenceKind: EvalReferenceKind,
  ) => {
    const generatedQuestions = questionMap(generated);
    const referenceQuestions = questionMap(reference);
    for (const questionId of orderedQuestionIdsForForms(generated, reference)) {
      const generatedQuestion = generatedQuestions.get(questionId);
      const referenceQuestion = referenceQuestions.get(questionId);
      const question = referenceQuestion ?? generatedQuestion;
      const questionMatch = generatedQuestion?.answer === referenceQuestion?.answer;
      const questionRow = ensureAgreementRow(questionRows, questionId, question?.text ?? questionId, questionId);
      addMatch(referenceStats(questionRow, referenceKind), questionMatch);

      if (generatedQuestion?.answer !== "No" || referenceQuestion?.answer !== "No") continue;
      const generatedSubQuestions = subQuestionMap(generatedQuestion);
      const referenceSubQuestions = subQuestionMap(referenceQuestion);
      const subQuestionIds = Array.from(new Set([...generatedSubQuestions.keys(), ...referenceSubQuestions.keys()])).sort(comparePath);
      for (const subQuestionId of subQuestionIds) {
        const generatedSubQuestion = generatedSubQuestions.get(subQuestionId);
        const referenceSubQuestion = referenceSubQuestions.get(subQuestionId);
        const subQuestion = referenceSubQuestion ?? generatedSubQuestion;
        const subQuestionMatch = Boolean(generatedSubQuestion?.answer) === Boolean(referenceSubQuestion?.answer);
        const subquestionRow = ensureAgreementRow(
          subquestionRows,
          `${questionId}:${subQuestionId}`,
          subQuestion?.text ?? subQuestionId,
          `${questionId} / ${subQuestionId}`,
        );
        addMatch(referenceStats(subquestionRow, referenceKind), subQuestionMatch);
      }
    }
  };

  for (const item of items) {
    for (const referenceKind of references) {
      const comparison = comparisonFor(item, referenceKind);
      if (!comparison) continue;
      const truth = item.ground_truths.find((candidate) => candidate.reference_kind === referenceKind);
      const agreementItems = comparison.agreement_items ?? [];
      const overallItem = agreementItems.find((agreementItem) => agreementItem.level === "overall");
      addMatch(referenceStats(overall, referenceKind), overallItem ? overallItem.matched : metricBool(comparison.metrics, "outcome_match"));

      const detailedAgreementItems = agreementItems.filter((agreementItem) => agreementItem.level !== "overall");
      if (detailedAgreementItems.length === 0 && item.generated_result && truth?.result) {
        addFormAgreementRows(item.generated_result, truth.result, referenceKind);
        continue;
      }

      for (const agreementItem of detailedAgreementItems) {
        if (agreementItem.level === "overall") continue;
        if (agreementItem.level === "question") {
          const questionId = agreementItem.question_id ?? "Question";
          const row = ensureAgreementRow(questionRows, questionId, agreementItem.question_text ?? questionId, questionId);
          addMatch(referenceStats(row, referenceKind), agreementItem.matched);
          continue;
        }

        const questionId = agreementItem.question_id ?? "Question";
        const subquestionId = agreementItem.subquestion_id ?? "Sub-question";
        const row = ensureAgreementRow(
          subquestionRows,
          `${questionId}:${subquestionId}`,
          agreementItem.subquestion_text ?? subquestionId,
          `${questionId} / ${subquestionId}`,
        );
        addMatch(referenceStats(row, referenceKind), agreementItem.matched);
      }
    }
  }

  const toBars = (row: AgreementAccumulator): EvalVisualizationBar[] =>
    references.flatMap((referenceKind) => {
      const stats = row.references[referenceKind];
      if (!stats || stats.total === 0) return [];
      const value = ratioFromStats(stats) * 100;
      return [
        {
          key: referenceKind,
          label: `${referenceKind} Agreement`,
          value,
          displayValue: percentDisplay(value, stats.matches, stats.total),
          color: resultSeriesColors[referenceKind],
        },
      ];
    });
  const toRows = (rows: AgreementAccumulator[]) =>
    rows
      .map((row) => ({ id: row.id, label: row.label, context: row.context, bars: toBars(row) }))
      .filter((row) => row.bars.length > 0);

  return [
    { id: "overall", title: "Overall Agreement", rows: toRows([overall]) },
    { id: "question", title: "Question Agreement", rows: toRows(Array.from(questionRows.values()).sort((a, b) => comparePath(a.id, b.id))) },
    {
      id: "subquestion",
      title: "Driver Agreement",
      rows: toRows(Array.from(subquestionRows.values()).sort((a, b) => comparePath(a.id, b.id))),
    },
  ];
}

function primaryReferenceKind(run: EvalRunRecord | null, rows: Array<{ referenceKind: EvalReferenceKind }>): EvalReferenceKind {
  if (run?.reference_policy === "r1") return "R1";
  if (run?.reference_policy === "r2") return "R2";
  return rows.some((row) => row.referenceKind === "R2") ? "R2" : "R1";
}

function readPersistedQueue(): { ids: string[]; hasPersisted: boolean } {
  if (typeof window === "undefined") return { ids: [], hasPersisted: false };
  try {
    const raw = window.localStorage.getItem(evalQueueStorageKey);
    if (raw === null) return { ids: [], hasPersisted: false };
    const parsed = JSON.parse(raw);
    return {
      ids: Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [],
      hasPersisted: true,
    };
  } catch {
    return { ids: [], hasPersisted: true };
  }
}

function persistQueue(ids: string[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(evalQueueStorageKey, JSON.stringify(ids));
  } catch {
    // Queue persistence should never block eval monitoring.
  }
}

export function EvaluationWorkbench() {
  const [datasets, setDatasets] = useState<EvalDatasetRecord[]>([]);
  const [runs, setRuns] = useState<EvalRunRecord[]>([]);
  const [itemsByRun, setItemsByRun] = useState<Record<string, EvalRunItemRecord[]>>({});
  const [queueRunIds, setQueueRunIds] = useState<string[]>([]);
  const [queueHydrated, setQueueHydrated] = useState(false);
  const [analysisRunId, setAnalysisRunId] = useState("");
  const [runSearch, setRunSearch] = useState("");
  const [runStatusFilter, setRunStatusFilter] = useState("all");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingRun, setEditingRun] = useState<EvalRunRecord | null>(null);
  const [viewingPair, setViewingPair] = useState<PairResultRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [savingRun, setSavingRun] = useState(false);
  const [actioningRun, setActioningRun] = useState("");
  const [error, setError] = useState("");

  const queueRunIdsRef = useRef<string[]>([]);
  const analysisRunIdRef = useRef("");
  const hasPersistedQueueRef = useRef(false);

  useEffect(() => {
    const persisted = readPersistedQueue();
    hasPersistedQueueRef.current = persisted.hasPersisted;
    setQueueRunIds(persisted.ids);
    setQueueHydrated(true);
  }, []);

  useEffect(() => {
    queueRunIdsRef.current = queueRunIds;
  }, [queueRunIds]);

  useEffect(() => {
    if (!queueHydrated) return;
    if (!hasPersistedQueueRef.current && queueRunIds.length === 0) return;
    persistQueue(queueRunIds);
    hasPersistedQueueRef.current = true;
  }, [queueHydrated, queueRunIds]);

  useEffect(() => {
    analysisRunIdRef.current = analysisRunId;
  }, [analysisRunId]);

  const completedRuns = useMemo(() => runs.filter((run) => run.status === "completed"), [runs]);
  const queueRuns = useMemo(
    () => queueRunIds.map((runId) => runs.find((run) => run.id === runId)).filter((run): run is EvalRunRecord => Boolean(run)),
    [queueRunIds, runs],
  );
  const analysisRun = useMemo(
    () => completedRuns.find((run) => run.id === analysisRunId) ?? completedRuns[0] ?? null,
    [analysisRunId, completedRuns],
  );
  const analysisItems = analysisRun ? itemsByRun[analysisRun.id] ?? [] : [];
  const hasActiveRuns = useMemo(() => runs.some(isActiveRun), [runs]);
  const filteredRuns = useMemo(() => {
    const query = runSearch.trim().toLowerCase();
    return runs.filter((run) => {
      if (runStatusFilter !== "all" && run.status !== runStatusFilter) return false;
      if (!query) return true;
      return [run.name, run.dataset_name, run.model_name, run.status, visibleVersion(run)]
        .join(" ")
        .toLowerCase()
        .includes(query);
    });
  }, [runSearch, runStatusFilter, runs]);

  const refresh = useCallback(async ({ initial = false, manual = false }: { initial?: boolean; manual?: boolean } = {}) => {
    if (initial) setLoading(true);
    if (manual) setRefreshing(true);
    setError("");
    try {
      const [nextDatasets, nextRuns] = await Promise.all([listEvalDatasets(), listEvalRuns()]);
      setDatasets(nextDatasets);
      setRuns(nextRuns);

      const validRunIds = new Set(nextRuns.map((run) => run.id));
      const activeIds = nextRuns.filter(isActiveRun).map((run) => run.id);
      const retainedQueue = queueRunIdsRef.current.filter((runId) => validRunIds.has(runId));
      const nextQueue =
        retainedQueue.length || hasPersistedQueueRef.current
          ? retainedQueue
          : activeIds;
      setQueueRunIds(nextQueue);

      const nextCompletedRuns = nextRuns.filter((run) => run.status === "completed");
      const currentAnalysisRunId = analysisRunIdRef.current;
      const nextAnalysisRunId =
        currentAnalysisRunId && nextCompletedRuns.some((run) => run.id === currentAnalysisRunId)
          ? currentAnalysisRunId
          : nextCompletedRuns[0]?.id ?? "";
      setAnalysisRunId(nextAnalysisRunId);

      const runIdsToLoad = new Set([...nextQueue, nextAnalysisRunId, ...activeIds].filter(Boolean));
      const entries = await Promise.all(
        Array.from(runIdsToLoad).map(async (runId) => [runId, await listEvalRunItems(runId)] as const),
      );
      if (entries.length) {
        setItemsByRun((current) => ({ ...current, ...Object.fromEntries(entries) }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load evaluation data.");
    } finally {
      if (initial) setLoading(false);
      if (manual) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (!queueHydrated) return;
    void refresh({ initial: true });
  }, [queueHydrated, refresh]);

  useEffect(() => {
    if (!hasActiveRuns) return;
    const interval = window.setInterval(() => {
      void refresh();
    }, pollMs);
    return () => window.clearInterval(interval);
  }, [hasActiveRuns, refresh]);

  useEffect(() => {
    const missingRunIds = [...queueRunIds, analysisRunId].filter((runId) => runId && !itemsByRun[runId]);
    if (!missingRunIds.length) return;
    let canceled = false;
    void Promise.all(missingRunIds.map(async (runId) => [runId, await listEvalRunItems(runId)] as const))
      .then((entries) => {
        if (!canceled) setItemsByRun((current) => ({ ...current, ...Object.fromEntries(entries) }));
      })
      .catch((err) => {
        if (!canceled) setError(err instanceof Error ? err.message : "Failed to load run items.");
      });
    return () => {
      canceled = true;
    };
  }, [analysisRunId, itemsByRun, queueRunIds]);

  const addToQueue = (run: EvalRunRecord) => {
    setQueueRunIds((current) => (current.includes(run.id) ? current : [run.id, ...current]));
  };

  const removeFromQueue = (runId: string) => {
    setQueueRunIds((current) => current.filter((candidate) => candidate !== runId));
  };

  const saveRun = async (payload: EvalRunPayload) => {
    setSavingRun(true);
    setError("");
    try {
      const run = await createEvalRun(payload);
      setDialogOpen(false);
      setEditingRun(null);
      await refresh();
      setQueueRunIds((current) => [
        run.id,
        ...current.filter((runId) => runId !== run.id && runId !== payload.base_run_id),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save evaluation run.");
    } finally {
      setSavingRun(false);
    }
  };

  const runAction = async (run: EvalRunRecord, action: RunAction) => {
    setActioningRun(`${run.id}:${action}`);
    setError("");
    try {
      if (action === "start") await resumeEvalRun(run.id);
      if (action === "pause") await pauseEvalRun(run.id);
      if (action === "resume") await resumeEvalRun(run.id);
      if (action === "cancel") await cancelEvalRun(run.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${action} evaluation run.`);
    } finally {
      setActioningRun("");
    }
  };

  const openCreateDialog = () => {
    setEditingRun(null);
    setDialogOpen(true);
  };

  const openEditDialog = (run: EvalRunRecord) => {
    if (run.status === "running") return;
    setEditingRun(run);
    setDialogOpen(true);
  };

  return (
    <div className="space-y-4">
      {error ? (
        <Card className="border-destructive/40">
          <CardContent className="p-4 text-sm text-destructive">{error}</CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(340px,420px)_1fr]">
        <EvalRunSetupCard
          runs={filteredRuns}
          queueRunIds={queueRunIds}
          runSearch={runSearch}
          runStatusFilter={runStatusFilter}
          loading={loading}
          refreshing={refreshing}
          onRunSearchChange={setRunSearch}
          onRunStatusFilterChange={setRunStatusFilter}
          onRefresh={() => void refresh({ manual: true })}
          onCreateRun={openCreateDialog}
          onAddRun={addToQueue}
        />
        <EvalQueuePanel
          runs={queueRuns}
          itemsByRun={itemsByRun}
          actioningRun={actioningRun}
          onAction={runAction}
          onEdit={openEditDialog}
          onRemove={removeFromQueue}
        />
      </div>

      <CompletedRunAnalysisCard
        runs={completedRuns}
        run={analysisRun}
        items={analysisItems}
        onRunChange={setAnalysisRunId}
      />

      <RunResultsHierarchyTable run={analysisRun} items={analysisItems} />

      <PairResultsTable run={analysisRun} items={analysisItems} onViewPair={setViewingPair} />

      <EvalResultsVisualization run={analysisRun} items={analysisItems} />

      <EvalRunDialog
        open={dialogOpen}
        datasets={datasets}
        editingRun={editingRun}
        saving={savingRun}
        onClose={() => {
          if (savingRun) return;
          setDialogOpen(false);
          setEditingRun(null);
        }}
        onSave={saveRun}
      />

      <PairComparisonDialog pair={viewingPair} onClose={() => setViewingPair(null)} />
    </div>
  );
}

function EvalRunSetupCard({
  runs,
  queueRunIds,
  runSearch,
  runStatusFilter,
  loading,
  refreshing,
  onRunSearchChange,
  onRunStatusFilterChange,
  onRefresh,
  onCreateRun,
  onAddRun,
}: {
  runs: EvalRunRecord[];
  queueRunIds: string[];
  runSearch: string;
  runStatusFilter: string;
  loading: boolean;
  refreshing: boolean;
  onRunSearchChange: (value: string) => void;
  onRunStatusFilterChange: (value: string) => void;
  onRefresh: () => void;
  onCreateRun: () => void;
  onAddRun: (run: EvalRunRecord) => void;
}) {
  return (
    <Card className="flex h-fit max-h-[680px] min-h-0 flex-col overflow-hidden">
      <CardHeader className="border-b">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <FolderArchive className="h-4 w-4 text-primary" />
            Eval Runs
          </CardTitle>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="icon" className="h-8 w-8" onClick={onRefresh} disabled={loading || refreshing}>
              {loading || refreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            </Button>
            <Button type="button" size="sm" className="gap-1.5" onClick={onCreateRun}>
              <Plus className="h-3.5 w-3.5" />
              New
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 space-y-3 overflow-hidden p-0">
        <div className="grid gap-3 border-b bg-secondary/35 p-3">
          <label className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={runSearch}
              onChange={(event) => onRunSearchChange(event.target.value)}
              className="h-8 pl-8 text-xs"
              placeholder="Search eval runs"
            />
          </label>
          <select
            value={runStatusFilter}
            onChange={(event) => onRunStatusFilterChange(event.target.value)}
            className="h-8 rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="all">All statuses</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="paused">Paused</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="canceled">Canceled</option>
          </select>
        </div>

        <div className="chat-scrollbar max-h-[430px] overflow-y-auto">
          {runs.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <FileText className="mx-auto h-8 w-8 text-muted-foreground/40" />
              <p className="mt-2 text-sm font-medium">No eval runs match</p>
            </div>
          ) : (
            runs.map((run) => {
              const queued = queueRunIds.includes(run.id);
              return (
                <div key={run.id} className="grid gap-3 border-b px-4 py-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-sm font-medium">{run.name}</p>
                      <Badge variant="outline">{visibleVersion(run)}</Badge>
                      <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
                    </div>
                    <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{run.dataset_name || run.dataset_id}</p>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="outline">{run.completed_count}/{run.total_count}</Badge>
                      <Badge variant="outline">{scorePercent(run.primary_score)}</Badge>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant={queued ? "outline" : "secondary"}
                      onClick={() => onAddRun(run)}
                      disabled={queued}
                    >
                      {queued ? "Queued" : "Add"}
                    </Button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function EvalQueuePanel({
  runs,
  itemsByRun,
  actioningRun,
  onAction,
  onEdit,
  onRemove,
}: {
  runs: EvalRunRecord[];
  itemsByRun: Record<string, EvalRunItemRecord[]>;
  actioningRun: string;
  onAction: (run: EvalRunRecord, action: RunAction) => Promise<void>;
  onEdit: (run: EvalRunRecord) => void;
  onRemove: (runId: string) => void;
}) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <PlayCircle className="h-4 w-4 text-primary" />
            Execution Queue
          </CardTitle>
          <Badge variant="outline">{runs.length} selected</Badge>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow className="bg-secondary/60">
              <TableHead>Run</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Progress</TableHead>
              <TableHead>Score</TableHead>
              <TableHead className="text-right">Controls</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-32 text-center text-muted-foreground">
                  Add eval runs to the queue to monitor progress and control execution.
                </TableCell>
              </TableRow>
            ) : (
              runs.map((run) => {
                const metrics = aggregateRunMetrics(run, itemsByRun[run.id] ?? []);
                return (
                  <TableRow key={run.id}>
                    <TableCell className="min-w-[260px]">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium">{run.name}</p>
                        <Badge variant="outline">{visibleVersion(run)}</Badge>
                      </div>
                      <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{run.dataset_name || run.dataset_id}</p>
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
                    </TableCell>
                    <TableCell className="min-w-[180px]">
                      <div className="h-2 overflow-hidden rounded-full bg-secondary">
                        <div className="h-full rounded-full bg-primary" style={{ width: `${run.progress_percent}%` }} />
                      </div>
                      <div className="mt-1 text-xs tabular-nums text-muted-foreground">
                        {run.progress_percent}% ({run.completed_count}/{run.total_count})
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm font-medium tabular-nums">{scorePercent(run.primary_score)}</div>
                      <div className="text-xs text-muted-foreground">
                        {metrics.outcomeAgreement === null ? "No agreement yet" : `${agreementPercent(metrics.outcomeAgreement)} outcome`}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        {run.status === "queued" ? (
                          <IconButton
                            label="Start run"
                            disabled={Boolean(actioningRun)}
                            onClick={() => void onAction(run, "start")}
                            loading={actioningRun === `${run.id}:start`}
                            className="text-emerald-700 hover:text-emerald-800 dark:text-emerald-300"
                          >
                            <Play className="h-4 w-4 fill-current" />
                          </IconButton>
                        ) : null}
                        {run.status === "running" ? (
                          <IconButton
                            label="Pause run"
                            disabled={Boolean(actioningRun)}
                            onClick={() => void onAction(run, "pause")}
                            loading={actioningRun === `${run.id}:pause`}
                            className="text-amber-700 hover:text-amber-800 dark:text-amber-300"
                          >
                            <Pause className="h-4 w-4 fill-current" />
                          </IconButton>
                        ) : null}
                        {run.status === "paused" ? (
                          <IconButton
                            label="Resume run"
                            disabled={Boolean(actioningRun)}
                            onClick={() => void onAction(run, "resume")}
                            loading={actioningRun === `${run.id}:resume`}
                            className="text-emerald-700 hover:text-emerald-800 dark:text-emerald-300"
                          >
                            <Play className="h-4 w-4 fill-current" />
                          </IconButton>
                        ) : null}
                        {run.status !== "completed" && run.status !== "canceled" ? (
                          <IconButton
                            label="Stop run"
                            disabled={Boolean(actioningRun)}
                            onClick={() => void onAction(run, "cancel")}
                            loading={actioningRun === `${run.id}:cancel`}
                            className="text-rose-700 hover:text-rose-800 dark:text-rose-300"
                          >
                            <Square className="h-4 w-4 fill-current" />
                          </IconButton>
                        ) : null}
                        {run.status !== "running" ? (
                          <IconButton label={`Edit as v${(run.config_version || 1) + 1}`} onClick={() => onEdit(run)}>
                            <SquarePen className="h-4 w-4" />
                          </IconButton>
                        ) : null}
                        <IconButton label="Remove from queue" onClick={() => onRemove(run.id)}>
                          <Trash2 className="h-4 w-4" />
                        </IconButton>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function CompletedRunAnalysisCard({
  runs,
  run,
  items,
  onRunChange,
}: {
  runs: EvalRunRecord[];
  run: EvalRunRecord | null;
  items: EvalRunItemRecord[];
  onRunChange: (runId: string) => void;
}) {
  const [search, setSearch] = useState("");
  const metrics = aggregateRunMetrics(run, items);
  const visibleRuns = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return runs;
    return runs.filter((candidate) =>
      [
        candidate.name,
        candidate.dataset_name,
        candidate.model_name,
        candidate.reference_policy,
        visibleVersion(candidate),
      ]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [runs, search]);
  const selectValue = visibleRuns.some((candidate) => candidate.id === run?.id) ? run?.id ?? "" : "";
  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Layers3 className="h-4 w-4 text-primary" />
            Completed Run Analysis
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <label className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className="h-9 w-[240px] pl-8 text-xs"
                placeholder="Search completed runs"
              />
            </label>
            <select
              value={selectValue}
              onChange={(event) => onRunChange(event.target.value)}
              className="h-9 min-w-[280px] rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              disabled={runs.length === 0 || visibleRuns.length === 0}
            >
              {runs.length === 0 ? <option value="">No completed runs</option> : null}
              {runs.length > 0 && visibleRuns.length === 0 ? <option value="">No runs match</option> : null}
              {visibleRuns.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.name} {visibleVersion(candidate)}
                </option>
              ))}
            </select>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-5">
        {!run ? (
          <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
            Completed eval runs will appear here for result analysis.
          </p>
        ) : (
          <div className="grid gap-3 md:grid-cols-4">
            <MiniMetric label="Completed" value={String(metrics.completedItems)} helper={`${run.failed_count} failed`} />
            <MiniMetric
              label="Outcome Agree"
              value={metrics.outcomeAgreement === null ? "-" : agreementPercent(metrics.outcomeAgreement)}
              helper="primary reference"
            />
            <MiniMetric
              label="Question Agree"
              value={metrics.questionAgreement === null ? "-" : agreementPercent(metrics.questionAgreement)}
              helper="Yes/No answers"
            />
            <MiniMetric
              label="Sub-question F1"
              value={metrics.subquestionF1 === null ? "-" : agreementPercent(metrics.subquestionF1)}
              helper="applicable sub-questions"
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function IconButton({
  label,
  disabled,
  loading,
  className,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  loading?: boolean;
  className?: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      className={cn("h-8 w-8", className)}
      disabled={disabled}
      onClick={onClick}
      title={label}
      aria-label={label}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : children}
    </Button>
  );
}

function MiniMetric({ label, value, helper }: { label: string; value: string; helper: string }) {
  return (
    <div className="rounded-md border bg-card px-3 py-2">
      <p className="text-[11px] font-semibold uppercase text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
      <p className="truncate text-[11px] text-muted-foreground">{helper}</p>
    </div>
  );
}

function RunResultsHierarchyTable({ run, items }: { run: EvalRunRecord | null; items: EvalRunItemRecord[] }) {
  const [search, setSearch] = useState("");
  const [referenceFilter, setReferenceFilter] = useState("primary");
  const [levelFilter, setLevelFilter] = useState("all");
  const [sortKey, setSortKey] = useState<"agreement" | "path" | "total">("agreement");
  const [metricColumns, setMetricColumns] = useState<MetricColumnKey[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const rows = useMemo(() => buildHierarchyRows(items), [items]);
  const primaryRef = primaryReferenceKind(run, rows);
  const selectedMetricDefinitions = useMemo(
    () => metricColumns.map((key) => metricColumnDefinitionByKey.get(key)).filter((definition): definition is MetricColumnDefinition => Boolean(definition)),
    [metricColumns],
  );
  const visibleTopRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    const subRowsByParent = new Map<string, HierarchyMetricRow[]>();
    for (const row of rows) {
      if (row.level === "subquestion") {
        const key = `${row.referenceKind}:${row.parentPath}`;
        subRowsByParent.set(key, [...(subRowsByParent.get(key) ?? []), row]);
      }
    }
    const matchesQuery = (row: HierarchyMetricRow) =>
      !query || [row.path, row.label, row.level, row.referenceKind].join(" ").toLowerCase().includes(query);
    const matchesReference = (row: HierarchyMetricRow) => {
      if (referenceFilter === "primary") return row.referenceKind === primaryRef;
      if (referenceFilter === "all") return true;
      return row.referenceKind === referenceFilter;
    };
    return rows
      .filter((row) => row.level !== "subquestion")
      .filter((row) => matchesReference(row))
      .filter((row) => {
        if (levelFilter !== "all" && row.level !== levelFilter) return false;
        const children = subRowsByParent.get(`${row.referenceKind}:${row.path}`) ?? [];
        return matchesQuery(row) || children.some(matchesQuery);
      })
      .sort((first, second) => {
        if (sortKey === "path") return first.path.localeCompare(second.path, undefined, { numeric: true });
        if (sortKey === "total") return second.total - first.total || first.path.localeCompare(second.path, undefined, { numeric: true });
        return first.agreement - second.agreement || first.path.localeCompare(second.path, undefined, { numeric: true });
      });
  }, [levelFilter, primaryRef, referenceFilter, rows, search, sortKey]);

  const childRowsByParent = useMemo(() => {
    const query = search.trim().toLowerCase();
    const matchesQuery = (row: HierarchyMetricRow) =>
      !query || [row.path, row.label, row.level, row.referenceKind].join(" ").toLowerCase().includes(query);
    return rows.reduce((map, row) => {
      if (row.level !== "subquestion") return map;
      if (referenceFilter === "primary" && row.referenceKind !== primaryRef) return map;
      if (referenceFilter !== "primary" && referenceFilter !== "all" && row.referenceKind !== referenceFilter) return map;
      if (!matchesQuery(row)) return map;
      const key = `${row.referenceKind}:${row.parentPath}`;
      map.set(key, [...(map.get(key) ?? []), row]);
      return map;
    }, new Map<string, HierarchyMetricRow[]>());
  }, [primaryRef, referenceFilter, rows, search]);
  const expandableRowIds = useMemo(
    () =>
      visibleTopRows
        .filter((row) => (childRowsByParent.get(`${row.referenceKind}:${row.path}`) ?? []).length > 0)
        .map((row) => row.id),
    [childRowsByParent, visibleTopRows],
  );

  const toggleExpanded = (rowId: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  };
  const addMetricColumn = (key: string) => {
    if (!key) return;
    setMetricColumns((current) => (current.includes(key as MetricColumnKey) ? current : [...current, key as MetricColumnKey]));
  };
  const removeMetricColumn = (key: MetricColumnKey) => {
    setMetricColumns((current) => current.filter((candidate) => candidate !== key));
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Run Results</CardTitle>
          {run ? <Badge variant="outline">{run.name} {visibleVersion(run)}</Badge> : null}
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="flex flex-wrap items-center gap-3 border-b bg-secondary/40 px-4 py-3">
          <div className="relative min-w-[240px] flex-1 sm:max-w-sm">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="h-8 pl-9 text-xs"
              placeholder="Search question, sub-question, reference..."
            />
          </div>
          <SelectFilter value={referenceFilter} onChange={setReferenceFilter} label="Reference">
            <option value="primary">Primary ref</option>
            <option value="all">All refs</option>
            <option value="R1">R1</option>
            <option value="R2">R2</option>
          </SelectFilter>
          <SelectFilter value={levelFilter} onChange={setLevelFilter} label="Level">
            <option value="all">All levels</option>
            <option value="form">Form</option>
            <option value="question">Questions</option>
          </SelectFilter>
          <SelectFilter value={sortKey} onChange={(value) => setSortKey(value as "agreement" | "path" | "total")} label="Sort">
            <option value="agreement">Lowest agreement</option>
            <option value="path">Path</option>
            <option value="total">Volume</option>
          </SelectFilter>
          <SelectFilter value="" onChange={addMetricColumn} label="Add metric column">
            <option value="">Add metric column...</option>
            {metricColumnDefinitions
              .filter((definition) => !metricColumns.includes(definition.key))
              .map((definition) => (
                <option key={definition.key} value={definition.key}>
                  {definition.label}
                </option>
              ))}
          </SelectFilter>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setExpanded(new Set(expandableRowIds))}
            disabled={expandableRowIds.length === 0}
          >
            Expand
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setExpanded(new Set())}
            disabled={expanded.size === 0}
          >
            Collapse
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setSearch("");
              setReferenceFilter("primary");
              setLevelFilter("all");
            }}
          >
            <X className="h-3.5 w-3.5" />
            Clear
          </Button>
        </div>
        {selectedMetricDefinitions.length ? (
          <div className="flex flex-wrap gap-2 border-b px-4 py-2">
            {selectedMetricDefinitions.map((definition) => (
              <button
                key={definition.key}
                type="button"
                onClick={() => removeMetricColumn(definition.key)}
                className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
                title={`Remove ${definition.label}`}
              >
                {definition.label}
                <X className="h-3 w-3" />
              </button>
            ))}
            <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setMetricColumns([])}>
              Reset columns
            </Button>
          </div>
        ) : null}
        <Table>
          <TableHeader>
            <TableRow className="bg-secondary/60">
              <TableHead className="w-9" />
              <TableHead>Path</TableHead>
              <TableHead>Level</TableHead>
              <TableHead>Reference</TableHead>
              <TableHead>Agreement</TableHead>
              <TableHead>Matches</TableHead>
              <TableHead>Avg Score</TableHead>
              {selectedMetricDefinitions.map((definition) => (
                <TableHead key={definition.key} className="min-w-[130px]">
                  {definition.label}
                </TableHead>
              ))}
              <TableHead>Label</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!run || visibleTopRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8 + selectedMetricDefinitions.length} className="h-24 text-center text-muted-foreground">
                  No hierarchy metrics available for this run.
                </TableCell>
              </TableRow>
            ) : (
              visibleTopRows.map((row) => {
                const children = childRowsByParent.get(`${row.referenceKind}:${row.path}`) ?? [];
                const isExpanded = expanded.has(row.id);
                return (
                  <Fragment key={row.id}>
                    <HierarchyTableRow
                      row={row}
                      metricColumns={selectedMetricDefinitions}
                      canExpand={children.length > 0}
                      expanded={isExpanded}
                      onToggle={() => toggleExpanded(row.id)}
                    />
                    {isExpanded
                      ? children.map((child) => <HierarchyTableRow key={child.id} row={child} metricColumns={selectedMetricDefinitions} child />)
                      : null}
                  </Fragment>
                );
              })
            )}
          </TableBody>
        </Table>
        <div className="border-t bg-secondary/20 px-4 py-2 text-xs text-muted-foreground">
          {visibleTopRows.length} of {rows.filter((row) => row.level !== "subquestion").length} top-level rows shown.
        </div>
      </CardContent>
    </Card>
  );
}

function HierarchyTableRow({
  row,
  metricColumns,
  child = false,
  canExpand = false,
  expanded = false,
  onToggle,
}: {
  row: HierarchyMetricRow;
  metricColumns: MetricColumnDefinition[];
  child?: boolean;
  canExpand?: boolean;
  expanded?: boolean;
  onToggle?: () => void;
}) {
  return (
    <TableRow className={child ? "bg-secondary/15" : undefined}>
      <TableCell className="text-center">
        {canExpand ? (
          <button
            type="button"
            onClick={onToggle}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md hover:bg-secondary"
            title={expanded ? "Collapse sub-questions" : "Expand sub-questions"}
            aria-label={expanded ? "Collapse sub-questions" : "Expand sub-questions"}
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        ) : null}
      </TableCell>
      <TableCell className={cn("font-mono text-xs", child && "pl-8 text-muted-foreground")}>{row.path}</TableCell>
      <TableCell>
        <Badge variant={row.level === "form" ? "secondary" : row.level === "question" ? "outline" : "warning"}>
          {row.level}
        </Badge>
      </TableCell>
      <TableCell>
        <Badge variant={row.referenceKind === "R2" ? "success" : "outline"}>{row.referenceKind}</Badge>
      </TableCell>
      <TableCell className="min-w-[140px]">
        <div className="h-2 overflow-hidden rounded-full bg-secondary">
          <div
            className={cn("h-full rounded-full", row.agreement >= 0.8 ? "bg-emerald-500" : row.agreement >= 0.5 ? "bg-amber-500" : "bg-rose-500")}
            style={{ width: `${Math.round(row.agreement * 100)}%` }}
          />
        </div>
        <div className="mt-1 text-xs font-medium tabular-nums">{agreementPercent(row.agreement)}</div>
      </TableCell>
      <TableCell className="tabular-nums">{row.matches}/{row.total}</TableCell>
      <TableCell className="tabular-nums">{scorePercent(row.averageScore)}</TableCell>
      {metricColumns.map((definition) => (
        <TableCell key={definition.key} className="tabular-nums">
          {formatMetricValue(row, definition)}
        </TableCell>
      ))}
      <TableCell className="max-w-[460px]">
        <div className="truncate text-sm">{row.label}</div>
      </TableCell>
    </TableRow>
  );
}

function PairResultsTable({
  run,
  items,
  onViewPair,
}: {
  run: EvalRunRecord | null;
  items: EvalRunItemRecord[];
  onViewPair: (pair: PairResultRow) => void;
}) {
  const [search, setSearch] = useState("");
  const [referenceFilter, setReferenceFilter] = useState("primary");
  const [agreementFilter, setAgreementFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);

  const rows = useMemo(() => buildPairRows(items), [items]);
  const primaryRef = primaryReferenceKind(run, rows);
  const visibleRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    return rows.filter((row) => {
      if (referenceFilter === "primary" && row.referenceKind !== primaryRef) return false;
      if (referenceFilter !== "primary" && referenceFilter !== "all" && row.referenceKind !== referenceFilter) return false;
      if (agreementFilter === "matched" && !row.outcomeMatch) return false;
      if (agreementFilter === "mismatched" && row.outcomeMatch) return false;
      if (!query) return true;
      return [
        row.claimNumber,
        row.referenceKind,
        row.status,
        row.generatedOutcome,
        row.referenceOutcome,
        row.item.error_message ?? "",
      ]
        .join(" ")
        .toLowerCase()
        .includes(query);
    });
  }, [agreementFilter, primaryRef, referenceFilter, rows, search]);
  const totalPages = Math.max(1, Math.ceil(visibleRows.length / pageSize));
  const paginatedRows = useMemo(
    () => visibleRows.slice((Math.min(page, totalPages) - 1) * pageSize, Math.min(page, totalPages) * pageSize),
    [page, pageSize, totalPages, visibleRows],
  );

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Audit Pair Results</CardTitle>
          {run ? <Badge variant="outline">{run.name} {visibleVersion(run)}</Badge> : null}
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="flex flex-wrap items-center gap-3 border-b bg-secondary/40 px-4 py-3">
          <div className="relative min-w-[240px] flex-1 sm:max-w-sm">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="h-8 pl-9 text-xs"
              placeholder="Search claim, outcome, reference..."
            />
          </div>
          <SelectFilter value={referenceFilter} onChange={setReferenceFilter} label="Reference">
            <option value="primary">Primary ref</option>
            <option value="all">All refs</option>
            <option value="R1">R1</option>
            <option value="R2">R2</option>
          </SelectFilter>
          <SelectFilter value={agreementFilter} onChange={setAgreementFilter} label="Agreement">
            <option value="all">All outcomes</option>
            <option value="matched">Outcome matched</option>
            <option value="mismatched">Outcome mismatch</option>
          </SelectFilter>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setSearch("");
              setReferenceFilter("primary");
              setAgreementFilter("all");
            }}
          >
            <X className="h-3.5 w-3.5" />
            Clear
          </Button>
        </div>
        <Table>
          <TableHeader>
            <TableRow className="bg-secondary/60">
              <TableHead className="w-12">View</TableHead>
              <TableHead>Claim</TableHead>
              <TableHead>Reference</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Score</TableHead>
              <TableHead>Outcome</TableHead>
              <TableHead>Question Agree</TableHead>
              <TableHead>Sub-question F1</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!run || visibleRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                  No audit pair results match the current filters.
                </TableCell>
              </TableRow>
            ) : (
              paginatedRows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => onViewPair(row)}
                      title="View side-by-side forms"
                      aria-label="View side-by-side forms"
                    >
                      <Eye className="h-4 w-4" />
                    </Button>
                  </TableCell>
                  <TableCell className="font-medium">{row.claimNumber}</TableCell>
                  <TableCell>
                    <Badge variant={row.referenceKind === "R2" ? "success" : "outline"}>{row.referenceKind}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={row.status === "completed" ? "success" : row.status === "failed" ? "danger" : "secondary"}>{row.status}</Badge>
                  </TableCell>
                  <TableCell className="tabular-nums">{scorePercent(row.score)}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge variant={row.outcomeMatch ? "success" : "danger"}>{row.outcomeMatch ? "Match" : "Mismatch"}</Badge>
                      <span className="text-xs text-muted-foreground">{row.generatedOutcome || "-"} vs {row.referenceOutcome || "-"}</span>
                    </div>
                  </TableCell>
                  <TableCell className="tabular-nums">{row.questionAgreement === null ? "-" : agreementPercent(row.questionAgreement)}</TableCell>
                  <TableCell className="tabular-nums">
                    {row.subquestionF1 === null ? "-" : agreementPercent(row.subquestionF1)}
                  </TableCell>
                </TableRow>
              ))
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

function EvalResultsVisualization({ run, items }: { run: EvalRunRecord | null; items: EvalRunItemRecord[] }) {
  const [mode, setMode] = useState<VisualizationMode>("results");
  const [referenceView, setReferenceView] = useState<ReferenceView>("R2");
  const initializedReferenceRunIdRef = useRef("");
  const availableKinds = useMemo(() => availableReferenceKinds(items), [items]);
  const effectiveReferenceView = useMemo(() => {
    if (referenceView === "both" && availableKinds.length > 1) return referenceView;
    if (referenceView !== "both" && availableKinds.includes(referenceView)) return referenceView;
    return preferredReferenceView(run, availableKinds);
  }, [availableKinds, referenceView, run]);
  const sections = useMemo(
    () =>
      mode === "results"
        ? buildResultSections(items, effectiveReferenceView)
        : buildAgreementSections(items, effectiveReferenceView),
    [effectiveReferenceView, items, mode],
  );
  const rowCount = sections.reduce((sum, section) => sum + section.rows.length, 0);
  const canShowBoth = availableKinds.length > 1 && availableKinds.includes("R2");

  useEffect(() => {
    if (!run || availableKinds.length === 0) return;
    setReferenceView((current) => {
      if (initializedReferenceRunIdRef.current !== run.id) {
        initializedReferenceRunIdRef.current = run.id;
        return preferredReferenceView(run, availableKinds);
      }
      if (current === "both" && canShowBoth) return current;
      if (current !== "both" && availableKinds.includes(current)) return current;
      return preferredReferenceView(run, availableKinds);
    });
  }, [availableKinds, canShowBoth, run]);

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <BarChart3 className="h-4 w-4 text-primary" />
            <CardTitle>Evaluation Comparison</CardTitle>
          </div>
          {run ? <Badge variant="outline">{run.name} {visibleVersion(run)}</Badge> : null}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-md border bg-background p-0.5">
              <button
                type="button"
                onClick={() => setMode("results")}
                className={cn(
                  "inline-flex h-7 items-center rounded px-2 text-xs font-medium",
                  mode === "results" ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                Results
              </button>
              <button
                type="button"
                onClick={() => setMode("agreement")}
                className={cn(
                  "inline-flex h-7 items-center rounded px-2 text-xs font-medium",
                  mode === "agreement" ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                Agreement
              </button>
            </div>
            {canShowBoth ? (
              <div className="inline-flex rounded-md border bg-background p-0.5">
                {(["R1", "R2", "both"] as ReferenceView[]).map((referenceOption) => (
                  <button
                    key={referenceOption}
                    type="button"
                    onClick={() => setReferenceView(referenceOption)}
                    className={cn(
                      "inline-flex h-7 items-center rounded px-2 text-xs font-medium",
                      effectiveReferenceView === referenceOption
                        ? "bg-secondary text-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {referenceOption === "both" ? "Both" : referenceOption}
                  </button>
                ))}
              </div>
            ) : availableKinds[0] ? (
              <Badge variant="outline">{availableKinds[0]} ground truth</Badge>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {!run || rowCount === 0 ? (
          <div className="p-6">
            <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
              Completed evaluation results will appear here once a run has comparisons.
            </p>
          </div>
        ) : (
          <div className="divide-y">
            {sections.map((section) => (
              <HorizontalComparisonSection key={section.id} section={section} mode={mode} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function HorizontalComparisonSection({
  section,
  mode,
}: {
  section: EvalVisualizationSection;
  mode: VisualizationMode;
}) {
  const maxValue = mode === "agreement" ? 100 : Math.max(1, ...section.rows.flatMap((row) => row.bars.map((bar) => bar.value)));

  return (
    <section className="px-4 py-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{section.title}</h3>
        <span className="text-xs text-muted-foreground">{section.rows.length} rows</span>
      </div>
      {section.rows.length === 0 ? (
        <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">No data in this level for the current selection.</p>
      ) : (
        <div className="space-y-3">
          {section.rows.map((row) => (
            <div key={row.id} className="grid gap-2 lg:grid-cols-[minmax(220px,360px)_1fr]">
              <div className="min-w-0">
                <p className="break-words text-sm font-medium leading-snug">{row.label}</p>
                <p className="mt-0.5 break-words text-[11px] text-muted-foreground">{row.context}</p>
              </div>
              <div className="space-y-1.5">
                {row.bars.map((bar) => {
                  const width = Math.max(1, (bar.value / maxValue) * 100);
                  return (
                    <div key={bar.key} className="grid grid-cols-[112px_1fr_92px] items-center gap-2">
                      <span className="truncate text-xs text-muted-foreground" title={bar.label}>
                        {bar.label}
                      </span>
                      <div className="h-3 overflow-hidden rounded-full bg-secondary">
                        <div className="h-full rounded-full" style={{ width: `${width}%`, backgroundColor: bar.color }} />
                      </div>
                      <span className="text-right text-xs font-medium tabular-nums">{bar.displayValue}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function PairComparisonDialog({ pair, onClose }: { pair: PairResultRow | null; onClose: () => void }) {
  const [referenceKind, setReferenceKind] = useState<EvalReferenceKind>("R2");
  const open = Boolean(pair);
  useBodyScrollLock(open);

  useEffect(() => {
    if (pair) setReferenceKind(pair.referenceKind);
  }, [pair]);

  if (!pair) return null;

  const truthOptions = pair.item.ground_truths.map((truth) => truth.reference_kind);
  const activeTruth = pair.item.ground_truths.find((truth) => truth.reference_kind === referenceKind) ?? pair.referenceTruth;
  const activeComparison = comparisonFor(pair.item, activeTruth.reference_kind) ?? pair.comparison;
  const questionAgreement = metricNumber(activeComparison.metrics, "question_agreement");
  const subquestionF1 = metricNumberFallback(activeComparison.metrics, ["subquestion_f1", "driver_f1"]);
  const outcomeMatch = metricBool(activeComparison.metrics, "outcome_match");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 p-4 backdrop-blur-sm">
      <div className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-lg border bg-card shadow-2xl">
        <div className="flex flex-wrap items-start gap-4 border-b bg-secondary/35 px-6 py-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold">Audit Pair</h2>
              <Badge variant="outline">{pair.claimNumber}</Badge>
              <Badge variant={outcomeMatch ? "success" : "danger"}>{outcomeMatch ? "Outcome match" : "Outcome mismatch"}</Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">Model output compared with selected ground truth.</p>
          </div>
          {truthOptions.length > 1 ? (
            <div className="ml-auto flex rounded-md border bg-background p-1">
              {truthOptions.map((kind) => (
                <button
                  key={kind}
                  type="button"
                  onClick={() => setReferenceKind(kind)}
                  className={cn(
                    "rounded px-3 py-1.5 text-xs font-medium",
                    referenceKind === kind ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {kind}
                </button>
              ))}
            </div>
          ) : null}
          <Button type="button" variant="ghost" size="icon" className="h-9 w-9" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="chat-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto p-6">
          <div className="grid gap-3 md:grid-cols-4">
            <MiniMetric label="Score" value={scorePercent(activeComparison.score)} helper={`Ground truth ${activeTruth.reference_kind}`} />
            <MiniMetric label="Question Agree" value={questionAgreement === null ? "-" : agreementPercent(questionAgreement)} helper="Yes/No answers" />
            <MiniMetric
              label="Sub-question F1"
              value={subquestionF1 === null ? "-" : agreementPercent(subquestionF1)}
              helper="applicable sub-questions"
            />
            <MiniMetric label="Attempts" value={String(pair.item.attempt_count)} helper={formatDate(pair.item.completed_at) || pair.item.status} />
          </div>

          <div className="grid gap-3 xl:grid-cols-2">
            <OutcomeCommentPanel
              title="Model Outcome Comment"
              outcome={pair.item.generated_result?.overall_outcome ?? ""}
              comment={pair.item.generated_result?.outcome_justification ?? ""}
            />
            <OutcomeCommentPanel
              title={`Ground Truth ${activeTruth.reference_kind} Outcome Comment`}
              outcome={activeTruth.result.overall_outcome}
              comment={activeTruth.result.outcome_justification}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <ReadOnlyFormPanel title="Model Generated" form={pair.item.generated_result ?? null} />
            <ReadOnlyFormPanel title={`Ground Truth ${activeTruth.reference_kind}`} form={activeTruth.result} />
          </div>
        </div>
      </div>
    </div>
  );
}

function OutcomeCommentPanel({
  title,
  outcome,
  comment,
}: {
  title: string;
  outcome: string;
  comment: string;
}) {
  return (
    <div className="rounded-lg border bg-background p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold">{title}</p>
        {outcome ? <Badge variant={outcome === "Meets" ? "success" : "danger"}>{outcome}</Badge> : null}
      </div>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
        {comment || "No outcome comment available."}
      </p>
    </div>
  );
}

function ReadOnlyFormPanel({ title, form }: { title: string; form: AuditFormResult | null }) {
  if (!form) {
    return (
      <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
        {title} is not available yet.
      </div>
    );
  }
  return (
    <div className="max-h-[560px] overflow-hidden rounded-lg border bg-background">
      <div className="border-b bg-secondary/35 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold">{title}</p>
          <Badge variant={form.overall_outcome === "Meets" ? "success" : "danger"}>{form.overall_outcome}</Badge>
        </div>
        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{form.outcome_justification}</p>
      </div>
      <div className="chat-scrollbar max-h-[470px] space-y-3 overflow-y-auto p-4">
        {form.questions.map((question) => (
          <ReadOnlyQuestion key={question.id} question={question} />
        ))}
      </div>
    </div>
  );
}

function ReadOnlyQuestion({ question }: { question: FormQuestion }) {
  const subQuestions = question.sub_questions ?? [];
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs font-semibold text-primary">{question.id}</p>
          <p className="mt-1 text-sm">{question.text}</p>
        </div>
        <Badge variant={question.answer === "Yes" ? "success" : "danger"}>{question.answer}</Badge>
      </div>
      {subQuestions.length ? (
        <div className="mt-3 space-y-2">
          {subQuestions.map((subQuestion) => (
            <div key={subQuestion.id} className="rounded-md border bg-background px-3 py-2">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] font-semibold text-muted-foreground">{subQuestion.id}</span>
                <Badge variant={subQuestion.answer ? "warning" : "outline"}>
                  {subQuestion.answer ? "applies" : "not applicable"}
                </Badge>
              </div>
              <p className="mt-1 text-sm">{subQuestion.text}</p>
              {subQuestion.reasoning ? <p className="mt-1 text-xs text-muted-foreground">{subQuestion.reasoning}</p> : null}
            </div>
          ))}
        </div>
      ) : question.comments || question.citations ? (
        <div className="mt-3 rounded-md border bg-background px-3 py-2 text-xs text-muted-foreground">
          {question.comments ? <p>{question.comments}</p> : null}
          {question.citations ? <p className="mt-1">{question.citations}</p> : null}
        </div>
      ) : null}
    </div>
  );
}

function SelectFilter({
  value,
  onChange,
  label,
  children,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
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

function EvalRunDialog({
  open,
  datasets,
  editingRun,
  saving,
  onClose,
  onSave,
}: {
  open: boolean;
  datasets: EvalDatasetRecord[];
  editingRun: EvalRunRecord | null;
  saving: boolean;
  onClose: () => void;
  onSave: (payload: EvalRunPayload) => Promise<void> | void;
}) {
  const [state, setState] = useState<EvalRunDialogState>(() => initialDialogState(datasets, editingRun));
  const [formError, setFormError] = useState("");
  const isEditing = Boolean(editingRun);
  useBodyScrollLock(open);

  useEffect(() => {
    if (!open) return;
    setState(initialDialogState(datasets, editingRun));
    setFormError("");
  }, [datasets, editingRun, open]);

  if (!open) return null;

  const selectedDataset = datasets.find((dataset) => dataset.id === state.dataset_id);
  const nextVersion = isEditing ? (editingRun?.config_version ?? 1) + 1 : 1;

  const save = async () => {
    if (!state.dataset_id) {
      setFormError("Select a dataset first.");
      return;
    }
    if (!state.name.trim()) {
      setFormError("Run name is required.");
      return;
    }
    setFormError("");
    await onSave({
      dataset_id: state.dataset_id,
      name: state.name.trim(),
      model_name: state.model_name.trim(),
      reference_policy: state.reference_policy,
      retry_limit: state.retry_limit,
      enable_mlflow: state.enable_mlflow,
      prompt_ref: null,
      base_run_id: editingRun?.id ?? null,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 p-4 backdrop-blur-sm">
      <div className="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border bg-card shadow-2xl">
        <div className="flex items-start gap-4 border-b bg-secondary/35 px-6 py-5">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border bg-background text-primary">
            <FlaskConical className="h-6 w-6" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold">{isEditing ? "Version Eval Run" : "Create Eval Run"}</h2>
              {isEditing ? <Badge variant="outline">v{nextVersion}</Badge> : null}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {isEditing ? "Editing creates a new immutable run version in the queue." : "Configure a ground-truth eval run for the queue."}
            </p>
          </div>
          <Button type="button" variant="ghost" size="icon" className="ml-auto h-9 w-9" onClick={onClose} disabled={saving}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="chat-scrollbar min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-6">
          <div className="grid gap-4 md:grid-cols-[1fr_180px]">
            <label className="grid gap-2">
              <span className="text-sm font-medium">Run Name</span>
              <Input value={state.name} onChange={(event) => setState((current) => ({ ...current, name: event.target.value }))} disabled={saving} />
            </label>
            <label className="grid gap-2">
              <span className="text-sm font-medium">Reference Policy</span>
              <select
                value={state.reference_policy}
                onChange={(event) => setState((current) => ({ ...current, reference_policy: event.target.value as EvalReferencePolicy }))}
                disabled={saving}
                className="h-10 rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="prefer_r2">Prefer R2</option>
                <option value="r2">R2 only</option>
                <option value="r1">R1 only</option>
                <option value="all">All refs</option>
              </select>
            </label>
          </div>

          <label className="grid gap-2">
            <span className="text-sm font-medium">Dataset</span>
            <select
              value={state.dataset_id}
              onChange={(event) => setState((current) => ({ ...current, dataset_id: event.target.value }))}
              disabled={saving}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {datasets.length === 0 ? <option value="">No datasets</option> : null}
              {datasets.map((dataset) => (
                <option key={dataset.id} value={dataset.id}>
                  {dataset.name}
                </option>
              ))}
            </select>
          </label>

          {selectedDataset ? (
            <div className="rounded-lg border bg-background p-4">
              <div className="flex flex-wrap gap-1.5">
                <Badge variant="outline">{selectedDataset.form_id}@{selectedDataset.form_version}</Badge>
                <Badge variant="secondary">{selectedDataset.case_count} cases</Badge>
                <Badge variant="secondary">R1 {selectedDataset.r1_count}</Badge>
                <Badge variant="secondary">R2 {selectedDataset.r2_count}</Badge>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">{selectedDataset.description || selectedDataset.source_kind}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Eval runs use the active prompt configured on this form version.
              </p>
            </div>
          ) : null}

          <div className="grid gap-4">
            <label className="grid gap-2">
              <span className="text-sm font-medium">Model</span>
              <Input
                value={state.model_name}
                onChange={(event) => setState((current) => ({ ...current, model_name: event.target.value }))}
                disabled={saving}
                placeholder="Backend default"
              />
            </label>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex items-center gap-2 rounded-md border bg-background px-3 py-2 text-sm">
              <input
                type="checkbox"
                checked={state.enable_mlflow}
                onChange={(event) => setState((current) => ({ ...current, enable_mlflow: event.target.checked }))}
                disabled={saving}
                className="h-4 w-4"
              />
              MLflow logging
            </label>
          </div>

          {formError ? <p className="text-sm text-destructive">{formError}</p> : null}
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t bg-secondary/35 px-6 py-5">
          <div className="text-xs text-muted-foreground">
            {isEditing ? `Previous ${visibleVersion(editingRun as EvalRunRecord)} remains unchanged.` : "Run is added to the queue."}
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
            <Button type="button" className="min-w-36 gap-2" onClick={() => void save()} disabled={saving}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
              {isEditing ? `Add v${nextVersion}` : "Add to Queue"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
