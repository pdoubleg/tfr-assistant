import { EvaluationWorkbench } from "@/components/evaluation/evaluation-workbench";

export default function EvaluationPage() {
  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-4 p-4 lg:p-6">
      <div>
        <h1 className="text-2xl font-semibold">Evaluation</h1>
        <p className="text-sm text-muted-foreground">
          Run ground-truth eval batches and track agreement against R1 and R2 audit results.
        </p>
      </div>
      <EvaluationWorkbench />
    </div>
  );
}
