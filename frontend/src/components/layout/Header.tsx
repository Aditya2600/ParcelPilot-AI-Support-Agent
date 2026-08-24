"use client";

import React, { useEffect, useRef, useState } from "react";
import { RotateCcw, BookOpen, Menu, MoreHorizontal } from "lucide-react";
import { Principal } from "@/types";
import { cn, principalDisplay } from "@/lib/utils";

interface HeaderProps {
  sessionTitle: string;
  currentPrincipal: Principal;
  onResetChat: () => void;
  isContextOpen: boolean;
  onToggleContext: () => void;
  onToggleSidebarMobile: () => void;
}

export function Header({
  sessionTitle,
  currentPrincipal,
  onResetChat,
  isContextOpen,
  onToggleContext,
  onToggleSidebarMobile,
}: HeaderProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const { name, scope } = principalDisplay(currentPrincipal);

  useEffect(() => {
    if (!isMenuOpen) return;
    const onPointerDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setIsMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsMenuOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [isMenuOpen]);

  return (
    <header className="min-h-[74px] border-b border-[var(--border)] bg-[var(--main)] px-3 sm:px-5 py-3 flex items-start justify-between gap-3 shrink-0 select-none">
      <div className="flex items-start gap-2.5 min-w-0">
        <button
          onClick={onToggleSidebarMobile}
          className="md:hidden p-1 mt-0.5 rounded text-[var(--text-2)] hover:text-[var(--text)] hover:bg-white/[0.05] cursor-pointer"
          aria-label="Open navigation"
        >
          <Menu className="w-4 h-4" />
        </button>

        <div className="min-w-0">
          <h1 className="text-[19px] font-semibold text-[var(--text)] truncate leading-tight tracking-[-0.015em]">
            {sessionTitle}
          </h1>

          {/* Acting tenant as a segmented pill: who, then under what scope. */}
          <div className="mt-1.5 inline-flex items-stretch rounded-md border border-[var(--border)] bg-[var(--surface)] overflow-hidden max-w-full">
            <span className="px-2 py-[3px] text-[11.5px] font-medium text-[var(--text)] bg-[var(--surface-active)] border-r border-[var(--border)] truncate">
              {name}
            </span>
            <span className="px-2 py-[3px] text-[11.5px] text-[var(--text-3)] truncate">
              {currentPrincipal.role === "customer" ? "Customer" : "Internal"} · {scope}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        <button
          onClick={onToggleContext}
          title={isContextOpen ? "Hide context inspector" : "Show context inspector"}
          className={cn(
            "h-8 px-2.5 rounded-md inline-flex items-center gap-1.5 text-[12.5px] transition-colors cursor-pointer border",
            isContextOpen
              ? "bg-[var(--surface-active)] border-[var(--border-hover)] text-[var(--text)]"
              : "bg-[var(--surface)] border-[var(--border)] text-[var(--text-2)] hover:text-[var(--text)] hover:border-[var(--border-hover)]"
          )}
        >
          <BookOpen className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Context</span>
        </button>

        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setIsMenuOpen((v) => !v)}
            aria-haspopup="menu"
            aria-expanded={isMenuOpen}
            aria-label="More actions"
            className="h-8 w-8 rounded-md inline-flex items-center justify-center border border-[var(--border)] bg-[var(--surface)] text-[var(--text-2)] hover:text-[var(--text)] hover:border-[var(--border-hover)] transition-colors cursor-pointer"
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>

          {isMenuOpen && (
            <div
              role="menu"
              className="absolute right-0 top-8 z-30 w-[176px] p-1 rounded-md border border-[var(--border-hover)] bg-[var(--popover)] shadow-xl shadow-black/40"
            >
              <button
                role="menuitem"
                onClick={() => {
                  onResetChat();
                  setIsMenuOpen(false);
                }}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-[12px] text-[var(--text-2)] hover:text-[var(--text)] hover:bg-white/[0.05] transition-colors cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reset conversation
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
