"use client";

import React, { useEffect, useRef } from "react";
import { ChatMessage, SourceItem } from "@/types";
import { UserMessage } from "./UserMessage";
import { AssistantMessage } from "./AssistantMessage";

interface ConversationProps {
  messages: ChatMessage[];
  isLoading: boolean;
  onSelectPrompt: (prompt: string) => void;
  onSelectSource: (source: SourceItem) => void;
  onOpenActivity: () => void;
  onConfirmEscalation: (token: string) => Promise<void>;
  isProcessingAction?: boolean;
  selectedSource?: SourceItem | null;
  /** Initials for the operator avatar on user turns. */
  userInitials?: string;
}

/** Short chip label -> the actual question sent to the agent. */
const QUICK_PROMPTS: { label: string; prompt: string }[] = [
  {
    label: "Can I cancel ORD-1001?",
    prompt: "Can Northstar cancel ORD-1001 without a cancellation fee?",
  },
  {
    label: "Check Northstar P1 SLA",
    prompt: "What is the P1 first-response SLA for ACCT-001?",
  },
  {
    label: "Investigate TKT-502",
    prompt: "Investigate TKT-502 and give the applicable SLA and workaround.",
  },
  {
    label: "Escalate TKT-505",
    prompt: "Escalate ticket TKT-505 immediately for API key exposure",
  },
];

export function Conversation({
  messages,
  isLoading,
  onSelectPrompt,
  onSelectSource,
  onOpenActivity,
  onConfirmEscalation,
  isProcessingAction,
  selectedSource,
  userInitials,
}: ConversationProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex-1 overflow-y-auto px-4">
      <div className="max-w-[700px] mx-auto min-h-full flex flex-col">
        {isEmpty ? (
          /* Compact welcome state -- the centre of the screen stays quiet. */
          <div className="m-auto w-full py-10 text-center">
            <h2 className="text-[15px] font-semibold text-[var(--text)] tracking-[-0.01em]">
              ParcelPilot Copilot
            </h2>
            <p className="mt-1.5 text-[13px] text-[var(--text-2)] leading-relaxed max-w-[320px] mx-auto">
              Ask about shipments, tickets, SLAs, agreements or operational policies.
            </p>

            <div className="mt-5 flex flex-wrap justify-center gap-1.5">
              {QUICK_PROMPTS.map((q) => (
                <button
                  key={q.label}
                  onClick={() => onSelectPrompt(q.prompt)}
                  className="h-[28px] px-2.5 rounded-md border border-[var(--border)] hover:border-[var(--border-hover)] bg-[var(--surface)] hover:bg-[var(--surface-hover)] text-[12px] text-[var(--text-2)] hover:text-[var(--text)] transition-colors cursor-pointer"
                >
                  {q.label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="py-6 flex flex-col">
            {messages.map((msg) =>
              msg.role === "user" ? (
                <UserMessage
                  key={msg.id}
                  content={msg.content}
                  timestamp={msg.timestamp}
                  initials={userInitials}
                />
              ) : (
                <AssistantMessage
                  key={msg.id}
                  message={msg}
                  onSelectSource={onSelectSource}
                  onOpenActivity={onOpenActivity}
                  onConfirmEscalation={onConfirmEscalation}
                  isProcessingAction={isProcessingAction}
                  selectedSourceId={selectedSource?.id}
                />
              )
            )}

            {isLoading && (
              <div className="mt-6 flex items-center gap-2 text-[13px] text-[var(--text-2)]">
                <span>ParcelPilot is working</span>
                <span className="flex items-center gap-[3px]" aria-hidden="true">
                  <span className="pp-dot w-[3px] h-[3px] rounded-full bg-[var(--text-2)]" />
                  <span className="pp-dot w-[3px] h-[3px] rounded-full bg-[var(--text-2)]" />
                  <span className="pp-dot w-[3px] h-[3px] rounded-full bg-[var(--text-2)]" />
                </span>
              </div>
            )}
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
