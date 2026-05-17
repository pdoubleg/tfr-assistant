"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  BarChart3,
  Clock3,
  Eye,
  FileText,
  FolderArchive,
  Loader2,
  Pause,
  Play,
  PlayCircle,
  RefreshCw,
  RotateCcw,
  Search,
  Square,
  SquarePen,
  X,
} from "lucide-react";

import { BatchRunDialog } from "@/components/app-shell/batch-run-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  cancelBatch,
  createBatchTemplate,
  getBatchSummary,
  getFormDefinition,
  launchBatchTemplate,
  listBatches,
  listBatchReviews,
  listBatchTemplates,
  listFormCatalog,
  pauseBatch,
  resumeBatch,
  retryFailedBatch,
} from "@/lib/api";
import { getClaimNumber, getUserVersion } from "@/lib/api";
import type {
  AuditFormDefinition,
  AuditFormResult,
  BatchRecord,
  BatchStatus,
  BatchSummary,
  BatchTemplatePayload,
  BatchTemplateRecord,
  FormCatalogEntry,
  FormQuestion,
  ReviewRecord,
} from "@/lib/types";

const pollMs = 3000;
const productionQueueStorageKey = "tfr.batch.productionQueue.v1";

type BatchAction = "pause" | "resume" | "retry" | "cancel";
type SortKey = "name" | "form" | "status" | "completed" | "runtime" | "started";

interface ProductionQueueItem {
  id: string;
  templateId?: string;
  batchId?: string;
  activated?: boolean;
}

interface ProductionQueueCard {
  item: ProductionQueueItem;
  template?: BatchTemplateRecord;
  batch?: BatchRecord;
}

function statusVariant(status?: BatchStatus | string): "secondary" | "outline" | "success" | "danger" | "warning" {
  if (status === "completed") return "success";
  if (status === "failed" || status === "canceled") return "danger";
  if (status === "running" || status === "paused") return "warning";
  return "secondary";
}

function reviewStatusVariant(status?: string): "secondary" | "outline" | "success" | "danger" | "warning" {
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "running") return "warning";
  return "secondary";
}

