"use client";

import { BarChart3 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

const VIRIDIS_COLORWAY = [
  "#440154",
  "#482878",
  "#3e4989",
  "#31688e",
  "#26828e",
  "#1f9e89",
  "#35b779",
  "#6ece58",
  "#b5de2b",
  "#fde725",
];

export interface PlotlyChartProps {
  data: unknown[];
  layout?: Record<string, unknown>;
  config?: Record<string, unknown>;
  caption?: string;
  sourceHandle?: string;
}

export function PlotlyChart({
  data,
  layout,
  config,
  caption,
  sourceHandle,
}: PlotlyChartProps) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDarkTheme, setIsDarkTheme] = useState(false);

  useEffect(() => {
    const syncTheme = () => setIsDarkTheme(document.documentElement.classList.contains("dark"));
    syncTheme();
    const observer = new MutationObserver(syncTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  const resolvedLayout = useMemo(
    () => {
      const theme = plotlyTheme(isDarkTheme);
      return {
        ...cloneJson(layout ?? {}),
        autosize: true,
        colorway: VIRIDIS_COLORWAY,
        margin: { l: 54, r: 24, t: caption ? 46 : 30, b: 50, ...(layout?.margin as object | undefined) },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        font: {
          family: "Inter, ui-sans-serif, system-ui, sans-serif",
          size: 12,
          color: theme.text,
          ...((layout?.font as object | undefined) ?? {}),
        },
        xaxis: {
          gridcolor: theme.grid,
          zerolinecolor: theme.zeroLine,
          linecolor: theme.axis,
          tickcolor: theme.axis,
          ...((layout?.xaxis as object | undefined) ?? {}),
        },
        yaxis: {
          gridcolor: theme.grid,
          zerolinecolor: theme.zeroLine,
          linecolor: theme.axis,
          tickcolor: theme.axis,
          ...((layout?.yaxis as object | undefined) ?? {}),
        },
        legend: {
          bgcolor: "rgba(0,0,0,0)",
          borderwidth: 0,
          ...((layout?.legend as object | undefined) ?? {}),
        },
        hoverlabel: {
          bgcolor: theme.hover,
          bordercolor: theme.axis,
          font: { color: theme.text },
          ...((layout?.hoverlabel as object | undefined) ?? {}),
        },
      };
    },
    [caption, isDarkTheme, layout],
  );

  const resolvedConfig = useMemo(
    () => ({
      displaylogo: false,
      responsive: true,
      modeBarButtonsToRemove: ["lasso2d", "select2d"],
      ...(config ?? {}),
    }),
    [config],
  );

  const resolvedData = useMemo(
    () => (Array.isArray(data) ? cloneJson(data) : []),
    [data],
  );

  useEffect(() => {
    let cancelled = false;
    const element = chartRef.current;
    if (!element) return;
    const container: HTMLElement = element;

    async function renderChart() {
      try {
        const Plotly = (await import("plotly.js-dist-min")).default;
        if (cancelled) return;
        await Plotly.react(container, cloneJson(resolvedData), cloneJson(resolvedLayout), cloneJson(resolvedConfig));
        if (!cancelled) setError(null);
      } catch {
        if (!cancelled) setError("Chart failed to render.");
      }
    }

    void renderChart();

    return () => {
      cancelled = true;
      void import("plotly.js-dist-min")
        .then((module) => module.default.purge(container))
        .catch(() => undefined);
    };
  }, [resolvedConfig, resolvedData, resolvedLayout]);

  useEffect(() => {
    const element = chartRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver(() => {
      void import("plotly.js-dist-min")
        .then((module) => module.default.Plots?.resize(element))
        .catch(() => undefined);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <figure className="overflow-hidden rounded-md border bg-background text-sm">
      {(caption || sourceHandle) ? (
        <div className="flex items-center gap-2 border-b bg-secondary/45 px-3 py-2">
          <BarChart3 className="h-4 w-4 shrink-0 text-primary" />
          <div className="min-w-0">
            {caption ? <figcaption className="truncate font-semibold">{caption}</figcaption> : null}
            {sourceHandle ? (
              <p className="truncate font-mono text-xs text-muted-foreground">{sourceHandle}</p>
            ) : null}
          </div>
        </div>
      ) : null}
      <div className="relative min-h-[320px] bg-card">
        <div ref={chartRef} className="h-[380px] min-h-[320px] w-full" />
        {error ? (
          <div className="absolute inset-0 flex items-center justify-center bg-card/90 px-4 text-center text-xs text-destructive">
            {error}
          </div>
        ) : null}
      </div>
    </figure>
  );
}

function plotlyTheme(isDarkTheme: boolean) {
  if (typeof document === "undefined") {
    return {
      paper: isDarkTheme ? "#111827" : "#ffffff",
      plot: isDarkTheme ? "#1f2937" : "#ffffff",
      text: isDarkTheme ? "#f9fafb" : "#111827",
      grid: isDarkTheme ? "rgba(255,255,255,0.12)" : "rgba(15,23,42,0.12)",
      zeroLine: isDarkTheme ? "rgba(255,255,255,0.24)" : "rgba(15,23,42,0.22)",
      axis: isDarkTheme ? "#374151" : "#d1d5db",
      hover: isDarkTheme ? "#1f2937" : "#ffffff",
    };
  }
  const rootStyles = getComputedStyle(document.documentElement);
  const color = (name: string, fallback: string) => {
    const raw = rootStyles.getPropertyValue(name).trim();
    return raw ? `hsl(${raw})` : fallback;
  };

  return {
    paper: color("--background", isDarkTheme ? "#111827" : "#ffffff"),
    plot: color("--card", isDarkTheme ? "#1f2937" : "#ffffff"),
    text: color("--foreground", isDarkTheme ? "#f9fafb" : "#111827"),
    grid: isDarkTheme ? "rgba(255,255,255,0.12)" : "rgba(15,23,42,0.12)",
    zeroLine: isDarkTheme ? "rgba(255,255,255,0.24)" : "rgba(15,23,42,0.22)",
    axis: color("--border", isDarkTheme ? "#374151" : "#d1d5db"),
    hover: color("--card", isDarkTheme ? "#1f2937" : "#ffffff"),
  };
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}
