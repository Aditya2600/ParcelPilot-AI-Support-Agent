import { z } from "zod";

export type Role = "customer" | "support_agent" | "ops_manager";

export interface Principal {
  user_id: string;
  role: Role;
  account_id: string | null;
  label?: string;
}

export const PrincipalSchema = z.object({
  user_id: z.string(),
  role: z.enum(["customer", "support_agent", "ops_manager"]),
  account_id: z.string().nullable().optional(),
  label: z.string().optional(),
});

export interface SourceItem {
  id: string;
  title: string;
  source_file: string;
  status: string; // 'current' | 'deprecated'
  lifecycle_state: string; // 'active' | 'superseded' | 'draft'
  page?: number | null;
  section?: string;
  document_type?: string; // 'agreement' | 'sop' | 'current_policy' | 'product_guide' | 'historical_ticket'
  account_id?: string | null;
  excerpt?: string;
  /** Ingested from the document's own "Effective:" line; null when it has none. */
  effective_from?: string | null;
  effective_to?: string | null;
  isGoverning?: boolean;
  overrideRule?: string;
}

export const SourceItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  source_file: z.string().optional(),
  status: z.string(),
  lifecycle_state: z.string().optional(),
  page: z.number().nullable().optional(),
  section: z.string().optional(),
  document_type: z.string().optional(),
  account_id: z.string().nullable().optional(),
  excerpt: z.string().optional(),
  effective_from: z.string().nullable().optional(),
  effective_to: z.string().nullable().optional(),
});

export interface ToolStep {
  tool: string;
  args?: Record<string, any>;
  thought?: string;
  summary: string;
}

export const ToolStepSchema = z.object({
  tool: z.string(),
  args: z.record(z.string(), z.any()).optional(),
  thought: z.string().optional(),
  summary: z.string(),
});

export interface PendingAction {
  action: string;
  ticket_id: string | null;
  account_id: string;
  reason: string;
  severity: "P1" | "P2" | "P3";
  prepared_by: string;
  confirmation_token: string;
  expires_at: string;
  expires_note?: string;
}

export const PendingActionSchema = z.object({
  action: z.string(),
  ticket_id: z.string().nullable(),
  account_id: z.string(),
  reason: z.string(),
  severity: z.enum(["P1", "P2", "P3"]),
  prepared_by: z.string(),
  confirmation_token: z.string(),
  expires_at: z.string(),
  expires_note: z.string().optional(),
});

export interface ConfirmedRecord {
  action: string;
  ticket_id: string | null;
  account_id: string;
  reason: string;
  severity: string;
  prepared_by: string;
  escalation_id: string;
  created_at: string;
}

export const ChatResponseSchema = z.object({
  answer: z.string(),
  confidence: z.enum(["high", "medium", "low"]),
  tool_trace: z.array(ToolStepSchema).default([]),
  sources: z.array(SourceItemSchema).default([]),
  pending_action: PendingActionSchema.nullable().optional(),
});

export type ChatResponse = z.infer<typeof ChatResponseSchema>;

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  confidence?: "high" | "medium" | "low";
  tool_trace?: ToolStep[];
  sources?: SourceItem[];
  pending_action?: PendingAction | null;
  confirmed_record?: ConfirmedRecord | null;
  /** True when this turn is a transport/backend failure rather than an answer. */
  error?: boolean;
  timestamp: string;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
  principal: Principal;
}

export interface ProactiveIssue {
  ticket_id: string;
  account: string;
  severity: "P1" | "P2" | "P3";
  urgency: "immediate" | "high" | "watch" | "normal";
  reason: string;
  owner: string;
}

export interface AccountMetadata {
  account_id: string;
  account_name: string;
  plan: string;
  status: string;
  csm: string;
  contract_file: string | null;
  premium_support: boolean;
  notes: string;
  sla_targets: {
    P1: { first_response_target: string; is_override: boolean; rule: string };
    P2: { first_response_target: string; is_override: boolean; rule: string };
    P3: { first_response_target: string; is_override: boolean; rule: string };
  };
  orders: {
    order_id: string;
    carrier: string;
    status: string;
    shipment_fee_inr: number;
    pickup_window_start: string;
    pickup_window_end: string;
    notes: string;
  }[];
  tickets: {
    ticket_id: string;
    status: string;
    subject: string;
    assigned_to: string;
    created_at: string;
  }[];
}

export interface AccountsResponse {
  snapshot: string;
  accounts: AccountMetadata[];
}
