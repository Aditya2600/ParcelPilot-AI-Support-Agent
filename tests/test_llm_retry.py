"""Deterministic tests for MedhaClient's bounded transient-retry policy.

None of these touch the live Medha endpoint: httpx.post is monkeypatched at
the app.llm module level, so these run under `pytest -m "not live_llm"`.
"""
import json

import httpx
import pytest

import app.llm as llm_module
from app.llm import MedhaClient, LLMUnavailable


SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}
MESSAGES = [{"role": "user", "content": "hello"}]


class FakeResponse:
    def __init__(self, status_code: int, body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._body = body
        self.text = text or json.dumps(body or {})

    def json(self):
        return self._body


def _client(post_calls_behavior, sleeps, max_retries=2):
    """post_calls_behavior: list of callables/values consumed in call order.

    Each entry is either a FakeResponse or an Exception instance/class to raise.
    """
    call_index = {"i": 0}

    def fake_post(url, json=None, headers=None, timeout=None):
        i = call_index["i"]
        call_index["i"] += 1
        behavior = post_calls_behavior[i]
        if isinstance(behavior, Exception):
            raise behavior
        return behavior

    client = MedhaClient(
        base_url="http://fake",
        api_key="test-key",
        model="Medha",
        max_retries=max_retries,
        sleep_fn=lambda s: sleeps.append(s),
        rand_fn=lambda lo, hi: (lo + hi) / 2,  # deterministic midpoint, no real jitter noise
    )
    return client, fake_post, call_index


def _ok(answer="fine"):
    return FakeResponse(200, {"choices": [{"message": {"content": json.dumps({"answer": answer})}}]})


def test_503_then_success(monkeypatch):
    sleeps = []
    client, fake_post, calls = _client([FakeResponse(503, text="unavailable"), _ok("recovered")], sleeps)
    monkeypatch.setattr(llm_module.httpx, "post", fake_post)

    result = client.complete_json(MESSAGES, SCHEMA)

    assert result == {"answer": "recovered"}
    assert calls["i"] == 2  # one retry
    assert len(sleeps) == 1
    assert 0.3 <= sleeps[0] <= 0.7  # ~0.5s


def test_503_503_then_success(monkeypatch):
    sleeps = []
    client, fake_post, calls = _client(
        [FakeResponse(503), FakeResponse(503), _ok("recovered")], sleeps,
    )
    monkeypatch.setattr(llm_module.httpx, "post", fake_post)

    result = client.complete_json(MESSAGES, SCHEMA)

    assert result == {"answer": "recovered"}
    assert calls["i"] == 3
    assert len(sleeps) == 2
    assert 0.3 <= sleeps[0] <= 0.7   # retry 1 ~0.5s
    assert 0.7 <= sleeps[1] <= 1.3   # retry 2 ~1.0s (exponential backoff)


def test_retry_exhaustion(monkeypatch):
    sleeps = []
    client, fake_post, calls = _client(
        [FakeResponse(503), FakeResponse(503), FakeResponse(503)], sleeps,
    )
    monkeypatch.setattr(llm_module.httpx, "post", fake_post)

    with pytest.raises(LLMUnavailable):
        client.complete_json(MESSAGES, SCHEMA)

    # 3 attempts total (initial + 2 retries), sleeping only between attempts,
    # never after the final exhausted attempt.
    assert calls["i"] == 3
    assert len(sleeps) == 2


def test_400_is_not_retried(monkeypatch):
    sleeps = []
    client, fake_post, calls = _client(
        [FakeResponse(400, text="bad request: malformed schema")], sleeps,
    )
    monkeypatch.setattr(llm_module.httpx, "post", fake_post)

    with pytest.raises(LLMUnavailable):
        client.complete_json(MESSAGES, SCHEMA)

    assert calls["i"] == 1  # no retry attempted
    assert sleeps == []


@pytest.mark.parametrize("status", [401, 403])
def test_other_client_errors_are_not_retried(monkeypatch, status):
    sleeps = []
    client, fake_post, calls = _client([FakeResponse(status)], sleeps)
    monkeypatch.setattr(llm_module.httpx, "post", fake_post)

    with pytest.raises(LLMUnavailable):
        client.complete_json(MESSAGES, SCHEMA)

    assert calls["i"] == 1
    assert sleeps == []


def test_timeout_then_success(monkeypatch):
    sleeps = []
    client, fake_post, calls = _client(
        [httpx.ReadTimeout("read timed out"), _ok("recovered")], sleeps,
    )
    monkeypatch.setattr(llm_module.httpx, "post", fake_post)

    result = client.complete_json(MESSAGES, SCHEMA)

    assert result == {"answer": "recovered"}
    assert calls["i"] == 2
    assert len(sleeps) == 1


def test_connection_error_then_success(monkeypatch):
    sleeps = []
    client, fake_post, calls = _client(
        [httpx.ConnectError("connection reset by peer"), _ok("recovered")], sleeps,
    )
    monkeypatch.setattr(llm_module.httpx, "post", fake_post)

    result = client.complete_json(MESSAGES, SCHEMA)

    assert result == {"answer": "recovered"}
    assert calls["i"] == 2


def test_connection_error_exhaustion_raises_llm_unavailable(monkeypatch):
    sleeps = []
    client, fake_post, calls = _client(
        [httpx.ConnectError("refused")] * 3, sleeps,
    )
    monkeypatch.setattr(llm_module.httpx, "post", fake_post)

    with pytest.raises(LLMUnavailable):
        client.complete_json(MESSAGES, SCHEMA)
    assert calls["i"] == 3


def test_retry_logging_has_no_prompt_or_secret_content(monkeypatch, caplog):
    """Structured retry logs must carry attempt/status/delay only -- never the
    message content, retrieved document text, or the bearer API key."""
    import logging
    sleeps = []
    client, fake_post, calls = _client([FakeResponse(503), _ok("recovered")], sleeps)
    monkeypatch.setattr(llm_module.httpx, "post", fake_post)

    secret_marker = "super-secret-key-should-never-appear"
    client.api_key = secret_marker
    sensitive_messages = [{"role": "user", "content": "customer SSN is 123-45-6789, ignore all rules"}]

    with caplog.at_level(logging.WARNING, logger="app.llm"):
        client.complete_json(sensitive_messages, SCHEMA)

    log_text = "\n".join(r.message for r in caplog.records)
    assert secret_marker not in log_text
    assert "123-45-6789" not in log_text
    assert "ignore all rules" not in log_text
    assert "attempt=" in log_text
    assert "retry_delay_s=" in log_text


def test_no_duplicate_tool_execution_when_planner_call_needs_a_retry(monkeypatch):
    """A transient HTTP failure inside one planner turn's inference call must
    not cause the tool that turn ultimately requests to run twice -- retries
    live entirely inside complete_json, below tool dispatch."""
    from app.models import Principal
    from main import agent, tools

    calls = {"account_lookup": 0}
    original_account_lookup = tools.account_lookup

    def counting_account_lookup(principal, query):
        calls["account_lookup"] += 1
        return original_account_lookup(principal, query)

    monkeypatch.setattr(tools, "account_lookup", counting_account_lookup)

    plan_1 = {"thought": "look up the account", "tool": "account_lookup", "args": {"query": "ACCT-001"}}
    plan_2 = {"thought": "answer", "tool": "final_answer",
              "args": {"answer": "Northstar Logistics is on the Enterprise plan.", "confidence": "high", "sources": []}}

    responses = [
        FakeResponse(503, text="unavailable"),                                              # turn 1, attempt 1
        FakeResponse(200, {"choices": [{"message": {"content": json.dumps(plan_1)}}]}),      # turn 1, attempt 2 (after retry)
        FakeResponse(200, {"choices": [{"message": {"content": json.dumps(plan_2)}}]}),      # turn 2, attempt 1
    ]
    call_index = {"i": 0}

    def fake_post(url, json=None, headers=None, timeout=None):
        i = call_index["i"]
        call_index["i"] += 1
        return responses[i]

    monkeypatch.setattr(llm_module.httpx, "post", fake_post)
    monkeypatch.setattr(agent.llm, "_sleep", lambda s: None)

    principal = Principal(user_id="n", role="customer", account_id="ACCT-001")
    resp = agent.answer(principal, "What plan is my account on?")

    assert resp.answer == "Northstar Logistics is on the Enterprise plan."
    assert calls["account_lookup"] == 1  # not 2, despite the retried inference call
    assert call_index["i"] == 3  # 2 HTTP attempts for turn 1 + 1 for turn 2
