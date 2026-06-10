"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Columns3,
  Copy,
  Database,
  Eye,
  FilePenLine,
  GitBranch,
  Info,
  Layers3,
  Loader2,
  PanelRightOpen,
  Plus,
  RefreshCw,
  Save,
  Search,
  Shuffle,
  X,
} from "lucide-react";

import { AuditResultEditSheet, type AuditResultEditSheetRow } from "@/components/data-table/audit-result-edit-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  addDatasetAppDbRows,
  browseDatasetAppDbRows,
  clusterDatasetPopulation,
  clonePublishedDataset,
  createDatasetPopulation,
  getDatasetPopulation,
  listDatasetPopulations,
  listFormCatalog,
  listPublishedDatasetRows,
  listPublishedDatasets,
  publishDatasetPopulation,
  sampleDatasetPopulation,
  updateDatasetCandidate,
  updateDatasetCandidateReference,
  updateDatasetPopulation,
} from "@/lib/api";
import type {
  AuditFormResult,
  DatasetCandidateRecord,
  DatasetPopulationRecord,
  DatasetReferenceRecord,
  DatasetSampleMode,
  DatasetSourceRowRecord,
  EvalDatasetRecord,
  FormCatalogEntry,
  PublishedDatasetRow,
} from "@/lib/types";

type AppDbResultVersion = "current" | "original";
type SourceSort =
  | "updated_desc"
  | "updated_asc"
  | "claim_asc"
  | "outcome_asc"
  | "issues_desc"
  | "feedback_low_score"
  | "feedback_count_desc";
type DatasetFeedbackFilter = "all" | "with_feedback" | "without_feedback" | "low_score";
type SourceRowColumn =
  | "claim"
  | "source"
  | "outcome"
  | "issues"
  | "drivers"
  | "feedback"
  | "feedback_score"
  | "updated";
type CandidateColumn =
  | "candidate"
  | "refs"
  | "outcome"
  | "issues"
  | "feedback"
  | "cluster"
  | "source";

const defaultSourceColumns: SourceRowColumn[] = [
  "claim",
  "source",
  "outcome",
  "issues",
  "drivers",
  "updated",
];
const defaultCandidateColumns: CandidateColumn[] = [
  "candidate",
  "refs",
  "outcome",
  "issues",
  "cluster",
  "source",
];

const sourceColumnLabels: Record<SourceRowColumn, string> = {
  claim: "Claim",
  source: "Source",
  outcome: "Outcome",
  issues: "Issues",
  drivers: "Drivers",
  feedback: "Feedback",
  feedback_score: "Score",
  updated: "Updated",
};

const candidateColumnLabels: Record<CandidateColumn, string> = {
  candidate: "Candidate",
  refs: "Refs",
  outcome: "Outcome",
  issues: "Issues",
  feedback: "Feedback",
  cluster: "Cluster",
  source: "Source",
};

const sampleModes: Array<{ value: DatasetSampleMode; label: string }> = [
  { value: "all", label: "All included" },
  { value: "random", label: "Random" },
  { value: "outcome", label: "Outcome split" },
  { value: "stratified_outcome_issues", label: "Outcome + issues" },
  { value: "cluster_balanced", label: "Cluster balanced" },
  { value: "diversity", label: "Diversity" },
];

function formKey(form: FormCatalogEntry): string {
  return `${form.id}@${form.version}`;
}

function compactFormLabel(form: FormCatalogEntry): string {
  return `${form.id}@${form.version}`;
}

function metricNumber(metrics: Record<string, unknown>, key: string): number | null {
  const value = metrics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatCurrency(value?: number | null): string {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 0,
    style: "currency",
  }).format(value);
}

function formatFeedbackScore(value?: number | null): string {
  if (value === null || value === undefined) return "-";
  return Number(value).toFixed(1);
}

function sortRows(rows: DatasetSourceRowRecord[], sort: SourceSort): DatasetSourceRowRecord[] {
  return [...rows].sort((first, second) => {
    if (sort === "claim_asc") return first.claim_number.localeCompare(second.claim_number, undefined, { numeric: true });
    if (sort === "outcome_asc") return first.outcome.localeCompare(second.outcome);
    if (sort === "issues_desc") return second.issue_count - first.issue_count;
    if (sort === "feedback_count_desc") return second.feedback_count - first.feedback_count;
    if (sort === "feedback_low_score") {
      const firstScore = first.feedback_min_score ?? Number.POSITIVE_INFINITY;
      const secondScore = second.feedback_min_score ?? Number.POSITIVE_INFINITY;
      return firstScore - secondScore;
    }
    const firstDate = first.updated_at ? new Date(first.updated_at).getTime() : 0;
    const secondDate = second.updated_at ? new Date(second.updated_at).getTime() : 0;
    return sort === "updated_asc" ? firstDate - secondDate : secondDate - firstDate;
  });
}

function feedbackCommentFromMetadata(metadata?: Record<string, unknown> | null): string {
  const feedback = metadata?.feedback;
  if (typeof feedback !== "object" || feedback === null) return "";
  const latest = "latest_comment" in feedback ? feedback.latest_comment : "";
  return typeof latest === "string" ? latest : "";
}

function referenceBadges(candidate: DatasetCandidateRecord) {
  const kinds = new Set(candidate.references.map((reference) => reference.reference_kind));
  return (
    <div className="flex gap-1">
      <Badge variant={kinds.has("R1") ? "secondary" : "outline"}>R1</Badge>
      <Badge variant={kinds.has("R2") ? "secondary" : "outline"}>R2</Badge>
    </div>
  );
}

function hasStaleFlag(value?: Record<string, unknown> | null): boolean {
  return Boolean(value && value.stale);
}

function preferredReference(candidate: DatasetCandidateRecord): DatasetReferenceRecord | null {
  return candidate.references.find((reference) => reference.reference_kind === "R2") ?? candidate.references[0] ?? null;
}

function candidateWasEdited(candidate: DatasetCandidateRecord): boolean {
  const metadata = candidate.metadata ?? {};
  const curation = metadata.curation;
  return Boolean(
    metadata.curated_edited ||
      (typeof curation === "object" && curation !== null && "edited_at" in curation),
  );
}

function buildCandidateEditRow(
  candidate: DatasetCandidateRecord | null,
  referenceKind: "R1" | "R2",
): AuditResultEditSheetRow | null {
  if (!candidate) return null;
  const reference =
    candidate.references.find((item) => item.reference_kind === referenceKind) ??
    preferredReference(candidate);
  if (!reference) return null;
  return {
    reviewId: `dataset-candidate:${candidate.id}:${reference.reference_kind}`,
    title: reference.result.title || candidate.claim_number || candidate.source_record_id,
    formKey: `${reference.result.form_id}@${reference.result.form_version}`,
    edited: candidateWasEdited(candidate),
    finalized: false,
    formStatus: candidateWasEdited(candidate) ? "edited" : "unedited",
    claimNumber: candidate.claim_number,
    form: reference.result,
    feedbackCount: 0,
    feedbackEnabled: false,
    firstFinalizedAt: "",
    lastFinalizedAt: "",
    createdAt: candidate.created_at ?? "",
    updatedAt: candidate.updated_at ?? "",
    source: candidate.source_label || candidate.source_key,
  };
}

