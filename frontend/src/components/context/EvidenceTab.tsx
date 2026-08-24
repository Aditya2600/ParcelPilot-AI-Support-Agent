"use client";

import React, { useEffect, useRef, useState } from "react";
import { ChevronRight, ExternalLink, FileText, Files } from "lucide-react";
import { SourceItem, ToolStep } from "@/types";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { cleanSourceTitle, cn, sourceMetaLine } from "@/lib/utils";

interface EvidenceTabProps {
  sources?: SourceItem[];
  toolTrace?: ToolStep[];
  selectedSource?: SourceItem | null;
  onSelectSource?: (source: SourceItem) => void;
}

/** Human label for the document_type the retriever tagged this source with. */
function kindLabel(src: SourceItem): string {
  const map: Record<string, string> = {
    agreement: "Agreement",
    sop: "SOP",
    current_policy: "Current policy",
    product_guide: "Product guide",
    historical_ticket: "Historical ticket",
  };
  return map[src.document_type || ""] || "Policy";
}

/** Sources that may never determine an answer, only colour it in. */
function isContextOnly(src: SourceItem): boolean {
  return (
    src.document_type === "historical_ticket" ||
    src.status === "deprecated" ||
    src.lifecycle_state === "superseded"
  );
}

function cleanExcerpt(excerpt?: string): string | null {
  if (!excerpt) return null;
  const text = excerpt.replace(/<\/?untrusted_document_content>/g, "").trim();
  return text.length > 0 ? text : null;
}

/**
 * A tool result that names an account-specific agreement as the rule it
 * applied. `sla_lookup` and `calculate_credit` already resolve the
 * agreement-vs-default question server-side and say so in plain text (see
 * `Toolbox.sla_lookup` / `Toolbox.calculate_credit`) -- this just reads that
 * back rather than re-deriving anything.
 */
interface DecisionEvidence {
  label: string;
  summary: string;
}

const DECISION_TOOLS: Record<string, string> = {
  sla_lookup: "SLA",
  credit_calculator: "credit",
};

function decisionEvidence(trace: ToolStep[]): DecisionEvidence[] {
  return trace
    .filter((step) => DECISION_TOOLS[step.tool] && /agreement/i.test(step.summary))
    .map((step) => ({ label: DECISION_TOOLS[step.tool], summary: step.summary }));
}

/** First `KI-###` token in a section heading, if the excerpt names one. */
function knownIssueId(text?: string): string | null {
  return text?.match(/KI-\d+/i)?.[0] ?? null;
}

/**
 * One source. `children` carries the optional excerpt/reasoning block a
 * group attaches once, not per card, so two chunks from the same document
 * don't repeat the same explanation.
 */
function SourceCard({
  src,
  isSelected,
  onSelect,
  cardRef,
}: {
  src: SourceItem;
  isSelected: boolean;
  onSelect?: () => void;
  cardRef?: (el: HTMLDivElement | null) => void;
}) {
  const sectionLine = [src.section, src.page ? `Page ${src.page}` : ""]
    .filter(Boolean)
    .join(" · ");

  return (
    <div
      ref={cardRef}
      onClick={onSelect}
      className={cn(
        "rounded-lg border p-3 cursor-pointer transition-colors",
        isSelected
          ? "border-[var(--accent-border)] bg-[var(--accent-soft)]"
          : "border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-hover)]",
      )}
    >
      <div className="flex items-start gap-2">
        <FileText className="w-3.5 h-3.5 text-[var(--text-3)] shrink-0 mt-[2px]" />
        <h4 className="flex-1 min-w-0 text-[12.5px] font-medium text-[var(--text)] leading-snug">
          {cleanSourceTitle(src.title)}
        </h4>
        <ExternalLink className="w-3.5 h-3.5 text-[var(--text-3)] shrink-0 mt-[2px]" />
      </div>

      <div className="mt-1.5 pl-[22px] text-[11.5px] text-[var(--text-3)]">
        {sourceMetaLine(src)}
        {src.account_id ? ` · ${src.account_id}` : ""}
      </div>

      {sectionLine && (
        <div className="mt-1.5 pl-[22px] text-[12px] text-[var(--text-2)]">
          {sectionLine}
        </div>
      )}
    </div>
  );
}

