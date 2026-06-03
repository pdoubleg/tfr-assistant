export const VIRIDIS_CONTROL_COLORS = [
  "#fde725",
  "#b5de2b",
  "#6ece58",
  "#35b779",
  "#1f9e89",
  "#26828e",
  "#31688e",
  "#3e4989",
  "#482878",
  "#440154",
] as const;

export function buildViridisColorway(traceCount: number): string[] {
  const colorCount = Math.max(traceCount, VIRIDIS_CONTROL_COLORS.length);

  if (colorCount === VIRIDIS_CONTROL_COLORS.length) {
    return [...VIRIDIS_CONTROL_COLORS];
  }

  return Array.from({ length: colorCount }, (_, index) =>
    interpolateViridisColor(index / (colorCount - 1)),
  );
}

export function viridisColorAt(index: number, total: number): string {
  if (total <= 1) return VIRIDIS_CONTROL_COLORS[4];
  return interpolateViridisColor(index / (total - 1));
}

export function hexToRgba(hex: string, alpha: number): string {
  const [red, green, blue] = hexToRgb(hex);
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

export function plotlyTheme(isDarkTheme: boolean) {
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

export function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function interpolateViridisColor(position: number): string {
  const clampedPosition = Math.min(Math.max(position, 0), 1);
  const scaledPosition = clampedPosition * (VIRIDIS_CONTROL_COLORS.length - 1);
  const lowerIndex = Math.floor(scaledPosition);
  const upperIndex = Math.ceil(scaledPosition);
  const blendAmount = scaledPosition - lowerIndex;

  return mixHexColors(
    VIRIDIS_CONTROL_COLORS[lowerIndex],
    VIRIDIS_CONTROL_COLORS[upperIndex],
    blendAmount,
  );
}

function mixHexColors(startHex: string, endHex: string, amount: number): string {
  const startRgb = hexToRgb(startHex);
  const endRgb = hexToRgb(endHex);
  const mixedRgb = startRgb.map((channel, index) =>
    Math.round(channel + (endRgb[index] - channel) * amount),
  );

  return rgbToHex(mixedRgb);
}

function hexToRgb(hex: string): [number, number, number] {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function rgbToHex(rgb: number[]): string {
  return `#${rgb.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}