function formatRuntime(seconds?: number | null): string {
  if (!seconds) return "-";
  const rounded = Math.max(1, Math.round(seconds));
  const minutes = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`;
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

function formatPct(value: number): string {
  return `${Math.round(value)}%`;
}

function batchFormKey(batch: BatchRecord): string {
  const input = batch.input_json ?? {};
  const formId = typeof input.form_id === "string" ? input.form_id : "";
  const formVersion = typeof input.form_version === "string" ? input.form_version : "";
  return formId && formVersion ? `${formId}@${formVersion}` : "-";
}

function templateFormKey(template: BatchTemplateRecord): string {
  return `${template.form_id}@${template.form_version}`;
}

function inputModeLabel(inputMode?: string, synthetic?: boolean): string {
  if (synthetic) return "Synthetic";
  if (inputMode === "upload") return "Spreadsheet";
  if (inputMode === "manual") return "Direct";
  return "Batch";
}

function progressCounts(batch: BatchRecord): string {
  return `${batch.completed_count}/${batch.total_count} complete${batch.failed_count ? `, ${batch.failed_count} failed` : ""}`;
}

function isActiveBatch(batch: BatchRecord): boolean {
  return batch.status === "running" || batch.status === "queued" || batch.status === "paused";
}

function emptySummary(): BatchSummary {
  return {
    active_batches: 0,
    queued_batches: 0,
    paused_batches: 0,
    failed_batches: 0,
    completed_batches: 0,
    total_reviews: 0,
    completed_reviews: 0,
    failed_reviews: 0,
    running_reviews: 0,
    queued_reviews: 0,
    completed_reviews_today: 0,
    average_duration_seconds: null,
    form_volume: [],
  };
}

function readPersistedProductionQueue(): { items: ProductionQueueItem[]; hasPersisted: boolean } {
  if (typeof window === "undefined") return { items: [], hasPersisted: false };
  try {
    const raw = window.localStorage.getItem(productionQueueStorageKey);
    if (raw === null) return { items: [], hasPersisted: false };
    const parsed = JSON.parse(raw);
    const items = Array.isArray(parsed)
      ? parsed.filter((item): item is ProductionQueueItem => (
          item &&
          typeof item === "object" &&
          typeof item.id === "string" &&
          (typeof item.templateId === "string" || typeof item.batchId === "string")
        ))
        .map((item) => ({
          id: item.id,
          templateId: item.templateId,
          batchId: item.batchId,
          activated: item.activated === true,
        }))
      : [];
    return { items, hasPersisted: true };
  } catch {
    return { items: [], hasPersisted: true };
  }
}

function persistProductionQueue(items: ProductionQueueItem[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(productionQueueStorageKey, JSON.stringify(items));
  } catch {
    // Queue persistence should not block batch monitoring.
  }
}

function useBodyScrollLock(open: boolean) {
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);
}

export function BatchAuditsWorkspace() {
  const [templates, setTemplates] = useState<BatchTemplateRecord[]>([]);
  const [batches, setBatches] = useState<BatchRecord[]>([]);
  const [forms, setForms] = useState<FormCatalogEntry[]>([]);
  const [summary, setSummary] = useState<BatchSummary>(() => emptySummary());
  const [queueItems, setQueueItems] = useState<ProductionQueueItem[]>([]);
  const [queueHydrated, setQueueHydrated] = useState(false);
  const [hasPersistedQueue, setHasPersistedQueue] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("started");
  const [sortDesc, setSortDesc] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogTemplate, setDialogTemplate] = useState<BatchTemplateRecord | null>(null);
  const [dialogQueueItemId, setDialogQueueItemId] = useState("");
  const [selectedBatch, setSelectedBatch] = useState<BatchRecord | null>(null);
  const [selectedForm, setSelectedForm] = useState<AuditFormDefinition | null>(null);
  const [summaryReviews, setSummaryReviews] = useState<ReviewRecord[]>([]);
  const [viewingReview, setViewingReview] = useState<ReviewRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [launchingTemplateId, setLaunchingTemplateId] = useState("");
  const [actioningBatch, setActioningBatch] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const persisted = readPersistedProductionQueue();
    setQueueItems(persisted.items);
    setHasPersistedQueue(persisted.hasPersisted);
    setQueueHydrated(true);
  }, []);

  useEffect(() => {
    if (!queueHydrated) return;
    if (!hasPersistedQueue && queueItems.length === 0) return;
    persistProductionQueue(queueItems);
    setHasPersistedQueue(true);
  }, [hasPersistedQueue, queueHydrated, queueItems]);

  const refresh = useCallback(async ({ initial = false, manual = false }: { initial?: boolean; manual?: boolean } = {}) => {
    if (initial) setLoading(true);
    if (manual) setRefreshing(true);
    setError("");
    try {
      const [nextForms, nextTemplates, nextBatches, nextSummary] = await Promise.all([
        listFormCatalog(),
        listBatchTemplates(),
        listBatches(),
        getBatchSummary(),
      ]);
      setForms(nextForms);
      setTemplates(nextTemplates);
      setBatches(nextBatches);
      setSummary(nextSummary);
      setQueueItems((current) => {
        const validTemplateIds = new Set(nextTemplates.map((template) => template.id));
        const validBatchIds = new Set(nextBatches.map((batch) => batch.id));
        const retained = current.filter((item) =>
          (item.templateId && validTemplateIds.has(item.templateId)) ||
          (item.batchId && validBatchIds.has(item.batchId)),
        );
        if (retained.length || hasPersistedQueue) return retained;
        return nextBatches
          .filter((batch) => isActiveBatch(batch))
          .map((batch) => ({
            id: `batch:${batch.id}`,
            batchId: batch.id,
            templateId: batch.template_id ?? undefined,
            activated: true,
          }));
      });
      setSelectedBatch((current) =>
        current ? nextBatches.find((batch) => batch.id === current.id) ?? null : null,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load batch audit data.");
    } finally {
      if (initial) setLoading(false);
      if (manual) setRefreshing(false);
    }
  }, [hasPersistedQueue]);

  useEffect(() => {
    void refresh({ initial: true });
  }, [refresh]);

  const hasRunningBatch = useMemo(() => batches.some((batch) => batch.status === "running"), [batches]);

  useEffect(() => {
    if (!hasRunningBatch) return;
    const interval = window.setInterval(() => {
      void refresh();
    }, pollMs);
    return () => window.clearInterval(interval);
  }, [hasRunningBatch, refresh]);

  useEffect(() => {
    if (!selectedBatch) {
      setSummaryReviews([]);
      return;
    }
    let canceled = false;
    void listBatchReviews(selectedBatch.id)
      .then((reviews) => {
        if (!canceled) setSummaryReviews(reviews);
      })
      .catch((err) => {
        if (!canceled) setError(err instanceof Error ? err.message : "Failed to load batch reviews.");
      });
    return () => {
      canceled = true;
    };
  }, [selectedBatch]);

  const queueCards = useMemo(() => {
    return queueItems.flatMap((item) => {
      const batch = item.batchId ? batches.find((candidate) => candidate.id === item.batchId) : undefined;
      const templateId = item.templateId ?? batch?.template_id ?? undefined;
      const template = templateId ? templates.find((candidate) => candidate.id === templateId) : undefined;
      if (!batch && !template) return [];
      return [{ item, batch, template }];
    });
  }, [batches, queueItems, templates]);
  const completedBatches = useMemo(
    () => batches.filter((batch) => batch.status === "completed" || batch.status === "failed" || batch.status === "canceled"),
    [batches],
  );
  const filteredCompleted = useMemo(() => {
    const query = search.trim().toLowerCase();
    const filtered = completedBatches.filter((batch) => {
      if (statusFilter !== "all" && batch.status !== statusFilter) return false;
      if (!query) return true;
      return [batch.name, batch.description, batch.status, batchFormKey(batch)]
        .join(" ")
        .toLowerCase()
        .includes(query);
    });
    return [...filtered].sort((first, second) => {
      const direction = sortDesc ? -1 : 1;
      const firstValue = sortableValue(first, sortKey);
      const secondValue = sortableValue(second, sortKey);
      if (firstValue < secondValue) return -1 * direction;
      if (firstValue > secondValue) return 1 * direction;
      return 0;
    });
  }, [completedBatches, search, sortDesc, sortKey, statusFilter]);

  const saveBatchConfiguration = async (payload: BatchTemplatePayload) => {
    setSaving(true);
    setError("");
    try {
      const template = await createBatchTemplate(payload);
      if (dialogQueueItemId) {
        setQueueItems((current) =>
          current.map((item) =>
            item.id === dialogQueueItemId
              ? { id: `template:${template.id}`, templateId: template.id, activated: true }
              : item,
          ),
        );
        setDialogOpen(false);
        setDialogTemplate(null);
        setDialogQueueItemId("");
        await refresh();
        return;
      }

      const run = await launchBatchTemplate(template.id);
      const launchedItem: ProductionQueueItem = {
        id: `batch:${run.id}`,
        batchId: run.id,
        templateId: template.id,
        activated: true,
      };
      setQueueItems((current) => {
        return [
          launchedItem,
          ...current.filter((item) => item.templateId !== template.id && item.batchId !== run.id),
        ];
      });
      setDialogOpen(false);
      setDialogTemplate(null);
      setDialogQueueItemId("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create and launch batch.");
    } finally {
      setSaving(false);
    }
  };

  const launchTemplate = async (queueItem: ProductionQueueItem, template: BatchTemplateRecord) => {
    if (!queueItem.activated) return;
    setLaunchingTemplateId(template.id);
    setError("");
    try {
      const run = await launchBatchTemplate(template.id);
      setQueueItems((current) =>
        current.map((item) =>
          item.id === queueItem.id && item.templateId === template.id && !item.batchId
            ? { id: `batch:${run.id}`, batchId: run.id, templateId: template.id, activated: true }
            : item,
        ),
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to launch batch.");
    } finally {
      setLaunchingTemplateId("");
    }
  };

  const runAction = async (batch: BatchRecord, action: BatchAction) => {
    setActioningBatch(`${batch.id}:${action}`);
    setError("");
    try {
      if (action === "pause") await pauseBatch(batch.id);
      if (action === "resume") await resumeBatch(batch.id);
      if (action === "retry") await retryFailedBatch(batch.id);
      if (action === "cancel") await cancelBatch(batch.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${action} batch.`);
    } finally {
      setActioningBatch("");
    }
  };

  const openNewBatch = () => {
    setDialogTemplate(null);
    setDialogQueueItemId("");
    setDialogOpen(true);
  };

  const openProductionConfig = (item: ProductionQueueItem, template: BatchTemplateRecord) => {
    setQueueItems((current) =>
      current.map((candidate) =>
        candidate.id === item.id ? { ...candidate, activated: true } : candidate,
      ),
    );
    setDialogTemplate(template);
    setDialogQueueItemId(item.id);
    setDialogOpen(true);
  };

  const addToProduction = (template: BatchTemplateRecord) => {
    setQueueItems((current) => {
      if (current.some((item) => item.templateId === template.id && !item.batchId)) {
        return current;
      }
      return [{ id: `template:${template.id}`, templateId: template.id, activated: false }, ...current];
    });
  };

  const removeProductionItem = (itemId: string) => {
    setQueueItems((current) => current.filter((item) => item.id !== itemId));
  };

  const previewForm = async (formId: string, formVersion: string) => {
    setError("");
    try {
      setSelectedForm(await getFormDefinition(formId, formVersion));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load form definition.");
    }
  };

  const setSort = (nextSortKey: SortKey) => {
    if (sortKey === nextSortKey) {
      setSortDesc((current) => !current);
      return;
    }
    setSortKey(nextSortKey);
    setSortDesc(nextSortKey === "started" || nextSortKey === "runtime");
  };

  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-4 p-4 lg:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Batch Audits</h1>
          <p className="text-sm text-muted-foreground">
            Configure audit batches, run them, and monitor production volume.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => void refresh({ manual: true })} disabled={loading || refreshing}>
            {loading || refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Refresh
          </Button>
          <Button type="button" size="sm" onClick={() => openNewBatch()}>
            <PlayCircle className="h-4 w-4" />
            New Batch
          </Button>
        </div>
      </div>

      {error ? (
        <Card className="border-destructive/40">
          <CardContent className="flex items-start gap-2 p-4 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            {error}
          </CardContent>
        </Card>
      ) : null}

      <ProductionMetrics summary={summary} />

      <div className="grid gap-4 xl:grid-cols-[minmax(340px,420px)_1fr]">
        <SavedConfigurationsCard
          templates={templates}
          queueItems={queueItems}
          loading={loading}
          onAdd={addToProduction}
          onPreviewForm={previewForm}
        />
        <ActiveQueueCard
          cards={queueCards}
          launchingTemplateId={launchingTemplateId}
          actioningBatch={actioningBatch}
          onLaunchTemplate={launchTemplate}
          onConfigure={openProductionConfig}
          onAction={runAction}
          onRemove={removeProductionItem}
          onViewBatch={setSelectedBatch}
        />
      </div>

      <CompletedBatchesTable
        batches={filteredCompleted}
        search={search}
        statusFilter={statusFilter}
        sortKey={sortKey}
        sortDesc={sortDesc}
        loading={loading}
        onSearchChange={setSearch}
        onStatusFilterChange={setStatusFilter}
        onSort={setSort}
        onViewBatch={setSelectedBatch}
      />

      <BatchRunDialog
        open={dialogOpen}
        template={dialogTemplate}
        mode={dialogTemplate ? "duplicate" : "create"}
        forms={forms}
        saving={saving}
        onClose={() => {
          if (saving) return;
          setDialogOpen(false);
          setDialogTemplate(null);
          setDialogQueueItemId("");
        }}
        onSave={saveBatchConfiguration}
      />

      <BatchSummaryDrawer
        batch={selectedBatch}
        reviews={summaryReviews}
        actioningBatch={actioningBatch}
        onClose={() => setSelectedBatch(null)}
        onAction={runAction}
        onViewReview={setViewingReview}
      />

      <ReadOnlyFormDialog formDefinition={selectedForm} onClose={() => setSelectedForm(null)} />
      <ReviewFormDialog review={viewingReview} onClose={() => setViewingReview(null)} />
    </div>
  );
}

