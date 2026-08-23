import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def customer(account_id="ACCT-001"):
    return {"user_id": "demo-customer", "role": "customer", "account_id": account_id}


def staff():
    return {"user_id": "support-1", "role": "support_agent", "account_id": None}


@pytest.mark.live_llm
def test_northstar_cancellation_contract_override():
    r = client.post("/api/chat", json={"message": "Can Northstar cancel ORD-1001 without a cancellation fee?", "principal": customer()})
    assert r.status_code == 200
    body = r.json()
    answer = body["answer"].lower()
    assert "no fee" in answer or "without" in answer or "no cancellation fee" in answer
    assert "agreement" in answer  # cites the contract, not just the default SOP
    assert {x["tool"] for x in body["tool_trace"]} >= {"structured_order_lookup", "document_search"}
    assert any(s["title"].startswith("05_Northstar") for s in body["sources"])


@pytest.mark.live_llm
def test_customer_cannot_read_another_account_order():
    r = client.post("/api/chat", json={"message": "Cancel ORD-2001", "principal": customer("ACCT-001")})
    assert r.status_code == 403


@pytest.mark.live_llm
def test_lumen_credit_uses_contract_rule():
    r = client.post("/api/chat", json={"message": "Is ORD-2002 eligible for a pickup credit?", "principal": customer("ACCT-002")})
    assert r.status_code == 200
    body = r.json()
    assert "300" in body["answer"]  # contract-specific amount, not the SOP default of 500
    credit_calls = [x for x in body["tool_trace"] if x["tool"] == "credit_calculator"]
    assert credit_calls and "LumenWorks" in credit_calls[0]["summary"]


@pytest.mark.live_llm
def test_escalation_requires_confirmation():
    r = client.post("/api/chat", json={"message": "Escalate TKT-501 as urgent outage", "principal": staff()})
    if r.status_code == 503:
        import time
        time.sleep(1)
        r = client.post("/api/chat", json={"message": "Escalate TKT-501 as urgent outage", "principal": staff()})
    body = r.json()
    assert r.status_code == 200 and body["pending_action"]
    token = body["pending_action"]["confirmation_token"]
    confirmed = client.post("/api/actions/confirm", json={"confirmation_token": token, "principal": staff()})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "created"


def test_sla_resolves_for_accounts_without_an_agreement():
    """ACCT-004 is Enterprise with no signed agreement: it must get the plan
    default, not Northstar's contract term, and not a table misread from the PDF."""
    from app.models import Principal
    from main import tools
    staff = Principal(user_id="support-1", role="support_agent")
    assert tools.sla_lookup(staff, "ACCT-004", "P1")["first_response_target"] == "30 minutes, 24x7"
    assert tools.sla_lookup(staff, "ACCT-001", "P1")["first_response_target"] == "15 minutes, 24x7"
    # Standard plan, also never exercised by the demo scenarios.
    assert tools.sla_lookup(staff, "ACCT-003", "P2")["first_response_target"] == "1 business day"


def test_credit_defaults_apply_to_accounts_without_contract_terms():
    """Accounts outside CONTRACT_CREDIT_TERMS must fall through to the SOP rule."""
    from app.models import Principal
    from main import tools
    staff = Principal(user_id="support-1", role="support_agent")
    beacon = tools.calculate_credit(staff, "ORD-3001")
    assert "SOP v4" in beacon["rule"]
    lumen = tools.calculate_credit(staff, "ORD-2002")
    assert lumen["eligible"] and lumen["proposed_amount_inr"] == 300


def test_customer_cannot_read_another_accounts_sla():
    from app.models import Principal
    from fastapi import HTTPException
    from main import tools
    import pytest
    cust = Principal(user_id="n", role="customer", account_id="ACCT-001")
    with pytest.raises(HTTPException) as exc:
        tools.sla_lookup(cust, "ACCT-002", "P1")
    assert exc.value.status_code == 403


def test_account_never_sees_another_accounts_agreement():
    """Retrieval must not surface a contract the account did not sign, even when
    its text is the best keyword match for the query."""
    from main import data
    for account_id in ["ACCT-003", "ACCT-004"]:  # neither has an agreement
        hits = data.search_documents("cancellation fee booked shipment", account_id)
        titles = {h.title for h in hits}
        assert not any("Agreement" in t for t in titles), titles
    # The signing account still gets its own contract, ranked first.
    own = data.search_documents("cancellation fee booked shipment", "ACCT-001")
    assert own[0].title == "05_Northstar_Logistics_Enterprise_Agreement.pdf"
    assert not any("LumenWorks" in h.title for h in own)


