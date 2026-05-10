import type { AuditFormResult, FormQuestion, FormSubQuestion, OverallOutcome, ReviewRecord } from "@/lib/types";

export type ResultVersionKind = "current" | "original";
export type TrendGranularity = "day" | "week" | "month";
export type TrendCompareBy = "none" | "form_id" | "form_version" | "source" | "result_version";
export type TrendMetric = "review_volume" | "meets_rate" | "does_not_meet_rate" | "question_no_rate" | "driver_review_rate";

export interface DashboardFilters {
  search: string;
  formId: string;
  formVersion: string;
  source: string;
  outcome: string;
  dateFrom: string;
  dateTo: string;
  resultVersion: ResultVersionKind;
}

export interface DashboardReviewRow {
  reviewId: string;
  batchId: string;
  status: string;
  source: string;
  claimNumber: string;
  runName: string;
  effectiveDate: string;
  synthetic: boolean;
  inputJson: Record<string, unknown> | null;
  batchDescription: string;
  batchTemplateId: string;
  sourceFileIds: string;
  formId: string;
  formVersion: string;
  formKey: string;
  title: string;
  description: string;
  outcome: OverallOutcome;
  outcomeJustification: string;
  questionCount: number;
  yesCount: number;
  noCount: number;
  subQuestionCount: number;
  driverCount: number;
  createdAt: string;
  updatedAt: string;
  resultVersion: ResultVersionKind;
  edited: boolean;
  form: AuditFormResult;
  originalForm: AuditFormResult | null;
  currentForm: AuditFormResult | null;
}

export interface DashboardFilterOptions {
  formIds: string[];
  formVersions: string[];
  sources: string[];
}

export interface AggregatedSubQuestionRow {
  key: string;
  id: string;
  parentId: string;
  text: string;
  driverCount: number;
  totalAppearances: number;
  driverPercent: number;
  questionTotalCount: number;
  questionNoCount: number;
}

export interface AggregatedQuestionRow {
  key: string;
  formId: string;
  formVersion: string;
  formKey: string;
  id: string;
  text: string;
  yesCount: number;
  noCount: number;
  totalCount: number;
  driverCount: number;
  editCount: number;
  yesPercent: number;
  noPercent: number;
  driverPercent: number;
  subQuestions: AggregatedSubQuestionRow[];
}

export type CommentReportType = "Outcome justification" | "Sub-question reasoning";

export interface CommentReportRow {
  id: string;
  reviewId: string;
  createdAt: string;
  updatedAt: string;
  claimNumber: string;
  runName: string;
  source: string;
  formId: string;
  formVersion: string;
  title: string;
  outcome: OverallOutcome;
  resultVersion: ResultVersionKind;
  commentType: CommentReportType;
  questionId: string;
  questionText: string;
  answer: string;
  subQuestionId: string;
  subQuestionText: string;
  applicable: boolean | null;
  comment: string;
  citations: string;
  row: DashboardReviewRow;
}

export interface CommentQuestionFilter {
  questionKeys: Set<string>;
  subQuestionKeys: Set<string>;
}

export const defaultDashboardFilters: DashboardFilters = {
  search: "",
  formId: "all",
  formVersion: "all",
  source: "all",
  outcome: "all",
  dateFrom: "",
  dateTo: "",
  resultVersion: "current",
};

export const resultVersionLabels: Record<ResultVersionKind, string> = {
  current: "Current user version",
  original: "Original agent version",
};

export const trendMetricLabels: Record<TrendMetric, string> = {
  review_volume: "Review volume",
  meets_rate: "Meets %",
  does_not_meet_rate: "Does Not Meet %",
  question_no_rate: "Question No %",
  driver_review_rate: "Reviews with drivers %",
};

export const trendCompareLabels: Record<TrendCompareBy, string> = {
  none: "All filtered reviews",
  form_id: "Form type",
  form_version: "Form version",
  source: "Source",
  result_version: "Original vs current",
};

export function questionCommentKey(formKey: string, questionId: string): string {
  return `${formKey}:${questionId}`;
}

export function subQuestionCommentKey(
  formKey: string,
  questionId: string,
  subQuestionId: string,
  subQuestionText: string,
): string {
  return `${questionCommentKey(formKey, questionId)}:${subQuestionId}:${subQuestionText}`;
}

function getStringField(record: ReviewRecord, key: string): string {
  const value = record.input_json?.[key];
  return typeof value === "string" ? value : "";
}

