"use client";

import React, { useEffect, useState } from "react";
import { ChevronRight, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { ProactiveQueueTab } from "./ProactiveQueueTab";
import { AccountMetadata, Principal } from "@/types";
import { cleanSourceTitle } from "@/lib/utils";

interface AccountTabProps {
  currentPrincipal: Principal;
  onSelectPrompt?: (prompt: string) => void;
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10.5px] font-semibold text-[var(--text-3)] uppercase tracking-[0.06em] mb-1">
      {children}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-[6px] border-b border-[var(--border)] last:border-b-0">
      <span className="text-[12px] text-[var(--text-3)] shrink-0">{label}</span>
      <span className="text-[12px] text-[var(--text)] text-right min-w-0 truncate">{children}</span>
    </div>
  );
}

export function AccountTab({ currentPrincipal, onSelectPrompt }: AccountTabProps) {
  const [accounts, setAccounts] = useState<AccountMetadata[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    const params = new URLSearchParams({
      role: currentPrincipal.role,
      user_id: currentPrincipal.user_id,
    });
    if (currentPrincipal.account_id) params.set("account_id", currentPrincipal.account_id);

    fetch(apiUrl(`/api/accounts?${params.toString()}`))
      .then((res) => {
        if (!res.ok) throw new Error(`Could not load account context (${res.status})`);
        return res.json();
      })
      .then((data: { accounts: AccountMetadata[] }) => {
        if (cancelled) return;
        setAccounts(data.accounts || []);
        setSelectedAccountId((prev) =>
          data.accounts?.some((a) => a.account_id === prev) ? prev : data.accounts?.[0]?.account_id || ""
        );
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [currentPrincipal]);

  if (isLoading && accounts.length === 0) {
    return (
      <div className="px-3.5 py-3 flex items-center gap-2 text-[12px] text-[var(--text-3)]">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        Loading account context…
      </div>
    );
  }

  if (error) {
    return <div className="px-3.5 py-3 text-[12px] text-[var(--critical-text)]">{error}</div>;
  }

  const account = accounts.find((a) => a.account_id === selectedAccountId) || accounts[0];

  if (!account) {
    return (
      <div className="px-3.5 py-3 text-[12px] text-[var(--text-3)]">
        No account is in scope for this principal.
      </div>
    );
  }

  const hasSlaOverride = (["P1", "P2", "P3"] as const).some(
    (sev) => account.sla_targets[sev]?.is_override
  );

  return (
    <div className="px-3.5 py-3 space-y-5 overflow-y-auto max-h-full">
      {/* Account switcher -- internal roles only; customers see one account. */}
      {accounts.length > 1 && (
        <select
          value={selectedAccountId}
          onChange={(e) => setSelectedAccountId(e.target.value)}
          aria-label="Select account"
          className="w-full h-[28px] px-2 rounded-md bg-[var(--surface)] border border-[var(--border)] hover:border-[var(--border-hover)] text-[12px] text-[var(--text)] outline-none cursor-pointer"
        >
          {accounts.map((acc) => (
            <option key={acc.account_id} value={acc.account_id}>
              {acc.account_name} · {acc.account_id}
            </option>
          ))}
        </select>
      )}

      {/* Identity */}
      <div>
        <h3 className="text-[14px] font-semibold text-[var(--text)] leading-tight">
          {account.account_name}
        </h3>
        <div className="mt-0.5 flex items-center gap-2">
          <span className="font-mono text-[11.5px] text-[var(--text-3)]">{account.account_id}</span>
          <Badge variant="enterprise">{account.plan}</Badge>
        </div>
      </div>

      {/* Account properties */}
      <div>
        <SectionLabel>Account</SectionLabel>
        <div>
          <Row label="Plan">{account.plan}</Row>
          <Row label="Status">{account.status}</Row>
          <Row label="CSM">{account.csm || "—"}</Row>
          <Row label="Agreement">
            {account.contract_file ? (
              <span className="text-[var(--success-text)]" title={account.contract_file}>
                {cleanSourceTitle(account.contract_file)}
              </span>
            ) : (
              <span className="text-[var(--text-3)]">Standard policy only</span>
            )}
          </Row>
          <Row label="Premium support">{account.premium_support ? "24×7" : "Standard hours"}</Row>
        </div>

        {account.notes && (
          <p className="mt-2 text-[11.5px] text-[var(--text-3)] leading-relaxed">{account.notes}</p>
        )}
      </div>

      {/* SLA targets */}
      <div>
        <SectionLabel>First response SLA</SectionLabel>
        <div>
          {(["P1", "P2", "P3"] as const).map((sev) => {
            const target = account.sla_targets[sev];
            return (
              <Row key={sev} label={sev}>
                <span className="inline-flex items-center gap-1.5">
                  {target?.first_response_target || "—"}
                  {target?.is_override && <Badge variant="governing">Agreement</Badge>}
                </span>
              </Row>
            );
          })}
        </div>
        {hasSlaOverride && (
          <p className="mt-1.5 text-[11.5px] text-[var(--success-text)]">Agreement override active</p>
        )}
      </div>

      {/* Shipments */}
      {account.orders.length > 0 && (
        <div>
          <SectionLabel>Shipments</SectionLabel>
          <div>
            {account.orders.map((ord) => (
              <div
                key={ord.order_id}
                className="flex items-center justify-between gap-2 py-[7px] border-b border-[var(--border)] last:border-b-0"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[12px] text-[var(--text)]">{ord.order_id}</span>
                    <span className="text-[11px] text-[var(--text-3)]">{ord.status}</span>
                  </div>
                  <div className="text-[11px] text-[var(--text-3)] truncate">{ord.carrier}</div>
                </div>

                {onSelectPrompt && (
                  <button
                    onClick={() =>
                      onSelectPrompt(`Can ${account.account_name} cancel ${ord.order_id} without a fee?`)
                    }
                    className="p-1 rounded text-[var(--text-3)] hover:text-[var(--text)] hover:bg-white/[0.04] transition-colors cursor-pointer shrink-0"
                    title={`Ask about ${ord.order_id}`}
                    aria-label={`Ask about ${ord.order_id}`}
                  >
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tickets */}
      {account.tickets.length > 0 && (
        <div>
          <SectionLabel>Tickets</SectionLabel>
          <div>
            {account.tickets.map((tkt) => (
              <div
                key={tkt.ticket_id}
                className="flex items-center justify-between gap-2 py-[7px] border-b border-[var(--border)] last:border-b-0"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[12px] text-[var(--text)]">{tkt.ticket_id}</span>
                    <span className="text-[11px] text-[var(--text-3)]">{tkt.status}</span>
                  </div>
                  <div className="text-[11.5px] text-[var(--text-2)] truncate">{tkt.subject}</div>
                </div>

                {onSelectPrompt && (
                  <button
                    onClick={() =>
                      onSelectPrompt(
                        `Provide triage status and recommended action for ticket ${tkt.ticket_id}`
                      )
                    }
                    className="p-1 rounded text-[var(--text-3)] hover:text-[var(--text)] hover:bg-white/[0.04] transition-colors cursor-pointer shrink-0"
                    title={`Ask about ${tkt.ticket_id}`}
                    aria-label={`Ask about ${tkt.ticket_id}`}
                  >
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Operational risks (internal roles only) */}
      <ProactiveQueueTab currentPrincipal={currentPrincipal} onSelectPrompt={onSelectPrompt} />
    </div>
  );
}
