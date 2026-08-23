import pytest
from fastapi.testclient import TestClient

from app.models import Principal
from app.rag.retriever import GOVERNING_AGREEMENT_TIER, POLICY_TIER, resolve_authority
from app.rag.store import CandidateChunk
from main import app, data, tools

client = TestClient(app)

NORTHSTAR = "05_Northstar_Logistics_Enterprise_Agreement.pdf"
LUMENWORKS = "06_LumenWorks_Service_Agreement.pdf"
POLICY_V3 = "01_Support_Policy_v3_CURRENT.pdf"
POLICY_V2 = "02_Support_Policy_v2_DEPRECATED.pdf"
SOP_V4 = "03_Cancellation_and_Service_Credit_SOP_v4.pdf"


def customer(account_id="ACCT-001"):
    return {"user_id": "demo-customer", "role": "customer", "account_id": account_id}


def staff():
    return {"user_id": "support-1", "role": "support_agent", "account_id": None}


@pytest.mark.live_llm
def test_scenario_a_correct_answer_and_correct_citation_live_medha():
    """A. Correct answer + correct citation.
    
    Northstar cancellation override:
    - correct answer mentioning no cancellation fee
    - Northstar agreement cited
    - LumenWorks agreement is NOT cited
    """
    resp = client.post(
        "/api/chat",
        json={"message": "Can Northstar cancel ORD-1001 without a cancellation fee?", "principal": customer("ACCT-001")},
    )
    assert resp.status_code == 200
    body = resp.json()
    answer = body["answer"].lower()
    assert "no fee" in answer or "without" in answer or "no cancellation fee" in answer
    assert any(s["title"].startswith("05_Northstar") for s in body["sources"])
    assert not any("LumenWorks" in s["title"] for s in body["sources"])
    # Check provenance fields
    ns_source = next(s for s in body["sources"] if s["title"].startswith("05_Northstar"))
    assert ns_source["document_type"] == "agreement"
    assert ns_source["status"] == "current"
    assert ns_source["account_id"] == "ACCT-001"


