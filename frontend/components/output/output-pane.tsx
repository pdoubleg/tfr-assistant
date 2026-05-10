"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  FileText,
  FolderArchive,
  Loader2,
  RefreshCw,
  Search,
  X,
} from "lucide-react";

import { OutputRenderer } from "@/components/output/output-renderer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  getBatchRunName,
  getClaimNumber,
  getReview,
  getUserVersion,
  listReviews,
  updateReviewUserVersion,
} from "@/lib/api";
import type { AuditFormResult, OutputComponent, ReviewRecord } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTfrAgent } from "@/hooks/use-tfr-agent";

const RECENT_LIMIT = 12;

interface OutputPaneProps {
  runNameFilter?: string;
  runNameFilterNonce?: number;
}

function formatSavedFormDate(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "numeric",
    year: "2-digit",
  }).format(date);
}

function getReviewSearchIds(review: ReviewRecord): string[] {
  const form = getUserVersion(review);
  const ids = [
    review.id,
    review.form_id,
    review.form_version,
    getBatchRunName(review),
    form?.id,
    form?.form_id,
    form?.form_version,
    review.original?.id,
    review.original?.form_id,
    review.original?.form_version,
  ].filter((value): value is string => Boolean(value));

  if (review.form_id && review.form_version) {
    ids.push(`${review.form_id}@${review.form_version}`);
  }
  if (form?.form_id && form.form_version) {
    ids.push(`${form.form_id}@${form.form_version}`);
  }

  return Array.from(new Set(ids));
}

function componentFromReview(review: ReviewRecord, collapsed = false): OutputComponent | null {
  const form = getUserVersion(review);
  if (!form) return null;
  return {
    id: `audit-form-${review.id}`,
    type: "audit_form",
    reviewId: review.id,
    title: form.title,
    form,
    source: review.source,
    createdAt: review.created_at,
    updatedAt: review.updated_at,
    claimNumber: getClaimNumber(review),
    collapsed,
  };
}

