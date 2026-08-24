import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatTimestamp(isoString?: string): string {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return isoString;
  }
}

export function formatFullDate(isoString?: string): string {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

/** Compact age for a conversation row: "Just now", "16m ago", "3h ago", "12 Aug". */
export function formatRelativeTime(isoString?: string): string {
  if (!isoString) return "";
  const then = new Date(isoString).getTime();
  if (isNaN(then)) return "";

  const seconds = Math.floor((Date.now() - then) / 1000);
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;

  return new Date(then).toLocaleDateString([], { month: "short", day: "numeric" });
}

/** Date-only rendering for a document's effective window: "Jan 1, 2026". */
export function formatEffectiveDate(isoString?: string | null): string {
  if (!isoString) return "";
  // Date-only strings ("2026-01-01") parse as UTC midnight, which renders as the
  // previous day west of Greenwich -- read the parts directly instead.
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoString);
  const d = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(isoString);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

/**
 * The one-line provenance under a source title: kind, then whichever date the
 * document actually carries. A historical ticket's `effective_from` is its
 * creation date, so it is labelled "Created" rather than implying a resolution
 * date the pipeline never recorded.
 */
export function sourceMetaLine(src: {
  document_type?: string;
  effective_from?: string | null;
}): string {
  const kinds: Record<string, string> = {
    agreement: "Agreement",
    sop: "SOP",
    current_policy: "Current policy",
    product_guide: "Product guide",
    historical_ticket: "Ticket",
  };
  const kind = kinds[src.document_type || ""] || "Policy";
  const when = formatEffectiveDate(src.effective_from);
  if (!when) return kind;

  const verb = src.document_type === "historical_ticket" ? "Created" : "Effective";
  return `${kind} · ${verb} ${when}`;
}

/**
 * Extracts and tags in-text superscript or bracket citations like [1], [2], ¹, ², etc.
 */
export function enrichCitations(text: string): string {
  return text;
}

/** Strips storage noise ("04_northstar_agreement.pdf") off a source title. */
export function cleanSourceTitle(title: string): string {
  return title
    .replace(/\.pdf$/i, "")
    .replace(/^\d+[_\-\s]+/, "")
    .replace(/[_]+/g, " ")
    .trim();
}

/**
 * Splits a principal into the two lines the UI shows everywhere the acting
 * identity appears: who (account or role name) and under what scope.
 * The role/account values come from the principal itself -- only the
 * parenthetical in the demo label is presentation text.
 */
export function principalDisplay(principal: {
  role: string;
  account_id: string | null;
  label?: string;
}): { name: string; scope: string } {
  const roleLabel =
    principal.role === "customer"
      ? "Customer"
      : principal.role === "ops_manager"
      ? "Ops manager"
      : "Support agent";

  const name = (principal.label || roleLabel).replace(/\s*\([^)]*\)\s*$/, "").trim();

  return { name, scope: principal.account_id || "All accounts" };
}
