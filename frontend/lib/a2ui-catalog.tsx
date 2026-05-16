"use client";

import type { ComponentProps, ReactElement, ReactNode } from "react";

import { CodeDisclosure } from "@/components/a2ui/code-disclosure";
import { DataTable } from "@/components/a2ui/data-table";
import type { A2UIComponent } from "@/lib/types";

export type ComponentRenderer = (
  props: Record<string, unknown>,
  children?: ReactNode,
) => ReactElement;

const a2uiCatalog: Record<string, ComponentRenderer> = {
  "a2ui.CodeDisclosure": (props) => <CodeDisclosure {...(props as unknown as ComponentProps<typeof CodeDisclosure>)} />,
  "a2ui.DataTable": (props) => <DataTable {...(props as unknown as ComponentProps<typeof DataTable>)} />,
};

export function getComponentRenderer(type: string): ComponentRenderer | undefined {
  return a2uiCatalog[type];
}

export function isChatComponent(component: A2UIComponent): boolean {
  return !component.zone || component.zone === "chat";
}
