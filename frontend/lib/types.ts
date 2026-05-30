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
  instructions?: string | null;
  tools?: string[] | null;
  knowledge_docs?: string[] | null;
  canonical: AuditFormResult;
  created_at?: string;
}

export type PromptRefType = "form_default" | "alias" | "version" | "manual";

export interface PromptReference {
  ref_type: PromptRefType;
  family_id?: string | null;
  alias?: string | null;
  version_id?: string | null;
  form_id?: string | null;
  task?: "audit_review";
  prompt_kind?: "instructions";
  manual_text?: string;
}

export interface ResolvedPrompt {
  ref: PromptReference;
  text: string;
  text_hash: string;
  family_id?: string | null;
  version_id?: string | null;
  version_number?: number | null;
  alias?: string | null;
  form_id?: string | null;
  source_kind: string;
  external_prompt_uri?: string | null;
  resolved_at?: string;
}

export interface PromptAliasRecord {
  id: string;
  family_id: string;
  alias: string;
  version_id: string;
  version_number?: number | null;
  updated_at?: string;
}

export interface PromptActivationRecord {
  id: string;
  family_id: string;
  version_id: string;
  version_number?: number | null;
  scope: "form_version" | "form_default";
  form_version?: string | null;
  activated_by: string;
  notes: string;
  created_at?: string;
  updated_at?: string;
}

export interface PromptVersionRecord {
  id: string;
  family_id: string;
  version_number: number;
  text: string;
  text_hash: string;
  source_kind: "form_default" | "handcrafted" | "manual_edit" | "gepa_candidate";
  source_run_id?: string | null;
  source_candidate_index?: number | null;
  source_metadata: Record<string, unknown>;
  commit_message: string;
  created_by: string;
  metrics: Record<string, unknown>;
  applicable_form_versions: string[];
  form_schema_fingerprint: string;
  external_prompt_uri?: string | null;
  created_at?: string;
}

export interface PromptFamilyRecord {
  id: string;
  form_id: string;
  task: "audit_review";
  prompt_kind: "instructions";
  name: string;
  description: string;
  external_registry_uri?: string | null;
  metadata: Record<string, unknown>;
  aliases: PromptAliasRecord[];
  activations: PromptActivationRecord[];
  versions: PromptVersionRecord[];
  created_at?: string;
  updated_at?: string;
}

