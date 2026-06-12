import type {
  AuditFormDefinition,
  AuditFormResult,
  BatchRecord,
  BatchSummary,
  BatchTemplatePayload,
  BatchTemplateRecord,
  ChatModelCatalog,
  ChatThreadRecord,
  ChatThreadSummary,
  DatasetAddCandidatesResponse,
  DatasetCandidateRecord,
  DatasetClusterResult,
  DatasetMaterializeResponse,
  DatasetPopulationRecord,
  DatasetSampleMode,
  DatasetSampleResult,
  DatasetSourceRecord,
  DatasetSourceRowRecord,
  EvalDatasetRecord,
  EvalRunItemRecord,
  EvalRunPayload,
  EvalRunRecord,
  FormCatalogEntry,
  FeedbackRecord,
  IntakeDocumentRecord,
  OptimizationCaseRecord,
  OptimizationDagArtifact,
  OptimizationRunPayload,
  OptimizationRunRecord,
  PromptActivationRecord,
  PromptAliasRecord,
  PromptFamilyRecord,
  PromptReference,
  PromptVersionRecord,
  PublishedDatasetRow,
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

export async function finalizeReview(
  reviewId: string,
  userVersion?: AuditFormResult,
): Promise<ReviewRecord> {
  const response = await fetch(`${apiBaseUrl}/api/reviews/${reviewId}/finalization`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_version: userVersion ?? null }),
  });
  return parseJsonResponse<ReviewRecord>(response);
}

export async function submitReviewFeedback(payload: {
  review_id: string;
  score: number;
  comment?: string | null;
}): Promise<FeedbackRecord> {
  const response = await fetch(`${apiBaseUrl}/api/evaluations/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<FeedbackRecord>(response);
}

export async function listChatModels(): Promise<ChatModelCatalog> {
  const response = await fetch(`${apiBaseUrl}/api/chat/models`, {
    cache: "no-store",
  });
  return parseJsonResponse<ChatModelCatalog>(response);
}

export async function listChatThreads(): Promise<ChatThreadSummary[]> {
  const response = await fetch(`${apiBaseUrl}/api/chat/threads`, {
    cache: "no-store",
  });
  return parseJsonResponse<ChatThreadSummary[]>(response);
}

export async function getChatThread(threadId: string): Promise<ChatThreadRecord> {
  const response = await fetch(`${apiBaseUrl}/api/chat/threads/${encodeURIComponent(threadId)}`, {
    cache: "no-store",
  });
  return parseJsonResponse<ChatThreadRecord>(response);
}

export async function deleteChatThread(threadId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/chat/threads/${encodeURIComponent(threadId)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(formatApiError(response, body));
  }
}

export async function listFormCatalog(
  options: { publishedOnly?: boolean } = {},
): Promise<FormCatalogEntry[]> {
  const params = new URLSearchParams();
  if (options.publishedOnly) params.set("published_only", "true");
  const query = params.toString();
  const response = await fetch(`${apiBaseUrl}/api/forms${query ? `?${query}` : ""}`, {
    cache: "no-store",
  });
  const forms = await parseJsonResponse<
    Array<{
      id: string;
      version: string;
      title: string;
      published?: boolean;
      form_kind?: "standard" | "financial";
      model_name?: string;
      description?: string | null;
      tools?: FormCatalogEntry["tools"] | null;
      knowledge_docs?: string[] | null;
      include_state_compliance?: boolean | null;
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
    published: form.published ?? false,
    formKind: form.form_kind ?? "standard",
    modelName: form.model_name ?? "gpt-5.4-nano",
    description: form.description ?? "",
    tools: form.tools ?? [],
    knowledgeDocs: form.knowledge_docs ?? [],
    includeStateCompliance: form.include_state_compliance ?? false,
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
      published: definition.published ?? false,
      form_kind: definition.form_kind ?? definition.canonical.form_kind ?? "standard",
      model_name: definition.model_name ?? "gpt-5.4-nano",
      description: definition.description ?? "",
      tools: definition.tools ?? null,
      knowledge_docs: definition.knowledge_docs ?? null,
      include_state_compliance: definition.include_state_compliance ?? false,
      canonical: {
        ...definition.canonical,
        form_kind: definition.canonical.form_kind ?? definition.form_kind ?? "standard",
      },
    }),
  });
  return parseJsonResponse<AuditFormDefinition>(response);
}

export async function setFormPublication(
  formId: string,
  version: string,
  published: boolean,
): Promise<AuditFormDefinition> {
  const response = await fetch(
    `${apiBaseUrl}/api/forms/${encodeURIComponent(formId)}/${encodeURIComponent(version)}/publication`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ published }),
    },
  );
  return parseJsonResponse<AuditFormDefinition>(response);
}

export async function listPromptFamilies(
  formId: string,
  formVersion?: string,
): Promise<PromptFamilyRecord[]> {
  const params = new URLSearchParams();
  if (formVersion) params.set("form_version", formVersion);
  const response = await fetch(
    `${apiBaseUrl}/api/prompts/forms/${encodeURIComponent(formId)}/families?${params.toString()}`,
    { cache: "no-store" },
  );
  return parseJsonResponse<PromptFamilyRecord[]>(response);
}

export async function bootstrapPromptFamily(
  formId: string,
  formVersion: string,
): Promise<PromptFamilyRecord> {
  const response = await fetch(
    `${apiBaseUrl}/api/prompts/forms/${encodeURIComponent(formId)}/${encodeURIComponent(formVersion)}/bootstrap`,
    { method: "POST" },
  );
  return parseJsonResponse<PromptFamilyRecord>(response);
}

export async function setPromptAlias(
  familyId: string,
  alias: string,
  versionId: string,
): Promise<PromptAliasRecord> {
  const response = await fetch(`${apiBaseUrl}/api/prompts/aliases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ family_id: familyId, alias, version_id: versionId }),
  });
  return parseJsonResponse<PromptAliasRecord>(response);
}

