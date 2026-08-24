import React from "react";
import { formatTimestamp } from "@/lib/utils";

interface UserMessageProps {
  content: string;
  timestamp?: string;
  /** Initials for the operator avatar, derived from the acting principal. */
  initials?: string;
}

/**
 * An attributed turn: avatar, speaker and time, then the text in a raised
 * bubble. The bubble is what separates the operator's words from the agent's
 * answer, which stays flat prose directly on the page.
 */
export function UserMessage({ content, timestamp, initials = "You" }: UserMessageProps) {
  return (
    <div className="mt-8 first:mt-0">
      <div className="flex items-center gap-2 mb-2">
        <span className="w-[26px] h-[26px] rounded-md bg-[var(--surface-active)] border border-[var(--border)] flex items-center justify-center shrink-0 text-[10px] font-semibold text-[var(--text-2)]">
          {initials.slice(0, 2).toUpperCase()}
        </span>
        <span className="text-[12.5px] font-semibold text-[var(--text)]">You</span>
        {timestamp && (
          <span className="text-[11px] text-[var(--text-3)]">{formatTimestamp(timestamp)}</span>
        )}
      </div>

      <div className="pl-[34px]">
        <div className="inline-block max-w-full rounded-lg rounded-tl-sm border border-[var(--border)] bg-[var(--surface)] px-3 py-2">
          <p className="text-[13.5px] leading-[1.5] text-[var(--text)] whitespace-pre-wrap select-text">
            {content}
          </p>
        </div>
      </div>
    </div>
  );
}