def test_deprecated_policy_is_never_retrieved():
    from main import data
    hits = data.search_documents("severity response targets enterprise growth standard")
    assert not any("DEPRECATED" in h.title for h in hits)


def test_graph_topology_matches_orchestration_contract():
    """The graph owns the loop; these are the edges that matter."""
    from main import agent
    g = agent.graph.get_graph()
    nodes = {n for n in g.nodes}
    assert {"planner", "execute_tool", "confirmation_gate", "finalize"} <= nodes
    edges = {(e.source, e.target) for e in g.edges}
    assert ("planner", "execute_tool") in edges          # planner -> tool
    assert ("execute_tool", "planner") in edges          # observation -> planner
    assert ("execute_tool", "confirmation_gate") in edges  # staging diverts to the gate
    assert ("confirmation_gate", "planner") in edges     # gate allows one final turn


@pytest.mark.live_llm
def test_confirmation_gate_fires_only_for_state_changing_actions():
    """A staged action must route through the gate; a read-only run must not."""
    from app.graph import build_graph
    from app.models import Principal
    from main import agent

    def path(principal, message, allowed):
        state = {"principal": principal, "allowed": allowed,
                 "messages": [{"role": "system", "content": agent._system_prompt(principal, allowed)},
                              {"role": "user", "content": message}],
                 "trace": [], "cited": [], "pending_action": None, "steps": 0, "force_final": False}
        seen = []
        for chunk in agent.graph.stream(state, stream_mode="updates", config={"recursion_limit": 22}):
            seen.extend(chunk.keys())
        return seen

    from app.agent import CUSTOMER_TOOLS, INTERNAL_TOOLS
    read_only = path(Principal(user_id="n", role="customer", account_id="ACCT-001"),
                     "Can I cancel ORD-1001 without a fee?", CUSTOMER_TOOLS)
    assert "confirmation_gate" not in read_only

    staged = path(Principal(user_id="support-1", role="support_agent"),
                  "Escalate TKT-501 as urgent, shipment creation is fully down", INTERNAL_TOOLS)
    assert "confirmation_gate" in staged
    # Once the gate fires, exactly one planner turn remains and no further tools run.
    assert staged[staged.index("confirmation_gate"):] == ["confirmation_gate", "planner", "finalize"]


def test_escalation_persists_across_restart():
    from app.models import Principal
    from app.tools import Toolbox
    from main import data

    staff_user = Principal(user_id="support-1", role="support_agent")
    t1 = Toolbox(data)
    prepared = t1.prepare_escalation(staff_user, ticket_id="TKT-501", account_id="ACCT-001", reason="Outage", severity="P1")
    token = prepared["action"]["confirmation_token"]

    # Brand new Toolbox instance simulating process restart
    t2 = Toolbox(data)
    confirmed = t2.confirm_action(staff_user, token)
    assert confirmed["status"] == "created"
    esc_id = confirmed["record"]["escalation_id"]
    assert esc_id.startswith("ESC-")

    # Brand new Toolbox instance again to verify confirmed state persists
    t3 = Toolbox(data)
    reconfirmed = t3.confirm_action(staff_user, token)
    assert reconfirmed["status"] == "created"
    assert reconfirmed["record"]["escalation_id"] == esc_id


def test_repeated_confirmation_is_idempotent():
    from app.models import Principal
    from main import tools

    staff_user = Principal(user_id="support-1", role="support_agent")
    prepared = tools.prepare_escalation(staff_user, ticket_id="TKT-501", account_id="ACCT-001", reason="Outage", severity="P1")
    token = prepared["action"]["confirmation_token"]

    first = tools.confirm_action(staff_user, token)
    second = tools.confirm_action(staff_user, token)
    assert first["status"] == "created"
    assert second["status"] == "created"
    assert first["record"]["escalation_id"] == second["record"]["escalation_id"]
    assert first["record"]["created_at"] == second["record"]["created_at"]


