"use client";

import { useAgent } from "@copilotkit/react-core/v2/headless";
import type { UseAgentUpdate } from "@copilotkit/react-core/v2/headless";
import type { AbstractAgent, Message, State } from "@ag-ui/client";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { deleteChatThread, getChatThread, listChatModels, listChatThreads } from "@/lib/api";
import type {
  ChatModelOption,
  ChatRunContext,
  ChatThreadSummary,
  HomeTableContext,
  OutputComponent,
  ReasoningEffort,
  TFRChatState,
} from "@/lib/types";

export const TFR_AGENT_ID = "tfr_agent";
export const TFR_CHAT_MODEL_CONTEXT_DESCRIPTION = "TFR chat model selection";

const agentUpdates = [
  "OnMessagesChanged",
  "OnStateChanged",
  "OnRunStatusChanged",
] as unknown as UseAgentUpdate[];

const emptyHomeTableContext: HomeTableContext = {
  selected_rows: [],
  visible_row_count: 0,
  total_row_count: 0,
  filters: {
    search: "",
    column_filters: {},
    sorting: [],
    page_index: 0,
    page_size: 25,
    density: "normal",
  },
};

interface ChatModelSelection {
  modelName: string;
  reasoningEffort: ReasoningEffort | null;
}

const defaultChatModelSelection: ChatModelSelection = {
  modelName: "gpt-5.4-mini",
  reasoningEffort: "low",
};

export const initialTfrChatState: TFRChatState = {
  active_route: "/",
  active_review_id: null,
  selected_form_ids: [],
  documents: [],
  artifact_session_id: "",
  handles: [],
  components: [],
  run_context: null,
  status: "idle",
  progress: 0,
  current_step: "",
  activity_log: [],
  error_message: null,
  chat_model_name: "",
  chat_context_window: null,
  chat_context_used_tokens: 0,
  chat_context_remaining_percent: null,
  chat_run_cost: 0,
  chat_total_cost: 0,
  chat_last_usage: {},
};

interface TfrAgentContextValue {
  agent: AbstractAgent;
  state: TFRChatState;
  setState: (state: TFRChatState | ((current: TFRChatState) => TFRChatState)) => void;
  homeTableContext: HomeTableContext;
  setHomeTableContext: (context: HomeTableContext) => void;
  buildRunContextSnapshot: () => ChatRunContext;
  runChatMessage: (content: string) => Promise<void>;
  stop: () => void;
  isRunning: boolean;
  chatModelOptions: ChatModelOption[];
  chatModelSelection: ChatModelSelection;
  setChatModelSelection: (selection: ChatModelSelection) => void;
  chatThreads: ChatThreadSummary[];
  activeThreadId: string | null;
  componentAnchorTurns: Record<string, number>;
  threadsLoading: boolean;
  threadError: string;
  refreshChatThreads: () => Promise<void>;
  loadChatThread: (threadId: string) => Promise<void>;
  startNewChatThread: () => void;
  deleteSavedChatThread: (threadId: string) => Promise<void>;
  outputComponents: OutputComponent[];
  openOutputComponent: (component: OutputComponent) => void;
  closeOutputComponent: (componentId: string) => void;
  collapseOutputComponent: (componentId: string) => void;
  expandOutputComponent: (componentId: string) => void;
}

const TfrAgentContext = createContext<TfrAgentContextValue | null>(null);

