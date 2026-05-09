import { EvaluationWorkbench } from "@/components/evaluation/evaluation-workbench";

export default function EvaluationPage() {
  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 p-4 lg:p-6">
      <div>
        <h1 className="text-2xl font-semibold">Evaluation</h1>
        <p className="text-sm text-muted-foreground">
          Compare original agent output against user-edited forms, log findings, and build quality signals.
        </p>
      </div>
      <EvaluationWorkbench />
    </div>
  );
}

