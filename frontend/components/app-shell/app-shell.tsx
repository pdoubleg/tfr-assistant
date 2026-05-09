"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { DockableChat } from "@/components/chat/dockable-chat";
import { HeaderNav } from "@/components/app-shell/header-nav";

export type ChatPanelMode = "hidden" | "small" | "large";

export function AppShell({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [chatMode, setChatMode] = useState<ChatPanelMode>("hidden");

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
  );
}
