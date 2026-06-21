import { ObservabilityWorkbench } from "@/components/observability/observability-workbench";

export default function ObservabilityPage() {
  return (
    <div className="mx-auto w-full max-w-[1700px] space-y-4 p-4 lg:p-6">
      <div>
        <h1 className="text-2xl font-semibold">Observability</h1>
        <p className="text-sm text-muted-foreground">
          Inspect audit generation traces, nested agent spans, token use, errors, and captured
          artifacts.
        </p>
      </div>
      <ObservabilityWorkbench />
    </div>
  );
}
