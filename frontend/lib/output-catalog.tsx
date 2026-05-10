"use client";

import type { ReactElement } from "react";

import { AuditQuestionForm } from "@/components/output/audit-question-form";
import type { AuditFormResult, OutputComponent } from "@/lib/types";

export type OutputRenderer = (
  component: OutputComponent,
  controls: {
    onSubmitAuditForm: (reviewId: string, form: AuditFormResult) => Promise<void>;
    onClose: (componentId: string) => void;
  },
) => ReactElement;

export const outputCatalog: Record<string, OutputRenderer> = {
  audit_form: (component, controls) => {
    if (!isAuditFormComponent(component)) {
      return <UnknownOutputComponent component={component} />;
    }

    return (
      <AuditQuestionForm
        reviewId={component.reviewId}
        form={component.form}
        collapsed={component.collapsed}
        metadata={{
          claimNumber: component.claimNumber,
          finalizedAt: component.createdAt,
          updatedAt: component.updatedAt,
          source: component.source,
        }}
        onSubmit={(form) => controls.onSubmitAuditForm(component.reviewId, form)}
        onClose={() => controls.onClose(component.id)}
      />
    );
  },
};

function isAuditFormComponent(
  component: OutputComponent,
): component is Extract<OutputComponent, { type: "audit_form" }> {
  return component.type === "audit_form";
}

export function renderOutputComponent(
  component: OutputComponent,
  controls: Parameters<OutputRenderer>[1],
): ReactElement {
  const renderer = outputCatalog[component.type];
  if (!renderer) {
    return <UnknownOutputComponent component={component} />;
  }
  return renderer(component, controls);
}

function UnknownOutputComponent({ component }: { component: OutputComponent }) {
  return (
    <div className="rounded-lg border border-amber-500/35 bg-amber-500/10 p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold">Unknown output component</p>
        <span className="rounded border bg-background px-2 py-0.5 font-mono text-[11px]">
          {component.type}
        </span>
      </div>
      <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-background p-3 text-xs">
        {JSON.stringify(component, null, 2)}
      </pre>
    </div>
  );
}