export default function DatasetsPage() {
  const [forms, setForms] = useState<FormCatalogEntry[]>([]);
  const [formKeyValue, setFormKeyValue] = useState("");
  const [includeFeedbackSignals, setIncludeFeedbackSignals] = useState(false);
  const [population, setPopulation] = useState<DatasetPopulationRecord | null>(null);
  const [draftPopulations, setDraftPopulations] = useState<DatasetPopulationRecord[]>([]);
  const [draftDrawerOpen, setDraftDrawerOpen] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [publishedDatasets, setPublishedDatasets] = useState<EvalDatasetRecord[]>([]);
  const [selectedPublishedDatasetId, setSelectedPublishedDatasetId] = useState("");
  const [publishedRows, setPublishedRows] = useState<PublishedDatasetRow[]>([]);
  const [publishedDrawerOpen, setPublishedDrawerOpen] = useState(false);

  const [appDbRows, setAppDbRows] = useState<DatasetSourceRowRecord[]>([]);
  const [selectedReviewIds, setSelectedReviewIds] = useState<Set<string>>(() => new Set());
  const [appDbSearch, setAppDbSearch] = useState("");
  const [appDbOutcome, setAppDbOutcome] = useState("all");
  const [appDbSource, setAppDbSource] = useState("all");
  const [appDbSort, setAppDbSort] = useState<SourceSort>("updated_desc");
  const [appDbResultVersion, setAppDbResultVersion] = useState<AppDbResultVersion>("current");
  const [appDbFeedbackFilter, setAppDbFeedbackFilter] = useState<DatasetFeedbackFilter>("all");
  const [sourceVisibleColumns, setSourceVisibleColumns] = useState<SourceRowColumn[]>(defaultSourceColumns);
  const [candidateVisibleColumns, setCandidateVisibleColumns] = useState<CandidateColumn[]>(defaultCandidateColumns);

  const [selectedCandidate, setSelectedCandidate] = useState<DatasetCandidateRecord | null>(null);
  const [editingCandidate, setEditingCandidate] = useState<DatasetCandidateRecord | null>(null);
  const [editingReferenceKind, setEditingReferenceKind] = useState<"R1" | "R2">("R2");
  const [selectedPublishedRow, setSelectedPublishedRow] = useState<PublishedDatasetRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [clusterMin, setClusterMin] = useState(2);
  const [clusterMax, setClusterMax] = useState(6);
  const [sampleMode, setSampleMode] = useState<DatasetSampleMode>("all");
  const [sampleSize, setSampleSize] = useState(10);
  const [seed, setSeed] = useState(0);
  const [publishName, setPublishName] = useState("Curated Dataset");
  const [publishDescription, setPublishDescription] = useState("");

  const [formId, formVersion] = formKeyValue.split("@");
  const selectedForm = forms.find((form) => formKey(form) === formKeyValue);
  const selectedPublishedDataset = publishedDatasets.find((dataset) => dataset.id === selectedPublishedDatasetId);
  const candidates = population?.candidates ?? [];
  const includedCandidates = candidates.filter((candidate) => candidate.included);
  const sortedAppDbRows = useMemo(() => sortRows(appDbRows, appDbSort), [appDbRows, appDbSort]);
  const sourceOptions = useMemo(
    () => Array.from(new Set(appDbRows.map((row) => row.source).filter(Boolean))).sort(),
    [appDbRows],
  );
  const analysisStale = hasStaleFlag(population?.cluster_config) || hasStaleFlag(population?.sample_config);
  const candidateEditRow = buildCandidateEditRow(editingCandidate, editingReferenceKind);

  const refreshPopulation = useCallback(async (populationId: string) => {
    const nextPopulation = await getDatasetPopulation(populationId);
    setPopulation(nextPopulation);
    setDraftName(nextPopulation.name);
    setDraftDescription(nextPopulation.description);
    if (nextPopulation.status === "draft") {
      setDraftPopulations((current) => {
        const withoutCurrent = current.filter((item) => item.id !== nextPopulation.id);
        return [nextPopulation, ...withoutCurrent].sort((first, second) => {
          const firstDate = first.updated_at ? new Date(first.updated_at).getTime() : 0;
          const secondDate = second.updated_at ? new Date(second.updated_at).getTime() : 0;
          return secondDate - firstDate;
        });
      });
    }
    return nextPopulation;
  }, []);

  const loadPublishedRows = useCallback(async (datasetId: string) => {
    if (!datasetId) {
      setPublishedRows([]);
      return;
    }
    const rows = await listPublishedDatasetRows(datasetId);
    setPublishedRows(rows);
  }, []);

  const loadForForm = useCallback(async () => {
    if (!formId || !formVersion) return;
    setLoading(true);
    setError("");
    try {
      const [nextPopulations, nextPublished] = await Promise.all([
        listDatasetPopulations(formId, formVersion),
        listPublishedDatasets(),
      ]);
      const scopedPublished = nextPublished.filter(
        (dataset) => dataset.form_id === formId && dataset.form_version === formVersion,
      );
      const drafts = nextPopulations.filter((item) => item.status === "draft");
      const currentDraft =
        population?.status === "draft" && drafts.some((item) => item.id === population.id)
          ? population.id
          : drafts[0]?.id;

      setDraftPopulations(drafts);
      setPublishedDatasets(scopedPublished);
      setSelectedPublishedDatasetId((current) =>
        current && scopedPublished.some((dataset) => dataset.id === current)
          ? current
          : scopedPublished[0]?.id ?? "",
      );
      setAppDbRows([]);
      setSelectedReviewIds(new Set());
      if (currentDraft) {
        await refreshPopulation(currentDraft);
      } else {
        setPopulation(null);
        setDraftName("");
        setDraftDescription("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load datasets.");
    } finally {
      setLoading(false);
    }
  }, [
    formId,
    formVersion,
    population?.id,
    population?.status,
    refreshPopulation,
  ]);

  useEffect(() => {
    async function loadForms() {
      setLoading(true);
      setError("");
      try {
        const nextForms = await listFormCatalog();
        setForms(nextForms);
        setFormKeyValue((current) => current || (nextForms[0] ? formKey(nextForms[0]) : ""));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load form catalog.");
      } finally {
        setLoading(false);
      }
    }
    void loadForms();
  }, []);

  useEffect(() => {
    void loadForForm();
  }, [loadForForm]);

  useEffect(() => {
    if (!includeFeedbackSignals) {
      setAppDbFeedbackFilter("all");
      if (appDbSort === "feedback_count_desc" || appDbSort === "feedback_low_score") {
        setAppDbSort("updated_desc");
      }
    }
  }, [appDbSort, includeFeedbackSignals]);

  useEffect(() => {
    let canceled = false;
    async function runLoad() {
      if (!selectedPublishedDatasetId) {
        setPublishedRows([]);
        return;
      }
      try {
        const rows = await listPublishedDatasetRows(selectedPublishedDatasetId);
        if (!canceled) setPublishedRows(rows);
      } catch (err) {
        if (!canceled) setError(err instanceof Error ? err.message : "Failed to load published dataset rows.");
      }
    }
    void runLoad();
    return () => {
      canceled = true;
    };
  }, [selectedPublishedDatasetId]);

  const run = async (action: () => Promise<void>, success: string) => {
    setWorking(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(success);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setWorking(false);
    }
  };

  const createDraft = async () => {
    if (!selectedForm) return null;
    const next = await createDatasetPopulation({
      name: `${selectedForm.id} ${selectedForm.version} Draft`,
      description: "Draft curated dataset.",
      form_id: selectedForm.id,
      form_version: selectedForm.version,
    });
    setPopulation(next);
    setDraftPopulations((current) => [next, ...current.filter((item) => item.id !== next.id)]);
    setDraftName(next.name);
    setDraftDescription(next.description);
    setPublishName(`${selectedForm.title} Curated Dataset`);
    setPublishDescription("");
    return next;
  };

  const ensureDraft = async () => {
    if (population?.status === "draft") return population;
    return createDraft();
  };

  const startNewDraft = async () => {
    await run(async () => {
      await createDraft();
    }, "New draft dataset started.");
  };

  const saveDraft = async () => {
    if (!population || population.status !== "draft") return;
    await run(async () => {
      const updated = await updateDatasetPopulation(population.id, {
        name: draftName.trim() || population.name,
        description: draftDescription,
      });
      await refreshPopulation(updated.id);
    }, "Draft details saved.");
  };

  const resumeDraft = async (populationId: string) => {
    await run(async () => {
      await refreshPopulation(populationId);
      setDraftDrawerOpen(false);
    }, "Draft resumed.");
  };

  const refreshAppDbRows = async () => {
    if (!formId || !formVersion) return;
    await run(async () => {
      const rows = await browseDatasetAppDbRows(formId, formVersion, {
        search: appDbSearch,
        outcome: appDbOutcome,
        source: appDbSource,
        result_version: appDbResultVersion,
        include_feedback: includeFeedbackSignals,
        feedback_filter: includeFeedbackSignals ? appDbFeedbackFilter : "all",
        limit: 200,
      });
      setAppDbRows(rows);
      setSelectedReviewIds(new Set());
    }, "Application DB rows loaded.");
  };

  const addAppDbRows = async () => {
    await run(async () => {
      const draft = await ensureDraft();
      if (!draft) return;
      const response = await addDatasetAppDbRows(draft.id, {
        review_ids: Array.from(selectedReviewIds),
        add_all_filtered: false,
        search: appDbSearch,
        outcome: appDbOutcome,
        source: appDbSource,
        result_version: appDbResultVersion,
        include_feedback: includeFeedbackSignals,
        feedback_filter: includeFeedbackSignals ? appDbFeedbackFilter : "all",
        limit: 200,
      });
      await refreshPopulation(response.population.id);
      setSelectedReviewIds(new Set());
    }, "Selected application rows added.");
  };

  const toggleCandidate = async (candidate: DatasetCandidateRecord) => {
    await run(async () => {
      await updateDatasetCandidate(candidate.id, { included: !candidate.included });
      await refreshPopulation(candidate.population_id);
    }, candidate.included ? "Candidate removed from draft." : "Candidate restored to draft.");
  };

  const openCandidateEditor = (candidate: DatasetCandidateRecord, referenceKind?: "R1" | "R2") => {
    const kind = referenceKind ?? (candidate.references.some((reference) => reference.reference_kind === "R2") ? "R2" : "R1");
    setEditingCandidate(candidate);
    setEditingReferenceKind(kind);
  };

  const saveCandidateReference = async (form: AuditFormResult) => {
    if (!editingCandidate) return;
    const currentReference =
      editingCandidate.references.find((reference) => reference.reference_kind === editingReferenceKind) ??
      preferredReference(editingCandidate);
    await updateDatasetCandidateReference(editingCandidate.id, editingReferenceKind, {
      result: form,
      reviewer: currentReference?.reviewer ?? "dataset-curator",
      source_metadata: currentReference?.source_metadata ?? {},
    });
    const nextPopulation = await refreshPopulation(editingCandidate.population_id);
    const nextCandidate = nextPopulation.candidates?.find((candidate) => candidate.id === editingCandidate.id) ?? null;
    if (selectedCandidate?.id === editingCandidate.id) setSelectedCandidate(nextCandidate);
    setEditingCandidate(null);
    setNotice("Candidate reference updated. Cluster and sample analysis should be rerun before publishing.");
  };

  const cluster = async () => {
    if (!population) return;
    await run(async () => {
      const result = await clusterDatasetPopulation(population.id, {
        min_clusters: clusterMin,
        max_clusters: clusterMax,
        seed,
      });
      await refreshPopulation(result.population.id);
    }, "Cluster labels added.");
  };

  const sample = async () => {
    if (!population) return;
    await run(async () => {
      const result = await sampleDatasetPopulation(population.id, {
        mode: sampleMode,
        size: sampleMode === "all" ? null : sampleSize,
        seed,
      });
      await refreshPopulation(result.population.id);
    }, "Candidate pool updated from sample.");
  };

  const publish = async () => {
    if (!population) return;
    await run(async () => {
      const published = await publishDatasetPopulation(population.id, {
        name: publishName,
        description: publishDescription,
        include_only: true,
      });
      const [nextPopulations, nextPublished] = await Promise.all([
        listDatasetPopulations(formId, formVersion),
        listPublishedDatasets(),
      ]);
      const scopedPublished = nextPublished.filter(
        (dataset) => dataset.form_id === formId && dataset.form_version === formVersion,
      );
      const drafts = nextPopulations.filter((item) => item.status === "draft");
      setPublishedDatasets(scopedPublished);
      setSelectedPublishedDatasetId(published.id);
      setDraftPopulations(drafts);
      setPopulation(drafts[0] ?? null);
      await loadPublishedRows(published.id);
    }, "Dataset published.");
  };

  const cloneToDraft = async (dataset: EvalDatasetRecord) => {
    await run(async () => {
      const cloned = await clonePublishedDataset(dataset.id, {
        name: `${dataset.name} Draft`,
        description: dataset.description || `Draft cloned from ${dataset.name}.`,
      });
      await refreshPopulation(cloned.id);
      setDraftDrawerOpen(false);
      setPublishedDrawerOpen(false);
    }, "Published dataset cloned into an editable draft.");
  };

  const availableCandidateColumns = includeFeedbackSignals
    ? (["candidate", "refs", "outcome", "issues", "feedback", "cluster", "source"] as const)
    : (["candidate", "refs", "outcome", "issues", "cluster", "source"] as const);
  const activeCandidateColumns = availableCandidateColumns.filter((column) =>
    candidateVisibleColumns.includes(column),
  );

  return (
    <div className="mx-auto w-full max-w-[1680px] space-y-4 p-4 lg:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Datasets</h1>
          <p className="text-sm text-muted-foreground">
            Build source candidates, curate a draft pool, then publish a reusable form-bound dataset.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => setDraftDrawerOpen(true)}>
            <PanelRightOpen className="h-4 w-4" />
            Drafts
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => setPublishedDrawerOpen(true)}>
            <PanelRightOpen className="h-4 w-4" />
            Published
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => void loadForForm()} disabled={loading || working}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="flex items-start gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          {notice}
        </div>
      ) : null}

        <Card>
          <CardHeader className="pb-3">
          <CardTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
            <span className="flex items-center gap-2">
              <Database className="h-4 w-4 text-primary" />
              Form Scope
            </span>
            <FeedbackSignalsToggle
              checked={includeFeedbackSignals}
              onChange={setIncludeFeedbackSignals}
            />
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-[minmax(260px,1.3fr)_minmax(260px,1fr)_auto]">
            <label className="grid min-w-0 gap-1.5">
              <span className="text-xs font-medium text-muted-foreground">Registered Form</span>
              <select
                value={formKeyValue}
                onChange={(event) => {
                  setFormKeyValue(event.target.value);
                  setPopulation(null);
                  setAppDbRows([]);
                  setPublishedRows([]);
                }}
                className="h-10 w-full min-w-0 rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {forms.map((form) => (
                  <option key={formKey(form)} value={formKey(form)}>
                    {compactFormLabel(form)}
                  </option>
                ))}
              </select>
              {selectedForm ? (
                <p className="truncate text-xs text-muted-foreground" title={selectedForm.title}>
                  {selectedForm.title}
                </p>
              ) : null}
            </label>

            <label className="grid min-w-0 gap-1.5">
              <span className="text-xs font-medium text-muted-foreground">Selected Published Dataset</span>
              <select
                value={selectedPublishedDatasetId}
                onChange={(event) => setSelectedPublishedDatasetId(event.target.value)}
                className="h-10 w-full min-w-0 rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {publishedDatasets.length === 0 ? <option value="">No published datasets</option> : null}
                {publishedDatasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name}
                  </option>
                ))}
              </select>
              <p className="truncate text-xs text-muted-foreground">
                {selectedPublishedDataset
                  ? `${selectedPublishedDataset.case_count} cases · ${selectedPublishedDataset.r2_count} R2 refs`
                  : "Publish a draft or open the drawer to review saved datasets."}
              </p>
            </label>

            <div className="flex items-start gap-2 lg:pt-6">
              <Button
                type="button"
                onClick={() => void startNewDraft()}
                disabled={working || !selectedForm}
                title="Start a new draft candidate pool for the selected form."
                aria-label="Start a new draft candidate pool for the selected form"
              >
                <Plus className="h-4 w-4" />
                New Draft
              </Button>
            </div>
          </div>

          {population?.status === "draft" ? (
            <div className="grid gap-3 rounded-md border bg-secondary/20 p-3 lg:grid-cols-[minmax(220px,0.8fr)_minmax(280px,1.2fr)_auto]">
              <label className="grid min-w-0 gap-1.5">
                <span className="text-xs font-medium text-muted-foreground">Active Draft</span>
                <Input value={draftName} onChange={(event) => setDraftName(event.target.value)} placeholder="Draft name" />
              </label>
              <label className="grid min-w-0 gap-1.5">
                <span className="text-xs font-medium text-muted-foreground">Description</span>
                <Textarea
                  value={draftDescription}
                  onChange={(event) => setDraftDescription(event.target.value)}
                  placeholder="Draft purpose, intended eval split, SME notes..."
                  className="min-h-10"
                />
              </label>
              <div className="flex items-end gap-2">
                {analysisStale ? <Badge variant="warning">Analysis stale</Badge> : null}
                <Button type="button" variant="outline" onClick={() => void saveDraft()} disabled={working}>
                  <Save className="h-4 w-4" />
                  Save Draft
                </Button>
              </div>
            </div>
          ) : (
            <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
              Start a draft or resume one from the drawer to curate candidates for this form.
            </p>
          )}
        </CardContent>
      </Card>

      <section className="space-y-4">
        <SectionTitle step="1" title="Source Candidates" detail="Load completed application reviews, then add selected rows into the draft pool." />

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Search className="h-4 w-4 text-primary" />
              App DB Source
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-2 xl:grid-cols-[minmax(220px,1fr)_140px_140px_140px_150px_150px_auto]">
              <Input
                value={appDbSearch}
                onChange={(event) => setAppDbSearch(event.target.value)}
                placeholder="Search reviews, claims, comments..."
              />
              <select
                value={appDbOutcome}
                onChange={(event) => setAppDbOutcome(event.target.value)}
                className="h-10 rounded-md border border-input bg-background px-3 text-sm outline-none"
              >
                <option value="all">All outcomes</option>
                <option value="Meets">Meets</option>
                <option value="Does Not Meet">Does Not Meet</option>
              </select>
              <select
                value={appDbSource}
                onChange={(event) => setAppDbSource(event.target.value)}
                className="h-10 rounded-md border border-input bg-background px-3 text-sm outline-none"
              >
                <option value="all">All sources</option>
                {sourceOptions.map((source) => (
                  <option key={source} value={source}>
                    {source}
                  </option>
                ))}
              </select>
              <select
                value={appDbResultVersion}
                onChange={(event) => setAppDbResultVersion(event.target.value as AppDbResultVersion)}
                className="h-10 rounded-md border border-input bg-background px-3 text-sm outline-none"
              >
                <option value="current">Current</option>
                <option value="original">Original</option>
              </select>
              {includeFeedbackSignals ? (
                <select
                  value={appDbFeedbackFilter}
                  onChange={(event) => setAppDbFeedbackFilter(event.target.value as DatasetFeedbackFilter)}
                  className="h-10 rounded-md border border-input bg-background px-3 text-sm outline-none"
                >
                  <option value="all">All feedback</option>
                  <option value="with_feedback">Has feedback</option>
                  <option value="without_feedback">No feedback</option>
                  <option value="low_score">Low score</option>
                </select>
              ) : null}
              <SortSelect value={appDbSort} onChange={setAppDbSort} includeFeedback={includeFeedbackSignals} />
              <Button type="button" variant="outline" onClick={() => void refreshAppDbRows()} disabled={working}>
                Load Rows
              </Button>
            </div>
            <SourceRowsTable
              rows={sortedAppDbRows}
              emptyText="No app DB rows match the current form and filters."
              selection={selectedReviewIds}
              selectionKey={(row) => row.review_id}
              onSelectionChange={setSelectedReviewIds}
              visibleColumns={sourceVisibleColumns}
              onVisibleColumnsChange={setSourceVisibleColumns}
              includeFeedback={includeFeedbackSignals}
            />
            <SourceActions
              selectedCount={selectedReviewIds.size}
              totalCount={appDbRows.length}
              disabled={working}
              onSelectAll={() => setSelectedReviewIds(new Set(appDbRows.map((row) => row.review_id).filter(Boolean)))}
              onClearSelection={() => setSelectedReviewIds(new Set())}
              onAddSelected={() => void addAppDbRows()}
            />
          </CardContent>
        </Card>
      </section>

      <section className="space-y-4">
        <SectionTitle step="2" title="Candidate Pool" detail="Remove rows you do not want, add cluster labels, or sample down to the draft set you plan to publish." />
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center justify-between gap-2 text-base">
              <span className="flex items-center gap-2">
                <Layers3 className="h-4 w-4 text-primary" />
                Draft Candidates
                {analysisStale ? <Badge variant="warning">Analysis stale</Badge> : null}
              </span>
              <span className="text-xs font-normal text-muted-foreground">
                {population?.included_count ?? 0} kept / {population?.candidate_count ?? 0} total
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-2 lg:grid-cols-[repeat(5,minmax(120px,1fr))_auto_auto]">
              <NumberControl label="Min clusters" value={clusterMin} min={1} max={25} onChange={setClusterMin} />
              <NumberControl label="Max clusters" value={clusterMax} min={1} max={50} onChange={setClusterMax} />
              <label className="grid gap-1">
                <span className="text-[11px] font-semibold uppercase text-muted-foreground">Sample</span>
                <select
                  value={sampleMode}
                  onChange={(event) => setSampleMode(event.target.value as DatasetSampleMode)}
                  className="h-10 rounded-md border border-input bg-background px-3 text-sm outline-none"
                >
                  {sampleModes.map((mode) => (
                    <option key={mode.value} value={mode.value}>
                      {mode.label}
                    </option>
                  ))}
                </select>
              </label>
              <NumberControl label="Size" value={sampleSize} min={1} onChange={setSampleSize} />
              <NumberControl label="Seed" value={seed} onChange={setSeed} />
              <div className="flex items-end">
                <Button type="button" variant="outline" onClick={() => void cluster()} disabled={!population || working || includedCandidates.length < 2}>
                  <GitBranch className="h-4 w-4" />
                  Cluster
                </Button>
              </div>
              <div className="flex items-end">
                <Button type="button" variant="outline" onClick={() => void sample()} disabled={!population || working || candidates.length === 0}>
                  <Shuffle className="h-4 w-4" />
                  Sample
                </Button>
              </div>
            </div>
            <div className="flex justify-end">
              <ColumnPicker
                options={availableCandidateColumns}
                labels={candidateColumnLabels}
                visible={candidateVisibleColumns}
                onChange={setCandidateVisibleColumns}
              />
            </div>
            <div className="max-h-[520px] overflow-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-secondary">
                  <tr className="text-left text-xs text-muted-foreground">
                    <th className="w-20 px-3 py-2">Keep</th>
                    {activeCandidateColumns.map((column) => (
                      <th key={column} className={column === "issues" ? "px-3 py-2 text-right" : "px-3 py-2"}>
                        {candidateColumnLabels[column]}
                      </th>
                    ))}
                    <th className="w-24 px-3 py-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {candidates.map((candidate) => (
                    <tr key={candidate.id} className={candidate.included ? "bg-card/50" : "bg-muted/30 text-muted-foreground"}>
                      <td className="px-3 py-2">
                        <Button
                          type="button"
                          variant={candidate.included ? "outline" : "ghost"}
                          size="sm"
                          onClick={() => void toggleCandidate(candidate)}
                          className="h-8"
                        >
                          {candidate.included ? "Keep" : "Restore"}
                        </Button>
                      </td>
                      {activeCandidateColumns.map((column) => (
                        <CandidateCell key={column} candidate={candidate} column={column} />
                      ))}
                      <td className="px-3 py-2">
                        <div className="flex justify-end gap-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => openCandidateEditor(candidate)}
                            disabled={population?.status !== "draft" || candidate.references.length === 0}
                            title="Edit reference"
                            aria-label="Edit reference"
                          >
                            <FilePenLine className="h-4 w-4" />
                          </Button>
                          <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => setSelectedCandidate(candidate)}>
                            <Eye className="h-4 w-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {candidates.length === 0 ? (
                    <tr>
                      <td colSpan={activeCandidateColumns.length + 2} className="px-3 py-8 text-center text-sm text-muted-foreground">
                        Load source rows above, then add selected or all loaded rows into the draft pool.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="space-y-4">
        <SectionTitle step="3" title="Curated Dataset" detail="Publish the kept candidates, then inspect the selected published dataset in the same view." />
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center justify-between gap-2 text-base">
              <span>Publish Draft</span>
              <span className="text-xs font-normal text-muted-foreground">
                {population?.included_count ?? 0} candidates ready
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 lg:grid-cols-[minmax(220px,1fr)_minmax(280px,1.5fr)_auto]">
              <Input value={publishName} onChange={(event) => setPublishName(event.target.value)} placeholder="Dataset name" />
              <Input value={publishDescription} onChange={(event) => setPublishDescription(event.target.value)} placeholder="Dataset description" />
              <Button type="button" onClick={() => void publish()} disabled={!population || working || includedCandidates.length === 0}>
                Publish Dataset
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              <MiniMetric label="Kept" value={String(population?.included_count ?? 0)} />
              <MiniMetric label="Clusters" value={String(population?.clustered_count ?? 0)} />
              <MiniMetric label="R1 refs" value={String(population?.r1_count ?? 0)} />
              <MiniMetric label="R2 refs" value={String(population?.r2_count ?? 0)} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center justify-between gap-2 text-base">
              <span>Selected Published Dataset</span>
              {selectedPublishedDataset ? (
                <Badge variant={selectedPublishedDataset.source_kind === "curated" ? "success" : "outline"}>
                  {selectedPublishedDataset.case_count} cases
                </Badge>
              ) : null}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {selectedPublishedDataset ? (
              <div className="flex flex-wrap items-center gap-2">
                <p className="min-w-0 flex-1 truncate text-sm font-medium">{selectedPublishedDataset.name}</p>
                <Badge variant="outline">{selectedPublishedDataset.form_id}@{selectedPublishedDataset.form_version}</Badge>
                <Badge variant="secondary">R1 {selectedPublishedDataset.r1_count}</Badge>
                <Badge variant="secondary">R2 {selectedPublishedDataset.r2_count}</Badge>
                <Button type="button" variant="outline" size="sm" onClick={() => void cloneToDraft(selectedPublishedDataset)} disabled={working}>
                  <Copy className="h-4 w-4" />
                  Clone to Draft
                </Button>
              </div>
            ) : null}
            <PublishedRowsTable rows={publishedRows} onView={setSelectedPublishedRow} />
          </CardContent>
        </Card>
      </section>

      <CandidateDrawer
        candidate={selectedCandidate}
        onClose={() => setSelectedCandidate(null)}
        onEditReference={(candidate, referenceKind) => openCandidateEditor(candidate, referenceKind)}
      />
      <PublishedRowDrawer row={selectedPublishedRow} onClose={() => setSelectedPublishedRow(null)} />
      <DraftDatasetsDrawer
        open={draftDrawerOpen}
        populations={draftPopulations}
        selectedId={population?.id ?? ""}
        onResume={(populationId) => void resumeDraft(populationId)}
        onClose={() => setDraftDrawerOpen(false)}
      />
      <PublishedDatasetsDrawer
        open={publishedDrawerOpen}
        datasets={publishedDatasets}
        selectedId={selectedPublishedDatasetId}
        onSelect={(datasetId) => {
          setSelectedPublishedDatasetId(datasetId);
          setPublishedDrawerOpen(false);
        }}
        onClone={(dataset) => void cloneToDraft(dataset)}
        onClose={() => setPublishedDrawerOpen(false)}
      />
      <AuditResultEditSheet
        row={candidateEditRow}
        onClose={() => setEditingCandidate(null)}
        onSubmit={saveCandidateReference}
      />
      {working ? (
        <div className="fixed bottom-4 right-4 flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm shadow-lg">
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
          Working
        </div>
      ) : null}
    </div>
  );
}

