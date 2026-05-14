"use client";

import { flexRender, type RowData, type Table as TanstackTable } from "@tanstack/react-table";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { DataTablePagination } from "@/components/data-table/data-table-pagination";
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

declare module "@tanstack/react-table" {
  interface ColumnMeta<TData extends RowData, TValue> {
    label?: string;
    align?: "left" | "center" | "right";
    headerClassName?: string;
    cellClassName?: string;
    description?: string;
  }
}

export function DataTable<TData>({
  table,
  toolbar,
  actionBar,
  emptyState,
  density = "normal",
  className,
}: {
  table: TanstackTable<TData>;
  toolbar?: ReactNode;
  actionBar?: ReactNode;
  emptyState?: ReactNode;
  density?: "compact" | "normal";
  className?: string;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const scrollbarRef = useRef<HTMLDivElement | null>(null);
  const tableRef = useRef<HTMLTableElement | null>(null);
  const [tableWidth, setTableWidth] = useState(1180);

  useEffect(() => {
    const scrollElement = scrollRef.current;
    const scrollbarElement = scrollbarRef.current;
    const tableElement = tableRef.current;
    if (!scrollElement || !scrollbarElement || !tableElement) return;

    let syncingMain = false;
    let syncingScrollbar = false;

    const syncWidth = () => {
      setTableWidth(Math.max(scrollElement.clientWidth, tableElement.scrollWidth));
    };
    const syncFromMain = () => {
      if (syncingScrollbar) return;
      syncingMain = true;
      scrollbarElement.scrollLeft = scrollElement.scrollLeft;
      syncingMain = false;
    };
    const syncFromScrollbar = () => {
      if (syncingMain) return;
      syncingScrollbar = true;
      scrollElement.scrollLeft = scrollbarElement.scrollLeft;
      syncingScrollbar = false;
    };

    syncWidth();
    syncFromMain();
    scrollElement.addEventListener("scroll", syncFromMain);
    scrollbarElement.addEventListener("scroll", syncFromScrollbar);
    window.addEventListener("resize", syncWidth);

    const observer = new ResizeObserver(syncWidth);
    observer.observe(scrollElement);
    observer.observe(tableElement);

    return () => {
      scrollElement.removeEventListener("scroll", syncFromMain);
      scrollbarElement.removeEventListener("scroll", syncFromScrollbar);
      window.removeEventListener("resize", syncWidth);
      observer.disconnect();
    };
  }, [table, density]);

  const selectedRowCount = Object.values(table.getState().rowSelection).filter(Boolean).length;

  return (
    <section className={cn("flex min-h-0 flex-col overflow-hidden rounded-lg border bg-card shadow-sm", className)}>
      {toolbar ? <div className="shrink-0 border-b bg-card">{toolbar}</div> : null}

      <div ref={scrollRef} className="chat-scrollbar min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
        <table
          ref={tableRef}
          className={cn("w-full min-w-[1180px] caption-bottom text-sm", density === "compact" && "text-xs")}
        >
          <TableHeader className="bg-secondary">
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id} className="hover:bg-transparent">
                {headerGroup.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    colSpan={header.colSpan}
                    className={cn(
                      "group/header sticky top-0 z-30 whitespace-nowrap border-r bg-secondary shadow-[0_1px_0_hsl(var(--border))] last:border-r-0",
                      density === "compact" && "h-9 px-2",
                      header.column.columnDef.meta?.align === "center" && "text-center",
                      header.column.columnDef.meta?.align === "right" && "text-right",
                      header.column.columnDef.meta?.headerClassName,
                    )}
                    style={{ width: header.getSize() }}
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id} data-state={row.getIsSelected() ? "selected" : undefined}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell
                      key={cell.id}
                      className={cn(
                        "border-r last:border-r-0",
                        density === "compact" ? "px-2 py-1.5" : "p-3",
                        cell.column.columnDef.meta?.align === "center" && "text-center",
                        cell.column.columnDef.meta?.align === "right" && "text-right",
                        cell.column.columnDef.meta?.cellClassName,
                      )}
                      style={{ width: cell.column.getSize() }}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={table.getAllLeafColumns().length}
                  className="h-40 text-center text-muted-foreground"
                >
                  {emptyState ?? "No rows match the current view."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </table>
      </div>

      <div className="shrink-0">
        <div ref={scrollbarRef} className="chat-scrollbar h-3 overflow-x-auto overflow-y-hidden border-t bg-card">
          <div className="h-px" style={{ width: tableWidth }} />
        </div>
        <DataTablePagination table={table} />
        {actionBar && selectedRowCount > 0 ? actionBar : null}
      </div>
    </section>
  );
}
