"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Copy,
  FileText,
  ShieldCheck,
  X,
} from "lucide-react";

import {
  ReviewFeedbackButton,
  ReviewFeedbackSubmittedCount,
} from "@/components/feedback/review-feedback-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  formStatusLabels,
  formStatusVariant,
  getQuestionDriverCount,
  getSubQuestionLabel,
  resultVersionLabels,
  type DashboardReviewRow,
} from "@/lib/dashboard-data";
import type { FormQuestion, FormSubQuestion } from "@/lib/types";
import { cn } from "@/lib/utils";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }, [text]);

  return (
    <button
      type="button"
      onClick={() => void handleCopy()}
      className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
      title="Copy"
      aria-label="Copy"
    >
      {copied ? <ClipboardCheck className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

function TextBlock({ label, text }: { label: string; text: string }) {
  if (!text) return null;
  return (
    <div className="rounded-lg border bg-background p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase text-muted-foreground">{label}</p>
        <CopyButton text={text} />
      </div>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-foreground/85">{text}</p>
    </div>
  );
}

function outcomeLabel(outcome: string): string {
  return outcome === "Does Not Meet" ? "DNM" : outcome;
}

function formatDateOnly(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function canSubmitFeedback(row: DashboardReviewRow): boolean {
  return row.rowKind !== "dataset_case" && !row.reviewId.startsWith("eval-ground-truth:");
}

function SubQuestionViewer({ subQuestion }: { subQuestion: FormSubQuestion }) {
  const applicable = Boolean(subQuestion.answer);
  return (
    <div className={cn("border-l-[3px] bg-background px-4 py-3", applicable ? "border-l-amber-500" : "border-l-emerald-500")}>
      <div className="flex items-start gap-3">
        <span className="mt-0.5 shrink-0 rounded border border-primary/15 bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-primary">
          {subQuestion.id}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="text-sm leading-relaxed">{subQuestion.text}</p>
            <Badge variant={applicable ? "warning" : "outline"}>{getSubQuestionLabel(subQuestion)}</Badge>
          </div>
          {subQuestion.help_text ? <p className="mt-1 text-xs italic text-muted-foreground">{subQuestion.help_text}</p> : null}
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <TextBlock label="Reasoning" text={subQuestion.reasoning} />
            <TextBlock label="Citations" text={subQuestion.citations} />
          </div>
        </div>
      </div>
    </div>
  );
}

function QuestionViewer({ question }: { question: FormQuestion }) {
  const subQuestions = question.sub_questions ?? [];
  const hasSubQuestions = subQuestions.length > 0;
  const [expanded, setExpanded] = useState(question.answer === "No" && hasSubQuestions);
  const driverCount = getQuestionDriverCount(question);

  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border bg-card",
        question.answer === "Yes" ? "border-l-[3px] border-l-emerald-500" : "border-l-[3px] border-l-rose-500",
      )}
    >
      <button
        type="button"
        onClick={() => hasSubQuestions && setExpanded((current) => !current)}
        className={cn("flex w-full items-start gap-3 p-4 text-left", hasSubQuestions && "hover:bg-secondary/40")}
      >
        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center text-muted-foreground">
          {hasSubQuestions ? (
            expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />
          ) : null}
        </span>
        <span className="mt-0.5 shrink-0 rounded border border-primary/15 bg-primary/10 px-2 py-0.5 font-mono text-[11px] font-bold text-primary">
          {question.id}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm leading-relaxed">{question.text}</p>
          {question.help_text ? <p className="mt-1 text-xs italic text-muted-foreground">{question.help_text}</p> : null}
          {driverCount ? (
            <div className="mt-2 flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-300">
              <AlertTriangle className="h-3.5 w-3.5" />
              {driverCount} applicable driver{driverCount === 1 ? "" : "s"}
            </div>
          ) : null}
        </div>
        <Badge variant={question.answer === "Yes" ? "success" : "danger"}>{question.answer}</Badge>
      </button>
      {!hasSubQuestions ? (
        <div className="grid gap-3 border-t bg-secondary/20 p-4 lg:grid-cols-2">
          <TextBlock label="Comments" text={question.comments ?? ""} />
          <TextBlock label="Citations" text={question.citations ?? ""} />
          {question.overwrite_dollars !== undefined || question.underwrite_dollars !== undefined ? (
            <div className="rounded-lg border bg-background p-4 lg:col-span-2">
              <p className="text-[11px] font-semibold uppercase text-muted-foreground">Financial Exceptions</p>
              <p className="mt-2 text-sm">
                OW ${Number(question.overwrite_dollars ?? 0).toFixed(2)} · UW ${Number(question.underwrite_dollars ?? 0).toFixed(2)}
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
      {expanded ? (
        <div className="divide-y border-t bg-secondary/25">
          {subQuestions.map((subQuestion) => (
            <SubQuestionViewer key={subQuestion.id} subQuestion={subQuestion} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function FormViewerSheet({
  row,
  open,
  onOpenChange,
  onFeedbackSubmitted,
}: {
  row: DashboardReviewRow | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onFeedbackSubmitted?: (reviewId: string) => void | Promise<void>;
}) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onOpenChange(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onOpenChange, open]);

  if (!open || !row) return null;

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        className="absolute inset-0 bg-foreground/30 backdrop-blur-[1px]"
        onClick={() => onOpenChange(false)}
        aria-label="Close form viewer"
      />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-4xl flex-col border-l bg-background shadow-2xl">
        <header className="shrink-0 border-b bg-secondary/35 p-5">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-primary">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="truncate text-lg font-semibold">{row.title}</h2>
                <Badge variant="outline" className="font-mono text-[10px]">
                  {row.formKey}
                </Badge>
                <Badge variant="outline">{row.formKind}</Badge>
                <Badge
                  variant={row.outcome === "Meets" ? "success" : "danger"}
                  className="whitespace-nowrap text-[11px]"
                  title={row.outcome}
                >
                  {row.outcome === "Meets" ? <CheckCircle2 className="mr-1 h-3 w-3" /> : <AlertTriangle className="mr-1 h-3 w-3" />}
                  {outcomeLabel(row.outcome)}
                </Badge>
              </div>
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{row.description}</p>
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <Badge variant="secondary">{resultVersionLabels[row.resultVersion]}</Badge>
                {row.claimNumber ? <Badge variant="outline">Claim {row.claimNumber}</Badge> : null}
                {row.runName ? <Badge variant="outline">{row.runName}</Badge> : null}
                <Badge variant={formStatusVariant(row.formStatus)}>
                  {formStatusLabels[row.formStatus]}
                </Badge>
                {row.lastFinalizedAt ? (
                  <Badge variant="outline">
                    {row.finalized ? "Finalized" : "Last finalized"} {formatDateOnly(row.lastFinalizedAt)}
                  </Badge>
                ) : null}
                {row.createdAt ? <Badge variant="outline">Created {formatDateOnly(row.createdAt)}</Badge> : null}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {canSubmitFeedback(row) ? (
                <>
                  <ReviewFeedbackSubmittedCount count={row.feedbackCount} />
                  <ReviewFeedbackButton
                    reviewId={row.reviewId}
                    claimNumber={row.claimNumber}
                    variant="outline"
                    size="sm"
                    onSubmitted={() => onFeedbackSubmitted?.(row.reviewId)}
                  />
                </>
              ) : null}
              <Button type="button" variant="ghost" size="icon" onClick={() => onOpenChange(false)} title="Close" aria-label="Close">
                <X className="h-5 w-5" />
              </Button>
            </div>
          </div>
        </header>

        <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto p-5">
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="rounded-lg border bg-card p-3">
              <p className="text-xs text-muted-foreground">Questions</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{row.questionCount}</p>
            </div>
            <div className="rounded-lg border bg-card p-3">
              <p className="text-xs text-muted-foreground">Yes</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-emerald-700 dark:text-emerald-300">{row.yesCount}</p>
            </div>
            <div className="rounded-lg border bg-card p-3">
              <p className="text-xs text-muted-foreground">No</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-rose-700 dark:text-rose-300">{row.noCount}</p>
            </div>
            <div className="rounded-lg border bg-card p-3">
              <p className="text-xs text-muted-foreground">Drivers</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-amber-700 dark:text-amber-300">{row.driverCount}</p>
            </div>
          </div>
          {row.formKind === "financial" ? (
            <div className="mt-3 grid gap-3 sm:grid-cols-4">
              <div className="rounded-lg border bg-card p-3">
                <p className="text-xs text-muted-foreground">Reviewed</p>
                <p className="mt-1 text-xl font-semibold tabular-nums">${(row.totalAmountReviewedDollars ?? 0).toFixed(2)}</p>
              </div>
              <div className="rounded-lg border bg-card p-3">
                <p className="text-xs text-muted-foreground">OW</p>
                <p className="mt-1 text-xl font-semibold tabular-nums">${row.totalOverwriteDollars.toFixed(2)}</p>
              </div>
              <div className="rounded-lg border bg-card p-3">
                <p className="text-xs text-muted-foreground">UW</p>
                <p className="mt-1 text-xl font-semibold tabular-nums">${row.totalUnderwriteDollars.toFixed(2)}</p>
              </div>
              <div className="rounded-lg border bg-card p-3">
                <p className="text-xs text-muted-foreground">OW / UW %</p>
                <p className="mt-1 text-xl font-semibold tabular-nums">
                  {(row.overwritePercent ?? 0).toFixed(2)} / {(row.underwritePercent ?? 0).toFixed(2)}
                </p>
              </div>
            </div>
          ) : null}

          <div className="mt-5 space-y-3">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-semibold">Questions</h3>
            </div>
            {row.form.questions.map((question) => (
              <QuestionViewer key={question.id} question={question} />
            ))}
          </div>

          <div className="mt-5">
            <TextBlock label="Outcome Justification" text={row.outcomeJustification} />
          </div>
        </div>
      </aside>
    </div>
  );
}
