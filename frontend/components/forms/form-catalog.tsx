"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Braces,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Code2,
  Copy,
  FileJson,
  FilePlus2,
  Files,
  GitBranch,
  Info,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  extractFormFromExcel,
  getFormDefinition,
  listFormCatalog,
  registerForm,
} from "@/lib/api";
import type {
  AuditFormDefinition,
  AuditFormResult,
  FormCatalogEntry,
  FormQuestion,
  FormSubQuestion,
  OverallOutcome,
  QuestionAnswer,
} from "@/lib/types";
import { cn } from "@/lib/utils";

type DialogMode = "create" | "edit";
type UsageFilter = "all" | "used" | "unused";
type PreviewMode = "form" | "json" | "string";

interface FormEditorState {
  id: string;
  version: string;
  title: string;
  description: string;
  auditScope: string;
  toolInstructions: string;
  questions: FormQuestion[];
  overallOutcome: OverallOutcome;
  outcomeJustification: string;
  jsonText: string;
}

const subQuestionSchema = z.object({
  id: z.string().trim().min(1, "Sub-question ID is required."),
  text: z.string().trim().min(1, "Sub-question text is required."),
  reasoning: z.string().default(""),
  citations: z.string().default(""),
  answer: z.boolean(),
  help_text: z.string().nullable().optional(),
});

const questionSchema = z
  .object({
    id: z.string().trim().min(1, "Question ID is required."),
    text: z.string().trim().min(1, "Question text is required."),
    answer: z.enum(["Yes", "No"]),
    sub_questions: z.array(subQuestionSchema),
    help_text: z.string().nullable().optional(),
  })
  .superRefine((question, ctx) => {
    if (question.answer === "No" && question.sub_questions.length === 0) {
      ctx.addIssue({
        code: "custom",
        message: `${question.id}: No answers need at least one driver.`,
        path: ["sub_questions"],
      });
    }
    if (
      question.answer === "No" &&
      question.sub_questions.length > 0 &&
      !question.sub_questions.some((subQuestion) => subQuestion.answer)
    ) {
      ctx.addIssue({
        code: "custom",
        message: `${question.id}: Mark at least one driver as applicable.`,
        path: ["sub_questions"],
      });
    }
    if (question.answer === "Yes" && question.sub_questions.length > 0) {
      ctx.addIssue({
        code: "custom",
        message: `${question.id}: Yes answers must not include drivers.`,
        path: ["sub_questions"],
      });
    }
  });

const auditFormSchema = z.object({
  form_id: z
    .string()
    .trim()
    .min(1, "Form ID is required.")
    .regex(/^[a-z][a-z0-9_]*$/, "Use lowercase letters, numbers, and underscores."),
  form_version: z
    .string()
    .trim()
    .min(1, "Version is required.")
    .regex(/^v?\d+(?:\.\d+)*$/, "Use a numeric version such as v0.1 or v1.0.0."),
  title: z.string().trim().min(1, "Title is required."),
  description: z.string().trim().min(1, "Description is required."),
  questions: z.array(questionSchema).min(1, "Add at least one question."),
  overall_outcome: z.enum(["Meets", "Does Not Meet"]),
  outcome_justification: z.string().trim().min(1, "Outcome justification is required."),
});

const emptySubQuestion = (questionId: string, index: number): FormSubQuestion => ({
  id: `${questionId}.${index}`,
  text: "",
  reasoning: "",
  citations: "",
  answer: true,
  help_text: "",
});

const emptyQuestion = (index: number): FormQuestion => {
  const id = `Q${index}`;
  return {
    id,
    text: "",
    answer: "No",
    help_text: "",
    sub_questions: [emptySubQuestion(id, 1)],
  };
};

function formKey(form: Pick<FormCatalogEntry, "id" | "version">): string {
  return `${form.id}@${form.version}`;
}

function splitFormKey(key: string): { id: string; version: string } {
  const separator = key.lastIndexOf("@");
  if (separator < 0) return { id: key, version: "" };
  return {
    id: key.slice(0, separator),
    version: key.slice(separator + 1),
  };
}

