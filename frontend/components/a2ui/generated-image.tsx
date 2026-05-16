"use client";

import { Check, Copy, Download, ExternalLink, Image as ImageIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { apiBaseUrl } from "@/lib/api";

export interface GeneratedImageProps {
  imageUrl: string;
  prompt: string;
  revisedPrompt?: string | null;
  filename?: string;
  model?: string;
  size?: string;
  quality?: string;
  mimeType?: string;
  createdAt?: string;
}

export function GeneratedImage({
  imageUrl,
  prompt,
  revisedPrompt,
  filename,
  model,
  size,
  quality,
}: GeneratedImageProps) {
  const [copied, setCopied] = useState(false);
  const src = useMemo(() => resolveImageUrl(imageUrl), [imageUrl]);
  const meta = [model, size, quality].filter(Boolean).join(" · ");
  const displayPrompt = revisedPrompt || prompt;

  const copyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(displayPrompt);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };

  return (
    <figure className="overflow-hidden rounded-md border bg-background text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-secondary/45 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <ImageIcon className="h-4 w-4 shrink-0 text-primary" />
          <div className="min-w-0">
            <figcaption className="truncate font-semibold">Generated image</figcaption>
            {meta ? <p className="truncate text-xs text-muted-foreground">{meta}</p> : null}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={() => void copyPrompt()}
            aria-label="Copy prompt"
            title="Copy prompt"
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          </Button>
          <Button
            asChild
            type="button"
            variant="outline"
            size="icon"
            className="h-7 w-7"
            aria-label="Download image"
            title="Download image"
          >
            <a href={src} download={filename}>
              <Download className="h-3.5 w-3.5" />
            </a>
          </Button>
          <Button
            asChild
            type="button"
            variant="outline"
            size="icon"
            className="h-7 w-7"
            aria-label="Open image"
            title="Open image"
          >
            <a href={src} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </Button>
        </div>
      </div>
      <div className="bg-card">
        <img
          src={src}
          alt={displayPrompt}
          className="max-h-[520px] min-h-48 w-full object-contain"
          loading="lazy"
        />
      </div>
      <div className="border-t px-3 py-2">
        <p className="line-clamp-3 text-xs leading-relaxed text-muted-foreground">
          {displayPrompt}
        </p>
      </div>
    </figure>
  );
}

function resolveImageUrl(imageUrl: string): string {
  if (/^(https?:|data:|blob:)/.test(imageUrl)) return imageUrl;
  return `${apiBaseUrl}${imageUrl.startsWith("/") ? imageUrl : `/${imageUrl}`}`;
}
