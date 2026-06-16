"use client";

import { useCallback, useEffect, useMemo, useState, type PointerEvent as ReactPointerEvent } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import dagre from "dagre";
import { motion } from "motion/react";
import {
  FileText,
  FolderArchive,
  GitBranch,
  GitCompareArrows,
  Info,
  Loader2,
  Maximize2,
  Minimize2,
  Network,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Square,
  Trash2,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  formatParentIds,
  nodeTypes,
  reflectionStatsFromEvents,
  type CandidateNodeData,
  type RunProgress,
} from "@/components/optimization/candidate-node";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  cancelOptimizationRun,
  createOptimizationRun,
  getOptimizationDagArtifact,
  getOptimizationRun,
  listFormCatalog,
  listOptimizationCases,
  listOptimizationRuns,
  optimizationArtifactUrl,
  optimizationEventsUrl,
  registerOptimizationCandidate,
} from "@/lib/api";
import type {
  FormKind,
  FormCatalogEntry,
  OptimizationCaseRecord,
  OptimizationCaseSplit,
  OptimizationDagArtifact,
  OptimizationEventRecord,
  OptimizationRunPayload,
  OptimizationRunRecord,
  OptimizationScoreKey,
  OptimizationSplit,
} from "@/lib/types";

const pollMs = 3500;
const nodeWidth = 284;
const nodeHeight = 168;
type GepaParamsState = OptimizationRunPayload["gepa_params"];
type BudgetMode = "metric_calls" | "full_evals" | "auto";
type MonitorView = "graph" | "native";
type ResizeDirection = "left" | "right" | "top" | "bottom" | "top-left" | "top-right" | "bottom-left" | "bottom-right";
type TextViewMode = "text" | "markdown";
type SeedSource = OptimizationRunPayload["seed_instruction_source"];

type StagedOptimizationConfig = {
  id: string;
  createdAt: string;
  payload: OptimizationRunPayload;
};

type ScoreKeyOption = {
  value: OptimizationScoreKey;
  label: string;
  formKinds: readonly ("all" | FormKind)[];
};

const scoreKeyOptions: ScoreKeyOption[] = [
  { value: "score", label: "Composite", formKinds: ["all"] },
  { value: "question_agreement", label: "Question Agreement", formKinds: ["all"] },
  { value: "outcome_score", label: "Outcome", formKinds: ["all"] },
  { value: "path_exact_rate", label: "Path Exact", formKinds: ["standard"] },
  { value: "subquestion_f1", label: "Driver F1", formKinds: ["standard"] },
  { value: "financial_score", label: "Financial Score", formKinds: ["financial"] },
  { value: "total_overwrite_agreement", label: "OW Total Agreement", formKinds: ["financial"] },
  { value: "total_underwrite_agreement", label: "UW Total Agreement", formKinds: ["financial"] },
  { value: "overwrite_percent_agreement", label: "OW % Agreement", formKinds: ["financial"] },
  { value: "underwrite_percent_agreement", label: "UW % Agreement", formKinds: ["financial"] },
  { value: "question_financial_agreement", label: "Question Financial Agreement", formKinds: ["financial"] },
  { value: "absolute_dollar_error_score", label: "Dollar Error Score", formKinds: ["financial"] },
  { value: "percent_error_score", label: "Percent Error Score", formKinds: ["financial"] },
];

function scoreOptionsForFormKind(formKind: FormKind) {
  return scoreKeyOptions.filter((option) => option.formKinds.includes("all") || option.formKinds.includes(formKind));
}

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
  batch_sampler: "audit_balanced",
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

