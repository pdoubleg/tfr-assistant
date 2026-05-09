export type QuestionAnswer = "Yes" | "No" | "Insufficient information";
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
  missing_info?: string | null;
  help_text?: string | null;
}

export interface AuditFormResult {
  id: string;
  form_id: string;
  form_version: string;
  title: string;
  peril: {
    peril: string;
    notes?: string | null;
  };
  questions: FormQuestion[];
  overall_outcome: OverallOutcome;
  outcome_justification: string;
  created_at: string;
  updated_at: string;
}

export interface ReviewRecord {
  id: string;
  original: AuditFormResult;
  userVersion: AuditFormResult;
  feedback: "up" | "down" | null;
  comments: string;
}

export interface FormCatalogEntry {
  id: string;
  version: string;
  title: string;
  description: string;
  questionCount: number;
  status: "active" | "draft";
  lastUpdated: string;
}

export interface AggregatedQuestion {
  id: string;
  text: string;
  yesCount: number;
  noCount: number;
  insufficientCount: number;
  totalCount: number;
  editCount: number;
}

