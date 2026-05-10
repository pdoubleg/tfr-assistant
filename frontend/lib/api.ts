import type {
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
      question_count: number;
    }>
  >(response);
  return forms.map((form) => ({
    id: form.id,
    version: form.version,
    title: form.title,
    description: form.description ?? "",
    questionCount: form.question_count,
    status: "active",
    lastUpdated: "",
  }));
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