@pytest.mark.live_llm
def test_scenario_b_default_rule_citation_live_medha():
    """B. Default-rule citation.
    
    Beacon cancellation:
    - current SOP v4 cited
    - no customer agreement cited
    """
    resp = client.post(
        "/api/chat",
        json={"message": "Can Beacon cancel ORD-3001 without a fee?", "principal": customer("ACCT-003")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert any("03_Cancellation_and_Service_Credit_SOP_v4" in s["title"] for s in body["sources"])
    assert not any(s["document_type"] == "agreement" for s in body["sources"])
    assert not any("Northstar" in s["title"] or "LumenWorks" in s["title"] for s in body["sources"])


@pytest.mark.live_llm
def test_scenario_c_sla_citations_live_medha():
    """C. SLA citation.
    
    - default plan SLA -> Support Policy v3
    - customer-specific SLA override -> customer agreement
    """
    # 1. Default plan SLA for Standard account (ACCT-003)
    resp_default = client.post(
        "/api/chat",
        json={"message": "What is our SLA first response target for P2 issues?", "principal": customer("ACCT-003")},
    )
    assert resp_default.status_code == 200
    body_default = resp_default.json()
    # Check that tool trace or sources reflect default SLA lookup / Support Policy v3
    assert any("sla_lookup" in t["tool"] or "document_search" in t["tool"] for t in body_default["tool_trace"])
    assert not any(s["document_type"] == "agreement" for s in body_default.get("sources", []))

    # 2. Contractual SLA override for Northstar (ACCT-001)
    resp_override = client.post(
        "/api/chat",
        json={"message": "What is our SLA first response target for P1 issues?", "principal": customer("ACCT-001")},
    )
    assert resp_override.status_code == 200
    body_override = resp_override.json()
    assert any("15 minutes" in t.get("summary", "") or "Northstar" in t.get("summary", "") for t in body_override["tool_trace"]) or "15 minutes" in body_override["answer"]


def test_scenario_d_deprecated_source_rejection():
    """D. Deprecated source rejection.
    
    Force a case where v2 is semantically relevant.
    Assert:
    - v2 cannot appear as final governing citation
    - v3 is used instead
    """
    query = "first response targets enterprise growth standard"
    hits = data.search_documents(query, account_id="ACCT-003")
    assert not any("DEPRECATED" in h.title or "v2" in h.title for h in hits)
    assert any("Support_Policy_v3" in h.title for h in hits)

    # Server-side validation check
    fake_v2_evidence = {
        "source_id": "02_Support_Policy_v2_DEPRECATED.pdf@v1#1",
        "chunk_id": "02_Support_Policy_v2_DEPRECATED.pdf@v1#1",
        "title": "02_Support_Policy_v2_DEPRECATED.pdf",
        "source_file": "02_Support_Policy_v2_DEPRECATED.pdf",
        "lifecycle_state": "superseded",
        "status": "deprecated",
        "document_type": "current_policy",
        "authority": 80,
    }
    from main import agent
    valid_chunks, _ = agent._validate_citations(
        Principal(user_id="cust", role="customer", account_id="ACCT-003"),
        claimed_ids=["02_Support_Policy_v2_DEPRECATED.pdf@v1#1"],
        trace=[],
        authoritative_evidence=[fake_v2_evidence],
        context_evidence=[],
    )
    assert not any("v2" in c.source_id or "DEPRECATED" in c.source_id for c in valid_chunks)


def test_scenario_e_historical_ticket_cannot_govern():
    """E. Historical ticket cannot govern.
    
    Historical ticket contains matching/wrong guidance.
    Assert:
    - may appear in context_evidence
    - never appears as authoritative citation
    - cannot independently support the final policy claim
    """
    cust = Principal(user_id="cust", role="customer", account_id="ACCT-001")
    search_res = tools.document_search(cust, "was a cancellation fee applied ninety minutes after booking", limit=8)
    assert all(h["document_type"] != "historical_ticket" for h in search_res["hits"])
    assert any(c["document_type"] == "historical_ticket" for c in search_res["context_only"])

    # Final response check: historical ticket in context_only never makes it into ChatResponse.sources
    from main import agent
    resp = agent._finalize(
        cust,
        {"answer": "A fee was charged in past ticket", "confidence": "high", "citations": ["ticket:TKT-450#1"]},
        trace=[{"tool": "document_search", "summary": "1 context-only"}],
        authoritative_evidence=[],
        context_evidence=search_res["context_only"],
        pending_action=None,
    )
    assert not any("ticket" in s["id"] for s in resp.sources)
    # Since authoritative evidence was empty and document_search found no governing passage,
    # insufficient-evidence fallback activates
    assert "authoritative evidence" in resp.answer.lower()
    assert resp.confidence == "low"


def test_scenario_f_cross_tenant_citation_rejection():
    """F. Cross-tenant citation rejection.
    
    ACCT-003 customer:
    - no Northstar/LumenWorks citation can appear
    - validated at server side, not just model output
    """
    from main import agent
    cust_beacon = Principal(user_id="cust", role="customer", account_id="ACCT-003")

    fake_northstar_evidence = {
        "source_id": "05_Northstar_Logistics_Enterprise_Agreement.pdf@v1#1",
        "chunk_id": "05_Northstar_Logistics_Enterprise_Agreement.pdf@v1#1",
        "title": "05_Northstar_Logistics_Enterprise_Agreement.pdf",
        "source_file": "05_Northstar_Logistics_Enterprise_Agreement.pdf",
        "lifecycle_state": "active",
        "status": "current",
        "document_type": "agreement",
        "account_id": "ACCT-001",
        "authority": 100,
    }

    valid_chunks, _ = agent._validate_citations(
        cust_beacon,
        claimed_ids=["05_Northstar_Logistics_Enterprise_Agreement.pdf@v1#1"],
        trace=[],
        authoritative_evidence=[fake_northstar_evidence],
        context_evidence=[],
    )
    assert not any("Northstar" in c.source_id for c in valid_chunks)
    assert len(valid_chunks) == 0


def test_scenario_g_invented_citation_id_rejection():
    """G. Invented citation ID.
    
    Simulate model output referencing a chunk that was not retrieved.
    Assert citation validation rejects it.
    """
    from main import agent
    cust = Principal(user_id="cust", role="customer", account_id="ACCT-001")
    valid_chunks, _ = agent._validate_citations(
        cust,
        claimed_ids=["non_existent_fake_document.pdf#999"],
        trace=[],
        authoritative_evidence=[],
        context_evidence=[],
    )
    assert len(valid_chunks) == 0


@pytest.mark.live_llm
def test_scenario_h_no_authoritative_evidence_live_medha():
    """H. No authoritative evidence.
    
    Query for a policy fact unsupported by eligible authoritative evidence.
    Assert:
    - no fabricated citation
    - no confident unsupported answer
    - returns insufficient-evidence / human-review response
    """
    resp = client.post(
        "/api/chat",
        json={"message": "What is the policy on shipping live penguins to Antarctica?", "principal": customer("ACCT-003")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert any(
        phrase in body["answer"].lower()
        for phrase in ["authoritative evidence", "do not have", "escalat", "human", "specialist", "support", "review"]
    )
    assert body["confidence"] == "low"
    assert len(body["sources"]) == 0


def test_scenario_i_citation_stability():
    """I. Citation stability.
    
    Same deterministic retrieval scenario twice:
    - citations resolve to valid stable chunk/source identifiers
    """
    query = "service credit for a missed pickup"
    first = data.hybrid_search(query, customer("ACCT-002"), top_k=5)
    second = data.hybrid_search(query, customer("ACCT-002"), top_k=5)
    assert [h.chunk_id for h in first.authoritative] == [h.chunk_id for h in second.authoritative]
    assert len(first.authoritative) > 0
    for h in first.authoritative:
        assert h.chunk_id.startswith(h.document_version_id + "#")
        assert h.source_file and h.section
