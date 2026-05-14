"use client";

import type { Table } from "@tanstack/react-table";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const pageSizeOptions = [10, 25, 50, 100];

export function DataTablePagination<TData>({
  table,
  className,
}: {
  table: Table<TData>;
  className?: string;
}) {
  const filteredRows = table.getFilteredRowModel().rows.length;
  const selectedRows = Object.values(table.getState().rowSelection).filter(Boolean).length;
  const pageIndex = table.getState().pagination.pageIndex;
  const pageSize = table.getState().pagination.pageSize;
  const start = filteredRows === 0 ? 0 : pageIndex * pageSize + 1;
  const end = Math.min(filteredRows, (pageIndex + 1) * pageSize);

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 border-t bg-secondary/30 px-4 py-2 text-xs text-muted-foreground",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span>
          Showing <span className="tabular-nums">{start}-{end}</span> of{" "}
          <span className="tabular-nums">{filteredRows}</span>
        </span>
        {selectedRows ? (
          <span className="rounded-md border bg-background px-2 py-1 text-foreground">
            {selectedRows} selected
          </span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2">
          <span>Rows</span>
          <select
            value={pageSize}
            onChange={(event) => table.setPageSize(Number(event.target.value))}
            className="h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {pageSizeOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="hidden h-8 w-8 sm:inline-flex"
            onClick={() => table.setPageIndex(0)}
            disabled={!table.getCanPreviousPage()}
            title="First page"
            aria-label="First page"
          >
            <ChevronsLeft className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
            title="Previous page"
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-20 text-center tabular-nums text-foreground">
            {pageIndex + 1} / {table.getPageCount() || 1}
          </span>
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
            title="Next page"
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="hidden h-8 w-8 sm:inline-flex"
            onClick={() => table.setPageIndex(table.getPageCount() - 1)}
            disabled={!table.getCanNextPage()}
            title="Last page"
            aria-label="Last page"
          >
            <ChevronsRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
