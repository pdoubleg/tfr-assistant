"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

import type { OutputComponent, TFRChatState } from "@/lib/types";

export const initialTfrChatState: TFRChatState = {
  active_route: "/",
  active_review_id: null,
  selected_form_ids: [],
  documents: [],
  status: "idle",
  progress: 0,
  current_step: "",
  activity_log: [],
  error_message: null,
};

interface TfrAgentContextValue {
  state: TFRChatState;
  setState: (state: TFRChatState | ((current: TFRChatState) => TFRChatState)) => void;
  outputComponents: OutputComponent[];
  openOutputComponent: (component: OutputComponent) => void;
  closeOutputComponent: (componentId: string) => void;
  collapseOutputComponent: (componentId: string) => void;
  expandOutputComponent: (componentId: string) => void;
}

const TfrAgentContext = createContext<TfrAgentContextValue | null>(null);

export function TfrAgentProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<TFRChatState>(initialTfrChatState);
  const [outputComponents, setOutputComponents] = useState<OutputComponent[]>([]);

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

  const value = useMemo<TfrAgentContextValue>(
    () => ({
      state,
      setState,
      outputComponents,
      openOutputComponent,
      closeOutputComponent,
      collapseOutputComponent,
      expandOutputComponent,
    }),
    [
      state,
      outputComponents,
      openOutputComponent,
      closeOutputComponent,
      collapseOutputComponent,
      expandOutputComponent,
    ],
  );

  return <TfrAgentContext.Provider value={value}>{children}</TfrAgentContext.Provider>;
}

export function useTfrAgent() {
  const context = useContext(TfrAgentContext);
  if (!context) {
    throw new Error("useTfrAgent must be used within TfrAgentProvider.");
  }
  return context;
}
