"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  BrainCircuit,
  Code2,
  FileCheck2,
  FlaskConical,
  GitBranch,
  MessageSquareCode,
  Play,
  ShieldCheck,
  SlidersHorizontal,
  Workflow,
  X,
} from "lucide-react";

import { useChatPanelMode } from "@/components/app-shell/chat-panel-mode-context";
import { cn } from "@/lib/utils";

const chatOpenInset = 560;
const chatHiddenInset = 24;

type Tone = "teal" | "blue" | "yellow" | "gray";

interface TextBlock {
  title: string;
  text: string;
  icon?: LucideIcon;
  tone?: Tone;
}

type LifecycleNodeData = {
  label: string;
  detail: string;
  points: LifecycleDetailPoint[];
  icon: LucideIcon;
  tone: Tone;
  optional?: boolean;
  handles: Partial<Record<LifecycleHandle, boolean>>;
};

type LifecycleDetailPoint = string | {
  label: string;
  children?: LifecycleDetailPoint[];
};

type LifecycleHandle =
  | "targetLeft"
  | "targetTop"
  | "targetBottom"
  | "sourceRight"
  | "sourceTop"
  | "sourceBottom";

const lifecycleNodes: Node<LifecycleNodeData>[] = [
  {
    id: "model",
    type: "lifecycle",
    data: {
      label: "Model Definition",
      detail: "Combines the LLM, questionnaire, prompt instructions, context, and tool access for the review.",
      points: [
        "Language model selection (typically OpenAI)",
        {
          label: "Questionnaire design",
          children: [
            "Questions with optional sub-question drivers",
            "Questions with financials, i.e., over/under write",
          ],
        },
        {
          label: "Knowledge Center selection",
          children: [
            "List of help guide IDs, e.g., HELP-0123456",
            "Whether to include state-specific compliance guides",
          ],
        },
        {
          label: "Context tools",
          children: [
            "Claim summary",
            "Notes",
            "Claim documents",
            "Policy documents",
            "Images, i.e., image files, PDF photo sheets",
          ],
        },
      ],
      icon: BrainCircuit,
      tone: "blue",
      handles: { sourceRight: true },
    },
    position: { x: 0, y: 118 },
  },
  {
    id: "batch",
    type: "lifecycle",
    data: {
      label: "Batch Execution",
      detail: "Run a registered form across a list of claim numbers.",
      points: [
        "Configure a run by entering or uploading a list of claim numbers and selecting a form",
        "Run, pause, resume, and monitor progress",
        "Re-run a configuration over a new list of claim numbers",
        "Also supports full manual entry and intake from completed audit PDF forms",
      ],
      icon: Play,
      tone: "teal",
      handles: { targetLeft: true, sourceRight: true, sourceBottom: true },
    },
    position: { x: 360, y: 118 },
  },
  {
    id: "reporting",
    type: "lifecycle",
    data: {
      label: "Reporting & Analytics",
      detail: "Explore a built-in reporting suite over the application database.",
      points: [
        {
          label: "Standard views",
          children: [
            "Visualize trends and aggregate metrics",
            "Roll-up views across forms, questions, drivers, and comments",
          ],
        },
        {
          label: "AI assisted analytics",
          children: [
            "Natural language database queries",
            "AI generated plots, tables, summary reports, Power Point slide decks, and Excel workbooks",
            "Summarize large volume of comments",
          ],
        },
      ],
      icon: BarChart3,
      tone: "blue",
      handles: { targetLeft: true, targetBottom: true },
    },
    position: { x: 720, y: 118 },
  },
  {
    id: "evaluate",
    type: "lifecycle",
    data: {
      label: "Evaluation",
      detail: 'Source "ground truth" data to evaluate a model against.',
      points: [
        "Source data from existing systems, e.g., TEAMThink",
        "Or use application data validated and/or edited by users",
        {
          label: "Purpose-built metrics suite",
          children: [
            "Outcome match",
            "Question agreement",
            "Driver F1",
            "Path exact rate",
            "Dollar error",
          ],
        },
        {
          label: "Sampling options",
          children: [
            "Outcome-based sampling",
            "Issue mix",
            "Cluster balance",
            "Published datasets",
          ],
        },
      ],
      icon: FileCheck2,
      tone: "yellow",
      optional: true,
      handles: { targetTop: true, sourceRight: true },
    },
    position: { x: 360, y: 350 },
  },
  {
    id: "optimize",
    type: "lifecycle",
    data: {
      label: "Prompt Optimization",
      detail: "Leverage metric-driven automated prompt engineering.",
      points: [
        "Learn the best prompt from the data, i.e., ground truth examples",
        'Leverage user feedback to "retrain" the model',
        "Repeatable process for language model retirements",
        "Supports comparison-based metrics and LLM-Judge",
      ],
      icon: FlaskConical,
      tone: "teal",
      optional: true,
      handles: { targetLeft: true, sourceTop: true },
    },
    position: { x: 720, y: 350 },
  },
];

