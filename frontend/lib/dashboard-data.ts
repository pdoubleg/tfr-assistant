import type {
  AuditFormResult,
  FormKind,
  FormQuestion,
  FormSubQuestion,
  OverallOutcome,
  PublishedDatasetRow,
  ReviewRecord,
} from "@/lib/types";

export type ResultVersionKind = "current" | "original";
export type TrendGranularity = "day" | "week" | "month";
export type TrendCompareBy =
  | "none"
  | "form_id"
  | "form_version"
  | "source"
  | "result_version"
  | "eval_result_role";
export type TrendMetric =
  | "review_volume"
  | "meets_rate"
  | "does_not_meet_rate"
  | "question_no_rate"
  | "driver_review_rate"
  | "overwrite_percent"
  | "underwrite_percent"
  | "overwrite_total"
  | "underwrite_total"
  | "net_exception";

export interface DashboardFilters {
  search: string;
  formId: string;
  formVersion: string;
  source: string;
  outcome: string;
  dateFrom: string;
  dateTo: string;
  resultVersion: ResultVersionKind;
  evalRole: string;
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
  evalRunId: string;
  evalRunName: string;
  evalResultRole: string;
  evalReferenceKind: string;
  evalConfigVersion: number | null;
  evalGroupKey: string;
  formId: string;
  formVersion: string;
  formKind: FormKind;
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
  totalAmountReviewedDollars: number | null;
  totalOverwriteDollars: number;
  totalUnderwriteDollars: number;
  overwritePercent: number | null;
  underwritePercent: number | null;
  netExceptionDollars: number;
  createdAt: string;
  updatedAt: string;
  resultVersion: ResultVersionKind;
  edited: boolean;
  form: AuditFormResult;
  originalForm: AuditFormResult | null;
  currentForm: AuditFormResult | null;
  rowKind?: "review" | "dataset_case";
  datasetId?: string;
  datasetCaseId?: string;
  groundTruthId?: string;
  referenceKind?: string;
}

export interface DashboardFilterOptions {
  formIds: string[];
  formVersions: string[];
  sources: string[];
  evalRoles: string[];
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
  formKind: FormKind;
  formId: string;
  formVersion: string;
  formKey: string;
  id: string;
  text: string;
  yesCount: number;
  noCount: number;
  totalCount: number;
  driverCount: number;
  totalOverwriteDollars: number;
  totalUnderwriteDollars: number;
  netExceptionDollars: number;
  editCount: number;
  yesPercent: number;
  noPercent: number;
  driverPercent: number;
  overwritePercent: number;
  underwritePercent: number;
  subQuestions: AggregatedSubQuestionRow[];
}

export type CommentReportType = "Outcome justification" | "Question comments" | "Sub-question reasoning" | "Financial exception";

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
  evalRole: "all",
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
  overwrite_percent: "Overwrite %",
  underwrite_percent: "Underwrite %",
  overwrite_total: "Overwrite total",
  underwrite_total: "Underwrite total",
  net_exception: "Net exception",
};

export const trendCompareLabels: Record<TrendCompareBy, string> = {
  none: "All filtered reviews",
  form_id: "Form type",
  form_version: "Form version",
  source: "Source",
  result_version: "Original vs current",
  eval_result_role: "Eval role",
};

export function evalRoleLabel(role: string, referenceKind?: string): string {
  if (role === "model") return "Model";
  if (role === "ground_truth") return referenceKind ? `Ground Truth ${referenceKind}` : "Ground Truth";
  return role || "Non-eval";
}

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

