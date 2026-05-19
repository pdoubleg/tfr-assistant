"use client";

import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type ToastVariant = "success" | "error" | "info";

function toastIcon(variant: ToastVariant): ReactNode {
  if (variant === "success") return <CheckCircle2 className="h-5 w-5" />;
  if (variant === "error") return <AlertTriangle className="h-5 w-5" />;
  return <Info className="h-5 w-5" />;
}

export function Toast({
  open,
  variant = "info",
  title,
  message,
  onClose,
}: {
  open: boolean;
  variant?: ToastVariant;
  title: string;
  message?: string;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!open || variant === "error") return;
    const timer = window.setTimeout(onClose, 2600);
    return () => window.clearTimeout(timer);
  }, [onClose, open, variant]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[100] flex justify-center px-4 sm:inset-x-auto sm:bottom-5 sm:right-5 sm:justify-end sm:px-0">
      <div
        role={variant === "error" ? "alert" : "status"}
        className={cn(
          "pointer-events-auto flex w-full max-w-md items-start gap-3 rounded-lg border border-border bg-card p-4 text-card-foreground shadow-xl shadow-black/10 ring-1 ring-border/50 dark:shadow-black/25",
        )}
      >
        <div
          className={cn(
            "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
            variant === "success" && "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
            variant === "error" && "border-destructive/15 bg-destructive/5 text-destructive",
            variant === "info" && "border-primary/15 bg-primary/5 text-primary",
          )}
        >
          {toastIcon(variant)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold leading-5">{title}</p>
          {message ? <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{message}</p> : null}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0 text-muted-foreground"
          onClick={onClose}
          aria-label="Dismiss notification"
          title="Dismiss"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    </div>,
    document.body,
  );
}