const lifecycleEdges: Edge[] = [
  edge("model", "batch", { sourceHandle: "source-right", targetHandle: "target-left" }),
  edge("batch", "reporting", { sourceHandle: "source-right", targetHandle: "target-left" }),
  optionalEdge("batch", "evaluate", "source-bottom", "target-top"),
  optionalEdge("evaluate", "optimize", "source-right", "target-left"),
  optionalEdge("optimize", "reporting", "source-top", "target-bottom"),
];

const technicalBlocks: TextBlock[] = [
  {
    title: "Structured output validation and merge",
    text: "Pydantic contracts validate audit outputs and merge sparse generated answers back onto canonical form questions and drivers.",
    icon: ShieldCheck,
    tone: "teal",
  },
  {
    title: "Dynamic tool definitions",
    text: "Review-agent tools are filtered by form configuration so each audit exposes only the context sources intended for that review.",
    icon: SlidersHorizontal,
    tone: "blue",
  },
  {
    title: "AG-UI and A2UI",
    text: "AG-UI streams chat state and tool progress. A2UI renders generated audit cards, tables, code blocks, Plotly charts, and artifact bundles.",
    icon: Workflow,
    tone: "yellow",
  },
  {
    title: "Coding-agent chat",
    text: "The chat agent uses discovery tools first, then execution tools: schema helpers, selected-row context, read-only SQL, Python, RLM, and output bundles.",
    icon: MessageSquareCode,
    tone: "teal",
  },
  {
    title: "SQL and Python analysis",
    text: "SQL creates durable dataset handles. Python transforms those handles, prepares dataframes, emits Plotly figures, and packages reports or decks.",
    icon: Code2,
    tone: "blue",
  },
  {
    title: "Dataset curation",
    text: "Sampling can use outcome, issue mix, cluster balance, diversity, published datasets, and reference policies.",
    icon: GitBranch,
    tone: "yellow",
  },
];

const nodeTypes = { lifecycle: LifecycleNode };

