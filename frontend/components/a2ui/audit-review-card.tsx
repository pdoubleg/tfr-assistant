"use client";

import { ClipboardCheck, ExternalLink, Pencil } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useTfrAgent } from "@/hooks/use-tfr-agent";
import { getClaimNumber, getReview, getUserVersion } from "@/lib/api";
import type { AuditFormResult, OutputComponent } from "@/lib/types";

export interface AuditReviewCardProps {
  reviewId: string;
  formId: string;
  formVersion: string;
  title: string;
  description?: string;
  claimNumber?: string;
  runName?: string;
  source?: string;
  status?: string;
  outcome?: string;
  feedbackCount?: number;
  createdAt?: string;
  updatedAt?: string;
  form: AuditFormResult;
}

export function AuditReviewCard({
  reviewId,
  formId,
  formVersion,
  title,
  description,
  claimNumber,
  runName,
  source,
  outcome,
  feedbackCount = 0,
  createdAt,
  updatedAt,
  form,
}: AuditReviewCardProps) {
  const {
    expandOutputComponent,
    openOutputComponent,
    outputComponents,
    setState,
  } = useTfrAgent();
  const [opening, setOpening] = useState(false);
  const [openError, setOpenError] = useState("");
  const componentId = `audit-form-${reviewId}`;
  const alreadyOpen = outputComponents.some((component) => component.id === componentId);
  const timestamp = formatDate(updatedAt || createdAt);

  const openReview = async () => {
    setState((current) => ({
      ...current,
      active_review_id: reviewId,
      selected_form_ids: [`${formId}@${formVersion}`],
    }));
    if (alreadyOpen) {
      expandOutputComponent(componentId);
      return;
    }

    setOpening(true);
    setOpenError("");
    let openedForm = form;
    let openedTitle = title || form.title;
    let openedSource = source;
    let openedCreatedAt = createdAt;
    let openedUpdatedAt = updatedAt;
    let openedClaimNumber = claimNumber;
    let openedFeedbackCount = feedbackCount;
    try {
      const review = await getReview(reviewId);
      openedForm = getUserVersion(review) ?? form;
      openedTitle = openedForm.title;
      openedSource = review.source;
      openedCreatedAt = review.created_at;
      openedUpdatedAt = review.updated_at;
      openedClaimNumber = getClaimNumber(review) || claimNumber;
      openedFeedbackCount = review.feedback_count ?? 0;
    } catch (error) {
      setOpenError(error instanceof Error ? error.message : "Failed to refresh review.");
    } finally {
      setOpening(false);
    }

    const component: OutputComponent = {
      id: componentId,
      type: "audit_form",
      reviewId,
      title: openedTitle,
      form: openedForm,
      source: openedSource,
      createdAt: openedCreatedAt,
      updatedAt: openedUpdatedAt,
      claimNumber: openedClaimNumber,
      feedbackCount: openedFeedbackCount,
      collapsed: false,
    };
    openOutputComponent(component);
  };

  return (
    <article className="overflow-hidden rounded-md border bg-background text-sm shadow-sm">
      <div className="flex items-start gap-3 border-b bg-secondary/45 px-3 py-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
          <ClipboardCheck className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-semibold">{title || "Audit review"}</h3>
            <Badge variant={outcome === "Meets" ? "success" : "danger"}>
              {outcome || "Review"}
            </Badge>
            {claimNumber ? <Badge variant="secondary">{claimNumber}</Badge> : null}
          </div>
          {description ? (
            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{description}</p>
          ) : null}
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <Badge variant="outline">{formId}@{formVersion}</Badge>
            {runName ? <Badge variant="outline">{runName}</Badge> : null}
            {source ? <Badge variant="outline">{source}</Badge> : null}
            {timestamp ? <Badge variant="outline">{timestamp}</Badge> : null}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 px-3 py-3">
        <Button type="button" size="sm" className="gap-1.5" onClick={() => void openReview()} disabled={opening}>
          {alreadyOpen ? <ExternalLink className="h-3.5 w-3.5" /> : <Pencil className="h-3.5 w-3.5" />}
          {opening ? "Opening..." : alreadyOpen ? "Show Open Form" : "Open / Edit Form"}
        </Button>
      </div>
      {openError ? (
        <div className="border-t bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
          Opened embedded result because the latest review could not be refreshed.
        </div>
      ) : null}
    </article>
  );
}

function formatDate(value: string | undefined) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
