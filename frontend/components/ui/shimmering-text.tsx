"use client";

import type { CSSProperties, HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

interface ShimmeringTextProps extends HTMLAttributes<HTMLSpanElement> {
  active?: boolean;
  duration?: number;
  text: string;
}

export function ShimmeringText({
  active = true,
  className,
  duration = 1.6,
  style,
  text,
  ...props
}: ShimmeringTextProps) {
  return (
    <span
      className={cn(active && "shimmering-text", className)}
      style={
        {
          "--shimmer-duration": `${duration}s`,
          ...style,
        } as CSSProperties
      }
      {...props}
    >
      {text}
    </span>
  );
}
