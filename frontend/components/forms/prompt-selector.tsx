"use client";

import { useEffect, useMemo, useState } from "react";
import { GitBranch, Loader2, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { listPromptFamilies } from "@/lib/api";
import type { PromptFamilyRecord, PromptReference, PromptVersionRecord } from "@/lib/types";
import { cn } from "@/lib/utils";

type PromptSelectorProps = {
  formId: string;
  formVersion: string;
  value?: PromptReference | null;
  onChange: (value: PromptReference | null) => void;
  label?: string;
  disabled?: boolean;
  className?: string;
  helperText?: string;
  includeFormDefault?: boolean;
};

type PromptOption =
  | {
      key: "form_default";
      label: string;
      description: string;
      ref: PromptReference | null;
      version?: never;
    }
  | {
      key: string;
      label: string;
      description: string;
      ref: PromptReference;
      version?: PromptVersionRecord;
    };

export function PromptSelector({
  formId,
  formVersion,
  value,
  onChange,
  label = "Prompt",
  disabled = false,
  className,
  helperText,
  includeFormDefault = true,
}: PromptSelectorProps) {
  const [families, setFamilies] = useState<PromptFamilyRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadFamilies = async () => {
    if (!formId || !formVersion) {
      setFamilies([]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      setFamilies(await listPromptFamilies(formId, formVersion));
    } catch (err) {
      setFamilies([]);
      setError(err instanceof Error ? err.message : "Failed to load prompt registry.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadFamilies();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formId, formVersion]);

  const options = useMemo<PromptOption[]>(() => {
    const registryOptions = families.flatMap((family) => {
      const aliasOptions: PromptOption[] = family.aliases.map((alias) => ({
        key: `alias:${family.id}:${alias.alias}`,
        label: `${alias.alias} alias`,
        description: alias.version_number ? `Mutable alias -> v${alias.version_number}` : "Mutable alias",
        ref: {
          ref_type: "alias",
          family_id: family.id,
          alias: alias.alias,
          form_id: family.form_id,
          task: "audit_review",
          prompt_kind: "instructions",
        },
      }));
      const versionOptions: PromptOption[] = family.versions.map((version) => ({
        key: `version:${version.id}`,
        label: `v${version.version_number}`,
        description: `${version.source_kind.replaceAll("_", " ")} · ${version.text_hash.slice(0, 8)}`,
        ref: {
          ref_type: "version",
          family_id: family.id,
          version_id: version.id,
          form_id: family.form_id,
          task: "audit_review",
          prompt_kind: "instructions",
        },
        version,
      }));
      return [...aliasOptions, ...versionOptions];
    });
    const formDefault: PromptOption = {
      key: "form_default",
      label: "Active registry",
      description: "Use the active prompt for this form version; fallback only if none exists",
      ref: null,
    };
    return includeFormDefault ? [formDefault, ...registryOptions] : registryOptions;
  }, [families, includeFormDefault]);

  const selectedKey = useMemo(() => {
    if (!value || value.ref_type === "form_default") return includeFormDefault ? "form_default" : "";
    if (value.ref_type === "alias") return `alias:${value.family_id ?? ""}:${value.alias ?? ""}`;
    if (value.ref_type === "version") return `version:${value.version_id ?? ""}`;
    return includeFormDefault ? "form_default" : "";
  }, [includeFormDefault, value]);

  const selectedOption = options.find((option) => option.key === selectedKey) ?? options[0];

  return (
    <div className={cn("grid gap-2", className)}>
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={`prompt-selector-${formId}-${formVersion}`} className="text-sm font-medium">
          {label}
        </label>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => void loadFamilies()}
          disabled={disabled || loading}
          title="Refresh prompt registry"
          aria-label="Refresh prompt registry"
        >
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
        </Button>
      </div>
      <div className="relative">
        <GitBranch className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <select
          id={`prompt-selector-${formId}-${formVersion}`}
          value={selectedOption?.key ?? ""}
          onChange={(event) => {
            const option = options.find((item) => item.key === event.target.value);
            onChange(option?.ref ?? null);
          }}
          disabled={disabled || loading || options.length === 0}
          className="h-10 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        >
          {options.length === 0 ? <option value="">No registry prompts</option> : null}
          {options.map((option) => (
            <option key={option.key} value={option.key}>
              {option.label} - {option.description}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <Badge variant="outline">{families.reduce((total, family) => total + family.versions.length, 0)} versions</Badge>
        <Badge variant="outline">{families.reduce((total, family) => total + family.aliases.length, 0)} aliases</Badge>
        <span>{helperText ?? selectedOption?.description}</span>
      </div>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