def test_concurrent_confirmations_create_single_escalation():
    import concurrent.futures
    from app.models import Principal
    from main import tools

    staff_user = Principal(user_id="support-1", role="support_agent")
    prepared = tools.prepare_escalation(staff_user, ticket_id="TKT-501", account_id="ACCT-001", reason="Outage", severity="P1")
    token = prepared["action"]["confirmation_token"]

    def do_confirm():
        return tools.confirm_action(staff_user, token)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(do_confirm)
        f2 = executor.submit(do_confirm)
        r1 = f1.result()
        r2 = f2.result()

    assert r1["status"] == "created"
    assert r2["status"] == "created"
    assert r1["record"]["escalation_id"] == r2["record"]["escalation_id"]


def test_confirm_invalid_token():
    import pytest
    from fastapi import HTTPException
    from app.models import Principal
    from main import tools

    staff_user = Principal(user_id="support-1", role="support_agent")
    with pytest.raises(HTTPException) as exc:
        tools.confirm_action(staff_user, "non-existent-token")
    assert exc.value.status_code == 404


def test_confirm_expired_token():
    import pytest
    from fastapi import HTTPException
    from app.models import Principal
    from main import tools

    staff_user = Principal(user_id="support-1", role="support_agent")
    unique_reason = "Outage expired token test verification"

    with tools._connection() as conn:
        initial_count = conn.execute(
            "SELECT count(*) AS c FROM escalations WHERE reason = %s", (unique_reason,)
        ).fetchone()["c"]

    prepared = tools.prepare_escalation(
        staff_user, ticket_id="TKT-501", account_id="ACCT-001", reason=unique_reason, severity="P1"
    )
    token = prepared["action"]["confirmation_token"]

    # Force expiration in DB
    with tools._connection() as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE pending_actions SET expires_at = now() - interval '1 minute' WHERE confirmation_token = %s",
                (token,),
            )

    with pytest.raises(HTTPException) as exc:
        tools.confirm_action(staff_user, token)
    assert exc.value.status_code == 410
    assert "expired" in str(exc.value.detail).lower()

    # Query DB to explicitly verify db_status and escalation_count
    with tools._connection() as conn:
        row = conn.execute(
            "SELECT status, escalation_id FROM pending_actions WHERE confirmation_token = %s", (token,)
        ).fetchone()
        db_status = row["status"]
        assert db_status == "expired"
        assert row["escalation_id"] is None

        escalation_count = conn.execute(
            "SELECT count(*) AS c FROM escalations WHERE reason = %s", (unique_reason,)
        ).fetchone()["c"]
        assert escalation_count == initial_count == 0


def test_different_staff_user_cannot_confirm():
    import pytest
    from fastapi import HTTPException
    from app.models import Principal
    from main import tools

    creator = Principal(user_id="support-1", role="support_agent")
    other_staff = Principal(user_id="support-2", role="support_agent")

    prepared = tools.prepare_escalation(creator, ticket_id="TKT-501", account_id="ACCT-001", reason="Outage", severity="P1")
    token = prepared["action"]["confirmation_token"]

    with pytest.raises(HTTPException) as exc:
        tools.confirm_action(other_staff, token)
    assert exc.value.status_code == 403


def test_customer_cannot_prepare_or_confirm():
    import pytest
    from fastapi import HTTPException
    from app.models import Principal
    from main import tools

    cust = Principal(user_id="cust-1", role="customer", account_id="ACCT-001")
    staff_user = Principal(user_id="support-1", role="support_agent")

    with pytest.raises(HTTPException) as exc1:
        tools.prepare_escalation(cust, ticket_id="TKT-501", account_id="ACCT-001", reason="Outage", severity="P1")
    assert exc1.value.status_code == 403

    prepared = tools.prepare_escalation(staff_user, ticket_id="TKT-501", account_id="ACCT-001", reason="Outage", severity="P1")
    token = prepared["action"]["confirmation_token"]

    with pytest.raises(HTTPException) as exc2:
        tools.confirm_action(cust, token)
    assert exc2.value.status_code == 403


def test_ticket_account_mismatch_uses_ground_truth():
    import pytest
    from fastapi import HTTPException
    from app.models import Principal
    from main import tools

    staff_user = Principal(user_id="support-1", role="support_agent")
    # TKT-501 belongs to ACCT-001; passing ACCT-002 is corrected to ACCT-001 server-side
    prepared = tools.prepare_escalation(staff_user, ticket_id="TKT-501", account_id="ACCT-002", reason="Outage", severity="P1")
    assert prepared["action"]["account_id"] == "ACCT-001"

    # Nonexistent ticket raises 404
    with pytest.raises(HTTPException) as exc:
        tools.prepare_escalation(staff_user, ticket_id="TKT-9999", account_id="ACCT-001", reason="Outage", severity="P1")
    assert exc.value.status_code == 404