function SectionTitle({ step, title, detail }: { step: string; title: string; detail: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary text-sm font-semibold text-primary-foreground">
        {step}
      </span>
      <div className="min-w-0">
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground">{detail}</p>
      </div>
    </div>
  );
}

function FeedbackSignalsToggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const tooltip = "Add feedback filters and columns for app DB rows and candidates.";

  return (
    <div className="flex items-center gap-2 text-xs font-medium">
      <span className="text-muted-foreground">Feedback signals</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        title={tooltip}
        onClick={() => onChange(!checked)}
        className={[
          "relative h-5 w-9 rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          checked ? "border-primary bg-primary" : "border-input bg-secondary",
        ].join(" ")}
      >
        <span
          className={[
            "absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-background shadow-sm transition-transform",
            checked ? "translate-x-4" : "translate-x-0",
          ].join(" ")}
        />
      </button>
      <span title={tooltip} aria-label={tooltip}>
        <Info className="h-3.5 w-3.5 text-muted-foreground" />
      </span>
    </div>
  );
}

function ColumnPicker<T extends string,>({
  options,
  labels,
  visible,
  onChange,
}: {
  options: readonly T[];
  labels: Record<T, string>;
  visible: T[];
  onChange: (visible: T[]) => void;
}) {
  const visibleSet = new Set(visible);
  const toggle = (column: T, checked: boolean) => {
    const next = checked
      ? [...visible.filter((item) => item !== column), column]
      : visible.filter((item) => item !== column);
    onChange(next);
  };

  return (
    <details className="relative">
      <summary className="inline-flex h-8 cursor-pointer list-none items-center justify-center gap-1.5 rounded-md border border-input bg-background px-3 text-xs font-medium transition-colors hover:bg-secondary [&::-webkit-details-marker]:hidden">
        <Columns3 className="h-3.5 w-3.5" />
        Columns
      </summary>
      <div className="absolute right-0 z-30 mt-2 w-56 rounded-md border bg-card p-2 shadow-lg">
        {options.map((option) => (
          <label key={option} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-secondary/60">
            <input
              type="checkbox"
              checked={visibleSet.has(option)}
              onChange={(event) => toggle(option, event.target.checked)}
              className="h-4 w-4 accent-primary"
            />
            <span className="truncate">{labels[option]}</span>
          </label>
        ))}
      </div>
    </details>
  );
}