export async function setPromptActivation(payload: {
  family_id: string;
  version_id: string;
  form_version?: string | null;
  scope?: "form_version" | "form_default";
  activated_by?: string;
  notes?: string;
}): Promise<PromptActivationRecord> {
  const response = await fetch(`${apiBaseUrl}/api/prompts/activations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<PromptActivationRecord>(response);
}

export async function createPromptVersion(payload: {
  family_id?: string | null;
  form_id: string;
  form_version?: string | null;
  text: string;
  source_kind?: "form_default" | "handcrafted" | "manual_edit" | "gepa_candidate";
  commit_message?: string;
  created_by?: string;
  applicable_form_versions?: string[];
  alias?: string | null;
}): Promise<PromptVersionRecord> {
  const response = await fetch(`${apiBaseUrl}/api/prompts/versions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<PromptVersionRecord>(response);
}

export async function registerOptimizationCandidate(payload: {
  run_id: string;
  candidate_index: number;
  activate_for_form_version?: boolean;
  commit_message?: string;
  created_by?: string;
}): Promise<PromptVersionRecord> {
  const response = await fetch(`${apiBaseUrl}/api/prompts/register-optimization-candidate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<PromptVersionRecord>(response);
}

export async function promoteOptimizationCandidate(payload: {
  run_id: string;
  candidate_index: number;
  alias?: string | null;
  commit_message?: string;
  created_by?: string;
}): Promise<PromptVersionRecord> {
  const response = await fetch(`${apiBaseUrl}/api/prompts/promote-optimization-candidate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<PromptVersionRecord>(response);
}

export function promptRefLabel(ref?: PromptReference | null): string {
  if (!ref || ref.ref_type === "form_default") return "Form default";
  if (ref.ref_type === "alias") return `${ref.alias ?? "alias"} prompt`;
  if (ref.ref_type === "version") return "Specific prompt version";
  return "Manual prompt";
}

export async function listBatchTemplates(): Promise<BatchTemplateRecord[]> {
  const response = await fetch(`${apiBaseUrl}/api/batches/templates`, {
    cache: "no-store",
  });
  return parseJsonResponse<BatchTemplateRecord[]>(response);
}

export async function listBatches(): Promise<BatchRecord[]> {
  const response = await fetch(`${apiBaseUrl}/api/batches`, {
    cache: "no-store",
  });
  return parseJsonResponse<BatchRecord[]>(response);
}

export async function getBatchSummary(): Promise<BatchSummary> {
  const response = await fetch(`${apiBaseUrl}/api/batches/summary`, {
    cache: "no-store",
  });
  return parseJsonResponse<BatchSummary>(response);
}

export async function listIntakeDocuments(): Promise<IntakeDocumentRecord[]> {
  const response = await fetch(`${apiBaseUrl}/api/batches/intake-documents`, {
    cache: "no-store",
  });
  return parseJsonResponse<IntakeDocumentRecord[]>(response);
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

export async function pauseBatch(batchId: string): Promise<BatchRecord> {
  const response = await fetch(`${apiBaseUrl}/api/batches/${batchId}/pause`, {
    method: "POST",
  });
  return parseJsonResponse<BatchRecord>(response);
}

export async function resumeBatch(batchId: string): Promise<BatchRecord> {
  const response = await fetch(`${apiBaseUrl}/api/batches/${batchId}/resume`, {
    method: "POST",
  });
  return parseJsonResponse<BatchRecord>(response);
}

export async function retryFailedBatch(batchId: string): Promise<BatchRecord> {
  const response = await fetch(`${apiBaseUrl}/api/batches/${batchId}/retry-failed`, {
    method: "POST",
  });
  return parseJsonResponse<BatchRecord>(response);
}

export async function cancelBatch(batchId: string): Promise<BatchRecord> {
  const response = await fetch(`${apiBaseUrl}/api/batches/${batchId}/cancel`, {
    method: "POST",
  });
  return parseJsonResponse<BatchRecord>(response);
}

export async function listEvalDatasets(): Promise<EvalDatasetRecord[]> {
  const response = await fetch(`${apiBaseUrl}/api/evaluations/datasets`, {
    cache: "no-store",
  });
  return parseJsonResponse<EvalDatasetRecord[]>(response);
}

export async function listDatasetPopulations(
  formId?: string,
  formVersion?: string,
): Promise<DatasetPopulationRecord[]> {
  const params = new URLSearchParams();
  if (formId) params.set("form_id", formId);
  if (formVersion) params.set("form_version", formVersion);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${apiBaseUrl}/api/datasets/populations${suffix}`, {
    cache: "no-store",
  });
  return parseJsonResponse<DatasetPopulationRecord[]>(response);
}

export async function createDatasetPopulation(payload: {
  name: string;
  description?: string;
  form_id: string;
  form_version: string;
}): Promise<DatasetPopulationRecord> {
  const response = await fetch(`${apiBaseUrl}/api/datasets/populations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<DatasetPopulationRecord>(response);
}

export async function updateDatasetPopulation(
  populationId: string,
  payload: { name?: string; description?: string },
): Promise<DatasetPopulationRecord> {
  const response = await fetch(`${apiBaseUrl}/api/datasets/populations/${populationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<DatasetPopulationRecord>(response);
}

export async function getDatasetPopulation(
  populationId: string,
): Promise<DatasetPopulationRecord> {
  const response = await fetch(`${apiBaseUrl}/api/datasets/populations/${populationId}`, {
    cache: "no-store",
  });
  return parseJsonResponse<DatasetPopulationRecord>(response);
}

export async function listDatasetSources(
  formId: string,
  formVersion: string,
): Promise<DatasetSourceRecord[]> {
  const params = new URLSearchParams({ form_id: formId, form_version: formVersion });
  const response = await fetch(`${apiBaseUrl}/api/datasets/sources?${params.toString()}`, {
    cache: "no-store",
  });
  return parseJsonResponse<DatasetSourceRecord[]>(response);
}

export async function fetchDatasetSource(
  populationId: string,
  payload: { source_id: string; params?: Record<string, unknown> },
): Promise<DatasetAddCandidatesResponse> {
  const response = await fetch(
    `${apiBaseUrl}/api/datasets/populations/${populationId}/fetch-source`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_id: payload.source_id, params: payload.params ?? {} }),
    },
  );
  return parseJsonResponse<DatasetAddCandidatesResponse>(response);
}

export async function browseDatasetSourceRows(
  formId: string,
  formVersion: string,
  payload: { source_id: string; params?: Record<string, unknown>; limit?: number },
): Promise<DatasetSourceRowRecord[]> {
  const params = new URLSearchParams({ form_id: formId, form_version: formVersion });
  const response = await fetch(`${apiBaseUrl}/api/datasets/source-preview?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_id: payload.source_id,
      params: payload.params ?? {},
      limit: payload.limit ?? 100,
    }),
  });
  return parseJsonResponse<DatasetSourceRowRecord[]>(response);
}

