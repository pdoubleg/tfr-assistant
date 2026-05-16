"use client";

import {
  Check,
  ChevronDown,
  ChevronRight,
  Code2,
  Copy,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

export interface CodeDisclosureProps {
  code: string;
  language: string;
  title?: string;
  caption?: string;
  defaultOpen?: boolean;
  copyable?: boolean;
  density?: "default" | "compact";
  tone?: "default" | "error";
  className?: string;
}

export function CodeDisclosure({
  code,
  language,
  title,
  caption,
  defaultOpen = false,
  copyable = true,
  density = "default",
  tone = "default",
  className,
}: CodeDisclosureProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [copied, setCopied] = useState(false);
  const [isDarkTheme, setIsDarkTheme] = useState(false);
  const compact = density === "compact";
  const normalizedLanguage = language.toLowerCase();
  const rendersMarkdown = normalizedLanguage === "markdown" || normalizedLanguage === "md";

  useEffect(() => {
    const syncTheme = () => setIsDarkTheme(document.documentElement.classList.contains("dark"));
    syncTheme();
    const observer = new MutationObserver(syncTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div
      className={cn(
        "overflow-hidden rounded-md border bg-background",
        tone === "error" && "border-destructive/35",
        compact ? "text-xs" : "text-sm",
        className,
      )}
    >
      <div
        className={cn(
          "flex items-center gap-2 bg-secondary/45",
          tone === "error" && "bg-destructive/10",
          open && "border-b",
          open && tone === "error" && "border-destructive/30",
          compact ? "min-h-8 px-2 py-1.5" : "min-h-11 px-3 py-2",
        )}
      >
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
          onClick={() => setOpen((current) => !current)}
        >
          {open ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <Code2
            className={cn(
              "shrink-0",
              tone === "error" ? "text-destructive" : "text-primary",
              compact ? "h-3.5 w-3.5" : "h-4 w-4",
            )}
          />
          <span
            className={cn(
              "min-w-0 shrink-0 truncate font-medium",
              tone === "error" && "text-destructive",
            )}
          >
            {title || `${language.toUpperCase()} code`}
          </span>
          {compact && caption ? (
            <span className="min-w-0 flex-1 truncate text-muted-foreground">{caption}</span>
          ) : null}
          <span className="rounded border bg-background px-1.5 py-0.5 font-mono text-[10px] uppercase text-muted-foreground">
            {language}
          </span>
        </button>
        {copyable ? (
          <button
            type="button"
            className={cn(
              "inline-flex shrink-0 items-center justify-center rounded-md border bg-background text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground",
              compact ? "h-6 w-6" : "h-7 w-7",
            )}
            onClick={() => void copyCode()}
            aria-label="Copy code"
            title="Copy code"
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
        ) : null}
      </div>
      {caption && !compact ? (
        <div className="border-b px-3 py-1.5 text-xs text-muted-foreground">
          {caption}
        </div>
      ) : null}
      {open ? (
        <div className={cn("chat-scrollbar overflow-auto", compact ? "max-h-[260px]" : "max-h-[360px]")}>
          {rendersMarkdown ? (
            <div className={cn("chat-markdown", compact ? "px-3 py-2" : "px-4 py-3")}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={buildDisclosureMarkdownComponents(isDarkTheme, compact)}
              >
                {code}
              </ReactMarkdown>
            </div>
          ) : (
            <SyntaxHighlighter
              language={language}
              style={isDarkTheme ? oneDark : oneLight}
              PreTag="pre"
              customStyle={{
                margin: 0,
                background: "transparent",
                padding: compact ? "0.65rem 0.75rem" : "0.85rem 1rem",
              }}
              codeTagProps={{
                style: {
                  fontFamily:
                    "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                  fontSize: compact ? "0.76rem" : "0.82rem",
                },
              }}
            >
              {code}
            </SyntaxHighlighter>
          )}
        </div>
      ) : null}
    </div>
  );
}

function buildDisclosureMarkdownComponents(isDarkTheme: boolean, compact: boolean): Components {
  return {
    table({ children }) {
      return (
        <div className="chat-markdown-table-wrap">
          <table>{children}</table>
        </div>
      );
    },
    code({ className, children }) {
      const codeString = toCodeString(children);
      const languageMatch = /language-(\w+)/.exec(className ?? "");
      const nestedLanguage = languageMatch?.[1]?.toLowerCase();
      const isInlineCode = !nestedLanguage && !codeString.includes("\n");

      if (isInlineCode) {
        return <code className={className}>{children}</code>;
      }

      return (
        <SyntaxHighlighter
          language={nestedLanguage ?? "text"}
          style={isDarkTheme ? oneDark : oneLight}
          PreTag="pre"
          customStyle={{
            margin: "0.45rem 0",
            background: "transparent",
            padding: 0,
          }}
          codeTagProps={{
            style: {
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
              fontSize: compact ? "0.76rem" : "0.82rem",
            },
          }}
        >
          {codeString}
        </SyntaxHighlighter>
      );
    },
  };
}

function toCodeString(children: ReactNode): string {
  if (Array.isArray(children)) {
    return children.map((child) => (typeof child === "string" ? child : "")).join("");
  }
  return typeof children === "string" ? children : "";
}
