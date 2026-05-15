"use client";

import type { ReactElement } from "react";

import { Badge } from "@/components/ui/badge";
import { getComponentRenderer } from "@/lib/a2ui-catalog";
import type { A2UIComponent } from "@/lib/types";
import { cn } from "@/lib/utils";

export function A2UIRenderer({
  component,
  className,
  showErrors = true,
}: {
  component: A2UIComponent;
  className?: string;
  showErrors?: boolean;
}): ReactElement | null {
  const renderer = component?.type ? getComponentRenderer(component.type) : undefined;

  if (!renderer) {
    if (!showErrors) return null;
    return (
      <div className="rounded-md border border-amber-500/35 bg-amber-500/10 p-3 text-xs">
        <div className="flex items-center gap-2 font-medium">
          Unknown component
          <Badge variant="outline">{component?.type || "missing"}</Badge>
        </div>
      </div>
    );
  }

  const children = component.children?.map((child) => (
    <A2UIRenderer key={child.id} component={child} showErrors={showErrors} />
  ));
  const rendered = renderer(component.props ?? {}, children);
  const wrapperClassName = cn(className, component.layout?.className, component.styling?.className);

  if (!wrapperClassName && !component.layout?.width && !component.layout?.height) {
    return rendered;
  }

  return (
    <div
      className={wrapperClassName}
      style={{
        width: component.layout?.width === "full" ? "100%" : component.layout?.width,
        height: component.layout?.height,
      }}
    >
      {rendered}
    </div>
  );
}

export function A2UIRendererList({
  components,
  className,
  showErrors = true,
}: {
  components: A2UIComponent[];
  className?: string;
  showErrors?: boolean;
}) {
  if (!components.length) return null;

  return (
    <div className={cn("space-y-3", className)}>
      {components.map((component) => (
        <A2UIRenderer key={component.id} component={component} showErrors={showErrors} />
      ))}
    </div>
  );
}