export function OutputPane({ runNameFilter = "", runNameFilterNonce = 0 }: OutputPaneProps) {
  const {
    state,
    outputComponents,
    openOutputComponent,
    closeOutputComponent,
    collapseOutputComponent,
    expandOutputComponent,
  } = useTfrAgent();
  const [showSavedForms, setShowSavedForms] = useState(false);
  const [reviews, setReviews] = useState<ReviewRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [claimQuery, setClaimQuery] = useState("");
  const [formQuery, setFormQuery] = useState("");
  const openedFromChatRef = useRef<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const nextReviews = await listReviews();
      setReviews(nextReviews);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load saved forms.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!runNameFilter) return;
    setShowSavedForms(true);
    setFormQuery(runNameFilter);
    void refresh();
  }, [refresh, runNameFilter, runNameFilterNonce]);

  useEffect(() => {
    const reviewId = state.active_review_id;
    if (!reviewId || openedFromChatRef.current.has(reviewId)) return;
    const activeReviewId: string = reviewId;
    openedFromChatRef.current.add(activeReviewId);

    async function openActiveReview() {
      try {
        const review = await getReview(activeReviewId);
        const component = componentFromReview(review, false);
        if (component) {
          openOutputComponent(component);
        }
        void refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to open generated form.");
      }
    }

    void openActiveReview();
  }, [openOutputComponent, refresh, state.active_review_id]);

  const filteredReviews = useMemo(() => {
    const claim = claimQuery.trim().toLowerCase();
    const reviewOrFormId = formQuery.trim().toLowerCase();
    return reviews
      .filter((review) => review.status === "completed")
      .filter((review) => {
        if (!claim) return true;
        return getClaimNumber(review).toLowerCase().includes(claim);
      })
      .filter((review) => {
        if (!reviewOrFormId) return true;
        return getReviewSearchIds(review).some((id) =>
          id.toLowerCase().includes(reviewOrFormId),
        );
      })
      .slice(0, RECENT_LIMIT);
  }, [claimQuery, formQuery, reviews]);
  const openAuditFormCount = outputComponents.filter(
    (component) => "reviewId" in component,
  ).length;

  const openReview = async (review: ReviewRecord) => {
    const componentId = `audit-form-${review.id}`;
    if (outputComponents.some((component) => component.id === componentId)) {
      closeOutputComponent(componentId);
      return;
    }

    const component = componentFromReview(review, true);
    if (component) {
      openOutputComponent(component);
      return;
    }

    const loaded = await getReview(review.id);
    const loadedComponent = componentFromReview(loaded, true);
    if (loadedComponent) {
      openOutputComponent(loadedComponent);
    }
  };

  const submitAuditForm = async (reviewId: string, form: AuditFormResult) => {
    const updated = await updateReviewUserVersion(reviewId, form);
    const currentComponent = outputComponents.find(
      (candidate) => "reviewId" in candidate && candidate.reviewId === reviewId,
    );
    const component = componentFromReview(updated, Boolean(currentComponent?.collapsed));
    if (component) {
      openOutputComponent(component);
    }
    void refresh();
  };

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-lg border bg-card shadow-sm">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
        <ClipboardCheck className="h-4 w-4 text-primary" />
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">Output</h2>
        </div>
        {outputComponents.length ? (
          <Badge variant="secondary" className="ml-1">
            {outputComponents.length} open
          </Badge>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          {state.status === "using_tools" || state.status === "thinking" ? (
            <Badge variant="outline" className="gap-1">
              <Loader2 className="h-3 w-3 animate-spin" />
              Agent
            </Badge>
          ) : null}
          {openAuditFormCount > 1 ? (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => outputComponents.forEach((component) => expandOutputComponent(component.id))}
              >
                <ChevronDown className="h-3.5 w-3.5" />
                Expand All
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => outputComponents.forEach((component) => collapseOutputComponent(component.id))}
              >
                <ChevronRight className="h-3.5 w-3.5" />
                Collapse All
              </Button>
            </>
          ) : null}
          <Button
            type="button"
            variant={showSavedForms ? "secondary" : "outline"}
            size="sm"
            className="gap-1.5"
            onClick={() => setShowSavedForms((current) => !current)}
          >
            <FolderArchive className="h-3.5 w-3.5" />
            Saved Forms
          </Button>
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={refresh}
            disabled={loading}
            title="Refresh saved forms"
            aria-label="Refresh saved forms"
          >
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          </Button>
        </div>
      </div>

      {showSavedForms ? (
        <div className="border-b bg-background">
          <div className="grid gap-3 border-b bg-secondary/35 p-3 md:grid-cols-[1fr_1fr_auto]">
            <label className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={claimQuery}
                onChange={(event) => setClaimQuery(event.target.value)}
                className="h-8 pl-8 text-xs"
                placeholder="Claim number"
              />
            </label>
            <label className="relative">
              <FileText className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={formQuery}
                onChange={(event) => setFormQuery(event.target.value)}
                className="h-8 pl-8 text-xs"
                placeholder="Run, review, or form ID"
              />
            </label>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="gap-1.5"
              onClick={() => {
                setClaimQuery("");
                setFormQuery("");
              }}
              disabled={!claimQuery && !formQuery}
            >
              <X className="h-3.5 w-3.5" />
              Clear
            </Button>
          </div>

          <div className="max-h-72 overflow-y-auto">
            {error ? (
              <div className="px-4 py-3 text-sm text-destructive">{error}</div>
            ) : null}
            {loading && reviews.length === 0 ? (
              <div className="flex items-center justify-center gap-2 px-4 py-8 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading saved forms
              </div>
            ) : null}
            {!loading && filteredReviews.length === 0 ? (
              <div className="px-4 py-8 text-center">
                <FolderArchive className="mx-auto h-8 w-8 text-muted-foreground/35" />
                <p className="mt-2 text-sm font-medium">No saved forms found</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Generate an audit result or adjust the filters.
                </p>
              </div>
            ) : null}
            {filteredReviews.map((review) => {
              const form = getUserVersion(review);
              const claimNumber = getClaimNumber(review);
              const runName = getBatchRunName(review);
              const rowDate = formatSavedFormDate(review.updated_at ?? review.created_at);
              const opened = outputComponents.some((component) => component.id === `audit-form-${review.id}`);
              return (
                <button
                  key={review.id}
                  type="button"
                  onClick={() => void openReview(review)}
                  className={cn(
                    "grid w-full gap-3 border-b px-4 py-3 text-left transition-colors hover:bg-secondary/45 md:grid-cols-[1fr_auto]",
                    opened && "bg-primary/5",
                  )}
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-sm font-medium">{form?.title ?? review.id}</p>
                      {opened ? <Badge variant="outline">Open</Badge> : null}
                    </div>
                    <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">
                      {form?.description ?? review.error_message ?? "Completed audit review"}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 md:justify-end">
                    {claimNumber ? <Badge variant="secondary">{claimNumber}</Badge> : null}
                    {runName ? <Badge variant="outline">{runName}</Badge> : null}
                    {rowDate ? <Badge variant="outline">{rowDate}</Badge> : null}
                    <Badge variant="outline">{review.form_id ?? form?.form_id}</Badge>
                    <Badge variant={form?.overall_outcome === "Meets" ? "success" : "danger"}>
                      {form?.overall_outcome ?? review.status}
                    </Badge>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      <div className="chat-scrollbar flex min-h-0 flex-1 flex-col overflow-y-auto bg-background/60 p-4">
        {outputComponents.length === 0 ? (
          <div className="flex min-h-[420px] flex-1 flex-col items-center justify-center rounded-lg border border-dashed bg-card/60 p-8 text-center">
            <ClipboardCheck className="h-10 w-10 text-muted-foreground/35" />
            <h3 className="mt-3 text-sm font-semibold text-foreground/75">No output open</h3>
            <p className="mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">
              Open a saved form from the menu, or ask the assistant to generate an audit result.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {outputComponents.map((component) => (
              <OutputRenderer
                key={component.id}
                component={component}
                onSubmitAuditForm={submitAuditForm}
                onClose={closeOutputComponent}
                onCollapse={collapseOutputComponent}
                onExpand={expandOutputComponent}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
