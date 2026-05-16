declare module "plotly.js-dist-min" {
  interface PlotlyRenderer {
    react(
      element: HTMLElement,
      data: unknown[],
      layout?: Record<string, unknown>,
      config?: Record<string, unknown>,
    ): Promise<unknown>;
    purge(element: HTMLElement): void;
    Plots?: {
      resize(element: HTMLElement): void;
    };
  }

  const Plotly: PlotlyRenderer;
  export default Plotly;
}
