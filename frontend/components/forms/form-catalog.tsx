"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Braces,
  BookOpen,
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
  bootstrapPromptFamily,
  createPromptVersion,
  getFormDefinition,
  listFormCatalog,
  listPromptFamilies,
  registerForm,
  setPromptActivation,
} from "@/lib/api";
import type {
  AuditFormDefinition,
  AuditFormResult,
  FormCatalogEntry,
  FormKind,
  FormQuestion,
  FormSubQuestion,
  OverallOutcome,
  PromptFamilyRecord,
} from "@/lib/types";
import { cn } from "@/lib/utils";

type DialogMode = "create" | "edit";
type UsageFilter = "all" | "used" | "unused";
type PreviewMode = "form" | "json" | "string";

const FORM_TOOL_OPTIONS = ["Claim Summary", "Notes", "Documents", "Images"] as const;
const CANONICAL_PLACEHOLDER = "Canonical template placeholder.";

interface FormEditorState {
  id: string;
  version: string;
  title: string;
  formKind: FormKind;
  description: string;
  instructions: string;
  tools: string[];
  knowledgeDocs: string[];
  knowledgeDocDraft: string;
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

const questionSchema = z.object({
  id: z.string().trim().min(1, "Question ID is required."),
  text: z.string().trim().min(1, "Question text is required."),
  answer: z.enum(["Yes", "No"]),
  comments: z.string().nullable().optional(),
  citations: z.string().nullable().optional(),
  sub_questions: z.array(subQuestionSchema).nullable().optional().default([]),
  overwrite_dollars: z.number().nonnegative().nullable().optional(),
  underwrite_dollars: z.number().nonnegative().nullable().optional(),
  help_text: z.string().nullable().optional(),
});

const auditFormSchema = z.object({
  form_kind: z.enum(["standard", "financial"]).default("standard"),
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
  total_amount_reviewed_dollars: z.number().positive().nullable().optional(),
  questions: z.array(questionSchema).min(1, "Add at least one question."),
  overall_outcome: z.enum(["Meets", "Does Not Meet"]),
  outcome_justification: z.string().trim().min(1, "Outcome justification is required."),
});

const emptySubQuestion = (questionId: string, index: number): FormSubQuestion => ({
  id: `${questionId}.${index}`,
  text: "",
  reasoning: CANONICAL_PLACEHOLDER,
  citations: CANONICAL_PLACEHOLDER,
  answer: true,
  help_text: "",
});

const emptyQuestion = (index: number, formKind: FormKind = "standard"): FormQuestion => {
  const id = formKind === "financial" ? `FQ${index}` : `Q${index}`;
  return {
    id,
    text: "",
    answer: "No",
    comments: CANONICAL_PLACEHOLDER,
    citations: CANONICAL_PLACEHOLDER,
    help_text: "",
    sub_questions: formKind === "financial" ? null : [emptySubQuestion(id, 1)],
    overwrite_dollars: formKind === "financial" ? 0 : undefined,
    underwrite_dollars: formKind === "financial" ? 0 : undefined,
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

function normalizeList(values: string[]): string[] | null {
  const unique = Array.from(
    new Set(values.map((value) => value.trim()).filter(Boolean)),
  );
  return unique.length ? unique : null;
}

function buildCanonical(state: FormEditorState): AuditFormResult {
  const formId = state.id.trim();
  const version = state.version.trim();
  const title = state.title.trim() || titleFromId(formId);
  const description = state.description.trim() || "Canonical audit form template.";
  const questions = state.questions.map((question) => {
    const subQuestions = state.formKind === "financial" ? [] : (question.sub_questions ?? []).map((subQuestion) => ({
      ...subQuestion,
      id: subQuestion.id.trim(),
      text: subQuestion.text.trim(),
      reasoning: (subQuestion.reasoning || CANONICAL_PLACEHOLDER).trim(),
      citations: (subQuestion.citations || CANONICAL_PLACEHOLDER).trim(),
      help_text: normalizeOptionalText(subQuestion.help_text),
      answer: true,
    }));
    const hasSubQuestions = subQuestions.length > 0;
    return {
      ...question,
      id: question.id.trim(),
      text: question.text.trim(),
      comments: hasSubQuestions
        ? normalizeOptionalText(question.comments)
        : normalizeOptionalText(question.comments) || CANONICAL_PLACEHOLDER,
      citations: hasSubQuestions
        ? normalizeOptionalText(question.citations)
        : normalizeOptionalText(question.citations) || CANONICAL_PLACEHOLDER,
      help_text: normalizeOptionalText(question.help_text),
      answer: question.answer,
      sub_questions: state.formKind === "financial" ? null : subQuestions.length ? subQuestions : undefined,
      overwrite_dollars: state.formKind === "financial" ? Number(question.overwrite_dollars ?? 0) : undefined,
      underwrite_dollars: state.formKind === "financial" ? Number(question.underwrite_dollars ?? 0) : undefined,
    };
  });
  return {
    form_kind: state.formKind,
    form_id: formId,
    form_version: version,
    title,
    description,
    total_amount_reviewed_dollars: state.formKind === "financial" ? 1 : undefined,
    questions,
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
    form_kind: canonical.form_kind ?? state.formKind,
    description: canonical.description,
    instructions: normalizeOptionalText(state.instructions),
    tools: normalizeList(state.tools),
    knowledge_docs: normalizeList(state.knowledgeDocs),
    canonical,
  };
}

function asQuestionnaireString(form: AuditFormResult): string {
  if (form.form_kind === "financial") {
    const lines = [
      `TFR Questionnaire: ${form.title}`,
      "Form Kind: financial",
      "Complete each question from the file evidence. Answers must be exactly 'Yes' or 'No'. Include total_amount_reviewed_dollars for the full reviewed amount. For each question, include overwrite_dollars and underwrite_dollars when a financial exception applies; use 0 when none apply.",
    ];
    for (const question of form.questions) {
      const helpText = question.help_text ? ` (help_text: ${question.help_text})` : "";
      lines.push("", `${question.id}: ${question.text}${helpText}`);
    }
    lines.push("", "Overall Outcome: Options: Meets, Does Not Meet");
    return lines.join("\n");
  }
  const lines = [
    `TFR Questionnaire: ${form.title}`,
    "Complete each question from the file evidence. Answers must be exactly 'Yes' or 'No'. When a question lists Sub-Questions, generate only the listed sub_question driver(s) that apply to the audit finding; do not generate non-applicable drivers. Do not include an answer field on sub_questions; including a sub_question means it applies. For a No answer with listed Sub-Questions, include at least one applicable sub_question with reasoning and citations. For a Yes answer with listed Sub-Questions, omit sub_questions or set it to null/[]. Keep question-level comments/citations null unless extra general context is needed. When a question does not list Sub-Questions, omit sub_questions or set it to null/[], and put the question-level reasoning in comments and the supporting evidence references in citations.",
  ];

  for (const question of form.questions) {
    const helpText = question.help_text ? ` (help_text: ${question.help_text})` : "";
    const subQuestions = question.sub_questions ?? [];
    lines.push("", `${question.id}: ${question.text}${helpText}`);
    if (subQuestions.length) {
      lines.push("Sub-Questions:");
      for (const subQuestion of subQuestions) {
        const subHelpText = subQuestion.help_text ? ` (help_text: ${subQuestion.help_text})` : "";
        lines.push(`  ${subQuestion.id}: ${subQuestion.text}${subHelpText}`);
      }
    } else {
      lines.push("No Sub-Questions: put reasoning in question.comments and evidence in question.citations.");
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
  const formKind = definition?.form_kind ?? canonical?.form_kind ?? "standard";
  const questions = canonical?.questions?.length
      ? canonical.questions.map((question) => ({
        ...question,
        comments: question.comments ?? CANONICAL_PLACEHOLDER,
        citations: question.citations ?? CANONICAL_PLACEHOLDER,
        help_text: question.help_text ?? "",
        overwrite_dollars: question.overwrite_dollars ?? 0,
        underwrite_dollars: question.underwrite_dollars ?? 0,
        sub_questions: formKind === "financial" ? null : (question.sub_questions ?? []).map((subQuestion) => ({
          ...subQuestion,
          reasoning: subQuestion.reasoning || CANONICAL_PLACEHOLDER,
          citations: subQuestion.citations || CANONICAL_PLACEHOLDER,
          answer: true,
          help_text: subQuestion.help_text ?? "",
        })),
      }))
    : [emptyQuestion(1, formKind)];

  const state: FormEditorState = {
    id: baseId,
    version,
    title,
    formKind,
    description,
    instructions: definition?.instructions ?? "",
    tools: definition?.tools ?? [],
    knowledgeDocs: definition?.knowledge_docs ?? [],
    knowledgeDocDraft: "",
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

async function readFirstColumnValues(file: File): Promise<string[]> {
  const XLSX = await import("xlsx");
  const workbook = XLSX.read(await file.arrayBuffer(), { type: "array", raw: false });
  const firstSheet = workbook.SheetNames[0];
  if (!firstSheet) return [];
  const rows = XLSX.utils.sheet_to_json<unknown[]>(workbook.Sheets[firstSheet], {
    header: 1,
    blankrows: false,
  });
  return rows
    .map((row) => (Array.isArray(row) ? String(row[0] ?? "").trim() : ""))
    .filter(Boolean);
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
        <Badge variant="outline">{form.formKind}</Badge>
        <Badge variant="outline">{form.questionCount} questions</Badge>
        {form.formKind === "standard" ? (
          <Badge variant="outline">{form.subQuestionCount} sub-questions</Badge>
        ) : null}
        <Badge variant="outline">{form.completedCount} completed</Badge>
        {!compact ? <Badge variant="outline">Created {formatDate(form.createdAt)}</Badge> : null}
      </div>
    </button>
  );
}

function QuestionPreview({ question }: { question: FormQuestion }) {
  const [expanded, setExpanded] = useState(true);
  const subQuestions = question.sub_questions ?? [];
  const hasDrivers = subQuestions.length > 0;

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
          {subQuestions.map((subQuestion) => (
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

function PromptRegistryPanel({
  families,
  loading,
  saving,
  promptError,
  formId,
  formVersion,
  registeredInstructions,
  onRefresh,
  onInitialize,
  onRegisterPrompt,
  onSetActive,
}: {
  families: PromptFamilyRecord[];
  loading: boolean;
  saving: boolean;
  promptError: string;
  formId: string;
  formVersion: string;
  registeredInstructions: string;
  onRefresh: () => void;
  onInitialize: () => Promise<void>;
  onRegisterPrompt: (familyId: string | null, text: string, commitMessage: string) => Promise<void>;
  onSetActive: (familyId: string, versionId: string) => Promise<void>;
}) {
  const family = families[0] ?? null;
  const versions = useMemo(() => family?.versions ?? [], [family?.versions]);
  const [leftVersionId, setLeftVersionId] = useState("");
  const [rightVersionId, setRightVersionId] = useState("");
  const [registerOpen, setRegisterOpen] = useState(false);
  const [newPromptText, setNewPromptText] = useState("");
  const [newPromptMessage, setNewPromptMessage] = useState("");

  useEffect(() => {
    if (!versions.length) {
      setLeftVersionId("");
      setRightVersionId("");
      return;
    }
    setLeftVersionId((current) => current || versions[Math.min(1, versions.length - 1)]?.id || versions[0].id);
    setRightVersionId((current) => current || versions[0].id);
  }, [versions]);

  const leftVersion = versions.find((version) => version.id === leftVersionId) ?? versions[Math.min(1, versions.length - 1)];
  const rightVersion = versions.find((version) => version.id === rightVersionId) ?? versions[0];
  const activeForVersion = useMemo(
    () => family?.activations.find((activation) => activation.scope === "form_version" && activation.form_version === formVersion) ?? null,
    [family?.activations, formVersion],
  );
  const activeDefault = useMemo(
    () => family?.activations.find((activation) => activation.scope === "form_default") ?? null,
    [family?.activations],
  );
  const activeVersionId = activeForVersion?.version_id ?? activeDefault?.version_id ?? "";
  const diffLines = leftVersion && rightVersion ? buildLineDiff(leftVersion.text, rightVersion.text) : [];
  const submitManualPrompt = async () => {
    if (!newPromptText.trim()) return;
    await onRegisterPrompt(family?.id ?? null, newPromptText, newPromptMessage);
    setNewPromptText("");
    setNewPromptMessage("");
    setRegisterOpen(false);
  };

  return (
    <div className="rounded-lg border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold">Prompt Registry</h3>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Register instruction prompt versions here, then mark the active prompt for this form version.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={onRefresh} disabled={loading}>
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Refresh
          </Button>
          <Button
            type="button"
            size="sm"
            className="gap-1.5"
            onClick={() => {
              setRegisterOpen((current) => !current);
              setNewPromptText((current) => current || registeredInstructions || "");
            }}
          >
            <Plus className="h-3.5 w-3.5" />
            Register Prompt
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 px-4 py-8 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading prompts
        </div>
      ) : !family ? (
        <div className="grid gap-4 p-4">
          {promptError ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {promptError}
            </div>
          ) : null}
          {registerOpen ? (
            <div className="rounded-md border bg-secondary/20 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold">Register Manual Prompt</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    This creates the prompt registry for the form and saves a new immutable prompt version.
                  </p>
                </div>
                <Button type="button" variant="ghost" size="sm" onClick={() => setRegisterOpen(false)}>
                  <X className="h-3.5 w-3.5" />
                  Close
                </Button>
              </div>
              <Textarea
                value={newPromptText}
                onChange={(event) => setNewPromptText(event.target.value)}
                className="mt-3 min-h-44 font-mono text-xs"
                placeholder="Instruction prompt text"
              />
              <Input
                value={newPromptMessage}
                onChange={(event) => setNewPromptMessage(event.target.value)}
                className="mt-2"
                placeholder="Change note, e.g. First handcrafted review prompt"
              />
              <div className="mt-3 flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => setRegisterOpen(false)}>Cancel</Button>
                <Button type="button" disabled={saving || !newPromptText.trim()} onClick={() => void submitManualPrompt()}>
                  {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                  Register
                </Button>
              </div>
            </div>
          ) : null}
          <div className="rounded-md border bg-card p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold">Registered Instructions</p>
                  <Badge variant="outline" className="font-mono text-[10px]">
                    {formId}@{formVersion}
                  </Badge>
                  <Badge variant="secondary">not yet persisted</Badge>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Initialize the registry from the instructions stored on this registered form.
                </p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <CopyButton text={registeredInstructions} label="Copy" />
                <Button
                  type="button"
                  size="sm"
                  className="gap-1.5"
                  disabled={saving || !registeredInstructions.trim()}
                  onClick={() => void onInitialize()}
                >
                  {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                  Initialize
                </Button>
              </div>
            </div>
            <p className="mt-3 max-h-48 overflow-y-auto whitespace-pre-wrap rounded-md border bg-secondary/20 p-3 text-sm leading-relaxed">
              {registeredInstructions || "This form does not define custom instructions."}
            </p>
          </div>
        </div>
      ) : (
        <div className="grid gap-4 p-4">
          {registerOpen ? (
            <div className="rounded-md border bg-secondary/20 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold">Register Manual Prompt</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    This creates a prompt version only. Activation stays explicit.
                  </p>
                </div>
                <Button type="button" variant="ghost" size="sm" onClick={() => setRegisterOpen(false)}>
                  <X className="h-3.5 w-3.5" />
                  Close
                </Button>
              </div>
              <Textarea
                value={newPromptText}
                onChange={(event) => setNewPromptText(event.target.value)}
                className="mt-3 min-h-44 font-mono text-xs"
                placeholder="Instruction prompt text"
              />
              <Input
                value={newPromptMessage}
                onChange={(event) => setNewPromptMessage(event.target.value)}
                className="mt-2"
                placeholder="Change note, e.g. Tightened citation rules"
              />
              <div className="mt-3 flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => setRegisterOpen(false)}>Cancel</Button>
                <Button type="button" disabled={saving || !newPromptText.trim()} onClick={() => void submitManualPrompt()}>
                  {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                  Register
                </Button>
              </div>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2 text-xs">
            <Badge variant="outline">{versions.length} versions</Badge>
            <Badge variant={activeVersionId ? "success" : "secondary"}>
              active {activeForVersion ? `${formVersion} -> v${activeForVersion.version_number ?? "?"}` : activeDefault ? `default -> v${activeDefault.version_number ?? "?"}` : "not set"}
            </Badge>
            {family.external_registry_uri ? <Badge variant="outline">{family.external_registry_uri}</Badge> : null}
          </div>

          <div className="grid gap-3">
            {versions.map((version) => {
              const applies =
                version.applicable_form_versions.length === 0 ||
                version.applicable_form_versions.includes(formVersion);
              const active = activeVersionId === version.id;
              return (
                <div key={version.id} className={cn("rounded-md border bg-card p-3", active && "border-emerald-400 bg-emerald-500/5")}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-semibold">v{version.version_number}</p>
                        {active ? <Badge variant="success">active</Badge> : null}
                        <Badge variant={version.source_kind === "gepa_candidate" ? "warning" : "outline"}>
                          {version.source_kind.replaceAll("_", " ")}
                        </Badge>
                        <Badge variant={applies ? "success" : "secondary"}>
                          {applies ? "applies here" : "other version"}
                        </Badge>
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                        {version.commit_message || "No commit message"}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                        <span className="font-mono">{version.text_hash.slice(0, 12)}</span>
                        {typeof version.metrics?.score === "number" ? <span>score {version.metrics.score.toFixed(4)}</span> : null}
                        {version.source_run_id ? <span>GEPA run {version.source_run_id.slice(0, 8)}</span> : null}
                      </div>
                    </div>
                    <div className="flex flex-wrap justify-end gap-1.5">
                      <Button
                        type="button"
                        variant={active ? "default" : "outline"}
                        size="sm"
                        className="h-8 px-2 text-xs"
                        disabled={saving || active}
                        onClick={() => void onSetActive(family.id, version.id)}
                      >
                        {active ? "Active" : "Set Active"}
                      </Button>
                      <CopyButton text={version.text} label="Copy" />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {versions.length > 1 ? (
            <div className="rounded-md border bg-secondary/20">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b px-3 py-2">
                <p className="text-sm font-semibold">Prompt Diff</p>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={leftVersion?.id ?? ""}
                    onChange={(event) => setLeftVersionId(event.target.value)}
                    className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                  >
                    {versions.map((version) => (
                      <option key={version.id} value={version.id}>Base v{version.version_number}</option>
                    ))}
                  </select>
                  <select
                    value={rightVersion?.id ?? ""}
                    onChange={(event) => setRightVersionId(event.target.value)}
                    className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                  >
                    {versions.map((version) => (
                      <option key={version.id} value={version.id}>Compare v{version.version_number}</option>
                    ))}
                  </select>
                </div>
              </div>
              <DiffBlock lines={diffLines} />
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function DiffBlock({ lines }: { lines: Array<{ kind: "same" | "add" | "remove"; text: string }> }) {
  return (
    <pre className="chat-scrollbar max-h-[520px] overflow-auto bg-slate-950 p-3 text-xs leading-relaxed text-slate-200">
      {lines.map((line, index) => {
        const prefix = line.kind === "add" ? "+" : line.kind === "remove" ? "-" : " ";
        const className =
          line.kind === "add"
            ? "block bg-emerald-500/15 text-emerald-100"
            : line.kind === "remove"
              ? "block bg-rose-500/15 text-rose-100"
              : "block text-slate-300";
        return (
          <span key={`${line.kind}-${index}`} className={className}>
            {prefix} {line.text || " "}
          </span>
        );
      })}
    </pre>
  );
}

function buildLineDiff(
  before: string,
  after: string,
): Array<{ kind: "same" | "add" | "remove"; text: string }> {
  const beforeLines = before.split(/\r?\n/);
  const afterLines = after.split(/\r?\n/);
  const table = Array.from({ length: beforeLines.length + 1 }, () =>
    Array<number>(afterLines.length + 1).fill(0),
  );

  for (let i = beforeLines.length - 1; i >= 0; i -= 1) {
    for (let j = afterLines.length - 1; j >= 0; j -= 1) {
      table[i][j] =
        beforeLines[i] === afterLines[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }

  const output: Array<{ kind: "same" | "add" | "remove"; text: string }> = [];
  let i = 0;
  let j = 0;
  while (i < beforeLines.length && j < afterLines.length) {
    if (beforeLines[i] === afterLines[j]) {
      output.push({ kind: "same", text: beforeLines[i] });
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      output.push({ kind: "remove", text: beforeLines[i] });
      i += 1;
    } else {
      output.push({ kind: "add", text: afterLines[j] });
      j += 1;
    }
  }
  while (i < beforeLines.length) {
    output.push({ kind: "remove", text: beforeLines[i] });
    i += 1;
  }
  while (j < afterLines.length) {
    output.push({ kind: "add", text: afterLines[j] });
    j += 1;
  }
  return output;
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
  const [promptFamilies, setPromptFamilies] = useState<PromptFamilyRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [definitionLoading, setDefinitionLoading] = useState(false);
  const [promptLoading, setPromptLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [promptError, setPromptError] = useState("");
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

  const refreshPrompts = useCallback(async (definition: AuditFormDefinition | null) => {
    if (!definition) {
      setPromptFamilies([]);
      setPromptError("");
      return;
    }
    setPromptLoading(true);
    setPromptError("");
    try {
      setPromptFamilies(await listPromptFamilies(definition.id, definition.version));
    } catch (err) {
      setPromptFamilies([]);
      setPromptError(err instanceof Error ? err.message : "Failed to load prompt registry.");
    } finally {
      setPromptLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshPrompts(selectedDefinition);
  }, [refreshPrompts, selectedDefinition]);

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
          form.instructions,
          form.tools.join(" "),
          form.knowledgeDocs.join(" "),
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

  const registerPromptVersion = async (
    familyId: string | null,
    text: string,
    commitMessage: string,
  ) => {
    setSaving(true);
    setError("");
    try {
      await createPromptVersion({
        family_id: familyId,
        form_id: selectedDefinition?.id ?? "",
        form_version: selectedDefinition?.version ?? "",
        text,
        source_kind: "manual_edit",
        commit_message: commitMessage || "Registered manual prompt.",
        applicable_form_versions: selectedDefinition ? [selectedDefinition.version] : [],
      });
      await refreshPrompts(selectedDefinition);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to register prompt.");
    } finally {
      setSaving(false);
    }
  };

  const setActivePrompt = async (familyId: string, versionId: string) => {
    if (!selectedDefinition) return;
    setSaving(true);
    setError("");
    try {
      await setPromptActivation({
        family_id: familyId,
        version_id: versionId,
        form_version: selectedDefinition.version,
        scope: "form_version",
        notes: `Activated for ${selectedDefinition.id}@${selectedDefinition.version}.`,
      });
      await refreshPrompts(selectedDefinition);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to activate prompt.");
    } finally {
      setSaving(false);
    }
  };

  const initializePromptRegistry = async () => {
    if (!selectedDefinition) return;
    setSaving(true);
    setPromptError("");
    try {
      await bootstrapPromptFamily(selectedDefinition.id, selectedDefinition.version);
      await refreshPrompts(selectedDefinition);
    } catch (err) {
      setPromptError(err instanceof Error ? err.message : "Failed to initialize prompt registry.");
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
                  placeholder="Search title, ID, instructions, tools, docs..."
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
                    <Badge variant="outline">{selectedDefinition.form_kind ?? "standard"}</Badge>
                  </div>
                  <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                    {selectedDefinition.description || "No description"}
                  </p>
                </div>

                <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-4">
                  <MetadataPill label="Questions" value={selectedForm.questionCount} />
                  {selectedForm.formKind === "standard" ? (
                    <MetadataPill label="Sub-Questions" value={selectedForm.subQuestionCount} />
                  ) : null}
                  <MetadataPill label="Reviews" value={selectedForm.reviewCount} />
                  <MetadataPill label="Completed" value={selectedForm.completedCount} />
                  <MetadataPill label="Failed" value={selectedForm.failedCount} />
                  <MetadataPill label="Created" value={formatDate(selectedForm.createdAt)} />
                  <MetadataPill label="Last Review" value={formatDate(selectedForm.lastReviewedAt)} />
                </div>

                {selectedDefinition.instructions ||
                selectedDefinition.tools?.length ||
                selectedDefinition.knowledge_docs?.length ? (
                  <div className="grid gap-3 lg:grid-cols-3">
                    {selectedDefinition.instructions ? (
                      <div className="rounded-lg border bg-background p-4">
                        <p className="text-[11px] font-semibold uppercase text-muted-foreground">Instructions</p>
                        <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{selectedDefinition.instructions}</p>
                      </div>
                    ) : null}
                    {selectedDefinition.tools?.length ? (
                      <div className="rounded-lg border bg-background p-4">
                        <p className="text-[11px] font-semibold uppercase text-muted-foreground">Tools</p>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {selectedDefinition.tools.map((tool) => (
                            <Badge key={tool} variant="outline">{tool}</Badge>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {selectedDefinition.knowledge_docs?.length ? (
                      <div className="rounded-lg border bg-background p-4">
                        <p className="text-[11px] font-semibold uppercase text-muted-foreground">Knowledge Docs</p>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {selectedDefinition.knowledge_docs.map((doc) => (
                            <Badge key={doc} variant="secondary">{doc}</Badge>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="flex justify-end">
                    <Badge
                      variant="outline"
                      className="gap-1 text-[10px] text-muted-foreground"
                      title="No instructions, tools, or knowledge documents are stored for this form."
                    >
                      <Info className="h-3 w-3" />
                      No prompt metadata
                    </Badge>
                  </div>
                )}

                <PromptRegistryPanel
                  families={promptFamilies}
                  loading={promptLoading}
                  saving={saving}
                  promptError={promptError}
                  formId={selectedDefinition.id}
                  formVersion={selectedDefinition.version}
                  registeredInstructions={selectedDefinition.instructions ?? ""}
                  onRefresh={() => void refreshPrompts(selectedDefinition)}
                  onInitialize={initializePromptRegistry}
                  onRegisterPrompt={registerPromptVersion}
                  onSetActive={setActivePrompt}
                />

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
  const [uploadedKnowledgeDocName, setUploadedKnowledgeDocName] = useState("");

  const isEditing = mode === "edit";
  const duplicateVersion = forms.some(
    (form) => form.id === state.id.trim() && form.version === state.version.trim(),
  );
  const runtimeMetadataMissing =
    !state.instructions.trim() && state.tools.length === 0 && state.knowledgeDocs.length === 0;

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
    setUploadedKnowledgeDocName("");
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
      questions: [...current.questions, emptyQuestion(current.questions.length + 1, current.formKind)],
    }));
    setExpandedQuestions((current) => new Set([...current, state.questions.length]));
  };

  const removeQuestion = (index: number) => {
    setState((current) => ({
      ...current,
      questions:
        current.questions.length === 1
          ? [emptyQuestion(1, current.formKind)]
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
              sub_questions: (question.sub_questions ?? []).map((subQuestion, currentSubIndex) =>
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
    if (state.formKind === "financial") return;
    setState((current) => ({
      ...current,
      questions: current.questions.map((question, index) =>
        index === questionIndex
          ? {
              ...question,
              sub_questions: [
                ...(question.sub_questions ?? []),
                emptySubQuestion(
                  question.id || `Q${questionIndex + 1}`,
                  (question.sub_questions ?? []).length + 1,
                ),
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
              sub_questions: (question.sub_questions ?? []).filter((_, subIndex) => subIndex !== subQuestionIndex),
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

  const refreshJson = () => {
    setState((current) => ({
      ...current,
      jsonText: JSON.stringify(buildCanonical(current), null, 2),
    }));
  };

  const toggleTool = (tool: string) => {
    setState((current) => ({
      ...current,
      tools: current.tools.includes(tool)
        ? current.tools.filter((item) => item !== tool)
        : [...current.tools, tool],
    }));
  };

  const addKnowledgeDoc = () => {
    const value = state.knowledgeDocDraft.trim();
    if (!value) return;
    setState((current) => ({
      ...current,
      knowledgeDocs: normalizeList([...current.knowledgeDocs, value]) ?? [],
      knowledgeDocDraft: "",
    }));
  };

  const removeKnowledgeDoc = (doc: string) => {
    setState((current) => ({
      ...current,
      knowledgeDocs: current.knowledgeDocs.filter((item) => item !== doc),
    }));
  };

  const importKnowledgeDocs = async (file: File) => {
    setFormError("");
    setUploadedKnowledgeDocName(file.name);
    try {
      const docs = await readFirstColumnValues(file);
      if (!docs.length) {
        setFormError("No knowledge document names or IDs were found in the first column.");
        return;
      }
      setState((current) => ({
        ...current,
        knowledgeDocs: normalizeList([...current.knowledgeDocs, ...docs]) ?? [],
      }));
      setImportMessage(`Added ${docs.length} knowledge doc item${docs.length === 1 ? "" : "s"}.`);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to import knowledge docs.");
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
                    htmlFor="form-kind-standard"
                    label="Form Kind"
                    tooltip="Financial forms are flat Yes/No questions with overwrite and underwrite dollars."
                  />
                  <div className="grid grid-cols-2 gap-2">
                    {(["standard", "financial"] as const).map((kind) => (
                      <Button
                        key={kind}
                        id={`form-kind-${kind}`}
                        type="button"
                        variant={state.formKind === kind ? "default" : "outline"}
                        disabled={saving || isEditing}
                        onClick={() => {
                          setState((current) => ({
                            ...current,
                            formKind: kind,
                            questions: current.questions.map((question, index) => ({
                              ...question,
                              id:
                                kind === "financial"
                                  ? question.id.replace(/^Q/, "FQ")
                                  : question.id.replace(/^FQ/, "Q"),
                              sub_questions:
                                kind === "financial"
                                  ? null
                                  : question.sub_questions?.length
                                    ? question.sub_questions
                                    : [emptySubQuestion(question.id || `Q${index + 1}`, 1)],
                              overwrite_dollars: kind === "financial" ? question.overwrite_dollars ?? 0 : undefined,
                              underwrite_dollars: kind === "financial" ? question.underwrite_dollars ?? 0 : undefined,
                            })),
                          }));
                        }}
                      >
                        {kind === "standard" ? "Standard" : "Financial"}
                      </Button>
                    ))}
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

            <div className="rounded-lg border bg-background p-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(280px,0.7fr)]">
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
                      className="min-h-[64px]"
                      placeholder="Review focus, use case, and catalog notes"
                    />
                  </div>
                  <div className="grid gap-2">
                    <FieldLabel
                      htmlFor="form-instructions"
                      label="Instructions"
                      optional
                      tooltip="Stored on the catalog definition and injected into the file-review agent prompt."
                    />
                    <Textarea
                      id="form-instructions"
                      value={state.instructions}
                      onChange={(event) =>
                        setState((current) => ({ ...current, instructions: event.target.value }))
                      }
                      disabled={saving}
                      className="min-h-[220px]"
                      placeholder="Form-specific review focus, evidence boundaries, citation expectations..."
                    />
                  </div>
                </div>

                <div className="grid gap-4">
                  <div className="grid gap-2">
                    <FieldLabel htmlFor="tools-selector" label="Tools" optional />
                    <details className="group relative">
                      <summary
                        id="tools-selector"
                        className="flex h-10 cursor-pointer list-none items-center justify-between rounded-md border border-input bg-background px-3 text-sm"
                      >
                        <span className="truncate">
                          {state.tools.length
                            ? `${state.tools.length} selected`
                            : "No tools selected"}
                        </span>
                        <ChevronDown className="h-4 w-4 text-muted-foreground group-open:rotate-180" />
                      </summary>
                      <div className="absolute z-50 mt-2 w-full rounded-md border bg-card p-2 shadow-xl ring-1 ring-border">
                        <div className="mb-2 flex gap-2">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-8 flex-1"
                            onClick={() =>
                              setState((current) => ({ ...current, tools: [...FORM_TOOL_OPTIONS] }))
                            }
                            disabled={saving}
                          >
                            All
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-8 flex-1"
                            onClick={() => setState((current) => ({ ...current, tools: [] }))}
                            disabled={saving}
                          >
                            None
                          </Button>
                        </div>
                        <div className="grid gap-1">
                          {FORM_TOOL_OPTIONS.map((tool) => (
                            <label
                              key={tool}
                              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-secondary"
                            >
                              <input
                                type="checkbox"
                                checked={state.tools.includes(tool)}
                                onChange={() => toggleTool(tool)}
                                disabled={saving}
                              />
                              {tool}
                            </label>
                          ))}
                        </div>
                      </div>
                    </details>
                    <div className="flex min-h-8 flex-wrap gap-1.5">
                      {state.tools.length ? (
                        state.tools.map((tool) => (
                          <Badge key={tool} variant="outline" className="gap-1">
                            <span className="max-w-[220px] truncate">{tool}</span>
                            <button
                              type="button"
                              onClick={() => toggleTool(tool)}
                              disabled={saving}
                              aria-label={`Remove ${tool}`}
                              title={`Remove ${tool}`}
                            >
                              <X className="h-3 w-3" />
                            </button>
                          </Badge>
                        ))
                      ) : (
                        <span className="text-xs text-muted-foreground">No tools selected.</span>
                      )}
                    </div>
                  </div>

                  <div className="grid gap-2">
                    <FieldLabel
                      htmlFor="knowledge-doc"
                      label="Knowledge Docs"
                      optional
                      tooltip="Names or IDs added to the agent context for this form."
                    />
                    <div className="flex gap-2">
                      <Input
                        id="knowledge-doc"
                        value={state.knowledgeDocDraft}
                        onChange={(event) =>
                          setState((current) => ({
                            ...current,
                            knowledgeDocDraft: event.target.value,
                          }))
                        }
                        onKeyDown={(event) => {
                          if (event.key !== "Enter") return;
                          event.preventDefault();
                          addKnowledgeDoc();
                        }}
                        disabled={saving}
                        placeholder="Document name or ID"
                      />
                      <Button type="button" variant="outline" onClick={addKnowledgeDoc} disabled={saving}>
                        Add
                      </Button>
                    </div>
                    <input
                      id="knowledge-doc-upload"
                      type="file"
                      accept=".xlsb,.xlsx,.xls,.csv"
                      disabled={saving}
                      className="sr-only"
                      onChange={(event) => {
                        const file = event.currentTarget.files?.[0];
                        if (file) void importKnowledgeDocs(file);
                        event.currentTarget.value = "";
                      }}
                    />
                    <div className="flex min-w-0 items-center gap-2">
                      <label
                        htmlFor="knowledge-doc-upload"
                        className={cn(
                          "inline-flex h-9 cursor-pointer items-center justify-center gap-2 rounded-md border border-input bg-background px-3 text-sm font-medium transition-colors hover:bg-secondary",
                          saving && "pointer-events-none opacity-50",
                        )}
                      >
                        <Upload className="h-3.5 w-3.5" />
                        Import
                      </label>
                      <span className="truncate text-xs text-muted-foreground">
                        {uploadedKnowledgeDocName || "Excel or CSV first column"}
                      </span>
                    </div>
                    <div className="flex min-h-8 flex-wrap gap-1.5">
                      {state.knowledgeDocs.length ? (
                        state.knowledgeDocs.map((doc) => (
                          <Badge key={doc} variant="secondary" className="gap-1">
                            <span className="max-w-[220px] truncate">{doc}</span>
                            <button
                              type="button"
                              onClick={() => removeKnowledgeDoc(doc)}
                              disabled={saving}
                              aria-label={`Remove ${doc}`}
                              title={`Remove ${doc}`}
                            >
                              <X className="h-3 w-3" />
                            </button>
                          </Badge>
                        ))
                      ) : (
                        <span className="text-xs text-muted-foreground">No knowledge docs added.</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-lg border bg-background">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-secondary/35 px-4 py-3">
                <div>
                  <h3 className="text-sm font-semibold">Audit Form Questions</h3>
                  <p className="text-xs text-muted-foreground">
                    Add the canonical question text and optional help text the agent should see.
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
                  const subQuestions = question.sub_questions ?? [];
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
                        <div className="grid min-w-0 flex-1 gap-3 md:grid-cols-[110px_minmax(0,1fr)_40px]">
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

                          <div className="rounded-lg border bg-card">
                            <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
                              <div>
                                <p className="text-sm font-medium">
                                  {state.formKind === "financial" ? "Financial Exceptions" : "Drivers"}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                  {state.formKind === "financial"
                                    ? "The completed audit captures OW and UW dollars for this question."
                                    : "Optional driver text and help text."}
                                </p>
                              </div>
                              {state.formKind === "standard" ? (
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
                              ) : null}
                            </div>
                            {state.formKind === "standard" ? (
                              <div className="divide-y">
                                {subQuestions.map((subQuestion, subQuestionIndex) => (
                                <div
                                  key={`${subQuestion.id}-${subQuestionIndex}`}
                                  className="grid gap-3 p-3 xl:grid-cols-[110px_minmax(0,1fr)_40px]"
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
                            ) : null}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  );
                })}
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
              disabled={saving}
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
