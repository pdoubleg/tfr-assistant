declare module "dagre" {
  const dagre: {
    graphlib: {
      Graph: new () => {
        setDefaultEdgeLabel: (callback: () => Record<string, unknown>) => void;
        setGraph: (options: Record<string, unknown>) => void;
        setNode: (id: string, options: Record<string, unknown>) => void;
        setEdge: (source: string, target: string) => void;
        node: (id: string) => { x: number; y: number };
      };
    };
    layout: (graph: unknown) => void;
  };
  export default dagre;
}
