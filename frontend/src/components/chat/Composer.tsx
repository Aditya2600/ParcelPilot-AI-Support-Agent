"use client";

import React, { useState, useRef, useEffect } from "react";
import { ArrowRight, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface ComposerProps {
  onSendMessage: (message: string) => Promise<void>;
  isLoading: boolean;
  placeholder?: string;
  initialValue?: string;
}

export function Composer({
  onSendMessage,
  isLoading,
  placeholder = "Ask about an order, ticket, SLA, policy or agreement…",
  initialValue = "",
}: ComposerProps) {
  const [input, setInput] = useState(initialValue);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (initialValue) {
      setInput(initialValue);
      textareaRef.current?.focus();
    }
  }, [initialValue]);

  // Auto-expand height up to 160px
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    await onSendMessage(trimmed);
  };

  return (
    <div className="shrink-0 px-4 pb-3 pt-2 bg-[var(--main)]">
      <div className="max-w-[700px] mx-auto">
        <form
          onSubmit={handleSubmit}
          className="rounded-[10px] border border-[var(--border)] focus-within:border-[var(--border-hover)] bg-[var(--surface)] transition-colors"
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            placeholder={placeholder}
            rows={2}
            className="w-full bg-transparent px-3.5 pt-3 text-[13.5px] text-[var(--text)] placeholder-[var(--text-3)] resize-none outline-none max-h-[160px] leading-[1.5] disabled:opacity-60"
          />

          <div className="flex items-center justify-between gap-2 px-2.5 pb-2.5 pt-1">
            <span className="text-[11px] text-[var(--text-3)] select-none">
              <span className="font-mono">⇧↵</span> New line
            </span>

            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className={cn(
                "h-8 w-8 rounded-md flex items-center justify-center transition-colors border",
                input.trim() && !isLoading
                  ? "bg-[var(--text)] border-transparent text-[var(--app-bg)] hover:opacity-90 cursor-pointer"
                  : "bg-[var(--surface-active)] border-[var(--border)] text-[var(--text-3)] cursor-not-allowed"
              )}
              aria-label="Send message"
            >
              {isLoading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <ArrowRight className="w-4 h-4 stroke-[2.25]" />
              )}
            </button>
          </div>
        </form>

        <p className="mt-2 text-center text-[11px] text-[var(--text-3)]">
          ParcelPilot can make mistakes. Verify critical decisions.
        </p>
      </div>
    </div>
  );
}
