"use client";

import { useAgent } from "@copilotkit/react-core/v2/headless";
import type { UseAgentUpdate } from "@copilotkit/react-core/v2/headless";
import type { AbstractAgent, Message, State } from "@ag-ui/client";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

import type {
  ChatRunContext,
  HomeTableContext,
  OutputComponent,
  TFRChatState,
} from "@/lib/types";

export const TFR_AGENT_ID = "tfr_agent";

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
        components: [],
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
    [agent, buildRunContextSnapshot],
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
    outputComponents,
    openOutputComponent,
    closeOutputComponent,
    collapseOutputComponent,
    expandOutputComponent,
  };

  return <TfrAgentContext.Provider value={value}>{children}</TfrAgentContext.Provider>;
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
  };
}

function makeId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}