export async function addDatasetSourceRows(
  populationId: string,
  payload: {
    source_id: string;
    params?: Record<string, unknown>;
    source_record_ids?: string[];
    add_all_filtered?: boolean;
    limit?: number;
  },
): Promise<DatasetAddCandidatesResponse> {
  const response = await fetch(
    `${apiBaseUrl}/api/datasets/populations/${populationId}/source-candidates`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_id: payload.source_id,
        params: payload.params ?? {},
        source_record_ids: payload.source_record_ids ?? [],
        add_all_filtered: payload.add_all_filtered ?? false,
        limit: payload.limit ?? 100,
      }),
    },
  );
  return parseJsonResponse<DatasetAddCandidatesResponse>(response);
}

export async function materializeDatasetSourceRows(
  formId: string,
  formVersion: string,
  payload: {
    source_id: string;
    params?: Record<string, unknown>;
    source_record_ids?: string[];
    add_all_filtered?: boolean;
    limit?: number;
  },
): Promise<DatasetMaterializeResponse> {
  const params = new URLSearchParams({ form_id: formId, form_version: formVersion });
  const response = await fetch(`${apiBaseUrl}/api/datasets/source-materialize?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_id: payload.source_id,
      params: payload.params ?? {},
      source_record_ids: payload.source_record_ids ?? [],
      add_all_filtered: payload.add_all_filtered ?? false,
      limit: payload.limit ?? 100,
    }),
  });
  return parseJsonResponse<DatasetMaterializeResponse>(response);
}

export async function browseDatasetAppDbRows(
  formId: string,
  formVersion: string,
  payload: {
    search?: string;
    source?: string;
    outcome?: string;
    result_version?: "current" | "original";
    include_feedback?: boolean;
    feedback_filter?: "all" | "with_feedback" | "without_feedback" | "low_score";
    limit?: number;
  },
): Promise<DatasetSourceRowRecord[]> {
  const params = new URLSearchParams({ form_id: formId, form_version: formVersion });
  const response = await fetch(`${apiBaseUrl}/api/datasets/app-db/browse?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      search: payload.search ?? "",
      source: payload.source ?? "all",
      outcome: payload.outcome ?? "all",
      result_version: payload.result_version ?? "current",
      include_feedback: payload.include_feedback ?? false,
      feedback_filter: payload.feedback_filter ?? "all",
      limit: payload.limit ?? 100,
    }),
  });
  return parseJsonResponse<DatasetSourceRowRecord[]>(response);
}

