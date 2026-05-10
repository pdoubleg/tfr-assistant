"use client";

import { useMemo, useState } from "react";
import { MessageSquarePlus, Save, ThumbsDown, ThumbsUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { reviews } from "@/lib/mock-data";
import type { ReviewRecord } from "@/lib/types";
import { cn } from "@/lib/utils";

export function EvaluationWorkbench() {
  const [selectedId, setSelectedId] = useState(reviews[0]?.id ?? "");
  const selected = useMemo(() => reviews.find((review) => review.id === selectedId) ?? reviews[0], [selectedId]);

  return (
    <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
      <Card className="h-fit">
        <CardHeader className="border-b">
          <CardTitle>Review Set</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 pt-5">
          {reviews.map((review) => {
            const userVersion = review.userVersion ?? review.user_version ?? review.original;
            const original = review.original;
            if (!userVersion || !original) return null;
            return (
              <button
                key={review.id}
                type="button"
                onClick={() => setSelectedId(review.id)}
                className={cn(
                  "w-full rounded-lg border p-3 text-left transition-colors hover:bg-secondary/60",
                  selected?.id === review.id && "border-primary bg-primary/5",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium">{userVersion.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{userVersion.description} · {review.id}</p>
                  </div>
                  <Badge variant={original.overall_outcome === userVersion.overall_outcome ? "secondary" : "warning"}>
                    {original.overall_outcome === userVersion.overall_outcome ? "same" : "edited"}
                  </Badge>
                </div>
              </button>
            );
          })}
        </CardContent>
      </Card>

      {selected ? <ComparisonPanel review={selected} /> : null}
    </div>
  );
}

function ComparisonPanel({ review }: { review: ReviewRecord }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <Signal label="Edit Rate" value="34%" tone="amber" />
        <Signal label="LLM Judge" value="pending" tone="cyan" />
        <Signal label="Feedback" value={review.feedback ?? "none"} tone={review.feedback === "down" ? "rose" : "emerald"} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <FormVersion title="Original Agent Output" readOnly review={review} version="original" />
        <FormVersion title="User Version" review={review} version="userVersion" />
      </div>

      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2">
            <MessageSquarePlus className="h-4 w-4 text-primary" />
            Findings
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 pt-5">
          <Textarea defaultValue={review.comments} placeholder="Log review findings, scoring notes, or prompt failure patterns..." />
          <div className="flex flex-wrap justify-between gap-2">
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="gap-1.5"><ThumbsUp className="h-4 w-4" /> Good</Button>
              <Button variant="outline" size="sm" className="gap-1.5"><ThumbsDown className="h-4 w-4" /> Needs Work</Button>
            </div>
            <Button size="sm" className="gap-1.5"><Save className="h-4 w-4" /> Save Evaluation</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function FormVersion({
  title,
  review,
  version,
  readOnly = false,
}: {
  title: string;
  review: ReviewRecord;
  version: "original" | "userVersion";
  readOnly?: boolean;
}) {
  const form = review[version];

  if (!form) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="border-b">
        <div className="flex items-center justify-between gap-2">
          <CardTitle>{title}</CardTitle>
          <Badge variant={readOnly ? "outline" : "success"}>{readOnly ? "read only" : "editable"}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-5">
        <div>
          <p className="text-sm font-medium">{form.title}</p>
          <p className="mt-1 text-sm text-muted-foreground">{form.outcome_justification}</p>
        </div>
        <div className="space-y-3">
          {form.questions.map((question) => (
            <div key={question.id} className="rounded-lg border p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-xs font-semibold text-primary">{question.id}</p>
                  <p className="mt-1 text-sm">{question.text}</p>
                </div>
                <Badge variant={question.answer === "Yes" ? "success" : "danger"}>
                  {question.answer}
                </Badge>
              </div>
              {!readOnly ? (
                <Textarea
                  className="mt-3 min-h-[72px]"
                  defaultValue=""
                  readOnly={readOnly}
                  placeholder="User edit note..."
                />
              ) : null}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function Signal({ label, value, tone }: { label: string; value: string; tone: "amber" | "cyan" | "emerald" | "rose" }) {
  const classes = {
    amber: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    cyan: "border-cyan-500/30 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300",
    emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    rose: "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300",
  }[tone];

  return (
    <div className={cn("rounded-lg border p-4", classes)}>
      <p className="text-xs font-medium uppercase">{label}</p>
      <p className="mt-2 text-xl font-semibold">{value}</p>
    </div>
  );
}
