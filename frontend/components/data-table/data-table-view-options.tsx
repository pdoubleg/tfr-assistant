"use client";

import type { Table } from "@tanstack/react-table";
import { CheckSquare, Columns3, Square } from "lucide-react";

import { cn } from "@/lib/utils";

export function DataTableViewOptions<TData>({
  table,
  className,
}: {
  table: Table<TData>;
  className?: string;
}) {
  const hidableColumns = table
    .getAllLeafColumns()
    .filter((column) => column.getCanHide());
  const visibleHidableColumns = hidableColumns.filter((column) => column.getIsVisible()).length;
  const allColumnsVisible = hidableColumns.length > 0 && visibleHidableColumns === hidableColumns.length;
  const noColumnsVisible = visibleHidableColumns === 0;

  const setAllColumnsVisible = (visible: boolean) => {
    hidableColumns.forEach((column) => column.toggleVisibility(visible));
  };

  return (
    <details className={cn("relative", className)}>
      <summary className="inline-flex h-8 cursor-pointer list-none items-center justify-center gap-1.5 rounded-md border border-input bg-background px-3 text-xs font-medium transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        <Columns3 className="h-3.5 w-3.5" />
        Columns
      </summary>
      <div className="absolute right-0 z-[80] mt-2 w-64 overflow-hidden rounded-md border bg-card p-2 text-card-foreground shadow-lg">
        <div className="border-b px-2 pb-2">
          <p className="text-xs font-semibold">Visible columns</p>
          <div className="mt-2 grid grid-cols-2 gap-1">
            <button
              type="button"
              className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md px-2 text-xs font-medium hover:bg-secondary disabled:pointer-events-none disabled:opacity-50"
              onClick={() => setAllColumnsVisible(true)}
              disabled={allColumnsVisible}
            >
              <CheckSquare className="h-3.5 w-3.5" />
              Select all
            </button>
            <button
              type="button"
              className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md px-2 text-xs font-medium hover:bg-secondary disabled:pointer-events-none disabled:opacity-50"
              onClick={() => setAllColumnsVisible(false)}
              disabled={noColumnsVisible}
            >
              <Square className="h-3.5 w-3.5" />
              Unselect all
            </button>
          </div>
        </div>
        <div className="max-h-72 overflow-y-auto py-1">
          {hidableColumns.map((column) => {
            const label = column.columnDef.meta?.label ?? column.id;
            return (
              <label
                key={column.id}
                className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-secondary/60"
              >
                <input
                  type="checkbox"
                  checked={column.getIsVisible()}
                  onChange={(event) => column.toggleVisibility(event.target.checked)}
                  className="h-4 w-4 rounded border-input accent-primary"
                />
                <span className="truncate">{label}</span>
              </label>
            );
          })}
        </div>
      </div>
    </details>
  );
}
