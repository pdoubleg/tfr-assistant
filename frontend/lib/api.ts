import type {
  AuditFormDefinition,
  AuditFormResult,
  BatchRecord,
  BatchTemplatePayload,
  BatchTemplateRecord,
  FormCatalogEntry,
  ReviewRecord,
} from "@/lib/types";

export const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface FastApiValidationError {
  detail?: Array<{
    loc?: Array<string | number>;
    msg?: string;
    input?: Record<string, unknown>;
  }> | string;
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(formatApiError(response, body));
  }
  return (await response.json()) as T;
}

function formatApiError(response: Response, body: string): string {
  const fallback = `${response.status} ${response.statusText}`;

  try {
    const parsed = JSON.parse(body) as FastApiValidationError;
    if (Array.isArray(parsed.detail)) {
      const messages = parsed.detail.map((item) => {
        const questionIndex = [...(item.loc ?? [])]
          .reverse()
          .find((part): part is number => typeof part === "number");
        const questionId =
          typeof item.input?.id === "string"
            ? item.input.id
            : questionIndex !== undefined
              ? `Question ${questionIndex + 1}`
              : "Field";
        const message = (item.msg ?? "Invalid value.").replace(/^Value error,\s*/i, "");
        return `${questionId}: ${message}`;
      });
      return messages.join(" ");
    }

    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
  } catch {
    // Fall through to the raw response text below.
  }

  return body ? `${fallback}: ${body}` : fallback;
}

export async function listReviews(): Promise<ReviewRecord[]> {
  const response = await fetch(`${apiBaseUrl}/api/reviews`, {
    cache: "no-store",
  });
  return parseJsonResponse<ReviewRecord[]>(response);
}

export async function getReview(reviewId: string): Promise<ReviewRecord> {
  const response = await fetch(`${apiBaseUrl}/api/reviews/${reviewId}`, {
    cache: "no-store",
  });
  return parseJsonResponse<ReviewRecord>(response);
}

export async function updateReviewUserVersion(
  reviewId: string,
  userVersion: AuditFormResult,
): Promise<ReviewRecord> {
  const response = await fetch(`${apiBaseUrl}/api/reviews/${reviewId}/user-version`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_version: userVersion }),
  });
  return parseJsonResponse<ReviewRecord>(response);
}

export async function listFormCatalog(): Promise<FormCatalogEntry[]> {
  const response = await fetch(`${apiBaseUrl}/api/forms`, {
    cache: "no-store",
  });
  const forms = await parseJsonResponse<
    Array<{
      id: string;
      version: string;
      title: string;
      description?: string | null;
      audit_scope?: string | null;
      tool_instructions?: string | null;
      question_count: number;
      sub_question_count?: number;
      review_count?: number;
      completed_count?: number;
      failed_count?: number;
      last_reviewed_at?: string | null;
      created_at?: string | null;
    }>
  >(response);
  return forms.map((form) => ({
    id: form.id,
    version: form.version,
    title: form.title,
    description: form.description ?? "",
    auditScope: form.audit_scope ?? "",
    toolInstructions: form.tool_instructions ?? "",
    questionCount: form.question_count,
    subQuestionCount: form.sub_question_count ?? 0,
    status: "active",
    lastUpdated: form.last_reviewed_at ?? form.created_at ?? "",
    reviewCount: form.review_count ?? 0,
    completedCount: form.completed_count ?? 0,
    failedCount: form.failed_count ?? 0,
    lastReviewedAt: form.last_reviewed_at ?? "",
    createdAt: form.created_at ?? "",
  }));
}

export async function getFormDefinition(
  formId: string,
  version: string,
): Promise<AuditFormDefinition> {
  const response = await fetch(
    `${apiBaseUrl}/api/forms/${encodeURIComponent(formId)}/${encodeURIComponent(version)}`,
    {
      cache: "no-store",
    },
  );
  return parseJsonResponse<AuditFormDefinition>(response);
}

export async function registerForm(
  definition: AuditFormDefinition,
): Promise<AuditFormDefinition> {
  const response = await fetch(`${apiBaseUrl}/api/forms`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: definition.id,
      version: definition.version,
      title: definition.title,
      description: definition.description ?? "",
      audit_scope: definition.audit_scope ?? "",
      tool_instructions: definition.tool_instructions ?? "",
      canonical: definition.canonical,
    }),
  });
  return parseJsonResponse<AuditFormDefinition>(response);
}

export async function extractFormFromExcel(file: File): Promise<AuditFormDefinition> {
  const formData = new FormData();
  formData.append("workbook", file);
  const response = await fetch(`${apiBaseUrl}/api/forms/extract-excel`, {
    method: "POST",
    body: formData,
  });
  return parseJsonResponse<AuditFormDefinition>(response);
}

export async function listBatchTemplates(): Promise<BatchTemplateRecord[]> {
  const response = await fetch(`${apiBaseUrl}/api/batches/templates`, {
    cache: "no-store",
  });
  return parseJsonResponse<BatchTemplateRecord[]>(response);
}

export async function createBatchTemplate(
  payload: BatchTemplatePayload,
): Promise<BatchTemplateRecord> {
  const response = await fetch(`${apiBaseUrl}/api/batches/templates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<BatchTemplateRecord>(response);
}

export async function updateBatchTemplate(
  templateId: string,
  payload: Omit<BatchTemplatePayload, "name">,
): Promise<BatchTemplateRecord> {
  const response = await fetch(`${apiBaseUrl}/api/batches/templates/${templateId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<BatchTemplateRecord>(response);
}

export async function launchBatchTemplate(templateId: string): Promise<BatchRecord> {
  const response = await fetch(`${apiBaseUrl}/api/batches/templates/${templateId}/runs`, {
    method: "POST",
  });
  return parseJsonResponse<BatchRecord>(response);
}

export async function getBatch(batchId: string): Promise<BatchRecord> {
  const response = await fetch(`${apiBaseUrl}/api/batches/${batchId}`, {
    cache: "no-store",
  });
  return parseJsonResponse<BatchRecord>(response);
}

export async function listBatchReviews(batchId: string): Promise<ReviewRecord[]> {
  const response = await fetch(`${apiBaseUrl}/api/batches/${batchId}/reviews`, {
    cache: "no-store",
  });
  return parseJsonResponse<ReviewRecord[]>(response);
}

export function getUserVersion(review: ReviewRecord): AuditFormResult | null {
  return review.user_version ?? review.userVersion ?? review.original ?? null;
}

export function getClaimNumber(review: ReviewRecord): string {
  const claimNumber = review.input_json?.claim_number;
  return typeof claimNumber === "string" ? claimNumber : "";
}

export function getBatchRunName(review: ReviewRecord): string {
  const runName = review.input_json?.batch_run_name;
  return typeof runName === "string" ? runName : "";
}
