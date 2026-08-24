"use client";

import React, { useState } from "react";
import {
  ArrowUpRight,
  ChevronDown,
  AlertTriangle,
  CheckCircle2,
  FileSearch,
  FileText,
  Package,
  Ticket,
  Building2,
  Timer,
  Coins,
  ShieldAlert,
} from "lucide-react";
import { ToolStep } from "@/types";
import { isFailedStep, toolDisplayName } from "@/lib/trace";
import { cn } from "@/lib/utils";

interface ResolutionStepsProps {
  steps?: ToolStep[];
  onOpenActivity?: () => void;
}

/** Icon per tool, matching the names `toolDisplayName` already normalises. */
const STEP_ICONS: Record<string, React.ElementType> = {
  document_search: FileSearch,
  order_lookup: Package,
  structured_order_lookup: Package,
  ticket_lookup: Ticket,
  structured_ticket_lookup: Ticket,
  account_lookup: Building2,
  sla_lookup: Timer,
  calculate_credit: Coins,
  credit_calculator: Coins,
  list_open_tickets: Ticket,
  prepare_escalation: ShieldAlert,
  final_answer: FileText,
};

/**
 * The execution trace inline in the feed: conversation first, then what ran, with
 * raw arguments and planner reasoning still one level deeper in the Activity
 * panel. Expanded by default -- how an answer was reached is part of reading it,
 * not an optional detour.
 */
export function ResolutionSteps({ steps, onOpenActivity }: ResolutionStepsProps) {
  const [isOpen, setIsOpen] = useState(true);

  if (!steps || steps.length === 0) return null;

  return (
    <div className="mt-3.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
      <button
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
        className={cn(
          "w-full flex items-center justify-between gap-2 px-3 h-[38px] text-left transition-colors cursor-pointer hover:bg-[var(--surface-hover)]",
          isOpen && "border-b border-[var(--border)]"
        )}
      >
        <span className="text-[12.5px] text-[var(--text)]">
          How this answer was resolved{" "}
          <span className="text-[var(--text-3)]">
            ({steps.length} {steps.length === 1 ? "step" : "steps"})
          </span>
        </span>
        <ChevronDown
          className={cn(
            "w-3.5 h-3.5 text-[var(--text-3)] shrink-0 transition-transform",
            isOpen && "rotate-180"
          )}
        />
      </button>

      {isOpen && (
        <>
          <ol>
            {steps.map((step, index) => {
              const failed = isFailedStep(step);
              const Icon = STEP_ICONS[step.tool] || FileText;
              return (
                <li
                  key={index}
                  className="flex items-center gap-2.5 px-3 py-2.5 border-b border-[var(--border)] last:border-b-0"
                >
                  <Icon className="w-4 h-4 text-[var(--text-3)] shrink-0" />

                  <div className="min-w-0 flex-1">
                    <div className="text-[12.5px] text-[var(--text)] leading-tight">
                      {toolDisplayName(step.tool)}
                    </div>
                    <div className="mt-0.5 text-[11.5px] text-[var(--text-3)] leading-snug break-words">
                      {step.summary}
                    </div>
                  </div>

                  {failed ? (
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-[var(--warning)]" />
                  ) : (
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-[var(--success)]" />
                  )}
                </li>
              );
            })}
          </ol>

          {onOpenActivity && (
            <button
              onClick={onOpenActivity}
              className="group w-full flex items-center gap-1.5 px-3 h-[32px] border-t border-[var(--border)] text-[11.5px] text-[var(--text-3)] hover:text-[var(--text-2)] hover:bg-[var(--surface-hover)] transition-colors cursor-pointer"
            >
              View technical trace
              <ArrowUpRight className="w-3 h-3 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
            </button>
          )}
        </>
      )}
    </div>
  );
}