function getBooleanField(record: ReviewRecord, key: string): boolean {
  const value = record.input_json?.[key];
  return typeof value === "boolean" ? value : false;
}

function getSourceFileIds(record: ReviewRecord): string {
  const value = record.input_json?.source_file_ids;
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string").join("; ") : "";
}

export function getCurrentForm(record: ReviewRecord): AuditFormResult | null {
  return record.user_version ?? record.userVersion ?? record.original ?? null;
}

export function getOriginalForm(record: ReviewRecord): AuditFormResult | null {
  return record.original ?? record.user_version ?? record.userVersion ?? null;
}

function getSelectedForm(record: ReviewRecord, resultVersion: ResultVersionKind): AuditFormResult | null {
  return resultVersion === "original" ? getOriginalForm(record) : getCurrentForm(record);
}

function normalizeComparableForm(form: AuditFormResult | null): string {
  if (!form) return "";
  return JSON.stringify({
    form_id: form.form_id,
    form_version: form.form_version,
    title: form.title,
    description: form.description,
    questions: form.questions,
    overall_outcome: form.overall_outcome,
    outcome_justification: form.outcome_justification,
  });
}

export function reviewHasEdits(record: ReviewRecord): boolean {
  const original = record.original;
  const current = getCurrentForm(record);
  if (!original || !current) return false;
  return normalizeComparableForm(original) !== normalizeComparableForm(current);
}

function questionWasEdited(row: DashboardReviewRow, questionId: string): boolean {
  const originalQuestion = row.originalForm?.questions.find((question) => question.id === questionId);
  const currentQuestion = row.currentForm?.questions.find((question) => question.id === questionId);
  if (!originalQuestion || !currentQuestion) return false;
  return JSON.stringify(originalQuestion) !== JSON.stringify(currentQuestion);
}

function countQuestionStats(form: AuditFormResult) {
  const questions = form.questions ?? [];
  return {
    questionCount: questions.length,
    yesCount: questions.filter((question) => question.answer === "Yes").length,
    noCount: questions.filter((question) => question.answer === "No").length,
    subQuestionCount: questions.reduce((sum, question) => sum + (question.sub_questions?.length ?? 0), 0),
    driverCount: questions.reduce(
      (sum, question) => sum + (question.sub_questions ?? []).filter((subQuestion) => Boolean(subQuestion.answer)).length,
      0,
    ),
  };
}

export function deriveReviewRows(records: ReviewRecord[], resultVersion: ResultVersionKind): DashboardReviewRow[] {
  return records
    .filter((record) => record.status === "completed")
    .map((record) => {
      const form = getSelectedForm(record, resultVersion);
      const currentForm = getCurrentForm(record);
      const originalForm = getOriginalForm(record);
      if (!form) return null;
      const stats = countQuestionStats(form);
      const formId = form.form_id || record.form_id || "";
      const formVersion = form.form_version || record.form_version || "";
      return {
        reviewId: record.id,
        batchId: record.batch_id ?? "",
        status: record.status ?? "",
        source: record.source ?? "",
        claimNumber: getStringField(record, "claim_number"),
        runName: getStringField(record, "batch_run_name"),
        effectiveDate: getStringField(record, "effective_date"),
        synthetic: getBooleanField(record, "synthetic"),
        inputJson: record.input_json ?? null,
        batchDescription: getStringField(record, "batch_description"),
        batchTemplateId: getStringField(record, "batch_template_id"),
        sourceFileIds: getSourceFileIds(record),
        formId,
        formVersion,
        formKey: formVersion ? `${formId}@${formVersion}` : formId,
        title: form.title,
        description: form.description,
        outcome: form.overall_outcome,
        outcomeJustification: form.outcome_justification,
        createdAt: record.created_at ?? form.created_at ?? "",
        updatedAt: record.updated_at ?? form.updated_at ?? "",
        resultVersion,
        edited: reviewHasEdits(record),
        form,
        originalForm,
        currentForm,
        ...stats,
      } satisfies DashboardReviewRow;
    })
    .filter((row): row is DashboardReviewRow => Boolean(row));
}

export function deriveVersionComparisonRows(records: ReviewRecord[]): DashboardReviewRow[] {
  return [
    ...deriveReviewRows(records, "original"),
    ...deriveReviewRows(records, "current"),
  ];
}

