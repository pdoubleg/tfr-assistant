"use client";

import { createContext, useContext } from "react";

export type ChatPanelMode = "hidden" | "small" | "large";

export const ChatPanelModeContext = createContext<{
  chatMode: ChatPanelMode;
  setChatMode: (mode: ChatPanelMode) => void;
} | null>(null);

export function useChatPanelMode() {
  const context = useContext(ChatPanelModeContext);
  if (!context) {
    throw new Error("useChatPanelMode must be used within AppShell.");
  }
  return context;
}
