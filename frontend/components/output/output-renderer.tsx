"use client";

import { ChevronDown, ChevronRight, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { renderOutputComponent } from "@/lib/output-catalog";
import type { AuditFormResult, OutputComponent } from "@/lib/types";

export function OutputRenderer({
  component,
  onSubmitAuditForm,
  onClose,
  onCollapse,
  onExpand,
}: {
  component: OutputComponent;
  onSubmitAuditForm: (reviewId: string, form: AuditFormResult) => Promise<void>;
  onClose: (componentId: string) => void;
  onCollapse: (componentId: string) => void;
  onExpand: (componentId: string) => void;
}) {
  return (
    <div className="output-rise group relative">
      {component.type !== "audit_form" ? (
        <div className="absolute right-2 top-2 z-10 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className="h-7 w-7"
            onClick={() =>
              component.collapsed ? onExpand(component.id) : onCollapse(component.id)
            }
            title={component.collapsed ? "Expand" : "Collapse"}
            aria-label={component.collapsed ? "Expand" : "Collapse"}
          >
            {component.collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </Button>
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className="h-7 w-7"
            onClick={() => onClose(component.id)}
            title="Close"
            aria-label="Close"
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      ) : null}
      {renderOutputComponent(component, {
        onSubmitAuditForm,
        onClose,
      })}
    </div>
  );
}