function SortSelect({
  value,
  onChange,
  includeFeedback = false,
}: {
  value: SourceSort;
  onChange: (value: SourceSort) => void;
  includeFeedback?: boolean;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value as SourceSort)}
      className="h-10 rounded-md border border-input bg-background px-3 text-sm outline-none"
    >
      <option value="updated_desc">Newest</option>
      <option value="updated_asc">Oldest</option>
      <option value="claim_asc">Claim</option>
      <option value="outcome_asc">Outcome</option>
      <option value="issues_desc">Issues</option>
      {includeFeedback ? <option value="feedback_low_score">Low feedback score</option> : null}
      {includeFeedback ? <option value="feedback_count_desc">Most feedback</option> : null}
    </select>
  );
}

function NumberControl({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="grid gap-1">
      <span className="text-[11px] font-semibold uppercase text-muted-foreground">{label}</span>
      <Input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={(event) => onChange(Number(event.target.value) || min || 0)}
      />
    </label>
  );
}

function SourceRowsTable({
  rows,
  emptyText,
  selection,
  selectionKey,
  onSelectionChange,
  visibleColumns,
  onVisibleColumnsChange,
  includeFeedback,
}: {
  rows: DatasetSourceRowRecord[];
  emptyText: string;
  selection: Set<string>;
  selectionKey: (row: DatasetSourceRowRecord) => string;
  onSelectionChange: (selection: Set<string>) => void;
  visibleColumns: SourceRowColumn[];
  onVisibleColumnsChange: (columns: SourceRowColumn[]) => void;
  includeFeedback: boolean;
}) {
  const availableColumns = includeFeedback
    ? ([
        "claim",
        "source",
        "outcome",
        "issues",
        "drivers",
        "feedback",
        "feedback_score",
        "updated",
      ] as const)
    : (["claim", "source", "outcome", "issues", "drivers", "updated"] as const);
  const activeColumns = availableColumns.filter((column) => visibleColumns.includes(column));
  const toggle = (key: string, checked: boolean) => {
    const next = new Set(selection);
    if (checked) next.add(key);
    else next.delete(key);
    onSelectionChange(next);
  };

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <ColumnPicker
          options={availableColumns}
          labels={sourceColumnLabels}
          visible={visibleColumns}
          onChange={onVisibleColumnsChange}
        />
      </div>
      <div className="max-h-80 overflow-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-secondary">
            <tr className="text-left text-xs text-muted-foreground">
              <th className="w-10 px-3 py-2">Add</th>
              {activeColumns.map((column) => (
                <th
                  key={column}
                  className={column === "issues" || column === "drivers" || column === "feedback_score" ? "px-3 py-2 text-right" : "px-3 py-2"}
                >
                  {sourceColumnLabels[column]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((row) => {
              const key = selectionKey(row);
              return (
                <tr key={row.source_record_id} className="bg-card/50">
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selection.has(key)}
                      onChange={(event) => toggle(key, event.target.checked)}
                      className="h-4 w-4 accent-primary"
                    />
                  </td>
                  {activeColumns.map((column) => (
                    <SourceRowCell key={column} row={row} column={column} />
                  ))}
                </tr>
              );
            })}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={activeColumns.length + 1} className="px-3 py-8 text-center text-sm text-muted-foreground">
                  {emptyText}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SourceRowCell({ row, column }: { row: DatasetSourceRowRecord; column: SourceRowColumn }) {
  if (column === "claim") {
    return (
      <td className="px-3 py-2">
        <p className="font-medium">{row.claim_number || row.source_record_id.slice(0, 12)}</p>
        <p className="line-clamp-1 text-xs text-muted-foreground">{row.title}</p>
      </td>
    );
  }
  if (column === "source") {
    return <td className="px-3 py-2"><Badge variant="secondary">{row.source_label || row.source}</Badge></td>;
  }
  if (column === "outcome") {
    return (
      <td className="px-3 py-2">
        <Badge variant={row.outcome === "Meets" ? "success" : "danger"}>{row.outcome || "-"}</Badge>
      </td>
    );
  }
  if (column === "issues") return <td className="px-3 py-2 text-right tabular-nums">{row.issue_count}</td>;
  if (column === "drivers") return <td className="px-3 py-2 text-right tabular-nums">{row.driver_count}</td>;
  if (column === "feedback") {
    return (
      <td className="max-w-[260px] px-3 py-2">
        <Badge variant={row.feedback_count ? "warning" : "outline"}>{row.feedback_count} item{row.feedback_count === 1 ? "" : "s"}</Badge>
        {row.feedback_latest_comment ? (
          <p className="mt-1 line-clamp-1 text-xs text-muted-foreground" title={row.feedback_latest_comment}>
            {row.feedback_latest_comment}
          </p>
        ) : null}
      </td>
    );
  }
  if (column === "feedback_score") {
    return (
      <td className="px-3 py-2 text-right tabular-nums">
        {row.feedback_count ? formatFeedbackScore(row.feedback_min_score) : "-"}
      </td>
    );
  }
  return <td className="px-3 py-2 text-xs text-muted-foreground">{formatDate(row.updated_at)}</td>;
}

function CandidateCell({ candidate, column }: { candidate: DatasetCandidateRecord; column: CandidateColumn }) {
  if (column === "candidate") {
    return (
      <td className="px-3 py-2">
        <p className="font-medium">{candidate.claim_number}</p>
        <p className="line-clamp-1 text-xs text-muted-foreground">{candidate.sample_reason || candidate.instructions}</p>
      </td>
    );
  }
  if (column === "refs") return <td className="px-3 py-2">{referenceBadges(candidate)}</td>;
  if (column === "outcome") {
    return (
      <td className="px-3 py-2">
        <Badge variant={candidate.metrics.outcome === "Meets" ? "success" : "danger"}>
          {String(candidate.metrics.outcome ?? "-")}
        </Badge>
      </td>
    );
  }
  if (column === "issues") {
    return <td className="px-3 py-2 text-right tabular-nums">{metricNumber(candidate.metrics, "issue_count") ?? 0}</td>;
  }
  if (column === "feedback") {
    const count = metricNumber(candidate.metrics, "feedback_count") ?? 0;
    const minScore = metricNumber(candidate.metrics, "feedback_min_score");
    const comment = feedbackCommentFromMetadata(candidate.metadata);
    return (
      <td className="max-w-[280px] px-3 py-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant={count ? "warning" : "outline"}>{count} item{count === 1 ? "" : "s"}</Badge>
          {count ? <Badge variant="outline">low {formatFeedbackScore(minScore)}</Badge> : null}
        </div>
        {comment ? <p className="mt-1 line-clamp-1 text-xs text-muted-foreground" title={comment}>{comment}</p> : null}
      </td>
    );
  }
  if (column === "cluster") {
    return (
      <td className="px-3 py-2">
        {candidate.cluster_id === null || candidate.cluster_id === undefined ? (
          <span className="text-xs text-muted-foreground">-</span>
        ) : (
          <Badge variant="outline">C{candidate.cluster_id}</Badge>
        )}
      </td>
    );
  }
  return (
    <td className="px-3 py-2">
      <Badge variant="secondary">{candidate.source_label || candidate.source_key}</Badge>
    </td>
  );
}

function SourceActions({
  selectedCount,
  totalCount,
  disabled,
  onSelectAll,
  onClearSelection,
  onAddSelected,
  secondaryLabel,
  onSecondarySelected,
}: {
  selectedCount: number;
  totalCount: number;
  disabled: boolean;
  onSelectAll: () => void;
  onClearSelection: () => void;
  onAddSelected: () => void;
  secondaryLabel?: string;
  onSecondarySelected?: () => void;
}) {
  const allSelected = totalCount > 0 && selectedCount >= totalCount;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onSelectAll} disabled={disabled || totalCount === 0 || allSelected}>
          Select All
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onClearSelection} disabled={disabled || selectedCount === 0}>
          Unselect All
        </Button>
      </div>
      <div className="flex flex-wrap gap-2">
        {secondaryLabel && onSecondarySelected ? (
          <Button type="button" variant="outline" onClick={onSecondarySelected} disabled={disabled || selectedCount === 0}>
            {secondaryLabel}
          </Button>
        ) : null}
        <Button type="button" onClick={onAddSelected} disabled={disabled || selectedCount === 0}>
          Add Selected ({selectedCount})
        </Button>
      </div>
    </div>
  );
}

