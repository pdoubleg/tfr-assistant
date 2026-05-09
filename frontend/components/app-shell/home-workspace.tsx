"use client";

import { useState } from "react";
import { ArrowLeftRight, ChevronsLeft, ChevronsRight, FileText, PlayCircle, Rows3 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { savedForms } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

export function HomeWorkspace() {
  const [expanded, setExpanded] = useState<"balanced" | "chat" | "output">("balanced");
  const latest = savedForms[0];

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 p-4 lg:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal">Review Workspace</h1>
          <p className="text-sm text-muted-foreground">
            Batch file reviews, live assistant context, and structured audit output in one work surface.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setExpanded("chat")}>
            <ChevronsRight className="mr-1 h-4 w-4" />
            Focus Chat
          </Button>
          <Button variant="outline" size="sm" onClick={() => setExpanded("balanced")}>
            <ArrowLeftRight className="mr-1 h-4 w-4" />
            Split
          </Button>
          <Button variant="outline" size="sm" onClick={() => setExpanded("output")}>
            <ChevronsLeft className="mr-1 h-4 w-4" />
            Focus Output
          </Button>
        </div>
      </div>

      <section className="grid gap-4 lg:grid-cols-12">
        <Card
          className={cn(
            "min-h-[620px]",
            expanded === "chat" && "lg:col-span-7",
            expanded === "output" && "lg:col-span-3",
            expanded === "balanced" && "lg:col-span-5",
          )}
        >
          <CardHeader className="border-b">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="flex items-center gap-2">
                <Rows3 className="h-4 w-4 text-primary" />
                Queue Context
              </CardTitle>
              <Badge variant="secondary">3 active</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4 pt-5">
            {savedForms.map((form) => (
              <button
                key={form.id}
                className="w-full rounded-lg border bg-background p-4 text-left transition-colors hover:bg-secondary/60"
                type="button"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium">{form.title}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {form.peril.peril} · {form.questions.length} questions · {form.form_version}
                    </p>
                  </div>
                  <Badge variant={form.overall_outcome === "Meets" ? "success" : "danger"}>
                    {form.overall_outcome}
                  </Badge>
                </div>
              </button>
            ))}
            <Button className="w-full gap-2">
              <PlayCircle className="h-4 w-4" />
              Start New File Review Batch
            </Button>
          </CardContent>
        </Card>

        <Card
          className={cn(
            "min-h-[620px]",
            expanded === "chat" && "lg:col-span-5",
            expanded === "output" && "lg:col-span-9",
            expanded === "balanced" && "lg:col-span-7",
          )}
        >
          <CardHeader className="border-b">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-primary" />
                Output
              </CardTitle>
              <Badge variant="outline">Original + User Version</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-5 pt-5">
            <div className="grid gap-3 sm:grid-cols-3">
              <Metric label="Outcome" value={latest.overall_outcome} tone="rose" />
              <Metric label="Questions" value={String(latest.questions.length)} tone="cyan" />
              <Metric label="Peril" value={latest.peril.peril} tone="amber" />
            </div>

            <div className="rounded-lg border">
              <div className="border-b bg-secondary/50 px-4 py-3">
                <p className="font-medium">{latest.title}</p>
                <p className="text-sm text-muted-foreground">{latest.outcome_justification}</p>
              </div>
              <div className="divide-y">
                {latest.questions.map((question) => (
                  <div key={question.id} className="grid gap-3 p-4 md:grid-cols-[80px_1fr_auto]">
                    <span className="font-mono text-sm font-semibold text-primary">{question.id}</span>
                    <div>
                      <p className="text-sm font-medium">{question.text}</p>
                      {question.missing_info ? (
                        <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">{question.missing_info}</p>
                      ) : null}
                    </div>
                    <Badge
                      variant={
                        question.answer === "Yes"
                          ? "success"
                          : question.answer === "No"
                            ? "danger"
                            : "warning"
                      }
                    >
                      {question.answer}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone: "rose" | "cyan" | "amber" }) {
  const toneClass = {
    rose: "border-rose-500/25 bg-rose-500/10 text-rose-700 dark:text-rose-300",
    cyan: "border-cyan-500/25 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300",
    amber: "border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  }[tone];

  return (
    <div className={cn("rounded-lg border p-4", toneClass)}>
      <p className="text-xs font-medium uppercase">{label}</p>
      <p className="mt-2 text-xl font-semibold">{value}</p>
    </div>
  );
}

