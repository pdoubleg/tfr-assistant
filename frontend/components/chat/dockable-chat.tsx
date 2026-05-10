"use client";

import {
  AlertCircle,
  Bot,
  Check,
  ClipboardCheck,
  ChevronDown,
  ChevronRight,
  Copy,
  Loader2,
  Maximize2,
  MessageSquareText,
  Minimize2,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import type {
  Dispatch,
  FormEvent,
  ReactNode,
  SetStateAction,
} from "react";
import { Children, isValidElement, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { ChatPanelMode } from "@/components/app-shell/app-shell";
import { apiBaseUrl } from "@/lib/api";
import type { TFRChatState, ToolStep } from "@/lib/types";
import { cn } from "@/lib/utils";
import { initialTfrChatState, useTfrAgent } from "@/hooks/use-tfr-agent";

type ChatRole = "user" | "assistant";

interface UserAssistantMessage {
  id: string;
  role: ChatRole;
  content: string;
  streaming?: boolean;
}

interface ToolStatusMessage {
  id: string;
  role: "tool_status";
  isLive: boolean;
  steps: ToolStep[];
}

type ChatMessage = UserAssistantMessage | ToolStatusMessage;

const starterMessages: ChatMessage[] = [
  {
    id: "welcome",
    role: "assistant",
    content:
      "### TFR Assistant\n\nI can help triage review batches, explain form results, and keep audit context synced as AG-UI state comes online.\n\n| Capability | Ready |\n| --- | --- |\n| Markdown tables | Yes |\n| Streaming text | Yes |\n| Tool status timeline | Starting now |",
  },
];

const RESPONSE_STARTED_STEP_ID = "assistant-response-started";
const MIN_PANEL_WIDTH = 460;
const MIN_PANEL_HEIGHT = 520;
const HEADER_OFFSET = 72;
const QUEUE_CONTEXT_TOP_OFFSET = 148;
const QUEUE_CONTEXT_BOTTOM_OFFSET = 24;
const PANEL_MARGIN = 8;
const DEFAULT_SMALL_SIZE = { width: 520, height: 0 };

export function DockableChat({
  mode,
  onModeChange,
}: {
  mode: ChatPanelMode;
  onModeChange: (mode: ChatPanelMode) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(starterMessages);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const { state: sharedState, setState: setSharedState } = useTfrAgent();
  const [collapsedToolMessages, setCollapsedToolMessages] = useState<Set<string>>(new Set());
  const [panelRect, setPanelRect] = useState({
    left: 24,
    top: QUEUE_CONTEXT_TOP_OFFSET,
    width: DEFAULT_SMALL_SIZE.width,
    height: 760,
  });
  const lastSmallRectRef = useRef(panelRect);
  const lastLargeRectRef = useRef(panelRect);
  const [isDarkTheme, setIsDarkTheme] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const threadId = useMemo(() => makeId("thread"), []);
  const lastVisibleModeRef = useRef<Exclude<ChatPanelMode, "hidden">>("small");
  const previousModeRef = useRef<ChatPanelMode>(mode);
  const hasVisiblePanelSnapshotRef = useRef(false);
  const restorePreviousRectOnShowRef = useRef(false);

  useEffect(() => {
    const syncTheme = () => setIsDarkTheme(document.documentElement.classList.contains("dark"));
    syncTheme();
    const observer = new MutationObserver(syncTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [input]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sharedState.current_step]);

  useEffect(() => {
    setCollapsedToolMessages((current) => {
      const next = new Set(current);
      let changed = false;
      for (const message of messages) {
        if (message.role === "tool_status" && !message.isLive && !next.has(message.id)) {
          next.add(message.id);
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [messages]);

  useEffect(() => {
    if (mode !== "hidden") {
      lastVisibleModeRef.current = mode;
    }

    const applyModeRect = () => {
      if (mode === "small") {
        const width = Math.min(Math.max(DEFAULT_SMALL_SIZE.width, MIN_PANEL_WIDTH), window.innerWidth - PANEL_MARGIN * 2);
        const height = Math.max(
          MIN_PANEL_HEIGHT,
          window.innerHeight - QUEUE_CONTEXT_TOP_OFFSET - QUEUE_CONTEXT_BOTTOM_OFFSET,
        );
        const nextRect = restorePreviousRectOnShowRef.current
          ? lastSmallRectRef.current
          : {
              ...lastSmallRectRef.current,
              left: Number.isFinite(lastSmallRectRef.current.left) ? lastSmallRectRef.current.left : 24,
              top: QUEUE_CONTEXT_TOP_OFFSET,
              width: Math.max(MIN_PANEL_WIDTH, Math.min(lastSmallRectRef.current.width || width, Math.min(720, window.innerWidth - PANEL_MARGIN * 2))),
              height,
            };
        setPanelRect(clampRectToViewport({
          ...nextRect,
        }, mode));
      }

      if (mode === "large") {
        const width = Math.max(MIN_PANEL_WIDTH, Math.floor(window.innerWidth * 0.82));
        const height = Math.max(MIN_PANEL_HEIGHT, Math.floor((window.innerHeight - 72) * 0.9));
        const nextRect = restorePreviousRectOnShowRef.current
          ? lastLargeRectRef.current
          : {
              ...lastLargeRectRef.current,
              left: Math.max(16, Math.floor((window.innerWidth - width) / 2)),
              top: 72,
              width,
              height,
            };
        setPanelRect(clampRectToViewport({
          ...nextRect,
        }, mode));
      }

      restorePreviousRectOnShowRef.current = false;
    };

    applyModeRect();
    window.addEventListener("resize", applyModeRect);
    return () => window.removeEventListener("resize", applyModeRect);
  }, [mode]);

  useEffect(() => {
    if (mode !== previousModeRef.current) {
      previousModeRef.current = mode;
      return;
    }
    if (mode === "small") {
      lastSmallRectRef.current = panelRect;
    }
    if (mode === "large") {
      lastLargeRectRef.current = panelRect;
    }
  }, [mode, panelRect]);

  const beginResize = (event: React.PointerEvent<HTMLButtonElement>, direction: ResizeDirection) => {
    event.preventDefault();
    const startX = event.clientX;
    const startY = event.clientY;
    const startRect = panelRect;

    const onMove = (moveEvent: PointerEvent) => {
      const dx = moveEvent.clientX - startX;
      const dy = moveEvent.clientY - startY;
      setPanelRect(resizeRect(startRect, direction, dx, dy, mode));
    };

    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  const beginDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    if (target.closest("button, textarea, a, input")) return;

    event.preventDefault();
    const startX = event.clientX;
    const startY = event.clientY;
    const startRect = panelRect;

    const onMove = (moveEvent: PointerEvent) => {
      setPanelRect({
        ...startRect,
        left: clamp(startRect.left + moveEvent.clientX - startX, 12, window.innerWidth - startRect.width - 12),
        top: clamp(startRect.top + moveEvent.clientY - startY, HEADER_OFFSET, window.innerHeight - startRect.height - PANEL_MARGIN),
      });
    };

    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  const rememberCurrentPanel = () => {
    if (mode === "hidden") return;
    lastVisibleModeRef.current = mode;
    hasVisiblePanelSnapshotRef.current = true;
    if (mode === "small") {
      lastSmallRectRef.current = panelRect;
    }
    if (mode === "large") {
      lastLargeRectRef.current = panelRect;
    }
  };

  const showPanel = () => {
    restorePreviousRectOnShowRef.current = hasVisiblePanelSnapshotRef.current;
    onModeChange(lastVisibleModeRef.current);
  };

  const hidePanel = () => {
    rememberCurrentPanel();
    onModeChange("hidden");
  };

  const togglePanelSize = () => {
    rememberCurrentPanel();
    onModeChange(mode === "large" ? "small" : "large");
  };

  const sendMessage = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault();
    const content = input.trim();
    if (!content || isStreaming) return;

    const userMessage: UserAssistantMessage = { id: makeId("user"), role: "user", content };
    const toolStatusId = makeId("tools");
    const assistantId = makeId("assistant");
    setInput("");
    setSharedState((current) => ({
      ...current,
      active_route: window.location.pathname,
      status: "thinking",
      progress: 0,
      current_step: "Starting assistant run...",
      activity_log: [],
      error_message: null,
    }));
    setMessages((current) => [
      ...current,
      userMessage,
      { id: toolStatusId, role: "tool_status", steps: [], isLive: true },
      { id: assistantId, role: "assistant", content: "", streaming: true },
    ]);
    setIsStreaming(true);

    try {
      await streamAgUiResponse(
        [...messages, userMessage].filter((message): message is UserAssistantMessage => message.role !== "tool_status"),
        assistantId,
        toolStatusId,
        threadId,
        {
          ...sharedState,
          active_route: window.location.pathname,
          status: "thinking",
          progress: 0,
          current_step: "Starting assistant run...",
          activity_log: [],
          error_message: null,
        },
        setMessages,
        setSharedState,
      );
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Unknown chat error.";
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                streaming: false,
                content: `I could not reach the chat agent yet.\n\n\`${errorMessage}\``,
              }
            : message.id === toolStatusId
              ? message.role === "tool_status" ? {
                  ...message,
                  isLive: false,
                  steps: [
                    ...message.steps,
                    {
                      id: makeId("error"),
                      message: "Chat agent request failed.",
                      status: "error",
                    },
                  ],
                } : message
              : message,
        ),
      );
    } finally {
      setIsStreaming(false);
    }
  };

  if (mode === "hidden") {
    return (
      <Button
        className="fixed bottom-5 left-5 z-50 h-14 w-14 rounded-full border border-primary/35 bg-primary text-primary-foreground shadow-[0_16px_45px_hsl(var(--primary)/0.35)] hover:bg-primary/90"
        onClick={showPanel}
        aria-label="Show assistant"
        title="Show assistant"
      >
        <span className="absolute inset-0 rounded-full bg-accent/25 blur-md" />
        <Bot className="relative h-6 w-6" />
      </Button>
    );
  }

  return (
    <aside
      className={cn(
        "fixed z-50 flex flex-col overflow-hidden rounded-lg border bg-card text-card-foreground shadow-panel",
        mode === "large" && "shadow-2xl",
      )}
      style={panelRect}
    >
      <ResizeHandles onResizeStart={beginResize} />

      <div
        className="flex h-14 min-h-14 cursor-move select-none items-center justify-between border-b px-3 py-2"
        onPointerDown={beginDrag}
      >
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/12 text-primary">
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">TFR Assistant</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={togglePanelSize}
            aria-label={mode === "large" ? "Shrink assistant" : "Expand assistant"}
            title={mode === "large" ? "Shrink assistant" : "Expand assistant"}
          >
            {mode === "large" ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </Button>
          <Button variant="ghost" size="icon" onClick={hidePanel} aria-label="Hide assistant" title="Hide assistant">
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div ref={scrollRef} className="chat-scrollbar flex-1 overflow-auto px-4 py-4">
        <div className="space-y-5">
          {messages.map((message) =>
            message.role === "tool_status" ? (
              <ToolStatusView
                key={message.id}
                message={message}
                collapsed={!message.isLive && collapsedToolMessages.has(message.id)}
                onToggle={() =>
                  setCollapsedToolMessages((current) => {
                    const next = new Set(current);
                    if (next.has(message.id)) next.delete(message.id);
                    else next.add(message.id);
                    return next;
                  })
                }
              />
            ) : (
              <MessageView key={message.id} message={message} isDarkTheme={isDarkTheme} />
            ),
          )}
        </div>
      </div>

      <form className="border-t p-3" onSubmit={sendMessage}>
        <div className="rounded-xl border bg-background p-2 focus-within:ring-2 focus-within:ring-ring">
          <Textarea
            ref={textareaRef}
            className="max-h-[180px] min-h-[48px] resize-none border-0 px-2 py-2 shadow-none focus-visible:ring-0"
            placeholder="Ask about a review, form, eval result, or workflow..."
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void sendMessage();
              }
            }}
          />
          <div className="flex items-center justify-between gap-2 px-1 pb-1">
            <span className="text-xs text-muted-foreground">Enter to send · Shift Enter for a new line</span>
            <Button size="icon" disabled={!input.trim() || isStreaming} aria-label="Send message" title="Send message">
              {isStreaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </form>
    </aside>
  );
}

function ToolStatusView({
  message,
  collapsed,
  onToggle,
}: {
  message: ToolStatusMessage;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const running = message.steps.filter((step) => step.status === "in_progress").length;
  const completed = message.steps.filter((step) => step.status === "completed").length;
  const errors = message.steps.filter((step) => step.status === "error").length;
  const summary =
    message.steps.length === 0
      ? message.isLive
        ? "Preparing agent run"
        : "Agent response started"
      : `${message.steps.length} step${message.steps.length === 1 ? "" : "s"} · ${
          running > 0 ? `${running} running` : `${completed} complete`
        }${errors ? ` · ${errors} error` : ""}`;

  return (
    <div className="rounded-lg border bg-secondary/45 p-3 text-sm">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 text-left"
        onClick={onToggle}
      >
        <span className="flex min-w-0 items-center gap-2">
          {message.isLive ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
          ) : errors ? (
            <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
          ) : (
            <Check className="h-4 w-4 shrink-0 text-emerald-600" />
          )}
          <span className="truncate font-medium text-foreground/85">{summary}</span>
        </span>
        {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>

      {!collapsed ? (
        <div className="mt-3 space-y-2">
          {message.steps.length === 0 ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              {message.isLive ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
              ) : (
                <Check className="h-3.5 w-3.5 text-emerald-600" />
              )}
              {message.isLive ? "Waiting for agent events..." : "Assistant response started."}
            </div>
          ) : (
            message.steps.map((step) => (
              <div key={step.id} className="flex items-start gap-2">
                {step.status === "in_progress" ? (
                  <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
                ) : step.status === "error" ? (
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
                ) : (
                  <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" />
                )}
                <span className="text-foreground/80">{step.message}</span>
              </div>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}

function MessageView({
  message,
  isDarkTheme,
}: {
  message: UserAssistantMessage;
  isDarkTheme: boolean;
}) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[88%] rounded-xl bg-primary px-3 py-2 text-sm leading-relaxed text-primary-foreground shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-none rounded-lg border border-transparent bg-background/40 px-3 py-2 text-sm leading-relaxed">
      <div className="chat-markdown max-w-none">
        {message.content ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={buildMarkdownComponents(isDarkTheme)}>
            {message.content}
          </ReactMarkdown>
        ) : (
          <span className="inline-flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Thinking
          </span>
        )}
      </div>
      {message.streaming ? <span className="mt-1 inline-block h-4 w-1.5 animate-pulse rounded-full bg-primary align-middle" /> : null}
    </div>
  );
}

async function streamAgUiResponse(
  history: UserAssistantMessage[],
  assistantId: string,
  toolStatusId: string,
  threadId: string,
  sharedState: TFRChatState,
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>,
  setSharedState: Dispatch<SetStateAction<TFRChatState>>,
) {
  const response = await fetch(`${apiBaseUrl}/api/chat/ag-ui`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      threadId,
      runId: makeId("run"),
      state: sharedState,
      messages: history.map((message) => ({
        id: message.id,
        role: message.role,
        content: message.content,
      })),
      tools: [],
      context: [
        {
          description: "Application",
          value: "Targeted File Review assistant scaffold with original and user-edited audit forms.",
        },
      ],
      forwardedProps: {},
    }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`Chat endpoint returned ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const rawEvent of events) {
      const dataLines = rawEvent
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim());

      for (const data of dataLines) {
        if (!data || data === "[DONE]") continue;
        applyAgUiEvent(data, assistantId, toolStatusId, setMessages, setSharedState);
      }
    }
  }

  setMessages((current) =>
    current.map((message) =>
      message.id === assistantId
        ? { ...message, streaming: false }
        : message.id === toolStatusId
          ? message.role === "tool_status" ? { ...message, isLive: false } : message
          : message,
    ),
  );
}

function applyAgUiEvent(
  rawData: string,
  assistantId: string,
  toolStatusId: string,
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>,
  setSharedState: Dispatch<SetStateAction<TFRChatState>>,
) {
  let event: {
    type?: string;
    delta?: string;
    message?: string;
    toolCallId?: string;
    toolCallName?: string;
    snapshot?: Partial<TFRChatState>;
  };
  try {
    event = JSON.parse(rawData);
  } catch {
    return;
  }

  if (event.type === "TEXT_MESSAGE_CONTENT" || event.type === "TEXT_MESSAGE_CHUNK") {
    const delta = event.delta ?? "";
    completeToolStatusForTextStart(setMessages, toolStatusId);
    setMessages((current) =>
      current.map((message) =>
        message.id === assistantId && message.role === "assistant"
          ? { ...message, content: `${message.content}${delta}` }
          : message,
      ),
    );
  }

  if (event.type === "TOOL_CALL_START") {
    upsertToolStep(setMessages, toolStatusId, {
      id: event.toolCallId ?? makeId("tool"),
      message: formatToolName(event.toolCallName ?? "tool_call"),
      status: "in_progress",
    });
  }

  if (event.type === "TOOL_CALL_END" && event.toolCallId) {
    setMessages((current) =>
      current.map((message) =>
        message.id === toolStatusId && message.role === "tool_status"
          ? {
              ...message,
              steps: message.steps.map((step) =>
                step.id === event.toolCallId ? { ...step, status: "completed" } : step,
              ),
            }
          : message,
      ),
    );
  }

  if (event.type === "STATE_SNAPSHOT" && event.snapshot) {
    const nextState = normalizeStateSnapshot(event.snapshot);
    setSharedState(nextState);
    for (const entry of nextState.activity_log) {
      upsertToolStep(setMessages, toolStatusId, entry);
    }
  }

  if (event.type === "RUN_FINISHED") {
    setSharedState((current) => ({
      ...current,
      status: current.status === "error" ? "error" : "complete",
      progress: current.status === "error" ? current.progress : 100,
      current_step: current.status === "error" ? current.current_step : "Assistant run complete.",
    }));
  }

  if (event.type === "RUN_ERROR") {
    const message = event.message ?? "Unknown agent error.";
    setSharedState((current) => ({
      ...current,
      status: "error",
      error_message: message,
      current_step: message,
    }));
    upsertToolStep(setMessages, toolStatusId, {
      id: makeId("run-error"),
      message,
      status: "error",
    });
    setMessages((current) =>
      current.map((chatMessage) =>
        chatMessage.id === assistantId
          ? { ...chatMessage, content: `The agent returned an error: ${message}`, streaming: false }
          : chatMessage,
      ),
    );
  }
}

function completeToolStatusForTextStart(
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>,
  toolStatusId: string,
) {
  setMessages((current) =>
    current.map((message) => {
      if (message.id !== toolStatusId || message.role !== "tool_status") return message;
      const steps =
        message.steps.length === 0
          ? [
              {
                id: RESPONSE_STARTED_STEP_ID,
                message: "Assistant response started.",
                status: "completed" as const,
              },
            ]
          : message.steps.map((step) =>
              step.status === "in_progress" ? { ...step, status: "completed" as const } : step,
            );
      return { ...message, isLive: false, steps };
    }),
  );
}

function upsertToolStep(
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>,
  toolStatusId: string,
  nextStep: ToolStep,
) {
  setMessages((current) =>
    current.map((message) => {
      if (message.id !== toolStatusId || message.role !== "tool_status") return message;
      const existingIndex = message.steps.findIndex((step) => step.id === nextStep.id);
      if (existingIndex === -1) {
        return { ...message, steps: [...message.steps, nextStep] };
      }
      const steps = [...message.steps];
      steps[existingIndex] = { ...steps[existingIndex], ...nextStep };
      return { ...message, steps };
    }),
  );
}

function normalizeStateSnapshot(snapshot: Partial<TFRChatState>): TFRChatState {
    return {
    ...initialTfrChatState,
    ...snapshot,
    selected_form_ids: snapshot.selected_form_ids ?? [],
    documents: snapshot.documents ?? [],
    activity_log: snapshot.activity_log ?? [],
  };
}

function buildMarkdownComponents(isDarkTheme: boolean): Components {
  return {
    table({ children }) {
      return (
        <div className="chat-markdown-table-wrap">
          <table>{children}</table>
        </div>
      );
    },
    code({ className, children }) {
      const codeString = toCodeString(children);
      const languageMatch = /language-(\w+)/.exec(className ?? "");
      const language = languageMatch?.[1]?.toLowerCase();
      const isInlineCode = !language && !codeString.includes("\n");

      if (isInlineCode) {
        return <code className={className}>{children}</code>;
      }

      if (language === "mermaid") {
        return <MermaidBlock code={codeString} isDarkTheme={isDarkTheme} />;
      }

      return (
        <CodeBlock
          code={codeString}
          language={language ?? "text"}
          isDarkTheme={isDarkTheme}
        />
      );
    },
    blockquote({ children }) {
      const parsed = parseCalloutChildren(children);
      if (!parsed) {
        return <blockquote>{children}</blockquote>;
      }

      const config = calloutConfig[parsed.type];
      return (
        <div className={cn("chat-callout", config.className)}>
          <div className="chat-callout-title">
            {config.icon}
            <span>{config.label}</span>
          </div>
          <div>{parsed.bodyNodes}</div>
        </div>
      );
    },
    input({ type, checked, ...props }) {
      if (type !== "checkbox") return <input type={type} {...props} />;
      return (
        <input
          type="checkbox"
          defaultChecked={Boolean(checked)}
          className="mr-2 h-4 w-4 rounded border border-border accent-primary"
          aria-label="Checklist item"
        />
      );
    },
    a({ href, children, ...props }) {
      const external = Boolean(href?.startsWith("http"));
      return (
        <a
          href={href}
          target={external ? "_blank" : undefined}
          rel={external ? "noopener noreferrer" : undefined}
          {...props}
        >
          {children}
        </a>
      );
    },
  };
}

function MermaidBlock({
  code,
  isDarkTheme,
}: {
  code: string;
  isDarkTheme: boolean;
}) {
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");
  const safeId = useMemo(() => `mermaid-${crypto.randomUUID()}`, []);

  useEffect(() => {
    let mounted = true;

    async function renderMermaid() {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: isDarkTheme ? "dark" : "default",
        });
        const result = await mermaid.render(safeId, code);
        if (mounted) {
          setSvg(result.svg);
          setError("");
        }
      } catch {
        if (mounted) {
          setSvg("");
          setError("Unable to render Mermaid diagram.");
        }
      }
    }

    void renderMermaid();
    return () => {
      mounted = false;
    };
  }, [code, isDarkTheme, safeId]);

  if (error) {
    return <CodeBlock code={code} language="mermaid" isDarkTheme={isDarkTheme} />;
  }

  if (!svg) {
    return (
      <div className="chat-mermaid-block flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
        Rendering diagram...
      </div>
    );
  }

  return (
    <div
      className="chat-mermaid-block"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

type ResizeDirection = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

function ResizeHandles({
  onResizeStart,
}: {
  onResizeStart: (event: React.PointerEvent<HTMLButtonElement>, direction: ResizeDirection) => void;
}) {
  const handles: Array<{ direction: ResizeDirection; className: string; label: string }> = [
    { direction: "n", label: "Resize top", className: "left-3 right-3 top-[-5px] h-2 cursor-ns-resize" },
    { direction: "s", label: "Resize bottom", className: "bottom-[-5px] left-3 right-3 h-2 cursor-ns-resize" },
    { direction: "e", label: "Resize right", className: "bottom-3 right-[-5px] top-3 w-2 cursor-ew-resize" },
    { direction: "w", label: "Resize left", className: "bottom-3 left-[-5px] top-3 w-2 cursor-ew-resize" },
    { direction: "ne", label: "Resize top right", className: "right-[-6px] top-[-6px] h-4 w-4 cursor-nesw-resize" },
    { direction: "nw", label: "Resize top left", className: "left-[-6px] top-[-6px] h-4 w-4 cursor-nwse-resize" },
    { direction: "se", label: "Resize bottom right", className: "bottom-[-6px] right-[-6px] h-4 w-4 cursor-nwse-resize" },
    { direction: "sw", label: "Resize bottom left", className: "bottom-[-6px] left-[-6px] h-4 w-4 cursor-nesw-resize" },
  ];

  return (
    <>
      {handles.map((handle) => (
        <button
          key={handle.direction}
          type="button"
          aria-label={handle.label}
          title={handle.label}
          onPointerDown={(event) => onResizeStart(event, handle.direction)}
          className={cn("absolute z-20 bg-transparent", handle.className)}
        />
      ))}
    </>
  );
}

function resizeRect(
  start: { left: number; top: number; width: number; height: number },
  direction: ResizeDirection,
  dx: number,
  dy: number,
  mode: ChatPanelMode = "large",
) {
  let { left, top, width, height } = start;

  if (direction.includes("e")) width += dx;
  if (direction.includes("s")) height += dy;
  if (direction.includes("w")) {
    width -= dx;
    left += dx;
  }
  if (direction.includes("n")) {
    height -= dy;
    top += dy;
  }

  if (width < MIN_PANEL_WIDTH) {
    if (direction.includes("w")) left -= MIN_PANEL_WIDTH - width;
    width = MIN_PANEL_WIDTH;
  }

  if (height < MIN_PANEL_HEIGHT) {
    if (direction.includes("n")) top -= MIN_PANEL_HEIGHT - height;
    height = MIN_PANEL_HEIGHT;
  }

  return clampRectToViewport({ left, top, width, height }, mode);
}

function clampRectToViewport(
  rect: { left: number; top: number; width: number; height: number },
  mode: ChatPanelMode = "large",
) {
  const topOffset = mode === "small" ? QUEUE_CONTEXT_TOP_OFFSET : HEADER_OFFSET;
  const bottomOffset = mode === "small" ? QUEUE_CONTEXT_BOTTOM_OFFSET : PANEL_MARGIN;
  const width = Math.min(Math.max(rect.width, MIN_PANEL_WIDTH), window.innerWidth - PANEL_MARGIN * 2);
  const height = Math.min(Math.max(rect.height, MIN_PANEL_HEIGHT), window.innerHeight - topOffset - bottomOffset);
  return {
    left: clamp(rect.left, PANEL_MARGIN, window.innerWidth - width - PANEL_MARGIN),
    top: clamp(rect.top, topOffset, window.innerHeight - height - bottomOffset),
    width,
    height,
  };
}

function CodeBlock({
  code,
  language,
  isDarkTheme,
}: {
  code: string;
  language: string;
  isDarkTheme: boolean;
}) {
  const [copied, setCopied] = useState(false);

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="chat-code-block">
      <div className="chat-code-header">
        <span>{language}</span>
        <button type="button" onClick={copyCode} aria-label="Copy code">
          {copied ? <ClipboardCheck className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={isDarkTheme ? oneDark : oneLight}
        PreTag="pre"
        customStyle={{
          margin: 0,
          borderRadius: "0 0 8px 8px",
          background: "transparent",
          padding: "0.85rem 1rem",
        }}
        codeTagProps={{
          style: {
            fontFamily:
              "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            fontSize: "0.82rem",
          },
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

type CalloutType = "note" | "tip" | "important" | "warning" | "caution";

const calloutConfig: Record<
  CalloutType,
  {
    label: string;
    icon: ReactNode;
    className: string;
  }
> = {
  note: {
    label: "Note",
    icon: <MessageSquareText className="h-4 w-4 text-blue-500" />,
    className: "border-blue-500/35 bg-blue-500/10",
  },
  tip: {
    label: "Tip",
    icon: <Sparkles className="h-4 w-4 text-emerald-500" />,
    className: "border-emerald-500/35 bg-emerald-500/10",
  },
  important: {
    label: "Important",
    icon: <AlertCircle className="h-4 w-4 text-violet-500" />,
    className: "border-violet-500/35 bg-violet-500/10",
  },
  warning: {
    label: "Warning",
    icon: <AlertCircle className="h-4 w-4 text-amber-500" />,
    className: "border-amber-500/35 bg-amber-500/10",
  },
  caution: {
    label: "Caution",
    icon: <AlertCircle className="h-4 w-4 text-red-500" />,
    className: "border-red-500/35 bg-red-500/10",
  },
};

function parseCalloutChildren(
  children: ReactNode,
): { type: CalloutType; bodyNodes: ReactNode[] } | null {
  const nodes = Children.toArray(children);
  const firstNode = nodes[0];
  const firstText =
    typeof firstNode === "string"
      ? firstNode
      : isValidElement<{ children?: ReactNode }>(firstNode)
        ? nodeToPlainText(firstNode.props.children)
        : "";
  const match = firstText.trimStart().match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*/i);
  if (!match) return null;

  const type = match[1].toLowerCase() as CalloutType;
  const bodyText = firstText.trimStart().replace(match[0], "");
  return {
    type,
    bodyNodes: [bodyText, ...nodes.slice(1)].filter(Boolean),
  };
}

function nodeToPlainText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeToPlainText).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return nodeToPlainText(node.props.children);
  return "";
}

function toCodeString(children: ReactNode): string {
  if (typeof children === "string") return children.replace(/\n$/, "");
  if (Array.isArray(children)) {
    return children
      .map((child) => (typeof child === "string" ? child : ""))
      .join("")
      .replace(/\n$/, "");
  }
  return "";
}

function formatToolName(name: string) {
  return name.replaceAll("_", " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function makeId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}