export function TfrAgentProvider({ children }: { children: ReactNode }) {
  const { agent } = useAgent({
    agentId: TFR_AGENT_ID,
    updates: agentUpdates,
    throttleMs: 50,
  });
  const [homeTableContext, setHomeTableContext] =
    useState<HomeTableContext>(emptyHomeTableContext);
  const [outputComponents, setOutputComponents] = useState<OutputComponent[]>([]);
  const [chatModelOptions, setChatModelOptions] = useState<ChatModelOption[]>([]);
  const [chatModelSelection, setChatModelSelectionState] =
    useState<ChatModelSelection>(defaultChatModelSelection);
  const [chatThreads, setChatThreads] = useState<ChatThreadSummary[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [componentAnchorTurns, setComponentAnchorTurns] = useState<Record<string, number>>({});
  const [threadsLoading, setThreadsLoading] = useState(false);
  const [threadError, setThreadError] = useState("");

  const state = useMemo(
    () => normalizeTfrChatState(agent.state as Partial<TFRChatState>),
    [agent.state],
  );

  const setState = useCallback(
    (nextState: TFRChatState | ((current: TFRChatState) => TFRChatState)) => {
      const current = normalizeTfrChatState(agent.state as Partial<TFRChatState>);
      const resolved = typeof nextState === "function" ? nextState(current) : nextState;
      agent.setState(normalizeTfrChatState(resolved) as unknown as State);
    },
    [agent],
  );

  const buildRunContextSnapshot = useCallback((): ChatRunContext => {
    const activeRoute = typeof window === "undefined" ? "/" : window.location.pathname;
    return {
      active_route: activeRoute,
      selected_home_rows: homeTableContext.selected_rows,
      home_table: homeTableContext,
      captured_at: new Date().toISOString(),
    };
  }, [homeTableContext]);

  useEffect(() => {
    let active = true;
    void listChatModels()
      .then((catalog) => {
        if (!active) return;
        setChatModelOptions(catalog.models);
        setChatModelSelectionState((current) => {
          const modelExists = catalog.models.some((model) => model.name === current.modelName);
          if (modelExists) return normalizeChatModelSelection(current, catalog.models);
          return normalizeChatModelSelection(
            {
              modelName: catalog.default_model_name || defaultChatModelSelection.modelName,
              reasoningEffort:
                catalog.default_reasoning_effort ?? defaultChatModelSelection.reasoningEffort,
            },
            catalog.models,
          );
        });
      })
      .catch(() => {
        if (active) setChatModelOptions([]);
      });
    return () => {
      active = false;
    };
  }, []);

  const setChatModelSelection = useCallback(
    (selection: ChatModelSelection) => {
      setChatModelSelectionState(normalizeChatModelSelection(selection, chatModelOptions));
    },
    [chatModelOptions],
  );

  const refreshChatThreads = useCallback(async () => {
    setThreadsLoading(true);
    setThreadError("");
    try {
      setChatThreads(await listChatThreads());
    } catch (error) {
      setThreadError(error instanceof Error ? error.message : "Failed to load saved chats.");
    } finally {
      setThreadsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshChatThreads();
  }, [refreshChatThreads]);

  const startNewChatThread = useCallback(() => {
    agent.threadId = crypto.randomUUID();
    agent.setMessages([]);
    agent.setState(normalizeTfrChatState(null) as unknown as State);
    setActiveThreadId(null);
    setComponentAnchorTurns({});
    setOutputComponents([]);
    setThreadError("");
  }, [agent]);

  const loadChatThread = useCallback(
    async (threadId: string) => {
      if (agent.isRunning) return;
      setThreadError("");
      try {
        const thread = await getChatThread(threadId);
        agent.threadId = thread.id;
        agent.setMessages(thread.messages as unknown as Message[]);
        agent.setState(normalizeTfrChatState(thread.state) as unknown as State);
        setActiveThreadId(thread.id);
        setComponentAnchorTurns(thread.component_anchor_turns ?? {});
        setOutputComponents([]);
        if (thread.model_name) {
          setChatModelSelectionState((current) =>
            resolveRestoredChatModelSelection(
              {
                modelName: thread.model_name,
                reasoningEffort: thread.reasoning_effort ?? null,
              },
              chatModelOptions,
              current,
            ),
          );
        }
      } catch (error) {
        setThreadError(error instanceof Error ? error.message : "Failed to restore saved chat.");
      }
    },
    [agent, chatModelOptions],
  );

  const deleteSavedChatThread = useCallback(
    async (threadId: string) => {
      setThreadError("");
      try {
        await deleteChatThread(threadId);
        if (activeThreadId === threadId) {
          startNewChatThread();
        }
        await refreshChatThreads();
      } catch (error) {
        setThreadError(error instanceof Error ? error.message : "Failed to delete saved chat.");
      }
    },
    [activeThreadId, refreshChatThreads, startNewChatThread],
  );

  const runChatMessage = useCallback(
    async (content: string) => {
      const runContext = buildRunContextSnapshot();
      const selectedFormIds = Array.from(
        new Set(runContext.selected_home_rows.map((row) => row.form_key).filter(Boolean)),
      );
      const nextState = normalizeTfrChatState({
        ...(agent.state as Partial<TFRChatState>),
        active_route: runContext.active_route,
        active_review_id: runContext.selected_home_rows[0]?.review_id ?? null,
        selected_form_ids: selectedFormIds,
        components: normalizeTfrChatState(agent.state as Partial<TFRChatState>).components,
        run_context: runContext,
        status: "thinking",
        progress: 0,
        current_step: "Starting assistant run...",
        activity_log: [],
        error_message: null,
      });

      agent.setState(nextState as unknown as State);
      agent.addMessage({
        id: makeId("user"),
        role: "user",
        content,
      } as Message);

      try {
        await agent.runAgent({
          context: [
            {
              description: "TFR run context captured when the user submitted chat input",
              value: JSON.stringify(runContext),
            },
            {
              description: TFR_CHAT_MODEL_CONTEXT_DESCRIPTION,
              value: JSON.stringify({
                model_name: chatModelSelection.modelName,
                reasoning_effort: chatModelSelection.reasoningEffort,
              }),
            },
          ],
        });
        const finalState = normalizeTfrChatState(agent.state as Partial<TFRChatState>);
        if (finalState.status === "thinking" || finalState.status === "using_tools") {
          agent.setState({
            ...finalState,
            status: "complete",
            progress: Math.max(finalState.progress, 100),
            current_step: "Assistant run complete.",
          } as unknown as State);
        }
        setActiveThreadId(agent.threadId);
        void refreshChatThreads();
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown chat error.";
        agent.setState({
          ...normalizeTfrChatState(agent.state as Partial<TFRChatState>),
          status: "error",
          error_message: message,
          current_step: message,
        } as unknown as State);
        throw error;
      }
    },
    [agent, buildRunContextSnapshot, chatModelSelection, refreshChatThreads],
  );

  const stop = useCallback(() => {
    agent.abortRun();
  }, [agent]);

  const openOutputComponent = useCallback((component: OutputComponent) => {
    setOutputComponents((current) => {
      const withoutExisting = current.filter((item) => item.id !== component.id);
      return [...withoutExisting, component];
    });
  }, []);

  const closeOutputComponent = useCallback((componentId: string) => {
    setOutputComponents((current) => current.filter((component) => component.id !== componentId));
  }, []);

  const collapseOutputComponent = useCallback((componentId: string) => {
    setOutputComponents((current) =>
      current.map((component) =>
        component.id === componentId ? { ...component, collapsed: true } : component,
      ),
    );
  }, []);

  const expandOutputComponent = useCallback((componentId: string) => {
    setOutputComponents((current) =>
      current.map((component) =>
        component.id === componentId ? { ...component, collapsed: false } : component,
      ),
    );
  }, []);

  const value: TfrAgentContextValue = {
    agent,
    state,
    setState,
    homeTableContext,
    setHomeTableContext,
    buildRunContextSnapshot,
    runChatMessage,
    stop,
    isRunning: agent.isRunning,
    chatModelOptions,
    chatModelSelection,
    setChatModelSelection,
    chatThreads,
    activeThreadId,
    componentAnchorTurns,
    threadsLoading,
    threadError,
    refreshChatThreads,
    loadChatThread,
    startNewChatThread,
    deleteSavedChatThread,
    outputComponents,
    openOutputComponent,
    closeOutputComponent,
    collapseOutputComponent,
    expandOutputComponent,
  };

  return <TfrAgentContext.Provider value={value}>{children}</TfrAgentContext.Provider>;
}

function normalizeChatModelSelection(
  selection: ChatModelSelection,
  models: ChatModelOption[],
): ChatModelSelection {
  const model =
    models.find((candidate) => candidate.name === selection.modelName) ?? models[0] ?? null;
  if (!model) return selection;
  const efforts = model.reasoning_efforts ?? [];
  const reasoningEffort =
    selection.reasoningEffort && efforts.includes(selection.reasoningEffort)
      ? selection.reasoningEffort
      : model.default_reasoning_effort ?? efforts[0] ?? null;
  return {
    modelName: model.name,
    reasoningEffort,
  };
}

function resolveRestoredChatModelSelection(
  selection: ChatModelSelection,
  models: ChatModelOption[],
  fallback: ChatModelSelection,
): ChatModelSelection {
  if (!models.length) return selection;
  const modelExists = models.some((candidate) => candidate.name === selection.modelName);
  return modelExists ? normalizeChatModelSelection(selection, models) : fallback;
}

export function useTfrAgent() {
  const context = useContext(TfrAgentContext);
  if (!context) {
    throw new Error("useTfrAgent must be used within TfrAgentProvider.");
  }
  return context;
}

export function normalizeTfrChatState(snapshot: Partial<TFRChatState> | null | undefined): TFRChatState {
  return {
    ...initialTfrChatState,
    ...(snapshot ?? {}),
    selected_form_ids: snapshot?.selected_form_ids ?? [],
    documents: snapshot?.documents ?? [],
    artifact_session_id: snapshot?.artifact_session_id ?? "",
    handles: snapshot?.handles ?? [],
    components: snapshot?.components ?? [],
    run_context: snapshot?.run_context ?? null,
    activity_log: snapshot?.activity_log ?? [],
    chat_context_window: snapshot?.chat_context_window ?? null,
    chat_context_remaining_percent: snapshot?.chat_context_remaining_percent ?? null,
    chat_last_usage: snapshot?.chat_last_usage ?? {},
  };
}

function makeId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}