function PublishedRowsTable({
  rows,
  onView,
}: {
  rows: PublishedDatasetRow[];
  onView: (row: PublishedDatasetRow) => void;
}) {
  return (
    <div className="max-h-96 overflow-auto rounded-md border">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-secondary">
          <tr className="text-left text-xs text-muted-foreground">
            <th className="px-3 py-2">Claim</th>
            <th className="px-3 py-2">Ref</th>
            <th className="px-3 py-2">Outcome</th>
            <th className="px-3 py-2">Cluster</th>
            <th className="px-3 py-2">Source</th>
            <th className="w-12 px-3 py-2"></th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {rows.map((row) => (
            <tr key={row.ground_truth_id} className="bg-card/50">
              <td className="px-3 py-2">
                <p className="font-medium">{row.claim_number || row.case_id.slice(0, 8)}</p>
                <p className="line-clamp-1 text-xs text-muted-foreground">{row.dataset_name}</p>
              </td>
              <td className="px-3 py-2"><Badge variant="outline">{row.reference_kind}</Badge></td>
              <td className="px-3 py-2">
                <Badge variant={row.result.overall_outcome === "Meets" ? "success" : "danger"}>
                  {row.result.overall_outcome}
                </Badge>
              </td>
              <td className="px-3 py-2">
                {row.cluster_id === null || row.cluster_id === undefined ? (
                  <span className="text-xs text-muted-foreground">-</span>
                ) : (
                  <Badge variant="secondary">C{row.cluster_id}</Badge>
                )}
              </td>
              <td className="px-3 py-2">
                <Badge variant="secondary">{row.source_label || row.source_key || row.source_kind || "dataset"}</Badge>
              </td>
              <td className="px-3 py-2">
                <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => onView(row)}>
                  <Eye className="h-4 w-4" />
                </Button>
              </td>
            </tr>
          ))}
          {rows.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-3 py-8 text-center text-sm text-muted-foreground">
                Select or publish a dataset to inspect rows.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function DraftDatasetsDrawer({
  open,
  populations,
  selectedId,
  onResume,
  onClose,
}: {
  open: boolean;
  populations: DatasetPopulationRecord[];
  selectedId: string;
  onResume: (populationId: string) => void;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <button type="button" className="absolute inset-0 bg-foreground/30 backdrop-blur-[1px]" onClick={onClose} aria-label="Close draft datasets" />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-xl flex-col border-l bg-background shadow-2xl">
        <header className="flex items-center justify-between border-b bg-secondary/35 p-5">
          <div>
            <h2 className="text-lg font-semibold">Draft Datasets</h2>
            <p className="text-sm text-muted-foreground">Resume a saved curation workspace for the selected form.</p>
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={onClose}>
            <X className="h-5 w-5" />
          </Button>
        </header>
        <div className="chat-scrollbar min-h-0 flex-1 space-y-2 overflow-y-auto p-5">
          {populations.map((population) => (
            <div
              key={population.id}
              className={[
                "rounded-md border bg-background p-3 transition",
                selectedId === population.id ? "border-primary/60 ring-1 ring-primary/20" : "",
              ].join(" ")}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">{population.name}</p>
                  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{population.description || "No description."}</p>
                </div>
                <Badge variant="outline">{population.candidate_count}</Badge>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1">
                <Badge variant="outline">{population.form_id}@{population.form_version}</Badge>
                <Badge variant="secondary">Kept {population.included_count}</Badge>
                <Badge variant="secondary">R2 {population.r2_count}</Badge>
                {hasStaleFlag(population.cluster_config) || hasStaleFlag(population.sample_config) ? (
                  <Badge variant="warning">Stale</Badge>
                ) : null}
                <Button type="button" variant="outline" size="sm" className="ml-auto h-7" onClick={() => onResume(population.id)}>
                  Resume
                </Button>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">Updated {formatDate(population.updated_at)}</p>
            </div>
          ))}
          {populations.length === 0 ? (
            <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
              No draft datasets for the selected form yet.
            </p>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function PublishedDatasetsDrawer({
  open,
  datasets,
  selectedId,
  onSelect,
  onClone,
  onClose,
}: {
  open: boolean;
  datasets: EvalDatasetRecord[];
  selectedId: string;
  onSelect: (datasetId: string) => void;
  onClone: (dataset: EvalDatasetRecord) => void;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <button type="button" className="absolute inset-0 bg-foreground/30 backdrop-blur-[1px]" onClick={onClose} aria-label="Close published datasets" />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-xl flex-col border-l bg-background shadow-2xl">
        <header className="flex items-center justify-between border-b bg-secondary/35 p-5">
          <div>
            <h2 className="text-lg font-semibold">Published Datasets</h2>
            <p className="text-sm text-muted-foreground">Select a dataset to inspect its rows below the publish controls.</p>
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={onClose}>
            <X className="h-5 w-5" />
          </Button>
        </header>
        <div className="chat-scrollbar min-h-0 flex-1 space-y-2 overflow-y-auto p-5">
          {datasets.map((dataset) => (
            <div
              key={dataset.id}
              className={[
                "w-full rounded-md border bg-background p-3 text-left transition hover:border-primary/50",
                selectedId === dataset.id ? "border-primary/60 ring-1 ring-primary/20" : "",
              ].join(" ")}
            >
              <button type="button" onClick={() => onSelect(dataset.id)} className="w-full text-left">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">{dataset.name}</p>
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{dataset.description || dataset.source_kind}</p>
                  </div>
                  <Badge variant={dataset.source_kind === "curated" ? "success" : "outline"}>
                    {dataset.case_count}
                  </Badge>
                </div>
              </button>
              <div className="mt-2 flex flex-wrap items-center gap-1">
                <Badge variant="outline">{dataset.form_id}@{dataset.form_version}</Badge>
                <Badge variant="secondary">R1 {dataset.r1_count}</Badge>
                <Badge variant="secondary">R2 {dataset.r2_count}</Badge>
                <Button type="button" variant="ghost" size="sm" className="ml-auto h-7" onClick={() => onClone(dataset)}>
                  <Copy className="h-3.5 w-3.5" />
                  Clone
                </Button>
              </div>
            </div>
          ))}
          {datasets.length === 0 ? (
            <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
              No published datasets for the selected form yet.
            </p>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function PublishedRowDrawer({
  row,
  onClose,
}: {
  row: PublishedDatasetRow | null;
  onClose: () => void;
}) {
  if (!row) return null;
  return (
    <div className="fixed inset-0 z-50">
      <button type="button" className="absolute inset-0 bg-foreground/30 backdrop-blur-[1px]" onClick={onClose} aria-label="Close dataset row" />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-4xl flex-col border-l bg-background shadow-2xl">
        <header className="flex items-start gap-3 border-b bg-secondary/35 p-5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border bg-background text-primary">
            <Database className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-lg font-semibold">{row.claim_number || row.case_id}</h2>
              <Badge variant="outline">{row.reference_kind}</Badge>
              {row.cluster_id !== null && row.cluster_id !== undefined ? <Badge variant="secondary">C{row.cluster_id}</Badge> : null}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{row.dataset_name}</p>
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={onClose}>
            <X className="h-5 w-5" />
          </Button>
        </header>
        <div className="chat-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          <div className="grid gap-3 md:grid-cols-4">
            <MiniMetric label="Source" value={row.source_label || row.source_key || row.source_kind || "dataset"} />
            <MiniMetric label="Case" value={row.case_id.slice(0, 8)} />
            <MiniMetric label="Ground Truth" value={row.ground_truth_id.slice(0, 8)} />
            <MiniMetric label="Updated" value={formatDate(row.updated_at)} />
          </div>
          <JsonBlock title="Curation Metadata" value={row.metadata ?? {}} />
          <ReadOnlyResult title={`Published Reference ${row.reference_kind}`} result={row.result} />
        </div>
      </aside>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-background px-3 py-2">
      <p className="text-[11px] font-semibold uppercase text-muted-foreground">{label}</p>
      <p className="mt-1 truncate text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function CandidateDrawer({
  candidate,
  onClose,
  onEditReference,
}: {
  candidate: DatasetCandidateRecord | null;
  onClose: () => void;
  onEditReference: (candidate: DatasetCandidateRecord, referenceKind: "R1" | "R2") => void;
}) {
  if (!candidate) return null;
  return (
    <div className="fixed inset-0 z-50">
      <button type="button" className="absolute inset-0 bg-foreground/30 backdrop-blur-[1px]" onClick={onClose} aria-label="Close candidate" />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-4xl flex-col border-l bg-background shadow-2xl">
        <header className="flex items-start gap-3 border-b bg-secondary/35 p-5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border bg-background text-primary">
            <Database className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-lg font-semibold">{candidate.claim_number}</h2>
              <Badge variant="outline">{candidate.source_label || candidate.source_key}</Badge>
              {candidate.cluster_id !== null && candidate.cluster_id !== undefined ? <Badge variant="secondary">C{candidate.cluster_id}</Badge> : null}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{candidate.instructions || "No instructions captured."}</p>
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={onClose}>
            <X className="h-5 w-5" />
          </Button>
        </header>
        <div className="chat-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          <div className="grid gap-3 md:grid-cols-4">
            <MiniMetric label="Outcome" value={String(candidate.metrics.outcome ?? "-")} />
            <MiniMetric label="Issues" value={String(metricNumber(candidate.metrics, "issue_count") ?? 0)} />
            <MiniMetric label="Drivers" value={String(metricNumber(candidate.metrics, "driver_count") ?? 0)} />
            <MiniMetric label="OW Total" value={formatCurrency(metricNumber(candidate.metrics, "total_overwrite_dollars"))} />
          </div>
          <JsonBlock title="Source Metadata" value={candidate.metadata ?? {}} />
          {candidate.references.map((reference) => (
            <div key={reference.reference_kind} className="space-y-2">
              <div className="flex justify-end">
                <Button type="button" variant="outline" size="sm" onClick={() => onEditReference(candidate, reference.reference_kind)}>
                  <FilePenLine className="h-4 w-4" />
                  Edit {reference.reference_kind}
                </Button>
              </div>
              <ReadOnlyResult title={`Reference ${reference.reference_kind}`} result={reference.result} />
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="rounded-md border bg-card">
      <div className="border-b bg-secondary/35 px-4 py-2 text-sm font-semibold">{title}</div>
      <pre className="max-h-64 overflow-auto p-4 text-xs">{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

function ReadOnlyResult({ title, result }: { title: string; result: AuditFormResult }) {
  return (
    <div className="rounded-md border bg-card">
      <div className="border-b bg-secondary/35 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold">{title}</p>
          <Badge variant={result.overall_outcome === "Meets" ? "success" : "danger"}>{result.overall_outcome}</Badge>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{result.outcome_justification}</p>
      </div>
      <div className="space-y-3 p-4">
        {result.questions.map((question) => (
          <div key={question.id} className="rounded-md border bg-background p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-mono text-xs font-semibold text-primary">{question.id}</p>
                <p className="mt-1 text-sm">{question.text}</p>
              </div>
              <Badge variant={question.answer === "Yes" ? "success" : "danger"}>{question.answer}</Badge>
            </div>
            {question.comments ? <p className="mt-2 text-xs text-muted-foreground">{question.comments}</p> : null}
            {(question.sub_questions ?? []).some((subQuestion) => subQuestion.answer) ? (
              <div className="mt-2 space-y-2">
                {(question.sub_questions ?? []).filter((subQuestion) => subQuestion.answer).map((subQuestion) => (
                  <div key={subQuestion.id} className="rounded-md border bg-card px-3 py-2 text-xs">
                    <p className="font-semibold">{subQuestion.id} {subQuestion.text}</p>
                    <p className="mt-1 text-muted-foreground">{subQuestion.reasoning}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
