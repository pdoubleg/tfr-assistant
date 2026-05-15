export type QuestionAnswer = "Yes" | "No";
export type OverallOutcome = "Meets" | "Does Not Meet";

export interface FormSubQuestion {
  id: string;
  text: string;
  reasoning: string;
  citations: string;
  answer: boolean;
  help_text?: string | null;
}

export interface FormQuestion {
  id: string;
  text: string;
  answer: QuestionAnswer;
  comments?: string | null;
  citations?: string | null;
  sub_questions?: FormSubQuestion[] | null;
  help_text?: string | null;
}

export interface AuditFormResult {
  id?: string | null;
  form_id: string;
  form_version: string;
  title: string;
  description: string;
  questions: FormQuestion[];
  overall_outcome: OverallOutcome;
  outcome_justification: string;
  created_at?: string;
  updated_at?: string;
}

export interface AuditFormDefinition {
  id: string;
  version: string;
  title: string;
  description?: string | null;
  audit_scope?: string | null;
  tool_instructions?: string | null;
  canonical: AuditFormResult;
  created_at?: string;
}

export interface ReviewRecord {
  id: string;
  form_id?: string;
  form_version?: string;
  status?: "queued" | "running" | "completed" | "failed";
  source?: "api" | "chat_tool" | "batch" | "eval";
  batch_id?: string | null;
  input_json?: {
    claim_number?: string;
    effective_date?: string;
    prompt?: string;
    instructions?: string;
    batch_run_name?: string;
    batch_description?: string;
    batch_template_id?: string;
    source_file_ids?: string[];
    synthetic?: boolean;
    eval_run_id?: string;
    eval_run_name?: string;
    eval_dataset_id?: string;
    eval_result_role?: string;
    eval_reference_kind?: EvalReferenceKind;
    eval_config_version?: number;
    [key: string]: unknown;
  } | null;
  original?: AuditFormResult | null;
  user_version?: AuditFormResult | null;
  userVersion?: AuditFormResult | null;
  feedback?: "up" | "down" | null;
  comments?: string;
  error_message?: string | null;
  created_at?: string;
  updated_at?: string;
}

export type BatchInputMode = "manual" | "upload" | "synthetic";

export interface BatchReviewInput {
  claim_number: string;
  effective_date?: string;
  instructions?: string;
  prompt?: string;
  source_file_ids?: string[];
  form_id?: string | null;
  form_version?: string | null;
  synthetic?: boolean | null;
}