export default function AboutPage() {
  const { chatMode } = useChatPanelMode();
  const [isDesktop, setIsDesktop] = useState(false);
  const chatVisible = chatMode !== "hidden";
  const graph = useMemo(
    () => ({ nodes: lifecycleNodes, edges: lifecycleEdges }),
    [],
  );

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const update = () => setIsDesktop(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  return (
    <div
      className="min-h-[calc(100vh-3.5rem)] w-full bg-background text-foreground"
      style={isDesktop ? { paddingLeft: chatVisible ? chatOpenInset : chatHiddenInset } : undefined}
    >
      <div className="mx-auto flex w-full max-w-[1320px] flex-col gap-10 px-4 py-8 sm:px-6 lg:pr-8 xl:pr-10">
        <PageIntro />

        <section className="space-y-4">
          <SectionHeader
            eyebrow="Model Lifecycle"
            title="How review work moves through the app"
            text="The same records support single reviews, batch runs, dashboards, evaluation, optimization, and chat analysis."
          />
          <LifecycleFlow nodes={graph.nodes} edges={graph.edges} />
        </section>

        <section className="space-y-4">
          <SectionHeader
            eyebrow="Technical Notes"
            title="Backend and agent capabilities"
          />
          <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {technicalBlocks.map((item) => (
              <CompactPanel key={item.title} item={item} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function PageIntro() {
  return (
    <header className="border-b pb-6">
      <div className="max-w-4xl">
        <p className="text-xs font-semibold uppercase text-[#06748C] dark:text-[#78E1E1]">
          AI File Review Workbench
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-normal sm:text-4xl">
          About the application
        </h1>
        <p className="mt-4 max-w-3xl text-sm leading-6 text-muted-foreground">
          The workbench uses AI to audit claim files at one-file, batch, and program scale.
          It supports the full lifecycle: define a targeted review, run it, evaluate quality,
          improve prompts, explore results, and generate audience-specific outputs.
        </p>
      </div>
    </header>
  );
}

function LifecycleFlow({ nodes, edges }: { nodes: Node<LifecycleNodeData>[]; edges: Edge[] }) {
  const shellRef = useRef<HTMLDivElement>(null);
  const flowRef = useRef<HTMLDivElement>(null);
  const [shellWidth, setShellWidth] = useState(0);
  const [width, setWidth] = useState(0);
  const [selectedNode, setSelectedNode] = useState<LifecycleNodeData | null>(null);
  const showSidePanel = shellWidth >= 920;
  const graphBounds = { width: 930, height: 520 };
  const graphHeight = 620;
  const zoom = Math.min(
    0.92,
    Math.max(
      0.6,
      Math.min((Math.max(width, 320) - 72) / graphBounds.width, (graphHeight - 72) / graphBounds.height),
    ),
  );
  const centeredX = (Math.max(width, 320) - graphBounds.width * zoom) / 2;
  const centeredY = (graphHeight - graphBounds.height * zoom) / 2;
  const defaultViewport = {
    x: Math.max(24, Math.min(80, centeredX)),
    y: Math.max(56, Math.min(116, centeredY)),
    zoom,
  };

  useEffect(() => {
    const shell = shellRef.current;
    const flow = flowRef.current;
    if (!shell || !flow) return undefined;
    const update = () => {
      setShellWidth(shell.getBoundingClientRect().width);
      setWidth(flow.getBoundingClientRect().width);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(shell);
    observer.observe(flow);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={shellRef}
      className={cn("grid gap-4", showSidePanel ? "grid-cols-[minmax(0,1fr)_340px] items-stretch" : "grid-cols-1")}
    >
      <div ref={flowRef} className="h-[620px] overflow-hidden rounded-lg border bg-card">
        {width > 0 ? (
          <ReactFlow
            key={`lifecycle-flow-${Math.round(width)}-${Math.round(zoom * 100)}`}
            className="optimization-flow"
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            defaultViewport={defaultViewport}
            minZoom={0.24}
            maxZoom={1.35}
            onNodeClick={(_, node) => setSelectedNode(node.data as LifecycleNodeData)}
            onPaneClick={() => setSelectedNode(null)}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={28} size={1.1} />
            <Controls />
          </ReactFlow>
        ) : null}
      </div>
      <LifecycleDetailPanel node={selectedNode} onClose={() => setSelectedNode(null)} />
    </div>
  );
}

function LifecycleNode({ data, selected }: NodeProps<Node<LifecycleNodeData>>) {
  const Icon = data.icon;
  return (
    <div
      className={cn(
        "flex min-h-[88px] w-[210px] cursor-pointer items-center rounded-lg border bg-card p-4 text-card-foreground shadow-sm transition",
        selected ? "border-[#78E1E1] ring-2 ring-[#78E1E1]/40" : "hover:border-[#78E1E1]/70",
        data.optional ? "border-dashed border-[#06748C]/60 dark:border-[#78E1E1]/50" : null,
      )}
    >
      {data.handles.targetLeft ? <FlowHandle id="target-left" type="target" position={Position.Left} /> : null}
      {data.handles.targetTop ? <FlowHandle id="target-top" type="target" position={Position.Top} /> : null}
      {data.handles.targetBottom ? <FlowHandle id="target-bottom" type="target" position={Position.Bottom} /> : null}
      <div className="flex min-w-0 items-center gap-3">
        <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-md", toneClass(data.tone))}>
          <Icon className="h-5 w-5" />
        </span>
        <p className="text-base font-semibold leading-snug">{data.label}</p>
      </div>
      {data.handles.sourceRight ? <FlowHandle id="source-right" type="source" position={Position.Right} /> : null}
      {data.handles.sourceTop ? <FlowHandle id="source-top" type="source" position={Position.Top} /> : null}
      {data.handles.sourceBottom ? <FlowHandle id="source-bottom" type="source" position={Position.Bottom} /> : null}
    </div>
  );
}

function LifecycleDetailPanel({
  node,
  onClose,
}: {
  node: LifecycleNodeData | null;
  onClose: () => void;
}) {
  if (!node) {
    return (
      <aside className="rounded-lg border bg-card p-5">
        <p className="text-sm leading-6 text-muted-foreground">Select a component to learn more</p>
      </aside>
    );
  }

  const Icon = node.icon;
  return (
    <aside className="rounded-lg border bg-card p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-md", toneClass(node.tone))}>
            <Icon className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase text-muted-foreground">
              {node.optional ? "Optional path" : "Primary path"}
            </p>
            <h3 className="mt-1 text-base font-semibold leading-snug">{node.label}</h3>
          </div>
        </div>
        <button
          type="button"
          aria-label="Close lifecycle details"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border text-muted-foreground transition hover:bg-secondary hover:text-foreground"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <p className="mt-4 text-[15px] leading-6 text-muted-foreground">{node.detail}</p>
      <div className="mt-4 border-t pt-4">
        <LifecyclePointList points={node.points} />
      </div>
    </aside>
  );
}

function LifecyclePointList({
  points,
  depth = 0,
}: {
  points: LifecycleDetailPoint[];
  depth?: number;
}) {
  return (
    <ul className={cn(depth > 0 ? "mt-1 space-y-0.5" : "space-y-2")}>
      {points.map((point) => {
        const label = typeof point === "string" ? point : point.label;
        const children = typeof point === "string" ? undefined : point.children;
        return (
          <li
            key={`${depth}-${label}`}
            className={cn(depth > 0 ? "text-[13px] leading-5 text-muted-foreground" : "text-[15px] leading-5")}
          >
            <div className="flex gap-2.5">
              <span
                className={cn(
                  "shrink-0 rounded-full",
                  depth > 0
                    ? "mt-2 h-1 w-1 bg-muted-foreground/70"
                    : "mt-1.5 h-1.5 w-1.5 bg-[#06748C] dark:bg-[#78E1E1]",
                )}
              />
              <span>{label}</span>
            </div>
            {children?.length ? (
              <div className="pl-4">
                <LifecyclePointList points={children} depth={depth + 1} />
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function FlowHandle({
  id,
  type,
  position,
}: {
  id: string;
  type: "source" | "target";
  position: Position;
}) {
  return <Handle id={id} type={type} position={position} className="!h-2 !w-2 !border-0 !bg-primary" />;
}

function SectionHeader({
  eyebrow,
  title,
  text,
}: {
  eyebrow: string;
  title: string;
  text?: string;
}) {
  return (
    <div className="max-w-3xl">
      <p className="text-xs font-semibold uppercase text-[#06748C] dark:text-[#78E1E1]">{eyebrow}</p>
      <h2 className="mt-2 text-2xl font-semibold tracking-normal">{title}</h2>
      {text ? <p className="mt-3 text-sm leading-6 text-muted-foreground">{text}</p> : null}
    </div>
  );
}

function CompactPanel({ item }: { item: TextBlock }) {
  const Icon = item.icon;
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-start gap-3">
        {Icon ? (
          <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-md", toneClass(item.tone))}>
            <Icon className="h-4 w-4" />
          </span>
        ) : null}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold leading-snug">{item.title}</h3>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.text}</p>
        </div>
      </div>
    </div>
  );
}

function edge(
  source: string,
  target: string,
  options: {
    animated?: boolean;
    sourceHandle?: string;
    targetHandle?: string;
    optional?: boolean;
  } = {},
): Edge {
  return {
    id: `${source}-${target}`,
    source,
    target,
    sourceHandle: options.sourceHandle,
    targetHandle: options.targetHandle,
    type: "smoothstep",
    animated: options.animated ?? false,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 16,
      height: 16,
    },
    style: {
      strokeWidth: options.optional ? 1.5 : 1.7,
      strokeDasharray: options.optional ? "6 5" : undefined,
      opacity: options.optional ? 0.82 : 1,
    },
  };
}

function optionalEdge(source: string, target: string, sourceHandle: string, targetHandle: string): Edge {
  return edge(source, target, {
    sourceHandle,
    targetHandle,
    optional: true,
  });
}

function toneClass(tone: Tone = "teal") {
  return {
    teal: "bg-[#78E1E1]/25 text-[#06748C] dark:bg-[#78E1E1]/10 dark:text-[#78E1E1]",
    blue: "bg-[#1A1446]/10 text-[#1A1446] dark:bg-[#78E1E1]/10 dark:text-[#78E1E1]",
    yellow: "bg-[#FFD000]/30 text-[#1A1446] dark:bg-[#FFD000]/20 dark:text-[#FFD000]",
    gray: "bg-[#343741]/10 text-[#343741] dark:bg-white/10 dark:text-white",
  }[tone];
}
