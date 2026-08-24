"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertCircle, ShieldCheck } from "lucide-react";
import { ChatMessage, SourceItem } from "@/types";
import { ResolutionSteps } from "./ResolutionSteps";
import { EscalationCard } from "./EscalationCard";
import { cleanSourceTitle, cn, formatTimestamp } from "@/lib/utils";

/** The agent's own mark, used as its avatar in the feed. */
function AgentAvatar() {
  return (
    <span className="w-[26px] h-[26px] rounded-full bg-[var(--surface-active)] border border-[var(--border)] flex items-center justify-center shrink-0 text-[var(--text)]">
      <svg
        width="13"
        height="13"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
        <path d="m9 12 2 2 4-4" />
      </svg>
    </span>
  );
}

interface AssistantMessageProps {
  message: ChatMessage;
  onSelectSource?: (source: SourceItem) => void;
  onOpenActivity?: () => void;
  onConfirmEscalation?: (token: string) => Promise<void>;
  isProcessingAction?: boolean;
  selectedSourceId?: string;
}

export function AssistantMessage({
  message,
  onSelectSource,
  onOpenActivity,
  onConfirmEscalation,
  isProcessingAction,
  selectedSourceId,
}: AssistantMessageProps) {
  const {
    content,
    confidence,
    tool_trace,
    sources,
    pending_action,
    confirmed_record,
  } = message;

  // A backend/transport failure is not an answer -- it never gets confidence,
  // citations or prose styling.
  if (message.error) {
    return (
      <div className="mt-8 first:mt-0">
        <div className="flex items-center gap-2 mb-2">
          <AgentAvatar />
          <span className="text-[12.5px] font-semibold text-[var(--text)]">
            ParcelPilot
          </span>
          {message.timestamp && (
            <span className="text-[11px] text-[var(--text-3)]">
              {formatTimestamp(message.timestamp)}
            </span>
          )}
        </div>
        <div className="rounded-md border border-[var(--critical-border)] bg-[var(--critical-soft)] px-3 py-2.5 flex items-start gap-2">
          <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-[2px] text-[var(--critical)]" />
          <p className="text-[13px] text-[var(--text-2)] leading-relaxed">
            {content}
          </p>
        </div>
      </div>
    );
  }

  // Confidence reads as a quiet marker, not a status light: the same neutral
  // chip in every state, with only the icon tint distinguishing low from high.
  const confidenceChip = confidence ? (
    <span className="inline-flex items-center gap-1.5 h-[24px] px-2 rounded-md border border-[var(--border)] bg-[var(--surface)] text-[11.5px] text-[var(--text-2)] shrink-0 whitespace-nowrap">
      <ShieldCheck
        className={cn(
          "w-3.5 h-3.5",
          confidence === "high"
            ? "text-[var(--success)]"
            : confidence === "medium"
              ? "text-[var(--warning)]"
              : "text-[var(--text-3)]",
        )}
      />
      {confidence.charAt(0).toUpperCase() + confidence.slice(1)} confidence
    </span>
  ) : null;

  const cleanAnswer = content
    .replace(/\n\nNothing has been created yet[\s\S]*$/, "")
    .trim();

  return (
    <div className="mt-8 first:mt-0">
      {/* Speaker, time, and how much to trust what follows */}
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <AgentAvatar />
          <span className="text-[12.5px] font-semibold text-[var(--text)]">
            ParcelPilot
          </span>
          {message.timestamp && (
            <span className="text-[11px] text-[var(--text-3)]">
              {formatTimestamp(message.timestamp)}
            </span>
          )}
        </div>
        {confidenceChip}
      </div>

      {/* Everything below the byline hangs off the avatar gutter, so the
          operator's bubble and the agent's answer share one text edge. */}
      <div className="pl-[34px]">
        {/* Answer */}
        <div className="prose-dark select-text">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code: ({ children }) => (
                <code className="font-mono">{children}</code>
              ),
            }}
          >
            {cleanAnswer}
          </ReactMarkdown>
        </div>

        {/* Citations -- chips directly under the answer, each opening the inspector */}
        {sources && sources.length > 0 && (
          <div className="mt-3.5">
            <div className="flex flex-wrap items-center gap-1.5">
              {sources.map((src, index) => {
                const isSelected =
                  !!selectedSourceId && selectedSourceId === src.id;
                return (
                  <button
                    key={src.id || index}
                    onClick={() => onSelectSource?.(src)}
                    title={`Open ${cleanSourceTitle(src.title)} in the Evidence panel`}
                    className={cn(
                      "inline-flex items-center gap-1.5 max-w-full h-[28px] px-2 rounded-md border text-[11.5px] transition-colors cursor-pointer",
                      isSelected
                        ? "bg-[var(--accent-soft)] border-[var(--accent-border)] text-[var(--accent-text)]"
                        : "bg-[var(--surface)] border-[var(--border)] text-[var(--text-2)] hover:text-[var(--text)] hover:border-[var(--border-hover)]",
                    )}
                  >
                    <span
                      className={cn(
                        "font-mono text-[10.5px] shrink-0",
                        isSelected
                          ? "text-[var(--accent-text)]"
                          : "text-[var(--text-3)]",
                      )}
                    >
                      [{index + 1}]
                    </span>
                    <span className="truncate">
                      {cleanSourceTitle(src.title)}
                    </span>
                    {src.section && (
                      <span className="text-[var(--text-3)] shrink-0">
                        · {src.section}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            <p className="mt-2 text-[11px] text-[var(--text-3)]">
              Sources are authoritative. Click to view.
            </p>
          </div>
        )}

        {/* What was executed -- one line, details live in the Activity panel */}
        {tool_trace && tool_trace.length > 0 && (
          <ResolutionSteps steps={tool_trace} onOpenActivity={onOpenActivity} />
        )}

        {/* Prepared vs. confirmed state-changing action */}
        {(pending_action || confirmed_record) && (
          <EscalationCard
            pendingAction={pending_action}
            confirmedRecord={confirmed_record}
            onConfirm={onConfirmEscalation}
            isProcessing={isProcessingAction}
          />
        )}
      </div>
    </div>
  );
}
