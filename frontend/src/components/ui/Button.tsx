import React from "react";
import { cn } from "@/lib/utils";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "destructive" | "outline";
  size?: "sm" | "md" | "lg" | "icon";
}

export function Button({
  className,
  variant = "secondary",
  size = "md",
  disabled,
  children,
  ...props
}: ButtonProps) {
  const variantStyles = {
    primary:
      "bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--app-bg)] border-transparent",
    secondary:
      "bg-white/[0.03] hover:bg-white/[0.06] text-[var(--text)] border-[var(--border)] hover:border-[var(--border-hover)]",
    ghost:
      "bg-transparent hover:bg-white/[0.05] text-[var(--text-2)] hover:text-[var(--text)] border-transparent",
    destructive:
      "bg-[var(--critical-soft)] hover:bg-[var(--critical-soft)] text-[var(--critical-text)] border-[var(--critical-border)]",
    outline:
      "bg-transparent hover:bg-white/[0.05] text-[var(--text-2)] hover:text-[var(--text)] border-[var(--border)] hover:border-[var(--border-hover)]",
  };

  const sizeStyles = {
    sm: "h-6 px-2 text-[11px] rounded gap-1.5",
    md: "h-7 px-2.5 text-xs rounded-md gap-1.5",
    lg: "h-8 px-3.5 text-[13px] rounded-md gap-2",
    icon: "h-6 w-6 p-0 rounded items-center justify-center",
  };

  return (
    <button
      className={cn(
        "inline-flex items-center justify-center font-medium border transition-colors duration-100 select-none cursor-pointer disabled:opacity-45 disabled:cursor-not-allowed disabled:pointer-events-none",
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
}
