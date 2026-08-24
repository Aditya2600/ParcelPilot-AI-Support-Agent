import { ToolStep } from "@/types";

/**
 * Human-readable name for a tool as it appears in the API's tool_trace.
 * The backend records either the planner's tool name or the tool record's own
 * name (e.g. `order_lookup` is recorded as `structured_order_lookup`), so both
 * spellings map to the same label.
 */
export function toolDisplayName(tool: string): string {
  const names: Record<string, string> = {
    document_search: "Document search",
    account_lookup: "Account lookup",
    order_lookup: "Order lookup",
    structured_order_lookup: "Order lookup",
    ticket_lookup: "Ticket lookup",
    structured_ticket_lookup: "Ticket lookup",
    calculate_credit: "Credit calculation",
    credit_calculator: "Credit calculation",
    sla_lookup: "SLA lookup",
    list_open_tickets: "Open ticket scan",
    prepare_escalation: "Escalation prepared",
    final_answer: "Answer generated",
  };

  return (
    names[tool] ||
    tool.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())
  );
}

/** A trace step the backend recorded as failed reads "Failed: ..." in its summary. */
export function isFailedStep(step: ToolStep): boolean {
  return /^failed:/i.test(step.summary || "");
}
