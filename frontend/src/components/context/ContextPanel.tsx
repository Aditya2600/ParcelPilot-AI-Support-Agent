"use client";

import React from "react";
import { X } from "lucide-react";
import { Principal, SourceItem, ToolStep } from "@/types";
import { EvidenceTab } from "./EvidenceTab";
import { ActivityTab } from "./ActivityTab";
import { AccountTab } from "./AccountTab";
import { cn } from "@/lib/utils";

export type ContextTab = "evidence" | "activity" | "account";

interface ContextPanelProps {
  currentPrincipal: Principal;
  sources?: SourceItem[];
  selectedSource?: SourceItem | null;
  toolTrace?: ToolStep[];
  confidence?: "high" | "medium" | "low" | null;
  activeTab: ContextTab;
  onTabChange: (tab: ContextTab) => void;
  onSelectSource?: (source: SourceItem) => void;
  onSelectPrompt?: (prompt: string) => void;
  onClose?: () => void;
}

const TABS: { id: ContextTab; label: string }[] = [
  { id: "evidence", label: "Evidence" },
  { id: "activity", label: "Activity" },
  { id: "account", label: "Account" },
];

export function ContextPanel({
  currentPrincipal,
  sources = [],
  selectedSource,
  toolTrace = [],
  confidence,
  activeTab,
  onTabChange,
  onSelectSource,
  onSelectPrompt,
  onClose,
}: ContextPanelProps) {
  return (
    <aside className="h-full flex flex-col bg-[var(--inspector)] border-l border-[var(--border)]">
      {/* Underline tabs: the active section is marked, not boxed. */}
      <div className="h-[52px] shrink-0 flex items-stretch justify-between gap-2 px-3 border-b border-[var(--border)]">
        <div className="flex items-stretch gap-3 min-w-0">
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                aria-selected={isActive}
                role="tab"
                className={cn(
                  "relative inline-flex items-center text-[13px] transition-colors cursor-pointer",
                  isActive
                    ? "text-[var(--text)] font-medium"
                    : "text-[var(--text-3)] hover:text-[var(--text-2)]"
                )}
              >
                {tab.label}
                {isActive && (
                  <span className="absolute left-0 right-0 bottom-0 h-[2px] rounded-full bg-[var(--text)]" />
                )}
              </button>
            );
          })}
        </div>

        {onClose && (
          <button
            onClick={onClose}
            className="self-center p-1 rounded text-[var(--text-3)] hover:text-[var(--text)] hover:bg-white/[0.04] transition-colors cursor-pointer shrink-0"
            title="Close panel"
            aria-label="Close context panel"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-hidden">
        {activeTab === "evidence" && (
          <EvidenceTab
            sources={sources}
            toolTrace={toolTrace}
            selectedSource={selectedSource}
            onSelectSource={onSelectSource}
          />
        )}
        {activeTab === "activity" && <ActivityTab trace={toolTrace} confidence={confidence} />}
        {activeTab === "account" && (
          <AccountTab currentPrincipal={currentPrincipal} onSelectPrompt={onSelectPrompt} />
        )}
      </div>
    </aside>
  );
}
