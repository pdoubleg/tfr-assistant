"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  Position,
  Handle,
} from "@xyflow/react";
import dagre from "dagre";
import { motion } from "motion/react";
import {
  CheckCircle2,
  CircleDot,
  Database,
  GitBranch,
  GitCompareArrows,
  Loader2,
  Network,
  Play,
  RefreshCw,
  Search,
  Sparkles,
  Square,
  Trophy,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  cancelOptimizationRun,
  createOptimizationDemoFixture,
  createOptimizationRun,
  getFormDefinition,
  getOptimizationDagArtifact,
  getOptimizationRun,
  listFormCatalog,
  listOptimizationCases,
  listOptimizationRuns,
  optimizationArtifactUrl,
  optimizationEventsUrl,
} from "@/lib/api";
import type {
  FormCatalogEntry,
  OptimizationCaseRecord,
  OptimizationCaseSplit,
  OptimizationDagArtifact,
  OptimizationEventRecord,
  OptimizationRunPayload,
  OptimizationRunRecord,
  OptimizationSplit,
} from "@/lib/types";

const pollMs = 3500;
const nodeWidth = 284;
const nodeHeight = 168;
const maxVisibleIterationNodes = 10;
type GepaParamsState = OptimizationRunPayload["gepa_params"];
type BudgetMode = "metric_calls" | "full_evals" | "auto";
type MonitorView = "graph" | "native";

const defaultGepaParams: GepaParamsState = {
  auto: null,
  max_full_evals: null,
  max_metric_calls: 24,
  reflection_model: "",
  reflection_minibatch_size: 3,
  perfect_score: 1,
  skip_perfect_score: true,
  candidate_selection_strategy: "pareto",
  frontier_type: "instance",
  batch_sampler: "epoch_shuffled",
  module_selector: "all",
  use_merge: false,
  max_merge_invocations: 5,
  merge_val_overlap_floor: 5,
  cache_evaluation: false,
  track_best_outputs: false,
  display_progress_bar: false,
  raise_on_exception: false,
  val_evaluation_policy: null,
  use_mlflow: false,
  mlflow_tracking_uri: "",
  mlflow_experiment_name: "",
  seed: 0,
};

const defaultTraceConfig = {
  capture_traces: true,
  max_tool_return_chars: 2000,
  include_debug_traces: true,
  include_thinking: true,
};