function useBodyScrollLock(open: boolean) {
  useEffect(() => {
    if (!open) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);
}

function normalizeGepaParams(params: GepaParamsState): GepaParamsState {
  return {
    ...params,
    auto: params.auto ?? null,
    max_full_evals: params.max_full_evals ?? null,
    max_metric_calls: params.max_metric_calls ?? null,
    reflection_model: params.reflection_model || null,
    perfect_score: 1,
    skip_perfect_score: true,
    frontier_type: "instance",
    module_selector: "all",
    track_best_outputs: false,
    val_evaluation_policy: params.val_evaluation_policy || null,
    mlflow_tracking_uri: params.use_mlflow ? params.mlflow_tracking_uri || null : null,
    mlflow_experiment_name: params.use_mlflow ? params.mlflow_experiment_name || null : null,
  };
}

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

function seedSourceLabel(payload: OptimizationRunPayload): string {
  if (payload.seed_instruction_source === "manual") return "manual seed";
  if (payload.seed_instruction_source === "prompt_registry") {
    const ref = payload.seed_prompt_ref;
    if (ref?.ref_type === "alias") return `${ref.alias ?? "registry"} seed`;
    if (ref?.ref_type === "version") return "version seed";
    return "active prompt seed";
  }
  return "form default seed";
}

function runConfigPayload(run: OptimizationRunRecord): OptimizationRunPayload {
  return run.config as unknown as OptimizationRunPayload;
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

type RuntimeCandidateDraft = {
  id: string;
  candidateIndex: number | null;
  role: string;
  status: string;
  title: string;
  label: string;
  score: number | null;
  candidate: Record<string, string>;
  parentIds: Array<number | null>;
  events: OptimizationEventRecord[];
  message: string;
};

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
  const [historyOpen, setHistoryOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [editingStageId, setEditingStageId] = useState<string | null>(null);
  const [stagedConfigs, setStagedConfigs] = useState<StagedOptimizationConfig[]>([]);
  const [configSearch, setConfigSearch] = useState("");
  const [configStatusFilter, setConfigStatusFilter] = useState("all");
  const [formKey, setFormKey] = useState("tfr_default@v0.1");
  const [search, setSearch] = useState("");
  const [runName, setRunName] = useState("GEPA Prompt Optimization");
  const [seedSource, setSeedSource] = useState<SeedSource>("prompt_registry");
  const [manualInstructions, setManualInstructions] = useState("");
  const [metricMode, setMetricMode] = useState<"comparison" | "comparison_with_judge">("comparison");
  const [scoreKey, setScoreKey] = useState<OptimizationRunPayload["score_key"]>("score");
  const [referencePolicy, setReferencePolicy] = useState<OptimizationRunPayload["reference_policy"]>("prefer_r2");
  const [judgeModel, setJudgeModel] = useState("");
  const [useFeedbackWhenAvailable, setUseFeedbackWhenAvailable] = useState(false);
  const [judgeScoreWeight, setJudgeScoreWeight] = useState(0.2);
  const [gepaParams, setGepaParams] = useState<GepaParamsState>(defaultGepaParams);
  const [traceConfig, setTraceConfig] = useState(defaultTraceConfig);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [refreshingCases, setRefreshingCases] = useState(false);
  const [error, setError] = useState("");

  const [formId, formVersion] = formKey.split("@");
  const selectedFormKind = useMemo<FormKind>(
    () => forms.find((form) => `${form.id}@${form.version}` === formKey)?.formKind ?? "standard",
    [formKey, forms],
  );
  const applicableScoreOptions = useMemo(() => scoreOptionsForFormKind(selectedFormKind), [selectedFormKind]);
  const counts = splitCounts(caseSplits);
  const activeRun = selectedRun && ["queued", "running"].includes(selectedRun.status) ? selectedRun : null;
  const filteredConfigRuns = useMemo(() => {
    const query = configSearch.trim().toLowerCase();
    return runs.filter((run) => {
      const matchesStatus = configStatusFilter === "all" || run.status === configStatusFilter;
      const matchesQuery =
        !query ||
        [
          run.name,
          run.form_id,
          run.form_version,
          seedSourceLabel(runConfigPayload(run)),
          run.status,
        ]
          .join(" ")
          .toLowerCase()
          .includes(query);
      return matchesStatus && matchesQuery;
    });
  }, [configSearch, configStatusFilter, runs]);

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
      const nextCases = await listOptimizationCases(formId, formVersion, search);
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
    if (!applicableScoreOptions.some((option) => option.value === scoreKey)) {
      setScoreKey("score");
    }
  }, [applicableScoreOptions, scoreKey]);

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

  const buildPayload = (): OptimizationRunPayload => ({
    name: runName.trim() || `GEPA ${formKey}`,
    form_id: formId,
    form_version: formVersion,
    seed_instruction_source: seedSource,
    manual_instructions: seedSource === "manual" ? manualInstructions : "",
    seed_prompt_ref: null,
    metric_mode: metricMode,
    score_key: scoreKey,
    reference_policy: referencePolicy,
    judge_model: metricMode === "comparison_with_judge" ? judgeModel || null : null,
    use_feedback_when_available: useFeedbackWhenAvailable,
    judge_score_weight: metricMode === "comparison_with_judge" ? judgeScoreWeight : 0,
    gepa_params: normalizeGepaParams(gepaParams),
    trace_config: traceConfig,
    case_splits: caseSplits,
  });

  const canStageConfig =
    counts.train > 0 &&
    counts.val > 0 &&
    (seedSource === "form" ||
      seedSource === "prompt_registry" ||
      (seedSource === "manual" && Boolean(manualInstructions.trim())));

  const stageConfig = () => {
    if (!canStageConfig) {
      setError("Select at least one train case and one validation case. Manual seed runs also need instructions.");
      return;
    }
    setError("");
    const payload = buildPayload();
    setStagedConfigs((current) => {
      if (editingStageId) {
        return current.map((item) => item.id === editingStageId ? { ...item, payload } : item);
      }
      return [
        ...current,
        {
          id: crypto.randomUUID(),
          createdAt: new Date().toISOString(),
          payload,
        },
      ];
    });
    setEditingStageId(null);
    setConfigOpen(false);
  };

  const editStage = (item: StagedOptimizationConfig) => {
    const payload = item.payload;
    setEditingStageId(item.id);
    setRunName(payload.name);
    setFormKey(`${payload.form_id}@${payload.form_version}`);
    setSeedSource(payload.seed_instruction_source);
    setManualInstructions(payload.manual_instructions);
    setMetricMode(payload.metric_mode);
    setScoreKey(payload.score_key);
    setReferencePolicy(payload.reference_policy);
    setJudgeModel(payload.judge_model ?? "");
    setUseFeedbackWhenAvailable(Boolean(payload.use_feedback_when_available));
    setJudgeScoreWeight(payload.judge_score_weight ?? 0.2);
    setGepaParams({ ...defaultGepaParams, ...payload.gepa_params });
    setTraceConfig({ ...defaultTraceConfig, ...payload.trace_config });
    setCaseSplits(payload.case_splits);
    setSelectedCaseIds(new Set(payload.case_splits.map((split) => split.case_id)));
    setConfigOpen(true);
  };

  const removeStage = (id: string) => {
    setStagedConfigs((current) => current.filter((item) => item.id !== id));
    if (editingStageId === id) setEditingStageId(null);
  };

  const stageFromRun = (run: OptimizationRunRecord) => {
    const config = runConfigPayload(run);
    const payload = {
      ...config,
      seed_prompt_ref: null,
      name: `${run.name} copy`,
      case_splits: run.case_splits?.length
        ? run.case_splits
        : (config.case_splits ?? []),
    };
    setStagedConfigs((current) => [
      {
        id: crypto.randomUUID(),
        createdAt: new Date().toISOString(),
        payload,
      },
      ...current,
    ]);
  };

  const openNewConfig = () => {
    setEditingStageId(null);
    setConfigOpen(true);
  };

  const launchStagedRun = async (item: StagedOptimizationConfig) => {
    setSaving(true);
    setError("");
    try {
      const run = await createOptimizationRun(item.payload);
      setSelectedRun(run);
      setStagedConfigs((current) => current.filter((candidate) => candidate.id !== item.id));
      await refreshRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to launch optimization run.");
    } finally {
      setSaving(false);
    }
  };

  const registerCandidate = async (candidateIndex: number, activateForFormVersion: boolean) => {
    if (!selectedRun) return;
    setSaving(true);
    setError("");
    try {
      await registerOptimizationCandidate({
        run_id: selectedRun.id,
        candidate_index: candidateIndex,
        activate_for_form_version: activateForFormVersion,
      });
      await refreshRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to register optimization candidate.");
      throw err;
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
            <Button type="button" variant="outline" onClick={() => setHistoryOpen(true)}>
              <FolderArchive className="h-4 w-4" />
              Completed Runs
            </Button>
            <Button type="button" variant="outline" onClick={() => void refreshRuns()} disabled={loading}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
            <Button type="button" onClick={openNewConfig}>
              <Plus className="h-4 w-4" />
              Configure Run
            </Button>
          </div>
        </div>

        {error ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        <div className="grid min-h-[760px] min-w-0 gap-4 xl:grid-cols-[390px_minmax(0,1fr)]">
          <ConfigLibraryPanel
            runs={filteredConfigRuns}
            stagedCount={stagedConfigs.length}
            saving={saving}
            loading={loading}
            search={configSearch}
            statusFilter={configStatusFilter}
            onSearchChange={setConfigSearch}
            onStatusFilterChange={setConfigStatusFilter}
            onConfigure={openNewConfig}
            onRefresh={() => void refreshRuns()}
            onStageFromRun={stageFromRun}
            onSelectRun={setSelectedRun}
          />

          <main className="min-h-0 min-w-0 space-y-4">
            <StagedRunsBar
              items={stagedConfigs}
              saving={saving}
              onLaunch={launchStagedRun}
              onEdit={editStage}
              onRemove={removeStage}
              onConfigure={openNewConfig}
            />
            <RunMonitor
              run={selectedRun}
              graph={graph}
              selectedNode={selectedNode}
              events={events}
              onNodeSelect={setSelectedNode}
              onCancel={cancelRun}
              onClear={clearMonitor}
              onRegisterCandidate={registerCandidate}
              saving={saving}
            />
          </main>
        </div>

        <RunHistoryDrawer
          open={historyOpen}
          runs={runs}
          selectedRun={selectedRun}
          loading={loading}
          onClose={() => setHistoryOpen(false)}
          onSelect={(run) => {
            setSelectedRun(run);
            setHistoryOpen(false);
          }}
        />

        <OptimizationConfigDialog
          open={configOpen}
          editing={Boolean(editingStageId)}
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
          scoreOptions={applicableScoreOptions}
          referencePolicy={referencePolicy}
          setReferencePolicy={setReferencePolicy}
          judgeModel={judgeModel}
          setJudgeModel={setJudgeModel}
          useFeedbackWhenAvailable={useFeedbackWhenAvailable}
          setUseFeedbackWhenAvailable={setUseFeedbackWhenAvailable}
          judgeScoreWeight={judgeScoreWeight}
          setJudgeScoreWeight={setJudgeScoreWeight}
          gepaParams={gepaParams}
          setGepaParams={setGepaParams}
          traceConfig={traceConfig}
          setTraceConfig={setTraceConfig}
          counts={counts}
          canStage={canStageConfig}
          cases={cases}
          selectedCaseIds={selectedCaseIds}
          caseSplits={caseSplits}
          search={search}
          setSearch={setSearch}
          refreshingCases={refreshingCases}
          onRefreshCases={() => void refreshCases()}
          onSelectAllCases={selectAllCases}
          onAutoSplit={applyAutoSplit}
          onToggleCase={toggleCase}
          onSetSplit={setCaseSplit}
          onClose={() => {
            setConfigOpen(false);
            setEditingStageId(null);
          }}
          onSave={stageConfig}
        />
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
    <Card className="h-full overflow-hidden">
      <CardHeader className="border-b py-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <GitBranch className="h-4 w-4 text-primary" />
          Runs
        </CardTitle>
      </CardHeader>
      <CardContent className="chat-scrollbar max-h-[calc(100vh-9rem)] overflow-y-auto p-2">
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

function RunHistoryDrawer({
  open,
  runs,
  selectedRun,
  loading,
  onClose,
  onSelect,
}: {
  open: boolean;
  runs: OptimizationRunRecord[];
  selectedRun: OptimizationRunRecord | null;
  loading: boolean;
  onClose: () => void;
  onSelect: (run: OptimizationRunRecord) => void;
}) {
  useBodyScrollLock(open);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 bg-foreground/20 backdrop-blur-sm">
      <motion.aside
        initial={{ x: -32, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        className="flex h-full w-full max-w-[420px] flex-col border-r bg-card shadow-2xl"
      >
        <div className="flex items-start gap-3 border-b bg-secondary/35 px-5 py-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg border bg-background text-primary">
            <FolderArchive className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h2 className="text-lg font-semibold">Completed Runs</h2>
            <p className="text-sm text-muted-foreground">Select a prior run to reopen its saved DAG.</p>
          </div>
          <Button type="button" variant="ghost" size="icon" className="ml-auto h-9 w-9" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto p-3">
          <RunHistory runs={runs} selectedRun={selectedRun} onSelect={onSelect} loading={loading} />
        </div>
      </motion.aside>
    </div>
  );
}

function ConfigLibraryPanel({
  runs,
  stagedCount,
  saving,
  loading,
  search,
  statusFilter,
  onSearchChange,
  onStatusFilterChange,
  onConfigure,
  onRefresh,
  onStageFromRun,
  onSelectRun,
}: {
  runs: OptimizationRunRecord[];
  stagedCount: number;
  saving: boolean;
  loading: boolean;
  search: string;
  statusFilter: string;
  onSearchChange: (value: string) => void;
  onStatusFilterChange: (value: string) => void;
  onConfigure: () => void;
  onRefresh: () => void;
  onStageFromRun: (run: OptimizationRunRecord) => void;
  onSelectRun: (run: OptimizationRunRecord) => void;
}) {
  return (
    <Card className="flex h-fit max-h-[760px] min-h-0 flex-col overflow-hidden">
      <CardHeader className="border-b">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <FolderArchive className="h-4 w-4 text-primary" />
            Run Configs
          </CardTitle>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="icon" className="h-8 w-8" onClick={onRefresh} disabled={loading}>
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            </Button>
            <Button type="button" size="sm" className="gap-1.5" onClick={onConfigure}>
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
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              className="h-8 pl-8 text-xs"
              placeholder="Search prior configs"
            />
          </label>
          <select
            value={statusFilter}
            onChange={(event) => onStatusFilterChange(event.target.value)}
            className="h-8 rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="all">All statuses</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="canceled">Canceled</option>
          </select>
          <div className="flex flex-wrap gap-1.5 text-xs">
            <Badge variant="secondary">{stagedCount} staged</Badge>
            <Badge variant="outline">{runs.length} shown</Badge>
          </div>
        </div>
        <div className="chat-scrollbar max-h-[590px] overflow-y-auto">
          {runs.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <FileText className="mx-auto h-8 w-8 text-muted-foreground/40" />
              <p className="mt-2 text-sm font-medium">No configs match</p>
              <p className="mt-1 text-xs text-muted-foreground">Create a new GEPA config or adjust the filters.</p>
            </div>
          ) : (
            <div className="divide-y">
              {runs.map((run) => {
                const payload = runConfigPayload(run);
                const counts = splitCounts(run.case_splits?.length ? run.case_splits : payload.case_splits ?? []);
                return (
                  <div key={run.id} className="grid gap-3 p-3">
                    <button type="button" className="min-w-0 text-left" onClick={() => onSelectRun(run)}>
                      <div className="flex items-start justify-between gap-2">
                        <p className="line-clamp-2 text-sm font-semibold">{run.name}</p>
                        <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                        <Badge variant="outline">{run.form_id}@{run.form_version}</Badge>
                        <Badge variant="secondary">{counts.train}/{counts.val}/{counts.test}</Badge>
                        <Badge variant="outline">{seedSourceLabel(payload)}</Badge>
                        <Badge variant="outline">best {formatScore(run.best_score)}</Badge>
                      </div>
                      <p className="mt-2 text-xs text-muted-foreground">{formatDate(run.updated_at)}</p>
                    </button>
                    <div className="flex justify-end gap-2">
                      <Button type="button" variant="outline" size="sm" onClick={() => onStageFromRun(run)} disabled={saving}>
                        <Plus className="h-3.5 w-3.5" />
                        Stage
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function StagedRunsBar({
  items,
  saving,
  onConfigure,
  onLaunch,
  onEdit,
  onRemove,
}: {
  items: StagedOptimizationConfig[];
  saving: boolean;
  onConfigure: () => void;
  onLaunch: (item: StagedOptimizationConfig) => Promise<void>;
  onEdit: (item: StagedOptimizationConfig) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-primary" />
            Staged GEPA Runs
          </CardTitle>
          <Button type="button" size="sm" className="gap-1.5" onClick={onConfigure}>
            <Plus className="h-3.5 w-3.5" />
            New Config
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {items.length === 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-5 text-sm">
            <div>
              <p className="font-medium text-foreground">No staged configurations</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Stage a prior config from the drawer or create a new one.
              </p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={onConfigure}>
              <Plus className="h-3.5 w-3.5" />
              Create
            </Button>
          </div>
        ) : (
          <div className="chat-scrollbar flex gap-3 overflow-x-auto p-3">
            {items.map((item) => {
              const counts = splitCounts(item.payload.case_splits);
              const budgetMode = getBudgetMode(item.payload.gepa_params);
              const budgetLabel =
                budgetMode === "auto"
                  ? `auto ${item.payload.gepa_params.auto ?? "light"}`
                  : budgetMode === "full_evals"
                    ? `${item.payload.gepa_params.max_full_evals ?? "-"} evals`
                    : `${item.payload.gepa_params.max_metric_calls ?? "-"} calls`;
              return (
                <div key={item.id} className="grid min-w-[320px] max-w-[380px] gap-3 rounded-lg border bg-background p-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-sm font-semibold">{item.payload.name}</p>
                      <Badge variant="outline">{item.payload.form_id}@{item.payload.form_version}</Badge>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                      <Badge variant="secondary">{counts.train} train</Badge>
                      <Badge variant="secondary">{counts.val} val</Badge>
                      <Badge variant="secondary">{counts.test} test</Badge>
                      <Badge variant="outline">{budgetLabel}</Badge>
                      <Badge variant="outline">{seedSourceLabel(item.payload)}</Badge>
                      <Badge variant="outline">
                        {item.payload.metric_mode === "comparison_with_judge"
                          ? `judge ${Math.round((item.payload.judge_score_weight ?? 0) * 100)}%`
                          : "comparison"}
                      </Badge>
                      {item.payload.use_feedback_when_available ? <Badge variant="secondary">feedback</Badge> : null}
                    </div>
                  </div>
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button type="button" variant="outline" size="sm" onClick={() => onEdit(item)} disabled={saving}>
                      <Pencil className="h-3.5 w-3.5" />
                      Edit
                    </Button>
                    <Button type="button" variant="outline" size="sm" onClick={() => onRemove(item.id)} disabled={saving}>
                      <Trash2 className="h-3.5 w-3.5" />
                      Remove
                    </Button>
                    <Button type="button" size="sm" onClick={() => void onLaunch(item)} disabled={saving}>
                      {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                      Launch
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function OptimizationConfigDialog(props: {
  open: boolean;
  editing: boolean;
  forms: FormCatalogEntry[];
  formKey: string;
  setFormKey: (value: string) => void;
  runName: string;
  setRunName: (value: string) => void;
  seedSource: SeedSource;
  setSeedSource: (value: SeedSource) => void;
  manualInstructions: string;
  setManualInstructions: (value: string) => void;
  metricMode: "comparison" | "comparison_with_judge";
  setMetricMode: (value: "comparison" | "comparison_with_judge") => void;
  scoreKey: OptimizationRunPayload["score_key"];
  setScoreKey: (value: OptimizationRunPayload["score_key"]) => void;
  scoreOptions: ScoreKeyOption[];
  referencePolicy: OptimizationRunPayload["reference_policy"];
  setReferencePolicy: (value: OptimizationRunPayload["reference_policy"]) => void;
  judgeModel: string;
  setJudgeModel: (value: string) => void;
  useFeedbackWhenAvailable: boolean;
  setUseFeedbackWhenAvailable: (value: boolean) => void;
  judgeScoreWeight: number;
  setJudgeScoreWeight: (value: number) => void;
  gepaParams: GepaParamsState;
  setGepaParams: (value: GepaParamsState) => void;
  traceConfig: typeof defaultTraceConfig;
  setTraceConfig: (value: typeof defaultTraceConfig) => void;
  counts: { train: number; val: number; test: number };
  canStage: boolean;
  cases: OptimizationCaseRecord[];
  selectedCaseIds: Set<string>;
  caseSplits: OptimizationCaseSplit[];
  search: string;
  setSearch: (value: string) => void;
  refreshingCases: boolean;
  onRefreshCases: () => void;
  onSelectAllCases: () => void;
  onAutoSplit: (mode: "random" | "outcome" | "outcome_issues") => void;
  onToggleCase: (caseId: string) => void;
  onSetSplit: (caseId: string, split: OptimizationSplit) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  useBodyScrollLock(props.open);
  if (!props.open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 p-4 backdrop-blur-sm">
      <div className="flex max-h-[94vh] w-full max-w-6xl flex-col overflow-hidden rounded-lg border bg-card shadow-2xl">
        <div className="flex items-start gap-4 border-b bg-secondary/35 px-6 py-5">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border bg-background text-primary">
            <Sparkles className="h-6 w-6" />
          </div>
          <div className="min-w-0">
            <h2 className="text-xl font-semibold">{props.editing ? "Edit GEPA Configuration" : "Configure GEPA Run"}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Set optimization parameters and curate the train/validation/test split before staging.
            </p>
          </div>
          <Button type="button" variant="ghost" size="icon" className="ml-auto h-9 w-9" onClick={props.onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="chat-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          <div className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
            <RunConfig
              forms={props.forms}
              formKey={props.formKey}
              setFormKey={props.setFormKey}
              runName={props.runName}
              setRunName={props.setRunName}
              seedSource={props.seedSource}
              setSeedSource={props.setSeedSource}
              manualInstructions={props.manualInstructions}
              setManualInstructions={props.setManualInstructions}
              metricMode={props.metricMode}
              setMetricMode={props.setMetricMode}
              scoreKey={props.scoreKey}
              setScoreKey={props.setScoreKey}
              scoreOptions={props.scoreOptions}
              referencePolicy={props.referencePolicy}
              setReferencePolicy={props.setReferencePolicy}
              judgeModel={props.judgeModel}
              setJudgeModel={props.setJudgeModel}
              useFeedbackWhenAvailable={props.useFeedbackWhenAvailable}
              setUseFeedbackWhenAvailable={props.setUseFeedbackWhenAvailable}
              judgeScoreWeight={props.judgeScoreWeight}
              setJudgeScoreWeight={props.setJudgeScoreWeight}
              gepaParams={props.gepaParams}
              setGepaParams={props.setGepaParams}
              traceConfig={props.traceConfig}
              setTraceConfig={props.setTraceConfig}
              counts={props.counts}
            />
            <DatasetCuration
              cases={props.cases}
              selectedCaseIds={props.selectedCaseIds}
              caseSplits={props.caseSplits}
              search={props.search}
              setSearch={props.setSearch}
              refreshing={props.refreshingCases}
              onRefresh={props.onRefreshCases}
              onSelectAll={props.onSelectAllCases}
              onAutoSplit={props.onAutoSplit}
              onToggleCase={props.onToggleCase}
              onSetSplit={props.onSetSplit}
            />
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t bg-secondary/35 px-6 py-5">
          <div className="text-xs text-muted-foreground">
            Hardcoded defaults for v1: instance frontier, all components, perfect score 1, and skip-perfect minibatches on.
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={props.onClose}>Cancel</Button>
            <Button type="button" className="min-w-36" onClick={props.onSave} disabled={!props.canStage}>
              <Plus className="h-4 w-4" />
              {props.editing ? "Update Stage" : "Add to Stage"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function RunConfig(props: {
  forms: FormCatalogEntry[];
  formKey: string;
  setFormKey: (value: string) => void;
  runName: string;
  setRunName: (value: string) => void;
  seedSource: SeedSource;
  setSeedSource: (value: SeedSource) => void;
  manualInstructions: string;
  setManualInstructions: (value: string) => void;
  metricMode: "comparison" | "comparison_with_judge";
  setMetricMode: (value: "comparison" | "comparison_with_judge") => void;
  scoreKey: OptimizationRunPayload["score_key"];
  setScoreKey: (value: OptimizationRunPayload["score_key"]) => void;
  scoreOptions: ScoreKeyOption[];
  referencePolicy: OptimizationRunPayload["reference_policy"];
  setReferencePolicy: (value: OptimizationRunPayload["reference_policy"]) => void;
  judgeModel: string;
  setJudgeModel: (value: string) => void;
  useFeedbackWhenAvailable: boolean;
  setUseFeedbackWhenAvailable: (value: boolean) => void;
  judgeScoreWeight: number;
  setJudgeScoreWeight: (value: number) => void;
  gepaParams: GepaParamsState;
  setGepaParams: (value: GepaParamsState) => void;
  traceConfig: typeof defaultTraceConfig;
  setTraceConfig: (value: typeof defaultTraceConfig) => void;
  counts: { train: number; val: number; test: number };
}) {
  const budgetMode = getBudgetMode(props.gepaParams);
  const selectedForm = props.forms.find((form) => `${form.id}@${form.version}` === props.formKey);

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
                {form.id}@{form.version} - {form.formKind}
              </option>
            ))}
          </select>
          {selectedForm ? (
            <span className="mt-1 block text-xs font-normal capitalize text-muted-foreground">{selectedForm.formKind} audit form</span>
          ) : null}
        </label>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <Button
            type="button"
            variant={props.seedSource === "prompt_registry" ? "default" : "outline"}
            onClick={() => props.setSeedSource("prompt_registry")}
          >
            Active Prompt
          </Button>
          <Button type="button" variant={props.seedSource === "form" ? "default" : "outline"} onClick={() => props.setSeedSource("form")}>
            Form Default
          </Button>
          <Button type="button" variant={props.seedSource === "manual" ? "default" : "outline"} onClick={() => props.setSeedSource("manual")}>
            Manual Seed
          </Button>
        </div>
        {props.seedSource === "prompt_registry" ? (
          <p className="rounded-md border bg-secondary/25 px-3 py-2 text-xs text-muted-foreground">
            Uses the active prompt selected in Forms for this form version.
          </p>
        ) : null}
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
              {props.scoreOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
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
          <div className="space-y-2 rounded-lg border bg-secondary/20 p-3">
            <Input value={props.judgeModel} onChange={(event) => props.setJudgeModel(event.target.value)} placeholder="Judge model, blank uses chat model" />
            <label className="block text-sm font-medium">
              Judge Score Weight
              <Input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={props.judgeScoreWeight}
                onChange={(event) => props.setJudgeScoreWeight(Math.max(0, Math.min(1, Number(event.target.value) || 0)))}
                className="mt-1"
              />
            </label>
            <p className="text-xs text-muted-foreground">
              Blends judge_score with the selected deterministic metric for candidate selection.
            </p>
          </div>
        ) : null}
        <label className="flex items-start gap-2 rounded-lg border bg-secondary/20 p-3 text-sm">
          <input
            type="checkbox"
            checked={props.useFeedbackWhenAvailable}
            onChange={(event) => props.setUseFeedbackWhenAvailable(event.target.checked)}
            className="mt-0.5 h-4 w-4 accent-primary"
          />
          <span>
            <span className="block font-medium">Use feedback when available</span>
            <span className="mt-0.5 block text-xs text-muted-foreground">
              Passes published case feedback text into metric feedback and the judge prompt when present.
            </span>
          </span>
        </label>
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
              Batch Sampler
              <select
                value={props.gepaParams.batch_sampler}
                onChange={(event) => props.setGepaParams({ ...props.gepaParams, batch_sampler: event.target.value as GepaParamsState["batch_sampler"] })}
                className="mt-1 h-10 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="audit_balanced">Audit Balanced</option>
                <option value="epoch_shuffled">Epoch Shuffled</option>
              </select>
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
  onRegisterCandidate,
  saving,
}: {
  run: OptimizationRunRecord | null;
  graph: { nodes: Node<CandidateNodeData>[]; edges: Edge[] };
  selectedNode: CandidateNodeData | null;
  events: OptimizationEventRecord[];
  onNodeSelect: (node: CandidateNodeData | null) => void;
  onCancel: () => Promise<void>;
  onClear: () => void;
  onRegisterCandidate: (candidateIndex: number, activateForFormVersion: boolean) => Promise<void>;
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
              key={`${run.id}-${graph.nodes.length}-${graph.edges.length}`}
              className="optimization-flow"
              nodes={graph.nodes}
              edges={graph.edges}
              nodeTypes={nodeTypes}
              defaultViewport={{ x: 420, y: 72, zoom: 0.82 }}
              minZoom={0.2}
              maxZoom={1.6}
              onNodeClick={(_, node) => onNodeSelect(node.data as CandidateNodeData)}
              onPaneClick={() => onNodeSelect(null)}
            >
              <Background gap={28} size={1.2} />
              <Controls />
              <MiniMap
                pannable
                zoomable
                nodeBorderRadius={4}
                nodeColor={(node) => nodeColor((node.data as CandidateNodeData).role)}
                nodeStrokeColor={(node) => nodeStrokeColor((node.data as CandidateNodeData).role)}
                nodeStrokeWidth={3}
                maskColor="hsl(var(--background) / 0.46)"
                bgColor="hsl(var(--card) / 0.98)"
                style={{ width: 240, height: 168 }}
              />
            </ReactFlow>
            {selectedNode ? (
              <NodeDetailDrawer
                node={selectedNode}
                run={run}
                onRegisterCandidate={onRegisterCandidate}
                onClose={() => onNodeSelect(null)}
              />
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
  onRegisterCandidate,
  onClose,
}: {
  node: CandidateNodeData;
  run: OptimizationRunRecord;
  onRegisterCandidate: (candidateIndex: number, activateForFormVersion: boolean) => Promise<void>;
  onClose: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [viewer, setViewer] = useState<{ title: string; content: string; mode: TextViewMode } | null>(null);
  const [drawerSize, setDrawerSize] = useState({ width: 760, height: 560 });
  const [registeringPrompt, setRegisteringPrompt] = useState(false);
  const [activateRegisteredPrompt, setActivateRegisteredPrompt] = useState(false);
  const [promotionMessage, setPromotionMessage] = useState("");
  useBodyScrollLock(expanded || Boolean(viewer));
  const candidateIndex = node.newCandidateIndex ?? node.candidateIndex ?? null;
  const canPromote =
    typeof candidateIndex === "number" &&
    Number.isFinite(candidateIndex) &&
    ["completed", "failed", "canceled"].includes(run.status);
  const instructionText =
    node.proposedInstructions?.instructions ??
    node.candidate?.instructions ??
    node.events?.find((event) => typeof event.data?.new_instructions === "object")?.data?.new_instructions;
  const printableInstructions =
    typeof instructionText === "string" ? instructionText : "No instruction text available for this node.";
  const reflectionDetails = formatReflectionDetails(node.events ?? []);
  const reflectionStats = reflectionStatsFromEvents(node.events ?? []);
  const promote = async () => {
    if (!canPromote || candidateIndex === null) return;
    setPromotionMessage("");
    setRegisteringPrompt(true);
    try {
      await onRegisterCandidate(candidateIndex, activateRegisteredPrompt);
      setPromotionMessage(
        activateRegisteredPrompt
          ? `Registered candidate ${candidateIndex} and set it active for ${run.form_version}.`
          : `Registered candidate ${candidateIndex}.`,
      );
      setActivateRegisteredPrompt(false);
    } catch (err) {
      setPromotionMessage(err instanceof Error ? err.message : "Registration failed.");
    } finally {
      setRegisteringPrompt(false);
    }
  };
  const startResize = useCallback((
    direction: ResizeDirection,
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    const startX = event.clientX;
    const startY = event.clientY;
    const startWidth = drawerSize.width;
    const startHeight = drawerSize.height;
    const maxWidth = Math.max(440, window.innerWidth - 40);
    const maxHeight = Math.max(360, window.innerHeight - 40);
    const onMove = (moveEvent: PointerEvent) => {
      const dx = moveEvent.clientX - startX;
      const dy = moveEvent.clientY - startY;
      const nextWidth = direction.includes("left")
        ? startWidth - dx
        : direction.includes("right")
          ? startWidth + dx
          : startWidth;
      const nextHeight = direction.includes("top")
        ? startHeight - dy
        : direction.includes("bottom")
          ? startHeight + dy
          : startHeight;
      setDrawerSize({
        width: Math.min(Math.max(nextWidth, 440), maxWidth),
        height: Math.min(Math.max(nextHeight, 360), maxHeight),
      });
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }, [drawerSize.height, drawerSize.width]);
  return (
    <>
    <motion.aside
      initial={{ opacity: 0, x: 18 }}
      animate={{ opacity: 1, x: 0 }}
      style={expanded ? { width: drawerSize.width, height: drawerSize.height } : undefined}
      className={[
        "absolute z-10 flex flex-col overflow-hidden rounded-lg border bg-card/95 shadow-xl backdrop-blur",
        expanded
          ? "fixed right-6 top-6 max-h-[calc(100vh-3rem)] max-w-[calc(100vw-3rem)]"
          : "bottom-4 right-4 top-4 w-[min(440px,calc(100%-2rem))]",
      ].join(" ")}
    >
      {expanded ? <ResizeHandles onStartResize={startResize} /> : null}
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{node.title}</p>
          <p className="text-xs text-muted-foreground">{run.name}</p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setExpanded((current) => !current)}
            title={expanded ? "Collapse summary" : "Expand summary"}
          >
            {expanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 border-b p-4 text-sm">
        <MetricRow label="Status" value={node.status} />
        <MetricRow label="Score" value={formatScore(node.score)} />
        <MetricRow label="Candidate" value={String(node.newCandidateIndex ?? node.candidateIndex ?? "-")} />
        <MetricRow label="Parents" value={formatParentIds(node.parentIds)} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {canPromote ? (
          <div className="mb-3 rounded-lg border bg-secondary/25 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs font-semibold uppercase text-muted-foreground">Register Prompt</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Save this candidate as an immutable prompt version. Activation can stay in Forms, or happen now for this version.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-2 rounded-md border bg-background px-2 py-1 text-xs">
                  <input
                    type="checkbox"
                    checked={activateRegisteredPrompt}
                    disabled={registeringPrompt}
                    onChange={(event) => {
                      setActivateRegisteredPrompt(event.target.checked);
                      setPromotionMessage("");
                    }}
                  />
                  Set active for {run.form_version}
                </label>
                <Button
                  type="button"
                  size="sm"
                  className="h-8 px-2 text-xs"
                  disabled={registeringPrompt}
                  onClick={() => void promote()}
                >
                  {registeringPrompt ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                  Register
                </Button>
              </div>
            </div>
            {promotionMessage ? <p className="mt-2 text-xs text-emerald-600">{promotionMessage}</p> : null}
          </div>
        ) : null}
        <div className="rounded-lg border bg-secondary/25 p-3">
          <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Summary</p>
          <p className="text-sm leading-relaxed">{node.message ?? "No summary available."}</p>
        </div>
        <details className="mt-3 rounded-lg border bg-secondary/25 p-3">
          <summary className="flex cursor-pointer select-none items-center justify-between gap-3 text-xs font-semibold uppercase text-muted-foreground">
            <span>Instructions</span>
            <span className="flex items-center gap-2">
              <Badge variant="outline" className="text-[10px]">{printableInstructions.length.toLocaleString()} chars</Badge>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 px-2 text-[10px]"
                onClick={(event) => {
                  event.preventDefault();
                  setViewer({ title: `${node.title} Instructions`, content: printableInstructions, mode: "markdown" });
                }}
              >
                Open
              </Button>
            </span>
          </summary>
          <p className={[
            "mt-3 overflow-y-auto whitespace-pre-wrap rounded-md border bg-card p-3 text-xs leading-relaxed",
            expanded ? "max-h-[520px]" : "max-h-[240px]",
          ].join(" ")}>
            {printableInstructions}
          </p>
        </details>
        {reflectionDetails ? (
          <details className="mt-3 rounded-lg border bg-secondary/25 p-3">
            <summary className="flex cursor-pointer select-none items-center justify-between gap-3 text-xs font-semibold uppercase text-muted-foreground">
              <span>Reflection Details</span>
              <span className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px]">
                  {reflectionStats.batches} batch{reflectionStats.batches === 1 ? "" : "es"} · {reflectionStats.trajectories} traj
                </Badge>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 px-2 text-[10px]"
                  onClick={(event) => {
                    event.preventDefault();
                    setViewer({ title: `${node.title} Reflection Details`, content: reflectionDetails, mode: "text" });
                  }}
                >
                  Open
                </Button>
              </span>
            </summary>
            <pre className={[
              "mt-3 overflow-auto whitespace-pre-wrap rounded-md border bg-card p-3 text-xs leading-relaxed",
              expanded ? "max-h-[520px]" : "max-h-[260px]",
            ].join(" ")}>
              {reflectionDetails}
            </pre>
          </details>
        ) : null}
        {node.events?.length ? (
          <details className="mt-3 rounded-lg border bg-secondary/25 p-3">
            <summary className="flex cursor-pointer select-none items-center justify-between gap-3 text-xs font-semibold uppercase text-muted-foreground">
              <span>Callbacks</span>
              <Badge variant="outline" className="text-[10px]">{node.events.length}</Badge>
            </summary>
            <div className="mt-3 space-y-2">
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
          </details>
        ) : null}
      </div>
    </motion.aside>
    <TextViewerModal viewer={viewer} onClose={() => setViewer(null)} />
    </>
  );
}

function ResizeHandles({
  onStartResize,
}: {
  onStartResize: (direction: ResizeDirection, event: ReactPointerEvent<HTMLDivElement>) => void;
}) {
  return (
    <>
      <div
        className="absolute left-4 right-4 top-0 z-20 h-2 cursor-ns-resize touch-none"
        onPointerDown={(event) => onStartResize("top", event)}
      />
      <div
        className="absolute bottom-0 left-4 right-4 z-20 h-2 cursor-ns-resize touch-none"
        onPointerDown={(event) => onStartResize("bottom", event)}
      />
      <div
        className="absolute bottom-4 top-4 left-0 z-20 w-2 cursor-ew-resize touch-none"
        onPointerDown={(event) => onStartResize("left", event)}
      />
      <div
        className="absolute bottom-4 right-0 top-4 z-20 w-2 cursor-ew-resize touch-none"
        onPointerDown={(event) => onStartResize("right", event)}
      />
      <div
        className="absolute left-0 top-0 z-20 h-4 w-4 cursor-nwse-resize touch-none"
        onPointerDown={(event) => onStartResize("top-left", event)}
      />
      <div
        className="absolute right-0 top-0 z-20 h-4 w-4 cursor-nesw-resize touch-none"
        onPointerDown={(event) => onStartResize("top-right", event)}
      />
      <div
        className="absolute bottom-0 left-0 z-20 h-4 w-4 cursor-nesw-resize touch-none"
        onPointerDown={(event) => onStartResize("bottom-left", event)}
      />
      <div
        className="absolute bottom-0 right-0 z-20 h-4 w-4 cursor-nwse-resize touch-none"
        onPointerDown={(event) => onStartResize("bottom-right", event)}
      />
    </>
  );
}

function TextViewerModal({
  viewer,
  onClose,
}: {
  viewer: { title: string; content: string; mode: TextViewMode } | null;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<TextViewMode>("text");
  useEffect(() => {
    if (viewer) setMode(viewer.mode);
  }, [viewer]);
  if (!viewer) return null;
  return (
    <div className="fixed inset-0 z-[70] bg-foreground/30 backdrop-blur-sm">
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        aria-label="Close text viewer"
        onClick={onClose}
      />
      <motion.aside
        initial={{ x: 48, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        className="absolute inset-y-0 right-0 flex w-[min(860px,94vw)] flex-col overflow-hidden border-l bg-card shadow-2xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-secondary/35 px-5 py-4">
          <div className="min-w-0">
            <h3 className="truncate text-lg font-semibold">{viewer.title}</h3>
            <p className="text-xs text-muted-foreground">{viewer.content.length.toLocaleString()} characters</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="grid grid-cols-2 overflow-hidden rounded-md border">
              {(["text", "markdown"] as TextViewMode[]).map((option) => (
                <Button
                  key={option}
                  type="button"
                  variant={mode === option ? "secondary" : "ghost"}
                  size="sm"
                  className="rounded-none border-0 capitalize"
                  onClick={() => setMode(option)}
                >
                  {option}
                </Button>
              ))}
            </div>
            <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={onClose}>
              <X className="h-4 w-4" />
              Close
            </Button>
          </div>
        </div>
        <div className="chat-scrollbar min-h-0 flex-1 overflow-auto bg-background/70 p-5">
          {mode === "markdown" ? (
            <div className="prose max-w-none text-[15px] leading-7 dark:prose-invert">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{viewer.content}</ReactMarkdown>
            </div>
          ) : (
            <pre className="whitespace-pre-wrap font-mono text-sm leading-7 text-foreground">
              {viewer.content}
            </pre>
          )}
        </div>
      </motion.aside>
    </div>
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
            <div className="flex flex-wrap items-center gap-1 rounded-md border bg-secondary/25 p-1">
              <span className="flex items-center gap-1 px-2 text-xs font-semibold text-muted-foreground">
                Split Data
                <Info className="h-3.5 w-3.5" />
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                title="Shuffle selected cases by seed, then apply the default train/val/test counts."
                onClick={() => props.onAutoSplit("random")}
              >
                Random
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                title="Keep each split balanced by overall outcome so Meets and Does Not Meet examples are represented."
                onClick={() => props.onAutoSplit("outcome")}
              >
                Outcome
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                title="Balance by overall outcome first, then spread higher issue/driver-count cases across train, val, and test."
                onClick={() => props.onAutoSplit("outcome_issues")}
              >
                Outcome + Issues
              </Button>
            </div>
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
  if (artifact?.nodes.length) {
    const artifactGraph = buildArtifactCandidateGraph(artifact, run, events);
    return layoutGraph(artifactGraph.nodes, artifactGraph.edges);
  }
  if (!run) return { nodes: [], edges: [] };
  const runGraph = buildRunCandidateGraph(run, events);
  return runGraph.nodes.length ? layoutGraph(runGraph.nodes, runGraph.edges) : runGraph;
}

function buildArtifactCandidateGraph(
  artifact: OptimizationDagArtifact,
  run: OptimizationRunRecord | null,
  events: OptimizationEventRecord[],
): { nodes: Node<CandidateNodeData>[]; edges: Edge[] } {
  const eventsByCandidate = eventsByCandidateIndex(events);
  const paretoFront = new Set(artifact.pareto_front);
  const finalIndex = maxCandidateIndex(artifact.nodes.map((node) => node.candidate_index));
  const progress = progressFromRun(run, events);
  const nodes: Node<CandidateNodeData>[] = artifact.nodes.map((node) => {
    const relatedEvents = eventsByCandidate.get(node.candidate_index) ?? [];
    const role = candidateRole(node.candidate_index, node.role, artifact.best_idx, paretoFront, finalIndex);
    return candidateNode({
      id: node.id,
      index: node.candidate_index,
      role,
      status: candidateStatus(role),
      score: node.score ?? scoreFromCandidateEvents(relatedEvents),
      candidate: node.candidate,
      parentIds: node.parents,
      events: relatedEvents,
      progress,
      message: candidateMessage(node.candidate_index, role, node.parents, relatedEvents),
    });
  });
  return {
    nodes,
    edges: artifact.edges.map((edge) => ({
      ...edge,
      animated: false,
      style: { strokeWidth: 2 },
    })),
  };
}

function buildRunCandidateGraph(
  run: OptimizationRunRecord,
  events: OptimizationEventRecord[],
): { nodes: Node<CandidateNodeData>[]; edges: Edge[] } {
  const eventsByCandidate = eventsByCandidateIndex(events);
  const bestIndex = bestCandidateIndexFromEvents(events, run);
  const paretoFront = latestParetoFront(events);
  const finalIndex = maxCandidateIndex((run.candidates ?? []).map((candidate) => candidate.candidate_index));
  const currentIndex = ["queued", "running"].includes(run.status) ? currentSelectedCandidateIndex(events) : null;
  const progress = progressFromRun(run, events);
  const records = [...(run.candidates ?? [])].sort((first, second) => first.candidate_index - second.candidate_index);
  const nodesById = new Map<string, Node<CandidateNodeData>>();
  const seedRecord = records.find((record) => record.candidate_index === 0);
  const seedEvent = events.find((event) => event.type === "run_started") ?? events.find((event) => event.type === "run_prepared");
  const seedCandidate =
    seedRecord?.candidate ??
    run.seed_candidate ??
    candidateFromUnknown(seedEvent?.data?.seed_candidate);

  if (seedCandidate || seedEvent) {
    const relatedEvents = eventsByCandidate.get(0) ?? [];
    const role = candidateRole(0, "seed", bestIndex, paretoFront, finalIndex);
    const status = currentIndex === 0 ? "selected" : candidateStatus(role);
    nodesById.set(
      "0",
      candidateNode({
        id: "0",
        index: 0,
        role,
        status,
        score: seedRecord?.score ?? run.original_score ?? scoreFromCandidateEvents(relatedEvents),
        candidate: seedCandidate ?? {},
        parentIds: seedRecord?.parent_indices ?? [null],
        events: relatedEvents,
        progress,
        message: candidateMessage(0, role, seedRecord?.parent_indices ?? [null], relatedEvents),
      }),
    );
  }

  for (const record of records) {
    if (!Number.isFinite(record.candidate_index)) continue;
    if (record.candidate_index === 0 && nodesById.has("0")) continue;
    const relatedEvents = eventsByCandidate.get(record.candidate_index) ?? [];
    const role = candidateRole(record.candidate_index, record.status, bestIndex, paretoFront, finalIndex);
    const status = currentIndex === record.candidate_index ? "selected" : candidateStatus(role);
    nodesById.set(
      String(record.candidate_index),
      candidateNode({
        id: String(record.candidate_index),
        index: record.candidate_index,
        role,
        status,
        score: record.score ?? scoreFromCandidateEvents(relatedEvents),
        candidate: record.candidate,
        parentIds: record.parent_indices,
        events: relatedEvents,
        progress,
        message: candidateMessage(record.candidate_index, role, record.parent_indices, relatedEvents),
      }),
    );
  }

  for (const draft of runtimeCandidateDraftsFromEvents(events, nodesById, bestIndex, paretoFront)) {
    nodesById.set(
      draft.id,
      candidateNode({
        id: draft.id,
        index: draft.candidateIndex,
        role: draft.role,
        status: draft.status,
        title: draft.title,
        label: draft.label,
        score: draft.score,
        candidate: draft.candidate,
        parentIds: draft.parentIds,
        events: draft.events,
        progress,
        message: draft.message,
      }),
    );
  }

  return {
    nodes: [...nodesById.values()],
    edges: lineageEdges([...nodesById.values()], run.status === "queued" || run.status === "running"),
  };
}

function runtimeCandidateDraftsFromEvents(
  events: OptimizationEventRecord[],
  nodesById: Map<string, Node<CandidateNodeData>>,
  bestIndex: number | null,
  paretoFront: Set<number>,
): RuntimeCandidateDraft[] {
  const selectedByIteration = new Map<number, number>();
  const acceptedByIteration = new Map<number, OptimizationEventRecord>();
  const rejectedByIteration = new Map<number, OptimizationEventRecord>();
  const proposalByIteration = new Map<number, OptimizationEventRecord>();
  const iterations = new Set<number>();
  for (const event of events) {
    if (typeof event.iteration !== "number") continue;
    iterations.add(event.iteration);
    const selectedIndex = numberFromUnknown(event.data?.candidate_idx);
    if (event.type === "candidate_selected" && selectedIndex !== null) {
      selectedByIteration.set(event.iteration, selectedIndex);
    }
    if (event.type === "proposal_created") proposalByIteration.set(event.iteration, event);
    if (event.type === "candidate_accepted" || event.type === "merge_accepted") {
      acceptedByIteration.set(event.iteration, event);
    }
    if (event.type === "candidate_rejected" || event.type === "merge_rejected") {
      rejectedByIteration.set(event.iteration, event);
    }
  }

  const activeIteration = [...events]
    .reverse()
    .find((event) => typeof event.iteration === "number" && !acceptedByIteration.has(event.iteration) && !rejectedByIteration.has(event.iteration))
    ?.iteration;

  const drafts: RuntimeCandidateDraft[] = [];
  for (const iteration of [...iterations].sort((first, second) => first - second)) {
    const iterationEvents = events.filter((event) => event.iteration === iteration);
    if (!iterationEvents.length) continue;
    const accepted = acceptedByIteration.get(iteration);
    const rejected = rejectedByIteration.get(iteration);
    const proposal = proposalByIteration.get(iteration);
    const sourceEvent = accepted ?? rejected ?? (iteration === activeIteration ? iterationEvents[iterationEvents.length - 1] : null);
    if (!sourceEvent) continue;

    const acceptedIndex = numberFromUnknown(accepted?.data?.new_candidate_idx);
    const id = acceptedIndex !== null ? String(acceptedIndex) : rejected ? `rejected-${iteration}` : `proposal-${iteration}`;
    if (nodesById.has(id)) continue;
    const parentIds = parentIdsFromEvent(sourceEvent, selectedByIteration.get(iteration));
    const role = acceptedIndex !== null
      ? candidateRole(acceptedIndex, "accepted", bestIndex, paretoFront, null)
      : rejected
        ? "rejected"
        : "current";
    const status = acceptedIndex !== null
      ? candidateStatus(role)
      : rejected
        ? "rejected"
        : statusFromIterationEvents(iterationEvents);
    const candidate =
      candidateFromUnknown(proposal?.data?.new_instructions) ??
      candidateFromUnknown(sourceEvent.data?.new_instructions) ??
      candidateFromUnknown(sourceEvent.data?.candidate) ??
      candidateFromUnknown(sourceEvent.data?.merged_candidate) ??
      {};
    const score =
      numberFromUnknown(sourceEvent.data?.new_score) ??
      numberFromUnknown(sourceEvent.data?.average_score) ??
      averageFromUnknownScores(sourceEvent.data?.scores);
    drafts.push({
      id,
      candidateIndex: acceptedIndex,
      role,
      status,
      title: acceptedIndex !== null ? `Candidate ${acceptedIndex}` : `Iteration ${iteration} Proposal`,
      label: acceptedIndex !== null ? `candidate ${acceptedIndex}` : `iteration ${iteration}`,
      score,
      candidate,
      parentIds,
      events: iterationEvents,
      message: sourceEvent.message || candidateMessage(acceptedIndex ?? iteration, role, parentIds, iterationEvents),
    });
  }
  return drafts;
}

function candidateNode({
  id,
  index,
  role,
  status,
  title,
  label,
  score,
  candidate,
  parentIds,
  events,
  progress,
  message,
}: {
  id: string;
  index: number | null;
  role: string;
  status: string;
  title?: string;
  label?: string;
  score?: number | null;
  candidate: Record<string, string>;
  parentIds: Array<number | null>;
  events: OptimizationEventRecord[];
  progress: RunProgress | null;
  message: string;
}): Node<CandidateNodeData> {
  const proposal = [...events].reverse().find((event) => event.type === "proposal_created");
  return {
    id,
    type: "candidate",
    data: {
      label: label ?? (index === 0 ? "seed" : `candidate ${index ?? "-"}`),
      title: title ?? (index === 0 ? "Seed Candidate" : `Candidate ${index ?? "-"}`),
      role,
      status,
      score,
      candidateIndex: index,
      parentIds,
      validationSize: validationSizeFromEvents(events),
      candidate,
      proposedInstructions: candidateFromUnknown(proposal?.data?.new_instructions),
      message,
      progress,
      event: events[events.length - 1],
      events,
    },
    position: { x: 0, y: 0 },
  };
}

function lineageEdges(nodes: Node<CandidateNodeData>[], animated: boolean): Edge[] {
  const ids = new Set(nodes.map((node) => node.id));
  const edges: Edge[] = [];
  for (const node of nodes) {
    for (const parent of node.data.parentIds ?? []) {
      if (parent === null) continue;
      const source = String(parent);
      if (!ids.has(source) || source === node.id) continue;
      edges.push({
        id: `${source}-${node.id}`,
        source,
        target: node.id,
        animated,
        style: { strokeWidth: 2 },
      });
    }
  }
  return edges;
}

function eventsByCandidateIndex(events: OptimizationEventRecord[]): Map<number, OptimizationEventRecord[]> {
  const acceptedByIteration = new Map<number, number>();
  const selectedByIteration = new Map<number, number>();
  for (const event of events) {
    if (typeof event.iteration !== "number") continue;
    const newIndex = numberFromUnknown(event.data?.new_candidate_idx);
    if ((event.type === "candidate_accepted" || event.type === "merge_accepted") && newIndex !== null) {
      acceptedByIteration.set(event.iteration, newIndex);
    }
    const selectedIndex = numberFromUnknown(event.data?.candidate_idx);
    if (event.type === "candidate_selected" && selectedIndex !== null) {
      selectedByIteration.set(event.iteration, selectedIndex);
    }
  }

  const scopedTypes = new Set([
    "budget_updated",
    "candidate_rejected",
    "evaluation_completed",
    "evaluation_skipped",
    "evaluation_started",
    "iteration_completed",
    "iteration_started",
    "merge_rejected",
    "minibatch_sampled",
    "proposal_created",
    "proposal_started",
    "reflective_dataset_built",
  ]);
  const output = new Map<number, OptimizationEventRecord[]>();
  const add = (index: number | null, event: OptimizationEventRecord) => {
    if (index === null || !Number.isFinite(index)) return;
    output.set(index, [...(output.get(index) ?? []), event]);
  };

  for (const event of events) {
    if (event.type === "run_started" || event.type === "run_prepared") {
      add(0, event);
      continue;
    }
    if (typeof event.iteration === "number" && scopedTypes.has(event.type)) {
      add(acceptedByIteration.get(event.iteration) ?? selectedByIteration.get(event.iteration) ?? null, event);
      continue;
    }
    const newIndex = numberFromUnknown(event.data?.new_candidate_idx);
    if (newIndex !== null) {
      add(newIndex, event);
      continue;
    }
    const candidateIndex = numberFromUnknown(event.data?.candidate_idx);
    if (candidateIndex !== null) {
      add(candidateIndex, event);
    }
  }
  return output;
}

function candidateRole(
  index: number,
  sourceRole: string | undefined,
  bestIndex: number | null,
  paretoFront: Set<number>,
  finalIndex: number | null,
): string {
  if (bestIndex === index) return "best";
  if (finalIndex === index && index !== 0) return "final";
  if (paretoFront.has(index)) return "pareto";
  if (index === 0) return "seed";
  if (sourceRole === "accepted" || sourceRole === "candidate" || sourceRole === "pareto" || sourceRole === "best") {
    return sourceRole;
  }
  return "candidate";
}

function candidateStatus(role: string): string {
  if (role === "best") return "best";
  if (role === "pareto") return "pareto";
  if (role === "final") return "final";
  if (role === "seed") return "seed";
  if (role === "errored") return "error";
  return "candidate";
}

function candidateMessage(
  index: number,
  role: string,
  parents: Array<number | null>,
  events: OptimizationEventRecord[],
): string {
  const latest = latestEventOfTypes(
    events,
    "validation_evaluated",
    "candidate_accepted",
    "merge_accepted",
    "candidate_rejected",
    "merge_rejected",
    "proposal_created",
    "evaluation_completed",
    "candidate_selected",
  );
  if (latest?.message) return latest.message;
  const parentCount = parents.filter((item) => item !== null).length;
  if (role === "best") return `Best candidate with ${parentCount || 0} parent link(s).`;
  if (role === "pareto") return `Pareto-front candidate with ${parentCount || 0} parent link(s).`;
  if (index === 0) return "Initial seed prompt candidate.";
  return `Candidate ${index} with ${parentCount || 0} parent link(s).`;
}

function latestEventOfTypes(events: OptimizationEventRecord[], ...types: string[]): OptimizationEventRecord | undefined {
  return [...events].reverse().find((event) => types.includes(event.type));
}

function scoreFromCandidateEvents(events: OptimizationEventRecord[]): number | null {
  const validationScore = numberFromUnknown(latestEventOfTypes(events, "validation_evaluated")?.data?.average_score);
  if (validationScore !== null) return validationScore;
  const evaluationScore = averageFromUnknownScores(latestEventOfTypes(events, "evaluation_completed")?.data?.scores);
  if (evaluationScore !== null) return evaluationScore;
  return numberFromUnknown(latestEventOfTypes(events, "candidate_accepted", "merge_accepted")?.data?.new_score);
}

function validationSizeFromEvents(events: OptimizationEventRecord[]): number | null {
  return numberFromUnknown(latestEventOfTypes(events, "validation_evaluated")?.data?.num_examples_evaluated);
}

function bestCandidateIndexFromEvents(events: OptimizationEventRecord[], run: OptimizationRunRecord): number | null {
  const bestEvent = [...events]
    .reverse()
    .find((event) => event.type === "validation_evaluated" && event.data?.is_best_program === true);
  const eventIndex = numberFromUnknown(bestEvent?.data?.candidate_idx);
  if (eventIndex !== null) return eventIndex;
  if (run.best_score === null || run.best_score === undefined) return null;
  const match = run.candidates.find((candidate) => candidate.score === run.best_score);
  return match?.candidate_index ?? null;
}

function latestParetoFront(events: OptimizationEventRecord[]): Set<number> {
  const event = [...events].reverse().find((item) => item.type === "pareto_front_updated");
  const front = Array.isArray(event?.data?.new_front) ? event.data.new_front : [];
  return new Set(front.filter((item): item is number => typeof item === "number" && Number.isFinite(item)));
}

function maxCandidateIndex(indexes: number[]): number | null {
  const finiteIndexes = indexes.filter((item) => Number.isFinite(item));
  return finiteIndexes.length ? Math.max(...finiteIndexes) : null;
}

function currentSelectedCandidateIndex(events: OptimizationEventRecord[]): number | null {
  const event = [...events].reverse().find((item) => item.type === "candidate_selected");
  return numberFromUnknown(event?.data?.candidate_idx);
}

function parentIdsFromEvent(
  event: OptimizationEventRecord,
  selectedParent?: number,
): Array<number | null> {
  const directParents = arrayOfNumbersOrNull(event.data?.parent_ids);
  if (directParents.length) return directParents;
  const fallbackCandidate = numberFromUnknown(event.data?.candidate_idx);
  if (fallbackCandidate !== null) return [fallbackCandidate];
  return typeof selectedParent === "number" ? [selectedParent] : [0];
}

function statusFromIterationEvents(events: OptimizationEventRecord[]): string {
  const latest = events[events.length - 1];
  if (!latest) return "candidate";
  if (latest.type === "proposal_started" || latest.type === "reflective_dataset_built") return "reflecting";
  if (latest.type === "proposal_created") return "proposed";
  if (latest.type === "evaluation_started") return "evaluating";
  if (latest.type === "evaluation_completed") return "evaluated";
  return latest.type.replaceAll("_", " ");
}

function formatReflectionDetails(events: OptimizationEventRecord[]): string {
  const sections: string[] = [];
  for (const event of events) {
    if (event.type === "reflective_dataset_built") {
      sections.push(formatReflectiveDataset(event));
    } else if (event.type === "proposal_started") {
      sections.push(`Proposal input\n${formatUnknownForDisplay(event.data, 12000)}`);
    } else if (event.type === "proposal_created") {
      const proposal = candidateFromUnknown(event.data?.new_instructions);
      sections.push(
        proposal?.instructions
          ? `Proposed instructions\n${proposal.instructions}`
          : `Proposed text\n${formatUnknownForDisplay(event.data, 12000)}`,
      );
    } else if (event.type === "evaluation_completed") {
      sections.push(formatEvaluationSummary(event));
    }
  }
  return sections.filter(Boolean).join("\n\n---\n\n");
}

function formatReflectiveDataset(event: OptimizationEventRecord): string {
  const dataset = recordFromUnknown(event.data?.dataset) ?? recordFromUnknown(event.data?.reflective_dataset);
  const traces = Array.isArray(dataset?.traces) ? dataset.traces : null;
  if (!traces) {
    return `Reflective dataset\n${formatUnknownForDisplay(dataset ?? event.data, 16000)}`;
  }
  const traceSummaries = traces.slice(0, 8).map((item, index) => {
    const record = recordFromUnknown(item);
    if (!record) return `Trace ${index + 1}\n${formatUnknownForDisplay(item, 3000)}`;
    const trace = recordFromUnknown(record.trace);
    const caseId = stringFromUnknown(record.case_id);
    const feedback = stringFromUnknown(record.feedback);
    const parts = [
      `Trace ${index + 1}${caseId ? ` (${caseId})` : ""}`,
      `Score: ${formatScore(numberFromUnknown(record.score))}`,
      `Success: ${record.success === true ? "yes" : record.success === false ? "no" : "-"}`,
    ];
    if (feedback) parts.push(`Metric feedback:\n${feedback}`);
    if (trace) parts.push(`Trajectory:\n${formatUnknownForDisplay(compactTrajectory(trace), 6000)}`);
    return parts.join("\n");
  });
  const omitted = traces.length > traceSummaries.length ? `\n\n[${traces.length - traceSummaries.length} additional traces omitted]` : "";
  return `Reflective dataset (${traces.length} trace${traces.length === 1 ? "" : "s"})\n\n${traceSummaries.join("\n\n")}${omitted}`;
}

function formatEvaluationSummary(event: OptimizationEventRecord): string {
  const summary = {
    scores: event.data?.scores,
    objective_scores: event.data?.objective_scores,
    parent_ids: event.data?.parent_ids,
    has_trajectories: event.data?.has_trajectories,
    average_score: averageFromUnknownScores(event.data?.scores),
  };
  return `Metric feedback / rollout summary\n${formatUnknownForDisplay(summary, 6000)}`;
}

function compactTrajectory(trace: Record<string, unknown>): Record<string, unknown> {
  const keys = [
    "claim_number",
    "prompt",
    "generated_output",
    "error",
    "elapsed_seconds",
    "usage",
    "messages",
  ];
  return Object.fromEntries(
    keys
      .filter((key) => key in trace)
      .map((key) => [key, key === "generated_output" ? stripHiddenAuditOutput(trace[key]) : trace[key]]),
  );
}

function stripHiddenAuditOutput(value: unknown): unknown {
  const record = recordFromUnknown(value);
  if (!record) return value;
  const output = { ...record };
  for (const key of ["id", "cost", "image_cost", "latency", "ground_truth", "extras"]) {
    delete output[key];
  }
  if (Array.isArray(output.questions)) {
    output.questions = output.questions.map((question) => {
      const questionRecord = recordFromUnknown(question);
      if (!questionRecord) return question;
      const nextQuestion = { ...questionRecord };
      delete nextQuestion.help_text;
      if (Array.isArray(nextQuestion.sub_questions)) {
        nextQuestion.sub_questions = nextQuestion.sub_questions.map((subQuestion) => {
          const subQuestionRecord = recordFromUnknown(subQuestion);
          if (!subQuestionRecord) return subQuestion;
          const nextSubQuestion = { ...subQuestionRecord };
          delete nextSubQuestion.answer;
          delete nextSubQuestion.help_text;
          return nextSubQuestion;
        });
      }
      return nextQuestion;
    });
  }
  return output;
}

function formatUnknownForDisplay(value: unknown, maxChars = 16000): string {
  let text: string;
  if (typeof value === "string") {
    text = value;
  } else {
    try {
      text = JSON.stringify(value, null, 2) ?? String(value);
    } catch {
      text = String(value);
    }
  }
  if (text.length <= maxChars) return text;
  return `${text.slice(0, maxChars)}\n\n[truncated ${text.length - maxChars} characters]`;
}

function stringFromUnknown(value: unknown): string {
  return typeof value === "string" ? value : "";
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
  const positioned = nodes.map((node) => {
    const position = graph.node(node.id);
    return {
      ...node,
      position: { x: position.x - nodeWidth / 2, y: position.y - nodeHeight / 2 },
    };
  });
  const minX = Math.min(...positioned.map((node) => node.position.x));
  const maxX = Math.max(...positioned.map((node) => node.position.x + nodeWidth));
  const minY = Math.min(...positioned.map((node) => node.position.y));
  const centerX = (minX + maxX) / 2;
  return {
    nodes: positioned.map((node) => ({
      ...node,
      position: { x: node.position.x - centerX, y: node.position.y - minY },
    })),
    edges,
  };
}

function nodeColor(role: string): string {
  if (role === "best") return "#f59e0b";
  if (role === "pareto") return "#f59e0b";
  if (role === "final") return "#fb7185";
  if (role === "accepted" || role === "current") return "#059669";
  if (role === "rejected" || role === "errored") return "#dc2626";
  if (role === "seed") return "#64748b";
  return "#94a3b8";
}

function nodeStrokeColor(role: string): string {
  if (role === "best") return "#facc15";
  if (role === "pareto") return "#f59e0b";
  if (role === "final") return "#e11d48";
  if (role === "seed") return "#cbd5e1";
  return "#0f172a";
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