function dateForFilter(row: DashboardReviewRow): Date | null {
  const value = row.createdAt || row.updatedAt;
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dateInputToStart(value: string): Date | null {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dateInputToEnd(value: string): Date | null {
  if (!value) return null;
  const date = new Date(`${value}T23:59:59.999`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function filterDashboardRows(rows: DashboardReviewRow[], filters: DashboardFilters): DashboardReviewRow[] {
  const query = filters.search.trim().toLowerCase();
  const start = dateInputToStart(filters.dateFrom);
  const end = dateInputToEnd(filters.dateTo);

  return rows.filter((row) => {
    if (filters.formId !== "all" && row.formId !== filters.formId) return false;
    if (filters.formVersion !== "all" && row.formVersion !== filters.formVersion) return false;
    if (filters.source !== "all" && row.source !== filters.source) return false;
    if (filters.outcome !== "all" && row.outcome !== filters.outcome) return false;

    const rowDate = dateForFilter(row);
    if (start && (!rowDate || rowDate < start)) return false;
    if (end && (!rowDate || rowDate > end)) return false;

    if (!query) return true;
    const searchable = [
      row.reviewId,
      row.batchId,
      row.claimNumber,
      row.runName,
      row.effectiveDate,
      row.formId,
      row.formVersion,
      row.formKey,
      row.title,
      row.description,
      row.outcome,
      row.source,
      row.outcomeJustification,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return searchable.includes(query);
  });
}

export function getFilterOptions(rows: DashboardReviewRow[]): DashboardFilterOptions {
  const sortStrings = (values: Iterable<string>) =>
    Array.from(values)
      .filter(Boolean)
      .sort((first, second) => first.localeCompare(second, undefined, { numeric: true }));
  return {
    formIds: sortStrings(new Set(rows.map((row) => row.formId))),
    formVersions: sortStrings(new Set(rows.map((row) => row.formVersion))),
    sources: sortStrings(new Set(rows.map((row) => row.source))),
  };
}

export function aggregateQuestions(rows: DashboardReviewRow[]): AggregatedQuestionRow[] {
  const questionMap = new Map<
    string,
    {
      key: string;
      formId: string;
      formVersion: string;
      formKey: string;
      id: string;
      text: string;
      yesCount: number;
      noCount: number;
      totalCount: number;
      driverCount: number;
      editCount: number;
      subQuestions: Map<string, AggregatedSubQuestionRow>;
    }
  >();

  for (const row of rows) {
    for (const question of row.form.questions ?? []) {
      const questionKey = questionCommentKey(row.formKey || row.formId, question.id);
      let entry = questionMap.get(questionKey);
      if (!entry) {
        entry = {
          key: questionKey,
          formId: row.formId,
          formVersion: row.formVersion,
          formKey: row.formKey,
          id: question.id,
          text: question.text,
          yesCount: 0,
          noCount: 0,
          totalCount: 0,
          driverCount: 0,
          editCount: 0,
          subQuestions: new Map(),
        };
        questionMap.set(questionKey, entry);
      }

      entry.totalCount += 1;
      if (question.answer === "Yes") entry.yesCount += 1;
      if (question.answer === "No") entry.noCount += 1;
      if (questionWasEdited(row, question.id)) entry.editCount += 1;

      for (const subQuestion of question.sub_questions ?? []) {
        const subQuestionKey = subQuestionCommentKey(row.formKey || row.formId, question.id, subQuestion.id, subQuestion.text);
        let subEntry = entry.subQuestions.get(subQuestionKey);
        if (!subEntry) {
          subEntry = {
            key: subQuestionKey,
            id: subQuestion.id,
            parentId: question.id,
            text: subQuestion.text,
            driverCount: 0,
            totalAppearances: 0,
            driverPercent: 0,
            questionTotalCount: 0,
            questionNoCount: 0,
          };
          entry.subQuestions.set(subQuestionKey, subEntry);
        }
        subEntry.totalAppearances += 1;
        if (subQuestion.answer) {
          subEntry.driverCount += 1;
          entry.driverCount += 1;
        }
      }
    }
  }

  return Array.from(questionMap.values())
    .sort((first, second) => {
      const formCompare = first.formKey.localeCompare(second.formKey, undefined, { numeric: true });
      return formCompare || first.id.localeCompare(second.id, undefined, { numeric: true });
    })
    .map((entry) => ({
      key: entry.key,
      formId: entry.formId,
      formVersion: entry.formVersion,
      formKey: entry.formKey,
      id: entry.id,
      text: entry.text,
      yesCount: entry.yesCount,
      noCount: entry.noCount,
      totalCount: entry.totalCount,
      driverCount: entry.driverCount,
      editCount: entry.editCount,
      yesPercent: percent(entry.yesCount, entry.totalCount),
      noPercent: percent(entry.noCount, entry.totalCount),
      driverPercent: percent(entry.driverCount, entry.totalCount),
      subQuestions: Array.from(entry.subQuestions.values())
        .sort((first, second) => first.id.localeCompare(second.id, undefined, { numeric: true }))
        .map((subQuestion) => ({
          ...subQuestion,
          driverPercent: percent(subQuestion.driverCount, subQuestion.totalAppearances),
          questionTotalCount: entry.totalCount,
          questionNoCount: entry.noCount,
        })),
    }));
}

export function buildCommentRows(rows: DashboardReviewRow[]): CommentReportRow[] {
  const commentRows: CommentReportRow[] = [];

  for (const row of rows) {
    const outcomeComment = row.outcomeJustification.trim();
    if (outcomeComment) {
      commentRows.push({
        id: `${row.reviewId}:outcome`,
        reviewId: row.reviewId,
        createdAt: row.createdAt,
        updatedAt: row.updatedAt,
        claimNumber: row.claimNumber,
        runName: row.runName,
        source: row.source,
        formId: row.formId,
        formVersion: row.formVersion,
        title: row.title,
        outcome: row.outcome,
        resultVersion: row.resultVersion,
        commentType: "Outcome justification",
        questionId: "Outcome",
        questionText: "Overall outcome",
        answer: row.outcome,
        subQuestionId: "",
        subQuestionText: "",
        applicable: null,
        comment: outcomeComment,
        citations: "",
        row,
      });
    }

    for (const question of row.form.questions ?? []) {
      for (const subQuestion of question.sub_questions ?? []) {
        const reasoning = subQuestion.reasoning.trim();
        const citations = subQuestion.citations.trim();
        if (!reasoning && !citations) continue;
        commentRows.push({
          id: `${row.reviewId}:${question.id}:${subQuestion.id}`,
          reviewId: row.reviewId,
          createdAt: row.createdAt,
          updatedAt: row.updatedAt,
          claimNumber: row.claimNumber,
          runName: row.runName,
          source: row.source,
          formId: row.formId,
          formVersion: row.formVersion,
          title: row.title,
          outcome: row.outcome,
          resultVersion: row.resultVersion,
          commentType: "Sub-question reasoning",
          questionId: question.id,
          questionText: question.text,
          answer: question.answer,
          subQuestionId: subQuestion.id,
          subQuestionText: subQuestion.text,
          applicable: Boolean(subQuestion.answer),
          comment: reasoning,
          citations,
          row,
        });
      }
    }
  }

  return commentRows;
}

export function formatShortDate(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

export function formatDateTime(value: string): string {
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

export function percent(value: number, total: number, digits = 0): number {
  if (!total) return 0;
  const multiplier = 10 ** digits;
  return Math.round((value / total) * 100 * multiplier) / multiplier;
}

export function compareDashboardValues(
  first: string | number | boolean | null | undefined,
  second: string | number | boolean | null | undefined,
  direction: "asc" | "desc",
): number {
  const modifier = direction === "asc" ? 1 : -1;
  if (typeof first === "number" && typeof second === "number") {
    return (first - second) * modifier;
  }
  if (typeof first === "boolean" && typeof second === "boolean") {
    return (Number(first) - Number(second)) * modifier;
  }
  const firstDate = typeof first === "string" ? Date.parse(first) : Number.NaN;
  const secondDate = typeof second === "string" ? Date.parse(second) : Number.NaN;
  if (!Number.isNaN(firstDate) && !Number.isNaN(secondDate)) {
    return (firstDate - secondDate) * modifier;
  }
  return String(first ?? "").localeCompare(String(second ?? ""), undefined, { numeric: true }) * modifier;
}

export function getQuestionDriverCount(question: FormQuestion): number {
  return (question.sub_questions ?? []).filter((subQuestion) => subQuestion.answer).length;
}

export function getSubQuestionLabel(subQuestion: FormSubQuestion): string {
  return subQuestion.answer ? "Applicable" : "Not applicable";
}