function formatDate(value?: string | null): string {
  if (!value) return "No activity";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "No activity";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function titleFromId(id: string): string {
  return id
    .split("_")
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(" ");
}

function incrementVersion(version: string): string {
  const match = version.match(/^(v?)(\d+(?:\.\d+)*)$/);
  if (!match) return "v0.1";
  const [, prefix, numeric] = match;
  const parts = numeric.split(".").map((part) => Number(part));
  parts[parts.length - 1] += 1;
  return `${prefix}${parts.join(".")}`;
}

function nextVersion(version: string, formId: string, forms: FormCatalogEntry[]): string {
  const used = new Set(forms.filter((form) => form.id === formId).map((form) => form.version));
  let candidate = incrementVersion(version);
  for (let attempts = 0; used.has(candidate) && attempts < 50; attempts += 1) {
    candidate = incrementVersion(candidate);
  }
  return candidate;
}

function normalizeOptionalText(value?: string | null): string | null {
  const trimmed = (value ?? "").trim();
  return trimmed ? trimmed : null;
}

function buildCanonical(state: FormEditorState): AuditFormResult {
  const formId = state.id.trim();
  const version = state.version.trim();
  const title = state.title.trim() || titleFromId(formId);
  const description = state.description.trim() || "Canonical audit form template.";
  return {
    form_id: formId,
    form_version: version,
    title,
    description,
    questions: state.questions.map((question) => ({
      ...question,
      id: question.id.trim(),
      text: question.text.trim(),
      help_text: normalizeOptionalText(question.help_text),
      answer: question.answer,
      sub_questions:
        question.answer === "Yes"
          ? []
          : question.sub_questions.map((subQuestion) => ({
              ...subQuestion,
              id: subQuestion.id.trim(),
              text: subQuestion.text.trim(),
              reasoning: subQuestion.reasoning ?? "",
              citations: subQuestion.citations ?? "",
              help_text: normalizeOptionalText(subQuestion.help_text),
              answer: Boolean(subQuestion.answer),
            })),
    })),
    overall_outcome: state.overallOutcome || "Does Not Meet",
    outcome_justification:
      state.outcomeJustification.trim() || "Canonical template placeholder outcome.",
  };
}

function buildDefinition(state: FormEditorState): AuditFormDefinition {
  const canonical = buildCanonical(state);
  return {
    id: canonical.form_id,
    version: canonical.form_version,
    title: canonical.title,
    description: canonical.description,
    audit_scope: normalizeOptionalText(state.auditScope),
    tool_instructions: normalizeOptionalText(state.toolInstructions),
    canonical,
  };
}

function asQuestionnaireString(form: AuditFormResult): string {
  const lines = [
    `TFR Questionnaire: ${form.title}`,
    "Complete each question from the file evidence. Answers must be exactly 'Yes' or 'No'. For 'Yes' answers, return an empty sub_questions list. For 'No' answers, include at least one listed sub-question and set answer=true for every applicable driver.",
  ];

  for (const question of form.questions) {
    const helpText = question.help_text ? ` (help_text: ${question.help_text})` : "";
    lines.push("", `${question.id}: ${question.text}${helpText}`);
    if (question.sub_questions.length) {
      lines.push("Sub-Questions:");
      for (const subQuestion of question.sub_questions) {
        const subHelpText = subQuestion.help_text ? ` (help_text: ${subQuestion.help_text})` : "";
        lines.push(`  ${subQuestion.id}: ${subQuestion.text}${subHelpText}`);
      }
    }
  }

  lines.push("", "Overall Outcome: Options: Meets, Does Not Meet");
  return lines.join("\n");
}

function definitionToState(
  definition: AuditFormDefinition | null,
  mode: DialogMode,
  forms: FormCatalogEntry[],
): FormEditorState {
  const canonical = definition?.canonical;
  const baseId = definition?.id ?? canonical?.form_id ?? "new_audit_form";
  const baseVersion = definition?.version ?? canonical?.form_version ?? "v0.1";
  const version = mode === "edit" ? nextVersion(baseVersion, baseId, forms) : baseVersion;
  const title = definition?.title ?? canonical?.title ?? titleFromId(baseId);
  const description = definition?.description ?? canonical?.description ?? "";
  const questions = canonical?.questions?.length
    ? canonical.questions.map((question) => ({
        ...question,
        help_text: question.help_text ?? "",
        sub_questions: (question.sub_questions ?? []).map((subQuestion) => ({
          ...subQuestion,
          reasoning: subQuestion.reasoning ?? "",
          citations: subQuestion.citations ?? "",
          help_text: subQuestion.help_text ?? "",
        })),
      }))
    : [emptyQuestion(1)];

  const state: FormEditorState = {
    id: baseId,
    version,
    title,
    description,
    auditScope: definition?.audit_scope ?? "",
    toolInstructions: definition?.tool_instructions ?? "",
    questions,
    overallOutcome: canonical?.overall_outcome ?? "Does Not Meet",
    outcomeJustification: canonical?.outcome_justification ?? "Canonical template draft.",
    jsonText: "",
  };
  return {
    ...state,
    jsonText: JSON.stringify(buildCanonical(state), null, 2),
  };
}

function zodMessage(error: unknown): string {
  if (error instanceof z.ZodError) {
    return error.issues.map((issue) => issue.message).join(" ");
  }
  if (error instanceof Error) return error.message;
  return "The form could not be validated.";
}

function useBodyScrollLock(open: boolean) {
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);
}

function MetadataPill({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border bg-background px-3 py-2">
      <p className="text-[11px] font-semibold uppercase text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-medium tabular-nums">{value}</p>
    </div>
  );
}

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  const copyText = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="gap-1.5"
      onClick={() => void copyText()}
      disabled={!text}
    >
      {copied ? <ClipboardCheck className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? "Copied" : label}
    </Button>
  );
}

function FieldLabel({
  htmlFor,
  label,
  optional,
  tooltip,
}: {
  htmlFor: string;
  label: string;
  optional?: boolean;
  tooltip?: string;
}) {
  return (
    <label htmlFor={htmlFor} className="flex items-center gap-1.5 text-sm font-medium">
      {label}
      {optional ? <span className="text-xs font-normal text-muted-foreground">optional</span> : null}
      {tooltip ? (
        <span title={tooltip} aria-label={tooltip}>
          <Info className="h-3.5 w-3.5 text-muted-foreground" />
        </span>
      ) : null}
    </label>
  );
}

