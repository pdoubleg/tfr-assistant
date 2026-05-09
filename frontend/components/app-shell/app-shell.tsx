"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { DockableChat } from "@/components/chat/dockable-chat";
import { HeaderNav } from "@/components/app-shell/header-nav";
import { cn } from "@/lib/utils";

export function AppShell({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [chatDocked, setChatDocked] = useState(true);
  const [chatOpen, setChatOpen] = useState(true);

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
        chatOpen={chatOpen}
        onToggleChat={() => setChatOpen((value) => !value)}
      />
      <DockableChat
        open={chatOpen}
        docked={chatDocked}
        onOpenChange={setChatOpen}
        onDockedChange={setChatDocked}
      />
      <main
        className={cn(
          "min-h-[calc(100vh-56px)] pt-14 transition-[padding] duration-200",
          chatOpen && chatDocked ? "lg:pl-[360px]" : "",
        )}
      >
        {children}
      </main>
    </div>
  );
}
