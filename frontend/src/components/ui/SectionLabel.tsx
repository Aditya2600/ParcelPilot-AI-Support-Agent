import React from "react";
import { cn } from "@/lib/utils";

/**
 * The uppercase group heading used by the sidebar and both inspector panels.
 * Small, letter-spaced and text-3 so a group reads as a divider rather than as
 * content competing with the rows beneath it.
 */
export function SectionLabel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "text-[10.5px] font-semibold text-[var(--text-3)] uppercase tracking-[0.06em] select-none",
        className
      )}
    >
      {children}
    </div>
  );
}
