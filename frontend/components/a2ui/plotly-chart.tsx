"use client";

import { BarChart3, ChevronDown, ChevronRight, Maximize2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { buildViridisColorway, cloneJson, plotlyTheme } from "@/lib/plotly-theme";

export interface PlotlyChartProps {
  data: unknown[];
  layout?: Record<string, unknown>;
  config?: Record<string, unknown>;
  caption?: string;
  sourceHandle?: string;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  showHeader?: boolean;
  surfaceClassName?: string;
}

export function PlotlyChart({
  data,
  layout,
  config,
  caption,
  sourceHandle,
  collapsible = true,
  defaultCollapsed = false,
  showHeader = true,
  surfaceClassName = "h-[380px] min-h-[320px]",
}: PlotlyChartProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const [poppedOut, setPoppedOut] = useState(false);
  const [isDarkTheme, setIsDarkTheme] = useState(false);

  useEffect(() => {
    const syncTheme = () => setIsDarkTheme(document.documentElement.classList.contains("dark"));
    syncTheme();
    const observer = new MutationObserver(syncTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  const resolvedData = useMemo(
    () => (Array.isArray(data) ? cloneJson(data) : []),
    [data],
  );

  const resolvedLayout = useMemo(
    () => {
      const theme = plotlyTheme(isDarkTheme);
      return {
        ...cloneJson(layout ?? {}),
        autosize: true,
        colorway: buildViridisColorway(resolvedData.length),
        margin: {
          l: 54,
          r: 24,
          t: caption ? 46 : 30,
          b: 50,
          ...(layout?.margin as object | undefined),
        },
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
    [caption, isDarkTheme, layout, resolvedData.length],
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

  return (
    <figure className="overflow-hidden rounded-md border bg-background text-sm">
      {showHeader ? (
        <div className="flex items-center gap-2 border-b bg-secondary/45 px-3 py-2">
          <BarChart3 className="h-4 w-4 shrink-0 text-primary" />
          <div className="min-w-0 flex-1">
            {caption ? <figcaption className="truncate font-semibold">{caption}</figcaption> : null}
            {sourceHandle ? (
              <p className="truncate font-mono text-xs text-muted-foreground">{sourceHandle}</p>
            ) : null}
            {!caption && !sourceHandle ? (
              <figcaption className="truncate font-semibold">Plotly chart</figcaption>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setPoppedOut(true)}
              aria-label="Pop out chart"
              title="Pop out chart"
            >
              <Maximize2 className="h-4 w-4" />
            </Button>
            {collapsible ? (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setCollapsed((current) => !current)}
                aria-label={collapsed ? "Expand chart" : "Collapse chart"}
                title={collapsed ? "Expand chart" : "Collapse chart"}
              >
                {collapsed ? (
                  <ChevronRight className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      {!collapsed ? (
        <PlotlySurface
          data={resolvedData}
          layout={resolvedLayout}
          config={resolvedConfig}
          className={surfaceClassName}
        />
      ) : null}

      {poppedOut ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/85 p-4 backdrop-blur-sm">
          <div className="flex h-[min(900px,calc(100vh-32px))] w-[min(1200px,calc(100vw-32px))] flex-col overflow-hidden rounded-md border bg-background shadow-xl">
            <div className="flex items-center gap-2 border-b bg-secondary/45 px-3 py-2">
              <BarChart3 className="h-4 w-4 shrink-0 text-primary" />
              <div className="min-w-0 flex-1">
                <div className="truncate font-semibold">{caption || "Plotly chart"}</div>
                {sourceHandle ? (
                  <p className="truncate font-mono text-xs text-muted-foreground">
                    {sourceHandle}
                  </p>
                ) : null}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setPoppedOut(false)}
                aria-label="Close popped out chart"
                title="Close"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <PlotlySurface
              data={resolvedData}
              layout={resolvedLayout}
              config={resolvedConfig}
              className="min-h-0 flex-1"
            />
          </div>
        </div>
      ) : null}
    </figure>
  );
}

function PlotlySurface({
  data,
  layout,
  config,
  className,
}: {
  data: unknown[];
  layout: Record<string, unknown>;
  config: Record<string, unknown>;
  className: string;
}) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const element = chartRef.current;
    if (!element) return;
    const container: HTMLElement = element;

    async function renderChart() {
      try {
        const Plotly = (await import("plotly.js-dist-min")).default;
        if (cancelled) return;
        await Plotly.react(container, cloneJson(data), cloneJson(layout), cloneJson(config));
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
  }, [config, data, layout]);

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
    <div className="relative min-h-[320px] bg-card">
      <div ref={chartRef} className={`w-full ${className}`} />
      {error ? (
        <div className="absolute inset-0 flex items-center justify-center bg-card/90 px-4 text-center text-xs text-destructive">
          {error}
        </div>
      ) : null}
    </div>
  );
}
