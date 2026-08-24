import { Principal } from "@/types";

export const DEMO_PRINCIPALS: Principal[] = [
  {
    label: "Northstar Logistics (Customer)",
    user_id: "northstar-user",
    role: "customer",
    account_id: "ACCT-001",
  },
  {
    label: "LumenWorks (Customer)",
    user_id: "lumen-user",
    role: "customer",
    account_id: "ACCT-002",
  },
  {
    label: "Support Agent (Tier 2)",
    user_id: "support-1",
    role: "support_agent",
    account_id: null,
  },
  {
    label: "Operations Manager",
    user_id: "ops-1",
    role: "ops_manager",
    account_id: null,
  },
];

export const TEST_SCENARIOS = [
  {
    id: "ord-1001-cancellation",
    tag: "ORD-1001",
    category: "agreement",
    title: "Agreement override",
    prompt: "Can Northstar cancel ORD-1001 without a cancellation fee?",
    description: "Evaluates contract §2 waiver over standard SOP",
    recommendedPrincipal: "northstar-user",
  },
  {
    id: "acct-001-sla",
    tag: "SLA P1",
    category: "sla",
    title: "SLA override",
    prompt: "What is the P1 first-response SLA for ACCT-001?",
    description: "Validates 15-minute 24x7 agreement override vs plan default",
    recommendedPrincipal: "northstar-user",
  },
  {
    id: "ord-2002-credit",
    tag: "ORD-2002",
    category: "credit",
    title: "Service credit",
    prompt: "Calculate credit eligibility for delayed order ORD-2002",
    description: "Applies contract-specific late pickup credit calculation",
    recommendedPrincipal: "lumen-user",
  },
  {
    id: "tkt-505-escalation",
    tag: "TKT-505",
    category: "security",
    title: "Security escalation",
    prompt: "Escalate ticket TKT-505 immediately for API key exposure",
    description: "Stages P1 security incident with explicit human confirmation gate",
    recommendedPrincipal: "ops-1",
  },
  {
    id: "ki-208-bulk-upload",
    tag: "KI-208",
    category: "policy",
    title: "Bulk upload limit",
    prompt: "Why does bulk CSV upload fail for large files?",
    description: "Explains known issue KI-208 and recommended batch workaround",
    recommendedPrincipal: "support-1",
  },
];