function sortableValue(batch: BatchRecord, sortKey: SortKey): string | number {
  if (sortKey === "name") return batch.name.toLowerCase();
  if (sortKey === "form") return batchFormKey(batch).toLowerCase();
  if (sortKey === "status") return batch.status;
  if (sortKey === "completed") return batch.completed_count;
  if (sortKey === "runtime") return batch.duration_seconds ?? 0;
  return new Date(batch.started_at ?? batch.created_at ?? 0).getTime();
}

function ProductionMetrics({ summary }: { summary: BatchSummary }) {
  const failureRate = summary.total_reviews ? Math.round((summary.failed_reviews / summary.total_reviews) * 100) : 0;
  const primaryForm = summary.form_volume[0];
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
      <MetricCard label="Active Batches" value={summary.active_batches} helper={`${summary.queued_batches} queued, ${summary.paused_batches} paused`} />
      <MetricCard label="Queued Reviews" value={summary.queued_reviews} helper={`${summary.running_reviews} running now`} />
      <MetricCard label="Completed Today" value={summary.completed_reviews_today} helper={`${summary.completed_reviews} completed total`} />
      <MetricCard label="Errors" value={summary.failed_reviews} helper={`${failureRate}% review failure rate`} />
      <MetricCard label="Avg Runtime" value={formatRuntime(summary.average_duration_seconds)} helper="completed/failed batches" />
      <MetricCard
        label="Top Form"
        value={primaryForm ? primaryForm.form_id : "-"}
        helper={primaryForm ? `${primaryForm.completed_count}/${primaryForm.total_count} completed` : "No batch volume"}
      />
    </div>
  );
}

