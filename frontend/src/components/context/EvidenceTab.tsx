"use client";

import React, { useEffect, useRef, useState } from "react";
import { ChevronRight, ExternalLink, FileText, Files } from "lucide-react";
import { SourceItem } from "@/types";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { cleanSourceTitle, cn, sourceMetaLine } from "@/lib/utils";

interface EvidenceTabProps {
  sources?: SourceItem[];
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
 * One source. `tone` marks a context-only card so a historical ticket never
 * looks like something the answer could have rested on.
 */
function SourceCard({
  src,
  isSelected,
  onSelect,
  cardRef,
  children,
}: {
  src: SourceItem;
  isSelected: boolean;
  onSelect?: () => void;
  cardRef?: (el: HTMLDivElement | null) => void;
  children?: React.ReactNode;
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

      {children}
    </div>
  );
}

export function EvidenceTab({
  sources = [],
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

  // Precedence: an account-scoped signed agreement outranks general policy.
  const governing =
    sources.find((s) => s.document_type === "agreement") ||
    sources.find((s) => s.title.toLowerCase().includes("agreement")) ||
    sources[0];

  const rest = sources.filter((s) => s !== governing);
  const supporting = rest.filter((s) => !isContextOnly(s));
  const contextOnly = rest.filter(isContextOnly);

  const governingIsAgreement =
    governing.document_type === "agreement" ||
    governing.title.toLowerCase().includes("agreement");

  // Explanation is derived from the retrieved metadata, never asserted blindly.
  const supersededTitles = supporting
    .filter(
      (s) => s.document_type === "sop" || s.document_type === "current_policy",
    )
    .map((s) => cleanSourceTitle(s.title));

  const whyText = governingIsAgreement
    ? governing.account_id
      ? `Customer-specific agreement terms for ${governing.account_id} override` +
        (supersededTitles.length
          ? ` the general ${supersededTitles.join(", ")}.`
          : " the general policy defaults.")
      : "Signed agreement clauses take precedence over general policy defaults."
    : `No account-specific agreement was retrieved for this question, so the current ${kindLabel(
        governing,
      ).toLowerCase()} of record applies.`;

  const governingExcerpt = cleanExcerpt(governing.excerpt);

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
          {/* Governing source, with the reasoning attached to the card itself */}
          <div>
            <SectionLabel className="mb-1.5">Governing source</SectionLabel>

            <SourceCard
              src={governing}
              isSelected={selectedSource?.id === governing.id}
              onSelect={() => onSelectSource?.(governing)}
              cardRef={(el) => {
                refs.current[governing.id] = el;
              }}
            >
              {governingExcerpt && (
                <div className="mt-2.5 rounded-md border border-[var(--border)] bg-[var(--app-bg)] px-2.5 py-2">
                  <p className="text-[12px] text-[var(--text-2)] leading-relaxed">
                    “{governingExcerpt.replace(/^["“]|["”]$/g, "")}”
                  </p>
                </div>
              )}

              <div className="mt-3 pt-3 border-t border-[var(--border)]">
                <div className="text-[12.5px] font-medium text-[var(--text)]">
                  Why this governs
                </div>
                <p className="mt-1 text-[12px] text-[var(--text-2)] leading-relaxed">
                  {whyText}
                </p>
              </div>
            </SourceCard>
          </div>

          {/* Supporting evidence -- may inform the answer, but does not govern it */}
          {supporting.length > 0 && (
            <div>
              <SectionLabel className="mb-1.5">
                Supporting evidence
              </SectionLabel>
              <div className="space-y-1.5">
                {supporting.map((src, idx) => (
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
          )}

          {/* Context only -- background that can never determine policy */}
          {contextOnly.length > 0 && (
            <div>
              <SectionLabel className="mb-1.5">Context only</SectionLabel>
              <div className="space-y-1.5">
                {contextOnly.map((src, idx) => (
                  <SourceCard
                    key={src.id || idx}
                    src={src}
                    isSelected={selectedSource?.id === src.id}
                    onSelect={() => onSelectSource?.(src)}
                    cardRef={(el) => {
                      refs.current[src.id] = el;
                    }}
                  >
                    <div className="mt-1.5 pl-[22px] text-[11.5px] text-[var(--text-3)]">
                      {src.status === "deprecated" ||
                      src.lifecycle_state === "superseded"
                        ? "Superseded · Context only"
                        : "Historical resolution · Context only"}
                    </div>
                  </SourceCard>
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
