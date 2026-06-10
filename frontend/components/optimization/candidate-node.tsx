"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { CheckCircle2, CircleDot, Trophy, XCircle } from "lucide-react";
import { motion } from "motion/react";

import { Badge } from "@/components/ui/badge";
import type { OptimizationEventRecord } from "@/lib/types";

export type RunProgress = {
  used: number;
  total: number | null;
  remaining: number | null;
  percent: number | null;
};

export type CandidateNodeData = {
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

export function formatParentIds(value?: Array<number | null>): string {
  const parents = (value ?? []).filter(
    (item): item is number => typeof item === "number" && Number.isFinite(item),
  );
  return parents.length ? parents.join(", ") : "-";
}

export function reflectionStatsFromEvents(
  events: OptimizationEventRecord[],
): { batches: number; trajectories: number } {
  let batches = 0;
  let trajectories = 0;
  for (const event of events) {
    if (event.type !== "reflective_dataset_built") continue;
    batches += 1;
    const dataset = recordFromUnknown(event.data?.dataset) ?? recordFromUnknown(event.data?.reflective_dataset);
    const traces = Array.isArray(dataset?.traces) ? dataset.traces : [];
    trajectories += traces.length;
  }
  return { batches, trajectories };
}

function recordFromUnknown(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function formatScore(value?: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function CandidateNode({ data }: NodeProps<Node<CandidateNodeData>>) {
  const isBest = data.role === "best";
  const isPareto = data.role === "pareto";
  const isSeed = data.role === "seed";
  const isFinal = data.role === "final";
  const isRejected = data.role === "rejected" || data.role === "errored";
  const isCurrent =
    data.status === "selected" || data.status === "evaluating" || data.role === "current";
  const isAccepted = data.role === "accepted" || isBest || isPareto;
  const parentText = formatParentIds(data.parentIds);
  const reflectionStats = reflectionStatsFromEvents(data.events ?? []);
  const thirdStatLabel =
    reflectionStats.trajectories > 0 ? "traj" : data.validationSize ? "val" : "events";
  const thirdStatValue =
    reflectionStats.trajectories > 0
      ? String(reflectionStats.trajectories)
      : data.validationSize
        ? String(data.validationSize)
        : String(data.events?.length ?? "-");
  const accentClass = isBest
    ? "border-amber-400 bg-gradient-to-br from-amber-50 to-yellow-100 text-amber-950 shadow-lg shadow-amber-500/20 ring-2 ring-amber-300/60 dark:from-amber-950/50 dark:to-yellow-950/25 dark:text-amber-50"
    : isPareto
      ? "border-amber-400 bg-amber-50 text-amber-950 dark:bg-amber-950/25 dark:text-amber-50"
      : isFinal
        ? "border-rose-400 bg-rose-50 text-rose-950 shadow-rose-500/10 dark:bg-rose-950/25 dark:text-rose-50"
        : isCurrent
          ? "border-primary/80 bg-primary/10 text-card-foreground shadow-primary/10"
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
          ) : isFinal ? (
            <CircleDot className="h-4 w-4 shrink-0 text-rose-600" />
          ) : isAccepted || isCurrent ? (
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
          ) : (
            <CircleDot className="h-4 w-4 shrink-0 text-primary" />
          )}
          <p className="truncate text-sm font-semibold">{data.title}</p>
        </div>
        <Badge
          variant={
            isBest || isPareto
              ? "warning"
              : isAccepted
                ? "success"
                : isRejected || isFinal
                  ? "danger"
                  : "outline"
          }
          className="shrink-0 text-[10px]"
        >
          {data.status}
        </Badge>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <div>
          <p className="text-[10px] uppercase opacity-65">score</p>
          <p className="font-mono font-semibold">{formatScore(data.score)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase opacity-65">parent</p>
          <p className="truncate font-mono font-semibold" title={parentText}>
            {parentText}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase opacity-65">{thirdStatLabel}</p>
          <p className="font-mono font-semibold">{thirdStatValue}</p>
        </div>
      </div>
      <p className="mt-3 line-clamp-2 min-h-[32px] text-xs leading-relaxed opacity-80">
        {data.message ??
          data.candidate?.instructions ??
          data.event?.message ??
          "Waiting for GEPA callback data."}
      </p>
      <div className="mt-3 flex items-center justify-between gap-2 text-[10px] uppercase opacity-65">
        <span>{data.label}</span>
        <span>
          {progressText
            ? `${progressText} calls`
            : data.events?.length
              ? `${data.events.length} callbacks`
              : ""}
        </span>
      </div>
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !bg-primary" />
    </motion.div>
  );
}

export const nodeTypes = { candidate: CandidateNode };
