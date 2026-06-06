"use client";

import {
  AlertTriangle,
  Code2,
  Download,
  ExternalLink,
  FileJson,
  FileSpreadsheet,
  FileText,
  Presentation,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { chatArtifactFileUrl } from "@/lib/api";

interface ArtifactBundleFile {
  role: string;
  path: string;
  media_type?: string;
  mediaType?: string;
  filename: string;
  label?: string;
  inline?: boolean;
}

export interface ArtifactBundleCardProps {
  sessionId: string;
  handle: string;
  kind: "report_bundle" | "deck_bundle" | string;
  title: string;
  subtitle?: string;
  summary?: string;
  files?: ArtifactBundleFile[];
  warnings?: string[];
  createdAt?: string;
}

const fileRoleOrder = ["html", "pptx", "data", "manifest", "spec"];

export function ArtifactBundleCard({
  sessionId,
  handle,
  kind,
  title,
  subtitle,
  summary,
  files = [],
  warnings = [],
  createdAt,
}: ArtifactBundleCardProps) {
  const sortedFiles = [...files].sort((first, second) => {
    const firstIndex = fileRoleOrder.indexOf(first.role);
    const secondIndex = fileRoleOrder.indexOf(second.role);
    return (firstIndex === -1 ? 99 : firstIndex) - (secondIndex === -1 ? 99 : secondIndex);
  });
  const bundleLabel = kind === "deck_bundle" ? "Deck bundle" : "Report bundle";

  return (
    <article className="overflow-hidden rounded-md border bg-background text-sm shadow-sm">
      <div className="flex items-start gap-3 border-b bg-secondary/45 px-3 py-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
          {kind === "deck_bundle" ? <Presentation className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-semibold">{title || bundleLabel}</h3>
            <span className="rounded border bg-background px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {handle}
            </span>
          </div>
          {subtitle ? <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p> : null}
          {summary ? <p className="mt-1 text-xs text-muted-foreground">{summary}</p> : null}
          {createdAt ? (
            <p className="mt-1 font-mono text-[10px] text-muted-foreground">{formatDate(createdAt)}</p>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 px-3 py-3">
        {sortedFiles.map((file) => {
          const url = chatArtifactFileUrl(sessionId, handle, file.role);
          const inline = Boolean(file.inline);
          return (
            <Button
              key={`${file.role}-${file.filename}`}
              asChild
              variant={inline ? "default" : "outline"}
              size="sm"
              className="gap-1.5"
            >
              <a
                href={url}
                target={inline ? "_blank" : undefined}
                rel={inline ? "noopener noreferrer" : undefined}
                download={inline ? undefined : file.filename}
              >
                {fileIcon(file.role)}
                {file.label || fileLabel(file.role)}
                {inline ? <ExternalLink className="h-3.5 w-3.5" /> : <Download className="h-3.5 w-3.5" />}
              </a>
            </Button>
          );
        })}
      </div>

      {warnings.length ? (
        <div className="border-t bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
          {warnings.map((warning, index) => (
            <div key={`${warning}-${index}`} className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{warning}</span>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function fileIcon(role: string) {
  if (role === "pptx") return <Presentation className="h-3.5 w-3.5" />;
  if (role === "data") return <FileSpreadsheet className="h-3.5 w-3.5" />;
  if (role === "manifest") return <FileJson className="h-3.5 w-3.5" />;
  if (role === "spec") return <Code2 className="h-3.5 w-3.5" />;
  return <FileText className="h-3.5 w-3.5" />;
}

function fileLabel(role: string) {
  if (role === "html") return "HTML";
  if (role === "pptx") return "PPTX";
  if (role === "data") return "Workbook";
  if (role === "manifest") return "Manifest";
  if (role === "spec") return "Spec";
  return role;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
