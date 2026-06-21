"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Database,
  Eye,
  FileText,
  RefreshCw,
  Search,
  Split,
  X,
} from "lucide-react";

import {
  getObservabilityFacets,
  getObservabilityTrace,
  getObservabilityTraceTree,
  listObservabilityArtifacts,
  listObservabilityTraces,
} from "@/lib/api";
import type {
  AuditArtifactRecord,
  AuditObservabilityFacets,
  AuditSpanRecord,
  AuditTraceDetail,
  AuditTraceRecord,
  AuditTraceTreeNode,
  ObservabilityTraceSearchParams,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const EMPTY_FILTERS: ObservabilityTraceSearchParams = {
  limit: 50,
  offset: 0,
};

const DEFAULT_FACETS: AuditObservabilityFacets = {
  sources: [
    "api",
    "batch",
    "batch_manual",
    "batch_upload",
    "chat_tool",
    "completed_intake",
    "eval",
    "manual_entry",
    "optimization",
    "synthetic",
  ],
  agent_names: ["audit_form_agent", "coverage_sub_agent", "optimization_audit_generation"],
  model_names: [],
  status_codes: ["OK", "ERROR", "UNSET"],
};

const SPAN_TREE_PAGE_SIZES = [5, 10, 25, 50, 100, 200];

interface SpanTreeRowData {
  span: AuditSpanRecord;
  depth: number;
  hasToolCalls?: boolean;
  isExpanded?: boolean;
  toolCallCount?: number;
}

interface ModelToolCall {
  id: string;
  name: string;
  index: number;
  argumentsValue?: unknown;
  raw: unknown;
}

function statusVariant(status: string, errorCount = 0): "success" | "danger" | "secondary" {
  if (status === "ERROR" || errorCount > 0) return "danger";
  if (status === "OK") return "success";
  return "secondary";
}

function formatDate(value?: string | null): string {
  if (!value) return "NA";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function formatDuration(value?: number | null): string {
  if (value === null || value === undefined) return "NA";
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

function compactId(value?: string | null): string {
  if (!value) return "NA";
  return value.length > 12 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value;
}

function joined(values: string[]): string {
  return values.length ? values.join(", ") : "NA";
}

function filterPayload(filters: ObservabilityTraceSearchParams): ObservabilityTraceSearchParams {
  return {
    ...filters,
    started_at_from: localDateTimeToIso(filters.started_at_from),
    started_at_to: localDateTimeToIso(filters.started_at_to),
    limit: filters.limit ?? 50,
    offset: filters.offset ?? 0,
  };
}

function localDateTimeToIso(value?: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

function splitFilterValue(value?: string): string[] {
  return (value ?? "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function joinFilterValue(values: string[]): string {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean))).join(", ");
}

function mergeFacetValues(defaults: string[], dynamic: string[]): string[] {
  return Array.from(new Set([...defaults, ...dynamic].filter(Boolean))).sort((a, b) =>
    a.localeCompare(b),
  );
}

function childClaimMatchLabel(trace: AuditTraceRecord, claimFilter?: string): string {
  const traceClaim = trace.claim_number.toLowerCase();
  const term = splitFilterValue(claimFilter).find(
    (value) => !traceClaim.includes(value.toLowerCase()),
  );
  return term ?? "";
}

function isDbSpan(span: AuditSpanRecord): boolean {
  const attributes = span.attributes ?? {};
  const name = span.name.toLowerCase();
  return (
    span.span_type === "db" ||
    Boolean(
      attributes["db.system"] ||
        attributes["db.statement"] ||
        attributes["db.operation"] ||
        attributes["db.operation.name"] ||
        attributes["db.query.text"] ||
        attributes["db.name"] ||
        attributes["db.namespace"],
    ) ||
    /^(select|insert|update|delete|commit|rollback)\b/.test(name)
  );
}

function isOutputMessagesArtifact(artifact: AuditArtifactRecord): boolean {
  return (
    artifact.artifact_type === "llm_output_messages" ||
    artifact.artifact_key === "gen_ai.output.messages"
  );
}

function parseJson(value: string): unknown | null {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function normalizeToolArguments(value: unknown): unknown {
  if (typeof value !== "string") return value;
  return parseJson(value) ?? value;
}

function extractToolCallsFromPayload(payload: unknown): ModelToolCall[] {
  const messages = Array.isArray(payload) ? payload : [payload];
  const calls: ModelToolCall[] = [];
  messages.forEach((message) => {
    if (!message || typeof message !== "object") return;
    const record = message as Record<string, unknown>;
    const directCalls = Array.isArray(record.tool_calls) ? record.tool_calls : [];
    const parts = Array.isArray(record.parts) ? record.parts : [];
    [...directCalls, ...parts].forEach((part) => {
      if (!part || typeof part !== "object") return;
      const partRecord = part as Record<string, unknown>;
      if (partRecord.type !== "tool_call" && !partRecord.function) return;
      const functionRecord =
        partRecord.function && typeof partRecord.function === "object"
          ? (partRecord.function as Record<string, unknown>)
          : {};
      const name = String(partRecord.name ?? functionRecord.name ?? "tool_call");
      const id = String(partRecord.id ?? `tool_call_${calls.length + 1}`);
      const argumentsValue = normalizeToolArguments(
        partRecord.arguments ?? functionRecord.arguments ?? partRecord.args,
      );
      calls.push({
        id,
        name,
        index: calls.length,
        argumentsValue,
        raw: partRecord,
      });
    });
  });
  return calls;
}

function extractToolCallsFromText(value: string): ModelToolCall[] {
  const parsed = parseJson(value);
  if (parsed !== null) return extractToolCallsFromPayload(parsed);

  const calls: ModelToolCall[] = [];
  const pattern =
    /"type"\s*:\s*"tool_call"[\s\S]*?"id"\s*:\s*"([^"]+)"[\s\S]*?"name"\s*:\s*"([^"]+)"/g;
  let match = pattern.exec(value);
  while (match) {
    calls.push({
      id: match[1],
      name: match[2],
      index: calls.length,
      raw: value,
    });
    match = pattern.exec(value);
  }
  return calls;
}

function buildToolCallsBySpanId(
  artifacts: AuditArtifactRecord[],
): Map<string, ModelToolCall[]> {
  const callsBySpanId = new Map<string, ModelToolCall[]>();
  artifacts.forEach((artifact) => {
    if (!artifact.span_id) return;
    if (
      artifact.artifact_type !== "llm_output_messages" &&
      artifact.artifact_key !== "gen_ai.output.messages"
    ) {
      return;
    }
    const text = artifact.content_text || artifact.content_preview;
    if (!text) return;
    const calls = extractToolCallsFromText(text);
    if (!calls.length) return;
    callsBySpanId.set(artifact.span_id, [
      ...(callsBySpanId.get(artifact.span_id) ?? []),
      ...calls,
    ]);
  });
  return callsBySpanId;
}

function toolCallToSpan(parent: AuditSpanRecord, call: ModelToolCall): AuditSpanRecord {
  return {
    ...parent,
    span_id: `${parent.span_id}:tool_call:${call.index}`,
    parent_span_id: parent.span_id,
    name: `tool call ${call.name}`,
    kind: "INTERNAL",
    span_type: "tool_call",
    tool_name: call.name,
    duration_ms: null,
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
    attributes: {
      "gen_ai.operation.name": "tool_call",
      "gen_ai.tool.call.id": call.id,
      "gen_ai.tool.name": call.name,
      "gen_ai.tool.arguments": call.argumentsValue,
      raw: call.raw,
      virtual: true,
    },
  };
}

function flattenSpanTree(
  tree: AuditTraceTreeNode[],
  includeDbSpans: boolean,
  toolCallsBySpanId: Map<string, ModelToolCall[]>,
  expandedToolCallRows: Set<string>,
  depth = 0,
): SpanTreeRowData[] {
  return tree.flatMap((node) => {
    const hiddenDbSpan = !includeDbSpans && isDbSpan(node.span);
    const toolCalls = toolCallsBySpanId.get(node.span.span_id) ?? [];
    const isExpanded = expandedToolCallRows.has(node.span.span_id);
    const rows = hiddenDbSpan
      ? []
      : [
          {
            span: node.span,
            depth,
            hasToolCalls: toolCalls.length > 0,
            isExpanded,
            toolCallCount: toolCalls.length,
          },
          ...(isExpanded
            ? toolCalls.map((call) => ({
                span: toolCallToSpan(node.span, call),
                depth: depth + 1,
              }))
            : []),
        ];
    return [
      ...rows,
      ...flattenSpanTree(
        node.children,
        includeDbSpans,
        toolCallsBySpanId,
        expandedToolCallRows,
        hiddenDbSpan ? depth : depth + 1,
      ),
    ];
  });
}

function SpanTreeRow({
  row,
  selectedSpanId,
  onSelect,
  onToggleToolCalls,
}: {
  row: SpanTreeRowData;
  selectedSpanId: string;
  onSelect: (span: AuditSpanRecord) => void;
  onToggleToolCalls: (spanId: string) => void;
}) {
  const { span, depth, hasToolCalls, isExpanded, toolCallCount } = row;
  return (
    <div
      role="button"
      tabIndex={0}
      className={cn(
        "grid w-full grid-cols-[minmax(0,1fr)_84px_84px_72px] items-center gap-2 border-b px-3 py-2 text-left text-xs transition-colors hover:bg-secondary/60",
        selectedSpanId === span.span_id && "bg-secondary",
      )}
      onClick={() => onSelect(span)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") onSelect(span);
      }}
    >
      <span className="flex min-w-0 items-center gap-2" style={{ paddingLeft: depth * 16 }}>
        {hasToolCalls ? (
          <button
            type="button"
            className="flex h-5 w-5 shrink-0 items-center justify-center rounded hover:bg-background"
            onClick={(event) => {
              event.stopPropagation();
              onToggleToolCalls(span.span_id);
            }}
            title={isExpanded ? "Collapse tool calls" : "Expand tool calls"}
          >
            {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </button>
        ) : (
          <span className="h-5 w-5 shrink-0" />
        )}
        <span
          className={cn(
            "h-2 w-2 rounded-full",
            span.status_code === "ERROR"
              ? "bg-destructive"
              : span.span_type === "tool_call"
                ? "bg-amber-400"
                : "bg-primary",
          )}
        />
        <span className="min-w-0 truncate font-medium">
          {span.name || span.span_id}
          {hasToolCalls && toolCallCount ? (
            <span className="ml-2 text-muted-foreground">({toolCallCount})</span>
          ) : null}
        </span>
      </span>
      <span className="truncate text-muted-foreground">{span.span_type || span.kind || "span"}</span>
      <span className="truncate text-muted-foreground">{formatDuration(span.duration_ms)}</span>
      <span className="text-right tabular-nums text-muted-foreground">{span.total_tokens || 0}</span>
    </div>
  );
}

function SpanTree({
  tree,
  selectedSpanId,
  includeDbSpans,
  toolCallsBySpanId,
  expandedToolCallRows,
  page,
  pageSize,
  onIncludeDbSpansChange,
  onToggleToolCalls,
  onPageChange,
  onPageSizeChange,
  onSelectSpan,
}: {
  tree: AuditTraceTreeNode[];
  selectedSpanId: string;
  includeDbSpans: boolean;
  toolCallsBySpanId: Map<string, ModelToolCall[]>;
  expandedToolCallRows: Set<string>;
  page: number;
  pageSize: number;
  onIncludeDbSpansChange: (include: boolean) => void;
  onToggleToolCalls: (spanId: string) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSelectSpan: (span: AuditSpanRecord) => void;
}) {
  const rows = useMemo(
    () => flattenSpanTree(tree, includeDbSpans, toolCallsBySpanId, expandedToolCallRows),
    [expandedToolCallRows, includeDbSpans, toolCallsBySpanId, tree],
  );
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const safePage = Math.min(page, totalPages - 1);
  const start = safePage * pageSize;
  const visibleRows = rows.slice(start, start + pageSize);
  const end = Math.min(start + pageSize, rows.length);

  useEffect(() => {
    if (page !== safePage) onPageChange(safePage);
  }, [onPageChange, page, safePage]);

  if (!tree.length) {
    return <div className="p-4 text-sm text-muted-foreground">No span tree for this trace.</div>;
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label
          className="inline-flex h-9 items-center gap-2 rounded-md border px-3 text-xs text-muted-foreground"
          title="Include DB operations"
        >
          <input
            type="checkbox"
            checked={includeDbSpans}
            onChange={(event) => onIncludeDbSpansChange(event.target.checked)}
          />
          <Database className="h-4 w-4" />
          <span>DB</span>
        </label>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <select
            value={pageSize}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
            className="h-9 rounded-md border bg-background px-2"
            title="Rows"
          >
            {SPAN_TREE_PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="h-9 w-9"
            onClick={() => onPageChange(Math.max(0, safePage - 1))}
            disabled={safePage === 0}
            title="Previous"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-24 text-center tabular-nums">
            {rows.length ? `${start + 1}-${end} of ${rows.length}` : "0 rows"}
          </span>
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="h-9 w-9"
            onClick={() => onPageChange(Math.min(totalPages - 1, safePage + 1))}
            disabled={safePage >= totalPages - 1}
            title="Next"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="overflow-hidden rounded-md border">
        <div className="grid grid-cols-[minmax(0,1fr)_84px_84px_72px] gap-2 border-b bg-secondary/60 px-3 py-2 text-xs font-medium text-muted-foreground">
          <span>Name</span>
          <span>Type</span>
          <span>Duration</span>
          <span className="text-right">Tokens</span>
        </div>
        {visibleRows.map((row) => (
          <SpanTreeRow
            key={row.span.span_id}
            row={row}
            selectedSpanId={selectedSpanId}
            onSelect={onSelectSpan}
            onToggleToolCalls={onToggleToolCalls}
          />
        ))}
        {!visibleRows.length ? (
          <div className="p-4 text-sm text-muted-foreground">No spans on this page.</div>
        ) : null}
      </div>
    </div>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-72 overflow-auto rounded-md border bg-secondary/30 p-3 text-xs leading-relaxed">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function MultiSelectFilter({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const parsedValues = splitFilterValue(value);
  const optionSet = useMemo(() => new Set(options), [options]);
  const selectedOptions = parsedValues.filter((item) => optionSet.has(item));
  const customValues = parsedValues.filter((item) => !optionSet.has(item));
  const [otherEnabled, setOtherEnabled] = useState(customValues.length > 0);
  const [otherValue, setOtherValue] = useState(customValues.join(", "));

  useEffect(() => {
    setOtherEnabled(customValues.length > 0);
    setOtherValue(customValues.join(", "));
  }, [value, customValues.length, customValues.join(", ")]);

  const commit = (nextSelected: string[], nextOtherEnabled = otherEnabled, nextOther = otherValue) => {
    const otherParts = nextOtherEnabled ? splitFilterValue(nextOther) : [];
    onChange(joinFilterValue([...nextSelected, ...otherParts]));
  };

  const summary =
    parsedValues.length === 0
      ? label
      : parsedValues.length === 1
        ? parsedValues[0]
        : `${parsedValues.length} selected`;

  return (
    <div className="relative min-w-0">
      <Button
        type="button"
        variant="outline"
        className="h-10 w-full justify-between px-3 text-left font-normal"
        onClick={() => setOpen((current) => !current)}
        title={label}
      >
        <span className={cn("truncate", !parsedValues.length && "text-muted-foreground")}>
          {summary}
        </span>
        <ChevronDown className="ml-2 h-4 w-4 shrink-0 text-muted-foreground" />
      </Button>
      {open ? (
        <div className="absolute left-0 top-full z-50 mt-1 max-h-80 w-full min-w-64 overflow-auto rounded-md border bg-card p-2 shadow-lg">
          <div className="mb-1 px-1 text-xs font-medium text-muted-foreground">{label}</div>
          <div className="space-y-1">
            {options.map((option) => {
              const checked = selectedOptions.includes(option);
              return (
                <button
                  key={option}
                  type="button"
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-secondary"
                  onClick={() => {
                    const nextSelected = checked
                      ? selectedOptions.filter((item) => item !== option)
                      : [...selectedOptions, option];
                    commit(nextSelected);
                  }}
                >
                  <span
                    className={cn(
                      "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                      checked && "border-primary bg-primary text-primary-foreground",
                    )}
                  >
                    {checked ? <Check className="h-3 w-3" /> : null}
                  </span>
                  <span className="min-w-0 truncate">{option}</span>
                </button>
              );
            })}
          </div>
          <div className="mt-2 border-t pt-2">
            <button
              type="button"
              className="mb-2 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-secondary"
              onClick={() => {
                const nextEnabled = !otherEnabled;
                setOtherEnabled(nextEnabled);
                commit(selectedOptions, nextEnabled, otherValue);
              }}
            >
              <span
                className={cn(
                  "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                  otherEnabled && "border-primary bg-primary text-primary-foreground",
                )}
              >
                {otherEnabled ? <Check className="h-3 w-3" /> : null}
              </span>
              <span>Other</span>
            </button>
            <Input
              value={otherValue}
              onChange={(event) => {
                const nextValue = event.target.value;
                setOtherValue(nextValue);
                commit(selectedOptions, true, nextValue);
                setOtherEnabled(true);
              }}
              placeholder={`Other ${label.toLowerCase()}`}
              className="h-8"
            />
          </div>
          <div className="mt-2 flex justify-between gap-2">
            <Button type="button" size="sm" variant="ghost" onClick={() => onChange("")}>
              Clear
            </Button>
            <Button type="button" size="sm" variant="secondary" onClick={() => setOpen(false)}>
              Done
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function ObservabilityWorkbench() {
  const [filters, setFilters] = useState<ObservabilityTraceSearchParams>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] =
    useState<ObservabilityTraceSearchParams>(EMPTY_FILTERS);
  const [traces, setTraces] = useState<AuditTraceRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedTraceId, setSelectedTraceId] = useState("");
  const [detail, setDetail] = useState<AuditTraceDetail | null>(null);
  const [tree, setTree] = useState<AuditTraceTreeNode[]>([]);
  const [selectedSpan, setSelectedSpan] = useState<AuditSpanRecord | null>(null);
  const [artifacts, setArtifacts] = useState<AuditArtifactRecord[]>([]);
  const [artifactType, setArtifactType] = useState("");
  const [includeContent, setIncludeContent] = useState(false);
  const [includeDbSpans, setIncludeDbSpans] = useState(false);
  const [expandedToolCallRows, setExpandedToolCallRows] = useState<Set<string>>(() => new Set());
  const [spanTreePage, setSpanTreePage] = useState(0);
  const [spanTreePageSize, setSpanTreePageSize] = useState(10);
  const [facets, setFacets] = useState<AuditObservabilityFacets>(DEFAULT_FACETS);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState("");

  const loadFacets = useCallback(async () => {
    try {
      const nextFacets = await getObservabilityFacets();
      setFacets({
        sources: mergeFacetValues(DEFAULT_FACETS.sources, nextFacets.sources),
        agent_names: mergeFacetValues(DEFAULT_FACETS.agent_names, nextFacets.agent_names),
        model_names: mergeFacetValues(DEFAULT_FACETS.model_names, nextFacets.model_names),
        status_codes: mergeFacetValues(DEFAULT_FACETS.status_codes, nextFacets.status_codes),
      });
    } catch {
      setFacets(DEFAULT_FACETS);
    }
  }, []);

  const loadTraces = useCallback(async () => {
    setLoadingList(true);
    setError("");
    try {
      const response = await listObservabilityTraces(filterPayload(appliedFilters));
      setTraces(response.traces);
      setTotal(response.total);
      if (!selectedTraceId && response.traces.length) {
        setSelectedTraceId(response.traces[0].trace_id);
      }
      if (selectedTraceId && !response.traces.some((trace) => trace.trace_id === selectedTraceId)) {
        setSelectedTraceId(response.traces[0]?.trace_id ?? "");
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load traces.");
    } finally {
      setLoadingList(false);
    }
  }, [appliedFilters, selectedTraceId]);

  const loadTraceStructure = useCallback(async () => {
    if (!selectedTraceId) {
      setDetail(null);
      setTree([]);
      setSelectedSpan(null);
      return;
    }
    setLoadingDetail(true);
    setError("");
    try {
      const [nextDetail, nextTree] = await Promise.all([
        getObservabilityTrace(selectedTraceId),
        getObservabilityTraceTree(selectedTraceId),
      ]);
      setDetail(nextDetail);
      setTree(nextTree);
      setSelectedSpan((current) => {
        const sameTrace = current?.trace_id === selectedTraceId;
        const realSpanExists =
          sameTrace && nextDetail.spans.some((span) => span.span_id === current?.span_id);
        const virtualParentExists =
          sameTrace &&
          current?.span_type === "tool_call" &&
          nextDetail.spans.some((span) => span.span_id === current.parent_span_id);
        if (current && (realSpanExists || virtualParentExists)) {
          return current;
        }
        return nextDetail.spans[0] ?? null;
      });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load trace detail.");
    } finally {
      setLoadingDetail(false);
    }
  }, [selectedTraceId]);

  const loadArtifacts = useCallback(async () => {
    if (!selectedTraceId) {
      setArtifacts([]);
      return;
    }
    setError("");
    try {
      const nextArtifacts = await listObservabilityArtifacts(selectedTraceId, {
        artifact_type: artifactType || undefined,
        include_content: includeContent,
      });
      setArtifacts(nextArtifacts);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load trace artifacts.");
    }
  }, [artifactType, includeContent, selectedTraceId]);

  useEffect(() => {
    void loadTraces();
  }, [loadTraces]);

  useEffect(() => {
    void loadFacets();
  }, [loadFacets]);

  useEffect(() => {
    void loadTraceStructure();
  }, [loadTraceStructure]);

  useEffect(() => {
    void loadArtifacts();
  }, [loadArtifacts]);

  useEffect(() => {
    setSpanTreePage(0);
  }, [includeDbSpans, selectedTraceId, spanTreePageSize, tree]);

  useEffect(() => {
    setExpandedToolCallRows(new Set());
  }, [selectedTraceId]);

  const toolCallsBySpanId = useMemo(() => buildToolCallsBySpanId(artifacts), [artifacts]);

  const toggleToolCalls = useCallback((spanId: string) => {
    setExpandedToolCallRows((current) => {
      const next = new Set(current);
      if (next.has(spanId)) {
        next.delete(spanId);
      } else {
        next.add(spanId);
      }
      return next;
    });
  }, []);

  useEffect(() => {
    const visibleRows = flattenSpanTree(
      tree,
      includeDbSpans,
      toolCallsBySpanId,
      expandedToolCallRows,
    );
    if (!visibleRows.length) return;
    const selectedSpanId = selectedSpan?.span_id ?? "";
    if (!selectedSpanId || !visibleRows.some((row) => row.span.span_id === selectedSpanId)) {
      setSelectedSpan(visibleRows[0].span);
    }
  }, [expandedToolCallRows, includeDbSpans, selectedSpan?.span_id, toolCallsBySpanId, tree]);

  const selectedTrace = useMemo(
    () => detail?.trace ?? traces.find((trace) => trace.trace_id === selectedTraceId) ?? null,
    [detail?.trace, selectedTraceId, traces],
  );

  const spanById = useMemo(() => {
    return new Map((detail?.spans ?? []).map((span) => [span.span_id, span]));
  }, [detail?.spans]);

  const visibleArtifacts = useMemo(() => {
    const dbFilteredArtifacts = includeDbSpans
      ? artifacts
      : artifacts.filter((artifact) => {
          if (!artifact.span_id) return true;
          const span = spanById.get(artifact.span_id);
          return !span || !isDbSpan(span);
        });
    if (!selectedSpan) return dbFilteredArtifacts;
    const selectedArtifactSpanId =
      selectedSpan.span_type === "tool_call" ? selectedSpan.parent_span_id : selectedSpan.span_id;
    const spanArtifacts = dbFilteredArtifacts.filter(
      (artifact) => artifact.span_id === selectedArtifactSpanId,
    );
    if (selectedSpan.span_type === "tool_call") {
      const outputArtifacts = spanArtifacts.filter(isOutputMessagesArtifact);
      return outputArtifacts.length ? outputArtifacts : spanArtifacts;
    }
    return spanArtifacts.length ? spanArtifacts : dbFilteredArtifacts;
  }, [artifacts, includeDbSpans, selectedSpan, spanById]);

  const setFilter = (key: keyof ObservabilityTraceSearchParams, value: string | number) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const applyFilters = () => {
    setAppliedFilters({ ...filters, offset: 0 });
    setSelectedTraceId("");
  };

  const resetFilters = () => {
    setFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
    setSelectedTraceId("");
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-3 rounded-md border bg-card p-3 lg:grid-cols-[repeat(4,minmax(0,1fr))_auto]">
        <Input
          value={filters.claim_number ?? ""}
          onChange={(event) => setFilter("claim_number", event.target.value)}
          placeholder="Claim contains"
        />
        <Input
          value={filters.audit_run_id ?? ""}
          onChange={(event) => setFilter("audit_run_id", event.target.value)}
          placeholder="Audit run"
        />
        <Input
          value={filters.batch_id ?? ""}
          onChange={(event) => setFilter("batch_id", event.target.value)}
          placeholder="Batch"
        />
        <MultiSelectFilter
          label="Source"
          options={facets.sources}
          value={filters.source ?? ""}
          onChange={(value) => setFilter("source", value)}
        />
        <div className="flex items-center gap-2">
          <Button type="button" size="sm" onClick={applyFilters}>
            <Search className="mr-1.5 h-4 w-4" />
            Search
          </Button>
          <Button type="button" size="icon" variant="outline" onClick={resetFilters} title="Clear filters">
            <X className="h-4 w-4" />
          </Button>
          <Button type="button" size="icon" variant="outline" onClick={loadTraces} title="Refresh">
            <RefreshCw className={cn("h-4 w-4", loadingList && "animate-spin")} />
          </Button>
        </div>
        <Input
          value={filters.case_id ?? ""}
          onChange={(event) => setFilter("case_id", event.target.value)}
          placeholder="Case"
        />
        <MultiSelectFilter
          label="Agent"
          options={facets.agent_names}
          value={filters.agent_name ?? ""}
          onChange={(value) => setFilter("agent_name", value)}
        />
        <MultiSelectFilter
          label="Model"
          options={facets.model_names}
          value={filters.model_name ?? ""}
          onChange={(value) => setFilter("model_name", value)}
        />
        <MultiSelectFilter
          label="Status"
          options={facets.status_codes}
          value={filters.status_code ?? ""}
          onChange={(value) => setFilter("status_code", value)}
        />
        <Input
          type="number"
          min={1}
          max={200}
          value={filters.limit ?? 50}
          onChange={(event) => setFilter("limit", Number(event.target.value))}
          title="Limit"
        />
        <label className="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
          <span>From</span>
          <Input
            type="datetime-local"
            value={filters.started_at_from ?? ""}
            onChange={(event) => setFilter("started_at_from", event.target.value)}
            className="h-10"
          />
        </label>
        <label className="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
          <span>To</span>
          <Input
            type="datetime-local"
            value={filters.started_at_to ?? ""}
            onChange={(event) => setFilter("started_at_to", event.target.value)}
            className="h-10"
          />
        </label>
        <Input
          value={filters.text_query ?? ""}
          onChange={(event) => setFilter("text_query", event.target.value)}
          placeholder="Artifact text"
          className="self-end lg:col-span-2"
        />
      </div>

      {error ? (
        <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          <span>{error}</span>
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.35fr)]">
        <Card className="overflow-hidden">
          <CardHeader className="flex-row items-center justify-between space-y-0 p-4">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Activity className="h-4 w-4" />
              Traces
            </CardTitle>
            <span className="text-xs text-muted-foreground">{total} total</span>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Started</TableHead>
                  <TableHead>Claim</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Tokens</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {traces.map((trace) => {
                  const matchedClaim = childClaimMatchLabel(trace, appliedFilters.claim_number);
                  return (
                    <TableRow
                      key={trace.trace_id}
                      className={cn(
                        "cursor-pointer",
                        trace.trace_id === selectedTraceId && "bg-secondary",
                      )}
                      onClick={() => setSelectedTraceId(trace.trace_id)}
                    >
                      <TableCell className="whitespace-nowrap">{formatDate(trace.started_at)}</TableCell>
                      <TableCell>
                        <div className="max-w-40 truncate font-medium">
                          {trace.claim_number || compactId(trace.audit_run_id)}
                        </div>
                        <div className="max-w-40 truncate text-xs text-muted-foreground">
                          {matchedClaim ? `match ${matchedClaim}` : compactId(trace.trace_id)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="max-w-28 truncate">{trace.source || "NA"}</div>
                        {trace.batch_id ? (
                          <div className="max-w-28 truncate text-xs text-muted-foreground">
                            {compactId(trace.batch_id)}
                          </div>
                        ) : null}
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusVariant(trace.status_code, trace.error_count)}>
                          {trace.status_code}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{trace.total_tokens}</TableCell>
                    </TableRow>
                  );
                })}
                {!traces.length ? (
                  <TableRow>
                    <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                      {loadingList ? "Loading traces..." : "No traces match these filters."}
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0 p-4">
              <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
                <Clock3 className="h-4 w-4" />
                <span className="truncate">
                  {selectedTrace ? compactId(selectedTrace.trace_id) : "Trace detail"}
                </span>
              </CardTitle>
              {loadingDetail ? <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground" /> : null}
            </CardHeader>
            <CardContent className="space-y-3 p-4 pt-0">
              {selectedTrace ? (
                <>
                  <div className="grid gap-2 text-sm sm:grid-cols-4">
                    <div>
                      <div className="text-xs text-muted-foreground">Duration</div>
                      <div className="font-medium">{formatDuration(selectedTrace.duration_ms)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">Spans</div>
                      <div className="font-medium">{selectedTrace.span_count}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">Errors</div>
                      <div className="font-medium">{selectedTrace.error_count}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">Tokens</div>
                      <div className="font-medium">{selectedTrace.total_tokens}</div>
                    </div>
                  </div>
                  <div className="grid gap-2 text-sm sm:grid-cols-2">
                    <div>
                      <div className="text-xs text-muted-foreground">Agents</div>
                      <div className="truncate">{joined(selectedTrace.agent_names)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">Models</div>
                      <div className="truncate">{joined(selectedTrace.model_names)}</div>
                    </div>
                  </div>
                  {detail?.delegations.length ? (
                    <div className="rounded-md border p-3">
                      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
                        <Split className="h-4 w-4" />
                        Delegations
                      </div>
                      <div className="space-y-1">
                        {detail.delegations.map((delegation) => (
                          <div
                            key={`${delegation.parent_span_id}-${delegation.child_span_id}`}
                            className="text-sm"
                          >
                            <span className="font-medium">
                              {delegation.parent_agent_name || "parent"}
                            </span>
                            <span className="text-muted-foreground"> via </span>
                            <span>{delegation.tool_name || "tool"}</span>
                            <span className="text-muted-foreground"> to </span>
                            <span className="font-medium">
                              {delegation.child_agent_name || "agent"}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="text-sm text-muted-foreground">Select a trace.</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="p-4">
              <CardTitle className="text-sm">Span Tree</CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0">
              <SpanTree
                tree={tree}
                selectedSpanId={selectedSpan?.span_id ?? ""}
                includeDbSpans={includeDbSpans}
                toolCallsBySpanId={toolCallsBySpanId}
                expandedToolCallRows={expandedToolCallRows}
                page={spanTreePage}
                pageSize={spanTreePageSize}
                onIncludeDbSpansChange={setIncludeDbSpans}
                onToggleToolCalls={toggleToolCalls}
                onPageChange={setSpanTreePage}
                onPageSizeChange={setSpanTreePageSize}
                onSelectSpan={setSelectedSpan}
              />
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.35fr)]">
        <Card>
          <CardHeader className="p-4">
            <CardTitle className="text-sm">Selected Span</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 p-4 pt-0">
            {selectedSpan ? (
              <>
                <div className="grid gap-2 text-sm sm:grid-cols-3">
                  <div>
                    <div className="text-xs text-muted-foreground">Name</div>
                    <div className="break-words font-medium">{selectedSpan.name}</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">Type</div>
                    <div>{selectedSpan.span_type || selectedSpan.kind || "span"}</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">Status</div>
                    <Badge variant={statusVariant(selectedSpan.status_code)}>
                      {selectedSpan.status_code}
                    </Badge>
                  </div>
                </div>
                {selectedSpan.error_message ? (
                  <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                    {selectedSpan.error_message}
                  </div>
                ) : null}
                <JsonBlock value={selectedSpan.attributes} />
              </>
            ) : (
              <div className="text-sm text-muted-foreground">Select a span from the tree.</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 p-4">
            <CardTitle className="flex items-center gap-2 text-sm">
              <FileText className="h-4 w-4" />
              Artifacts
            </CardTitle>
            <div className="flex items-center gap-2">
              <Input
                value={artifactType}
                onChange={(event) => setArtifactType(event.target.value)}
                placeholder="Type"
                className="h-8 w-32"
              />
              <Button
                type="button"
                size="sm"
                variant="outline"
                className={cn(
                  includeContent &&
                    "border-emerald-500/70 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/20 hover:text-emerald-200",
                )}
                onClick={() => setIncludeContent((value) => !value)}
                title={includeContent ? "Raw content on" : "Raw content off"}
              >
                <Eye className="mr-1.5 h-4 w-4" />
                Raw
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 p-4 pt-0">
            {visibleArtifacts.length ? (
              visibleArtifacts.map((artifact) => (
                <div key={artifact.id} className="rounded-md border p-3">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">{artifact.artifact_type}</Badge>
                    <span className="min-w-0 truncate text-sm font-medium">{artifact.name}</span>
                    <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                      {artifact.content_size.toLocaleString()} bytes
                    </span>
                  </div>
                  <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-secondary/35 p-3 text-xs leading-relaxed">
                    {includeContent && artifact.content_text
                      ? artifact.content_text
                      : artifact.content_preview}
                  </pre>
                </div>
              ))
            ) : (
              <div className="text-sm text-muted-foreground">
                No artifacts for the selected trace or span.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
