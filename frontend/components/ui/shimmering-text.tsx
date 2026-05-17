"use client";

import { motion, useReducedMotion } from "motion/react";
import type { CSSProperties } from "react";
import type { HTMLMotionProps, Transition } from "motion/react";

import { cn } from "@/lib/utils";

interface ShimmeringTextProps
  extends Omit<HTMLMotionProps<"span">, "animate" | "children" | "transition"> {
  active?: boolean;
  breakDuration?: number;
  color?: string;
  delay?: number;
  duration?: number;
  repeat?: boolean;
  shimmerColor?: string;
  shimmeringColor?: string;
  spread?: number;
  text: string;
}

export function ShimmeringText({
  active = true,
  breakDuration = 0.5,
  className,
  color = "var(--shimmer-text, hsl(var(--muted-foreground)))",
  delay = 0,
  duration = 2,
  repeat = true,
  shimmerColor,
  shimmeringColor,
  spread = 2,
  style,
  text,
  ...props
}: ShimmeringTextProps) {
  const prefersReducedMotion = useReducedMotion();
  const shouldAnimate = active && !prefersReducedMotion && text.length > 0;
  const shouldUseReducedMotionFallback = active && !shouldAnimate;
  const highlightColor =
    shimmerColor ?? shimmeringColor ?? "var(--shimmer-text-highlight, hsl(var(--foreground)))";
  const cycleDuration = Math.max(duration, 0.2);
  const shimmerSpread = Math.max(text.length * spread, 16);

  const transition: Transition = {
    delay,
    duration: cycleDuration,
    ease: "linear",
    repeat: repeat ? Infinity : 0,
    repeatDelay: repeat ? Math.max(breakDuration, 0) : 0,
    repeatType: "loop",
  };

  return (
    <motion.span
      aria-label={text}
      className={cn("inline-block whitespace-nowrap", className)}
      animate={shouldAnimate ? { backgroundPosition: ["100% 50%", "0% 50%"] } : undefined}
      style={{
        display: "inline-block",
        ...style,
        ...(shouldAnimate
          ? ({
              backgroundClip: "text",
              backgroundImage: `linear-gradient(90deg, ${color} calc(50% - ${shimmerSpread}px), ${highlightColor} 50%, ${color} calc(50% + ${shimmerSpread}px))`,
              backgroundPosition: "100% 50%",
              backgroundSize: "250% 100%",
              color: "transparent",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            } satisfies CSSProperties)
          : shouldUseReducedMotionFallback
            ? ({ color } satisfies CSSProperties)
            : null),
      }}
      transition={shouldAnimate ? transition : undefined}
      {...props}
    >
      {text}
    </motion.span>
  );
}
