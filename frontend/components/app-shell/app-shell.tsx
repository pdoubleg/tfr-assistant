"use client";

import { HttpAgent } from "@ag-ui/client";
import {
  CopilotKitContext,
  CopilotKitCoreReact,
  EMPTY_SET,
} from "@copilotkit/react-core/v2/context";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { DockableChat } from "@/components/chat/dockable-chat";
import { HeaderNav } from "@/components/app-shell/header-nav";
import { ChatPanelModeContext, type ChatPanelMode } from "@/components/app-shell/chat-panel-mode-context";
import { initialTfrChatState, TFR_AGENT_ID, TfrAgentProvider } from "@/hooks/use-tfr-agent";
import { apiBaseUrl } from "@/lib/api";

export function AppShell({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [chatMode, setChatMode] = useState<ChatPanelMode>("small");
  const chatPanelModeValue = useMemo(() => ({ chatMode, setChatMode }), [chatMode]);
  const agents = useMemo(
    () => ({
      [TFR_AGENT_ID]: new HttpAgent({
        agentId: TFR_AGENT_ID,
        url: `${apiBaseUrl}/api/chat/ag-ui`,
        initialState: initialTfrChatState,
      }),
    }),
    [],
  );
  const copilotkit = useMemo(() => {
    const core = new CopilotKitCoreReact({
      agents__unsafe_dev_only: agents,
      headers: {},
      properties: {},
    });
    core.setDefaultThrottleMs(50);
    return core;
  }, [agents]);
  const copilotkitContextValue = useMemo(
    () => ({
      copilotkit,
      executingToolCallIds: EMPTY_SET,
    }),
    [copilotkit],
  );

  useEffect(() => {
    const storedTheme = window.localStorage.getItem("tfr-theme") as "light" | "dark" | null;
    const nextTheme = storedTheme ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    setTheme(nextTheme);
    document.documentElement.classList.toggle("dark", nextTheme === "dark");
  }, []);

  useEffect(() => {
    if (window.innerWidth < 768) {
      setChatMode("hidden");
    }
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "light" ? "dark" : "light";
    setTheme(nextTheme);
    window.localStorage.setItem("tfr-theme", nextTheme);
    document.documentElement.classList.toggle("dark", nextTheme === "dark");
  };

  return (
    <CopilotKitContext.Provider value={copilotkitContextValue}>
      <TfrAgentProvider>
        <ChatPanelModeContext.Provider value={chatPanelModeValue}>
          <div className="min-h-screen bg-background">
            <HeaderNav
              theme={theme}
              onToggleTheme={toggleTheme}
            />
            <DockableChat
              mode={chatMode}
              onModeChange={setChatMode}
            />
            <main className="min-h-[calc(100vh-56px)] pt-14">{children}</main>
          </div>
        </ChatPanelModeContext.Provider>
      </TfrAgentProvider>
    </CopilotKitContext.Provider>
  );
}
