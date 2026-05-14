"use client";

import type { Column } from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown, EyeOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function DataTableColumnHeader<TData, TValue>({
  column,
  title,
  className,
}: {
  column: Column<TData, TValue>;
  title: string;
  className?: string;
}) {
  if (!column.getCanSort()) {
    return <span className={cn("truncate", className)}>{title}</span>;
  }

  const sorted = column.getIsSorted();
  const SortIcon = sorted === "desc" ? ArrowDown : sorted === "asc" ? ArrowUp : ChevronsUpDown;

  return (
    <div className={cn("flex items-center gap-1", className)}>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="-ml-2 h-8 gap-1.5 px-2 text-xs"
        onClick={() => column.toggleSorting(sorted === "asc")}
        title={`Sort by ${title}`}
        aria-label={`Sort by ${title}`}
      >
        <span className="truncate">{title}</span>
        <SortIcon className={cn("h-3.5 w-3.5", !sorted && "text-muted-foreground/55")} />
      </Button>
      {column.getCanHide() ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground opacity-0 transition-opacity group-hover/header:opacity-100"
          onClick={() => column.toggleVisibility(false)}
          title={`Hide ${title}`}
          aria-label={`Hide ${title}`}
        >
          <EyeOff className="h-3.5 w-3.5" />
        </Button>
      ) : null}
    </div>
  );
}