# ------------------------------------------------------- answer completeness
#
# The system prompt's ANSWER COMPLETENESS rule: when retrieved evidence carries
# an applicable known issue, warning, exception, or workaround for the specific
# operation asked about, the final answer must state it alongside the primary
# decision -- not just the primary decision alone, and not a caveat that does
# not actually apply.


@pytest.mark.live_llm
def test_capability_answer_carries_its_applicable_known_issue():
    """Bulk Upload is technically supported, and the same evidence flags KI-208
    for exactly this operation at this scale. Both belong in one answer."""
    r = client.post("/api/chat", json={"message": "Can Axis Labs upload a 4,500-row CSV?", "principal": customer("ACCT-004")})
    assert r.status_code == 200
    answer = r.json()["answer"]
    assert "5,000" in answer or "5000" in answer, answer  # the primary eligibility fact
    assert "KI-208" in answer or "3,000" in answer or "3000" in answer, answer  # the applicable known issue / workaround


@pytest.mark.live_llm
def test_status_answer_carries_its_applicable_sync_delay_warning():
    """A 'still BOOKED after pickup' question must not be answered as a flat
    failure when the retrieved known issue explains a benign sync delay."""
    r = client.post("/api/chat", json={"message": "TKT-504 still shows BOOKED after pickup. Did pickup fail?", "principal": staff()})
    assert r.status_code == 200
    answer = r.json()["answer"].lower()
    assert any(phrase in answer for phrase in ("ki-211", "webhook", "sync", "20 minute")), answer


@pytest.mark.live_llm
def test_synthesis_does_not_invent_a_warning_when_none_is_retrieved():
    """A plain SLA lookup retrieves no known-issue evidence at all; the rule
    must not manufacture a caveat that was never in what came back."""
    r = client.post("/api/chat", json={"message": "What is Beacon Retail's P3 response target?", "principal": customer("ACCT-003")})
    assert r.status_code == 200
    answer = r.json()["answer"]
    assert "KI-" not in answer
    assert "known issue" not in answer.lower()


@pytest.mark.live_llm
def test_synthesis_mentions_only_the_known_issue_that_applies():
    """The product guide's known issues sit next to each other in the source
    pack and are often co-retrieved; a CSV-upload question must surface KI-208
    (the applicable one) and not KI-211 (a different operation's issue)."""
    r = client.post("/api/chat", json={"message": "Can Axis Labs upload a 4,500-row CSV?", "principal": customer("ACCT-004")})
    assert r.status_code == 200
    answer = r.json()["answer"]
    assert "KI-211" not in answer, answer


def test_transaction_rollback_leaves_no_partial_escalation(monkeypatch):
    import pytest
    from app.models import Principal
    from main import tools

    staff_user = Principal(user_id="support-1", role="support_agent")
    prepared = tools.prepare_escalation(staff_user, ticket_id="TKT-501", account_id="ACCT-001", reason="Outage", severity="P1")
    token = prepared["action"]["confirmation_token"]

    original_connection = tools._connection

    class FailingConnectionWrapper:
        def __init__(self, conn):
            self.conn = conn
        def transaction(self):
            return self.conn.transaction()
        def execute(self, query, params=None):
            if "UPDATE pending_actions" in str(query):
                raise RuntimeError("Simulated crash before pending_actions update")
            return self.conn.execute(query, params)

    class FailingContextManager:
        def __init__(self, cm):
            self.cm = cm
        def __enter__(self):
            real_conn = self.cm.__enter__()
            return FailingConnectionWrapper(real_conn)
        def __exit__(self, exc_type, exc_val, exc_tb):
            return self.cm.__exit__(exc_type, exc_val, exc_tb)

    def failing_connection():
        cm = original_connection()
        return FailingContextManager(cm)

    monkeypatch.setattr(tools, "_connection", failing_connection)

    with pytest.raises(RuntimeError, match="Simulated crash"):
        tools.confirm_action(staff_user, token)

    monkeypatch.undo()

    # Verify pending action is still pending and no escalation was committed for it
    with tools._connection() as conn:
        cur = conn.execute("SELECT status, escalation_id FROM pending_actions WHERE confirmation_token = %s", (token,))
        row = cur.fetchone()
        assert row["status"] == "pending"
        assert row["escalation_id"] is None
