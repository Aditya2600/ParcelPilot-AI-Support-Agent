"use client";

import React, { useEffect, useState } from "react";
import { ChevronRight, RefreshCw } from "lucide-react";
import { Principal, ProactiveIssue } from "@/types";
import { Badge } from "@/components/ui/Badge";
import { apiUrl } from "@/lib/api";

interface ProactiveQueueTabProps {
  currentPrincipal: Principal;
  onSelectPrompt?: (prompt: string) => void;
}

/**
 * Open operational risks for internal staff, rendered as a section of the
 * Account tab rather than a top-level destination. Renders nothing for
 * customer principals, who have no visibility into the triage queue.
 */
export function ProactiveQueueTab({ currentPrincipal, onSelectPrompt }: ProactiveQueueTabProps) {
  const [issues, setIssues] = useState<ProactiveIssue[]>([]);
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isInternal = ["support_agent", "ops_manager"].includes(currentPrincipal.role);

  const fetchRisks = async () => {
    if (!isInternal) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(
        apiUrl(`/api/proactive?role=${currentPrincipal.role}&user_id=${currentPrincipal.user_id}`)
      );
      if (!res.ok) throw new Error("Could not load the triage queue");
      const data = await res.json();
      setIssues(data.issues || []);
      setSnapshot(data.snapshot || null);
    } catch (err: any) {
      setError(err.message || "Could not load the triage queue");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRisks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPrincipal]);

  if (!isInternal) return null;

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10.5px] font-semibold text-[var(--text-3)] uppercase tracking-[0.06em]">
          Open risks
        </span>
        <button
          onClick={fetchRisks}
          disabled={isLoading}
          title={snapshot ? `Snapshot ${snapshot}` : "Refresh"}
          aria-label="Refresh open risks"
          className="p-1 rounded text-[var(--text-3)] hover:text-[var(--text)] hover:bg-white/[0.04] transition-colors cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${isLoading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error && <div className="text-[12px] text-[var(--critical-text)]">{error}</div>}

      {!error && issues.length === 0 && !isLoading && (
        <div className="text-[12px] text-[var(--text-3)]">No open risks in this snapshot.</div>
      )}

      <div className="space-y-1.5">
        {issues.map((issue) => (
          <div
            key={issue.ticket_id}
            className="rounded-md border border-[var(--border)] bg-[var(--surface)] p-2.5 hover:border-[var(--border-hover)] transition-colors"
          >
            <div className="flex items-center gap-2 min-w-0">
              <Badge variant={issue.severity.toLowerCase() as "p1" | "p2" | "p3"}>
                {issue.severity}
              </Badge>
              <span className="font-mono text-[12px] text-[var(--text)]">{issue.ticket_id}</span>
              <span className="text-[11.5px] text-[var(--text-3)] truncate">{issue.account}</span>
            </div>

            <p className="mt-1.5 text-[11.5px] text-[var(--text-2)] leading-relaxed">{issue.reason}</p>

            <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-[var(--text-3)]">
              <span className="truncate">{issue.owner}</span>
              {onSelectPrompt && (
                <button
                  onClick={() =>
                    onSelectPrompt(
                      issue.severity === "P1"
                        ? `Escalate ticket ${issue.ticket_id} immediately: ${issue.reason}`
                        : `What is the status and policy guidance for ${issue.ticket_id}?`
                    )
                  }
                  className="inline-flex items-center gap-0.5 text-[var(--accent-text)] hover:text-[var(--text)] transition-colors cursor-pointer shrink-0"
                >
                  Investigate
                  <ChevronRight className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
