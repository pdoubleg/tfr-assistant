"use client";

import type { Message } from "@ag-ui/client";
import {
  AlertCircle,
  Bot,
  Brain,
  Check,
  ClipboardCheck,
  ChevronDown,
  ChevronRight,
  Copy,
  CircleAlert,
  Loader2,
  Download,
  Lightbulb,
  Maximize2,
  MessageSquareText,
  Minimize2,
  PanelLeft,
  Plus,
  Send,
  Settings2,
  Sparkles,
  Trash2,
  Wrench,
  X,
} from "lucide-react";
import type { FormEvent, KeyboardEvent, MouseEvent, ReactNode } from "react";
import { Children, isValidElement, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { ShimmeringText } from "@/components/ui/shimmering-text";
import { Textarea } from "@/components/ui/textarea";
import { CodeDisclosure } from "@/components/a2ui/code-disclosure";
import { A2UIRendererList } from "@/components/a2ui/a2ui-renderer";
import type { ChatPanelMode } from "@/components/app-shell/chat-panel-mode-context";
import { isChatComponent } from "@/lib/a2ui-catalog";
import type { A2UIComponent, ChatThreadSummary, ToolStep } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTfrAgent } from "@/hooks/use-tfr-agent";

type ChatRole = "user" | "assistant";

interface UserAssistantMessage {
  id: string;
  role: ChatRole;
  content: string;
  streaming?: boolean;
}

interface ReasoningChatMessage {
  id: string;
  role: "reasoning";
  content: string;
  streaming?: boolean;
}

interface ToolStatusMessage {
  id: string;
  role: "tool_status";
  isLive: boolean;
  steps: ToolStep[];
}

interface ComponentListMessage {
  id: string;
  role: "components";
  components: A2UIComponent[];
}

interface ComponentRunGroup {
  id: string;
  anchorUserId: string;
  components: A2UIComponent[];
}

type StatusTranscriptItem = ReasoningChatMessage | ToolStatusMessage;

interface StatusGroupMessage {
  id: string;
  role: "status_group";
  items: StatusTranscriptItem[];
  finalized: boolean;
}

interface ToolCodePreview {
  code: string;
  language: string;
  title?: string;
  caption?: string;
  defaultOpen?: boolean;
}

type ChatMessage = UserAssistantMessage | ReasoningChatMessage | ToolStatusMessage;
type TranscriptItem = ChatMessage | ComponentListMessage | StatusGroupMessage;

const statusGroupTimingById = new Map<string, { endedAt?: number; startedAt: number }>();

const starterMessages: ChatMessage[] = [
  {
    id: "welcome",
    role: "assistant",
    content:
      "### TFR Assistant\n\nHi, how can I help you today?",
  },
];

const MIN_PANEL_WIDTH = 460;
const MIN_PANEL_HEIGHT = 520;
const HEADER_OFFSET = 72;
const QUEUE_CONTEXT_TOP_OFFSET = 148;
const QUEUE_CONTEXT_BOTTOM_OFFSET = 24;
const PANEL_MARGIN = 8;
const DEFAULT_SMALL_SIZE = { width: 520, height: 0 };
const LARGE_PANEL_WIDTH_RATIO = 0.66;
const LARGE_PANEL_MAX_WIDTH = 1280;
const PROMPT_HISTORY_LIMIT = 30;
const PROMPT_HISTORY_STORAGE_KEY = "tfr-assistant.prompt-history.v1";
const promptSuggestions = [
  "What tools do you have access to?",
  "Fetch some data and generate a few example plots",
  "Fetch some data and generate an example executive summary report",
];

