from __future__ import annotations

import json
from typing import Any, Optional, TYPE_CHECKING, TypedDict

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:  # avoid a circular import at runtime
    from .agent import SupportAgent

MAX_STEPS = 6

GATE_NUDGE = ("The action above is STAGED ONLY and has not been created. Reply now with "
              "final_answer: say what you staged, and that a human must confirm it explicitly. "
              "Do not claim it has been created, escalated, or actioned.")


class AgentState(TypedDict, total=False):
    """What flows between nodes.

    Deliberately plain data: the graph carries the conversation, the trace and the
    staged action, while every decision about *what is allowed* stays in `Toolbox`.
    """
    principal: Any
    allowed: list[str]
    messages: list[dict[str, str]]
    trace: list[dict[str, Any]]
    cited: list[str]
    authoritative_evidence: list[dict[str, Any]]
    context_evidence: list[dict[str, Any]]
    pending_action: Optional[dict[str, Any]]
    plan: dict[str, Any]
    steps: int
    force_final: bool


def build_graph(agent: "SupportAgent"):
    """Wire the planner/tool/observation cycle as an explicit state machine.

        planner -> execute_tool -> (observation) -> planner -> ... -> finalize
                        |
                        +-> confirmation_gate -> planner (final answer only)

    The loop is the only thing LangGraph owns. Planning still goes through
    `MedhaClient` with the same JSON schema, tools still run through `Toolbox`,
    and source precedence is unchanged. Making the cycle a graph buys one real
    safety property: staging an action is an edge into `confirmation_gate`, which
    permanently drops the planner to a final-answer-only schema. After an action
    is staged the model is structurally unable to call another tool, rather than
    merely instructed not to.
    """

    def planner(state: AgentState) -> AgentState:
        # Narrow the schema on the last permitted step, or once an action is
        # staged, so the run always terminates with an answer.
        last = state["steps"] >= MAX_STEPS - 1
        allowed = ["final_answer"] if (last or state.get("force_final")) else state["allowed"]
        plan = agent.llm.complete_json(state["messages"], agent._schema(allowed))
        return {"plan": plan, "steps": state["steps"] + 1}

    def execute_tool(state: AgentState) -> AgentState:
        plan = state["plan"]
        tool = str(plan.get("tool") or "final_answer")
        args = plan.get("args") or {}
        thought = str(plan.get("thought", "")).strip()

        # Scope violations raise out of here, exactly as before, so a cross-account
        # request still surfaces as HTTP 403 instead of becoming an observation.
        observation, record = agent._run_tool(state["principal"], tool, args)

        cited = list(state.get("cited") or [])
        auth_evidence = list(state.get("authoritative_evidence") or [])
        ctx_evidence = list(state.get("context_evidence") or [])

        if tool == "document_search":
            hits = record.get("hits", [])
            context = record.get("context_only", [])
            cited.extend(h["source_id"] for h in hits)
            auth_evidence.extend(hits)
            ctx_evidence.extend(context)

        pending = state.get("pending_action")
        if tool == "prepare_escalation" and record.get("action"):
            pending = record["action"]

        trace = state["trace"] + [{
            "tool": record.get("tool", tool), "args": agent._public_args(args),
            "thought": thought, "summary": agent._summarize(tool, record),
        }]
        messages = state["messages"] + [
            {"role": "assistant", "content": json.dumps(plan)},
            {"role": "user", "content": f"OBSERVATION from {tool}:\n{observation}"},
        ]
        return {
            "messages": messages,
            "trace": trace,
            "cited": cited,
            "authoritative_evidence": auth_evidence,
            "context_evidence": ctx_evidence,
            "pending_action": pending,
        }

    def confirmation_gate(state: AgentState) -> AgentState:
        """Reached the moment a state-changing action is staged.

        Latches the planner into final-answer-only mode and tells it plainly that
        nothing has been created yet, so the reply cannot narrate the action as done.
        """
        return {
            "force_final": True,
            "messages": state["messages"] + [{"role": "user", "content": GATE_NUDGE}],
        }

    def finalize(state: AgentState) -> AgentState:
        return state

    def route_after_planner(state: AgentState) -> str:
        """Stop when the planner answers, or when it names a tool its role lacks."""
        tool = str(state["plan"].get("tool") or "final_answer")
        if tool == "final_answer" or tool not in state["allowed"]:
            return "finalize"
        return "execute_tool"

    def route_after_tool(state: AgentState) -> str:
        if state.get("pending_action") and not state.get("force_final"):
            return "confirmation_gate"
        if state["steps"] >= MAX_STEPS:
            return "finalize"
        return "planner"

    graph = StateGraph(AgentState)
    graph.add_node("planner", planner)
    graph.add_node("execute_tool", execute_tool)
    graph.add_node("confirmation_gate", confirmation_gate)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", route_after_planner,
                                {"execute_tool": "execute_tool", "finalize": "finalize"})
    graph.add_conditional_edges("execute_tool", route_after_tool,
                                {"planner": "planner", "confirmation_gate": "confirmation_gate",
                                 "finalize": "finalize"})
    graph.add_edge("confirmation_gate", "planner")
    graph.add_edge("finalize", END)
    return graph.compile()
