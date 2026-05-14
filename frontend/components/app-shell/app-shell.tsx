"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { DockableChat } from "@/components/chat/dockable-chat";
import { HeaderNav } from "@/components/app-shell/header-nav";
import { ChatPanelModeContext, type ChatPanelMode } from "@/components/app-shell/chat-panel-mode-context";
import { TfrAgentProvider } from "@/hooks/use-tfr-agent";

export function AppShell({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [chatMode, setChatMode] = useState<ChatPanelMode>("small");
  const chatPanelModeValue = useMemo(() => ({ chatMode, setChatMode }), [chatMode]);

  useEffect(() => {
    const storedTheme = window.localStorage.getItem("tfr-theme") as "light" | "dark" | null;
    const nextTheme = storedTheme ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    setTheme(nextTheme);
    document.documentElement.classList.toggle("dark", nextTheme === "dark");
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "light" ? "dark" : "light";
    setTheme(nextTheme);
    window.localStorage.setItem("tfr-theme", nextTheme);
    document.documentElement.classList.toggle("dark", nextTheme === "dark");
  };

  return (
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
  );
}
