"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, Check, Copy, Download } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
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

export function DataTable({
  headers,
  rows,
  caption,
  sortable = true,
  copyable = true,
  downloadable = true,
}: DataTableProps) {
  const [sortColumn, setSortColumn] = useState<number | null>(null);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
  const [copyStatus, setCopyStatus] = useState<"idle" | "success" | "error">("idle");

  const displayRows = useMemo(() => {
    if (!sortable || sortColumn === null) return rows;
    return [...rows].sort((first, second) => {
      const firstValue = first[sortColumn];
      const secondValue = second[sortColumn];
      if (typeof firstValue === "number" && typeof secondValue === "number") {
        return sortDirection === "asc" ? firstValue - secondValue : secondValue - firstValue;
      }
      const firstText = String(firstValue ?? "").toLowerCase();
      const secondText = String(secondValue ?? "").toLowerCase();
      return firstText.localeCompare(secondText, undefined, { numeric: true }) * (sortDirection === "asc" ? 1 : -1);
    });
  }, [rows, sortColumn, sortDirection, sortable]);

  const baseFileName = useMemo(() => {
    const sourceLabel = caption || headers[0] || "table";
    return sourceLabel.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "table";
  }, [caption, headers]);

  const tableAsTsv = useMemo(() => {
    const allRows = [headers, ...displayRows];
    return allRows.map((row) => row.map(serializePlainCell).join("\t")).join("\n");
  }, [displayRows, headers]);

  const tableAsCsv = useMemo(() => {
    const allRows = [headers, ...displayRows];
    return allRows.map((row) => row.map(serializeCsvCell).join(",")).join("\n");
  }, [displayRows, headers]);

  const handleSort = (columnIndex: number) => {
    if (!sortable) return;
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

  return (
    <div className="overflow-hidden rounded-md border bg-background text-sm">
      {(caption || copyable || downloadable) ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-secondary/45 px-3 py-2">
          <div className="min-w-0">
            {caption ? <h3 className="truncate text-sm font-semibold">{caption}</h3> : null}
            <p className="text-xs text-muted-foreground">{displayRows.length} rows</p>
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
      ) : null}

      <div className="chat-scrollbar max-h-[460px] overflow-auto">
        <table className="w-full min-w-[680px] border-collapse">
          <thead className="sticky top-0 z-10 border-b bg-card">
            <tr>
              {headers.map((header, index) => (
                <th
                  key={`${header}-${index}`}
                  className={cn(
                    "px-3 py-2 text-left text-xs font-semibold text-muted-foreground",
                    sortable && "cursor-pointer select-none hover:bg-secondary/60",
                  )}
                  onClick={() => handleSort(index)}
                >
                  <span className="inline-flex items-center gap-1.5">
                    {header}
                    {sortable ? getSortIcon(sortColumn, sortDirection, index) : null}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows.length ? (
              displayRows.map((row, rowIndex) => (
                <tr key={rowIndex} className="border-b last:border-0 odd:bg-secondary/20 hover:bg-secondary/35">
                  {headers.map((_, cellIndex) => (
                    <td key={cellIndex} className="px-3 py-2 text-xs text-foreground/90">
                      {formatCell(row[cellIndex])}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-3 py-6 text-center text-xs text-muted-foreground" colSpan={Math.max(headers.length, 1)}>
                  No rows
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {copyStatus === "error" ? (
        <div className="border-t px-3 py-2 text-xs text-destructive">Copy failed.</div>
      ) : null}
    </div>
  );
}

function getSortIcon(
  sortColumn: number | null,
  sortDirection: "asc" | "desc",
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
