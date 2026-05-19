"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { TextareaHTMLAttributes } from "react";
import {
  AlertTriangle,
  Ban,
  CheckCheck,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronsDown,
  ChevronsUp,
  ClipboardCheck,
  ClipboardList,
  Copy,
  Loader2,
  Pencil,
  Save,
  X,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Toast } from "@/components/ui/toast";
import type { AuditFormResult, FormQuestion, FormSubQuestion, OverallOutcome, QuestionAnswer } from "@/lib/types";
import { cn } from "@/lib/utils";

type DraftQuestionAnswer = QuestionAnswer | "";
type DraftOverallOutcome = OverallOutcome | "";

interface AuditFormMetadata {
  claimNumber?: string;
  finalizedAt?: string;
  updatedAt?: string;
  source?: string;
}

function cloneForm(form: AuditFormResult): AuditFormResult {
  return JSON.parse(JSON.stringify(form)) as AuditFormResult;
}

function formatMetadataDate(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function sameTimestamp(first?: string, second?: string): boolean {
  if (!first || !second) return false;
  return Math.abs(new Date(first).getTime() - new Date(second).getTime()) <= 5000;
}

function buildMetadataItems(reviewId: string, metadata?: AuditFormMetadata) {
  const finalizedAt = formatMetadataDate(metadata?.finalizedAt);
  const updatedAt = formatMetadataDate(metadata?.updatedAt);
  const items = [
    {
      label: metadata?.claimNumber ? "Claim" : "Review",
      value: metadata?.claimNumber || reviewId.slice(0, 8),
    },
    finalizedAt ? { label: "Finalized", value: finalizedAt } : null,
    updatedAt && !sameTimestamp(metadata?.finalizedAt, metadata?.updatedAt)
      ? { label: "Updated", value: updatedAt }
      : null,
  ];

  return items.filter((item): item is { label: string; value: string } => Boolean(item?.value));
}

function normalizeFormForSubmit(form: AuditFormResult): AuditFormResult {
  return {
    ...form,
    questions: form.questions.map((question) => ({
      ...question,
      comments: question.comments?.trim() ? question.comments : null,
      citations: question.citations?.trim() ? question.citations : null,
      sub_questions: question.sub_questions?.length ? question.sub_questions : null,
    })),
  };
}

function getQuestionAnswer(question: FormQuestion): DraftQuestionAnswer {
  return (question.answer ?? "") as DraftQuestionAnswer;
}

function getOverallOutcome(form: AuditFormResult): DraftOverallOutcome {
  return (form.overall_outcome ?? "") as DraftOverallOutcome;
}

function AutoResizeTextarea({
  value,
  onChange,
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${element.scrollHeight}px`;
  }, [value]);

  return (
    <textarea
      ref={ref}
      value={value}
      onChange={onChange}
      className={cn(
        "min-h-11 w-full resize-none overflow-hidden rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed outline-none transition-colors placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      {...props}
    />
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="h-8 w-8 shrink-0 text-muted-foreground"
      onClick={copy}
      title="Copy"
      aria-label="Copy"
    >
      {copied ? <ClipboardCheck className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
    </Button>
  );
}

function AnswerButtons({
  value,
  onChange,
}: {
  value: DraftQuestionAnswer;
  onChange: (answer: QuestionAnswer) => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <button
        type="button"
        onClick={() => onChange("Yes")}
        className={cn(
          "inline-flex h-8 items-center gap-1 rounded-md border px-3 text-xs font-semibold transition-all active:scale-[0.98]",
          value === "Yes"
            ? "border-emerald-500/40 bg-emerald-600 text-white shadow-sm"
            : "border-emerald-500/35 text-emerald-700 hover:bg-emerald-500/12 dark:text-emerald-300",
        )}
      >
        <CheckCircle2 className="h-3.5 w-3.5" />
        Yes
      </button>
      <button
        type="button"
        onClick={() => onChange("No")}
        className={cn(
          "inline-flex h-8 items-center gap-1 rounded-md border px-3 text-xs font-semibold transition-all active:scale-[0.98]",
          value === "No"
            ? "border-rose-500/40 bg-rose-600 text-white shadow-sm"
            : "border-rose-500/35 text-rose-700 hover:bg-rose-500/12 dark:text-rose-300",
        )}
      >
        <XCircle className="h-3.5 w-3.5" />
        No
      </button>
    </div>
  );
}

function OutcomeButtons({
  value,
  onChange,
}: {
  value: DraftOverallOutcome;
  onChange: (outcome: OverallOutcome) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <button
        type="button"
        onClick={() => onChange("Meets")}
        className={cn(
          "inline-flex h-8 items-center gap-1 rounded-md border px-3 text-xs font-semibold transition-all active:scale-[0.98]",
          value === "Meets"
            ? "border-emerald-500/40 bg-emerald-600 text-white shadow-sm"
            : "border-emerald-500/35 text-emerald-700 hover:bg-emerald-500/12 dark:text-emerald-300",
        )}
      >
        <CheckCircle2 className="h-3.5 w-3.5" />
        Meets
      </button>
      <button
        type="button"
        onClick={() => onChange("Does Not Meet")}
        className={cn(
          "inline-flex h-8 items-center gap-1 rounded-md border px-3 text-xs font-semibold transition-all active:scale-[0.98]",
          value === "Does Not Meet"
            ? "border-rose-500/40 bg-rose-600 text-white shadow-sm"
            : "border-rose-500/35 text-rose-700 hover:bg-rose-500/12 dark:text-rose-300",
        )}
      >
        <XCircle className="h-3.5 w-3.5" />
        Does Not Meet
      </button>
    </div>
  );
}

function SubQuestionRow({
  subQuestion,
  expanded,
  disabled = false,
  onToggleExpanded,
  onChange,
}: {
  subQuestion: FormSubQuestion;
  expanded: boolean;
  disabled?: boolean;
  onToggleExpanded: () => void;
  onChange: (subQuestion: FormSubQuestion) => void;
}) {
  const selected = Boolean(subQuestion.answer);

  return (
    <div
      className={cn(
        "border-l-[3px] bg-background transition-colors",
        disabled
          ? "border-l-muted bg-secondary/25 opacity-70"
          : selected
            ? "border-l-rose-500/70"
            : "border-l-emerald-500/60",
      )}
    >
      <button
        type="button"
        onClick={onToggleExpanded}
        className="flex w-full items-start gap-3 px-4 py-3 text-left"
      >
        {expanded ? (
          <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <span className="mt-0.5 rounded border border-primary/15 bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-primary">
          {subQuestion.id}
        </span>
        <div className="min-w-0 flex-1">
          <p className={cn("text-sm leading-relaxed", disabled ? "text-muted-foreground" : "text-foreground/90")}>{subQuestion.text}</p>
          {subQuestion.help_text ? (
            <p className="mt-1 text-xs italic text-muted-foreground">{subQuestion.help_text}</p>
          ) : null}
        </div>
      </button>

      {expanded ? (
        <div className="space-y-3 px-10 pb-4 pr-4">
          <button
            type="button"
            onClick={() => {
              if (!disabled) onChange({ ...subQuestion, answer: !selected });
            }}
            disabled={disabled}
            className={cn(
              "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60",
              disabled
                ? "border-border bg-secondary/35 text-muted-foreground"
                : selected
                ? "border-rose-500/35 bg-rose-500/12 text-rose-700 dark:text-rose-300"
                : "border-border bg-secondary/45 text-muted-foreground hover:bg-secondary",
            )}
          >
            {selected ? <CheckCheck className="h-3.5 w-3.5" /> : <Ban className="h-3.5 w-3.5" />}
            {selected ? "Driver applies" : "Not applicable"}
          </button>

          <div>
            <label className="text-[11px] font-semibold uppercase text-muted-foreground">Reasoning</label>
            <div className="mt-1 flex items-start gap-1">
              <AutoResizeTextarea
                value={subQuestion.reasoning}
                onChange={(event) => onChange({ ...subQuestion, reasoning: event.target.value })}
                disabled={disabled}
                placeholder="Explain why this driver does or does not apply..."
              />
              <CopyButton text={subQuestion.reasoning} />
            </div>
          </div>

          <div>
            <label className="text-[11px] font-semibold uppercase text-muted-foreground">Citations</label>
            <div className="mt-1 flex items-start gap-1">
              <AutoResizeTextarea
                value={subQuestion.citations}
                onChange={(event) => onChange({ ...subQuestion, citations: event.target.value })}
                disabled={disabled}
                placeholder="Reference supporting evidence..."
              />
              <CopyButton text={subQuestion.citations} />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function QuestionRow({
  question,
  onChange,
  expandAllSignal,
  collapseAllSignal,
  blankEntryMode = false,
}: {
  question: FormQuestion;
  onChange: (question: FormQuestion) => void;
  expandAllSignal: number;
  collapseAllSignal: number;
  blankEntryMode?: boolean;
}) {
  const questionAnswer = getQuestionAnswer(question);
  const [expanded, setExpanded] = useState(questionAnswer === "No");
  const [expandedSubs, setExpandedSubs] = useState<Set<string>>(new Set());
  const [driverClearNotice, setDriverClearNotice] = useState(false);
  const subQuestions = question.sub_questions ?? [];
  const driverCount = subQuestions.filter((subQuestion) => subQuestion.answer).length;
  const subQuestionsDisabled = subQuestions.length > 0 && questionAnswer !== "No";

  useEffect(() => {
    if (questionAnswer === "No" && subQuestions.length > 0) {
      setExpanded(true);
      setDriverClearNotice(false);
      return;
    }
    if (blankEntryMode && subQuestions.length > 0) {
      setExpanded(false);
      setExpandedSubs(new Set());
    }
  }, [blankEntryMode, questionAnswer, subQuestions.length]);

  useEffect(() => {
    if (expandAllSignal === 0) return;
    setExpanded(true);
    setExpandedSubs(new Set(subQuestions.map((subQuestion) => subQuestion.id)));
  }, [expandAllSignal]);

  useEffect(() => {
    if (collapseAllSignal === 0) return;
    setExpanded(false);
    setExpandedSubs(new Set());
  }, [collapseAllSignal]);

  const updateSubQuestion = (subQuestion: FormSubQuestion) => {
    if (subQuestionsDisabled) return;
    onChange({
      ...question,
      sub_questions: subQuestions.map((candidate) =>
        candidate.id === subQuestion.id ? subQuestion : candidate,
      ),
    });
  };

  const updateAnswer = (answer: QuestionAnswer) => {
    const hadDrivers = driverCount > 0;
    const nextSubQuestions = answer === "Yes" && subQuestions.length > 0
      ? subQuestions.map((subQuestion) => ({ ...subQuestion, answer: false }))
      : subQuestions;
    setDriverClearNotice(answer === "Yes" && hadDrivers);
    onChange({
      ...question,
      answer,
      sub_questions: subQuestions.length > 0 ? nextSubQuestions : question.sub_questions,
    });
  };

  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border border-border/70 border-l-[3px] bg-card shadow-sm transition-shadow hover:shadow-md",
        questionAnswer === "Yes"
          ? "border-l-emerald-500/70"
          : questionAnswer === "No"
            ? "border-l-rose-500/70"
            : "border-l-muted",
      )}
    >
      <div className="flex flex-col gap-3 p-4 xl:flex-row xl:items-start">
        <span className="w-fit rounded-md border border-primary/15 bg-primary/10 px-2 py-0.5 font-mono text-[11px] font-bold text-primary">
          {question.id}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm leading-relaxed text-foreground">{question.text}</p>
          {question.help_text ? (
            <p className="mt-1 text-xs italic text-muted-foreground">{question.help_text}</p>
          ) : null}
          {subQuestions.length > 0 ? (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={blankEntryMode && questionAnswer !== "No"}
                onClick={() => setExpanded((current) => !current)}
                className="inline-flex items-center gap-1.5 rounded-md border bg-secondary/50 px-2.5 py-1.5 text-xs font-semibold text-foreground/75 transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-60"
              >
                {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                {subQuestions.length} option{subQuestions.length === 1 ? "" : "s"}
              </button>
              {driverCount && questionAnswer === "No" ? (
                <Badge variant="danger" className="text-[11px]">
                  {driverCount} driver{driverCount === 1 ? "" : "s"}
                </Badge>
              ) : null}
              {subQuestionsDisabled ? (
                <Badge variant="outline" className="text-[11px]">
                  drivers off
                </Badge>
              ) : null}
            </div>
          ) : null}
          {driverClearNotice && questionAnswer === "Yes" ? (
            <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-300">
              <AlertTriangle className="h-3.5 w-3.5" />
              Driver selections were cleared for this Yes answer.
            </p>
          ) : null}
        </div>
        <AnswerButtons
          value={questionAnswer}
          onChange={updateAnswer}
        />
      </div>

      {subQuestions.length === 0 ? (
        <div className="grid gap-3 border-t bg-secondary/20 p-4 md:grid-cols-2">
          <div>
            <label className="text-[11px] font-semibold uppercase text-muted-foreground">Comments</label>
            <div className="mt-1 flex items-start gap-1">
              <AutoResizeTextarea
                value={question.comments ?? ""}
                onChange={(event) => onChange({ ...question, comments: event.target.value })}
                placeholder="Question-level reasoning..."
              />
              <CopyButton text={question.comments ?? ""} />
            </div>
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase text-muted-foreground">Citations</label>
            <div className="mt-1 flex items-start gap-1">
              <AutoResizeTextarea
                value={question.citations ?? ""}
                onChange={(event) => onChange({ ...question, citations: event.target.value })}
                placeholder="Question-level evidence references..."
              />
              <CopyButton text={question.citations ?? ""} />
            </div>
          </div>
        </div>
      ) : null}

      {expanded ? (
        <div className="divide-y border-t bg-secondary/30">
          {subQuestions.map((subQuestion) => (
            <SubQuestionRow
              key={subQuestion.id}
              subQuestion={subQuestion}
              expanded={expandedSubs.has(subQuestion.id)}
              onToggleExpanded={() =>
                setExpandedSubs((current) => {
                  const next = new Set(current);
                  if (next.has(subQuestion.id)) next.delete(subQuestion.id);
                  else next.add(subQuestion.id);
                  return next;
                })
              }
              disabled={subQuestionsDisabled}
              onChange={updateSubQuestion}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function AuditQuestionForm({
  reviewId,
  form,
  onSubmit,
  onClose,
  collapsed = false,
  metadata,
  submitLabel = "Submit Form",
  allowSubmitWhenPristine = false,
  blankEntryMode = false,
}: {
  reviewId: string;
  form: AuditFormResult;
  onSubmit: (form: AuditFormResult) => Promise<void>;
  onClose?: () => void;
  collapsed?: boolean;
  metadata?: AuditFormMetadata;
  submitLabel?: string;
  allowSubmitWhenPristine?: boolean;
  blankEntryMode?: boolean;
}) {
  const [draft, setDraft] = useState(() => cloneForm(form));
  const [baseline, setBaseline] = useState(() => cloneForm(form));
  const [saving, setSaving] = useState(false);
  const [savedPulse, setSavedPulse] = useState(false);
  const [collapsedLocal, setCollapsedLocal] = useState(collapsed);
  const [expandAllSignal, setExpandAllSignal] = useState(0);
  const [collapseAllSignal, setCollapseAllSignal] = useState(0);
  const [nestedExpanded, setNestedExpanded] = useState(false);
  const [saveNotice, setSaveNotice] = useState<{
    type: "error" | "success";
    title: string;
    message: string;
  } | null>(null);

  useEffect(() => {
    setDraft(cloneForm(form));
    setBaseline(cloneForm(form));
  }, [form]);

  useEffect(() => {
    setCollapsedLocal(collapsed);
  }, [collapsed]);

  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(baseline),
    [draft, baseline],
  );
  const yesCount = draft.questions.filter((question) => getQuestionAnswer(question) === "Yes").length;
  const noCount = draft.questions.filter((question) => getQuestionAnswer(question) === "No").length;
  const unansweredCount = draft.questions.filter((question) => !getQuestionAnswer(question)).length;
  const driverCount = draft.questions.reduce(
    (count, question) =>
      count + (getQuestionAnswer(question) === "No"
        ? (question.sub_questions ?? []).filter((subQuestion) => subQuestion.answer).length
        : 0),
    0,
  );
  const overallOutcome = getOverallOutcome(draft);
  const metadataItems = useMemo(
    () => buildMetadataItems(reviewId, metadata),
    [metadata, reviewId],
  );

  const updateQuestion = (question: FormQuestion) => {
    setSaveNotice(null);
    setDraft((current) => ({
      ...current,
      questions: current.questions.map((candidate) =>
        candidate.id === question.id ? question : candidate,
      ),
    }));
  };

  const save = async () => {
    const localValidationError = validateFormForSubmit(draft, {
      manualEntryMode: blankEntryMode,
      requireOutcomeJustification: blankEntryMode,
    });
    if (localValidationError) {
      setSaveNotice({
        type: "error",
        title: "Form needs attention",
        message: localValidationError,
      });
      return;
    }

    const nextForm = normalizeFormForSubmit(draft);
    setSaving(true);
    try {
      await onSubmit(nextForm);
      setDraft(cloneForm(nextForm));
      setBaseline(cloneForm(nextForm));
      setSavedPulse(true);
      setSaveNotice({
        type: "success",
        title: "Form saved",
        message: "This entry is ready in the batch configuration.",
      });
      window.setTimeout(() => setSavedPulse(false), 1800);
    } catch (error) {
      setSaveNotice({
        type: "error",
        title: "Unable to save form",
        message: error instanceof Error ? error.message : "Unable to save the form.",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <article className="relative overflow-hidden rounded-lg border bg-card shadow-sm">
      <Toast
        open={Boolean(saveNotice)}
        variant={saveNotice?.type ?? "info"}
        title={saveNotice?.title ?? ""}
        message={saveNotice?.message}
        onClose={() => setSaveNotice(null)}
      />
      <div className="relative border-b bg-secondary/45 px-4 py-3 pr-36">
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <ClipboardList className="h-4 w-4 text-primary" />
              <h2 className="truncate text-base font-semibold">{draft.title}</h2>
              <Badge variant="outline" className="font-mono text-[10px]">
                {draft.form_id}@{draft.form_version}
              </Badge>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{draft.description}</p>
            {metadataItems.length ? (
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                {metadataItems.map((item) => (
                  <span
                    key={`${item.label}-${item.value}`}
                    className="inline-flex items-center gap-1 rounded-md border bg-background/70 px-2 py-1 text-[11px] text-muted-foreground"
                  >
                    <span className="font-semibold text-foreground/70">{item.label}</span>
                    <span>{item.value}</span>
                  </span>
                ))}
              </div>
            ) : null}
          </div>
          <div className="absolute right-3 top-3 flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => {
                if (nestedExpanded) {
                  setCollapseAllSignal((current) => current + 1);
                  setNestedExpanded(false);
                } else {
                  setCollapsedLocal(false);
                  setExpandAllSignal((current) => current + 1);
                  setNestedExpanded(true);
                }
              }}
              title={nestedExpanded ? "Collapse questions and sub-questions" : "Expand form and sub-questions"}
              aria-label={nestedExpanded ? "Collapse questions and sub-questions" : "Expand form and sub-questions"}
            >
              {nestedExpanded ? <ChevronsUp className="h-4 w-4" /> : <ChevronsDown className="h-4 w-4" />}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => setCollapsedLocal((current) => !current)}
              title={collapsedLocal ? "Expand form" : "Collapse form"}
              aria-label={collapsedLocal ? "Expand form" : "Collapse form"}
            >
              {collapsedLocal ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
            {onClose ? (
              <Button type="button" variant="ghost" size="icon" onClick={onClose} title="Close form" aria-label="Close form">
                <X className="h-4 w-4" />
              </Button>
            ) : null}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {overallOutcome ? (
            <Badge variant={overallOutcome === "Meets" ? "success" : "danger"}>
              {overallOutcome}
            </Badge>
          ) : (
            <Badge variant="outline">Outcome not selected</Badge>
          )}
          <Badge variant="outline">{draft.questions.length} questions</Badge>
          <Badge variant="success">{yesCount} Yes</Badge>
          <Badge variant="danger">{noCount} No</Badge>
          {unansweredCount ? <Badge variant="outline">{unansweredCount} unanswered</Badge> : null}
          {driverCount ? <Badge variant="warning">{driverCount} drivers</Badge> : null}
          <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            {saving ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Saving
              </>
            ) : dirty ? (
              <>
                <Pencil className="h-3.5 w-3.5 text-amber-600" />
                Unsaved changes
              </>
            ) : savedPulse ? (
              <>
                <CheckCheck className="h-3.5 w-3.5 text-emerald-600" />
                Saved
              </>
            ) : (
              <>
                <CheckCheck className="h-3.5 w-3.5 text-emerald-600" />
                Up to date
              </>
            )}
          </span>
        </div>
      </div>

      {!collapsedLocal ? (
        <div className="space-y-4 p-4">
          <div className="space-y-3">
            {draft.questions.map((question) => (
              <QuestionRow
                key={question.id}
                question={question}
                onChange={updateQuestion}
                expandAllSignal={expandAllSignal}
                collapseAllSignal={collapseAllSignal}
                blankEntryMode={blankEntryMode}
              />
            ))}
          </div>

          <div className="rounded-lg border bg-background p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <label className="text-[11px] font-semibold uppercase text-muted-foreground">
                  Overall Rating
                </label>
                <div className="mt-2">
                  <OutcomeButtons
                    value={overallOutcome}
                    onChange={(overall_outcome) => {
                      setSaveNotice(null);
                      setDraft((current) => ({
                        ...current,
                        overall_outcome,
                      }));
                    }}
                  />
                </div>
              </div>
            </div>

            <div className="mt-4">
              <label className="text-[11px] font-semibold uppercase text-muted-foreground">
                Outcome Justification
              </label>
              <div className="mt-2 flex items-start gap-1">
                <AutoResizeTextarea
                  value={draft.outcome_justification}
                  onChange={(event) => {
                    setSaveNotice(null);
                    setDraft((current) => ({
                      ...current,
                      outcome_justification: event.target.value,
                    }));
                  }}
                  placeholder="Explain the outcome..."
                />
                <CopyButton text={draft.outcome_justification} />
              </div>
            </div>
          </div>

          <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card/95 p-3 shadow-sm backdrop-blur">
            <div className="text-xs text-muted-foreground">
              Review <span className="font-mono">{reviewId.slice(0, 8)}</span>
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setDraft(cloneForm(baseline));
                  setSavedPulse(false);
                }}
                disabled={!dirty || saving}
              >
                <X className="h-3.5 w-3.5" />
                Reset
              </Button>
              {onClose ? (
                <Button type="button" variant="outline" size="sm" onClick={onClose} disabled={saving}>
                  Close
                </Button>
              ) : null}
              <Button type="button" size="sm" onClick={save} disabled={saving || (!dirty && !allowSubmitWhenPristine)}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                {submitLabel}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </article>
  );
}

function validateFormForSubmit(
  form: AuditFormResult,
  {
    manualEntryMode = false,
    requireOutcomeJustification = false,
  }: {
    manualEntryMode?: boolean;
    requireOutcomeJustification?: boolean;
  } = {},
): string {
  if (!getOverallOutcome(form)) {
    return "Choose an overall rating before submitting.";
  }
  if (requireOutcomeJustification && !form.outcome_justification.trim()) {
    return "Add an outcome justification before submitting.";
  }
  for (const question of form.questions) {
    const answer = getQuestionAnswer(question);
    if (!answer) {
      return `${question.id} needs a Yes or No answer before submitting.`;
    }
    const subQuestions = question.sub_questions ?? [];
    if (subQuestions.length === 0) {
      const needsQuestionReasoning = !manualEntryMode || answer === "No";
      if (needsQuestionReasoning && !question.comments?.trim()) {
        return `${question.id} needs question-level comments before submitting.`;
      }
      if (!manualEntryMode && !question.citations?.trim()) {
        return `${question.id} needs question-level citations before submitting.`;
      }
    }
    if (answer === "No" && subQuestions.length > 0 && !subQuestions.some((subQuestion) => subQuestion.answer)) {
      return `${question.id} has driver options. Select at least one driver before submitting.`;
    }
    if (answer === "Yes" && subQuestions.some((subQuestion) => subQuestion.answer)) {
      return `${question.id} is Yes, so its driver options must be off before submitting.`;
    }
    for (const subQuestion of subQuestions) {
      if (!subQuestion.answer) continue;
      if (!subQuestion.reasoning.trim()) {
        return `${subQuestion.id} is selected and needs reasoning before submitting.`;
      }
      if (!manualEntryMode && !subQuestion.citations.trim()) {
        return `${subQuestion.id} is selected and needs citations before submitting.`;
      }
    }
  }

  return "";
}
