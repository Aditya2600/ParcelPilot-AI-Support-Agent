from __future__ import annotations

from typing import Any

from .llm import MedhaClient
from .models import Principal
from .sources import ParcelPilotData
from .tools import Toolbox

POLICY_FILE = "01_Support_Policy_v3_CURRENT.pdf"
KNOWN_ISSUES_FILE = "04_Product_Operations_Guide_and_Known_Issues.pdf"

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "severity": {"type": "string", "enum": ["P1", "P2", "P3"]},
        "urgency": {"type": "string", "enum": ["immediate", "high", "watch", "normal"]},
        "matched_known_issue": {"type": "string", "description": "A KI id if this ticket matches one, else empty."},
        "reason": {"type": "string", "description": "One sentence citing the policy clause or known issue."},
    },
    "required": ["severity", "urgency", "matched_known_issue", "reason"],
    "additionalProperties": False,
}

SYSTEM_TEMPLATE = """You triage one open ParcelPilot support ticket. Ground every judgement only in the policy text and known-issue list below; do not use outside knowledge of shipping, other companies, or generic SaaS conventions, and do not assume a ticket matches a known issue unless its content actually supports that.

SEVERITY DEFINITIONS (current Support Policy v3):
{severity_defs}

CURRENT KNOWN ISSUES (Product Operations Guide):
{known_issues}

Classify the ticket:
- severity: P1 only for a complete outage, a confirmed or suspected security/credential incident, or another event with immediate material business risk and no workaround. P2 for a major feature unavailable or badly degraded where a workaround exists, including anything matching an open known issue. P3 for anything else (how-to questions, minor defects, limited impact).
- urgency: "immediate" for P1; "high" for an active, unresolved known-issue match; "watch" for a known issue that is monitored/likely transient; "normal" otherwise.
- matched_known_issue: the KI id if the ticket's actual content matches one of the known issues above, else an empty string. A resolved known issue should not be matched to a new ticket unless the ticket's evidence specifically matches it.
- reason: one sentence, naming the policy clause or known issue id you relied on."""


class TicketTriage:
    """Classifies open tickets against the current policy text and known-issue list,
    instead of matching literal substrings from tickets already in the dataset.

    Each call is grounded in the actual current documents (re-read fresh, so an
    update to the policy or known-issues file changes triage without a code change)
    and reasons about the ticket's content, so a new ticket phrased differently from
    the ones in this sample dataset is classified on its substance, not its wording.
    """

    def __init__(self, data: ParcelPilotData, tools: Toolbox, llm: MedhaClient | None = None):
        self.data, self.tools = data, tools
        self.llm = llm or MedhaClient()

    def run(self, principal: Principal) -> list[dict[str, Any]]:
        tickets = self.tools.open_tickets(principal)
        if not tickets:
            return []
        system = SYSTEM_TEMPLATE.format(
            severity_defs=self._file_text(POLICY_FILE),
            known_issues=self._file_text(KNOWN_ISSUES_FILE),
        )
        items = []
        for t in tickets:
            user = (f"Ticket {t['ticket_id']} for {t['account_name']} ({t['plan']} plan).\n"
                    f"Subject: {t['subject']}\nDescription: {t['description']}")
            plan = self.llm.complete_json(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                TRIAGE_SCHEMA, schema_name="triage",
            )
            reason = plan["reason"]
            if plan.get("matched_known_issue"):
                reason = f"{reason} (matches {plan['matched_known_issue']})"
            items.append({"ticket_id": t["ticket_id"], "account": t["account_name"],
                          "severity": plan["severity"], "urgency": plan["urgency"],
                          "reason": reason, "owner": t["assigned_to"]})
        return items

    def _file_text(self, filename: str) -> str:
        sections = [c.text for c in self.data.chunks if c.title == filename]
        if not sections:
            raise ValueError(f"Expected source file {filename!r} was not loaded.")
        return "\n\n".join(sections)
