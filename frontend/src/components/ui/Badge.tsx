import React from "react";
import { cn } from "@/lib/utils";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?:
    | "default"
    | "governing"
    | "active"
    | "sop"
    | "deprecated"
    | "context"
    | "p1"
    | "p2"
    | "p3"
    | "enterprise"
    | "growth"
    | "standard"
    | "accent"
    | "outline";
  size?: "sm" | "md";
}

/**
 * Restrained status marker: ~20-22px tall, 4px radius, soft fill + hairline
 * border, never a glow. Only three chroma families are in play (accent /
 * success / warning / critical), so several badges can sit side by side
 * without the panel reading as a developer dashboard.
 */
export function Badge({
  className,
  variant = "default",
  size = "sm",
  children,
  ...props
}: BadgeProps) {
  const variantStyles = {
    default: "bg-white/[0.04] text-[var(--text-2)] border-[var(--border)]",
    governing:
      "bg-[var(--success-soft)] text-[var(--success-text)] border-[var(--success-border)]",
    active:
      "bg-[var(--success-soft)] text-[var(--success-text)] border-[var(--success-border)]",
    sop: "bg-white/[0.04] text-[var(--text-2)] border-[var(--border)]",
    deprecated:
      "bg-[var(--critical-soft)] text-[var(--critical-text)] border-[var(--critical-border)]",
    context: "bg-white/[0.04] text-[var(--text-2)] border-[var(--border)]",
    p1: "bg-[var(--critical-soft)] text-[var(--critical-text)] border-[var(--critical-border)]",
    p2: "bg-[var(--warning-soft)] text-[var(--warning-text)] border-[var(--warning-border)]",
    p3: "bg-white/[0.04] text-[var(--text-2)] border-[var(--border)]",
    enterprise:
      "bg-[var(--accent-soft)] text-[var(--accent-text)] border-[var(--accent-border)]",
    growth: "bg-white/[0.04] text-[var(--text-2)] border-[var(--border)]",
    standard: "bg-white/[0.04] text-[var(--text-2)] border-[var(--border)]",
    accent:
      "bg-[var(--accent-soft)] text-[var(--accent-text)] border-[var(--accent-border)]",
    outline: "bg-transparent text-[var(--text-2)] border-[var(--border)]",
  };

  const sizeStyles = {
    sm: "h-[18px] text-[10px] px-1.5 tracking-[0.04em]",
    md: "h-[21px] text-[11px] px-2 tracking-[0.03em]",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded font-medium border uppercase select-none whitespace-nowrap leading-none",
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
}