export function DockableChat({
  mode,
  onModeChange,
}: {
  mode: ChatPanelMode;
  onModeChange: (mode: ChatPanelMode) => void;
}) {
  const [input, setInput] = useState("");
  const [promptHistory, setPromptHistory] = useState<string[]>(readPromptHistory);
  const [promptHistoryIndex, setPromptHistoryIndex] = useState<number | null>(null);
  const {
    activeThreadId,
    agent,
    chatModelOptions,
    chatModelSelection,
    chatThreads,
    componentAnchorTurns,
    deleteSavedChatThread,
    homeTableContext,
    isRunning,
    loadChatThread,
    runChatMessage,
    setChatModelSelection,
    startNewChatThread,
    state: sharedState,
    threadError,
    threadsLoading,
  } = useTfrAgent();
  const [expandedToolMessages, setExpandedToolMessages] = useState<Set<string>>(new Set());
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [threadSidebarOpen, setThreadSidebarOpen] = useState(false);
  const [deleteCandidate, setDeleteCandidate] = useState<ChatThreadSummary | null>(null);
  const [deleteInProgress, setDeleteInProgress] = useState(false);
  const liveToolMessagesRef = useRef<Set<string>>(new Set());
  const shouldStickToBottomRef = useRef(true);
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
  const promptDraftRef = useRef("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const componentAnchorByIdRef = useRef<Map<string, string>>(new Map());
  const lastVisibleModeRef = useRef<Exclude<ChatPanelMode, "hidden">>("small");
  const previousModeRef = useRef<ChatPanelMode>(mode);
  const hasVisiblePanelSnapshotRef = useRef(false);
  const restorePreviousRectOnShowRef = useRef(false);
  const messages = useMemo<ChatMessage[]>(
    () => [
      ...starterMessages,
      ...agent.messages
        .map((message) => agentMessageToChatMessage(message, agent.messages, agent.isRunning))
        .flat()
        .filter((message): message is ChatMessage => Boolean(message)),
    ],
    [agent.isRunning, agent.messages],
  );
  const chatComponents = useMemo(
    () => sharedState.components.filter(isChatComponent),
    [sharedState.components],
  );
  const chatComponentGroups = useMemo(
    () => groupComponentsByFirstSeenUser(chatComponents, messages, componentAnchorByIdRef.current),
    [chatComponents, messages],
  );
  const transcriptItems = useMemo<TranscriptItem[]>(
    () =>
      packageCompletedStatusGroups(
        insertComponentGroupsBeforeRunResponses(
          messages,
          chatComponentGroups,
        ),
      ),
    [chatComponentGroups, messages],
  );
  const transcriptScrollKey = useMemo(
    () =>
      transcriptItems
        .map((item) => {
          if (item.role === "components") {
            return `${item.id}:${item.components.map((component) => component.id).join(",")}`;
          }
          if (item.role === "status_group") {
            return `${item.id}:${item.finalized ? "finalized" : "open"}:${item.items
              .map((statusItem) =>
                statusItem.role === "tool_status"
                  ? `${statusItem.id}:${statusItem.isLive}:${statusItem.steps
                      .map((step) => `${step.status}:${step.code?.code.length ?? 0}`)
                      .join(",")}`
                  : `${statusItem.id}:${statusItem.content.length}:${statusItem.streaming ? "streaming" : "done"}`,
              )
              .join("|")}`;
          }
          if (item.role === "tool_status") {
            return `${item.id}:${item.isLive}:${item.steps
              .map((step) => `${step.status}:${step.code?.code.length ?? 0}`)
              .join(",")}`;
          }
          return `${item.id}:${item.content.length}:${item.streaming ? "streaming" : "done"}`;
        })
        .join("|"),
    [transcriptItems],
  );
  const chatGutter = useMemo(() => getChatGutter(panelRect.width, mode), [mode, panelRect.width]);
  const selectedChatModel = useMemo(
    () => chatModelOptions.find((model) => model.name === chatModelSelection.modelName) ?? null,
    [chatModelOptions, chatModelSelection.modelName],
  );
  const reasoningEfforts =
    selectedChatModel?.api === "responses" ? (selectedChatModel.reasoning_efforts ?? []) : [];
  const showReasoningEffortSelector = reasoningEfforts.length > 0;
  const contextWindow = selectedChatModel?.context_window ?? sharedState.chat_context_window;
  const contextRemainingPercent =
    typeof sharedState.chat_context_remaining_percent === "number"
      ? sharedState.chat_context_remaining_percent
      : contextWindow
        ? 100
        : null;

  useEffect(() => {
    componentAnchorByIdRef.current = componentAnchorTurnsToMessageIds(
      agent.messages,
      componentAnchorTurns,
    );
  }, [agent.messages, componentAnchorTurns]);

  useEffect(() => {
    const syncTheme = () => setIsDarkTheme(document.documentElement.classList.contains("dark"));
    syncTheme();
    const observer = new MutationObserver(syncTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    writePromptHistory(promptHistory);
  }, [promptHistory]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [input]);

  useEffect(() => {
    if (!shouldStickToBottomRef.current) return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [sharedState.current_step, transcriptScrollKey]);

  useLayoutEffect(() => {
    const liveIds = new Set(
      messages
        .filter((message): message is ToolStatusMessage => message.role === "tool_status" && message.isLive)
        .map((message) => message.id),
    );
    const previouslyLiveIds = liveToolMessagesRef.current;

    setExpandedToolMessages((current) => {
      const next = new Set(current);
      let changed = false;
      for (const messageId of previouslyLiveIds) {
        if (!liveIds.has(messageId) && next.has(messageId)) {
          next.delete(messageId);
          changed = true;
        }
      }
      return changed ? next : current;
    });

    liveToolMessagesRef.current = liveIds;
  }, [messages]);

  const handleScroll = () => {
    const container = scrollRef.current;
    if (!container) return;
    shouldStickToBottomRef.current =
      container.scrollHeight - container.scrollTop - container.clientHeight < 80;
  };

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
        const width = Math.max(
          MIN_PANEL_WIDTH,
          Math.min(
            Math.floor(window.innerWidth * LARGE_PANEL_WIDTH_RATIO),
            LARGE_PANEL_MAX_WIDTH,
            window.innerWidth - PANEL_MARGIN * 2,
          ),
        );
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
    if (target.closest("button, textarea, a, input, select, [data-chat-model-menu]")) return;

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

  const toggleToolMessage = (messageId: string) => {
    const container = scrollRef.current;
    const previousScrollTop = container?.scrollTop ?? null;
    shouldStickToBottomRef.current = false;
    setExpandedToolMessages((current) => {
      const next = new Set(current);
      if (next.has(messageId)) {
        next.delete(messageId);
      } else {
        next.add(messageId);
      }
      return next;
    });
    if (container && previousScrollTop !== null) {
      window.requestAnimationFrame(() => {
        container.scrollTop = previousScrollTop;
      });
    }
  };

  const rememberPrompt = (content: string) => {
    setPromptHistory((current) => {
      const withoutDuplicate = current.filter((item) => item !== content);
      return [...withoutDuplicate, content].slice(-PROMPT_HISTORY_LIMIT);
    });
    setPromptHistoryIndex(null);
    promptDraftRef.current = "";
  };

  const navigatePromptHistory = (direction: "previous" | "next") => {
    if (!promptHistory.length) return;
    if (direction === "previous") {
      const nextIndex =
        promptHistoryIndex === null
          ? promptHistory.length - 1
          : Math.max(promptHistoryIndex - 1, 0);
      if (promptHistoryIndex === null) {
        promptDraftRef.current = input;
      }
      setPromptHistoryIndex(nextIndex);
      setInput(promptHistory[nextIndex]);
      return;
    }

    if (promptHistoryIndex === null) return;
    const nextIndex = promptHistoryIndex + 1;
    if (nextIndex >= promptHistory.length) {
      setPromptHistoryIndex(null);
      setInput(promptDraftRef.current);
      promptDraftRef.current = "";
      return;
    }
    setPromptHistoryIndex(nextIndex);
    setInput(promptHistory[nextIndex]);
  };

  const handleInputKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
      return;
    }

    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const textarea = event.currentTarget;
    const atStart = textarea.selectionStart === 0 && textarea.selectionEnd === 0;
    const atEnd =
      textarea.selectionStart === textarea.value.length &&
      textarea.selectionEnd === textarea.value.length;

    if (event.key === "ArrowUp" && (promptHistoryIndex !== null || atStart)) {
      event.preventDefault();
      navigatePromptHistory("previous");
      return;
    }

    if (event.key === "ArrowDown" && (promptHistoryIndex !== null || atEnd)) {
      event.preventDefault();
      navigatePromptHistory("next");
    }
  };

  const sendMessage = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault();
    const content = input.trim();
    if (!content || isRunning) return;

    shouldStickToBottomRef.current = true;
    setModelMenuOpen(false);
    setSuggestionsOpen(false);
    rememberPrompt(content);
    setInput("");
    try {
      await runChatMessage(content);
    } catch (error) {
      console.error(error);
    }
  };

  const applyPromptSuggestion = (suggestion: string) => {
    setInput((current) => {
      const trimmed = current.trimEnd();
      return trimmed ? `${trimmed}\n${suggestion}` : suggestion;
    });
    setPromptHistoryIndex(null);
    promptDraftRef.current = "";
    setSuggestionsOpen(false);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  };

  const handleDeleteThread = (
    thread: ChatThreadSummary,
    event: MouseEvent<HTMLButtonElement>,
  ) => {
    event.stopPropagation();
    if (isRunning) return;
    setDeleteCandidate(thread);
  };

  const confirmDeleteThread = async () => {
    if (!deleteCandidate || deleteInProgress) return;
    setDeleteInProgress(true);
    try {
      await deleteSavedChatThread(deleteCandidate.id);
      setDeleteCandidate(null);
    } finally {
      setDeleteInProgress(false);
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
    <>
      <aside
        className={cn(
          "fixed z-50 flex flex-col overflow-hidden rounded-lg border bg-card text-card-foreground shadow-panel",
          mode === "large" && "shadow-2xl",
        )}
        style={panelRect}
      >
        <ResizeHandles onResizeStart={beginResize} />

        <div
          className="flex min-h-[76px] cursor-move select-none items-start justify-between gap-2 border-b px-3 py-2"
          onPointerDown={beginDrag}
        >
          <div className="flex min-w-0 flex-1 items-start gap-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Sparkles className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex min-w-0 items-center gap-2">
                <p className="shrink-0 text-sm font-semibold">TFR Assistant</p>
                <div className="relative min-w-0">
                  <button
                    type="button"
                    className="inline-flex h-7 max-w-[210px] items-center gap-1.5 rounded-md border bg-secondary/35 px-2 text-xs font-medium text-foreground transition-colors hover:bg-secondary"
                    onClick={() => setModelMenuOpen((current) => !current)}
                    aria-expanded={modelMenuOpen}
                    aria-label="Select chat model"
                    title="Select chat model"
                  >
                    <Settings2 className="h-3.5 w-3.5 shrink-0 text-primary" />
                    <span className="truncate">
                      {selectedChatModel?.label ?? chatModelSelection.modelName}
                    </span>
                    <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  </button>
                  {modelMenuOpen ? (
                    <div
                      className="absolute left-0 top-12 z-40 mt-1 w-[min(360px,calc(100vw-3rem))] rounded-lg border bg-card p-3 text-xs shadow-xl"
                      data-chat-model-menu
                    >
                      <div className="grid gap-2">
                        <label className="grid gap-1">
                          <span className="font-medium text-muted-foreground">Model</span>
                          <select
                            value={chatModelSelection.modelName}
                            onChange={(event) => {
                              const nextModel = chatModelOptions.find(
                                (model) => model.name === event.target.value,
                              );
                              setChatModelSelection({
                                modelName: event.target.value,
                                reasoningEffort:
                                  nextModel?.api === "responses"
                                    ? (nextModel.default_reasoning_effort ??
                                      nextModel.reasoning_efforts?.[0] ??
                                      null)
                                    : null,
                              });
                            }}
                            className="h-9 rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            {(chatModelOptions.length
                              ? chatModelOptions
                              : [{ name: chatModelSelection.modelName, label: chatModelSelection.modelName }]
                            ).map((model) => (
                              <option key={model.name} value={model.name}>
                                {model.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        {showReasoningEffortSelector ? (
                          <label className="grid gap-1">
                            <span className="font-medium text-muted-foreground">Reasoning</span>
                            <select
                              value={chatModelSelection.reasoningEffort ?? ""}
                              onChange={(event) =>
                                setChatModelSelection({
                                  modelName: chatModelSelection.modelName,
                                  reasoningEffort: event.target.value
                                    ? (event.target.value as typeof chatModelSelection.reasoningEffort)
                                    : null,
                                })
                              }
                              className="h-9 rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            >
                              {reasoningEfforts.map((effort) => (
                                <option key={effort} value={effort}>
                                  {effort}
                                </option>
                              ))}
                            </select>
                          </label>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[11px] leading-4 text-muted-foreground">
                <span>{formatContextWindow(contextWindow)} context</span>
                {contextRemainingPercent !== null ? (
                  <span>{formatPercent(contextRemainingPercent)} left</span>
                ) : null}
                <span title={sharedState.chat_run_cost ? `Last run ${formatChatCost(sharedState.chat_run_cost)}` : undefined}>
                  {formatChatCost(sharedState.chat_total_cost)} total
                </span>
              </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setThreadSidebarOpen((current) => !current)}
              aria-label={threadSidebarOpen ? "Hide saved chats" : "Show saved chats"}
              title={threadSidebarOpen ? "Hide saved chats" : "Show saved chats"}
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
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

        <div className="flex min-h-0 flex-1">
          {threadSidebarOpen ? (
            <ThreadSidebar
              activeThreadId={activeThreadId}
              threads={chatThreads}
              loading={threadsLoading}
              error={threadError}
              disabled={isRunning || deleteInProgress}
              onNewChat={() => {
                startNewChatThread();
                setInput("");
                setSuggestionsOpen(false);
              }}
              onSelectThread={(threadId) => {
                setInput("");
                setSuggestionsOpen(false);
                void loadChatThread(threadId);
              }}
              onDeleteThread={handleDeleteThread}
            />
          ) : null}

          <div className="flex min-w-0 flex-1 flex-col">
            <div
              ref={scrollRef}
              className="chat-scrollbar flex-1 overflow-auto py-4"
              style={{ paddingLeft: chatGutter, paddingRight: chatGutter }}
              onScroll={handleScroll}
            >
              <div className="flex flex-col">
                {transcriptItems.map((message, index) => (
                  <div
                    key={message.id}
                    className={transcriptItemSpacing(message, transcriptItems[index - 1])}
                  >
                    {message.role === "components" ? (
                      <A2UIRendererList components={message.components} />
                    ) : message.role === "status_group" ? (
                      <StatusGroupView
                        group={message}
                        isDarkTheme={isDarkTheme}
                        expandedToolMessages={expandedToolMessages}
                        onToggleTool={toggleToolMessage}
                      />
                    ) : message.role === "tool_status" ? (
                      <ToolStatusView
                        message={message}
                        collapsed={!expandedToolMessages.has(message.id)}
                        onToggle={() => toggleToolMessage(message.id)}
                      />
                    ) : (
                      <MessageView message={message} isDarkTheme={isDarkTheme} />
                    )}
                  </div>
                ))}
              </div>
            </div>

            <form
              className="border-t py-3"
              style={{ paddingLeft: chatGutter, paddingRight: chatGutter }}
              onSubmit={sendMessage}
            >
              <div className="rounded-xl border bg-background p-2 focus-within:ring-2 focus-within:ring-ring">
                <Textarea
                  ref={textareaRef}
                  className="max-h-[180px] min-h-[48px] resize-none border-0 px-2 py-2 shadow-none focus-visible:ring-0"
                  placeholder="Ask about a review, form, eval result, or workflow..."
                  value={input}
                  onChange={(event) => {
                    setInput(event.target.value);
                    setPromptHistoryIndex(null);
                    promptDraftRef.current = "";
                  }}
                  onKeyDown={handleInputKeyDown}
                />
                <div className="flex items-center justify-between gap-2 px-1 pb-1">
                  <span className="min-w-0 truncate text-xs text-muted-foreground">
                    {homeTableContext.selected_rows.length
                      ? `${homeTableContext.selected_rows.length} selected in home table`
                      : "Enter to send · Shift Enter for a new line"}
                  </span>
                  <div className="flex shrink-0 items-center gap-1">
                    <div className="relative">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => setSuggestionsOpen((current) => !current)}
                        aria-expanded={suggestionsOpen}
                        aria-label="Show prompt suggestions"
                        title="Prompt suggestions"
                      >
                        <Lightbulb className="h-4 w-4" />
                      </Button>
                      {suggestionsOpen ? (
                        <div className="absolute bottom-11 right-0 z-40 w-[min(320px,calc(100vw-3rem))] rounded-lg border bg-card p-2 text-xs shadow-xl">
                          <div className="mb-1 px-2 py-1 font-semibold text-muted-foreground">
                            Suggestions
                          </div>
                          {promptSuggestions.map((suggestion) => (
                            <button
                              key={suggestion}
                              type="button"
                              className="block w-full rounded-md px-2 py-2 text-left text-sm leading-snug hover:bg-secondary"
                              onClick={() => applyPromptSuggestion(suggestion)}
                            >
                              {suggestion}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                    <Button size="icon" disabled={!input.trim() || isRunning} aria-label="Send message" title="Send message">
                      {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    </Button>
                  </div>
                </div>
              </div>
            </form>
          </div>
        </div>
      </aside>
      <DeleteThreadDialog
        thread={deleteCandidate}
        deleting={deleteInProgress}
        onCancel={() => {
          if (!deleteInProgress) setDeleteCandidate(null);
        }}
        onConfirm={() => void confirmDeleteThread()}
      />
    </>
  );
}

function DeleteThreadDialog({
  thread,
  deleting,
  onCancel,
  onConfirm,
}: {
  thread: ChatThreadSummary | null;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  if (!thread) return null;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-background/60 px-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !deleting) onCancel();
      }}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-chat-title"
        aria-describedby="delete-chat-description"
        className="w-full max-w-sm rounded-lg border bg-card p-4 text-card-foreground shadow-2xl"
      >
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-destructive/10 text-destructive">
            <Trash2 className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="delete-chat-title" className="text-sm font-semibold">
              Delete saved chat?
            </h2>
            <p id="delete-chat-description" className="mt-1 text-xs leading-5 text-muted-foreground">
              This removes the saved transcript and any artifacts generated in this thread.
            </p>
          </div>
        </div>

        <div className="mt-4 rounded-md border bg-secondary/25 px-3 py-2">
          <p className="break-words text-sm font-medium">{thread.title || "New chat"}</p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {formatThreadDate(thread.updated_at)}
            {thread.total_cost ? ` · ${formatChatCost(thread.total_cost)} total` : ""}
          </p>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={deleting}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" size="sm" onClick={onConfirm} disabled={deleting}>
            {deleting ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <Trash2 className="mr-2 h-3.5 w-3.5" />}
            Delete
          </Button>
        </div>
      </div>
    </div>
  );
}

function ThreadSidebar({
  activeThreadId,
  threads,
  loading,
  error,
  disabled,
  onNewChat,
  onSelectThread,
  onDeleteThread,
}: {
  activeThreadId: string | null;
  threads: ChatThreadSummary[];
  loading: boolean;
  error: string;
  disabled: boolean;
  onNewChat: () => void;
  onSelectThread: (threadId: string) => void;
  onDeleteThread: (thread: ChatThreadSummary, event: MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <div className="flex w-60 shrink-0 flex-col border-r bg-secondary/20">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <span className="text-xs font-semibold uppercase text-muted-foreground">Chats</span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onNewChat}
          disabled={disabled}
          aria-label="Start new chat"
          title="New chat"
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      {error ? <div className="border-b px-3 py-2 text-xs text-destructive">{error}</div> : null}
      <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="flex items-center gap-2 px-2 py-3 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Loading chats
          </div>
        ) : null}
        {!loading && !threads.length ? (
          <div className="px-2 py-3 text-xs text-muted-foreground">No saved chats yet.</div>
        ) : null}
        <div className="space-y-1">
          {threads.map((thread) => {
            const active = thread.id === activeThreadId;
            return (
              <div
                key={thread.id}
                className={cn(
                  "group/thread flex items-center gap-1 rounded-md",
                  active ? "bg-primary/10 text-primary" : "hover:bg-secondary",
                )}
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 rounded-md px-2 py-2 text-left"
                  onClick={() => onSelectThread(thread.id)}
                  disabled={disabled}
                  aria-current={active ? "true" : undefined}
                >
                  <div className="truncate text-sm font-medium">{thread.title || "New chat"}</div>
                  <div className="mt-0.5 truncate text-[10px] text-muted-foreground">
                    {formatThreadDate(thread.updated_at)}
                    {thread.total_cost ? ` · ${formatChatCost(thread.total_cost)}` : ""}
                  </div>
                </button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="mr-1 h-7 w-7 opacity-70 hover:opacity-100"
                  onClick={(event) => onDeleteThread(thread, event)}
                  disabled={disabled}
                  aria-label={`Delete ${thread.title || "chat"}`}
                  title="Delete chat"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function agentMessageToChatMessage(
  message: Message,
  allMessages: Message[],
  isRunning: boolean,
): ChatMessage[] {
  if (message.role === "reasoning") {
    const content = messageContentToString(message.content);
    const streaming = isRunning && allMessages[allMessages.length - 1]?.id === message.id;
    if (!content && !streaming) return [];
    return [{
      id: message.id,
      role: "reasoning",
      content,
      streaming,
    }];
  }

  if (message.role !== "user" && message.role !== "assistant") return [];
  const toolCalls = getMessageToolCalls(message);
  if (message.role === "assistant" && toolCalls.length) {
    const responseStarted = hasAssistantTextAfter(message, allMessages);
    const completedToolCallIds = new Set(
      allMessages
        .map(getToolResultCallId)
        .filter((toolCallId): toolCallId is string => Boolean(toolCallId)),
    );
    const toolResultContentById = getToolResultContentById(allMessages);
    const steps = toolCalls.map((toolCall) => {
      const completed = completedToolCallIds.has(toolCall.id) || responseStarted;
      const toolResultContent = toolResultContentById.get(toolCall.id);
      const failed = isToolResultError(toolResultContent);
      const executionError = getToolResultExecutionError(toolResultContent);
      return {
        id: toolCall.id,
        message: formatToolStatusMessage(
          toolCall.function.name,
          completed,
          toolCall.function.arguments,
          failed,
        ),
        status: failed ? "error" : completed || !isRunning ? "completed" : "in_progress",
        code:
          toolResultCodePreview(
            toolCall.function.name,
            toolCall.function.arguments,
            toolResultContent,
          ) ?? toolCallCodePreview(toolCall.function.name, toolCall.function.arguments),
        error: executionError
          ? {
              message: executionError,
              title: "Execution Error",
              caption: "Returned to model",
            }
          : undefined,
      } satisfies ToolStep;
    });
    return [
      {
        id: `tools-${message.id}`,
        role: "tool_status",
        isLive: steps.some((step) => step.status === "in_progress"),
        steps,
      },
    ];
  }

  const content = messageContentToString(message.content);
  if (!content && message.role === "assistant") {
    if (!isRunning) return [];
    return [{
      id: message.id,
      role: "assistant",
      content: "",
      streaming: isRunning,
    }];
  }
  return [{
    id: message.id,
    role: message.role,
    content,
    streaming: false,
  }];
}

function hasAssistantTextAfter(message: Message, allMessages: Message[]) {
  const currentIndex = allMessages.indexOf(message);
  if (currentIndex === -1) return false;
  return allMessages
    .slice(currentIndex + 1)
    .some((candidate) => candidate.role === "assistant" && messageContentToString(candidate.content).trim());
}

function componentAnchorTurnsToMessageIds(
  messages: Message[],
  componentAnchorTurns: Record<string, number>,
): Map<string, string> {
  const userMessageIds = messages
    .filter((message) => message.role === "user")
    .map((message) => message.id);
  const fallback = userMessageIds[userMessageIds.length - 1] ?? "welcome";
  const anchors = new Map<string, string>();

  for (const [componentId, turn] of Object.entries(componentAnchorTurns)) {
    const index = Math.max(0, Math.min(userMessageIds.length - 1, Math.trunc(turn) - 1));
    anchors.set(componentId, userMessageIds[index] ?? fallback);
  }

  return anchors;
}

function groupComponentsByFirstSeenUser(
  components: A2UIComponent[],
  messages: ChatMessage[],
  anchorByComponentId: Map<string, string>,
): ComponentRunGroup[] {
  const fallbackAnchor = "welcome";
  const latestUserId =
    [...messages].reverse().find((message) => message.role === "user")?.id ?? fallbackAnchor;
  const currentComponentIds = new Set(components.map((component) => component.id));

  for (const componentId of Array.from(anchorByComponentId.keys())) {
    if (!currentComponentIds.has(componentId)) {
      anchorByComponentId.delete(componentId);
    }
  }

  const groups = new Map<string, A2UIComponent[]>();
  for (const component of components) {
    if (!anchorByComponentId.has(component.id)) {
      anchorByComponentId.set(component.id, latestUserId);
    }
    const anchorUserId = anchorByComponentId.get(component.id) ?? fallbackAnchor;
    groups.set(anchorUserId, [...(groups.get(anchorUserId) ?? []), component]);
  }

  return Array.from(groups.entries()).map(([anchorUserId, groupComponents]) => ({
    id: `components-${anchorUserId}`,
    anchorUserId,
    components: groupComponents,
  }));
}

function insertComponentGroupsBeforeRunResponses(
  messages: ChatMessage[],
  componentGroups: ComponentRunGroup[],
): TranscriptItem[] {
  const items: TranscriptItem[] = [...messages];
  if (!componentGroups.length) return items;

  for (const group of componentGroups) {
    const componentMessage: ComponentListMessage = {
      id: group.id,
      role: "components",
      components: group.components,
    };
    const anchorIndex = items.findIndex(
      (item) => item.role === "user" && item.id === group.anchorUserId,
    );
    const runStart = anchorIndex === -1 ? items.length : anchorIndex + 1;
    const nextUserIndex = items.findIndex(
      (item, index) => index >= runStart && item.role === "user",
    );
    const runEnd = nextUserIndex === -1 ? items.length : nextUserIndex;
    const firstAssistantResponseIndex = items.findIndex(
      (item, index) =>
        index >= runStart &&
        index < runEnd &&
        item.role === "assistant" &&
        item.content.trim().length > 0,
    );

    if (firstAssistantResponseIndex !== -1) {
      items.splice(firstAssistantResponseIndex, 0, componentMessage);
      continue;
    }

    const lastToolStatusIndex = findLastIndex(
      items,
      (item, index) =>
        index >= runStart &&
        index < runEnd &&
        item.role === "tool_status",
    );
    items.splice(lastToolStatusIndex === -1 ? runEnd : lastToolStatusIndex + 1, 0, componentMessage);
  }
  return items;
}

function packageCompletedStatusGroups(items: TranscriptItem[]): TranscriptItem[] {
  const packagedItems: TranscriptItem[] = [];
  let pending: StatusTranscriptItem[] = [];

  const flushPending = (finalized: boolean) => {
    if (!pending.length) return;
    const groupIsLive = pending.some((item) =>
      item.role === "tool_status" ? item.isLive : Boolean(item.streaming),
    );
    if (groupIsLive) {
      packagedItems.push(...pending);
    } else {
      packagedItems.push({
        id: `status-group-${pending[0].id}`,
        role: "status_group",
        items: pending,
        finalized,
      });
    }
    pending = [];
  };

  for (const item of items) {
    if (isPackageableStatus(item)) {
      if (isStatusItemLive(item)) {
        flushPending(false);
        packagedItems.push(item);
        continue;
      }
      pending.push(item);
      continue;
    }

    flushPending(true);
    packagedItems.push(item);
  }

  flushPending(false);
  return packagedItems;
}

function isStatusItemLive(item: StatusTranscriptItem) {
  return item.role === "tool_status" ? item.isLive : Boolean(item.streaming);
}

function getStatusGroupTiming(groupId: string, finalized: boolean) {
  let timing = statusGroupTimingById.get(groupId);
  if (!timing) {
    const now = Date.now();
    timing = { startedAt: now, endedAt: finalized ? now : undefined };
    statusGroupTimingById.set(groupId, timing);
  }
  return timing;
}

function formatWorkDuration(milliseconds: number) {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}m ${seconds}s`;
}

function formatContextWindow(value: number | null | undefined) {
  if (!value) return "Unknown";
  if (value >= 1_000_000) {
    const millions = value / 1_000_000;
    return `${Number.isInteger(millions) ? millions.toFixed(0) : millions.toFixed(2)}M`;
  }
  if (value >= 1_000) {
    const thousands = value / 1_000;
    return `${Number.isInteger(thousands) ? thousands.toFixed(0) : thousands.toFixed(1)}K`;
  }
  return value.toLocaleString();
}

function formatPercent(value: number) {
  return `${Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1)}%`;
}

function formatChatCost(value: number | null | undefined) {
  const cost = Math.max(0, value ?? 0);
  if (cost === 0) return "$0.00";
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

function formatThreadDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function findLastIndex<T>(items: T[], predicate: (item: T, index: number) => boolean) {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (predicate(items[index], index)) return index;
  }
  return -1;
}

function transcriptItemSpacing(item: TranscriptItem, previous: TranscriptItem | undefined) {
  if (!previous) return "";
  const itemIsStatus = isTranscriptStatus(item);
  const previousIsStatus = isTranscriptStatus(previous);
  if (itemIsStatus && previousIsStatus) return "mt-1";
  if (itemIsStatus || previousIsStatus) return "mt-2.5";
  return "mt-5";
}

function isTranscriptStatus(item: TranscriptItem): item is StatusTranscriptItem | StatusGroupMessage {
  return item.role === "reasoning" || item.role === "tool_status" || item.role === "status_group";
}

function isPackageableStatus(item: TranscriptItem): item is StatusTranscriptItem {
  return item.role === "reasoning" || item.role === "tool_status";
}

function readPromptHistory(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(PROMPT_HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
      .slice(-PROMPT_HISTORY_LIMIT);
  } catch {
    return [];
  }
}

function writePromptHistory(history: string[]) {
  if (typeof window === "undefined") return;
  try {
    if (!history.length) {
      window.localStorage.removeItem(PROMPT_HISTORY_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(PROMPT_HISTORY_STORAGE_KEY, JSON.stringify(history));
  } catch {
    // Ignore storage errors; prompt history is a convenience layer.
  }
}

type ToolCallLike = {
  id: string;
  function: {
    name: string;
    arguments?: string;
  };
};

function getMessageToolCalls(message: Message): ToolCallLike[] {
  if (!("toolCalls" in message) || !Array.isArray(message.toolCalls)) return [];
  return message.toolCalls
    .map((toolCall) => {
      if (
        !toolCall ||
        typeof toolCall !== "object" ||
        !("id" in toolCall) ||
        typeof toolCall.id !== "string" ||
        !("function" in toolCall) ||
        !toolCall.function ||
        typeof toolCall.function !== "object" ||
        !("name" in toolCall.function) ||
        typeof toolCall.function.name !== "string"
      ) {
        return null;
      }
      return toolCall as ToolCallLike;
    })
    .filter((toolCall): toolCall is ToolCallLike => Boolean(toolCall));
}

function getToolResultCallId(message: Message) {
  if (message.role !== "tool") return null;
  const record = message as Message & {
    toolCallId?: unknown;
    tool_call_id?: unknown;
  };
  if (typeof record.toolCallId === "string") return record.toolCallId;
  if (typeof record.tool_call_id === "string") return record.tool_call_id;
  return null;
}

function getToolResultContentById(messages: Message[]) {
  const results = new Map<string, string>();
  for (const message of messages) {
    const toolCallId = getToolResultCallId(message);
    if (!toolCallId) continue;
    results.set(toolCallId, toolResultContentToString(message.content));
  }
  return results;
}

function toolResultContentToString(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return messageContentToString(content);
  if (!content || typeof content !== "object") return "";
  try {
    return JSON.stringify(content);
  } catch {
    return "";
  }
}

function isToolResultError(result: string | undefined) {
  if (!result?.trim()) return false;
  try {
    const parsed = JSON.parse(result) as unknown;
    return hasErrorStatus(parsed);
  } catch {
    return false;
  }
}

function getToolResultExecutionError(result: string | undefined) {
  if (!result?.trim()) return null;
  try {
    const parsed = JSON.parse(result) as unknown;
    return findExecutionError(parsed);
  } catch {
    return null;
  }
}

function hasErrorStatus(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const record = value as {
    content?: unknown;
    result?: unknown;
    return_value?: unknown;
    returnValue?: unknown;
    status?: unknown;
  };
  if (record.status === "error") return true;
  return (
    hasErrorStatus(record.return_value) ||
    hasErrorStatus(record.returnValue) ||
    hasErrorStatus(record.result) ||
    hasErrorStatus(record.content)
  );
}

function findExecutionError(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const record = value as {
    content?: unknown;
    error?: unknown;
    error_details?: { message?: unknown };
    model_guidance?: unknown;
    result?: unknown;
    return_value?: unknown;
    returnValue?: unknown;
    status?: unknown;
  };
  if (record.status === "error") {
    if (typeof record.error === "string" && record.error.trim()) return record.error.trim();
    const detailsMessage = record.error_details?.message;
    if (typeof detailsMessage === "string" && detailsMessage.trim()) {
      return detailsMessage.trim();
    }
    if (typeof record.model_guidance === "string" && record.model_guidance.trim()) {
      return record.model_guidance.trim();
    }
  }
  return (
    findExecutionError(record.return_value) ||
    findExecutionError(record.returnValue) ||
    findExecutionError(record.result) ||
    findExecutionError(record.content)
  );
}

function formatToolName(name: string) {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatToolStatusMessage(
  name: string,
  completed: boolean,
  args: string | undefined,
  failed = false,
) {
  const parsed = parseToolArgs(args);
  const tableName = getStringArg(parsed, "table_name");
  const scope = getStringArg(parsed, "scope");
  const code = getStringArg(parsed, "code");
  const helpTarget = getStringArg(parsed, "name").trim();

  if (isHelpToolName(name)) {
    const target = helpTarget || "overview";
    return completed
      ? `Python repl help loaded: ${target}.`
      : `Loading Python repl help: ${target}...`;
  }

  if (isExecuteToolName(name)) {
    if (failed) {
      return name === "execute" ? "Database query failed." : "Python repl failed.";
    }
    if (code.trim()) {
      return completed ? "Python repl completed." : "Running Python repl...";
    }
  }
  if (name === "execute") {
    const scopeSuffix = scope ? ` (${scope} scope)` : "";
    return completed
      ? `Database query completed${scopeSuffix}.`
      : `Running database query${scopeSuffix}...`;
  }
  if (name === "explain") {
    const scopeSuffix = scope ? ` (${scope} scope)` : "";
    return completed
      ? `Query plan prepared${scopeSuffix}.`
      : `Preparing query plan${scopeSuffix}...`;
  }
  if (name === "get_table_info") {
    return completed
      ? `Finished inspecting ${tableName || "table"}.`
      : `Inspecting ${tableName || "table"}...`;
  }
  if (name === "get_foreign_keys") {
    return completed
      ? `Loaded foreign keys for ${tableName || "table"}.`
      : `Reading foreign keys for ${tableName || "table"}...`;
  }
  if (name === "get_related_tables") {
    return completed
      ? `Found tables related to ${tableName || "table"}.`
      : `Finding tables related to ${tableName || "table"}...`;
  }
  if (name === "get_schema") {
    return completed ? "Database schema loaded." : "Inspecting database schema...";
  }
  if (name === "get_tables") {
    return completed ? "Database table list loaded." : "Reading database table list...";
  }
  if (name === "get_selected_rows_info") {
    return completed
      ? "Selected-row SQL context loaded."
      : "Reading selected-row SQL context...";
  }
  if (name.startsWith("get_")) {
    return completed ? "Database inspection completed." : "Inspecting database...";
  }
  return `${formatToolName(name)} ${completed ? "completed" : "running"}.`;
}

function toolCallCodePreview(
  name: string,
  args: string | undefined,
): ToolCodePreview | undefined {
  if (!isExecuteToolName(name) || !args) return undefined;
  const parsed = parseToolArgs(args);
  const code = getStringArg(parsed, "code");
  if (code.trim()) {
    return {
      code,
      language: "python",
      title: "Python",
      caption: "Python repl",
      defaultOpen: false,
    };
  }
  const sql = getStringArg(parsed, "sql") || getStringArg(parsed, "sql_query") || getStringArg(parsed, "query");
  if (!sql.trim()) return undefined;
  const scope = getStringArg(parsed, "scope");
  const limit = getStringArg(parsed, "limit");
  const caption = [
    scope ? `Scope: ${scope}` : "",
    limit ? `Preview limit: ${limit}` : "",
  ].filter(Boolean).join(" · ");
  return {
    code: formatSqlForDisplay(sql),
    language: "sql",
    title: "SQL",
    caption,
    defaultOpen: false,
  };
}

function toolResultCodePreview(
  name: string,
  args: string | undefined,
  result: string | undefined,
): ToolCodePreview | undefined {
  if (!isHelpToolName(name) || !result?.trim()) return undefined;
  const parsed = parseToolArgs(args);
  const target = getStringArg(parsed, "name").trim() || "overview";
  return {
    code: result,
    language: "markdown",
    title: "Help",
    caption: `Python repl help: ${target}`,
    defaultOpen: false,
  };
}

function isExecuteToolName(name: string): boolean {
  return name === "execute" || name.endsWith("_execute");
}

function isHelpToolName(name: string): boolean {
  return name === "help" || name.endsWith("_help");
}

function formatSqlForDisplay(sql: string): string {
  const tokens = tokenizeSql(sql.trim().replace(/\s+/g, " "));
  const lines: string[] = [];
  let current = "";
  let indent = 0;
  let parenDepth = 0;

  const push = () => {
    const line = current.trim();
    if (line) lines.push(`${"  ".repeat(Math.max(indent, 0))}${line}`);
    current = "";
  };
  const append = (token: string) => {
    current = current ? `${current} ${token}` : token;
  };

  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    const next = tokens[index + 1] ?? "";
    const upper = token.toUpperCase();
    const twoWord = `${upper} ${next.toUpperCase()}`;

    if (
      twoWord === "GROUP BY" ||
      twoWord === "ORDER BY" ||
      twoWord === "LEFT JOIN" ||
      twoWord === "RIGHT JOIN" ||
      twoWord === "FULL JOIN" ||
      twoWord === "INNER JOIN" ||
      twoWord === "CROSS JOIN"
    ) {
      push();
      append(twoWord);
      index += 1;
      continue;
    }

    if (["SELECT", "FROM", "WHERE", "HAVING", "LIMIT", "OFFSET"].includes(upper)) {
      push();
      append(upper);
      continue;
    }

    if (upper === "JOIN") {
      push();
      append(upper);
      continue;
    }

    if (upper === "ON") {
      push();
      append(upper);
      continue;
    }

    if (upper === "AND" || upper === "OR") {
      push();
      append(upper);
      continue;
    }

    if (token === "(") {
      append(token);
      parenDepth += 1;
      indent += 1;
      continue;
    }

    if (token === ")") {
      push();
      parenDepth = Math.max(parenDepth - 1, 0);
      indent = Math.max(indent - 1, 0);
      append(token);
      continue;
    }

    if (token === ",") {
      current = `${current.trimEnd()},`;
      if (parenDepth === 0) push();
      continue;
    }

    append(token);
  }

  push();
  return lines.join("\n");
}

function tokenizeSql(sql: string): string[] {
  const tokens: string[] = [];
  let current = "";
  let quote: "'" | '"' | "`" | null = null;

  const push = () => {
    if (current) {
      tokens.push(current);
      current = "";
    }
  };

  for (let index = 0; index < sql.length; index += 1) {
    const character = sql[index];
    if (quote) {
      current += character;
      if (character === quote) {
        const next = sql[index + 1];
        if (quote === "'" && next === "'") {
          current += next;
          index += 1;
        } else {
          quote = null;
        }
      }
      continue;
    }

    if (character === "'" || character === '"' || character === "`") {
      push();
      quote = character;
      current = character;
      continue;
    }

    if (/\s/.test(character)) {
      push();
      continue;
    }

    if (character === "(" || character === ")" || character === ",") {
      push();
      tokens.push(character);
      continue;
    }

    current += character;
  }

  push();
  return tokens;
}

function parseToolArgs(args: string | undefined): Record<string, unknown> {
  if (!args) return {};
  try {
    const parsed = JSON.parse(args) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

function getStringArg(args: Record<string, unknown>, key: string): string {
  const value = args[key];
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string") return item;
        if (typeof item === "number" || typeof item === "boolean") return String(item);
        return "";
      })
      .filter(Boolean)
      .join(", ");
  }
  return "";
}

function messageContentToString(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((part) => {
      if (typeof part === "string") return part;
      if (part && typeof part === "object" && "text" in part) {
        const text = (part as { text?: unknown }).text;
        return typeof text === "string" ? text : "";
      }
      return "";
    })
    .join("");
}

function StatusGroupView({
  group,
  expandedToolMessages,
  isDarkTheme,
  onToggleTool,
}: {
  group: StatusGroupMessage;
  expandedToolMessages: Set<string>;
  isDarkTheme: boolean;
  onToggleTool: (messageId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [timing] = useState(() => getStatusGroupTiming(group.id, group.finalized));
  const [now, setNow] = useState(() => Date.now());
  const stats = statusGroupStats(group.items);
  const groupIsOpen = !group.finalized;

  useEffect(() => {
    if (!groupIsOpen) {
      timing.endedAt ??= Date.now();
      setNow(timing.endedAt);
      return;
    }

    timing.endedAt = undefined;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [groupIsOpen, timing]);

  const elapsed = formatWorkDuration((timing.endedAt ?? now) - timing.startedAt);
  const label = `${groupIsOpen ? "Working" : "Worked"} for ${elapsed}${
    stats.errors ? ` · ${stats.errors} error${stats.errors === 1 ? "" : "s"}` : ""
  }`;

  return (
    <div
      className={cn(
        "text-xs text-muted-foreground transition-colors",
        expanded
          ? "rounded-md border bg-secondary/25 p-2"
          : "-mx-1 rounded-md border border-transparent bg-transparent px-1.5 py-1 hover:bg-secondary/25",
      )}
    >
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 text-left"
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <Check className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
          <ShimmeringText
            active={groupIsOpen}
            breakDuration={0.35}
            className="truncate font-normal text-muted-foreground"
            duration={1.35}
            text={label}
          />
          {stats.errors ? (
            <CircleAlert
              className="h-3 w-3 shrink-0 text-amber-500"
              aria-label={`${stats.errors} recoverable error${stats.errors === 1 ? "" : "s"}`}
            />
          ) : null}
        </span>
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground/75" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/75" />
        )}
      </button>

      {expanded ? (
        <div className="mt-1.5 space-y-1">
          {group.items.map((item) =>
            item.role === "tool_status" ? (
              <ToolStatusView
                key={item.id}
                message={item}
                collapsed={!expandedToolMessages.has(item.id)}
                onToggle={() => onToggleTool(item.id)}
              />
            ) : (
              <MessageView key={item.id} message={item} isDarkTheme={isDarkTheme} />
            ),
          )}
        </div>
      ) : null}
    </div>
  );
}

function statusGroupStats(items: StatusTranscriptItem[]) {
  return items.reduce(
    (stats, item) => {
      if (item.role === "reasoning") {
        return {
          ...stats,
          steps: stats.steps + 1,
        };
      }

      const stepCount = Math.max(item.steps.length, 1);
      const errorCount = item.steps.filter((step) => step.status === "error").length;
      return {
        steps: stats.steps + stepCount,
        errors: stats.errors + errorCount,
      };
    },
    { steps: 0, errors: 0 },
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
  const steps = message.steps.map((step) => ({
    ...step,
    status:
      !message.isLive && step.status === "in_progress"
        ? "completed"
        : step.status,
  })) satisfies ToolStep[];
  const running = steps.filter((step) => step.status === "in_progress").length;
  const completed = steps.filter((step) => step.status === "completed").length;
  const errors = steps.filter((step) => step.status === "error").length;
  const summary =
    steps.length === 0
      ? message.isLive
        ? "Preparing agent run"
        : "Agent response started"
      : `${steps.length} step${steps.length === 1 ? "" : "s"} · ${
          running > 0 ? `${running} running` : `${completed} complete`
        }${errors ? ` · ${errors} error` : ""}`;
  const expanded = !collapsed;

  return (
    <div
      className={cn(
        "transition-colors",
        expanded
          ? "rounded-lg border bg-secondary/45 p-3 text-sm"
          : "-mx-1 rounded-md border border-transparent bg-transparent px-1.5 py-1 text-xs text-muted-foreground hover:bg-secondary/25",
      )}
    >
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 text-left"
        onClick={onToggle}
      >
        <span className={cn("flex min-w-0 items-center", expanded ? "gap-2" : "gap-1.5")}>
          <Wrench
            className={cn(
              "shrink-0 text-primary/75",
              expanded ? "h-4 w-4" : "h-3.5 w-3.5",
            )}
          />
          <ShimmeringText
            active={message.isLive}
            className={cn(
              "truncate",
              expanded ? "font-medium text-foreground/85" : "font-normal text-muted-foreground",
            )}
            duration={1.35}
            text={summary}
          />
          {errors ? (
            <CircleAlert
              className="h-3 w-3 shrink-0 text-amber-500"
              aria-label={`${errors} recoverable tool error${errors === 1 ? "" : "s"}`}
            />
          ) : null}
        </span>
        {collapsed ? (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/75" />
        ) : (
          <ChevronDown className="h-4 w-4" />
        )}
      </button>

      {expanded ? (
        <div className="mt-3 space-y-2">
          {steps.length === 0 ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              {message.isLive ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
              ) : (
                <Check className="h-3.5 w-3.5 text-emerald-600" />
              )}
              {message.isLive ? "Waiting for agent events..." : "Assistant response started."}
            </div>
          ) : (
            steps.map((step) => (
              <div key={step.id} className="space-y-2">
                <div className="flex items-start gap-2">
                  {step.status === "in_progress" ? (
                    <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
                  ) : step.status === "error" ? (
                    <X className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
                  ) : (
                    <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" />
                  )}
                  <span className="text-foreground/80">{step.message}</span>
                </div>
                {step.code ? (
                  <CodeDisclosure
                    code={step.code.code}
                    language={step.code.language}
                    title={step.code.title}
                    caption={step.code.caption}
                    defaultOpen={step.code.defaultOpen}
                    density="compact"
                    className="ml-5"
                  />
                ) : null}
                {step.error ? (
                  <CodeDisclosure
                    code={step.error.message}
                    language="text"
                    title={step.error.title ?? "Execution Error"}
                    caption={step.error.caption}
                    defaultOpen={false}
                    density="compact"
                    tone="error"
                    className="ml-5"
                  />
                ) : null}
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
  message: UserAssistantMessage | ReasoningChatMessage;
  isDarkTheme: boolean;
}) {
  if (message.role === "reasoning") {
    return <ReasoningMessageView message={message} isDarkTheme={isDarkTheme} />;
  }

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

function ReasoningMessageView({
  message,
  isDarkTheme,
}: {
  message: ReasoningChatMessage;
  isDarkTheme: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [dotCount, setDotCount] = useState(0);

  useEffect(() => {
    if (!message.streaming) {
      setDotCount(0);
      return;
    }

    const timer = window.setInterval(() => {
      setDotCount((current) => (current + 1) % 4);
    }, 360);
    return () => window.clearInterval(timer);
  }, [message.streaming]);

  const hasContent = message.content.trim().length > 0;
  const expanded = open && hasContent;
  return (
    <div
      className={cn(
        "text-xs text-muted-foreground transition-colors",
        expanded
          ? "rounded-md border bg-secondary/25 px-2.5 py-1.5"
          : "-mx-1 rounded-md border border-transparent bg-transparent px-1.5 py-1 hover:bg-secondary/25",
      )}
    >
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 text-left"
        onClick={() => hasContent && setOpen((current) => !current)}
        aria-expanded={hasContent ? open : undefined}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <Brain className="h-3.5 w-3.5 shrink-0 text-primary/75" />
          <ShimmeringText
            active={Boolean(message.streaming)}
            className="truncate font-normal"
            duration={1.35}
            text={`Thinking${message.streaming ? ".".repeat(dotCount) : ""}`}
          />
        </span>
        {hasContent ? (
          open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />
        ) : null}
      </button>
      {expanded ? (
        <div className="chat-markdown mt-1.5 border-l pl-2.5 text-xs text-foreground/70">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={buildMarkdownComponents(isDarkTheme)}>
            {message.content}
          </ReactMarkdown>
        </div>
      ) : null}
    </div>
  );
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
    <div className="chat-mermaid-block group/mermaid relative">
      <div className="chat-mermaid-actions">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 gap-1 px-2 text-[10px]"
          onClick={() => downloadMermaidSvg(svg)}
          aria-label="Download Mermaid SVG"
          title="Download SVG"
        >
          <Download className="h-3 w-3" />
          SVG
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 gap-1 px-2 text-[10px]"
          onClick={() => void downloadMermaidPng(svg)}
          aria-label="Download Mermaid PNG"
          title="Download PNG"
        >
          <Download className="h-3 w-3" />
          PNG
        </Button>
      </div>
      <div dangerouslySetInnerHTML={{ __html: svg }} />
    </div>
  );
}

function downloadMermaidSvg(svg: string) {
  triggerBlobDownload(
    new Blob([svg], { type: "image/svg+xml;charset=utf-8" }),
    mermaidFilename("svg"),
  );
}

async function downloadMermaidPng(svg: string) {
  const svgUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }));
  try {
    const image = await loadImage(svgUrl);
    const width = image.naturalWidth || 1200;
    const height = image.naturalHeight || 800;
    const scale = 2;
    const canvas = document.createElement("canvas");
    canvas.width = width * scale;
    canvas.height = height * scale;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.scale(scale, scale);
    context.drawImage(image, 0, 0, width, height);
    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, "image/png");
    });
    if (blob) {
      triggerBlobDownload(blob, mermaidFilename("png"));
    }
  } finally {
    URL.revokeObjectURL(svgUrl);
  }
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Unable to prepare Mermaid image download."));
    image.src = src;
  });
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function mermaidFilename(extension: "svg" | "png") {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  return `mermaid-diagram-${stamp}.${extension}`;
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

function getChatGutter(width: number, mode: ChatPanelMode) {
  if (mode === "small") return 16;
  if (width >= 1180) return 32;
  if (width >= 900) return 28;
  if (width >= 680) return 24;
  return 16;
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

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}
