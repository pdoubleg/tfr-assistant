"use client";

import { useEffect, useState } from "react";

import { useChatPanelMode } from "@/components/app-shell/chat-panel-mode-context";

const chatOpenInset = 560;
const chatHiddenInset = 24;

export default function AboutPage() {
  const { chatMode } = useChatPanelMode();
  const [isDesktop, setIsDesktop] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const update = () => setIsDesktop(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  const chatVisible = chatMode !== "hidden";

  return (
    <div
      className="flex w-full flex-col gap-6 px-4 py-8 sm:px-6 lg:pr-8"
      style={isDesktop ? { paddingLeft: chatVisible ? chatOpenInset : chatHiddenInset } : undefined}
    >
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase text-muted-foreground">User Workspace</p>
        <h1 className="text-2xl font-semibold">About</h1>
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
          This page will house product context, workflow notes, and ownership details for the
          Targeted File Review Assistant.
        </p>
      </div>
      <div className="max-w-3xl border-t border-dashed pt-5">
        <p className="text-sm font-medium">About content coming soon.</p>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
          The main audit workspace, batch audit tooling, and dashboard remain available from the
          user-facing side of the header.
        </p>
      </div>
    </div>
  );
}
