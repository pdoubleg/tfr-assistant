"use client";

import { Bot, Tag } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function EvalRoleBadge({
  role,
  referenceKind,
  className,
}: {
  role?: string;
  referenceKind?: string;
  className?: string;
}) {
  if (role === "model") {
    return (
      <Badge
        variant="outline"
        className={cn(
          "gap-1.5 whitespace-nowrap border-sky-500/30 bg-sky-500/15 text-sky-700 dark:text-sky-300",
          className,
        )}
        title="Model generated eval result"
      >
        <Bot className="h-3 w-3" />
        Model
      </Badge>
    );
  }

  if (role === "ground_truth") {
    const label = referenceKind || "GT";
    return (
      <Badge
        variant="outline"
        className={cn(
          "gap-1.5 whitespace-nowrap border-amber-500/35 bg-amber-400/20 text-amber-800 dark:text-amber-200",
          className,
        )}
        title={`Ground truth ${label}`}
      >
        <Tag className="h-3 w-3 fill-current" />
        {label}
      </Badge>
    );
  }

  return <span className="text-xs text-muted-foreground">-</span>;
}