function getNumberField(record: ReviewRecord, key: string): number | null {
  const value = record.input_json?.[key];
  return typeof value === "number" ? value : null;
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
  const totalOverwriteDollars = questions.reduce((sum, question) => sum + (Number(question.overwrite_dollars) || 0), 0);
  const totalUnderwriteDollars = questions.reduce((sum, question) => sum + (Number(question.underwrite_dollars) || 0), 0);
  const totalAmountReviewedDollars =
    form.form_kind === "financial" ? Number(form.total_amount_reviewed_dollars) || 0 : null;
  return {
    questionCount: questions.length,
    yesCount: questions.filter((question) => question.answer === "Yes").length,
    noCount: questions.filter((question) => question.answer === "No").length,
    subQuestionCount: form.form_kind === "financial" ? 0 : questions.reduce((sum, question) => sum + (question.sub_questions?.length ?? 0), 0),
    driverCount: questions.reduce(
      (sum, question) => sum + (question.sub_questions ?? []).filter((subQuestion) => Boolean(subQuestion.answer)).length,
      0,
    ),
    totalAmountReviewedDollars,
    totalOverwriteDollars,
    totalUnderwriteDollars,
    overwritePercent: totalAmountReviewedDollars ? (totalOverwriteDollars / totalAmountReviewedDollars) * 100 : null,
    underwritePercent: totalAmountReviewedDollars ? (totalUnderwriteDollars / totalAmountReviewedDollars) * 100 : null,
    netExceptionDollars: totalOverwriteDollars - totalUnderwriteDollars,
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
      const formKind = form.form_kind ?? record.form_kind ?? "standard";
      const evalResultRole =
        getStringField(record, "eval_result_role") || (record.source === "eval" ? "model" : "");
      const evalReferenceKind = getStringField(record, "eval_reference_kind");
      const evalRunId = getStringField(record, "eval_run_id");
      const evalRunName = getStringField(record, "eval_run_name");
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
        evalRunId,
        evalRunName,
        evalResultRole,
        evalReferenceKind,
        evalConfigVersion: getNumberField(record, "eval_config_version"),
        evalGroupKey: [
          evalRunId,
          getStringField(record, "claim_number"),
          formId,
          formVersion,
        ].filter(Boolean).join(":"),
        formId,
        formVersion,
        formKind,
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

export function derivePublishedDatasetRows(records: PublishedDatasetRow[]): DashboardReviewRow[] {
  return records.map((record) => {
    const form = record.result;
    const stats = countQuestionStats(form);
    const formKind = form.form_kind ?? record.form_kind ?? "standard";
    const source = record.source_label || record.source_kind || "dataset";
    return {
      reviewId: `dataset:${record.case_id}:${record.ground_truth_id}`,
      batchId: record.dataset_id,
      status: "completed",
      source,
      claimNumber: record.claim_number,
      runName: record.dataset_name,
      effectiveDate: record.effective_date ?? "",
      synthetic: false,
      inputJson: record.metadata ?? null,
      batchDescription: record.sample_reason,
      batchTemplateId: "",
      sourceFileIds: "",
      evalRunId: "",
      evalRunName: record.dataset_name,
      evalResultRole: "ground_truth",
      evalReferenceKind: record.reference_kind,
      evalConfigVersion: null,
      evalGroupKey: [record.dataset_id, record.case_id, record.reference_kind].join(":"),
      formId: record.form_id,
      formVersion: record.form_version,
      formKind,
      formKey: `${record.form_id}@${record.form_version}`,
      title: form.title,
      description: form.description,
      outcome: form.overall_outcome,
      outcomeJustification: form.outcome_justification,
      createdAt: record.created_at ?? "",
      updatedAt: record.updated_at ?? record.created_at ?? "",
      resultVersion: "current",
      edited: false,
      form,
      originalForm: form,
      currentForm: form,
      rowKind: "dataset_case",
      datasetId: record.dataset_id,
      datasetCaseId: record.case_id,
      groundTruthId: record.ground_truth_id,
      referenceKind: record.reference_kind,
      ...stats,
    } satisfies DashboardReviewRow;
  });
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
    if (filters.evalRole !== "all") {
      const rowRole = evalRoleLabel(row.evalResultRole, row.evalReferenceKind);
      if (rowRole !== filters.evalRole) return false;
    }

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
      row.formKind,
      row.formKey,
      row.title,
      row.description,
      row.outcome,
      row.source,
      evalRoleLabel(row.evalResultRole, row.evalReferenceKind),
      row.evalRunName,
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
    evalRoles: sortStrings(
      new Set(
        rows
          .filter((row) => row.source === "eval" || row.evalResultRole)
          .map((row) => evalRoleLabel(row.evalResultRole, row.evalReferenceKind)),
      ),
    ),
  };
}

export function aggregateQuestions(rows: DashboardReviewRow[]): AggregatedQuestionRow[] {
  const questionMap = new Map<
    string,
    {
      key: string;
      formId: string;
      formKind: FormKind;
      formVersion: string;
      formKey: string;
      id: string;
      text: string;
      yesCount: number;
      noCount: number;
      totalCount: number;
      driverCount: number;
      totalOverwriteDollars: number;
      totalUnderwriteDollars: number;
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
          formKind: row.formKind,
          formVersion: row.formVersion,
          formKey: row.formKey,
          id: question.id,
          text: question.text,
          yesCount: 0,
          noCount: 0,
          totalCount: 0,
          driverCount: 0,
          totalOverwriteDollars: 0,
          totalUnderwriteDollars: 0,
          editCount: 0,
          subQuestions: new Map(),
        };
        questionMap.set(questionKey, entry);
      }

      entry.totalCount += 1;
      if (question.answer === "Yes") entry.yesCount += 1;
      if (question.answer === "No") entry.noCount += 1;
      entry.totalOverwriteDollars += Number(question.overwrite_dollars) || 0;
      entry.totalUnderwriteDollars += Number(question.underwrite_dollars) || 0;
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
      formKind: entry.formKind,
      formVersion: entry.formVersion,
      formKey: entry.formKey,
      id: entry.id,
      text: entry.text,
      yesCount: entry.yesCount,
      noCount: entry.noCount,
      totalCount: entry.totalCount,
      driverCount: entry.driverCount,
      totalOverwriteDollars: entry.totalOverwriteDollars,
      totalUnderwriteDollars: entry.totalUnderwriteDollars,
      netExceptionDollars: entry.totalOverwriteDollars - entry.totalUnderwriteDollars,
      editCount: entry.editCount,
      yesPercent: percent(entry.yesCount, entry.totalCount),
      noPercent: percent(entry.noCount, entry.totalCount),
      driverPercent: percent(entry.driverCount, entry.totalCount),
      overwritePercent: percent(entry.totalOverwriteDollars, entry.totalCount, 2),
      underwritePercent: percent(entry.totalUnderwriteDollars, entry.totalCount, 2),
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
      const questionComment = (question.comments ?? "").trim();
      const questionCitations = (question.citations ?? "").trim();
      if (questionComment || questionCitations) {
        commentRows.push({
          id: `${row.reviewId}:${question.id}:question`,
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
          commentType: "Question comments",
          questionId: question.id,
          questionText: question.text,
          answer: question.answer,
          subQuestionId: "",
          subQuestionText: "",
          applicable: null,
          comment: questionComment,
          citations: questionCitations,
          row,
        });
      }

      if (row.formKind === "financial" && ((question.overwrite_dollars ?? 0) || (question.underwrite_dollars ?? 0))) {
        commentRows.push({
          id: `${row.reviewId}:${question.id}:financial`,
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
          commentType: "Financial exception",
          questionId: question.id,
          questionText: question.text,
          answer: question.answer,
          subQuestionId: "",
          subQuestionText: "",
          applicable: null,
          comment: `OW $${Number(question.overwrite_dollars ?? 0).toFixed(2)}; UW $${Number(question.underwrite_dollars ?? 0).toFixed(2)}`,
          citations: question.citations ?? "",
          row,
        });
      }

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