export interface BatchRecord {
  id: string;
  template_id?: string | null;
  name: string;
  description: string;
  status: "queued" | "running" | "completed" | "failed";
  source: string;
  total_count: number;
  completed_count: number;
  failed_count: number;
  input_json?: Record<string, unknown> | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface BatchTemplateRecord {
  id: string;
  name: string;
  description: string;
  form_id: string;
  form_version: string;
  synthetic: boolean;
  synthetic_count: number;
  input_mode: BatchInputMode;
  excel_column_map: Record<string, string>;
  items: BatchReviewInput[];
  item_count: number;
  latest_run?: BatchRecord | null;
  run_count: number;
  created_at?: string;
  updated_at?: string;
}

export type BatchTemplatePayload = Omit<
  BatchTemplateRecord,
  "id" | "item_count" | "latest_run" | "run_count" | "created_at" | "updated_at"
>;

export type EvalReferenceKind = "R1" | "R2";
export type EvalReferencePolicy = "prefer_r2" | "r1" | "r2" | "all";
export type EvalRunStatus = "queued" | "running" | "paused" | "completed" | "failed" | "canceled";
export type EvalRunItemStatus = "queued" | "running" | "completed" | "failed" | "skipped";

export interface EvalGroundTruthRecord {
  id: string;
  case_id: string;
  reference_kind: EvalReferenceKind;
  result: AuditFormResult;
  reviewer?: string | null;
  source_metadata?: Record<string, unknown> | null;
  created_at?: string;
}

export interface EvalCaseRecord {
  id: string;
  dataset_id: string;
  claim_number: string;
  effective_date?: string | null;
  instructions: string;
  input: Record<string, unknown>;
  ground_truths: EvalGroundTruthRecord[];
  created_at?: string;
  updated_at?: string;
}

export interface EvalDatasetRecord {
  id: string;
  name: string;
  description: string;
  form_id: string;
  form_version: string;
  source_kind: string;
  source_metadata?: Record<string, unknown> | null;
  dataset_hash: string;
  case_count: number;
  r1_count: number;
  r2_count: number;
  cases?: EvalCaseRecord[];
  created_at?: string;
  updated_at?: string;
}

export interface EvalRunPayload {
  dataset_id: string;
  name: string;
  model_name?: string;
  reference_policy: EvalReferencePolicy;
  concurrency?: number;
  retry_limit: number;
  enable_mlflow: boolean;
  synthetic: boolean;
  base_run_id?: string | null;
}

export interface EvalRunRecord {
  id: string;
  dataset_id: string;
  dataset_name: string;
  lineage_id?: string | null;
  source_run_id?: string | null;
  config_version: number;
  name: string;
  status: EvalRunStatus;
  model_name: string;
  reference_policy: EvalReferencePolicy;
  concurrency: number;
  retry_limit: number;
  enable_mlflow: boolean;
  mlflow_run_id?: string | null;
  synthetic: boolean;
  total_count: number;
  completed_count: number;
  failed_count: number;
  running_count: number;
  queued_count: number;
  progress_percent: number;
  primary_score?: number | null;
  input: Record<string, unknown>;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface EvalComparisonRecord {
  id: string;
  run_id: string;
  run_item_id: string;
  case_id: string;
  ground_truth_id: string;
  reference_kind: EvalReferenceKind;
  score?: number | null;
  metrics: Record<string, unknown>;
  created_at?: string;
}

export interface EvalRunItemRecord {
  id: string;
  run_id: string;
  case_id: string;
  claim_number: string;
  effective_date?: string | null;
  status: EvalRunItemStatus;
  attempt_count: number;
  generated_review_id?: string | null;
  generated_result?: AuditFormResult | null;
  ground_truths: EvalGroundTruthRecord[];
  error_message?: string | null;
  comparisons: EvalComparisonRecord[];
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface FormCatalogEntry {
  id: string;
  version: string;
  title: string;
  description: string;
  auditScope: string;
  toolInstructions: string;
  questionCount: number;
  subQuestionCount: number;
  status: "active" | "draft";
  lastUpdated: string;
  reviewCount: number;
  completedCount: number;
  failedCount: number;
  lastReviewedAt: string;
  createdAt: string;
}

export interface AggregatedQuestion {
  id: string;
  text: string;
  yesCount: number;
  noCount: number;
  totalCount: number;
  editCount: number;
}

export interface ToolStep {
  id: string;
  message: string;
  status: "in_progress" | "completed" | "error";
  timestamp?: string;
}

export type A2UICellValue = string | number | boolean | null;

export interface A2UIComponent {
  id: string;
  type: string;
  props: Record<string, unknown>;
  children?: A2UIComponent[];
  layout?: {
    width?: string;
    height?: string;
    position?: "relative" | "absolute" | "fixed" | "sticky";
    className?: string;
  } | null;
  styling?: {
    variant?: string;
    theme?: string;
    className?: string;
  } | null;
  zone?: "chat" | string | null;
}

export interface SelectedHomeRowContext {
  row_id: string;
  review_id: string;
  result_version: "current" | "original" | string;
  form_id: string;
  form_version: string;
  form_key: string;
  claim_number: string;
  batch_id: string;
  run_name: string;
  source: string;
  outcome: OverallOutcome | string;
  title: string;
  created_at: string;
  updated_at: string;
  question_count: number;
  no_count: number;
  driver_count: number;
  edited: boolean;
}

export interface HomeTableContext {
  selected_rows: SelectedHomeRowContext[];
  visible_row_count: number;
  total_row_count: number;
  filters: {
    search: string;
    column_filters: Record<string, string>;
    sorting: Array<{ id: string; desc: boolean }>;
    page_index: number;
    page_size: number;
    density: string;
  };
}

export interface ChatRunContext {
  active_route: string;
  selected_home_rows: SelectedHomeRowContext[];
  home_table: HomeTableContext;
  captured_at: string;
}

export interface TFRChatState {
  active_route: string;
  active_review_id: string | null;
  selected_form_ids: string[];
  documents: Array<Record<string, unknown>>;
  components: A2UIComponent[];
  run_context: ChatRunContext | null;
  status: "idle" | "thinking" | "using_tools" | "complete" | "error";
  progress: number;
  current_step: string;
  activity_log: ToolStep[];
  error_message: string | null;
}

export type OutputComponent =
  | {
      id: string;
      type: "audit_form";
      reviewId: string;
      title: string;
      form: AuditFormResult;
      source?: string;
      createdAt?: string;
      updatedAt?: string;
      claimNumber?: string;
      collapsed?: boolean;
    }
  | {
      id: string;
      type: string;
      title?: string;
      props: Record<string, unknown>;
      collapsed?: boolean;
    };
