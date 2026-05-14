"use client";

import { useRef, useState } from "react";
import type { CSSProperties } from "react";

import { BatchQueuePanel } from "@/components/app-shell/batch-queue-panel";
import { OutputPane } from "@/components/output/output-pane";

export function BatchAuditsWorkspace() {
  const workspaceRef = useRef<HTMLDivElement | null>(null);
  const [leftSpacePct, setLeftSpacePct] = useState(42);
  const [queueWidthPct, setQueueWidthPct] = useState(26);
  const [savedFormsRunFilter, setSavedFormsRunFilter] = useState({ name: "", nonce: 0 });

  const startLeftResize = () => {
    const workspace = workspaceRef.current;
    if (!workspace) return;

    const bounds = workspace.getBoundingClientRect();
    const onPointerMove = (event: PointerEvent) => {
      const nextLeftPct = ((event.clientX - bounds.left) / bounds.width) * 100;
      setLeftSpacePct(Math.min(Math.max(nextLeftPct, 0), 80 - queueWidthPct));
    };
    const stopResize = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopResize);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopResize);
  };

  const startQueueResize = () => {
    const workspace = workspaceRef.current;
    if (!workspace) return;

    const bounds = workspace.getBoundingClientRect();
    const onPointerMove = (event: PointerEvent) => {
      const pointerPct = ((event.clientX - bounds.left) / bounds.width) * 100;
      const nextQueuePct = pointerPct - leftSpacePct;
      setQueueWidthPct(Math.min(Math.max(nextQueuePct, 18), 82 - leftSpacePct));
    };
    const stopResize = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopResize);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopResize);
  };

  return (
    <div className="flex h-[calc(100vh-3.5rem)] w-full flex-col gap-4 px-5 py-4 sm:px-6 lg:py-6 xl:pl-10 xl:pr-8 2xl:pl-20 2xl:pr-12">
      <div className="shrink-0">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal">Batch Audits</h1>
          <p className="text-sm text-muted-foreground">
            Batch file reviews, saved run configurations, and structured audit output in one work surface.
          </p>
        </div>
      </div>

      <section
        ref={workspaceRef}
        className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[var(--left-space)_12px_var(--queue-width)_12px_minmax(0,1fr)]"
        style={
          {
            "--left-space": `${leftSpacePct}%`,
            "--queue-width": `${queueWidthPct}%`,
          } as CSSProperties
        }
      >
        <div className="hidden lg:block" />

        <button
          type="button"
          className="hidden h-full cursor-col-resize items-center justify-center rounded-md border border-transparent text-muted-foreground transition-colors hover:border-border hover:bg-secondary/60 lg:flex"
          onPointerDown={startLeftResize}
          aria-label="Move queue and output panes"
          title="Move panes"
        >
          <span className="h-12 w-1 rounded-full bg-border" />
        </button>

        <BatchQueuePanel
          onBatchCompleted={(name) =>
            setSavedFormsRunFilter((current) => ({ name, nonce: current.nonce + 1 }))
          }
        />

        <button
          type="button"
          className="hidden h-full cursor-col-resize items-center justify-center rounded-md border border-transparent text-muted-foreground transition-colors hover:border-border hover:bg-secondary/60 lg:flex"
          onPointerDown={startQueueResize}
          aria-label="Resize queue and output panes"
          title="Resize panes"
        >
          <span className="h-12 w-1 rounded-full bg-border" />
        </button>

        <div className="h-full min-h-0">
          <OutputPane
            runNameFilter={savedFormsRunFilter.name}
            runNameFilterNonce={savedFormsRunFilter.nonce}
          />
        </div>
      </section>
    </div>
  );
}
