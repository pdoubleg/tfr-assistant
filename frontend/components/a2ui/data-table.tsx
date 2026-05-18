"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, Check, Copy, Download, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TablePagination } from "@/components/dashboard/table-pagination";
import type { A2UICellValue } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface DataTableProps {
  headers: string[];
  rows: A2UICellValue[][];
  caption?: string;
  sortable?: boolean;
  copyable?: boolean;
  downloadable?: boolean;
}

type SortDirection = "asc" | "desc";

export function DataTable({
  headers,
  rows,
  caption,
  sortable = true,
  copyable = true,
  downloadable = true,
}: DataTableProps) {
  const [sortColumn, setSortColumn] = useState<number | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [search, setSearch] = useState("");
  const [columnFilterIndex, setColumnFilterIndex] = useState(0);
  const [columnFilterValue, setColumnFilterValue] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [copyStatus, setCopyStatus] = useState<"idle" | "success" | "error">("idle");
  const tableScrollerRef = useRef<HTMLDivElement | null>(null);
  const [tableViewportWidth, setTableViewportWidth] = useState(0);

  const safeColumnFilterIndex = headers.length ? Math.min(columnFilterIndex, headers.length - 1) : 0;

  useEffect(() => {
    if (columnFilterIndex !== safeColumnFilterIndex) {
      setColumnFilterIndex(safeColumnFilterIndex);
    }
  }, [columnFilterIndex, safeColumnFilterIndex]);

  const filteredRows = useMemo(() => {
    const globalQuery = search.trim().toLowerCase();
    const columnQuery = columnFilterValue.trim().toLowerCase();

    return rows.filter((row) => {
      if (globalQuery && !row.some((cell) => toSearchText(cell).includes(globalQuery))) {
        return false;
      }

      if (columnQuery && !toSearchText(row[safeColumnFilterIndex]).includes(columnQuery)) {
        return false;
      }

      return true;
    });
  }, [columnFilterValue, rows, safeColumnFilterIndex, search]);

  const sortedRows = useMemo(() => {
    if (!sortable || sortColumn === null) return filteredRows;
    return [...filteredRows].sort((first, second) => {
      const firstValue = first[sortColumn];
      const secondValue = second[sortColumn];
      if (typeof firstValue === "number" && typeof secondValue === "number") {
        return sortDirection === "asc" ? firstValue - secondValue : secondValue - firstValue;
      }
      const firstText = String(firstValue ?? "").toLowerCase();
      const secondText = String(secondValue ?? "").toLowerCase();
      return firstText.localeCompare(secondText, undefined, { numeric: true }) * (sortDirection === "asc" ? 1 : -1);
    });
  }, [filteredRows, sortColumn, sortDirection, sortable]);

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const paginatedRows = useMemo(
    () => sortedRows.slice((safePage - 1) * pageSize, safePage * pageSize),
    [pageSize, safePage, sortedRows],
  );

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  useEffect(() => {
    const element = tableScrollerRef.current;
    if (!element) return;

    const syncWidth = () => {
      const nextWidth = Math.floor(element.clientWidth);
      setTableViewportWidth((currentWidth) => (currentWidth === nextWidth ? currentWidth : nextWidth));
    };

    syncWidth();

    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", syncWidth);
      return () => window.removeEventListener("resize", syncWidth);
    }

    const observer = new ResizeObserver(syncWidth);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const preferredColumnWidths = useMemo(
    () => headers.map((header, index) => getPreferredColumnWidth(header, sortable, rows, index)),
    [headers, rows, sortable],
  );
  const preferredTableWidth = useMemo(
    () => preferredColumnWidths.reduce((total, width) => total + width, 0),
    [preferredColumnWidths],
  );
  const renderedTableWidth = Math.max(preferredTableWidth, tableViewportWidth);
  const renderedColumnWidths = useMemo(
    () => distributeColumnWidths(preferredColumnWidths, renderedTableWidth),
    [preferredColumnWidths, renderedTableWidth],
  );
  const rowSummary = sortedRows.length === rows.length
    ? `${rows.length} row${rows.length === 1 ? "" : "s"}`
    : `${sortedRows.length} of ${rows.length} rows`;

  const baseFileName = useMemo(() => {
    const sourceLabel = caption || headers[0] || "table";
    return sourceLabel.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "table";
  }, [caption, headers]);

  const tableAsTsv = useMemo(() => {
    const allRows = [headers, ...sortedRows];
    return allRows.map((row) => row.map(serializePlainCell).join("\t")).join("\n");
  }, [headers, sortedRows]);

  const tableAsCsv = useMemo(() => {
    const allRows = [headers, ...sortedRows];
    return allRows.map((row) => row.map(serializeCsvCell).join(",")).join("\n");
  }, [headers, sortedRows]);

  const handleSort = (columnIndex: number) => {
    if (!sortable) return;
    setPage(1);
    setSortDirection(sortColumn === columnIndex && sortDirection === "asc" ? "desc" : "asc");
    setSortColumn(columnIndex);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(tableAsTsv);
      setCopyStatus("success");
      window.setTimeout(() => setCopyStatus("idle"), 1400);
    } catch {
      setCopyStatus("error");
      window.setTimeout(() => setCopyStatus("idle"), 1600);
    }
  };

  const handleDownload = (content: string, extension: string, mimeType: string) => {
    const blob = new Blob([content], { type: `${mimeType};charset=utf-8;` });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${baseFileName}.${extension}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const resetTableFilters = () => {
    setSearch("");
    setColumnFilterValue("");
    setPage(1);
  };

  const hasActiveFilters = Boolean(search || columnFilterValue);

  return (
    <div className="overflow-hidden rounded-md border bg-background text-sm">
      <div className="border-b bg-secondary/45">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-secondary/45 px-3 py-2">
          <div className="min-w-0">
            {caption ? <h3 className="truncate text-sm font-semibold">{caption}</h3> : null}
            <p className="text-xs text-muted-foreground">{rowSummary}</p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {downloadable ? (
              <>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 gap-1.5 px-2"
                  onClick={() => handleDownload(tableAsCsv, "csv", "text/csv")}
                >
                  <Download className="h-3.5 w-3.5" />
                  CSV
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 gap-1.5 px-2"
                  onClick={() => handleDownload(tableAsTsv, "xls", "application/vnd.ms-excel")}
                >
                  <Download className="h-3.5 w-3.5" />
                  Excel
                </Button>
              </>
            ) : null}
            {copyable ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 gap-1.5 px-2"
                onClick={() => void handleCopy()}
              >
                {copyStatus === "success" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                {copyStatus === "success" ? "Copied" : "Copy"}
              </Button>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 px-3 py-2">
          <div className="relative min-w-[220px] flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="h-8 pl-8 text-xs"
              placeholder="Search table..."
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
            />
          </div>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="sr-only">Filter column</span>
            <select
              value={safeColumnFilterIndex}
              onChange={(event) => {
                setColumnFilterIndex(Number(event.target.value));
                setPage(1);
              }}
              disabled={!headers.length}
              className="h-8 max-w-[180px] rounded-md border border-input bg-background px-2 text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              {headers.length ? (
                headers.map((header, index) => (
                  <option key={`${header}-${index}`} value={index}>
                    {header}
                  </option>
                ))
              ) : (
                <option value={0}>No columns</option>
              )}
            </select>
          </label>
          <Input
            className="h-8 min-w-[180px] flex-1 text-xs sm:max-w-[240px]"
            placeholder={`Filter ${headers[safeColumnFilterIndex] ?? "column"}...`}
            value={columnFilterValue}
            onChange={(event) => {
              setColumnFilterValue(event.target.value);
              setPage(1);
            }}
            disabled={!headers.length}
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 gap-1.5 px-2 text-xs"
            onClick={resetTableFilters}
            disabled={!hasActiveFilters}
          >
            <X className="h-3.5 w-3.5" />
            Clear
          </Button>
        </div>
      </div>

      <div ref={tableScrollerRef} className="chat-scrollbar max-h-[460px] overflow-auto overscroll-x-contain">
        <table
          className="min-w-full table-fixed border-collapse"
          style={{
            width: renderedTableWidth || undefined,
            minWidth: renderedTableWidth || undefined,
          }}
        >
          <colgroup>
            {renderedColumnWidths.map((width, index) => (
              <col key={`${headers[index]}-${index}`} style={{ width }} />
            ))}
          </colgroup>
          <thead className="sticky top-0 z-10 border-b bg-card">
            <tr>
              {headers.map((header, index) => (
                <th
                  key={`${header}-${index}`}
                  title={header}
                  className={cn(
                    "px-3 py-2 text-left align-top text-xs font-semibold text-muted-foreground",
                    sortable && "cursor-pointer select-none hover:bg-secondary/60",
                  )}
                  style={{ width: renderedColumnWidths[index] }}
                  onClick={() => handleSort(index)}
                >
                  <span className="inline-flex max-w-full items-center gap-1.5">
                    <span className="truncate">{header}</span>
                    {sortable ? getSortIcon(sortColumn, sortDirection, index) : null}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedRows.length ? (
              paginatedRows.map((row, rowIndex) => (
                <tr key={rowIndex} className="border-b last:border-0 odd:bg-secondary/20 hover:bg-secondary/35">
                  {headers.map((_, cellIndex) => (
                    <td
                      key={cellIndex}
                      className="px-3 py-2 align-top text-xs text-foreground/90 [overflow-wrap:anywhere]"
                    >
                      {formatCell(row[cellIndex])}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-3 py-6 text-center text-xs text-muted-foreground" colSpan={Math.max(headers.length, 1)}>
                  {rows.length ? "No rows match the current filters." : "No rows"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <TablePagination
        totalRows={sortedRows.length}
        page={safePage}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={(nextPageSize) => {
          setPageSize(nextPageSize);
          setPage(1);
        }}
      />

      {copyStatus === "error" ? (
        <div className="border-t px-3 py-2 text-xs text-destructive">Copy failed.</div>
      ) : null}
    </div>
  );
}

function getSortIcon(
  sortColumn: number | null,
  sortDirection: SortDirection,
  columnIndex: number,
) {
  if (sortColumn !== columnIndex) return <ArrowUpDown className="h-3 w-3 opacity-45" />;
  return sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />;
}

function formatCell(value: A2UICellValue) {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return value;
}

function serializePlainCell(value: A2UICellValue): string {
  return String(formatCell(value)).replace(/\r?\n/g, " ").replace(/\t/g, " ").trim();
}

function serializeCsvCell(value: A2UICellValue): string {
  const normalized = serializePlainCell(value);
  const escaped = normalized.replace(/"/g, '""');
  return /[",]/.test(escaped) ? `"${escaped}"` : escaped;
}

function toSearchText(value: A2UICellValue): string {
  return String(formatCell(value)).toLowerCase();
}

function distributeColumnWidths(columnWidths: number[], targetWidth: number): number[] {
  const currentWidth = columnWidths.reduce((total, width) => total + width, 0);
  if (!columnWidths.length || targetWidth <= currentWidth) return columnWidths;

  const extraWidth = targetWidth - currentWidth;
  let distributedWidth = 0;

  return columnWidths.map((width, index) => {
    if (index === columnWidths.length - 1) {
      return width + extraWidth - distributedWidth;
    }

    const extraForColumn = Math.floor(extraWidth * (width / currentWidth));
    distributedWidth += extraForColumn;
    return width + extraForColumn;
  });
}

function getPreferredColumnWidth(
  header: string,
  sortable: boolean,
  rows: A2UICellValue[][],
  columnIndex: number,
): number {
  const headerLength = Math.max(3, header.replace(/[_-]+/g, " ").length);
  const sampledCellLength = rows
    .slice(0, 25)
    .reduce((maxLength, row) => Math.max(maxLength, getCellSizingLength(row[columnIndex])), 0);
  const normalizedLength = Math.max(headerLength, sampledCellLength);
  const iconSpace = sortable ? 34 : 16;
  return Math.min(360, Math.max(92, normalizedLength * 8 + iconSpace));
}

function getCellSizingLength(value: A2UICellValue): number {
  const text = serializePlainCell(value);
  if (!text) return 0;

  const longestSegment = text.split(/\s+/).reduce((maxLength, segment) => Math.max(maxLength, segment.length), 0);
  if (text.length <= 28) return text.length;
  return Math.min(34, Math.max(longestSegment, 22));
}
