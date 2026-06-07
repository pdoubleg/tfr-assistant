"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  MessageSquarePlus,
  Star,
  X,
} from "lucide-react";

import { Button, type ButtonProps } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { submitReviewFeedback } from "@/lib/api";
import type { FeedbackRecord } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ReviewFeedbackButtonProps {
  reviewId: string;
  claimNumber?: string;
  onSubmitted?: (feedback: FeedbackRecord) => void | Promise<void>;
  variant?: ButtonProps["variant"];
  size?: ButtonProps["size"];
  className?: string;
  iconOnly?: boolean;
}

export function ReviewFeedbackButton({
  reviewId,
  claimNumber = "",
  onSubmitted,
  variant = "outline",
  size = "sm",
  className,
  iconOnly = false,
}: ReviewFeedbackButtonProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        type="button"
        variant={variant}
        size={size}
        className={cn("gap-1.5", className)}
        onClick={() => setOpen(true)}
        title="Leave feedback on this generated form"
        aria-label="Leave feedback on this generated form"
      >
        <MessageSquarePlus className="h-4 w-4" />
        {iconOnly ? <span className="sr-only">Feedback</span> : "Feedback"}
      </Button>
      {open ? (
        <ReviewFeedbackDialog
          reviewId={reviewId}
          claimNumber={claimNumber}
          onClose={() => setOpen(false)}
          onSubmitted={async (feedback) => {
            await onSubmitted?.(feedback);
            setOpen(false);
          }}
        />
      ) : null}
    </>
  );
}

export function ReviewFeedbackSubmittedCount({ count }: { count?: number }) {
  const safeCount = Math.max(0, count ?? 0);

  return (
    <span
      className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border bg-background px-2.5 text-xs font-medium text-muted-foreground"
      title={`${safeCount} feedback submission${safeCount === 1 ? "" : "s"}`}
      aria-label={`${safeCount} feedback submission${safeCount === 1 ? "" : "s"}`}
    >
      <CheckCircle2 className="h-3.5 w-3.5 text-primary" />
      {safeCount} submitted
    </span>
  );
}

function ReviewFeedbackDialog({
  reviewId,
  claimNumber,
  onClose,
  onSubmitted,
}: {
  reviewId: string;
  claimNumber: string;
  onClose: () => void;
  onSubmitted: (feedback: FeedbackRecord) => void | Promise<void>;
}) {
  const [score, setScore] = useState(0);
  const [hoverScore, setHoverScore] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [zeroWarning, setZeroWarning] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const activeScore = hoverScore ?? score;

  const chooseScore = (value: number) => {
    setScore((current) => (current === value ? 0 : value));
    setZeroWarning(false);
    setError("");
  };

  const submit = async () => {
    if (score === 0 && !zeroWarning) {
      setZeroWarning(true);
      setError("");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const feedback = await submitReviewFeedback({
        review_id: reviewId,
        score,
        comment: comment.trim() || null,
      });
      setSubmitted(true);
      await onSubmitted(feedback);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to submit feedback.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-foreground/35 p-4 backdrop-blur-sm">
      <button
        type="button"
        className="absolute inset-0"
        onClick={submitting ? undefined : onClose}
        aria-label="Close feedback dialog"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-feedback-title"
        className="relative w-full max-w-md overflow-hidden rounded-lg border bg-card shadow-2xl"
      >
        <div className="flex items-start gap-3 border-b bg-secondary/35 p-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-primary">
            <MessageSquarePlus className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="review-feedback-title" className="text-base font-semibold">
              Review Feedback
            </h2>
            <p className="mt-1 truncate text-xs text-muted-foreground">
              {claimNumber ? `Claim ${claimNumber}` : `Review ${reviewId.slice(0, 8)}`}
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onClose}
            disabled={submitting}
            title="Close feedback dialog"
            aria-label="Close feedback dialog"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-4 p-4">
          <div>
            <p className="text-sm font-medium">Rating</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1" onMouseLeave={() => setHoverScore(null)}>
                {[1, 2, 3, 4, 5].map((value) => (
                  <button
                    key={value}
                    type="button"
                    className="rounded p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-amber-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    onMouseEnter={() => setHoverScore(value)}
                    onFocus={() => setHoverScore(value)}
                    onBlur={() => setHoverScore(null)}
                    onClick={() => chooseScore(value)}
                    title={score === value ? "Clear rating" : `${value} star${value === 1 ? "" : "s"}`}
                    aria-label={score === value ? "Clear rating" : `${value} star${value === 1 ? "" : "s"}`}
                  >
                    <Star
                      className={cn(
                        "h-6 w-6",
                        value <= activeScore && "fill-amber-400 text-amber-500",
                      )}
                    />
                  </button>
                ))}
              </div>
              <span className="text-xs text-muted-foreground">
                {score}/5
              </span>
            </div>
          </div>

          <label className="grid gap-2">
            <span className="text-sm font-medium">Comments</span>
            <Textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="What should the agent preserve or improve next time?"
              disabled={submitting || submitted}
            />
          </label>

          {zeroWarning ? (
            <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-200">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>No stars selected will submit a 0-star score. Submit again to confirm.</span>
            </div>
          ) : null}
          {error ? (
            <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}
          {submitted ? (
            <div className="flex items-start gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-300">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              <span>Feedback submitted.</span>
            </div>
          ) : null}
        </div>

        <div className="flex items-center justify-end gap-2 border-t bg-secondary/20 p-4">
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="button" onClick={() => void submit()} disabled={submitting || submitted}>
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageSquarePlus className="h-4 w-4" />}
            {score === 0 && zeroWarning ? "Confirm 0 Stars" : "Submit Feedback"}
          </Button>
        </div>
      </div>
    </div>
  );
}
