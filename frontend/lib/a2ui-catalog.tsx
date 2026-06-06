"use client";

import type { ComponentProps, ReactElement, ReactNode } from "react";

import { ArtifactBundleCard } from "@/components/a2ui/artifact-bundle-card";
import { AuditReviewCard } from "@/components/a2ui/audit-review-card";
import { CodeDisclosure } from "@/components/a2ui/code-disclosure";
import { DataTable } from "@/components/a2ui/data-table";
import { PlotlyChart } from "@/components/a2ui/plotly-chart";
import type { A2UIComponent } from "@/lib/types";

export type ComponentRenderer = (
  props: Record<string, unknown>,
  children?: ReactNode,
) => ReactElement;

const a2uiCatalog: Record<string, ComponentRenderer> = {
  "a2ui.ArtifactBundleCard": (props) => <ArtifactBundleCard {...(props as unknown as ComponentProps<typeof ArtifactBundleCard>)} />,
  "a2ui.AuditReviewCard": (props) => <AuditReviewCard {...(props as unknown as ComponentProps<typeof AuditReviewCard>)} />,
  "a2ui.CodeDisclosure": (props) => <CodeDisclosure {...(props as unknown as ComponentProps<typeof CodeDisclosure>)} />,
  "a2ui.DataTable": (props) => <DataTable {...(props as unknown as ComponentProps<typeof DataTable>)} />,
  "a2ui.PlotlyChart": (props) => <PlotlyChart {...(props as unknown as ComponentProps<typeof PlotlyChart>)} />,
};

export function getComponentRenderer(type: string): ComponentRenderer | undefined {
  return a2uiCatalog[type];
}

export function isChatComponent(component: A2UIComponent): boolean {
  return !component.zone || component.zone === "chat";
}
