"use client";

import React, { useState } from "react";
import { Check, ChevronDown, ChevronRight, Copy } from "lucide-react";
import { ToolStep } from "@/types";
import { Button } from "@/components/ui/Button";

interface ToolTraceTabProps {
  trace?: ToolStep[];
}

/**
 * Raw execution detail: tool names as the graph recorded them, planner
 * reasoning, and public tool arguments. Rendered inside the Activity tab behind
 * "View technical trace" -- never a top-level destination.
 */
export function ToolTraceTab({ trace = [] }: ToolTraceTabProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);

  if (trace.length === 0) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(trace, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[10.5px] font-semibold text-[var(--text-3)] uppercase tracking-[0.06em]">
          Execution graph · {trace.length} {trace.length === 1 ? "step" : "steps"}
        </span>
        <Button variant="ghost" size="sm" onClick={handleCopy}>
          {copied ? <Check className="w-3 h-3 text-[var(--success)]" /> : <Copy className="w-3 h-3" />}
          {copied ? "Copied" : "Copy JSON"}
        </Button>
      </div>

      {trace.map((step, index) => {
        const isExpanded = expandedIndex === index;
        return (
          <div
            key={index}
            className="border border-[var(--border)] rounded-md bg-[var(--surface)] overflow-hidden"
          >
            <button
              onClick={() => setExpandedIndex(isExpanded ? null : index)}
              className="w-full flex items-start justify-between gap-2 p-2.5 text-left hover:bg-[var(--surface-hover)] transition-colors cursor-pointer"
            >
              <div className="min-w-0">
                <span className="font-mono text-[11.5px] text-[var(--accent-text)]">{step.tool}</span>
                <p className="mt-0.5 text-[11px] text-[var(--text-3)] leading-snug break-words">
                  {step.summary}
                </p>
              </div>
              {isExpanded ? (
                <ChevronDown className="w-3.5 h-3.5 text-[var(--text-3)] shrink-0 mt-0.5" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5 text-[var(--text-3)] shrink-0 mt-0.5" />
              )}
            </button>

            {isExpanded && (
              <div className="px-2.5 pb-2.5 pt-2 border-t border-[var(--border)] space-y-2">
                {step.thought && (
                  <div>
                    <div className="text-[10px] font-semibold text-[var(--text-3)] uppercase tracking-[0.06em] mb-1">
                      Planner reasoning
                    </div>
                    <p className="text-[11.5px] text-[var(--text-2)] leading-relaxed">{step.thought}</p>
                  </div>
                )}

                {step.args && Object.keys(step.args).length > 0 && (
                  <div>
                    <div className="text-[10px] font-semibold text-[var(--text-3)] uppercase tracking-[0.06em] mb-1">
                      Tool arguments
                    </div>
                    <pre className="p-2 rounded border border-[var(--border)] bg-black/25 text-[11px] font-mono text-[var(--text-2)] overflow-x-auto">
                      {JSON.stringify(step.args, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