export async function addDatasetAppDbRows(
  populationId: string,
  payload: {
    review_ids?: string[];
    add_all_filtered?: boolean;
    search?: string;
    source?: string;
    outcome?: string;
    result_version?: "current" | "original";
    include_feedback?: boolean;
    feedback_filter?: "all" | "with_feedback" | "without_feedback" | "low_score";
    limit?: number;
  },
): Promise<DatasetAddCandidatesResponse> {
  const response = await fetch(`${apiBaseUrl}/api/datasets/populations/${populationId}/app-db`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      review_ids: payload.review_ids ?? [],
      add_all_filtered: payload.add_all_filtered ?? false,
      search: payload.search ?? "",
      source: payload.source ?? "all",
      outcome: payload.outcome ?? "all",
      result_version: payload.result_version ?? "current",
      include_feedback: payload.include_feedback ?? false,
      feedback_filter: payload.feedback_filter ?? "all",
      limit: payload.limit ?? 100,
    }),
  });
  return parseJsonResponse<DatasetAddCandidatesResponse>(response);
}

export async function updateDatasetCandidate(
  candidateId: string,
  payload: { included?: boolean; tags?: string[]; sample_reason?: string },
): Promise<DatasetCandidateRecord> {
  const response = await fetch(`${apiBaseUrl}/api/datasets/candidates/${candidateId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<DatasetCandidateRecord>(response);
}

export async function updateDatasetCandidateReference(
  candidateId: string,
  referenceKind: "R1" | "R2",
  payload: {
    result: AuditFormResult;
    reviewer?: string | null;
    source_metadata?: Record<string, unknown> | null;
  },
): Promise<DatasetCandidateRecord> {
  const response = await fetch(`${apiBaseUrl}/api/datasets/candidates/${candidateId}/references/${referenceKind}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<DatasetCandidateRecord>(response);
}

export async function clusterDatasetPopulation(
  populationId: string,
  payload: {
    min_clusters: number;
    max_clusters: number;
    seed: number;
    semantic_weight?: number;
    structured_weight?: number;
  },
): Promise<DatasetClusterResult> {
  const response = await fetch(`${apiBaseUrl}/api/datasets/populations/${populationId}/cluster`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<DatasetClusterResult>(response);
}

export async function sampleDatasetPopulation(
  populationId: string,
  payload: { mode: DatasetSampleMode; size?: number | null; seed: number },
): Promise<DatasetSampleResult> {
  const response = await fetch(`${apiBaseUrl}/api/datasets/populations/${populationId}/sample`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<DatasetSampleResult>(response);
}

export async function publishDatasetPopulation(
  populationId: string,
  payload: { name: string; description?: string; include_only?: boolean },
): Promise<EvalDatasetRecord> {
  const response = await fetch(`${apiBaseUrl}/api/datasets/populations/${populationId}/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<EvalDatasetRecord>(response);
}

export async function listPublishedDatasets(): Promise<EvalDatasetRecord[]> {
  const response = await fetch(`${apiBaseUrl}/api/datasets`, { cache: "no-store" });
  return parseJsonResponse<EvalDatasetRecord[]>(response);
}

export async function listPublishedDatasetRows(
  datasetId: string,
): Promise<PublishedDatasetRow[]> {
  const response = await fetch(`${apiBaseUrl}/api/datasets/${datasetId}/rows`, {
    cache: "no-store",
  });
  return parseJsonResponse<PublishedDatasetRow[]>(response);
}

export async function clonePublishedDataset(
  datasetId: string,
  payload: { name?: string; description?: string } = {},
): Promise<DatasetPopulationRecord> {
  const response = await fetch(`${apiBaseUrl}/api/datasets/${datasetId}/clone`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<DatasetPopulationRecord>(response);
}

export async function getEvalDataset(datasetId: string): Promise<EvalDatasetRecord> {
  const response = await fetch(`${apiBaseUrl}/api/evaluations/datasets/${datasetId}`, {
    cache: "no-store",
  });
  return parseJsonResponse<EvalDatasetRecord>(response);
}

export async function listEvalRuns(): Promise<EvalRunRecord[]> {
  const response = await fetch(`${apiBaseUrl}/api/evaluations/runs`, {
    cache: "no-store",
  });
  return parseJsonResponse<EvalRunRecord[]>(response);
}

export async function createEvalRun(payload: EvalRunPayload): Promise<EvalRunRecord> {
  const response = await fetch(`${apiBaseUrl}/api/evaluations/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<EvalRunRecord>(response);
}

export async function getEvalRun(runId: string): Promise<EvalRunRecord> {
  const response = await fetch(`${apiBaseUrl}/api/evaluations/runs/${runId}`, {
    cache: "no-store",
  });
  return parseJsonResponse<EvalRunRecord>(response);
}

export async function listEvalRunItems(runId: string): Promise<EvalRunItemRecord[]> {
  const response = await fetch(`${apiBaseUrl}/api/evaluations/runs/${runId}/items`, {
    cache: "no-store",
  });
  return parseJsonResponse<EvalRunItemRecord[]>(response);
}

export async function pauseEvalRun(runId: string): Promise<EvalRunRecord> {
  const response = await fetch(`${apiBaseUrl}/api/evaluations/runs/${runId}/pause`, {
    method: "POST",
  });
  return parseJsonResponse<EvalRunRecord>(response);
}

export async function resumeEvalRun(runId: string): Promise<EvalRunRecord> {
  const response = await fetch(`${apiBaseUrl}/api/evaluations/runs/${runId}/resume`, {
    method: "POST",
  });
  return parseJsonResponse<EvalRunRecord>(response);
}

export async function cancelEvalRun(runId: string): Promise<EvalRunRecord> {
  const response = await fetch(`${apiBaseUrl}/api/evaluations/runs/${runId}/cancel`, {
    method: "POST",
  });
  return parseJsonResponse<EvalRunRecord>(response);
}

export async function listOptimizationCases(
  formId: string,
  formVersion: string,
  search = "",
): Promise<OptimizationCaseRecord[]> {
  const params = new URLSearchParams({
    form_id: formId,
    form_version: formVersion,
    search,
  });
  const response = await fetch(`${apiBaseUrl}/api/optimizations/cases?${params.toString()}`, {
    cache: "no-store",
  });
  return parseJsonResponse<OptimizationCaseRecord[]>(response);
}

export async function listOptimizationRuns(): Promise<OptimizationRunRecord[]> {
  const response = await fetch(`${apiBaseUrl}/api/optimizations/runs`, {
    cache: "no-store",
  });
  return parseJsonResponse<OptimizationRunRecord[]>(response);
}

export async function createOptimizationRun(
  payload: OptimizationRunPayload,
): Promise<OptimizationRunRecord> {
  const response = await fetch(`${apiBaseUrl}/api/optimizations/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<OptimizationRunRecord>(response);
}

export async function getOptimizationRun(runId: string): Promise<OptimizationRunRecord> {
  const response = await fetch(`${apiBaseUrl}/api/optimizations/runs/${runId}`, {
    cache: "no-store",
  });
  return parseJsonResponse<OptimizationRunRecord>(response);
}

export async function cancelOptimizationRun(runId: string): Promise<OptimizationRunRecord> {
  const response = await fetch(`${apiBaseUrl}/api/optimizations/runs/${runId}/cancel`, {
    method: "POST",
  });
  return parseJsonResponse<OptimizationRunRecord>(response);
}

export async function getOptimizationDagArtifact(runId: string): Promise<OptimizationDagArtifact> {
  const response = await fetch(`${apiBaseUrl}/api/optimizations/runs/${runId}/artifacts/dag`, {
    cache: "no-store",
  });
  return parseJsonResponse<OptimizationDagArtifact>(response);
}

export function optimizationEventsUrl(runId: string): string {
  return `${apiBaseUrl}/api/optimizations/runs/${runId}/events`;
}

export function optimizationArtifactUrl(runId: string, artifactType: string): string {
  return `${apiBaseUrl}/api/optimizations/runs/${runId}/artifacts/${artifactType}`;
}

export function chatArtifactFileUrl(
  sessionId: string,
  handle: string,
  role: string,
): string {
  return `${apiBaseUrl}/api/chat/artifacts/${encodeURIComponent(sessionId)}/${encodeURIComponent(handle)}/files/${encodeURIComponent(role)}`;
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
