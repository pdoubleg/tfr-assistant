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
  sub_questions: FormSubQuestion[];
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
  source?: "api" | "chat_tool" | "batch";
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

export interface TFRChatState {
  active_route: string;
  active_review_id: string | null;
  selected_form_ids: string[];
  documents: Array<Record<string, unknown>>;
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
