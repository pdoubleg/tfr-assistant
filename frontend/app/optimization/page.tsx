import { FlaskConical, GitCompareArrows, Play, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const steps = [
  { title: "Collect user-edited forms", status: "ready", icon: GitCompareArrows },
  { title: "Generate prompt candidates with GEPA", status: "planned", icon: Sparkles },
  { title: "Run regression eval batch", status: "planned", icon: FlaskConical },
];

export default function OptimizationPage() {
  return (
    <div className="mx-auto w-full max-w-6xl space-y-4 p-4 lg:p-6">
      <div>
        <h1 className="text-2xl font-semibold">Optimization</h1>
        <p className="text-sm text-muted-foreground">
          Placeholder workflow for GEPA-based prompt optimization using user-edited audit forms.
        </p>
      </div>

      <Card>
        <CardHeader className="border-b">
          <div className="flex items-center justify-between gap-3">
            <CardTitle>Prompt Optimization Pipeline</CardTitle>
            <Button className="gap-1.5">
              <Play className="h-4 w-4" />
              Queue Experiment
            </Button>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 pt-5 md:grid-cols-3">
          {steps.map((step) => {
            const Icon = step.icon;
            return (
              <div key={step.title} className="rounded-lg border p-4">
                <div className="flex items-center justify-between gap-3">
                  <Icon className="h-5 w-5 text-primary" />
                  <Badge variant={step.status === "ready" ? "success" : "outline"}>{step.status}</Badge>
                </div>
                <p className="mt-5 font-medium">{step.title}</p>
                <p className="mt-2 text-sm text-muted-foreground">
                  {step.status === "ready"
                    ? "Evaluation data is already modeled as original versus user version."
                    : "Detailed scoring and orchestration will be added after the review data layer settles."}
                </p>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}