function statusVariant(status?: string): "secondary" | "outline" | "success" | "danger" | "warning" {
  if (status === "completed") return "success";
  if (status === "failed" || status === "canceled") return "danger";
  if (status === "running" || status === "queued") return "warning";
  return "secondary";
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatScore(value?: number | null): string {
  return typeof value === "number" ? value.toFixed(4) : "-";
}

function getBudgetMode(params: GepaParamsState): BudgetMode {
  if (params.max_full_evals !== null && params.max_full_evals !== undefined) return "full_evals";
  if (params.auto) return "auto";
  return "metric_calls";
}

function setBudgetMode(params: GepaParamsState, mode: BudgetMode): GepaParamsState {
  if (mode === "full_evals") {
    return { ...params, auto: null, max_full_evals: params.max_full_evals ?? 4, max_metric_calls: null };
  }
  if (mode === "auto") {
    return { ...params, auto: params.auto ?? "light", max_full_evals: null, max_metric_calls: null };
  }
  return { ...params, auto: null, max_full_evals: null, max_metric_calls: params.max_metric_calls ?? 24 };
}

function splitCounts(splits: OptimizationCaseSplit[]) {
  return splits.reduce(
    (acc, item) => {
      acc[item.split] += 1;
      return acc;
    },
    { train: 0, val: 0, test: 0 },
  );
}

function autoSplit(
  cases: OptimizationCaseRecord[],
  selectedIds: Set<string>,
  mode: "random" | "outcome" | "outcome_issues",
  seed: number,
): OptimizationCaseSplit[] {
  const seeded = mulberry32(seed);
  const selected = cases.filter((item) => selectedIds.has(item.case_id));
  let ordered: OptimizationCaseRecord[] = [];
  if (mode === "random") {
    ordered = shuffle(selected, seeded);
  } else {
    const groups = new Map<string, OptimizationCaseRecord[]>();
    selected.forEach((item) => {
      const issueBucket = item.issue_count > 1 ? "multi" : String(item.issue_count);
      const key = mode === "outcome" ? item.outcome : `${item.outcome}:${issueBucket}`;
      groups.set(key, [...(groups.get(key) ?? []), item]);
    });
    const shuffledGroups = [...groups.entries()]
      .sort(([first], [second]) => first.localeCompare(second))
      .map(([key, values]) => [key, shuffle(values, seeded)] as const);
    while (shuffledGroups.some(([, values]) => values.length > 0)) {
      shuffledGroups.forEach(([, values]) => {
        const next = values.pop();
        if (next) ordered.push(next);
      });
    }
  }
  const trainCut = Math.max(1, Math.round(ordered.length * 0.6));
  const valCut = Math.min(ordered.length, trainCut + Math.max(1, Math.round(ordered.length * 0.2)));
  return ordered.map((item, index) => ({
    case_id: item.case_id,
    split: index < trainCut ? "train" : index < valCut ? "val" : "test",
  }));
}

function mulberry32(seed: number) {
  return () => {
    let value = (seed += 0x6d2b79f5);
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffle<T>(items: T[], random: () => number): T[] {
  const output = [...items];
  for (let index = output.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(random() * (index + 1));
    [output[index], output[swapIndex]] = [output[swapIndex], output[index]];
  }
  return output;
}

type CandidateNodeData = {
  label: string;
  title: string;
  score?: number | null;
  role: string;
  status: string;
  message?: string;
  iteration?: number | null;
  candidateIndex?: number | null;
  newCandidateIndex?: number | null;
  parentIds?: Array<number | null>;
  minibatchSize?: number | null;
  validationSize?: number | null;
  progress?: RunProgress | null;
  candidate?: Record<string, string>;
  proposedInstructions?: Record<string, string>;
  event?: OptimizationEventRecord;
  events?: OptimizationEventRecord[];
};

type RunProgress = {
  used: number;
  total: number | null;
  remaining: number | null;
  percent: number | null;
};

function CandidateNode({ data }: NodeProps<Node<CandidateNodeData>>) {
  const isBest = data.role === "best";
  const isPareto = data.role === "pareto";
  const isSeed = data.role === "seed";
  const isRejected = data.role === "rejected" || data.role === "errored";
  const isAccepted = data.role === "accepted" || isBest || isPareto;
  const accentClass = isBest
    ? "border-amber-400 bg-amber-50 text-amber-950 dark:bg-amber-950/25 dark:text-amber-50"
    : isAccepted
      ? "border-emerald-500/70 bg-emerald-50 text-emerald-950 dark:bg-emerald-950/25 dark:text-emerald-50"
      : isRejected
        ? "border-rose-500/70 bg-rose-50 text-rose-950 dark:bg-rose-950/25 dark:text-rose-50"
        : isSeed
          ? "border-slate-400/60 bg-slate-50 text-slate-950 dark:bg-slate-900/50 dark:text-slate-50"
          : "border-primary/45 bg-card text-card-foreground";
  const progressText = data.progress
    ? `${data.progress.used}${data.progress.total ? ` / ${data.progress.total}` : ""}`
    : null;
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      className={[
        "min-h-[150px] w-[268px] rounded-lg border p-3 shadow-sm ring-1 ring-background/60",
        accentClass,
      ].join(" ")}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !bg-primary" />
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {isBest ? (
            <Trophy className="h-4 w-4 shrink-0 text-amber-600" />
          ) : isRejected ? (
            <XCircle className="h-4 w-4 shrink-0 text-rose-600" />
          ) : isAccepted ? (
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
          ) : (
            <CircleDot className="h-4 w-4 shrink-0 text-primary" />
          )}
          <p className="truncate text-sm font-semibold">{data.title}</p>
        </div>
        <Badge variant={isBest ? "warning" : isAccepted ? "success" : isRejected ? "danger" : "outline"} className="shrink-0 text-[10px]">
          {data.status}
        </Badge>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <div>
          <p className="text-[10px] uppercase opacity-65">score</p>
          <p className="font-mono font-semibold">{formatScore(data.score)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase opacity-65">candidate</p>
          <p className="font-mono font-semibold">
            {data.newCandidateIndex ?? data.candidateIndex ?? "-"}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase opacity-65">budget</p>
          <p className="font-mono font-semibold">{progressText ?? "-"}</p>
        </div>
      </div>
      <p className="mt-3 line-clamp-2 min-h-[32px] text-xs leading-relaxed opacity-80">
        {data.message ?? data.candidate?.instructions ?? data.event?.message ?? "Waiting for GEPA callback data."}
      </p>
      <div className="mt-3 flex items-center justify-between gap-2 text-[10px] uppercase opacity-65">
        <span>{data.label}</span>
        <span>{data.minibatchSize ? `${data.minibatchSize} train` : data.validationSize ? `${data.validationSize} val` : ""}</span>
      </div>
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !bg-primary" />
    </motion.div>
  );
}

const nodeTypes = { candidate: CandidateNode };

export default function OptimizationPage() {
  const [forms, setForms] = useState<FormCatalogEntry[]>([]);
  const [runs, setRuns] = useState<OptimizationRunRecord[]>([]);
  const [cases, setCases] = useState<OptimizationCaseRecord[]>([]);
  const [selectedRun, setSelectedRun] = useState<OptimizationRunRecord | null>(null);
  const [dagArtifact, setDagArtifact] = useState<OptimizationDagArtifact | null>(null);
  const [events, setEvents] = useState<OptimizationEventRecord[]>([]);
  const [selectedCaseIds, setSelectedCaseIds] = useState<Set<string>>(() => new Set());
  const [caseSplits, setCaseSplits] = useState<OptimizationCaseSplit[]>([]);
  const [selectedNode, setSelectedNode] = useState<CandidateNodeData | null>(null);
  const [formKey, setFormKey] = useState("tfr_default@v0.1");
  const [search, setSearch] = useState("");
  const [runName, setRunName] = useState("GEPA Prompt Optimization");
  const [seedSource, setSeedSource] = useState<"form" | "manual">("form");
  const [manualInstructions, setManualInstructions] = useState("");
  const [metricMode, setMetricMode] = useState<"comparison" | "comparison_with_judge">("comparison");
  const [scoreKey, setScoreKey] = useState<OptimizationRunPayload["score_key"]>("score");
  const [referencePolicy, setReferencePolicy] = useState<OptimizationRunPayload["reference_policy"]>("prefer_r2");
  const [judgeModel, setJudgeModel] = useState("");
  const [gepaParams, setGepaParams] = useState<GepaParamsState>(defaultGepaParams);
  const [traceConfig, setTraceConfig] = useState(defaultTraceConfig);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [refreshingCases, setRefreshingCases] = useState(false);
  const [error, setError] = useState("");

  const [formId, formVersion] = formKey.split("@");
  const counts = splitCounts(caseSplits);
  const selectedCases = useMemo(
    () => cases.filter((item) => selectedCaseIds.has(item.case_id)),
    [cases, selectedCaseIds],
  );
  const activeRun = selectedRun && ["queued", "running"].includes(selectedRun.status) ? selectedRun : null;

  const refreshRuns = useCallback(async () => {
    const nextRuns = await listOptimizationRuns();
    setRuns(nextRuns);
    setSelectedRun((current) => {
      if (!current) return nextRuns[0] ?? null;
      return nextRuns.find((run) => run.id === current.id) ?? current;
    });
  }, []);

  const refreshCases = useCallback(async () => {
    if (!formId || !formVersion) return;
    setRefreshingCases(true);
    try {
      const nextCases = await listOptimizationCases(formId, formVersion, search, true);
      setCases(nextCases);
      setSelectedCaseIds((current) => {
        const valid = new Set(nextCases.map((item) => item.case_id));
        return new Set([...current].filter((id) => valid.has(id)));
      });
      setCaseSplits((current) => current.filter((item) => nextCases.some((candidate) => candidate.case_id === item.case_id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load optimization cases.");
    } finally {
      setRefreshingCases(false);
    }
  }, [formId, formVersion, search]);

  useEffect(() => {
    let canceled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const [nextForms, nextRuns] = await Promise.all([listFormCatalog(), listOptimizationRuns()]);
        if (canceled) return;
        setForms(nextForms);
        if (nextForms.length) setFormKey(`${nextForms[0].id}@${nextForms[0].version}`);
        setRuns(nextRuns);
        setSelectedRun(nextRuns[0] ?? null);
      } catch (err) {
        if (!canceled) setError(err instanceof Error ? err.message : "Failed to load optimization workspace.");
      } finally {
        if (!canceled) setLoading(false);
      }
    }
    void load();
    return () => {
      canceled = true;
    };
  }, []);

  useEffect(() => {
    void refreshCases();
  }, [refreshCases]);

  useEffect(() => {
    if (!activeRun) return;
    const interval = window.setInterval(() => {
      void getOptimizationRun(activeRun.id).then(setSelectedRun).catch(() => undefined);
      void refreshRuns().catch(() => undefined);
    }, pollMs);
    return () => window.clearInterval(interval);
  }, [activeRun, refreshRuns]);

  useEffect(() => {
    if (!selectedRun) {
      setEvents([]);
      setDagArtifact(null);
      return;
    }
    setEvents(selectedRun.events ?? []);
    setSelectedNode(null);
    if (selectedRun.status === "completed" || selectedRun.status === "canceled" || selectedRun.status === "failed") {
      void getOptimizationDagArtifact(selectedRun.id)
        .then(setDagArtifact)
        .catch(() => setDagArtifact(null));
    } else {
      setDagArtifact(null);
    }
    const source = new EventSource(optimizationEventsUrl(selectedRun.id));
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as OptimizationEventRecord;
        setEvents((current) => {
          if (current.some((item) => item.id === event.id)) return current;
          return [...current, event].sort((first, second) => first.sequence - second.sequence);
        });
        if (["run_completed", "run_error"].includes(event.type)) {
          void getOptimizationRun(selectedRun.id).then(setSelectedRun).catch(() => undefined);
          void getOptimizationDagArtifact(selectedRun.id).then(setDagArtifact).catch(() => undefined);
        }
      } catch {
        // Ignore malformed heartbeat-style lines.
      }
    };
    return () => source.close();
  }, [selectedRun?.id, selectedRun?.status]);

  const graph = useMemo(() => buildGraph(dagArtifact, selectedRun, events), [dagArtifact, selectedRun, events]);

  const createDemo = async () => {
    setSaving(true);
    setError("");
    try {
      const fixture = await createOptimizationDemoFixture();
      const nextForms = await listFormCatalog();
      setForms(nextForms);
      setFormKey(`${fixture.form_id}@${fixture.form_version}`);
      await refreshCases();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create demo fixture.");
    } finally {
      setSaving(false);
    }
  };

  const selectAllCases = () => {
    const ids = new Set(cases.map((item) => item.case_id));
    setSelectedCaseIds(ids);
    setCaseSplits(autoSplit(cases, ids, "outcome_issues", gepaParams.seed));
  };

  const applyAutoSplit = (mode: "random" | "outcome" | "outcome_issues") => {
    setCaseSplits(autoSplit(cases, selectedCaseIds, mode, gepaParams.seed));
  };

  const setCaseSplit = (caseId: string, split: OptimizationSplit) => {
    setSelectedCaseIds((current) => new Set([...current, caseId]));
    setCaseSplits((current) => {
      const remaining = current.filter((item) => item.case_id !== caseId);
      return [...remaining, { case_id: caseId, split }];
    });
  };

  const toggleCase = (caseId: string) => {
    setSelectedCaseIds((current) => {
      const next = new Set(current);
      if (next.has(caseId)) {
        next.delete(caseId);
        setCaseSplits((splits) => splits.filter((item) => item.case_id !== caseId));
      } else {
        next.add(caseId);
        setCaseSplits((splits) => [...splits, { case_id: caseId, split: "train" }]);
      }
      return next;
    });
  };

  const launchRun = async () => {
    setSaving(true);
    setError("");
    try {
      const definition = await getFormDefinition(formId, formVersion);
      const payload: OptimizationRunPayload = {
        name: runName || `GEPA ${formKey}`,
        form_id: formId,
        form_version: formVersion,
        seed_instruction_source: seedSource,
        manual_instructions: seedSource === "manual" ? manualInstructions : "",
        metric_mode: metricMode,
        score_key: scoreKey,
        reference_policy: referencePolicy,
        judge_model: metricMode === "comparison_with_judge" ? judgeModel || null : null,
        gepa_params: {
          ...gepaParams,
          auto: gepaParams.auto ?? null,
          max_full_evals: gepaParams.max_full_evals ?? null,
          max_metric_calls: gepaParams.max_metric_calls ?? null,
          reflection_model: gepaParams.reflection_model || null,
          val_evaluation_policy: gepaParams.val_evaluation_policy || null,
          mlflow_tracking_uri: gepaParams.use_mlflow ? gepaParams.mlflow_tracking_uri || null : null,
          mlflow_experiment_name: gepaParams.use_mlflow ? gepaParams.mlflow_experiment_name || null : null,
        },
        trace_config: traceConfig,
        case_splits: caseSplits,
      };
      if (seedSource === "form" && !definition.instructions) {
        payload.manual_instructions = "";
      }
      const run = await createOptimizationRun(payload);
      setSelectedRun(run);
      await refreshRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to launch optimization run.");
    } finally {
      setSaving(false);
    }
  };

  const cancelRun = async () => {
    if (!selectedRun) return;
    setSaving(true);
    try {
      const run = await cancelOptimizationRun(selectedRun.id);
      setSelectedRun(run);
      await refreshRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel optimization run.");
    } finally {
      setSaving(false);
    }
  };

  const clearMonitor = () => {
    setSelectedRun(null);
    setDagArtifact(null);
    setEvents([]);
    setSelectedNode(null);
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto flex w-full max-w-[1800px] flex-col gap-4 p-4 lg:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Network className="h-6 w-6 text-primary" />
              <h1 className="text-2xl font-semibold">GEPA Optimization</h1>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Prompt optimization for registered audit form review agents.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" onClick={() => void createDemo()} disabled={saving}>
              <Database className="h-4 w-4" />
              Demo Fixture
            </Button>
            <Button type="button" variant="outline" onClick={() => void refreshRuns()} disabled={loading}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>

        {error ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        <div className="grid min-h-[760px] min-w-0 gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
          <aside className="min-w-0 space-y-4">
            <RunHistory runs={runs} selectedRun={selectedRun} onSelect={setSelectedRun} loading={loading} />
            <RunConfig
              forms={forms}
              formKey={formKey}
              setFormKey={setFormKey}
              runName={runName}
              setRunName={setRunName}
              seedSource={seedSource}
              setSeedSource={setSeedSource}
              manualInstructions={manualInstructions}
              setManualInstructions={setManualInstructions}
              metricMode={metricMode}
              setMetricMode={setMetricMode}
              scoreKey={scoreKey}
              setScoreKey={setScoreKey}
              referencePolicy={referencePolicy}
              setReferencePolicy={setReferencePolicy}
              judgeModel={judgeModel}
              setJudgeModel={setJudgeModel}
              gepaParams={gepaParams}
              setGepaParams={setGepaParams}
              traceConfig={traceConfig}
              setTraceConfig={setTraceConfig}
              counts={counts}
              saving={saving}
              canLaunch={counts.train > 0 && counts.val > 0 && (seedSource === "form" || Boolean(manualInstructions.trim()))}
              onLaunch={launchRun}
            />
          </aside>

          <main className="flex min-h-0 min-w-0 flex-col gap-4">
            <RunMonitor
              run={selectedRun}
              graph={graph}
              selectedNode={selectedNode}
              events={events}
              onNodeSelect={setSelectedNode}
              onCancel={cancelRun}
              onClear={clearMonitor}
              saving={saving}
            />
            <DatasetCuration
              cases={cases}
              selectedCaseIds={selectedCaseIds}
              caseSplits={caseSplits}
              search={search}
              setSearch={setSearch}
              refreshing={refreshingCases}
              onRefresh={() => void refreshCases()}
              onSelectAll={selectAllCases}
              onAutoSplit={applyAutoSplit}
              onToggleCase={toggleCase}
              onSetSplit={setCaseSplit}
            />
          </main>
        </div>
      </div>
    </div>
  );
}

function RunHistory({
  runs,
  selectedRun,
  onSelect,
  loading,
}: {
  runs: OptimizationRunRecord[];
  selectedRun: OptimizationRunRecord | null;
  onSelect: (run: OptimizationRunRecord) => void;
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader className="border-b py-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <GitBranch className="h-4 w-4 text-primary" />
          Runs
        </CardTitle>
      </CardHeader>
      <CardContent className="max-h-[300px] overflow-y-auto p-2">
        {loading ? (
          <LoadingState label="Loading runs" />
        ) : runs.length === 0 ? (
          <EmptyState label="No optimization runs yet." />
        ) : (
          <div className="space-y-2">
            {runs.map((run) => (
              <button
                key={run.id}
                type="button"
                onClick={() => onSelect(run)}
                className={[
                  "w-full rounded-lg border p-3 text-left transition hover:bg-secondary/50",
                  selectedRun?.id === run.id ? "border-primary bg-primary/5" : "bg-card",
                ].join(" ")}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium">{run.name}</p>
                  <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>{run.form_id}@{run.form_version}</span>
                  <span>best {formatScore(run.best_score)}</span>
                  <span>{formatDate(run.updated_at)}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RunConfig(props: {
  forms: FormCatalogEntry[];
  formKey: string;
  setFormKey: (value: string) => void;
  runName: string;
  setRunName: (value: string) => void;
  seedSource: "form" | "manual";
  setSeedSource: (value: "form" | "manual") => void;
  manualInstructions: string;
  setManualInstructions: (value: string) => void;
  metricMode: "comparison" | "comparison_with_judge";
  setMetricMode: (value: "comparison" | "comparison_with_judge") => void;
  scoreKey: OptimizationRunPayload["score_key"];
  setScoreKey: (value: OptimizationRunPayload["score_key"]) => void;
  referencePolicy: OptimizationRunPayload["reference_policy"];
  setReferencePolicy: (value: OptimizationRunPayload["reference_policy"]) => void;
  judgeModel: string;
  setJudgeModel: (value: string) => void;
  gepaParams: GepaParamsState;
  setGepaParams: (value: GepaParamsState) => void;
  traceConfig: typeof defaultTraceConfig;
  setTraceConfig: (value: typeof defaultTraceConfig) => void;
  counts: { train: number; val: number; test: number };
  saving: boolean;
  canLaunch: boolean;
  onLaunch: () => Promise<void>;
}) {
  const budgetMode = getBudgetMode(props.gepaParams);

  return (
    <Card>
      <CardHeader className="border-b py-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4 text-primary" />
          Configure
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <label className="block text-sm font-medium">
          Run Name
          <Input value={props.runName} onChange={(event) => props.setRunName(event.target.value)} className="mt-1" />
        </label>
        <label className="block text-sm font-medium">
          Form
          <select
            value={props.formKey}
            onChange={(event) => props.setFormKey(event.target.value)}
            className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {props.forms.map((form) => (
              <option key={`${form.id}@${form.version}`} value={`${form.id}@${form.version}`}>
                {form.id}@{form.version}
              </option>
            ))}
          </select>
        </label>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Button type="button" variant={props.seedSource === "form" ? "default" : "outline"} onClick={() => props.setSeedSource("form")}>
            Form Seed
          </Button>
          <Button type="button" variant={props.seedSource === "manual" ? "default" : "outline"} onClick={() => props.setSeedSource("manual")}>
            Manual Seed
          </Button>
        </div>
        {props.seedSource === "manual" ? (
          <Textarea
            value={props.manualInstructions}
            onChange={(event) => props.setManualInstructions(event.target.value)}
            className="min-h-32"
            placeholder="Initial audit-review instructions"
          />
        ) : null}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <label className="text-sm font-medium">
            Metric
            <select
              value={props.metricMode}
              onChange={(event) => props.setMetricMode(event.target.value as "comparison" | "comparison_with_judge")}
              className="mt-1 h-10 w-full rounded-md border bg-background px-2 text-sm"
            >
              <option value="comparison">Comparison</option>
              <option value="comparison_with_judge">With Judge</option>
            </select>
          </label>
          <label className="text-sm font-medium">
            Score
            <select
              value={props.scoreKey}
              onChange={(event) => props.setScoreKey(event.target.value as OptimizationRunPayload["score_key"])}
              className="mt-1 h-10 w-full rounded-md border bg-background px-2 text-sm"
            >
              <option value="score">Composite</option>
              <option value="question_agreement">Question Agreement</option>
              <option value="path_exact_rate">Path Exact</option>
              <option value="subquestion_f1">Driver F1</option>
              <option value="outcome_score">Outcome</option>
            </select>
          </label>
        </div>
        <label className="block text-sm font-medium">
          Reference Policy
          <select
            value={props.referencePolicy}
            onChange={(event) => props.setReferencePolicy(event.target.value as OptimizationRunPayload["reference_policy"])}
            className="mt-1 h-10 w-full rounded-md border bg-background px-2 text-sm"
          >
            <option value="prefer_r2">Prefer R2</option>
            <option value="r2">R2 Only</option>
            <option value="r1">R1 Only</option>
            <option value="all">All Average</option>
          </select>
        </label>
        {props.metricMode === "comparison_with_judge" ? (
          <Input value={props.judgeModel} onChange={(event) => props.setJudgeModel(event.target.value)} placeholder="Judge model, blank uses chat model" />
        ) : null}
        <div className="space-y-3 rounded-lg border bg-secondary/20 p-3">
          <div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">GEPA Budget</p>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {([
                ["metric_calls", "Calls"],
                ["full_evals", "Full Evals"],
                ["auto", "Auto"],
              ] as const).map(([mode, label]) => (
                <Button
                  key={mode}
                  type="button"
                  variant={budgetMode === mode ? "default" : "outline"}
                  size="sm"
                  onClick={() => props.setGepaParams(setBudgetMode(props.gepaParams, mode))}
                >
                  {label}
                </Button>
              ))}
            </div>
          </div>
          {budgetMode === "metric_calls" ? (
            <label className="block text-sm font-medium">
              Max Metric Calls
              <Input
                type="number"
                min={1}
                value={props.gepaParams.max_metric_calls ?? 24}
                onChange={(event) => props.setGepaParams({ ...setBudgetMode(props.gepaParams, "metric_calls"), max_metric_calls: Number(event.target.value) })}
                className="mt-1"
              />
            </label>
          ) : null}
          {budgetMode === "full_evals" ? (
            <label className="block text-sm font-medium">
              Max Full Evaluations
              <Input
                type="number"
                min={1}
                value={props.gepaParams.max_full_evals ?? 4}
                onChange={(event) => props.setGepaParams({ ...setBudgetMode(props.gepaParams, "full_evals"), max_full_evals: Number(event.target.value) })}
                className="mt-1"
              />
            </label>
          ) : null}
          {budgetMode === "auto" ? (
            <label className="block text-sm font-medium">
              Auto Budget
              <select
                value={props.gepaParams.auto ?? "light"}
                onChange={(event) => props.setGepaParams({ ...setBudgetMode(props.gepaParams, "auto"), auto: event.target.value as GepaParamsState["auto"] })}
                className="mt-1 h-10 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="light">Light</option>
                <option value="medium">Medium</option>
                <option value="heavy">Heavy</option>
              </select>
            </label>
          ) : null}
          <p className="text-xs text-muted-foreground">
            GEPA accepts exactly one budget mode; the inactive budget fields are sent as null.
          </p>
        </div>

        <div className="space-y-3 rounded-lg border bg-secondary/20 p-3">
          <p className="text-xs font-semibold uppercase text-muted-foreground">Reflection And Selection</p>
          <Input
            value={props.gepaParams.reflection_model ?? ""}
            onChange={(event) => props.setGepaParams({ ...props.gepaParams, reflection_model: event.target.value })}
            placeholder="Reflection model, blank uses chat model"
          />
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="text-sm font-medium">
              Minibatch
              <Input
                type="number"
                min={1}
                value={props.gepaParams.reflection_minibatch_size}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, reflection_minibatch_size: Number(event.target.value) })}
                className="mt-1"
              />
            </label>
            <label className="text-sm font-medium">
              Perfect Score
              <Input
                type="number"
                min={0}
                step="0.01"
                value={props.gepaParams.perfect_score}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, perfect_score: Number(event.target.value) })}
                className="mt-1"
              />
            </label>
            <label className="text-sm font-medium">
              Candidate Selector
              <select
                value={props.gepaParams.candidate_selection_strategy}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, candidate_selection_strategy: event.target.value as GepaParamsState["candidate_selection_strategy"] })}
                className="mt-1 h-10 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="pareto">Pareto</option>
                <option value="current_best">Current Best</option>
                <option value="epsilon_greedy">Epsilon Greedy</option>
                <option value="top_k_pareto">Top-K Pareto</option>
              </select>
            </label>
            <label className="text-sm font-medium">
              Frontier
              <select
                value={props.gepaParams.frontier_type}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, frontier_type: event.target.value as GepaParamsState["frontier_type"] })}
                className="mt-1 h-10 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="instance">Instance</option>
                <option value="objective">Objective</option>
                <option value="hybrid">Hybrid</option>
                <option value="cartesian">Cartesian</option>
              </select>
            </label>
            <label className="text-sm font-medium">
              Component Selector
              <select
                value={props.gepaParams.module_selector}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, module_selector: event.target.value })}
                className="mt-1 h-10 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="all">All</option>
                <option value="round_robin">Round Robin</option>
              </select>
            </label>
            <label className="text-sm font-medium">
              Val Policy
              <select
                value={props.gepaParams.val_evaluation_policy ?? ""}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, val_evaluation_policy: (event.target.value || null) as GepaParamsState["val_evaluation_policy"] })}
                className="mt-1 h-10 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="">Default</option>
                <option value="full_eval">Full Eval</option>
              </select>
            </label>
          </div>
        </div>

        <div className="space-y-3 rounded-lg border bg-secondary/20 p-3">
          <p className="text-xs font-semibold uppercase text-muted-foreground">Runtime Options</p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={props.gepaParams.skip_perfect_score}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, skip_perfect_score: event.target.checked })}
              />
              Skip perfect minibatches
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={props.gepaParams.track_best_outputs}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, track_best_outputs: event.target.checked })}
              />
              Track best outputs
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={props.gepaParams.cache_evaluation}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, cache_evaluation: event.target.checked })}
              />
              Cache evaluations
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={props.gepaParams.raise_on_exception}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, raise_on_exception: event.target.checked })}
              />
              Raise on exception
            </label>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="text-sm font-medium">
              Seed
              <Input
                type="number"
                value={props.gepaParams.seed}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, seed: Number(event.target.value) })}
                className="mt-1"
              />
            </label>
            <label className="text-sm font-medium">
              Tool chars
              <Input
                type="number"
                value={props.traceConfig.max_tool_return_chars}
                onChange={(event) => props.setTraceConfig({ ...props.traceConfig, max_tool_return_chars: Number(event.target.value) })}
                className="mt-1"
              />
            </label>
          </div>
        </div>

        <div className="space-y-3 rounded-lg border bg-secondary/20 p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs font-semibold uppercase text-muted-foreground">Merge</p>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={props.gepaParams.use_merge}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, use_merge: event.target.checked })}
              />
              Enabled
            </label>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="text-sm font-medium">
              Max Invocations
              <Input
                type="number"
                min={0}
                value={props.gepaParams.max_merge_invocations}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, max_merge_invocations: Number(event.target.value) })}
                className="mt-1"
                disabled={!props.gepaParams.use_merge}
              />
            </label>
            <label className="text-sm font-medium">
              Val Overlap Floor
              <Input
                type="number"
                min={0}
                value={props.gepaParams.merge_val_overlap_floor}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, merge_val_overlap_floor: Number(event.target.value) })}
                className="mt-1"
                disabled={!props.gepaParams.use_merge}
              />
            </label>
          </div>
        </div>

        <div className="space-y-3 rounded-lg border bg-secondary/20 p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs font-semibold uppercase text-muted-foreground">MLflow</p>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={props.gepaParams.use_mlflow}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, use_mlflow: event.target.checked })}
              />
              Enabled
            </label>
          </div>
          {props.gepaParams.use_mlflow ? (
            <div className="space-y-2">
              <Input
                value={props.gepaParams.mlflow_tracking_uri ?? ""}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, mlflow_tracking_uri: event.target.value })}
                placeholder="Tracking URI"
              />
              <Input
                value={props.gepaParams.mlflow_experiment_name ?? ""}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, mlflow_experiment_name: event.target.value })}
                placeholder="Experiment name"
              />
            </div>
          ) : null}
        </div>
        <div className="grid grid-cols-3 gap-2 rounded-lg border bg-secondary/35 p-3 text-center text-xs">
          <div><b>{props.counts.train}</b><br />train</div>
          <div><b>{props.counts.val}</b><br />val</div>
          <div><b>{props.counts.test}</b><br />test</div>
        </div>
        <Button type="button" className="w-full" onClick={() => void props.onLaunch()} disabled={props.saving || !props.canLaunch}>
          {props.saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Launch GEPA Run
        </Button>
      </CardContent>
    </Card>
  );
}

