"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Clock3,
  FileText,
  FolderArchive,
  Loader2,
  Pencil,
  PlayCircle,
  Plus,
  RefreshCw,
  Rows3,
  Search,
  X,
} from "lucide-react";

import { BatchRunDialog } from "@/components/app-shell/batch-run-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  createBatchTemplate,
  launchBatchTemplate,
  listBatchTemplates,
  listFormCatalog,
  updateBatchTemplate,
} from "@/lib/api";
import type {
  BatchRecord,
  BatchTemplatePayload,
  BatchTemplateRecord,
  FormCatalogEntry,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface BatchQueuePanelProps {
  onBatchCompleted?: (runName: string) => void;
}

function isRunningRun(run?: BatchRecord | null): boolean {
  return run?.status === "running";
}

function statusVariant(status?: string): "secondary" | "outline" | "success" | "danger" | "warning" {
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "running") return "warning";
  return "secondary";
}

function formatRuntime(seconds?: number | null): string {
  if (!seconds) return "";
  const rounded = Math.max(1, Math.round(seconds));
  const minutes = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  if (!minutes) return `${remainder}s`;
  return `${minutes}m ${remainder}s`;
}

function formatDate(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function getRunCounts(run?: BatchRecord | null): string {
  if (!run) return "No runs yet";
  const pending = Math.max(0, run.total_count - run.completed_count - run.failed_count);
  return `${run.completed_count}/${run.total_count} complete${run.failed_count ? ` · ${run.failed_count} failed` : ""}${pending ? ` · ${pending} pending` : ""}`;
}

export function BatchQueuePanel({ onBatchCompleted }: BatchQueuePanelProps) {
  const [templates, setTemplates] = useState<BatchTemplateRecord[]>([]);
  const [forms, setForms] = useState<FormCatalogEntry[]>([]);
  const [showSavedJobs, setShowSavedJobs] = useState(false);
  const [jobNameQuery, setJobNameQuery] = useState("");
  const [renderedTemplateIds, setRenderedTemplateIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [launchingId, setLaunchingId] = useState("");
  const [error, setError] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<BatchTemplateRecord | null>(null);
  const knownRunStatuses = useRef<Map<string, string>>(new Map());

  const activeCount = useMemo(
    () => templates.filter((template) => isRunningRun(template.latest_run)).length,
    [templates],
  );
  const filteredSavedJobs = useMemo(() => {
    const query = jobNameQuery.trim().toLowerCase();
    if (!query) return templates;
    return templates.filter((template) => template.name.toLowerCase().includes(query));
  }, [jobNameQuery, templates]);
  const renderedTemplates = useMemo(
    () => templates.filter((template) => renderedTemplateIds.includes(template.id)),
    [renderedTemplateIds, templates],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextForms, nextTemplates] = await Promise.all([
        listFormCatalog(),
        listBatchTemplates(),
      ]);
      setForms(nextForms);
      setTemplates(nextTemplates);
      setRenderedTemplateIds((current) =>
        current.filter((templateId) =>
          nextTemplates.some((template) => template.id === templateId),
        ),
      );

      for (const template of nextTemplates) {
        const latest = template.latest_run;
        if (!latest) continue;
        const previous = knownRunStatuses.current.get(latest.id);
        knownRunStatuses.current.set(latest.id, latest.status);
        if (
          previous &&
          previous !== "completed" &&
          latest.status === "completed"
        ) {
          onBatchCompleted?.(template.name);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load batch runs.");
    } finally {
      setLoading(false);
    }
  }, [onBatchCompleted]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const openCreateDialog = () => {
    setEditingTemplate(null);
    setDialogOpen(true);
  };

  const toggleRenderedTemplate = (templateId: string) => {
    setRenderedTemplateIds((current) =>
      current.includes(templateId)
        ? current.filter((candidate) => candidate !== templateId)
        : [templateId, ...current],
    );
  };

  const closeRenderedTemplate = (templateId: string) => {
    setRenderedTemplateIds((current) => current.filter((candidate) => candidate !== templateId));
  };

  const openEditDialog = (template: BatchTemplateRecord) => {
    setEditingTemplate(template);
    setDialogOpen(true);
  };

  const saveTemplate = async (payload: BatchTemplatePayload) => {
    setSaving(true);
    setError("");
    try {
      let savedTemplate: BatchTemplateRecord;
      if (editingTemplate) {
        const { name: _name, ...updatePayload } = payload;
        savedTemplate = await updateBatchTemplate(editingTemplate.id, updatePayload);
      } else {
        savedTemplate = await createBatchTemplate(payload);
        setRenderedTemplateIds((current) =>
          current.includes(savedTemplate.id) ? current : [savedTemplate.id, ...current],
        );
      }
      setDialogOpen(false);
      setEditingTemplate(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save batch configuration.");
    } finally {
      setSaving(false);
    }
  };

  const launchTemplate = async (template: BatchTemplateRecord) => {
    setLaunchingId(template.id);
    setError("");
    try {
      const run = await launchBatchTemplate(template.id);
      knownRunStatuses.current.set(run.id, run.status);
      setRenderedTemplateIds((current) =>
        current.includes(template.id) ? current : [template.id, ...current],
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to launch batch run.");
    } finally {
      setLaunchingId("");
    }
  };

  return (
    <>
      <Card className="flex h-full min-h-0 flex-col overflow-hidden">
        <CardHeader className="border-b">
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="flex items-center gap-2">
              <Rows3 className="h-4 w-4 text-primary" />
              Batch Audits
            </CardTitle>
            <div className="flex items-center gap-2">
              {activeCount ? <Badge variant="warning">{activeCount} active</Badge> : null}
              {renderedTemplates.length ? <Badge variant="secondary">{renderedTemplates.length} open</Badge> : null}
              <Button
                type="button"
                variant={showSavedJobs ? "secondary" : "outline"}
                size="sm"
                className="gap-1.5"
                onClick={() => setShowSavedJobs((current) => !current)}
              >
                <FolderArchive className="h-3.5 w-3.5" />
                Saved Batch Jobs
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => void refresh()}
                disabled={loading}
                title="Refresh batch runs"
                aria-label="Refresh batch runs"
              >
                {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="chat-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto pt-5">
          {error ? (
            <div className="rounded-lg border border-destructive/35 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          ) : null}

          {showSavedJobs ? (
            <div className="overflow-hidden rounded-lg border bg-background">
              <div className="grid gap-3 border-b bg-secondary/35 p-3">
                <label className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={jobNameQuery}
                    onChange={(event) => setJobNameQuery(event.target.value)}
                    className="h-8 pl-8 text-xs"
                    placeholder="Filter by batch job name"
                  />
                </label>
              </div>

              <div className="max-h-72 overflow-y-auto">
                {loading && templates.length === 0 ? (
                  <div className="flex items-center justify-center gap-2 px-4 py-8 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading saved batch jobs
                  </div>
                ) : null}
                {!loading && templates.length === 0 ? (
                  <div className="px-4 py-8 text-center">
                    <FileText className="mx-auto h-8 w-8 text-muted-foreground/40" />
                    <p className="mt-2 text-sm font-medium">No saved batch jobs</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Create a run configuration to save a repeatable batch job.
                    </p>
                  </div>
                ) : null}
                {!loading && templates.length > 0 && filteredSavedJobs.length === 0 ? (
                  <div className="px-4 py-8 text-center">
                    <FolderArchive className="mx-auto h-8 w-8 text-muted-foreground/40" />
                    <p className="mt-2 text-sm font-medium">No saved batch jobs match</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Adjust the name filter.
                    </p>
                  </div>
                ) : null}
                {filteredSavedJobs.map((template) => {
                  const run = template.latest_run;
                  const opened = renderedTemplateIds.includes(template.id);
                  return (
                    <button
                      key={template.id}
                      type="button"
                      onClick={() => toggleRenderedTemplate(template.id)}
                      className={cn(
                        "grid w-full gap-3 border-b px-4 py-3 text-left transition-colors hover:bg-secondary/45 md:grid-cols-[1fr_auto]",
                        opened && "bg-primary/5",
                      )}
                    >
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="truncate text-sm font-medium">{template.name}</p>
                          {opened ? <Badge variant="outline">Open</Badge> : null}
                        </div>
                        <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">
                          {template.description || "No description"}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 md:justify-end">
                        <Badge variant={statusVariant(run?.status)}>{run?.status ?? "ready"}</Badge>
                        <Badge variant="outline">{getRunCounts(run)}</Badge>
                        <Badge variant="outline">{template.form_id}@{template.form_version}</Badge>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}

          {!loading && !renderedTemplates.length ? (
            <div className="rounded-lg border border-dashed bg-background p-5 text-center">
              <FolderArchive className="mx-auto h-8 w-8 text-muted-foreground/40" />
              <p className="mt-2 text-sm font-medium">No batch job open</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Open Saved Batch Jobs and select a job to render its card here.
              </p>
            </div>
          ) : null}

          {renderedTemplates.map((template) => {
            const run = template.latest_run;
            const active = isRunningRun(run);
            const runtime = formatRuntime(run?.duration_seconds);
            const launchedAt = formatDate(run?.started_at ?? run?.created_at);
            return (
              <div
                key={template.id}
                className={cn(
                  "rounded-lg border bg-background p-4 transition-colors",
                  active && "border-amber-300 bg-amber-50/40",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate font-medium">{template.name}</p>
                      <Badge variant={statusVariant(run?.status)}>
                        {run?.status ?? "ready"}
                      </Badge>
                    </div>
                    <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                      {template.description || "No description"}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0"
                    onClick={() => closeRenderedTemplate(template.id)}
                    aria-label={`Close ${template.name}`}
                    title="Close card"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>

                <div className="mt-4 grid gap-2 text-xs text-muted-foreground">
                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant="outline">{template.form_id}@{template.form_version}</Badge>
                    <Badge variant="outline">
                      {template.synthetic
                        ? "Synthetic"
                        : template.input_mode === "completed_intake"
                          ? "Completed Intake"
                          : template.input_mode === "manual_entry"
                            ? "Manual Entry"
                            : template.input_mode === "upload"
                              ? "Spreadsheet"
                              : "Direct"}
                    </Badge>
                    <Badge variant="outline">{template.item_count} reviews</Badge>
                    <Badge variant="outline">{template.run_count} runs</Badge>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span>{getRunCounts(run)}</span>
                    {launchedAt ? <span>· Started {launchedAt}</span> : null}
                    {runtime ? (
                      <span className="inline-flex items-center gap-1">
                        · <Clock3 className="h-3 w-3" />
                        {runtime}
                      </span>
                    ) : null}
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    type="button"
                    className="gap-2"
                    size="sm"
                    disabled={active || launchingId === template.id}
                    onClick={() => void launchTemplate(template)}
                  >
                    {launchingId === template.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <PlayCircle className="h-4 w-4" />
                    )}
                    Launch
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => openEditDialog(template)}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                    {active ? "Inspect" : "Edit"}
                  </Button>
                  {run?.status === "completed" ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => onBatchCompleted?.(template.name)}
                    >
                      Show Results
                    </Button>
                  ) : null}
                </div>
              </div>
            );
          })}

          <Button className="w-full gap-2" onClick={openCreateDialog}>
            <Plus className="h-4 w-4" />
            New Batch Audit
          </Button>
        </CardContent>
      </Card>

      <BatchRunDialog
        open={dialogOpen}
        template={editingTemplate}
        forms={forms}
        locked={Boolean(editingTemplate?.latest_run && isRunningRun(editingTemplate.latest_run))}
        saving={saving}
        onClose={() => {
          if (saving) return;
          setDialogOpen(false);
          setEditingTemplate(null);
        }}
        onSave={saveTemplate}
      />
    </>
  );
}