/** The excerpt + "why this governs" block a group attaches once, below its cards. */
function GovernsNote({
  governs,
  whyText,
  detailLines,
  excerpt,
}: {
  governs: string;
  whyText: string;
  detailLines?: string[];
  excerpt?: string | null;
}) {
  return (
    <div className="mt-1.5 rounded-md border border-[var(--border)] bg-[var(--app-bg)] px-2.5 py-2">
      {excerpt && (
        <p className="text-[12px] text-[var(--text-2)] leading-relaxed">
          “{excerpt.replace(/^["“]|["”]$/g, "")}”
        </p>
      )}
      <div className={cn(excerpt && "mt-2.5 pt-2.5 border-t border-[var(--border)]")}>
        <div className="text-[12px] font-medium text-[var(--success)]">{governs}</div>
        <p className="mt-1 text-[12px] text-[var(--text-2)] leading-relaxed">{whyText}</p>
        {detailLines?.map((line, i) => (
          <p key={i} className="mt-1 text-[11px] text-[var(--text-3)] leading-relaxed">
            {line}
          </p>
        ))}
      </div>
    </div>
  );
}

export function EvidenceTab({
  sources = [],
  toolTrace = [],
  selectedSource,
  onSelectSource,
}: EvidenceTabProps) {
  const refs = useRef<Record<string, HTMLDivElement | null>>({});
  const [showAll, setShowAll] = useState(false);

  // A citation click in the answer selects a source here -- bring it into view.
  useEffect(() => {
    if (!selectedSource?.id) return;
    refs.current[selectedSource.id]?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
  }, [selectedSource?.id]);

  if (sources.length === 0) {
    return (
      <div className="px-3.5 py-3">
        <div className="text-[12.5px] font-medium text-[var(--text-2)]">
          No sources yet
        </div>
        <p className="mt-1 text-[12px] text-[var(--text-3)] leading-relaxed">
          Sources used by ParcelPilot will appear here after an answer.
        </p>
      </div>
    );
  }

  const active = sources.filter((s) => !isContextOnly(s));
  const contextOnly = sources.filter(isContextOnly);

  // Every validated, active source is grouped by the kind of authority it
  // carries -- not collapsed into one "governing" pick -- so an answer that
  // rests on two different sources (an agreement for one clause, a product
  // guide for another) shows both as governing, each with its own reasoning.
  const agreementSources = active.filter((s) => s.document_type === "agreement");
  const policySources = active.filter(
    (s) => s.document_type === "sop" || s.document_type === "current_policy",
  );
  const guideSources = active.filter((s) => s.document_type === "product_guide");
  const otherSources = active.filter(
    (s) =>
      s.document_type !== "agreement" &&
      s.document_type !== "sop" &&
      s.document_type !== "current_policy" &&
      s.document_type !== "product_guide",
  );

  // Decisions (SLA, credit) that a structured tool resolved via an
  // account-specific agreement override -- read from the tool's own summary,
  // never re-derived. This is what lets the panel say an agreement governed
  // a decision even on a run where the model didn't also cite the agreement
  // PDF as a document passage.
  const decisions = decisionEvidence(toolTrace);
  const decisionLabels = decisions.map((d) => d.label);

  const attachTo = (group: SourceItem[]) => {
    const first = group[0];
    return {
      first,
      rest: group.slice(1),
    };
  };

  const groups: {
    key: string;
    heading: string;
    sources: SourceItem[];
    governs: string;
    whyText: string;
    detailLines?: string[];
  }[] = [];

  if (agreementSources.length > 0) {
    const { first } = attachTo(agreementSources);
    const decisionPhrase = decisionLabels.length
      ? ` for ${decisionLabels.join(" and ")}`
      : "";
    groups.push({
      key: "agreement",
      heading:
        decisionLabels.length === 1
          ? `Governing ${decisionLabels[0]} source`
          : "Governing agreement source",
      sources: agreementSources,
      governs: decisionLabels.length
        ? `✓ Governs ${decisionLabels.join(" and ")} decision`
        : "✓ Overrides general policy for this account",
      whyText: first.account_id
        ? `Customer-specific agreement terms for ${first.account_id} override the general policy default${decisionPhrase}.`
        : `Signed agreement clauses take precedence over general policy defaults${decisionPhrase}.`,
      detailLines: decisions.map((d) => `${d.label}: ${d.summary}`),
    });
  } else if (decisions.length > 0) {
    // An agreement governed a decision, but its chunk wasn't cited as a
    // document passage this run (e.g. the SLA number came straight from
    // `sla_lookup`, not from reading the PDF). Say what was actually applied
    // instead of a document card -- never claim no agreement was retrieved
    // when a tool result shows one was applied.
    groups.push({
      key: "agreement-applied",
      heading: `Governing ${decisionLabels.join(" and ")} source`,
      sources: [],
      governs: `✓ Governs ${decisionLabels.join(" and ")} decision`,
      whyText:
        "Resolved from the account's agreement record. The agreement document itself wasn't cited as a passage for this answer.",
      detailLines: decisions.map((d) => `${d.label}: ${d.summary}`),
    });
  }

  if (policySources.length > 0) {
    const { first } = attachTo(policySources);
    groups.push({
      key: "policy",
      heading: "Governing policy source",
      sources: policySources,
      governs: "✓ Sets the default rule applied here",
      whyText:
        agreementSources.length > 0 || decisions.length > 0
          ? `${kindLabel(first)} applies alongside the account's agreement where the agreement is silent.`
          : `No account-specific agreement override applies here, so the current ${kindLabel(
              first,
            ).toLowerCase()} of record applies.`,
    });
  }

  if (guideSources.length > 0) {
    const { first } = attachTo(guideSources);
    const ki = knownIssueId(guideSources.map((s) => s.section).join(" "));
    groups.push({
      key: "guide",
      heading: "Applicable product guidance",
      sources: guideSources,
      governs: ki ? `✓ Governs operational workaround (${ki})` : "✓ Governs operational guidance",
      whyText: ki
        ? `Documented in the current ${cleanSourceTitle(first.title)} as known issue ${ki}.`
        : `Documented in the current ${cleanSourceTitle(first.title)}.`,
    });
  }

  if (otherSources.length > 0) {
    groups.push({
      key: "other",
      heading: "Supporting evidence",
      sources: otherSources,
      governs: "✓ Supports this answer",
      whyText: "Retrieved as evidence for this question.",
    });
  }

  return (
    <div className="px-3.5 py-3.5 overflow-y-auto max-h-full">
      {showAll ? (
        /* Flat disclosure of everything retrieved, in rank order. */
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <SectionLabel>All sources ({sources.length})</SectionLabel>
            <button
              onClick={() => setShowAll(false)}
              className="text-[11.5px] text-[var(--text-2)] hover:text-[var(--text)] transition-colors cursor-pointer"
            >
              Back
            </button>
          </div>

          <div className="space-y-1.5">
            {sources.map((src, idx) => (
              <SourceCard
                key={src.id || idx}
                src={src}
                isSelected={selectedSource?.id === src.id}
                onSelect={() => onSelectSource?.(src)}
                cardRef={(el) => {
                  refs.current[src.id] = el;
                }}
              />
            ))}
          </div>
        </div>
      ) : (
        <div className="space-y-5">
          {/* Every validated, currently-active source, grouped by the kind
              of authority it carries -- an answer resting on two governing
              sources shows both, each with its own reasoning. */}
          {groups.map((group) => {
            const firstExcerpt =
              group.sources.length > 0 ? cleanExcerpt(group.sources[0].excerpt) : null;
            return (
              <div key={group.key}>
                <SectionLabel className="mb-1.5">{group.heading}</SectionLabel>

                {group.sources.length > 0 && (
                  <div className="space-y-1.5">
                    {group.sources.map((src, idx) => (
                      <SourceCard
                        key={src.id || idx}
                        src={src}
                        isSelected={selectedSource?.id === src.id}
                        onSelect={() => onSelectSource?.(src)}
                        cardRef={(el) => {
                          refs.current[src.id] = el;
                        }}
                      />
                    ))}
                  </div>
                )}

                <GovernsNote
                  governs={group.governs}
                  whyText={group.whyText}
                  detailLines={group.detailLines}
                  excerpt={firstExcerpt}
                />
              </div>
            );
          })}

          {/* Context only -- background that can never determine policy */}
          {contextOnly.length > 0 && (
            <div>
              <SectionLabel className="mb-1.5">Context only</SectionLabel>
              <div className="space-y-1.5">
                {contextOnly.map((src, idx) => (
                  <div key={src.id || idx}>
                    <SourceCard
                      src={src}
                      isSelected={selectedSource?.id === src.id}
                      onSelect={() => onSelectSource?.(src)}
                      cardRef={(el) => {
                        refs.current[src.id] = el;
                      }}
                    />
                    <div className="mt-1 pl-1 text-[11.5px] text-[var(--text-3)]">
                      {src.status === "deprecated" || src.lifecycle_state === "superseded"
                        ? "Superseded · Context only"
                        : "Historical resolution · Context only"}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <button
            onClick={() => setShowAll(true)}
            className="w-full flex items-center gap-2 px-3 h-[38px] rounded-lg border border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-hover)] hover:bg-[var(--surface-hover)] transition-colors cursor-pointer"
          >
            <Files className="w-3.5 h-3.5 text-[var(--text-3)] shrink-0" />
            <span className="flex-1 text-left text-[12.5px] text-[var(--text-2)]">
              View all sources ({sources.length})
            </span>
            <ChevronRight className="w-3.5 h-3.5 text-[var(--text-3)] shrink-0" />
          </button>
        </div>
      )}
    </div>
  );
}
