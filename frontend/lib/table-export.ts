import * as XLSX from "xlsx";

export interface ExportColumn<T> {
  header: string;
  value: (row: T) => string | number | boolean | null | undefined;
}

function normalizeCell(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function escapeCsvCell(value: string): string {
  const escaped = value.replace(/"/g, '""');
  return /[",\n\r]/.test(escaped) ? `"${escaped}"` : escaped;
}

function escapeTsvCell(value: string): string {
  return value.replace(/\t/g, " ").replace(/\r?\n/g, " ");
}

export function buildCsv<T>(rows: T[], columns: ExportColumn<T>[]): string {
  const header = columns.map((column) => escapeCsvCell(column.header)).join(",");
  const body = rows.map((row) =>
    columns
      .map((column) => escapeCsvCell(normalizeCell(column.value(row))))
      .join(","),
  );
  return [header, ...body].join("\n");
}

export function buildTsv<T>(rows: T[], columns: ExportColumn<T>[]): string {
  const header = columns.map((column) => escapeTsvCell(column.header)).join("\t");
  const body = rows.map((row) =>
    columns
      .map((column) => escapeTsvCell(normalizeCell(column.value(row))))
      .join("\t"),
  );
  return [header, ...body].join("\n");
}

export function buildExportObjects<T>(rows: T[], columns: ExportColumn<T>[]): Record<string, string>[] {
  return rows.map((row) =>
    Object.fromEntries(
      columns.map((column) => [column.header, normalizeCell(column.value(row))]),
    ),
  );
}

export function downloadText(content: string, fileName: string, mimeType: string): void {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8;` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function safeSheetName(name: string): string {
  return name.replace(/[\\/?*[\]:]/g, " ").slice(0, 31) || "Sheet";
}

export function downloadWorkbook<TView, TData>({
  fileName,
  viewSheetName = "view",
  dataSheetName = "data",
  viewRows,
  viewColumns,
  dataRows,
  dataColumns,
}: {
  fileName: string;
  viewSheetName?: string;
  dataSheetName?: string;
  viewRows: TView[];
  viewColumns: ExportColumn<TView>[];
  dataRows: TData[];
  dataColumns: ExportColumn<TData>[];
}): void {
  const workbook = XLSX.utils.book_new();
  const viewSheet = XLSX.utils.json_to_sheet(buildExportObjects(viewRows, viewColumns));
  const dataSheet = XLSX.utils.json_to_sheet(buildExportObjects(dataRows, dataColumns));
  XLSX.utils.book_append_sheet(workbook, viewSheet, safeSheetName(viewSheetName));
  XLSX.utils.book_append_sheet(workbook, dataSheet, safeSheetName(dataSheetName));
  XLSX.writeFile(workbook, fileName);
}