export interface ReviewRecord {
  id: string;
  form_id?: string;
  form_version?: string;
  status?: "queued" | "running" | "completed" | "failed";
  source?:
    | "api"
    | "chat_tool"
    | "batch"
    | "batch_manual"
    | "batch_upload"
    | "synthetic"
    | "completed_intake"
    | "manual_entry"
    | "eval";
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

export type BatchInputMode = "manual" | "upload" | "synthetic" | "completed_intake" | "manual_entry";
export type BatchStatus = "queued" | "running" | "paused" | "completed" | "failed" | "canceled";

export interface BatchReviewInput {
  claim_number: string;
  effective_date?: string;
  instructions?: string;
  prompt?: string;
  generation_prompt?: string;
  source_file_ids?: string[];
  form_id?: string | null;
  form_version?: string | null;
  synthetic?: boolean | null;
  manual_result?: AuditFormResult | null;
}

export interface BatchRecord {
  id: string;
  template_id?: string | null;
  name: string;
  description: string;
  status: BatchStatus;
  source: string;
  total_count: number;
  completed_count: number;
  failed_count: number;
  running_count: number;
  queued_count: number;
  progress_percent: number;
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
  generation_prompt: string;
  prompt_ref?: PromptReference | null;
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

export interface BatchFormVolume {
  form_id: string;
  form_version: string;
  total_count: number;
  completed_count: number;
  failed_count: number;
}

export interface BatchSummary {
  active_batches: number;
  queued_batches: number;
  paused_batches: number;
  failed_batches: number;
  completed_batches: number;
  total_reviews: number;
  completed_reviews: number;
  failed_reviews: number;
  running_reviews: number;
  queued_reviews: number;
  completed_reviews_today: number;
  average_duration_seconds?: number | null;
  form_volume: BatchFormVolume[];
}

export interface IntakeDocumentRecord {
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  modified_at: string;
  preview?: string;
}

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
  prompt_ref?: PromptReference | null;
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
  prompt_ref?: PromptReference | null;
  mlflow_run_id?: string | null;
  total_count: number;
  completed_count: number;
  failed_count: number;
  running_count: number;
  queued_count: number;
  progress_percent: number;
  primary_score?: number | null;
  metrics: Record<string, unknown>;
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
  agreement_items: EvalAgreementItemRecord[];
  created_at?: string;
}

export interface EvalAgreementItemRecord {
  id: string;
  run_id: string;
  run_item_id: string;
  case_id: string;
  ground_truth_id: string;
  comparison_id: string;
  reference_kind: EvalReferenceKind;
  level: "overall" | "question" | "subquestion";
  question_id?: string | null;
  subquestion_id?: string | null;
  question_text?: string | null;
  subquestion_text?: string | null;
  generated_answer?: string | null;
  reference_answer?: string | null;
  matched: boolean;
  agreement: number;
  generated_comment?: string | null;
  reference_comment?: string | null;
  generated_citations?: string | null;
  reference_citations?: string | null;
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

export type OptimizationRunStatus = "queued" | "running" | "completed" | "failed" | "canceled";
export type OptimizationSplit = "train" | "val" | "test";
export type OptimizationMetricMode = "comparison" | "comparison_with_judge";
export type OptimizationScoreKey =
  | "score"
  | "question_agreement"
  | "path_exact_rate"
  | "subquestion_f1"
  | "outcome_score";
export type OptimizationReferencePolicy = "prefer_r2" | "r1" | "r2" | "all";
export type OptimizationAutoBudget = "light" | "medium" | "heavy";
export type OptimizationCandidateSelectionStrategy = "pareto" | "current_best" | "epsilon_greedy" | "top_k_pareto";
export type OptimizationFrontierType = "instance" | "objective" | "hybrid" | "cartesian";
export type OptimizationBatchSampler = "epoch_shuffled";
export type OptimizationValEvaluationPolicy = "full_eval";

export interface OptimizationCaseRecord {
  case_id: string;
  dataset_id: string;
  dataset_name: string;
  source_kind: string;
  claim_number: string;
  effective_date?: string | null;
  instructions: string;
  outcome: string;
  issue_count: number;
  driver_count: number;
  reference_kinds: string[];
  created_at?: string;
}

export interface OptimizationCaseSplit {
  case_id: string;
  split: OptimizationSplit;
}

export interface OptimizationRunPayload {
  name: string;
  form_id: string;
  form_version: string;
  seed_instruction_source: "form" | "manual" | "prompt_registry";
  manual_instructions: string;
  seed_prompt_ref?: PromptReference | null;
  resolved_seed_prompt?: ResolvedPrompt | null;
  metric_mode: OptimizationMetricMode;
  score_key: OptimizationScoreKey;
  reference_policy: OptimizationReferencePolicy;
  judge_model?: string | null;
  gepa_params: {
    auto?: OptimizationAutoBudget | null;
    max_full_evals?: number | null;
    max_metric_calls?: number | null;
    reflection_model?: string | null;
    reflection_minibatch_size: number;
    perfect_score: number;
    skip_perfect_score: boolean;
    candidate_selection_strategy: OptimizationCandidateSelectionStrategy;
    frontier_type: OptimizationFrontierType;
    batch_sampler: OptimizationBatchSampler;
    module_selector: string;
    use_merge: boolean;
    max_merge_invocations: number;
    merge_val_overlap_floor: number;
    cache_evaluation: boolean;
    track_best_outputs: boolean;
    display_progress_bar: boolean;
    raise_on_exception: boolean;
    val_evaluation_policy?: OptimizationValEvaluationPolicy | null;
    use_mlflow: boolean;
    mlflow_tracking_uri?: string | null;
    mlflow_experiment_name?: string | null;
    seed: number;
  };
  trace_config: {
    capture_traces: boolean;
    max_tool_return_chars: number;
    include_debug_traces: boolean;
    include_thinking: boolean;
  };
  case_splits: OptimizationCaseSplit[];
}

export interface OptimizationCandidateRecord {
  id: string;
  run_id: string;
  candidate_index: number;
  parent_indices: Array<number | null>;
  status: string;
  candidate: Record<string, string>;
  score?: number | null;
  metrics: Record<string, unknown>;
  created_at?: string;
}

export interface OptimizationEventRecord {
  id: string;
  run_id: string;
  sequence: number;
  type: string;
  message: string;
  iteration?: number | null;
  level: string;
  data: Record<string, unknown>;
  created_at?: string;
}

export interface OptimizationRunRecord {
  id: string;
  name: string;
  status: OptimizationRunStatus;
  form_id: string;
  form_version: string;
  config: Record<string, unknown>;
  case_splits: OptimizationCaseSplit[];
  seed_candidate?: Record<string, string> | null;
  best_candidate?: Record<string, string> | null;
  metrics: Record<string, unknown>;
  artifacts: Record<string, unknown>;
  token_usage: Record<string, unknown>;
  total_count: number;
  train_count: number;
  val_count: number;
  test_count: number;
  best_score?: number | null;
  original_score?: number | null;
  total_metric_calls: number;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string;
  updated_at?: string;
  candidates: OptimizationCandidateRecord[];
  events: OptimizationEventRecord[];
}

export interface OptimizationDemoFixtureRecord {
  dataset_id: string;
  form_id: string;
  form_version: string;
  case_count: number;
  created: boolean;
}

export interface OptimizationDagNode {
  id: string;
  candidate_index: number;
  role: string;
  score?: number | null;
  candidate: Record<string, string>;
  parents: Array<number | null>;
}

export interface OptimizationDagEdge {
  id: string;
  source: string;
  target: string;
}

export interface OptimizationDagArtifact {
  schema_version: number;
  nodes: OptimizationDagNode[];
  edges: OptimizationDagEdge[];
  best_idx: number;
  pareto_front: number[];
  config: OptimizationRunPayload;
  test_report: Record<string, unknown>;
  total_metric_calls?: number | null;
}

export interface FormCatalogEntry {
  id: string;
  version: string;
  title: string;
  description: string;
  instructions: string;
  tools: string[];
  knowledgeDocs: string[];
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
  code?: {
    code: string;
    language: string;
    title?: string;
    caption?: string;
    defaultOpen?: boolean;
  };
  error?: {
    message: string;
    title?: string;
    caption?: string;
  };
}

export interface ChatHandleMetadata {
  handle: string;
  kind: "dataset" | "plotly_chart";
  label?: string;
  row_count?: number | null;
  column_count?: number | null;
  columns?: string[];
  source?: string;
  created_at?: string;
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
  artifact_session_id: string;
  handles: ChatHandleMetadata[];
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