function FormCatalogRow({
  form,
  selected,
  compact,
  onSelect,
}: {
  form: FormCatalogEntry;
  selected: boolean;
  compact: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClickCapture={(event) => {
        if (!selected) return;
        event.preventDefault();
        event.stopPropagation();
        onSelect();
      }}
      onPointerDown={(event) => {
        if (!selected) return;
        event.preventDefault();
        onSelect();
      }}
      onClick={() => {
        if (!selected) onSelect();
      }}
      className={cn(
        "grid w-full gap-3 border-b px-4 py-3 text-left transition-colors hover:bg-secondary/45",
        compact ? "grid-cols-1" : "md:grid-cols-[minmax(0,1fr)_auto]",
        selected && "border-primary bg-primary/5",
      )}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate text-sm font-medium">{form.title}</p>
          {selected ? <Badge variant="outline">Open</Badge> : null}
          <Badge variant="outline" className="font-mono text-[10px]">
            {form.id}@{form.version}
          </Badge>
        </div>
        <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">
          {form.description || "No description"}
        </p>
      </div>
      <div className={cn("flex flex-wrap items-center gap-1.5", compact ? "" : "md:justify-end")}>
        <Badge variant={form.reviewCount ? "success" : "secondary"}>
          {form.reviewCount ? "used" : "unused"}
        </Badge>
        <Badge variant="outline">{form.questionCount} questions</Badge>
        <Badge variant="outline">{form.subQuestionCount} sub-questions</Badge>
        <Badge variant="outline">{form.completedCount} completed</Badge>
        {!compact ? <Badge variant="outline">Created {formatDate(form.createdAt)}</Badge> : null}
      </div>
    </button>
  );
}

