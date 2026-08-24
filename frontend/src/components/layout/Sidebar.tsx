"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Plus,
  Trash2,
  ChevronDown,
  ChevronRight,
  ChevronsLeft,
  Check,
  Building2,
  FileText,
  Timer,
  Coins,
  ShieldAlert,
  BookOpen,
} from "lucide-react";
import { ChatSession, Principal } from "@/types";
import { TEST_SCENARIOS } from "@/lib/constants";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { cn, formatRelativeTime, principalDisplay } from "@/lib/utils";

interface SidebarProps {
  principals: Principal[];
  currentPrincipal: Principal;
  onPrincipalChange: (principal: Principal) => void;
  sessions: ChatSession[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession: (id: string) => void;
  onSelectScenario: (prompt: string, principalId?: string) => void;
  apiHealthOk: boolean;
  /** Dataset snapshot the API is serving, e.g. "2026-08-16 11:00 Asia/Kolkata". */
  snapshot?: string | null;
  onViewSnapshotDetails?: () => void;
}

/** Icon per scenario, keyed off the `category` already on each TEST_SCENARIOS entry. */
const SCENARIO_ICONS: Record<string, React.ElementType> = {
  agreement: FileText,
  sla: Timer,
  credit: Coins,
  security: ShieldAlert,
  policy: BookOpen,
};

/** "2026-08-16 11:00 Asia/Kolkata" -> "Aug 16, 2026 · 11:00 AM" */
function formatSnapshot(snapshot?: string | null): string | null {
  if (!snapshot) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(snapshot.trim());
  if (!m) return snapshot;

  const [, year, month, day, hh, mm] = m;
  const d = new Date(Number(year), Number(month) - 1, Number(day), Number(hh), Number(mm));
  if (isNaN(d.getTime())) return snapshot;

  const date = d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${date} · ${time}`;
}

export function Sidebar({
  principals,
  currentPrincipal,
  onPrincipalChange,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  onSelectScenario,
  apiHealthOk,
  snapshot,
  onViewSnapshotDetails,
}: SidebarProps) {
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const [isFooterPickerOpen, setIsFooterPickerOpen] = useState(false);
  const [isHistoryCollapsed, setIsHistoryCollapsed] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);
  const footerRef = useRef<HTMLDivElement>(null);
  const active = principalDisplay(currentPrincipal);
  const snapshotLabel = formatSnapshot(snapshot);

  // Close either principal picker on outside click / Escape.
  useEffect(() => {
    if (!isPickerOpen && !isFooterPickerOpen) return;
    const onPointerDown = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setIsPickerOpen(false);
      }
      if (footerRef.current && !footerRef.current.contains(e.target as Node)) {
        setIsFooterPickerOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsPickerOpen(false);
        setIsFooterPickerOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [isPickerOpen, isFooterPickerOpen]);

  /** Shared option list for both entry points into the principal switcher. */
  const principalOptions = (onPick: () => void) =>
    principals.map((p) => {
      const info = principalDisplay(p);
      const isActive = p.user_id === currentPrincipal.user_id;
      return (
        <button
          key={p.user_id}
          role="option"
          aria-selected={isActive}
          onClick={() => {
            onPrincipalChange(p);
            onPick();
          }}
          className={cn(
            "w-full flex items-center justify-between gap-2 px-2 py-1.5 rounded text-left transition-colors cursor-pointer",
            isActive ? "bg-white/[0.06]" : "hover:bg-white/[0.04]"
          )}
        >
          <span className="min-w-0">
            <span
              className={cn(
                "block text-[12px] truncate leading-tight",
                isActive ? "text-[var(--text)] font-medium" : "text-[var(--text-2)]"
              )}
            >
              {info.name}
            </span>
            <span className="block text-[10.5px] text-[var(--text-3)] truncate leading-tight mt-px">
              {info.scope}
            </span>
          </span>
          {isActive && <Check className="w-3.5 h-3.5 text-[var(--accent-text)] shrink-0" />}
        </button>
      );
    });

  return (
    <aside className="w-[280px] h-full flex flex-col bg-[var(--sidebar)] border-r border-[var(--border)] select-none">
      {/* Brand -- monochrome mark, so the only colour in the rail is status. */}
      <div className="px-3 pt-3.5 pb-3.5">
        <div className="flex items-center gap-2.5">
          <div className="w-[26px] h-[26px] rounded-[7px] bg-[var(--surface-active)] border border-[var(--border)] flex items-center justify-center text-[var(--text)] shrink-0">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </div>
          <div className="min-w-0">
            <div className="text-[13.5px] font-semibold text-[var(--text)] tracking-[-0.01em] leading-tight">
              ParcelPilot
            </div>
            <div className="text-[11px] text-[var(--text-3)] leading-tight mt-px">
              AI Support Operations
            </div>
          </div>
        </div>
      </div>

      {/* Acting principal -- the answer to "who am I acting as?" */}
      <div className="px-3 pb-3" ref={pickerRef}>
        <SectionLabel className="mb-1.5">Acting principal</SectionLabel>
        <div className="relative">
          <button
            onClick={() => setIsPickerOpen((v) => !v)}
            aria-haspopup="listbox"
            aria-expanded={isPickerOpen}
            className={cn(
              "w-full flex items-center gap-2 px-2 h-[46px] rounded-md border text-left transition-colors cursor-pointer",
              isPickerOpen
                ? "bg-[var(--surface-active)] border-[var(--border-hover)]"
                : "bg-[var(--surface)] border-[var(--border)] hover:border-[var(--border-hover)]"
            )}
          >
            <span className="w-[26px] h-[26px] rounded-md bg-[var(--surface-active)] border border-[var(--border)] flex items-center justify-center shrink-0">
              <Building2 className="w-3.5 h-3.5 text-[var(--text-2)]" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[12.5px] font-medium text-[var(--text)] truncate leading-tight">
                {active.name}
              </span>
              <span className="block text-[10.5px] text-[var(--text-3)] truncate leading-tight mt-px">
                {currentPrincipal.role === "customer" ? "Customer" : "Internal"} · {active.scope}
              </span>
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-[var(--text-3)] shrink-0" />
          </button>

          {isPickerOpen && (
            <div
              role="listbox"
              className="absolute z-30 top-[50px] left-0 right-0 p-1 rounded-md border border-[var(--border-hover)] bg-[var(--popover)] shadow-xl shadow-black/40"
            >
              {principalOptions(() => setIsPickerOpen(false))}
            </div>
          )}
        </div>
      </div>

      {/* New conversation */}
      <div className="px-3 pb-3">
        <button
          onClick={onNewSession}
          className="w-full h-[34px] flex items-center justify-between px-2.5 rounded-md bg-[var(--surface)] hover:bg-[var(--surface-hover)] border border-[var(--border)] hover:border-[var(--border-hover)] transition-colors cursor-pointer"
        >
          <span className="flex items-center gap-2 text-[12.5px] font-medium text-[var(--text)]">
            <Plus className="w-3.5 h-3.5 text-[var(--text-2)]" />
            New conversation
          </span>
          <kbd className="text-[10px] text-[var(--text-3)] font-mono">⌘N</kbd>
        </button>
      </div>

      {/* Conversation history -- the primary list, given the remaining height */}
      <div className="flex-1 min-h-0 overflow-y-auto px-2">
        <div className="flex items-center justify-between gap-1 px-1.5 pb-1.5">
          <SectionLabel>Conversations</SectionLabel>
          <button
            onClick={() => setIsHistoryCollapsed((v) => !v)}
            className="p-0.5 rounded text-[var(--text-3)] hover:text-[var(--text-2)] hover:bg-white/[0.04] transition-colors cursor-pointer"
            title={isHistoryCollapsed ? "Expand conversations" : "Collapse conversations"}
            aria-expanded={!isHistoryCollapsed}
          >
            <ChevronsLeft
              className={cn(
                "w-3 h-3 transition-transform",
                isHistoryCollapsed && "rotate-180"
              )}
            />
          </button>
        </div>

        {isHistoryCollapsed ? null : sessions.length === 0 ? (
          <div className="px-1.5 py-2 text-[11.5px] text-[var(--text-3)]">No conversations yet</div>
        ) : (
          <div className="space-y-px">
            {sessions.map((sess) => {
              const isActive = sess.id === activeSessionId;
              return (
                <div
                  key={sess.id}
                  onClick={() => onSelectSession(sess.id)}
                  className={cn(
                    "group relative h-[32px] flex items-center justify-between gap-1.5 pl-2.5 pr-1.5 rounded-md cursor-pointer transition-colors",
                    isActive
                      ? "bg-[var(--surface-active)] text-[var(--text)]"
                      : "text-[var(--text-2)] hover:bg-white/[0.03] hover:text-[var(--text)]"
                  )}
                >
                  {/* Selection is a marker, not a box -- no border to compete with the rail. */}
                  {isActive && (
                    <span className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full bg-[var(--text)]" />
                  )}
                  <span className="truncate text-[12px]">{sess.title}</span>

                  {/* Age by default; the delete affordance takes its place on hover. */}
                  <span className="shrink-0 text-[10.5px] text-[var(--text-3)] group-hover:hidden">
                    {formatRelativeTime(sess.updatedAt)}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteSession(sess.id);
                    }}
                    className="hidden group-hover:block p-0.5 rounded text-[var(--text-3)] hover:text-[var(--critical-text)] transition-colors cursor-pointer shrink-0"
                    title="Delete conversation"
                    aria-label={`Delete conversation ${sess.title}`}
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Demo scenarios -- deliberately below the fold of real work */}
      <div className="border-t border-[var(--border)] px-2 py-2 shrink-0">
        <SectionLabel className="px-1.5 pb-1.5">Demo scenarios</SectionLabel>
        <div className="space-y-px">
          {TEST_SCENARIOS.map((sc) => {
            const Icon = SCENARIO_ICONS[sc.category] || FileText;
            return (
              <button
                key={sc.id}
                onClick={() => onSelectScenario(sc.prompt, sc.recommendedPrincipal)}
                title={sc.description}
                className="w-full h-[30px] flex items-center gap-2 px-2 rounded-md text-left text-[12px] text-[var(--text-2)] hover:text-[var(--text)] hover:bg-white/[0.03] transition-colors cursor-pointer"
              >
                <Icon className="w-3.5 h-3.5 text-[var(--text-3)] shrink-0" />
                <span className="truncate">{sc.title}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Dataset snapshot -- what "now" means for every answer in this session */}
      <div className="px-3 pb-2.5 pt-2 shrink-0">
        <div className="rounded-md border border-[var(--border)] bg-[var(--surface)] px-2.5 py-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11.5px] font-medium text-[var(--text)]">Dataset snapshot</span>
            <span className="flex items-center gap-1.5 text-[10.5px] text-[var(--text-3)] shrink-0">
              <span
                className={cn(
                  "w-1.5 h-1.5 rounded-full",
                  apiHealthOk ? "bg-[var(--success)]" : "bg-[var(--critical)]"
                )}
              />
              {apiHealthOk ? "Live" : "Offline"}
            </span>
          </div>

          <div className="mt-1 text-[10.5px] text-[var(--text-3)] leading-tight">
            {snapshotLabel ? `As of ${snapshotLabel}` : "Awaiting API"}
          </div>

          {onViewSnapshotDetails && (
            <button
              onClick={onViewSnapshotDetails}
              className="mt-1.5 inline-flex items-center gap-1 text-[10.5px] text-[var(--text-2)] hover:text-[var(--text)] transition-colors cursor-pointer"
            >
              View details
              <ChevronRight className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Operator identity -- second entry point to the same principal switcher */}
      <div className="px-3 pb-3 shrink-0 relative" ref={footerRef}>
        {isFooterPickerOpen && (
          <div
            role="listbox"
            className="absolute z-30 bottom-[52px] left-3 right-3 p-1 rounded-md border border-[var(--border-hover)] bg-[var(--popover)] shadow-xl shadow-black/40"
          >
            {principalOptions(() => setIsFooterPickerOpen(false))}
          </div>
        )}

        <button
          onClick={() => setIsFooterPickerOpen((v) => !v)}
          aria-haspopup="listbox"
          aria-expanded={isFooterPickerOpen}
          className={cn(
            "w-full flex items-center gap-2 px-1.5 h-[42px] rounded-md border transition-colors cursor-pointer text-left",
            isFooterPickerOpen
              ? "bg-[var(--surface-active)] border-[var(--border-hover)]"
              : "border-transparent hover:bg-white/[0.03]"
          )}
        >
          <span className="w-[26px] h-[26px] rounded-md bg-[var(--surface-active)] border border-[var(--border)] flex items-center justify-center shrink-0 text-[10.5px] font-semibold text-[var(--text-2)]">
            {active.name.slice(0, 2).toUpperCase()}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[12px] font-medium text-[var(--text)] truncate leading-tight">
              {active.name}
            </span>
            <span className="block text-[10.5px] text-[var(--text-3)] truncate leading-tight mt-px">
              {principalDisplay(currentPrincipal).scope === "All accounts"
                ? currentPrincipal.role === "ops_manager"
                  ? "Ops manager"
                  : "Support agent"
                : "Customer"}
            </span>
          </span>
          <ChevronDown className="w-3.5 h-3.5 text-[var(--text-3)] shrink-0" />
        </button>
      </div>
    </aside>
  );
}
