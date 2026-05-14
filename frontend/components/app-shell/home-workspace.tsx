"use client";

import { useCallback, useEffect, useMemo, useState, type PointerEvent } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

import { useChatPanelMode } from "@/components/app-shell/chat-panel-mode-context";
import { AuditDataTable } from "@/components/data-table/audit-data-table";
import { listReviews, updateReviewUserVersion } from "@/lib/api";
import { deriveReviewRows } from "@/lib/dashboard-data";
import type { AuditFormResult, ReviewRecord } from "@/lib/types";

const layoutSettingsKey = "tfr-home-table-layout";
const chatOpenDefaultInset = 560;
const chatHiddenDefaultInset = 24;
const minTableWidth = 560;
const minInset = 24;

interface HomeTableLayoutSettings {
  chatOpenInset?: number;
  chatHiddenInset?: number;
}

function loadHomeTableLayoutSettings(): HomeTableLayoutSettings {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(layoutSettingsKey) ?? "{}") as HomeTableLayoutSettings;
  } catch {
    return {};
  }
}

function clampInset(value: number) {
  if (typeof window === "undefined") return value;
  const maxInset = Math.max(minInset, window.innerWidth - minTableWidth);
  return Math.min(Math.max(value, minInset), maxInset);
}

export function HomeWorkspace() {
  const { chatMode } = useChatPanelMode();
  const [reviews, setReviews] = useState<ReviewRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isDesktop, setIsDesktop] = useState(false);
  const [layoutSettingsLoaded, setLayoutSettingsLoaded] = useState(false);
  const [layoutSettings, setLayoutSettings] = useState<HomeTableLayoutSettings>({});
  const chatVisible = chatMode !== "hidden";
  const activeLayoutKey = chatVisible ? "chatOpenInset" : "chatHiddenInset";
  const defaultInset = chatVisible ? chatOpenDefaultInset : chatHiddenDefaultInset;
  const tableInset = clampInset(layoutSettings[activeLayoutKey] ?? defaultInset);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const nextReviews = await listReviews();
      setReviews(nextReviews);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load audit data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const update = () => setIsDesktop(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    setLayoutSettings(loadHomeTableLayoutSettings());
    setLayoutSettingsLoaded(true);
  }, []);

  useEffect(() => {
    if (!layoutSettingsLoaded) return;
    window.localStorage.setItem(layoutSettingsKey, JSON.stringify(layoutSettings));
  }, [layoutSettings, layoutSettingsLoaded]);

  const rows = useMemo(() => deriveReviewRows(reviews, "current"), [reviews]);

  const saveForm = async (reviewId: string, form: AuditFormResult) => {
    const updatedReview = await updateReviewUserVersion(reviewId, form);
    setReviews((current) =>
      current.map((review) => (review.id === reviewId ? updatedReview : review)),
    );
  };

  const updateTableInset = (value: number) => {
    setLayoutSettings((current) => ({
      ...current,
      [activeLayoutKey]: clampInset(value),
    }));
  };

  const resetTableInset = () => {
    setLayoutSettings((current) => {
      const next = { ...current };
      delete next[activeLayoutKey];
      return next;
    });
  };

  const startTableResize = (event: PointerEvent<HTMLButtonElement>) => {
    if (!isDesktop) return;
    event.preventDefault();

    const onPointerMove = (moveEvent: globalThis.PointerEvent) => {
      updateTableInset(moveEvent.clientX);
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
    <div
      className="relative flex h-[calc(100vh-3.5rem)] w-full flex-col gap-4 px-5 py-4 sm:px-6 lg:py-6 lg:pl-0 lg:pr-6 xl:pr-8 2xl:pr-12"
      style={isDesktop ? { paddingLeft: tableInset } : undefined}
    >
      {isDesktop ? (
        <button
          type="button"
          className="absolute bottom-6 top-6 z-20 hidden w-5 -translate-x-1/2 cursor-col-resize items-center justify-center border border-transparent text-muted-foreground lg:flex"
          style={{ left: tableInset }}
          onPointerDown={startTableResize}
          onDoubleClick={resetTableInset}
          aria-label="Resize audit table width"
        >
          <span className="h-20 w-1 rounded-full bg-border shadow-sm" />
        </button>
      ) : null}
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal">Home</h1>
          <p className="text-sm text-muted-foreground">
            Ask the assistant about audit data, then open or edit the stored form behind any row.
          </p>
        </div>
        {loading ? (
          <div className="inline-flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
            Loading audit data
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="flex shrink-0 items-start gap-2 rounded-lg border border-destructive/35 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </div>
      ) : null}

      <div className="min-h-0 flex-1">
        <AuditDataTable
          rows={rows}
          totalCount={rows.length}
          loading={loading}
          onRefresh={() => void refresh()}
          onSaveForm={saveForm}
        />
      </div>
    </div>
  );
}