function QuestionPreview({ question }: { question: FormQuestion }) {
  const [expanded, setExpanded] = useState(true);
  const hasDrivers = question.sub_questions.length > 0;

  return (
    <div className="rounded-lg border bg-background">
      <button
        type="button"
        onClick={() => hasDrivers && setExpanded((current) => !current)}
        className={cn("flex w-full items-start gap-3 p-3 text-left", hasDrivers && "hover:bg-secondary/40")}
      >
        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center text-muted-foreground">
          {hasDrivers ? (
            expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />
          ) : null}
        </span>
        <span className="mt-0.5 shrink-0 rounded border border-primary/15 bg-primary/10 px-2 py-0.5 font-mono text-[11px] font-bold text-primary">
          {question.id}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm leading-relaxed md:text-[15px]">{question.text}</p>
          {question.help_text ? <p className="mt-1 text-xs italic text-muted-foreground">{question.help_text}</p> : null}
        </div>
      </button>
      {expanded ? (
        <div className="divide-y border-t bg-secondary/25">
          {question.sub_questions.map((subQuestion) => (
            <div key={subQuestion.id} className="flex items-start gap-3 px-4 py-3">
              <span className="mt-0.5 shrink-0 rounded border bg-background px-1.5 py-0.5 font-mono text-[10px] font-bold text-muted-foreground">
                {subQuestion.id}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm">{subQuestion.text}</p>
                {subQuestion.help_text ? (
                  <p className="mt-1 text-xs italic text-muted-foreground">{subQuestion.help_text}</p>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function FormPreviewContent({
  canonical,
  mode,
  jsonText,
}: {
  canonical: AuditFormResult;
  mode: PreviewMode;
  jsonText: string;
}) {
  if (mode === "json") {
    return (
      <Textarea
        value={jsonText}
        readOnly
        className="min-h-[420px] font-mono text-xs"
        spellCheck={false}
      />
    );
  }

  if (mode === "string") {
    return (
      <pre className="chat-scrollbar max-h-[560px] overflow-auto whitespace-pre-wrap rounded-lg border bg-secondary/25 p-4 font-mono text-xs leading-relaxed">
        {asQuestionnaireString(canonical)}
      </pre>
    );
  }

  return (
    <div className="chat-scrollbar max-h-[560px] space-y-3 overflow-auto rounded-lg border bg-secondary/20 p-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-base font-semibold">{canonical.title}</h3>
          <Badge variant="outline" className="font-mono text-[10px]">
            {canonical.form_id}@{canonical.form_version}
          </Badge>
        </div>
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{canonical.description}</p>
      </div>
      <div className="space-y-3">
        {canonical.questions.map((question) => (
          <QuestionPreview key={question.id} question={question} />
        ))}
      </div>
    </div>
  );
}

function FormPreviewPanel({
  state,
  open,
  mode,
  onOpenChange,
  onModeChange,
  onRefreshJson,
}: {
  state: FormEditorState;
  open: boolean;
  mode: PreviewMode;
  onOpenChange: (open: boolean) => void;
  onModeChange: (mode: PreviewMode) => void;
  onRefreshJson: () => void;
}) {
  const canonical = buildCanonical(state);
  const previewJson = state.jsonText || JSON.stringify(canonical, null, 2);
  const previewString = asQuestionnaireString(canonical);
  const content = (
    <FormPreviewContent
      canonical={canonical}
      mode={mode}
      jsonText={previewJson}
    />
  );

  const controls = (
    <div className="flex flex-wrap items-center gap-2">
      {(["form", "json", "string"] as PreviewMode[]).map((candidate) => {
        const Icon = candidate === "form" ? BookOpen : candidate === "json" ? Code2 : FileJson;
        return (
          <button
            key={candidate}
            type="button"
            onClick={() => {
              if (candidate === "json") onRefreshJson();
              onModeChange(candidate);
            }}
            className={cn(
              "inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors",
              mode === candidate
                ? "border-primary bg-primary text-primary-foreground"
                : "bg-background hover:bg-secondary",
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {candidate === "form" ? "Form" : candidate === "json" ? "JSON" : "String"}
          </button>
        );
      })}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="gap-1.5"
        onClick={onRefreshJson}
      >
        <RefreshCw className="h-3.5 w-3.5" />
        Refresh Form
      </Button>
      {mode === "json" ? <CopyButton text={previewJson} label="Copy JSON" /> : null}
      {mode === "string" ? <CopyButton text={previewString} label="Copy String" /> : null}
    </div>
  );

  return (
    <>
      <div className="rounded-lg border bg-background">
        <button
          type="button"
          onClick={() => {
            if (!open) onRefreshJson();
            onOpenChange(!open);
          }}
          className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-secondary/35"
        >
          <span className="flex items-center gap-2 text-sm font-semibold">
            <BookOpen className="h-4 w-4 text-primary" />
            Form Preview
          </span>
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
        {open ? (
          <div className="grid gap-3 border-t p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              {controls}
            </div>
            {content}
          </div>
        ) : null}
      </div>
    </>
  );
}

export function FormCatalog() {
  const [forms, setForms] = useState<FormCatalogEntry[]>([]);
  const [query, setQuery] = useState("");
  const [usageFilter, setUsageFilter] = useState<UsageFilter>("all");
  const [selectedKey, setSelectedKey] = useState("");
  const [selectedDefinition, setSelectedDefinition] = useState<AuditFormDefinition | null>(null);
  const [loading, setLoading] = useState(true);
  const [definitionLoading, setDefinitionLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState<DialogMode>("create");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const nextForms = await listFormCatalog();
      setForms(nextForms);
      setSelectedKey((current) => {
        if (current && nextForms.some((form) => formKey(form) === current)) return current;
        return "";
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the form catalog.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedKey) {
      setSelectedDefinition(null);
      return;
    }
    const { id, version } = splitFormKey(selectedKey);
    let active = true;
    setDefinitionLoading(true);
    setError("");
    getFormDefinition(id, version)
      .then((definition) => {
        if (active) setSelectedDefinition(definition);
      })
      .catch((err) => {
        if (active) {
          setSelectedDefinition(null);
          setError(err instanceof Error ? err.message : "Failed to load that form definition.");
        }
      })
      .finally(() => {
        if (active) setDefinitionLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedKey]);

  const filteredForms = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return forms.filter((form) => {
      const matchesQuery =
        !normalized ||
        [
          form.id,
          form.version,
          form.title,
          form.description,
          form.auditScope,
          form.toolInstructions,
        ]
          .join(" ")
          .toLowerCase()
          .includes(normalized);
      const matchesUsage =
        usageFilter === "all" ||
        (usageFilter === "used" ? form.reviewCount > 0 : form.reviewCount === 0);
      return matchesQuery && matchesUsage;
    });
  }, [forms, query, usageFilter]);

  const selectedForm = useMemo(
    () => forms.find((form) => formKey(form) === selectedKey) ?? null,
    [forms, selectedKey],
  );

  const aggregateStats = useMemo(
    () => ({
      forms: filteredForms.length,
      questions: filteredForms.reduce((total, form) => total + form.questionCount, 0),
      subQuestions: filteredForms.reduce((total, form) => total + form.subQuestionCount, 0),
      reviews: filteredForms.reduce((total, form) => total + form.reviewCount, 0),
      completed: filteredForms.reduce((total, form) => total + form.completedCount, 0),
    }),
    [filteredForms],
  );
  const hasSelection = Boolean(selectedKey);

  const openCreate = () => {
    setDialogMode("create");
    setDialogOpen(true);
  };

  const openEdit = () => {
    if (!selectedDefinition) return;
    setDialogMode("edit");
    setDialogOpen(true);
  };

  const saveDefinition = async (definition: AuditFormDefinition) => {
    setSaving(true);
    setError("");
    try {
      const saved = await registerForm(definition);
      setDialogOpen(false);
      await refresh();
      setSelectedKey(`${saved.id}@${saved.version}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to register form.");
      throw err;
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className={cn("grid gap-4", hasSelection && "xl:grid-cols-[600px_minmax(0,1fr)]")}>
        <Card className="min-w-0 overflow-hidden">
          <CardHeader className="border-b">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2">
                <Files className="h-4 w-4 text-primary" />
                Form Catalog
              </CardTitle>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => void refresh()}
                  disabled={loading}
                  title="Refresh forms"
                  aria-label="Refresh forms"
                >
                  {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                </Button>
                <Button type="button" size="sm" className="gap-1.5" onClick={openCreate}>
                  <Plus className="h-4 w-4" />
                  Register
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4 p-0">
            {error ? (
              <div className="m-4 rounded-lg border border-destructive/35 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            ) : null}

            <div className={cn("grid gap-3 border-b bg-secondary/35 p-3", hasSelection ? "grid-cols-1" : "lg:grid-cols-[minmax(220px,1fr)_180px]")}>
              <label className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  className="pl-9"
                  placeholder="Search title, ID, scope, instructions..."
                />
              </label>
              <select
                value={usageFilter}
                onChange={(event) => setUsageFilter(event.target.value as UsageFilter)}
                className="h-10 rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="all">All usage</option>
                <option value="used">Used in reviews</option>
                <option value="unused">Unused</option>
              </select>
            </div>

            <div className={cn("grid gap-2 px-4", hasSelection ? "grid-cols-2" : "sm:grid-cols-5")}>
              <MetadataPill label="Visible" value={aggregateStats.forms} />
              <MetadataPill label="Questions" value={aggregateStats.questions} />
              <MetadataPill label="Sub-Questions" value={aggregateStats.subQuestions} />
              <MetadataPill label="Reviews" value={aggregateStats.reviews} />
              {!hasSelection ? <MetadataPill label="Completed" value={aggregateStats.completed} /> : null}
            </div>

            <div className="chat-scrollbar max-h-[calc(100vh-18rem)] overflow-y-auto">
              {loading && forms.length === 0 ? (
                <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading forms
                </div>
              ) : null}
              {!loading && filteredForms.length === 0 ? (
                <div className="p-8 text-center">
                  <FileJson className="mx-auto h-8 w-8 text-muted-foreground/40" />
                  <p className="mt-2 text-sm font-medium">No forms match</p>
                  <p className="mt-1 text-xs text-muted-foreground">Adjust the search or usage filter.</p>
                </div>
              ) : null}
              {filteredForms.map((form) => {
                const key = formKey(form);
                const selected = selectedKey === key;
                return (
                  <FormCatalogRow
                    key={`${key}-${selected ? "open" : "closed"}`}
                    form={form}
                    selected={selected}
                    compact={hasSelection}
                    onSelect={() => setSelectedKey(selected ? "" : key)}
                  />
                );
              })}
            </div>
          </CardContent>
        </Card>

        {hasSelection ? (
        <Card className="min-w-0">
          <CardHeader className="border-b">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2">
                <FilePlus2 className="h-4 w-4 text-primary" />
                Selected Form
              </CardTitle>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="gap-1.5"
                  onClick={openEdit}
                  disabled={!selectedDefinition || definitionLoading}
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => setSelectedKey("")}
                  aria-label="Close selected form"
                  title="Close selected form"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4 pt-5">
            {definitionLoading ? (
              <div className="flex items-center justify-center gap-2 rounded-lg border bg-background p-8 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading definition
              </div>
            ) : null}

            {selectedForm && selectedDefinition ? (
              <>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-semibold">{selectedDefinition.title}</h2>
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {selectedDefinition.id}@{selectedDefinition.version}
                    </Badge>
                  </div>
                  <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                    {selectedDefinition.description || "No description"}
                  </p>
                </div>

                <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-4">
                  <MetadataPill label="Questions" value={selectedForm.questionCount} />
                  <MetadataPill label="Sub-Questions" value={selectedForm.subQuestionCount} />
                  <MetadataPill label="Reviews" value={selectedForm.reviewCount} />
                  <MetadataPill label="Completed" value={selectedForm.completedCount} />
                  <MetadataPill label="Failed" value={selectedForm.failedCount} />
                  <MetadataPill label="Created" value={formatDate(selectedForm.createdAt)} />
                  <MetadataPill label="Last Review" value={formatDate(selectedForm.lastReviewedAt)} />
                </div>

                {selectedDefinition.audit_scope || selectedDefinition.tool_instructions ? (
                  <div className="grid gap-3 lg:grid-cols-2">
                    {selectedDefinition.audit_scope ? (
                      <div className="rounded-lg border bg-background p-4">
                        <p className="text-[11px] font-semibold uppercase text-muted-foreground">Audit Scope</p>
                        <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{selectedDefinition.audit_scope}</p>
                      </div>
                    ) : null}
                    {selectedDefinition.tool_instructions ? (
                      <div className="rounded-lg border bg-background p-4">
                        <p className="text-[11px] font-semibold uppercase text-muted-foreground">Tool Instructions</p>
                        <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{selectedDefinition.tool_instructions}</p>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="flex justify-end">
                    <Badge
                      variant="outline"
                      className="gap-1 text-[10px] text-muted-foreground"
                      title="No audit scope or tool instructions are stored for this form."
                    >
                      <Info className="h-3 w-3" />
                      No prompt metadata
                    </Badge>
                  </div>
                )}

                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Braces className="h-4 w-4 text-primary" />
                    <h3 className="text-sm font-semibold">Audit Form Questions</h3>
                  </div>
                  {selectedDefinition.canonical.questions.map((question) => (
                    <QuestionPreview key={question.id} question={question} />
                  ))}
                </div>
              </>
            ) : null}
          </CardContent>
        </Card>
        ) : null}
      </div>

      <FormRegistrationDialog
        open={dialogOpen}
        mode={dialogMode}
        forms={forms}
        sourceDefinition={dialogMode === "edit" ? selectedDefinition : null}
        saving={saving}
        onClose={() => {
          if (saving) return;
          setDialogOpen(false);
        }}
        onSave={saveDefinition}
      />
    </>
  );
}

function FormRegistrationDialog({
  open,
  mode,
  forms,
  sourceDefinition,
  saving,
  onClose,
  onSave,
}: {
  open: boolean;
  mode: DialogMode;
  forms: FormCatalogEntry[];
  sourceDefinition: AuditFormDefinition | null;
  saving: boolean;
  onClose: () => void;
  onSave: (definition: AuditFormDefinition) => Promise<void>;
}) {
  const [state, setState] = useState<FormEditorState>(() =>
    definitionToState(sourceDefinition, mode, forms),
  );
  const [expandedQuestions, setExpandedQuestions] = useState<Set<number>>(new Set([0]));
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewMode, setPreviewMode] = useState<PreviewMode>("form");
  const [formError, setFormError] = useState("");
  const [importMessage, setImportMessage] = useState("");
  const [importing, setImporting] = useState(false);
  const [uploadedWorkbookName, setUploadedWorkbookName] = useState("");

  const isEditing = mode === "edit";
  const duplicateVersion = forms.some(
    (form) => form.id === state.id.trim() && form.version === state.version.trim(),
  );
  const runtimeMetadataMissing = !state.auditScope.trim() && !state.toolInstructions.trim();

  useBodyScrollLock(open);

  useEffect(() => {
    if (!open) return;
    const nextState = definitionToState(sourceDefinition, mode, forms);
    setState(nextState);
    setExpandedQuestions(new Set(nextState.questions.map((_, index) => index)));
    setPreviewOpen(false);
    setPreviewMode("form");
    setFormError("");
    setImportMessage("");
    setImporting(false);
    setUploadedWorkbookName("");
  }, [forms, mode, open, sourceDefinition]);

  if (!open) return null;

  const setQuestion = (index: number, patch: Partial<FormQuestion>) => {
    setState((current) => ({
      ...current,
      questions: current.questions.map((question, questionIndex) =>
        questionIndex === index ? { ...question, ...patch } : question,
      ),
    }));
  };

  const addQuestion = () => {
    setState((current) => ({
      ...current,
      questions: [...current.questions, emptyQuestion(current.questions.length + 1)],
    }));
    setExpandedQuestions((current) => new Set([...current, state.questions.length]));
  };

  const removeQuestion = (index: number) => {
    setState((current) => ({
      ...current,
      questions:
        current.questions.length === 1
          ? [emptyQuestion(1)]
          : current.questions.filter((_, questionIndex) => questionIndex !== index),
    }));
  };

  const setSubQuestion = (
    questionIndex: number,
    subQuestionIndex: number,
    patch: Partial<FormSubQuestion>,
  ) => {
    setState((current) => ({
      ...current,
      questions: current.questions.map((question, currentQuestionIndex) =>
        currentQuestionIndex === questionIndex
          ? {
              ...question,
              sub_questions: question.sub_questions.map((subQuestion, currentSubIndex) =>
                currentSubIndex === subQuestionIndex
                  ? { ...subQuestion, ...patch }
                  : subQuestion,
              ),
            }
          : question,
      ),
    }));
  };

  const addSubQuestion = (questionIndex: number) => {
    setState((current) => ({
      ...current,
      questions: current.questions.map((question, index) =>
        index === questionIndex
          ? {
              ...question,
              sub_questions: [
                ...question.sub_questions,
                emptySubQuestion(question.id || `Q${questionIndex + 1}`, question.sub_questions.length + 1),
              ],
            }
          : question,
      ),
    }));
  };

  const removeSubQuestion = (questionIndex: number, subQuestionIndex: number) => {
    setState((current) => ({
      ...current,
      questions: current.questions.map((question, index) =>
        index === questionIndex
          ? {
              ...question,
              sub_questions: question.sub_questions.filter((_, subIndex) => subIndex !== subQuestionIndex),
            }
          : question,
      ),
    }));
  };

  const toggleQuestionExpanded = (index: number) => {
    setExpandedQuestions((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const applyImportedState = (nextState: FormEditorState) => {
    setState((current) => {
      const merged = isEditing
        ? {
            ...nextState,
            id: current.id,
            version: current.version,
          }
        : nextState;
      return {
        ...merged,
        jsonText: JSON.stringify(buildCanonical(merged), null, 2),
      };
    });
  };

  const refreshJson = () => {
    setState((current) => ({
      ...current,
      jsonText: JSON.stringify(buildCanonical(current), null, 2),
    }));
  };

  const importWorkbook = async (file: File) => {
    setImporting(true);
    setFormError("");
    setImportMessage("");
    setUploadedWorkbookName(file.name);
    try {
      const extracted = await extractFormFromExcel(file);
      const nextState = definitionToState(extracted, "create", forms);
      applyImportedState(nextState);
      setExpandedQuestions(new Set(nextState.questions.map((_, index) => index)));
      setImportMessage("Workbook draft loaded. Review the placeholder fields before saving.");
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to extract the workbook.");
    } finally {
      setImporting(false);
    }
  };

  const handleSave = async () => {
    try {
      const definition = buildDefinition(state);
      auditFormSchema.parse(definition.canonical);
      if (duplicateVersion) {
        setFormError("That form ID and version already exist. Edit as a new version before saving.");
        return;
      }
      setFormError("");
      await onSave(definition);
    } catch (err) {
      setFormError(zodMessage(err));
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 p-4 backdrop-blur-sm">
      <div
        aria-modal="true"
        role="dialog"
        className="flex max-h-[94vh] w-full max-w-6xl flex-col overflow-hidden rounded-lg border bg-card shadow-2xl"
      >
        <div className="flex shrink-0 items-start gap-4 border-b bg-secondary/35 px-6 py-5">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border bg-background text-primary">
            {isEditing ? <GitBranch className="h-6 w-6" /> : <FilePlus2 className="h-6 w-6" />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold">
                {isEditing ? "Edit as New Version" : "Register Audit Form"}
              </h2>
              {sourceDefinition && isEditing ? (
                <Badge variant="outline" className="font-mono text-[10px]">
                  source {sourceDefinition.id}@{sourceDefinition.version}
                </Badge>
              ) : null}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {state.title || "Canonical form draft"} · {state.questions.length} questions
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="ml-auto h-9 w-9"
            onClick={onClose}
            disabled={saving}
            aria-label="Close form registration"
            title="Close"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto px-6 py-6">
          <div className="space-y-5">
            <div className="rounded-lg border bg-background p-4">
              <div className="grid gap-4 lg:grid-cols-[minmax(220px,1fr)_150px_minmax(260px,1.2fr)_minmax(260px,1.3fr)]">
                <div className="grid gap-2">
                  <FieldLabel
                    htmlFor="workbook-upload"
                    label="Excel Workbook"
                    optional
                    tooltip="Accepts xlsb, xlsx, and xls uploads. The current extractor is a placeholder draft generator."
                  />
                  <input
                    id="workbook-upload"
                    type="file"
                    accept=".xlsb,.xlsx,.xls"
                    disabled={saving || importing}
                    className="sr-only"
                    onChange={(event) => {
                      const file = event.currentTarget.files?.[0];
                      if (file) void importWorkbook(file);
                      event.currentTarget.value = "";
                    }}
                  />
                  <div className="flex min-w-0 items-center gap-2">
                    <label
                      htmlFor="workbook-upload"
                      className={cn(
                        "inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-md border border-input bg-background px-3 text-sm font-medium transition-colors hover:bg-secondary",
                        (saving || importing) && "pointer-events-none opacity-50",
                      )}
                    >
                      {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                      Upload
                    </label>
                    <span className="truncate text-xs text-muted-foreground">
                      {uploadedWorkbookName || "No workbook selected"}
                    </span>
                  </div>
                  {importMessage ? (
                    <p className="flex items-start gap-1.5 text-xs text-emerald-700 dark:text-emerald-300">
                      <ClipboardCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      {importMessage}
                    </p>
                  ) : null}
                </div>

                <div className="grid gap-2">
                  <FieldLabel
                    htmlFor="form-id"
                    label="Form ID"
                    tooltip="Stable lowercase catalog identifier used by batch jobs and generated reviews."
                  />
                  <Input
                    id="form-id"
                    value={state.id}
                    onChange={(event) => setState((current) => ({ ...current, id: event.target.value }))}
                    disabled={saving || isEditing}
                    placeholder="interior_water"
                  />
                </div>

                <div className="grid gap-2">
                  <FieldLabel
                    htmlFor="form-version"
                    label="Version"
                    tooltip="Editing creates a new version; existing catalog files are not overwritten."
                  />
                  <Input
                    id="form-version"
                    value={state.version}
                    onChange={(event) => setState((current) => ({ ...current, version: event.target.value }))}
                    disabled={saving}
                    placeholder="v0.1"
                  />
                  {duplicateVersion ? (
                    <p className="flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-300">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      This version already exists in the catalog.
                    </p>
                  ) : null}
                </div>

                <div className="grid gap-2">
                  <FieldLabel htmlFor="form-title" label="Title" />
                  <Input
                    id="form-title"
                    value={state.title}
                    onChange={(event) => setState((current) => ({ ...current, title: event.target.value }))}
                    disabled={saving}
                    placeholder="Interior Water Loss Review"
                  />
                </div>
              </div>
            </div>

            <div className="rounded-lg border bg-background">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-secondary/35 px-4 py-3">
                <div>
                  <h3 className="text-sm font-semibold">Audit Form Questions</h3>
                  <p className="text-xs text-muted-foreground">
                    Answers and applicable drivers are stored only so the backend can validate this canonical template.
                  </p>
                </div>
                <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={addQuestion} disabled={saving}>
                  <Plus className="h-3.5 w-3.5" />
                  Question
                </Button>
              </div>
              <div className="divide-y">
                {state.questions.map((question, questionIndex) => {
                  const expanded = expandedQuestions.has(questionIndex);
                  const hasDriverWarning =
                    question.answer === "No" &&
                    (!question.sub_questions.length ||
                      !question.sub_questions.some((subQuestion) => subQuestion.answer));
                  return (
                    <div key={`${question.id}-${questionIndex}`} className="p-4">
                      <div className="flex items-start gap-3">
                        <button
                          type="button"
                          className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-md hover:bg-secondary"
                          onClick={() => toggleQuestionExpanded(questionIndex)}
                          aria-label={expanded ? "Collapse question" : "Expand question"}
                          title={expanded ? "Collapse question" : "Expand question"}
                        >
                          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                        </button>
                        <div className="grid min-w-0 flex-1 gap-3 md:grid-cols-[110px_minmax(0,1fr)_120px_40px]">
                          <Input
                            value={question.id}
                            onChange={(event) => setQuestion(questionIndex, { id: event.target.value })}
                            disabled={saving}
                            placeholder="Q1"
                            className="font-mono"
                          />
                          <Input
                            value={question.text}
                            onChange={(event) => setQuestion(questionIndex, { text: event.target.value })}
                            disabled={saving}
                            placeholder="Question text"
                          />
                          <select
                            value={question.answer}
                            onChange={(event) =>
                              setQuestion(questionIndex, {
                                answer: event.target.value as QuestionAnswer,
                              })
                            }
                            disabled={saving}
                            title="Template answer used for validation only."
                            className="h-10 rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <option value="No">No</option>
                            <option value="Yes">Yes</option>
                          </select>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-10 w-10"
                            onClick={() => removeQuestion(questionIndex)}
                            disabled={saving}
                            aria-label="Remove question"
                            title="Remove question"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>

                      {expanded ? (
                        <div className="mt-4 grid gap-4 pl-11">
                          <div className="grid gap-2">
                            <FieldLabel htmlFor={`question-help-${questionIndex}`} label="Question Help Text" optional />
                            <Textarea
                              id={`question-help-${questionIndex}`}
                              value={question.help_text ?? ""}
                              onChange={(event) =>
                                setQuestion(questionIndex, { help_text: event.target.value })
                              }
                              disabled={saving}
                              className="min-h-[76px]"
                              placeholder="Evidence to consider for this question"
                            />
                          </div>

                          {question.answer === "Yes" ? (
                            <div className="flex items-start gap-2 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200">
                              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                              <span>Drivers are omitted from saved Yes-answer questions.</span>
                            </div>
                          ) : (
                            <div className="rounded-lg border bg-card">
                              <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
                                <div>
                                  <p className="text-sm font-medium">Drivers</p>
                                  {hasDriverWarning ? (
                                    <p className="text-xs text-amber-700 dark:text-amber-300">
                                      Mark at least one driver as applicable.
                                    </p>
                                  ) : null}
                                </div>
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  className="gap-1.5"
                                  onClick={() => addSubQuestion(questionIndex)}
                                  disabled={saving}
                                >
                                  <Plus className="h-3.5 w-3.5" />
                                  Driver
                                </Button>
                              </div>
                              <div className="divide-y">
                                {question.sub_questions.map((subQuestion, subQuestionIndex) => (
                                  <div
                                    key={`${subQuestion.id}-${subQuestionIndex}`}
                                    className="grid gap-3 p-3 xl:grid-cols-[110px_minmax(0,1fr)_120px_40px]"
                                  >
                                    <Input
                                      value={subQuestion.id}
                                      onChange={(event) =>
                                        setSubQuestion(questionIndex, subQuestionIndex, {
                                          id: event.target.value,
                                        })
                                      }
                                      disabled={saving}
                                      className="font-mono"
                                      placeholder={`${question.id}.1`}
                                    />
                                    <div className="grid gap-2">
                                      <Input
                                        value={subQuestion.text}
                                        onChange={(event) =>
                                          setSubQuestion(questionIndex, subQuestionIndex, {
                                            text: event.target.value,
                                          })
                                        }
                                        disabled={saving}
                                        placeholder="Driver text"
                                      />
                                      <Input
                                        value={subQuestion.help_text ?? ""}
                                        onChange={(event) =>
                                          setSubQuestion(questionIndex, subQuestionIndex, {
                                            help_text: event.target.value,
                                          })
                                        }
                                        disabled={saving}
                                        placeholder="Optional driver help text"
                                      />
                                    </div>
                                    <label className="flex h-10 items-center gap-2 rounded-md border bg-background px-3 text-sm" title="Used to keep the canonical template valid for the backend.">
                                      <input
                                        type="checkbox"
                                        checked={subQuestion.answer}
                                        onChange={(event) =>
                                          setSubQuestion(questionIndex, subQuestionIndex, {
                                            answer: event.target.checked,
                                          })
                                        }
                                        disabled={saving}
                                      />
                                      Applicable
                                    </label>
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="icon"
                                      className="h-10 w-10"
                                      onClick={() => removeSubQuestion(questionIndex, subQuestionIndex)}
                                      disabled={saving}
                                      aria-label="Remove driver"
                                      title="Remove driver"
                                    >
                                      <Trash2 className="h-4 w-4" />
                                    </Button>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="grid gap-4">
              <div className="grid gap-2">
                <FieldLabel htmlFor="form-description" label="Description" optional />
                <Textarea
                  id="form-description"
                  value={state.description}
                  onChange={(event) =>
                    setState((current) => ({ ...current, description: event.target.value }))
                  }
                  disabled={saving}
                  className="min-h-[92px]"
                  placeholder="Review focus, use case, and catalog notes"
                />
              </div>
              <div className="grid gap-2">
                <FieldLabel
                  htmlFor="audit-scope"
                  label="Audit Scope"
                  optional
                  tooltip="Stored on the catalog definition and injected into the file-review agent prompt."
                />
                <Textarea
                  id="audit-scope"
                  value={state.auditScope}
                  onChange={(event) =>
                    setState((current) => ({ ...current, auditScope: event.target.value }))
                  }
                  disabled={saving}
                  className="min-h-[112px]"
                  placeholder="Claim types, document boundaries, review focus..."
                />
              </div>
              <div className="grid gap-2">
                <FieldLabel
                  htmlFor="tool-instructions"
                  label="Tool Instructions"
                  optional
                  tooltip="Stored with the form and mapped to runtime prompt metadata."
                />
                <Textarea
                  id="tool-instructions"
                  value={state.toolInstructions}
                  onChange={(event) =>
                    setState((current) => ({ ...current, toolInstructions: event.target.value }))
                  }
                  disabled={saving}
                  className="min-h-[112px]"
                  placeholder="Evidence lookup preferences, citation expectations, escalation notes..."
                />
                {runtimeMetadataMissing ? (
                  <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                    <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    Optional runtime metadata can make form-specific prompt behavior more explicit.
                  </p>
                ) : null}
              </div>
            </div>

            <FormPreviewPanel
              state={state}
              open={previewOpen}
              mode={previewMode}
              onOpenChange={setPreviewOpen}
              onModeChange={setPreviewMode}
              onRefreshJson={refreshJson}
            />
          </div>

          {formError ? (
            <div className="mt-5 rounded-lg border border-destructive/35 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {formError}
            </div>
          ) : null}
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t bg-secondary/35 px-6 py-5">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant={duplicateVersion ? "warning" : "outline"}>
              {state.id || "form"}@{state.version || "version"}
            </Badge>
            {runtimeMetadataMissing ? <span>Runtime metadata is optional.</span> : null}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button
              type="button"
              className="min-w-36 gap-2"
              onClick={() => void handleSave()}
              disabled={saving || importing}
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {isEditing ? "Save Version" : "Register Form"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
