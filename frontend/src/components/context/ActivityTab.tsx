"use client";

import React, { useState } from "react";
import { AlertTriangle, ArrowRight, Check } from "lucide-react";
import { ToolStep } from "@/types";
import { ToolTraceTab } from "./ToolTraceTab";
import { isFailedStep, toolDisplayName } from "@/lib/trace";

interface ActivityTabProps {
  trace?: ToolStep[];
  confidence?: "high" | "medium" | "low" | null;
}

/**
 * The friendly view of what the agent did. Raw arguments and planner reasoning
 * stay behind "View technical trace" so debugging detail is available without
 * being the default reading experience.
 */
export function ActivityTab({ trace = [], confidence }: ActivityTabProps) {
  const [showTechnical, setShowTechnical] = useState(false);

  if (trace.length === 0) {
    return (
      <div className="px-3.5 py-3">
        <div className="text-[12.5px] font-medium text-[var(--text-2)]">No activity yet</div>
        <p className="mt-1 text-[12px] text-[var(--text-3)] leading-relaxed">
          Tools and lookups ParcelPilot runs will appear here after an answer.
        </p>
      </div>
    );
  }

  const confidenceLabel = confidence
    ? `${confidence.charAt(0).toUpperCase()}${confidence.slice(1)} confidence`
    : null;

  return (
    <div className="px-3.5 py-3 overflow-y-auto max-h-full">
      <ol className="space-y-3">
        {trace.map((step, index) => {
          const failed = isFailedStep(step);
          return (
            <li key={index} className="flex items-start gap-2">
              {failed ? (
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-[2px] text-[var(--warning)]" />
              ) : (
                <Check className="w-3.5 h-3.5 shrink-0 mt-[2px] text-[var(--success)]" />
              )}
              <div className="min-w-0">
                <div className="text-[12.5px] text-[var(--text)] leading-tight">
                  {toolDisplayName(step.tool)}
                </div>
                <div className="mt-0.5 text-[11.5px] text-[var(--text-3)] leading-relaxed break-words">
                  {step.summary}
                </div>
              </div>
            </li>
          );
        })}

        {confidenceLabel && (
          <li className="flex items-start gap-2">
            <Check className="w-3.5 h-3.5 shrink-0 mt-[2px] text-[var(--success)]" />
            <div className="min-w-0">
              <div className="text-[12.5px] text-[var(--text)] leading-tight">Answer generated</div>
              <div className="mt-0.5 text-[11.5px] text-[var(--text-3)]">{confidenceLabel}</div>
            </div>
          </li>
        )}
      </ol>

      <div className="mt-4 pt-3 border-t border-[var(--border)]">
        <button
          onClick={() => setShowTechnical((v) => !v)}
          className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--text-2)] hover:text-[var(--text)] transition-colors cursor-pointer"
        >
          {showTechnical ? "Hide technical trace" : "View technical trace"}
          <ArrowRight
            className={`w-3 h-3 transition-transform ${showTechnical ? "rotate-90" : ""}`}
          />
        </button>

        {showTechnical && (
          <div className="mt-2.5">
            <ToolTraceTab trace={trace} />
          </div>
        )}
      </div>
    </div>
  );
}