function MetricCard({ label, value, helper }: { label: string; value: ReactNode; helper: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-[11px] font-semibold uppercase text-muted-foreground">{label}</p>
        <p className="mt-2 truncate text-2xl font-semibold tabular-nums">{value}</p>
        <p className="mt-1 truncate text-xs text-muted-foreground">{helper}</p>
      </CardContent>
    </Card>
  );
}

function SavedConfigurationsCard({
  templates,
  queueItems,
  loading,
  onAdd,
  onPreviewForm,
}: {
  templates: BatchTemplateRecord[];
  queueItems: ProductionQueueItem[];
  loading: boolean;
  onAdd: (template: BatchTemplateRecord) => void;
  onPreviewForm: (formId: string, formVersion: string) => void;
}) {
  const [query, setQuery] = useState("");
  const filteredTemplates = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return templates;
    return templates.filter((template) =>
      [template.name, template.description, templateFormKey(template)].join(" ").toLowerCase().includes(normalized),
    );
  }, [query, templates]);
  const queuedTemplateIds = useMemo(
    () => new Set(queueItems.map((item) => item.templateId).filter(Boolean)),
    [queueItems],
  );

  return (
    <Card className="flex h-fit max-h-[620px] min-h-0 flex-col overflow-hidden">
      <CardHeader className="border-b">
        <CardTitle className="flex items-center gap-2">
          <FolderArchive className="h-4 w-4 text-primary" />
          Run Configurations
        </CardTitle>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 p-0">
        <div className="border-b bg-secondary/35 p-3">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(event) => setQuery(event.target.value)} className="h-8 pl-8 text-xs" placeholder="Search configurations" />
          </label>
        </div>
        <div className="chat-scrollbar max-h-[500px] overflow-y-auto">
          {loading && templates.length === 0 ? (
            <LoadingState label="Loading configurations" />
          ) : null}
          {!loading && templates.length === 0 ? (
            <EmptyState icon={<FileText className="h-8 w-8 text-muted-foreground/40" />} title="No saved configurations" />
          ) : null}
          {filteredTemplates.map((template) => {
            const latest = template.latest_run;
            const added = queuedTemplateIds.has(template.id);
            return (
              <div key={template.id} className="grid gap-3 border-b px-4 py-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate text-sm font-medium">{template.name}</p>
                    <Badge variant="outline">{templateFormKey(template)}</Badge>
                  </div>
                  <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{template.description || "No description"}</p>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="secondary">{inputModeLabel(template.input_mode, template.synthetic)}</Badge>
                  <Badge variant={statusVariant(latest?.status)}>{latest?.status ?? "ready"}</Badge>
                  <Badge variant="outline">{template.item_count} reviews</Badge>
                  <Badge variant="outline">{template.run_count} runs</Badge>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" className="gap-1.5" onClick={() => onAdd(template)} disabled={added}>
                    <PlayCircle className="h-3.5 w-3.5" />
                    {added ? "Added" : "Add"}
                  </Button>
                  <Button type="button" variant="ghost" size="sm" className="gap-1.5" onClick={() => onPreviewForm(template.form_id, template.form_version)}>
                    <Eye className="h-3.5 w-3.5" />
                    Form
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function ActiveQueueCard({
  cards,
  launchingTemplateId,
  actioningBatch,
  onLaunchTemplate,
  onConfigure,
  onAction,
  onRemove,
  onViewBatch,
}: {
  cards: ProductionQueueCard[];
  launchingTemplateId: string;
  actioningBatch: string;
  onLaunchTemplate: (item: ProductionQueueItem, template: BatchTemplateRecord) => void;
  onConfigure: (item: ProductionQueueItem, template: BatchTemplateRecord) => void;
  onAction: (batch: BatchRecord, action: BatchAction) => void;
  onRemove: (itemId: string) => void;
  onViewBatch: (batch: BatchRecord) => void;
}) {
  return (
    <Card className="min-h-[280px]">
      <CardHeader className="border-b">
        <CardTitle className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-primary" />
          Active Production
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4">
        {cards.length === 0 ? (
          <EmptyState icon={<PlayCircle className="h-8 w-8 text-muted-foreground/40" />} title="No production items" />
        ) : (
          <div className="grid gap-3">
            {cards.map(({ item, batch, template }) => (
              <div key={item.id} className="rounded-lg border bg-background p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate font-medium">{batch?.name || template?.name || "Untitled batch"}</p>
                      <Badge variant={statusVariant(batch?.status)}>{batch?.status ?? (item.activated ? "ready" : "configure")}</Badge>
                      <Badge variant="outline">{batch ? batchFormKey(batch) : template ? templateFormKey(template) : "-"}</Badge>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {batch
                        ? progressCounts(batch)
                        : item.activated
                          ? "Ready to launch from this production queue."
                          : "Open once to review the claim list before launch."}
                    </p>
                  </div>
                  <ProductionControls
                    item={item}
                    batch={batch}
                    template={template}
                    launchingTemplateId={launchingTemplateId}
                    actioningBatch={actioningBatch}
                    onConfigure={onConfigure}
                    onLaunchTemplate={onLaunchTemplate}
                    onAction={onAction}
                    onRemove={onRemove}
                    onViewBatch={onViewBatch}
                  />
                </div>
                {batch ? <ProgressBar value={batch.progress_percent} /> : null}
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                    {batch ? (
                      <>
                        <span>{batch.running_count} running</span>
                        <span>{batch.queued_count} queued</span>
                        <span>Started {formatDate(batch.started_at ?? batch.created_at)}</span>
                      </>
                    ) : template ? (
                      <>
                        <span>{inputModeLabel(template.input_mode, template.synthetic)}</span>
                        <span>{template.item_count} reviews</span>
                        <span>{template.run_count} prior runs</span>
                      </>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ProductionControls({
  item,
  batch,
  template,
  launchingTemplateId,
  actioningBatch,
  onConfigure,
  onLaunchTemplate,
  onAction,
  onRemove,
  onViewBatch,
}: {
  item: ProductionQueueItem;
  batch?: BatchRecord;
  template?: BatchTemplateRecord;
  launchingTemplateId: string;
  actioningBatch: string;
  onConfigure: (item: ProductionQueueItem, template: BatchTemplateRecord) => void;
  onLaunchTemplate: (item: ProductionQueueItem, template: BatchTemplateRecord) => void;
  onAction: (batch: BatchRecord, action: BatchAction) => void;
  onRemove: (itemId: string) => void;
  onViewBatch: (batch: BatchRecord) => void;
}) {
  const loadingAction = (action: BatchAction) => (batch ? actioningBatch === `${batch.id}:${action}` : false);
  const canConfigure = Boolean(template && !batch);
  const canLaunch = Boolean(template && !batch && item.activated);
  const isLaunching = Boolean(template && launchingTemplateId === template.id);
  const canPause = batch?.status === "running";
  const canResume = batch?.status === "paused" || batch?.status === "queued";
  const canRetry = Boolean(batch && batch.failed_count > 0 && batch.status !== "running");
  const canCancel = Boolean(batch && batch.status !== "completed" && batch.status !== "canceled");

  return (
    <div className="flex flex-wrap justify-end gap-1">
      <ControlButton
        label="Configure production run"
        disabled={!canConfigure}
        onClick={() => {
          if (template) onConfigure(item, template);
        }}
      >
        <SquarePen className="h-4 w-4" />
      </ControlButton>
      <ControlButton
        label={item.activated ? "Launch batch" : "Open configuration before launch"}
        disabled={!canLaunch || isLaunching}
        loading={isLaunching}
        className="text-emerald-700 hover:text-emerald-800 dark:text-emerald-300"
        onClick={() => {
          if (template) onLaunchTemplate(item, template);
        }}
      >
        <Play className="h-4 w-4 fill-current" />
      </ControlButton>
      <ControlButton
        label="Pause batch"
        disabled={!canPause || Boolean(actioningBatch)}
        loading={loadingAction("pause")}
        className="text-amber-700 hover:text-amber-800 dark:text-amber-300"
        onClick={() => {
          if (batch) onAction(batch, "pause");
        }}
      >
        <Pause className="h-4 w-4 fill-current" />
      </ControlButton>
      <ControlButton
        label="Resume batch"
        disabled={!canResume || Boolean(actioningBatch)}
        loading={loadingAction("resume")}
        className="text-emerald-700 hover:text-emerald-800 dark:text-emerald-300"
        onClick={() => {
          if (batch) onAction(batch, "resume");
        }}
      >
        <PlayCircle className="h-4 w-4" />
      </ControlButton>
      <ControlButton
        label="Retry failed reviews"
        disabled={!canRetry || Boolean(actioningBatch)}
        loading={loadingAction("retry")}
        onClick={() => {
          if (batch) onAction(batch, "retry");
        }}
      >
        <RotateCcw className="h-4 w-4" />
      </ControlButton>
      <ControlButton
        label="Stop batch"
        disabled={!canCancel || Boolean(actioningBatch)}
        loading={loadingAction("cancel")}
        className="text-rose-700 hover:text-rose-800 dark:text-rose-300"
        onClick={() => {
          if (batch) onAction(batch, "cancel");
        }}
      >
        <Square className="h-4 w-4 fill-current" />
      </ControlButton>
      <ControlButton
        label="View batch summary"
        disabled={!batch}
        onClick={() => {
          if (batch) onViewBatch(batch);
        }}
      >
        <Eye className="h-4 w-4" />
      </ControlButton>
      <ControlButton label="Remove from production" onClick={() => onRemove(item.id)}>
        <X className="h-4 w-4" />
      </ControlButton>
    </div>
  );
}

function ControlButton({
  label,
  loading = false,
  disabled = false,
  className = "",
  onClick,
  children,
}: {
  label: string;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      className={`h-8 w-8 ${className}`}
      disabled={disabled}
      onClick={onClick}
      aria-label={label}
      title={label}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : children}
    </Button>
  );
}

function BatchActionButtons({
  batch,
  actioningBatch,
  onAction,
}: {
  batch: BatchRecord;
  actioningBatch: string;
  onAction: (batch: BatchRecord, action: BatchAction) => void;
}) {
  const loadingAction = (action: BatchAction) => actioningBatch === `${batch.id}:${action}`;
  return (
    <div className="flex flex-wrap justify-end gap-2">
      {batch.status === "running" ? (
        <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => onAction(batch, "pause")} disabled={loadingAction("pause")}>
          {loadingAction("pause") ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Pause className="h-3.5 w-3.5" />}
          Pause
        </Button>
      ) : null}
      {batch.status === "paused" || batch.status === "queued" ? (
        <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => onAction(batch, "resume")} disabled={loadingAction("resume")}>
          {loadingAction("resume") ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          Resume
        </Button>
      ) : null}
      {batch.failed_count > 0 ? (
        <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => onAction(batch, "retry")} disabled={loadingAction("retry") || batch.status === "running"}>
          {loadingAction("retry") ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
          Retry
        </Button>
      ) : null}
      {batch.status !== "completed" && batch.status !== "canceled" ? (
        <Button type="button" variant="ghost" size="sm" className="gap-1.5" onClick={() => onAction(batch, "cancel")} disabled={loadingAction("cancel")}>
          {loadingAction("cancel") ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Square className="h-3.5 w-3.5" />}
          Cancel
        </Button>
      ) : null}
    </div>
  );
}

function CompletedBatchesTable({
  batches,
  search,
  statusFilter,
  sortKey,
  sortDesc,
  loading,
  onSearchChange,
  onStatusFilterChange,
  onSort,
  onViewBatch,
}: {
  batches: BatchRecord[];
  search: string;
  statusFilter: string;
  sortKey: SortKey;
  sortDesc: boolean;
  loading: boolean;
  onSearchChange: (value: string) => void;
  onStatusFilterChange: (value: string) => void;
  onSort: (key: SortKey) => void;
  onViewBatch: (batch: BatchRecord) => void;
}) {
  return (
    <Card>
      <CardHeader className="border-b">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Clock3 className="h-4 w-4 text-primary" />
            Completed Batches
          </CardTitle>
          <div className="flex flex-wrap gap-2">
            <label className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input value={search} onChange={(event) => onSearchChange(event.target.value)} className="h-8 w-64 pl-8 text-xs" placeholder="Search completed runs" />
            </label>
            <select
              value={statusFilter}
              onChange={(event) => onStatusFilterChange(event.target.value)}
              className="h-8 rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="all">All statuses</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="canceled">Canceled</option>
            </select>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-sm">
            <thead className="border-b bg-secondary/60 text-xs text-muted-foreground">
              <tr>
                <SortableHead label="Batch" sortId="name" active={sortKey} desc={sortDesc} onSort={onSort} />
                <SortableHead label="Form" sortId="form" active={sortKey} desc={sortDesc} onSort={onSort} />
                <SortableHead label="Status" sortId="status" active={sortKey} desc={sortDesc} onSort={onSort} />
                <SortableHead label="Completed" sortId="completed" active={sortKey} desc={sortDesc} onSort={onSort} />
                <SortableHead label="Runtime" sortId="runtime" active={sortKey} desc={sortDesc} onSort={onSort} />
                <SortableHead label="Started" sortId="started" active={sortKey} desc={sortDesc} onSort={onSort} />
                <th className="px-4 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && batches.length === 0 ? (
                <tr>
                  <td colSpan={7} className="h-24 text-center text-muted-foreground">
                    Loading completed batches
                  </td>
                </tr>
              ) : batches.length === 0 ? (
                <tr>
                  <td colSpan={7} className="h-24 text-center text-muted-foreground">
                    No completed batches match the current filters.
                  </td>
                </tr>
              ) : (
                batches.map((batch) => (
                  <tr key={batch.id} className="border-b last:border-b-0 hover:bg-secondary/35">
                    <td className="px-4 py-3">
                      <p className="font-medium">{batch.name || "Untitled batch"}</p>
                      <p className="line-clamp-1 text-xs text-muted-foreground">{batch.description || batch.id}</p>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant="outline">{batchFormKey(batch)}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={statusVariant(batch.status)}>{batch.status}</Badge>
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {batch.completed_count}/{batch.total_count}
                      {batch.failed_count ? <span className="text-destructive"> · {batch.failed_count} failed</span> : null}
                    </td>
                    <td className="px-4 py-3 tabular-nums">{formatRuntime(batch.duration_seconds)}</td>
                    <td className="px-4 py-3">{formatDate(batch.started_at ?? batch.created_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <Button type="button" variant="ghost" size="sm" onClick={() => onViewBatch(batch)}>
                        <Eye className="h-3.5 w-3.5" />
                        Summary
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function SortableHead({
  label,
  sortId,
  active,
  desc,
  onSort,
}: {
  label: string;
  sortId: SortKey;
  active: SortKey;
  desc: boolean;
  onSort: (key: SortKey) => void;
}) {
  return (
    <th className="px-4 py-3 text-left font-medium">
      <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => onSort(sortId)}>
        {label}
        {active === sortId ? <span>{desc ? "desc" : "asc"}</span> : null}
      </button>
    </th>
  );
}

function BatchSummaryDrawer({
  batch,
  reviews,
  actioningBatch,
  onClose,
  onAction,
  onViewReview,
}: {
  batch: BatchRecord | null;
  reviews: ReviewRecord[];
  actioningBatch: string;
  onClose: () => void;
  onAction: (batch: BatchRecord, action: BatchAction) => void;
  onViewReview: (review: ReviewRecord) => void;
}) {
  const open = Boolean(batch);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  useBodyScrollLock(open);
  useEffect(() => {
    setPage(1);
  }, [batch?.id, reviews.length]);
  if (!batch) return null;

  const totalPages = Math.max(1, Math.ceil(reviews.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const paginatedReviews = reviews.slice((safePage - 1) * pageSize, safePage * pageSize);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-foreground/30 backdrop-blur-sm">
      <div className="flex h-full w-full max-w-5xl flex-col overflow-hidden border-l bg-card shadow-2xl">
        <div className="flex shrink-0 flex-wrap items-start justify-between gap-4 border-b bg-secondary/35 px-6 py-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold">{batch.name || "Batch Summary"}</h2>
              <Badge variant={statusVariant(batch.status)}>{batch.status}</Badge>
              <Badge variant="outline">{batchFormKey(batch)}</Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{batch.description || batch.id}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <BatchActionButtons batch={batch} actioningBatch={actioningBatch} onAction={onAction} />
            <Button type="button" variant="ghost" size="icon" className="h-9 w-9" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="chat-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto p-6">
          <div className="grid gap-3 md:grid-cols-4">
            <MetricCard label="Progress" value={formatPct(batch.progress_percent)} helper={progressCounts(batch)} />
            <MetricCard label="Runtime" value={formatRuntime(batch.duration_seconds)} helper={`Started ${formatDate(batch.started_at ?? batch.created_at)}`} />
            <MetricCard label="Errors" value={batch.failed_count} helper={batch.error_message || "No batch-level error"} />
            <MetricCard label="Cost/Tokens" value="-" helper="Not tracked yet" />
          </div>
          <ProgressBar value={batch.progress_percent} />
          <div className="overflow-hidden rounded-lg border">
            <div className="border-b bg-secondary/35 px-4 py-3">
              <p className="text-sm font-semibold">Individual Forms</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-sm">
                <thead className="border-b bg-secondary/50 text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">Claim</th>
                    <th className="px-4 py-3 text-left font-medium">Status</th>
                    <th className="px-4 py-3 text-left font-medium">Form</th>
                    <th className="px-4 py-3 text-left font-medium">Updated</th>
                    <th className="px-4 py-3 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {reviews.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="h-20 text-center text-muted-foreground">
                        No forms loaded for this batch yet.
                      </td>
                    </tr>
                  ) : (
                    paginatedReviews.map((review) => (
                      <tr key={review.id} className="border-b last:border-b-0">
                        <td className="px-4 py-3 font-medium">{getClaimNumber(review) || review.id.slice(0, 8)}</td>
                        <td className="px-4 py-3">
                          <Badge variant={reviewStatusVariant(review.status)}>{review.status ?? "queued"}</Badge>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="outline">{review.form_id}@{review.form_version}</Badge>
                        </td>
                        <td className="px-4 py-3">{formatDate(review.updated_at)}</td>
                        <td className="px-4 py-3 text-right">
                          <Button type="button" variant="ghost" size="sm" onClick={() => onViewReview(review)} disabled={!getUserVersion(review)}>
                            <Eye className="h-3.5 w-3.5" />
                            View
                          </Button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-secondary/25 px-4 py-3 text-xs text-muted-foreground">
              <span>
                Showing {reviews.length ? (safePage - 1) * pageSize + 1 : 0}-
                {Math.min(safePage * pageSize, reviews.length)} of {reviews.length} forms
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={pageSize}
                  onChange={(event) => {
                    setPageSize(Number(event.target.value));
                    setPage(1);
                  }}
                  className="h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value={25}>25 rows</option>
                  <option value={50}>50 rows</option>
                  <option value={100}>100 rows</option>
                </select>
                <Button type="button" variant="outline" size="sm" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={safePage <= 1}>
                  Previous
                </Button>
                <span className="tabular-nums">
                  Page {safePage} of {totalPages}
                </span>
                <Button type="button" variant="outline" size="sm" onClick={() => setPage((current) => Math.min(totalPages, current + 1))} disabled={safePage >= totalPages}>
                  Next
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="mt-3 h-2 overflow-hidden rounded-full bg-secondary">
      <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.min(Math.max(value, 0), 100)}%` }} />
    </div>
  );
}

function LoadingState({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center gap-2 px-4 py-8 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}

function EmptyState({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="px-4 py-8 text-center">
      <div className="mx-auto flex h-10 w-10 items-center justify-center">{icon}</div>
      <p className="mt-2 text-sm font-medium">{title}</p>
    </div>
  );
}

function ReadOnlyFormDialog({
  formDefinition,
  onClose,
}: {
  formDefinition: AuditFormDefinition | null;
  onClose: () => void;
}) {
  useBodyScrollLock(Boolean(formDefinition));
  if (!formDefinition) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 p-4 backdrop-blur-sm">
      <div className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border bg-card shadow-2xl">
        <DialogHeader title={formDefinition.title} subtitle={`${formDefinition.id}@${formDefinition.version}`} onClose={onClose} />
        <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto p-5">
          <ReadOnlyFormPanel form={formDefinition.canonical} />
        </div>
      </div>
    </div>
  );
}

function ReviewFormDialog({ review, onClose }: { review: ReviewRecord | null; onClose: () => void }) {
  const form = review ? getUserVersion(review) : null;
  useBodyScrollLock(Boolean(review));
  if (!review || !form) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 p-4 backdrop-blur-sm">
      <div className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border bg-card shadow-2xl">
        <DialogHeader title={form.title} subtitle={getClaimNumber(review) || review.id} onClose={onClose} />
        <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto p-5">
          <ReadOnlyFormPanel form={form} />
        </div>
      </div>
    </div>
  );
}

function DialogHeader({ title, subtitle, onClose }: { title: string; subtitle: string; onClose: () => void }) {
  return (
    <div className="flex shrink-0 items-start gap-4 border-b bg-secondary/35 px-6 py-5">
      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border bg-background text-primary">
        <FileText className="h-6 w-6" />
      </div>
      <div className="min-w-0">
        <h2 className="text-xl font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </div>
      <Button type="button" variant="ghost" size="icon" className="ml-auto h-9 w-9" onClick={onClose}>
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}

function ReadOnlyFormPanel({ form }: { form: AuditFormResult }) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-background p-4">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-semibold">{form.title}</p>
          <Badge variant={form.overall_outcome === "Meets" ? "success" : "danger"}>{form.overall_outcome}</Badge>
        </div>
        <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">{form.outcome_justification || form.description}</p>
      </div>
      <div className="space-y-3">
        {form.questions.map((question) => (
          <ReadOnlyQuestion key={question.id} question={question} />
        ))}
      </div>
    </div>
  );
}

function ReadOnlyQuestion({ question }: { question: FormQuestion }) {
  return (
    <div className="rounded-lg border bg-background p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-xs font-semibold text-primary">{question.id}</p>
          <p className="mt-1 text-sm">{question.text}</p>
        </div>
        <Badge variant={question.answer === "Yes" ? "success" : "danger"}>{question.answer}</Badge>
      </div>
      {question.sub_questions?.length ? (
        <div className="mt-3 grid gap-2">
          {question.sub_questions.map((subQuestion) => (
            <div key={subQuestion.id} className="rounded-md border bg-card px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[11px] font-semibold text-muted-foreground">{subQuestion.id}</span>
                <Badge variant={subQuestion.answer ? "warning" : "outline"}>{subQuestion.answer ? "applies" : "not applicable"}</Badge>
              </div>
              <p className="mt-1 text-sm">{subQuestion.text}</p>
              {subQuestion.reasoning ? <p className="mt-1 text-xs text-muted-foreground">{subQuestion.reasoning}</p> : null}
            </div>
          ))}
        </div>
      ) : question.comments || question.citations ? (
        <div className="mt-3 rounded-md border bg-card px-3 py-2 text-xs text-muted-foreground">
          {question.comments ? <p>{question.comments}</p> : null}
          {question.citations ? <p className="mt-1">{question.citations}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
