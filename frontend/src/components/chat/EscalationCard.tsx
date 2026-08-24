"use client";

import React, { useState } from "react";
import { AlertTriangle, Check, Copy, Loader2 } from "lucide-react";
import { PendingAction, ConfirmedRecord } from "@/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

interface EscalationCardProps {
  pendingAction?: PendingAction | null;
  confirmedRecord?: ConfirmedRecord | null;
  onConfirm?: (token: string) => Promise<void>;
  isProcessing?: boolean;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-[5px]">
      <span className="text-[11.5px] text-[var(--text-3)] shrink-0">{label}</span>
      <span className="text-[12px] text-[var(--text)] text-right min-w-0 truncate">{children}</span>
    </div>
  );
}

/**
 * The one place in the UI where "prepared" and "executed" must never be
 * confusable: a staged action is amber and explicitly says nothing was created,
 * a confirmed one is green and carries the escalation id the API returned.
 */
export function EscalationCard({
  pendingAction,
  confirmedRecord,
  onConfirm,
  isProcessing = false,
}: EscalationCardProps) {
  const [isCancelled, setIsCancelled] = useState(false);
  const [copied, setCopied] = useState(false);

  if (isCancelled) {
    return (
      <div className="mt-4 px-3 py-2 rounded-md border border-[var(--border)] bg-[var(--surface)] text-[12px] text-[var(--text-2)] flex items-center gap-2">
        <AlertTriangle className="w-3.5 h-3.5 text-[var(--warning)] shrink-0" />
        Escalation dismissed. Nothing was created.
      </div>
    );
  }

  if (confirmedRecord) {
    const handleCopy = () => {
      navigator.clipboard.writeText(confirmedRecord.escalation_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    };

    return (
      <div className="mt-4 rounded-md border border-[var(--success-border)] bg-[var(--success-soft)] overflow-hidden">
        <div className="flex items-center justify-between gap-2 px-3 h-[38px] border-b border-[var(--success-border)]">
          <span className="flex items-center gap-2 text-[13px] font-medium text-[var(--success-text)]">
            <Check className="w-3.5 h-3.5" />
            Escalation created
          </span>
          <Badge variant="governing">Confirmed</Badge>
        </div>

        <div className="px-3 py-1.5 divide-y divide-[var(--border)]">
          <Row label="Escalation ID">
            <span className="inline-flex items-center gap-1.5">
              <span className="font-mono text-[var(--success-text)]">
                {confirmedRecord.escalation_id}
              </span>
              <button
                onClick={handleCopy}
                className="text-[var(--text-3)] hover:text-[var(--text)] cursor-pointer"
                title="Copy escalation ID"
                aria-label="Copy escalation ID"
              >
                {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
              </button>
            </span>
          </Row>
          <Row label="Severity">{confirmedRecord.severity}</Row>
          {confirmedRecord.ticket_id && (
            <Row label="Ticket">
              <span className="font-mono">{confirmedRecord.ticket_id}</span>
            </Row>
          )}
          <Row label="Account">
            <span className="font-mono">{confirmedRecord.account_id}</span>
          </Row>
          <Row label="Created">{confirmedRecord.created_at}</Row>
        </div>
      </div>
    );
  }

  if (pendingAction) {
    return (
      <div className="mt-4 rounded-md border border-[var(--warning-border)] bg-[var(--warning-soft)] overflow-hidden">
        <div className="flex items-center justify-between gap-2 px-3 h-[38px] border-b border-[var(--warning-border)]">
          <span className="flex items-center gap-2 text-[13px] font-medium text-[var(--warning-text)]">
            <AlertTriangle className="w-3.5 h-3.5" />
            Escalation prepared
          </span>
          <Badge variant="p2">Not yet created</Badge>
        </div>

        <div className="px-3 py-1.5 divide-y divide-[var(--border)]">
          <Row label="Ticket">
            <span className="font-mono">{pendingAction.ticket_id || "None (direct)"}</span>
          </Row>
          <Row label="Account">
            <span className="font-mono">{pendingAction.account_id}</span>
          </Row>
          <Row label="Severity">{pendingAction.severity}</Row>
          <Row label="Prepared by">
            <span className="font-mono">{pendingAction.prepared_by}</span>
          </Row>
        </div>

        <div className="px-3 pt-1.5 pb-2.5">
          <div className="text-[11.5px] text-[var(--text-3)] mb-0.5">Reason</div>
          <p className="text-[12.5px] text-[var(--text-2)] leading-relaxed">{pendingAction.reason}</p>
        </div>

        <div className="px-3 py-2.5 border-t border-[var(--warning-border)] flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
          <p className="text-[11.5px] text-[var(--text-3)]">
            Nothing has been created yet. Confirm to record it.
          </p>
          <div className="flex items-center gap-1.5 shrink-0">
            <Button variant="outline" size="sm" onClick={() => setIsCancelled(true)} disabled={isProcessing}>
              Dismiss
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => onConfirm && onConfirm(pendingAction.confirmation_token)}
              disabled={isProcessing}
            >
              {isProcessing ? (
                <>
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Recording…
                </>
              ) : (
                "Confirm escalation"
              )}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
