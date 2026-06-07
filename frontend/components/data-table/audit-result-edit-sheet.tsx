"use client";

import { FilePenLine, X } from "lucide-react";

import {
  ReviewFeedbackButton,
  ReviewFeedbackSubmittedCount,
} from "@/components/feedback/review-feedback-button";
import { AuditQuestionForm } from "@/components/output/audit-question-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formStatusLabels, formStatusVariant, type ReviewFormStatus } from "@/lib/dashboard-data";
import type { AuditFormResult } from "@/lib/types";

export interface AuditResultEditSheetRow {
  reviewId: string;
  title: string;
  formKey: string;
  edited: boolean;
  finalized: boolean;
  formStatus: ReviewFormStatus;
  claimNumber: string;
  form: AuditFormResult;
  feedbackCount: number;
  feedbackEnabled: boolean;
  firstFinalizedAt: string;
  lastFinalizedAt: string;
  createdAt: string;
  updatedAt: string;
  source: string;
}

export function AuditResultEditSheet({
  row,
  onClose,
  onSubmit,
  onFinalize,
  onFeedbackSubmitted,
}: {
  row: AuditResultEditSheetRow | null;
  onClose: () => void;
  onSubmit: (form: AuditFormResult) => Promise<void>;
  onFinalize?: (form: AuditFormResult) => Promise<void>;
  onFeedbackSubmitted?: (reviewId: string) => void | Promise<void>;
}) {
  if (!row) return null;

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        className="absolute inset-0 bg-foreground/30 backdrop-blur-[1px]"
        onClick={onClose}
        aria-label="Close form editor"
      />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-5xl flex-col border-l bg-background shadow-2xl">
        <header className="flex shrink-0 items-start gap-3 border-b bg-secondary/35 p-5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-primary">
            <FilePenLine className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-lg font-semibold">{row.title}</h2>
              <Badge variant="outline" className="font-mono text-[10px]">
                {row.formKey}
              </Badge>
              <Badge variant={formStatusVariant(row.formStatus)}>
                {formStatusLabels[row.formStatus]}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {row.claimNumber ? `Claim ${row.claimNumber}` : row.reviewId}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {row.feedbackEnabled ? (
              <>
                <ReviewFeedbackSubmittedCount count={row.feedbackCount} />
                <ReviewFeedbackButton
                  reviewId={row.reviewId}
                  claimNumber={row.claimNumber}
                  variant="outline"
                  size="sm"
                  onSubmitted={() => onFeedbackSubmitted?.(row.reviewId)}
                />
              </>
            ) : null}
            <Button type="button" variant="ghost" size="icon" onClick={onClose} title="Close" aria-label="Close">
              <X className="h-5 w-5" />
            </Button>
          </div>
        </header>
        <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto p-5">
          <AuditQuestionForm
            reviewId={row.reviewId}
            form={row.form}
            onSubmit={onSubmit}
            onFinalize={onFinalize}
            onClose={onClose}
            metadata={{
              claimNumber: row.claimNumber,
              finalized: row.finalized,
              firstFinalizedAt: row.firstFinalizedAt,
              lastFinalizedAt: row.lastFinalizedAt,
              createdAt: row.createdAt,
              updatedAt: row.updatedAt,
              source: row.source,
            }}
            submitLabel="Save Changes"
          />
        </div>
      </aside>
    </div>
  );
}