function RunMonitor({
  run,
  graph,
  selectedNode,
  events,
  onNodeSelect,
  onCancel,
  onClear,
  saving,
}: {
  run: OptimizationRunRecord | null;
  graph: { nodes: Node<CandidateNodeData>[]; edges: Edge[] };
  selectedNode: CandidateNodeData | null;
  events: OptimizationEventRecord[];
  onNodeSelect: (node: CandidateNodeData | null) => void;
  onCancel: () => Promise<void>;
  onClear: () => void;
  saving: boolean;
}) {
  const [view, setView] = useState<MonitorView>("graph");
  const progress = useMemo(() => progressFromRun(run, events), [run, events]);
  const nativeAvailable = Boolean(run && ["completed", "canceled", "failed"].includes(run.status));

  useEffect(() => {
    if (!nativeAvailable) setView("graph");
  }, [nativeAvailable, run?.id]);

  return (
    <Card className="min-h-[680px] overflow-hidden">
      <CardHeader className="border-b py-4">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Network className="h-4 w-4 text-primary" />
              Pareto DAG
            </CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              {run ? <Badge variant={statusVariant(run.status)}>{run.status}</Badge> : null}
              {run ? <Badge variant="outline">best {formatScore(run.best_score)}</Badge> : null}
              {run ? (
                <div className="grid grid-cols-2 overflow-hidden rounded-md border">
                  <Button
                    type="button"
                    variant={view === "graph" ? "secondary" : "ghost"}
                    size="sm"
                    className="rounded-none border-0"
                    onClick={() => setView("graph")}
                  >
                    DAG
                  </Button>
                  <Button
                    type="button"
                    variant={view === "native" ? "secondary" : "ghost"}
                    size="sm"
                    className="rounded-none border-0"
                    onClick={() => setView("native")}
                    disabled={!nativeAvailable}
                  >
                    Native
                  </Button>
                </div>
              ) : null}
              {run && ["queued", "running"].includes(run.status) ? (
                <Button type="button" variant="outline" size="sm" onClick={() => void onCancel()} disabled={saving}>
                  <Square className="h-3.5 w-3.5" />
                  Cancel
                </Button>
              ) : null}
              {run ? (
                <Button type="button" variant="outline" size="sm" onClick={onClear}>
                  Clear
                </Button>
              ) : null}
            </div>
          </div>
          <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
            <div className="h-2 overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${progress?.percent ?? 0}%` }}
              />
            </div>
            <div className="text-xs text-muted-foreground">
              {progress ? (
                <span>
                  {progress.used}
                  {progress.total ? ` / ${progress.total}` : ""} metric calls
                  {progress.remaining !== null ? ` · ${progress.remaining} left` : ""}
                </span>
              ) : (
                <span>Waiting for GEPA progress</span>
              )}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="relative h-[640px] p-0">
        {run && view === "native" && nativeAvailable ? (
          <iframe
            title="Native GEPA candidate tree"
            src={optimizationArtifactUrl(run.id, "native-html")}
            className="h-full w-full border-0 bg-background"
          />
        ) : run ? (
          <div className="relative h-full">
            <ReactFlow
              className="optimization-flow"
              nodes={graph.nodes}
              edges={graph.edges}
              nodeTypes={nodeTypes}
              defaultViewport={{ x: 320, y: 40, zoom: 0.86 }}
              minZoom={0.2}
              maxZoom={1.6}
              onNodeClick={(_, node) => onNodeSelect(node.data as CandidateNodeData)}
              onPaneClick={() => onNodeSelect(null)}
            >
              <Background gap={28} size={1.2} />
              <Controls />
              <MiniMap nodeColor={(node) => nodeColor((node.data as CandidateNodeData).role)} pannable zoomable />
            </ReactFlow>
            {selectedNode ? (
              <NodeDetailDrawer node={selectedNode} run={run} onClose={() => onNodeSelect(null)} />
            ) : null}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Select or launch a run to inspect its candidate graph.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function NodeDetailDrawer({
  node,
  run,
  onClose,
}: {
  node: CandidateNodeData;
  run: OptimizationRunRecord;
  onClose: () => void;
}) {
  const instructionText =
    node.proposedInstructions?.instructions ??
    node.candidate?.instructions ??
    node.events?.find((event) => typeof event.data?.new_instructions === "object")?.data?.new_instructions;
  const printableInstructions =
    typeof instructionText === "string" ? instructionText : "No instruction text available for this node.";
  return (
    <motion.aside
      initial={{ opacity: 0, x: 18 }}
      animate={{ opacity: 1, x: 0 }}
      className="absolute bottom-4 right-4 top-4 z-10 flex w-[min(420px,calc(100%-2rem))] flex-col overflow-hidden rounded-lg border bg-card/95 shadow-xl backdrop-blur"
    >
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{node.title}</p>
          <p className="text-xs text-muted-foreground">{run.name}</p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-2 border-b p-4 text-sm">
        <MetricRow label="Status" value={node.status} />
        <MetricRow label="Score" value={formatScore(node.score)} />
        <MetricRow label="Candidate" value={String(node.newCandidateIndex ?? node.candidateIndex ?? "-")} />
        <MetricRow label="Parents" value={(node.parentIds ?? []).filter((item) => item !== null).join(", ") || "-"} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="rounded-lg border bg-secondary/25 p-3">
          <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Summary</p>
          <p className="text-sm leading-relaxed">{node.message ?? "No summary available."}</p>
        </div>
        <div className="mt-3 rounded-lg border bg-secondary/25 p-3">
          <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Instructions</p>
          <p className="max-h-[240px] overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed">
            {printableInstructions}
          </p>
        </div>
        {node.events?.length ? (
          <div className="mt-3 rounded-lg border bg-secondary/25 p-3">
            <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Callbacks</p>
            <div className="space-y-2">
              {node.events.map((event) => (
                <div key={event.id} className="rounded-md border bg-card px-2 py-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-xs font-semibold">{event.type}</p>
                    <span className="text-[10px] text-muted-foreground">#{event.sequence}</span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{event.message}</p>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </motion.aside>
  );
}

function DatasetCuration(props: {
  cases: OptimizationCaseRecord[];
  selectedCaseIds: Set<string>;
  caseSplits: OptimizationCaseSplit[];
  search: string;
  setSearch: (value: string) => void;
  refreshing: boolean;
  onRefresh: () => void;
  onSelectAll: () => void;
  onAutoSplit: (mode: "random" | "outcome" | "outcome_issues") => void;
  onToggleCase: (caseId: string) => void;
  onSetSplit: (caseId: string, split: OptimizationSplit) => void;
}) {
  const splitByCase = new Map(props.caseSplits.map((item) => [item.case_id, item.split]));
  return (
    <Card className="min-h-0">
      <CardHeader className="border-b py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <GitCompareArrows className="h-4 w-4 text-primary" />
            Dataset
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={props.onSelectAll}>Select All</Button>
            <Button type="button" variant="outline" size="sm" onClick={() => props.onAutoSplit("random")}>Random</Button>
            <Button type="button" variant="outline" size="sm" onClick={() => props.onAutoSplit("outcome")}>Outcome</Button>
            <Button type="button" variant="outline" size="sm" onClick={() => props.onAutoSplit("outcome_issues")}>Outcome+Issues</Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b p-3">
          <div className="relative min-w-[260px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input value={props.search} onChange={(event) => props.setSearch(event.target.value)} className="pl-9" placeholder="Search cases" />
          </div>
          <Button type="button" variant="outline" onClick={props.onRefresh} disabled={props.refreshing}>
            {props.refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Load
          </Button>
        </div>
        <div className="max-h-[340px] overflow-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead className="sticky top-0 z-10 border-b bg-secondary/80 text-xs text-muted-foreground backdrop-blur">
              <tr>
                <th className="px-3 py-2 text-left">Case</th>
                <th className="px-3 py-2 text-left">Outcome</th>
                <th className="px-3 py-2 text-left">Issues</th>
                <th className="px-3 py-2 text-left">Dataset</th>
                <th className="px-3 py-2 text-left">Split</th>
              </tr>
            </thead>
            <tbody>
              {props.cases.length === 0 ? (
                <tr><td colSpan={5} className="h-24 text-center text-muted-foreground">No cases match this form and search.</td></tr>
              ) : props.cases.map((item) => {
                const selected = props.selectedCaseIds.has(item.case_id);
                const split = splitByCase.get(item.case_id);
                return (
                  <tr key={item.case_id} className="border-b hover:bg-secondary/35">
                    <td className="px-3 py-2">
                      <label className="flex items-start gap-2">
                        <input type="checkbox" checked={selected} onChange={() => props.onToggleCase(item.case_id)} className="mt-1" />
                        <span>
                          <span className="font-medium">{item.claim_number}</span>
                          <span className="line-clamp-1 text-xs text-muted-foreground">{item.instructions}</span>
                        </span>
                      </label>
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant={item.outcome === "Meets" ? "success" : "danger"}>{item.outcome}</Badge>
                    </td>
                    <td className="px-3 py-2 tabular-nums">{item.issue_count} / {item.driver_count}</td>
                    <td className="px-3 py-2">
                      <p className="text-xs">{item.dataset_name}</p>
                      <Badge variant="outline" className="mt-1 text-[10px]">{item.source_kind}</Badge>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1">
                        {(["train", "val", "test"] as OptimizationSplit[]).map((option) => (
                          <Button
                            key={option}
                            type="button"
                            variant={split === option ? "default" : "outline"}
                            size="sm"
                            className="h-7 px-2 text-xs"
                            onClick={() => props.onSetSplit(item.case_id, option)}
                          >
                            {option}
                          </Button>
                        ))}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function buildGraph(
  artifact: OptimizationDagArtifact | null,
  run: OptimizationRunRecord | null,
  events: OptimizationEventRecord[],
): { nodes: Node<CandidateNodeData>[]; edges: Edge[] } {
  const iterationGraph = buildIterationGraph(run, events);
  if (iterationGraph.nodes.length > 0) {
    return layoutGraph(iterationGraph.nodes, iterationGraph.edges);
  }
  if (artifact?.nodes.length) {
    const rawNodes: Node<CandidateNodeData>[] = artifact.nodes.map((node) => ({
      id: node.id,
      type: "candidate",
      data: {
        label: `Candidate ${node.candidate_index}`,
        title: `Candidate ${node.candidate_index}`,
        score: node.score,
        role: node.role,
        status: node.role,
        candidateIndex: node.candidate_index,
        parentIds: node.parents,
        candidate: node.candidate,
        message: `${node.role} candidate with ${node.parents.filter((item) => item !== null).length || 0} parent link(s).`,
      },
      position: { x: 0, y: 0 },
    }));
    const edges: Edge[] = artifact.edges.map((edge) => ({
      ...edge,
      animated: false,
      style: { strokeWidth: 2 },
    }));
    const compacted = compactCandidateGraph(rawNodes, edges);
    return layoutGraph(compacted.nodes, compacted.edges);
  }
  return { nodes: [], edges: [] };
}

function buildIterationGraph(
  run: OptimizationRunRecord | null,
  events: OptimizationEventRecord[],
): { nodes: Node<CandidateNodeData>[]; edges: Edge[] } {
  if (!run || events.length === 0) return { nodes: [], edges: [] };
  const nodes: Node<CandidateNodeData>[] = [];
  const seedEvent = events.find((event) => event.type === "run_started") ?? events.find((event) => event.type === "run_prepared");
  const preparedProgress = progressFromRun(run, events);
  if (seedEvent || run.seed_candidate) {
    nodes.push({
      id: "seed",
      type: "candidate",
      data: {
        label: "seed",
        title: "Seed Candidate",
        role: "seed",
        status: "seed",
        score: run.original_score,
        candidateIndex: 0,
        candidate: candidateFromUnknown(seedEvent?.data?.seed_candidate) ?? run.seed_candidate ?? undefined,
        message: seedEvent?.message ?? "Initial prompt candidate.",
        progress: preparedProgress,
        event: seedEvent,
        events: seedEvent ? [seedEvent] : [],
      },
      position: { x: 0, y: 0 },
    });
  }

  const byIteration = new Map<number, OptimizationEventRecord[]>();
  for (const event of events) {
    if (typeof event.iteration !== "number" || event.iteration <= 0) continue;
    byIteration.set(event.iteration, [...(byIteration.get(event.iteration) ?? []), event]);
  }

  const iterationNodes = [...byIteration.entries()]
    .sort(([first], [second]) => first - second)
    .map(([iteration, bucket]) => iterationNodeFromEvents(iteration, bucket));
  nodes.push(...compactIterationNodes(iterationNodes));

  const terminal = [...events].reverse().find((event) => ["run_completed", "run_error"].includes(event.type));
  if (terminal) {
    nodes.push({
      id: "terminal",
      type: "candidate",
      data: {
        label: "final",
        title: terminal.type === "run_completed" ? "Run Complete" : "Run Error",
        role: terminal.type === "run_completed" ? "best" : "errored",
        status: terminal.type === "run_completed" ? "complete" : "error",
        score: run.best_score,
        candidate: run.best_candidate ?? undefined,
        message: terminal.message,
        progress: progressFromRun(run, events),
        event: terminal,
        events: [terminal],
      },
      position: { x: 0, y: 0 },
    });
  }

  const edges: Edge[] = nodes.slice(1).map((node, index) => ({
    id: `${nodes[index].id}-${node.id}`,
    source: nodes[index].id,
    target: node.id,
    animated: run.status === "running" || run.status === "queued",
    style: { strokeWidth: 2 },
  }));
  return { nodes, edges };
}

function iterationNodeFromEvents(
  iteration: number,
  bucket: OptimizationEventRecord[],
): Node<CandidateNodeData> {
  const eventOfType = (...types: string[]) => [...bucket].reverse().find((event) => types.includes(event.type));
  const selected = eventOfType("candidate_selected");
  const sampled = eventOfType("minibatch_sampled");
  const proposal = eventOfType("proposal_created");
  const accepted = eventOfType("candidate_accepted", "merge_accepted");
  const rejected = eventOfType("candidate_rejected", "merge_rejected");
  const validation = eventOfType("validation_evaluated");
  const evaluation = eventOfType("evaluation_completed");
  const error = eventOfType("run_error");
  const progressEvent = eventOfType("budget_updated");
  const proposedInstructions = candidateFromUnknown(proposal?.data?.new_instructions);
  const candidate = proposedInstructions ?? candidateFromUnknown(selected?.data?.candidate);
  const acceptedScore = numberFromUnknown(accepted?.data?.new_score);
  const validationScore = numberFromUnknown(validation?.data?.average_score);
  const evaluationScore = averageFromUnknownScores(evaluation?.data?.scores);
  const selectedScore = numberFromUnknown(selected?.data?.score);
  const score = acceptedScore ?? validationScore ?? evaluationScore ?? selectedScore;
  const newCandidateIndex = numberFromUnknown(accepted?.data?.new_candidate_idx);
  const candidateIndex = numberFromUnknown(selected?.data?.candidate_idx);
  const parentIds = arrayOfNumbersOrNull(accepted?.data?.parent_ids ?? evaluation?.data?.parent_ids);
  const minibatchIds = Array.isArray(sampled?.data?.minibatch_ids) ? sampled.data.minibatch_ids : null;
  const validationSize = numberFromUnknown(validation?.data?.num_examples_evaluated);
  const status = error
    ? "error"
    : accepted
      ? "accepted"
      : rejected
        ? "rejected"
        : proposal
          ? "proposed"
          : validation
            ? "validated"
            : "running";
  const role = error
    ? "errored"
    : accepted
      ? "accepted"
      : rejected
        ? "rejected"
        : validation?.data?.is_best_program
          ? "best"
          : "candidate";
  const message =
    rejected?.message ??
    accepted?.message ??
    validation?.message ??
    proposal?.message ??
    evaluation?.message ??
    selected?.message ??
    bucket[bucket.length - 1]?.message;

  return {
    id: `iteration-${iteration}`,
    type: "candidate",
    data: {
      label: `i${iteration}`,
      title: `Iteration ${iteration}`,
      role,
      status,
      score,
      iteration,
      candidateIndex,
      newCandidateIndex,
      parentIds,
      minibatchSize: minibatchIds?.length ?? null,
      validationSize,
      candidate,
      proposedInstructions,
      message,
      progress: progressFromEvents(bucket),
      event: bucket[bucket.length - 1],
      events: bucket,
    },
    position: { x: 0, y: 0 },
  };
}

function compactIterationNodes(nodes: Node<CandidateNodeData>[]): Node<CandidateNodeData>[] {
  if (nodes.length <= maxVisibleIterationNodes) return nodes;
  const head = nodes.slice(0, 1);
  const tail = nodes.slice(-4);
  const middle = nodes.slice(1, -4);
  const bucketSize = Math.max(1, Math.ceil(middle.length / 3));
  const buckets: Node<CandidateNodeData>[] = [];
  for (let index = 0; index < middle.length; index += bucketSize) {
    const chunk = middle.slice(index, index + bucketSize);
    const first = chunk[0]?.data.iteration;
    const last = chunk[chunk.length - 1]?.data.iteration;
    buckets.push({
      id: `iteration-bucket-${first}-${last}`,
      type: "candidate",
      data: {
        label: `i${first}-${last}`,
        title: `Iterations ${first}-${last}`,
        role: "bucket",
        status: "bucket",
        score: chunk[chunk.length - 1]?.data.score,
        message: `${chunk.length} GEPA iterations grouped. Click to inspect the callback summaries.`,
        progress: chunk[chunk.length - 1]?.data.progress,
        events: chunk.flatMap((node) => node.data.events ?? []),
      },
      position: { x: 0, y: 0 },
    });
  }
  return [...head, ...buckets, ...tail];
}

function compactCandidateGraph(
  nodes: Node<CandidateNodeData>[],
  edges: Edge[],
): { nodes: Node<CandidateNodeData>[]; edges: Edge[] } {
  if (nodes.length <= 28) return { nodes, edges };
  const importantIds = new Set<string>();
  for (const node of nodes) {
    if (["seed", "best", "pareto"].includes(node.data.role)) importantIds.add(node.id);
  }
  for (const node of nodes.slice(-12)) importantIds.add(node.id);
  const visible = nodes.filter((node) => importantIds.has(node.id));
  const omitted = nodes.filter((node) => !importantIds.has(node.id));
  if (!omitted.length) return { nodes: visible, edges: edges.filter((edge) => importantIds.has(edge.source) && importantIds.has(edge.target)) };
  const bucketNode: Node<CandidateNodeData> = {
    id: "candidate-bucket",
    type: "candidate",
    data: {
      label: "bucket",
      title: `${omitted.length} Candidates`,
      role: "bucket",
      status: "bucket",
      message: `${omitted.length} non-frontier candidates are grouped to keep the replay readable.`,
      events: [],
    },
    position: { x: 0, y: 0 },
  };
  const visibleEdges = edges.filter((edge) => importantIds.has(edge.source) && importantIds.has(edge.target));
  const seed = visible.find((node) => node.data.role === "seed") ?? visible[0];
  const bucketEdges: Edge[] = seed
    ? [{ id: `${seed.id}-candidate-bucket`, source: seed.id, target: bucketNode.id, style: { strokeWidth: 2 } }]
    : [];
  return { nodes: [...visible, bucketNode], edges: [...visibleEdges, ...bucketEdges] };
}

function progressFromRun(
  run: OptimizationRunRecord | null,
  events: OptimizationEventRecord[],
): RunProgress | null {
  const eventProgress = progressFromEvents(events);
  if (eventProgress) return eventProgress;
  if (!run) return null;
  const prepared = [...events].reverse().find((event) => event.type === "run_prepared");
  const preparedTotal = numberFromUnknown(prepared?.data?.estimated_metric_calls);
  const configTotal = metricBudgetFromRunConfig(run.config);
  const total = preparedTotal ?? configTotal;
  const used = run.total_metric_calls ?? 0;
  return {
    used,
    total,
    remaining: total !== null ? Math.max(total - used, 0) : null,
    percent: total ? clampPercent((used / total) * 100) : null,
  };
}

function progressFromEvents(events: OptimizationEventRecord[]): RunProgress | null {
  const budgetEvent = [...events].reverse().find((event) => event.type === "budget_updated");
  if (!budgetEvent) return null;
  const used = numberFromUnknown(budgetEvent.data?.metric_calls_used) ?? 0;
  const remaining = numberFromUnknown(budgetEvent.data?.metric_calls_remaining);
  const total = remaining !== null ? used + remaining : null;
  return {
    used,
    total,
    remaining,
    percent: total ? clampPercent((used / total) * 100) : null,
  };
}

function metricBudgetFromRunConfig(config: Record<string, unknown>): number | null {
  const gepaParams = recordFromUnknown(config.gepa_params);
  return numberFromUnknown(gepaParams?.max_metric_calls);
}

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value));
}

function numberFromUnknown(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function recordFromUnknown(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function candidateFromUnknown(value: unknown): Record<string, string> | undefined {
  const record = recordFromUnknown(value);
  if (!record) return undefined;
  return Object.fromEntries(
    Object.entries(record)
      .filter((entry): entry is [string, string] => typeof entry[1] === "string")
  );
}

function averageFromUnknownScores(value: unknown): number | null {
  if (!Array.isArray(value)) return null;
  const scores = value.filter((item): item is number => typeof item === "number" && Number.isFinite(item));
  return scores.length ? scores.reduce((sum, item) => sum + item, 0) / scores.length : null;
}

function arrayOfNumbersOrNull(value: unknown): Array<number | null> {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is number | null => item === null || typeof item === "number");
}

function layoutGraph(nodes: Node<CandidateNodeData>[], edges: Edge[]): { nodes: Node<CandidateNodeData>[]; edges: Edge[] } {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "TB", ranksep: 86, nodesep: 44 });
  nodes.forEach((node) => graph.setNode(node.id, { width: nodeWidth, height: nodeHeight }));
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target));
  dagre.layout(graph);
  return {
    nodes: nodes.map((node) => {
      const position = graph.node(node.id);
      return {
        ...node,
        position: { x: position.x - nodeWidth / 2, y: position.y - nodeHeight / 2 },
      };
    }),
    edges,
  };
}

function nodeColor(role: string): string {
  if (role === "best") return "#d97706";
  if (role === "pareto" || role === "accepted") return "#059669";
  if (role === "rejected" || role === "errored") return "#dc2626";
  if (role === "seed") return "#64748b";
  if (role === "bucket") return "#8b5cf6";
  return "#94a3b8";
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function LoadingState({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return <div className="py-8 text-center text-sm text-muted-foreground">{label}</div>;
}
