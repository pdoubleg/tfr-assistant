"use client";

import { Maximize2, MessageSquareText, Minimize2, PanelLeftClose, PanelLeftOpen, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const messages = [
  {
    role: "assistant",
    content: "I can help triage review batches, explain form results, and keep the current audit context synced once AG-UI is connected.",
  },
  {
    role: "user",
    content: "Filter to interior files with user edits and queue the next review.",
  },
  {
    role: "assistant",
    content: "Ready. The evaluation workflow can use that filtered set for side-by-side review.",
  },
];

export function DockableChat({
  open,
  docked,
  onOpenChange,
  onDockedChange,
}: {
  open: boolean;
  docked: boolean;
  onOpenChange: (open: boolean) => void;
  onDockedChange: (docked: boolean) => void;
}) {
  if (!open) {
    return (
      <Button
        className="fixed bottom-4 left-4 z-50 gap-2 shadow-panel"
        onClick={() => onOpenChange(true)}
        aria-label="Open assistant"
      >
        <MessageSquareText className="h-4 w-4" />
        Assistant
      </Button>
    );
  }

  return (
    <aside
      className={cn(
        "z-50 flex flex-col border bg-card text-card-foreground shadow-panel",
        docked
          ? "fixed bottom-0 left-0 top-14 w-full sm:w-[360px]"
          : "fixed bottom-4 left-4 top-auto h-[620px] max-h-[calc(100vh-88px)] w-[min(420px,calc(100vw-32px))] rounded-lg",
      )}
    >
      <div className="flex h-12 items-center justify-between border-b px-3">
        <div className="flex items-center gap-2">
          <MessageSquareText className="h-4 w-4 text-primary" />
          <div>
            <p className="text-sm font-semibold">TFR Assistant</p>
            <p className="text-xs text-muted-foreground">AG-UI transport placeholder</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onDockedChange(!docked)}
            aria-label={docked ? "Undock assistant" : "Dock assistant"}
            title={docked ? "Undock assistant" : "Dock assistant"}
          >
            {docked ? <Maximize2 className="h-4 w-4" /> : <Minimize2 className="h-4 w-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onOpenChange(false)}
            aria-label="Close assistant"
            title="Close assistant"
          >
            {docked ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-auto p-3">
        {messages.map((message, index) => (
          <div key={`${message.role}-${index}`} className={cn("flex", message.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[88%] rounded-lg border px-3 py-2 text-sm leading-relaxed",
                message.role === "user" ? "bg-primary text-primary-foreground" : "bg-secondary/70",
              )}
            >
              {message.content}
            </div>
          </div>
        ))}
      </div>

      <div className="border-t p-3">
        <div className="flex gap-2">
          <Textarea className="min-h-[72px] resize-none" placeholder="Ask about a review, form, or eval run..." />
          <Button size="icon" className="h-[72px] w-11" aria-label="Send message" title="Send message">
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </aside>
  );
}

